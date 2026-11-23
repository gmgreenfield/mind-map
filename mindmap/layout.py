"""Pure geometry: where to put new branches and which node lies N/S/E/W.

Coordinates are Qt scene coordinates: +x is east, +y is south.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

DIRECTIONS: dict[str, tuple[float, float]] = {
    "N": (0.0, -1.0),
    "E": (1.0, 0.0),
    "S": (0.0, 1.0),
    "W": (-1.0, 0.0),
}

BRANCH_DISTANCE = 260.0
MIN_GAP = 180.0


@dataclass(frozen=True)
class Point:
    id: int
    x: float
    y: float


def _free(x: float, y: float, occupied: Iterable[tuple[float, float]], gap: float) -> bool:
    return all(math.hypot(x - ox, y - oy) >= gap for ox, oy in occupied)


def _direction_order(parent: tuple[float, float], grandparent: tuple[float, float] | None) -> list[str]:
    """Prefer continuing outward (away from the grandparent), then the sides, then back."""
    if grandparent is None:
        return ["E", "S", "W", "N"]
    dx, dy = parent[0] - grandparent[0], parent[1] - grandparent[1]
    if abs(dx) >= abs(dy):
        out = "E" if dx >= 0 else "W"
        sides = ["S", "N"]
    else:
        out = "S" if dy >= 0 else "N"
        sides = ["E", "W"]
    back = {"E": "W", "W": "E", "N": "S", "S": "N"}[out]
    return [out, *sides, back]


def place_child(
    parent: tuple[float, float],
    occupied: Sequence[tuple[float, float]],
    grandparent: tuple[float, float] | None = None,
    distance: float = BRANCH_DISTANCE,
    gap: float = MIN_GAP,
) -> tuple[float, float]:
    """Pick a free spot N/E/S/W of the parent, then diagonals, moving further out."""
    order = _direction_order(parent, grandparent)
    diagonals = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    for ring in range(1, 8):
        r = distance * ring
        candidates = [(DIRECTIONS[d][0] * r, DIRECTIONS[d][1] * r) for d in order]
        candidates += [(dx * r * 0.75, dy * r * 0.75) for dx, dy in diagonals]
        for cx, cy in candidates:
            x, y = parent[0] + cx, parent[1] + cy
            if _free(x, y, occupied, gap):
                return (x, y)
    # Crowded: fall back to straight out, far away.
    dx, dy = DIRECTIONS[order[0]]
    return (parent[0] + dx * distance * 8, parent[1] + dy * distance * 8)


def nearest_in_direction(
    current: tuple[float, float], candidates: Iterable[Point], direction: str
) -> Point | None:
    """Closest candidate within a 45° half-angle cone of the given direction."""
    ux, uy = DIRECTIONS[direction]
    best: tuple[float, Point] | None = None
    for p in candidates:
        dx, dy = p.x - current[0], p.y - current[1]
        dist = math.hypot(dx, dy)
        if dist == 0:
            continue
        along = (dx * ux + dy * uy) / dist  # cos of angle to direction
        if along < math.cos(math.radians(45)) - 1e-9:
            continue
        # Penalise off-axis nodes so straight-ahead wins ties.
        score = dist * (2.0 - along)
        if best is None or score < best[0]:
            best = (score, p)
    return best[1] if best else None
