"""
claude_tts: lets the Foundry MCP bridge stream narration through your ComfyUI.

It starts server.py (faster-qwen3-tts, streams audio while it generates) next to ComfyUI and passes
requests to it under /claude-tts/..., so nothing new has to be published by Docker or opened in a firewall:
the bridge talks to the same address and port as ComfyUI.

Settings, as environment variables of the ComfyUI process (all optional):
    CLAUDE_TTS_PYTHON   Python with faster-qwen3-tts installed (default /opt/fq/bin/python)
    CLAUDE_TTS_PORT     port of the private server (default 8190, only 127.0.0.1)
    CLAUDE_TTS_AUTOSTART  set to 0 to start it yourself
"""
import atexit
import os
import subprocess
import sys

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("CLAUDE_TTS_PORT", "8190"))
PYTHON = os.environ.get("CLAUDE_TTS_PYTHON", "/opt/fq/bin/python")
_process = None


def _start_server():
    global _process
    if os.environ.get("CLAUDE_TTS_AUTOSTART", "1") == "0":
        return
    if not os.path.exists(PYTHON):
        print(f"[claude_tts] {PYTHON} not found, so the narration server was not started. Set CLAUDE_TTS_PYTHON.", file=sys.stderr)
        return
    try:
        _process = subprocess.Popen([PYTHON, os.path.join(HERE, "server.py"), "--port", str(PORT)], cwd=HERE)
        atexit.register(lambda: _process and _process.terminate())
        print(f"[claude_tts] narration server starting on 127.0.0.1:{PORT} (the model loads on first use)")
    except Exception as error:
        print(f"[claude_tts] could not start the narration server: {error}", file=sys.stderr)


def _register_routes():
    try:
        import aiohttp
        from aiohttp import web
        from server import PromptServer
    except Exception as error:  # not running inside ComfyUI (for example when tests import this folder)
        print(f"[claude_tts] routes not registered: {error}", file=sys.stderr)
        return

    routes = PromptServer.instance.routes
    skip = {"connection", "keep-alive", "transfer-encoding", "content-length", "host", "content-encoding"}

    @routes.route("*", "/claude-tts/{tail:.*}")
    async def forward(request: web.Request):
        url = f"http://127.0.0.1:{PORT}/{request.match_info['tail']}"
        body = await request.read()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=3)) as session:
                async with session.request(request.method, url, data=body or None, headers={"Content-Type": request.headers.get("Content-Type", "application/json")}) as upstream:
                    response = web.StreamResponse(status=upstream.status)
                    for key, value in upstream.headers.items():
                        if key.lower() not in skip:
                            response.headers[key] = value
                    await response.prepare(request)
                    async for chunk in upstream.content.iter_any():
                        await response.write(chunk)
                    await response.write_eof()
                    return response
        except aiohttp.ClientConnectorError:
            return web.json_response({"ok": False, "error": "The narration server is not running. Check the ComfyUI log for [claude_tts]."}, status=503)


_start_server()
_register_routes()
