from mindmap.branching import (
    BASE_SYSTEM,
    brief_request,
    chat_context,
    system_prompt,
    title_from_text,
    trim_history,
)
from mindmap.store import Message


def msg(i, role, content):
    return Message(i, 1, role, content)


def test_trim_keeps_most_recent_within_budget():
    history = [msg(1, "user", "a" * 10), msg(2, "assistant", "b" * 10), msg(3, "user", "c" * 10)]
    assert [m.id for m in trim_history(history, max_chars=25)] == [2, 3]
    assert [m.id for m in trim_history(history, max_chars=100)] == [1, 2, 3]


def test_trim_always_keeps_latest_message():
    history = [msg(1, "user", "x" * 1000)]
    assert [m.id for m in trim_history(history, max_chars=10)] == [1]


def test_system_prompt_includes_brief_only_when_present():
    assert system_prompt(None) == BASE_SYSTEM
    with_brief = system_prompt("## Goal\nexplore X")
    assert with_brief.startswith(BASE_SYSTEM)
    assert "explore X" in with_brief


def test_chat_context_shape():
    history = [msg(1, "user", "hi"), msg(2, "assistant", "hello")]
    ctx = chat_context("the brief", history)
    assert ctx[0]["role"] == "system" and "the brief" in ctx[0]["content"]
    assert ctx[1:] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_brief_request_appends_instruction_with_topic():
    history = [msg(1, "user", "we are building a mind map app")]
    ctx = brief_request(None, history, "  idea describing this project ")
    assert ctx[-1]["role"] == "user"
    assert "idea describing this project" in ctx[-1]["content"]
    assert "ONLY this brief" in ctx[-1]["content"]
    assert ctx[1]["content"] == "we are building a mind map app"


def test_title_from_text():
    assert title_from_text("  hello\n world ") == "hello world"
    assert title_from_text("") == "New chat"
    long = title_from_text("word " * 30, limit=20)
    assert len(long) <= 20 and long.endswith("…")
