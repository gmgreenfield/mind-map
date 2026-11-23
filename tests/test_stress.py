"""End-to-end stress tests: the real MainWindow driven with the mock Qwen."""

import html
import math
import random

import pytest

from mindmap.demo import COFFEE, KYOTO, count, seed
from mindmap.layout import MIN_GAP
from mindmap.mock_llm import MockLLMClient
from mindmap.store import Store
from mindmap.ui.main_window import MainWindow
from tests.fakes import FakeBriefDialog


def make_window(qtbot, store, client):
    w = MainWindow(store, client)
    w.map.animation_ms = 0
    w.brief_dialog_factory = FakeBriefDialog
    FakeBriefDialog.accept = True
    w.confirm = lambda *a: True
    w.ask_text = lambda title, label, text: (text + " (renamed)", True)
    w.resize(1100, 750)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def app(qtbot):
    store = Store()
    seed(store)
    client = MockLLMClient(delay=0)
    w = make_window(qtbot, store, client)
    yield w, store, client
    w.close()
    store.close()


def wait_idle(qtbot, w):
    qtbot.waitUntil(w.idle, timeout=5000)


def by_title(store, title):
    return next(s for s in store.sessions() if s.title == title)


def check_invariants(w, store):
    sessions = store.sessions()
    ids = {s.id for s in sessions}
    # Map mirrors the store.
    assert set(w.map.nodes) == ids
    assert len(w.map.edges) == sum(1 for s in sessions if s.parent_id is not None)
    for s in sessions:
        node = w.map.nodes[s.id]
        assert (node.x(), node.y()) == pytest.approx((s.x, s.y))
    # Exactly one highlighted node, and it is the current one.
    current = [sid for sid, n in w.map.nodes.items() if n.current]
    if w.current_id is not None:
        assert w.current_id in ids
        assert current == [w.current_id]
    # Conversations stay well-formed.
    for s in sessions:
        msgs = store.messages(s.id)
        assert all(m.content.strip() for m in msgs)
        roles = [m.role for m in msgs]
        assert all(a != b for a, b in zip(roles, roles[1:])), (s.title, roles)
    # The chat view shows the right session.
    if w.in_chat():
        crumbs = w.chat.crumbs.text()
        assert html.escape(store.get_session(w.current_id).title) in crumbs


def test_demo_map_renders(app):
    w, store, _ = app
    check_invariants(w, store)
    assert len(w.map.nodes) == count(COFFEE) + count(KYOTO) == 13


def test_deep_branch_chain_carries_context(app, qtbot):
    w, store, client = app
    w.open_session(by_title(store, "Ventilation and permits").id)
    depth_before = len(store.ancestry(w.current_id))
    for i in range(1, 7):
        w.handle_input(f"level {i}: what are the next steps?")
        wait_idle(qtbot, w)
        parent_id = w.current_id
        w.handle_input(f"/branch level {i} detail")
        child = store.get_session(w.current_id)
        assert child.parent_id == parent_id
        assert child.brief.startswith(f"## Goal\nExplore level {i} detail")
        # The brief summarises the parent's latest messages…
        assert f"level {i}: what are the next steps?" in child.brief
        # …and names the parent's own goal, so context chains down the tree.
        assert "Parent session's goal:" in child.brief
        check_invariants(w, store)

    path = store.ancestry(w.current_id)
    assert len(path) == depth_before + 6
    assert w.chat.crumbs.text().count("href=") == len(path) - 1

    # Jump straight back to the root via the breadcrumb.
    w.pivot_to(path[0].id)
    assert w.current_id == path[0].id and w.in_chat()
    check_invariants(w, store)


def test_child_context_excludes_parent_history(app, qtbot):
    w, store, client = app
    root = by_title(store, "Kyoto trip in April")
    w.open_session(root.id)
    w.handle_input("/branch rainy day plans")
    w.handle_input("anything indoors?")
    wait_idle(qtbot, w)
    sent = client.calls[-1]
    parent_texts = {m.content for m in store.messages(root.id)}
    assert not any(m["content"] in parent_texts for m in sent)
    assert "rainy day plans" in sent[0]["content"]


def test_wide_fan_out_never_overlaps(app, qtbot):
    w, store, _ = app
    hub = by_title(store, "Wholesale pricing")
    for i in range(12):
        w.open_session(hub.id)
        w.handle_input(f"/branch pricing angle {i}")
    assert len(store.children(hub.id)) == 12
    pts = [(s.x, s.y) for s in store.sessions()]
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            assert math.hypot(a[0] - b[0], a[1] - b[1]) >= MIN_GAP - 1e-6
    check_invariants(w, store)


def test_navigation_round_trip_over_whole_tree(app):
    w, store, _ = app
    for s in store.sessions():
        w.open_session(s.id)
        for child in store.children(s.id):
            # Every child is reachable from its parent by some ⌘+arrow…
            reached = False
            for d in "NESW":
                w.pivot_to(s.id)
                w.navigate(d)
                if w.current_id == child.id:
                    reached = True
                    break
            # …(unless a closer sibling shadows it in every direction).
            if not reached:
                assert len(store.children(s.id)) > 4
            w.pivot_to(child.id)
            w.handle_input("/parent")
            assert w.current_id == s.id
    check_invariants(w, store)


