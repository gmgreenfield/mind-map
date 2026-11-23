"""Which model a session uses: a provider plus a model name.

Stored as "provider:name", e.g. "local:unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M",
"anthropic:claude-opus-5-5" or "openai:<model id>". Split on the first colon only,
since local names contain one.
"""

from __future__ import annotations

from dataclasses import dataclass

PROVIDERS = {
    "local": "Local",
    "anthropic": "Claude",
    "openai": "ChatGPT",
}
COMPANIES = {"anthropic": "Anthropic", "openai": "OpenAI"}


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    name: str

    @classmethod
    def parse(cls, value: str | None) -> "ModelSpec":
        if not value:
            return DEFAULT_MODEL
        provider, sep, name = value.partition(":")
        if not sep or provider not in PROVIDERS or not name:
            return DEFAULT_MODEL
        return cls(provider, name)

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"

    @property
    def is_local(self) -> bool:
        return self.provider == "local"

    @property
    def label(self) -> str:
        """Short name for the map and the chat header."""
        if self.provider == "local":
            repo = self.name.split(":")[0].split("/")[-1]
            return repo.removesuffix("-GGUF").removesuffix("-gguf")
        for label, model_id in CLAUDE_PRESETS:
            if model_id == self.name:
                return label
        return self.name


DEFAULT_MODEL = ModelSpec("local", "unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M")

# (label, Hugging Face "repo:quant" for llama-server -hf, note)
LOCAL_PRESETS = [
    ("Qwen3 4B Instruct", "unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M",
     "2.5 GB download · fast on any Mac"),
    ("Qwen3 30B-A3B Instruct", "unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:Q4_K_M",
     "~18 GB download · smarter, needs 32 GB RAM"),
]

CLAUDE_PRESETS = [
    ("Claude Opus 5.5", "claude-opus-5-5"),
    ("Claude Sonnet 5.5", "claude-sonnet-5-5"),
    ("Claude Haiku 5.5", "claude-haiku-5-5"),
]
