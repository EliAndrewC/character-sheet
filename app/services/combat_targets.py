"""A PC's side of the group's fight: whom they can attack, and with what.

Two mistakes players kept making in a fight were typing the wrong TN for the
NPC they attacked and the wrong weapon damage. During a fight the attack
modal therefore opens on a "who are you attacking?" step, and the server
fills in both numbers:

* **The TN.** ``for_pc`` lists the fight's NPCs that are still fighting,
  each with whether this PC can reach it (``Encounter.reach``; a melee or
  athletics attack offers only those, an arrow any of them) and its TN -
  but only once players know it (``EncounterNpc.tn_revealed``, or the NPC
  has been attacked: ``combat_view.tn_known``). An unknown TN, and the
  Parry behind it, are never sent. Picking an NPC whose TN is not known
  reveals it (``reveal``) - which, by the rules, commits the PC to the
  attack. ``lock_target`` then replaces whatever TN the roll request
  carries with the NPC's real one, so the lock does not depend on the
  browser.
* **The weapon.** The GM sets each PC's weapon dice for the fight
  (``Encounter.weapons``, seeded from the group's previous fight);
  ``lock_weapon`` puts them into the damage roll.

* **The duel.** The GM marks which NPC a PC is in an iaijutsu duel with
  (``Encounter.duels``). The duel modal then needs no opponent XP: its
  starting TN comes from the NPC (``duel_tn``), and ``lock_duel`` judges
  the strike against it plus 5 per focus the opponent declared. The PC's
  Evaluate Stance roll answers what that roll tells them about this NPC
  (``stance``) - computed here, so the NPC's Fire and TN never reach the
  browser beyond what the roll reveals.

* **The phase.** The GM moves the fight's clock (``Encounter.current_phase``,
  0-10; "New round" starts at 0). An attack made in the fight reads it
  (``lock_phase``): Kakita 3rd Dan counts from the current phase, not the
  die's, Shinjo's and an arrow's hold bonus run to it, Doji 4th Dan adds it.
  A Kakita 3rd Dan (or Kitsuki 4th Dan) knows when a target within striking
  range acts next (``next_phase``), so that phase is filled in too. A
  Mantis may not declare a posture for a phase the fight has not reached
  (``posture_phase_refusal``), and a Priest's "Bless a combat phase" choice
  is kept per phase on the fight (``set_blessing``). The combat page shows
  both (``phase_abilities``).

Melee reach is list-only: the server does not refuse an attack on an NPC
out of reach (the GM trusts the players, and lines are often drawn late).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Character, Encounter, EncounterNpc, GamingGroup, RollSession
from app.services import npcs
from app.services.combat_actions import tn_to_be_hit

WEAPON_LIMITS = ((0, 10), (1, 10))  # rolled, kept: as the damage action clamps them


def pc_encounter(db: Session, pc: Character) -> Optional[Encounter]:
    """The active fight this PC is in (every visible PC of the group is), or None."""
    if pc.is_npc or pc.is_hidden or not pc.gaming_group_id:
        return None
    return npcs.active_encounter(db, pc.gaming_group_id)


def _link(encounter: Encounter, npc_id: Any) -> Optional[EncounterNpc]:
    if isinstance(npc_id, bool) or not isinstance(npc_id, int):
        return None
    link = npcs.link_for(encounter, npc_id)
    return link if link is not None and link.status == "fighting" else None


def weapon_for(encounter: Optional[Encounter], pc_id: int) -> Optional[Tuple[int, int]]:
    w = ((encounter.weapons or {}) if encounter else {}).get(str(pc_id))
    return (int(w[0]), int(w[1])) if w else None


def _numbers(npc: Character) -> Dict[str, int]:
    """What attacking this NPC is judged against (rules/03-combat.md)."""
    return {"tn": tn_to_be_hit(npc), "athletics_tn": 5 + 10 * (npc.parry or 1)}


def duel_tn(npc: Character) -> int:
    """A duelist's starting TN to be hit: total XP / 10 (rules/03-combat.md)."""
    return ((npc.starting_xp or 0) + (npc.earned_xp or 0)) // 10


