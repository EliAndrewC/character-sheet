"""What the combat page shows: the GM's tracker and the public view (design 4.5).

``public_state`` is built field by field from an allow-list and never from a
model's ``to_dict``: players see each NPC's name, wounds, whether it is down,
the actions it took this round (kind, target and the roll's TOTAL - D29) and
how many actions it took last round (D22), plus every visible PC's wounds and
remaining action dice (D32). Never an NPC's dice, void, phases, remaining
actions, stats, or how a total was reached. ``tests/test_combat_view.py``
pins the exact key sets.

Both payloads carry ``rev``, which moves whenever anything either view shows
could have changed (the encounter's own ``rev`` plus every combatant's
``tracking_rev``), so the page's poll redraws only when something happened.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Character, Encounter, EncounterAction, GamingGroup
from app.services import npc_generator as gen
from app.services import npcs
from app.services.combat_actions import tn_to_be_hit
from app.services.dice import is_impaired
from app.services.per_adventure import per_adventure_abilities, remaining
from app.services.void_spend import void_limits, void_pools


def visible_pcs(db: Session, group: GamingGroup) -> List[Character]:
    """Every visible PC in the group is in the fight (D30)."""
    return (
        db.query(Character)
        .filter(Character.gaming_group_id == group.id, Character.is_hidden.is_(False),
                Character.is_npc.is_not(True))
        .order_by(Character.name)
        .all()
    )


def _actions(db: Session, encounter: Optional[Encounter]) -> List[EncounterAction]:
    if encounter is None:
        return []
    return (
        db.query(EncounterAction)
        .filter(EncounterAction.encounter_id == encounter.id)
        .order_by(EncounterAction.id)
        .all()
    )


def _rev(encounter: Optional[Encounter], people: List[Character]) -> str:
    parts = [f"{encounter.id}.{encounter.rev}" if encounter else "none"]
    parts += [f"{c.id}.{c.tracking_rev or 0}" for c in people]
    return "-".join(parts)


def _dice(character: Character, *, spent: bool) -> List[Dict[str, Any]]:
    out = []
    for d in character.action_dice or []:
        if d.get("spent") and not spent:
            continue
        entry = {"value": d.get("value")}
        if spent:  # the GM's view: the sheet's die icon and its tooltip
            entry["spent"] = bool(d.get("spent"))
            entry["spent_by"] = d.get("spent_by") or ""
            entry["athletics_only"] = bool(d.get("athletics_only"))
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def _public_action(action: EncounterAction, names: Dict[int, str]) -> Dict[str, Any]:
    detail = action.detail or {}
    return {
        "kind": action.kind,
        "label": action.label,
        "target": names.get(action.target_character_id) if action.target_character_id else None,
        "total": action.total,
        "outcome": detail.get("outcome"),
        "damage": detail.get("damage"),
    }


def public_state(db: Session, group: GamingGroup) -> Dict[str, Any]:
    encounter = npcs.active_encounter(db, group.id)
    pcs = visible_pcs(db, group)
    links = list(encounter.npcs) if encounter else []
    names = {c.id: c.name for c in pcs}
    names.update({link.character_id: link.character.name for link in links})
    actions = _actions(db, encounter)
    current = encounter.current_round if encounter else 0
    out_npcs = []
    for link in links:
        npc = link.character
        mine = [a for a in actions if a.character_id == npc.id]
        # Players learn an NPC's TN once someone has attacked it: it has
        # wounds from this fight (a returning NPC is healed) or has parried.
        attacked = (npc.current_light_wounds or 0) + (npc.current_serious_wounds or 0) > 0 \
            or any(a.kind == "parry" for a in mine)
        out_npcs.append({
            "id": npc.id,
            "name": npc.name,
            "light_wounds": npc.current_light_wounds or 0,
            "serious_wounds": npc.current_serious_wounds or 0,
            "down": link.status != "fighting",
            "actions_this_round": [_public_action(a, names) for a in mine if a.round == current],
            "actions_last_round": (
                sum(1 for a in mine if a.round == current - 1) if current >= 2 else None
            ),
            "tn_to_be_hit": tn_to_be_hit(npc) if attacked else None,
        })
    return {
        "rev": _rev(encounter, pcs + [link.character for link in links]),
        "group": {"id": group.id, "name": group.name},
        "encounter": {"name": encounter.name, "round": current} if encounter else None,
        "pcs": [
            {
                "id": pc.id,
                "name": pc.name,
                "light_wounds": pc.current_light_wounds or 0,
                "serious_wounds": pc.current_serious_wounds or 0,
                "action_dice": _dice(pc, spent=False),
            }
            for pc in pcs
        ],
        "npcs": out_npcs,
    }


# ---------------------------------------------------------------------------
# GM
# ---------------------------------------------------------------------------

def _combatant(character: Character) -> Dict[str, Any]:
    data = character.to_dict()
    limits = void_limits(data)
    pools = void_pools(character, limits)
    return {
        "id": character.id,
        "name": character.name,
        "light_wounds": character.current_light_wounds or 0,
        "serious_wounds": character.current_serious_wounds or 0,
        "earth": character.ring_earth,
        "max_serious_wounds": 2 * (character.ring_earth or 2),
        "impaired": is_impaired(data),
        "void": pools["regular"],
        "temp_void": pools["temp"],
        "worldliness_void": pools["worldliness"],
        "void_max": limits["void_max"],
        "tn_to_be_hit": tn_to_be_hit(character),
        "parry": character.parry or 1,
        "action_dice": _dice(character, spent=True),
        "bonuses": [remaining(character, a) for a in per_adventure_abilities(character)],
        "sheet_url": f"/characters/{character.id}",
    }


def _gm_action(action: EncounterAction, names: Dict[int, str]) -> Dict[str, Any]:
    return {
        "id": action.id,
        "round": action.round,
        "npc_id": action.character_id,
        "npc": names.get(action.character_id),
        "kind": action.kind,
        "label": action.label,
        "target_id": action.target_character_id,
        "target": names.get(action.target_character_id) if action.target_character_id else None,
        "total": action.total,
        "detail": action.detail or {},
    }


def gm_state(db: Session, group: GamingGroup) -> Dict[str, Any]:
    encounter = npcs.active_encounter(db, group.id)
    pcs = visible_pcs(db, group)
    links = list(encounter.npcs) if encounter else []
    names = {c.id: c.name for c in pcs}
    names.update({link.character_id: link.character.name for link in links})
    out_npcs = []
    for link in links:
        npc = link.character
        g = npc.npc_generation or {}
        out_npcs.append({
            **_combatant(npc),
            "status": link.status,
            "type": gen.npc_type_label(g.get("npc_type") or npcs._infer_type(npc)),
            "earned_xp": npc.earned_xp or 0,
            "combat_share": g.get("combat_share"),
        })
    return {
        "rev": _rev(encounter, pcs + [link.character for link in links]),
        "gm": True,
        "group": {"id": group.id, "name": group.name},
        "encounter": (
            {"id": encounter.id, "name": encounter.name, "round": encounter.current_round}
            if encounter else None
        ),
        "pcs": [_combatant(pc) for pc in pcs],
        "npcs": out_npcs,
        "actions": [_gm_action(a, names) for a in _actions(db, encounter)],
    }


# ---------------------------------------------------------------------------
# Combat rolls view (D21)
# ---------------------------------------------------------------------------

def combat_rolls(db: Session, group: GamingGroup, encounter: Encounter) -> List[Dict[str, Any]]:
    """Every recorded roll made during ``encounter`` by the group's PCs or the
    fight's NPCs, oldest first, for the GM to eyeball how the dice went."""
    from app.models import EncounterNpc, RollHistory

    npc_ids = {
        cid for (cid,) in db.query(EncounterNpc.character_id)
        .filter(EncounterNpc.encounter_id == encounter.id)
    }
    pc_ids = {c.id for c in db.query(Character.id).filter(Character.gaming_group_id == group.id)}
    ids = npc_ids | pc_ids
    if not ids:
        return []
    # Compare through SQLite's datetime(): created_at is stored as
    # "YYYY-MM-DD HH:MM:SS" while a bound Python datetime carries
    # ".ffffff", and as strings the shorter one sorts first - so a roll in
    # the same second as the fight started would otherwise fall outside it.
    created = func.datetime(RollHistory.created_at)
    q = db.query(RollHistory).filter(
        RollHistory.character_id.in_(ids), created >= func.datetime(encounter.started_at),
    )
    if encounter.ended_at is not None:
        q = q.filter(created <= func.datetime(encounter.ended_at))
    names = {c.id: c.name for c in db.query(Character).filter(Character.id.in_(ids))}
    out = []
    for row in q.order_by(RollHistory.created_at, RollHistory.id):
        payload = row.payload or {}
        out.append({
            "id": row.id,
            "at": row.created_at,
            "character": names.get(row.character_id, "?"),
            "is_npc": row.character_id in npc_ids,
            "title": payload.get("title") or row.roll_key,
            "total": payload.get("total"),
            "kept": [sum(c.get("parts") or [0]) for c in payload.get("kept") or []],
            "dropped": [sum(c.get("parts") or [0]) for c in payload.get("dropped") or []],
            "show_total": payload.get("show_total", True),
        })
    return out
