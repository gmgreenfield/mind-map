"""Entry point: python -m mindmap"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .llm import DEFAULT_BASE_URL, LLMClient
from .store import Store
from .ui.main_window import MainWindow


def data_path() -> Path:
    override = os.environ.get("MINDMAP_DB")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "MindMap" / "mindmap.db"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Mind Map")
    store = Store(data_path())
    client = LLMClient(os.environ.get("MINDMAP_LLM_URL", DEFAULT_BASE_URL))
    window = MainWindow(store, client)
    window.show()
    code = app.exec()
    client.close()
    store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
