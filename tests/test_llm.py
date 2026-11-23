import json

import httpx
import pytest

from mindmap.llm import DEFAULT_MAX_TOKENS, TRUNCATION_NOTE, LLMClient, LLMError


def sse(*deltas, done=True):
    lines = []
    for d in deltas:
        chunk = {"choices": [{"delta": {"content": d}}]}
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines)


def client_for(handler):
    return LLMClient(base_url="http://test/v1", transport=httpx.MockTransport(handler))


def test_streams_deltas_and_sends_messages():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=sse("Hel", "lo", "!"))

    c = client_for(handler)
    msgs = [{"role": "user", "content": "hi"}]
    assert list(c.stream_chat(msgs)) == ["Hel", "lo", "!"]
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["stream"] is True
    assert seen["body"]["messages"] == msgs


def test_complete_joins_stream():
    c = client_for(lambda r: httpx.Response(200, text=sse("a", "b")))
    assert c.complete([]) == "ab"


def test_skips_role_only_and_malformed_chunks():
    body = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        "data: not-json\n\n"
        ": keepalive comment\n\n"
        'data: {"choices":[]}\n\n'
        + sse("ok")
    )
    c = client_for(lambda r: httpx.Response(200, text=body))
    assert c.complete([]) == "ok"


def test_http_error_status_raises():
    c = client_for(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(LLMError, match="500"):
        c.complete([])


def test_connection_error_has_helpful_message():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    c = client_for(handler)
    with pytest.raises(LLMError, match="serve.sh"):
        c.complete([])


def test_sends_max_tokens_by_default():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=sse("x"))

    client_for(handler).complete([])
    assert seen["body"]["max_tokens"] == DEFAULT_MAX_TOKENS


def test_max_tokens_none_omits_limit():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=sse("x"))

    c = LLMClient(base_url="http://test/v1", transport=httpx.MockTransport(handler), max_tokens=None)
    c.complete([])
    assert "max_tokens" not in seen["body"]


def test_length_cutoff_appends_note():
    body = sse("partial", done=False) + (
        'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n'
    )
    text = client_for(lambda r: httpx.Response(200, text=body)).complete([])
    assert text == "partial" + TRUNCATION_NOTE


def test_normal_stop_has_no_note():
    body = sse("done", done=False) + (
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    )
    assert client_for(lambda r: httpx.Response(200, text=body)).complete([]) == "done"
