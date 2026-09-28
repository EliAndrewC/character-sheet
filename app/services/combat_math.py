"""Attack, damage and wound-check arithmetic, for rolls made on the server.

The Python twin of the pieces of ``app/static/js/roll_math.js`` that the
sheet's attack and wound-check modals use, needed because the GM's combat
tracker resolves NPC actions on the server (combat-design/design.md 4.4,
D7). Each function names its JS counterpart. Both sides are pinned to ONE
table of cases, ``tests/shared/combat_math_cases.json``, run by
``tests/test_combat_math.py`` and ``tests/js/shared_cases.test.js``: a change
to either side alone turns a suite red.

``damage_pool`` assembles the damage dice the way the sheet's
``atkComputeDamage`` does for the parts that apply to every character
(weapon, ring, school extra dice, excess, lunge, double attack, failed parry
with the Brotherhood / Mirumoto 4th Dan modifiers, Otaku 4th Dan, Ikoma 4th
Dan's 10-dice floor, Wave Man W3 / W9, the 10k10 cap, Shosuro 5th Dan). Posture- and per-round bonuses that live in the
sheet's interactive state (Mantis postures, Hiruma's post-parry bonus,
banked bonuses) are not modelled here; the GM opens the NPC's sheet for
those (design 4.4).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

WEAPONS: Dict[str, tuple] = {
    "katana": (4, 2),
    "spear": (3, 2),
    "wakizashi": (3, 2),
    "knife": (2, 2),
    "unarmed": (0, 2),
}


def excess_to_extra_dice(excess: int) -> int:
    """``excessToExtraDice``: one extra damage die per full 5 over the TN."""
    return excess // 5 if excess > 0 else 0


def attack_effective_tn(base_tn: int, is_double_attack: bool) -> int:
    """``attackEffectiveTn``: a double attack's TN is raised by 20."""
    return base_tn + 20 if is_double_attack else base_tn


def failed_parry_dice_reduction(total_extra: int, parry_skill: int, mode: str) -> int:
    """``failedParryDiceReduction``: "full", "half" (Mirumoto 4th Dan) or "none"."""
    if mode == "none":
        return total_extra
    reduce = parry_skill // 2 if mode == "half" else parry_skill
    return max(0, total_extra - reduce)


