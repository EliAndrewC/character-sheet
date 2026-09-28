"""The GM's quick actions for NPCs, resolved on the server (design 4.4, D7).

Every rule comes from where it already lives: formulas from
``build_all_roll_formulas``, dice and void from ``roll_engine`` /
``void_spend`` (the same path the Discord commands use), rounds from
``tracking.start_combat_round``, and the attack / damage / wound-check
arithmetic from ``combat_math`` (the server twin of ``roll_math.js``).

What a PC does is never written here (D19): an NPC's attack is compared
against the target PC's TN to be hit, the GM tells the player the result,
the player parries (or not) on their own sheet or with physical dice, the
GM says how that went, and the damage total is for the GM to read out. The
PC's wounds are the player's to enter.

Each function mutates and flushes; the route commits once.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models import Character, Encounter, EncounterAction, RollHistory
from app.services import combat_math as cm
from app.services import npcs
from app.services.dice import build_all_roll_formulas
from app.services.roll_engine import execute_initiative, execute_roll, impaired_now, roll_dice
from app.services.tracking import start_combat_round
from app.services.void_spend import VoidSpendRefused, apply_void_spend, plan_void_spend

PARRY_OUTCOMES = ("none", "failed", "parried")
PREDECLARED_PARRY_BONUS = 5  # "a free raise to your parry" (rules/03-combat.md)


class ActionError(ValueError):
    """A request the rules or the NPC's state cannot satisfy. Nothing changed."""


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

def formulas(npc: Character) -> Dict[str, Dict[str, Any]]:
    # An NPC is never a party member, so it has no party effects.
    return build_all_roll_formulas(npc.to_dict(), party_members=[])


def attack_options(npc: Character) -> List[Dict[str, str]]:
    """The NPC's attack-type rolls, as ``{"key", "label"}``, plain attack first."""
    out = [
        {"key": key, "label": f.get("label") or key}
        for key, f in formulas(npc).items() if f.get("is_attack_type")
    ]
    return sorted(out, key=lambda o: (o["key"] != "attack", o["label"]))


def tn_to_be_hit(character: Character) -> int:
    return 5 + 5 * (character.parry or 1)


def _spend_dice(npc: Character, indices: Sequence[int]) -> List[int]:
    """Mark the chosen action dice spent. An interrupt parry names two."""
    dice = [dict(d) for d in (npc.action_dice or [])]
    chosen = []
    for raw in indices:
        try:
            i = int(raw)
        except (TypeError, ValueError):
            raise ActionError("pick an action die") from None
        if not 0 <= i < len(dice) or dice[i].get("spent") or i in chosen:
            raise ActionError("that action die is not available")
        chosen.append(i)
    if not chosen:
        raise ActionError("pick an action die")
    for i in chosen:
        dice[i]["spent"] = True
    npc.action_dice = dice
    return [dice[i]["value"] for i in chosen]


def _plan(npc: Character, formula: Dict[str, Any], void: int, label: str):
    if void and formula.get("void_blocked"):
        raise ActionError(f"{npc.name} cannot spend void points on {label}")
    try:
        return plan_void_spend(
            npc, void, activation_cost=1 if formula.get("requires_void_point") else 0,
            roll_label=label,
        )
    except VoidSpendRefused as exc:
        raise ActionError(str(exc)) from None


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


