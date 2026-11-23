"""A fake Qwen for exercising the UI without a model server.

Same interface as LLMClient.stream_chat. Replies stream word by word with a
small delay. Branch-brief requests get a brief built from the actual parent
conversation, so you can see context being handed to the child.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Iterator

from .branching import BRIEF_INSTRUCTIONS

_BRIEF_MARKER = BRIEF_INSTRUCTIONS.split("{topic}")[0][-60:]

# Keyword -> reply. First match (in order) wins.
SCRIPTED: list[tuple[tuple[str, ...], str]] = [
    (
        ("hello", "hi", "hey"),
        "Hi! I'm a **mock** Qwen — replies are canned so you can test the map "
        "without a model. Try `/branch <topic>` to fork this chat.",
    ),
    (
        ("price", "pricing", "cost", "budget"),
        "Let's break the cost down:\n\n"
        "1. **Fixed costs** — rent, equipment, insurance.\n"
        "2. **Variable costs** — materials per unit, packaging, shipping.\n"
        "3. **Margin** — aim for 60–70% gross margin on direct sales.\n\n"
        "Want to branch into a detailed spreadsheet model?",
    ),
    (
        ("name", "brand", "logo"),
        "A few naming directions:\n\n"
        "- **Descriptive** — says what it is (clear, forgettable).\n"
        "- **Evocative** — hints at a feeling or place.\n"
        "- **Invented** — unique and trademarkable, but needs explaining.\n\n"
        "Evocative usually wins for small, local brands.",
    ),
    (
        ("risk", "problem", "worry", "concern"),
        "The main risks I see:\n\n"
        "- Underestimating time to the first paying customer.\n"
        "- Supplier dependency.\n"
        "- Cash flow in the first six months.\n\n"
        "Each of those could be its own branch.",
    ),
    (
        ("code", "python", "function", "bug"),
        "Here's a sketch:\n\n```python\ndef branch(session, topic):\n"
        "    brief = summarise(session, focus=topic)\n"
        "    return Session(parent=session, brief=brief)\n```\n\n"
        "The key design choice is that the child sees only the brief.",
    ),
    (
        ("plan", "steps", "next", "start"),
        "A simple plan:\n\n"
        "1. Write down the goal in one sentence.\n"
        "2. List what you already know and what's still open.\n"
        "3. Pick the riskiest open question and test it cheaply.\n"
        "4. Branch each big open question into its own session.",
    ),
]

GENERIC = [
    "Good question. Three angles worth considering: what you want to "
    "achieve, what constrains you, and what you'd do first. Which matters most?",
    "Here's how I'd think about it: start from the outcome, work backwards to "
    "the smallest next step, and keep side questions out of this thread — "
    "they make good branches.",
    "There are trade-offs either way. If you tell me which you care about more "
    "— speed, cost or quality — I can narrow it down.",
]


def tokenize(text: str) -> list[str]:
    """Split into word-ish chunks that join back to the original text."""
    return re.findall(r"\s*\S+|\s+", text)


def _first_sentence(text: str, limit: int = 110, min_len: int = 30) -> str:
    """Leading sentences, enough to say something (>= min_len), capped at limit."""
    text = " ".join(text.replace("*", "").replace("`", "").split())
    sentences = re.findall(r".+?[.!?](?=\s|$)|.+$", text)
    s = ""
    for sent in sentences:
        s = f"{s} {sent.strip()}".strip()
        if len(s) >= min_len:
            break
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _goal_from_system(system: str) -> str | None:
    m = re.search(r"Goal:?\**\s*\n?\s*(.+)", system)
    return m.group(1).strip() if m else None


def parse_brief_request(content: str) -> tuple[str, list[tuple[str, str]], str | None]:
    """Pull (topic, [(role, text)], parent_goal) out of a brief request."""
    m = re.search(r"focused on: (.+)", content)
    topic = m.group(1).strip() if m else "the new topic"
    t = re.search(r"TRANSCRIPT:\n<<<\n(.*?)\n>>>", content, re.S)
    convo: list[tuple[str, str]] = []
    if t:
        for chunk in re.split(r"\n\n(?=(?:USER|ASSISTANT): )", t.group(1)):
            role, _, text = chunk.partition(": ")
            if role in ("USER", "ASSISTANT"):
                convo.append(("user" if role == "USER" else "assistant", text))
    bg = re.search(r"BACKGROUND[^\n]*\n(.*?)\n\nTRANSCRIPT:", content, re.S)
    goal = _goal_from_system(bg.group(1)) if bg else None
    return topic, convo, goal


def make_brief(
    topic: str, convo: list[tuple[str, str]], parent_goal: str | None = None
) -> str:
    facts = [
        f"- {'User' if role == 'user' else 'Assistant'}: {_first_sentence(text)}"
        for role, text in convo[-4:]
    ] or ["- (The parent conversation was empty.)"]
    if parent_goal:
        facts.insert(0, f"- Parent session's goal: {parent_goal}")
    return (
        f"## Goal\nExplore {topic} in depth.\n\n"
        "## Context\n" + "\n".join(facts) + "\n\n"
        f"## Open questions\n- What does success look like for {topic}?\n"
        "- What are the constraints and the first concrete step?"
    )


def make_reply(messages: list[dict]) -> str:
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    lowered = last_user.lower()
    words = set(re.findall(r"[a-z]+", lowered))
    for keys, reply in SCRIPTED:
        if any(k in words for k in keys):
            return reply
    system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
    goal = _goal_from_system(system)
    digest = int(hashlib.sha1(last_user.encode()).hexdigest(), 16)
    reply = GENERIC[digest % len(GENERIC)]
    if goal:
        reply = f"Keeping to this branch's goal — *{goal}* — {reply[0].lower()}{reply[1:]}"
    return reply


class MockLLMClient:
    def __init__(self, delay: float = 0.03):
        self.delay = delay
        self.calls: list[list[dict]] = []

    def close(self) -> None:
        pass

    def stream_chat(self, messages: list[dict], temperature: float = 0.7) -> Iterator[str]:
        self.calls.append(messages)
        last = messages[-1]["content"] if messages else ""
        if _BRIEF_MARKER in last:
            text = make_brief(*parse_brief_request(last))
        else:
            text = make_reply(messages)
        for tok in tokenize(text):
            if self.delay:
                time.sleep(self.delay)
            yield tok

    def complete(self, messages: list[dict], temperature: float = 0.7) -> str:
        return "".join(self.stream_chat(messages, temperature))