def test_concurrent_replies_land_in_their_own_sessions(qtbot):
    store = Store()
    seed(store)
    client = MockLLMClient(delay=0.005)
    w = make_window(qtbot, store, client)
    a = by_title(store, "Nara itinerary")
    b = by_title(store, "Food to try")
    w.open_session(a.id)
    w.handle_input("what about pricing for the deer crackers?")
    w.pivot_to(b.id)
    w.handle_input("hello")
    assert set(w.workers) == {a.id, b.id}
    assert w.map.nodes[a.id].busy and w.map.nodes[b.id].busy
    # Sending again while busy is refused, not queued.
    w.handle_input("hello again")
    assert "still replying" in w.chat.status.text()
    wait_idle(qtbot, w)
    assert "cost" in store.messages(a.id)[-1].content
    assert "mock" in store.messages(b.id)[-1].content
    assert not w.map.nodes[a.id].busy
    check_invariants(w, store)
    w.close()
    store.close()


def test_drag_and_reload_from_disk(qtbot, tmp_path):
    path = tmp_path / "map.db"
    store = Store(path)
    seed(store)
    w = make_window(qtbot, store, MockLLMClient(delay=0))
    roaster = by_title(store, "Choosing a roaster")
    subtree = w.map.subtree(roaster.id)
    before = {sid: (store.get_session(sid).x, store.get_session(sid).y) for sid in subtree}
    w.map.drag_nodes(roaster.id, -300, 120)
    w.map.finish_drag(roaster.id)
    single = by_title(store, "Food to try")
    w.map.drag_nodes(single.id, 40, 40, subtree=False)
    w.map.finish_drag(single.id, subtree=False)
    w.close()
    store.close()

    store2 = Store(path)
    w2 = make_window(qtbot, store2, MockLLMClient(delay=0))
    for sid, (x, y) in before.items():
        s = store2.get_session(sid)
        assert (s.x, s.y) == (x - 300, y + 120)
    check_invariants(w2, store2)
    w2.close()
    store2.close()


@pytest.mark.parametrize("seed_value", [1, 2, 3])
def test_random_walk(qtbot, seed_value):
    """Hammer the app with a random sequence of user actions, checking invariants."""
    rng = random.Random(seed_value)
    store = Store()
    seed(store)
    client = MockLLMClient(delay=0)
    w = make_window(qtbot, store, client)
    prompts = ["hello", "what's the plan?", "what about pricing?", "any risks?",
               "tell me more", "how would the code work?", "naming ideas?"]

    def ensure_chat():
        if not store.sessions():
            w.create_root(0, 0)
        if not w.in_chat():
            w.open_session(w.current_id or rng.choice(store.sessions()).id)

    def any_session():
        if not store.sessions():
            w.create_root(0, 0)
        return rng.choice(store.sessions())

    actions = {
        "open": lambda: w.open_session(any_session().id),
        "send": lambda: (ensure_chat(), w.handle_input(rng.choice(prompts)), wait_idle(qtbot, w)),
        "branch": lambda: (ensure_chat(), w.handle_input(f"/branch topic {rng.randint(0, 999)}")),
        "parent": lambda: (ensure_chat(), w.handle_input("/parent")),
        "navigate": lambda: (ensure_chat(), w.navigate(rng.choice("NESW"))),
        "crumb": lambda: (ensure_chat(), w.pivot_to(rng.choice(store.ancestry(w.current_id)).id)),
        "map": lambda: (ensure_chat(), w.handle_input("/map")),
        "drag": lambda: _drag(w, store, rng),
        "new_root": lambda: w.create_root(rng.uniform(-3000, 3000), rng.uniform(-3000, 3000)),
        "bad_command": lambda: (ensure_chat(), w.handle_input("/nonsense")),
        "rename": lambda: w.rename_session(any_session().id),
        "delete_leaf": lambda: _delete_leaf(w, store, rng),
        "delete_any": lambda: w.delete_session(any_session().id),
    }
    weights = {"open": 3, "send": 5, "branch": 4, "parent": 2, "navigate": 4,
               "crumb": 2, "map": 2, "drag": 3, "new_root": 1, "bad_command": 1,
               "rename": 2, "delete_leaf": 2, "delete_any": 1}
    names = list(weights)
    for _ in range(150):
        name = rng.choices(names, weights=[weights[n] for n in names])[0]
        actions[name]()
        check_invariants(w, store)
    wait_idle(qtbot, w)
    check_invariants(w, store)
    w.close()
    store.close()


def _delete_leaf(w, store, rng):
    leaves = [s for s in store.sessions() if not store.children(s.id)]
    if leaves:
        w.delete_session(rng.choice(leaves).id)


def _drag(w, store, rng):
    if not store.sessions():
        return
    s = rng.choice(store.sessions())
    subtree = rng.random() < 0.7
    w.map.drag_nodes(s.id, rng.uniform(-200, 200), rng.uniform(-200, 200), subtree)
    w.map.finish_drag(s.id, subtree)
