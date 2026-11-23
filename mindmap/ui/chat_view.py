"""Zoomed-in view of one session: breadcrumb, brief card, message bubbles, input."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..store import Message, Session
from . import style

ARROWS = {Qt.Key_Up: "N", Qt.Key_Down: "S", Qt.Key_Left: "W", Qt.Key_Right: "E"}
BUBBLE_WIDTH = 0.78  # fraction of the message area a bubble may use

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)(?:```|\Z)", re.S)


def split_segments(text: str) -> list[tuple[str, str, str]]:
    """Split Markdown into ("text", md, "") and ("code", source, lang) parts.

    An unclosed fence (mid-stream) counts as code running to the end.
    """
    out: list[tuple[str, str, str]] = []
    pos = 0
    for m in _FENCE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()], ""))
        out.append(("code", m.group(2).rstrip("\n"), m.group(1).strip()))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:], ""))
    return [s for s in out if s[0] == "code" or s[1].strip()] or [("text", text, "")]


def md_to_html(text: str) -> str:
    """Markdown to Qt rich text, with a monospace font macOS actually has.

    Qt asks for 'monospace' for inline code; macOS has no such family and
    falls back to a serif.
    """
    doc = QTextDocument()
    doc.setMarkdown(text.strip())
    return doc.toHtml().replace("font-family:'monospace'", "font-family:'Menlo'")


class _MdLabel(QLabel):
    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        super().setText(md_to_html(text))


def _md_label(text: str) -> QLabel:
    label = _MdLabel()
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    label.setOpenExternalLinks(True)
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    label.setText(text.strip())
    return label


class CodeBlock(QFrame):
    def __init__(self, code: str, lang: str):
        super().__init__()
        self.setObjectName("codeBlock")
        self.lang = QLabel(lang or "code")
        self.lang.setObjectName("lang")
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.clicked.connect(self.copy)
        # Owned by this block, so it dies with it (a bare singleShot would fire
        # after the block is deleted mid-stream and crash).
        self._reset = QTimer(self, singleShot=True, interval=1500)
        self._reset.timeout.connect(lambda: self.copy_btn.setText("Copy"))
        self.code = QLabel()
        self.code.setObjectName("code")
        self.code.setTextFormat(Qt.PlainText)
        self.code.setWordWrap(True)
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        head = QHBoxLayout()
        head.addWidget(self.lang)
        head.addStretch(1)
        head.addWidget(self.copy_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(4)
        layout.addLayout(head)
        layout.addWidget(self.code)
        self.set_code(code, lang)

    def set_code(self, code: str, lang: str) -> None:
        self._source = code
        self.code.setText(code)
        self.lang.setText(lang or "code")

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self._source)
        self.copy_btn.setText("Copied")
        self._reset.start()


class Bubble(QFrame):
    """One message. Re-renders in place while text streams in."""

    def __init__(self, role: str, text: str = ""):
        super().__init__()
        self.role = role
        self.setObjectName("userBubble" if role == "user" else "assistantBubble")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(8)
        self._parts: list[tuple[str, QWidget]] = []
        self.text = ""
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self.text = text
        segments = split_segments(text)
        if [k for k, _, _ in segments] == [k for k, _ in self._parts]:
            for (kind, content, lang), (_, widget) in zip(segments, self._parts):
                if kind == "code":
                    widget.set_code(content, lang)
                else:
                    widget.setText(content.strip())
            return
        for _, widget in self._parts:
            widget.deleteLater()
        self._parts = []
        for kind, content, lang in segments:
            widget = CodeBlock(content, lang) if kind == "code" else _md_label(content)
            self._layout.addWidget(widget)
            self._parts.append((kind, widget))

    def code_blocks(self) -> list[CodeBlock]:
        return [w for k, w in self._parts if k == "code"]


class ThinkingBubble(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("thinkingBubble")
        self.label = QLabel("Qwen is thinking")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(self.label)
        self._dots = 0
        self._timer = QTimer(self, interval=400)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.label.setText("Qwen is thinking" + "." * self._dots)


class MessageRow(QWidget):
    """Aligns a bubble left (Qwen) or right (you), with a small role label."""

    def __init__(self, bubble: QFrame, role: str):
        super().__init__()
        self.bubble = bubble
        who = QLabel("You" if role == "user" else "Qwen")
        who.setObjectName("role")
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(who, 0, Qt.AlignRight if role == "user" else Qt.AlignLeft)
        col.addWidget(bubble)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row.addStretch(1)
            row.addLayout(col)
        else:
            row.addLayout(col)
            row.addStretch(1)


class BriefCard(QFrame):
    """The parent's handoff brief, foldable."""

    def __init__(self):
        super().__init__()
        self.setObjectName("briefCard")
        self.toggle = QToolButton()
        self.toggle.setObjectName("briefToggle")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toggle.toggled.connect(self.set_expanded)
        self.body = _md_label("")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 10)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.hide()

    def set_brief(self, brief: str | None, expanded: bool) -> None:
        if not brief:
            self.hide()
            return
        self.body.setText(brief.strip())
        self.show()
        self.toggle.setChecked(expanded)
        self.set_expanded(expanded)

    def set_expanded(self, expanded: bool) -> None:
        arrow = "▾" if expanded else "▸"
        self.toggle.setText(f"{arrow}  Handoff brief from parent")
        self.body.setVisible(expanded)

    def expanded(self) -> bool:
        return self.body.isVisibleTo(self)


