"""Layout for the GM's Dark Secret map (``/groups/{id}/dark-secrets``).

Pure computation: given a gaming group's visible characters, build the
node positions and curved arrow paths the SVG template draws. Kept out
of the route so the geometry is unit-testable without a browser.

Coordinate space is the SVG ``viewBox`` (``WIDTH`` x ``HEIGHT``):

* "Involved" characters - anyone who holds a dark secret or knows one -
  sit on a circle. Their arrows run knower -> holder, curved so that a
  mutual pair (A knows B's, B knows A's) draws as two distinct arcs.
* A knowing *player* with no character in this group gets a "ghost"
  node on the same circle so the arrow still has somewhere to land.
* Everyone else (no secret held, no secret known) lines up in a column
  off to the right, wearing a halo.

Reading the knower relation exposes the private "who knows" data, so
the route that calls this is admin-only.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from app.services.dark_secret import DARK_SECRET_ID

WIDTH = 920
HEIGHT = 556
CIRCLE_CX = 330
CIRCLE_CY = 278
CIRCLE_R = 200
HALO_COLUMN_X = 790
PORTRAIT_W = 80
PORTRAIT_H = 108
# How far from a node's centre an arrow starts/ends (so it clears the
# portrait + name), and the extra clearance for the arrowhead.
NODE_CLEARANCE = 78
ARROWHEAD_CLEARANCE = 12
CURVE_OFFSET = 42

Point = Tuple[float, float]


def _bezier(p0: Point, c: Point, p1: Point, t: float) -> Point:
    mt = 1 - t
    return (
        mt * mt * p0[0] + 2 * mt * t * c[0] + t * t * p1[0],
        mt * mt * p0[1] + 2 * mt * t * c[1] + t * t * p1[1],
    )


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _subcurve(p0: Point, c: Point, p1: Point, t0: float, t1: float) -> Tuple[Point, Point, Point]:
    """De Casteljau: the quadratic sub-segment of [p0, c, p1] on [t0, t1]."""
    def lerp(a: Point, b: Point, t: float) -> Point:
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    # Split at t0, keep the right half.
    q0 = lerp(p0, c, t0)
    q1 = lerp(c, p1, t0)
    r0 = lerp(q0, q1, t0)
    # New curve: r0, q1, p1. Reparametrize t1 on it.
    u = (t1 - t0) / (1 - t0) if t0 < 1 else 0.0
    s0 = lerp(r0, q1, u)
    s1 = lerp(q1, p1, u)
    end = lerp(s0, s1, u)
    return r0, s0, end


def arrow_path(src: Point, dst: Point) -> Dict[str, Any]:
    """Curved arrow from ``src`` to ``dst``, trimmed to clear both nodes.

    Returns the SVG path ``d`` plus the label anchor (curve midpoint).
    The control point is offset to the right of the src->dst direction,
    so the reverse arrow bends the other way and the pair reads as two
    separate arcs.
    """
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length  # unit normal (right-hand side)
    mid = ((src[0] + dst[0]) / 2, (src[1] + dst[1]) / 2)
    ctrl = (mid[0] + nx * CURVE_OFFSET, mid[1] + ny * CURVE_OFFSET)

    # Sample to find where the curve leaves the src node and enters dst.
    steps = 200
    t0 = 0.0
    t1 = 1.0
    for i in range(steps + 1):
        t = i / steps
        if _dist(_bezier(src, ctrl, dst, t), src) >= NODE_CLEARANCE:
            t0 = t
            break
    for i in range(steps, -1, -1):
        t = i / steps
        if _dist(_bezier(src, ctrl, dst, t), dst) >= NODE_CLEARANCE + ARROWHEAD_CLEARANCE:
            t1 = t
            break
    if t1 <= t0:  # nodes overlap - draw a straight stub so nothing crashes
        t0, t1 = 0.4, 0.6
    a, b, c = _subcurve(src, ctrl, dst, t0, t1)
    label = _bezier(src, ctrl, dst, (t0 + t1) / 2)
    return {
        "d": f"M {a[0]:.1f} {a[1]:.1f} Q {b[0]:.1f} {b[1]:.1f} {c[0]:.1f} {c[1]:.1f}",
        "label_x": round(label[0], 1),
        "label_y": round(label[1], 1),
    }


def build_dark_secret_map(
    characters: List[Any],
    player_names: Dict[str, str],
    headshot_url_for,
) -> Dict[str, Any]:
    """Compute nodes + arrows for the map.

    ``characters`` are the group's visible Character rows;
    ``player_names`` maps discord id -> display name (for ghost nodes);
    ``headshot_url_for(char)`` resolves the portrait URL (or None).
    """
    by_owner: Dict[str, List[Any]] = {}
    for c in characters:
        by_owner.setdefault(c.owner_discord_id or "", []).append(c)

    holders = [
        c for c in characters
        if DARK_SECRET_ID in (c.disadvantages or [])
    ]

    # Relation edges as (knower_key, holder_id). knower_key is a
    # character id for a real node or "player:<discord_id>" for a ghost.
    edges: List[Tuple[str, Any]] = []
    unchosen: List[Any] = []
    ghost_players: Dict[str, str] = {}
    for h in holders:
        detail = (h.advantage_details or {}).get(DARK_SECRET_ID) or {}
        pid = detail.get("player") or ""
        if not pid:
            unchosen.append(h)
            continue
        knowers = [k for k in by_owner.get(pid, []) if k.id != h.id]
        if knowers:
            for k in knowers:
                edges.append((k.id, h))
        else:
            ghost_players[pid] = player_names.get(pid) or pid
            edges.append((f"player:{pid}", h))

    involved_ids = {h.id for h in holders} | {
        k for k, _ in edges if not isinstance(k, str)
    }
    involved = [c for c in characters if c.id in involved_ids]
    haloed = [c for c in characters if c.id not in involved_ids]

    # Place involved characters, then ghost players, around the circle.
    ring_keys: List[Any] = [c.id for c in involved] + [f"player:{p}" for p in ghost_players]
    positions: Dict[Any, Point] = {}
    n = len(ring_keys)
    for i, key in enumerate(ring_keys):
        if n == 1:
            positions[key] = (CIRCLE_CX, CIRCLE_CY)
            continue
        angle = -math.pi / 2 + 2 * math.pi * i / n
        positions[key] = (
            round(CIRCLE_CX + CIRCLE_R * math.cos(angle), 1),
            round(CIRCLE_CY + CIRCLE_R * math.sin(angle), 1),
        )

    unchosen_ids = {c.id for c in unchosen}
    nodes: List[Dict[str, Any]] = []
    for c in involved:
        x, y = positions[c.id]
        nodes.append({
            "kind": "character",
            "id": c.id,
            "name": c.name or f"Character #{c.id}",
            "x": x, "y": y,
            "headshot_url": headshot_url_for(c),
            "holds_secret": c.id in {h.id for h in holders},
            "knower_unchosen": c.id in unchosen_ids,
            "halo": False,
        })
    for pid, pname in ghost_players.items():
        x, y = positions[f"player:{pid}"]
        nodes.append({
            "kind": "player",
            "id": f"player:{pid}",
            "name": pname,
            "x": x, "y": y,
            "headshot_url": None,
            "holds_secret": False,
            "knower_unchosen": False,
            "halo": False,
        })

    # Halo column: evenly spaced down the right edge.
    m = len(haloed)
    for i, c in enumerate(haloed):
        y = HEIGHT / 2 if m == 1 else 90 + (HEIGHT - 180) * i / (m - 1)
        nodes.append({
            "kind": "character",
            "id": c.id,
            "name": c.name or f"Character #{c.id}",
            "x": HALO_COLUMN_X, "y": round(y, 1),
            "headshot_url": headshot_url_for(c),
            "holds_secret": False,
            "knower_unchosen": False,
            "halo": True,
        })

    name_of = {nd["id"]: nd["name"] for nd in nodes}
    arrows: List[Dict[str, Any]] = []
    for knower_key, holder in edges:
        geom = arrow_path(positions[knower_key], positions[holder.id])
        knower_name = name_of[knower_key]
        arrows.append({
            "from": knower_key,
            "to": holder.id,
            "holder_name": holder.name or f"Character #{holder.id}",
            "knower_name": knower_name,
            "ghost": isinstance(knower_key, str),
            **geom,
        })

    return {
        "width": WIDTH,
        "height": HEIGHT,
        "portrait_w": PORTRAIT_W,
        "portrait_h": PORTRAIT_H,
        "nodes": nodes,
        "arrows": arrows,
        "holder_count": len(holders),
    }
