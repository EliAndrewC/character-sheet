"""Character API routes — CRUD and HTMX partial endpoints."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.game_data import ADVANTAGES, DISADVANTAGES, SCHOOLS, SKILLS, SCHOOL_KNACKS, Ring
from app.models import Character
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
    form = await request.form()
    form_data = dict(form)
    data = _parse_form_to_dict(form_data)

    character = Character.from_dict(data)
    db.add(character)
    db.commit()
    db.refresh(character)

    return RedirectResponse(f"/characters/{character.id}", status_code=303)


@router.post("/{char_id}")
async def update_character(
    request: Request, char_id: int, db: Session = Depends(get_db)
):
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    form = await request.form()
    form_data = dict(form)
    data = _parse_form_to_dict(form_data)

    # Update fields
    character.name = data["name"]
    character.player_name = data["player_name"]
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
    character.recognition = data["recognition"]
    character.recognition_halved = data["recognition_halved"]
    character.starting_xp = data["starting_xp"]
    character.earned_xp = data["earned_xp"]
    character.notes = data["notes"]

    db.commit()

    return RedirectResponse(f"/characters/{character.id}", status_code=303)


@router.post("/{char_id}/delete")
def delete_character(char_id: int, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == char_id).first()
    if character:
        db.delete(character)
        db.commit()
    return RedirectResponse("/", status_code=303)


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
