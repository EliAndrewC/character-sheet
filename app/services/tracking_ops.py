"""Tracking operations: the sheet's state changes, applied by the server
(server-rolls-design 4.2, Phase 2).

The tracking section used to change its own copy of the state and post the
whole blob to ``/track``. Each of its buttons is now an operation here: the
tab says what happened ("take 1 serious wound", "spend Absorb Void"), the
server checks it against the rules and the character, applies it, and the
tab adopts the snapshot it answers with. An operation never answers 409
(audit B9) - two operations compose; ``prefetch_body`` keeps each atomic.

``apply_op`` raises ``OpRefused`` before changing anything.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from app.models import Character
from app.services.attack_rolls import attack_flags
from app.services.wound_checks import wound_check_flags
from app.services.parry_feint import parry_feint_flags
from app.services.per_adventure import per_adventure_abilities
from app.services.tracking import set_serious_wounds
from app.services.void_spend import (
    VoidSpendRefused, apply_void_spend, plan_void_spend, school_dan, void_limits,
)

BANK_KEYS = (
    "akodo_banked_bonuses", "hiruma_banked_attack_bonus", "bayushi_banked_feint_raise",
    "banked_wc_excess", "matsu_banked_wc_bonus", "matsu_banked_wc_bonuses",
    "ide_banked_tn_reduce", "hida_banked_wc_bonus",
)
MANTIS_ROUND_KEYS = (
    "mantis_posture_phase", "mantis_posture_history",
    "mantis_offensive_3rd_dan_accum", "mantis_defensive_3rd_dan_accum",
)
MAX_LABEL = 500


class OpRefused(ValueError):
    """An operation the rules or the character's state cannot take."""


def _int(args: Dict[str, Any], key: str) -> int:
    try:
        return int(args.get(key))
    except (TypeError, ValueError):
        raise OpRefused(f"{key} must be a whole number") from None


def _delta(args: Dict[str, Any]) -> int:
    delta = _int(args, "delta")
    if delta not in (-1, 1):
        raise OpRefused("delta must be 1 or -1")
    return delta


def _ability(character: Character, ability_id: Any, kind: str) -> Dict[str, Any]:
    for a in per_adventure_abilities(character):
        if a["id"] == ability_id and a["type"] == kind:
            return a
    raise OpRefused(f"{character.name} has no {ability_id} {kind}")


def _state(character: Character) -> Dict[str, Any]:
    return dict(character.adventure_state or {})


def _dice(character: Character, args: Dict[str, Any]):
    dice = [dict(d) for d in (character.action_dice or [])]
    i = _int(args, "index")
    if not 0 <= i < len(dice):
        raise OpRefused("no such action die")
    return dice, i


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def _light_wounds(c: Character, args: Dict[str, Any]) -> None:
    mode, value = args.get("mode"), _int(args, "value")
    if mode == "add":
        if value < 1:
            raise OpRefused("add at least 1 light wound")
        c.current_light_wounds = (c.current_light_wounds or 0) + value
    elif mode == "set":
        if value < 0:
            raise OpRefused("light wounds cannot be negative")
        c.current_light_wounds = value
    else:
        raise OpRefused("mode must be add or set")


def _take_serious(c: Character, args: Dict[str, Any]) -> None:
    """Take serious wounds and clear the light wounds (the light-wound
    modal's "take serious wounds", and a passed wound check's choice)."""
    count = _int(args, "count")
    if count < 1:
        raise OpRefused("take at least 1 serious wound")
    set_serious_wounds(c, (c.current_serious_wounds or 0) + count)
    c.current_light_wounds = 0


def _serious_wounds(c: Character, args: Dict[str, Any]) -> None:
    set_serious_wounds(c, (c.current_serious_wounds or 0) + _delta(args))


def _void(c: Character, args: Dict[str, Any]) -> None:
    top = void_limits(c.to_dict())["void_max"]
    c.current_void_points = max(0, min(top, (c.current_void_points or 0) + _delta(args)))


def _temp_void(c: Character, args: Dict[str, Any]) -> None:
    c.current_temp_void_points = max(0, (c.current_temp_void_points or 0) + _delta(args))


