"""Character API routes — CRUD, auto-save, publish, revert, and HTMX partials."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.game_data import (
    ADVANTAGES, CAMPAIGN_ADVANTAGES, CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES, SCHOOLS, SKILLS, SCHOOL_KNACKS, Ring,
)
from app.models import Character, CharacterVersion, User
from app.services.auth import can_edit_character, can_view_drafts, get_admin_ids
from app.services.versions import publish_character, revert_character
from app.services.xp import calculate_total_xp

router = APIRouter(prefix="/characters")


def _templates():
    from app.main import templates
    return templates


def _parse_form_to_dict(form_data: dict) -> dict:
    """Parse flat form data into the nested structure for Character.from_dict."""
    data = {
        "name": form_data.get("name", "").strip(),
        "player_name": form_data.get("player_name", "").strip(),
        "school": form_data.get("school", ""),
        "school_ring_choice": form_data.get("school_ring_choice", ""),
        "rings": {},
        "skills": {},
        "knacks": {},
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

    # Advantages / Disadvantages (checkboxes)
    for adv_id in ADVANTAGES:
        if form_data.get(f"adv_{adv_id}") == "on":
            data["advantages"].append(adv_id)
    for dis_id in DISADVANTAGES:
        if form_data.get(f"dis_{dis_id}") == "on":
            data["disadvantages"].append(dis_id)

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

    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        character.editor_discord_ids or [],
    ):
        return HTMLResponse("You don't have permission to edit this character.", status_code=403)

    form = await request.form()
    form_data = dict(form)
    data = _parse_form_to_dict(form_data)

    # Update fields
    character.name = data["name"]
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
    character.school_ring_choice = data["school_ring_choice"]
    character.ring_air = data["rings"]["Air"]
    character.ring_fire = data["rings"]["Fire"]
    character.ring_earth = data["rings"]["Earth"]
    character.ring_water = data["rings"]["Water"]
    character.ring_void = data["rings"]["Void"]
    character.attack = data["attack"]
    character.parry = data["parry"]
    character.skills = data["skills"]
    character.knacks = data["knacks"]
    character.advantages = data["advantages"]
    character.disadvantages = data["disadvantages"]
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
        if not can_edit_character(
            user["discord_id"],
            character.owner_discord_id,
            character.editor_discord_ids or [],
        ):
            return HTMLResponse("You don't have permission to delete this character.", status_code=403)
        db.delete(character)
        db.commit()
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Auto-save, publish, revert
# ---------------------------------------------------------------------------


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
    owner_granted = owner.granted_account_ids or [] if owner else []
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        owner_granted,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = await request.json()

    # Update character fields from JSON
    if "name" in body:
        character.name = body["name"]
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
        character.school_ring_choice = body["school_ring_choice"]
    if "rings" in body:
        rings = body["rings"]
        character.ring_air = rings.get("Air", character.ring_air)
        character.ring_fire = rings.get("Fire", character.ring_fire)
        character.ring_earth = rings.get("Earth", character.ring_earth)
        character.ring_water = rings.get("Water", character.ring_water)
        character.ring_void = rings.get("Void", character.ring_void)
    if "attack" in body:
        character.attack = body["attack"]
    if "parry" in body:
        character.parry = body["parry"]
    if "skills" in body:
        character.skills = body["skills"]
    if "knacks" in body:
        character.knacks = body["knacks"]
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
    if "earned_xp" in body:
        character.earned_xp = body["earned_xp"]
    if "notes" in body:
        character.notes = body["notes"]

    db.commit()
    return JSONResponse({"status": "saved"})


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
    owner_granted = owner.granted_account_ids or [] if owner else []
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        owner_granted,
    ):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    custom_summary = body.get("summary", "")

    version = publish_character(
        character, db,
        summary=custom_summary,
        author_discord_id=user["discord_id"],
    )
    db.commit()

    return JSONResponse({
        "status": "published",
        "version_number": version.version_number,
        "summary": version.summary,
    })


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
    owner_granted = owner.granted_account_ids or [] if owner else []
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        owner_granted,
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
    owner_granted = owner.granted_account_ids or [] if owner else []
    if not can_edit_character(
        user["discord_id"],
        character.owner_discord_id,
        owner_granted,
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


# ---------------------------------------------------------------------------
# Live tracking (combat state, per-adventure abilities)
# ---------------------------------------------------------------------------


@router.post("/{char_id}/track")
async def track_state(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    """Update mutable combat/adventure state from the character sheet."""
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return JSONResponse({"error": "Not found"}, status_code=404)

    body = await request.json()

    if "current_light_wounds" in body:
        character.current_light_wounds = max(0, int(body["current_light_wounds"]))
    if "current_serious_wounds" in body:
        character.current_serious_wounds = max(0, int(body["current_serious_wounds"]))
    if "current_void_points" in body:
        character.current_void_points = max(0, int(body["current_void_points"]))
    if "adventure_state" in body:
        character.adventure_state = body["adventure_state"]

    db.commit()
    return JSONResponse({"status": "ok"})


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
