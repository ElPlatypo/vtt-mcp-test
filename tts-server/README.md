# claude_tts: streaming narration for the `speak` tool

A small ComfyUI custom node that runs [faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) (CUDA graphs) and **streams audio while it generates**. The `speak` tool's `qwen3-fast` engine uses it: the first words are heard in about a second, and the voice is Qwen3-TTS 1.7B.

It adds no port and no setting of its own. The bridge reaches it through the ComfyUI you already chose (Settings, Map Generation), at `<your ComfyUI>/claude-tts/...`.

## How it fits together

```
MCP server --HTTP--> ComfyUI :8188 /claude-tts/*  --> server.py on 127.0.0.1:8190 (inside the container)
                                                         streams raw PCM while it generates
```

`__init__.py` starts `server.py` when ComfyUI starts and passes requests through. The model is loaded on the first narration (about 30 s, once) and stays in GPU memory (about 4 GB) until ComfyUI restarts or you call `POST /claude-tts/unload`.

## Install

1. Copy the `claude_tts` folder into ComfyUI's `custom_nodes` folder (for the Docker setup, the folder mounted at `/root/ComfyUI/custom_nodes`).
2. Restart ComfyUI. The log shows `[claude_tts] narration server starting`.
3. In Foundry: Module Settings, Narration engine: `qwen3-fast`, Narration voice: `Ryan` (or Serena, Aiden, Dylan, Eric, Sohee, Ono_anna, Uncle_fu).

It needs a Python with `faster-qwen3-tts`, `fastapi` and `uvicorn` (default `/opt/fq/bin/python`) and the Qwen3-TTS model folders under `ComfyUI/models/qwen-tts/` (`Qwen3-TTS-12Hz-1.7B-CustomVoice`, optionally `0.6B-CustomVoice` and `1.7B-VoiceDesign`).

## Settings (environment variables of the ComfyUI process, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `CLAUDE_TTS_PYTHON` | `/opt/fq/bin/python` | Python that has faster-qwen3-tts |
| `CLAUDE_TTS_PORT` | `8190` | private port of the server (127.0.0.1 only) |
| `CLAUDE_TTS_MODELS` | `/root/ComfyUI/models/qwen-tts` | folder with the model folders |
| `CLAUDE_TTS_AUTOSTART` | `1` | `0` to start `server.py` yourself |

## API

- `GET  /claude-tts/health` and `GET /claude-tts/voices`
- `POST /claude-tts/speak` with `{text, mode: "custom"|"design", speaker, instruct, language, model, chunk_size}` streams raw 16-bit mono PCM (`X-Sample-Rate` header, 24000 Hz).
- `POST /claude-tts/unload` frees the GPU memory.

Measured on an RTX 3060: first audio 0.35 s after the model is loaded, about 1.7 times faster than speech.

## Notes

- ComfyUI runs with the `cudaMallocAsync` allocator, which breaks CUDA graph capture, so `server.py` clears that setting for itself. Image generation is not affected.
- The Python environment (`/opt/fq`) lives in the container, not in a mounted folder. If the container is recreated (`docker compose up` after changing the compose file), reinstall `faster-qwen3-tts` there.
