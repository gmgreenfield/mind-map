import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QDialog

from mindmap.llm import LLMError
from mindmap.store import Store
from mindmap.ui.main_window import NEW_CHAT, MainWindow


class FakeClient:
    def __init__(self):
        self.calls = []
        self.replies = ["Hi", " there"]
        self.error = None

    def stream_chat(self, messages, temperature=0.7):
        self.calls.append(messages)
        yield from self.replies
        if self.error:
            raise self.error


class FakeBriefDialog:
    """Stands in for BriefDialog: waits for the brief, then accepts or rejects."""

    accept = True
    title_override = None

    def __init__(self, topic, parent=None):
        self.topic = topic
        self.text = ""
        self._done = False
        self._loop = QEventLoop()

    def append(self, d):
        self.text += d

    def finish(self, _full=""):
        self._done = True
        self._loop.quit()

    def fail(self, err):
        self.finish()

    def exec(self):
        if not self._done:
            QTimer.singleShot(2000, self._loop.quit)
            self._loop.exec()
        return QDialog.Accepted if self.accept else QDialog.Rejected

    def brief(self):
        return self.text

    def title(self):
        return self.title_override or self.topic


@pytest.fixture
def setup(qtbot):
    store = Store()
    client = FakeClient()
    w = MainWindow(store, client)
    w.map.animation_ms = 0
    w.brief_dialog_factory = FakeBriefDialog
    FakeBriefDialog.accept = True
    qtbot.addWidget(w)
    w.resize(1000, 700)
    yield w, store, client
    w.close()
    store.close()


def wait_idle(qtbot, w):
    qtbot.waitUntil(lambda: not w.workers, timeout=3000)


def test_starts_with_one_root_on_map(setup):
    w, store, _ = setup
    assert [s.title for s in store.sessions()] == [NEW_CHAT]
    assert not w.in_chat()


def test_open_session_zooms_into_chat(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    assert w.in_chat() and w.current_id == root.id
    w.back_to_map()
    assert not w.in_chat()


def test_send_streams_reply_and_titles_session(setup, qtbot):
    w, store, client = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    w.handle_input("Plan a mind map app")
    wait_idle(qtbot, w)
    msgs = store.messages(root.id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "Plan a mind map app"),
        ("assistant", "Hi there"),
    ]
    assert store.get_session(root.id).title == "Plan a mind map app"
    assert client.calls[0][0]["role"] == "system"
    assert "Hi there" in w.chat.transcript.toPlainText()


def test_failed_reply_keeps_partial_and_shows_error(setup, qtbot):
    w, store, client = setup
    client.error = LLMError("server went away")
    root = store.sessions()[0]
    w.open_session(root.id)
    w.handle_input("hello")
    wait_idle(qtbot, w)
    assert store.messages(root.id)[-1].content == "Hi there"
    assert "server went away" in w.chat.status.text()


def test_branch_creates_child_with_brief_and_pivots(setup, qtbot):
    w, store, client = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    w.handle_input("we are building a mind map")
    wait_idle(qtbot, w)

    client.replies = ["## Goal\n", "describe the project"]
    w.handle_input("/branch idea describing this project")
    child = next(s for s in store.sessions() if s.parent_id == root.id)
    assert child.title == "idea describing this project"
    assert child.brief == "## Goal\ndescribe the project"
    assert (child.x, child.y) != (root.x, root.y)
    assert w.current_id == child.id and w.in_chat()
    assert child.id in w.map.nodes and len(w.map.edges) == 1

    # The brief request saw the parent's history plus the instruction.
    brief_call = client.calls[-1]
    assert any("mind map" in m["content"] for m in brief_call)
    assert "idea describing this project" in brief_call[-1]["content"]

    # The child's first turn sees only the brief, not the parent's messages.
    client.replies = ["ok"]
    w.handle_input("go")
    wait_idle(qtbot, w)
    child_call = client.calls[-1]
    assert "describe the project" in child_call[0]["content"]
    assert not any(m["content"] == "we are building a mind map" for m in child_call)


def test_cancelled_branch_creates_nothing(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    FakeBriefDialog.accept = False
    assert w.start_branch("nope") is None
    assert len(store.sessions()) == 1


def test_parent_command_and_breadcrumb_pivot(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    child = w.create_branch(root.id, "child", "brief")
    assert w.current_id == child.id
    w.handle_input("/parent")
    assert w.current_id == root.id and w.in_chat()
    w.handle_input("/parent")
    assert "root" in w.chat.status.text()


def test_cmd_arrow_navigation_follows_connections(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    east = w.create_branch(root.id, "east", "b")
    assert store.get_session(east.id).x > root.x
    w.navigate("W")
    assert w.current_id == root.id
    w.navigate("E")
    assert w.current_id == east.id
    w.navigate("N")
    assert w.current_id == east.id
    assert "north" in w.chat.status.text()


def test_unknown_command_flashes(setup):
    w, store, _ = setup
    w.open_session(store.sessions()[0].id)
    w.handle_input("/nope")
    assert "Unknown command" in w.chat.status.text()
    assert store.messages(store.sessions()[0].id) == []


def test_drag_persists_positions(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    child = w.create_branch(root.id, "c", "b")
    before = store.get_session(child.id)
    w.map.drag_nodes(root.id, 50, 25)
    w.map.finish_drag(root.id)
    after = store.get_session(child.id)
    assert (after.x, after.y) == (before.x + 50, before.y + 25)
    assert (store.get_session(root.id).x, store.get_session(root.id).y) == (50, 25)


def test_double_click_creates_new_root(setup):
    w, store, _ = setup
    s = w.create_root(500, 500)
    assert s.parent_id is None and (s.x, s.y) == (500, 500)
    assert w.current_id == s.id and w.in_chat()
