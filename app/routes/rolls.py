"""Roll history API.

GET, POST, PATCH endpoints for the Roll History feature. Recording is
owner-only with a blanket admin exclusion (GMs never pollute someone
else's history); viewing + editing (annotation, hide/unhide) is open
to any editor.
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db, prefetch_body
from app.models import Character, RollHistory, User
from app.models import RollSession as RollSessionModel
from app.services.npcs import npc_guard
from app.services.auth import (
    can_edit_character,
    can_view_drafts,
    get_admin_ids,
    get_all_editors,
)
from app.services import fight_log, roll_sessions
from app.services.roll_descriptions import label_for_roll
from app.services.rolls_history import (
    coerce_action_die_spent,
    coerce_annotation,
    coerce_payload,
    coerce_tn,
    should_record_roll,
    skill_rank_for_roll,
)


router = APIRouter(
    prefix="/characters", tags=["rolls"],
    dependencies=[Depends(prefetch_body), Depends(npc_guard)],
)


def _load_character(db: Session, char_id: int) -> tuple[Character, User]:
    """Look up the character and its owner row. Returns (char, owner)
    or (None, None) if the character doesn't exist. Owner may be None
    when the character has no owner_discord_id."""
    char = db.query(Character).filter(Character.id == char_id).first()
    if char is None:
        return None, None
    owner = (
        db.query(User)
        .filter(User.discord_id == char.owner_discord_id)
        .first()
    )
    return char, owner


def _viewer_can_see_character(user, character, owner) -> bool:
    """Mirror of the pages.py viewer-gate for hidden drafts: editors AND
    admins can see anything; everyone else 404s on hidden / draft chars."""
    if not character.is_hidden and character.is_published:
        return True
    granted = (owner.granted_account_ids or []) if owner else []
    return can_view_drafts(
        (user or {}).get("discord_id"),
        character.owner_discord_id,
        granted,
    )


def _require_editor(user, character, owner) -> bool:
    """True iff the user has edit access to the character."""
    if not user:  # pragma: no cover - every caller 401s anonymous first
        return False
    granted = (owner.granted_account_ids or []) if owner else []
    all_editors = get_all_editors(
        character.editor_discord_ids or [], granted,
    )
    return can_edit_character(
        user["discord_id"], character.owner_discord_id, all_editors,
    )


def _iso_utc(dt) -> "str | None":
    """Serialize a datetime as a UTC-marked ISO string.

    SQLite's ``CURRENT_TIMESTAMP`` returns naive UTC datetimes. Without
    an explicit ``Z`` marker the JavaScript ``Date`` parser treats the
    string as local time, so a roll made at 21:00 UTC would render in
    the user's browser as 9:00 PM regardless of their actual timezone.
    """
    if dt is None:
        return None
    s = dt.isoformat()
    if dt.tzinfo is None and not s.endswith("Z"):
        return s + "Z"
    return s


def _serialize_roll(r: RollHistory) -> dict:
    return {
        "id": r.id,
        "roll_key": r.roll_key,
        "roll_label": label_for_roll(r.roll_key, r.payload),
        "payload": r.payload or {},
        "impaired_at_roll": bool(r.impaired_at_roll),
        "tn": r.tn,
        "action_die_spent": r.action_die_spent,
        "is_hidden": bool(r.is_hidden),
        "annotation": r.annotation or "",
        "actor_discord_id": r.actor_discord_id,
        "is_owner_roll": bool(r.is_owner_roll),
        "created_at": _iso_utc(r.created_at),
    }


# ---------------------------------------------------------------------------
# POST /characters/{char_id}/rolls - create
# ---------------------------------------------------------------------------


@router.post("/{char_id}/rolls")
async def create_roll(
    request: Request, char_id: int, db: Session = Depends(get_db),
):
    """Record a roll the user just made.

    Gate: anonymous -> 401, missing char -> 404, hidden + non-editor -> 404.
    Recording decision delegates to ``should_record_roll``:
    - owner -> persist as owner roll
    - non-admin editor -> persist as non-owner-editor roll (tagged)
    - admin who is NOT the owner -> 204 No Content, NO row created
      (regardless of whether they're also in ``editor_discord_ids`` or
      ``granted_account_ids``). GMs are always treated as test rollers
      on characters they don't own.
    - any other visitor (logged-in non-editor) -> 204 No Content
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character, owner = _load_character(db, char_id)
    if character is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _viewer_can_see_character(user, character, owner):
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner_grants = (owner.granted_account_ids or []) if owner else []
    record, is_owner_roll = should_record_roll(
        user["discord_id"], character, owner_grants,
    )
    if not record:
        return Response(status_code=204)

    body = await request.json()
    payload = coerce_payload(body.get("payload"))
    action_die = coerce_action_die_spent(body.get("action_die_spent"))
    tn = coerce_tn(body.get("tn"))
    roll_key = (body.get("roll_key") or "")[:200]
    # roll_label is intentionally NOT stored - the display label is derived from
    # payload.title at read time (see _serialize_roll / label_for_roll). Clients
    # may still send it; we ignore it.
    impaired = bool(body.get("impaired_at_roll", False))

    # Stamp the governing skill / knack rank into the payload at record
    # time. The dice formula sums trait + skill, so the rank cannot be
    # recovered from the row afterwards, and looking it up on the
    # character later would report today's rank rather than the one the
    # roll was actually made with. Server-derived from roll_key (never
    # taken from the client). See GET /api/rolls, which surfaces it.
    rank = skill_rank_for_roll(roll_key, character)
    if rank is not None:
        payload["skill_rank"] = rank
    # Only the Discord boost command names a target; a client cannot.
    payload.pop("target_message_id", None)

    row = RollHistory(
        character_id=character.id,
        roll_key=roll_key,
        actor_discord_id=user["discord_id"],
        is_owner_roll=is_owner_roll,
        impaired_at_roll=impaired,
        tn=tn,
        payload=payload,
        action_die_spent=action_die,
    )
    db.add(row)
    db.commit()
    return JSONResponse({
        "id": row.id,
        "created_at": _iso_utc(row.created_at),
    })