def _roll(
    db: Session, npc: Character, gm: str, roll_key: str, void: int, *,
    rng: Optional[random.Random], tn: Optional[int] = None, flat_bonus: int = 0,
    die: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Roll one of the NPC's formulas with a pre-roll void spend: check the
    spend, roll, deduct, record. Returns ``(formula, payload, row)``."""
    formula = formulas(npc).get(roll_key)
    if not formula:
        raise ActionError(f"{npc.name} has no {roll_key} roll")
    label = formula.get("label") or roll_key
    plan = _plan(npc, formula, void, label)
    if flat_bonus:
        formula = dict(formula, flat=(formula.get("flat") or 0) + flat_bonus)
    payload = execute_roll(npc.to_dict(), roll_key, party_members=[], rng=rng,
                           void_spent=void, formula=formula)
    apply_void_spend(npc, plan)
    row = _record(db, npc, roll_key, payload, gm, tn=tn, die=die)
    return formula, payload, row


def _log(
    db: Session, encounter: Encounter, npc: Character, kind: str, label: str, *,
    total: Optional[int] = None, target: Optional[Character] = None,
    row: Optional[RollHistory] = None, detail: Optional[Dict[str, Any]] = None,
) -> EncounterAction:
    action = EncounterAction(
        encounter_id=encounter.id, character_id=npc.id, round=encounter.current_round,
        kind=kind, label=label, total=total,
        target_character_id=target.id if target is not None else None,
        roll_history_id=row.id if row is not None else None, detail=detail or {},
    )
    db.add(action)
    npcs.touch(encounter)
    db.flush()
    return action


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
    start_combat_round(npc, result["action_dice"])
    _record(db, npc, "initiative", result["payload"], gm)
    npcs.touch(encounter)
    db.flush()
    return [d["value"] for d in result["action_dice"]]


def new_round(db: Session, encounter: Encounter, gm: str,
              rng: Optional[random.Random] = None) -> Dict[int, List[int]]:
    """The GM's "New round" (D31): initiative for every NPC still fighting.
    PCs roll their own."""
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

def attack(
    db: Session, encounter: Encounter, npc: Character, gm: str, *,
    roll_key: str, die: int, target: Optional[Character], tn: Optional[int],
    void: int = 0, rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """An NPC attacks (D19). ``tn`` defaults to the target PC's TN to be hit;
    the GM may change it for situational modifiers."""
    formula = formulas(npc).get(roll_key)
    if not formula or not formula.get("is_attack_type"):
        raise ActionError(f"{npc.name} has no {roll_key} attack")
    if tn is None:
        if target is None:
            raise ActionError("pick a target or give a TN")
        tn = tn_to_be_hit(target)
    variant = formula.get("attack_variant") or "attack"
    is_double = variant == "double_attack"
    effective_tn = cm.attack_effective_tn(tn, is_double)
    _plan(npc, formula, void, formula.get("label") or roll_key)  # refuse before spending the die
    values = _spend_dice(npc, [die])
    _, payload, row = _roll(db, npc, gm, roll_key, void, rng=rng, tn=effective_tn,
                            die={"value": values[0]})
    raw = payload["total"]
    total, raises = raw, 0
    copies = formula.get("wave_man_miss_raise") or 0
    if raw < effective_tn and copies:
        w1 = cm.wave_man_miss_raise(raw, effective_tn, copies)
        total, raises = w1["total"], w1["raises_used"]
    hit = total >= effective_tn
    # A double attack earns its extra dice over the UNRAISED TN, and a
    # Wave Man's raise earns none (the raise only reaches the TN).
    excess = raw - tn if is_double else raw - effective_tn
    extra = cm.excess_to_extra_dice(excess) if hit and raw >= effective_tn else 0
    label = formula.get("label") or roll_key
    detail = {
        "roll_key": roll_key, "variant": variant, "tn": tn, "effective_tn": effective_tn,
        "raw_total": raw, "wave_man_raises": raises, "hit": hit, "extra_dice": extra,
        "void": void, "die": values[0], "outcome": "hit" if hit else "missed",
    }
    action = _log(db, encounter, npc, "attack", label, total=total, target=target, row=row, detail=detail)
    return {"action_id": action.id, "total": total, "hit": hit, "tn": effective_tn,
            "extra_dice": extra, "payload": payload}


def damage(
    db: Session, encounter: Encounter, action: EncounterAction, gm: str, *,
    parry: str = "none", parry_skill: Optional[int] = None, weapon: str = "katana",
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """Resolve a hit once the player has said how their parry went."""
    npc = db.get(Character, action.character_id)
    detail = dict(action.detail or {})
    if action.kind != "attack" or not detail.get("hit"):
        raise ActionError("only a hit rolls damage")
    if "damage" in detail or detail.get("outcome") == "parried":
        raise ActionError("this attack is already resolved")
    if parry not in PARRY_OUTCOMES:
        raise ActionError("parry must be none, failed or parried")
    if parry == "parried":
        detail["outcome"] = "parried"
        action.detail = detail
        npcs.touch(encounter)
        db.flush()
        return {"outcome": "parried"}
    if weapon not in cm.WEAPONS:
        raise ActionError(f"unknown weapon {weapon!r}")
    if parry_skill is None:
        target = db.get(Character, action.target_character_id) if action.target_character_id else None
        parry_skill = (target.parry or 1) if target is not None else 0
    formula = dict(formulas(npc).get(detail["roll_key"]) or {}, void_spent=detail.get("void", 0))
    pool = cm.damage_pool(
        formula, weapon=weapon, extra_dice=detail.get("extra_dice", 0),
        failed_parry=parry == "failed", parry_skill=parry_skill,
        flags=cm.damage_flags(npc.to_dict()),
    )
    dice = roll_dice(pool["rolled"], pool["kept"], True, rng)  # damage always rerolls 10s
    total = dice["kept_sum"] + pool["flat"]
    extras = list(pool["parts"])
    if pool["add_lowest_three"]:
        cells = dice["kept"] + dice["dropped"]
        lowest = sum(sorted(c["value"] for c in cells)[:3])
        total += lowest
        extras.append(f"+{lowest} from 5th Dan (lowest 3 dice added to result)")
    rounded = cm.wave_man_round_damage(total, formula.get("wave_man_round_damage") or 0)
    if rounded != total:
        extras.append(f"Wave Man: {total} rounded to {rounded}")
        total = rounded
    payload = {
        "title": f"{detail.get('variant', 'attack').replace('_', ' ').title()} damage",
        "formula": f"{pool['rolled']}k{pool['kept']}" + (f" + {pool['flat']}" if pool["flat"] else ""),
        "kept": [{"parts": d["parts"]} for d in dice["kept"]],
        "dropped": [{"parts": d["parts"]} for d in dice["dropped"]],
        "bonuses": [], "extras": extras, "kept_sum": dice["kept_sum"], "total": total,
        "alternatives": [],
    }
    row = _record(db, npc, "damage", payload, gm)
    detail.update(damage=total, damage_roll_id=row.id, parry=parry, weapon=weapon)
    action.detail = detail
    npcs.touch(encounter)
    db.flush()
    return {"outcome": "hit", "damage": total, "payload": payload}


def parry(
    db: Session, encounter: Encounter, npc: Character, gm: str, *,
    dice: Sequence[int], attack_total: int, void: int = 0, predeclared: bool = False,
    attacker: Optional[Character] = None, rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """An NPC parries a PC's attack, whose total is its TN. Two dice make an
    interrupt parry - still one action."""
    if len(dice) not in (1, 2):
        raise ActionError("a parry spends one action die, or two as an interrupt")
    formula = formulas(npc).get("parry")
    _plan(npc, formula, void, "Parry")
    values = _spend_dice(npc, dice)
    bonus = PREDECLARED_PARRY_BONUS if predeclared else 0
    _, payload, row = _roll(db, npc, gm, "parry", void, rng=rng, tn=attack_total,
                            flat_bonus=bonus, die={"value": values[0]})
    total = payload["total"]
    success = total >= attack_total
    detail = {"tn": attack_total, "void": void, "dice": values, "interrupt": len(dice) == 2,
              "predeclared": predeclared, "outcome": "parried" if success else "failed"}
    action = _log(db, encounter, npc, "parry", "Parry", total=total, target=attacker,
                  row=row, detail=detail)
    return {"action_id": action.id, "total": total, "success": success, "payload": payload}


def other(db: Session, encounter: Encounter, npc: Character, *, die: int, label: str) -> Dict[str, Any]:
    """Any other action: spends the die, logs what the GM called it."""
    label = (label or "").strip()[:80] or "Action"
    values = _spend_dice(npc, [die])
    action = _log(db, encounter, npc, "other", label, detail={"die": values[0]})
    return {"action_id": action.id}


# ---------------------------------------------------------------------------
# Wounds
# ---------------------------------------------------------------------------

def take_damage(
    db: Session, encounter: Encounter, npc: Character, gm: str, *,
    amount: int, void: int = 0, rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """A PC hit the NPC for ``amount``: add the light wounds and roll the
    wound check. A failure takes its serious wounds and clears the light
    wounds; a pass leaves the keep-or-take choice to the GM (D20)."""
    if amount <= 0:
        raise ActionError("damage must be positive")
    formula = formulas(npc).get("wound_check")
    _plan(npc, formula, void, "Wound Check")
    npc.current_light_wounds = (npc.current_light_wounds or 0) + amount
    lw = npc.current_light_wounds
    _, payload, _row = _roll(db, npc, gm, "wound_check", void, rng=rng, tn=lw)
    result = cm.wound_check_result(payload["total"], lw, bool(formula.get("bayushi_5th_dan_half_lw")))
    if not result["passed"]:
        npc.current_serious_wounds = (npc.current_serious_wounds or 0) + result["serious_wounds"]
        npc.current_light_wounds = 0
    npcs.touch(encounter)
    db.flush()
    return {
        "total": payload["total"], "light_wounds": lw, "passed": result["passed"],
        "serious_wounds_taken": result["serious_wounds"], "choice_needed": result["passed"],
        "down_prompt": _down_prompt(encounter, npc), "payload": payload,
    }


def take_serious_wound(db: Session, encounter: Encounter, npc: Character) -> Dict[str, Any]:
    """After a passed wound check: take 1 serious wound to clear the light wounds."""
    npc.current_serious_wounds = (npc.current_serious_wounds or 0) + 1
    npc.current_light_wounds = 0
    npcs.touch(encounter)
    db.flush()
    return {"down_prompt": _down_prompt(encounter, npc)}


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
