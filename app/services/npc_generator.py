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
* prices the NPC's advantages and disadvantages (``trait_budget``) and
  shrinks the simulator's budget to match,
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
import re
import statistics
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from simulation.schools.factory import get_school
from simulation.templates.generator import generate_template
from simulation.templates.strategies import SCHOOL_NAMES as SIM_SCHOOL_NAMES
from simulation.templates.strategies import SCHOOL_PRIORITIES as SIM_SCHOOL_PRIORITIES

from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
    COMBAT_SKILLS,
    DISADVANTAGES,
    NPC_COMBAT_SHARE_SAMPLES,
    PROFESSION_CHARACTER_TYPE,
    SCHOOL_KNACKS,
    SCHOOL_TECHNIQUE_BONUSES,
    SCHOOLS,
    SKILLS,
)
from app.services.xp import (
    TECHNIQUE_CHOICE_REQUIREMENTS,
    _advantage_is_combat,
    _combat_advantage_labels,
    advantage_items,
    calculate_total_xp,
    disadvantage_items,
)

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
# Advantages and disadvantages
# ---------------------------------------------------------------------------

# Trait field -> (catalog, what to call an id missing from it).
_TRAIT_CATALOGS: Dict[str, Tuple[Dict[str, Any], str]] = {
    "advantages": (ADVANTAGES, "advantage"),
    "disadvantages": (DISADVANTAGES, "disadvantage"),
    "campaign_advantages": (CAMPAIGN_ADVANTAGES, "campaign advantage"),
    "campaign_disadvantages": (CAMPAIGN_DISADVANTAGES, "campaign disadvantage"),
}
TRAIT_FIELDS = tuple(_TRAIT_CATALOGS) + ("specializations", "advantage_details")