def duel_link(encounter: Optional[Encounter], pc_id: int) -> Optional[EncounterNpc]:
    """The NPC (still fighting) this PC is in a duel with, or None."""
    npc_id = ((encounter.duels or {}) if encounter else {}).get(str(pc_id))
    return _link(encounter, npc_id) if npc_id is not None else None


def stance(npc: Character, total: int) -> Dict[str, Any]:
    """What an Evaluate Stance roll of ``total`` tells about ``npc``: its
    Fire is at least total / 5 (known exactly when that exceeds it), and its
    starting TN at least the total (known exactly when the total exceeds it)."""
    total = max(0, int(total or 0))
    fire, tn, bound = npc.ring_fire or 0, duel_tn(npc), total // 5
    return {
        "name": npc.name,
        "fire": {"exact": True, "value": fire} if bound > fire else {"exact": False, "value": bound},
        "tn": {"exact": True, "value": tn} if total > tn else {"exact": False, "value": total},
    }


PHASES = (0, 10)
NO_ACTION_PHASE = 11  # rules/04-schools.md: no action left, "considered to act in phase 11"
BLESSINGS = {"attack": "attacks", "parry": "parries", "damage": "damage", "wound_check": "wound checks"}
BLESSING_ABILITY = "priest_combat_rounding"


def next_phase(npc: Character) -> int:
    """This NPC's next action: its lowest unspent die, even one held from an
    earlier phase (GM, 2026-10-27: in phase 3 a die held from phase 1 is
    shown as 1 - the Kakita 3rd Dan bonus is clamped at 0 anyway); 11 with
    none left."""
    left = [int(d.get("value") or 0) for d in npc.action_dice or [] if not d.get("spent")]
    return min(left) if left else NO_ACTION_PHASE


def knows_next_actions(pc: Character) -> bool:
    """Kakita 3rd Dan ("You know the next action of all potential targets
    within striking range") and Kitsuki 4th Dan ("the Void, parry, and phase
    of the next action of each character")."""
    from app.services.void_spend import school_dan

    dan = school_dan(pc.to_dict())
    return (pc.school == "kakita_duelist" and dan >= 3) or knows_parry(pc)


def knows_parry(pc: Character) -> bool:
    """Kitsuki 4th Dan knows every character's parry, so every TN."""
    from app.services.void_spend import school_dan

    return pc.school == "kitsuki_magistrate" and school_dan(pc.to_dict()) >= 4


def set_phase(db: Session, encounter: Encounter, delta: Any) -> int:
    """The GM moves the fight's phase by ``delta`` (an operation, so two
    clicks are two steps), kept within 0-10."""
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise ValueError("delta must be a whole number")
    encounter.current_phase = max(PHASES[0], min(PHASES[1], (encounter.current_phase or 0) + delta))
    npcs.touch(encounter)
    db.flush()
    return encounter.current_phase


def can_bless_phase(pc: Character) -> bool:
    """A Priest has every ritual; a profession character holds it or not; a
    Kitsune Warden at 3rd Dan may, for a 3rd Dan free raise."""
    from app.services.professions import holds_ability
    from app.services.special_rolls import kitsune_rituals

    return pc.school == "priest" or holds_ability(pc, BLESSING_ABILITY) or kitsune_rituals(pc)


def blessing_is_optional(pc: Character) -> bool:
    """A Kitsune Warden pays a free raise for it, so not blessing a phase is
    the usual case and is not shown as "not yet chosen"."""
    from app.services.special_rolls import ritual_costs_a_raise

    return ritual_costs_a_raise(pc, BLESSING_ABILITY)


