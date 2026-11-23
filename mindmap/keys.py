"""API keys for cloud models, kept in the macOS Keychain.

An environment variable (ANTHROPIC_API_KEY / OPENAI_API_KEY) wins over the
Keychain, so developers can keep using their shell setup.
"""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

SERVICE = "Mind Map"
ENV_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def get_key(provider: str) -> str | None:
    env = os.environ.get(ENV_VARS.get(provider, ""), "").strip()
    if env:
        return env
    try:
        return keyring.get_password(SERVICE, provider) or None
    except KeyringError:
        return None


def key_source(provider: str) -> str | None:
    """'env', 'keychain' or None, for showing where a key comes from."""
    if os.environ.get(ENV_VARS.get(provider, ""), "").strip():
        return "env"
    try:
        return "keychain" if keyring.get_password(SERVICE, provider) else None
    except KeyringError:
        return None


def set_key(provider: str, key: str) -> None:
    keyring.set_password(SERVICE, provider, key.strip())


def delete_key(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE, provider)
    except KeyringError:
        pass
