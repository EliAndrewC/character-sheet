"""
XP Calculation Engine for the L7R Character Builder.

All functions are pure: they take data in, return results, and have no
side-effects or database dependencies.
"""

from __future__ import annotations

from typing import Dict, List

from app.game_data import (
    ADVANCED_SKILL_COSTS,
    ADVANTAGE_DETAIL_FIELDS,
    ADVANTAGES,
    BASIC_SKILL_COSTS,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
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
    RECOGNITION_START,
    RECOGNITION_HALVE_START_XP,
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
    max_recognition,
    ring_raise_cost,
    skill_raise_cost,
    total_skill_cost,
)
from app.services.rolls import compute_dan


# ---------------------------------------------------------------------------
# Individual cost functions
# ---------------------------------------------------------------------------

def calculate_ring_xp(rings: Dict[str, int], school_ring: str, dan: int = 0) -> int:
    """Return total XP spent on raising rings above their free starting values.

    *school_ring* is the resolved ring name (e.g. ``"Water"``).  The school
    ring starts at 3 for free; all others start at 2.  Cost to raise from
    current to current+1 is ``5 * (current + 1)``.

    At 4th Dan, the school ring gets a 5 XP discount per raise, and the
    raise from 3 to 4 is free (part of the 4th Dan technique).
    """
    xp = 0
    for ring_name, target in rings.items():
        is_school = ring_name == school_ring
        base = RING_SCHOOL_DEFAULT if is_school else RING_DEFAULT

        # 4th Dan auto-raises school ring to 4 for free
        if is_school and dan >= 4:
            base = max(base, 4)  # 3->4 is free from 4th Dan technique

        for new_val in range(base + 1, target + 1):
            cost = ring_raise_cost(new_val)
            # 4th Dan: school ring costs 5 less per raise
            if is_school and dan >= 4:
                cost = max(0, cost - 5)
            xp += cost
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


def _halved_recognition_base() -> float:
    """Return the starting Recognition when halved, rounded down to nearest 0.5."""
    import math
    return math.floor(RECOGNITION_START / 2 * 2) / 2


def calculate_recognition_xp(
    recognition: float,
    rank: float,
    halved: bool = False,
) -> int:
    """Return XP cost (or gain) for Recognition.

    * Normal: Recognition starts at ``RECOGNITION_START`` for free.  Raising
      costs 1 XP per 1.0 above that base, up to 150 % of Rank.
    * Halved (``halved=True``): Recognition starts at half of
      ``RECOGNITION_START`` (rounded down to nearest 0.5) and the character
      *gains* 3 XP (returned as a negative number).  Any amount above the
      halved base still costs XP to raise.
    """
    if halved:
        base = _halved_recognition_base()
        xp = -RECOGNITION_HALVE_START_XP
        if recognition > base:
            xp += round((recognition - base) * RECOGNITION_COST_PER_ONE)
        return xp
    if recognition <= RECOGNITION_START:
        return 0
    cost = (recognition - RECOGNITION_START) * RECOGNITION_COST_PER_ONE
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


def calculate_campaign_advantage_xp(campaign_advantages: List[str]) -> int:
    """Return total XP spent on campaign-specific advantages."""
    xp = 0
    for adv_id in campaign_advantages:
        adv = CAMPAIGN_ADVANTAGES.get(adv_id)
        if adv is not None:
            xp += adv.xp_cost
    return xp


def calculate_campaign_disadvantage_xp(campaign_disadvantages: List[str]) -> int:
    """Return XP gained from campaign-specific disadvantages (as negative)."""
    xp = 0
    for dis_id in campaign_disadvantages:
        dis = CAMPAIGN_DISADVANTAGES.get(dis_id)
        if dis is not None:
            xp += dis.xp_value
    return -xp


# ---------------------------------------------------------------------------
# Per-item breakdown helpers (used by the expandable XP Summary on the sheet)
# ---------------------------------------------------------------------------
#
# Each item is a plain dict so it serialises naturally and Jinja can read it.
# Three shapes are used:
#
#   Rank-up item:    {"xp": int, "label": str, "from_val": num, "to_val": num}
#   Flat-cost item:  {"xp": int, "label": str}
#   Note item:       {"xp": 0, "label": str, "note": True}


