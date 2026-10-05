"""The GM's NPC generator (app/services/npc_generator.py; combat-design/design.md 4.1-4.2)."""

import importlib.metadata
import pathlib
import random
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.game_data import NPC_COMBAT_SHARE_SAMPLES, SCHOOLS
from app.services import npc_generator as gen
from app.services.xp import calculate_total_xp, validate_character

# Warnings every NPC gets because it is not a PC; Phase 3 suppresses them on
# NPC sheets. Anything else from validate_character is a real translation bug.
_PC_ONLY_WARNINGS = ("Age is not set.", "Lineage is not set.", "unclaimed profession pick")


def _as_character(build):
    d = dict(build)
    d.update(name="NPC", honor=1.0, rank=7.5, recognition=7.5)
    return d


class FakeRng:
    """Deterministic stand-in: ``randint`` and ``choice`` pop scripted values."""

    def __init__(self, ints=(), choices=()):
        self.ints = list(ints)
        self.choices = list(choices)

    def randint(self, a, b):
        return self.ints.pop(0)

    def choice(self, seq):
        value = self.choices.pop(0)
        assert value in seq
        return value


# ---------------------------------------------------------------------------
# Combat share table
# ---------------------------------------------------------------------------

def test_combat_share_table_matches_the_analysis():
    analysis = pathlib.Path(__file__).resolve().parent.parent / "analysis"
    sys.path.insert(0, str(analysis))
    try:
        import xp_profile_ranges
    finally:
        sys.path.remove(str(analysis))
    assert NPC_COMBAT_SHARE_SAMPLES == xp_profile_ranges.npc_combat_share_samples()


def test_default_share_and_bounds_come_from_the_samples():
    assert gen.default_combat_share() == pytest.approx(0.741)
    assert gen.combat_share_bounds() == (0.532, 0.91)


def test_draw_resamples_a_measured_deviation():
    # target 0.70 + (0.785 - 0.741)
    assert gen.draw_combat_share(0.70, FakeRng(choices=[0.785])) == pytest.approx(0.744)


@pytest.mark.parametrize("target,sample,expected", [
    (0.88, 0.91, 0.91),     # 0.88 + 0.169 clamps to the highest real PC
    (0.55, 0.532, 0.532),   # 0.55 - 0.209 clamps to the lowest
])
def test_draw_is_clamped_to_the_measured_range(target, sample, expected):
    assert gen.draw_combat_share(target, FakeRng(choices=[sample])) == expected


def test_clamp_applies_to_overrides_too():
    assert gen.clamp_combat_share(1.0) == 0.91
    assert gen.clamp_combat_share(0.1) == 0.532
    assert gen.clamp_combat_share(0.8) == 0.8


# ---------------------------------------------------------------------------
# XP roll
# ---------------------------------------------------------------------------

def test_exploding_d10_rerolls_tens():
    assert gen.exploding_d10(FakeRng(ints=[10, 10, 2])) == [10, 10, 2]
    assert gen.exploding_d10(FakeRng(ints=[7])) == [7]


def test_roll_extra_xp_is_five_times_the_total():
    assert gen.roll_extra_xp(FakeRng(ints=[10, 10, 2])) == (110, [10, 10, 2])
    assert gen.roll_extra_xp(FakeRng(ints=[3])) == (15, [3])


def test_roll_extra_xp_with_a_real_rng_is_a_multiple_of_five():
    rng = random.Random(7)
    for _ in range(200):
        bonus, faces = gen.roll_extra_xp(rng)
        assert bonus == 5 * sum(faces) and bonus % 5 == 0 and bonus >= 5
        assert all(f == 10 for f in faces[:-1]) and faces[-1] != 10


# ---------------------------------------------------------------------------
# Vocabulary mapping
# ---------------------------------------------------------------------------

def test_every_simulator_school_is_offered_or_explicitly_unsupported():
    offered = set(gen.npc_types().values())
    for sim_key in gen.SIM_SCHOOL_NAMES:
        assert (sim_key in offered) != (sim_key in gen.UNSUPPORTED_SIM_KEYS), sim_key


