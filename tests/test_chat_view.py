from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from mindmap.store import Message, Session
from mindmap.ui.chat_view import Bubble, ChatView, ThinkingBubble, split_segments


def sess(i, title, parent=None, brief=None):
    return Session(i, parent, title, brief, 0, 0)


def msgs(*pairs):
    return [Message(i, 1, r, c) for i, (r, c) in enumerate(pairs, 1)]


def make(qtbot):
    v = ChatView()
    v.resize(900, 700)
    qtbot.addWidget(v)
    return v


# --- segment splitting -------------------------------------------------------
def test_split_text_and_code():
    segs = split_segments("Intro\n\n```python\nx = 1\n```\nOutro")
    assert segs == [("text", "Intro\n\n", ""), ("code", "x = 1", "python"), ("text", "\nOutro", "")]


def test_split_unclosed_fence_while_streaming():
    assert split_segments("Here:\n```js\nlet a") == [("text", "Here:\n", ""), ("code", "let a", "js")]


def test_split_plain_text():
    assert split_segments("just text") == [("text", "just text", "")]


# --- bubbles -------------------------------------------------------------------
def test_bubbles_alignment_and_count(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root")], msgs(("user", "hi"), ("assistant", "hello")))
    kinds = [b.objectName() for b in v.bubbles()]
    assert kinds == ["userBubble", "assistantBubble"]
    assert not v.empty_hint.isVisibleTo(v)
    assert "hi" in v.transcript_text() and "hello" in v.transcript_text()


def test_empty_session_shows_hint(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root")], [])
    assert v.empty_hint.isVisibleTo(v)


def test_streaming_updates_one_bubble_in_place(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root")], msgs(("user", "hi")), partial="")
    assert isinstance(v.bubbles()[-1], ThinkingBubble)
    v.set_partial("Hel")
    bubble = v.bubbles()[-1]
    assert isinstance(bubble, Bubble)
    v.set_partial("Hello there")
    assert v.bubbles()[-1] is bubble and bubble.text == "Hello there"
    assert len(v.bubbles()) == 2
    v.set_partial(None)
    assert len(v.bubbles()) == 1


def test_code_block_rendering_and_copy(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root")], msgs(("assistant", "Try:\n```python\nprint('hi')\n```")))
    bubble = v.bubbles()[0]
    (block,) = bubble.code_blocks()
    assert block.code.text() == "print('hi')"
    assert block.lang.text() == "python"
    block.copy_btn.click()
    assert QGuiApplication.clipboard().text() == "print('hi')"
    assert block.copy_btn.text() == "Copied"


def test_code_block_appears_mid_stream(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root")], [], partial="")
    v.set_partial("Run this")
    v.set_partial("Run this\n```sh\nls")
    assert len(v.bubbles()[-1].code_blocks()) == 1


# --- brief card ----------------------------------------------------------------
def test_brief_card_expanded_for_new_branch_collapsed_later(qtbot):
    v = make(qtbot)
    ancestry = [sess(1, "root"), sess(2, "child", 1, "## Goal\nDo X")]
    v.show_session(ancestry, [])
    assert v.brief_card.isVisibleTo(v) and v.brief_card.expanded()
    v.show_session(ancestry, msgs(("user", "hi")))
    assert v.brief_card.isVisibleTo(v) and not v.brief_card.expanded()
    v.brief_card.toggle.click()
    assert v.brief_card.expanded()


def test_root_has_no_brief_card(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root")], [])
    assert not v.brief_card.isVisibleTo(v)


# --- breadcrumb, input, menu -----------------------------------------------------
def test_breadcrumb_and_link_navigation(qtbot):
    v = make(qtbot)
    v.show_session([sess(1, "root"), sess(2, "child <x>", 1, "b")], [])
    assert 'href="1"' in v.crumbs.text()
    assert "child &lt;x&gt;" in v.crumbs.text()
    with qtbot.waitSignal(v.sessionRequested) as blocker:
        v.crumbs.linkActivated.emit("1")
    assert blocker.args == [1]


def test_enter_sends_shift_enter_does_not(qtbot):
    v = make(qtbot)
    sent = []
    v.sendRequested.connect(sent.append)
    qtbot.keyClicks(v.input, "hello")
    qtbot.keyClick(v.input, Qt.Key_Return, Qt.ShiftModifier)
    assert sent == []
    qtbot.keyClick(v.input, Qt.Key_Return)
    assert sent == ["hello\n"]


def test_send_button(qtbot):
    v = make(qtbot)
    sent = []
    v.sendRequested.connect(sent.append)
    assert not v.send_btn.isEnabled()
    qtbot.keyClicks(v.input, "hey")
    assert v.send_btn.isEnabled()
    v.send_btn.click()
    assert sent == ["hey"]


def test_input_grows_with_content(qtbot):
    v = make(qtbot)
    v.show()
    one_line = v.input.height()
    v.input.setPlainText("a\nb\nc\nd")
    assert v.input.height() > one_line
    v.input.setPlainText("\n".join("x" * 20))
    assert v.input.height() <= v.input.MAX_LINES * v.input.fontMetrics().lineSpacing() + 20


def test_cmd_arrow_navigates_only_when_input_empty(qtbot):
    v = make(qtbot)
    dirs = []
    v.navigateRequested.connect(dirs.append)
    qtbot.keyClick(v.input, Qt.Key_Left, Qt.ControlModifier)
    qtbot.keyClick(v.input, Qt.Key_Up, Qt.ControlModifier)
    assert dirs == ["W", "N"]
    qtbot.keyClicks(v.input, "draft")
    qtbot.keyClick(v.input, Qt.Key_Left, Qt.ControlModifier)
    assert dirs == ["W", "N"]


def test_menu_actions_emit(qtbot):
    v = make(qtbot)
    with qtbot.waitSignal(v.renameRequested):
        v.rename_action.trigger()
    with qtbot.waitSignal(v.deleteRequested):
        v.delete_action.trigger()


def test_inline_code_uses_a_real_monospace_font():
    from mindmap.ui.chat_view import md_to_html

    html = md_to_html("Call `log()` now")
    assert "Menlo" in html and "'monospace'" not in html


def test_model_chip(qtbot):
    v = make(qtbot)
    v.set_model_label("Claude Opus 5.5", cloud=True)
    assert "Claude Opus 5.5" in v.model_btn.text() and v.assistant_name == "Claude Opus 5.5"
    with qtbot.waitSignal(v.modelRequested):
        v.model_btn.click()


def test_replies_are_labelled_with_the_model_name(qtbot):
    v = make(qtbot)
    v.set_model_label("Claude Opus 5.5", cloud=True)
    v.show_session([sess(1, "root")], msgs(("user", "hi"), ("assistant", "yo")), partial="")
    names = [r.findChild(type(v.crumbs), "role").text() for r in v.rows]
    assert names == ["You", "Claude Opus 5.5", "Claude Opus 5.5"]
    assert "Claude Opus 5.5 is thinking" in v.bubbles()[-1].label.text()
