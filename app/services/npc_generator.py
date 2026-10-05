"""Generated NPCs: build a combatant from the combat simulator's XP progression.

The GM says "the party is fighting Wave Men with about 50 earned XP"; this
module turns that into character fields. It deliberately decides NOTHING about
how XP is spent: that is the simulator's job (``l7r/simulator``, installed as
the ``l7r-combat-simulator`` package), whose per-school priority lists are
where questions like "when does a parry school take Air from 5 to 6" are
answered. This module only:

* rolls the XP (``roll_extra_xp``: base + 5 x an exploding d10, D5),
* draws the combat share (``draw_combat_share``: target + a deviation
  resampled from real characters, clamped to their range, D6/D14),
* calls ``simulation.templates.generator.generate_template``, and
* translates the result into this app's ids (the ONE place the two
  projects' vocabularies meet - see ``_SIM_SCHOOL_OVERRIDES`` and
  ``_SIM_ABILITY_TO_SHEET``; ``tests/test_npc_generator.py`` fails when the
  simulator grows something this cannot map).

See combat-design/design.md, sections 4.1 and 4.2.
"""

from __future__ import annotations

import functools
import importlib.metadata
import json
import os
import random
import statistics
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from simulation.schools.factory import get_school
from simulation.templates.generator import generate_template
from simulation.templates.strategies import SCHOOL_NAMES as SIM_SCHOOL_NAMES

from app.game_data import (
    NPC_COMBAT_SHARE_SAMPLES,
    PROFESSION_CHARACTER_TYPE,
    SCHOOL_KNACKS,
    SCHOOL_TECHNIQUE_BONUSES,
    SCHOOLS,
    SKILLS,
)
from app.services.xp import TECHNIQUE_CHOICE_REQUIREMENTS

# Starting XP every character has before any is earned (D2: "50 earned" is
# 150 + 50 = 200 total).
STARTING_XP = 150

WAVE_MAN = "wave_man"

# ---------------------------------------------------------------------------
# Vocabulary mapping (simulator -> this app)
# ---------------------------------------------------------------------------

# A simulator school maps to the sheet school whose name is its name minus
# " School"; these are the exceptions.
_SIM_SCHOOL_OVERRIDES: Dict[str, str] = {
    "Kakita Bushi School": "kakita_duelist",
}

# Simulator keys that are deliberately NOT offered as NPCs, with why.
UNSUPPORTED_SIM_KEYS: Dict[str, str] = {
    "ninja": "Ninja abilities are hidden in this app until their unlock feature exists",
}

# Per-school knack renames, simulator id -> this app's id. The rules swapped
# Hiruma's counterattack for lunge (rules commit 48410d9) and the simulator has
# not caught up (its BACKLOG.md). The GM's ruling: its XP progression is still
# good, so the counterattack ranks become lunge ranks. Drop the entry once the
# simulator's Hiruma has lunge.
SIM_KNACK_RENAMES: Dict[str, Dict[str, str]] = {
    "hiruma": {"counterattack": "lunge"},
}

# Wave Man abilities: simulator name -> this app's id (rules/09-professions.md order).
_SIM_ABILITY_TO_SHEET: Dict[str, str] = {
    "missed attack bonus": "wave_man_miss_raise",
    "parry penalty": "wave_man_parry_tn",
    "weapon damage bonus": "wave_man_weapon_dice",
    "rolled damage bonus": "wave_man_round_damage",
    "crippled bonus": "wave_man_impaired_reroll",
    "initiative bonus": "wave_man_initiative_die",
    "wound check bonus": "wave_man_wound_check_dice",
    "damage penalty": "wave_man_damage_reduction",
    "failed parry damage bonus": "wave_man_failed_parry_dice",
    "wound check penalty": "wave_man_wound_check_tn",
}

# Roll types a technique pick may name besides skills and knacks.
_COMBAT_ROLLS = ("attack", "damage", "initiative", "parry", "wound_check")

# Picks the simulator does not model. Kitsune Warden 3rd Dan adds "three
# skills of your choice" to its precepts free raises; they never matter in a
# fight, so any three eligible skills will do.
_FALLBACK_KITSUNE_THIRD_DAN_SKILLS = ["sincerity", "tact", "etiquette"]
_FALLBACK_COMBAT_ROLL_ORDER = ["wound_check", "attack", "initiative", "damage", "parry"]


def sheet_id(sim_name: str) -> str:
    """A simulator skill/knack/roll name ("double attack") as this app's id."""
    return sim_name.replace(" ", "_")


def _sheet_school_for(sim_school_name: str) -> Optional[str]:
    if sim_school_name in _SIM_SCHOOL_OVERRIDES:
        return _SIM_SCHOOL_OVERRIDES[sim_school_name]
    bare = sim_school_name.removesuffix(" School")
    for school in SCHOOLS.values():
        if school.name == bare:
            return school.id
    return None


