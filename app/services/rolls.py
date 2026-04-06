"""Skill roll computation for the L7R Character Builder.

Computes the dice rolled, dice kept, flat bonuses, and free raises for
any skill given a full character data dict.

A "free raise" is a flat +5 bonus to the roll.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.game_data import (
    ADVANTAGES,
    SCHOOL_TECHNIQUE_BONUSES,
    SCHOOLS,
    SKILLS,
)

FREE_RAISE_VALUE = 5


@dataclass
class RollResult:
    rolled: int = 0
    kept: int = 0
    flat_bonus: int = 0
    adventure_raises_available: int = 0
    adventure_raises_max_per_roll: int = 0
    tooltip_lines: List[str] = field(default_factory=list)

    @property
    def display(self) -> str:
        if self.rolled == 0:
            return ""
        parts = [f"{self.rolled}k{self.kept}"]
        if self.flat_bonus > 0:
            parts.append(f"+ {self.flat_bonus}")
        return " ".join(parts)

    @property
    def tooltip(self) -> str:
        return "\n".join(self.tooltip_lines)


def compute_dan(knacks: dict) -> int:
    """Dan = minimum rank among school knacks."""
    if not knacks:
        return 0
    return min(knacks.values())


# Advantage -> (skill_ids, free_raises_count)
_ADVANTAGE_SKILL_BONUSES = {
    "charming": (["etiquette", "culture"], 1),
    "fierce": (["bragging", "intimidation"], 1),
    "discerning": (["interrogation"], 1),  # investigation handled separately
    "genealogist": (["heraldry"], 2),
    "tactician": (["strategy", "history"], 1),
    "worldly_advantage": (["commerce", "underworld"], 1),
}

# Discerning gives different bonuses to different skills
_DISCERNING_BONUSES = {"interrogation": 1, "investigation": 2}

# Skill synergies: skill_id -> (boosted_skills, raises_per_rank)
_SKILL_SYNERGIES = {
    "history": (["culture", "law", "strategy"], 1),
    "acting": (["sincerity", "intimidation", "sneaking"], 1),
}

# Skills that get honor bonus and the multiplier
_HONOR_BONUS_SKILLS = {
    "bragging": 2,    # +2x Honor (also gets +2x Recognition)
    "precepts": 2,    # +2x Honor
    "sincerity": 2,   # +2x Honor (on open rolls)
}

_RECOGNITION_BONUS_SKILLS = {
    "bragging": 2,    # +2x Recognition
}


def compute_skill_roll(skill_id: str, character_data: dict) -> RollResult:
    """Compute the full roll for a given skill based on character state.

    Free raises are converted to +5 flat bonus each and included in
    flat_bonus. The tooltip shows each source with its contribution.
    """
    skill_def = SKILLS.get(skill_id)
    if skill_def is None:
        return RollResult()

    skills = character_data.get("skills", {})
    rank = skills.get(skill_id, 0)
    if rank <= 0:
        return RollResult()

    rings = character_data.get("rings", {})
    ring_val = rings.get(skill_def.ring.value, 2)

    result = RollResult()
    result.rolled = rank + ring_val
    result.kept = ring_val

    # We'll collect bonus explanations, then build the tooltip at the end
    bonus_parts = []  # list of (amount, description) for the parenthetical

    # --- School technique bonuses (extra dice) ---
    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {})
    dan = compute_dan(knacks) if knacks else 0
    bonuses = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})

    # 1st Dan: extra rolled die
    if dan >= 1 and bonuses.get("first_dan_extra_die"):
        if skill_id in bonuses["first_dan_extra_die"]:
            result.rolled += 1
            bonus_parts.append((0, "+1 rolled die from 1st Dan technique"))

    # 2nd Dan: free raise = +5
    if dan >= 2 and bonuses.get("second_dan_free_raise"):
        if skill_id == bonuses["second_dan_free_raise"]:
            result.flat_bonus += FREE_RAISE_VALUE
            bonus_parts.append((FREE_RAISE_VALUE, "+5 from 2nd Dan technique"))

    # --- Advantage bonuses (free raises = +5 each) ---
    advantages = character_data.get("advantages", [])
    for adv_id in advantages:
        if adv_id == "discerning" and skill_id in _DISCERNING_BONUSES:
            raises = _DISCERNING_BONUSES[skill_id]
            amount = raises * FREE_RAISE_VALUE
            result.flat_bonus += amount
            adv_name = ADVANTAGES[adv_id].name
            bonus_parts.append((amount, f"+{amount} from {adv_name}"))
        elif adv_id in _ADVANTAGE_SKILL_BONUSES:
            skill_list, raises = _ADVANTAGE_SKILL_BONUSES[adv_id]
            if skill_id in skill_list:
                amount = raises * FREE_RAISE_VALUE
                result.flat_bonus += amount
                adv_name = ADVANTAGES[adv_id].name
                bonus_parts.append((amount, f"+{amount} from {adv_name}"))

    # --- Higher Purpose & Specialization (conditional bonuses from advantage_details) ---
    advantage_details = character_data.get("advantage_details", {})
    if "higher_purpose" in advantages:
        hp = advantage_details.get("higher_purpose", {})
        hp_skills = hp.get("skills", [])
        hp_text = hp.get("text", "your cause")
        if skill_id in hp_skills:
            result.flat_bonus += FREE_RAISE_VALUE
            bonus_parts.append(
                (FREE_RAISE_VALUE, f"+{FREE_RAISE_VALUE} from Higher Purpose when related to {hp_text}")
            )

    if "specialization" in advantages:
        sp = advantage_details.get("specialization", {})
        sp_skills = sp.get("skills", [])
        sp_text = sp.get("text", "your specialization")
        if skill_id in sp_skills:
            amount = 2 * FREE_RAISE_VALUE
            result.flat_bonus += amount
            bonus_parts.append(
                (amount, f"+{amount} from Specialization when related to {sp_text}")
            )

    # --- Disadvantage notes (no mechanical roll change, but contextual info) ---
    disadvantages = character_data.get("disadvantages", [])
    if "transparent" in disadvantages and skill_id == "sincerity":
        bonus_parts.append(
            (0, "roll always considered 5 for the purpose of lying or concealing information")
        )
    if "unkempt" in disadvantages and skill_id == "culture":
        bonus_parts.append(
            (0, "-10 in the eyes of those who judge the unkempt")
        )
    if "thoughtless" in disadvantages and skill_id in ("tact", "sincerity"):
        bonus_parts.append(
            (0, "+20 to opponents' Manipulation against you (+10 against your allies)")
        )

    # --- Skill synergies (free raises = +5 per rank) ---
    for source_id, (boosted, per_rank) in _SKILL_SYNERGIES.items():
        if skill_id in boosted:
            source_rank = skills.get(source_id, 0)
            if source_rank > 0:
                raises = source_rank * per_rank
                amount = raises * FREE_RAISE_VALUE
                source_name = SKILLS[source_id].name
                result.flat_bonus += amount
                bonus_parts.append((amount, f"+{amount} from {source_name}"))

    # --- Honor bonus ---
    honor = character_data.get("honor", 1.0)
    if skill_id in _HONOR_BONUS_SKILLS:
        mult = _HONOR_BONUS_SKILLS[skill_id]
        bonus = int(mult * honor)
        if bonus > 0:
            result.flat_bonus += bonus
            bonus_parts.append((bonus, f"+{bonus} from Honor"))

    # --- Recognition bonus ---
    recognition = character_data.get("recognition", 1.0)
    if skill_id in _RECOGNITION_BONUS_SKILLS:
        mult = _RECOGNITION_BONUS_SKILLS[skill_id]
        bonus = int(mult * recognition)
        if bonus > 0:
            result.flat_bonus += bonus
            bonus_parts.append((bonus, f"+{bonus} from Recognition"))

    # --- 3rd Dan: adventure free raises (not added to flat_bonus, shown separately) ---
    if dan >= 3 and bonuses.get("third_dan"):
        t3 = bonuses["third_dan"]
        if skill_id in t3["applicable_to"]:
            source_rank = skills.get(t3["source_skill"], 0)
            available = 2 * source_rank
            max_per_roll = source_rank
            if available > 0:
                result.adventure_raises_available = available
                result.adventure_raises_max_per_roll = max_per_roll
                source_name = SKILLS.get(t3["source_skill"])
                sname = source_name.name if source_name else t3["source_skill"]
                bonus_parts.append(
                    (0, f"{available} free raises/adventure, max {max_per_roll}/roll from {sname}")
                )

    # Build tooltip: "4k2 + 9 (breakdown)"
    result.tooltip_lines.append(
        f"Base: {rank} ({skill_def.name}) + {ring_val} ({skill_def.ring.value})"
    )
    for _, desc in bonus_parts:
        result.tooltip_lines.append(desc)

    return result
