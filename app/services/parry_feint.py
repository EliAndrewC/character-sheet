"""Parry and feint school abilities, decided once (server-rolls-design Phase 6).

``parry_feint_flags`` is the single definition: the sheet's ``schoolAbilities``
spreads it (pages.py) to decide what to show, and ``roll_sessions`` reads it
to apply the hooks after a live parry or feint and to check the result
panel's actions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.void_spend import school_dan

PARRY_KEYS = ("parry", "athletics:parry")


def is_feint(roll_key: str) -> bool:
    # There is no athletics (or other-ring) feint: "knack:feint" is the only one.
    return roll_key == "knack:feint"


def parry_feint_flags(character_data: Dict[str, Any]) -> Dict[str, Any]:
    school = character_data.get("school") or ""
    dan = school_dan(character_data)
    attack = int(character_data.get("attack", 1) or 0)
    return {
        # Mirumoto Special: 1 temp VP after any (non-athletics) parry.
        "mirumoto_temp_vp_on_parry": school == "mirumoto_bushi",
        # Mirumoto 3rd Dan: 2X points a round, +2 each on a parry or attack.
        "mirumoto_round_points": school == "mirumoto_bushi" and dan >= 3,
        "mirumoto_round_points_max": 2 * attack if school == "mirumoto_bushi" and dan >= 3 else 0,
        # Shinjo 3rd Dan: a parry lowers every unspent action die by X.
        "shinjo_3rd_dan_parry_decrement": attack if school == "shinjo_bushi" and dan >= 3 else 0,
        # Shinjo 5th Dan: bank a parry's excess for a future wound check.
        "shinjo_bank_parry_excess": school == "shinjo_bushi" and dan >= 5,
        # Hiruma 3rd Dan: a parry banks 2X for the next attack and damage.
        "hiruma_post_parry_bonus": school == "hiruma_scout" and dan >= 3,
        "hiruma_post_parry_amount": 2 * attack if school == "hiruma_scout" and dan >= 3 else 0,
        # Feint (rules/05-school_knacks.md): a successful feint - one that met
        # its TN and was not parried - gives anyone 1 temp VP; the Akodo
        # Special makes that 4, and 1 for an unsuccessful feint (GM ruling:
        # 4 in total, not 4 + 1).
        "feint_success_temp_vp": 4 if school == "akodo_bushi" else 1,
        "feint_failure_temp_vp": 1 if school == "akodo_bushi" else 0,
        "akodo_temp_vp_on_feint": school == "akodo_bushi",
        # Bayushi 4th Dan: a feint banks a free raise for a future attack.
        "bayushi_post_feint_raise": school == "bayushi_bushi" and dan >= 4,
        # Ide Special: a feint may bank -10 to the target's TN.
        "ide_feint_tn_reduce": school == "ide_diplomat",
        # Bayushi 3rd Dan feint damage / Shiba 3rd Dan parry damage.
        "bayushi_feint_damage": school == "bayushi_bushi" and dan >= 3,
        "bayushi_feint_damage_rolled": attack if school == "bayushi_bushi" and dan >= 3 else 0,
        "shiba_parry_damage": school == "shiba_bushi" and dan >= 3,
        "shiba_parry_damage_rolled": 2 * attack if school == "shiba_bushi" and dan >= 3 else 0,
        # Akodo 4th Dan: a void point after the roll for +5 on a combat roll.
        "akodo_combat_vp_free_raise": school == "akodo_bushi" and dan >= 4,
    }


def apply_post_roll_hooks(character: Any, roll_key: str) -> List[str]:
    """What a live parry or feint does to the character by itself, the moment
    it is rolled. Returns a note per effect. Does not commit. A feint's
    success-dependent effects are not here: ``feint_outcome`` decides them
    and ``roll_sessions`` keeps them in step with the roll's total."""
    flags = parry_feint_flags(character.to_dict())
    notes: List[str] = []
    state = dict(character.adventure_state or {})
    if roll_key == "parry" and flags["mirumoto_temp_vp_on_parry"]:
        character.current_temp_void_points = (character.current_temp_void_points or 0) + 1
        notes.append("Gained 1 temp void point from the parry (Mirumoto)")
    if roll_key in PARRY_KEYS and flags["shinjo_3rd_dan_parry_decrement"]:
        dec = flags["shinjo_3rd_dan_parry_decrement"]
        character.action_dice = [
            d if d.get("spent") else dict(d, value=int(d.get("value") or 0) - dec)
            for d in (character.action_dice or [])
        ]
        notes.append(f"Unspent action dice lowered by {dec} (Shinjo 3rd Dan)")
    if roll_key == "parry" and flags["hiruma_post_parry_bonus"]:
        state["hiruma_banked_attack_bonus"] = (int(state.get("hiruma_banked_attack_bonus") or 0)
                                               + flags["hiruma_post_parry_amount"])
        notes.append(f"+{flags['hiruma_post_parry_amount']} banked for the next attack and damage (Hiruma 3rd Dan)")
    if roll_key == "knack:feint" and flags["bayushi_post_feint_raise"]:
        state["bayushi_banked_feint_raise"] = int(state.get("bayushi_banked_feint_raise") or 0) + 5
        notes.append("+5 banked for a future attack (Bayushi 4th Dan)")
    character.adventure_state = state
    return notes


def highest_die_move(action_dice: List[Dict[str, Any]], spent_index: Optional[int],
                     phase: int) -> Optional[Dict[str, int]]:
    """A successful feint moves the character's highest action to the current
    phase - the phase of the die the feint spent. The highest UNSPENT die
    other than that one is lowered to ``phase``; a die already at or below
    the phase stays where it is (moving it would delay it)."""
    best = None
    for i, d in enumerate(action_dice or []):
        if i == spent_index or d.get("spent"):
            continue
        value = int(d.get("value") or 0)
        if value > phase and (best is None or value > best["from"]):
            best = {"index": i, "from": value, "to": phase}
    return best


def feint_outcome(flags: Dict[str, Any], total: int, tn: int, parried: bool) -> Dict[str, Any]:
    """Whether a feint at ``total`` succeeded against ``tn``, and the temp
    void points that earns. Met the TN and not parried is success."""
    met = total >= tn
    success = met and not parried
    gain = flags["feint_success_temp_vp"] if success else flags["feint_failure_temp_vp"]
    return {"met_tn": met, "success": success, "temp_vp": gain}