@functools.lru_cache(maxsize=1)
def npc_types() -> Dict[str, str]:
    """NPC type id (a sheet school id, or ``"wave_man"``) -> simulator key.

    Everything the simulator can build, minus ``UNSUPPORTED_SIM_KEYS``. A
    simulator school that maps to nothing raises: that is drift, and must be
    fixed here (or listed as unsupported), never silently skipped.
    """
    out: Dict[str, str] = {}
    for sim_key, sim_name in SIM_SCHOOL_NAMES.items():
        if sim_key in UNSUPPORTED_SIM_KEYS:
            continue
        if sim_key == WAVE_MAN:
            out[WAVE_MAN] = sim_key
            continue
        school_id = _sheet_school_for(sim_name)
        if school_id is None:
            raise LookupError(f"simulator school {sim_name!r} has no match in app/game_data.py SCHOOLS")
        out[school_id] = sim_key
    return out


def npc_type_label(npc_type: str) -> str:
    if npc_type == WAVE_MAN:
        return "Wave Man"
    return SCHOOLS[npc_type].name


def npc_type_options() -> List[Tuple[str, str]]:
    """``(id, label)`` pairs for the encounter builder's picker, by label."""
    return sorted(((t, npc_type_label(t)) for t in npc_types()), key=lambda p: p[1])


def is_peasant_type(npc_type: str) -> bool:
    """Wave Men draw names from the peasant pool (D26)."""
    return npc_type == WAVE_MAN


# ---------------------------------------------------------------------------
# XP and combat share
# ---------------------------------------------------------------------------

def exploding_d10(rng: random.Random) -> List[int]:
    """One d10 whose 10s are rerolled and added: [10, 10, 2] totals 22."""
    faces = [rng.randint(1, 10)]
    while faces[-1] == 10:
        faces.append(rng.randint(1, 10))
    return faces


def roll_extra_xp(rng: random.Random) -> Tuple[int, List[int]]:
    """``(bonus earned XP, die faces)``: 5 x an exploding d10 (D5)."""
    faces = exploding_d10(rng)
    return 5 * sum(faces), faces


def combat_share_bounds() -> Tuple[float, float]:
    """Lowest and highest combat share any measured real character has had (D14)."""
    return min(NPC_COMBAT_SHARE_SAMPLES), max(NPC_COMBAT_SHARE_SAMPLES)


def default_combat_share() -> float:
    """The median measured combat share - the default target (D6)."""
    return statistics.median(NPC_COMBAT_SHARE_SAMPLES)


def clamp_combat_share(share: float) -> float:
    low, high = combat_share_bounds()
    return round(min(high, max(low, share)), 3)


def draw_combat_share(target: float, rng: random.Random) -> float:
    """``target`` plus one real character's deviation from the median, clamped.

    Resampling the measured deviations keeps the data's actual shape - a
    tight middle with a few far-out generalists and pure fighters - rather
    than assuming a bell curve.
    """
    deviation = rng.choice(NPC_COMBAT_SHARE_SAMPLES) - default_combat_share()
    return clamp_combat_share(target + deviation)