def ring_xp_items(
    rings: Dict[str, int],
    school_ring: str,
    dan: int = 0,
) -> List[dict]:
    """One item per individual ring raise. Mirrors ``calculate_ring_xp``.

    Free school-ring raises (the school-ring 2->3 everyone gets, and the
    additional 3->4 from the 4th Dan technique) are included as 0 XP rows
    so the breakdown shows every raise the character actually received.
    """
    items: List[dict] = []
    for ring_name, target in rings.items():
        is_school = ring_name == school_ring
        base = RING_SCHOOL_DEFAULT if is_school else RING_DEFAULT
        if is_school and dan >= 4:
            base = max(base, 4)  # 3->4 free at 4th Dan

        if is_school and target >= RING_SCHOOL_DEFAULT:
            items.append({
                "xp": 0,
                "label": ring_name,
                "from_val": RING_DEFAULT,
                "to_val": RING_SCHOOL_DEFAULT,
            })
            if dan >= 4 and target >= 4:
                items.append({
                    "xp": 0,
                    "label": ring_name,
                    "from_val": RING_SCHOOL_DEFAULT,
                    "to_val": 4,
                })

        for new_val in range(base + 1, target + 1):
            cost = ring_raise_cost(new_val)
            if is_school and dan >= 4:
                cost = max(0, cost - 5)
            items.append({
                "xp": cost,
                "label": ring_name,
                "from_val": new_val - 1,
                "to_val": new_val,
            })
    items.sort(key=lambda i: (i["from_val"], i["label"]))
    return items


def school_knack_xp_items(knacks: Dict[str, int]) -> List[dict]:
    """One item per knack raise above the free rank 1."""
    items: List[dict] = []
    for knack_id, rank in knacks.items():
        if rank <= 1:
            continue
        knack_def = SCHOOL_KNACKS.get(knack_id)
        label = knack_def.name if knack_def else knack_id
        for new_rank in range(2, min(rank, KNACK_MAX) + 1):
            items.append({
                "xp": KNACK_COSTS[new_rank],
                "label": label,
                "from_val": new_rank - 1,
                "to_val": new_rank,
            })
    items.sort(key=lambda i: (i["from_val"], i["label"]))
    return items


def skill_xp_items(skills: Dict[str, int]) -> dict:
    """Per-skill items split into ``basic`` and ``advanced`` lists."""
    basic_items: List[dict] = []
    advanced_items: List[dict] = []
    for skill_id, rank in skills.items():
        if rank <= 0:
            continue
        skill_def = SKILLS.get(skill_id)
        if skill_def is None:
            is_advanced = True
            label = skill_id
        else:
            is_advanced = skill_def.is_advanced
            label = skill_def.name
        target_list = advanced_items if is_advanced else basic_items
        cost_table = ADVANCED_SKILL_COSTS if is_advanced else BASIC_SKILL_COSTS
        for new_rank in range(1, min(rank, SKILL_MAX) + 1):
            target_list.append({
                "xp": cost_table[new_rank],
                "label": label,
                "from_val": new_rank - 1,
                "to_val": new_rank,
            })
    basic_items.sort(key=lambda i: (i["from_val"], i["label"]))
    advanced_items.sort(key=lambda i: (i["from_val"], i["label"]))
    return {"basic": basic_items, "advanced": advanced_items}


def combat_skill_xp_items(attack: int = 1, parry: int = 1) -> List[dict]:
    """Per-rank items for Attack and Parry, sorted by ``from_val`` then label.

    With the ``(from_val, label)`` sort, the order interleaves the two skills:
    Attack 1->2, Parry 1->2, Attack 2->3, Parry 2->3, ... — matching the
    user-stated requirement that lower-rank raises always appear before
    higher-rank raises.
    """
    items: List[dict] = []
    for label, rank in (("Attack", attack), ("Parry", parry)):
        for new_rank in range(2, min(rank, COMBAT_SKILL_MAX) + 1):
            items.append({
                "xp": ADVANCED_SKILL_COSTS[new_rank],
                "label": label,
                "from_val": new_rank - 1,
                "to_val": new_rank,
            })
    items.sort(key=lambda i: (i["from_val"], i["label"]))
    return items


def advantage_items(
    advantages: List[str],
    campaign_advantages: List[str],
) -> List[dict]:
    """One item per advantage (regular + campaign), alphabetised."""
    items: List[dict] = []
    for adv_id in advantages:
        adv = ADVANTAGES.get(adv_id)
        if adv is not None:
            items.append({"xp": adv.xp_cost, "label": adv.name})
    for adv_id in campaign_advantages:
        adv = CAMPAIGN_ADVANTAGES.get(adv_id)
        if adv is not None:
            items.append({"xp": adv.xp_cost, "label": adv.name})
    items.sort(key=lambda i: i["label"])
    return items


