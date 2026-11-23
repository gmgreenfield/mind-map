"""Parse slash commands typed into the chat input."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str  # "branch" | "parent" | "map" | "unknown"
    arg: str = ""


@dataclass(frozen=True)
class CommandError:
    message: str


KNOWN = {"branch", "parent", "map"}


def parse(text: str) -> Command | CommandError | None:
    """Return a Command, a CommandError, or None when the text is a normal message."""
    stripped = text.strip()
    if not stripped.startswith("/") or stripped.startswith("//"):
        return None
    head, _, rest = stripped[1:].partition(" ")
    name = head.lower()
    arg = rest.strip()
    if name not in KNOWN:
        return CommandError(f"Unknown command /{head}. Try /branch <topic>, /parent or /map.")
    if name == "branch" and not arg:
        return CommandError("Usage: /branch <topic to explore in the new session>")
    return Command(name, arg)


def unescape(text: str) -> str:
    """'//foo' sends a literal '/foo' message."""
    stripped = text.strip()
    return stripped[1:] if stripped.startswith("//") else text
