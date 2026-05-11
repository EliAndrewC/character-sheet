"""Character API routes — CRUD, auto-save, publish, revert, and HTMX partials."""

from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

import json

from app.database import get_db
from app.game_data import (
    ADVANTAGES, CAMPAIGN_ADVANTAGES, CAMPAIGN_DISADVANTAGES,
    COMBAT_SKILLS, DISADVANTAGES, SCHOOLS, SKILLS, SCHOOL_KNACKS, Ring,
    ring_max,
)
from app.models import Character, CharacterVersion, GamingGroup, User
from app.services.auth import can_edit_character, can_view_drafts, get_admin_ids, get_all_editors
from app.services.rolls import compute_dan
from app.services.sanitize import sanitize_sections
from app.services.versions import (
    compute_diff_summary,
    compute_version_diff,
    discard_draft_changes,
    publish_character,
    revert_character,
    stringify_version_diff_entries,
)
from app.services.xp import calculate_total_xp

router = APIRouter(prefix="/characters")


def _templates():
    from app.main import templates
    return templates


def _apply_school_ring_change(character: Character, new_choice: str, knacks: dict) -> str:
    """Reconcile a request to set ``school_ring_choice``.

    Returns the value that should actually be persisted on the row.

    Rules:
    - Published characters can never change their school ring after
      Apply Changes. The editor locks the picker visibly, but the
      server is the source of truth: ignore any incoming choice that
      doesn't match the persisted one. This is the path that produced
      Kitsune Moriko's orphan state - a tab whose JS thought the
      character was unpublished POSTed a school-ring switch the
      editor wouldn't otherwise have offered.

    - Unpublished characters can change freely. When the choice does
      change, drop the OLD school ring's value by the auto-raise
      amount it had received (1 always, plus 1 more at Dan>=4), so
      the free school-ring raises don't carry over as if the player
      had paid XP for them. Floored at 2.

    The old ring's drop happens IN PLACE on the character row. The
    caller still applies ring clamps after this returns.
    """
    if not new_choice:
        new_choice = ""
    old_choice = character.school_ring_choice or ""
    if new_choice == old_choice:
        return old_choice
    if character.is_published:
        # Lock-after-publish: keep the persisted value, regardless of
        # what the client sent.
        return old_choice
    # Unpublished + actual change: drop the old school ring using the
    # Dan computed from the incoming knacks (so a same-request knack
    # change is reflected). Knack data is the route's responsibility
    # to provide consistently.
    if old_choice:
        dan = compute_dan(knacks or {}) if knacks else 0
        drop = 1 + (1 if dan >= 4 else 0)
        column = f"ring_{old_choice.lower()}"
        current_val = getattr(character, column, None)
        if isinstance(current_val, int):
            setattr(character, column, max(2, current_val - drop))
    return new_choice


def _clamp_ring(ring_name: str, raw, school_ring_choice: str, knacks: dict, current_value: int) -> int:
    """Clamp a posted ring value to the legal range for the
    character's current school ring + Dan.

    Defense-in-depth for the cap that the editor UI already enforces.
    Non-integer / missing values fall back to the character's existing
    value so partial autosave payloads don't reset rings.
    """
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return current_value
    dan = compute_dan(knacks or {}) if knacks else 0
    upper = ring_max(ring_name, school_ring_choice or "", dan=dan)
    # Lower bound: 2 for any ring, 3 for school ring, 4 once 4th Dan
    # auto-raises the school ring. Mirrors the UI's schoolRingMin().
    if ring_name == school_ring_choice:
        lower = 4 if dan >= 4 else 3
    else:
        lower = 2
    return max(lower, min(upper, v))


def _sanitize_specializations(raw) -> list:
    """Coerce a posted ``specializations`` payload into the canonical
    ``List[Dict]`` shape, dropping garbage rows.

    Drops entries with empty/whitespace text, missing skill, or an
    unknown skill id. Always returns a list; coerces ``None`` and other
    non-list inputs to ``[]``.
    """
    if not isinstance(raw, list):
        return []
    cleaned: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = (entry.get("text") or "").strip()
        skills = entry.get("skills") or []
        if not text or not isinstance(skills, list) or not skills:
            continue
        sid = skills[0]
        if sid not in SKILLS and sid not in COMBAT_SKILLS:
            continue
        cleaned.append({"text": text, "skills": [sid]})
    return cleaned