def disadvantage_items(
    disadvantages: List[str],
    campaign_disadvantages: List[str],
) -> List[dict]:
    """One item per disadvantage (regular + campaign), alphabetised. XP is negative."""
    items: List[dict] = []
    for dis_id in disadvantages:
        dis = DISADVANTAGES.get(dis_id)
        if dis is not None:
            items.append({"xp": -dis.xp_value, "label": dis.name})
    for dis_id in campaign_disadvantages:
        dis = CAMPAIGN_DISADVANTAGES.get(dis_id)
        if dis is not None:
            items.append({"xp": -dis.xp_value, "label": dis.name})
    items.sort(key=lambda i: i["label"])
    return items


def hrr_items(
    honor: float,
    rank: float,
    rank_locked: bool,
    recognition: float,
    recognition_halved: bool,
) -> List[dict]:
    """Honor / Rank / Recognition summary items, plus a permanent Wasp note."""
    items: List[dict] = []

    honor_xp = calculate_honor_xp(honor)
    if honor_xp != 0:
        items.append({
            "xp": honor_xp,
            "label": "Honor",
            "from_val": HONOR_START,
            "to_val": honor,
        })

    if not rank_locked:
        rank_xp = calculate_rank_xp(rank, campaign_default=RANK_START)
        if rank_xp != 0:
            items.append({
                "xp": rank_xp,
                "label": "Rank",
                "from_val": RANK_START,
                "to_val": rank,
            })

    if recognition_halved:
        items.append({
            "xp": -RECOGNITION_HALVE_START_XP,
            "label": "Recognition halved",
        })
        base = _halved_recognition_base()
        if recognition > base:
            extra = round((recognition - base) * RECOGNITION_COST_PER_ONE)
            if extra != 0:
                items.append({
                    "xp": extra,
                    "label": "Recognition",
                    "from_val": base,
                    "to_val": recognition,
                })
    else:
        rec_xp = calculate_recognition_xp(recognition, rank, halved=False)
        if rec_xp != 0:
            items.append({
                "xp": rec_xp,
                "label": "Recognition",
                "from_val": RECOGNITION_START,
                "to_val": recognition,
            })

    items.append({
        "xp": 0,
        "label": "Wasp Campaign characters begin at 7.5 Rank at no XP cost.",
        "note": True,
    })
    return items


