"""Building model context: normal chat, handoff briefs, and branch children."""

from __future__ import annotations

from collections.abc import Sequence

from .store import Message

BASE_SYSTEM = (
    "You are a helpful, concise assistant inside a mind-map chat app. "
    "Each conversation is one node on a map; users branch side topics into "
    "new nodes."
)

BRIEF_INSTRUCTIONS = (
    "The user wants to branch this conversation into a NEW, separate chat "
    "session focused on: {topic}\n\n"
    "Write a handoff brief for that new session. The new session will see "
    "ONLY this brief, not the conversation above. Include:\n"
    "- Goal: one sentence on what the new session should explore.\n"
    "- Context: the facts, decisions, constraints and terminology from this "
    "conversation that matter for that topic. Leave out anything unrelated.\n"
    "- Open questions: what is still undecided about the topic.\n\n"
    "Write it as plain Markdown with those three headings. Be specific and "
    "brief (under 250 words). Output only the brief."
)

# Characters, not tokens: ~4 chars/token keeps us well inside an 8k context.
DEFAULT_HISTORY_CHARS = 16_000


def trim_history(
    messages: Sequence[Message], max_chars: int = DEFAULT_HISTORY_CHARS
) -> list[Message]:
    """Keep the most recent messages that fit in max_chars (always at least 1)."""
    kept: list[Message] = []
    total = 0
    for m in reversed(messages):
        total += len(m.content)
        if kept and total > max_chars:
            break
        kept.append(m)
    return list(reversed(kept))


def system_prompt(brief: str | None) -> str:
    if not brief:
        return BASE_SYSTEM
    return (
        f"{BASE_SYSTEM}\n\nThis session was branched from a parent "
        f"conversation. Handoff brief from the parent:\n\n{brief}"
    )


def chat_context(
    brief: str | None,
    history: Sequence[Message],
    max_chars: int = DEFAULT_HISTORY_CHARS,
) -> list[dict]:
    """Messages to send for a normal chat turn in a session."""
    msgs = [{"role": "system", "content": system_prompt(brief)}]
    msgs += [{"role": m.role, "content": m.content} for m in trim_history(history, max_chars)]
    return msgs


def brief_request(
    brief: str | None,
    history: Sequence[Message],
    topic: str,
    max_chars: int = DEFAULT_HISTORY_CHARS,
) -> list[dict]:
    """Messages asking the model to write a handoff brief for a new branch."""
    msgs = chat_context(brief, history, max_chars)
    msgs.append(
        {"role": "user", "content": BRIEF_INSTRUCTIONS.format(topic=topic.strip())}
    )
    return msgs


def title_from_text(text: str, limit: int = 40) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line or "New chat"
    return one_line[: limit - 1].rstrip() + "…"
