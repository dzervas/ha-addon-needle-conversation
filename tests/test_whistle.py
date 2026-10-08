"""Exercise the real HTTP/client path without downloading model weights."""
import asyncio
from concurrent.futures import Future
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace

from aiohttp import ClientSession
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


server = load("whistle_server", ROOT / "addon-needle-3/rootfs/app/server.py")
client_module = load("needle_client", ROOT / "custom_components/needle/client.py")


class Worker:
    def __init__(self):
        self.calls = []

    def submit(self, fn, audio, language):
        self.calls.append((audio, language))
        result = Future()
        result.set_result({"text": "turn on the lights", "language": language})
        return result


@pytest.fixture
def endpoint():
    worker = Worker()
    class Handler(server.Handler):
        pass
    Handler.worker = worker
    Handler.engine = SimpleNamespace(name="needle-3 (base)")
    Handler.speech_lock = threading.Lock()
    http = server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}", worker, Handler
    http.shutdown()
    http.server_close()
    thread.join()


@pytest.mark.asyncio
async def test_discovery_transcription_and_existing_model_api(endpoint):
    url, worker, _ = endpoint
    async with ClientSession() as session:
        client = client_module.NeedleClient(session, url, 10)
        assert await client.async_model() == "needle-3 (base)"
        assert await client.async_stt_languages() == list(server.LANGUAGES)
        assert await client.async_transcribe(b"\0\0\xff\x7f", "de") == "turn on the lights"
        assert worker.calls == [(b"\0\0\xff\x7f", "de")]
        # No language header explicitly selects English, not autodetection.
        async with session.post(url + "/transcribe", data=b"\0\0",
                                headers={"Content-Type": "audio/pcm"}) as response:
            assert response.status == 200
        assert worker.calls[-1][1] == "en"


@pytest.mark.asyncio
@pytest.mark.parametrize("audio,language,content_type,status", [
    (b"\0\0", "el", "audio/pcm", 400),
    (b"\0", "en", "audio/pcm", 400),
    (b"", "en", "audio/pcm", 400),
    (b"\0" * (server.MAX_AUDIO_BYTES + 2), "en", "audio/pcm", 400),
    (b"\0\0", "en", "audio/wav", 415),
])
async def test_invalid_audio_is_rejected_before_inference(endpoint, audio, language, content_type, status):
    url, worker, _ = endpoint
    async with ClientSession() as session:
        async with session.post(url + "/transcribe", data=audio, headers={
            "Content-Type": content_type, "X-Language": language,
        }) as response:
            assert response.status == status
    assert not worker.calls


@pytest.mark.asyncio
async def test_busy_worker_and_http_errors(endpoint):
    url, worker, handler = endpoint
    handler.speech_lock.acquire()
    try:
        async with ClientSession() as session:
            client = client_module.NeedleClient(session, url, 10)
            with pytest.raises(client_module.NeedleConnectionError):
                await client.async_transcribe(b"\0\0", "en")
    finally:
        handler.speech_lock.release()
    assert not worker.calls


def test_pcm_conversion_preserves_signed_little_endian_samples(monkeypatch):
    captured = {}
    def transcribe(samples, language):
        captured.update(samples=list(samples), language=language)
        return {"text": ""}
    monkeypatch.setattr(server, "_whistle", SimpleNamespace(transcribe=transcribe))
    assert server.transcribe(b"\0\x80\0\0\xff\x7f", "en") == {"text": ""}
    assert captured == {"samples": [-1.0, 0.0, 32767 / 32768], "language": "en"}
