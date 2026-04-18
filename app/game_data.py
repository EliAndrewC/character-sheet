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

RANK_START = 7.5  # Wasp campaign starting Rank (free, locked)
RANK_COST_PER_HALF = 1  # same as Honor

RECOGNITION_START = 7.5  # Wasp campaign starting Recognition (free)
CAMPAIGN_STIPEND_RANK = 4  # Wasp campaign: characters considered 4th rank for stipend

# Mutually exclusive advantage/disadvantage pairs.
# Each tuple is (id_a, name_a, id_b, name_b).  Spans regular and campaign lists.
# Advantages/disadvantages that require extra detail fields.
# Each entry maps an ID to a dict describing what's needed:
#   "text": label for the freeform text field
#   "skills": True if the player must select skills (multi for many, single for one)
#   "player": True if the player must select another player character
ADVANTAGE_DETAIL_FIELDS = {
    "virtue": {"text": "Which virtue?"},
    "jealousy": {"text": "Which skill do you measure yourself by?"},
    "unconventional": {"text": "What aspect of bushido?"},
    "good_reputation": {"text": "What are you known for?"},
    "bad_reputation": {"text": "What are you known for?"},
    "dark_secret": {"text": "What is your secret?", "player": True},
    "driven": {"text": "What is your ultimate goal?"},
    "higher_purpose": {"text": "What is your cause?", "skills": "multi"},
    "specialization": {"text": "What specialization?", "skills": "single"},
}

EXCLUSIVE_PAIRS = [
    ("vain", "Vain", "unkempt", "Unkempt"),
    ("imperial_favor", "Imperial Favor", "imperial_disdain", "Imperial Disdain"),
    ("quick_healer", "Quick Healer", "slow_healer", "Slow Healer"),
    ("virtue", "Virtue", "unconventional", "Unconventional"),
    ("wealthy", "Wealthy", "poor", "Poor"),
    ("family_reckoning_righteous_sting", "Family Reckoning: Righteous Sting",
     "family_reckoning_venomous_sting", "Family Reckoning: Venomous Sting"),
]
RECOGNITION_MAX_FACTOR = 1.5  # up to 150% of Rank
RECOGNITION_COST_PER_ONE = 1  # 1 XP per 1.0 Recognition
RECOGNITION_HALVE_START_XP = 3  # 3 XP to halve starting Recognition


# ---------------------------------------------------------------------------
# CAMPAIGN PLAYER ROSTER
# Discord ID -> default display name for all campaign participants.
# Used to pre-seed User records and populate the owner dropdown.
# ---------------------------------------------------------------------------
CAMPAIGN_PLAYERS = {
    "183026066498125825": "Eli",
    "282617191147241474": "Chris Russo",
    "143899133680418818": "Phil",
    "551647271423574026": "Julie",
    "316306960855072769": "Marshall",
    "832037313558609930": "Alex",
    "829461716525514762": "Patrick",
    "741082265404047481": "Craig",
    "209412082351734785": "Sean",
    "153227112633860097": "Chris Larkin",
    "213078006250340353": "Joel",
    "193187249708335105": "Jack",
    "test_user_1": "Test User 1",
    "test_user_2": "Test User 2",
}


# ---------------------------------------------------------------------------
# COMBAT REFERENCE
# ---------------------------------------------------------------------------

COMBAT_SKILLS = {
    "attack": {
        "name": "Attack",
        "ring": "Fire",
        "start": 1,
        "max": 5,
        "cost_table": ADVANCED_SKILL_COSTS,
        "description": (
            "Roll Attack + Fire to hit. TN to hit = 5 + 5 * defender's Parry skill. "
            "Extra damage die for every 5 points exceeding the TN."
        ),
        "roll_description": "Roll Attack + Fire.",
    },
    "parry": {
        "name": "Parry",
        "ring": "Air",
        "start": 1,
        "max": 5,
        "cost_table": ADVANCED_SKILL_COSTS,
        "description": (
            "Roll Parry + Air to deflect an attack. TN = attacker's roll result. "
            "Your TN to be hit = 5 + 5 * Parry. Declaring parry before attack roll grants a free raise."
        ),
        "roll_description": "Roll Parry + Air. Your TN to be hit: 5 + 5 * Parry.",
    },
}