def _parse_form_to_dict(form_data: dict) -> dict:
    """Parse flat form data into the nested structure for Character.from_dict."""
    data = {
        "name": form_data.get("name", "").strip(),
        "name_explanation": form_data.get("name_explanation", ""),
        "player_name": form_data.get("player_name", "").strip(),
        "lineage": (form_data.get("lineage") or "").strip(),
        "school": form_data.get("school", ""),
        "school_ring_choice": form_data.get("school_ring_choice", ""),
        "rings": {},
        "skills": {},
        "knacks": {},
        "foreign_knacks": {},
        "advantages": [],
        "disadvantages": [],
        "honor": float(form_data.get("honor", 1.0)),
        "rank": float(form_data.get("rank", 1.0)),
        "rank_locked": form_data.get("rank_locked") == "on",
        "recognition": float(form_data.get("recognition", 1.0)),
        "recognition_halved": form_data.get("recognition_halved") == "on",
        "starting_xp": int(form_data.get("starting_xp", 150)),
        "earned_xp": int(form_data.get("earned_xp", 0)),
        "notes": form_data.get("notes", ""),
        "attack": int(form_data.get("attack", 1)),
        "parry": int(form_data.get("parry", 1)),
    }

    # Rings
    for ring in Ring:
        key = f"ring_{ring.value.lower()}"
        data["rings"][ring.value] = int(form_data.get(key, 2))

    # Skills — only include non-zero
    for skill_id in SKILLS:
        key = f"skill_{skill_id}"
        val = int(form_data.get(key, 0))
        if val > 0:
            data["skills"][skill_id] = val

    # Knacks
    school = SCHOOLS.get(data["school"])
    if school:
        for knack_id in school.school_knacks:
            key = f"knack_{knack_id}"
            val = int(form_data.get(key, 1))
            data["knacks"][knack_id] = max(1, val)  # minimum 1

    # Foreign school knacks (non-supernatural knacks from other schools).
    # The legacy form-POST path is rarely used (autosave is JSON), but keep
    # it parity-compatible. Only entries with rank >= 1 are stored.
    for knack_id in SCHOOL_KNACKS:
        key = f"foreign_knack_{knack_id}"
        if key in form_data:
            try:
                val = int(form_data.get(key, 0))
            except (TypeError, ValueError):
                val = 0
            if val >= 1:
                data["foreign_knacks"][knack_id] = val

    # Advantages / Disadvantages (checkboxes)
    for adv_id in ADVANTAGES:
        if form_data.get(f"adv_{adv_id}") == "on":
            data["advantages"].append(adv_id)
    for dis_id in DISADVANTAGES:
        if form_data.get(f"dis_{dis_id}") == "on":
            data["disadvantages"].append(dis_id)

    # Specializations: editor sends the full list as a hidden JSON field
    # to mirror the autosave wire format. Missing field = empty list.
    raw = form_data.get("specializations_json", "")
    parsed = []
    if raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = []
    data["specializations"] = _sanitize_specializations(parsed)

    return data


@router.post("")
async def create_character(request: Request, db: Session = Depends(get_db)):
    """Create a blank draft character and redirect to the editor."""
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    character = Character(
        name="New Character",
        owner_discord_id=user["discord_id"],
        player_name=user.get("display_name", ""),
        current_void_points=2,  # start with full VP (all rings default to 2)
        # New drafts start hidden so the creator can iterate before sharing.
        # Cleared one-way by Apply Changes or the Make Draft Visible button.
        is_hidden=True,
    )
    db.add(character)
    db.commit()
    db.refresh(character)

    return RedirectResponse(f"/characters/{character.id}/edit", status_code=303)


