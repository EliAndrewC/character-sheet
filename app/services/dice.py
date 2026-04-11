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
    alternatives: List[dict] = field(default_factory=list)
    bonuses: List[dict] = field(default_factory=list)
    adventure_raises_max_per_roll: int = 0

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
) -> None:
    """Apply 1st Dan extra die and 2nd Dan free raise if the school has them."""
    if not school_id:
        return
    bonuses_def = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})
    dan = compute_dan(knacks) if knacks else 0

    if dan >= 1 and bonuses_def.get("first_dan_extra_die"):
        if skill_or_knack_id in bonuses_def["first_dan_extra_die"]:
            formula.rolled += 1

    if dan >= 2 and bonuses_def.get("second_dan_free_raise"):
        if skill_or_knack_id == bonuses_def["second_dan_free_raise"]:
            _add_flat_bonus(formula, "2nd Dan technique", FREE_RAISE_VALUE)


def build_skill_formula(
    skill_id: str, character_data: dict
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
    ring_val = rings.get(skill_def.ring.value, 2)

    formula = RollFormula(
        label=f"{skill_def.name} ({skill_def.ring.value})",
        rolled=rank + ring_val,
        kept=ring_val,
        flat=0,
        **_reroll_fields(character_data),
    )

    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {}) or {}
    _apply_school_technique_bonus(formula, skill_id, school_id, knacks)

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

    rings = character_data.get("rings", {})
    # Knacks may have a fixed ring, "varies" (use Earth as a sane default), or None
    ring_name = knack_def.ring if knack_def.ring in {r.value for r in Ring} else None
    if ring_name is None:
        # Knacks without a ring (e.g. passive) — use the lowest ring as a placeholder.
        # In practice these aren't typically rolled; the formula is best-effort.
        ring_name = "Earth"
    ring_val = rings.get(ring_name, 2)

    formula = RollFormula(
        label=f"{knack_def.name} ({ring_name})",
        rolled=rank + ring_val,
        kept=ring_val,
        flat=0,
        **_reroll_fields(character_data),
    )

    school_id = character_data.get("school", "")
    _apply_school_technique_bonus(formula, knack_id, school_id, knacks)

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
    _apply_school_technique_bonus(formula, which, school_id, knacks)
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

    # Strength of the Earth advantage
    advantages = character_data.get("advantages", []) or []
    if "strength_of_the_earth" in advantages:
        flat += FREE_RAISE_VALUE
        bonus_sources.append("+5 from Strength of the Earth")

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
    }


def build_initiative_formula(character_data: dict) -> Optional[dict]:
    """Build the initiative roll formula.

    Initiative: roll (Void+1) dice, keep the *lowest* Void dice (discard
    the highest). No reroll-10s. The kept dice become action dice — each
    value is the phase number when the character can act.

    School-specific modifications are encoded as boolean flags so the
    client can apply them after rolling.
    """
    rings = character_data.get("rings", {})
    void_val = rings.get("Void", 2)
    rolled = void_val + 1
    kept = void_val

    school_id = character_data.get("school", "")
    knacks = character_data.get("knacks", {}) or {}
    dan = compute_dan(knacks) if knacks else 0
    bonuses = SCHOOL_TECHNIQUE_BONUSES.get(school_id, {})

    # Matsu Bushi: always roll 10 dice
    matsu_override = school_id == "matsu_bushi"
    if matsu_override:
        rolled = 10

    # 1st Dan extra die on initiative (Shinjo, Kakita, Hiruma)
    if dan >= 1 and bonuses.get("first_dan_extra_die"):
        if "initiative" in (bonuses["first_dan_extra_die"] or []):
            rolled += 1

    # Kakita Duelist: 10s on initiative are Phase 0
    kakita_phase_zero = school_id == "kakita_duelist"

    # Shinjo Bushi 4th Dan: highest action die set to 1
    shinjo_4th_dan = school_id == "shinjo_bushi" and dan >= 4

    # Hiruma Scout 4th Dan: lower action dice by 2 (min 1)
    hiruma_4th_dan = school_id == "hiruma_scout" and dan >= 4

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
        "alternatives": [],
        "bonuses": [],
        "adventure_raises_max_per_roll": 0,
    }


def build_all_roll_formulas(
    character_data: dict,
) -> Dict[str, dict]:
    """Pre-compute every roll formula needed by the sheet.

    Returns a dict keyed like ``"skill:bragging"``, ``"knack:iaijutsu"``,
    ``"attack"``, ``"parry"``, ``"athletics:Air"``, etc. Each value is a
    plain dict (the dataclass serialised via ``to_dict``) so it serialises
    cleanly into JSON for embedding in the page.
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

    # Brotherhood of Shinsei: +1 rolled +1 kept on unarmed damage (1st Dan)
    if school_id == "brotherhood_of_shinsei_monk" and dan >= 1:
        damage_extra_rolled += 1
        damage_extra_kept += 1
        damage_bonus_sources.append("+1k1 from 1st Dan (unarmed)")

    # Detect bushi vs non-bushi for default weapon
    _school_obj = SCHOOLS.get(school_id)
    is_bushi = _school_obj.category in {"bushi", "counterattack", "duelist", "investigator"} if _school_obj else False

    def _annotate_attack_type(key: str, formula_dict: dict) -> dict:
        bare = key.split(":", 1)[-1] if ":" in key else key
        if bare in ATTACK_TYPE_KEYS:
            formula_dict["is_attack_type"] = True
            formula_dict["attack_variant"] = bare
            formula_dict["damage_ring_name"] = damage_ring_name
            formula_dict["damage_ring_val"] = damage_ring_val
            formula_dict["damage_flat_bonus"] = damage_flat_bonus
            formula_dict["damage_extra_rolled"] = damage_extra_rolled
            formula_dict["damage_extra_kept"] = damage_extra_kept
            formula_dict["damage_bonus_sources"] = damage_bonus_sources
            formula_dict["is_bushi"] = is_bushi
            # Courtier also gets +Air flat on attack rolls
            if school_id == "courtier":
                air_val = rings.get("Air", 2)
                formula_dict["flat"] = formula_dict.get("flat", 0) + air_val
                if not any("Courtier" in b.get("label", "") for b in formula_dict.get("bonuses", [])):
                    formula_dict.setdefault("bonuses", []).append(
                        {"label": "Courtier (Air)", "amount": air_val}
                    )
        return formula_dict

    # Skills with rank > 0
    skills = character_data.get("skills", {}) or {}
    for skill_id, rank in skills.items():
        if rank <= 0:
            continue
        formula = build_skill_formula(skill_id, character_data)
        if formula is not None:
            out[f"skill:{skill_id}"] = _annotate_third_dan(
                f"skill:{skill_id}", formula.to_dict()
            )

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

    # Initiative
    init_formula = build_initiative_formula(character_data)
    if init_formula is not None:
        out["initiative"] = init_formula

    # Wound check
    wc_formula = build_wound_check_formula(character_data)
    out["wound_check"] = _annotate_third_dan("wound_check", wc_formula)

    return out
