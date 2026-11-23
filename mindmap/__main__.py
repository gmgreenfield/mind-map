"""Entry point: python -m mindmap [--mock] [--demo] [--reset-demo] [--no-server]"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .llm import DEFAULT_BASE_URL, LLMClient
from .server import ModelServer
from .store import Store
from .ui.main_window import MainWindow

APP_DIR = Path.home() / "Library" / "Application Support" / "MindMap"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m mindmap")
    p.add_argument("--mock", action="store_true",
                   help="use a fake Qwen with canned replies (no model server needed)")
    p.add_argument("--demo", action="store_true",
                   help="open the demo map (separate database, seeded on first use)")
    p.add_argument("--reset-demo", action="store_true",
                   help="wipe and re-seed the demo map (implies --demo)")
    p.add_argument("--no-server", action="store_true",
                   help="don't start llama-server; only use one that is already running")
    p.add_argument("--mock-delay", type=float, default=0.03,
                   help="seconds between mock tokens (default 0.03)")
    args = p.parse_args(argv)
    if args.reset_demo:
        args.demo = True
    return args


def data_path(demo: bool = False) -> Path:
    override = os.environ.get("MINDMAP_DB")
    if override:
        return Path(override)
    return APP_DIR / ("demo.db" if demo else "mindmap.db")


def open_store(args: argparse.Namespace) -> Store:
    path = data_path(args.demo)
    if args.reset_demo and path.exists():
        path.unlink()
    store = Store(path)
    if args.demo and not store.sessions():
        from .demo import seed

        seed(store)
    return store


def make_client(args: argparse.Namespace):
    if args.mock:
        from .mock_llm import MockLLMClient

        return MockLLMClient(delay=args.mock_delay)
    return LLMClient(os.environ.get("MINDMAP_LLM_URL", DEFAULT_BASE_URL))


def make_server(args: argparse.Namespace) -> ModelServer | None:
    if args.mock:
        return None
    server = ModelServer()
    if not args.no_server:
        server.ensure_running()
    return server


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Mind Map")
    store = open_store(args)
    client = make_client(args)
    server = make_server(args)
    try:
        window = MainWindow(store, client, server)
        if args.mock:
            window.setWindowTitle("Mind Map — mock Qwen")
            window.set_model_status("info", "Mock Qwen")
        window.show()
        window.raise_()
        window.activateWindow()
        return app.exec()
    finally:
        if server is not None:
            server.close()  # stops llama-server only if we started it
        client.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())