@router.post("/{char_id}")
async def update_character(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return HTMLResponse("You don't have permission to edit this character.", status_code=403)

    form = await request.form()
    form_data = dict(form)
    data = _parse_form_to_dict(form_data)

    # Update fields
    character.name = data["name"]
    character.name_explanation = data["name_explanation"]
    character.lineage = data["lineage"]
    # Handle owner reassignment (GM only)
    new_owner_id = form_data.get("owner_discord_id")
    if new_owner_id:
        from app.services.auth import is_admin
        if is_admin(user["discord_id"]):
            new_owner = db.query(User).filter(User.discord_id == new_owner_id).first()
            if new_owner:
                character.owner_discord_id = new_owner.discord_id
                character.player_name = new_owner.display_name or new_owner.discord_name
    character.school = data["school"]
    # Reconcile the school-ring choice against the publish-lock and
    # auto-drop the old school ring (for unpublished characters) if
    # it's actually changing. See ``_apply_school_ring_change`` for
    # the full rules.
    _knacks = data.get("knacks") or {}
    character.school_ring_choice = _apply_school_ring_change(
        character, data["school_ring_choice"], _knacks,
    )
    # Clamp ring values against the form's own school + knacks so a
    # crafted POST can't bypass the editor's cap UI. The cap depends
    # on the school ring (school_ring_choice) and the character's
    # current Dan (derived from knacks).
    _src = data["rings"]
    _src_ring = character.school_ring_choice or ""
    character.ring_air = _clamp_ring("Air", _src.get("Air"), _src_ring, _knacks, character.ring_air)
    character.ring_fire = _clamp_ring("Fire", _src.get("Fire"), _src_ring, _knacks, character.ring_fire)
    character.ring_earth = _clamp_ring("Earth", _src.get("Earth"), _src_ring, _knacks, character.ring_earth)
    character.ring_water = _clamp_ring("Water", _src.get("Water"), _src_ring, _knacks, character.ring_water)
    character.ring_void = _clamp_ring("Void", _src.get("Void"), _src_ring, _knacks, character.ring_void)
    character.attack = data["attack"]
    character.parry = data["parry"]
    character.skills = data["skills"]
    character.knacks = data["knacks"]
    character.foreign_knacks = data.get("foreign_knacks", {}) or {}
    character.advantages = data["advantages"]
    character.disadvantages = data["disadvantages"]
    character.specializations = data["specializations"]
    character.honor = data["honor"]
    character.rank = data["rank"]
    character.rank_locked = data["rank_locked"]
    character.recognition = data["recognition"]
    character.recognition_halved = data["recognition_halved"]
    character.starting_xp = data["starting_xp"]
    character.earned_xp = data["earned_xp"]
    character.notes = data["notes"]

    db.commit()

    return RedirectResponse(f"/characters/{character.id}", status_code=303)


@router.post("/{char_id}/delete")
def delete_character(request: Request, char_id: int, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    character = db.query(Character).filter(Character.id == char_id).first()
    if character:
        owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
        all_editors = get_all_editors(
            character.editor_discord_ids or [],
            owner.granted_account_ids or [] if owner else [],
        )
        if not can_edit_character(
            user["discord_id"],
            character.owner_discord_id,
            all_editors,
        ):
            return HTMLResponse("You don't have permission to delete this character.", status_code=403)

        # Clean up S3 art keys before the row is gone. Capture the keys
        # first because ``db.delete`` will null them on the in-memory
        # object. A failure here (S3 down, bad IAM) is non-fatal: the
        # orphan-cleanup sweep in ``art_backup`` will catch the leftover
        # on the next startup.
        art_key = character.art_s3_key
        head_key = character.headshot_s3_key
        if art_key or head_key:
            import os
            import logging
            bucket = os.environ.get("S3_BACKUP_BUCKET")
            if bucket:
                region = os.environ.get("S3_BACKUP_REGION", "us-east-1")
                try:
                    from app.services.art_storage import delete_art
                    delete_art(bucket, region, art_key, head_key)
                except Exception as exc:
                    logging.getLogger(__name__).exception(
                        "Failed to clean art for deleted character %s: %s",
                        char_id, exc,
                    )

        db.delete(character)
        db.commit()
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Auto-save, publish, revert
# ---------------------------------------------------------------------------


def _check_rolling_char_can_edit_for_priest_spend(
    db: Session, user: dict, rolling_character_id: Any, priest: Character
) -> tuple[bool, JSONResponse | None]:
    """Phase 7 tightening: for cross-character priest-resource spends,
    the caller must have edit access to the ``rolling_character`` (i.e.
    the character whose sheet they're rolling from) AND that character
    must share the priest's gaming group. Returns (allowed, error_response).

    Read-only viewers (who can't edit the rolling character) are rejected
    server-side even though the frontend shim already short-circuits the
    POST; we can't assume the client is well-behaved.
    """
    if not priest.gaming_group_id:
        return False, JSONResponse(
            {"error": "Priest is not in a gaming group"}, status_code=403
        )
    if rolling_character_id is None:
        return False, JSONResponse(
            {"error": "rolling_character_id required"}, status_code=400
        )
    try:
        rolling_id = int(rolling_character_id)
    except (TypeError, ValueError):
        return False, JSONResponse(
            {"error": "rolling_character_id must be an integer"}, status_code=400
        )
    rolling = db.query(Character).filter(Character.id == rolling_id).first()
    if not rolling:
        return False, JSONResponse(
            {"error": "Rolling character not found"}, status_code=403
        )
    if rolling.gaming_group_id != priest.gaming_group_id:
        return False, JSONResponse(
            {"error": "Rolling character not in priest's gaming group"},
            status_code=403,
        )
    rolling_owner = db.query(User).filter(
        User.discord_id == rolling.owner_discord_id
    ).first()
    all_editors = get_all_editors(
        rolling.editor_discord_ids or [],
        rolling_owner.granted_account_ids or [] if rolling_owner else [],
    )
    if not can_edit_character(
        user["discord_id"], rolling.owner_discord_id, all_editors
    ):
        return False, JSONResponse(
            {"error": "Caller cannot edit rolling character"}, status_code=403
        )
    return True, None


@router.post("/{char_id}/ally-conviction")
async def ally_conviction(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Priest 5th Dan: a party member with edit access to their own
    character (which must share the priest's gaming group) can spend
    the priest's conviction on their rolls. The endpoint updates the
    priest's ``conviction_used`` counter in ``adventure_state`` by the
    requested ``delta`` (+1 or -1).

    Phase 7 tightening: bare gaming-group membership is no longer enough
    - the caller must have edit access to the ``rolling_character_id``
    they pass in the body. Read-only viewers are blocked server-side.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    priest = db.query(Character).filter(Character.id == char_id).first()
    if not priest:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if priest.school != "priest":
        return JSONResponse({"error": "Not a priest"}, status_code=400)
    # Priest must be at 5th Dan (lowest school knack >= 5).
    p_school_obj = SCHOOLS.get(priest.school)
    p_knack_ranks = [
        (priest.knacks or {}).get(k, 1) for k in (p_school_obj.school_knacks or [])
    ] if p_school_obj else []
    p_dan = min(p_knack_ranks) if p_knack_ranks else 0
    if p_dan < 5:
        return JSONResponse({"error": "Priest is not at 5th Dan"}, status_code=400)
    body = await request.json()
    allowed, err = _check_rolling_char_can_edit_for_priest_spend(
        db, user, body.get("rolling_character_id"), priest
    )
    if not allowed:
        return err
    try:
        delta = int(body.get("delta", 0))
    except (TypeError, ValueError):
        delta = 0
    if delta not in (-1, 1):
        return JSONResponse({"error": "delta must be +1 or -1"}, status_code=400)
    adv_state = dict(priest.adventure_state or {})
    pool_max = 2 * (priest.knacks or {}).get("conviction", 0)
    used = int(adv_state.get("conviction_used", 0))
    new_used = max(0, min(pool_max, used + delta))
    adv_state["conviction_used"] = new_used
    priest.adventure_state = adv_state
    db.commit()
    return JSONResponse({"used": new_used, "pool_max": pool_max})


@router.post("/{char_id}/precepts-pool")
async def precepts_pool(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Priest 3rd Dan: a party member can commit a post-swap pool back to
    this priest's ``precepts_pool`` column. The swap itself (which dice
    move in and out) is computed client-side; this endpoint just accepts
    the resulting whole-list and normalises it.

    Replace-whole-list was chosen over a per-index mutation so concurrent
    allies editing in the same session can't produce a partially-mutated
    pool; last-write-wins matches the best-effort ``_postPriestAllyDelta``
    pattern used by the 5th Dan conviction sibling.

    Phase 7 tightening: non-owner callers must have edit access to the
    ``rolling_character_id`` they pass in the body, and that character
    must share the priest's gaming group. Owner-as-caller continues to
    be allowed unconditionally (a priest swapping from their own pool
    via this endpoint, rather than through /track, is a supported path).
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    priest = db.query(Character).filter(Character.id == char_id).first()
    if not priest:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if priest.school != "priest":
        return JSONResponse({"error": "Not a priest"}, status_code=400)
    p_school_obj = SCHOOLS.get(priest.school)
    p_knack_ranks = [
        (priest.knacks or {}).get(k, 1) for k in (p_school_obj.school_knacks or [])
    ] if p_school_obj else []
    p_dan = min(p_knack_ranks) if p_knack_ranks else 0
    if p_dan < 3:
        return JSONResponse({"error": "Priest is not at 3rd Dan"}, status_code=400)
    body = await request.json()
    if not isinstance(body, dict) or "pool" not in body:
        return JSONResponse({"error": "Body must include 'pool'"}, status_code=400)
    is_owner = priest.owner_discord_id == user["discord_id"]
    if not is_owner:
        allowed, err = _check_rolling_char_can_edit_for_priest_spend(
            db, user, body.get("rolling_character_id"), priest
        )
        if not allowed:
            return err
    priest.precepts_pool = _sanitize_precepts_pool(body["pool"])
    db.commit()
    return JSONResponse({"pool": priest.precepts_pool})


@router.post("/{char_id}/autosave")
async def autosave_character(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Auto-save draft character from JSON payload."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    # Check edit permission using account-level grants
    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = await request.json()

    # Update character fields from JSON
    if "name" in body:
        character.name = body["name"]
    if "name_explanation" in body:
        character.name_explanation = body["name_explanation"] or ""
    if "age" in body:
        # Coerce to int; treat blank/invalid as "unset" so the player can
        # clear the field. Negative values are persisted but flagged by
        # validate_character so the user sees the issue on the View Sheet.
        raw = body.get("age")
        if raw in (None, "", "null"):
            character.age = None
        else:
            try:
                character.age = int(raw)
            except (TypeError, ValueError):
                character.age = None
    if "lineage" in body:
        # Metadata, same shape contract as age: blank/null is "unset"
        # (flagged by validate_character). Anything else stored verbatim
        # after trimming whitespace.
        raw = body.get("lineage")
        character.lineage = raw.strip() if isinstance(raw, str) else ""
    if body.get("owner_discord_id"):
        # Only admins can reassign ownership
        from app.services.auth import is_admin
        if is_admin(user["discord_id"]):
            new_owner = db.query(User).filter(
                User.discord_id == body["owner_discord_id"]
            ).first()
            if new_owner:
                character.owner_discord_id = new_owner.discord_id
                character.player_name = new_owner.display_name or new_owner.discord_name
    if "school" in body:
        character.school = body["school"]
    if "school_ring_choice" in body:
        # Reconcile against the publish-lock + auto-drop the old
        # school ring (for unpublished characters) if changing.
        # Knacks for the Dan check come from the body when present,
        # else the persisted value.
        _src_knacks = body.get("knacks", character.knacks) or {}
        character.school_ring_choice = _apply_school_ring_change(
            character, body["school_ring_choice"], _src_knacks,
        )
    if "rings" in body:
        rings = body["rings"]
        # Clamp ring values against the autosave payload's own school
        # ring + knacks so a crafted JSON can't bypass the editor cap.
        # ``body`` may not include ``school_ring_choice`` / ``knacks``
        # in this autosave call - fall back to the persisted values.
        clamp_ring_choice = character.school_ring_choice
        clamp_knacks = body.get("knacks", character.knacks) or {}
        character.ring_air = _clamp_ring("Air", rings.get("Air"), clamp_ring_choice, clamp_knacks, character.ring_air)
        character.ring_fire = _clamp_ring("Fire", rings.get("Fire"), clamp_ring_choice, clamp_knacks, character.ring_fire)
        character.ring_earth = _clamp_ring("Earth", rings.get("Earth"), clamp_ring_choice, clamp_knacks, character.ring_earth)
        character.ring_water = _clamp_ring("Water", rings.get("Water"), clamp_ring_choice, clamp_knacks, character.ring_water)
        character.ring_void = _clamp_ring("Void", rings.get("Void"), clamp_ring_choice, clamp_knacks, character.ring_void)
        # For unpublished characters, keep void points at max as rings change
        if not character.is_published:
            ring_vals = [character.ring_air, character.ring_fire,
                         character.ring_earth, character.ring_water,
                         character.ring_void]
            if character.school in ("shugenja", "isawa_ishi"):
                from app.game_data import void_points_max_shugenja, SCHOOLS
                rings = {"Air": character.ring_air, "Fire": character.ring_fire,
                         "Earth": character.ring_earth, "Water": character.ring_water,
                         "Void": character.ring_void}
                knacks = character.knacks or {}
                school_def = SCHOOLS.get(character.school)
                school_knack_ranks = [knacks.get(k, 1) for k in school_def.school_knacks] if school_def else [0]
                dan = min(school_knack_ranks) if school_knack_ranks else 0
                character.current_void_points = void_points_max_shugenja(rings, dan)
            else:
                character.current_void_points = min(ring_vals)
    if "attack" in body:
        character.attack = body["attack"]
    if "parry" in body:
        character.parry = body["parry"]
    if "skills" in body:
        character.skills = body["skills"]
    if "knacks" in body:
        character.knacks = body["knacks"]
    if "foreign_knacks" in body:
        # Coerce ranks to ints; drop entries with rank < 1 so removal via
        # decrement-to-zero on the editor is honored.
        raw = body.get("foreign_knacks") or {}
        cleaned: dict = {}
        if isinstance(raw, dict):
            for kid, rank in raw.items():
                try:
                    r = int(rank)
                except (TypeError, ValueError):
                    continue
                if r >= 1:
                    cleaned[kid] = r
        character.foreign_knacks = cleaned
    if "advantages" in body:
        character.advantages = body["advantages"]
    if "campaign_advantages" in body:
        character.campaign_advantages = body["campaign_advantages"]
    if "campaign_disadvantages" in body:
        character.campaign_disadvantages = body["campaign_disadvantages"]
    if "disadvantages" in body:
        character.disadvantages = body["disadvantages"]
    if "advantage_details" in body:
        character.advantage_details = body["advantage_details"]
    if "specializations" in body:
        character.specializations = _sanitize_specializations(
            body["specializations"]
        )
    if "technique_choices" in body:
        # Validate the Mantis 2nd Dan free-raise choice so a crafted POST
        # cannot persist initiative or a non-rollable knack. An empty/None
        # value clears the choice and is allowed.
        choices = body["technique_choices"] or {}
        if isinstance(choices, dict) and "mantis_2nd_dan_free_raise" in choices:
            from app.services.dice import mantis_2nd_dan_eligible_choices
            val = choices.get("mantis_2nd_dan_free_raise")
            if val not in (None, ""):
                school_id = body.get("school") or character.school
                # Foreign rollable knacks are valid targets too. Read foreign
                # knacks from the incoming body if present, otherwise from the
                # persisted character so we don't reject an existing valid
                # selection during a partial save.
                fk = (
                    body.get("foreign_knacks")
                    if "foreign_knacks" in body
                    else (character.foreign_knacks or {})
                )
                eligible = mantis_2nd_dan_eligible_choices(school_id, fk)
                if val not in eligible:
                    return JSONResponse(
                        {"error": f"Invalid mantis_2nd_dan_free_raise choice: {val!r}"},
                        status_code=400,
                    )
        character.technique_choices = body["technique_choices"]
    if "honor" in body:
        character.honor = body["honor"]
    if "rank" in body:
        character.rank = body["rank"]
    if "rank_locked" in body:
        character.rank_locked = body["rank_locked"]
    if "recognition" in body:
        character.recognition = body["recognition"]
    if "recognition_halved" in body:
        character.recognition_halved = body["recognition_halved"]
    if "rank_recognition_awards" in body:
        # Validate the shape so the client can't push junk into the JSON
        # column. Each award must have id + numeric deltas + a non-empty
        # source. Recognition deltas can never be negative.
        raw_awards = body["rank_recognition_awards"]
        if not isinstance(raw_awards, list):
            return JSONResponse(
                {"error": "rank_recognition_awards must be a list"},
                status_code=400,
            )
        cleaned: list = []
        for entry in raw_awards:
            if not isinstance(entry, dict):
                return JSONResponse(
                    {"error": "Each award must be an object"}, status_code=400
                )
            try:
                rank_delta = float(entry.get("rank_delta", 0))
                recog_delta = float(entry.get("recognition_delta", 0))
            except (TypeError, ValueError):
                return JSONResponse(
                    {"error": "Award deltas must be numbers"}, status_code=400
                )
            if recog_delta < 0:
                return JSONResponse(
                    {"error": "Recognition delta cannot be negative"},
                    status_code=400,
                )
            source = (entry.get("source") or "").strip()
            if not source:
                return JSONResponse(
                    {"error": "Award source is required"}, status_code=400
                )
            award_type = entry.get("type", "rank_recognition")
            if award_type not in ("rank_recognition", "good_reputation", "bad_reputation"):
                award_type = "rank_recognition"
            cleaned.append({
                "id": str(entry.get("id") or ""),
                "type": award_type,
                "rank_delta": rank_delta,
                "recognition_delta": recog_delta,
                "source": source,
                "created_at": entry.get("created_at") or "",
            })
        character.rank_recognition_awards = cleaned
    if "earned_xp" in body:
        character.earned_xp = body["earned_xp"]
    if "notes" in body:
        character.notes = body["notes"]
    if "sections" in body:
        character.sections = sanitize_sections(body["sections"])

    db.commit()
    # Surface has_unpublished_changes so the editor can show / hide the
    # Apply Changes and Discard Changes buttons based on whether the
    # save actually moved the character away from the published state.
    # Metadata-only edits (e.g. age) won't flip the flag.
    return JSONResponse({
        "status": "saved",
        "has_unpublished_changes": character.has_unpublished_changes,
    })


@router.post("/{char_id}/set-group")
async def set_group(request: Request, char_id: int, db: Session = Depends(get_db)):
    """Assign or unassign a character's gaming group.

    Bypasses the version system entirely: ``gaming_group_id`` is excluded from
    ``Character.to_dict()``, so it never enters published_state snapshots or
    triggers a "modified" badge.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = await request.json()
    raw = body.get("gaming_group_id")
    if raw in (None, "", "null"):
        character.gaming_group_id = None
    else:
        try:
            gid = int(raw)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Invalid gaming_group_id"}, status_code=400)
        group = db.query(GamingGroup).filter(GamingGroup.id == gid).first()
        if not group:
            return JSONResponse({"error": "Group not found"}, status_code=404)
        character.gaming_group_id = gid

    db.commit()
    return JSONResponse({"ok": True, "gaming_group_id": character.gaming_group_id})


@router.post("/{char_id}/set-award-source")
async def set_award_source(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Update only the freeform ``source`` text on a single GM award.

    Bypasses the version system: source text is metadata so editing it must
    NOT trigger a draft / "modified" badge. ``has_unpublished_changes``
    explicitly strips ``source`` from each award before diffing.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = await request.json()
    award_id = str(body.get("award_id") or "")
    new_source = (body.get("source") or "").strip()
    if not award_id:
        return JSONResponse({"error": "award_id is required"}, status_code=400)
    if not new_source:
        return JSONResponse({"error": "source is required"}, status_code=400)

    # Build a fresh list of fresh dicts so SQLAlchemy detects the JSON column
    # change. (In-place mutation of nested dicts inside a JSON column does not
    # mark the column dirty.)
    new_awards = [dict(a) for a in (character.rank_recognition_awards or [])]
    found = False
    for award in new_awards:
        if award.get("id") == award_id:
            award["source"] = new_source
            found = True
            break
    if not found:
        return JSONResponse({"error": "Award not found"}, status_code=404)

    character.rank_recognition_awards = new_awards
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/{char_id}/show")
async def show_character_route(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Make a character visible to non-editors. Editors only.

    The /show + /hide pair is a bidirectional toggle; the edit-page
    visibility chip uses one or the other based on the current state."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    character.is_hidden = False
    db.commit()
    return JSONResponse({"status": "visible"})


@router.post("/{char_id}/hide")
async def hide_character_route(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Hide a character from non-editors. Editors only.

    Mirror of /show. A re-hidden character behaves the same as a never-
    revealed draft from a non-editor's perspective: omitted from the
    homepage list, 404 on direct view, stripped from other party
    members' party-effect data."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    character.is_hidden = True
    db.commit()
    return JSONResponse({"status": "hidden"})


@router.post("/{char_id}/publish")
async def publish_character_route(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Publish the current draft as a new version."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    custom_summary = body.get("summary", "")
    make_visible = bool(body.get("make_visible", False))

    version = publish_character(
        character, db,
        summary=custom_summary,
        author_discord_id=user["discord_id"],
        make_visible=make_visible,
    )
    db.commit()

    return JSONResponse({
        "status": "published",
        "version_number": version.version_number,
        "summary": version.summary,
    })


@router.post("/{char_id}/discard")
async def discard_changes_route(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Roll back a draft's unapplied edits to the last published state.

    No new version is created. Returns 409 when the character has never
    been published (nothing to revert to); the editor's Discard button
    is gated on ``is_published`` so a real user shouldn't hit that path.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    did = discard_draft_changes(character, db)
    if not did:
        return JSONResponse(
            {"error": "Character has no published version to discard to."},
            status_code=409,
        )
    db.commit()
    return JSONResponse({"status": "discarded"})


@router.get("/{char_id}/draft-diff")
async def draft_diff_route(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Return the list of human-readable diff lines between the draft
    state and the last published state. Used by the Discard confirmation
    modal so the user can see what they're about to undo. Empty list
    when there are no unapplied changes."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    if not character.is_published:
        return JSONResponse({"lines": []})
    # Use the comprehensive structured diff (same one that powers the
    # version-history drill-down) so the modal stays in sync with
    # has_unpublished_changes. The older sparse compute_diff_summary
    # missed fields like notes / sections / foreign_knacks, producing
    # a confusing "(no changes)" message while the badge still showed
    # "Draft changes".
    entries = compute_version_diff(
        character.published_state or {}, character.to_dict(),
    )
    return JSONResponse({"lines": stringify_version_diff_entries(entries)})


@router.post("/{char_id}/revert/{version_id}")
async def revert_character_route(
    request: Request, char_id: int, version_id: int, db: Session = Depends(get_db)
):
    """Revert character to a previous version."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    custom_summary = body.get("summary", "")

    version = revert_character(
        character, version_id, db,
        summary=custom_summary,
        author_discord_id=user["discord_id"],
    )
    db.commit()

    return JSONResponse({
        "status": "reverted",
        "version_number": version.version_number,
    })


@router.post("/{char_id}/versions/{version_id}/summary")
async def update_version_summary(
    request: Request, char_id: int, version_id: int, db: Session = Depends(get_db)
):
    """Update the summary text of a version."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    version = db.query(CharacterVersion).filter(
        CharacterVersion.id == version_id,
        CharacterVersion.character_id == char_id,
    ).first()
    if not version:
        return JSONResponse({"error": "Version not found"}, status_code=404)

    body = await request.json()
    version.summary = body.get("summary", version.summary)
    db.commit()

    return JSONResponse({"status": "ok", "summary": version.summary})


@router.get("/{char_id}/versions")
def get_versions(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Get version history for a character."""
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    versions = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.character_id == char_id)
        .order_by(CharacterVersion.version_number.desc())
        .all()
    )

    return JSONResponse({
        "versions": [
            {
                "id": v.id,
                "version_number": v.version_number,
                "summary": v.summary,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]
    })


@router.get("/{char_id}/versions/{version_id}/diff", response_class=HTMLResponse)
def get_version_diff(
    request: Request, char_id: int, version_id: int, db: Session = Depends(get_db)
):
    """HTMX partial showing what changed between this version and the prior one.

    Editor-only - the version-history block on the sheet is already
    gated by ``viewer_can_edit``, but we duplicate the gate here so a
    non-editor can't poke the endpoint directly.

    Returns 404 for the very first version (no prior to diff against).
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"], character.owner_discord_id, all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    version = db.query(CharacterVersion).filter(
        CharacterVersion.id == version_id,
        CharacterVersion.character_id == char_id,
    ).first()
    if not version:
        return JSONResponse({"error": "Version not found"}, status_code=404)

    if version.version_number <= 1:
        return JSONResponse({"error": "No prior version"}, status_code=404)

    prev = db.query(CharacterVersion).filter(
        CharacterVersion.character_id == char_id,
        CharacterVersion.version_number == version.version_number - 1,
    ).first()
    if not prev:
        # Defensive: a version_number gap (e.g. row deleted) shouldn't
        # 500 the drill-down. Treat it like "no prior to diff against".
        return JSONResponse({"error": "Prior version missing"}, status_code=404)

    entries = compute_version_diff(prev.state or {}, version.state or {})
    return _templates().TemplateResponse(
        request=request,
        name="character/partials/version_diff.html",
        context={"entries": entries, "version": version, "prev": prev},
    )


# ---------------------------------------------------------------------------
# Live tracking (combat state, per-adventure abilities)
# ---------------------------------------------------------------------------


@router.post("/{char_id}/track")
async def track_state(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Update mutable combat/adventure state from the character sheet."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    owner = db.query(User).filter(User.discord_id == character.owner_discord_id).first()
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        all_editors,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = await request.json()

    if "current_light_wounds" in body:
        character.current_light_wounds = max(0, int(body["current_light_wounds"]))
    if "current_serious_wounds" in body:
        character.current_serious_wounds = max(0, int(body["current_serious_wounds"]))
    if "current_void_points" in body:
        character.current_void_points = max(0, int(body["current_void_points"]))
    if "current_temp_void_points" in body:
        character.current_temp_void_points = max(0, int(body["current_temp_void_points"]))
    if "adventure_state" in body:
        character.adventure_state = body["adventure_state"]
    if "action_dice" in body:
        character.action_dice = _sanitize_action_dice(body["action_dice"])
    if "precepts_pool" in body:
        pool = _sanitize_precepts_pool(body["precepts_pool"])
        # Defensive guard: only Priests at 3rd Dan or higher can hold a
        # pool. An incoming payload from a stale tab (character dropped
        # below 3rd Dan after the tab loaded) gets silently wiped rather
        # than persisting a pool that should no longer exist.
        if pool and (
            character.school != "priest"
            or compute_dan(character.knacks or {}) < 3
        ):
            pool = []
        character.precepts_pool = pool

    db.commit()
    return JSONResponse({"status": "ok"})


def _sanitize_action_dice(raw: Any) -> list:
    """Coerce a client-supplied action_dice list into safe storage shape.

    Each entry becomes ``{"value": int, "spent": bool}`` with the value
    clamped to 0-10. An optional ``"spent_by"`` string (describing the
    action that auto-spent the die) is preserved, capped at 500 chars.
    The ``athletics_only`` flag (Togashi Ise Zumi extra die, Mantis 4th
    Dan bonus die) and the ``mantis_4th_dan`` marker flag are preserved
    so the die's spending restrictions survive a reload. Malformed or
    non-list payloads become ``[]``.
    """
    if not isinstance(raw, list):
        return []
    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            value = int(entry.get("value", 0))
        except (TypeError, ValueError):
            continue
        value = max(0, min(10, value))
        out = {"value": value, "spent": bool(entry.get("spent", False))}
        spent_by = entry.get("spent_by")
        if isinstance(spent_by, str) and spent_by:
            out["spent_by"] = spent_by[:500]
        if entry.get("athletics_only"):
            out["athletics_only"] = True
        if entry.get("mantis_4th_dan"):
            out["mantis_4th_dan"] = True
        cleaned.append(out)
    return cleaned


PRECEPTS_POOL_MAX_ENTRIES = 10
# Upper sanity bound on a single die value. Reroll-10s means a single die
# can legitimately exceed 10 (e.g. 10 + 9 = 19); a very long run of 10s
# could theoretically produce any integer. Cap at 100 to reject obvious
# garbage without clipping realistic rolls.
PRECEPTS_POOL_MAX_VALUE = 100


def _sanitize_precepts_pool(raw: Any) -> list:
    """Coerce a client-supplied precepts_pool list into safe storage shape.

    Each entry becomes ``{"value": int}`` clamped to ``1..PRECEPTS_POOL_MAX_VALUE``.
    Non-list payloads become ``[]``; malformed entries are dropped; the list
    is capped at ``PRECEPTS_POOL_MAX_ENTRIES`` entries (the maximum
    reasonable precepts skill rank).
    """
    if not isinstance(raw, list):
        return []
    cleaned: list = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            value = int(entry.get("value"))
        except (TypeError, ValueError):
            continue
        value = max(1, min(PRECEPTS_POOL_MAX_VALUE, value))
        cleaned.append({"value": value})
        if len(cleaned) >= PRECEPTS_POOL_MAX_ENTRIES:
            break
    return cleaned


# ---------------------------------------------------------------------------
# HTMX partial endpoints
# ---------------------------------------------------------------------------


@router.post("/api/xp-calc", response_class=HTMLResponse)
async def xp_calc_partial(request: Request):
    """Recalculate XP from form data and return the XP summary partial."""
    form = await request.form()
    form_data = dict(form)
    data = _parse_form_to_dict(form_data)

    # Build the dict shape expected by calculate_total_xp
    char_dict = {
        "school": data["school"],
        "school_ring_choice": data["school_ring_choice"],
        "rings": data["rings"],
        "attack": data["attack"],
        "parry": data["parry"],
        "skills": data["skills"],
        "knacks": data["knacks"],
        "foreign_knacks": data.get("foreign_knacks", {}),
        "advantages": data["advantages"],
        "disadvantages": data["disadvantages"],
        "honor": data["honor"],
        "rank": data["rank"],
        "recognition": data["recognition"],
        "recognition_halved": data["recognition_halved"],
        "earned_xp": data["earned_xp"],
        "starting_xp": data["starting_xp"],
    }

    xp = calculate_total_xp(char_dict)
    available = data["starting_xp"] + data["earned_xp"]
    remaining = available - xp["total"]

    return _templates().TemplateResponse(
        request=request,
        name="character/partials/xp_summary.html",
        context={"xp": xp, "available": available, "remaining": remaining},
    )


@router.get("/api/school-info/{school_id}", response_class=HTMLResponse)
def school_info_partial(request: Request, school_id: str):
    """Return school details partial when school selection changes."""
    school = SCHOOLS.get(school_id)
    if not school:
        return HTMLResponse("")

    knacks = {kid: SCHOOL_KNACKS.get(kid) for kid in school.school_knacks}

    return _templates().TemplateResponse(
        request=request,
        name="character/partials/school_info.html",
        context={"school": school, "knacks": knacks, "rings": [r.value for r in Ring]},
    )
