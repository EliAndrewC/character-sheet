"""Dice roll formula builder for the L7R Character Builder.

This module is the single source of truth for: building roll formulas for
every clickable item on the character sheet (skills, school knacks, attack,
parry, athletics rolls), applying L7R dice cap rules, and computing whether
a character is currently Impaired.

The actual dice rolling happens in the browser via static/js/dice.js for
animation responsiveness; this module precomputes the formula (rolled, kept,
flat bonus, conditional alternatives) that the client uses.

The existing services/rolls.py drives the inline tooltip display on the
sheet and stays untouched. This module shares its bonus tables and constants.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from app.game_data import (
    SCHOOL_KNACKS,
    SCHOOL_TECHNIQUE_BONUSES,
    SCHOOLS,
    SKILLS,
    Ring,
)
from app.services.rolls import (
    FREE_RAISE_VALUE,
    _ADVANTAGE_SKILL_BONUSES,
    _CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES,
    _CAMPAIGN_ADVANTAGE_SKILL_BONUSES,
    _DISCERNING_BONUSES,
    _HONOR_BONUS_SKILLS,
    _RECOGNITION_BONUS_SKILLS,
    _SKILL_SYNERGIES,
    compute_dan,
)
from app.game_data import ADVANTAGES, CAMPAIGN_ADVANTAGES


# TN/contested skill groupings for 5th Dan court bonuses (Courtier, Doji Artisan)
# Skills that are ALWAYS TN or contested (bonus auto-applies)
_5TH_DAN_TN_ALWAYS = frozenset({
    "sneaking", "interrogation", "manipulation", "heraldry", "investigation",
})
# Skills that are NEVER TN or contested (bonus never applies)
_5TH_DAN_TN_NEVER = frozenset({
    "etiquette", "acting", "history",
})
# All other skills: sometimes TN/contested (checkbox on roll result)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


# Knacks that the character sheet does not allow rolling directly
# (e.g. passive lookups like Discern Honor / Worldliness, or social
# probes that don't reduce to a single roll). Mirrors the same list in
# templates/character/sheet.html.
NON_ROLLABLE_KNACKS = frozenset({
    "discern_honor",
    "worldliness",
    "otherworldliness",
    "conviction",
})


# Combat rolls eligible for the Mantis Wave-Treader 2nd Dan free raise.
# Initiative is excluded per the rules text - a free raise has no meaning on
# an initiative roll.
_MANTIS_2ND_DAN_COMBAT_ROLLS = frozenset({"attack", "damage", "parry", "wound_check"})


def mantis_2nd_dan_eligible_choices(school_id: str) -> frozenset:
    """Return the set of valid roll-type ids the Mantis 2nd Dan free raise
    may target for a character of the given school.

    Includes: all SKILLS ids, the school's rollable knacks (NON_ROLLABLE_KNACKS
    filtered out - so no worldliness), and the combat rolls in
    _MANTIS_2ND_DAN_COMBAT_ROLLS. Initiative is never eligible.

    Returns an empty frozenset for non-Mantis schools.
    """
    if school_id != "mantis_wave_treader":
        return frozenset()
    school = SCHOOLS.get(school_id)
    knack_ids: set = set()
    if school is not None:
        for kid in school.school_knacks:
            if kid not in NON_ROLLABLE_KNACKS:
                knack_ids.add(kid)
    return frozenset(set(SKILLS.keys()) | knack_ids | set(_MANTIS_2ND_DAN_COMBAT_ROLLS))


@dataclass
class RollFormula:
    """A roll formula for one clickable item on the sheet.

    The client rolls the dice using ``rolled`` and ``kept``; reroll-10s rules
    are governed by ``reroll_tens`` (False if Impaired). The base total is the
    sum of kept dice plus ``flat``. Each entry in ``alternatives`` represents
    a *conditional* bonus that may add ``extra_flat`` if the condition applies.

    ``bonuses`` is the structured breakdown of the unconditional ``flat``
    total: each entry is ``{"label": str, "amount": int}`` where the sum of
    amounts equals ``flat``. The result modal renders this as either a single
    line (when there is exactly one bonus) or a "+N total flat bonus" line
    with sub-bullets (when there are several).
    """
    label: str
    rolled: int
    kept: int
    flat: int = 0
    reroll_tens: bool = True
    no_reroll_reason: str = ""
    unskilled_skill_name: str = ""
    alternatives: List[dict] = field(default_factory=list)
    bonuses: List[dict] = field(default_factory=list)
    adventure_raises_max_per_roll: int = 0
    courtier_5th_dan_optional: int = 0
    doji_5th_dan_always: bool = False
    doji_5th_dan_optional: bool = False
    shosuro_5th_dan: bool = False
    is_damage_roll: bool = False
    otherworldliness_capacity: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _add_flat_bonus(formula: "RollFormula", label: str, amount: int) -> None:
    """Append a labeled flat bonus and update the running total."""
    if amount == 0:
        return
    formula.flat += amount
    formula.bonuses.append({"label": label, "amount": amount})


def _finalize_caps(formula: "RollFormula") -> None:
    """Apply L7R 10k10 caps in-place at the end of formula construction.

    Overflow from the kept-dice cap appears as a labeled bonus so the modal
    shows where the +2-per-die bonus came from.
    """
    if formula.rolled > 10:
        formula.kept += formula.rolled - 10
        formula.rolled = 10
    if formula.kept > 10:
        overflow = formula.kept - 10
        _add_flat_bonus(formula, f"extra dice above 10k10 (+2 \u00d7 {overflow})", 2 * overflow)
        formula.kept = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reroll_fields(character_data: dict) -> dict:
    """Return ``reroll_tens`` and ``no_reroll_reason`` for a formula."""
    if is_impaired(character_data):
        return {"reroll_tens": False, "no_reroll_reason": "impaired"}
    return {"reroll_tens": True, "no_reroll_reason": ""}


def is_impaired(character_data: dict) -> bool:
    """True iff current_serious_wounds >= Earth ring."""
    earth = character_data.get("rings", {}).get("Earth", 2)
    return character_data.get("current_serious_wounds", 0) >= earth


def apply_dice_caps(rolled: int, kept: int) -> Tuple[int, int, int]:
    """Apply L7R dice caps.

    * Rolled dice past 10 become additional kept dice.
    * Kept dice past 10 translate to a +2 bonus per overflow die.

    Returns ``(rolled, kept, flat_bonus_from_overflow)``.
    """
    flat = 0
    if rolled > 10:
        kept += rolled - 10
        rolled = 10
    if kept > 10:
        flat += 2 * (kept - 10)
        kept = 10
    return rolled, kept, flat


# ---------------------------------------------------------------------------
# Formula builders
# ---------------------------------------------------------------------------


def _apply_school_technique_bonus(
    formula: RollFormula,
    skill_or_knack_id: str,
    school_id: str,
    knacks: dict,
    technique_choices: Optional[dict] = None,
) -> None:
    """Apply 1st Dan extra die and 2nd Dan free raise if the school has them."""
    if not school_id:
        return
    bonuses_def = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})
    dan = compute_dan(knacks) if knacks else 0

    if dan >= 1 and bonuses_def.get("first_dan_extra_die"):
        if skill_or_knack_id in bonuses_def["first_dan_extra_die"]:
            formula.rolled += 1

    # Flexible 1st Dan: player-chosen skills (Ide, Isawa Ishi, Priest, Shugenja)
    if dan >= 1 and bonuses_def.get("first_dan_extra_die") is None and technique_choices:
        chosen = technique_choices.get("first_dan_choices") or []
        if skill_or_knack_id in chosen:
            formula.rolled += 1

    if dan >= 2 and bonuses_def.get("second_dan_free_raise"):
        if skill_or_knack_id == bonuses_def["second_dan_free_raise"]:
            _add_flat_bonus(formula, "2nd Dan technique", FREE_RAISE_VALUE)

    # Flexible 2nd Dan: player-chosen skill (Ide, Isawa Ishi, Shugenja)
    if dan >= 2 and bonuses_def.get("second_dan_free_raise") is None and technique_choices:
        chosen_2nd = technique_choices.get("second_dan_choice")
        if chosen_2nd and skill_or_knack_id == chosen_2nd:
            _add_flat_bonus(formula, "2nd Dan technique", FREE_RAISE_VALUE)

    # Mantis Wave-Treader 2nd Dan: player-chosen roll type (skills, rollable
    # knacks, attack, parry, wound_check, damage). Wound-check and damage are
    # applied elsewhere (build_wound_check_formula / _annotate_attack_type);
    # this branch covers skills, knacks, attack, and parry.
    if dan >= 2 and school_id == "mantis_wave_treader" and technique_choices:
        mantis_2nd = technique_choices.get("mantis_2nd_dan_free_raise")
        if mantis_2nd and skill_or_knack_id == mantis_2nd:
            _add_flat_bonus(formula, "2nd Dan technique", FREE_RAISE_VALUE)


def build_unskilled_formula(
    skill_id: str,
    character_data: dict,
    party_members: Optional[List[dict]] = None,
) -> Optional[RollFormula]:
    """Build a roll formula for an unskilled roll (rank 0).

    Unskilled rolls never reroll 10s. Advanced skills at rank 0 get
    a -10 penalty.
    """
    skill_def = SKILLS.get(skill_id)
    if skill_def is None:
        return None
    rings = character_data.get("rings", {})
    ring_val = rings.get(skill_def.ring.value, 2)
    flat = -10 if skill_def.is_advanced else 0
    bonuses = [{"label": "unskilled advanced penalty", "amount": -10}] if skill_def.is_advanced else []
    formula = RollFormula(
        label=f"{skill_def.name} ({skill_def.ring.value})",
        rolled=ring_val,
        kept=ring_val,
        flat=flat,
        bonuses=bonuses,
        reroll_tens=False,
        no_reroll_reason="unskilled",
        unskilled_skill_name=skill_def.name,
        otherworldliness_capacity=5 if not skill_def.is_advanced else 0,
    )
    # Priest 2nd Dan ally bonus: same skills as the skilled version.
    if skill_id in ("bragging", "precepts", "sincerity") and party_members:
        ally_priest = next(
            (p for p in party_members
             if p.get("school") == "priest" and (p.get("dan") or 0) >= 2),
            None,
        )
        if ally_priest is not None:
            ally_name = ally_priest.get("name", "an ally")
            label = f"Priest 2nd Dan ({ally_name} in party)"
            if skill_id == "sincerity":
                formula.alternatives.append({
                    "label": f"on open rolls ({label})",
                    "extra_flat": FREE_RAISE_VALUE,
                })
            else:
                _add_flat_bonus(formula, label, FREE_RAISE_VALUE)
    return formula


def build_skill_formula(
    skill_id: str,
    character_data: dict,
    party_members: Optional[List[dict]] = None,
) -> Optional[RollFormula]:
    """Build a roll formula for a skill the character has at rank > 0."""
    skill_def = SKILLS.get(skill_id)
    if skill_def is None:
        return None

    skills = character_data.get("skills", {}) or {}
    rank = skills.get(skill_id, 0)
    if rank <= 0:
        return None

    rings = character_data.get("rings", {})
    school_id = character_data.get("school", "")

    # Kitsuki Magistrate: use Water for interrogation rolls
    if school_id == "kitsuki_magistrate" and skill_id == "interrogation":
        ring_name = "Water"
    else:
        ring_name = skill_def.ring.value
    ring_val = rings.get(ring_name, 2)

    formula = RollFormula(
        label=f"{skill_def.name} ({ring_name})",
        rolled=rank + ring_val,
        kept=ring_val,
        flat=0,
        otherworldliness_capacity=max(0, 5 - rank) if not skill_def.is_advanced else 0,
        **_reroll_fields(character_data),
    )

    knacks = character_data.get("knacks", {}) or {}
    tech_choices = character_data.get("technique_choices") or {}
    _apply_school_technique_bonus(formula, skill_id, school_id, knacks, tech_choices)

    # Courtier 5th Dan: +Air to TN and contested rolls
    dan = compute_dan(knacks) if knacks else 0
    if school_id == "courtier" and dan >= 5:
        air_val = rings.get("Air", 2)
        if skill_id in _5TH_DAN_TN_ALWAYS:
            _add_flat_bonus(formula, "Courtier 5th Dan", air_val)
        elif skill_id not in _5TH_DAN_TN_NEVER:
            formula.courtier_5th_dan_optional = air_val

    # Doji Artisan 5th Dan: bonus = floor((TN - 10) / 5) on TN/contested rolls
    if school_id == "doji_artisan" and dan >= 5:
        if skill_id in _5TH_DAN_TN_ALWAYS:
            formula.doji_5th_dan_always = True
        elif skill_id not in _5TH_DAN_TN_NEVER:
            formula.doji_5th_dan_optional = True

    # --- Advantage bonuses (free raises = +5 each) ---
    advantages = character_data.get("advantages", []) or []
    for adv_id in advantages:
        if adv_id == "discerning" and skill_id in _DISCERNING_BONUSES:
            raises = _DISCERNING_BONUSES[skill_id]
            _add_flat_bonus(formula, ADVANTAGES[adv_id].name, raises * FREE_RAISE_VALUE)
        elif adv_id in _ADVANTAGE_SKILL_BONUSES:
            skill_list, raises = _ADVANTAGE_SKILL_BONUSES[adv_id]
            if skill_id in skill_list:
                _add_flat_bonus(formula, ADVANTAGES[adv_id].name, raises * FREE_RAISE_VALUE)

    # --- Campaign advantage bonuses (e.g. Highest Regard) ---
    campaign_advantages = character_data.get("campaign_advantages", []) or []
    for adv_id in campaign_advantages:
        if adv_id in _CAMPAIGN_ADVANTAGE_SKILL_BONUSES:
            skill_list, raises = _CAMPAIGN_ADVANTAGE_SKILL_BONUSES[adv_id]
            if skill_id in skill_list:
                _add_flat_bonus(
                    formula,
                    CAMPAIGN_ADVANTAGES[adv_id].name,
                    raises * FREE_RAISE_VALUE,
                )
        if adv_id in _CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES:
            skill_list, extra_raises, cond_text = (
                _CAMPAIGN_ADVANTAGE_CONDITIONAL_SKILL_BONUSES[adv_id]
            )
            if skill_id in skill_list:
                formula.alternatives.append({
                    "label": cond_text,
                    "extra_flat": extra_raises * FREE_RAISE_VALUE,
                })

    # --- Skill synergies (e.g. History → Culture/Law/Strategy) ---
    for source_id, (boosted, per_rank) in _SKILL_SYNERGIES.items():
        if skill_id in boosted:
            source_rank = skills.get(source_id, 0)
            if source_rank > 0:
                _add_flat_bonus(
                    formula,
                    SKILLS[source_id].name,
                    source_rank * per_rank * FREE_RAISE_VALUE,
                )

    # --- Priest 2nd Dan: free raise on Honor bonus rolls (bragging, precepts, open sincerity) ---
    if school_id == "priest" and dan >= 2 and skill_id in ("bragging", "precepts", "sincerity"):
        if skill_id == "sincerity":
            # Sincerity honor bonus is conditional (open rolls only), so the priest bonus is too
            formula.alternatives.append({
                "label": "on open rolls (Priest 2nd Dan)",
                "extra_flat": FREE_RAISE_VALUE,
            })
        else:
            _add_flat_bonus(formula, "Priest 2nd Dan", FREE_RAISE_VALUE)

    # --- Priest 2nd Dan (ally): same free raise if any party member is a
    # Priest at dan 2+. Does not stack with the self-Priest bonus.
    elif skill_id in ("bragging", "precepts", "sincerity") and party_members:
        ally_priest = next(
            (p for p in party_members
             if p.get("school") == "priest" and (p.get("dan") or 0) >= 2),
            None,
        )
        if ally_priest is not None:
            ally_name = ally_priest.get("name", "an ally")
            label = f"Priest 2nd Dan ({ally_name} in party)"
            if skill_id == "sincerity":
                formula.alternatives.append({
                    "label": f"on open rolls ({label})",
                    "extra_flat": FREE_RAISE_VALUE,
                })
            else:
                _add_flat_bonus(formula, label, FREE_RAISE_VALUE)

    # --- Honor bonus (Bragging, Precepts: unconditional. Sincerity: conditional) ---
    honor = character_data.get("honor", 1.0)
    if skill_id in _HONOR_BONUS_SKILLS:
        mult = _HONOR_BONUS_SKILLS[skill_id]
        bonus = int(mult * honor)
        if bonus > 0:
            if skill_id == "sincerity":
                formula.alternatives.append({
                    "label": "on open rolls",
                    "extra_flat": bonus,
                })
            else:
                _add_flat_bonus(formula, "Honor", bonus)

    # --- Recognition bonus (Bragging) ---
    recognition = character_data.get("recognition", 1.0)
    if skill_id in _RECOGNITION_BONUS_SKILLS:
        mult = _RECOGNITION_BONUS_SKILLS[skill_id]
        bonus = int(mult * recognition)
        if bonus > 0:
            _add_flat_bonus(formula, "Recognition", bonus)

    # --- Higher Purpose / Specialization (conditional → alternatives) ---
    advantage_details = character_data.get("advantage_details", {}) or {}
    if "higher_purpose" in advantages:
        hp = advantage_details.get("higher_purpose", {})
        hp_skills = hp.get("skills", []) or []
        hp_text = hp.get("text") or "your higher purpose"
        if skill_id in hp_skills:
            formula.alternatives.append({
                "label": f"if related to Higher Purpose ({hp_text})",
                "extra_flat": FREE_RAISE_VALUE,
            })

    if "specialization" in advantages:
        sp = advantage_details.get("specialization", {})
        sp_skills = sp.get("skills", []) or []
        sp_text = sp.get("text") or "your specialization"
        if skill_id in sp_skills:
            formula.alternatives.append({
                "label": f"if related to Specialization ({sp_text})",
                "extra_flat": 2 * FREE_RAISE_VALUE,
            })

    _finalize_caps(formula)
    return formula


def build_knack_formula(
    knack_id: str, character_data: dict
) -> Optional[RollFormula]:
    """Build a roll formula for a school knack the character has at rank >= 1."""
    knack_def = SCHOOL_KNACKS.get(knack_id)
    if knack_def is None:
        return None

    knacks = character_data.get("knacks", {}) or {}
    rank = knacks.get(knack_id, 0)
    if rank <= 0:
        return None

    # Dragon Tattoo: fixed (2X)k1 damage roll (X = knack rank). Not ring-based;
    # respects impaired reroll rules like any other personal roll. Damage rolls
    # don't accept void spending.
    if knack_id == "dragon_tattoo":
        return RollFormula(
            label=f"{knack_def.name} Damage",
            rolled=2 * rank,
            kept=1,
            flat=0,
            is_damage_roll=True,
            **_reroll_fields(character_data),
        )

    rings = character_data.get("rings", {})
    # Knacks may have a fixed ring, "varies" (use Earth as a sane default), or None
    ring_name = knack_def.ring if knack_def.ring in {r.value for r in Ring} else None
    if ring_name is None:
        # Knacks without a ring (e.g. passive) — use the lowest ring as a placeholder.
        # In practice these aren't typically rolled; the formula is best-effort.
        ring_name = "Earth"
    ring_val = rings.get(ring_name, 2)

    school_id = character_data.get("school", "")
    dan = compute_dan(knacks) if knacks else 0

    # Shugenja 5th Dan: non-Void rings +1 for commune and spellcasting
    if (school_id == "shugenja" and dan >= 5
            and knack_id in ("commune", "spellcasting")
            and ring_name in ("Air", "Fire", "Earth", "Water")):
        ring_val += 1

    formula = RollFormula(
        label=f"{knack_def.name} ({ring_name})",
        rolled=rank + ring_val,
        kept=ring_val,
        flat=0,
        **_reroll_fields(character_data),
    )

    tech_choices = character_data.get("technique_choices") or {}
    _apply_school_technique_bonus(formula, knack_id, school_id, knacks, tech_choices)

    # Courtier 5th Dan: +Air to all TN and contested rolls
    if school_id == "courtier" and dan >= 5:
        air_val = rings.get("Air", 2)
        _add_flat_bonus(formula, "Courtier 5th Dan", air_val)

    # Doji Artisan 5th Dan: knacks are always TN/contested
    if school_id == "doji_artisan" and dan >= 5:
        formula.doji_5th_dan_always = True

    _finalize_caps(formula)
    return formula


def build_combat_formula(
    which: str, character_data: dict
) -> Optional[RollFormula]:
    """Build a roll formula for ``attack`` or ``parry``."""
    if which not in ("attack", "parry"):
        return None
    rank = character_data.get(which, 1)
    if rank <= 0:
        return None
    rings = character_data.get("rings", {})
    ring_name = "Fire" if which == "attack" else "Air"
    ring_val = rings.get(ring_name, 2)

    formula = RollFormula(
        label=f"{which.title()} ({ring_name})",
        rolled=rank + ring_val,
        kept=ring_val,
        flat=0,
        **_reroll_fields(character_data),
    )

    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {}) or {}
    tech_choices = character_data.get("technique_choices") or {}
    _apply_school_technique_bonus(formula, which, school_id, knacks, tech_choices)

    dan = compute_dan(knacks) if knacks else 0

    # Kitsuki Magistrate: +2*Water flat on attack rolls
    if school_id == "kitsuki_magistrate" and which == "attack":
        water_val = rings.get("Water", 2)
        _add_flat_bonus(formula, "Kitsuki Magistrate (2x Water)", 2 * water_val)

    # Shosuro Actor: +acting_rank rolled dice on attack and parry
    if school_id == "shosuro_actor":
        skills = character_data.get("skills", {}) or {}
        acting_rank = skills.get("acting", 0)
        if acting_rank > 0:
            formula.rolled += acting_rank

    # Shosuro Actor 5th Dan: add sum of lowest 3 dice to roll (post-roll)
    if school_id == "shosuro_actor" and dan >= 5:
        formula.shosuro_5th_dan = True

    # Courtier 5th Dan: +Air to all TN and contested rolls
    if school_id == "courtier" and dan >= 5:
        air_val = rings.get("Air", 2)
        _add_flat_bonus(formula, "Courtier 5th Dan", air_val)

    # Doji Artisan 5th Dan: flag for client-side bonus (TN known from attack modal)
    if school_id == "doji_artisan" and dan >= 5:
        formula.doji_5th_dan_always = True

    _finalize_caps(formula)
    return formula


def build_athletics_formula(
    ring_name: str, character_data: dict
) -> Optional[RollFormula]:
    """Build an athletics roll formula for the given ring.

    Formula: ``2 * Ring`` rolled, ``Ring`` kept, plus the Athletics knack rank
    as additional rolled dice. Then L7R dice caps are applied.
    """
    if ring_name not in {r.value for r in Ring}:
        return None
    rings = character_data.get("rings", {})
    ring_val = rings.get(ring_name, 2)
    knacks = character_data.get("knacks", {}) or {}
    athletics_rank = knacks.get("athletics", 0)

    formula = RollFormula(
        label=f"Athletics ({ring_name})",
        rolled=2 * ring_val + athletics_rank,
        kept=ring_val,
        flat=0,
        **_reroll_fields(character_data),
    )

    school_id = character_data.get("school", "")
    tech_choices = character_data.get("technique_choices") or {}
    _apply_school_technique_bonus(formula, "athletics", school_id, knacks, tech_choices)

    _finalize_caps(formula)
    return formula


def build_athletics_combat_formula(
    which: str, character_data: dict
) -> Optional[RollFormula]:
    """Build an athletics-attack or athletics-parry formula.

    Per rules/05-school_knacks.md §Athletics: "You may also use this knack to
    attack or parry. If you use it to attack, your TN is increased by 5 times
    the defender's parry skill. If you use it to parry, then your TN is raised
    by 5 times the attack skill of the attacker."

    The base roll is the athletics formula locked to the combat ring
    (Fire for attack, Air for parry). In addition to athletics-specific school
    bonuses (inherited from build_athletics_formula), attack/parry school
    bonuses also apply - e.g. Kitsuki +2*Water on attack, Shinjo's 1st Dan
    extra die on parry.

    Returns None if the character has no athletics knack (rank 0).
    """
    if which not in ("attack", "parry"):
        return None
    knacks = character_data.get("knacks", {}) or {}
    if knacks.get("athletics", 0) <= 0:
        return None
    ring_name = "Fire" if which == "attack" else "Air"

    formula = build_athletics_formula(ring_name, character_data)
    if formula is None:  # pragma: no cover — ring_name is always Fire/Air (valid), so build_athletics_formula cannot return None here; guard is defensive against future refactors.
        return None
    formula.label = f"Athletics {'Attack' if which == 'attack' else 'Parry'} ({ring_name})"

    school_id = character_data.get("school", "")
    tech_choices = character_data.get("technique_choices") or {}
    _apply_school_technique_bonus(formula, which, school_id, knacks, tech_choices)

    dan = compute_dan(knacks) if knacks else 0
    rings = character_data.get("rings", {})

    if school_id == "kitsuki_magistrate" and which == "attack":
        water_val = rings.get("Water", 2)
        _add_flat_bonus(formula, "Kitsuki Magistrate (2x Water)", 2 * water_val)

    if school_id == "shosuro_actor":
        skills = character_data.get("skills", {}) or {}
        acting_rank = skills.get("acting", 0)
        if acting_rank > 0:
            formula.rolled += acting_rank

    if school_id == "shosuro_actor" and dan >= 5:
        formula.shosuro_5th_dan = True

    if school_id == "courtier" and dan >= 5:
        air_val = rings.get("Air", 2)
        _add_flat_bonus(formula, "Courtier 5th Dan", air_val)

    if school_id == "doji_artisan" and dan >= 5:
        formula.doji_5th_dan_always = True

    _finalize_caps(formula)
    return formula


def build_wound_check_formula(character_data: dict) -> dict:
    """Build the wound check roll formula.

    Base: (Water+1) rolled, Water kept.  School techniques may add an extra
    die (1st Dan) or a free raise / +5 flat (2nd Dan).  The Strength of the
    Earth advantage adds another +5 flat.

    Wound checks ALWAYS reroll 10s (the ``reroll_tens`` flag is True
    regardless of Impaired status - being Impaired does not suppress rerolls
    on wound checks).
    """
    rings = character_data.get("rings", {})
    water = rings.get("Water", 2)
    rolled = water + 1
    kept = water
    flat = 0

    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {}) or {}
    dan = compute_dan(knacks) if knacks else 0
    bonuses = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})

    bonus_sources: list = []

    # 1st Dan: extra rolled die on wound_check
    if dan >= 1 and bonuses.get("first_dan_extra_die"):
        if "wound_check" in (bonuses["first_dan_extra_die"] or []):
            rolled += 1
            bonus_sources.append("+1 rolled die from 1st Dan")

    # 2nd Dan: free raise (+5) on wound_check
    if dan >= 2 and bonuses.get("second_dan_free_raise"):
        if bonuses["second_dan_free_raise"] == "wound_check":
            flat += FREE_RAISE_VALUE
            bonus_sources.append("+5 from 2nd Dan")

    # Mantis Wave-Treader 2nd Dan: flexible free raise can target wound_check.
    if dan >= 2 and school_id == "mantis_wave_treader":
        tech_choices_wc = character_data.get("technique_choices") or {}
        if tech_choices_wc.get("mantis_2nd_dan_free_raise") == "wound_check":
            flat += FREE_RAISE_VALUE
            bonus_sources.append("+5 from 2nd Dan")

    # Shosuro Actor: +acting_rank rolled dice on wound checks
    if school_id == "shosuro_actor":
        skills = character_data.get("skills", {}) or {}
        acting_rank = skills.get("acting", 0)
        if acting_rank > 0:
            rolled += acting_rank
            bonus_sources.append(f"+{acting_rank} rolled dice from Acting")

    # Shiba Bushi 4th Dan: +3k1 on wound checks
    if school_id == "shiba_bushi" and dan >= 4:
        rolled += 3
        kept += 1
        bonus_sources.append("+3k1 from 4th Dan")

    # Kuni Witch Hunter Special: +1k1 on wound checks (base, before Taint bonus)
    if school_id == "kuni_witch_hunter":
        rolled += 1
        kept += 1
        bonus_sources.append("+1k1 from Kuni Special (untainted base)")

    # Courtier 5th Dan: +Air on wound checks (TN = light wounds)
    if school_id == "courtier" and dan >= 5:
        air_val = rings.get("Air", 2)
        flat += air_val
        bonus_sources.append(f"+{air_val} from Courtier 5th Dan")

    # Strength of the Earth advantage
    advantages = character_data.get("advantages", []) or []
    if "strength_of_the_earth" in advantages:
        flat += FREE_RAISE_VALUE
        bonus_sources.append("+5 from Strength of the Earth")

    # Bayushi Bushi 5th Dan: halve light wounds for serious wound calculation
    bayushi_5th_dan_half_lw = school_id == "bayushi_bushi" and dan >= 5

    # Doji Artisan 5th Dan: flag for client-side bonus (TN = light wounds)
    doji_5th_dan_wc = school_id == "doji_artisan" and dan >= 5

    # Shosuro Actor 5th Dan: add sum of lowest 3 dice to roll (post-roll)
    shosuro_5th_dan = school_id == "shosuro_actor" and dan >= 5

    return {
        "label": "Wound Check",
        "rolled": rolled,
        "kept": kept,
        "flat": flat,
        "reroll_tens": True,
        "no_reroll_reason": "",
        "is_wound_check": True,
        "bonus_sources": bonus_sources,
        "alternatives": [],
        "bonuses": [],
        "adventure_raises_max_per_roll": 0,
        "bayushi_5th_dan_half_lw": bayushi_5th_dan_half_lw,
        "doji_5th_dan_wc": doji_5th_dan_wc,
        "shosuro_5th_dan": shosuro_5th_dan,
    }


def build_initiative_formula(character_data: dict) -> Optional[dict]:
    """Build the initiative roll formula.

    Initiative: roll (Void+1) dice, keep the *lowest* Void dice (discard
    the highest). No reroll-10s. The kept dice become action dice — each
    value is the phase number when the character can act.

    School-specific modifications are encoded as boolean flags so the
    client can apply them after rolling.

    Togashi Ise Zumi special ability: "Roll either 1 or 3 extra action
    dice at the beginning of each combat round." The default ``rolled`` /
    ``kept`` reflect the "+1 extra die, athletics-only" variant; the
    "+3 extra dice, all athletics" variant is exposed as the separate
    ``initiative:athletics`` key via :func:`build_all_roll_formulas`.
    """
    rings = character_data.get("rings", {})
    void_val = rings.get("Void", 2)
    base_rolled = void_val + 1
    base_kept = void_val

    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {}) or {}
    dan = compute_dan(knacks) if knacks else 0
    bonuses = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})

    # Matsu Bushi: always roll 10 dice
    if school_id == "matsu_bushi":
        base_rolled = 10

    # 1st Dan extra die on initiative (Shinjo, Kakita, Hiruma, Togashi)
    if dan >= 1 and "initiative" in (bonuses.get("first_dan_extra_die") or []):
        base_rolled += 1

    # Kakita Duelist: 10s on initiative are Phase 0
    kakita_phase_zero = school_id == "kakita_duelist"

    # Shinjo Bushi 4th Dan: highest action die set to 1
    shinjo_4th_dan = school_id == "shinjo_bushi" and dan >= 4

    # Hiruma Scout 4th Dan: lower action dice by 2 (min 1)
    hiruma_4th_dan = school_id == "hiruma_scout" and dan >= 4

    # Togashi Ise Zumi: default variant is normal initiative (rolled/kept
    # unchanged) PLUS one separate athletics-only action die rolled
    # alongside. The client handles the extra die as an independent 1k1
    # roll so it can be visually distinguished from the normal action dice.
    is_togashi = school_id == "togashi_ise_zumi"
    rolled = base_rolled
    kept = base_kept

    return {
        "label": "Initiative",
        "rolled": rolled,
        "kept": kept,
        "flat": 0,
        "reroll_tens": False,
        "is_initiative": True,
        "kakita_phase_zero": kakita_phase_zero,
        "shinjo_4th_dan": shinjo_4th_dan,
        "hiruma_4th_dan": hiruma_4th_dan,
        "togashi_ise_zumi": is_togashi,
        # Togashi default variant rolls 1 extra athletics-only die alongside
        # the normal initiative roll (client handles as a separate d10).
        "togashi_athletics_extra_die": is_togashi,
        "togashi_base_rolled": base_rolled if is_togashi else 0,
        "togashi_base_kept": base_kept if is_togashi else 0,
        "alternatives": [],
        "bonuses": [],
        "adventure_raises_max_per_roll": 0,
    }


def build_all_roll_formulas(
    character_data: dict,
    party_members: Optional[List[dict]] = None,
) -> Dict[str, dict]:
    """Pre-compute every roll formula needed by the sheet.

    Returns a dict keyed like ``"skill:bragging"``, ``"knack:iaijutsu"``,
    ``"attack"``, ``"parry"``, ``"athletics:Air"``, etc. Each value is a
    plain dict (the dataclass serialised via ``to_dict``) so it serialises
    cleanly into JSON for embedding in the page.

    ``party_members`` is an optional list of fellow gaming-group characters
    (each dict including ``school`` + ``dan``). Used for shared-bonus
    mechanics like Priest 2nd Dan, which grants a free raise to the whole
    party on bragging / precepts / open sincerity.
    """
    out: Dict[str, dict] = {}

    # 3rd Dan: determine which roll keys get adventure free raises and
    # the per-roll cap (= source skill rank).
    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {}) or {}
    dan = compute_dan(knacks) if knacks else 0
    third_dan_applicable: set = set()
    third_dan_max_per_roll: int = 0
    tech_bonuses = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})
    if dan >= 3 and tech_bonuses.get("third_dan"):
        t3 = tech_bonuses["third_dan"]
        source_rank = (character_data.get("skills") or {}).get(t3["source_skill"], 0)
        if source_rank > 0:
            third_dan_max_per_roll = source_rank
            # The applicable_to list contains bare IDs like "bragging",
            # "attack", etc.  We'll match against the formula key's
            # trailing component (e.g. "skill:bragging" → "bragging").
            third_dan_applicable = set(t3["applicable_to"])

    def _annotate_third_dan(key: str, formula_dict: dict) -> dict:
        """Stamp ``adventure_raises_max_per_roll`` on applicable formulas."""
        # Strip the category prefix (skill:, knack:, athletics:) to get
        # the bare ID that appears in applicable_to.
        bare = key.split(":", 1)[-1] if ":" in key else key
        if bare in third_dan_applicable:
            formula_dict["adventure_raises_max_per_roll"] = third_dan_max_per_roll
        return formula_dict

    # Attack-type metadata for the combat modal. These formulas open the
    # attack modal instead of the void-spending dropdown.
    ATTACK_TYPE_KEYS = {"attack", "double_attack", "counterattack", "lunge"}
    rings = character_data.get("rings", {})
    advantages = character_data.get("advantages", []) or []

    # Determine damage ring and school-specific damage bonuses
    damage_ring_name = "Water" if school_id == "isawa_duelist" else "Fire"
    damage_ring_val = rings.get(damage_ring_name, 2)
    damage_flat_bonus = 0
    damage_extra_rolled = 0
    damage_extra_kept = 0
    damage_bonus_sources: list = []

    # Courtier: +Air as flat bonus on attack and damage
    if school_id == "courtier":
        air_val = rings.get("Air", 2)
        damage_flat_bonus += air_val
        damage_bonus_sources.append(f"+{air_val} from Courtier (Air)")

    # Yogo Warden / Kuni Witch Hunter: +1 rolled die on damage (1st Dan)
    if school_id in ("yogo_warden", "kuni_witch_hunter") and dan >= 1:
        damage_extra_rolled += 1
        damage_bonus_sources.append("+1 rolled die from 1st Dan")

    # Brotherhood of Shinsei: +1 rolled +1 kept on unarmed damage (1st Dan)
    if school_id == "brotherhood_of_shinsei_monk" and dan >= 1:
        damage_extra_rolled += 1
        damage_extra_kept += 1
        damage_bonus_sources.append("+1k1 from 1st Dan (unarmed)")

    # Mantis Wave-Treader 2nd Dan: flexible free raise can target damage.
    if (
        school_id == "mantis_wave_treader"
        and dan >= 2
        and (character_data.get("technique_choices") or {}).get(
            "mantis_2nd_dan_free_raise"
        ) == "damage"
    ):
        damage_flat_bonus += FREE_RAISE_VALUE
        damage_bonus_sources.append("+5 from 2nd Dan (damage)")

    # Detect bushi vs non-bushi for default weapon
    _school_obj = SCHOOLS.get(school_id)
    is_bushi = _school_obj.category in {"bushi", "counterattack", "duelist", "investigator"} if _school_obj else False

    def _annotate_attack_type(key: str, formula_dict: dict) -> dict:
        bare = key.split(":", 1)[-1] if ":" in key else key
        if bare in ATTACK_TYPE_KEYS:
            # Start with shared damage metadata; copy sources list so
            # per-variant additions don't bleed into other attack types.
            variant_damage_flat = damage_flat_bonus
            variant_damage_sources = list(damage_bonus_sources)

            formula_dict["is_attack_type"] = True
            formula_dict["attack_variant"] = bare
            formula_dict["damage_ring_name"] = damage_ring_name
            formula_dict["damage_ring_val"] = damage_ring_val
            formula_dict["damage_flat_bonus"] = variant_damage_flat
            formula_dict["damage_extra_rolled"] = damage_extra_rolled
            formula_dict["damage_extra_kept"] = damage_extra_kept
            formula_dict["damage_bonus_sources"] = variant_damage_sources
            formula_dict["is_bushi"] = is_bushi
            # Courtier also gets +Air flat on attack rolls (special ability)
            if school_id == "courtier":
                air_val = rings.get("Air", 2)
                formula_dict["flat"] = formula_dict.get("flat", 0) + air_val
                formula_dict.setdefault("bonuses", []).append(
                    {"label": "Courtier Special (Air)", "amount": air_val}
                )
            # Shosuro Actor 5th Dan: sum of lowest 3 dice added to roll (post-roll)
            if school_id == "shosuro_actor" and dan >= 5:
                formula_dict["shosuro_5th_dan"] = True

            # Derive bonus_sources for the attack modal's pre-roll panel.
            # Mirrors build_wound_check_formula's bonus_sources list. Picks up
            # every structured flat bonus in bonuses[] (Kitsuki +2xWater,
            # Courtier Special/5th Dan, 2nd Dan free raises, etc.), plus
            # rolled-die bonuses that don't live in bonuses[] (1st Dan extra
            # die, Shosuro acting dice).
            bonus_sources: list = []
            tech_bonuses_here = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})
            first_dan_list = tech_bonuses_here.get("first_dan_extra_die") or []
            if dan >= 1 and bare in first_dan_list:
                bonus_sources.append("+1 rolled die from 1st Dan")
            if school_id == "shosuro_actor":
                char_skills = character_data.get("skills", {}) or {}
                acting_rank = char_skills.get("acting", 0)
                if acting_rank > 0:
                    bonus_sources.append(
                        f"+{acting_rank} rolled dice from Acting (Shosuro Special)"
                    )
            for b in formula_dict.get("bonuses", []) or []:
                amount = b.get("amount", 0)
                label = b.get("label") or ""
                if amount and label:
                    sign = "+" if amount >= 0 else ""
                    bonus_sources.append(f"{sign}{amount} from {label}")
            formula_dict["bonus_sources"] = bonus_sources
        return formula_dict

    # Skills with rank > 0
    skills = character_data.get("skills", {}) or {}
    for skill_id, rank in skills.items():
        if rank <= 0:
            continue
        formula = build_skill_formula(skill_id, character_data, party_members=party_members)
        if formula is not None:
            out[f"skill:{skill_id}"] = _annotate_third_dan(
                f"skill:{skill_id}", formula.to_dict()
            )

    # Unskilled rolls: generate formulas for ALL skills at rank 0 so
    # they can still be rolled (no reroll 10s, advanced get -10 penalty).
    for skill_id, skill_def in SKILLS.items():
        if skills.get(skill_id, 0) > 0:
            continue  # already handled above
        formula = build_unskilled_formula(skill_id, character_data, party_members=party_members)
        if formula is not None:
            d = formula.to_dict()
            d["is_unskilled"] = True
            out[f"skill:{skill_id}"] = d

    # School knacks (look up from the character's school)
    school = SCHOOLS.get(school_id)
    if school is not None:
        for knack_id in school.school_knacks:
            if knack_id in NON_ROLLABLE_KNACKS:
                continue
            formula = build_knack_formula(knack_id, character_data)
            if formula is not None:
                d = _annotate_third_dan(f"knack:{knack_id}", formula.to_dict())
                out[f"knack:{knack_id}"] = _annotate_attack_type(f"knack:{knack_id}", d)

    # Iaijutsu knack: stamp damage metadata so the duel modal can use it.
    # Iaijutsu is NOT in ATTACK_TYPE_KEYS (it uses the roll menu, not
    # attack modal), but its damage metadata is needed for duel damage.
    if "knack:iaijutsu" in out:
        iai_flat = damage_flat_bonus
        iai_sources = list(damage_bonus_sources)
        if school_id == "kakita_duelist" and dan >= 4:
            iai_flat += FREE_RAISE_VALUE
            iai_sources.append("+5 from 4th Dan (iaijutsu)")
        out["knack:iaijutsu"]["damage_ring_name"] = damage_ring_name
        out["knack:iaijutsu"]["damage_ring_val"] = damage_ring_val
        out["knack:iaijutsu"]["damage_flat_bonus"] = iai_flat
        out["knack:iaijutsu"]["damage_extra_rolled"] = damage_extra_rolled
        out["knack:iaijutsu"]["damage_extra_kept"] = damage_extra_kept
        out["knack:iaijutsu"]["damage_bonus_sources"] = iai_sources

    # Iaijutsu strike variant (10s never rerolled during the strike)
    if school is not None and "iaijutsu" in school.school_knacks:
        base_formula = build_knack_formula("iaijutsu", character_data)
        if base_formula is not None:
            strike = base_formula.to_dict()
            # "Iaijutsu (Fire)" -> "Iaijutsu Strike (Fire)"
            strike["label"] = base_formula.label.replace("Iaijutsu", "Iaijutsu Strike", 1)
            strike["reroll_tens"] = False
            strike["no_reroll_reason"] = "iaijutsu_strike"
            out["knack:iaijutsu:strike"] = _annotate_third_dan(
                "knack:iaijutsu:strike", strike
            )

    # Combat
    for which in ("attack", "parry"):
        formula = build_combat_formula(which, character_data)
        if formula is not None:
            d = _annotate_third_dan(which, formula.to_dict())
            out[which] = _annotate_attack_type(which, d)

    # Athletics on each ring
    for ring_name in (r.value for r in Ring):
        formula = build_athletics_formula(ring_name, character_data)
        if formula is not None:
            out[f"athletics:{ring_name}"] = formula.to_dict()

    # Athletics used as attack/parry (rules p05 §Athletics). Only offered when
    # the character has athletics rank 1+. Attack opens the attack modal with
    # a doubled TN (5 + 10*parry); parry goes through the normal roll menu.
    for which in ("attack", "parry"):
        ath = build_athletics_combat_formula(which, character_data)
        if ath is not None:
            key = f"athletics:{which}"
            d = _annotate_third_dan(key, ath.to_dict())
            if which == "attack":
                d = _annotate_attack_type(key, d)
                d["attack_variant"] = "athletics_attack"
                d["is_athletics_attack"] = True
            else:
                d["is_athletics_parry"] = True
            out[key] = d

    # Initiative
    init_formula = build_initiative_formula(character_data)
    if init_formula is not None:
        out["initiative"] = init_formula
        # Togashi Ise Zumi: expose the "3 extra dice, all athletics" variant
        # as a second roll key so the client can offer both choices.
        if init_formula.get("togashi_ise_zumi"):
            base_rolled = init_formula["togashi_base_rolled"]
            base_kept = init_formula["togashi_base_kept"]
            out["initiative:athletics"] = {
                **init_formula,
                "label": "Athletics Initiative",
                "rolled": base_rolled + 3,
                "kept": base_kept + 3,
                "togashi_athletics_only": True,
                # Athletics variant has no separate standalone die.
                "togashi_athletics_extra_die": False,
            }

    # Wound check
    wc_formula = build_wound_check_formula(character_data)
    out["wound_check"] = _annotate_third_dan("wound_check", wc_formula)

    return out
