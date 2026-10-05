"""The fight log for rolls made with the sheet's own roller.

The combat page drives an NPC through the same die menus and roll modals as a
character sheet (the NPC roll overlay), so its rolls arrive through the
ordinary roll routes. These hooks turn the ones a fight cares about into
``EncounterAction`` rows - the GM's fight log (players see none of it, D34;
they see spent dice):

* an attack (any live roll whose answer carries an ``attack`` block), with
  its target when the GM picked a PC in the fight, and later its damage;
* a parry, with its outcome when the attack total it parried was given;
* a feint.

A die marked spent by hand is not an action of its own: spent dice are
public and the view shows them (spending, unspending and spending it again
is still one die). ``note_dice_replaced`` keeps each round's spent count.

Only for an NPC in its group's active fight, and only live rolls.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import Character, Encounter, EncounterAction, GamingGroup
from app.services import npcs

PARRY_KEYS = ("parry", "athletics:parry")


def npc_encounter(db: Session, character: Character) -> Optional[Encounter]:
    """The active fight this NPC is in, or None."""
    if not character.is_npc or not character.npc_group_id:
        return None
    encounter = npcs.active_encounter(db, character.npc_group_id)
    if encounter is None or npcs.link_for(encounter, character.id) is None:
        return None
    return encounter


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _target(db: Session, encounter: Encounter, raw: Any) -> Optional[int]:
    """A PC id the public view may name: visible in the fight's group."""
    from app.services.combat_view import visible_pcs

    target = _int(raw)
    group = db.get(GamingGroup, encounter.gaming_group_id)
    return target if target in {pc.id for pc in visible_pcs(db, group)} else None


def _log(db: Session, encounter: Encounter, character: Character, kind: str, label: str, *,
         total: Optional[int] = None, target: Optional[int] = None,
         detail: Optional[Dict[str, Any]] = None) -> None:
    db.add(EncounterAction(
        encounter_id=encounter.id, character_id=character.id, round=encounter.current_round,
        kind=kind, label=label, total=total, target_character_id=target,
        roll_history_id=None, detail=detail or {},
    ))
    npcs.touch(encounter)
    db.flush()


def record_roll(db: Session, character: Character, body: Dict[str, Any], result: Dict[str, Any]) -> None:
    """After ``POST /characters/{id}/roll``."""
    encounter = npc_encounter(db, character)
    if encounter is None or result.get("mode") != "live":
        return
    roll_key = str(body.get("roll_key") or "")
    label = (result.get("formula") or {}).get("label") or roll_key
    total = result.get("total")
    detail: Dict[str, Any] = {"session_id": result.get("session_id"), "roll_key": roll_key}
    attack = result.get("attack")
    if attack:
        detail.update(tn=attack.get("tn"), effective_tn=attack.get("effective_tn"),
                      outcome="hit" if attack.get("hit") else "missed")
        _log(db, encounter, character, "attack", label, total=total,
             target=_target(db, encounter, body.get("target_id")), detail=detail)
    elif roll_key in PARRY_KEYS:
        tn = _int(body.get("tn"))
        if tn is not None:
            detail.update(tn=tn, outcome="parried" if (total or 0) >= tn else "failed")
        _log(db, encounter, character, "parry", label, total=total,
             target=_target(db, encounter, body.get("target_id")), detail=detail)
    elif result.get("feint"):
        feint = result["feint"]
        detail.update(tn=feint.get("tn"), outcome="succeeded" if feint.get("success") else "failed")
        _log(db, encounter, character, "feint", label, total=total, detail=detail)


def record_act(db: Session, character: Character, session_id: str, action: str,
               result: Dict[str, Any]) -> None:
    """After ``POST .../roll/{session}/act``. An attack's damage joins its
    entry; any other action that rescored the roll (a raise, a reroll)
    moves the entry's total, and its outcome with it."""
    encounter = npc_encounter(db, character)
    if encounter is None:
        return
    entry = next((e for e in db.query(EncounterAction).filter(
        EncounterAction.encounter_id == encounter.id,
        EncounterAction.character_id == character.id)
        if (e.detail or {}).get("session_id") == session_id), None)
    if entry is None:
        return
    detail = dict(entry.detail)
    if action == "damage":
        if not result.get("damage"):
            return
        detail["damage"] = result["damage"].get("total")
    elif result.get("total") is not None:
        entry.total = result["total"]
        if result.get("attack"):
            detail["outcome"] = "hit" if result["attack"].get("hit") else "missed"
        elif entry.kind == "parry" and detail.get("tn") is not None:
            detail["outcome"] = "parried" if entry.total >= detail["tn"] else "failed"
    else:
        return
    entry.detail = detail
    npcs.touch(encounter)
    db.flush()


def note_dice_replaced(db: Session, character: Character) -> None:
    """Before an NPC's action dice are replaced (initiative, a new round):
    note how many it spent this round. Spent dice are public; what the NPC
    spent in earlier rounds is how many actions players know it has."""
    encounter = npc_encounter(db, character)
    if encounter is None:
        return
    link = npcs.link_for(encounter, character.id)
    key = str(encounter.current_round or 0)
    spent = sum(1 for d in character.action_dice or [] if d.get("spent"))
    counts = dict(link.spent_by_round or {})
    counts[key] = max(spent, counts.get(key, 0))
    link.spent_by_round = counts
    db.flush()


def known_actions(link: Any, current_round: int) -> int:
    """The most dice the NPC spent in any earlier round of this fight."""
    return max((n for r, n in (link.spent_by_round or {}).items() if int(r) < current_round), default=0)
