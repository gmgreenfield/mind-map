"""Zoomed-in view of one session: breadcrumb, transcript, input."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..store import Message, Session

ARROWS = {Qt.Key_Up: "N", Qt.Key_Down: "S", Qt.Key_Left: "W", Qt.Key_Right: "E"}


class ChatInput(QPlainTextEdit):
    """Enter sends, Shift+Enter newline. ⌘+arrow navigates when the input is empty."""

    submitted = Signal(str)
    navigate = Signal(str)

    def keyPressEvent(self, event) -> None:
        key, mods = event.key(), event.modifiers()
        if key in (Qt.Key_Return, Qt.Key_Enter) and not (mods & Qt.ShiftModifier):
            text = self.toPlainText()
            if text.strip():
                self.submitted.emit(text)
            return
        if key in ARROWS and (mods & Qt.ControlModifier) and not self.toPlainText():
            self.navigate.emit(ARROWS[key])
            return
        super().keyPressEvent(event)


def render_markdown(brief: str | None, messages: list[Message], partial: str | None) -> str:
    parts: list[str] = []
    if brief:
        quoted = "\n".join(f"> {line}" for line in brief.splitlines())
        parts.append(f"> **Handoff brief from parent**\n>\n{quoted}")
    for m in messages:
        who = "You" if m.role == "user" else "Qwen"
        parts.append(f"**{who}**\n\n{m.content}")
    if partial is not None:
        parts.append(f"**Qwen**\n\n{partial or '…'}")
    if not parts:
        parts.append("*Empty session. Say something, or type `/branch <topic>` later to fork.*")
    return "\n\n---\n\n".join(parts)


class ChatView(QWidget):
    sendRequested = Signal(str)
    backRequested = Signal()
    branchRequested = Signal()
    sessionRequested = Signal(int)
    navigateRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.crumbs = QLabel()
        self.crumbs.setTextFormat(Qt.RichText)
        self.crumbs.linkActivated.connect(lambda href: self.sessionRequested.emit(int(href)))
        self.map_btn = QPushButton("Map  (Esc)")
        self.map_btn.clicked.connect(self.backRequested)
        self.branch_btn = QPushButton("Branch…")
        self.branch_btn.clicked.connect(self.branchRequested)

        top = QHBoxLayout()
        top.addWidget(self.map_btn)
        top.addWidget(self.crumbs, 1)
        top.addWidget(self.branch_btn)

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setFocusPolicy(Qt.ClickFocus)

        self.input = ChatInput()
        self.input.setPlaceholderText(
            "Message Qwen…   /branch <topic> to fork · /parent · ⌘+arrows to move (empty input)"
        )
        self.input.setFixedHeight(80)
        self.input.submitted.connect(self.sendRequested)
        self.input.navigate.connect(self.navigateRequested)

        self.status = QLabel()
        self.status.setStyleSheet("color: #c0504d;")
        self.status.hide()
        self._status_timer = QTimer(self, singleShot=True, interval=5000)
        self._status_timer.timeout.connect(self.status.hide)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.addLayout(top)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.input)

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.backRequested.emit)

    def show_session(
        self,
        ancestry: list[Session],
        messages: list[Message],
        partial: str | None = None,
    ) -> None:
        links = [
            f'<a href="{s.id}" style="text-decoration:none">{html.escape(s.title)}</a>'
            for s in ancestry[:-1]
        ]
        links.append(f"<b>{html.escape(ancestry[-1].title)}</b>")
        self.crumbs.setText("  ›  ".join(links))
        self._brief = ancestry[-1].brief
        self._messages = messages
        self.set_partial(partial)

    def set_partial(self, partial: str | None) -> None:
        bar = self.transcript.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.transcript.setMarkdown(render_markdown(self._brief, self._messages, partial))
        if at_bottom or partial is not None:
            bar.setValue(bar.maximum())

    def clear_input(self) -> None:
        self.input.clear()

    def focus_input(self) -> None:
        self.input.setFocus()

    def flash(self, text: str) -> None:
        self.status.setText(text)
        self.status.show()
        self._status_timer.start()
