"""Choose the model for a chat: a local model, Claude, or ChatGPT."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import keys
from ..models import CLAUDE_PRESETS, LOCAL_PRESETS, PROVIDERS, ModelSpec
from ..providers import list_cloud_models

TAB_ORDER = ["local", "anthropic", "openai"]


class CloudTab(QWidget):
    def __init__(self, provider: str, presets: list[str], dialog: "ModelPickerDialog"):
        super().__init__()
        self.provider = provider
        self.dialog = dialog
        company = "Anthropic" if provider == "anthropic" else "OpenAI"

        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(presets)
        self.model.lineEdit().setPlaceholderText("Model ID")
        self.refresh_btn = QPushButton("Load my models")
        self.refresh_btn.setToolTip(f"Ask {company} which models your key can use")
        self.refresh_btn.clicked.connect(self.refresh)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model, 1)
        model_row.addWidget(self.refresh_btn)

        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.remove_btn = QPushButton("Remove saved key")
        self.remove_btn.clicked.connect(self.remove_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        key_row.addWidget(self.remove_btn)

        self.status = QLabel()
        self.status.setObjectName("subtle")
        self.status.setWordWrap(True)
        note = QLabel(
            f"Messages in chats using this model are sent to {company}. "
            "Your key is stored in the macOS Keychain."
        )
        note.setObjectName("subtle")
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Model"))
        layout.addLayout(model_row)
        layout.addSpacing(6)
        layout.addWidget(QLabel("API key"))
        layout.addLayout(key_row)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addWidget(note)
        self.update_key_state()

    def update_key_state(self) -> None:
        source = self.dialog.key_source(self.provider)
        env = keys.ENV_VARS[self.provider]
        self.key.setPlaceholderText(
            {"keychain": "Saved in Keychain (paste a new one to replace it)",
             "env": f"Using {env} from the environment"}.get(source, "Paste your API key")
        )
        self.remove_btn.setEnabled(source == "keychain")

    def remove_key(self) -> None:
        self.dialog.delete_key(self.provider)
        self.update_key_state()
        self.status.setText("Key removed.")

    def current_key(self) -> str | None:
        return self.key.text().strip() or self.dialog.get_key(self.provider)

    def refresh(self) -> None:
        key = self.current_key()
        if not key:
            self.status.setText("Add an API key first.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ids = self.dialog.list_models(self.provider, key)
        except Exception as e:  # network or auth problems: show, don't crash
            self.status.setText(f"Couldn't load models: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        current = self.model.currentText()
        self.model.clear()
        self.model.addItems(ids)
        if current in ids:
            self.model.setCurrentText(current)
        self.status.setText(f"{len(ids)} models available.")


class ModelPickerDialog(QDialog):
    def __init__(
        self,
        current: ModelSpec,
        parent=None,
        get_key=keys.get_key,
        key_source=keys.key_source,
        set_key=keys.set_key,
        delete_key=keys.delete_key,
        list_models=list_cloud_models,
    ):
        super().__init__(parent)
        self.setWindowTitle("Choose a model")
        self.resize(520, 400)
        self.get_key, self.key_source = get_key, key_source
        self.set_key, self.delete_key = set_key, delete_key
        self.list_models = list_models

        self.tabs = QTabWidget()

        # Local
        local = QWidget()
        self.local_group = QButtonGroup(self)
        local_layout = QVBoxLayout(local)
        self.local_radios: list[tuple[QRadioButton, str]] = []
        for label, repo, note in LOCAL_PRESETS:
            radio = QRadioButton(f"{label}   ·   {note}")
            self.local_group.addButton(radio)
            local_layout.addWidget(radio)
            self.local_radios.append((radio, repo))
        self.custom_radio = QRadioButton("Any GGUF model from Hugging Face:")
        self.local_group.addButton(self.custom_radio)
        self.custom_repo = QLineEdit()
        self.custom_repo.setPlaceholderText("owner/repo-GGUF:Q4_K_M")
        self.custom_repo.textEdited.connect(lambda _t: self.custom_radio.setChecked(True))
        local_layout.addWidget(self.custom_radio)
        local_layout.addWidget(self.custom_repo)
        local_layout.addStretch(1)
        local_note = QLabel(
            "Runs on this Mac. Nothing leaves your computer. "
            "The first chat with a new model downloads it."
        )
        local_note.setObjectName("subtle")
        local_note.setWordWrap(True)
        local_layout.addWidget(local_note)

        self.claude = CloudTab("anthropic", [m for _, m in CLAUDE_PRESETS], self)
        self.openai = CloudTab("openai", [], self)
        self.tabs.addTab(local, PROVIDERS["local"])
        self.tabs.addTab(self.claude, PROVIDERS["anthropic"])
        self.tabs.addTab(self.openai, PROVIDERS["openai"])

        self.error = QLabel()
        self.error.setObjectName("status")
        self.error.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Use this model")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self.select(current)

    def select(self, spec: ModelSpec) -> None:
        self.tabs.setCurrentIndex(TAB_ORDER.index(spec.provider))
        if spec.is_local:
            for radio, repo in self.local_radios:
                if repo == spec.name:
                    radio.setChecked(True)
                    return
            self.custom_radio.setChecked(True)
            self.custom_repo.setText(spec.name)
        else:
            self._cloud(spec.provider).model.setCurrentText(spec.name)
        if not self.local_group.checkedButton():
            self.local_radios[0][0].setChecked(True)

    def _cloud(self, provider: str) -> CloudTab:
        return self.claude if provider == "anthropic" else self.openai

    def selected(self) -> ModelSpec | None:
        """The chosen model, or None (with self.error set) if something is missing."""
        provider = TAB_ORDER[self.tabs.currentIndex()]
        if provider == "local":
            if self.custom_radio.isChecked():
                repo = self.custom_repo.text().strip()
                if "/" not in repo:
                    self.error.setText("Enter a Hugging Face repo like owner/repo-GGUF:Q4_K_M.")
                    return None
                return ModelSpec("local", repo)
            for radio, repo in self.local_radios:
                if radio.isChecked():
                    return ModelSpec("local", repo)
            return None
        tab = self._cloud(provider)
        name = tab.model.currentText().strip()
        if not name:
            self.error.setText("Choose or type a model ID.")
            return None
        if not tab.current_key():
            self.error.setText(f"{PROVIDERS[provider]} needs an API key.")
            return None
        return ModelSpec(provider, name)

    def accept(self) -> None:
        spec = self.selected()
        if spec is None:
            return
        if not spec.is_local:
            entered = self._cloud(spec.provider).key.text().strip()
            if entered:
                self.set_key(spec.provider, entered)
        self.result_spec = spec
        super().accept()


def pick_model(current: ModelSpec, parent=None) -> ModelSpec | None:
    dialog = ModelPickerDialog(current, parent)
    return dialog.result_spec if dialog.exec() == QDialog.Accepted else None
