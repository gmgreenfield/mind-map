"""Start, watch and stop the local llama-server so the app works on its own.

If a server is already answering on the port (e.g. scripts/serve.sh), the
app uses it and leaves it alone on quit. Otherwise it starts its own copy
and stops it on quit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

DEFAULT_MODEL = "unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
DEFAULT_PORT = 8080
LOG_DIR = Path.home() / "Library" / "Logs" / "MindMap"


def bundled_binary() -> Path | None:
    """llama-server shipped inside the .app (PyInstaller puts it under _MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    path = Path(base) / "llama" / "llama-server"
    return path if path.exists() else None


def find_binary() -> Path | None:
    candidates = [
        os.environ.get("LLAMA_SERVER"),
        bundled_binary(),
        Path.home() / ".local" / "llama.cpp" / "current" / "llama-server",
        shutil.which("llama-server"),
    ]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return Path(c)
    return None


def default_threads() -> int:
    """Physical cores: hyperthreads don't help llama.cpp."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True, timeout=2
        )
        return max(1, int(out.stdout.strip()))
    except Exception:
        return max(1, (os.cpu_count() or 2) // 2)


class ModelServer:
    def __init__(
        self,
        port: int = DEFAULT_PORT,
        model: str = DEFAULT_MODEL,
        ctx: int = 8192,
        threads: int | None = None,
        binary: Path | None = None,
        log_dir: Path = LOG_DIR,
        transport: httpx.BaseTransport | None = None,
    ):
        self.port = port
        self.model = os.environ.get("MINDMAP_MODEL", model)
        self.ctx = ctx
        self.threads = threads
        self.binary = binary
        self.log_path = log_dir / "llama-server.log"
        self.proc: subprocess.Popen | None = None
        self.missing = False  # no llama-server binary found
        self.http = httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(0.5), transport=transport
        )

    # --- state ----------------------------------------------------------------
    def health(self) -> str:
        """'ready', 'loading' (model still loading) or 'down'."""
        try:
            r = self.http.get("/health")
        except httpx.HTTPError:
            return "down"
        if r.status_code == 200:
            return "ready"
        if r.status_code == 503:
            return "loading"
        return "down"

    def ours(self) -> bool:
        return self.proc is not None

    def exited(self) -> int | None:
        """Exit code if the server we started has died, else None."""
        return self.proc.poll() if self.proc is not None else None

    def command(self, binary: Path) -> list[str]:
        return [
            str(binary),
            "-hf", self.model,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--ctx-size", str(self.ctx),
            "--threads", str(self.threads or default_threads()),
            "--jinja",
        ]

    # --- control --------------------------------------------------------------
    def ensure_running(self) -> str:
        """'external' (someone else's server is up), 'started', or 'missing'."""
        if self.health() != "down":
            return "external"
        binary = self.binary or find_binary()
        if binary is None:
            self.missing = True
            return "missing"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "ab")
        self.proc = subprocess.Popen(
            self.command(binary),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        log.close()  # the child has its own handle
        return "started"

    def stop(self, timeout: float = 5.0) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None

    def close(self) -> None:
        self.stop()
        self.http.close()
