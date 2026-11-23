import os
import stat
import time

import httpx
import pytest

from mindmap import server
from mindmap.server import ModelServer, find_binary


def fake_binary(tmp_path, body="sleep 30"):
    path = tmp_path / "llama-server"
    path.write_text(f"#!/bin/sh\necho started \"$@\"\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def with_health(status):
    def handler(request):
        if status is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(status)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("status,expected", [(200, "ready"), (503, "loading"), (500, "down"), (None, "down")])
def test_health(tmp_path, status, expected):
    assert ModelServer(log_dir=tmp_path, transport=with_health(status)).health() == expected


def test_uses_external_server_when_one_is_up(tmp_path):
    s = ModelServer(log_dir=tmp_path, binary=fake_binary(tmp_path), transport=with_health(200))
    assert s.ensure_running() == "external"
    assert not s.ours()


def test_missing_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "find_binary", lambda: None)
    s = ModelServer(log_dir=tmp_path, transport=with_health(None))
    assert s.ensure_running() == "missing"


def test_starts_logs_and_stops_own_server(tmp_path):
    s = ModelServer(log_dir=tmp_path, binary=fake_binary(tmp_path), threads=3, transport=with_health(None))
    assert s.ensure_running() == "started"
    assert s.ours() and s.exited() is None
    pid = s.proc.pid
    deadline = time.time() + 3
    while "started" not in s.log_path.read_text() and time.time() < deadline:
        time.sleep(0.05)
    log = s.log_path.read_text()
    assert "-hf" in log and "--threads 3" in log and "--port 8080" in log
    s.stop()
    assert not s.ours()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_reports_crash(tmp_path):
    s = ModelServer(log_dir=tmp_path, binary=fake_binary(tmp_path, "exit 3"), transport=with_health(None))
    s.ensure_running()
    s.proc.wait(3)
    assert s.exited() == 3
    s.stop()


def test_find_binary_prefers_env(tmp_path, monkeypatch):
    b = fake_binary(tmp_path)
    monkeypatch.setenv("LLAMA_SERVER", str(b))
    assert find_binary() == b


def test_find_binary_uses_bundle(tmp_path, monkeypatch):
    monkeypatch.delenv("LLAMA_SERVER", raising=False)
    (tmp_path / "llama").mkdir()
    b = fake_binary(tmp_path / "llama")
    monkeypatch.setattr(server.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert find_binary() == b


def test_model_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDMAP_MODEL", "x/y:Q8")
    assert "x/y:Q8" in ModelServer(log_dir=tmp_path).command(tmp_path / "bin")