def calculate_xp_breakdown(character_data: dict) -> dict:
    """Rich per-item breakdown for the expandable XP Summary on the sheet.

    Each category entry has shape ``{"label", "total", "items"}`` (or
    ``{"label", "total", "subsections"}`` for Skills). Campaign advantages and
    disadvantages are merged into the regular Advantages / Disadvantages
    categories. ``grand_total`` is the sum across all categories and matches
    ``calculate_total_xp(...)["total"]``.
    """
    school_ring = character_data.get("school_ring_choice", "")
    knack_data = character_data.get("knacks", {})
    dan = compute_dan(knack_data) if knack_data else 0

    rings_list = ring_xp_items(
        character_data.get("rings", {}), school_ring, dan=dan,
    )
    knacks_list = school_knack_xp_items(knack_data)
    skills_split = skill_xp_items(character_data.get("skills", {}))
    combat_list = combat_skill_xp_items(
        attack=character_data.get("attack", COMBAT_SKILL_START),
        parry=character_data.get("parry", COMBAT_SKILL_START),
    )
    adv_list = advantage_items(
        character_data.get("advantages", []),
        character_data.get("campaign_advantages", []),
    )
    dis_list = disadvantage_items(
        character_data.get("disadvantages", []),
        character_data.get("campaign_disadvantages", []),
    )
    hrr_list = hrr_items(
        honor=character_data.get("honor", HONOR_START),
        rank=character_data.get("rank", RANK_START),
        rank_locked=character_data.get("rank_locked", False),
        recognition=character_data.get("recognition", RECOGNITION_START),
        recognition_halved=character_data.get("recognition_halved", False),
    )

    rings_total = sum(i["xp"] for i in rings_list)
    knacks_total = sum(i["xp"] for i in knacks_list)
    skills_total = (
        sum(i["xp"] for i in skills_split["basic"])
        + sum(i["xp"] for i in skills_split["advanced"])
    )
    combat_total = sum(i["xp"] for i in combat_list)
    adv_total = sum(i["xp"] for i in adv_list)
    dis_total = sum(i["xp"] for i in dis_list)
    hrr_total = sum(i["xp"] for i in hrr_list if not i.get("note"))

    grand_total = (
        rings_total + knacks_total + skills_total + combat_total
        + adv_total + dis_total + hrr_total
    )

    return {
        "rings": {
            "label": "Rings",
            "total": rings_total,
            "rows": rings_list,
        },
        "school_knacks": {
            "label": "School Knacks",
            "total": knacks_total,
            "rows": knacks_list,
        },
        "skills": {
            "label": "Skills",
            "total": skills_total,
            "subsections": [
                {"label": "Basic Skills", "rows": skills_split["basic"]},
                {"label": "Advanced Skills", "rows": skills_split["advanced"]},
            ],
        },
        "combat_skills": {
            "label": "Attack / Parry",
            "total": combat_total,
            "rows": combat_list,
        },
        "advantages": {
            "label": "Advantages",
            "total": adv_total,
            "rows": adv_list,
        },
        "honor_rank_recognition": {
            "label": "Honor / Rank / Recognition",
            "total": hrr_total,
            "rows": hrr_list,
        },
        "disadvantages": {
            "label": "Disadvantages",
            "total": dis_total,
            "rows": dis_list,
        },
        "grand_total": grand_total,
    }


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

    # Compute Dan for 4th Dan ring discount
    knack_data = character_data.get("knacks", {})
    dan = compute_dan(knack_data) if knack_data else 0

    rings = calculate_ring_xp(character_data.get("rings", {}), school_ring, dan=dan)
    skills = calculate_skill_xp(character_data.get("skills", {}))
    knacks = calculate_knack_xp(knack_data)
    combat_skills = calculate_combat_skill_xp(
        attack=character_data.get("attack", COMBAT_SKILL_START),
        parry=character_data.get("parry", COMBAT_SKILL_START),
    )
    honor = calculate_honor_xp(character_data.get("honor", HONOR_START))
    if character_data.get("rank_locked", False):
        rank = 0
    else:
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
    campaign_advs = calculate_campaign_advantage_xp(
        character_data.get("campaign_advantages", []),
    )
    campaign_dises = calculate_campaign_disadvantage_xp(
        character_data.get("campaign_disadvantages", []),
    )

    total = (
        rings + skills + knacks + combat_skills + honor + rank + recognition
        + advantages + disadvantages + campaign_advs + campaign_dises
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
        "campaign_advantages": campaign_advs,
        "campaign_disadvantages": campaign_dises,
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
    attack_val = character_data.get("attack", COMBAT_SKILL_START)
    parry_val = character_data.get("parry", COMBAT_SKILL_START)
    for cs_name, cs_val in [("attack", attack_val), ("parry", parry_val)]:
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
    if parry_val > attack_val + 1:
        errors.append(
            f"Parry ({parry_val}) cannot exceed Attack ({attack_val}) + 1."
        )

    # -- Rings --
    knack_data = character_data.get("knacks", {})
    dan = compute_dan(knack_data) if knack_data else 0
    rings = character_data.get("rings", {})
    for ring_name in RING_NAMES:
        value = rings.get(ring_name, RING_DEFAULT)
        # School ring minimum: 3 (base) or 4 (at 4th Dan).
        # School ring maximum: 6 normally, 7 at 4th Dan.
        if ring_name == school_ring:
            min_val = 4 if dan >= 4 else RING_SCHOOL_DEFAULT
            max_val = RING_MAX_SCHOOL + (1 if dan >= 4 else 0)
        else:
            min_val = RING_DEFAULT
            max_val = RING_MAX_NORMAL
        if value < min_val:
            errors.append(
                f"Ring {ring_name} ({value}) is below minimum ({min_val})"
                f"{' (school ring)' if ring_name == school_ring else ''}."
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
    recognition = character_data.get("recognition", RECOGNITION_START)
    halved = character_data.get("recognition_halved", False)
    max_rec = max_recognition(rank_val)
    min_recognition = _halved_recognition_base() if halved else RECOGNITION_START

    if recognition > max_rec:
        errors.append(
            f"Recognition ({recognition}) exceeds 150% of Rank "
            f"({max_rec})."
        )
    if recognition < min_recognition:
        errors.append(
            f"Recognition ({recognition}) is below minimum "
            f"({min_recognition})."
        )

    # -- Advantage / disadvantage detail fields --
    advantage_details = character_data.get("advantage_details") or {}
    all_taken_ids = (
        (character_data.get("advantages") or [])
        + (character_data.get("disadvantages") or [])
    )
    for taken_id in all_taken_ids:
        field_def = ADVANTAGE_DETAIL_FIELDS.get(taken_id)
        if field_def and "text" in field_def:
            detail = advantage_details.get(taken_id) or {}
            text_val = (detail.get("text") or "").strip()
            if not text_val:
                # Look up the display name from either advantages or disadvantages
                lookup = ADVANTAGES.get(taken_id) or DISADVANTAGES.get(taken_id)
                name = lookup.name if lookup else taken_id
                errors.append(
                    f"{name} requires a description: \"{field_def['text']}\""
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
