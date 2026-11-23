from mindmap import branching
from mindmap.mock_llm import (
    GENERIC,
    MockLLMClient,
    make_brief,
    make_reply,
    parse_brief_request,
    tokenize,
)
from mindmap.store import Message


def test_tokenize_round_trips():
    text = "Hello  world,\n\n- item one\n```py\nx = 1\n```"
    assert "".join(tokenize(text)) == text
    assert len(tokenize(text)) > 5


def test_keyword_reply():
    assert "cost" in make_reply([{"role": "user", "content": "What about pricing?"}])


def test_generic_reply_is_deterministic():
    msgs = [{"role": "user", "content": "tell me about xyzzy"}]
    assert make_reply(msgs) == make_reply(msgs)
    assert make_reply(msgs) in GENERIC


def test_reply_in_branch_mentions_goal():
    ctx = branching.chat_context("## Goal\nExplore pitch wording in depth.\n", [
        Message(1, 1, "user", "what do you think about xyzzy"),
    ])
    assert "Explore pitch wording in depth." in make_reply(ctx)


def test_brief_request_produces_brief_from_parent_history():
    history = [
        Message(1, 1, "user", "We're opening a coffee roastery in Leeds. It is small."),
        Message(2, 1, "assistant", "Nice. Start with wholesale to cafés."),
    ]
    req = branching.brief_request(None, history, "naming the roastery")
    client = MockLLMClient(delay=0)
    brief = client.complete(req)
    assert brief.startswith("## Goal\nExplore naming the roastery")
    assert "coffee roastery in Leeds." in brief
    assert "wholesale to cafés." in brief
    assert "## Open questions" in brief


def test_nested_brief_carries_parent_goal():
    req = branching.brief_request(
        "## Goal\nExplore naming in depth.\n", [Message(1, 1, "user", "hm")], "logo"
    )
    brief = MockLLMClient(delay=0).complete(req)
    assert "Parent session's goal: Explore naming in depth." in brief


def test_parse_brief_request_round_trips_multiline_messages():
    history = [
        Message(1, 1, "user", "line one\n\nstill the user"),
        Message(2, 1, "assistant", "answer"),
    ]
    req = branching.brief_request("## Goal\nParent goal.\n", history, "topic x")
    topic, convo, goal = parse_brief_request(req[-1]["content"])
    assert topic == "topic x"
    assert convo == [("user", "line one\n\nstill the user"), ("assistant", "answer")]
    assert goal == "Parent goal."


def test_empty_parent_brief():
    assert "empty" in make_brief("x", [])


def test_streams_multiple_chunks_and_records_calls():
    c = MockLLMClient(delay=0)
    chunks = list(c.stream_chat([{"role": "user", "content": "hello"}]))
    assert len(chunks) > 3
    assert len(c.calls) == 1