# ---------------------------------------------------------------------------
# Simulator provenance
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def simulator_version() -> str:
    """The simulator commit this process builds with, for NPC provenance.

    A deploy installs a copy of the simulator's committed HEAD and is told
    its commit through ``SIMULATOR_COMMIT`` (scripts/deploy.sh); a checkout
    installed editable is asked for its HEAD directly; a GitHub install
    records it in pip's metadata.
    """
    stamp = os.environ.get("SIMULATOR_COMMIT", "").strip()
    if stamp:
        return stamp
    try:
        dist = importlib.metadata.distribution("l7r-combat-simulator")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
    info = json.loads(dist.read_text("direct_url.json") or "{}")
    commit = (info.get("vcs_info") or {}).get("commit_id")
    if commit:
        return commit[:12]
    url = info.get("url", "")
    if url.startswith("file://"):
        try:
            out = subprocess.run(
                ["git", "-C", url[len("file://"):], "rev-parse", "--short=12", "HEAD"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            return out.stdout.strip() + "-local"
        except (OSError, subprocess.SubprocessError):
            pass
    return dist.version


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def _technique_choices(school_id: str, sim_school: Any) -> Dict[str, Any]:
    """Technique picks for schools whose Dans let the player choose a roll
    type, taken from the simulator school's own defaults where it has them
    (``extra_rolled`` / ``free_raise_skills``), so an NPC's sheet carries the
    same bonuses the simulator built it with."""
    fixed = set((SCHOOL_TECHNIQUE_BONUSES.get(school_id) or {}).get("first_dan_extra_die") or [])
    fixed.add("precepts")  # auto-applied wherever a school's 1st Dan includes it
    sim_extra = [sheet_id(x) for x in sim_school.extra_rolled()]
    sim_free = [sheet_id(x) for x in sim_school.free_raise_skills()]

    def eligible(pick: str) -> bool:
        return pick in _COMBAT_ROLLS or pick in SKILLS or pick in SCHOOL_KNACKS

    choices: Dict[str, Any] = {}
    for req in TECHNIQUE_CHOICE_REQUIREMENTS:
        if school_id not in req["schools"]:
            continue
        key, count = req["key"], req["count"]
        if key == "first_dan_choices" and school_id == "priest":
            # Priest: [one skill, one combat roll] on top of precepts.
            pool = sim_extra + sim_free
            skill = next((p for p in pool if p in SKILLS and p not in fixed), "sincerity")
            roll = next((p for p in pool if p in _COMBAT_ROLLS), "wound_check")
            choices[key] = [skill, roll]
        elif key == "first_dan_choices":
            picks = [p for p in sim_extra if eligible(p) and p not in fixed]
            for p in _FALLBACK_COMBAT_ROLL_ORDER:
                if len(picks) >= count:
                    break
                if p not in picks and p not in fixed:
                    picks.append(p)
            choices[key] = picks[:count]
        elif key == "third_dan_skill_choices":
            choices[key] = list(_FALLBACK_KITSUNE_THIRD_DAN_SKILLS[:count])
        else:  # a single free-raise pick (second_dan_choice, mantis_2nd_dan_free_raise)
            pick = next((p for p in sim_free if eligible(p)), "wound_check")
            choices[key] = pick
    return choices


def build_npc(npc_type: str, earned_xp: int, combat_share: float) -> Dict[str, Any]:
    """Character fields for one NPC, in ``Character.to_dict()`` shape.

    ``earned_xp`` is on top of ``STARTING_XP``. The unspent remainder is the
    non-combat XP the simulator deliberately leaves unassigned.
    """
    if npc_type not in npc_types():
        raise ValueError(f"unknown NPC type {npc_type!r}")
    if earned_xp < 0:
        raise ValueError("earned XP cannot be negative")
    sim_key = npc_types()[npc_type]
    config, breakdown = generate_template(
        sim_key, STARTING_XP + earned_xp, combat_xp_fraction=combat_share,
    )

    is_profession = npc_type == WAVE_MAN
    school_id = "" if is_profession else npc_type
    school_knacks = set() if is_profession else set(SCHOOLS[school_id].school_knacks)
    sim_school = None if is_profession else get_school(SIM_SCHOOL_NAMES[sim_key])
    renames = SIM_KNACK_RENAMES.get(sim_key, {})

    skills: Dict[str, int] = {}
    knacks: Dict[str, int] = {}
    foreign: Dict[str, int] = {}
    attack = parry = 1
    for name, rank in config.skills.items():
        sid = renames.get(sheet_id(name), sheet_id(name))
        if sid == "attack":
            attack = rank
        elif sid == "parry":
            parry = rank
        elif sid in school_knacks:
            knacks[sid] = rank
        elif sid in SCHOOL_KNACKS:
            foreign[sid] = rank
        elif sid in SKILLS:
            skills[sid] = rank
        else:
            raise LookupError(f"simulator skill {name!r} has no match in this app")
    for knack in school_knacks:
        knacks.setdefault(knack, 1)  # school knacks start at 1 for free

    abilities: Dict[str, int] = {}
    for name, count in config.abilities.items():
        if name not in _SIM_ABILITY_TO_SHEET:
            raise LookupError(f"simulator ability {name!r} has no match in this app")
        abilities[_SIM_ABILITY_TO_SHEET[name]] = count

    rings = {ring.capitalize(): rank for ring, rank in config.rings.items()}
    return {
        "school": school_id,
        "school_ring_choice": "" if is_profession else sim_school.school_ring().capitalize(),
        "profession": PROFESSION_CHARACTER_TYPE if is_profession else "",
        "profession_abilities": abilities,
        "rings": rings,
        "attack": attack,
        "parry": parry,
        "skills": skills,
        "knacks": knacks,
        "foreign_knacks": foreign,
        "technique_choices": {} if is_profession else _technique_choices(school_id, sim_school),
        "starting_xp": STARTING_XP,
        "earned_xp": earned_xp,
        "generation": {
            "npc_type": npc_type,
            "earned_xp": earned_xp,
            "combat_share": combat_share,
            "combat_budget": breakdown["combat_budget"],
            "simulator": simulator_version(),
        },
    }


def never_below(previous: Dict[str, Any], build: Dict[str, Any]) -> Dict[str, Any]:
    """``build`` with every stat raised to at least ``previous``'s.

    A returning NPC who gained XP is re-generated at the higher total (D8),
    and should never come back weaker. The simulator's greedy walk is not
    strictly monotonic between its tiers for every school (see its
    BACKLOG.md), so a re-generation can occasionally lower one stat by a
    rank; holding it costs a few of the NPC's unspent non-combat XP.
    """
    out = dict(build)
    out["rings"] = {r: max(v, (previous.get("rings") or {}).get(r, 0)) for r, v in build["rings"].items()}
    out["attack"] = max(build["attack"], previous.get("attack", 1))
    out["parry"] = max(build["parry"], previous.get("parry", 1))
    for field in ("skills", "knacks", "foreign_knacks", "profession_abilities"):
        merged = dict(previous.get(field) or {})
        for k, v in (build.get(field) or {}).items():
            merged[k] = max(v, merged.get(k, 0))
        out[field] = merged
    return out