def set_blessing(db: Session, encounter: Encounter, pc: Character, kind: Any) -> Dict[str, Any]:
    """The pick for the fight's current phase, or ``None`` to take it back (a
    mistake; the rules allow one pick per phase). A Kitsune Warden's first
    pick in a phase spends a 3rd Dan free raise and taking it back returns
    it; changing the pick costs nothing more. Returns ``{phase, kind}``."""
    from app.services.special_rolls import ritual_raises_left, spend_ritual_raise

    if not can_bless_phase(pc):
        raise ValueError(f"{pc.name} cannot bless a combat phase")
    if kind is not None and kind not in BLESSINGS:
        raise ValueError("choose attack, parry, damage or wound_check")
    choices = {k: dict(v) for k, v in (encounter.phase_choices or {}).items()}
    mine = choices.get(str(pc.id), {})
    phase = str(encounter.current_phase or 0)
    had = phase in mine
    if blessing_is_optional(pc):
        if kind is not None and not had:
            if ritual_raises_left(pc) < 1:
                raise ValueError(f"{pc.name} has no 3rd Dan free raise left to perform the ritual")
            spend_ritual_raise(pc, 1)
        elif kind is None and had:
            spend_ritual_raise(pc, -1)
    if kind is None:
        mine.pop(phase, None)
    else:
        mine[phase] = kind
    choices[str(pc.id)] = mine
    encounter.phase_choices = choices
    npcs.touch(encounter)
    db.flush()
    return {"phase": int(phase), "kind": kind}


def phase_abilities(encounter: Optional[Encounter], pc: Character) -> List[Dict[str, Any]]:
    """The per-phase choices this PC makes, for the fight's current phase:
    ``[{kind, label, choice}]``, ``choice`` None while not yet made. A Mantis
    Wave-Treader's posture (phases 1-10) and a Priest's blessing."""
    if encounter is None:
        return []
    phase = encounter.current_phase or 0
    out = []
    if pc.school == "mantis_wave_treader" and phase >= 1:
        history = (pc.adventure_state or {}).get("mantis_posture_history") or []
        out.append({"kind": "posture", "label": "Posture",
                    "choice": history[phase - 1] if len(history) >= phase else None})
    if can_bless_phase(pc):
        pick = ((encounter.phase_choices or {}).get(str(pc.id)) or {}).get(str(phase))
        entry = {"kind": "blessing", "label": "Blessing", "choice": BLESSINGS.get(pick), "value": pick}
        if blessing_is_optional(pc):
            entry["optional"] = True  # only shown once made (a Kitsune's free raise)
        out.append(entry)
    return out


def posture_phase_refusal(db: Session, pc: Character) -> Optional[str]:
    """Why a Mantis may not declare its next posture yet: the fight has not
    reached that phase. None when it may (or outside a fight)."""
    encounter = pc_encounter(db, pc)
    if encounter is None:
        return None
    want = int((pc.adventure_state or {}).get("mantis_posture_phase") or 1)
    now = encounter.current_phase or 0
    if want > now:
        return (f"The fight is at phase {now}: your posture for phase {want} "
                f"can be chosen once the GM reaches it.")
    return None


def for_pc(db: Session, pc: Character) -> Optional[Dict[str, Any]]:
    """The attack modal's target step for ``pc``, or None outside a fight."""
    from app.services.combat_view import tn_known

    encounter = pc_encounter(db, pc)
    if encounter is None:
        return None
    links = npcs.in_standing_order(encounter, "npcs", [lk for lk in encounter.npcs if lk.status == "fighting"],
                                   id_of=lambda lk: lk.character_id)
    reach = {p[1] for p in encounter.reach or [] if p[0] == pc.id}
    phase = encounter.current_phase or 0
    sees_next, sees_parry = knows_next_actions(pc), knows_parry(pc)
    targets = []
    for link in links:
        reachable = link.character_id in reach
        entry = {"id": link.character_id, "name": link.character.name,
                 "reachable": reachable, "tn": None, "athletics_tn": None, "next_phase": None}
        if sees_parry or tn_known(db, encounter, link):
            entry.update(_numbers(link.character))
        # Kakita 3rd Dan: targets within striking range; Kitsuki 4th Dan: anyone.
        if sees_next and (reachable or sees_parry):
            entry["next_phase"] = next_phase(link.character)
        targets.append(entry)
    weapon = weapon_for(encounter, pc.id)
    duel = duel_link(encounter, pc.id)
    return {
        "group_id": encounter.gaming_group_id,
        "encounter": encounter.name,
        "phase": phase,
        "weapon": list(weapon) if weapon else None,
        "targets": targets,
        "duel": {"id": duel.character_id, "name": duel.character.name, "tn": duel_tn(duel.character)}
        if duel else None,
    }


