from mindmap.__main__ import data_path, make_client, open_store, parse_args
from mindmap.llm import LLMClient
from mindmap.mock_llm import MockLLMClient
from mindmap.providers import ModelRouter


def test_flags():
    a = parse_args([])
    assert not a.mock and not a.demo
    a = parse_args(["--reset-demo"])
    assert a.demo and a.reset_demo


def test_demo_uses_separate_db(monkeypatch):
    monkeypatch.delenv("MINDMAP_DB", raising=False)
    assert data_path(False).name == "mindmap.db"
    assert data_path(True).name == "demo.db"


def test_client_choice():
    mock = make_client(parse_args(["--mock", "--mock-delay", "0"]))
    assert isinstance(mock, MockLLMClient) and mock.delay == 0
    real = make_client(parse_args([]))
    assert isinstance(real, ModelRouter) and isinstance(real.llm, LLMClient)
    real.close()


def test_demo_seeds_once_and_reset_reseeds(tmp_path, monkeypatch):
    db = tmp_path / "demo.db"
    monkeypatch.setenv("MINDMAP_DB", str(db))
    s = open_store(parse_args(["--demo"]))
    n = len(s.sessions())
    assert n > 10
    s.create_session("extra")
    s.close()

    s = open_store(parse_args(["--demo"]))
    assert len(s.sessions()) == n + 1  # not re-seeded
    s.close()

    s = open_store(parse_args(["--reset-demo"]))
    assert len(s.sessions()) == n
    s.close()


def test_plain_store_is_not_seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDMAP_DB", str(tmp_path / "m.db"))
    s = open_store(parse_args([]))
    assert s.sessions() == []
    s.close()


def test_make_server(monkeypatch):
    from mindmap import __main__ as m

    assert m.make_server(parse_args(["--mock"])) is None
    started = []
    monkeypatch.setattr(m.ModelServer, "ensure_running", lambda self: started.append(1) or "started")
    s = m.make_server(parse_args(["--no-server"]))
    assert s is not None and started == []
    s.close()
    s = m.make_server(parse_args([]))
    assert started == [1]
    s.close()


def test_self_check_runs(capsys):
    from mindmap import __main__ as m

    code = m.main(["--self-check"])
    out = capsys.readouterr().out
    assert "anthropic SDK:" in out and "keyring backend:" in out
    assert code in (0, 1)
