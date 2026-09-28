"""The attack as the server makes it for the sheet (server-rolls-design Phase 7).

``attack_flags`` is the one definition of the attack-side school flags: the
sheet's ``schoolAbilities`` spreads it (pages.py), and the roll session reads
it to build the attack, judge the hit and check the result panel's actions.

``build_attack`` turns the attack modal's situational inputs (the TN, the
phases, the specialization boxes, a GM's extra bonus) plus what the server
knows (the Mantis postures, the Hiruma / Ide banks) into the rolled formula,
in the order the sheet always stacked them. ``attack_outcome`` is the hit,
Matsu's near miss, the Wave Man's miss raises and the extra damage dice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services import combat_math as cm
from app.services.void_spend import school_dan

MAX_EXTRA_LABEL = 60


def attack_flags(character_data: Dict[str, Any]) -> Dict[str, Any]:
    school = character_data.get("school") or ""
    dan = school_dan(character_data)
    attack = int(character_data.get("attack", 1) or 0)
    return {
        # Isawa Duelist 3rd Dan: trade -5 TN to be hit for +3X on the attack.
        "isawa_tn_trade": school == "isawa_duelist" and dan >= 3,
        "isawa_tn_trade_bonus": 3 * attack if school == "isawa_duelist" and dan >= 3 else 0,
        # Matsu 4th Dan: a double attack missing by less than 20 still hits.
        "matsu_near_miss": school == "matsu_bushi" and dan >= 4,
        # Otaku 5th Dan: trade 10 damage dice for an automatic serious wound.
        "otaku_trade_dice_for_sw": school == "otaku_bushi" and dan >= 5,
        # Courtier 4th Dan: a temp void point after a successful attack.
        "courtier_temp_vp_on_hit": school == "courtier" and dan >= 4,
        # Hida 3rd Dan: reroll X dice (2X on a counterattack) after the roll.
        "hida_reroll": school == "hida_bushi" and dan >= 3,
        "hida_reroll_x": attack if school == "hida_bushi" and dan >= 3 else 0,
        # Hida 5th Dan: a counterattack's excess is banked for a wound check.
        "hida_counterattack_wc_bonus": school == "hida_bushi" and dan >= 5,
        # Mantis Wave-Treader: 5th Dan adds the round's offensive postures;
        # 3rd Dan spends an action die for +X (offensive or defensive).
        "mantis_posture_accumulation": school == "mantis_wave_treader" and dan >= 5,
        "mantis_3rd_dan_offensive": school == "mantis_wave_treader" and dan >= 3,
        "mantis_3rd_dan_defensive": school == "mantis_wave_treader" and dan >= 3,
        "mantis_3rd_dan_x": attack if school == "mantis_wave_treader" and dan >= 3 else 0,
        # Shinjo Special: +2 per phase the attack's action die was held.
        "shinjo_phase_bonus": school == "shinjo_bushi",
        # Kakita 3rd Dan: +X per phase before the defender's next action.
        "kakita_3rd_dan_defender_phase_bonus_x": attack if school == "kakita_duelist" and dan >= 3 else 0,
        # Akodo 3rd Dan: a passed wound check banks a bonus for an attack.
        "akodo_wc_attack_bonus": school == "akodo_bushi" and dan >= 3,
    }


def current_posture(state: Dict[str, Any]) -> Optional[str]:
    history = state.get("mantis_posture_history") or []
    return history[-1] if history else None


def offensive_count(state: Dict[str, Any]) -> int:
    return sum(1 for p in state.get("mantis_posture_history") or [] if p == "offensive")


def _bonus(formula: Dict[str, Any], label: str, amount: int) -> None:
    formula["flat"] = (formula.get("flat") or 0) + amount
    formula["bonuses"] = list(formula.get("bonuses") or []) + [{"label": label, "amount": amount}]


def _int(choices: Dict[str, Any], key: str, low: int = 0, high: int = 999) -> Optional[int]:
    value = choices.get(key)
    if value is None or value == "":
        return None
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a whole number") from None


def build_attack(character: Any, formula: Dict[str, Any], choices: Dict[str, Any],
                 specs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The attack formula with its situational bonuses, and what it takes
    from the character's banks: ``{"formula", "consumes"}``. Raises
    ``ValueError`` for a bad input; changes nothing."""
    data = character.to_dict()
    flags = attack_flags(data)
    state = character.adventure_state or {}
    f = dict(formula)
    tn = _int(choices, "tn")
    if tn is None:
        raise ValueError("the attack needs a TN")
    f["attack_tn"] = tn
    # Mantis Wave-Treader Special: +5 in an offensive posture.
    if current_posture(state) == "offensive":
        _bonus(f, "offensive posture", 5)
    extra = _int(choices, "extra_bonus", -999, 999)
    if extra:
        label = str(choices.get("extra_label") or "").strip()[:MAX_EXTRA_LABEL] or "extra bonus"
        _bonus(f, label, extra)
    if flags["mantis_posture_accumulation"] and offensive_count(state):
        _bonus(f, "Mantis 5th Dan (offensive posture count)", offensive_count(state))
    accum = int(state.get("mantis_offensive_3rd_dan_accum") or 0)
    if flags["mantis_3rd_dan_offensive"] and accum:
        _bonus(f, "Mantis 3rd Dan (offensive)", accum)
    # Doji Artisan 5th Dan: +1 per 5 of the TN over 10.
    if f.get("doji_5th_dan_always"):
        doji = max(0, (tn - 10) // 5)
        if doji:
            f["flat"] = (f.get("flat") or 0) + doji
            f["doji_5th_dan_bonus"] = doji
    # Doji Artisan 4th Dan: the phase, against a target who has not attacked.
    phase = _int(choices, "doji_phase", 0, 10)
    if f.get("doji_4th_dan_untouched_target") and phase:
        f["flat"] = (f.get("flat") or 0) + phase
        f["doji_4th_dan_bonus"] = phase
        f["doji_4th_dan_phase"] = phase
    # Attack specializations: +10 per box ticked.
    picked = []
    for i in choices.get("specs") or []:
        if not isinstance(i, int) or not 0 <= i < len(specs) or i in picked:
            raise ValueError("no such attack specialization")
        picked.append(i)
    if picked:
        f["flat"] = (f.get("flat") or 0) + 10 * len(picked)
        f["attack_spec_bonus"] = 10 * len(picked)
        f["attack_spec_applied_texts"] = [specs[i].get("text") or "unspecified" for i in picked]
    die = _int(choices, "die_value", 0, 10)
    # Shinjo Special: +2 per phase the action die was held.
    shinjo_phase = _int(choices, "shinjo_phase", 0, 10)
    if f.get("shinjo_phase_bonus_attack") and flags["shinjo_phase_bonus"] and die is not None and shinjo_phase:
        bonus = 2 * max(0, shinjo_phase - die)
        if bonus:
            f["flat"] = (f.get("flat") or 0) + bonus
            f.update(shinjo_phase_bonus=bonus, shinjo_phase_bonus_phase=shinjo_phase,
                     shinjo_phase_bonus_die_value=die)
    # Kakita 3rd Dan: X per phase before the defender acts.
    x = flags["kakita_3rd_dan_defender_phase_bonus_x"]
    attacker = _int(choices, "attacker_phase", 0, 10)
    attacker = die if attacker is None else attacker
    defender = _int(choices, "kakita_defender_phase", 0, 10)
    if f.get("kakita_3rd_dan_defender_phase_bonus") and x and attacker is not None and defender is not None:
        bonus = x * max(0, defender - attacker)
        if bonus:
            f["flat"] = (f.get("flat") or 0) + bonus
            f.update(kakita_3rd_dan_bonus=bonus, kakita_3rd_dan_attacker_phase=attacker,
                     kakita_3rd_dan_defender_phase=defender, kakita_3rd_dan_x=x)
    # The banks an attack spends by being made.
    consumes = []
    hiruma = int(state.get("hiruma_banked_attack_bonus") or 0)
    if hiruma:
        f["flat"] = (f.get("flat") or 0) + hiruma
        f["hiruma_parry_bonus"] = hiruma
        consumes.append("hiruma_banked_attack_bonus")
    ide = int(state.get("ide_banked_tn_reduce") or 0)
    if ide:
        f["ide_tn_reduce"] = ide
        consumes.append("ide_banked_tn_reduce")
    return {"formula": f, "consumes": consumes}


def attack_outcome(formula: Dict[str, Any], total: int, wave_man_raised: int = 0,
                   near_miss_rule: bool = False) -> Dict[str, Any]:
    """Hit or miss for the roll's current ``total`` (which includes
    ``wave_man_raised`` points of W1 raises): the effective TN (a double
    attack's +20, less Ide's banked reduction), Matsu's near miss, and the
    extra damage dice - earned on the UNRAISED total, over the base TN for a
    double attack."""
    tn = int(formula.get("attack_tn") or 0)
    is_double = formula.get("attack_variant") == "double_attack"
    effective = max(0, cm.attack_effective_tn(tn, is_double) - int(formula.get("ide_tn_reduce") or 0))
    excess = total - effective
    hit, near = excess >= 0, False
    if not hit and near_miss_rule and is_double and excess >= -19:
        hit, near = True, True
    raw = total - wave_man_raised
    for_damage = raw - tn if is_double else raw - effective
    extra = cm.excess_to_extra_dice(for_damage) if hit and not near and for_damage >= 0 else 0
    return {"tn": tn, "effective_tn": effective, "hit": hit, "near_miss": near,
            "excess": excess, "extra_dice": extra}