class ChatInput(QPlainTextEdit):
    """Enter sends, Shift+Enter newline. ⌘+arrow navigates when the input is empty.

    Grows with its content up to a few lines.
    """

    submitted = Signal(str)
    navigate = Signal(str)
    MIN_LINES, MAX_LINES = 1, 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.textChanged.connect(self._fit_height)
        self._fit_height()

    def _fit_height(self) -> None:
        wanted = max(self.MIN_LINES, int(self.document().size().height()))
        lines = min(self.MAX_LINES, wanted)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if wanted > self.MAX_LINES else Qt.ScrollBarAlwaysOff
        )
        self.setFixedHeight(lines * self.fontMetrics().lineSpacing() + 20)

    def changeEvent(self, event) -> None:
        # The stylesheet font arrives after construction; refit when it does.
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._fit_height()

    def keyPressEvent(self, event) -> None:
        key, mods = event.key(), event.modifiers()
        if key in (Qt.Key_Return, Qt.Key_Enter) and not (mods & Qt.ShiftModifier):
            self.submit()
            return
        if key in ARROWS and (mods & Qt.ControlModifier) and not self.toPlainText():
            self.navigate.emit(ARROWS[key])
            return
        super().keyPressEvent(event)

    def submit(self) -> None:
        text = self.toPlainText()
        if text.strip():
            self.submitted.emit(text)


