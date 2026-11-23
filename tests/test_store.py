import sqlite3

import pytest

from mindmap.store import Store


@pytest.fixture
def store():
    s = Store()
    yield s
    s.close()


def test_create_and_get_session(store):
    s = store.create_session("Root", x=10, y=20)
    got = store.get_session(s.id)
    assert got.title == "Root"
    assert got.parent_id is None
    assert (got.x, got.y) == (10, 20)


def test_missing_session_raises(store):
    with pytest.raises(KeyError):
        store.get_session(999)


def test_children_and_ancestry(store):
    root = store.create_session("root")
    a = store.create_session("a", parent_id=root.id, brief="brief a")
    b = store.create_session("b", parent_id=a.id)
    assert [c.id for c in store.children(root.id)] == [a.id]
    assert [s.title for s in store.ancestry(b.id)] == ["root", "a", "b"]
    assert store.get_session(a.id).brief == "brief a"


def test_subtree_ids(store):
    root = store.create_session("root")
    a = store.create_session("a", parent_id=root.id)
    b = store.create_session("b", parent_id=a.id)
    other = store.create_session("other")
    assert sorted(store.subtree_ids(a.id)) == sorted([a.id, b.id])
    assert other.id not in store.subtree_ids(root.id)


def test_move_subtree_moves_descendants_only(store):
    root = store.create_session("root", x=0, y=0)
    a = store.create_session("a", parent_id=root.id, x=100, y=0)
    b = store.create_session("b", parent_id=a.id, x=200, y=50)
    moved = store.move_subtree(a.id, 10, -5)
    assert sorted(moved) == sorted([a.id, b.id])
    assert (store.get_session(a.id).x, store.get_session(a.id).y) == (110, -5)
    assert (store.get_session(b.id).x, store.get_session(b.id).y) == (210, 45)
    assert (store.get_session(root.id).x, store.get_session(root.id).y) == (0, 0)


def test_set_position_and_rename(store):
    s = store.create_session("x")
    store.set_position(s.id, 5, 6)
    store.rename(s.id, "y")
    got = store.get_session(s.id)
    assert (got.x, got.y, got.title) == (5, 6, "y")


def test_messages_in_order(store):
    s = store.create_session("s")
    store.add_message(s.id, "user", "hi")
    store.add_message(s.id, "assistant", "hello")
    assert [(m.role, m.content) for m in store.messages(s.id)] == [
        ("user", "hi"),
        ("assistant", "hello"),
    ]


def test_invalid_role_rejected(store):
    s = store.create_session("s")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_message(s.id, "system", "nope")


def test_delete_cascades(store):
    root = store.create_session("root")
    child = store.create_session("c", parent_id=root.id)
    store.add_message(child.id, "user", "hi")
    store.delete_session(root.id)
    assert store.sessions() == []
    assert store.messages(child.id) == []


def test_persists_to_file(tmp_path):
    path = tmp_path / "sub" / "m.db"
    s1 = Store(path)
    sid = s1.create_session("keep").id
    s1.close()
    s2 = Store(path)
    assert s2.get_session(sid).title == "keep"
    s2.close()


def test_model_column_set_and_default(store):
    s = store.create_session("s")
    assert s.model is None
    store.set_model(s.id, "anthropic:claude-opus-5-5")
    assert store.get_session(s.id).model == "anthropic:claude-opus-5-5"
    c = store.create_session("c", parent_id=s.id, model="openai:x")
    assert store.children(s.id)[0].model == "openai:x" == c.model


def test_migrates_old_database_without_model_column(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER,"
        " title TEXT NOT NULL, brief TEXT, x REAL NOT NULL DEFAULT 0, y REAL NOT NULL DEFAULT 0,"
        " created_at REAL NOT NULL);"
        "INSERT INTO sessions (title, created_at) VALUES ('legacy', 0);"
    )
    old.commit()
    old.close()
    s = Store(path)
    (legacy,) = s.sessions()
    assert legacy.title == "legacy" and legacy.model is None
    s.set_model(legacy.id, "local:x:y")
    assert s.get_session(legacy.id).model == "local:x:y"
    s.close()
