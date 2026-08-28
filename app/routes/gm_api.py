"""GM-facing, token-authenticated read-only JSON API.

Exists for out-of-band tooling - specifically the GM's ``gm-assistant``
REPL - rather than for the browser. Players post their rolls into Discord
as dice-card PNGs, which are a lossy render of a ``roll_history`` row this
app already holds; the REPL joins the Discord message (author's discord id
+ message timestamp) against ``GET /api/rolls`` (``actor_discord_id`` +
``updated_at``) to recover the exact roll, character and skill without any
OCR. Because an attachment's filename cannot distinguish a roll card from a
meme, the join IS the detector.

``GET /characters/{id}/rolls`` does not fit that job: it needs a browser
session belonging to an editor of that one character, so a poll would cost
one authenticated call per PC per tick. These routes are cross-character
and authenticate with a single shared secret the REPL keeps in a config
file.

Everything here is READ-ONLY. The token grants read access to every
character's rolls including hidden ones, so it is GM-equivalent and is
accepted only from the ``Authorization`` header - never from a query
string, which would leak it into logs and browser history.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, GamingGroup, RollHistory
from app.routes.rolls import _iso_utc
from app.services.roll_descriptions import label_for_roll


router = APIRouter(prefix="/api", tags=["gm-api"])


#: Env var holding the shared secret. Set as a Fly secret in production;
#: the GM copies the same value into gm-assistant's gitignored
#: ``development-secrets.ini``. Unset -> the endpoints 503 rather than
#: silently becoming open to the world.
TOKEN_ENV_VAR = "ROLL_QUERY_TOKEN"

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _authorize(request: Request) -> Optional[JSONResponse]:
    """Return an error response if the caller may not use the API, else None.

    ``503`` when the token is not configured (fail-closed: an unset env var
    must never mean "no auth required"), ``401`` for a missing, malformed
    or wrong ``Authorization: Bearer`` header. The comparison is
    constant-time so a wrong token leaks nothing about the right one.
    """
    expected = (os.environ.get(TOKEN_ENV_VAR) or "").strip()
    if not expected:
        return JSONResponse(
            {"error": f"{TOKEN_ENV_VAR} is not configured"}, status_code=503,
        )
    scheme, _, presented = (
        request.headers.get("Authorization") or ""
    ).partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        presented.strip(), expected,
    ):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return None


# ---------------------------------------------------------------------------
# Query-parameter parsing
#
# The params are declared as bare strings and validated by hand rather than
# via FastAPI type coercion, so that a request with a bad token gets a 401
# instead of a 422 that would tell an unauthenticated caller which
# parameters the endpoint takes.
# ---------------------------------------------------------------------------


def _parse_since(raw: Optional[str]) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse the required ``since`` bound into a naive-UTC datetime.

    ``roll_history.updated_at`` is a SQLite ``func.now()`` value, i.e.
    naive UTC, so the comparison value has to be naive UTC too. A naive
    input is REJECTED rather than assumed to be UTC - a client in a
    non-UTC timezone that guessed wrong would silently miss rolls, and a
    400 is far easier to debug than a poll that skips half a session.
    """
    if not raw or not raw.strip():
        return None, "since is required (ISO-8601 with an explicit timezone)"
    text = raw.strip()
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None, "since is not a valid ISO-8601 timestamp"
    if dt.tzinfo is None:
        return None, "since must carry an explicit timezone offset"
    return dt.astimezone(timezone.utc).replace(tzinfo=None), None


