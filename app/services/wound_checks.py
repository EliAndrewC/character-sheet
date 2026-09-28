"""The wound check as the server makes it for the sheet (server-rolls-design
Phase 8).

``wound_check_flags`` is the one definition of the wound-check school flags
the result panel and the server both read; ``build_wound_check`` adds what the
server knows (the Mantis defensive postures and accumulator, the Hida bank it
spends, Doji 5th Dan, a Daidoji counterattack) to the rolled formula.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.attack_rolls import attack_flags, current_posture
from app.services.void_spend import school_dan


def wound_check_flags(character_data: Dict[str, Any]) -> Dict[str, Any]:
    school = character_data.get("school") or ""
    dan = school_dan(character_data)
    attack = int(character_data.get("attack", 1) or 0)
    return {
        # Akodo / Yogo 4th Dan: a void point after a wound check is +5.
        "wc_vp_free_raise": (school == "akodo_bushi" and dan >= 4) or (school == "yogo_warden" and dan >= 4),
        # Yogo Warden Special: a temp void point per serious wound taken.
        "yogo_temp_vp_on_sw": school == "yogo_warden",
        # Isawa 5th Dan: a passed check's margin is banked for a later one.
        "isawa_bank_wc_excess": school == "isawa_duelist" and dan >= 5,
        # Akodo 3rd Dan: a passed check banks (margin / 5) x attack for an attack.
        "akodo_attack_skill": attack if school == "akodo_bushi" and dan >= 3 else 0,
        # Daidoji 3rd Dan: X free raises on a wound check from a hit you countered.
        "daidoji_counterattack_raises": school == "daidoji_yojimbo" and dan >= 3,
        "daidoji_counterattack_raises_amount": attack if school == "daidoji_yojimbo" and dan >= 3 else 0,
        # Akodo 5th Dan: void points spent after taking damage reflect it.
        "akodo_reflect_damage": school == "akodo_bushi" and dan >= 5,
    }


def daidoji_counterattack(character: Any, party: List[Any]) -> Optional[Dict[str, Any]]:
    """Who can have counterattacked for this character: themselves at Daidoji
    3rd Dan, else the first visible Daidoji of their party at 3rd Dan."""
    own = wound_check_flags(character.to_dict())
    if own["daidoji_counterattack_raises"]:
        x = own["daidoji_counterattack_raises_amount"]
        return {"label": "Hit was counterattacked", "raises": x, "bonus": 5 * x}
    for p in party:
        flags = wound_check_flags(p.to_dict())
        if flags["daidoji_counterattack_raises"]:
            x = flags["daidoji_counterattack_raises_amount"]
            return {"label": f"{p.name} counterattacked this hit", "raises": x, "bonus": 5 * x}
    return None


def akodo_banked_bonus(margin: int, attack_skill: int) -> int:
    """``akodoBankedBonus``: (margin / 5) x attack skill."""
    if margin <= 0 or attack_skill <= 0:
        return 0
    return (margin // 5) * attack_skill


def _bonus(formula: Dict[str, Any], label: str, amount: int) -> None:
    formula["flat"] = (formula.get("flat") or 0) + amount
    formula["bonuses"] = list(formula.get("bonuses") or []) + [{"label": label, "amount": amount}]


def build_wound_check(character: Any, formula: Dict[str, Any], light_wounds: int, *,
                      strike: bool, daidoji: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """``{"formula", "consumes"}``: the check against ``light_wounds`` with
    its automatic bonuses. An iaijutsu strike's check never rerolls 10s."""
    data = character.to_dict()
    flags = attack_flags(data)
    state = character.adventure_state or {}
    f = dict(formula, light_wounds=light_wounds)
    if current_posture(state) == "defensive":
        _bonus(f, "defensive posture", 5)
    defensive = sum(1 for p in state.get("mantis_posture_history") or [] if p == "defensive")
    if flags["mantis_posture_accumulation"] and defensive:
        _bonus(f, "Mantis 5th Dan (defensive posture count)", defensive)
    accum = int(state.get("mantis_defensive_3rd_dan_accum") or 0)
    if flags["mantis_3rd_dan_defensive"] and accum:
        _bonus(f, "Mantis 3rd Dan (defensive)", accum)
    if strike:
        f.update(reroll_tens=False, no_reroll_reason="iaijutsu_strike", iaijutsu_strike=True)
    consumes = []
    hida = int(state.get("hida_banked_wc_bonus") or 0)
    if hida:
        _bonus(f, "Hida 5th Dan counterattack excess", hida)
        f["hida_counterattack_bonus"] = hida
        consumes.append("hida_banked_wc_bonus")
    if f.get("doji_5th_dan_wc"):
        doji = max(0, (light_wounds - 10) // 5)
        if doji:
            _bonus(f, "Doji 5th Dan", doji)
            f["doji_5th_dan_bonus"] = doji
    if daidoji:
        _bonus(f, f"Daidoji counterattack ({daidoji['raises']} free raises)", daidoji["bonus"])
        f["daidoji_counterattack_bonus"] = daidoji["bonus"]
        f["daidoji_counterattack_raises"] = daidoji["raises"]
    return {"formula": f, "consumes": consumes}
