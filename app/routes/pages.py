"""Page routes — serve full HTML pages via Jinja2 templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.game_data import (
    ADVANTAGES,
    DISADVANTAGES,
    SCHOOLS,
    SCHOOLS_BY_CATEGORY,
    SKILLS,
    SCHOOL_KNACKS,
    SPELLS_BY_ELEMENT,
    Ring,
)
from app.models import Character
from app.services.xp import calculate_total_xp, validate_character

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    characters = db.query(Character).order_by(Character.updated_at.desc()).all()
    return _templates().TemplateResponse(
        request=request,
        name="index.html",
        context={"characters": characters},
    )


@router.get("/characters/new", response_class=HTMLResponse)
def new_character(request: Request):
    return _templates().TemplateResponse(
        request=request,
        name="character/create.html",
        context={
            "schools": SCHOOLS,
            "schools_by_category": SCHOOLS_BY_CATEGORY,
            "rings": [r.value for r in Ring],
            "skills": SKILLS,
            "advantages": ADVANTAGES,
            "disadvantages": DISADVANTAGES,
            "school_knacks": SCHOOL_KNACKS,
        },
    )


@router.get("/characters/{char_id}", response_class=HTMLResponse)
def view_character(request: Request, char_id: int, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    char_dict = character.to_dict()
    xp_breakdown = calculate_total_xp(char_dict)
    errors = validate_character(char_dict)
    school = SCHOOLS.get(character.school)

    # Build the knack list for this character's school
    char_knacks = {}
    if school:
        for knack_id in school.school_knacks:
            knack_data = SCHOOL_KNACKS.get(knack_id)
            rank = character.knacks.get(knack_id, 1) if character.knacks else 1
            char_knacks[knack_id] = {"data": knack_data, "rank": rank}

    # Dan = lowest school knack
    knack_ranks = [char_knacks[k]["rank"] for k in char_knacks] if char_knacks else [0]
    dan = min(knack_ranks) if knack_ranks else 0

    return _templates().TemplateResponse(
        request=request,
        name="character/sheet.html",
        context={
            "character": character,
            "char_dict": char_dict,
            "school": school,
            "xp": xp_breakdown,
            "errors": errors,
            "skills": SKILLS,
            "advantages": ADVANTAGES,
            "disadvantages": DISADVANTAGES,
            "school_knacks": SCHOOL_KNACKS,
            "char_knacks": char_knacks,
            "dan": dan,
            "spells_by_element": SPELLS_BY_ELEMENT,
        },
    )


@router.get("/characters/{char_id}/edit", response_class=HTMLResponse)
def edit_character(request: Request, char_id: int, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    char_dict = character.to_dict()
    xp_breakdown = calculate_total_xp(char_dict)
    school = SCHOOLS.get(character.school)

    # Build knacks dict for the school_info partial
    knacks = {}
    if school:
        knacks = {kid: SCHOOL_KNACKS.get(kid) for kid in school.school_knacks}

    return _templates().TemplateResponse(
        request=request,
        name="character/edit.html",
        context={
            "character": character,
            "char_dict": char_dict,
            "school": school,
            "xp": xp_breakdown,
            "schools": SCHOOLS,
            "schools_by_category": SCHOOLS_BY_CATEGORY,
            "rings": [r.value for r in Ring],
            "skills": SKILLS,
            "advantages": ADVANTAGES,
            "disadvantages": DISADVANTAGES,
            "school_knacks": SCHOOL_KNACKS,
            "knacks": knacks,
        },
    )