def _counter(c: Character, args: Dict[str, Any]) -> None:
    ability = _ability(c, args.get("id"), "counter")
    state = _state(c)
    key = ability["id"] + "_used"
    state[key] = max(0, min(ability["max"], int(state.get(key, 0) or 0) + _delta(args)))
    c.adventure_state = state


def _toggle(c: Character, args: Dict[str, Any]) -> None:
    ability = _ability(c, args.get("id"), "toggle")
    state = _state(c)
    state[ability["id"]] = bool(args.get("value"))
    c.adventure_state = state


def _reset_ability(c: Character, args: Dict[str, Any]) -> None:
    ability_id = args.get("id")
    ability = next((a for a in per_adventure_abilities(c) if a["id"] == ability_id), None)
    if ability is None:
        raise OpRefused(f"{c.name} has no {ability_id}")
    state = _state(c)
    if ability["type"] == "counter":
        state[ability_id + "_used"] = 0
    else:
        state[ability_id] = False
    c.adventure_state = state


def _reset_adventure(c: Character, args: Dict[str, Any]) -> None:
    """Every per-adventure counter and toggle, the action dice, the precepts
    pool, every banked bonus and the Mantis round tracker."""
    state = _state(c)
    for a in per_adventure_abilities(c):
        if a["type"] == "counter":
            state[a["id"] + "_used"] = 0
        else:
            state[a["id"]] = False
    for key in BANK_KEYS + MANTIS_ROUND_KEYS + ("mirumoto_round_points",):
        state.pop(key, None)
    c.adventure_state = state
    c.action_dice = []
    c.precepts_pool = []


def _absorb_void(c: Character, args: Dict[str, Any]) -> None:
    """Absorb Void: a void point for one use of the pool (and its undo)."""
    delta = _delta(args)
    ability = _ability(c, "absorb_void", "counter")
    state = _state(c)
    used = int(state.get("absorb_void_used", 0) or 0)
    if delta > 0 and used >= ability["max"]:
        raise OpRefused("Absorb Void is used up")
    if delta < 0 and used <= 0:
        raise OpRefused("no Absorb Void to undo")
    state["absorb_void_used"] = used + delta
    c.adventure_state = state
    top = void_limits(c.to_dict())["void_max"]
    c.current_void_points = max(0, min(top, (c.current_void_points or 0) + delta))


def _togashi_heal(c: Character, args: Dict[str, Any]) -> None:
    """Togashi Ise Zumi 5th Dan: a void point heals 2 serious wounds."""
    if c.school != "togashi_ise_zumi" or school_dan(c.to_dict()) < 5:
        raise OpRefused(f"{c.name} cannot heal serious wounds with void")
    if (c.current_serious_wounds or 0) < 2:
        raise OpRefused("needs at least 2 serious wounds")
    try:
        plan = plan_void_spend(c, 0, activation_cost=1, roll_label="the 5th Dan heal")
    except VoidSpendRefused as exc:
        raise OpRefused(str(exc)) from None
    apply_void_spend(c, plan)
    set_serious_wounds(c, (c.current_serious_wounds or 0) - 2)


def _hida_trade(c: Character, args: Dict[str, Any]) -> None:
    """Hida Bushi 4th Dan: take 2 serious wounds to clear the light wounds."""
    if c.school != "hida_bushi" or school_dan(c.to_dict()) < 4:
        raise OpRefused(f"{c.name} cannot trade serious wounds for light wounds")
    if (c.current_light_wounds or 0) <= 0:
        raise OpRefused("no light wounds to clear")
    set_serious_wounds(c, (c.current_serious_wounds or 0) + 2)
    c.current_light_wounds = 0


def _action_die(c: Character, args: Dict[str, Any]) -> None:
    dice, i = _dice(c, args)
    action = args.get("action")
    label = str(args.get("label") or "")[:MAX_LABEL]
    if action == "spend":
        if dice[i].get("spent"):
            raise OpRefused("that action die is already spent")
        dice[i]["spent"] = True
        dice[i].pop("spent_by", None)
        if label:
            dice[i]["spent_by"] = label
    elif action == "unspend":
        dice[i]["spent"] = False
        dice[i].pop("spent_by", None)
    elif action == "annotate":
        if label:
            dice[i]["spent_by"] = label
        else:
            dice[i].pop("spent_by", None)
    elif action == "set_value":
        # A player who rolled physical dice sets each die to match (or the
        # GM corrects one); the dice stay in order, spent state and all.
        value = args.get("value")
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
            raise OpRefused("an action die's value is 1 to 10")
        dice[i]["value"] = value
        dice.sort(key=lambda d: d.get("value") or 0)
    else:
        raise OpRefused("action must be spend, unspend, annotate or set_value")
    c.action_dice = dice