def _parse_limit(raw: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Parse ``limit``: default 200, clamped to MAX_LIMIT, must be >= 1."""
    if raw is None or not str(raw).strip():
        return DEFAULT_LIMIT, None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None, "limit must be an integer"
    if value < 1:
        return None, "limit must be at least 1"
    return min(value, MAX_LIMIT), None


def _parse_group(raw: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Parse the optional ``group`` filter (a ``gaming_groups.id``)."""
    if raw is None or not str(raw).strip():
        return None, None
    try:
        return int(str(raw).strip()), None
    except ValueError:
        return None, "group must be an integer gaming_groups.id"


# ---------------------------------------------------------------------------
# Payload flattening
# ---------------------------------------------------------------------------


def _die_values(cells: Any) -> List[int]:
    """Flatten payload dice cells to one int per die.

    A cell is ``{"parts": [10, 7]}`` - a 10 that exploded into a 7 - and
    the client needs the die's contribution to the total, not the card's
    is-ten / reroll styling, so each cell collapses to the sum of its
    parts (17 in that example). Plain ``{"value": n}`` cells and bare ints
    are accepted too, mirroring ``dice_card._coerce_cells``.
    """
    out: List[int] = []
    if not isinstance(cells, list):
        return out
    for cell in cells:
        if isinstance(cell, dict):
            parts = cell.get("parts")
            if not isinstance(parts, list):
                value = cell.get("value")
                parts = [value] if value is not None else []
        elif isinstance(cell, int) and not isinstance(cell, bool):
            parts = [cell]
        else:
            continue
        total = 0
        for part in parts:
            try:
                total += int(part)
            except (TypeError, ValueError):
                continue
        out.append(total)
    return out


def _bonuses(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize the payload's bonus rows to ``{label, value}``.

    Stored rows use ``amount`` (the dice-card renderer's key); the API
    name is ``value``. ``amount`` is read first so a hand-written payload
    that already used ``value`` still works.
    """
    out: List[Dict[str, Any]] = []
    for raw in payload.get("bonuses") or []:
        if not isinstance(raw, dict):
            continue
        amount = raw.get("amount", raw.get("value"))
        try:
            value = int(amount)
        except (TypeError, ValueError):
            continue
        out.append({"label": str(raw.get("label") or ""), "value": value})
    return out


def _alternatives(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The payload's "alternative totals" rows, passed through as stored.

    Keys are already the API's: ``label``, ``extra_flat``, and the
    optional ``max_total`` / ``max_total_source`` pair that carries a
    conditional ceiling (e.g. Withdrawn capping an open sincerity roll).
    Those caps are exactly what a hand-typed roll leaves ambiguous, so
    they are worth returning verbatim.
    """
    return [
        row for row in (payload.get("alternatives") or [])
        if isinstance(row, dict)
    ]


def _serialize_roll(
    row: RollHistory, character: Character, group: Optional[GamingGroup],
) -> Dict[str, Any]:
    payload = row.payload or {}
    out: Dict[str, Any] = {
        "id": row.id,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
        "character_id": row.character_id,
        "character_name": character.name,
        "gaming_group_id": character.gaming_group_id,
        "gaming_group_name": group.name if group else None,
        "owner_discord_id": character.owner_discord_id,
        "actor_discord_id": row.actor_discord_id,
        "is_owner_roll": bool(row.is_owner_roll),
        "roll_key": row.roll_key,
        "label": label_for_roll(row.roll_key, payload),
        "skill_rank": payload.get("skill_rank"),
        "formula": payload.get("formula") or "",
        "total": payload.get("total"),
        "kept": _die_values(payload.get("kept")),
        "dropped": _die_values(payload.get("dropped")),
        "bonuses": _bonuses(payload),
        "alternatives": _alternatives(payload),
        "tn": row.tn,
        "impaired_at_roll": bool(row.impaired_at_roll),
        "action_die_spent": row.action_die_spent,
        "is_hidden": bool(row.is_hidden),
        "annotation": row.annotation or "",
    }
    # The card's "Roll made by" line; set only when someone other than the
    # owner made the roll, so pass it through only when it is present.
    rolled_by = payload.get("rolled_by")
    if rolled_by:
        out["rolled_by"] = rolled_by
    return out


# ---------------------------------------------------------------------------
# GET /api/rolls
# ---------------------------------------------------------------------------


@router.get("/rolls")
async def list_rolls(
    request: Request,
    since: Optional[str] = None,
    limit: Optional[str] = None,
    group: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Recent rolls across EVERY character, oldest-first.

    Query params:

    - ``since`` (required): ISO-8601 **with an explicit timezone**; a naive
      value is a 400. Filters on ``updated_at``, not ``created_at``: a
      player can toggle post-roll bonuses (PATCH) after the row is created
      and before pasting the dice card into Discord, so polling on
      ``updated_at`` guarantees the caller eventually sees the final state
      of a row it first saw mid-edit. The bound is inclusive.
    - ``limit`` (optional): default 200, capped at 1000.
    - ``group`` (optional): a ``gaming_groups.id``; restricts to characters
      in that group. Purely a convenience - every row carries
      ``gaming_group_id`` so the client can filter itself.

    Ordering is ascending by ``(updated_at, id)`` and the response carries
    ``more``, so a client pages by passing the last row's ``updated_at``
    back as ``since`` (the inclusive bound re-delivers that row, which the
    client de-duplicates by ``id``).

    Hidden rolls ARE included, flagged ``is_hidden`` - the GM is the
    audience here, and a roll the player hid from their own history is
    still a roll that happened. The GM's own NPC characters are included
    too: a contested roll is scored on the difference between the two
    sides, so the NPC's roll matters as much as the PC's. Characters in no
    gaming group appear with ``gaming_group_id: null``.

    Per-roll notes:

    - ``kept`` / ``dropped`` are plain ints, one per die, each the sum of
      an exploded chain (a 10 rerolled into a 7 is ``17``).
    - ``bonuses`` rows are ``{label, value}``.
    - ``skill_rank`` is the rank the character had in the governing skill
      or knack WHEN THE ROLL WAS MADE, stamped into the payload at record
      time. It is ``null`` for rolls with no single governing rank (rings,
      wound checks, initiative, bless, freeform) and for rows recorded
      before that stamping existed.
    """
    denied = _authorize(request)
    if denied is not None:
        return denied

    since_dt, error = _parse_since(since)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    row_limit, error = _parse_limit(limit)
    if error:
        return JSONResponse({"error": error}, status_code=400)
    group_id, error = _parse_group(group)
    if error:
        return JSONResponse({"error": error}, status_code=400)

    q = (
        db.query(RollHistory, Character, GamingGroup)
        .join(Character, Character.id == RollHistory.character_id)
        .outerjoin(GamingGroup, GamingGroup.id == Character.gaming_group_id)
        .filter(RollHistory.updated_at >= since_dt)
    )
    if group_id is not None:
        q = q.filter(Character.gaming_group_id == group_id)
    q = q.order_by(RollHistory.updated_at.asc(), RollHistory.id.asc())

    # One extra row is fetched purely to answer "is there another page?"
    # without a second COUNT query; it is trimmed before serializing.
    rows = q.limit(row_limit + 1).all()
    more = len(rows) > row_limit
    rows = rows[:row_limit]

    return JSONResponse({
        "rolls": [_serialize_roll(r, c, g) for r, c, g in rows],
        "more": more,
    })


# ---------------------------------------------------------------------------
# GET /api/characters
# ---------------------------------------------------------------------------


@router.get("/characters")
async def list_characters(request: Request, db: Session = Depends(get_db)):
    """Every character, with owner / editor ids, group, and current ranks.

    Two things the roll feed alone cannot supply:

    1. **Contested rolls are scored against the opponent's rank**, and a
       hand-typed roll often omits it (``44 Precepts`` with no ``@rank``).
       This map lets the client fill the rank in from the sheet instead of
       asking the GM mid-game.
    2. **Attribution for typed rolls.** A hand-typed roll never touches
       ``roll_history``, so the only handle on it is the Discord message
       author - this is the map from discord id to character.

    ``skills`` is the character's stored skill dict plus the two combat
    skills that live in their own columns, under the same ``attack`` /
    ``parry`` keys the roll feed uses for them (no catalog skill shares
    those ids). ``knacks`` merges school knacks with ``foreign_knacks``
    (knacks bought from another school), since a lookup only cares what
    rank the character actually has; the two sets never share an id.

    **These are the ranks NOW, not as of some past roll.** Ranks change
    when XP is spent, so back-filling an old session can attribute a rank
    the character did not have at the time. For live play that is correct;
    where a roll matters and its row exists in ``roll_history``, prefer
    that row's ``skill_rank``.
    """
    denied = _authorize(request)
    if denied is not None:
        return denied

    groups = db.query(GamingGroup).order_by(GamingGroup.name.asc()).all()
    group_names = {g.id: g.name for g in groups}

    characters = db.query(Character).order_by(Character.id.asc()).all()
    out = []
    for c in characters:
        skills = dict(c.skills or {})
        skills["attack"] = int(c.attack or 0)
        skills["parry"] = int(c.parry or 0)
        knacks = dict(c.knacks or {})
        knacks.update(c.foreign_knacks or {})
        out.append({
            "id": c.id,
            "name": c.name,
            "owner_discord_id": c.owner_discord_id,
            "editor_discord_ids": list(c.editor_discord_ids or []),
            "gaming_group_id": c.gaming_group_id,
            "gaming_group_name": group_names.get(c.gaming_group_id),
            "skills": skills,
            "knacks": knacks,
        })

    return JSONResponse({
        "characters": out,
        "gaming_groups": [g.to_dict() for g in groups],
    })
