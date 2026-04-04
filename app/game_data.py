"""
L7R (Legend of the Five Rings Homebrew) Character Builder - Game Data Module

All game rules, schools, skills, advantages, disadvantages, knacks, spells,
and cost calculations are defined here as pure Python dataclasses and constants.
No database or framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# RINGS
# ---------------------------------------------------------------------------

class Ring(str, Enum):
    AIR = "Air"
    FIRE = "Fire"
    EARTH = "Earth"
    WATER = "Water"
    VOID = "Void"


RING_NAMES: List[str] = [r.value for r in Ring]

RING_DEFAULT = 2
RING_SCHOOL_DEFAULT = 3
RING_MAX_NORMAL = 5
RING_MAX_SCHOOL = 6


def ring_raise_cost(new_value: int) -> int:
    """Cost in XP to raise a ring to *new_value*."""
    return 5 * new_value


# ---------------------------------------------------------------------------
# SKILL COSTS
# ---------------------------------------------------------------------------

BASIC_SKILL_COSTS: Dict[int, int] = {
    # new_rank -> xp cost
    1: 2,
    2: 2,
    3: 3,
    4: 3,
    5: 3,
}

ADVANCED_SKILL_COSTS: Dict[int, int] = {
    1: 4,
    2: 4,
    3: 6,
    4: 8,
    5: 10,
}

KNACK_COSTS = ADVANCED_SKILL_COSTS  # knacks use advanced cost table

SKILL_MAX = 5
KNACK_MAX = 5


def skill_raise_cost(new_rank: int, is_advanced: bool) -> int:
    """Return XP cost to raise a skill (or knack) to *new_rank*."""
    table = ADVANCED_SKILL_COSTS if is_advanced else BASIC_SKILL_COSTS
    return table[new_rank]


def total_skill_cost(target_rank: int, is_advanced: bool) -> int:
    """Total XP from rank 0 to *target_rank*."""
    table = ADVANCED_SKILL_COSTS if is_advanced else BASIC_SKILL_COSTS
    return sum(table[r] for r in range(1, target_rank + 1))


# ---------------------------------------------------------------------------
# HONOR / RANK / RECOGNITION
# ---------------------------------------------------------------------------

HONOR_START = 1.0
HONOR_MAX = 5.0
HONOR_COST_PER_HALF = 1  # 1 XP per 0.5 Honor

RANK_START = 1.0
RANK_COST_PER_HALF = 1  # same as Honor

RECOGNITION_MAX_FACTOR = 1.5  # up to 150% of Rank
RECOGNITION_COST_PER_ONE = 1  # 1 XP per 1.0 Recognition
RECOGNITION_HALVE_START_XP = 3  # 3 XP to halve starting Recognition


# ---------------------------------------------------------------------------
# COMBAT REFERENCE
# ---------------------------------------------------------------------------

COMBAT_REFERENCE = {
    "attack_ring": Ring.FIRE,
    "attack_skill_start": 1,
    "tn_to_hit_formula": "5 + 5 * defender_parry",
    "parry_ring": Ring.AIR,
    "parry_skill_start": 1,
    "parry_tn": "attacker_roll_result",
    "wound_check_roll": "(Water+1)k(Water)",
    "wound_check_tn": "light_wound_total",
    "initiative_roll": "(Void+1) dice, keep all but highest, no reroll 10s",
    "void_points_max": "lowest_ring",
    "void_regen": "1 per 8 hours sleep",
    "crippled_threshold": "serious_wounds >= Earth",
    "mortally_wounded_threshold": "serious_wounds >= 2 * Earth",
    "weapons": {
        "katana": "4k2",
        "spear": "3k2",
        "wakizashi": "3k2",
        "knife": "2k2",
        "unarmed": "0k2",
    },
    "damage_formula": "weapon_dice + Fire_ring rolled dice",
}


# ---------------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    ring: Ring
    category: str  # "social" or "knowledge"
    is_advanced: bool
    description: str
    roll_description: str


@dataclass(frozen=True)
class SchoolKnack:
    id: str
    name: str
    ring: Optional[str]  # Ring value, "varies", or None
    description: str


@dataclass(frozen=True)
class School:
    id: str
    name: str
    school_ring: str  # Ring value or special like "any non-Void"
    category: str  # bushi, counterattack, duelist, monk, investigator, court, artisan, spellcaster
    special_ability: str
    school_knacks: List[str]  # list of knack ids
    techniques: Dict[int, str]  # dan level -> description


@dataclass(frozen=True)
class Advantage:
    id: str
    name: str
    xp_cost: int
    description: str


@dataclass(frozen=True)
class Disadvantage:
    id: str
    name: str
    xp_value: int
    description: str


@dataclass(frozen=True)
class Spell:
    id: str
    name: str
    element: Ring
    mastery_level: int
    description: str


# ---------------------------------------------------------------------------
# SKILLS
# ---------------------------------------------------------------------------

_SKILLS_LIST: List[Skill] = [
    # --- Social Skills (Basic, rolled with Air) ---
    Skill(
        id="bragging",
        name="Bragging",
        ring=Ring.AIR,
        category="social",
        is_advanced=False,
        description=(
            "Open roll to convince someone of your talent or qualifications. "
            "Bonus equals twice your Recognition plus twice your Honor."
        ),
        roll_description="Roll Bragging + Air. Bonus: +2x Recognition + 2x Honor.",
    ),
    Skill(
        id="etiquette",
        name="Etiquette",
        ring=Ring.AIR,
        category="social",
        is_advanced=False,
        description=(
            "Open roll for formal situations and first impressions."
        ),
        roll_description="Roll Etiquette + Air.",
    ),
    Skill(
        id="intimidation",
        name="Intimidation",
        ring=Ring.AIR,
        category="social",
        is_advanced=False,
        description=(
            "Open roll for threats. The GM sets hidden thresholds that "
            "determine the degree of success."
        ),
        roll_description="Roll Intimidation + Air. GM sets hidden thresholds.",
    ),
    Skill(
        id="sincerity",
        name="Sincerity",
        ring=Ring.AIR,
        category="social",
        is_advanced=False,
        description=(
            "Contested vs interrogation when lying. Open roll for commitments. "
            "Bonus equals twice your Honor on open rolls."
        ),
        roll_description=(
            "Roll Sincerity + Air. Contested vs Interrogation when lying. "
            "Bonus: +2x Honor on open rolls."
        ),
    ),
    Skill(
        id="sneaking",
        name="Sneaking",
        ring=Ring.AIR,
        category="social",
        is_advanced=False,
        description=(
            "Open roll to be unremarkable. Contested vs investigation to stay hidden."
        ),
        roll_description=(
            "Roll Sneaking + Air. Open to be unremarkable; contested vs Investigation to stay hidden."
        ),
    ),
    Skill(
        id="tact",
        name="Tact",
        ring=Ring.AIR,
        category="social",
        is_advanced=False,
        description=(
            "Open roll before saying something offensive. Contested vs manipulation."
        ),
        roll_description="Roll Tact + Air. Contested vs Manipulation.",
    ),

    # --- Social Skills (Advanced, rolled with Air) ---
    Skill(
        id="acting",
        name="Acting",
        ring=Ring.AIR,
        category="social",
        is_advanced=True,
        description=(
            "Grants 1 free raise per rank on sincerity, intimidation, and sneaking rolls. "
            "Contested vs interrogation for impersonation."
        ),
        roll_description=(
            "Roll Acting + Air. Grants 1 free raise per rank on sincerity, intimidation, sneaking. "
            "Contested vs Interrogation for impersonation."
        ),
    ),
    Skill(
        id="interrogation",
        name="Interrogation",
        ring=Ring.AIR,
        category="social",
        is_advanced=True,
        description=(
            "Contested vs sincerity to detect lies. "
            "Excess of 10+ reveals concealment; 20+ reveals motivations."
        ),
        roll_description=(
            "Roll Interrogation + Air. Contested vs Sincerity. "
            "10+ excess reveals concealment; 20+ excess reveals motivations."
        ),
    ),
    Skill(
        id="manipulation",
        name="Manipulation",
        ring=Ring.AIR,
        category="social",
        is_advanced=True,
        description=(
            "Contested vs tact. Success forces acknowledgment, retraction, or "
            "apology based on margin of success."
        ),
        roll_description=(
            "Roll Manipulation + Air. Contested vs Tact. "
            "Success forces acknowledgment/retraction/apology based on margin."
        ),
    ),

    # --- Knowledge Skills (Basic, rolled with Water) ---
    Skill(
        id="culture",
        name="Culture",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=False,
        description=(
            "Open roll for arts, fashion, and literature. "
            "Gift purchasing gets free raises equal to your commerce skill."
        ),
        roll_description=(
            "Roll Culture + Water. Free raises on gift purchases = Commerce skill."
        ),
    ),
    Skill(
        id="heraldry",
        name="Heraldry",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=False,
        description=(
            "TN-based (15-75) modified by familiarity, research, and Recognition."
        ),
        roll_description=(
            "Roll Heraldry + Water. TN 15-75 modified by familiarity, research, Recognition."
        ),
    ),
    Skill(
        id="investigation",
        name="Investigation",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=False,
        description=(
            "Finding clues, forgeries, codes. The GM does NOT reveal the TN "
            "(exception to normal rules)."
        ),
        roll_description=(
            "Roll Investigation + Water. GM does NOT reveal TN (special exception)."
        ),
    ),
    Skill(
        id="law",
        name="Law",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=False,
        description=(
            "Open or contested roll for legality arguments. "
            "Can compel NPC compliance."
        ),
        roll_description="Roll Law + Water. Open/contested for legality arguments.",
    ),
    Skill(
        id="precepts",
        name="Precepts",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=False,
        description=(
            "Arguing righteousness via bushido and Shinsei. "
            "Bonus equals twice your Honor."
        ),
        roll_description="Roll Precepts + Water. Bonus: +2x Honor.",
    ),
    Skill(
        id="strategy",
        name="Strategy",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=False,
        description=(
            "Tactics, troop command, Shadowlands creatures, skill games. "
            "Contested for battles and games."
        ),
        roll_description="Roll Strategy + Water. Contested for battles/games.",
    ),

    # --- Knowledge Skills (Advanced, rolled with Water) ---
    Skill(
        id="commerce",
        name="Commerce",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=True,
        description="Money, taxes, business. Open or contested.",
        roll_description="Roll Commerce + Water. Open/contested.",
    ),
    Skill(
        id="history",
        name="History",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=True,
        description=(
            "Grants 1 free raise per rank on culture, law, and strategy rolls. "
            "Grants free raises on heraldry (cap 25 total). "
            "Open or contested for citing historical examples."
        ),
        roll_description=(
            "Roll History + Water. Grants 1 free raise/rank on culture, law, strategy. "
            "Free raises on heraldry (cap 25 total). Open/contested for examples."
        ),
    ),
    Skill(
        id="underworld",
        name="Underworld",
        ring=Ring.WATER,
        category="knowledge",
        is_advanced=True,
        description=(
            "Knowledge of bandits, smugglers, bloodspeakers, and ninja. "
            "Open or contested."
        ),
        roll_description="Roll Underworld + Water. Open/contested.",
    ),
]

SKILLS: Dict[str, Skill] = {s.id: s for s in _SKILLS_LIST}


# ---------------------------------------------------------------------------
# SCHOOL KNACKS
# ---------------------------------------------------------------------------

_KNACKS_LIST: List[SchoolKnack] = [
    SchoolKnack(
        id="absorb_void",
        name="Absorb Void",
        ring=None,
        description=(
            "Ability to absorb and redirect void energy. "
            "Used by Isawa Ishi shugenja."
        ),
    ),
    SchoolKnack(
        id="athletics",
        name="Athletics",
        ring="varies",
        description=(
            "Physical feats of agility, climbing, running, swimming, and acrobatics."
        ),
    ),
    SchoolKnack(
        id="commune",
        name="Commune",
        ring="varies",
        description=(
            "Commune with the elemental kami of a chosen element. "
            "Rolled with the ring of the element communed with."
        ),
    ),
    SchoolKnack(
        id="conviction",
        name="Conviction",
        ring=None,
        description=(
            "Inner spiritual resolve. Used by monks and priests to fuel "
            "special abilities and resist spiritual corruption."
        ),
    ),
    SchoolKnack(
        id="counterattack",
        name="Counterattack",
        ring=Ring.FIRE.value,
        description=(
            "Attack made in response to being attacked. Rolled with Fire. "
            "Normally costs 2 action dice as an interrupt action; "
            "some schools reduce this to 1."
        ),
    ),
    SchoolKnack(
        id="detect_taint",
        name="Detect Taint",
        ring=Ring.EARTH.value,
        description=(
            "Sense the presence and degree of Shadowlands Taint in a target. "
            "Rolled with Earth."
        ),
    ),
    SchoolKnack(
        id="discern_honor",
        name="Discern Honor",
        ring=None,
        description=(
            "Sense the approximate Honor level of another character. "
            "No roll required; passive ability."
        ),
    ),
    SchoolKnack(
        id="double_attack",
        name="Double Attack",
        ring=Ring.FIRE.value,
        description=(
            "Make two attacks in a single action. Rolled with Fire. "
            "Each attack is rolled separately."
        ),
    ),
    SchoolKnack(
        id="dragon_tattoo",
        name="Dragon Tattoo",
        ring=None,
        description=(
            "Mystical tattoos of the Togashi order that grant supernatural abilities. "
            "Each tattoo has a unique effect."
        ),
    ),
    SchoolKnack(
        id="feint",
        name="Feint",
        ring=Ring.FIRE.value,
        description=(
            "A deceptive attack that sets up future strikes. Rolled with Fire. "
            "May grant temporary void points or TN reductions depending on school."
        ),
    ),
    SchoolKnack(
        id="iaijutsu",
        name="Iaijutsu",
        ring=Ring.FIRE.value,
        description=(
            "The art of the draw-cut. Rolled with Fire for the strike. "
            "The iaijutsu stance phase uses Air. "
            "Used in formal duels and surprise attacks."
        ),
    ),
    SchoolKnack(
        id="kharmic_spin",
        name="Kharmic Spin",
        ring=Ring.VOID.value,
        description=(
            "Manipulate fate and kharmic energy. Rolled with Void. "
            "Used by Isawa Ishi shugenja."
        ),
    ),
    SchoolKnack(
        id="lunge",
        name="Lunge",
        ring=Ring.FIRE.value,
        description=(
            "An aggressive, committed attack that sacrifices defense for offense. "
            "Rolled with Fire."
        ),
    ),
    SchoolKnack(
        id="oppose_knowledge",
        name="Oppose Knowledge",
        ring=Ring.AIR.value,
        description=(
            "Counter or undermine another character's knowledge-based arguments. "
            "Rolled with Air."
        ),
    ),
    SchoolKnack(
        id="oppose_social",
        name="Oppose Social",
        ring=Ring.WATER.value,
        description=(
            "Counter or undermine another character's social maneuvers. "
            "Rolled with Water."
        ),
    ),
    SchoolKnack(
        id="otherworldliness",
        name="Otherworldliness",
        ring=None,
        description=(
            "An aura of spiritual detachment and mystical presence. "
            "Passive social effect; no roll required."
        ),
    ),
    SchoolKnack(
        id="pontificate",
        name="Pontificate",
        ring=Ring.WATER.value,
        description=(
            "Deliver lengthy speeches and sermons that inspire or persuade. "
            "Rolled with Water."
        ),
    ),
    SchoolKnack(
        id="presence",
        name="Presence",
        ring=Ring.WATER.value,
        description=(
            "Project authority and command attention in a scene. "
            "Rolled with Water."
        ),
    ),
    SchoolKnack(
        id="spellcasting",
        name="Spellcasting",
        ring="varies",
        description=(
            "Cast elemental spells. Rolled with the ring of the element being cast. "
            "Requires the Shugenja school."
        ),
    ),
    SchoolKnack(
        id="worldliness",
        name="Worldliness",
        ring=None,
        description=(
            "Broad familiarity with the customs, practices, and ways of the world. "
            "Passive benefit; no roll required."
        ),
    ),
]

SCHOOL_KNACKS: Dict[str, SchoolKnack] = {k.id: k for k in _KNACKS_LIST}


# ---------------------------------------------------------------------------
# SCHOOLS
# ---------------------------------------------------------------------------

_SCHOOLS_LIST: List[School] = [
    # ======================== BUSHI SCHOOLS ========================

    School(
        id="akodo_bushi",
        name="Akodo Bushi",
        school_ring=Ring.WATER.value,
        category="bushi",
        special_ability=(
            "You gain four temporary void points after a successful feint "
            "and one void point after an unsuccessful feint."
        ),
        school_knacks=["double_attack", "feint", "iaijutsu"],
        techniques={
            1: (
                "Roll an extra die on attack, double attack, and wound check rolls."
            ),
            2: "Free raise on wound checks.",
            3: (
                "Excess from wound checks divided by 5 adds a bonus to future "
                "attack rolls, scaled by attack skill."
            ),
            4: (
                "+1 Water; Water ring costs 5 fewer XP to raise; "
                "spend void points for free raises on wound checks."
            ),
            5: (
                "Spend void points after receiving damage to inflict 10 light wounds "
                "per void point spent back to attacker (capped by damage taken)."
            ),
        },
    ),

    School(
        id="bayushi_bushi",
        name="Bayushi Bushi",
        school_ring=Ring.FIRE.value,
        category="bushi",
        special_ability=(
            "Add 1k1 to the damage rolls of those attacks per void point spent."
        ),
        school_knacks=["double_attack", "feint", "iaijutsu"],
        techniques={
            1: "Roll an extra die on iaijutsu, double attack, and wound check rolls.",
            2: "Free raise on double attack rolls.",
            3: (
                "Feints deal damage based on attack skill; "
                "no extra damage dice are added."
            ),
            4: (
                "+1 Fire; Fire ring costs 5 fewer XP to raise; "
                "free raise on any attack after a successful or unsuccessful feint."
            ),
            5: (
                "Failed wound checks calculate serious wounds as half light wounds."
            ),
        },
    ),

    School(
        id="hida_bushi",
        name="Hida Bushi",
        school_ring=Ring.WATER.value,
        category="bushi",
        special_ability=(
            "Counterattack as an interrupt action by spending only 1 action die, "
            "but the attacker gets a free raise."
        ),
        school_knacks=["counterattack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll an extra die on attack, counterattack, and wound check rolls.",
            2: "Free raise on all counterattack rolls.",
            3: (
                "Reroll 2X dice on counterattacks or X dice on other attacks; "
                "half effectiveness when crippled but reroll 10s."
            ),
            4: (
                "+1 Water; Water ring costs 5 fewer XP to raise; "
                "trade 2 serious wounds to reset light wounds to 0."
            ),
            5: (
                "Add counterattack excess to wound check; "
                "may counterattack after seeing damage rolls."
            ),
        },
    ),

    School(
        id="mirumoto_bushi",
        name="Mirumoto Bushi",
        school_ring=Ring.VOID.value,
        category="bushi",
        special_ability=(
            "Free ring boost can apply to Void. "
            "Parries give you one temporary void point."
        ),
        school_knacks=["counterattack", "double_attack", "iaijutsu"],
        techniques={
            1: "Roll an extra die on attack, double attack, and parry rolls.",
            2: "Free raise on parry rolls.",
            3: (
                "At the start of each round, gain 2X points to decrease action "
                "phases for parries or +2 on any attack or parry roll."
            ),
            4: (
                "+1 Void; Void ring costs 5 fewer XP to raise; "
                "failed parries reduce fewer extra damage dice."
            ),
            5: "Void points provide +10 when spent on combat rolls.",
        },
    ),

    School(
        id="matsu_bushi",
        name="Matsu Bushi",
        school_ring=Ring.FIRE.value,
        category="bushi",
        special_ability=(
            "Always roll 10 dice when rolling initiative, keeping the usual number."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll an extra die on double attack, iaijutsu, and wound check rolls.",
            2: "Free raise on iaijutsu rolls.",
            3: (
                "Spend a void point to add 3X to a future wound check after seeing the roll."
            ),
            4: (
                "+1 Fire; Fire ring costs 5 fewer XP to raise; "
                "near-misses on double attacks still hit with no bonus damage."
            ),
            5: (
                "After dealing serious wounds, reset the defender's light wounds "
                "to 15 instead of 0."
            ),
        },
    ),

    School(
        id="otaku_bushi",
        name="Otaku Bushi",
        school_ring=Ring.FIRE.value,
        category="bushi",
        special_ability=(
            "Make a lunge attack at your attacker as an interrupt action "
            "at the cost of one action die."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll an extra die on iaijutsu, lunge, and wound check rolls.",
            2: "Free raise on wound checks.",
            3: (
                "Increase attacker's next action dice by (6 - Fire) minimum 1, "
                "scaled by attack skill, maximum phase 10."
            ),
            4: (
                "+1 Fire; Fire ring costs 5 fewer XP to raise; "
                "lunge always rolls an extra damage die even if unsuccessfully parried."
            ),
            5: (
                "After a successful attack, spend 10 dice to automatically deal "
                "1 serious wound; once per damage roll."
            ),
        },
    ),

    School(
        id="shinjo_bushi",
        name="Shinjo Bushi",
        school_ring=Ring.AIR.value,
        category="bushi",
        special_ability=(
            "Each action you take in combat has a bonus of 2X, "
            "where X is the number of phases held."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll an extra die on double attack, initiative, and parry rolls.",
            2: "Free raise on parry rolls.",
            3: (
                "After a parry, decrease all action dice by X (attack skill); "
                "new values count as held since the reduction."
            ),
            4: (
                "+1 Air; Air ring costs 5 fewer XP to raise; "
                "highest action die set to 1 at round start."
            ),
            5: (
                "After a successful parry, add parry excess to a future wound "
                "check after seeing the roll."
            ),
        },
    ),

    School(
        id="yogo_warden",
        name="Yogo Warden",
        school_ring=Ring.EARTH.value,
        category="bushi",
        special_ability=(
            "Gain a temporary void point every time you take a serious wound."
        ),
        school_knacks=["double_attack", "iaijutsu", "feint"],
        techniques={
            1: "Roll an extra die on attack, damage, and wound check rolls.",
            2: "Free raise on all wound checks.",
            3: (
                "Spend a void point to reduce your current light wound total by 2X."
            ),
            4: (
                "+1 Earth; Earth ring costs 5 fewer XP to raise; "
                "extra free raise per void point spent on wound checks."
            ),
            5: "(Unreleased)",
        },
    ),

    # =================== COUNTERATTACK SCHOOLS ====================

    School(
        id="daidoji_yojimbo",
        name="Daidoji Yojimbo",
        school_ring=Ring.WATER.value,
        category="counterattack",
        special_ability=(
            "Counterattack as an interrupt action by spending only 1 action die; "
            "your opponent gets a free raise. "
            "May counterattack for others."
        ),
        school_knacks=["counterattack", "double_attack", "iaijutsu"],
        techniques={
            1: "Roll an extra die on attack, counterattack, and wound check rolls.",
            2: "Free raise on counterattack rolls.",
            3: (
                "Add X free raises to wound checks from counterattack damage."
            ),
            4: (
                "+1 Water; Water ring costs 5 fewer XP to raise; "
                "intercept adjacent character damage before rolling."
            ),
            5: (
                "Lower next attacker TN by wound check excess; minimum 0."
            ),
        },
    ),

    School(
        id="shiba_bushi",
        name="Shiba Bushi",
        school_ring=Ring.AIR.value,
        category="counterattack",
        special_ability=(
            "Parry as an interrupt action by spending your lowest 1 action die. "
            "Parry attacks directed at other characters."
        ),
        school_knacks=["counterattack", "double_attack", "iaijutsu"],
        techniques={
            1: "Roll an extra die on double attack, parry, and wound check rolls.",
            2: "Free raise on parry rolls.",
            3: (
                "Parries deal (2X)k1 damage; no extra damage dice from ring or TN excess."
            ),
            4: (
                "+1 Air; Air ring costs 5 fewer XP to raise; "
                "extra 3k1 on wound checks."
            ),
            5: (
                "After a successful parry, lower next attacker TN by parry excess; "
                "can go negative."
            ),
        },
    ),

    # ===================== DUELIST SCHOOLS ========================

    School(
        id="isawa_duelist",
        name="Isawa Duelist",
        school_ring=Ring.WATER.value,
        category="duelist",
        special_ability=(
            "Add your Water instead of Fire to your rolled damage dice."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll an extra die on double attack, lunge, and wound check rolls.",
            2: "Free raise on wound checks.",
            3: (
                "Trade -5 TN to be hit next round for +3X on attack; "
                "no penalty if the attack is parried."
            ),
            4: (
                "+1 Water; Water ring costs 5 fewer XP to raise; "
                "lunge once per round as an interrupt action."
            ),
            5: (
                "After a successful wound check, add excess to a future wound "
                "check this combat."
            ),
        },
    ),

    School(
        id="kakita_duelist",
        name="Kakita Duelist",
        school_ring=Ring.FIRE.value,
        category="duelist",
        special_ability=(
            "Your 10s on initiative rolls are in Phase 0 and can be used "
            "for interrupt attacks."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll an extra die on double attack, iaijutsu, and initiative rolls.",
            2: "Free raise on iaijutsu rolls.",
            3: (
                "Attacks gain a bonus per phase before the defender's next action; "
                "know the next action of enemies in range."
            ),
            4: (
                "+1 Fire; Fire ring costs 5 fewer XP to raise; "
                "free raise on iaijutsu damage rolls."
            ),
            5: (
                "At Phase 0, contested iaijutsu with bonus damage dice per 5 excess "
                "or penalty per 5 deficit."
            ),
        },
    ),

    # ====================== MONK SCHOOLS ==========================

    School(
        id="brotherhood_of_shinsei_monk",
        name="Brotherhood of Shinsei Monk",
        school_ring="any non-Void",
        category="monk",
        special_ability=(
            "Roll and keep one extra die for damage rolls from unarmed attacks."
        ),
        school_knacks=["conviction", "otherworldliness", "worldliness"],
        techniques={
            1: "Roll an extra die on attack, damage, and wound check rolls.",
            2: "Free raise on all attack rolls.",
            3: (
                "Gain 2X free raises per adventure (X = precepts skill); "
                "apply to history, law, precepts, wound checks, attack; "
                "can lower action dice by 5."
            ),
            4: (
                "+1 to a non-Void ring; that ring costs 5 fewer XP to raise; "
                "failed parries don't lower damage dice."
            ),
            5: (
                "After being attacked but before damage, spend an action die to "
                "counter-attack; negates the original attack if successful."
            ),
        },
    ),

    School(
        id="togashi_ise_zumi",
        name="Togashi Ise Zumi",
        school_ring=Ring.VOID.value,
        category="monk",
        special_ability=(
            "Roll either 1 or 3 extra action dice at the beginning of each combat round."
        ),
        school_knacks=["athletics", "conviction", "dragon_tattoo"],
        techniques={
            1: "Roll an extra die on attack, parry, and athletics rolls.",
            2: "Free raise on athletics rolls.",
            3: (
                "Gain 4X free raises daily (X = precepts skill) for athletics; "
                "max X per roll."
            ),
            4: (
                "+1 to any ring; that ring costs 5 fewer XP to raise; "
                "reroll any contested roll once after seeing the result."
            ),
            5: "Spend 1 void point to heal 2 serious wounds at any time.",
        },
    ),

    # ============== INVESTIGATOR / SUPPORT SCHOOLS ================

    School(
        id="hiruma_scout",
        name="Hiruma Scout",
        school_ring=Ring.AIR.value,
        category="investigator",
        special_ability=(
            "Two allies fighting on your left and right have their TN to be hit "
            "raised by 5."
        ),
        school_knacks=["double_attack", "feint", "iaijutsu"],
        techniques={
            1: "Roll an extra die on initiative, parry, and wound check rolls.",
            2: "Free raise on parry rolls.",
            3: (
                "After a parry, add 2X to your next attack against the attacker "
                "or adjacent targets."
            ),
            4: (
                "+1 Air; Air ring costs 5 fewer XP to raise; "
                "lower action dice by 2 (minimum 1) after rolling initiative."
            ),
            5: (
                "After a parry, the attacker deals 10 fewer light wounds on "
                "their next 2 damage rolls."
            ),
        },
    ),

    School(
        id="kitsuki_magistrate",
        name="Kitsuki Magistrate",
        school_ring=Ring.WATER.value,
        category="investigator",
        special_ability=(
            "Use Water for interrogation rolls and add twice your Water "
            "to all attack rolls."
        ),
        school_knacks=["discern_honor", "iaijutsu", "presence"],
        techniques={
            1: "Roll an extra die on investigation, interrogation, and wound check rolls.",
            2: "Free raise on interrogation rolls.",
            3: (
                "Gain 2X free raises per adventure (X = investigation skill); "
                "apply to interrogation, intimidation, law, underworld, attack, "
                "wound checks; max X per roll."
            ),
            4: (
                "+1 Water; Water ring costs 5 fewer XP to raise; "
                "automatically know target's Void, parry, and next action phase in combat."
            ),
            5: (
                "Reduce targeted characters' Air, Fire, and Water by 1; "
                "limited by total experience."
            ),
        },
    ),

    School(
        id="kuni_witch_hunter",
        name="Kuni Witch Hunter",
        school_ring=Ring.EARTH.value,
        category="investigator",
        special_ability=(
            "Never become Tainted. Extra (X+1)k(X+1) on wound checks "
            "based on target's Shadowlands Taint level."
        ),
        school_knacks=["detect_taint", "iaijutsu", "presence"],
        techniques={
            1: "Roll an extra die on damage, interrogation, and wound check rolls.",
            2: "Free raise on interrogation rolls.",
            3: (
                "Gain 2X free raises per adventure (X = investigation skill); "
                "apply to interrogation, intimidation, law, underworld, attack, "
                "wound checks, damage vs Tainted; max X per roll."
            ),
            4: (
                "+1 Earth; Earth ring costs 5 fewer XP to raise; "
                "extra action die (attacks only vs Tainted)."
            ),
            5: (
                "After a wound check, inflict light wounds back on a Tainted attacker."
            ),
        },
    ),

    # ================ COURT & MERCHANT SCHOOLS ====================

    School(
        id="courtier",
        name="Courtier",
        school_ring=Ring.AIR.value,
        category="court",
        special_ability="Add your Air to all attack and damage rolls.",
        school_knacks=["discern_honor", "oppose_social", "worldliness"],
        techniques={
            1: "Roll an extra die on tact, manipulation, and wound check rolls.",
            2: "Free raise on manipulation rolls.",
            3: (
                "Gain 2X free raises per adventure (X = tact skill); "
                "apply to heraldry, manipulation, sincerity, tact, attack, "
                "wound checks; max X per roll."
            ),
            4: (
                "+1 Air; Air ring costs 5 fewer XP to raise; "
                "gain a temporary void point after a successful attack or "
                "manipulation per target."
            ),
            5: "Add your Air to all TN and contested rolls for attack rolls.",
        },
    ),

    School(
        id="doji_artisan",
        name="Doji Artisan",
        school_ring="Air or Water",
        category="court",
        special_ability=(
            "Spend a void point to counterattack as an interrupt action. "
            "Void point still gives +1k1. "
            "Bonus equal to attacker's roll divided by 5."
        ),
        school_knacks=["counterattack", "oppose_social", "worldliness"],
        techniques={
            1: "Roll an extra die on counterattack, manipulation, and wound check rolls.",
            2: "Free raise on manipulation.",
            3: (
                "Gain 2X free raises per adventure (X = culture skill); "
                "apply to bragging, culture, heraldry, manipulation, "
                "counterattack, wound checks; max X per roll."
            ),
            4: (
                "+1 Air or Water; that ring costs 5 fewer XP to raise; "
                "bonus equal to current phase when attacking untouched targets."
            ),
            5: (
                "On TN/contested rolls, gain (X-10)/5 bonus where X is the "
                "opponent's result."
            ),
        },
    ),

    School(
        id="ide_diplomat",
        name="Ide Diplomat",
        school_ring="any non-Void",
        category="court",
        special_ability=(
            "After a feint which met its TN, lower the TN of the target by 10 "
            "the next time they are attacked."
        ),
        school_knacks=["double_attack", "feint", "worldliness"],
        techniques={
            1: "Roll an extra die on precepts and two chosen roll types.",
            2: "Free raise on any chosen roll type.",
            3: (
                "After any roll, spend a void point to subtract Xk1; "
                "know all contested results except sincerity/interrogation."
            ),
            4: (
                "+1 to a non-Void ring; that ring costs 5 fewer XP to raise; "
                "regain an extra void point nightly."
            ),
            5: (
                "Gain a temporary void point whenever spending non-technique "
                "void points."
            ),
        },
    ),

    School(
        id="merchant",
        name="Merchant",
        school_ring=Ring.WATER.value,
        category="court",
        special_ability="Spend void points after your initial roll.",
        school_knacks=["discern_honor", "oppose_knowledge", "worldliness"],
        techniques={
            1: "Roll an extra die on interrogation, sincerity, and wound check rolls.",
            2: "Free raise on interrogation rolls.",
            3: (
                "Gain 2X free raises per adventure (X = sincerity skill); "
                "apply to commerce, heraldry, interrogation, sincerity, "
                "attack, wound checks; max X per roll."
            ),
            4: (
                "+1 Water; Water ring costs 5 fewer XP to raise; "
                "Rank considered 5.0 higher for stipend."
            ),
            5: (
                "After any non-initiative roll, reroll dice totaling 5*(X-1) "
                "where X is the number rerolled; spend void before or after."
            ),
        },
    ),

    School(
        id="shosuro_actor",
        name="Shosuro Actor",
        school_ring=Ring.AIR.value,
        category="court",
        special_ability=(
            "Roll extra dice equal to your acting skill on attack, parry, "
            "and wound check rolls."
        ),
        school_knacks=["athletics", "discern_honor", "pontificate"],
        techniques={
            1: "Roll an extra die on attack, sincerity, and wound check rolls.",
            2: "Free raise on sincerity rolls.",
            3: (
                "Gain 2X free raises per adventure (X = sincerity skill); "
                "apply to acting, heraldry, sincerity, sneaking, attack, "
                "wound checks; max X per roll."
            ),
            4: (
                "+1 Air; Air ring costs 5 fewer XP to raise; "
                "Rank considered 5.0 higher for stipend."
            ),
            5: (
                "After TN/contested rolls, add your lowest three dice to the result."
            ),
        },
    ),

    # =============== ARTISAN / KNOWLEDGE SCHOOLS ===================

    School(
        id="ikoma_bard",
        name="Ikoma Bard",
        school_ring="any non-Void",
        category="artisan",
        special_ability=(
            "Force the opponent to spend their next available action die to "
            "attempt to parry; they do not get a free raise."
        ),
        school_knacks=["discern_honor", "oppose_knowledge", "oppose_social"],
        techniques={
            1: "Roll an extra die on attack, bragging, and wound check rolls.",
            2: "Free raise on attack rolls.",
            3: (
                "Gain 2X free raises per adventure (X = bragging skill); "
                "apply to bragging, culture, heraldry, intimidation, attack, "
                "wound checks; max X per roll."
            ),
            4: (
                "+1 to a non-Void ring; that ring costs 5 fewer XP to raise; "
                "unparried attacks always roll 10 dice."
            ),
            5: (
                "Once per round, apply the Oppose knack or Special Ability again."
            ),
        },
    ),

    # ================== SPELLCASTER SCHOOLS =======================

    School(
        id="isawa_ishi",
        name="Isawa Ishi",
        school_ring=Ring.VOID.value,
        category="spellcaster",
        special_ability=(
            "Maximum void points equals highest ring plus school rank. "
            "Regain lowest Ring per night, one per 2 hours partial. "
            "May not spend more than lowest Ring minus 1 per roll."
        ),
        school_knacks=["absorb_void", "kharmic_spin", "otherworldliness"],
        techniques={
            1: "Roll an extra die on precepts and two chosen skill rolls.",
            2: "Free raise on all rolls for a chosen skill.",
            3: (
                "After an ally's roll, spend a void point to roll Xk1 and add "
                "the result (X = precepts skill); once per roll."
            ),
            4: (
                "+1 Void; Void ring costs 5 fewer XP to raise; "
                "contested opponents can't spend void points."
            ),
            5: (
                "Negate another character's school for a conversation or fight; "
                "costs 2X void for school rank X, or experience/50 for non-school."
            ),
        },
    ),

    School(
        id="priest",
        name="Priest",
        school_ring="any non-Void",
        category="spellcaster",
        special_ability=(
            "You have all 10 rituals listed under the Priest profession."
        ),
        school_knacks=["conviction", "otherworldliness", "pontificate"],
        techniques={
            1: (
                "Roll an extra die on precepts, one chosen skill, "
                "and one combat roll type."
            ),
            2: (
                "Free raise on all Honor bonus rolls (bragging, precepts, "
                "open sincerity) for self and allies."
            ),
            3: (
                "Roll X dice (X = precepts skill) at combat start; swap for "
                "any rolled die on attack/parry/wound/damage; "
                "swap lower dice for allies."
            ),
            4: (
                "+1 School Ring; that ring costs 5 fewer XP to raise; "
                "free raise for self and allies on contested rolls vs "
                "equal or higher skills."
            ),
            5: (
                "Spend Conviction points on allies' rolls; refresh per round; "
                "spend to lower action dice for counterattack/parry."
            ),
        },
    ),

    School(
        id="shugenja",
        name="Shugenja",
        school_ring="any non-Void",
        category="spellcaster",
        special_ability=(
            "Maximum void points equals highest ring plus school rank. "
            "Regain lowest Ring per night, one per 2 hours partial. "
            "May not spend more than lowest Ring minus 1 per roll."
        ),
        school_knacks=["commune", "pontificate", "spellcasting"],
        techniques={
            1: (
                "Roll an extra die on precepts or commune/spellcasting for "
                "a chosen element."
            ),
            2: (
                "Free raise on precepts or commune/spellcasting for a chosen element."
            ),
            3: (
                "Gain 2X free raises per adventure (X = precepts skill); "
                "apply to bragging, intimidation, precepts, tact, wound checks, "
                "spellcasting for element; max X per roll."
            ),
            4: (
                "+1 to the chosen element's ring; that ring costs 5 fewer XP to raise; "
                "cast one spell per round as an interrupt action."
            ),
            5: (
                "All non-Void rings considered 1 higher when rolling "
                "commune/spellcasting."
            ),
        },
    ),
]

SCHOOLS: Dict[str, School] = {s.id: s for s in _SCHOOLS_LIST}


# ---------------------------------------------------------------------------
# ADVANTAGES
# ---------------------------------------------------------------------------

_ADVANTAGES_LIST: List[Advantage] = [
    Advantage("charming", "Charming", 2,
              "You are naturally likable and put others at ease."),
    Advantage("discerning", "Discerning", 5,
              "You have a keen eye for detail and rarely miss important nuances."),
    Advantage("fierce", "Fierce", 2,
              "Your presence on the battlefield is intimidating."),
    Advantage("genealogist", "Genealogist", 2,
              "You have extensive knowledge of family lineages and histories."),
    Advantage("good_reputation", "Good Reputation", 3,
              "You are well-regarded and your name carries positive weight."),
    Advantage("great_destiny", "Great Destiny", 8,
              "Fate has marked you for greatness; you are protected from premature death."),
    Advantage("higher_purpose", "Higher Purpose", 2,
              "You are driven by a noble goal that gives you strength."),
    Advantage("imperial_favor", "Imperial Favor", 2,
              "You have gained the attention and favor of the Imperial court."),
    Advantage("kind_eye", "Kind Eye", 3,
              "Others sense your genuine compassion and trust you more readily."),
    Advantage("lucky", "Lucky", 5,
              "Fortune smiles upon you; you may reroll dice in critical moments."),
    Advantage("quick_healer", "Quick Healer", 3,
              "Your body recovers from injury faster than normal."),
    Advantage("specialization", "Specialization", 2,
              "You excel in a specific narrow application of a skill."),
    Advantage("strength_of_the_earth", "Strength of the Earth", 8,
              "Your resilience is legendary; you shrug off wounds that would fell others."),
    Advantage("tactician", "Tactician", 2,
              "You have a natural gift for battlefield strategy."),
    Advantage("virtue", "Virtue", 3,
              "You embody one of the tenets of Bushido to an exceptional degree."),
    Advantage("wealthy", "Wealthy", 2,
              "You have access to greater financial resources than your rank suggests."),
    Advantage("worldly", "Worldly", 4,
              "You have traveled widely and understand diverse customs and perspectives."),
]

ADVANTAGES: Dict[str, Advantage] = {a.id: a for a in _ADVANTAGES_LIST}


# ---------------------------------------------------------------------------
# DISADVANTAGES
# ---------------------------------------------------------------------------

_DISADVANTAGES_LIST: List[Disadvantage] = [
    Disadvantage("bad_reputation", "Bad Reputation", 3,
                 "You are known for something negative that colors others' perceptions."),
    Disadvantage("contrary", "Contrary", 5,
                 "You reflexively argue against whatever position others take."),
    Disadvantage("dark_secret", "Dark Secret", 6,
                 "You harbor a secret that would destroy you if revealed."),
    Disadvantage("discordant", "Discordant", 12,
                 "You are fundamentally at odds with the social order around you."),
    Disadvantage("driven", "Driven", 5,
                 "An obsessive goal consumes you, sometimes to your detriment."),
    Disadvantage("emotional", "Emotional", 3,
                 "You have difficulty controlling a particular emotion."),
    Disadvantage("humble", "Humble", 2,
                 "You downplay your accomplishments and defer to others excessively."),
    Disadvantage("jealousy", "Jealousy", 3,
                 "You covet what others possess, whether status, skill, or affection."),
    Disadvantage("long_temper", "Long Temper", 5,
                 "You suppress anger until it explodes in disproportionate outbursts."),
    Disadvantage("meddler", "Meddler", 2,
                 "You cannot resist involving yourself in others' affairs."),
    Disadvantage("permanent_wound", "Permanent Wound", 12,
                 "You carry a grievous injury that will never fully heal."),
    Disadvantage("poor", "Poor", 4,
                 "Your financial resources are significantly below your station."),
    Disadvantage("proud", "Proud", 2,
                 "Your pride makes it difficult to accept help or admit fault."),
    Disadvantage("slow_healer", "Slow Healer", 3,
                 "Your body recovers from injury slower than normal."),
    Disadvantage("short_temper", "Short Temper", 8,
                 "You are easily provoked to anger and rash action."),
    Disadvantage("thoughtless", "Thoughtless", 5,
                 "You speak and act without considering the consequences."),
    Disadvantage("transparent", "Transparent", 12,
                 "Your emotions and intentions are an open book to everyone."),
    Disadvantage("unconventional", "Unconventional", 4,
                 "Your methods and behavior defy the norms of your station."),
    Disadvantage("unkempt", "Unkempt", 4,
                 "You neglect your appearance in a culture that values presentation."),
    Disadvantage("unlucky", "Unlucky", 8,
                 "Misfortune follows you; fate conspires against you at critical moments."),
    Disadvantage("vain", "Vain", 2,
                 "You are excessively concerned with your appearance and reputation."),
    Disadvantage("withdrawn", "Withdrawn", 4,
                 "You avoid social interaction and struggle in group settings."),
]

DISADVANTAGES: Dict[str, Disadvantage] = {d.id: d for d in _DISADVANTAGES_LIST}


# ---------------------------------------------------------------------------
# SPELLS
# ---------------------------------------------------------------------------

_SPELLS_LIST: List[Spell] = [
    # Air spells
    Spell("stifling_wind", "Stifling Wind", Ring.AIR, 3,
          "A blast of air that hampers movement and disrupts concentration."),
    Spell("wind_borne_speed", "Wind-Borne Speed", Ring.AIR, 4,
          "The winds carry you with supernatural swiftness."),
    Spell("gift_of_the_wind_spirits", "Gift of the Wind Spirits", Ring.AIR, 5,
          "The wind spirits grant a powerful boon of their choosing."),

    # Earth spells
    Spell("jade_strike", "Jade Strike", Ring.EARTH, 3,
          "A bolt of pure jade energy effective against Tainted creatures."),
    Spell("earths_protection", "Earth's Protection", Ring.EARTH, 4,
          "The earth rises to shield you from harm."),
    Spell("path_of_the_zokujin", "Path of the Zokujin", Ring.EARTH, 5,
          "Channel the ancient power of the zokujin to reshape stone and earth."),

    # Fire spells
    Spell("the_fires_from_within", "The Fires From Within", Ring.FIRE, 3,
          "Channel inner fire into a damaging blast of flame."),
    Spell("the_fires_that_cleanse", "The Fires That Cleanse", Ring.FIRE, 4,
          "Purifying flames that burn away corruption and impurity."),
    Spell("foxfire", "Foxfire", Ring.FIRE, 5,
          "Conjure elusive spirit-flames with mystical properties."),

    # Water spells
    Spell("path_to_inner_peace", "Path to Inner Peace", Ring.WATER, 3,
          "Soothing waters that heal wounds and calm the spirit."),
    Spell("kamis_strength", "Kami's Strength", Ring.WATER, 4,
          "The water kami bolster your physical capabilities."),
    Spell("reflecting_pool", "Reflecting Pool", Ring.WATER, 5,
          "Peer through water to observe distant places or hidden truths."),
]

SPELLS: Dict[str, Spell] = {s.id: s for s in _SPELLS_LIST}

# Convenience: spells grouped by element
SPELLS_BY_ELEMENT: Dict[Ring, List[Spell]] = {}
for _spell in _SPELLS_LIST:
    SPELLS_BY_ELEMENT.setdefault(_spell.element, []).append(_spell)


# ---------------------------------------------------------------------------
# SCHOOL CATEGORIES (for UI grouping)
# ---------------------------------------------------------------------------

SCHOOL_CATEGORIES = {
    "bushi": "Bushi",
    "counterattack": "Counterattack",
    "duelist": "Duelist",
    "monk": "Monk",
    "investigator": "Investigator / Support",
    "court": "Court & Merchant",
    "artisan": "Artisan / Knowledge",
    "spellcaster": "Spellcaster",
}

SCHOOLS_BY_CATEGORY: Dict[str, List[School]] = {}
for _school in _SCHOOLS_LIST:
    SCHOOLS_BY_CATEGORY.setdefault(_school.category, []).append(_school)


# ---------------------------------------------------------------------------
# HELPER: Character defaults & XP calculations
# ---------------------------------------------------------------------------

def starting_rings(school_ring: str) -> Dict[str, int]:
    """Return the initial ring values for a character with the given school ring.

    The school ring starts at 3; all others start at 2.
    For schools with 'any non-Void' or 'Air or Water', the caller must
    resolve the choice before calling this function -- pass the chosen ring.
    """
    rings = {r.value: RING_DEFAULT for r in Ring}
    if school_ring in rings:
        rings[school_ring] = RING_SCHOOL_DEFAULT
    return rings


def ring_max(ring_name: str, school_ring: str) -> int:
    """Maximum value for a ring. School ring can reach 6; others cap at 5."""
    if ring_name == school_ring:
        return RING_MAX_SCHOOL
    return RING_MAX_NORMAL


def void_points_max(rings: Dict[str, int]) -> int:
    """Standard void point maximum = lowest ring value."""
    return min(rings.values())


def void_points_max_shugenja(rings: Dict[str, int], school_rank: int) -> int:
    """Void point max for Shugenja / Isawa Ishi = highest ring + school rank."""
    return max(rings.values()) + school_rank


def void_regen_per_night(rings: Dict[str, int]) -> int:
    """Standard: regain 1 per 8 hours."""
    return 1


def void_regen_per_night_shugenja(rings: Dict[str, int]) -> int:
    """Shugenja / Isawa Ishi: regain lowest Ring per night."""
    return min(rings.values())


def void_spend_cap_shugenja(rings: Dict[str, int]) -> int:
    """Shugenja / Isawa Ishi: may not spend more than (lowest Ring - 1) per roll."""
    return min(rings.values()) - 1


def honor_raise_cost(current: float, target: float) -> int:
    """XP cost to raise Honor from *current* to *target* (in 0.5 increments)."""
    steps = int((target - current) / 0.5)
    return steps * HONOR_COST_PER_HALF


def rank_raise_cost(current: float, target: float) -> int:
    """XP cost to raise Rank from *current* to *target* (in 0.5 increments)."""
    steps = int((target - current) / 0.5)
    return steps * RANK_COST_PER_HALF


def recognition_raise_cost(current: float, target: float) -> int:
    """XP cost to raise Recognition from *current* to *target* (1.0 increments)."""
    steps = int(target - current)
    return steps * RECOGNITION_COST_PER_ONE


def starting_recognition(rank: float, halved: bool = False) -> float:
    """Starting Recognition equals Rank, or half Rank for 3 XP."""
    if halved:
        return rank / 2.0
    return rank


def max_recognition(rank: float) -> float:
    """Recognition can go up to 150% of Rank."""
    return rank * RECOGNITION_MAX_FACTOR


# ---------------------------------------------------------------------------
# DAN / SCHOOL RANK helpers
# ---------------------------------------------------------------------------

# School rank (dan) is typically 1-5, determined by total XP spent.
# The thresholds are campaign-dependent but commonly:
DAN_XP_THRESHOLDS: Dict[int, int] = {
    1: 0,
    2: 50,
    3: 100,
    4: 175,
    5: 250,
}


def dan_for_xp(total_xp_spent: int) -> int:
    """Return the school rank (dan) for the given total XP spent."""
    dan = 1
    for level, threshold in sorted(DAN_XP_THRESHOLDS.items()):
        if total_xp_spent >= threshold:
            dan = level
    return dan


# ---------------------------------------------------------------------------
# CONVENIENCE: all data in one place for iteration
# ---------------------------------------------------------------------------

ALL_DATA = {
    "rings": RING_NAMES,
    "skills": SKILLS,
    "school_knacks": SCHOOL_KNACKS,
    "schools": SCHOOLS,
    "advantages": ADVANTAGES,
    "disadvantages": DISADVANTAGES,
    "spells": SPELLS,
    "spells_by_element": SPELLS_BY_ELEMENT,
    "schools_by_category": SCHOOLS_BY_CATEGORY,
    "combat_reference": COMBAT_REFERENCE,
}
