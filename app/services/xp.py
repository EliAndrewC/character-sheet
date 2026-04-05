"""
XP Calculation Engine for the L7R Character Builder.

All functions are pure: they take data in, return results, and have no
side-effects or database dependencies.
"""

from __future__ import annotations

from typing import Dict, List

from app.game_data import (
    ADVANCED_SKILL_COSTS,
    ADVANTAGES,
    COMBAT_SKILL_MAX,
    COMBAT_SKILL_START,
    DISADVANTAGES,
    HONOR_COST_PER_HALF,
    HONOR_MAX,
    HONOR_START,
    KNACK_COSTS,
    KNACK_MAX,
    RANK_COST_PER_HALF,
    RANK_START,
    RECOGNITION_HALVE_START_XP,
    RECOGNITION_MAX_FACTOR,
    RECOGNITION_COST_PER_ONE,
    RING_DEFAULT,
    RING_MAX_NORMAL,
    RING_MAX_SCHOOL,
    RING_NAMES,
    RING_SCHOOL_DEFAULT,
    SCHOOL_KNACKS,
    SCHOOLS,
    SKILL_MAX,
    SKILLS,
    ring_raise_cost,
    skill_raise_cost,
    total_skill_cost,
)


# ---------------------------------------------------------------------------
# Individual cost functions
# ---------------------------------------------------------------------------

def calculate_ring_xp(rings: Dict[str, int], school_ring: str) -> int:
    """Return total XP spent on raising rings above their free starting values.

    *school_ring* is the resolved ring name (e.g. ``"Water"``).  The school
    ring starts at 3 for free; all others start at 2.  Cost to raise from
    current to current+1 is ``5 * (current + 1)``.
    """
    xp = 0
    for ring_name, target in rings.items():
        base = RING_SCHOOL_DEFAULT if ring_name == school_ring else RING_DEFAULT
        for new_val in range(base + 1, target + 1):
            xp += ring_raise_cost(new_val)
    return xp


def calculate_skill_xp(skills: Dict[str, int]) -> int:
    """Return total XP spent on skills (from rank 0 to each skill's rank).

    Uses the basic or advanced cost table depending on the skill definition
    in ``game_data.SKILLS``.
    """
    xp = 0
    for skill_id, rank in skills.items():
        if rank <= 0:
            continue
        skill_def = SKILLS.get(skill_id)
        if skill_def is None:
            # Unknown skill -- treat as advanced to be safe
            is_advanced = True
        else:
            is_advanced = skill_def.is_advanced
        xp += total_skill_cost(min(rank, SKILL_MAX), is_advanced)
    return xp


def calculate_knack_xp(knacks: Dict[str, int]) -> int:
    """Return total XP spent on knacks above the free rank 1.

    Every school grants its three knacks at rank 1 for free.  Raising above
    rank 1 uses the advanced skill cost table.  So a knack at rank 2 costs
    ``ADVANCED_SKILL_COSTS[2]`` (4 XP), rank 3 costs 4 + 6 = 10, etc.
    """
    xp = 0
    for knack_id, rank in knacks.items():
        if rank <= 1:
            continue
        # Sum advanced costs from rank 2 up to target rank
        for new_rank in range(2, min(rank, KNACK_MAX) + 1):
            xp += KNACK_COSTS[new_rank]
    return xp


def calculate_combat_skill_xp(attack: int = 1, parry: int = 1) -> int:
    """Return total XP spent on Attack and Parry above the free starting rank of 1.

    Both use the advanced skill cost table.
    """
    xp = 0
    for rank in (attack, parry):
        for new_rank in range(2, min(rank, COMBAT_SKILL_MAX) + 1):
            xp += ADVANCED_SKILL_COSTS[new_rank]
    return xp


def calculate_honor_xp(honor: float) -> int:
    """Return XP spent on Honor above the free starting value of 1.0.

    1 XP per 0.5 Honor above ``HONOR_START`` (1.0).
    """
    if honor <= HONOR_START:
        return 0
    increments = (honor - HONOR_START) / 0.5
    return round(increments) * HONOR_COST_PER_HALF


