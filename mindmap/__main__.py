"""Entry point: python -m mindmap [--mock] [--demo] [--reset-demo] [--no-server]"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .llm import DEFAULT_BASE_URL, LLMClient
from .providers import ModelRouter
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
    p.add_argument("--self-check", action="store_true",
                   help="check the cloud SDKs, Keychain and llama-server are usable, then exit")
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


def make_client(args: argparse.Namespace, server: ModelServer | None = None):
    """The mock serves every model; otherwise a router picks local, Claude or ChatGPT."""
    if args.mock:
        from .mock_llm import MockLLMClient

        return MockLLMClient(delay=args.mock_delay)
    local = LLMClient(os.environ.get("MINDMAP_LLM_URL", DEFAULT_BASE_URL))
    return ModelRouter(local, server)


def make_server(args: argparse.Namespace) -> ModelServer | None:
    if args.mock:
        return None
    server = ModelServer()
    if not args.no_server:
        server.ensure_running()
    return server


def self_check() -> int:
    """Used by the release build to catch packaging gaps (e.g. a missing backend)."""
    import anthropic
    import keyring
    import openai

    from .server import find_binary

    backend = keyring.get_keyring()
    checks = {
        "anthropic SDK": anthropic.__version__,
        "openai SDK": openai.__version__,
        "keyring backend": type(backend).__module__ + "." + type(backend).__name__,
        "llama-server": str(find_binary() or "missing"),
    }
    for name, value in checks.items():
        print(f"{name}: {value}")
    ok = "fail" not in checks["keyring backend"].lower() and checks["llama-server"] != "missing"
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_check:
        return self_check()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Mind Map")
    store = open_store(args)
    server = make_server(args)
    client = make_client(args, server)
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