def test_offered_schools_agree_with_this_app():
    """The simulator's school knacks and ring must match this app's (which
    track the rules), or its builds would be priced and Dan-ranked wrongly
    here. A school that drifts must be fixed in the simulator or listed in
    UNSUPPORTED_SIM_KEYS."""
    from app.game_data import SCHOOL_RING_OPTIONS
    from simulation.schools.factory import get_school
    for npc_type, sim_key in gen.npc_types().items():
        if npc_type == "wave_man":
            continue
        sim_school = get_school(gen.SIM_SCHOOL_NAMES[sim_key])
        renames = gen.SIM_KNACK_RENAMES.get(sim_key, {})
        sim_knacks = [renames.get(gen.sheet_id(k), gen.sheet_id(k)) for k in sim_school.school_knacks()]
        assert sorted(sim_knacks) == sorted(SCHOOLS[npc_type].school_knacks), npc_type
        assert sim_school.school_ring().capitalize() in SCHOOL_RING_OPTIONS[npc_type], npc_type


def test_npc_types_include_the_new_schools_and_wave_man():
    types = gen.npc_types()
    assert types["kakita_duelist"] == "kakita"
    assert types["mantis_wave_treader"] == "mantis"
    assert types["kitsune_warden"] == "kitsune_warden"
    assert types["suzume_overseer"] == "suzume"
    assert types["wave_man"] == "wave_man"
    assert "ninja" not in types.values()
    assert types["hiruma_scout"] == "hiruma"
    assert "shugenja" not in types


def test_an_unmappable_simulator_school_is_loud(monkeypatch):
    monkeypatch.setattr(gen, "SIM_SCHOOL_NAMES", {"x": "Nonexistent Bushi School"})
    gen.npc_types.cache_clear()
    try:
        with pytest.raises(LookupError, match="Nonexistent"):
            gen.npc_types()
    finally:
        gen.npc_types.cache_clear()


def test_type_options_are_labelled_and_sorted():
    options = gen.npc_type_options()
    labels = [label for _, label in options]
    assert labels == sorted(labels)
    assert ("wave_man", "Wave Man") in options
    assert ("kakita_duelist", SCHOOLS["kakita_duelist"].name) in options


def test_only_wave_men_are_peasants():
    assert gen.is_peasant_type("wave_man")
    assert not gen.is_peasant_type("kakita_duelist")


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("npc_type", sorted(gen.npc_types()))
@pytest.mark.parametrize("earned", [0, 50, 125, 300])
def test_every_type_builds_a_valid_character(npc_type, earned):
    build = gen.build_npc(npc_type, earned, gen.default_combat_share())
    character = _as_character(build)
    spent = calculate_total_xp(character)["total"]
    assert spent <= gen.STARTING_XP + earned
    # Everything the simulator bought is priced identically here: the spend
    # lands at the combat budget, short by at most one unaffordable item.
    assert build["generation"]["combat_budget"] - 30 <= spent <= build["generation"]["combat_budget"]
    problems = [w for w in validate_character(character) if not any(p in w for p in _PC_ONLY_WARNINGS)]
    assert problems == []


def test_a_school_npc_translates_rings_skills_and_knacks():
    build = gen.build_npc("kakita_duelist", 50, 0.741)
    assert build["school"] == "kakita_duelist"
    assert build["school_ring_choice"] == "Fire"
    assert build["profession"] == ""
    assert set(build["rings"]) == {"Air", "Earth", "Fire", "Water", "Void"}
    assert set(build["knacks"]) == {"double_attack", "iaijutsu", "lunge"}
    assert build["attack"] >= 1 and build["parry"] >= 1
    assert build["earned_xp"] == 50 and build["starting_xp"] == 150
    assert build["generation"]["combat_share"] == 0.741
    assert build["generation"]["simulator"]


def test_a_wave_man_is_a_profession_character():
    build = gen.build_npc("wave_man", 50, 0.741)
    assert build["school"] == "" and build["profession"] == "profession"
    assert build["knacks"] == {} and build["technique_choices"] == {}
    assert all(k.startswith("wave_man_") for k in build["profession_abilities"])
    # One ability at 150 total XP, +1 per 15 (the simulator bug fixed for D1).
    assert sum(build["profession_abilities"].values()) == (200 - 150) // 15 + 1


def test_combat_share_moves_the_budget():
    lean = gen.build_npc("wave_man", 100, 0.6)
    heavy = gen.build_npc("wave_man", 100, 0.9)
    assert heavy["generation"]["combat_budget"] > lean["generation"]["combat_budget"]
    assert sum(heavy["rings"].values()) >= sum(lean["rings"].values())