def _clear_action_dice(c: Character, args: Dict[str, Any]) -> None:
    c.action_dice = []
    state = _state(c)
    for key in MANTIS_ROUND_KEYS:
        state.pop(key, None)
    c.adventure_state = state


def _mirumoto_points(c: Character, args: Dict[str, Any]) -> None:
    """Mirumoto 3rd Dan's points left this round: +/-1, or ``reset`` to full.
    (Spent on an attack still rolled in the browser; a parry spends them
    through its roll session.)"""
    flags = parry_feint_flags(c.to_dict())
    if not flags["mirumoto_round_points"]:
        raise OpRefused(f"{c.name} has no 3rd Dan round points")
    top = flags["mirumoto_round_points_max"]
    state = _state(c)
    left = int(state.get("mirumoto_round_points") or 0)
    state["mirumoto_round_points"] = top if args.get("reset") else max(0, min(top, left + _delta(args)))
    c.adventure_state = state


def _mantis_posture(c: Character, args: Dict[str, Any]) -> None:
    """Mantis Wave-Treader Special: declare this phase's posture."""
    if c.school != "mantis_wave_treader":
        raise OpRefused(f"{c.name} does not take postures")
    kind = args.get("type")
    if kind not in ("offensive", "defensive"):
        raise OpRefused("type must be offensive or defensive")
    state = _state(c)
    phase = int(state.get("mantis_posture_phase") or 1)
    if phase > 10:
        raise OpRefused("every phase of this round already has a posture")
    state["mantis_posture_history"] = list(state.get("mantis_posture_history") or []) + [kind]
    state["mantis_posture_phase"] = phase + 1
    c.adventure_state = state


def _mantis_3rd_dan(c: Character, args: Dict[str, Any]) -> None:
    """Mantis 3rd Dan: spend an action die for +X on the posture's rolls for
    the rest of the round. The die is ``index`` if given, else the 4th Dan
    bonus die, else the highest unspent regular die."""
    side = args.get("side")
    if side not in ("offensive", "defensive"):
        raise OpRefused("side must be offensive or defensive")
    flags = attack_flags(c.to_dict())
    if not flags["mantis_3rd_dan_" + side] or not flags["mantis_3rd_dan_x"]:
        raise OpRefused(f"{c.name} has no Mantis 3rd Dan technique")
    dice = [dict(d) for d in (c.action_dice or [])]
    if args.get("index") is not None:
        i = _int(args, "index")
        if not 0 <= i < len(dice) or dice[i].get("spent"):
            raise OpRefused("that action die cannot be spent")
    else:
        fourth = [j for j, d in enumerate(dice) if not d.get("spent") and d.get("mantis_4th_dan")]
        regular = [j for j, d in enumerate(dice) if not d.get("spent") and not d.get("athletics_only")]
        if fourth:
            i = fourth[0]
        elif regular:
            i = max(regular, key=lambda j: (int(dice[j].get("value") or 0), -j))
        else:
            raise OpRefused("no action die left to spend")
    dice[i]["spent"] = True
    dice[i]["spent_by"] = f"Mantis 3rd Dan ({side})"
    c.action_dice = dice
    state = _state(c)
    key = f"mantis_{side}_3rd_dan_accum"
    state[key] = int(state.get(key) or 0) + flags["mantis_3rd_dan_x"]
    c.adventure_state = state


