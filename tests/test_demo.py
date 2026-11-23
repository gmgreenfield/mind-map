import math

import pytest

from mindmap.demo import COFFEE, KYOTO, count, seed
from mindmap.layout import MIN_GAP
from mindmap.store import Store


@pytest.fixture
def seeded():
    store = Store()
    ids = seed(store)
    yield store, ids
    store.close()


def test_all_nodes_created(seeded):
    store, ids = seeded
    assert len(store.sessions()) == count(COFFEE) + count(KYOTO) == len(ids)


def test_two_roots_and_depth_four(seeded):
    store, ids = seeded
    roots = [s for s in store.sessions() if s.parent_id is None]
    assert {r.title for r in roots} == {COFFEE.title, KYOTO.title}
    path = store.ancestry(ids["Ventilation and permits"])
    assert [s.title for s in path] == [
        "Opening a small coffee roastery",
        "Choosing a roaster",
        "Used vs new roasters",
        "Ventilation and permits",
    ]


def test_every_branch_has_brief_and_every_node_has_messages(seeded):
    store, _ = seeded
    for s in store.sessions():
        assert store.messages(s.id), s.title
        if s.parent_id is not None:
            assert s.brief and s.brief.startswith("## Goal"), s.title
        else:
            assert s.brief is None


def test_conversations_alternate_and_start_with_user(seeded):
    store, _ = seeded
    for s in store.sessions():
        roles = [m.role for m in store.messages(s.id)]
        assert roles[0] == "user", s.title
        assert all(a != b for a, b in zip(roles, roles[1:])), s.title


def test_no_overlapping_nodes(seeded):
    store, _ = seeded
    pts = [(s.x, s.y) for s in store.sessions()]
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            assert math.hypot(a[0] - b[0], a[1] - b[1]) >= MIN_GAP