def test_school_ring_choice_schools_take_the_simulators_default():
    assert gen.build_npc("mantis_wave_treader", 50, 0.741)["school_ring_choice"] == "Fire"
    assert gen.build_npc("kitsune_warden", 50, 0.741)["school_ring_choice"] == "Fire"
    assert gen.build_npc("suzume_overseer", 50, 0.741)["school_ring_choice"] == "Water"


def test_technique_picks_follow_the_simulators_defaults():
    # Ide: the simulator's 1st Dan extra dice are precepts + wound check + initiative
    # (precepts is automatic here) and its 2nd Dan free raise is attack.
    ide = gen.build_npc("ide_diplomat", 150, 0.741)["technique_choices"]
    assert ide["first_dan_choices"] == ["wound_check", "initiative"]
    assert ide["second_dan_choice"] == "attack"
    kitsune = gen.build_npc("kitsune_warden", 150, 0.741)["technique_choices"]
    assert kitsune["first_dan_choices"] == ["attack", "damage", "wound_check"]
    assert kitsune["second_dan_choice"] == "wound_check"
    assert len(kitsune["third_dan_skill_choices"]) == 3
    assert gen.build_npc("mantis_wave_treader", 150, 0.741)["technique_choices"] == {
        "mantis_2nd_dan_free_raise": "attack",
    }
    priest = gen.build_npc("priest", 150, 0.741)["technique_choices"]["first_dan_choices"]
    assert priest[0] in gen.SKILLS and priest[1] in gen._COMBAT_ROLLS


def test_technique_picks_fall_back_when_the_simulator_has_too_few():
    school = SimpleNamespace(extra_rolled=lambda: ["precepts"], free_raise_skills=lambda: ["nothing useful"])
    picks = gen._technique_choices("kitsune_warden", school)
    assert picks["first_dan_choices"] == ["wound_check", "attack", "initiative"]
    assert picks["second_dan_choice"] == "wound_check"
    priest = gen._technique_choices("priest", school)
    assert priest["first_dan_choices"] == ["sincerity", "wound_check"]


def test_build_rejects_unknown_types_and_negative_xp():
    with pytest.raises(ValueError):
        gen.build_npc("shugenja", 50, 0.741)
    with pytest.raises(ValueError):
        gen.build_npc("wave_man", -5, 0.741)


def _fake_template(skills=None, abilities=None):
    def fake(sim_key, total_xp, combat_xp_fraction):
        config = SimpleNamespace(
            skills=skills or {"attack": 2, "parry": 2},
            abilities=abilities or {},
            rings={"air": 2, "earth": 2, "fire": 2, "water": 2, "void": 2},
        )
        return config, {"combat_budget": 10}
    return fake


def test_a_foreign_knack_lands_in_foreign_knacks(monkeypatch):
    monkeypatch.setattr(gen, "generate_template", _fake_template({"attack": 2, "parry": 2, "lunge": 2, "sincerity": 1}))
    build = gen.build_npc("wave_man", 0, 0.741)
    assert build["foreign_knacks"] == {"lunge": 2}
    assert build["skills"] == {"sincerity": 1}


def test_an_unmappable_skill_or_ability_is_loud(monkeypatch):
    monkeypatch.setattr(gen, "generate_template", _fake_template({"attack": 2, "juggling": 3}))
    with pytest.raises(LookupError, match="juggling"):
        gen.build_npc("wave_man", 0, 0.741)
    monkeypatch.setattr(gen, "generate_template", _fake_template(abilities={"flying": 1}))
    with pytest.raises(LookupError, match="flying"):
        gen.build_npc("wave_man", 0, 0.741)


def test_every_simulator_wave_man_ability_is_mapped():
    from simulation.templates.strategies import WAVE_MAN_ABILITIES
    assert set(WAVE_MAN_ABILITIES) == set(gen._SIM_ABILITY_TO_SHEET)
    from app.game_data import PROFESSION_ABILITIES
    assert set(gen._SIM_ABILITY_TO_SHEET.values()) <= set(PROFESSION_ABILITIES)


# ---------------------------------------------------------------------------
# Returning NPCs
# ---------------------------------------------------------------------------