def reveal(db: Session, encounter: Encounter, npc_id: Any) -> Dict[str, Any]:
    """A PC picked this NPC as a target: its TN is known from now on.
    An operation (picking it twice is the same as once). Raises
    ``LookupError`` for an NPC not fighting in this fight."""
    link = _link(encounter, npc_id)
    if link is None:
        raise LookupError("that NPC is not fighting in this fight")
    if not link.tn_revealed:
        link.tn_revealed = True
        npcs.touch(encounter)
        db.flush()
    return {"id": link.character_id, "name": link.character.name, **_numbers(link.character)}


def set_weapon(db: Session, encounter: Encounter, pc_id: Any, rolled: Any, kept: Any,
               pcs: List[int]) -> None:
    """The GM sets (or, with ``rolled`` None, clears) a PC's weapon dice."""
    if isinstance(pc_id, bool) or pc_id not in pcs:
        raise ValueError("that character is not in this fight")
    weapons = dict(encounter.weapons or {})
    if rolled is None:
        weapons.pop(str(pc_id), None)
    else:
        dice = []
        for value, (low, high), what in zip((rolled, kept), WEAPON_LIMITS, ("rolled", "kept")):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"weapon {what} dice must be a whole number from {low} to {high}")
            dice.append(value)
        weapons[str(pc_id)] = dice
    encounter.weapons = weapons
    npcs.touch(encounter)
    db.flush()


def set_duel(db: Session, encounter: Encounter, pc_id: Any, npc_id: Any, pcs: List[int]) -> None:
    """The GM marks (or, with ``npc_id`` None, clears) whom a PC duels."""
    if isinstance(pc_id, bool) or pc_id not in pcs:
        raise ValueError("that character is not in this fight")
    duels = dict(encounter.duels or {})
    if npc_id is None:
        duels.pop(str(pc_id), None)
    else:
        if _link(encounter, npc_id) is None:
            raise ValueError("that NPC is not fighting in this fight")
        duels[str(pc_id)] = npc_id
    encounter.duels = duels
    npcs.touch(encounter)
    db.flush()


def current_duels(encounter: Optional[Encounter], pcs: List[int]) -> List[List[int]]:
    """``[pc_id, npc_id]`` for each PC in the fight dueling a fighting NPC."""
    return [[pc, duel_link(encounter, pc).character_id] for pc in pcs if duel_link(encounter, pc)]


def seed_weapons(db: Session, encounter: Encounter) -> None:
    """A new fight starts with the weapons of the group's previous one."""
    previous = (
        db.query(Encounter)
        .filter(Encounter.gaming_group_id == encounter.gaming_group_id, Encounter.id != encounter.id)
        .order_by(Encounter.id.desc())
        .first()
    )
    if previous is not None and previous.weapons:
        encounter.weapons = dict(previous.weapons)
        db.flush()


# ---------------------------------------------------------------------------
# The locks, applied by the roll routes
# ---------------------------------------------------------------------------