def calculate_rank_xp(rank: float, campaign_default: float = 1.0) -> int:
    """Return XP spent on Rank above the campaign default.

    Same formula as Honor: 1 XP per 0.5 above the default.
    """
    if rank <= campaign_default:
        return 0
    increments = (rank - campaign_default) / 0.5
    return round(increments) * RANK_COST_PER_HALF


def calculate_recognition_xp(
    recognition: float,
    rank: float,
    halved: bool = False,
) -> int:
    """Return XP cost (or gain) for Recognition.

    * Normal: Recognition starts equal to Rank.  Raising costs 1 XP per 1.0
      above Rank, up to 150 % of Rank.
    * Halved (``halved=True``): Recognition starts at ``rank / 2`` and the
      character *gains* 3 XP (returned as a negative number).
    """
    if halved:
        return -RECOGNITION_HALVE_START_XP
    if recognition <= rank:
        return 0
    cost = (recognition - rank) * RECOGNITION_COST_PER_ONE
    return round(cost)


def calculate_advantage_xp(advantages: List[str]) -> int:
    """Return total XP spent on advantages."""
    xp = 0
    for adv_id in advantages:
        adv = ADVANTAGES.get(adv_id)
        if adv is not None:
            xp += adv.xp_cost
    return xp


def calculate_disadvantage_xp(disadvantages: List[str]) -> int:
    """Return XP *gained* from disadvantages (as a negative number).

    Disadvantages give XP back, so the returned value is ``<= 0``.
    """
    xp = 0
    for dis_id in disadvantages:
        dis = DISADVANTAGES.get(dis_id)
        if dis is not None:
            xp += dis.xp_value
    return -xp


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def calculate_total_xp(character_data: dict) -> dict:
    """Return a breakdown dict of XP spent across all categories.

    Expected *character_data* shape::

        {
            "school": "akodo_bushi",
            "school_ring_choice": "Water",
            "rings": {"Air": 2, ...},
            "skills": {"bragging": 1, ...},
            "knacks": {"double_attack": 1, ...},
            "advantages": ["lucky", "fierce"],
            "disadvantages": ["proud", "vain"],
            "honor": 2.0,
            "rank": 1.0,
            "recognition": 1.0,
            "recognition_halved": False,
            "earned_xp": 0,
            "starting_xp": 150,
        }
    """
    school_ring = character_data.get("school_ring_choice", "")

    rings = calculate_ring_xp(character_data.get("rings", {}), school_ring)
    skills = calculate_skill_xp(character_data.get("skills", {}))
    knacks = calculate_knack_xp(character_data.get("knacks", {}))
    combat_skills = calculate_combat_skill_xp(
        attack=character_data.get("attack", COMBAT_SKILL_START),
        parry=character_data.get("parry", COMBAT_SKILL_START),
    )
    honor = calculate_honor_xp(character_data.get("honor", HONOR_START))
    rank = calculate_rank_xp(
        character_data.get("rank", RANK_START),
        campaign_default=RANK_START,
    )
    recognition = calculate_recognition_xp(
        character_data.get("recognition", 0.0),
        character_data.get("rank", RANK_START),
        halved=character_data.get("recognition_halved", False),
    )
    advantages = calculate_advantage_xp(character_data.get("advantages", []))
    disadvantages = calculate_disadvantage_xp(
        character_data.get("disadvantages", []),
    )

    total = (
        rings + skills + knacks + combat_skills + honor + rank + recognition
        + advantages + disadvantages
    )

    return {
        "rings": rings,
        "skills": skills,
        "knacks": knacks,
        "combat_skills": combat_skills,
        "honor": honor,
        "rank": rank,
        "recognition": recognition,
        "advantages": advantages,
        "disadvantages": disadvantages,
        "total": total,
    }


