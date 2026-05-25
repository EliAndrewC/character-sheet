"""Roll history API.

GET, POST, PATCH endpoints for the Roll History feature. Recording is
owner-only with a blanket admin exclusion (GMs never pollute someone
else's history); viewing + editing (annotation, hide/unhide) is open
to any editor.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, RollHistory, User
from app.services.auth import (
    can_edit_character,
    can_view_drafts,
    get_admin_ids,
    get_all_editors,
)
from app.services.roll_descriptions import label_for_roll
from app.services.rolls_history import (
    coerce_action_die_spent,
    coerce_annotation,
    coerce_payload,
    coerce_tn,
    should_record_roll,
)


router = APIRouter(prefix="/characters", tags=["rolls"])


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
        row.payload = coerce_payload(body["payload"])
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