COMBAT_SKILL_START = 1
COMBAT_SKILL_MAX = 5


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
    "impaired_threshold": "serious_wounds >= Earth",
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
    rules_text: str = ""  # full canonical rules text from upstream rules repo


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
        rules_text=(
            "A number of times per day equal to your rank in this knack, you may "
            "draw void from your surroundings and regain a spent void point. If "
            "you target a character when doing this, that character loses a void "
            "point; if that character has no void points then the next time they "
            "would regain one they do not. You may do this either while conversing "
            "with that character or when attacking or being attacked by that "
            "character in combat, but you may not target the same character more "
            "than once per day."
        ),
    ),
    SchoolKnack(
        id="athletics",
        name="Athletics",
        ring="varies",
        description=(
            "Physical feats of agility, climbing, running, swimming, and acrobatics."
        ),
        rules_text=(
            "When performing generic athletic tasks, roll extra dice equal to "
            "this knack. You may also use this knack to attack or parry. If you "
            "use it to attack, your TN is equal to 5 plus 10 times the defender's "
            "parry skill. If you use it to parry, then your TN is raised by 5 "
            "times the attack skill of the attacker."
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
        rules_text=(
            "You may ask the elemental spirits about events which they have "
            "recently witnessed. Spend a void point and roll this knack with the "
            "Ring of the element of the spirits you are questioning. This is an "
            "open roll, and the GM weighs it against the time passed since the "
            "events in question and how much has happened here since then."
            "\n\n"
            "Different elemental spirits perceive humans differently and give "
            "different types of information about them. Fire spirits read surface "
            "thoughts, Air spirits sense emotional states, Earth spirits perceive "
            "the motives behind actions, and Water spirits see the directions of "
            "comings and goings. The higher your roll, the more details about "
            "these things you receive."
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
        rules_text=(
            "You receive 2X points per day, where X is equal to the rank of this "
            "knack. After you make any roll, you may spend up to X of these "
            "points to raise the roll by the number of points spent."
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
        rules_text=(
            "When an opponent attacks you, roll this knack to make an attack "
            "against them before they roll theirs. If you counterattack an attack "
            "directed at someone else, the TN is raised by 5 times the attacker's "
            "parry skill. You may counterattack as an interrupt action."
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
        rules_text=(
            "This knack is used to detect the Shadowlands Taint in humans. To "
            "use it, you must spend a full minute concentrating on someone, who "
            "cannot leave your sight during this time. Success is automatic "
            "against anyone without the ability to conceal their Shadowlands "
            "Taint, although you must still roll the knack every time."
            "\n\n"
            "Against bloodspeakers, this is a contested roll against their Fear "
            "knack. If successful, the GM secretly rolls 1k1, and the Witch "
            "Hunter successfully detects the Shadowlands Taint if the roll is "
            "greater than twice the bloodspeaker's School Rank."
            "\n\n"
            "The following bonuses and penalties apply to the contested roll:"
            "\n"
            "\u2022 The bloodspeaker gets a bonus of 10 * (7 \u2013 X) to their "
            "roll, where X is the bloodspeaker's Shadowlands Taint."
            "\n"
            "\u2022 If forced to swallow a piece of jade, this bonus is "
            "eliminated entirely."
            "\n"
            "\u2022 If stabbed by a jade object enough to draw blood during the "
            "roll, bloodspeakers can't reroll 10s."
            "\n"
            "\u2022 Because servants of the Dark Lord cannot stand to be bound, "
            "if you tie the hands of a bloodspeaker, they are unable to receive "
            "any other bonuses to their roll, such as their Desire knack, or "
            "their Rank 3 Technique."
            "\n"
            "\u2022 By tying a bloodspeaker's arms tightly to their body as well "
            "as tightly tying their legs together, Witch Hunters receive two "
            "free raises per hour in which the bloodspeaker was tied in this "
            "manner before the detect Taint roll is made."
            "\n"
            "\u2022 By spending extra time concentrating on a single target, the "
            "Witch Hunter receives two free raises per hour."
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
        rules_text=(
            "By engaging another character in conversation you may gain insight "
            "into that character's Honor. When you use this knack the GM tells "
            "you that that character's honor + 0.5 * (1k1 \u2013 0.5). After "
            "each conversation past the first, you get a more accurate idea of "
            "their honor, and the GM tells you a number which is 0.X closer to "
            "the truth, where X is your rank in this knack."
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
        rules_text=(
            "The TN to hit your target is raised by 20. If successful, roll "
            "extra damage dice as if the TN hadn't been raised, and inflict a "
            "serious wound in addition to the normal damage roll. On an "
            "unsuccessful parry, this extra serious wound becomes 2 extra rolled "
            "damage dice, or 4 extra rolled damage dice if someone else "
            "unsucessfully parried for the target."
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
        rules_text=(
            "At the beginning of each combat round, you may breath spiritual "
            "fire which extends around you 10 feet in every direction. These "
            "flames do not harm physical objects, except that they deal (2X)k1 "
            "damage to any characters you choose to be harmed, where X is your "
            "rank in this knack."
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
        rules_text=(
            "This attack does no damage, but if successful it yields a temporary "
            "void point which may be used this round. Your highest action is "
            "then moved to the current phase. The target is not told whether the "
            "attack against them is a feint until after they see whether it "
            "hits, and after any parries are resolved."
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
        rules_text=(
            "The iaijutsu rules are explained with the other combat rules."
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
        rules_text=(
            "Spend a void and roll this knack to swap the highest and second "
            "highest Ring ranks of the target character for the remainder of one "
            "conversation or fight. In the case of a tie for the second-lowest "
            "Ring, the target chooses which Ring is switched with the highest "
            "one. You roll this knack against a secret TN equal to 5 times the "
            "sum of the ranks of the target character's two highest Rings. You "
            "may do this either while conversing with that character or when "
            "attacking or being attacked by that character in combat, but you "
            "may not target the same character more than once per day."
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
        rules_text=(
            "Roll this knack instead of attack when attacking someone to roll an "
            "extra die of damage if you hit. Everyone fighting you gets a free "
            "raise on their next attack against you this round."
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
        rules_text=(
            "You have such command over factual arguments that you can trip "
            "others up. Once per conversation you may target a character, roll "
            "this knack, and divide the result by 5, rounding down. Subtract "
            "that amount from all skill rolls made by that character for the "
            "rest of the conversation which roll with Water."
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
        rules_text=(
            "You have such command over social situations that you can trip "
            "others up. Once per conversation you may target a character, roll "
            "this knack, and divide the result by 5, rounding down. Subtract "
            "that amount from all skill rolls made by that character for the "
            "rest of the conversation which roll with Air."
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
        rules_text=(
            "When rolling a basic skill, you may increase the skill's rank by "
            "one, to a maximum of five. This may be done multiple times on the "
            "same roll, but only a number of times per adventure equal to twice "
            "your rank in this knack."
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
        rules_text=(
            "Once per conversation, you may use your practiced aura of "
            "knowledgeable confidence to roll this knack instead of any basic "
            "skill when making an uncontested roll."
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
        rules_text=(
            "Once per conversation, you may use your practiced presence of "
            "authority to roll this knack instead of any skill when making a "
            "contested roll initiated by another character."
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
        rules_text=(
            "To cast a spell, you spend actions equal to its mastery level minus "
            "2. You then roll this knack with the Ring of that spell's element "
            "against a TN of its mastery level times 5. You may not cast the "
            "same spell more than once per combat round."
            "\n\n"
            "After you roll, you lose void points equal to its mastery level. "
            "For every 5 by which you exceed the TN, this cost is lowered by 1, "
            "to a minimum of 1. If you end up not having enough void points, "
            "then all of your void points are lost and you fail to cast the "
            "spell."
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
        rules_text=(
            "Each adventure, you may spend a number of extra void points equal "
            "to the rank of this knack."
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
            "You get four temporary void points after a successful feint "
            "and one void point after an unsuccessful feint."
        ),
        school_knacks=["double_attack", "feint", "iaijutsu"],
        techniques={
            1: "Rolls one extra die on attack, double attack, and wound checks.",
            2: "You get a free raise on wound checks.",
            3: (
                "After you exceed the TN of a wound check, divide the difference "
                "between your wound check and the damage roll by 5, rounding down. "
                "You may add that number multiplied by X to any future attack this "
                "combat, where X is your attack skill."
            ),
            4: (
                "Raise your current and maximum Water by 1. Raising your Water "
                "now costs 5 fewer XP.\n"
                "You may spend void points after rolling a wound check to receive "
                "a free raise for each void point spent."
            ),
            5: (
                "After you take damage, you may spend void points to deal 10 light "
                "wounds to the attacker for every void point spent, up to the amount "
                "of damage you took."
            ),
        },
    ),

    School(
        id="bayushi_bushi",
        name="Bayushi Bushi",
        school_ring=Ring.FIRE.value,
        category="bushi",
        special_ability=(
            "When spending void points on all types of attack rolls, add 1k1 to "
            "the damage rolls of those attacks per void point spent."
        ),
        school_knacks=["double_attack", "feint", "iaijutsu"],
        techniques={
            1: "Roll one extra die on iaijutsu, double attack, and wound check rolls.",
            2: "You get a free raise on double attack rolls.",
            3: (
                "Your feints do Xk1 damage, where X is your attack skill. You "
                "don't roll extra damage dice from your Fire or from exceeding "
                "the TN, but your Special Ability may increase the damage."
            ),
            4: (
                "Raise your current and maximum Fire by 1. Raising your Fire "
                "now costs 5 fewer XP.\n"
                "After a successful or unsuccessful feint, you may apply a free "
                "raise to any future attack this combat."
            ),
            5: (
                "When you fail a wound check, calculate your serious wounds as "
                "if you had half your number of light wounds (rounded down)."
            ),
        },
    ),

    School(
        id="hida_bushi",
        name="Hida Bushi",
        school_ring=Ring.WATER.value,
        category="bushi",
        special_ability=(
            "You may counterattack as an interrupt action by spending only 1 "
            "action die, but if you do so then the attacker gets a free raise "
            "on their attack roll."
        ),
        school_knacks=["counterattack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll one extra die on attack, counterattack, and wound check rolls.",
            2: "You get a free raise on all counterattack rolls.",
            3: (
                "You may re-roll 2X dice on each counterattack roll or X dice on "
                "any other attack roll, where X is your attack skill. When impaired, "
                "your number of extra dice on these rolls is divided in half (round "
                "up), but you reroll 10s on these rolls despite being impaired."
            ),
            4: (
                "Raise your current and maximum Water by 1. Raising your Water "
                "now costs 5 fewer XP.\n"
                "Instead of making a wound check, you may choose to take 2 serious "
                "wounds to reduce your light wounds to 0. You may not do this "
                "during the iaijutsu phase of a duel."
            ),
            5: (
                "When you counterattack successfully, note the quantity X by which "
                "the counterattack roll exceeded its TN. Add X to your wound check "
                "on the damage from the attack you counterattacked. You may choose "
                "to counterattack after seeing an opponent's damage roll, but that "
                "roll goes through even if your counterattack impairs or kills "
                "the opponent."
            ),
        },
    ),

    School(
        id="mirumoto_bushi",
        name="Mirumoto Bushi",
        school_ring=Ring.VOID.value,
        category="bushi",
        special_ability=(
            "Your successful or unsuccessful parries give you a temporary void point."
        ),
        school_knacks=["counterattack", "double_attack", "iaijutsu"],
        techniques={
            1: "Roll one extra die on parry, double attack, and wound check rolls.",
            2: "You get a free raise on parry rolls.",
            3: (
                "At the beginning of each round, you get 2X points, where X is "
                "equal to your attack skill. Each point may be spent to decrease "
                "the phase of one of your actions by 1 in order to parry, or to "
                "provide a bonus of +2 on any type of attack or parry after you "
                "have seen your roll."
            ),
            4: (
                "Raise your current and maximum Void by 1. Raising your Void "
                "now costs 5 fewer XP.\n"
                "Failed parries against your double attacks do not prevent the "
                "automatic serious wound, and against your regular attacks the "
                "number of extra rolled damage dice the failed parry reduced is "
                "cut in half (rounded down)."
            ),
            5: "Your void points provide an extra +10 when spent on combat rolls.",
        },
    ),

    School(
        id="matsu_bushi",
        name="Matsu Bushi",
        school_ring=Ring.FIRE.value,
        category="bushi",
        special_ability=(
            "You always roll 10 dice when rolling initiative, keeping the "
            "usual number as action dice."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll one extra die on double attack, iaijutsu, and wound check rolls.",
            2: "You get a free raise on iaijutsu rolls.",
            3: (
                "When you spend a void point, you may add 3X to any future wound "
                "check this combat after seeing the roll, where X is your "
                "attack skill."
            ),
            4: (
                "Raise your current and maximum Fire by 1. Raising your Fire "
                "now costs 5 fewer XP.\n"
                "When you miss the TN on a double attack roll by less than 20, "
                "you are still considered to have hit, but you deal no "
                "extra damage."
            ),
            5: (
                "After you deal light wounds which result in the defender taking "
                "one or more serious wounds, their light wound total is reset to "
                "15 instead of 0."
            ),
        },
    ),

    School(
        id="otaku_bushi",
        name="Otaku Bushi",
        school_ring=Ring.FIRE.value,
        category="bushi",
        special_ability=(
            "After an attack against you is completely resolved, you may make "
            "a lunge attack at your attacker as an interrupt action at the cost "
            "of one action die."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll one extra die on iaijutsu, lunge, and wound check rolls.",
            2: "You get a free raise on wound checks.",
            3: (
                "After you roll damage against an opponent, increase that "
                "character's next X action dice this turn by (6 - that "
                "character's Fire) min 1, where X is your attack skill, to a "
                "maximum of phase 10."
            ),
            4: (
                "Raise your current and maximum Fire by 1. Raising your Fire "
                "now costs 5 fewer XP.\n"
                "When you lunge, you always roll the extra damage die from using "
                "lunge even if your attack is unsuccessfully parried."
            ),
            5: (
                "After a successful attack or lunge roll, you may decrease the "
                "number of rolled damage dice by 10, to a minimum of 2, to "
                "automatically deal 1 serious wound to your opponent. You may "
                "only do this once per damage roll."
            ),
        },
    ),

    School(
        id="shinjo_bushi",
        name="Shinjo Bushi",
        school_ring=Ring.AIR.value,
        category="bushi",
        special_ability=(
            "Each action you take in combat has a bonus of 2X, where X is the "
            "number of phases for which the action die was held."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll one extra die on double attack, initiative, and parry rolls.",
            2: "You get a free raise on parry rolls.",
            3: (
                "After a successful or unsuccessful parry, all your action dice "
                "are decreased by X, where X is equal to your attack skill. "
                "Action dice are considered to have been held since their newly "
                "lowered value. This can lower dice to negative numbers."
            ),
            4: (
                "Raise your current and maximum Air by 1. Raising your Air "
                "now costs 5 fewer XP.\n"
                "Your highest action die is set to 1 at the beginning of each "
                "combat round."
            ),
            5: (
                "After you successfully parry, you may add X to a future wound "
                "check this combat after seeing your roll, where X is the amount "
                "by which your parry roll exceeded its TN."
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
            1: "Roll one extra die on attack, damage, and wound check rolls.",
            2: "You get a free raise on all wound check rolls.",
            3: (
                "Whenever you spend a void point, reduce your current light "
                "wound total by 2X, where X is your attack skill."
            ),
            4: (
                "Raise your current and maximum Earth by 1. Raising your Earth "
                "now costs 5 fewer XP.\n"
                "You get an extra free raise for each void point you spend on "
                "wound check rolls."
            ),
            5: "TBD",
        },
    ),

    # =================== COUNTERATTACK SCHOOLS ====================

    School(
        id="daidoji_yojimbo",
        name="Daidoji Yojimbo",
        school_ring=Ring.WATER.value,
        category="counterattack",
        special_ability=(
            "You may counterattack as an interrupt action by spending only 1 "
            "action die, but if you do so then your opponent gets a free raise "
            "on their wound check if you hit. You may counterattack for other "
            "characters at no penalty."
        ),
        school_knacks=["counterattack", "double_attack", "iaijutsu"],
        techniques={
            1: "Roll one extra die on attack, counterattack, and wound check rolls.",
            2: "You get a free raise on all counterattack rolls.",
            3: (
                "When you counterattack, add X free raises to the wound check "
                "from the original attack, where X is your attack skill."
            ),
            4: (
                "Raise your current and maximum Water by 1. Raising your Water "
                "now costs 5 fewer XP.\n"
                "You may choose to take the damage from a hit dealt to an "
                "adjacent character before damage has been rolled."
            ),
            5: (
                "After you or a character for whom you've counterattacked makes "
                "a wound check, lower the TN to hit the attacker the next time "
                "they are attacked by the amount by which the wound check "
                "exceeded the damage roll. This can lower a TN to below 0."
            ),
        },
    ),

    School(
        id="shiba_bushi",
        name="Shiba Bushi",
        school_ring=Ring.AIR.value,
        category="counterattack",
        special_ability=(
            "You may parry as an interrupt action by spending your lowest 1 "
            "action die, and you may parry attacks directed at other characters "
            "with no penalty."
        ),
        school_knacks=["counterattack", "double_attack", "iaijutsu"],
        techniques={
            1: "Roll an extra die on double attack, parry, and wound check rolls.",
            2: "You get a free raise on parry rolls.",
            3: (
                "Your successful or unsuccessful parry rolls deal (2X)k1 damage, "
                "where X is equal to your attack skill. You don't roll extra "
                "damage dice from your Fire or from exceeding the TN."
            ),
            4: (
                "Raise your current and maximum Air by 1. Raising your Air "
                "now costs 5 fewer XP.\n"
                "You roll an extra 3k1 on wound checks."
            ),
            5: (
                "After you successfully parry, the TN to hit the parried "
                "opponent on the next attack directed at them this combat is "
                "lowered by the amount by which your parry roll exceeded its TN. "
                "This can lower the TN to a negative number."
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
            "You add your Water instead of Fire to your rolled damage dice."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll one extra die on double attack, lunge, and wound check rolls.",
            2: "You get a free raise on wound checks.",
            3: (
                "After you make any type of attack roll, you may lower your TN "
                "to be hit by 5 for the next time that you are attacked this "
                "round to get a bonus of 3X on your attack roll, where X is your "
                "attack skill. If a successful or unsuccessful parry is made "
                "against your attack, you do not suffer the TN penalty."
            ),
            4: (
                "Raise your current and maximum Water by 1. Raising your Water "
                "now costs 5 fewer XP.\n"
                "Once per round, you may lunge as an interrupt action at the "
                "cost of 1 action die."
            ),
            5: (
                "After a successful wound check, you may add X to a future wound "
                "check this combat, where X is the amount by which the wound "
                "check exceeded the light wound total."
            ),
        },
    ),

    School(
        id="kakita_duelist",
        name="Kakita Duelist",
        school_ring=Ring.FIRE.value,
        category="duelist",
        special_ability=(
            "Your 10s on initiative rolls are considered to be in a special "
            "Phase 0. You may use interrupt actions to attack using iaijutsu, "
            "and any Phase 0 attacks use iaijutsu."
        ),
        school_knacks=["double_attack", "iaijutsu", "lunge"],
        techniques={
            1: "Roll one extra die on double attack, iaijutsu, and initiative rolls.",
            2: "You get a free raise on all iaijutsu rolls.",
            3: (
                "Your attacks get a bonus of X for each phase before the "
                "defender's next action they occur, where X is equal to your "
                "attack skill. If a defender does not have an action remaining "
                "in this round, they are considered to act in phase 11. This "
                "applies to all types of attacks, and you know the next action "
                "of everyone within striking range."
            ),
            4: (
                "Raise your current and maximum Fire by 1. Raising your Fire "
                "now costs 5 fewer XP.\n"
                "You get a free raise to all damage rolls from attacks "
                "using iaijutsu."
            ),
            5: (
                "At the beginning of phase 0 in each combat round, make a "
                "contested iaijutsu roll against an opponent. If the opponent "
                "doesn't have iaijutsu, they may roll attack instead, and you "
                "get an extra free raise. Make a damage roll against this "
                "opponent; if you won the contested roll then roll 1 extra "
                "damage die for every 5 by which your roll exceeded your "
                "opponent's, and if you lost then roll 1 fewer damage die for "
                "every 5 by which their roll exceeded yours."
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
            1: "Roll one extra die on attack, damage, and wound check rolls.",
            2: "You get a free raise on all attack rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your precepts skill, which may be applied to the following "
                "rolls: history, law, precepts, wound checks, and attack. You "
                "may not spend more than X of these free raises on a single "
                "roll. These free raises may also be applied to action dice at "
                "any time, lowering a single die by 5 phases."
            ),
            4: (
                "Raise your current and maximum rank in a non-Void ring of your "
                "choice by 1. Raising this Ring now costs 5 fewer XP.\n"
                "Failed parry attempts do not lower your rolled damage dice."
            ),
            5: (
                "Once per round after you have been attacked but before damage "
                "is rolled, you may spend an action die from any phase to attack "
                "your attacker. If your attack roll is at least as high as your "
                "attacker's then the attack against you is canceled; your attack "
                "continues and you hit/miss and roll damage as normal."
            ),
        },
    ),

    School(
        id="togashi_ise_zumi",
        name="Togashi Ise Zumi",
        school_ring=Ring.VOID.value,
        category="monk",
        special_ability=(
            "Roll either 1 or 3 extra action dice at the beginning of each "
            "combat round. If you roll 1 die, it may only be spent on athletics "
            "actions; if you roll 3 dice, all of your action dice may only be "
            "spent on athletics actions."
        ),
        school_knacks=["athletics", "conviction", "dragon_tattoo"],
        techniques={
            1: "Roll one extra die on attack, parry, and athletics rolls.",
            2: "You get a free raise on athletics rolls.",
            3: (
                "Each day you get 4X free raises which may be applied to "
                "athletics rolls, where X is your precepts skill. You may not "
                "spend more than X of these free raises on a single roll."
            ),
            4: (
                "Raise the current and maximum rank of any Ring by 1. Raising "
                "that Ring now costs 5 fewer XP.\n"
                "You may reroll any contested roll once after seeing the result."
            ),
            5: "At any time, you may spend 1 void point to heal 2 serious wounds.",
        },
    ),

    # ============== INVESTIGATOR / SUPPORT SCHOOLS ================

    School(
        id="hiruma_scout",
        name="Hiruma Scout",
        school_ring=Ring.AIR.value,
        category="investigator",
        special_ability=(
            "The two allies fighting on your left and right have their TN to "
            "be hit raised by 5."
        ),
        school_knacks=["double_attack", "feint", "iaijutsu"],
        techniques={
            1: "Roll an extra die on initiative, parry, and wound check rolls.",
            2: "You get a free raise to all parry rolls.",
            3: (
                "After making a successful or unsuccessful parry, add 2X to "
                "your next attack and damage roll against the attacker or "
                "someone adjacent to them, where X is your attack skill."
            ),
            4: (
                "Raise your current and maximum Air by 1. Raising your Air "
                "now costs 5 fewer XP.\n"
                "After rolling initiative, lower all of your action dice by 2, "
                "to a minimum of 1."
            ),
            5: (
                "After making a successful or unsuccessful parry roll, the "
                "attacker deals 10 fewer light wounds on their next 2 "
                "damage rolls."
            ),
        },
    ),

    School(
        id="kitsuki_magistrate",
        name="Kitsuki Magistrate",
        school_ring=Ring.WATER.value,
        category="investigator",
        special_ability=(
            "You use Water for interrogation rolls, and you add twice your "
            "Water to all attack rolls."
        ),
        school_knacks=["discern_honor", "iaijutsu", "presence"],
        techniques={
            1: "Roll one extra die on investigation, interrogation, and wound check rolls.",
            2: "You get a free raise on interrogation rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your investigation skill, which may be applied to the following "
                "rolls: interrogation, intimidation, law, underworld, attack, "
                "and wound checks. You may not spend more than X of these free "
                "raises on any single roll."
            ),
            4: (
                "Raise your current and maximum Water by 1. Raising your Water "
                "now costs 5 fewer XP.\n"
                "You automatically know the Void, parry, and phase of the next "
                "action of each character during combat, and you know the result "
                "of contested rolls made against you out of combat."
            ),
            5: (
                "Your presence is so overwhelming that the Air, Fire and Water "
                "rings of chosen characters are reduced by one. You may do this "
                "to any one character, or you may do it to multiple characters "
                "so long as the sum of their experience does not exceed your "
                "experience. This does not work during the iaijutsu phase of a "
                "duel, and it does not stack with other Kitsuki Magistrates "
                "targeting the same character."
            ),
        },
    ),

    School(
        id="kuni_witch_hunter",
        name="Kuni Witch Hunter",
        school_ring=Ring.EARTH.value,
        category="investigator",
        special_ability=(
            "You may never become Tainted. Roll an extra (X+1)k(X+1) on wound "
            "checks, where X is the Shadowlands Taint of the attacker, rounded "
            "down to the nearest whole number."
        ),
        school_knacks=["detect_taint", "iaijutsu", "presence"],
        techniques={
            1: "Roll one extra die on damage, interrogation, and wound check rolls.",
            2: "You get a free raise a free on interrogation rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your investigation skill, which may be applied to the following "
                "rolls: interrogation, intimidation, law, underworld, attack, "
                "and wound checks. You may also spend these free raises on "
                "damage rolls against targets with the Shadowlands Taint. You "
                "may not spend more than X of these free raises on a single roll."
            ),
            4: (
                "Raise your current and maximum Earth by 1. Raising your Earth "
                "now costs 5 fewer XP.\n"
                "Roll an an extra action die in combat, which may not be used to "
                "attack targets without the Shadowlands Taint."
            ),
            5: (
                "After you take light wounds and resolve your wound check, you "
                "may choose to inflict that number of light wounds on the "
                "opponent who dealt them and take half that amount yourself. If "
                "the opponent has the Shadowlands Taint, then you may also use "
                "an attack in the current phase to add to that damage."
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
            1: "Roll one extra die on tact, manipulation, and wound check rolls.",
            2: "You get a free raise on manipulation rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your tact skill, which may be applied to the following rolls: "
                "heraldry, manipulation, sincerity, tact, attack, and wound "
                "checks. You may not spend more than X of these free raises on "
                "a single roll."
            ),
            4: (
                "Raise your current and maximum Air by 1. Raising your Air "
                "now costs 5 fewer XP.\n"
                "Once per target per conversation or fight, you get a temporary "
                "void point after a successful attack or manipulation roll."
            ),
            5: (
                "Add your Air to all TN and contested rolls. This stacks with "
                "your Special Ability for attack rolls."
            ),
        },
    ),

    School(
        id="doji_artisan",
        name="Doji Artisan",
        school_ring="Air or Water",
        category="court",
        special_ability=(
            "You may spend a void point to counterattack as an interrupt action "
            "at the cost of one actions die; this void point still gives your "
            "counterattack +1k1. While counterattacking, you receive a bonus "
            "equal to the attacker's roll divided by 5, rounded down."
        ),
        school_knacks=["counterattack", "oppose_social", "worldliness"],
        techniques={
            1: "Roll one extra die on counterattack, manipulation, and wound check rolls.",
            2: "You get a free raise on manipulation.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your culture skill, which may be applied to the following "
                "rolls: bragging, culture, heraldry, manipulation, "
                "counterattack, and wound checks. You may not spend more than X "
                "of these free raises on a single roll."
            ),
            4: (
                "Raise your current and maximum Air or Water by 1. Raising that "
                "ring now costs 5 fewer XP.\n"
                "When attacking a target who has not attacked you this round, "
                "you receive a bonus equal to the current phase."
            ),
            5: (
                "When making any TN or contested roll, you receive a bonus "
                "equal to (X-10) / 5 where X is the TN or result of your "
                "opponent's contested roll."
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
            "the next time they are attacked, even if the feint was parried."
        ),
        school_knacks=["double_attack", "feint", "worldliness"],
        techniques={
            1: "Roll one extra die on precepts and any two rolls of your choice.",
            2: "You get a free raise on any type of roll of your choice.",
            3: (
                "After seeing the result of any TN or contested skill roll, you "
                "may spend a void point to subtract Xk1 from the roll, where X "
                "is equal to your tact skill. You know the result of all TN and "
                "contested rolls except sincerity and interrogation."
            ),
            4: (
                "Raise your current and maximum in any non-Void Ring by 1. "
                "Raising that Ring now costs 5 fewer XP.\n"
                "You regain an extra void point every night."
            ),
            5: (
                "Gain a temporary void point whenever you spend a void point "
                "that was not gained from this technique."
            ),
        },
    ),

    School(
        id="merchant",
        name="Merchant",
        school_ring=Ring.WATER.value,
        category="court",
        special_ability=(
            "You may spend void points after you see the results of your "
            "initial roll."
        ),
        school_knacks=["discern_honor", "oppose_knowledge", "worldliness"],
        techniques={
            1: "Roll one extra die on interrogation, sincerity, and wound check rolls.",
            2: "You get a free raise on interrogation rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your sincerity skill, which may be applied to the following "
                "rolls: commerce, heraldry, interrogation, sincerity, attack, "
                "and wound checks. You may not spend more than X of these free "
                "raises on a single roll."
            ),
            4: (
                "Raise your current and maximum Water by 1. Raising your Water "
                "now costs 5 fewer XP.\n"
                "Your Rank is considered 5.0 higher for the purpose of "
                "calculating your stipend."
            ),
            5: (
                "After making any non-initiative roll, you may reroll some of "
                "the dice so long as the dice being rerolled add up to at least "
                "5*(X-1) where X is the number of dice being rerolled. You may "
                "only do this once per roll. As per your Special Ability, you "
                "may spend Void Points before and/or after you make this reroll."
            ),
        },
    ),

    School(
        id="shosuro_actor",
        name="Shosuro Actor",
        school_ring=Ring.AIR.value,
        category="court",
        special_ability=(
            "Roll extra dice equal to your acting on attack, parry, and wound "
            "check rolls."
        ),
        school_knacks=["athletics", "discern_honor", "pontificate"],
        techniques={
            1: "Roll one extra die on attack, sincerity, and wound check rolls.",
            2: "You get a free raise on sincerity rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your sincerity skill, which may be applied to the following "
                "rolls: acting, heraldry, sincerity, sneaking, attack, and "
                "wound checks. You may not spend more than X of these free "
                "raises on a single roll."
            ),
            4: (
                "Raise your current and maximum Air by 1. Raising your Air "
                "now costs 5 fewer XP.\n"
                "Your Rank is considered 5.0 higher for the purpose of "
                "calculating your stipend."
            ),
            5: (
                "After making any TN or contested roll, add your lowest three "
                "dice to the result. (Some dice may be counted twice.)"
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
            "Once per round before making an attack roll against an opponent, "
            "you may force the opponent to spend their next available action "
            "die to attempt to parry your attack. The opponent does not get a "
            "free raise for pre-declaring the parry."
        ),
        school_knacks=["discern_honor", "oppose_knowledge", "oppose_social"],
        techniques={
            1: "Roll one extra die on attack, bragging, and wound check rolls.",
            2: "You get a free raise on attack rolls.",
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your bragging skill, which may be applied to the following "
                "rolls: bragging, culture, heraldry, intimidation, attack, and "
                "wound checks. You may not spend more than X of these free "
                "raises on a single roll."
            ),
            4: (
                "Raise your current and maximum in any non-Void Ring by 1. "
                "Raising that Ring now costs 5 fewer XP.\n"
                "When making a damage roll for an unparried attack for which "
                "you are not keeping extra damage dice, you always roll 10 dice."
            ),
            5: (
                "Once per conversation or combat round, you can apply an oppose "
                "knack or your Special ability an additional time. You may "
                "choose to use your Special Ability after an opponent has made "
                "an attack roll against you, in which case their attack is "
                "canceled and their attack roll will be used as their "
                "parry roll."
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
            "Your maximum number of void points is equal to your highest ring "
            "plus your school rank. You regain a number of void points equal "
            "to your lowest Ring after a full night's rest, and one void point "
            "per 2 hours for a partial night. However, you may not spend more "
            "void points on any one roll than your lowest Ring minus 1."
        ),
        school_knacks=["absorb_void", "kharmic_spin", "otherworldliness"],
        techniques={
            1: "Roll one extra die on precepts and any two skills of your choice.",
            2: "You get a free raise on all rolls for any skill of your choice.",
            3: (
                "After another character makes a roll for which void points may "
                "be spent, you may spend one void point to roll Xk1 and add the "
                "result to their total, where X is your precepts skill. You may "
                "only do this once per roll."
            ),
            4: (
                "Raise your current and maximum Void by 1. Raising your Void "
                "now costs 5 fewer XP.\n"
                "Characters opposing you in contested rolls may not spend void "
                "points. If someone is opposing both you and someone else, they "
                "may spend void points, but the bonus will only count against "
                "whoever else they're opposing."
            ),
            5: (
                "You may completely negate another character's school or "
                "profession for the remainder of one conversation or fight. "
                "Against characters with a school, you must spend void points "
                "equal to twice their school rank. Against characters with no "
                "school, you must spend void points equal to their experience "
                "divided by 50, rounded down. This is instantaneous and does "
                "not require spending an action."
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
                "Roll one extra die on precepts, any one skill, and any one "
                "type of combat roll."
            ),
            2: (
                "You and your allies get a free raise on all rolls for which "
                "you receive an Honor bonus (bragging, precepts, and open "
                "sincerity)."
            ),
            3: (
                "Roll X dice at the beginning of combat, where X is equal to "
                "your precepts skill. You may swap any of these dice for any "
                "rolled die on any attack, parry, wound check, or damage roll. "
                "You may swap any of these dice for any lower die on any of "
                "those types of rolls made by any ally."
            ),
            4: (
                "Raise your current and maximum of your School's chosen Ring "
                "by 1. Raising that Ring now costs 5 fewer XP.\n"
                "You and your allies get a free raise on all contested rolls "
                "for which your opponent has an equal or higher skill rank."
            ),
            5: (
                "You may spend the points from your Conviction knack on your "
                "allies' rolls, and your Conviction points refresh after each "
                "conversation and combat round. You may also spend these points "
                "to lower action dice in order for you or an ally to "
                "counterattack or parry."
            ),
        },
    ),

    School(
        id="shugenja",
        name="Shugenja",
        school_ring="any non-Void",
        category="spellcaster",
        special_ability=(
            "Your maximum number of void points is equal to your highest ring "
            "plus your school rank. You regain a number of void points equal "
            "to your lowest Ring after a full night's rest, and one void point "
            "per 2 hours for a partial night. However, you may not spend more "
            "void points on any one roll than your lowest Ring minus 1."
        ),
        school_knacks=["commune", "pontificate", "spellcasting"],
        techniques={
            1: (
                "Roll one extra die when rolling precepts or with commune and "
                "spellcasting for your chosen element."
            ),
            2: (
                "You get a free raise when rolling precepts or with commune and "
                "spellcasting for your chosen element."
            ),
            3: (
                "Each adventure you get 2X free raises, where X is equal to "
                "your precepts skill, which may be applied to the following "
                "rolls: bragging, intimidation, precepts, tact, wound checks, "
                "and spellcasting for your chosen element. You may not spend "
                "more than X of these free raises on any single roll."
            ),
            4: (
                "Raise your current and maximum Ring of your chosen element "
                "by 1. Raising that Ring now costs 5 fewer XP.\n"
                "You may cast one spell per round as an interrupt action."
            ),
            5: (
                "Your non-Void rings are all considered 1 higher when rolling "
                "commune and spellcasting."
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
              "You get a free raise on etiquette and culture rolls."),
    Advantage("discerning", "Discerning", 5,
              "You get a free raise on interrogation rolls and 2 free raises on investigation rolls."),
    Advantage("fierce", "Fierce", 2,
              "You get a free raise on bragging and intimidation rolls."),
    Advantage("genealogist", "Genealogist", 2,
              "You get 2 free raises on heraldry rolls."),
    Advantage("good_reputation", "Good Reputation", 3,
              "Your Recognition is considered 1.0 higher for the purposes of being recognized, "
              "and your Rank is considered to be 2.0 higher when dealing with anyone who knows your reputation."),
    Advantage("great_destiny", "Great Destiny", 8,
              "It takes one additional serious wound to kill you."),
    Advantage("higher_purpose", "Higher Purpose", 2,
              "You are devoted to some noble cause, and you get a free raise on any roll made "
              "to advocate a position which furthers this cause."),
    Advantage("imperial_favor", "Imperial Favor", 2,
              "Your Rank and Recognition are considered to be 3.0 higher when dealing with anyone "
              "from an Imperial family, and are considered 1.0 higher when dealing with anyone else "
              "serving in Imperial posts."),
    Advantage("kind_eye", "Kind Eye", 3,
              "You get 4 free raises on tact and open sincerity rolls when talking to peasant characters "
              "such as servants who are often treated badly by samurai."),
    Advantage("lucky", "Lucky", 5,
              "You may re-roll any roll once per adventure."),
    Advantage("quick_healer", "Quick Healer", 3,
              "You heal two serious wounds instead of one the first night after being wounded."),
    Advantage("specialization", "Specialization", 2,
              "You get 2 free raises to a chosen subset of a skill, to be discussed with the GM. "
              "This may be taken multiple times."),
    Advantage("strength_of_the_earth", "Strength of the Earth", 8,
              "You get a free raise on wound checks."),
    Advantage("tactician", "Tactician", 2,
              "You get a free raise on strategy and history rolls."),
    Advantage("virtue", "Virtue", 3,
              "You have cultivated a particular virtue, such as courage or loyalty. When someone uses "
              "the discern Honor knack on you, instead of adding 0.5 × (1k1 − 5) they add the absolute "
              "value of that."),
    Advantage("wealthy", "Wealthy", 2,
              "Disabled for Wasp Campaign - all characters are considered 4th rank for stipend "
              "(16 koku/year). Take Household Wealth instead. "
              "Normal rules: Your Rank is considered to be 3.0 higher when calculating your stipend."),
    Advantage("worldly", "Worldly", 4,
              "You get a free raise on commerce and underworld rolls."),
]

ADVANTAGES: Dict[str, Advantage] = {a.id: a for a in _ADVANTAGES_LIST}


# ---------------------------------------------------------------------------
# DISADVANTAGES
# ---------------------------------------------------------------------------

_DISADVANTAGES_LIST: List[Disadvantage] = [
    Disadvantage("bad_reputation", "Bad Reputation", 3,
                 "Your Recognition is considered 1.0 higher for the purposes of being recognized, "
                 "but your Rank is considered 1.5 lower to anyone who knows about this reputation."),
    Disadvantage("contrary", "Contrary", 5,
                 "You cannot remain a neutral third party in any disagreement; you must actively take a side."),
    Disadvantage("dark_secret", "Dark Secret", 6,
                 "You have done something in the past which is considered disgraceful, and one of the PCs "
                 "and a small number of NPCs (chosen by the GM) know about it. Characters who know your "
                 "secret treat you as if your Rank and Recognition were 6.0 lower."),
    Disadvantage("discordant", "Discordant", 12,
                 "You are spiritually unbalanced in a way that affects the harmony of the five elements. "
                 "Because of this, you may not spend void points on skills."),
    Disadvantage("driven", "Driven", 5,
                 "You have some ultimate goal which you want to achieve so badly that you'll disregard "
                 "the adventure goal in order to pursue it."),
    Disadvantage("emotional", "Emotional", 3,
                 "You do not exhibit the emotional reserve appropriate to a samurai. Instead, you are very "
                 "quick to let your emotions show, which will make some people uncomfortable. NPCs will tend "
                 "to not address your character directly and instead talk to other PCs in conversations."),
    Disadvantage("humble", "Humble", 2,
                 "Bragging rolls about your accomplishments are unaffected by this disadvantage, as are "
                 "the Rank and Recognition bonuses you receive for them. However, while you may speak well "
                 "of your accomplishments, you are self-deprecating about your skills and talents. Rokugan "
                 "considers humility a vice, or at least an unfortunate eccentricity, so this will be "
                 "frowned upon by many."),
    Disadvantage("jealousy", "Jealousy", 3,
                 "You have some skill by which you measure yourself against everyone else. You must "
                 "constantly size up everyone you meet to determine roughly how they fare compared to you "
                 "at this skill."),
    Disadvantage("long_temper", "Long Temper", 5,
                 "You hold grudges over perceived insults, especially over matters of honor. Although you "
                 "need not react immediately, you will not forget the insult and will burn with the need "
                 "to extract payback."),
    Disadvantage("meddler", "Meddler", 2,
                 "You want to know everything that's going on and investigate every interesting event "
                 "around. Any intriguing goings on simply have to be looked into, no matter how sensitive "
                 "the issue."),
    Disadvantage("permanent_wound", "Permanent Wound", 12,
                 "It takes one fewer serious wound to kill you. You may not take the Great Destiny advantage."),
    Disadvantage("poor", "Poor", 4,
                 "Disabled for Wasp Campaign - all characters are considered 4th rank for stipend "
                 "(16 koku/year). Normal rules: Divide your Rank in half for the purpose of calculating "
                 "your stipend."),
    Disadvantage("proud", "Proud", 2,
                 "You are a shameless self-promoter who will never be self-deprecating or play down "
                 "accomplishments. You will never directly apologize or admit a mistake even when actually "
                 "at fault."),
    Disadvantage("slow_healer", "Slow Healer", 3,
                 "You do not heal the first night after being wounded, but heal normally after that."),
    Disadvantage("short_temper", "Short Temper", 8,
                 "You are easily insulted and must react immediately against perceived slights, "
                 "particularly when they are related to matters of honor."),
    Disadvantage("thoughtless", "Thoughtless", 5,
                 "You don't think before you speak, and sometimes you cross lines you didn't see. "
                 "People have 4 free raises when using Manipulation on you, and 2 free raises when "
                 "rolling Manipulation against anyone on your side of an argument."),
    Disadvantage("transparent", "Transparent", 12,
                 "You are always considered to have rolled a 5 on sincerity rolls when lying or "
                 "otherwise concealing information."),
    Disadvantage("unconventional", "Unconventional", 4,
                 "You have a slightly unusual way of approaching some aspect of bushido which can "
                 "sometimes make you seem less honorable than you are at first. Whenever someone uses the "
                 "discern Honor knack on you, instead of adding 0.5 × (1k1 − 5) to your honor, the GM "
                 "subtracts the absolute value of that number."),
    Disadvantage("unkempt", "Unkempt", 4,
                 "You are less diligent about cleanliness and grooming than is considered proper. As a "
                 "result, some characters will view you as uncivilized or undisciplined, and you get a "
                 "-10 penalty to all culture rolls."),
    Disadvantage("unlucky", "Unlucky", 8,
                 "Once per adventure, the GM may apply a -5 penalty to any non-initiative roll."),
    Disadvantage("vain", "Vain", 2,
                 "You clearly care a great deal about your appearance, which to some is unseemly and unmanly."),
    Disadvantage("withdrawn", "Withdrawn", 4,
                 "You are very reserved and only speak when you feel you have something to say, and even "
                 "then you express it as succinctly as possible without giving much regard to social niceties. "
                 "As a result, your etiquette and open sincerity rolls are never considered to be higher than 15."),
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


def ring_max(ring_name: str, school_ring: str, dan: int = 0) -> int:
    """Maximum value for a ring.

    School ring caps at 6 normally, or 7 once the character reaches 4th Dan
    (the 4th Dan technique raises the school ring's max by 1). All other
    rings always cap at 5.
    """
    if ring_name == school_ring:
        return RING_MAX_SCHOOL + (1 if dan >= 4 else 0)
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
    """Recognition can go up to 150% of Rank, rounded down to the nearest 0.5."""
    import math
    return math.floor(rank * RECOGNITION_MAX_FACTOR * 2) / 2


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
# SCHOOL TECHNIQUE BONUSES (structured data for 1st/2nd/3rd Dan)
# ---------------------------------------------------------------------------
#
# Keys:
#   first_dan_extra_die  – list of roll-type IDs that gain +1 rolled die
#   second_dan_free_raise – single roll-type ID that gains a free raise
#   third_dan            – present ONLY when the 3rd Dan follows the standard
#                          "Gain 2X free raises per adventure" pattern
#       source_skill   – skill whose rank = X
#       applicable_to  – list of skill / roll-type IDs the raises apply to
#       formula        – always "2X"
#       max_per_roll   – always "X"
#
# Roll-type IDs for combat: attack, parry, wound_check, damage, initiative,
#   counterattack, double_attack, iaijutsu, lunge, athletics
# Skill IDs match the SKILLS dict (e.g. tact, manipulation, sincerity …).
# Schools whose 1st/2nd Dan say "chosen" or are otherwise non-standard
# use None for the relevant field.

SCHOOL_TECHNIQUE_BONUSES: Dict[str, dict] = {
    # ======================== BUSHI SCHOOLS ========================
    "akodo_bushi": {
        "first_dan_extra_die": ["attack", "double_attack", "wound_check"],
        "second_dan_free_raise": "wound_check",
        # 3rd Dan: non-standard (excess from wound checks → attack bonus)
    },
    "bayushi_bushi": {
        "first_dan_extra_die": ["iaijutsu", "double_attack", "wound_check"],
        "second_dan_free_raise": "double_attack",
        # 3rd Dan: non-standard (feints deal damage)
    },
    "hida_bushi": {
        "first_dan_extra_die": ["attack", "counterattack", "wound_check"],
        "second_dan_free_raise": "counterattack",
        # 3rd Dan: non-standard (reroll dice on counterattacks/attacks)
    },
    "mirumoto_bushi": {
        "first_dan_extra_die": ["parry", "double_attack", "wound_check"],
        "second_dan_free_raise": "parry",
        # 3rd Dan: non-standard (gain points to decrease action phases)
    },
    "matsu_bushi": {
        "first_dan_extra_die": ["double_attack", "iaijutsu", "wound_check"],
        "second_dan_free_raise": "iaijutsu",
        # 3rd Dan: non-standard (spend void to add to wound check)
    },
    "otaku_bushi": {
        "first_dan_extra_die": ["iaijutsu", "lunge", "wound_check"],
        "second_dan_free_raise": "wound_check",
        # 3rd Dan: non-standard (increase attacker's next action dice)
    },
    "shinjo_bushi": {
        "first_dan_extra_die": ["double_attack", "initiative", "parry"],
        "second_dan_free_raise": "parry",
        # 3rd Dan: non-standard (decrease action dice after parry)
    },
    "yogo_warden": {
        "first_dan_extra_die": ["attack", "damage", "wound_check"],
        "second_dan_free_raise": "wound_check",
        # 3rd Dan: non-standard (spend void to reduce light wounds)
    },

    # =================== COUNTERATTACK SCHOOLS ====================
    "daidoji_yojimbo": {
        "first_dan_extra_die": ["attack", "counterattack", "wound_check"],
        "second_dan_free_raise": "counterattack",
        # 3rd Dan: non-standard (add free raises to wound checks from counterattack damage)
    },
    "shiba_bushi": {
        "first_dan_extra_die": ["double_attack", "parry", "wound_check"],
        "second_dan_free_raise": "parry",
        # 3rd Dan: non-standard (parries deal damage)
    },

    # ===================== DUELIST SCHOOLS ========================
    "isawa_duelist": {
        "first_dan_extra_die": ["double_attack", "lunge", "wound_check"],
        "second_dan_free_raise": "wound_check",
        # 3rd Dan: non-standard (trade TN for attack bonus)
    },
    "kakita_duelist": {
        "first_dan_extra_die": ["double_attack", "iaijutsu", "initiative"],
        "second_dan_free_raise": "iaijutsu",
        # 3rd Dan: non-standard (attacks gain bonus per phase)
    },

    # ====================== MONK SCHOOLS ==========================
    "brotherhood_of_shinsei_monk": {
        "first_dan_extra_die": ["attack", "damage", "wound_check"],
        "second_dan_free_raise": "attack",
        "third_dan": {
            "source_skill": "precepts",
            "applicable_to": [
                "history", "law", "precepts", "wound_check", "attack",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },
    "togashi_ise_zumi": {
        "first_dan_extra_die": ["attack", "parry", "athletics"],
        "second_dan_free_raise": "athletics",
        # 3rd Dan: non-standard (4X free raises daily for athletics only)
    },

    # ============== INVESTIGATOR / SUPPORT SCHOOLS ================
    "hiruma_scout": {
        "first_dan_extra_die": ["initiative", "parry", "wound_check"],
        "second_dan_free_raise": "parry",
        # 3rd Dan: non-standard (add bonus to next attack after parry)
    },
    "kitsuki_magistrate": {
        "first_dan_extra_die": ["investigation", "interrogation", "wound_check"],
        "second_dan_free_raise": "interrogation",
        "third_dan": {
            "source_skill": "investigation",
            "applicable_to": [
                "interrogation", "intimidation", "law", "underworld",
                "attack", "wound_check",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },
    "kuni_witch_hunter": {
        "first_dan_extra_die": ["damage", "interrogation", "wound_check"],
        "second_dan_free_raise": "interrogation",
        "third_dan": {
            "source_skill": "investigation",
            "applicable_to": [
                "interrogation", "intimidation", "law", "underworld",
                "attack", "wound_check", "damage",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },

    # ================ COURT & MERCHANT SCHOOLS ====================
    "courtier": {
        "first_dan_extra_die": ["tact", "manipulation", "wound_check"],
        "second_dan_free_raise": "manipulation",
        "third_dan": {
            "source_skill": "tact",
            "applicable_to": [
                "heraldry", "manipulation", "sincerity", "tact",
                "attack", "wound_check",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },
    "doji_artisan": {
        "first_dan_extra_die": ["counterattack", "manipulation", "wound_check"],
        "second_dan_free_raise": "manipulation",
        "third_dan": {
            "source_skill": "culture",
            "applicable_to": [
                "bragging", "culture", "heraldry", "manipulation",
                "counterattack", "wound_check",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },
    "ide_diplomat": {
        "first_dan_extra_die": None,   # "precepts and two chosen roll types"
        "second_dan_free_raise": None,  # "any chosen roll type"
        # 3rd Dan: non-standard (spend void to subtract Xk1 after any roll)
    },
    "merchant": {
        "first_dan_extra_die": ["interrogation", "sincerity", "wound_check"],
        "second_dan_free_raise": "interrogation",
        "third_dan": {
            "source_skill": "sincerity",
            "applicable_to": [
                "commerce", "heraldry", "interrogation", "sincerity",
                "attack", "wound_check",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },
    "shosuro_actor": {
        "first_dan_extra_die": ["attack", "sincerity", "wound_check"],
        "second_dan_free_raise": "sincerity",
        "third_dan": {
            "source_skill": "sincerity",
            "applicable_to": [
                "acting", "heraldry", "sincerity", "sneaking",
                "attack", "wound_check",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },

    # =============== ARTISAN / KNOWLEDGE SCHOOLS ===================
    "ikoma_bard": {
        "first_dan_extra_die": ["attack", "bragging", "wound_check"],
        "second_dan_free_raise": "attack",
        "third_dan": {
            "source_skill": "bragging",
            "applicable_to": [
                "bragging", "culture", "heraldry", "intimidation",
                "attack", "wound_check",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },

    # ================== SPELLCASTER SCHOOLS =======================
    "isawa_ishi": {
        "first_dan_extra_die": None,   # "precepts and two chosen skill rolls"
        "second_dan_free_raise": None,  # "all rolls for a chosen skill"
        # 3rd Dan: non-standard (spend void to add Xk1 to ally's roll)
    },
    "priest": {
        "first_dan_extra_die": None,   # "precepts, one chosen skill, one combat roll type"
        "second_dan_free_raise": None,  # "all Honor bonus rolls" (special)
        # 3rd Dan: non-standard (roll dice at combat start; swap for rolled dice)
    },
    "shugenja": {
        "first_dan_extra_die": None,   # "precepts or commune/spellcasting for a chosen element"
        "second_dan_free_raise": None,  # "precepts or commune/spellcasting for a chosen element"
        "third_dan": {
            "source_skill": "precepts",
            "applicable_to": [
                "bragging", "intimidation", "precepts", "tact",
                "wound_check", "spellcasting",
            ],
            "formula": "2X",
            "max_per_roll": "X",
        },
    },
}


# ---------------------------------------------------------------------------
# SCHOOL RING OPTIONS
# ---------------------------------------------------------------------------

SCHOOL_RING_OPTIONS: Dict[str, List[str]] = {}
for _sid, _school in SCHOOLS.items():
    if _school.school_ring in ("Air", "Fire", "Earth", "Water", "Void"):
        SCHOOL_RING_OPTIONS[_sid] = [_school.school_ring]
    elif _school.school_ring == "any non-Void":
        SCHOOL_RING_OPTIONS[_sid] = ["Air", "Fire", "Earth", "Water"]
    elif _school.school_ring == "Air or Water":
        SCHOOL_RING_OPTIONS[_sid] = ["Air", "Water"]
    else:  # pragma: no cover
        # Import-time guard: fires only if someone adds a school with a
        # school_ring format this loop doesn't recognize. Can't test without
        # monkey-patching SCHOOLS mid-import.
        raise ValueError(
            f"School {_sid!r} has unrecognized school_ring {_school.school_ring!r}; "
            "add it to SCHOOL_RING_OPTIONS handling in game_data.py."
        )


# ---------------------------------------------------------------------------
# CAMPAIGN ADVANTAGES & DISADVANTAGES (Wasp Bounty Hunters)
# ---------------------------------------------------------------------------

_CAMPAIGN_ADVANTAGES_LIST: List[Advantage] = [
    Advantage(
        "family_reckoning_righteous_sting",
        "Family Reckoning: Righteous Sting",
        5,
        "Your family's actions during the Wasp clan's founding are remembered favorably. "
        "Your Rank is considered 2.0 higher, and the Rank of your entire party is considered "
        "1.0 higher when dealing with those who know this history.",
    ),
    Advantage(
        "highest_regard",
        "Highest Regard",
        4,
        "You carry a written letter of introduction from a notable Wasp figure. Your Rank and "
        "Recognition are considered 2.0 higher when dealing with Wasp clan members. You get "
        "4 free raises on bragging and intimidation rolls with Wasp (2 free raises with others).",
    ),
    Advantage(
        "household_wealth",
        "Household Wealth",
        4,
        "Replaces Wealthy. Your base stipend rank is 10 instead of the campaign default of 4, "
        "giving you 100 koku/year. If you are a Merchant or Shosuro Actor, your stipend rank "
        "is 15 (225 koku/year).",
    ),
    Advantage(
        "minor_clan_major_ally_sparrow",
        "Minor Clan Major Ally: Sparrow",
        2,
        "Your Rank and Recognition are considered 3.0 higher when dealing with Sparrow clan "
        "members. You can call on Sparrow allies to delay legal proceedings or investigations.",
    ),
    Advantage(
        "minor_clan_major_ally_fox",
        "Minor Clan Major Ally: Fox",
        4,
        "Your Rank and Recognition are considered 3.0 higher when dealing with Fox clan members. "
        "You have access to Fox shugenja specialists who may assist with spiritual matters.",
    ),
    Advantage(
        "minor_clan_major_ally_mantis",
        "Minor Clan Major Ally: Mantis",
        6,
        "Your Rank and Recognition are considered 3.0 higher when dealing with Mantis clan members. "
        "You have access to discreet Mantis warriors who can be called upon for assistance.",
    ),
    Advantage(
        "streetwise",
        "Streetwise",
        5,
        "You get a free raise on etiquette, law, intimidation, and underworld rolls when they "
        "are related to your authority as a bounty hunter.",
    ),
]

CAMPAIGN_ADVANTAGES: Dict[str, Advantage] = {a.id: a for a in _CAMPAIGN_ADVANTAGES_LIST}

_CAMPAIGN_DISADVANTAGES_LIST: List[Disadvantage] = [
    Disadvantage(
        "crane_indebted",
        "Crane-indebted",
        4,
        "You owe a debt to Crane patrons who supported the Wasp clan. You are expected to "
        "act in their interests when called upon. Failure to honor this obligation results "
        "in gaining the Bad Reputation disadvantage.",
    ),
    Disadvantage(
        "family_reckoning_venomous_sting",
        "Family Reckoning: Venomous Sting",
        5,
        "Your family's actions during the Wasp clan's founding are remembered unfavorably. "
        "Your Rank is considered 2.0 lower, and the Rank of your entire party is considered "
        "1.0 lower when dealing with those who know this history.",
    ),
    Disadvantage(
        "imperial_disdain",
        "Imperial Disdain",
        2,
        "You do not gain Recognition bonuses from bragging when dealing with those serving in "
        "Imperial posts. Additionally, the Rank of your entire party is considered 1.0 lower "
        "when dealing with Imperial post holders.",
    ),
    Disadvantage(
        "lion_enmity",
        "Lion Enmity",
        4,
        "You have earned the enmity of the Lion clan. You suffer a -10 penalty to all rolls "
        "when dealing with the Zenji house, and a -5 penalty with other Matsu families.",
    ),
    Disadvantage(
        "peasantborn",
        "Peasantborn",
        2,
        "You are never considered to have peer standing with samurai-born characters. You face "
        "restrictions on dueling, making arrests, and initiating violence against samurai.",
    ),
    Disadvantage(
        "scorpion_advocate",
        "Scorpion Advocate",
        2,
        "A Scorpion contact has leverage over you and periodically directs you to thwart Wasp "
        "bounty hunters who are acting dishonorably or outside the bounds of their authority.",
    ),
]

CAMPAIGN_DISADVANTAGES: Dict[str, Disadvantage] = {d.id: d for d in _CAMPAIGN_DISADVANTAGES_LIST}


# ---------------------------------------------------------------------------
# GROUP EFFECTS
# ---------------------------------------------------------------------------
#
# Advantages / disadvantages whose effects also apply to other party members
# in the same gaming group. Each entry is a dict with:
#   "name":          display name (used in callout headings + status modifier sources)
#   "label":         short rule summary shown in the Party Effects callout
#   "rank_modifier" (optional): tuple of (delta, context_template). When present,
#                               the effect contributes a Rank modifier to every
#                               party member's effective status. The context
#                               template gets ``{name}`` filled with the source
#                               character's name.

GROUP_EFFECTS: Dict[str, Dict[str, Any]] = {
    "thoughtless": {
        "name": "Thoughtless",
        "label": (
            "Opponents get +2 free raises on Manipulation rolls against allies "
            "(in addition to the +4 against the taker)."
        ),
    },
    "lion_enmity": {
        "name": "Lion Enmity",
        "label": (
            "-10 to all rolls dealing with the Zenji house and -5 with other "
            "Matsu families, for the entire party."
        ),
    },
    "family_reckoning_venomous_sting": {
        "name": "Family Reckoning: Venomous Sting",
        "label": (
            "Party Rank is considered 1.0 lower when dealing with those who "
            "know this history."
        ),
        "rank_modifier": (-1.0, "with those aware of {name}'s family history"),
    },
    "family_reckoning_righteous_sting": {
        "name": "Family Reckoning: Righteous Sting",
        "label": (
            "Party Rank is considered 1.0 higher when dealing with those who "
            "know this history."
        ),
        "rank_modifier": (1.0, "with those aware of {name}'s family history"),
    },
    "imperial_disdain": {
        "name": "Imperial Disdain",
        "label": (
            "Party Rank is considered 1.0 lower when dealing with Imperial "
            "post holders."
        ),
        "rank_modifier": (-1.0, "with Imperial post holders ({name}'s Imperial Disdain)"),
    },
}


# ---------------------------------------------------------------------------
# CONVENIENCE: all data in one place for iteration
# ---------------------------------------------------------------------------

# Schools whose abilities, techniques, or knacks (e.g. feint) can grant
# temporary void points. The View Sheet shows a Temp VP counter for these.
SCHOOLS_WITH_TEMP_VOID: set = set()
for _s in _SCHOOLS_LIST:
    # Check if any technique or the special ability mentions "temporary void"
    _texts = [_s.special_ability or ""]
    _texts.extend(str(v) for v in _s.techniques.values())
    if any("temporary void" in t.lower() for t in _texts):
        SCHOOLS_WITH_TEMP_VOID.add(_s.id)
    # Schools with the feint knack also get temp VP (feint grants them)
    if "feint" in _s.school_knacks:
        SCHOOLS_WITH_TEMP_VOID.add(_s.id)


_BUSHI_CATEGORIES = {"bushi", "counterattack", "duelist", "investigator"}
SCHOOLS_BUSHI_NONBUSHI = [
    ("Bushi Schools", sorted(
        [s for s in _SCHOOLS_LIST if s.category in _BUSHI_CATEGORIES],
        key=lambda s: s.name,
    )),
    ("Non-Bushi Schools", sorted(
        [s for s in _SCHOOLS_LIST if s.category not in _BUSHI_CATEGORIES],
        key=lambda s: s.name,
    )),
]


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