def normalize_traits(traits: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validated, canonical traits: every ``TRAIT_FIELDS`` key present.

    Raises ``ValueError`` naming the problem, so a GM request is refused
    before anything is built. The legacy ``specialization`` advantage flag is
    dropped: the ``specializations`` list is what the sheet prices and rolls.
    """
    traits = traits or {}
    unknown = sorted(set(traits) - set(TRAIT_FIELDS))
    if unknown:
        raise ValueError(f"unknown trait field {unknown[0]!r}")
    out: Dict[str, Any] = {}
    for field, (catalog, what) in _TRAIT_CATALOGS.items():
        ids = traits.get(field) or []
        if not isinstance(ids, list):
            raise ValueError(f"{field} must be a list")
        ids = [i for i in ids if not (field == "advantages" and i == "specialization")]
        for i in ids:
            if i not in catalog:
                raise ValueError(f"unknown {what} {i!r}")
        if len(set(ids)) != len(ids):
            raise ValueError(f"a {what} is listed twice")
        out[field] = list(ids)
    specs = []
    for spec in traits.get("specializations") or []:
        text = (spec.get("text") or "").strip() if isinstance(spec, dict) else ""
        skills = spec.get("skills") if isinstance(spec, dict) else None
        if not text or not isinstance(skills, list) or len(skills) != 1 or (
                skills[0] not in SKILLS and skills[0] not in COMBAT_SKILLS):
            raise ValueError(f"bad specialization {spec!r}: needs text and one skill id")
        specs.append({"text": text, "skills": [skills[0]]})
    out["specializations"] = specs
    details = traits.get("advantage_details") or {}
    if not isinstance(details, dict):
        raise ValueError("advantage_details must be an object")
    out["advantage_details"] = dict(details)
    return out


def trait_budget(traits: Dict[str, Any]) -> Tuple[int, int, int]:
    """``(combat advantage XP, all advantage XP, disadvantage XP gained)``,
    priced and classified exactly as the sheet and the combat-share
    measurement do (``xp.advantage_items`` / ``_advantage_is_combat``)."""
    adv = advantage_items(traits["advantages"], traits["campaign_advantages"],
                          specializations=traits["specializations"])
    combat_labels = _combat_advantage_labels()
    combat = sum(i["xp"] for i in adv if _advantage_is_combat(i["label"], combat_labels))
    gained = -sum(i["xp"] for i in disadvantage_items(
        traits["disadvantages"], traits["campaign_disadvantages"]))
    return combat, sum(i["xp"] for i in adv), gained


def _trait_index() -> Dict[str, Tuple[str, str]]:
    """Lower-cased name or id -> (trait field, id), over every catalog."""
    index: Dict[str, Tuple[str, str]] = {}
    for field, (catalog, _what) in _TRAIT_CATALOGS.items():
        for tid, entry in catalog.items():
            if tid == "specialization":
                continue  # its skill cannot be told from a bare line
            index[tid.lower()] = (field, tid)
            index[entry.name.lower()] = (field, tid)
    return index


def match_trait_lines(lines: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Split a character's trait lines (Obsidian Portal's GM info lists one
    per line, e.g. "Contrary", "squinty") into ``(traits, flavor)``.

    A line matches when it IS an advantage or disadvantage name or id,
    ignoring case and surrounding space; anything else ("pauses before
    speaking") is flavor and is returned for the GM to read, never guessed
    at. Ids come back sorted, each once.
    """
    index = _trait_index()
    found: Dict[str, set] = {field: set() for field in _TRAIT_CATALOGS}
    flavor: List[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        hit = index.get(text.lower())
        if hit:
            found[hit[0]].add(hit[1])
        else:
            flavor.append(text)
    traits = {field: sorted(ids) for field, ids in found.items()}
    traits.update(specializations=[], advantage_details={})
    return traits, flavor


# ---------------------------------------------------------------------------
# Recorded stats
# ---------------------------------------------------------------------------
# Numbers the GM has already used in play ("NPC numbers: Air 4, sincerity 1"
# in an Obsidian Portal character's GM info). They do not add XP: they move to
# the front of the build order, so the same budget buys them first.

_RINGS = ("Air", "Earth", "Fire", "Water", "Void")


def _stat_names() -> Dict[str, str]:
    """Lower-cased stat name or id -> canonical key (ring name or id)."""
    names: Dict[str, str] = {r.lower(): r for r in _RINGS}
    names.update(attack="attack", parry="parry")
    for catalog in (SKILLS, SCHOOL_KNACKS):
        for sid, entry in catalog.items():
            names[sid] = sid
            names[entry.name.lower()] = sid
    return names


def normalize_recorded(recorded: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Validated recorded stats keyed by ring name or skill / knack id."""
    names = _stat_names()
    out: Dict[str, int] = {}
    for key, value in (recorded or {}).items():
        canonical = names.get(str(key).strip().lower())
        if canonical is None:
            raise ValueError(f"unknown stat {key!r}")
        try:
            rank = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a whole number") from None
        if not 0 <= rank <= 6:
            raise ValueError(f"{key} must be between 0 and 6")
        out[canonical] = rank
    return out


_STAT_LINE = re.compile(r"^\s*[-*]?\s*(.+?)\s+(\d+)\s*$")


def match_stat_lines(lines: List[str]) -> Tuple[Dict[str, int], List[str]]:
    """``(recorded, unrecognised lines)`` from "- Air 4" style lines."""
    names = _stat_names()
    recorded: Dict[str, int] = {}
    unknown: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        m = _STAT_LINE.match(line)
        key = names.get(m.group(1).strip().lower()) if m else None
        if key is None:
            unknown.append(line.strip())
        else:
            recorded[key] = int(m.group(2))
    return recorded, unknown


def _recorded_plan(sim_key: str, recorded: Dict[str, int]) -> Tuple[list, Dict[str, int]]:
    """``(priority entries to put first, stats to buy from the remainder)``.

    What the simulator's own build order buys for this school (rings, attack,
    parry, its knacks and skills) leads that order, inside the combat budget;
    anything else (a courtier's Heraldry on a bushi) is bought afterwards out
    of the non-combat XP the simulator leaves unspent.
    """
    priorities = SIM_SCHOOL_PRIORITIES[SIM_SCHOOL_NAMES[sim_key]]
    sim_skills = {name for cat, name, _r in priorities if cat == "skill"} | {"attack", "parry"}
    to_sim = {v: k for k, v in SIM_KNACK_RENAMES.get(sim_key, {}).items()}
    lead: list = []
    rest: Dict[str, int] = {}
    for key, rank in recorded.items():
        if key in _RINGS:
            lead.append(("ring", key.lower(), rank))
            continue
        sim_name = to_sim.get(key, key).replace("_", " ")
        if sim_name in sim_skills:
            lead.append(("skill", sim_name, rank))
        elif rank > 0:
            rest[key] = rank
    return lead + list(priorities), rest


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


def build_npc(
    npc_type: str, earned_xp: int, combat_share: float,
    traits: Optional[Dict[str, Any]] = None,
    recorded: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Character fields for one NPC, in ``Character.to_dict()`` shape.

    ``earned_xp`` is on top of ``STARTING_XP``. The unspent remainder is the
    non-combat XP the simulator deliberately leaves unassigned.

    ``traits`` (``normalize_traits``) are the NPC's advantages and
    disadvantages, paid for the way the combat share was measured on real
    characters: disadvantages add their XP to the budget, as on the sheet;
    combat advantages (Lucky, Strength of the Earth, Quick Healer, combat
    specializations) come out of the combat share; the rest come out of the
    unspent remainder, and only shrink the combat spend when they do not fit.

    ``recorded`` (``normalize_recorded``) are stats already used in play.
    They cost no extra XP: they are bought first (``_recorded_plan``), and a
    build that cannot reach one is refused rather than quietly built short.
    """
    if npc_type not in npc_types():
        raise ValueError(f"unknown NPC type {npc_type!r}")
    if earned_xp < 0:
        raise ValueError("earned XP cannot be negative")
    traits = normalize_traits(traits)
    recorded = normalize_recorded(recorded)
    adv_combat, adv_total, gained = trait_budget(traits)
    total = STARTING_XP + earned_xp
    budget = total + gained
    combat = int(budget * combat_share)
    # The simulator keeps its own total at starting + earned (it sizes a
    # Wave Man's ability picks from it, as the sheet does), so a disadvantage
    # gain can never make it spend more than that.
    sim_combat = min(combat - adv_combat, budget - adv_total, total)
    if sim_combat <= 0:
        raise ValueError(
            f"the advantages cost more XP ({adv_total}) than this NPC has to spend"
        )
    # Untouched when nothing moved, so an NPC without traits builds exactly
    # as before; otherwise the fraction that floors to ``sim_combat``.
    unchanged = sim_combat == int(total * combat_share)
    fraction = combat_share if unchanged else min(1.0, (sim_combat + 0.5) / total)
    sim_key = npc_types()[npc_type]
    if recorded:
        priorities, rest = _recorded_plan(sim_key, recorded)
        config, breakdown = generate_template(
            sim_key, total, priorities=priorities, combat_xp_fraction=fraction)
    else:
        rest = {}
        config, breakdown = generate_template(sim_key, total, combat_xp_fraction=fraction)

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
    for key, rank in rest.items():
        bucket = knacks if key in school_knacks else foreign if key in SCHOOL_KNACKS else skills
        bucket[key] = max(rank, bucket.get(key, 0))

    abilities: Dict[str, int] = {}
    for name, count in config.abilities.items():
        if name not in _SIM_ABILITY_TO_SHEET:
            raise LookupError(f"simulator ability {name!r} has no match in this app")
        abilities[_SIM_ABILITY_TO_SHEET[name]] = count

    rings = {ring.capitalize(): rank for ring, rank in config.rings.items()}
    if recorded:
        _check_recorded(recorded, rings, attack, parry, {**skills, **knacks, **foreign})
    generation = {
        "npc_type": npc_type,
        "earned_xp": earned_xp,
        "combat_share": combat_share,
        "combat_budget": breakdown["combat_budget"],
        "simulator": simulator_version(),
    }
    if any(traits.values()):
        generation["traits"] = traits
    if recorded:
        generation["recorded"] = recorded
    out = {
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
        **traits,
        "generation": generation,
    }
    if rest:
        spent = calculate_total_xp(dict(out, name=""))["total"]
        if spent > budget:
            raise ValueError(
                f"the recorded stats need more XP than this NPC has ({spent} of {budget})"
            )
    return out


def _check_recorded(recorded: Dict[str, int], rings: Dict[str, int], attack: int,
                    parry: int, ranks: Dict[str, int]) -> None:
    for key, rank in recorded.items():
        have = rings.get(key) if key in _RINGS else {"attack": attack, "parry": parry}.get(
            key, ranks.get(key, 0))
        if have < rank:
            name = key if key in _RINGS else key.replace("_", " ")
            raise ValueError(f"the build could not reach {name} {rank} within its XP")


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
