import math

from mindmap.layout import (
    BRANCH_DISTANCE,
    MIN_GAP,
    Point,
    nearest_in_direction,
    place_child,
)


def test_first_child_of_root_goes_east():
    assert place_child((0, 0), occupied=[(0, 0)]) == (BRANCH_DISTANCE, 0)


def test_children_fan_out_without_overlap():
    occupied = [(0, 0)]
    for _ in range(12):
        pos = place_child((0, 0), occupied)
        assert all(math.hypot(pos[0] - x, pos[1] - y) >= MIN_GAP for x, y in occupied)
        occupied.append(pos)


def test_second_and_third_children_use_other_directions():
    occupied = [(0, 0)]
    first = place_child((0, 0), occupied)
    occupied.append(first)
    second = place_child((0, 0), occupied)
    assert second == (0, BRANCH_DISTANCE)  # south


def test_continues_outward_from_grandparent():
    # Parent is west of its own parent, so the child should keep going west.
    assert place_child((-260, 0), occupied=[(0, 0), (-260, 0)], grandparent=(0, 0)) == (
        -520,
        0,
    )
    # Parent north of grandparent -> child goes north.
    assert place_child((0, -260), occupied=[(0, 0), (0, -260)], grandparent=(0, 0)) == (
        0,
        -520,
    )


def test_nearest_in_direction_picks_cone_and_distance():
    pts = [
        Point(1, 100, 0),   # east, near
        Point(2, 300, 0),   # east, far
        Point(3, 0, -100),  # north
        Point(4, 0, 100),   # south
        Point(5, -100, 0),  # west
    ]
    assert nearest_in_direction((0, 0), pts, "E").id == 1
    assert nearest_in_direction((0, 0), pts, "N").id == 3
    assert nearest_in_direction((0, 0), pts, "S").id == 4
    assert nearest_in_direction((0, 0), pts, "W").id == 5


def test_nearest_in_direction_none_when_nothing_there():
    assert nearest_in_direction((0, 0), [Point(1, 100, 0)], "W") is None
    assert nearest_in_direction((0, 0), [], "N") is None


def test_nearest_in_direction_prefers_on_axis():
    pts = [Point(1, 100, 90), Point(2, 120, 0)]
    assert nearest_in_direction((0, 0), pts, "E").id == 2


def test_ignores_self_position():
    assert nearest_in_direction((0, 0), [Point(1, 0, 0)], "E") is None
