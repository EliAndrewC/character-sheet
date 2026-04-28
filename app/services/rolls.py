"""Skill roll computation for the L7R Character Builder.

Computes the dice rolled, dice kept, flat bonuses, and free raises for
any skill given a full character data dict.

A "free raise" is a flat +5 bonus to the roll.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
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
        elif self.flat_bonus < 0:
            parts.append(f"- {abs(self.flat_bonus)}")
        return " ".join(parts)

    @property
    def tooltip(self) -> str:
        return "\n".join(self.tooltip_lines)

    @property
    def parenthetical(self) -> str:
        """Bonus breakdown shown next to the dice formula on the sheet.

        Skips the leading "Base: ..." line. When there is exactly one bonus
        whose description starts with "+N from ...", strips the redundant
        "+N " (since N is already in the dice formula) so e.g. ``+5 from
        Charming`` becomes ``from Charming``. With two or more bonuses, every
        "+N from ..." stays intact so the player can see each contribution.
        """
        parts = list(self.tooltip_lines[1:])
        if len(parts) == 1:
            parts[0] = re.sub(r"^\+\d+ from ", "from ", parts[0])
        return ", ".join(parts)


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
    "worldly": (["commerce", "underworld"], 1),
}

# Campaign advantage -> (skill_ids, unconditional_free_raises). The
# unconditional portion always applies to flat_bonus. Additional conditional
# bonuses are listed in _CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES below.
_CAMPAIGN_ADVANTAGE_SKILL_BONUSES = {
    # Highest Regard: 2 free raises on bragging/intimidation with non-Wasp,
    # 4 free raises with Wasp clan members.
    "highest_regard": (["bragging", "intimidation"], 2),
}

# Campaign advantage -> (skill_ids, extra_free_raises, condition_text). The
# extra raises are added on top of the unconditional portion when the
# condition applies.
_CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES = {
    "highest_regard": (["bragging", "intimidation"], 2, "vs Wasp"),
}

# Discerning gives different bonuses to different skills
_DISCERNING_BONUSES = {"interrogation": 1, "investigation": 2}

# Skill synergies: skill_id -> (boosted_skills, raises_per_rank)
# Some entries are conditional and surfaced as a note rather than baked into
# flat_bonus: see the special cases in compute_skill_roll's synergy loop.
_SKILL_SYNERGIES = {
    "history": (["culture", "law", "strategy", "heraldry"], 1),
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


def compute_skill_roll(
    skill_id: str,
    character_data: dict,
    party_members: Optional[List[dict]] = None,
) -> RollResult:
    """Compute the full roll for a given skill based on character state.

    Free raises are converted to +5 flat bonus each and included in
    flat_bonus. The tooltip shows each source with its contribution.

    *party_members* is the optional list of OTHER characters in the same
    gaming group (each with ``name``, ``advantages``, ``disadvantages``,
    ``campaign_advantages``, ``campaign_disadvantages``). Some group-wide
    disadvantages — currently just Thoughtless — surface as inline notes on
    specific skills (Thoughtless ⇒ +10 to opponents' Manipulation on every
    other party member's Tact roll).
    """
    skill_def = SKILLS.get(skill_id)
    if skill_def is None:
        return RollResult()

    skills = character_data.get("skills", {})
    rank = skills.get(skill_id, 0)
    unskilled = rank <= 0

    rings = character_data.get("rings", {})
    ring_val = rings.get(skill_def.ring.value, 2)

    result = RollResult()
    # Unskilled rolls don't add the rank to the dice pool, get a -10 penalty
    # if the skill is advanced, and never reroll 10s. All other bonuses still
    # apply (free raises, honor/recognition multipliers, synergies).
    result.rolled = ring_val if unskilled else rank + ring_val
    result.kept = ring_val

    # We'll collect bonus explanations, then build the tooltip at the end
    bonus_parts = []  # list of (amount, description) for the parenthetical

    if unskilled and skill_def.is_advanced:
        result.flat_bonus -= 10

    # --- School technique bonuses (extra dice) ---
    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {})
    dan = compute_dan(knacks) if knacks else 0
    bonuses = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})

    # 1st Dan: extra rolled die
    if dan >= 1 and bonuses.get("first_dan_extra_die"):
        if skill_id in bonuses["first_dan_extra_die"]:
            result.rolled += 1
            bonus_parts.append((0, "+1 rolled die from 1st Dan"))

    # Flexible 1st Dan (Kitsune Warden, Isawa Ishi, Priest, Shugenja):
    # the player picks which rolls get the extra die via
    # technique_choices.first_dan_choices.
    technique_choices = character_data.get("technique_choices") or {}
    if (
        dan >= 1
        and "first_dan_extra_die" in bonuses
        and bonuses.get("first_dan_extra_die") is None
    ):
        chosen_1st = technique_choices.get("first_dan_choices") or []
        if skill_id in chosen_1st:
            result.rolled += 1
            bonus_parts.append((0, "+1 rolled die from 1st Dan"))

    # 2nd Dan: free raise = +5
    if dan >= 2 and bonuses.get("second_dan_free_raise"):
        if skill_id == bonuses["second_dan_free_raise"]:
            result.flat_bonus += FREE_RAISE_VALUE
            bonus_parts.append((FREE_RAISE_VALUE, "+5 from 2nd Dan"))

    # Flexible 2nd Dan (Kitsune Warden, Ide Diplomat, Isawa Ishi, Shugenja,
    # Suzume Overseer): the player's chosen roll type lives in
    # technique_choices.second_dan_choice.
    if (
        dan >= 2
        and "second_dan_free_raise" in bonuses
        and bonuses.get("second_dan_free_raise") is None
    ):
        if technique_choices.get("second_dan_choice") == skill_id:
            result.flat_bonus += FREE_RAISE_VALUE
            bonus_parts.append((FREE_RAISE_VALUE, "+5 from 2nd Dan"))

    # Mantis Wave-Treader 2nd Dan: flexible-with-its-own-key. Same shape as
    # the generic flexible 2nd Dan but writes to a school-specific key.
    if (
        dan >= 2
        and school_id == "mantis_wave_treader"
        and technique_choices.get("mantis_2nd_dan_free_raise") == skill_id
    ):
        result.flat_bonus += FREE_RAISE_VALUE
        bonus_parts.append((FREE_RAISE_VALUE, "+5 from 2nd Dan"))

    # Priest 2nd Dan (self): free raise on Honor-bonus rolls
    # (bragging, precepts; sincerity only on open rolls).
    if school_id == "priest" and dan >= 2 and skill_id in ("bragging", "precepts", "sincerity"):
        if skill_id == "sincerity":
            bonus_parts.append((0, "+5 on open rolls from Priest 2nd Dan"))
        else:
            result.flat_bonus += FREE_RAISE_VALUE
            bonus_parts.append((FREE_RAISE_VALUE, "+5 from Priest 2nd Dan"))
    # Priest 2nd Dan (ally): same bonus if any party member is a Priest dan >= 2.
    elif skill_id in ("bragging", "precepts", "sincerity") and party_members:
        ally_priest = next(
            (p for p in party_members
             if p.get("school") == "priest" and (p.get("dan") or 0) >= 2),
            None,
        )
        if ally_priest is not None:
            ally_name = ally_priest.get("name", "an ally")
            if skill_id == "sincerity":
                bonus_parts.append(
                    (0, f"+5 on open rolls from {ally_name}'s Priest 2nd Dan")
                )
            else:
                result.flat_bonus += FREE_RAISE_VALUE
                bonus_parts.append(
                    (FREE_RAISE_VALUE, f"+5 from {ally_name}'s Priest 2nd Dan")
                )

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
        elif adv_id == "kind_eye" and skill_id in ("tact", "sincerity"):
            # 4 free raises (+20) vs servants and the mistreated. Conditional,
            # so it's a note only - never added to flat_bonus.
            bonus_parts.append((0, "+20 for servants and the mistreated"))

    # --- Campaign advantage bonuses (e.g. Highest Regard) ---
    campaign_advantages = character_data.get("campaign_advantages", [])
    for adv_id in campaign_advantages:
        if adv_id in _CAMPAIGN_ADVANTAGE_SKILL_BONUSES:
            skill_list, raises = _CAMPAIGN_ADVANTAGE_SKILL_BONUSES[adv_id]
            if skill_id in skill_list:
                amount = raises * FREE_RAISE_VALUE
                result.flat_bonus += amount
                adv_name = CAMPAIGN_ADVANTAGES[adv_id].name
                bonus_parts.append((amount, f"+{amount} from {adv_name}"))
        if adv_id in _CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES:
            skill_list, extra_raises, cond_text = (
                _CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES[adv_id]
            )
            if skill_id in skill_list:
                extra = extra_raises * FREE_RAISE_VALUE
                bonus_parts.append((0, f"+{extra} more {cond_text}"))

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
    if "thoughtless" in disadvantages and skill_id == "tact":
        bonus_parts.append(
            (0, "+20 to opponents' Manipulation from Thoughtless")
        )

    # --- Party-wide disadvantage notes from OTHER members ---
    # Thoughtless on a teammate adds +10 to opponents' Manipulation rolls
    # against allies — this character. Only Tact reflects this (Sincerity
    # is unaffected).
    if skill_id == "tact" and party_members:
        for member in party_members:
            member_disadvantages = member.get("disadvantages") or []
            if "thoughtless" in member_disadvantages:
                member_name = member.get("name", "an ally")
                bonus_parts.append(
                    (0, f"+10 to opponents' Manipulation from {member_name}'s Thoughtless")
                )

    # --- Skill synergies (free raises = +5 per rank) ---
    for source_id, (boosted, per_rank) in _SKILL_SYNERGIES.items():
        if skill_id in boosted:
            source_rank = skills.get(source_id, 0)
            if source_rank > 0:
                raises = source_rank * per_rank
                amount = raises * FREE_RAISE_VALUE
                source_name = SKILLS[source_id].name
                # Acting → Sneaking is conditional: the free raises only
                # apply on "blending into a crowd" rolls, not on
                # "remaining unseen" rolls. History → Heraldry is similarly
                # conditional: the raises only apply to questions about
                # places, families, and institutions - not specific
                # individuals. Both live in tooltip_lines as a conditional
                # note rather than baked into flat_bonus.
                if skill_id == "sneaking" and source_id == "acting":
                    bonus_parts.append((0, f"+{amount} for blending in"))
                elif skill_id == "heraldry" and source_id == "history":
                    bonus_parts.append((0, f"+{amount} for non-individuals"))
                else:
                    result.flat_bonus += amount
                    bonus_parts.append((amount, f"+{amount} from {source_name}"))

    # --- Honor bonus ---
    # Sincerity's honor bonus only applies on open rolls, so it's shown as a
    # conditional note rather than being baked into the flat bonus.
    honor = character_data.get("honor", 1.0)
    if skill_id in _HONOR_BONUS_SKILLS:
        mult = _HONOR_BONUS_SKILLS[skill_id]
        bonus = int(mult * honor)
        if bonus > 0:
            if skill_id == "sincerity":
                bonus_parts.append((0, f"+{bonus} from Honor on open rolls"))
            else:
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

    # --- Courtier 5th Dan: +Air on TN/contested rolls ---
    from app.services.dice import _5TH_DAN_TN_ALWAYS, _5TH_DAN_TN_NEVER
    if school_id == "courtier" and dan >= 5:
        air_val = rings.get("Air", 2)
        if skill_id in _5TH_DAN_TN_ALWAYS:
            result.flat_bonus += air_val
            bonus_parts.append((air_val, f"+{air_val} from 5th Dan"))
        elif skill_id not in _5TH_DAN_TN_NEVER:
            bonus_parts.append((0, f"+{air_val} from 5th Dan if TN/contested"))

    # --- 3rd Dan: adventure free raises (not added to flat_bonus, shown separately) ---
    if dan >= 3 and bonuses.get("third_dan"):
        t3 = bonuses["third_dan"]
        applicable = set(t3["applicable_to"])
        # Kitsune Warden 3rd Dan: extend with player-chosen skills
        # (technique_choices.third_dan_skill_choices). Iaijutsu is dropped
        # defensively even if it sneaks into the picks.
        if t3.get("applicable_to_choices_count"):
            for pick in (technique_choices.get("third_dan_skill_choices") or []):
                if pick and pick != "iaijutsu":
                    applicable.add(pick)
        if skill_id in applicable:
            source_rank = skills.get(t3["source_skill"], 0)
            available = 2 * source_rank
            max_per_roll = source_rank
            if available > 0:
                result.adventure_raises_available = available
                result.adventure_raises_max_per_roll = max_per_roll
                bonus_parts.append(
                    (0, f"{available} free raises/adventure from 3rd Dan")
                )

    # Apply L7R 10k10 caps: rolled past 10 -> kept, kept past 10 -> +2 each.
    if result.rolled > 10:
        result.kept += result.rolled - 10
        result.rolled = 10
    if result.kept > 10:
        overflow = result.kept - 10
        bonus = 2 * overflow
        result.flat_bonus += bonus
        bonus_parts.append((bonus, f"+{bonus} from extra dice above 10k10"))
        result.kept = 10

    if unskilled:
        if skill_def.is_advanced:
            bonus_parts.append((0, "unskilled: -10 advanced, no 10s reroll"))
        else:
            bonus_parts.append((0, "unskilled: no 10s reroll"))

    # Build tooltip: "4k2 + 9 (breakdown)"
    result.tooltip_lines.append(
        f"Base: {rank} ({skill_def.name}) + {ring_val} ({skill_def.ring.value})"
    )
    for _, desc in bonus_parts:
        result.tooltip_lines.append(desc)

    return result
