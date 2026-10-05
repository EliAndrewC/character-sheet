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
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, prefetch_body
from app.models import Character, Encounter, EncounterAction, GamingGroup
from app.services import combat_actions as actions
from app.services import combat_math as cm
from app.services import combat_view
from app.services import npc_generator as gen
from app.services import npcs
from app.services.auth import is_admin
from app.services.npc_names import fetch_names

router = APIRouter(dependencies=[Depends(prefetch_body)])


def _templates():
    from app.main import templates
    return templates


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


# ---------------------------------------------------------------------------
# NPC actions (design 4.4) - every roll resolved on the server
# ---------------------------------------------------------------------------

def _pc(db: Session, group: GamingGroup, pc_id: Any) -> Optional[Character]:
    """A visible PC of this group (the only things an NPC attacks)."""
    try:
        pc_id = int(pc_id)
    except (TypeError, ValueError):
        return None
    return (
        db.query(Character)
        .filter(Character.id == pc_id, Character.gaming_group_id == group.id,
                Character.is_hidden.is_(False), Character.is_npc.is_not(True))
        .first()
    )


def _opt_int(body: Dict[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
    value = body.get(key)
    if value in (None, ""):
        return default
    return npcs._int(value, key.replace("_", " "))


async def _action_context(group_id: int, npc_id: int, request: Request, db: Session):
    """``(gm, group, encounter, npc, body, error)`` for an NPC action."""
    gm, group, err = _load(db, group_id, request)
    if err:
        return None, None, None, None, None, err
    encounter, npc = _active(db, group), _npc(db, group, npc_id)
    if encounter is None:
        return None, None, None, None, None, _error("No fight in progress", 409)
    if npc is None or npcs.link_for(encounter, npc.id) is None:
        return None, None, None, None, None, _error("That NPC is not in this fight", 404)
    return gm, group, encounter, npc, await _body(request), None


# Error paths return without committing; the request's session is closed
# afterwards, which discards anything flushed. (No explicit rollback: it adds
# nothing here, and in the test harness it would roll back the shared outer
# transaction.)
def _done(db: Session, result: Dict[str, Any]) -> Dict[str, Any]:
    db.commit()
    return result


@router.post("/groups/{group_id}/combat/new-round")
def new_round(group_id: int, request: Request, db: Session = Depends(get_db)):
    gm, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter = _active(db, group)
    if encounter is None:
        return _error("No fight in progress", 409)
    rolled = actions.new_round(db, encounter, gm)
    return _done(db, {"round": encounter.current_round,
                      "action_dice": {str(k): v for k, v in rolled.items()}})


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/initiative")
async def initiative(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    gm, _, encounter, npc, _, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    return _done(db, {"action_dice": actions.roll_initiative(db, encounter, npc, gm)})


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/attack")
async def attack(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    gm, group, encounter, npc, body, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    target = None
    if body.get("target_id") not in (None, ""):
        target = _pc(db, group, body["target_id"])
        if target is None:
            return _error("That target is not a PC in this group", 404)
    try:
        result = actions.attack(
            db, encounter, npc, gm, roll_key=str(body.get("roll_key") or "attack"),
            die=_opt_int(body, "die", -1), target=target, tn=_opt_int(body, "tn"),
            void=_opt_int(body, "void", 0),
        )
    except ValueError as exc:
        return _error(str(exc))
    return _done(db, result)


@router.post("/groups/{group_id}/combat/actions/{action_id}/damage")
async def damage(group_id: int, action_id: int, request: Request, db: Session = Depends(get_db)):
    gm, group, err = _load(db, group_id, request)
    if err:
        return err
    encounter = _active(db, group)
    action = db.get(EncounterAction, action_id)
    if encounter is None or action is None or action.encounter_id != encounter.id:
        return _error("Not found", 404)
    body = await _body(request)
    try:
        result = actions.damage(
            db, encounter, action, gm, parry=str(body.get("parry") or "none"),
            parry_skill=_opt_int(body, "parry_skill"), weapon=str(body.get("weapon") or "katana"),
        )
    except ValueError as exc:
        return _error(str(exc))
    return _done(db, result)


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/parry")
async def parry(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    gm, group, encounter, npc, body, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    attacker = None
    if body.get("attacker_id") not in (None, ""):
        attacker = _pc(db, group, body["attacker_id"])
    dice = body.get("dice")
    if not isinstance(dice, list):
        dice = [body.get("die")]
    try:
        attack_total = _opt_int(body, "attack_total")
        if attack_total is None:
            raise ValueError("enter the attack roll to parry")
        result = actions.parry(
            db, encounter, npc, gm, dice=dice, attack_total=attack_total,
            void=_opt_int(body, "void", 0), predeclared=bool(body.get("predeclared")),
            attacker=attacker,
        )
    except ValueError as exc:
        return _error(str(exc))
    return _done(db, result)


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/other")
async def other_action(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, _, encounter, npc, body, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    try:
        result = actions.other(db, encounter, npc, die=_opt_int(body, "die", -1),
                               label=str(body.get("label") or ""))
    except ValueError as exc:
        return _error(str(exc))
    return _done(db, result)


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/take-damage")
async def take_damage(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    gm, _, encounter, npc, body, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    try:
        result = actions.take_damage(db, encounter, npc, gm, amount=_opt_int(body, "amount", 0),
                                     void=_opt_int(body, "void", 0))
    except ValueError as exc:
        return _error(str(exc))
    return _done(db, result)


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/take-serious-wound")
async def take_serious_wound(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, _, encounter, npc, _, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    return _done(db, actions.take_serious_wound(db, encounter, npc))


@router.post("/groups/{group_id}/combat/npcs/{npc_id}/tracking")
async def set_tracking(group_id: int, npc_id: int, request: Request, db: Session = Depends(get_db)):
    _, _, encounter, npc, body, err = await _action_context(group_id, npc_id, request, db)
    if err:
        return err
    try:
        result = actions.set_tracking(
            db, encounter, npc, light=_opt_int(body, "light"),
            serious=_opt_int(body, "serious"), void=_opt_int(body, "void"),
        )
    except ValueError as exc:
        return _error(str(exc))
    return _done(db, result)


# ---------------------------------------------------------------------------
# Pages (design 4.5)
# ---------------------------------------------------------------------------

def _group_or_404(db: Session, group_id: int) -> Optional[GamingGroup]:
    return db.query(GamingGroup).filter(GamingGroup.id == group_id).first()


@router.get("/groups/{group_id}/combat", response_class=HTMLResponse)
def combat_page(group_id: int, request: Request, view: Optional[str] = None,
                db: Session = Depends(get_db)):
    """Public (D27). The GM, logged in, gets the tracker; everyone else -
    logged in or not - gets the same public view.

    ``?view=player`` gives the GM the public view in THIS tab only (the URL
    is the toggle, so the GM's other tabs keep the tracker): a tab to share
    on screen. It is rendered from the public state, so nothing GM-only
    reaches it, and it polls ``/state?view=player``."""
    group = _group_or_404(db, group_id)
    if group is None:
        return HTMLResponse("Group not found", status_code=404)
    is_gm = _gm_id(request) is not None
    player_view = view == "player"
    gm = is_gm and not player_view
    state = combat_view.gm_state(db, group) if gm else combat_view.public_state(db, group)
    low, high = gen.combat_share_bounds()
    context = {
        "group": group, "gm": gm, "state": state,
        "gm_in_player_view": is_gm and player_view,
        "npc_types": [{"id": t, "label": label} for t, label in gen.npc_type_options()] if gm else [],
        "share": {"default": round(100 * gen.default_combat_share()), "min": round(100 * low), "max": round(100 * high)},
        "weapons": list(cm.WEAPONS),
    }
    return _templates().TemplateResponse(request=request, name="group_combat.html", context=context)


@router.get("/groups/{group_id}/combat/state")
def combat_state(group_id: int, request: Request, view: Optional[str] = None,
                 db: Session = Depends(get_db)):
    """What the page polls. The GM's full state, or the public allow-list
    (always, for a ``?view=player`` tab)."""
    group = _group_or_404(db, group_id)
    if group is None:
        return _error("No such group", 404)
    if _gm_id(request) is not None and view != "player":
        return combat_view.gm_state(db, group)
    return combat_view.public_state(db, group)


@router.get("/groups/{group_id}/combat/rolls", response_class=HTMLResponse)
def combat_rolls(group_id: int, request: Request, encounter: Optional[int] = None,
                 db: Session = Depends(get_db)):
    """The GM's combat rolls view (D21): every roll made during one fight,
    PCs' and NPCs', in order."""
    if _gm_id(request) is None:
        return HTMLResponse("Admin access required", status_code=403)
    group = _group_or_404(db, group_id)
    if group is None:
        return HTMLResponse("Group not found", status_code=404)
    fights = (
        db.query(Encounter).filter(Encounter.gaming_group_id == group.id)
        .order_by(Encounter.id.desc()).all()
    )
    chosen = next((f for f in fights if f.id == encounter), fights[0] if fights else None)
    rows = combat_view.combat_rolls(db, group, chosen) if chosen else []
    return _templates().TemplateResponse(
        request=request, name="group_combat_rolls.html",
        context={"group": group, "fights": fights, "chosen": chosen, "rows": rows},
    )