def lock_target(db: Session, character: Character, body: Dict[str, Any], live: bool) -> None:
    """Before ``POST /characters/{id}/roll``: an attack by a PC in a fight
    whose ``target_id`` names an NPC fighting there is judged against that
    NPC's real TN, whatever the request says. ``build_attack`` picks the
    number for the kind of attack (an arrow's base TN - distance, cover and
    evasion stay the player's - or 5 + 10 x Parry for an athletics attack).
    A live roll reveals the TN."""
    body.pop("target_numbers", None)  # only ever set here
    encounter = pc_encounter(db, character)
    if encounter is None:
        return
    link = _link(encounter, body.get("target_id"))
    if link is None:
        return
    body["target_numbers"] = _numbers(link.character)
    if live and not link.tn_revealed:
        reveal(db, encounter, link.character_id)


def lock_phase(db: Session, character: Character, body: Dict[str, Any]) -> None:
    """Before an attack by a PC in a fight: the phase it is made in is the
    fight's. Kakita 3rd Dan counts from it (unless the request names one -
    the phase 0 interrupt does), and from the target's next action when the
    attacker may know it; Shinjo's and an arrow's hold bonus run to it;
    Doji 4th Dan (sent only when its box is ticked) adds it."""
    body.pop("attacker_phase_from_fight", None)  # only ever set here
    encounter = pc_encounter(db, character)
    if encounter is None:
        return
    phase = encounter.current_phase or 0
    if body.get("attacker_phase") is None:
        body["attacker_phase"] = phase
        body["attacker_phase_from_fight"] = True
    body["shinjo_phase"] = phase
    if body.get("doji_phase"):
        body["doji_phase"] = phase
    if isinstance(body.get("archery"), dict):
        body["archery"] = dict(body["archery"], phase=phase)
    link = _link(encounter, body.get("target_id"))
    if link is not None and knows_next_actions(character):
        reach = {p[1] for p in encounter.reach or [] if p[0] == character.id}
        if link.character_id in reach or knows_parry(character):
            body["kakita_defender_phase"] = next_phase(link.character)


def lock_duel(db: Session, character: Character, body: Dict[str, Any]) -> None:
    """Before an iaijutsu strike by a PC the GM put in a duel: the opponent's
    TN is the NPC's starting TN plus 5 per focus it declared
    (``opponent_focuses``), whatever ``opponent_tn`` the request says."""
    if str(body.get("roll_key") or "") != "iaijutsu:strike":
        return
    link = duel_link(pc_encounter(db, character), character.id)
    if link is None:
        return
    try:
        focuses = max(0, min(20, int(body.get("opponent_focuses") or 0)))
    except (TypeError, ValueError):
        focuses = 0
    body["opponent_tn"] = duel_tn(link.character) + 5 * focuses


EVALUATE_STANCE_KEY = "knack:iaijutsu:evaluate"


def add_stance(db: Session, character: Character, roll_key: str, result: Dict[str, Any]) -> None:
    """After a live Evaluate Stance roll (or an action that rescored one) by
    a PC in a duel: what it tells them about their opponent."""
    if roll_key != EVALUATE_STANCE_KEY or result.get("mode", "live") != "live" or result.get("total") is None:
        return
    link = duel_link(pc_encounter(db, character), character.id)
    if link is not None:
        result["stance"] = stance(link.character, result["total"])


def lock_act_phase(db: Session, character: Character, action: str, args: Dict[str, Any]) -> None:
    """Before a parry's Shinjo phase action by a PC in a fight: the die was
    spent in the fight's phase."""
    if action != "shinjo_phase":
        return
    encounter = pc_encounter(db, character)
    if encounter is not None:
        args["phase"] = encounter.current_phase or 0


def lock_weapon(db: Session, character: Character, session: RollSession, action: str,
                args: Dict[str, Any]) -> None:
    """Before an attack's ``damage`` action: the GM's weapon for this PC."""
    if action != "damage" or not (session.formula or {}).get("is_attack_type"):
        return
    weapon = weapon_for(pc_encounter(db, character), character.id)
    if weapon is not None:
        args["weapon_rolled"], args["weapon_kept"] = weapon
