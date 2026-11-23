"""Building model context: normal chat, handoff briefs, and branch children."""

from __future__ import annotations

from collections.abc import Sequence

from .store import Message

BASE_SYSTEM = (
    "You are a helpful, concise assistant inside a mind-map chat app. "
    "Each conversation is one node on a map; users branch side topics into "
    "new nodes."
)

BRIEF_SYSTEM = (
    "You write handoff briefs that summarise conversations accurately. "
    "Never invent facts or reverse conclusions."
)

BRIEF_INSTRUCTIONS = (
    "The user wants to branch the transcript above into a NEW, separate chat "
    "session focused on: {topic}\n\n"
    "Write a handoff brief for that new session. The new session will see "
    "ONLY this brief, not the transcript. Include:\n"
    "- Goal: one sentence on what the new session should explore.\n"
    "- Context: facts, decisions and constraints that were actually stated "
    "in the transcript and matter for that topic. Include conclusions "
    "already reached (e.g. which option was preferred). Do NOT add facts, "
    "names, numbers or assumptions that were not said. Leave out anything "
    "unrelated.\n"
    "- Open questions: at most 4 short questions still undecided about "
    "the topic.\n\n"
    "Use the headings '## Goal', '## Context' and '## Open questions'. "
    "Keep it under 150 words. Output only the brief."
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
    """Messages asking the model to write a handoff brief for a new branch.

    The conversation is passed as a quoted transcript in one message rather
    than as chat turns: Qwen3-4B summarised chat turns unreliably (it
    reversed a stated conclusion in 4/4 runs) but got it right 3/3 times
    from a transcript.
    """
    lines = [
        f"{'USER' if m.role == 'user' else 'ASSISTANT'}: {m.content}"
        for m in trim_history(history, max_chars)
    ]
    parts = []
    if brief:
        parts.append(f"BACKGROUND (the brief this conversation started from):\n{brief}")
    parts.append("TRANSCRIPT:\n<<<\n" + ("\n\n".join(lines) or "(empty)") + "\n>>>")
    parts.append(BRIEF_INSTRUCTIONS.format(topic=topic.strip()))
    return [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def title_from_text(text: str, limit: int = 40) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line or "New chat"
    return one_line[: limit - 1].rstrip() + "…"
