"""Giữ OCR và LLM trong bộ nhớ để dùng lại giữa các lần xử lý.

- OCR (~1–2 GB RAM): nạp lần đầu cần dùng, giữ đến khi tắt app.
- LLM (12–18 GB RAM): bật llama-server khi cần; tự TẮT sau LLM_IDLE_SECONDS không dùng
  để trả RAM cho máy.
"""

from __future__ import annotations

import threading
import time

from app.llm import LlamaServer, LlmClient

LLM_IDLE_SECONDS = 600


class OcrService:
    def __init__(self, factory=None):
        self._factory = factory
        self._engine = None
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            if self._engine is None:
                if self._factory is None:
                    from app.ocr import OcrEngine

                    self._factory = OcrEngine
                self._engine = self._factory()
            return self._engine

    @property
    def loaded(self) -> bool:
        return self._engine is not None


class LlmService:
    def __init__(self, idle_seconds: int = LLM_IDLE_SECONDS):
        self.idle_seconds = idle_seconds
        self._server: LlamaServer | None = None
        self._lock = threading.Lock()
        self._last_used = 0.0
        self._watcher = threading.Thread(target=self._idle_loop, daemon=True)
        self._watcher.start()

    def client(self) -> LlmClient:
        with self._lock:
            if self._server is None or self._server.proc is None or self._server.proc.poll() is not None:
                server = LlamaServer()
                server.start()
                self._server = server
            self._last_used = time.monotonic()
            return self._server.client()

    def touch(self) -> None:
        self._last_used = time.monotonic()

    def stop(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.stop()
                self._server = None

    @property
    def running(self) -> bool:
        return self._server is not None and self._server.proc is not None and self._server.proc.poll() is None

    def _idle_loop(self) -> None:
        while True:
            time.sleep(15)
            if self.running and time.monotonic() - self._last_used > self.idle_seconds:
                self.stop()
