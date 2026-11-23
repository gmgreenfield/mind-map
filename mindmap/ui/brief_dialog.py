"""Shows the handoff brief as Qwen writes it; user edits, then confirms or cancels."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)


class BriefDialog(QDialog):
    def __init__(self, topic: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Branch into a new session")
        self.resize(560, 460)

        self.title_edit = QLineEdit(topic)
        self.status = QLabel("Qwen is writing the handoff brief…")
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = self.buttons.button(QDialogButtonBox.Ok)
        self.ok.setText("Create branch")
        self.ok.setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("New session title"))
        layout.addWidget(self.title_edit)
        layout.addWidget(self.status)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.buttons)

    def append(self, delta: str) -> None:
        self.editor.insertPlainText(delta)
        self.editor.ensureCursorVisible()

    def finish(self, _full: str = "") -> None:
        self.status.setText("Edit the brief if you like — the new session sees only this.")
        self._make_editable()

    def fail(self, error: str) -> None:
        self.status.setText(f"Couldn't generate a brief ({error}). You can write one yourself.")
        self._make_editable()

    def _make_editable(self) -> None:
        self.editor.setReadOnly(False)
        self.ok.setEnabled(bool(self.brief().strip()))
        self.editor.textChanged.connect(
            lambda: self.ok.setEnabled(bool(self.brief().strip()))
        )
        self.editor.setFocus()

    def brief(self) -> str:
        return self.editor.toPlainText().strip()

    def title(self) -> str:
        return self.title_edit.text().strip()
