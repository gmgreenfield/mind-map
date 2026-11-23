import pytest

from mindmap.llm import LLMError
from mindmap.store import Store
from mindmap.ui.main_window import NEW_CHAT, MainWindow
from tests.fakes import FakeBriefDialog


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


@pytest.fixture
def setup(qtbot):
    store = Store()
    client = FakeClient()
    w = MainWindow(store, client)
    w.map.animation_ms = 0
    w.brief_dialog_factory = FakeBriefDialog
    FakeBriefDialog.accept = True
    FakeBriefDialog.brief_override = None
    qtbot.addWidget(w)
    w.resize(1000, 700)
    yield w, store, client
    w.close()
    store.close()


def wait_idle(qtbot, w):
    qtbot.waitUntil(w.idle, timeout=3000)


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
    assert "Hi there" in w.chat.transcript_text()


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


def test_empty_brief_does_not_create_branch(setup):
    w, store, _ = setup
    w.open_session(store.sessions()[0].id)
    FakeBriefDialog.brief_override = "   "
    try:
        assert w.start_branch("topic") is None
    finally:
        FakeBriefDialog.brief_override = None
    assert len(store.sessions()) == 1
    assert "empty" in w.chat.status.text()


# --- rename & delete -----------------------------------------------------------
def test_rename_via_prompt_updates_store_map_and_breadcrumb(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    w.ask_text = lambda title, label, text: ("  Better   name ", True)
    assert w.rename_session(root.id)
    assert store.get_session(root.id).title == "Better name"
    assert w.map.nodes[root.id].title == "Better name"
    assert "Better name" in w.chat.crumbs.text()


def test_rename_cancel_or_blank_does_nothing(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.ask_text = lambda *a: ("x", False)
    assert not w.rename_session(root.id)
    assert not w.rename_session(root.id, "   ")
    assert store.get_session(root.id).title == NEW_CHAT


def test_delete_removes_subtree_after_confirm(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    a = w.create_branch(root.id, "a", "b")
    a1 = w.create_branch(a.id, "a1", "b")
    keep = w.create_branch(root.id, "keep", "b")
    asked = []
    w.confirm = lambda title, text: asked.append(text) or True
    assert w.delete_session(a.id)
    assert "the 1 branch below it" in asked[0]
    ids = {s.id for s in store.sessions()}
    assert ids == {root.id, keep.id}
    assert set(w.map.nodes) == ids and len(w.map.edges) == 1
    assert a1.id not in w.map.nodes


def test_delete_cancelled_keeps_everything(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.create_branch(root.id, "a", "b")
    w.confirm = lambda *a: False
    assert not w.delete_session(root.id)
    assert len(store.sessions()) == 2


def test_deleting_open_session_moves_to_parent_chat(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    child = w.create_branch(root.id, "child", "b")
    assert w.current_id == child.id and w.in_chat()
    w.confirm = lambda *a: True
    w.chat.deleteRequested.emit()
    assert w.current_id == root.id and w.in_chat()
    assert w.map.nodes[root.id].current


def test_deleting_last_root_returns_to_empty_map(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    w.confirm = lambda *a: True
    assert w.delete_session(root.id)
    assert store.sessions() == [] and w.current_id is None and not w.in_chat()
    new = w.create_root(0, 0)
    assert w.current_id == new.id


def test_delete_while_reply_streaming_is_safe(qtbot):
    import time

    class SlowClient:
        def stream_chat(self, messages, temperature=0.7):
            for word in ["one ", "two ", "three"]:
                time.sleep(0.05)
                yield word

    store = Store()
    w = MainWindow(store, SlowClient())
    w.map.animation_ms = 0
    qtbot.addWidget(w)
    root = store.sessions()[0]
    w.open_session(root.id)
    w.handle_input("hello")
    w.confirm = lambda *a: True
    assert w.delete_session(root.id)
    qtbot.waitUntil(w.idle, timeout=3000)
    assert store.sessions() == []
    w.close()
    store.close()


def test_rename_from_chat_menu(setup):
    w, store, _ = setup
    root = store.sessions()[0]
    w.open_session(root.id)
    w.ask_text = lambda *a: ("From menu", True)
    w.chat.rename_action.trigger()
    assert store.get_session(root.id).title == "From menu"


# --- model status ----------------------------------------------------------------
class FakeServer:
    def __init__(self, state="down", ours=True, exited=None, missing=False):
        self.state, self._ours, self._exited, self.missing = state, ours, exited, missing

    def health(self):
        return self.state

    def ours(self):
        return self._ours

    def exited(self):
        return self._exited


@pytest.mark.parametrize(
    "server,kind,text",
    [
        (FakeServer("ready"), "ready", "Qwen ready"),
        (FakeServer("loading"), "busy", "Loading Qwen…"),
        (FakeServer("down"), "busy", "Starting Qwen…"),
        (FakeServer("down", exited=1), "error", "Qwen stopped"),
        (FakeServer("down", ours=False), "error", "Qwen offline"),
        (FakeServer("down", ours=False, missing=True), "error", "llama-server not found"),
    ],
)
def test_model_status(qtbot, server, kind, text):
    store = Store()
    w = MainWindow(store, FakeClient(), server)
    qtbot.addWidget(w)
    assert w.model_status[0] == kind and w.model_status[1].startswith(text)
    assert text in w.map.model_status.text() and text in w.chat.model_status.text()
    w.close()
    store.close()


def test_status_poll_switches_to_ready(qtbot):
    store = Store()
    server = FakeServer("loading")
    w = MainWindow(store, FakeClient(), server)
    qtbot.addWidget(w)
    server.state = "ready"
    qtbot.waitUntil(lambda: w.model_status[1] == "Qwen ready", timeout=3000)
    w.close()
    store.close()


def test_no_server_means_no_status(setup):
    w, _, _ = setup
    assert w.map.model_status.isHidden()