def wound_check_result(roll_total: int, light_wounds: int, bayushi_half_lw: bool = False) -> Dict[str, Any]:
    """``woundCheckResult``: pass iff the roll meets the light wounds; a
    failure costs 1 serious wound plus 1 per full 10 it fell short."""
    if roll_total >= light_wounds:
        return {"passed": True, "margin": roll_total - light_wounds, "serious_wounds": 0}
    effective = light_wounds // 2 if bayushi_half_lw else light_wounds
    margin = max(0, effective - roll_total)
    return {"passed": False, "margin": margin, "serious_wounds": margin // 10 + 1}


def wave_man_weapon_floor(rolled: int, copies: int) -> int:
    """``waveManWeaponFloor`` (W3): +1 rolled die per copy, up to 4."""
    r, n = max(0, int(rolled)), max(0, int(copies))
    if r >= 4 or n == 0:
        return r
    return min(4, r + n)


def wave_man_round_damage(total: int, copies: int) -> int:
    """``waveManRoundDamage`` (W4): up to the next multiple of 5, or +3 if
    already one, once per copy - applied LAST."""
    v, n = max(0, int(total)), max(0, int(copies))
    for _ in range(n):
        v = v + 3 if v % 5 == 0 else math.ceil(v / 5) * 5
    return v


def wave_man_miss_raise(total: int, tn: int, copies: int) -> Dict[str, Any]:
    """``waveManMissRaise`` (W1): +5 per copy while the attack would miss."""
    v, n, used = int(total), max(0, int(copies)), 0
    while v < tn and used < n:
        v += 5
        used += 1
    return {"total": v, "raises_used": used, "hit": v >= tn}


def wave_man_failed_parry_dice(parry_skill: int, copies: int) -> int:
    """``waveManFailedParryDice`` (W9): give back 2 per copy of what a failed
    parry removed, never more than it removed."""
    return min(2 * max(0, int(copies)), max(0, int(parry_skill)))


def damage_flags(character_data: Dict[str, Any]) -> Dict[str, bool]:
    """The attacker's school flags that change a damage roll. The sheet's
    ``schoolAbilities`` spreads this same dict (pages.py), so the browser's
    ``atkComputeDamage`` and ``damage_pool`` read one definition."""
    from app.services.void_spend import school_dan

    school = character_data.get("school") or ""
    dan = school_dan(character_data)
    return {
        # Otaku 4th Dan: lunge always rolls its extra damage die, even if parried
        "otaku_lunge_extra_die": school == "otaku_bushi" and dan >= 4,
        # Brotherhood 4th Dan: failed parries don't lower rolled damage dice
        "brotherhood_parry_no_reduce": school == "brotherhood_of_shinsei_monk" and dan >= 4,
        # Mirumoto 4th Dan: vs double attacks the auto SW stays; vs others the reduction halves
        "mirumoto_parry_modifier": school == "mirumoto_bushi" and dan >= 4,
        # Bayushi Special: +1k1 on damage per VP spent on the attack
        "bayushi_vp_damage": school == "bayushi_bushi",
        # Ikoma 4th Dan: 10-dice floor on damage for unparried attacks
        "ikoma_10_dice_floor": school == "ikoma_bard" and dan >= 4,
    }


def damage_pool(
    formula: Dict[str, Any],
    *,
    weapon: str = "katana",
    extra_dice: int = 0,
    failed_parry: bool = False,
    parry_skill: int = 0,
    flags: Dict[str, bool] | None = None,
) -> Dict[str, Any]:
    """The damage roll for a hit: ``{"rolled", "kept", "flat", "parts"}``,
    after the 10k10 cap. ``formula`` is the attack formula (its damage_*
    fields and attack_variant); ``flags`` are the attacker's school flags
    (``damage_flags``)."""
    from app.services.roll_engine import apply_dice_cap

    flags = flags or {}
    variant = formula.get("attack_variant") or "attack"
    is_lunge, is_double = variant == "lunge", variant == "double_attack"
    base_rolled, base_kept = WEAPONS.get(weapon, WEAPONS["katana"])
    wm_weapon = wave_man_weapon_floor(base_rolled, formula.get("wave_man_weapon_dice") or 0)
    ring_val = formula.get("damage_ring_val") or 2
    ring_name = formula.get("damage_ring_name") or "Fire"
    extra_r = formula.get("damage_extra_rolled") or 0
    extra_k = formula.get("damage_extra_kept") or 0
    flat = formula.get("damage_flat_bonus") or 0
    if flags.get("bayushi_vp_damage"):
        spent = formula.get("void_spent") or 0
        extra_r += spent
        extra_k += spent

    total_extra = extra_dice + (1 if is_lunge else 0) + (2 if is_double and failed_parry else 0)
    parts: List[str] = [f"{wm_weapon}k{base_kept} {weapon}", f"+{ring_val}k0 from {ring_name}"]
    if extra_r or extra_k:
        parts.append(f"+{extra_r}k{extra_k} from school")
    if extra_dice:
        parts.append(f"+{extra_dice}k0 extra from attack roll")
    if is_lunge:
        parts.append("+1k0 from Lunge")
    if is_double and failed_parry:
        parts.append("+2k0 from Double Attack (failed parry)")
    if failed_parry:
        if flags.get("brotherhood_parry_no_reduce"):
            mode = "none"
            parts.append("parry does not reduce dice (4th Dan)")
        elif flags.get("mirumoto_parry_modifier") and not is_double:
            mode = "half"
            parts.append(f"-{parry_skill // 2}k0 from failed parry (halved by 4th Dan)")
        else:
            mode = "full"
            parts.append(f"-{parry_skill}k0 from failed parry")
        total_extra = failed_parry_dice_reduction(total_extra, parry_skill, mode)
        recovered = wave_man_failed_parry_dice(parry_skill, formula.get("wave_man_failed_parry_dice") or 0)
        if recovered:
            total_extra += recovered
            parts.append(f"+{recovered}k0 recovered from Wave Man")
        if is_lunge and flags.get("otaku_lunge_extra_die"):
            total_extra += 1
            parts.append("+1k0 from Lunge (Otaku 4th Dan)")
    if wm_weapon > base_rolled:
        parts.append(f"+{wm_weapon - base_rolled}k0 weapon dice from Wave Man")
    if flat:
        parts.append(f"+{flat} flat")
    rolled = wm_weapon + ring_val + extra_r + total_extra
    if flags.get("ikoma_10_dice_floor") and not failed_parry and rolled < 10:
        parts.append(f"rolled {rolled} -> 10 (4th Dan, unparried)")
        rolled = 10
    capped = apply_dice_cap(rolled, base_kept + extra_k, flat)
    if capped["overflow_flat"]:
        parts.append(f"+{capped['overflow_flat']} from rolling above 10k10")
    return {
        "rolled": capped["rolled"], "kept": capped["kept"], "flat": capped["flat"], "parts": parts,
        # Shosuro Actor 5th Dan: the lowest 3 dice are added after the roll.
        "add_lowest_three": bool(formula.get("shosuro_5th_dan")),
    }
