"""The iaijutsu duel and Kakita 5th Dan as the server makes them for the
sheet (server-rolls-design Phase 9): which formula each roll uses, the
bonuses the modal's inputs add, and the damage pools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.roll_engine import apply_dice_cap
from app.services.void_spend import school_dan

# Roll key recorded -> the formula it rolls.
DUEL_KEYS = {"iaijutsu:contested": "knack:iaijutsu", "iaijutsu:strike": "knack:iaijutsu:strike"}
KAKITA_5TH = "kakita_5th_dan"


def restart_bonus(choices: Dict[str, Any]) -> int:
    """The +5 per restart a duel's winner of the tied round carries forward."""
    try:
        value = int(choices.get("restart_bonus") or 0)
    except (TypeError, ValueError):
        raise ValueError("restart_bonus must be a whole number") from None
    if value < 0 or value % 5:
        raise ValueError("restart_bonus must be a multiple of 5")
    return min(value, 100)


def _int(choices: Dict[str, Any], key: str, default: int, low: int = 0, high: int = 999) -> int:
    value = choices.get(key, default)
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a whole number") from None


def kakita_5th_formula(character: Any, formulas: Dict[str, Any], choices: Dict[str, Any]) -> Dict[str, Any]:
    """Kakita Duelist 5th Dan's contested iaijutsu at phase 0: +5 if the
    opponent has no iaijutsu, the 3rd Dan's X per phase (attacker phase 0),
    and +5 per rank of iaijutsu over the opponent's contested skill."""
    data = character.to_dict()
    if character.school != "kakita_duelist" or school_dan(data) < 5:
        raise ValueError(f"{character.name} has no Kakita 5th Dan contest")
    if (character.adventure_state or {}).get("kakita_5th_dan_used"):
        raise ValueError("Kakita 5th Dan has already been used this round")
    f = dict(formulas.get("knack:iaijutsu:attack") or formulas["knack:iaijutsu"])
    bonuses = list(f.get("bonuses") or [])

    def add(label: str, amount: int) -> None:
        if amount:
            f["flat"] = (f.get("flat") or 0) + amount
            bonuses.append({"label": label, "amount": amount})

    if not choices.get("opponent_has_iaijutsu", True):
        add("opponent has no iaijutsu", 5)
    x = int(data.get("attack", 1) or 0) if school_dan(data) >= 3 else 0
    add("Kakita 3rd Dan (phase 0)", x * _int(choices, "defender_phase", 11, 0, 11))
    own = int((character.knacks or {}).get("iaijutsu") or 0)
    add("contested skill", 5 * max(0, own - _int(choices, "opponent_skill_rank", 4, 0, 10)))
    f["bonuses"] = bonuses
    f["label"] = "Kakita 5th Dan Contest"
    # A contested roll, not an attack against a TN.
    f["is_attack_type"] = False
    return f


def duel_damage_pool(formula: Dict[str, Any], weapon: tuple, extra_dice: int) -> Dict[str, int]:
    """The duel strike's damage: weapon + ring + school dice + a die per point
    of the strike's excess."""
    rolled = weapon[0] + (formula.get("damage_ring_val") or 2) + (formula.get("damage_extra_rolled") or 0) \
        + max(0, extra_dice)
    kept = weapon[1] + (formula.get("damage_extra_kept") or 0)
    return apply_dice_cap(rolled, kept, formula.get("damage_flat_bonus") or 0)


def kakita_5th_damage_pool(formula: Dict[str, Any], weapon: tuple, diff: int) -> Dict[str, int]:
    """Kakita 5th Dan's damage: +/- a rolled die per 5 the contest was won or
    lost by."""
    adjust = diff // 5 if diff >= 0 else -((-diff) // 5)
    rolled = max(0, weapon[0] + (formula.get("damage_extra_rolled") or 0)
                 + (formula.get("damage_ring_val") or 0) + adjust)
    kept = max(0, weapon[1] + (formula.get("damage_extra_kept") or 0))
    capped = apply_dice_cap(rolled, kept, formula.get("damage_flat_bonus") or 0)
    capped["adjust"] = adjust
    return capped


def weapon_dice(args: Dict[str, Any], default: Optional[tuple] = None) -> tuple:
    default = default or (4, 2)
    try:
        return (max(0, min(10, int(args.get("weapon_rolled", default[0])))),
                max(0, min(10, int(args.get("weapon_kept", default[1])))))
    except (TypeError, ValueError):
        raise ValueError("weapon dice must be whole numbers") from None
