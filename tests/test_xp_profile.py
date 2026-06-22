"""Tests for the combat/non-combat categorization and the NPC XP profile
(app/services/xp.py: combat_skill_names, combat_noncombat_split, xp_profile)."""

import pytest

from app.game_data import ADVANTAGES, XP_PROFILE_BANDS, XP_PROFILE_TIER_BREAK
from app.services.xp import (
    _advantage_is_combat,
    _combat_advantage_labels,
    _profile_band,
    _profile_level,
    calculate_foreign_knack_xp,
    calculate_skill_xp,
    calculate_xp_breakdown,
    combat_noncombat_split,
    combat_skill_names,
    editor_xp_view,
    profile_tier,
    xp_profile,
)
from tests.conftest import make_character_data


class TestCombatSkillNames:
    def test_attack_school_has_no_general_combat_skill(self):
        # Akodo's 3rd Dan keys off Attack, not a general skill.
        assert combat_skill_names("akodo_bushi") == set()

    def test_unknown_school_is_empty(self):
        assert combat_skill_names("not_a_school") == set()

    def test_third_dan_skill_is_combat(self):
        # Kitsuki Magistrate: "X is your investigation skill".
        assert combat_skill_names("kitsuki_magistrate") == {"Investigation"}

    def test_special_ability_skill_is_combat(self):
        # Shosuro Actor: 3rd Dan (Sincerity) plus Special Ability (Acting).
        assert combat_skill_names("shosuro_actor") == {"Acting", "Sincerity"}


class TestAdvantageCategorization:
    def test_combat_advantage_labels_include_lucky(self):
        assert ADVANTAGES["lucky"].name in _combat_advantage_labels()

    def test_named_combat_advantage(self):
        labels = _combat_advantage_labels()
        assert _advantage_is_combat(ADVANTAGES["lucky"].name, labels) is True

    def test_specialization_in_combat_domain(self):
        assert _advantage_is_combat("Specialization (Iaijutsu)", set()) is True

    def test_specialization_in_noncombat_domain(self):
        assert _advantage_is_combat("Specialization (Calligraphy)", set()) is False

    def test_plain_noncombat_advantage(self):
        assert _advantage_is_combat("Charming", set()) is False


class TestCombatNoncombatSplit:
    def test_total_equals_combat_plus_noncombat(self):
        char = make_character_data(skills={"etiquette": 2}, advantages=["lucky"])
        s = combat_noncombat_split(char)
        assert s["total"] == s["combat"] + s["noncombat"]

    def test_rings_match_breakdown(self):
        char = make_character_data(rings={"Air": 3, "Fire": 3, "Earth": 2,
                                          "Water": 3, "Void": 2})
        s = combat_noncombat_split(char)
        assert s["rings"] == calculate_xp_breakdown(char)["rings"]["total"]

    def test_school_combat_skill_counts_as_combat(self):
        # Shosuro Actor: Acting is a combat skill, so its XP is combat.
        base = make_character_data(
            school="shosuro_actor", school_ring_choice="Air",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
        )
        withact = make_character_data(
            school="shosuro_actor", school_ring_choice="Air",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 3},
        )
        d_combat = combat_noncombat_split(withact)["combat"] - combat_noncombat_split(base)["combat"]
        d_non = combat_noncombat_split(withact)["noncombat"] - combat_noncombat_split(base)["noncombat"]
        assert d_combat == calculate_skill_xp({"acting": 3})
        assert d_non == 0

    def test_general_skill_counts_as_noncombat(self):
        # Akodo has no general combat skill, so Etiquette is non-combat.
        base = make_character_data()
        withetq = make_character_data(skills={"etiquette": 2})
        d_combat = combat_noncombat_split(withetq)["combat"] - combat_noncombat_split(base)["combat"]
        d_non = combat_noncombat_split(withetq)["noncombat"] - combat_noncombat_split(base)["noncombat"]
        assert d_combat == 0
        assert d_non == calculate_skill_xp({"etiquette": 2})

    def test_foreign_knacks_count_in_combat_and_knacks(self):
        base = make_character_data()
        withfk = make_character_data(foreign_knacks={"commune": 2})
        cost = calculate_foreign_knack_xp({"commune": 2})
        sb, sf = combat_noncombat_split(base), combat_noncombat_split(withfk)
        assert sf["knacks"] - sb["knacks"] == cost
        assert sf["combat"] - sb["combat"] == cost

    def test_combat_advantage_in_combat_noncombat_advantage_in_noncombat(self):
        base = make_character_data()
        lucky = make_character_data(advantages=["lucky"])
        charming = make_character_data(advantages=["charming"])
        assert (combat_noncombat_split(lucky)["combat"]
                - combat_noncombat_split(base)["combat"]) == ADVANTAGES["lucky"].xp_cost
        assert (combat_noncombat_split(charming)["noncombat"]
                - combat_noncombat_split(base)["noncombat"]) == ADVANTAGES["charming"].xp_cost


