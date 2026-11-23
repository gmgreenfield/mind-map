from PySide6.QtCore import Qt

from mindmap.store import Message, Session
from mindmap.ui.chat_view import ChatView, render_markdown


def sess(i, title, parent=None, brief=None):
    return Session(i, parent, title, brief, 0, 0)


def test_render_includes_brief_messages_and_partial():
    md = render_markdown(
        "## Goal\nX",
        [Message(1, 1, "user", "hi"), Message(2, 1, "assistant", "hello")],
        "typing",
    )
    assert "> **Handoff brief from parent**" in md
    assert "> ## Goal" in md
    assert "**You**\n\nhi" in md
    assert md.endswith("**Qwen**\n\ntyping")


def test_render_empty_session_hint():
    assert "/branch" in render_markdown(None, [], None)


def test_breadcrumb_and_link_navigation(qtbot):
    v = ChatView()
    qtbot.addWidget(v)
    v.show_session([sess(1, "root"), sess(2, "child <x>", 1, "b")], [])
    assert 'href="1"' in v.crumbs.text()
    assert "child &lt;x&gt;" in v.crumbs.text()
    with qtbot.waitSignal(v.sessionRequested) as blocker:
        v.crumbs.linkActivated.emit("1")
    assert blocker.args == [1]


def test_enter_sends_shift_enter_does_not(qtbot):
    v = ChatView()
    qtbot.addWidget(v)
    sent = []
    v.sendRequested.connect(sent.append)
    qtbot.keyClicks(v.input, "hello")
    qtbot.keyClick(v.input, Qt.Key_Return, Qt.ShiftModifier)
    assert sent == []
    qtbot.keyClick(v.input, Qt.Key_Return)
    assert sent == ["hello\n"]


def test_cmd_arrow_navigates_only_when_input_empty(qtbot):
    v = ChatView()
    qtbot.addWidget(v)
    dirs = []
    v.navigateRequested.connect(dirs.append)
    qtbot.keyClick(v.input, Qt.Key_Left, Qt.ControlModifier)
    qtbot.keyClick(v.input, Qt.Key_Up, Qt.ControlModifier)
    assert dirs == ["W", "N"]
    qtbot.keyClicks(v.input, "draft")
    qtbot.keyClick(v.input, Qt.Key_Left, Qt.ControlModifier)
    assert dirs == ["W", "N"]
