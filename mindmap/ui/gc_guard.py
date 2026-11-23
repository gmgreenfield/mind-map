"""Run Python's cyclic garbage collector on the Qt main thread only.

Automatic collection runs on whichever thread happens to allocate, including
the reply threads. If it frees a Qt object there (one stuck in a reference
cycle, e.g. a closed window or a removed chat bubble), Qt destroys it off the
main thread and the process segfaults. So: turn automatic collection off and
collect from a main-thread timer instead.
"""

from __future__ import annotations

import gc

from PySide6.QtCore import QObject, QTimer


class MainThreadGC(QObject):
    def __init__(self, interval_ms: int = 500, parent: QObject | None = None):
        super().__init__(parent)
        self.thresholds = gc.get_threshold()
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(interval_ms)

    def check(self) -> None:
        counts = gc.get_count()
        for generation in (2, 1, 0):
            if counts[generation] > self.thresholds[generation]:
                gc.collect(generation)
                return


_installed: MainThreadGC | None = None


def install(app) -> MainThreadGC:
    """Idempotent: one collector per process, owned by the QApplication."""
    global _installed
    if _installed is None:
        _installed = MainThreadGC(parent=app)
    return _installed