class ChatView(QWidget):
    sendRequested = Signal(str)
    backRequested = Signal()
    branchRequested = Signal()
    sessionRequested = Signal(int)
    navigateRequested = Signal(str)
    renameRequested = Signal()
    modelRequested = Signal()
    deleteRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chatView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._link_color = style.current().accent

        # Top bar
        self.map_btn = QPushButton("‹  Map")
        self.map_btn.setToolTip("Back to the map (Esc)")
        self.map_btn.clicked.connect(self.backRequested)
        self.crumbs = QLabel()
        self.crumbs.setObjectName("crumbs")
        self.crumbs.setTextFormat(Qt.RichText)
        self.crumbs.linkActivated.connect(lambda href: self.sessionRequested.emit(int(href)))
        self.menu_btn = QToolButton()
        self.menu_btn.setObjectName("menuButton")
        self.menu_btn.setText("⋯")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.menu_btn)
        self.rename_action = menu.addAction("Rename…", self.renameRequested.emit)
        self.delete_action = menu.addAction("Delete…", self.deleteRequested.emit)
        self.menu_btn.setMenu(menu)
        self.branch_btn = QPushButton("Branch")
        self.branch_btn.setObjectName("accentButton")
        self.branch_btn.setToolTip("Start a new branch from this chat (/branch <topic>)")
        self.branch_btn.clicked.connect(self.branchRequested)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.map_btn)
        top.addWidget(self.crumbs, 1)
        self.model_btn = QPushButton()
        self.model_btn.setObjectName("modelChip")
        self.model_btn.setToolTip("Change the model for this chat")
        self.model_btn.clicked.connect(self.modelRequested)
        top.addWidget(self.model_btn)
        self.model_status = QLabel()
        self.model_status.setObjectName("subtle")
        self.model_status.setTextFormat(Qt.RichText)
        self.model_status.hide()
        top.addWidget(self.model_status)
        top.addWidget(self.menu_btn)
        top.addWidget(self.branch_btn)

        # Brief + messages
        self.brief_card = BriefCard()
        self.list_widget = QWidget()
        self.list_widget.setObjectName("messageList")
        self.list_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(4, 8, 12, 8)
        self.list_layout.setSpacing(14)
        self.list_layout.addWidget(self.brief_card)
        self.empty_hint = QLabel("Empty chat. Say something to Qwen.")
        self.empty_hint.setObjectName("subtle")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.list_layout.addWidget(self.empty_hint)
        self.list_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.list_widget)
        bar = self.scroll.verticalScrollBar()
        self._stick = True
        bar.valueChanged.connect(lambda v: setattr(self, "_stick", v >= bar.maximum() - 24))
        bar.rangeChanged.connect(lambda _lo, hi: self._stick and bar.setValue(hi))

        # Status + input
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.hide()
        self._status_timer = QTimer(self, singleShot=True, interval=5000)
        self._status_timer.timeout.connect(self.status.hide)

        self.input = ChatInput()
        self.input.setPlaceholderText("Message Qwen…    /branch <topic> · /parent · Esc for the map")
        self.input.submitted.connect(self.sendRequested)
        self.input.navigate.connect(self.navigateRequested)
        self.send_btn = QToolButton()
        self.send_btn.setObjectName("sendButton")
        self.send_btn.setText("↑")
        self.send_btn.setToolTip("Send (Enter)")
        self.send_btn.clicked.connect(self.input.submit)
        self.input.textChanged.connect(
            lambda: self.send_btn.setEnabled(bool(self.input.toPlainText().strip()))
        )
        self.send_btn.setEnabled(False)
        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        in_row = QHBoxLayout(input_frame)
        in_row.setContentsMargins(10, 6, 8, 6)
        in_row.addWidget(self.input, 1)
        in_row.addWidget(self.send_btn, 0, Qt.AlignBottom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 18)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.status)
        layout.addWidget(input_frame)

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.backRequested.emit)

        self.rows: list[MessageRow] = []
        self.partial_row: MessageRow | None = None

    # --- content ----------------------------------------------------------------
    def show_session(
        self,
        ancestry: list[Session],
        messages: list[Message],
        partial: str | None = None,
    ) -> None:
        links = [
            f'<a href="{s.id}" style="text-decoration:none; color:{self._link_color}">'
            f"{html.escape(s.title)}</a>"
            for s in ancestry[:-1]
        ]
        links.append(f"<b>{html.escape(ancestry[-1].title)}</b>")
        self.crumbs.setText("  ›  ".join(links))

        self._clear_rows()
        self.brief_card.set_brief(ancestry[-1].brief, expanded=not messages)
        for m in messages:
            self._add_row(Bubble(m.role, m.content), m.role)
        self._stick = True
        self.set_partial(partial)

    def set_partial(self, partial: str | None) -> None:
        """None: no reply in progress. "": waiting for the first token. Else: text so far."""
        if partial is None:
            if self.partial_row is not None:
                self._remove_row(self.partial_row)
                self.partial_row = None
        elif partial == "":
            if self.partial_row is None or not isinstance(self.partial_row.bubble, ThinkingBubble):
                if self.partial_row is not None:
                    self._remove_row(self.partial_row)
                self.partial_row = self._add_row(ThinkingBubble(), "assistant")
        else:
            if self.partial_row is None or not isinstance(self.partial_row.bubble, Bubble):
                if self.partial_row is not None:
                    self._remove_row(self.partial_row)
                self.partial_row = self._add_row(Bubble("assistant", partial), "assistant")
            else:
                self.partial_row.bubble.set_text(partial)
        self._update_empty_hint()

    def _add_row(self, bubble: QFrame, role: str) -> MessageRow:
        row = MessageRow(bubble, role)
        bubble.setMaximumWidth(self._bubble_width())
        self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self.rows.append(row)
        self._update_empty_hint()
        return row

    def _remove_row(self, row: MessageRow) -> None:
        self.rows.remove(row)
        self.list_layout.removeWidget(row)
        row.deleteLater()

    def _clear_rows(self) -> None:
        for row in list(self.rows):
            self._remove_row(row)
        self.partial_row = None

    def _update_empty_hint(self) -> None:
        self.empty_hint.setVisible(not self.rows)

    def _bubble_width(self) -> int:
        return max(240, int(self.scroll.viewport().width() * BUBBLE_WIDTH))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self._bubble_width()
        for row in self.rows:
            row.bubble.setMaximumWidth(w)

    def bubbles(self) -> list[QFrame]:
        return [r.bubble for r in self.rows]

    def transcript_text(self) -> str:
        parts = []
        for b in self.bubbles():
            parts.append(b.text if isinstance(b, Bubble) else b.label.text())
        return "\n\n".join(parts)

    # --- misc ---------------------------------------------------------------------
    def set_model_label(self, label: str, cloud: bool) -> None:
        self.model_btn.setText(f"{'☁  ' if cloud else ''}{label}  ▾")

    def set_model_status(self, html_text: str) -> None:
        self.model_status.setText(html_text)
        self.model_status.setVisible(bool(html_text))

    def clear_input(self) -> None:
        self.input.clear()

    def focus_input(self) -> None:
        self.input.setFocus()

    def flash(self, text: str) -> None:
        self.status.setText(text)
        self.status.show()
        self._status_timer.start()
