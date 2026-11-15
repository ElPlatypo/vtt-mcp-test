"""
Streaming narration server for the Foundry MCP bridge.

Runs faster-qwen3-tts (CUDA graphs) and streams raw 16-bit mono PCM while it generates, so the first
audio arrives in about half a second. It loads a model on first use and keeps it until /unload.

Voices: a preset speaker (CustomVoice), or a SAVED voice. A saved voice is made once from a description
(VoiceDesign writes a short reference clip, re-made until its pace is natural) and is then cloned for every
line (Base model), so each character keeps one steady voice and speaks at the pace of its reference.

Start it with the Python of the venv that has faster-qwen3-tts, for example:
    /opt/fq/bin/python server.py --port 8190

Normally the claude_tts ComfyUI node starts it and exposes it through ComfyUI's own port.

API
    GET  /health          {"ok": true, "loaded": ["clone/1.7B"], "busy": false}
    GET  /voices          {"speakers": [...], "languages": [...], "saved": [...], "creating": [...]}
    POST /voices/create   JSON {name, description, text?, language?, replace?, wait?} -> starts making a saved voice
    GET  /voices/{name}   one saved voice (or its creation status)
    DELETE /voices/{name} removes a saved voice
    POST /speak           JSON {text, mode: custom|design|clone, speaker, voice, instruct, language, model, chunk_size}
                          -> body: raw PCM s16le mono, streamed. Headers: X-Sample-Rate, X-Channels
    POST /unload          frees the GPU memory
"""
import argparse
import asyncio
import json
import os
import queue as thread_queue
import re
import subprocess
import urllib.request

# ComfyUI sets the cudaMallocAsync allocator for its own process, and a server it starts inherits that. CUDA graphs
# (what makes this server fast) cannot be captured with it, so start from the default allocator.
for _name in ("PYTORCH_CUDA_ALLOC_CONF", "PYTORCH_ALLOC_CONF"):
    os.environ.pop(_name, None)

import threading
import time
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

MODELS_DIR = os.environ.get("CLAUDE_TTS_MODELS", "/root/ComfyUI/models/qwen-tts")
VOICES_DIR = os.environ.get("CLAUDE_TTS_VOICES", os.path.join(MODELS_DIR, "voices"))
COMFY_URL = os.environ.get("CLAUDE_TTS_COMFY", "http://127.0.0.1:8188")
MODEL_NAMES = {
    ("custom", "1.7B"): "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    ("custom", "0.6B"): "Qwen3-TTS-12Hz-0.6B-CustomVoice",
    ("design", "1.7B"): "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    ("clone", "1.7B"): "Qwen3-TTS-12Hz-1.7B-Base",
}
SPEAKERS = ["Aiden", "Dylan", "Eric", "Ono_anna", "Ryan", "Serena", "Sohee", "Uncle_fu", "Vivian"]
LANGUAGES = ["Auto", "English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]

# What a reference clip says: about 30 words with a question and a few sentence ends, so the voice shows its range.
SAMPLE_TEXT = "The road north is long, and the night grows cold. Keep your voice down and stay close to me. Do you hear that? Something is moving in the trees ahead."
# Natural speech is about 0.30 to 0.42 seconds of audio per word; a reference outside this is made again.
PACE_MIN, PACE_MAX = 0.24, 0.42
PACE_HINT = " Speak at a brisk, lively, natural pace."

app = FastAPI(title="claude-tts")
_models = {}  # (mode, size) -> FasterQwen3TTS
_lock = threading.Lock()  # one generation or model change at a time on the GPU
_busy = False
_jobs = {}  # voice slug -> {"status": "creating" | "failed", ...}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    mode: str = "custom"  # custom: a preset speaker with a style; design: a described voice; clone: a saved voice
    speaker: str = "Ryan"
    voice: Optional[str] = None  # clone: the name of a saved voice
    instruct: Optional[str] = None
    language: str = "English"
    model: str = "1.7B"
    chunk_size: int = Field(default=6, ge=2, le=24)  # codec steps per chunk, 12 per second of audio
    seed: Optional[int] = None  # fixes the sampling, so a take can be repeated and a voice stays steady
    temperature: float = Field(default=0.7, ge=0.1, le=1.5)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)  # 1 = as generated; the audio is time-stretched (pitch kept) while it streams


class CreateVoiceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=3, max_length=600)
    text: Optional[str] = Field(default=None, max_length=400)
    language: str = "English"
    replace: bool = False
    tries: int = Field(default=4, ge=1, le=8)
    seed: Optional[int] = None
    wait: bool = False  # answer when the voice is ready (can take a minute) instead of at once


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "voice"


def free_comfy():
    """Tell ComfyUI to unload its models and cache, so a model load here never competes with them for the GPU."""
    try:
        request = urllib.request.Request(
            f"{COMFY_URL}/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(), headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(request, timeout=5).read()
        time.sleep(1.5)
    except Exception as error:
        print(f"[claude-tts] could not ask ComfyUI to free its memory: {error}", flush=True)


def release_gpu():
    import gc
    import torch

    gc.collect()
    torch.cuda.empty_cache()


def ensure(mode: str, size: str):
    """The model for (mode, size), loaded. Call with _lock held. Saved voices (clone) are the hot path, so a
    clone model alone is kept next to one other model; loading the clone model drops everything else."""
    key = (mode, size)
    if key in _models:
        return _models[key]
    name = MODEL_NAMES.get(key)
    if name is None:
        raise HTTPException(400, f"No model for mode={mode} model={size}. Available: {sorted(set(f'{m}/{s}' for m, s in MODEL_NAMES))}")
    for other in list(_models):
        if mode == "clone" or other[0] != "clone":
            del _models[other]
    release_gpu()
    free_comfy()
    import torch
    from faster_qwen3_tts import FasterQwen3TTS

    path = os.path.join(MODELS_DIR, name)
    started = time.time()
    tts = FasterQwen3TTS.from_pretrained(path, device="cuda", dtype=torch.bfloat16, attn_implementation="sdpa", max_seq_len=2048, local_files_only=True)
    tts.warmup(prefill_len=100)
    print(f"[claude-tts] loaded {name} in {time.time() - started:.1f}s", flush=True)
    _models[key] = tts
    return tts


# ---- saved voices -------------------------------------------------------------------------------------------

def voice_paths(name: str):
    base = os.path.join(VOICES_DIR, slug(name))
    return base + ".wav", base + ".json"


def read_voice(name: str):
    wav, meta_path = voice_paths(name)
    if not (os.path.exists(wav) and os.path.exists(meta_path)):
        return None
    with open(meta_path, encoding="utf-8") as handle:
        meta = json.load(handle)
    meta["wav"] = wav
    return meta


def list_voices():
    out = []
    if os.path.isdir(VOICES_DIR):
        for entry in sorted(os.listdir(VOICES_DIR)):
            if entry.endswith(".json"):
                meta = read_voice(entry[:-5])
                if meta:
                    meta.pop("wav", None)
                    out.append(meta)
    return out


def trim_silence(wav: np.ndarray, rate: int) -> np.ndarray:
    loud = np.where(np.abs(wav) > 0.01)[0]
    if loud.size == 0:
        return wav
    pad = int(rate * 0.12)
    return wav[max(0, loud[0] - pad) : min(len(wav), loud[-1] + pad)]


def collect(generator):
    chunks, rate = [], 24000
    for audio, sample_rate, _timing in generator:
        chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        rate = sample_rate
    if not chunks:
        raise RuntimeError("No audio was produced")
    return np.concatenate(chunks), rate


def make_voice(req: CreateVoiceRequest):
    """Make the reference clip of a voice from its description and save it. Runs in a thread; sets _jobs."""
    global _busy
    key = slug(req.name)
    text = (req.text or SAMPLE_TEXT).strip()
    words = len(text.split())
    try:
        import soundfile as sf
        import torch

        with _lock:
            _busy = True
            try:
                tts = ensure("design", "1.7B")
                base_seed = req.seed if req.seed is not None else int(time.time()) % 100000
                best = None
                for attempt in range(req.tries):
                    instruct = req.description if attempt == 0 else req.description + PACE_HINT
                    torch.manual_seed(base_seed + attempt)
                    torch.cuda.manual_seed_all(base_seed + attempt)
                    wav, rate = collect(
                        tts.generate_voice_design_streaming(text=text, instruct=instruct, language=req.language, chunk_size=12, temperature=0.7)
                    )
                    wav = trim_silence(wav, rate)
                    pace = len(wav) / rate / words
                    miss = 0.0 if PACE_MIN <= pace <= PACE_MAX else min(abs(pace - PACE_MIN), abs(pace - PACE_MAX))
                    print(f"[claude-tts] voice {key} try {attempt + 1}: {pace:.3f} s/word", flush=True)
                    if best is None or miss < best[0]:
                        best = (miss, wav, rate, pace, attempt + 1, base_seed + attempt)
                    if miss == 0.0:
                        break
                # Free the design model: speaking needs only the clone model.
                _models.pop(("design", "1.7B"), None)
                release_gpu()
            finally:
                _busy = False
        _miss, wav, rate, pace, attempt, seed = best
        os.makedirs(VOICES_DIR, exist_ok=True)
        wav_path, meta_path = voice_paths(req.name)
        sf.write(wav_path, wav, rate)
        meta = {
            "name": req.name,
            "description": req.description,
            "ref_text": text,
            "language": req.language,
            "seconds": round(len(wav) / rate, 2),
            "seconds_per_word": round(pace, 3),
            "tries": attempt,
            "seed": seed,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=1)
        _jobs.pop(key, None)
        print(f"[claude-tts] saved voice {key} ({meta['seconds']}s, {meta['seconds_per_word']} s/word, try {attempt})", flush=True)
    except Exception as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        print(f"[claude-tts] voice {key} failed: {detail}", flush=True)
        _jobs[key] = {"name": req.name, "status": "failed", "error": detail}


@app.get("/health")
def health():
    return {"ok": True, "loaded": [f"{m}/{s}" for m, s in _models], "busy": _busy, "creating": [j["name"] for j in _jobs.values() if j["status"] == "creating"]}


@app.get("/voices")
def voices():
    return {
        "speakers": SPEAKERS,
        "languages": LANGUAGES,
        "models": sorted(set(f"{m}/{s}" for m, s in MODEL_NAMES)),
        "saved": list_voices(),
        "creating": [j for j in _jobs.values()],
    }


@app.get("/voices/{name}")
def voice_info(name: str):
    meta = read_voice(name)
    if meta:
        meta.pop("wav", None)
        return {"ok": True, "status": "ready", "voice": meta}
    job = _jobs.get(slug(name))
    if job:
        return {"ok": job["status"] != "failed", **job}
    raise HTTPException(404, f'No saved voice named "{name}"')


@app.delete("/voices/{name}")
def voice_delete(name: str):
    wav, meta_path = voice_paths(name)
    found = False
    for path in (wav, meta_path):
        if os.path.exists(path):
            os.remove(path)
            found = True
    _jobs.pop(slug(name), None)
    if not found:
        raise HTTPException(404, f'No saved voice named "{name}"')
    return {"ok": True}


@app.post("/voices/create")
async def voice_create(req: CreateVoiceRequest):
    key = slug(req.name)
    existing = read_voice(req.name)
    if existing and not req.replace:
        existing.pop("wav", None)
        return {"ok": True, "status": "exists", "voice": existing}
    current = _jobs.get(key)
    if current and current["status"] == "creating":
        return {"ok": True, "status": "creating", "name": req.name}
    _jobs[key] = {"name": req.name, "status": "creating", "started": time.time()}
    thread = threading.Thread(target=make_voice, args=(req,), daemon=True)
    thread.start()
    if req.wait:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, thread.join)
        return voice_info(req.name)
    return {"ok": True, "status": "creating", "name": req.name, "note": "About a minute: the voice model loads, then a short reference is made until its pace is natural."}