def calculate_available_xp(
    earned_xp: int = 0,
    starting_xp: int = 150,
) -> int:
    """Return the total XP budget (starting + earned)."""
    return starting_xp + earned_xp


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_character(character_data: dict) -> List[str]:
    """Return a list of validation error strings.  Empty list means valid."""
    errors: List[str] = []

    school_id = character_data.get("school", "")
    school = SCHOOLS.get(school_id)
    school_ring = character_data.get("school_ring_choice", "")

    # -- Combat skills (Attack / Parry) --
    for cs_name in ("attack", "parry"):
        cs_val = character_data.get(cs_name, COMBAT_SKILL_START)
        if cs_val < COMBAT_SKILL_START:
            errors.append(
                f"{cs_name.title()} ({cs_val}) must be at least "
                f"{COMBAT_SKILL_START}."
            )
        if cs_val > COMBAT_SKILL_MAX:
            errors.append(
                f"{cs_name.title()} ({cs_val}) exceeds maximum "
                f"({COMBAT_SKILL_MAX})."
            )

    # -- Rings --
    rings = character_data.get("rings", {})
    for ring_name in RING_NAMES:
        value = rings.get(ring_name, RING_DEFAULT)
        min_val = RING_DEFAULT
        max_val = RING_MAX_SCHOOL if ring_name == school_ring else RING_MAX_NORMAL
        if value < min_val:
            errors.append(
                f"Ring {ring_name} ({value}) is below minimum ({min_val})."
            )
        if value > max_val:
            errors.append(
                f"Ring {ring_name} ({value}) exceeds maximum ({max_val})."
            )

    # -- Skills --
    skills = character_data.get("skills", {})
    for skill_id, rank in skills.items():
        if rank < 0:
            errors.append(f"Skill '{skill_id}' has negative rank ({rank}).")
        if rank > SKILL_MAX:
            errors.append(
                f"Skill '{skill_id}' ({rank}) exceeds maximum ({SKILL_MAX})."
            )

    # -- Knacks --
    knacks = character_data.get("knacks", {})
    for knack_id, rank in knacks.items():
        if rank < 1:
            errors.append(
                f"Knack '{knack_id}' ({rank}) must be at least 1 "
                f"(school grants rank 1)."
            )
        if rank > KNACK_MAX:
            errors.append(
                f"Knack '{knack_id}' ({rank}) exceeds maximum ({KNACK_MAX})."
            )

    # -- School knacks must match school --
    if school is not None:
        expected_knacks = set(school.school_knacks)
        actual_knacks = set(knacks.keys())
        missing = expected_knacks - actual_knacks
        extra = actual_knacks - expected_knacks
        if missing:
            errors.append(
                f"Missing school knacks for {school.name}: "
                f"{', '.join(sorted(missing))}."
            )
        if extra:
            errors.append(
                f"Unknown knacks for {school.name}: "
                f"{', '.join(sorted(extra))}."
            )

    # -- Honor --
    honor = character_data.get("honor", HONOR_START)
    if honor < HONOR_START:
        errors.append(f"Honor ({honor}) is below minimum ({HONOR_START}).")
    if honor > HONOR_MAX:
        errors.append(f"Honor ({honor}) exceeds maximum ({HONOR_MAX}).")

    # -- Recognition --
    rank_val = character_data.get("rank", RANK_START)
    recognition = character_data.get("recognition", rank_val)
    halved = character_data.get("recognition_halved", False)
    max_recognition = rank_val * RECOGNITION_MAX_FACTOR
    min_recognition = rank_val / 2.0 if halved else rank_val

    if recognition > max_recognition:
        errors.append(
            f"Recognition ({recognition}) exceeds 150% of Rank "
            f"({max_recognition})."
        )
    if recognition < min_recognition:
        errors.append(
            f"Recognition ({recognition}) is below minimum "
            f"({min_recognition})."
        )

    # -- XP budget --
    breakdown = calculate_total_xp(character_data)
    available = calculate_available_xp(
        earned_xp=character_data.get("earned_xp", 0),
        starting_xp=character_data.get("starting_xp", 150),
    )
    if breakdown["total"] > available:
        errors.append(
            f"Total XP spent ({breakdown['total']}) exceeds available "
            f"XP ({available})."
        )

    return errors
