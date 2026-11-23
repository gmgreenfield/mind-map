from contextlib import contextmanager
from types import SimpleNamespace as NS

import anthropic
import httpx2
import openai
import pytest

from mindmap.llm import TRUNCATION_NOTE, LLMError
from mindmap.models import ModelSpec
from mindmap.providers import (
    FALLBACK_BETA,
    REFUSAL_NOTE,
    ClaudeClient,
    LocalModelClient,
    MissingKeyClient,
    ModelRouter,
    OpenAIClient,
    split_system,
)

REQ = httpx2.Request("POST", "https://example.invalid")


def http_error(lib, cls, status):
    return cls("nope", response=httpx2.Response(status, request=REQ), body=None)


# --- Claude ------------------------------------------------------------------------
class FakeClaudeStream:
    def __init__(self, texts, stop_reason):
        self.text_stream = iter(texts)
        self._stop = stop_reason

    def get_final_message(self):
        return NS(stop_reason=self._stop)


class FakeAnthropic:
    def __init__(self, texts=("Hi", " there"), stop_reason="end_turn", error=None):
        self.calls = []
        self.texts, self.stop_reason, self.error = texts, stop_reason, error
        self.messages = NS(stream=self._stream("plain"))
        self.beta = NS(messages=NS(stream=self._stream("beta")))

    def _stream(self, kind):
        @contextmanager
        def stream(**params):
            self.calls.append((kind, params))
            if self.error:
                raise self.error
            yield FakeClaudeStream(self.texts, self.stop_reason)

        return stream


MSGS = [
    {"role": "system", "content": "be brief"},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
    {"role": "user", "content": "more"},
]


def test_split_system():
    system, rest = split_system(MSGS)
    assert system == "be brief"
    assert [m["role"] for m in rest] == ["user", "assistant", "user"]


def test_claude_streams_with_fallbacks_on_supported_models():
    fake = FakeAnthropic()
    out = "".join(ClaudeClient("claude-opus-5-5", "k", client=fake).stream_chat(MSGS, temperature=0.3))
    assert out == "Hi there"
    kind, params = fake.calls[0]
    assert kind == "beta"
    assert params["betas"] == [FALLBACK_BETA] and params["fallbacks"] == "default"
    assert params["system"] == "be brief"
    assert params["messages"][0] == {"role": "user", "content": "hi"}
    assert "temperature" not in params  # rejected by current Claude models


def test_claude_haiku_uses_plain_stream_without_fallbacks():
    fake = FakeAnthropic()
    list(ClaudeClient("claude-haiku-5-5", "k", client=fake).stream_chat(MSGS))
    kind, params = fake.calls[0]
    assert kind == "plain" and "fallbacks" not in params


def test_claude_omits_empty_system():
    fake = FakeAnthropic()
    list(ClaudeClient("claude-haiku-5-5", "k", client=fake).stream_chat([{"role": "user", "content": "x"}]))
    assert "system" not in fake.calls[0][1]


@pytest.mark.parametrize("stop,note", [("refusal", REFUSAL_NOTE), ("max_tokens", TRUNCATION_NOTE), ("end_turn", "")])
def test_claude_stop_reason_notes(stop, note):
    out = "".join(ClaudeClient("claude-opus-5-5", "k", client=FakeAnthropic(("a",), stop)).stream_chat(MSGS))
    assert out == "a" + note


@pytest.mark.parametrize(
    "error,match",
    [
        (http_error(anthropic, anthropic.AuthenticationError, 401), "API key"),
        (http_error(anthropic, anthropic.NotFoundError, 404), "doesn't know the model"),
        (http_error(anthropic, anthropic.RateLimitError, 429), "rate limit"),
        (http_error(anthropic, anthropic.InternalServerError, 500), "Claude error 500"),
        (anthropic.APIConnectionError(request=REQ), "internet"),
    ],
)
def test_claude_errors_become_readable(error, match):
    with pytest.raises(LLMError, match=match):
        list(ClaudeClient("claude-opus-5-5", "k", client=FakeAnthropic(error=error)).stream_chat(MSGS))


# --- OpenAI -------------------------------------------------------------------------
def chunk(text=None, finish=None):
    return NS(choices=[NS(delta=NS(content=text), finish_reason=finish)])


class FakeOpenAI:
    def __init__(self, chunks, error=None):
        self.calls = []
        self.chunks, self.error = chunks, error
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **params):
        self.calls.append(params)
        if self.error:
            raise self.error
        return iter(self.chunks)


def test_openai_streams_and_keeps_system_role():
    fake = FakeOpenAI([NS(choices=[]), chunk("Hel"), chunk("lo"), chunk(None, "stop")])
    out = "".join(OpenAIClient("gpt-x", "k", client=fake).stream_chat(MSGS, temperature=0.2))
    assert out == "Hello"
    params = fake.calls[0]
    assert params["stream"] is True and params["model"] == "gpt-x"
    assert params["messages"][0]["role"] == "system"
    assert "temperature" not in params


def test_openai_length_cutoff_note():
    fake = FakeOpenAI([chunk("x"), chunk(None, "length")])
    assert "".join(OpenAIClient("m", "k", client=fake).stream_chat(MSGS)) == "x" + TRUNCATION_NOTE


@pytest.mark.parametrize(
    "error,match",
    [
        (http_error(openai, openai.AuthenticationError, 401), "API key"),
        (http_error(openai, openai.RateLimitError, 429), "quota"),
        (openai.APIConnectionError(request=REQ), "internet"),
    ],
)
def test_openai_errors(error, match):
    with pytest.raises(LLMError, match=match):
        list(OpenAIClient("m", "k", client=FakeOpenAI([], error=error)).stream_chat(MSGS))


# --- local + router ------------------------------------------------------------------
class FakeLLM:
    def __init__(self):
        self.closed = False

    def stream_chat(self, messages, temperature=0.7):
        yield "local reply"

    def close(self):
        self.closed = True


class FakeServer:
    def __init__(self):
        self.events = []

    def use_model(self, model):
        self.events.append(("use", model))

    def wait_until_ready(self, timeout):
        self.events.append(("wait",))


def test_local_client_switches_model_before_streaming():
    server = FakeServer()
    out = "".join(LocalModelClient("repo:Q4", server, FakeLLM()).stream_chat(MSGS))
    assert out == "local reply"
    assert server.events == [("use", "repo:Q4"), ("wait",)]


def test_router_picks_clients_and_caches_cloud_ones():
    router = ModelRouter(FakeLLM(), FakeServer(), get_key=lambda p: {"anthropic": "ak"}.get(p))
    assert isinstance(router.client_for(ModelSpec("local", "a:b")), LocalModelClient)
    c1 = router.client_for(ModelSpec("anthropic", "claude-opus-5-5"))
    assert isinstance(c1, ClaudeClient)
    assert router.client_for(ModelSpec("anthropic", "claude-opus-5-5")) is c1
    assert isinstance(router.client_for(ModelSpec("openai", "m")), MissingKeyClient)


def test_missing_key_message():
    with pytest.raises(LLMError, match="No ChatGPT API key"):
        list(MissingKeyClient("openai").stream_chat(MSGS))