class TestProfileLevel:
    def test_at_low_cutoff_is_low(self):
        assert _profile_level(69.0, 69.0, 75.0) == "low"

    def test_just_above_low_is_medium(self):
        assert _profile_level(69.1, 69.0, 75.0) == "medium"

    def test_at_high_cutoff_is_medium(self):
        assert _profile_level(75.0, 69.0, 75.0) == "medium"

    def test_above_high_is_high(self):
        assert _profile_level(75.1, 69.0, 75.0) == "high"


class TestXpProfile:
    def test_unbuilt_character_is_zero_and_low(self):
        # make_character_data spends no XP (free defaults).
        p = xp_profile(make_character_data())
        assert p["total_xp"] == 0
        assert p["combat_pct"] == 0.0
        assert p["noncombat_pct"] == 0.0
        assert p["combat_level"] == "low"
        assert p["rings_level"] == "low"
        assert p["knacks_level"] == "low"

    def test_percentages_match_split(self):
        char = make_character_data(
            rings={"Air": 3, "Fire": 4, "Earth": 3, "Water": 3, "Void": 3},
            knacks={"double_attack": 4, "feint": 3, "iaijutsu": 3},
            attack=3, parry=3, skills={"etiquette": 3}, advantages=["lucky"],
        )
        s = combat_noncombat_split(char)
        p = xp_profile(char)
        assert p["combat_pct"] == round(100.0 * s["combat"] / s["total"], 1)
        assert p["rings_pct"] == round(100.0 * s["rings"] / s["total"], 1)
        assert p["knacks_pct"] == round(100.0 * s["knacks"] / s["total"], 1)
        assert p["noncombat_pct"] == round(100.0 - p["combat_pct"], 1)
        assert p["combat_xp"] == s["combat"]
        assert p["total_xp"] == s["total"]

    def test_levels_follow_bands(self):
        char = make_character_data(
            rings={"Air": 3, "Fire": 4, "Earth": 3, "Water": 3, "Void": 3},
            knacks={"double_attack": 4, "feint": 3, "iaijutsu": 3},
            attack=3, parry=3, skills={"etiquette": 3}, advantages=["lucky"],
        )
        p = xp_profile(char)
        lo, hi = XP_PROFILE_BANDS["combat"]
        expected = ("low" if p["combat_pct"] <= lo
                    else "high" if p["combat_pct"] > hi else "medium")
        assert p["combat_level"] == expected

    def test_editor_xp_view_includes_profile(self):
        char = make_character_data(attack=3)
        view = editor_xp_view(char)
        assert view["profile"] == xp_profile(char)


class TestXpTieredBands:
    def test_profile_tier_boundary(self):
        assert profile_tier(XP_PROFILE_TIER_BREAK) == "developing"      # <= break
        assert profile_tier(XP_PROFILE_TIER_BREAK + 1) == "veteran"
        assert profile_tier(0) == "developing"

    def test_combat_band_is_not_tiered(self):
        # combat keeps one band regardless of tier
        assert _profile_band("combat", "developing") == _profile_band("combat", "veteran")
        assert _profile_band("combat", "veteran") == XP_PROFILE_BANDS["combat"]

    def test_rings_and_knacks_bands_are_tiered(self):
        assert _profile_band("rings", "developing") != _profile_band("rings", "veteran")
        assert _profile_band("knacks", "developing") != _profile_band("knacks", "veteran")
        assert _profile_band("rings", "veteran") == XP_PROFILE_BANDS["rings"]["veteran"]

    def test_same_rings_share_reads_differently_by_tier(self):
        # rings% rises with XP, so a share that is "high" for a developing
        # character is merely "low/medium" for a veteran.
        share = 33.0
        dev = _profile_level(share, *_profile_band("rings", "developing"))
        vet = _profile_level(share, *_profile_band("rings", "veteran"))
        assert dev == "high"
        assert vet == "low"

    def test_profile_reports_tier_and_uses_it(self):
        char = make_character_data(
            rings={"Air": 3, "Fire": 4, "Earth": 3, "Water": 3, "Void": 3},
            knacks={"double_attack": 4, "feint": 3, "iaijutsu": 3},
            attack=3, parry=3, skills={"etiquette": 3}, advantages=["lucky"],
        )
        p = xp_profile(char)
        assert p["tier"] == profile_tier(p["total_xp"])
        assert p["rings_level"] == _profile_level(
            p["rings_pct"], *_profile_band("rings", p["tier"]))
