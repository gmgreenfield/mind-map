from mindmap.ui.brief_dialog import BriefDialog


def test_brief_dialog_flow(qtbot):
    d = BriefDialog("idea x")
    qtbot.addWidget(d)
    assert not d.ok.isEnabled() and d.editor.isReadOnly()
    d.append("## Goal\n")
    d.append("explore x")
    d.finish("## Goal\nexplore x")
    assert d.ok.isEnabled() and not d.editor.isReadOnly()
    assert d.brief() == "## Goal\nexplore x"
    assert d.title() == "idea x"
    d.editor.setPlainText("   ")
    assert not d.ok.isEnabled()


def test_brief_dialog_failure_allows_manual_brief(qtbot):
    d = BriefDialog("t")
    qtbot.addWidget(d)
    d.fail("server down")
    assert "server down" in d.status.text()
    assert not d.editor.isReadOnly()
    d.editor.setPlainText("my own brief")
    assert d.ok.isEnabled()
