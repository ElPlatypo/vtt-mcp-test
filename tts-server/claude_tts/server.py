"""
Streaming narration server for the Foundry MCP bridge.

Runs faster-qwen3-tts (CUDA graphs) and streams raw 16-bit mono PCM while it generates, so the first
audio arrives in about half a second. It loads a model on first use and keeps it until /unload.

Start it with the Python of the venv that has faster-qwen3-tts, for example:
    /opt/fq/bin/python server.py --port 8190

Normally the claude_tts ComfyUI node starts it and exposes it through ComfyUI's own port.

API
    GET  /health          {"ok": true, "loaded": ["1.7B"], "busy": false}
    GET  /voices          {"speakers": [...], "languages": [...]}
    POST /speak           JSON {text, mode, speaker, instruct, language, model, chunk_size}
                          -> body: raw PCM s16le mono, streamed. Headers: X-Sample-Rate, X-Channels
    POST /unload          frees the GPU memory
"""
import argparse
import asyncio
import os

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
MODEL_NAMES = {
    ("custom", "1.7B"): "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    ("custom", "0.6B"): "Qwen3-TTS-12Hz-0.6B-CustomVoice",
    ("design", "1.7B"): "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
}
SPEAKERS = ["Aiden", "Dylan", "Eric", "Ono_anna", "Ryan", "Serena", "Sohee", "Uncle_fu", "Vivian"]
LANGUAGES = ["Auto", "English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]

app = FastAPI(title="claude-tts")
_models = {}  # (mode, size) -> FasterQwen3TTS
_lock = threading.Lock()  # one generation at a time on the GPU
_busy = False


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    mode: str = "custom"  # custom: a preset speaker with a style; design: a described voice
    speaker: str = "Ryan"
    instruct: Optional[str] = None
    language: str = "English"
    model: str = "1.7B"
    chunk_size: int = Field(default=6, ge=2, le=24)  # codec steps per chunk, 12 per second of audio
    seed: Optional[int] = None  # fixes the sampling, so a take can be repeated and a voice stays steady
    temperature: float = Field(default=0.7, ge=0.1, le=1.5)


def load(mode: str, size: str):
    key = (mode, size)
    if key in _models:
        return _models[key]
    name = MODEL_NAMES.get(key)
    if name is None:
        raise HTTPException(400, f"No model for mode={mode} model={size}. Available: {sorted(set(f'{m}/{s}' for m, s in MODEL_NAMES))}")
    import torch
    from faster_qwen3_tts import FasterQwen3TTS

    path = os.path.join(MODELS_DIR, name)
    started = time.time()
    tts = FasterQwen3TTS.from_pretrained(path, device="cuda", dtype=torch.bfloat16, attn_implementation="sdpa", max_seq_len=2048, local_files_only=True)
    tts.warmup(prefill_len=100)
    print(f"[claude-tts] loaded {name} in {time.time() - started:.1f}s", flush=True)
    _models[key] = tts
    return tts


@app.get("/health")
def health():
    return {"ok": True, "loaded": [f"{m}/{s}" for m, s in _models], "busy": _busy}


@app.get("/voices")
def voices():
    return {"speakers": SPEAKERS, "languages": LANGUAGES, "models": sorted(set(f"{m}/{s}" for m, s in MODEL_NAMES))}


@app.post("/unload")
def unload():
    if _busy:
        return JSONResponse({"ok": False, "error": "Busy generating"}, status_code=409)
    _models.clear()
    import gc
    import torch

    gc.collect()
    torch.cuda.empty_cache()
    return {"ok": True}


def pcm16(audio) -> bytes:
    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    return (np.clip(a, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


@app.post("/speak")
async def speak(req: SpeakRequest):
    global _busy
    if req.mode not in ("custom", "design"):
        raise HTTPException(400, "mode must be custom or design")
    loop = asyncio.get_running_loop()
    # Load before answering, so a bad model name is a clean error and not a broken stream.
    tts = await loop.run_in_executor(None, load, req.mode, req.model)

    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    cancelled = threading.Event()
    rate_holder = {}

    def produce():
        global _busy
        with _lock:
            _busy = True
            try:
                if req.seed is not None:
                    import torch

                    torch.manual_seed(req.seed)
                    torch.cuda.manual_seed_all(req.seed)
                if req.mode == "custom":
                    gen = tts.generate_custom_voice_streaming(
                        text=req.text, speaker=req.speaker, language=req.language, instruct=req.instruct, chunk_size=req.chunk_size, temperature=req.temperature
                    )
                else:
                    gen = tts.generate_voice_design_streaming(
                        text=req.text, instruct=req.instruct or "A calm narrator.", language=req.language, chunk_size=req.chunk_size, temperature=req.temperature
                    )
                for audio, rate, _timing in gen:
                    if cancelled.is_set():
                        break
                    rate_holder["rate"] = rate
                    asyncio.run_coroutine_threadsafe(queue.put(pcm16(audio)), loop).result()
            except Exception as error:  # surfaced to the client as a short error chunk marker below
                print(f"[claude-tts] generation failed: {error}", flush=True)
                rate_holder["error"] = str(error)
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