def test_never_below_holds_every_stat():
    previous = {
        "rings": {"Air": 3, "Fire": 4}, "attack": 4, "parry": 3,
        "skills": {"precepts": 5}, "knacks": {"iaijutsu": 5}, "foreign_knacks": {},
        "profession_abilities": {"wave_man_parry_tn": 2},
    }
    build = {
        "rings": {"Air": 2, "Fire": 5}, "attack": 3, "parry": 4,
        "skills": {"precepts": 4, "tact": 1}, "knacks": {"iaijutsu": 4}, "foreign_knacks": {"lunge": 1},
        "profession_abilities": {"wave_man_parry_tn": 1, "wave_man_weapon_dice": 1},
        "earned_xp": 99,
    }
    out = gen.never_below(previous, build)
    assert out["rings"] == {"Air": 3, "Fire": 5}
    assert (out["attack"], out["parry"]) == (4, 4)
    assert out["skills"] == {"precepts": 5, "tact": 1}
    assert out["knacks"] == {"iaijutsu": 5}
    assert out["foreign_knacks"] == {"lunge": 1}
    assert out["profession_abilities"] == {"wave_man_parry_tn": 2, "wave_man_weapon_dice": 1}
    assert out["earned_xp"] == 99


# ---------------------------------------------------------------------------
# Simulator provenance
# ---------------------------------------------------------------------------

class _Dist:
    def __init__(self, direct_url, version="0.1.0"):
        self._direct_url = direct_url
        self.version = version

    def read_text(self, name):
        return self._direct_url


@pytest.fixture
def fresh_version():
    gen.simulator_version.cache_clear()
    yield
    gen.simulator_version.cache_clear()


def test_version_from_a_github_install(monkeypatch, fresh_version):
    monkeypatch.setattr(importlib.metadata, "distribution",
                        lambda name: _Dist('{"url": "https://github.com/x", "vcs_info": {"commit_id": "abcdef1234567890"}}'))
    assert gen.simulator_version() == "abcdef123456"


def test_version_from_an_editable_checkout(monkeypatch, fresh_version):
    monkeypatch.setattr(importlib.metadata, "distribution",
                        lambda name: _Dist('{"url": "file:///somewhere", "dir_info": {"editable": true}}'))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="0123456789ab\n"))
    assert gen.simulator_version() == "0123456789ab-local"


def test_version_when_git_is_unavailable(monkeypatch, fresh_version):
    monkeypatch.setattr(importlib.metadata, "distribution",
                        lambda name: _Dist('{"url": "file:///somewhere"}', version="0.1.0"))

    def boom(*a, **k):
        raise subprocess.CalledProcessError(128, "git")
    monkeypatch.setattr(subprocess, "run", boom)
    assert gen.simulator_version() == "0.1.0"


def test_version_without_direct_url(monkeypatch, fresh_version):
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: _Dist(None, version="0.2.0"))
    assert gen.simulator_version() == "0.2.0"


def test_version_when_not_installed(monkeypatch, fresh_version):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(importlib.metadata, "distribution", missing)
    assert gen.simulator_version() == "unknown"


def test_version_from_the_deploy_stamp(monkeypatch, fresh_version):
    """A deploy installs the simulator from a copy of its committed HEAD
    (scripts/deploy.sh), which has no git history; the script passes the
    commit in as SIMULATOR_COMMIT."""
    monkeypatch.setenv("SIMULATOR_COMMIT", "3e9fec9095db")
    monkeypatch.setattr(importlib.metadata, "distribution",
                        lambda name: pytest.fail("the stamp wins without asking pip"))
    assert gen.simulator_version() == "3e9fec9095db"


def test_hiruma_scout_takes_the_simulators_counterattack_ranks_as_lunge():
    """The simulator's Hiruma predates the rules' counterattack -> lunge swap.
    Its progression is used as-is, with the counterattack ranks renamed, so
    the NPC reaches the Dan the simulator built rather than sitting at 1st."""
    npc = gen.build_npc("hiruma_scout", 150, 0.6)
    assert npc["school"] == "hiruma_scout"
    assert set(npc["knacks"]) == {"double_attack", "iaijutsu", "lunge"}
    assert "counterattack" not in npc["foreign_knacks"]
    assert min(npc["knacks"].values()) >= 3
