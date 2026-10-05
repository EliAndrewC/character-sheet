"""The GM's NPC round and wound bookkeeping on the server (design 4.4, D7).

What is left here after the combat page moved its NPC rolls onto the
sheet's own roller (the NPC roll overlay, ``routes/combat.py npc_roller``;
the fight log is ``fight_log``): a new round's initiative for every NPC,
one NPC's initiative, and the GM's manual corrections of wounds and void.
Formulas come from ``build_all_roll_formulas`` and rounds from
``tracking.start_combat_round``.

What a PC does is never written here (D19): the PC's wounds are the
player's to enter.

Each function mutates and flushes; the route commits once.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Character, Encounter, RollHistory
from app.services import fight_log, npcs
from app.services.roll_engine import execute_initiative, impaired_now
from app.services.tracking import start_combat_round



class ActionError(ValueError):
    """A request the rules or the NPC's state cannot satisfy. Nothing changed."""


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

def tn_to_be_hit(character: Character) -> int:
    return 5 + 5 * (character.parry or 1)


def _record(
    db: Session, npc: Character, roll_key: str, payload: Dict[str, Any], gm: str,
    *, tn: Optional[int] = None, die: Optional[Dict[str, Any]] = None,
) -> RollHistory:
    """NPC rolls are always recorded (D21), whichever GM made them."""
    row = RollHistory(
        character_id=npc.id, roll_key=roll_key, actor_discord_id=gm,
        is_owner_roll=gm == npc.owner_discord_id,
        impaired_at_roll=impaired_now(npc.to_dict()),
        tn=tn, payload=payload, action_die_spent=die,
    )
    db.add(row)
    db.flush()
    return row


def _down_prompt(encounter: Encounter, npc: Character) -> bool:
    """At 2 x Earth serious wounds the GM says unconscious or dead (D9)."""
    link = npcs.link_for(encounter, npc.id)
    down = (npc.current_serious_wounds or 0) >= 2 * (npc.ring_earth or 2)
    return bool(down and link is not None and link.status == "fighting")


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------

def roll_initiative(db: Session, encounter: Encounter, npc: Character, gm: str,
                    rng: Optional[random.Random] = None) -> List[int]:
    result = execute_initiative(npc.to_dict(), rng=rng, party_members=[])
    fight_log.note_dice_replaced(db, npc)
    start_combat_round(npc, result["action_dice"])
    _record(db, npc, "initiative", result["payload"], gm)
    npcs.touch(encounter)
    db.flush()
    return [d["value"] for d in result["action_dice"]]


def new_round(db: Session, encounter: Encounter, gm: str,
              rng: Optional[random.Random] = None) -> Dict[int, List[int]]:
    """The GM's "New round" (D31): initiative for every NPC still fighting.
    PCs roll their own."""
    for link in encounter.npcs:  # close out the round that is ending
        fight_log.note_dice_replaced(db, link.character)
    encounter.current_round = (encounter.current_round or 0) + 1
    rolled = {}
    for link in encounter.npcs:
        if link.status == "fighting":
            rolled[link.character_id] = roll_initiative(db, encounter, link.character, gm, rng)
        else:
            link.character.action_dice = []
    npcs.touch(encounter)
    db.flush()
    return rolled


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Wounds
# ---------------------------------------------------------------------------

def set_tracking(
    db: Session, encounter: Encounter, npc: Character, *,
    light: Optional[int] = None, serious: Optional[int] = None, void: Optional[int] = None,
) -> Dict[str, Any]:
    """The GM's manual correction of an NPC's wounds or void."""
    for value in (light, serious, void):
        if value is not None and value < 0:
            raise ActionError("values cannot be negative")
    if light is not None:
        npc.current_light_wounds = light
    if serious is not None:
        npc.current_serious_wounds = serious
    if void is not None:
        npc.current_void_points = void
    npcs.touch(encounter)
    db.flush()
    return {"down_prompt": _down_prompt(encounter, npc)}
