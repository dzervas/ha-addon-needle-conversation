"""Opt-in native smoke test: prefetch Needle/Whistle models and set env below."""
import os
from pathlib import Path
import socket
import subprocess
import sys

from aiohttp import ClientSession
import pytest

from test_whistle import ROOT, client_module


@pytest.mark.skipif(os.environ.get("NEEDLE_TEST_NATIVE") != "1", reason="Native models not requested")
@pytest.mark.asyncio
async def test_native_speech_and_conversation_keep_separate_models():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "addon-needle-3/rootfs/app/server.py"),
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        line = process.stdout.readline()
        assert "Needle 3 and Whistle ready" in line, line
        async with ClientSession() as session:
            client = client_module.NeedleClient(session, f"http://127.0.0.1:{port}", 120)
            assert await client.async_model() == "needle-3 (base)"
            assert "en" in await client.async_stt_languages()
            assert await client.async_transcribe(bytes(32000), "en") == ""
            if audio := os.environ.get("NEEDLE_TEST_SPEECH_PCM"):
                text = await client.async_transcribe(Path(audio).read_bytes(), "en")
                assert "americans" in text.lower(), text
            tools = [{"name": "set_light", "description": "Turn a light on or off",
                      "parameters": {"type": "object", "properties": {"on": {"type": "boolean"}}, "required": ["on"]}}]
            result = await client.async_complete("turn on the light", tools)
            assert result["function_calls"] == [{"name": "set_light", "arguments": {"on": True}}], result
            assert await client.async_transcribe(bytes(32000), "de") == ""
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
