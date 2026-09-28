"""The combat page and the GM's encounter / NPC routes (combat-design/design.md).

``GET /groups/{group_id}/combat`` is public (D27): the GM, logged in, gets the
tracker; everyone else gets the public view. Everything that changes state is
admin-only and answers JSON.

Write routes follow the house rule for read-modify-write atomicity: this
router prefetches the body (``prefetch_body``), so a handler runs from its
first query to its commit without yielding.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, prefetch_body
from app.models import Character, Encounter, GamingGroup
from app.services import npc_generator as gen
from app.services import npcs
from app.services.auth import is_admin
from app.services.npc_names import fetch_names

router = APIRouter(dependencies=[Depends(prefetch_body)])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gm_id(request: Request) -> Optional[str]:
    viewer = npcs.viewer_id(request)
    return viewer if viewer and is_admin(viewer) else None


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _load(db: Session, group_id: int, request: Request):
    """``(gm_id, group, error_response)`` for an admin-only route."""
    gm = _gm_id(request)
    if gm is None:
        return None, None, _error("Admin access required", 403)
    group = db.query(GamingGroup).filter(GamingGroup.id == group_id).first()
    if group is None:
        return gm, None, _error("No such group", 404)
    return gm, group, None


def _npc(db: Session, group: GamingGroup, npc_id: int) -> Optional[Character]:
    return (
        db.query(Character)
        .filter(Character.id == npc_id, Character.is_npc.is_(True),
                Character.npc_group_id == group.id)
        .first()
    )


def _active(db: Session, group: GamingGroup) -> Optional[Encounter]:
    return npcs.active_encounter(db, group.id)


# ---------------------------------------------------------------------------
# Encounters
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/combat/npc-types")
def npc_type_options(group_id: int, request: Request, db: Session = Depends(get_db)):
    """What the encounter builder offers, and its defaults."""
    _, _, err = _load(db, group_id, request)
    if err:
        return err
    low, high = gen.combat_share_bounds()
    return {
        "types": [{"id": t, "label": label} for t, label in gen.npc_type_options()],
        "combat_share": {"default": gen.default_combat_share(), "min": low, "max": high},
    }


@router.post("/groups/{group_id}/combat/start")
async def start(group_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    body = await _body(request)
    try:
        encounter = npcs.start_encounter(db, group.id, str(body.get("name") or ""),
                                         replace=bool(body.get("replace")))
    except npcs.EncounterConflict as exc:
        return JSONResponse(
            {"error": "fight_in_progress", "message": f"{exc} is still going. End it first?"},
            status_code=409,
        )
    db.commit()
    return {"encounter_id": encounter.id}


@router.post("/groups/{group_id}/combat/end")
def end(group_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter = _active(db, group)
    if encounter is None:
        return _error("No fight in progress", 404)
    npcs.end_encounter(db, encounter)
    db.commit()
    return {"status": "ended"}


@router.post("/groups/{group_id}/combat/generate")
async def generate(group_id: int, request: Request, db: Session = Depends(get_db)):
    gm, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter = _active(db, group)
    if encounter is None:
        return _error("Start a fight first", 409)
    body = await _body(request)
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        return _error("Nothing to generate")
    try:
        plans = [npcs._plan_row(row) for row in rows]
    except ValueError as exc:
        return _error(str(exc))
    # Names are fetched BEFORE any row is written: the network wait must not
    # sit inside the handler's read-modify-write (see database.prefetch_body).
    picked = [n for p in plans for n in p["names"]]
    for plan in plans:
        missing = plan["count"] - len(plan["names"])
        if missing > 0:
            suggested = await fetch_names(missing, gen.is_peasant_type(plan["npc_type"]), avoid=picked)
            plan["names"] = plan["names"] + suggested
            picked += suggested
    try:
        created = npcs.generate(db, group, encounter, gm, plans)
    except ValueError as exc:
        db.rollback()
        return _error(str(exc))
    db.commit()
    return {"created": [{"id": c.id, "name": c.name} for c in created]}


# ---------------------------------------------------------------------------
# NPCs in the fight
# ---------------------------------------------------------------------------

@router.post("/groups/{group_id}/combat/npcs/{npc_id}/status")
async def set_status(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter, npc = _active(db, group), _npc(db, group, npc_id)
    if encounter is None or npc is None:
        return _error("Not found", 404)
    body = await _body(request)
    try:
        npcs.set_status(db, encounter, npc, str(body.get("status") or ""))
    except ValueError as exc:
        return _error(str(exc))
    except LookupError as exc:
        return _error(str(exc), 404)
    db.commit()
    return {"status": body["status"]}


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/remove")
def remove(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter, npc = _active(db, group), _npc(db, group, npc_id)
    if encounter is None or npc is None:
        return _error("Not found", 404)
    try:
        npcs.remove_from_encounter(db, encounter, npc)
    except LookupError as exc:
        return _error(str(exc), 404)
    db.commit()
    return {"status": "removed"}


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/rebuild")
async def rebuild(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    """The GM's per-NPC overrides after generation: earned XP and / or combat share."""
    gm, group, err = _load(db, group_id, request)
    if err:
        return err
    npc = _npc(db, group, npc_id)
    if npc is None:
        return _error("Not found", 404)
    body = await _body(request)
    try:
        earned = body.get("earned_xp")
        earned = None if earned in (None, "") else npcs._int(earned, "earned XP")
        if earned is not None and not 0 <= earned <= 2000:
            raise ValueError("earned XP must be between 0 and 2000")
        share = body.get("combat_share")
        share = None if share in (None, "") else npcs._share(share)
    except ValueError as exc:
        return _error(str(exc))
    npcs.rebuild_npc(db, npc, earned_xp=earned, combat_share=share, author_discord_id=gm)
    encounter = _active(db, group)
    if encounter is not None:
        npcs.touch(encounter)
    db.commit()
    return {"earned_xp": npc.earned_xp, "combat_share": npc.npc_generation["combat_share"]}


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/rename")
async def rename(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    npc = _npc(db, group, npc_id)
    if npc is None:
        return _error("Not found", 404)
    body = await _body(request)
    name = str(body.get("name") or "").strip()[:80]
    if not name:
        return _error("A name is required")
    npc.name = name
    encounter = _active(db, group)
    if encounter is not None:
        npcs.touch(encounter)
    db.commit()
    return {"name": name}


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/combat/roster")
def roster(group_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter = _active(db, group)
    in_fight = {link.character_id for link in encounter.npcs} if encounter else set()
    return {"npcs": [
        {
            "id": c.id, "name": c.name,
            "type": gen.npc_type_label((c.npc_generation or {}).get("npc_type") or npcs._infer_type(c)),
            "earned_xp": c.earned_xp or 0,
            "status": npcs.last_status(db, c),
            "in_fight": c.id in in_fight,
        }
        for c in npcs.roster(db, group.id)
    ]}


@router.post("/groups/{group_id}/combat/roster/{npc_id}/bring-back")
async def bring_back(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    gm, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter, npc = _active(db, group), _npc(db, group, npc_id)
    if npc is None:
        return _error("Not found", 404)
    if encounter is None:
        return _error("Start a fight first", 409)
    body = await _body(request)
    try:
        gained = npcs._int(body.get("gained_xp") or 0, "gained XP")
        npcs.bring_back(db, encounter, npc, gained_xp=gained, author_discord_id=gm)
    except ValueError as exc:
        db.rollback()
        return _error(str(exc))
    db.commit()
    return {"id": npc.id, "earned_xp": npc.earned_xp}


@router.post("/groups/{group_id}/combat/roster/{npc_id}/delete")
def delete(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, group, err = _load(db, group_id, request)
    if err:
        return err
    npc = _npc(db, group, npc_id)
    if npc is None:
        return _error("Not found", 404)
    npcs.delete_npc(db, npc)
    db.commit()
    return {"status": "deleted"}
