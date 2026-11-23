import keyring
import pytest
from keyring.backend import KeyringBackend

from mindmap import keys
from mindmap.models import DEFAULT_MODEL, ModelSpec


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, password):
        self.store[(service, user)] = password

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


@pytest.fixture
def memkeys(monkeypatch):
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
    keyring.set_keyring(old)


# --- ModelSpec -----------------------------------------------------------------
def test_parse_round_trip_keeps_colons_in_local_names():
    spec = ModelSpec.parse("local:unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M")
    assert spec == ModelSpec("local", "unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M")
    assert str(spec) == "local:unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
    assert spec.is_local


@pytest.mark.parametrize("bad", [None, "", "nope", "weird:thing", "anthropic:"])
def test_bad_values_fall_back_to_default(bad):
    assert ModelSpec.parse(bad) == DEFAULT_MODEL


def test_labels():
    assert ModelSpec.parse("local:unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M").label == "Qwen3-4B-Instruct-2507"
    assert ModelSpec("anthropic", "claude-opus-5-5").label == "Claude Opus 5.5"
    assert ModelSpec("openai", "some-model").label == "some-model"


# --- keys ------------------------------------------------------------------------
def test_keychain_round_trip(memkeys):
    assert keys.get_key("anthropic") is None and keys.key_source("anthropic") is None
    keys.set_key("anthropic", "  sk-test  ")
    assert keys.get_key("anthropic") == "sk-test"
    assert keys.key_source("anthropic") == "keychain"
    keys.delete_key("anthropic")
    assert keys.get_key("anthropic") is None


def test_env_var_wins(memkeys, monkeypatch):
    keys.set_key("openai", "from-keychain")
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert keys.get_key("openai") == "from-env"
    assert keys.key_source("openai") == "env"
