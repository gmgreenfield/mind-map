import pytest

from mindmap.models import DEFAULT_MODEL, LOCAL_PRESETS, ModelSpec
from mindmap.ui.model_picker import ModelPickerDialog


class Keys:
    def __init__(self, **saved):
        self.saved = dict(saved)
        self.listed = []

    def get(self, p):
        return self.saved.get(p)

    def source(self, p):
        return "keychain" if p in self.saved else None

    def set(self, p, k):
        self.saved[p] = k

    def delete(self, p):
        self.saved.pop(p, None)

    def list_models(self, p, key):
        self.listed.append((p, key))
        if key == "bad":
            raise RuntimeError("401 unauthorized")
        return ["model-b", "model-a"]


def make(qtbot, current=DEFAULT_MODEL, **saved):
    k = Keys(**saved)
    d = ModelPickerDialog(current, get_key=k.get, key_source=k.source, set_key=k.set,
                          delete_key=k.delete, list_models=k.list_models)
    qtbot.addWidget(d)
    return d, k


def test_preselects_current_local_model(qtbot):
    d, _ = make(qtbot)
    assert d.tabs.currentIndex() == 0
    assert d.selected() == DEFAULT_MODEL


def test_pick_other_local_preset(qtbot):
    d, _ = make(qtbot)
    d.local_radios[1][0].setChecked(True)
    d.accept()
    assert d.result_spec == ModelSpec("local", LOCAL_PRESETS[1][1])


def test_custom_hugging_face_repo(qtbot):
    d, _ = make(qtbot)
    d.custom_radio.setChecked(True)
    d.custom_repo.setText("nope")
    assert d.selected() is None and "Hugging Face" in d.error.text()
    d.custom_repo.setText("someone/Model-GGUF:Q5_K_M")
    assert d.selected() == ModelSpec("local", "someone/Model-GGUF:Q5_K_M")


def test_custom_repo_preselected(qtbot):
    d, _ = make(qtbot, ModelSpec("local", "x/y-GGUF:Q8_0"))
    assert d.custom_radio.isChecked() and d.custom_repo.text() == "x/y-GGUF:Q8_0"


def test_claude_requires_key_then_saves_it(qtbot):
    d, k = make(qtbot)
    d.tabs.setCurrentIndex(1)
    assert d.claude.model.currentText() == "claude-opus-5-5"
    d.accept()
    assert not hasattr(d, "result_spec") and "API key" in d.error.text()
    d.claude.key.setText("  sk-ant-123 ")
    d.accept()
    assert d.result_spec == ModelSpec("anthropic", "claude-opus-5-5")
    assert k.saved["anthropic"] == "sk-ant-123"


def test_saved_key_is_enough(qtbot):
    d, k = make(qtbot, ModelSpec("anthropic", "claude-sonnet-5-5"), anthropic="saved")
    assert d.tabs.currentIndex() == 1 and d.claude.model.currentText() == "claude-sonnet-5-5"
    assert "Keychain" in d.claude.key.placeholderText()
    d.accept()
    assert d.result_spec.name == "claude-sonnet-5-5"


def test_openai_load_models_and_choose(qtbot):
    d, k = make(qtbot, openai="ok")
    d.tabs.setCurrentIndex(2)
    d.openai.refresh()
    assert [d.openai.model.itemText(i) for i in range(d.openai.model.count())] == ["model-b", "model-a"]
    assert "2 models" in d.openai.status.text()
    d.openai.model.setCurrentText("model-a")
    d.accept()
    assert d.result_spec == ModelSpec("openai", "model-a")


def test_load_models_errors_are_shown(qtbot):
    d, _ = make(qtbot)
    d.tabs.setCurrentIndex(2)
    d.openai.refresh()
    assert "API key first" in d.openai.status.text()
    d.openai.key.setText("bad")
    d.openai.refresh()
    assert "401" in d.openai.status.text()


def test_remove_saved_key(qtbot):
    d, k = make(qtbot, anthropic="saved")
    assert d.claude.remove_btn.isEnabled()
    d.claude.remove_btn.click()
    assert "anthropic" not in k.saved and not d.claude.remove_btn.isEnabled()


@pytest.mark.parametrize("tab", [1, 2])
def test_empty_model_id_rejected(qtbot, tab):
    d, _ = make(qtbot, anthropic="k", openai="k")
    d.tabs.setCurrentIndex(tab)
    cloud = d.claude if tab == 1 else d.openai
    cloud.model.setCurrentText("")
    assert d.selected() is None and "model ID" in d.error.text()
