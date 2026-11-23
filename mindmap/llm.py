"""Streaming client for an OpenAI-compatible chat server (llama-server)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"

# ~380 words: a hard ceiling so a rambling reply can't take minutes on CPU.
DEFAULT_MAX_TOKENS = 512
TRUNCATION_NOTE = "\n\n*[Reply cut off at the length limit. Say \u201ccontinue\u201d for more.]*"


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "qwen",
        timeout: float = 300.0,
        transport: httpx.BaseTransport | None = None,
        max_tokens: int | None = DEFAULT_MAX_TOKENS,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.http = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def stream_chat(
        self, messages: list[dict], temperature: float = 0.7
    ) -> Iterator[str]:
        """Yield content deltas as the server generates them."""
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        truncated = False
        try:
            with self.http.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise LLMError(f"server returned {resp.status_code}: {resp.text}")
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    if choices[0].get("finish_reason") == "length":
                        truncated = True
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
            if truncated:
                yield TRUNCATION_NOTE
        except httpx.ConnectError as e:
            raise LLMError(
                "can't reach the model server — is scripts/serve.sh running?"
            ) from e
        except httpx.HTTPError as e:
            raise LLMError(str(e)) from e

    def complete(self, messages: list[dict], temperature: float = 0.7) -> str:
        return "".join(self.stream_chat(messages, temperature))
