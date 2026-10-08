"""Needle playground with a bounded Whistle transcription endpoint."""
from __future__ import annotations

import argparse
import array
from concurrent.futures import ProcessPoolExecutor
import json
import logging
import multiprocessing
import sys
import threading
from http.server import ThreadingHTTPServer

from needle.playground.server import Engine, _Handler

LANGUAGES = ("en", "de", "fr", "es", "it", "nl", "pl")
MAX_AUDIO_BYTES = 16000 * 2 * 30
_LOGGER = logging.getLogger(__name__)
_whistle = None


def load_whistle():
    """Load in a separate process: the native runtime has global model state."""
    global _whistle
    from needle import Whistle
    _whistle = Whistle()


def transcribe(audio: bytes, language: str) -> dict:
    """Convert signed little-endian PCM16 to normalized float samples."""
    samples = array.array("h")
    samples.frombytes(audio)
    if sys.byteorder != "little":
        samples.byteswap()
    return _whistle.transcribe(
        array.array("f", (sample / 32768.0 for sample in samples)),
        language=language,
    )


def ready():
    return _whistle is not None


class Handler(_Handler):
    """Keep the existing API/UI and add Whistle without exposing a LAN port."""

    worker = None
    speech_lock = threading.Lock()

    def do_GET(self):
        if self.path == "/stt":
            self._send(200, json.dumps({"name": "Whistle", "languages": LANGUAGES}))
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/transcribe":
            super().do_POST()
            return
        # HA supplies raw PCM, even though its metadata format is called WAV.
        language = self.headers.get("X-Language", "en")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if language not in LANGUAGES:
            self._send(400, json.dumps({"error": "Unsupported Whistle language"}))
            return
        if self.headers.get_content_type() != "audio/pcm":
            self._send(415, json.dumps({"error": "Expected 16 kHz mono PCM16"}))
            return
        if length <= 0 or length % 2 or length > MAX_AUDIO_BYTES:
            self._send(400, json.dumps({"error": "Audio must contain aligned PCM16, up to 30 seconds"}))
            return
        # Reject concurrent requests rather than accumulating unbounded audio.
        if not self.speech_lock.acquire(blocking=False):
            self._send(503, json.dumps({"error": "Whistle is busy; retry shortly"}))
            return
        try:
            self.connection.settimeout(30)
            audio = self.rfile.read(length)
            if len(audio) != length:
                self._send(400, json.dumps({"error": "Incomplete audio"}))
                return
            result = self.worker.submit(transcribe, audio, language).result()
            self._send(200, json.dumps(result))
        except Exception:
            _LOGGER.exception("Whistle transcription failed")
            self._send(500, json.dumps({"error": "Whistle transcription failed"}))
        finally:
            self.speech_lock.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--weights")
    args = parser.parse_args()
    engine = Engine(weights=args.weights)
    engine.load()
    if not args.weights:
        engine.name = "needle-3 (base)"
    Handler.engine = engine
    with ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"),
        initializer=load_whistle,
    ) as worker:
        # Startup fails if the bundled engine/Whistle model cannot load.
        assert worker.submit(ready).result()
        Handler.worker = worker
        with ThreadingHTTPServer((args.host, args.port), Handler) as server:
            print(f"Needle 3 and Whistle ready on port {args.port}", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