@app.post("/unload")
def unload():
    if _busy:
        return JSONResponse({"ok": False, "error": "Busy generating"}, status_code=409)
    _models.clear()
    release_gpu()
    return {"ok": True}


def pcm16(audio) -> bytes:
    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    return (np.clip(a, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


class Stretcher:
    """Streams 16-bit mono PCM through ffmpeg's atempo (a time stretch that keeps the pitch), so a voice can speak faster or slower."""

    def __init__(self, rate: int, speed: float):
        self.proc = subprocess.Popen(
            ["ffmpeg", "-v", "quiet", "-fflags", "nobuffer", "-flags", "low_delay", "-probesize", "32", "-analyzeduration", "0", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0", "-filter:a", f"atempo={speed}", "-flush_packets", "1", "-f", "s16le", "pipe:1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        self.out = thread_queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            data = self.proc.stdout.read(4096)
            if not data:
                break
            self.out.put(data)
        self.out.put(None)

    def feed(self, pcm: bytes):
        self.proc.stdin.write(pcm)
        self.proc.stdin.flush()

    def ready(self):
        """Stretched audio produced so far."""
        chunks = []
        while True:
            try:
                data = self.out.get_nowait()
            except thread_queue.Empty:
                return chunks
            if data is None:
                self.out.put(None)
                return chunks
            chunks.append(data)

    def finish(self):
        """Close the input and return everything still to come."""
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        chunks = []
        while True:
            data = self.out.get()
            if data is None:
                return chunks
            chunks.append(data)

    def kill(self):
        try:
            self.proc.kill()
        except Exception:
            pass


@app.post("/speak")
async def speak(req: SpeakRequest):
    global _busy
    if req.mode not in ("custom", "design", "clone"):
        raise HTTPException(400, "mode must be custom, design or clone")
    voice = None
    if req.mode == "clone":
        if not req.voice:
            raise HTTPException(400, "clone needs voice (the name of a saved voice)")
        voice = read_voice(req.voice)
        if voice is None:
            raise HTTPException(404, f'No saved voice named "{req.voice}"')
    loop = asyncio.get_running_loop()

    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    cancelled = threading.Event()
    rate_holder = {}

    def produce():
        global _busy
        with _lock:
            _busy = True
            try:
                tts = ensure(req.mode, req.model)
                if req.seed is not None:
                    import torch

                    torch.manual_seed(req.seed)
                    torch.cuda.manual_seed_all(req.seed)
                if req.mode == "custom":
                    gen = tts.generate_custom_voice_streaming(
                        text=req.text, speaker=req.speaker, language=req.language, instruct=req.instruct, chunk_size=req.chunk_size, temperature=req.temperature
                    )
                elif req.mode == "clone":
                    gen = tts.generate_voice_clone_streaming(
                        text=req.text, language=req.language, ref_audio=voice["wav"], ref_text=voice["ref_text"], chunk_size=req.chunk_size, temperature=req.temperature
                    )
                else:
                    gen = tts.generate_voice_design_streaming(
                        text=req.text, instruct=req.instruct or "A calm narrator.", language=req.language, chunk_size=req.chunk_size, temperature=req.temperature
                    )
                def send(data: bytes):
                    asyncio.run_coroutine_threadsafe(queue.put(data), loop).result()

                stretcher = None
                try:
                    for audio, rate, _timing in gen:
                        if cancelled.is_set():
                            break
                        rate_holder["rate"] = rate
                        pcm = pcm16(audio)
                        if abs(req.speed - 1.0) < 0.02:
                            send(pcm)
                            continue
                        if stretcher is None:
                            stretcher = Stretcher(rate, req.speed)
                        stretcher.feed(pcm)
                        for data in stretcher.ready():
                            send(data)
                    if stretcher is not None and not cancelled.is_set():
                        for data in stretcher.finish():
                            send(data)
                finally:
                    if stretcher is not None:
                        stretcher.kill()
            except Exception as error:  # surfaced to the client as a short error chunk marker below
                detail = error.detail if isinstance(error, HTTPException) else str(error)
                print(f"[claude-tts] generation failed: {detail}", flush=True)
                rate_holder["error"] = detail
            finally:
                _busy = False
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    thread = threading.Thread(target=produce, daemon=True)
    thread.start()

    first = await queue.get()
    if first is None:
        raise HTTPException(500, rate_holder.get("error", "No audio was produced"))

    async def body():
        try:
            yield first
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            cancelled.set()  # the client went away: stop generating
            while not queue.empty():
                queue.get_nowait()

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": str(rate_holder.get("rate", 24000)), "X-Channels": "1", "Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8190)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
