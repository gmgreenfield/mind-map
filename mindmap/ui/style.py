"""Shared colours and the app stylesheet, so the map and chat look like one app."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    border: str
    text: str
    subtext: str
    accent: str
    accent_text: str
    assistant_bubble: str
    code_bg: str
    grid: str
    node_border: str
    edge: str
    busy: str
    danger: str


LIGHT = Palette(
    dark=False,
    bg="#f6f6f4",
    surface="#ffffff",
    border="#e1e2e5",
    text="#1d1f23",
    subtext="#70747c",
    accent="#3d7bfd",
    accent_text="#ffffff",
    assistant_bubble="#ffffff",
    code_bg="#f0f1f3",
    grid="#e8e8e4",
    node_border="#c9cbd0",
    edge="#b4b8bf",
    busy="#e0a030",
    danger="#d9534f",
)

DARK = Palette(
    dark=True,
    bg="#1b1c1f",
    surface="#26282c",
    border="#3a3d43",
    text="#e8e8ea",
    subtext="#9a9ea6",
    accent="#4d8bff",
    accent_text="#ffffff",
    assistant_bubble="#2c2f35",
    code_bg="#17181b",
    grid="#26282c",
    node_border="#4a4f58",
    edge="#5a606b",
    busy="#e0a030",
    danger="#e5605b",
)


def system_is_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().window().color().lightness() < 128


def current() -> Palette:
    return DARK if system_is_dark() else LIGHT


def stylesheet(p: Palette) -> str:
    return f"""
    QWidget#chatView, QWidget#messageList, QDialog {{
        background: {p.bg};
        color: {p.text};
    }}
    QLabel {{ color: {p.text}; }}
    QLabel#subtle {{ color: {p.subtext}; font-size: 12px; }}
    QLabel#status {{ color: {p.danger}; font-size: 12px; }}
    QLabel#crumbs {{ color: {p.subtext}; font-size: 13px; }}

    QPushButton, QToolButton {{
        background: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 13px;
    }}
    QPushButton:hover, QToolButton:hover {{ border-color: {p.subtext}; }}
    QPushButton#accentButton {{
        background: {p.accent};
        color: {p.accent_text};
        border: none;
        font-weight: 600;
    }}
    QPushButton#accentButton:disabled {{ background: {p.border}; color: {p.subtext}; }}
    QToolButton#menuButton::menu-indicator {{ image: none; }}
    QPushButton#modelChip {{
        border-radius: 12px;
        padding: 4px 12px;
        color: {p.subtext};
        font-size: 12px;
    }}

    QScrollArea {{ border: none; background: {p.bg}; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

    QFrame#userBubble {{
        background: {p.accent};
        border-radius: 16px;
    }}
    QFrame#userBubble QLabel {{ color: {p.accent_text}; }}
    QFrame#assistantBubble, QFrame#thinkingBubble {{
        background: {p.assistant_bubble};
        border: 1px solid {p.border};
        border-radius: 16px;
    }}
    QFrame#thinkingBubble QLabel {{ color: {p.subtext}; font-style: italic; }}
    QLabel#role {{ color: {p.subtext}; font-size: 11px; font-weight: 600; }}

    QFrame#codeBlock {{
        background: {p.code_bg};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QFrame#codeBlock QLabel#code {{
        font-family: Menlo, Monaco, monospace;
        font-size: 12px;
        color: {p.text};
    }}
    QFrame#codeBlock QLabel#lang {{ color: {p.subtext}; font-size: 11px; }}
    QFrame#codeBlock QToolButton {{ padding: 2px 8px; font-size: 11px; border-radius: 6px; }}
    QFrame#userBubble QFrame#codeBlock QLabel#code {{ color: {p.text}; }}

    QFrame#briefCard {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-left: 3px solid {p.accent};
        border-radius: 10px;
    }}
    QFrame#briefCard QToolButton#briefToggle {{
        border: none;
        background: transparent;
        color: {p.subtext};
        font-weight: 600;
        padding: 2px 0;
        text-align: left;
    }}

    QFrame#inputFrame {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 14px;
    }}
    QFrame#inputFrame QPlainTextEdit {{
        background: transparent;
        border: none;
        color: {p.text};
        font-size: 14px;
    }}
    QToolButton#sendButton {{
        background: {p.accent};
        color: {p.accent_text};
        border: none;
        border-radius: 15px;
        min-width: 30px; max-width: 30px;
        min-height: 30px; max-height: 30px;
        padding: 0;
        font-size: 16px;
        font-weight: 700;
    }}
    QToolButton#sendButton:disabled {{ background: {p.border}; }}

    QPlainTextEdit, QLineEdit {{
        background: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; }}
    QMenu::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
    """