# ---------------------------------------------------------------------------
# PATCH /characters/{char_id}/rolls/{roll_id} - update payload
# ---------------------------------------------------------------------------


@router.patch("/{char_id}/rolls/{roll_id}")
async def update_roll(
    request: Request, char_id: int, roll_id: int,
    db: Session = Depends(get_db),
):
    """Update the payload (and action_die_spent) on a recorded roll.

    Used when the player toggles a post-roll discretionary bonus (3rd
    Dan free raise, Lucky reroll, VP spend, etc.) - the live modal
    PATCHes the updated payload through here so the saved history row
    always reflects the modal's current state.

    Gate: must be the same actor that originally created the row, to
    prevent a non-owner editor from rewriting an owner's roll mid-flight.
    ``annotation``, ``is_hidden``, ``tn`` are NOT touched by this endpoint.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character, owner = _load_character(db, char_id)
    if character is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _viewer_can_see_character(user, character, owner):
        return JSONResponse({"error": "Not found"}, status_code=404)

    row = (
        db.query(RollHistory)
        .filter(RollHistory.id == roll_id, RollHistory.character_id == char_id)
        .first()
    )
    if row is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if row.actor_discord_id != user["discord_id"]:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = await request.json()
    if "payload" in body:
        previous_rank = (row.payload or {}).get("skill_rank")
        previous_target = (row.payload or {}).get("target_message_id")
        row.payload = coerce_payload(body["payload"])
        # The client PATCHes a freshly-built payload that has no notion of
        # skill_rank (it is stamped server-side at create time), so carry
        # the create-time value forward rather than letting a post-roll
        # bonus toggle erase it.
        if previous_rank is not None and "skill_rank" not in row.payload:
            row.payload = {**row.payload, "skill_rank": previous_rank}
        # The boost's target (set by the Discord command) is server-stamped
        # too, and never the client's to change or erase.
        row.payload = {
            k: v for k, v in row.payload.items() if k != "target_message_id"
        }
        if previous_target is not None:
            row.payload["target_message_id"] = previous_target
    if "action_die_spent" in body:
        row.action_die_spent = coerce_action_die_spent(body["action_die_spent"])
    db.commit()
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# GET /characters/{char_id}/rolls - list
# ---------------------------------------------------------------------------


@router.get("/{char_id}/rolls")
async def list_rolls(
    request: Request, char_id: int, include_hidden: int = 0,
    db: Session = Depends(get_db),
):
    """List rolls for a character. Editor-only view.

    Returns ``{"rolls": [...]}`` newest-first. Default omits hidden rolls;
    pass ``include_hidden=1`` to include them.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character, owner = _load_character(db, char_id)
    if character is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _viewer_can_see_character(user, character, owner):
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _require_editor(user, character, owner):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    q = db.query(RollHistory).filter(RollHistory.character_id == char_id)
    if not include_hidden:
        q = q.filter(RollHistory.is_hidden == False)  # noqa: E712
    q = q.order_by(RollHistory.created_at.desc(), RollHistory.id.desc())
    return JSONResponse({"rolls": [_serialize_roll(r) for r in q.all()]})


# ---------------------------------------------------------------------------
# PATCH /characters/{char_id}/rolls/{roll_id}/annotation
# ---------------------------------------------------------------------------


