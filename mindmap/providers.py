"""One streaming interface over the local server, Claude and ChatGPT.

Every client here has stream_chat(messages, temperature) -> Iterator[str] and
raises LLMError with a message fit to show in the chat, like LLMClient.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import anthropic
import openai

from . import keys
from .llm import TRUNCATION_NOTE, LLMClient, LLMError
from .models import PROVIDERS, ModelSpec

REFUSAL_NOTE = "\n\n*[The model declined to answer this.]*"

CLAUDE_MAX_TOKENS = 64_000
# Models that take the server-side refusal fallback ("default" routes by category).
CLAUDE_FALLBACK_MODELS = {
    "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
    "claude-fable-5-2", "claude-fable-5-1",
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Claude takes the system prompt as a separate field."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    return system, rest


class ClaudeClient:
    def __init__(self, model: str, api_key: str, client: anthropic.Anthropic | None = None):
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key)

    def stream_chat(self, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        # temperature is ignored: current Claude models reject sampling parameters.
        system, convo = split_system(messages)
        params: dict = {"model": self.model, "max_tokens": CLAUDE_MAX_TOKENS, "messages": convo}
        if system:
            params["system"] = system
        try:
            if self.model in CLAUDE_FALLBACK_MODELS:
                manager = self.client.beta.messages.stream(
                    **params, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                manager = self.client.messages.stream(**params)
            with manager as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
            if final.stop_reason == "refusal":
                yield REFUSAL_NOTE
            elif final.stop_reason == "max_tokens":
                yield TRUNCATION_NOTE
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude rejected the API key. Update it from the model menu.") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Claude doesn't know the model “{self.model}”.") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Claude rate limit hit. Wait a moment and try again.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Can't reach Claude. Check your internet connection.") from e


class OpenAIClient:
    def __init__(self, model: str, api_key: str, client: openai.OpenAI | None = None):
        self.model = model
        self.client = client or openai.OpenAI(api_key=api_key)

    def stream_chat(self, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        # temperature is left at the model default: reasoning models reject other values.
        try:
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, stream=True
            )
            truncated = False
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason == "length":
                    truncated = True
                if choice.delta and choice.delta.content:
                    yield choice.delta.content
            if truncated:
                yield TRUNCATION_NOTE
        except openai.AuthenticationError as e:
            raise LLMError("OpenAI rejected the API key. Update it from the model menu.") from e
        except openai.NotFoundError as e:
            raise LLMError(f"OpenAI doesn't know the model “{self.model}”.") from e
        except openai.RateLimitError as e:
            raise LLMError("OpenAI rate limit or quota hit. Check your account and try again.") from e
        except openai.APIStatusError as e:
            raise LLMError(f"OpenAI error {e.status_code}: {e.message}") from e
        except openai.APIConnectionError as e:
            raise LLMError("Can't reach OpenAI. Check your internet connection.") from e


class LocalModelClient:
    """Makes sure llama-server is running the wanted model, then streams from it."""

    def __init__(self, model: str, server, llm: LLMClient, load_timeout: float = 1800):
        self.model = model
        self.server = server
        self.llm = llm
        self.load_timeout = load_timeout

    def stream_chat(self, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        if self.server is not None:
            self.server.use_model(self.model)
            self.server.wait_until_ready(self.load_timeout)
        yield from self.llm.stream_chat(messages, temperature)


class MissingKeyClient:
    def __init__(self, provider: str):
        self.provider = provider

    def stream_chat(self, messages, temperature=0.7):
        raise LLMError(
            f"No {PROVIDERS[self.provider]} API key yet. Click the model name above to add one."
        )
        yield  # pragma: no cover  (makes this a generator)


class ModelRouter:
    """Hands out the right client for a session's model."""

    def __init__(self, llm: LLMClient, server=None, get_key=keys.get_key):
        self.llm = llm
        self.server = server
        self.get_key = get_key
        self._cache: dict[tuple, object] = {}
        self._lock = threading.Lock()

    def client_for(self, spec: ModelSpec):
        if spec.is_local:
            return LocalModelClient(spec.name, self.server, self.llm)
        key = self.get_key(spec.provider)
        if not key:
            return MissingKeyClient(spec.provider)
        cache_key = (spec.provider, spec.name, key)
        with self._lock:
            if cache_key not in self._cache:
                cls = ClaudeClient if spec.provider == "anthropic" else OpenAIClient
                self._cache[cache_key] = cls(spec.name, key)
            return self._cache[cache_key]

    def close(self) -> None:
        self.llm.close()


def list_cloud_models(provider: str, api_key: str) -> list[str]:
    """Model IDs the account can use, newest first where the API says so."""
    if provider == "anthropic":
        client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=15)
        return [m.id for m in client.models.list()]
    client = openai.OpenAI(api_key=api_key, max_retries=0, timeout=15)
    models = sorted(client.models.list(), key=lambda m: getattr(m, "created", 0), reverse=True)
    return [m.id for m in models]

