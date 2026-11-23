import pytest
from PySide6.QtCore import QPointF, Qt

from mindmap.store import Store
from mindmap.ui.map_view import MapView


@pytest.fixture
def tree():
    s = Store()
    root = s.create_session("root", x=0, y=0)
    a = s.create_session("a", parent_id=root.id, brief="b", x=260, y=0)
    b = s.create_session("b", parent_id=a.id, brief="b", x=520, y=0)
    c = s.create_session("c", parent_id=root.id, brief="b", x=0, y=260)
    yield s, root, a, b, c
    s.close()


@pytest.fixture
def view(qtbot, tree):
    v = MapView()
    v.animation_ms = 0
    v.resize(800, 600)
    qtbot.addWidget(v)
    v.load(tree[0].sessions())
    return v


def test_load_creates_nodes_and_edges(view):
    assert len(view.nodes) == 4
    assert len(view.edges) == 3


def test_subtree(view, tree):
    _, root, a, b, c = tree
    assert sorted(view.subtree(a.id)) == sorted([a.id, b.id])
    assert sorted(view.subtree(root.id)) == sorted([root.id, a.id, b.id, c.id])


def test_drag_moves_subtree_and_reports_positions(view, tree, qtbot):
    _, root, a, b, c = tree
    view.drag_nodes(a.id, 10, 20, subtree=True)
    assert view.nodes[a.id].pos() == QPointF(270, 20)
    assert view.nodes[b.id].pos() == QPointF(530, 20)
    assert view.nodes[root.id].pos() == QPointF(0, 0)
    with qtbot.waitSignal(view.nodesMoved) as blocker:
        view.finish_drag(a.id, subtree=True)
    assert sorted(blocker.args[0]) == sorted([(a.id, 270, 20), (b.id, 530, 20)])


def test_alt_drag_moves_single_node(view, tree):
    _, root, a, b, c = tree
    view.drag_nodes(a.id, 5, 5, subtree=False)
    assert view.nodes[a.id].pos() == QPointF(265, 5)
    assert view.nodes[b.id].pos() == QPointF(520, 0)


def test_edges_follow_nodes(view, tree):
    _, root, a, b, c = tree
    edge = next(e for e in view.edges if e.b.session_id == b.id)
    view.drag_nodes(b.id, 0, 100)
    assert edge.path().currentPosition() == QPointF(520, 100)


def test_add_node_and_current(view, tree):
    store, root, *_ = tree
    new = store.create_session("new", parent_id=root.id, brief="x", x=-260, y=0)
    view.add_node(new)
    assert new.id in view.nodes and len(view.edges) == 4
    view.set_current(new.id)
    assert view.nodes[new.id].current
    assert not view.nodes[root.id].current


def test_click_on_node_activates(view, tree, qtbot):
    _, root, *_ = tree
    view.center_on_node(root.id)
    pt = view.mapFromScene(view.nodes[root.id].pos())
    with qtbot.waitSignal(view.nodeActivated) as blocker:
        qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=pt)
    assert blocker.args == [root.id]


def test_zoom_into_and_pivot_reach_target(view, tree):
    _, root, a, b, c = tree
    done = []
    view.zoom_into(a.id, on_done=lambda: done.append("in"))
    center, scale = view.camera()
    assert done == ["in"]
    assert scale == pytest.approx(view.fill_scale())
    assert abs(center.x() - 260) < 2 and abs(center.y()) < 2
    view.pivot(a.id, c.id, on_done=lambda: done.append("pivot"))
    center, _ = view.camera()
    assert done[-1] == "pivot"
    assert abs(center.x()) < 2 and abs(center.y() - 260) < 2