@router.patch("/{char_id}/rolls/{roll_id}/annotation")
async def update_annotation(
    request: Request, char_id: int, roll_id: int,
    db: Session = Depends(get_db),
):
    """Set the freeform editor annotation on a roll. Any editor may
    update; the system does not record who wrote the annotation."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    character, owner = _load_character(db, char_id)
    if character is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _viewer_can_see_character(user, character, owner):
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _require_editor(user, character, owner):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    row = (
        db.query(RollHistory)
        .filter(RollHistory.id == roll_id, RollHistory.character_id == char_id)
        .first()
    )
    if row is None:
        return JSONResponse({"error": "Not found"}, status_code=404)

    body = await request.json()
    row.annotation = coerce_annotation(body.get("annotation"))
    db.commit()
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# POST /characters/{char_id}/rolls/{roll_id}/hide and /unhide
# ---------------------------------------------------------------------------


def _set_hidden(
    request: Request, char_id: int, roll_id: int,
    db: Session, hidden: bool,
):
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    character, owner = _load_character(db, char_id)
    if character is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _viewer_can_see_character(user, character, owner):
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not _require_editor(user, character, owner):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    row = (
        db.query(RollHistory)
        .filter(RollHistory.id == roll_id, RollHistory.character_id == char_id)
        .first()
    )
    if row is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    row.is_hidden = hidden
    db.commit()
    return JSONResponse({"ok": True, "is_hidden": hidden})


@router.post("/{char_id}/rolls/{roll_id}/hide")
async def hide_roll(
    request: Request, char_id: int, roll_id: int,
    db: Session = Depends(get_db),
):
    return _set_hidden(request, char_id, roll_id, db, True)


@router.post("/{char_id}/rolls/{roll_id}/unhide")
async def unhide_roll(
    request: Request, char_id: int, roll_id: int,
    db: Session = Depends(get_db),
):
    return _set_hidden(request, char_id, roll_id, db, False)


# ---------------------------------------------------------------------------
# POST /characters/{char_id}/roll - the server makes the roll
# ---------------------------------------------------------------------------


def _client_address(request: Request) -> str:
    return (request.headers.get("fly-client-ip")
            or (request.client.host if request.client else "") or "unknown")


@router.post("/{char_id}/roll")
async def make_roll(request: Request, char_id: int, db: Session = Depends(get_db)):
    """Roll on the server (server-rolls-design 4.1; decisions S1, S6).

    Anyone who can see the sheet may roll: an editor LIVE (spends apply,
    and the roll is recorded under ``should_record_roll``), anyone else in
    SIMULATE mode (Read-only Roll Mode - nothing about the character
    changes). Anonymous visitors are rate-limited. Body:
    ``{"roll_key", "void", "otherworldliness", "kitsune_swap", "request_id"}``
    (a retry with the same ``request_id`` gets the same roll back).
    """
    user = getattr(request.state, "user", None)
    character, owner = _load_character(db, char_id)
    if character is None or not _viewer_can_see_character(user, character, owner):
        return JSONResponse({"error": "Not found"}, status_code=404)
    if not user and not roll_sessions.anonymous_allowed(_client_address(request)):
        return JSONResponse({"error": "Too many rolls - try again in a minute"}, status_code=429)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "Expected a JSON object"}, status_code=400)
    viewer = user["discord_id"] if user else None
    live = bool(user) and _require_editor(user, character, owner)
    record, is_owner_roll = (False, False)
    if live:
        grants = (owner.granted_account_ids or []) if owner else []
        record, is_owner_roll = should_record_roll(viewer, character, grants)
    try:
        result = roll_sessions.start_roll(
            db, character, str(body.get("roll_key") or ""), body,
            viewer=viewer, live=live, record=record, is_owner_roll=is_owner_roll,
            request_id=body.get("request_id") or None, rng=_test_rng(request),
        )
    except roll_sessions.RollRefused as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    fight_log.record_roll(db, character, body, result)
    db.commit()
    return JSONResponse(result)


def _test_rng(request: Request):
    """The clicktest server's scripted dice (``X-Test-Dice``), else None."""
    if os.environ.get("TEST_AUTH_BYPASS") == "true" and request.headers.get("x-test-dice"):
        return roll_sessions.scripted_rng_from_header(request.headers["x-test-dice"])
    return None


@router.post("/{char_id}/roll/{session_id}/act")
async def act_on_roll(request: Request, char_id: int, session_id: str,
                      db: Session = Depends(get_db)):
    """A post-roll action on a roll the server made (server-rolls-design
    Phases 3-4): ``{"action", "args"}`` - raise / conviction / togashi_raise
    (and their ``undo_`` forms), ``courtier_5th`` with ``{"on"}``, and the
    rerolls in ``roll_sessions.REROLLS``. The
    session's mode was fixed when it was rolled: a live session spends the
    pools, a simulated one never does. Only the viewer who rolled may act."""
    user = getattr(request.state, "user", None)
    viewer = user["discord_id"] if user else None
    session = db.get(RollSessionModel, session_id)
    if session is None or session.character_id != char_id or session.viewer_discord_id != viewer:
        return JSONResponse({"error": "Not found"}, status_code=404)
    character = db.get(Character, char_id)
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "Expected a JSON object"}, status_code=400)
    action = str(body.get("action") or "")
    # A reroll rolls dice, so an anonymous visitor's counts against the
    # same limit as their rolls.
    if (not user and action in roll_sessions.REROLLS
            and not roll_sessions.anonymous_allowed(_client_address(request))):
        return JSONResponse({"error": "Too many rolls - try again in a minute"}, status_code=429)
    try:
        result = roll_sessions.act(db, session, character, action, body.get("args") or {},
                                   rng=_test_rng(request))
    except roll_sessions.RollRefused as exc:
        return JSONResponse({"error": str(exc), "tracking": roll_sessions.tracking_snapshot(character)},
                            status_code=400)
    fight_log.record_act(db, character, session_id, action, result)
    db.commit()
    return JSONResponse(result)
