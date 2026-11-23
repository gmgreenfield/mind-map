"""Run a streaming model request off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..llm import LLMError


class StreamWorker(QThread):
    token = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, client, messages: list[dict], temperature: float = 0.7, parent=None):
        super().__init__(parent)
        self.client = client
        self.messages = messages
        self.temperature = temperature
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        parts: list[str] = []
        stream = self.client.stream_chat(self.messages, self.temperature)
        try:
            for delta in stream:
                if self._stop:
                    break
                parts.append(delta)
                self.token.emit(delta)
            self.done.emit("".join(parts))
        except LLMError as e:
            self.failed.emit(str(e))
        except Exception as e:  # keep the UI alive on unexpected errors
            self.failed.emit(f"unexpected error: {e}")
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