def _kakita_interrupt(c: Character, args: Dict[str, Any]) -> None:
    """Kakita Duelist Phase 0 interrupt: the two highest unspent regular
    action dice pay for it."""
    if c.school != "kakita_duelist":
        raise OpRefused(f"{c.name} has no Phase 0 interrupt")
    dice = [dict(d) for d in (c.action_dice or [])]
    free = sorted((j for j, d in enumerate(dice) if not d.get("spent") and not d.get("athletics_only")),
                  key=lambda j: -int(dice[j].get("value") or 0))
    if len(free) < 2:
        raise OpRefused("the interrupt needs two unspent action dice")
    for j in free[:2]:
        dice[j]["spent"] = True
        dice[j]["spent_by"] = "Kakita Phase 0 interrupt"
    c.action_dice = dice


def _akodo_reflect(c: Character, args: Dict[str, Any]) -> None:
    """Akodo 5th Dan: void points spent after taking damage (10 light wounds
    back per point). Drawn like any spend, with its school consequences."""
    if not wound_check_flags(c.to_dict())["akodo_reflect_damage"]:
        raise OpRefused(f"{c.name} cannot reflect damage")
    count = _int(args, "count")
    if count < 1:
        raise OpRefused("spend at least 1 void point")
    try:
        plan = plan_void_spend(c, 0, activation_cost=count, roll_label="the 5th Dan reflect")
    except VoidSpendRefused as exc:
        raise OpRefused(str(exc)) from None
    apply_void_spend(c, plan)


BANK_LIST_KEYS = ("akodo_banked_bonuses", "banked_wc_excess", "matsu_banked_wc_bonuses")
BANK_AMOUNT_KEYS = ("hiruma_banked_attack_bonus", "bayushi_banked_feint_raise", "ide_banked_tn_reduce",
                    "hida_banked_wc_bonus")


def _bank(c: Character, args: Dict[str, Any]) -> None:
    """The tracking section's hand edits to a banked bonus: ``spend`` one
    amount (off a list bank, or subtracted from a single-amount bank), or
    ``clear`` it."""
    key = args.get("key")
    if key not in BANK_LIST_KEYS + BANK_AMOUNT_KEYS:
        raise OpRefused("no such bank")
    state = _state(c)
    if args.get("clear"):
        state.pop(key, None)
    else:
        amount = _int(args, "spend")
        if key in BANK_LIST_KEYS:
            bank = list(state.get(key) or [])
            if amount not in bank:
                raise OpRefused(f"no banked +{amount} to spend")
            bank.remove(amount)
            state[key] = bank
        else:
            state[key] = max(0, int(state.get(key) or 0) - max(0, amount))
    c.adventure_state = state


def precepts_pool_flags(c: Character) -> Dict[str, Any]:
    """Priest 3rd Dan: a pool of X dice (X = precepts) to swap into the
    party's attack / parry / damage / wound check rolls."""
    data = c.to_dict()
    on = c.school == "priest" and school_dan(data) >= 3
    return {"priest_precepts_pool": on,
            "priest_precepts_pool_size": int((data.get("skills") or {}).get("precepts", 0) or 0) if on else 0}


def _precepts_pool_clear(c: Character, args: Dict[str, Any]) -> None:
    c.precepts_pool = []


OPS: Dict[str, Callable[[Character, Dict[str, Any]], None]] = {
    "light_wounds": _light_wounds,
    "take_serious": _take_serious,
    "serious_wounds": _serious_wounds,
    "void": _void,
    "temp_void": _temp_void,
    "counter": _counter,
    "toggle": _toggle,
    "reset_ability": _reset_ability,
    "reset_adventure": _reset_adventure,
    "absorb_void": _absorb_void,
    "togashi_heal": _togashi_heal,
    "hida_trade": _hida_trade,
    "action_die": _action_die,
    "clear_action_dice": _clear_action_dice,
    "mirumoto_points": _mirumoto_points,
    "mantis_posture": _mantis_posture,
    "mantis_3rd_dan": _mantis_3rd_dan,
    "kakita_interrupt": _kakita_interrupt,
    "akodo_reflect": _akodo_reflect,
    "precepts_pool_clear": _precepts_pool_clear,
    "bank": _bank,
}



def apply_op(character: Character, op: str, args: Dict[str, Any]) -> None:
    if op not in OPS:
        raise OpRefused(f"unknown operation {op!r}")
    if not isinstance(args, dict):
        raise OpRefused("args must be an object")
    OPS[op](character, args)
