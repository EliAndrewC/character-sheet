"""Page routes — serve full HTML pages via Jinja2 templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES,
    ADVANTAGE_DETAIL_FIELDS,
    EXCLUSIVE_PAIRS,
    SCHOOLS,
    SCHOOLS_BY_CATEGORY,
    SCHOOL_RING_OPTIONS,
    SCHOOL_TECHNIQUE_BONUSES,
    SKILLS,
    SCHOOL_KNACKS,
    SPELLS_BY_ELEMENT,
    Ring,
)
from app.models import Character, CharacterVersion, GamingGroup, User as UserModel
from app.services.auth import can_view_drafts, get_admin_ids, is_admin, can_edit_character
from app.services.rolls import compute_skill_roll
from app.services.status import compute_effective_status, compute_party_effects
from app.services.xp import calculate_total_xp, calculate_xp_breakdown, validate_character

router = APIRouter()


def _templates():
    from app.main import templates
    return templates


@router.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return _templates().TemplateResponse(request=request, name="terms.html")


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return _templates().TemplateResponse(request=request, name="privacy.html")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    user_id = user["discord_id"] if user else None

    all_characters = db.query(Character).order_by(Character.updated_at.desc()).all()
    all_groups = db.query(GamingGroup).order_by(GamingGroup.name).all()

    # Cluster characters by gaming group; omit empty groups; trailing Unassigned
    grouped: list = []
    for group in all_groups:
        chars_in_group = [c for c in all_characters if c.gaming_group_id == group.id]
        if chars_in_group:
            grouped.append((group.name, chars_in_group))
    unassigned = [c for c in all_characters if c.gaming_group_id is None]
    if unassigned:
        grouped.append(("Unassigned", unassigned))

    # Build owner display name lookup
    owner_ids = {c.owner_discord_id for c in all_characters if c.owner_discord_id}
    owners = db.query(UserModel).filter(UserModel.discord_id.in_(owner_ids)).all() if owner_ids else []
    owner_names = {u.discord_id: u.display_name or u.discord_name for u in owners}

    return _templates().TemplateResponse(
        request=request,
        name="index.html",
        context={
            "characters": all_characters,
            "grouped": grouped,
            "owner_names": owner_names,
        },
    )


@router.get("/characters/new", response_class=HTMLResponse)
def new_character(request: Request):
    """Redirect to POST — new character creation is done via POST /characters."""
    return RedirectResponse("/", status_code=303)


@router.get("/characters/{char_id}", response_class=HTMLResponse)
def view_character(request: Request, char_id: int, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    user = getattr(request.state, "user", None)
    user_id = user["discord_id"] if user else None

    # Determine if viewer can edit
    from app.services.auth import can_view_drafts
    from app.models import User as UserModel
    owner = db.query(UserModel).filter(UserModel.discord_id == character.owner_discord_id).first()
    owner_granted = owner.granted_account_ids or [] if owner else []
    viewer_can_edit = can_view_drafts(user_id, character.owner_discord_id, owner_granted)

    # Everyone sees the current draft state
    char_dict = character.to_dict()

    xp_breakdown = calculate_xp_breakdown(char_dict)
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

    # Load party members in the same gaming group, if any.
    party_members_data: list = []
    if character.gaming_group_id:
        party_chars = (
            db.query(Character)
            .filter(
                Character.gaming_group_id == character.gaming_group_id,
                Character.id != char_id,
            )
            .all()
        )
        for p in party_chars:
            party_members_data.append({
                "name": p.name,
                "advantages": p.advantages or [],
                "disadvantages": p.disadvantages or [],
                "campaign_advantages": p.campaign_advantages or [],
                "campaign_disadvantages": p.campaign_disadvantages or [],
            })

    effective = compute_effective_status(char_dict, party_members=party_members_data)
    party_effects = compute_party_effects(char_dict, character.name, party_members_data)
    all_groups = db.query(GamingGroup).order_by(GamingGroup.name).all()

    # Compute roll info for each skill
    skill_rolls = {}
    for sid in (char_dict.get("skills") or {}):
        roll = compute_skill_roll(sid, char_dict)
        if roll.rolled > 0:
            skill_rolls[sid] = roll

    # Compute per-adventure abilities
    per_adventure = []
    advantages = character.advantages or []
    disadvantages = character.disadvantages or []

    # 3rd Dan free raises
    tech_bonuses = SCHOOL_TECHNIQUE_BONUSES.get(character.school, {})
    if dan >= 3 and tech_bonuses.get("third_dan"):
        t3 = tech_bonuses["third_dan"]
        source_skill = t3["source_skill"]
        source_rank = (character.skills or {}).get(source_skill, 0)
        if source_rank > 0:
            skill_name = SKILLS[source_skill].name if source_skill in SKILLS else source_skill
            per_adventure.append({
                "id": "adventure_raises",
                "name": f"3rd Dan Free Raises ({skill_name})",
                "type": "counter",
                "max": 2 * source_rank,
            })

    # Lucky / Unlucky
    if "lucky" in advantages:
        per_adventure.append({"id": "lucky_used", "name": "Lucky (re-roll)", "type": "toggle"})
    if "unlucky" in disadvantages:
        per_adventure.append({"id": "unlucky_used", "name": "Unlucky (GM penalty)", "type": "toggle"})

    # Spendable knacks: conviction, otherworldliness, worldliness
    for knack_id in ("conviction", "otherworldliness", "worldliness"):
        if knack_id in char_knacks:
            knack_rank = char_knacks[knack_id]["rank"]
            knack_name = char_knacks[knack_id]["data"].name
            per_adventure.append({
                "id": knack_id,
                "name": knack_name,
                "type": "counter",
                "max": knack_rank,
            })

    # Compute void points max
    ring_vals = [char_dict["rings"].get(r, 2) for r in ("Air", "Fire", "Earth", "Water", "Void")]
    void_max = min(ring_vals)

    # Get version history
    versions = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.character_id == char_id)
        .order_by(CharacterVersion.version_number.desc())
        .all()
    )

    return _templates().TemplateResponse(
        request=request,
        name="character/sheet.html",
        context={
            "character": character,
            "char_dict": char_dict,
            "school": school,
            "xp_breakdown": xp_breakdown,
            "errors": errors,
            "skills": SKILLS,
            "advantages": ADVANTAGES,
            "disadvantages": DISADVANTAGES,
            "school_knacks": SCHOOL_KNACKS,
            "char_knacks": char_knacks,
            "dan": dan,
            "spells_by_element": SPELLS_BY_ELEMENT,
            "effective": effective,
            "skill_rolls": skill_rolls,
            "viewer_can_edit": viewer_can_edit,
            "versions": versions,
            "owner_display_name": (owner.display_name or owner.discord_name) if owner else character.player_name,
            "advantage_detail_fields": ADVANTAGE_DETAIL_FIELDS,
            "advantage_details": character.advantage_details or {},
            "player_names": {u.discord_id: u.display_name or u.discord_name
                             for u in db.query(UserModel).all()},
            "per_adventure": per_adventure,
            "void_max": void_max,
            "adventure_state": character.adventure_state or {},
            "party_effects": party_effects,
            "all_groups": all_groups,
        },
    )


@router.get("/characters/{char_id}/edit", response_class=HTMLResponse)
def edit_character(request: Request, char_id: int, db: Session = Depends(get_db)):
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

    char_dict = character.to_dict()
    xp_breakdown = calculate_total_xp(char_dict)
    school = SCHOOLS.get(character.school)

    # Build knacks dict for the school_info partial
    knacks = {}
    if school:
        knacks = {kid: SCHOOL_KNACKS.get(kid) for kid in school.school_knacks}

    viewer_is_admin = is_admin(user["discord_id"])
    all_players = db.query(UserModel).order_by(UserModel.display_name).all()
    all_groups = db.query(GamingGroup).order_by(GamingGroup.name).all()

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
            "technique_bonuses": SCHOOL_TECHNIQUE_BONUSES,
            "campaign_advantages": CAMPAIGN_ADVANTAGES,
            "campaign_disadvantages": CAMPAIGN_DISADVANTAGES,
            "school_ring_options": SCHOOL_RING_OPTIONS,
            "viewer_is_admin": viewer_is_admin,
            "all_players": all_players,
            "all_groups": all_groups,
            "exclusive_pairs": EXCLUSIVE_PAIRS,
            "advantage_detail_fields": ADVANTAGE_DETAIL_FIELDS,
            "is_first_version": not character.is_published,
        },
    )


# ---------------------------------------------------------------------------
# Profile & Account Access
# ---------------------------------------------------------------------------


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    user_obj = db.query(UserModel).filter(
        UserModel.discord_id == user["discord_id"]
    ).first()

    # All other registered users (for grant/revoke UI)
    all_users = db.query(UserModel).order_by(UserModel.discord_name).all()
    other_users = [u for u in all_users if u.discord_id != user["discord_id"]]

    admin_ids = get_admin_ids()
    granted_ids = set(user_obj.granted_account_ids or [])

    return _templates().TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "user_obj": user_obj,
            "other_users": other_users,
            "admin_ids": admin_ids,
            "granted_ids": granted_ids,
        },
    )


@router.post("/profile", response_class=HTMLResponse)
async def update_profile(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    user_obj = db.query(UserModel).filter(
        UserModel.discord_id == user["discord_id"]
    ).first()

    form = await request.form()
    new_name = form.get("display_name", "").strip()
    if new_name:
        user_obj.display_name = new_name

    # Parse granted account checkboxes
    admin_ids = get_admin_ids()
    all_users = db.query(UserModel).filter(
        UserModel.discord_id != user["discord_id"]
    ).all()
    granted = []
    for u in all_users:
        # Admins always have access — don't store them in the list
        if u.discord_id in admin_ids:
            continue
        if form.get(f"grant_{u.discord_id}") == "on":
            granted.append(u.discord_id)
    user_obj.granted_account_ids = granted

    db.commit()

    return RedirectResponse("/profile", status_code=303)


# ---------------------------------------------------------------------------
# Admin: Manage Gaming Groups
# ---------------------------------------------------------------------------


def _require_admin(request: Request):
    """Return None if request is from an admin, else an HTMLResponse to return."""
    user = getattr(request.state, "user", None)
    if not user or not is_admin(user["discord_id"]):
        return HTMLResponse("Admin access required", status_code=403)
    return None


@router.get("/admin/groups", response_class=HTMLResponse)
def admin_groups(request: Request, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    groups = db.query(GamingGroup).order_by(GamingGroup.name).all()
    counts = {
        g.id: db.query(Character).filter(Character.gaming_group_id == g.id).count()
        for g in groups
    }
    return _templates().TemplateResponse(
        request=request,
        name="admin/groups.html",
        context={"groups": groups, "counts": counts},
    )


@router.post("/admin/groups/new")
async def admin_groups_create(request: Request, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        return RedirectResponse("/admin/groups", status_code=303)
    existing = db.query(GamingGroup).filter(GamingGroup.name == name).first()
    if existing is None:
        db.add(GamingGroup(name=name))
        db.commit()
    return RedirectResponse("/admin/groups", status_code=303)


@router.post("/admin/groups/{group_id}/rename")
async def admin_groups_rename(request: Request, group_id: int, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    form = await request.form()
    new_name = (form.get("name") or "").strip()
    group = db.query(GamingGroup).filter(GamingGroup.id == group_id).first()
    if group and new_name:
        # Avoid duplicate-name collisions
        clash = db.query(GamingGroup).filter(
            GamingGroup.name == new_name, GamingGroup.id != group_id
        ).first()
        if clash is None:
            group.name = new_name
            db.commit()
    return RedirectResponse("/admin/groups", status_code=303)


@router.post("/admin/groups/{group_id}/delete")
async def admin_groups_delete(request: Request, group_id: int, db: Session = Depends(get_db)):
    deny = _require_admin(request)
    if deny is not None:
        return deny
    group = db.query(GamingGroup).filter(GamingGroup.id == group_id).first()
    if group:
        # SQLite ON DELETE SET NULL requires PRAGMA foreign_keys=ON, which we
        # don't enable. Manually unassign characters first to be safe.
        db.query(Character).filter(
            Character.gaming_group_id == group_id
        ).update({Character.gaming_group_id: None}, synchronize_session=False)
        db.delete(group)
        db.commit()
    return RedirectResponse("/admin/groups", status_code=303)
