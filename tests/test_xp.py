"""Tests for the XP calculation engine."""

import pytest

from app.services.xp import (
    calculate_advantage_xp,
    calculate_disadvantage_xp,
    calculate_honor_xp,
    calculate_knack_xp,
    calculate_rank_xp,
    calculate_recognition_xp,
    calculate_ring_xp,
    calculate_skill_xp,
    calculate_total_xp,
    calculate_available_xp,
    validate_character,
)
from tests.conftest import make_character_data


class TestRingXP:
    def test_default_rings_cost_nothing(self):
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}
        assert calculate_ring_xp(rings, school_ring="Water") == 0

    def test_non_school_ring_raised(self):
        rings = {"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}
        # Air 2->3 costs 15
        assert calculate_ring_xp(rings, school_ring="Water") == 15

    def test_school_ring_raised(self):
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2}
        # Water 3->4 costs 20
        assert calculate_ring_xp(rings, school_ring="Water") == 20

    def test_multiple_rings_raised(self):
        rings = {"Air": 3, "Fire": 3, "Earth": 2, "Water": 4, "Void": 2}
        # Air 2->3 = 15, Fire 2->3 = 15, Water 3->4 = 20
        assert calculate_ring_xp(rings, school_ring="Water") == 50

    def test_ring_raised_to_5(self):
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 5, "Void": 2}
        # Water 3->4 = 20, 4->5 = 25
        assert calculate_ring_xp(rings, school_ring="Water") == 45

    def test_non_school_ring_to_5(self):
        rings = {"Air": 5, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}
        # Air 2->3=15, 3->4=20, 4->5=25
        assert calculate_ring_xp(rings, school_ring="Water") == 60

    def test_empty_rings(self):
        assert calculate_ring_xp({}, school_ring="Water") == 0


class TestSkillXP:
    def test_no_skills(self):
        assert calculate_skill_xp({}) == 0

    def test_single_basic_skill(self):
        # Bragging is basic. Rank 1 costs 2.
        assert calculate_skill_xp({"bragging": 1}) == 2

    def test_basic_skill_to_3(self):
        # 2 + 2 + 3 = 7
        assert calculate_skill_xp({"precepts": 3}) == 7

    def test_single_advanced_skill(self):
        # Acting is advanced. Rank 1 costs 4.
        assert calculate_skill_xp({"acting": 1}) == 4

    def test_advanced_skill_to_3(self):
        # 4 + 4 + 6 = 14
        assert calculate_skill_xp({"history": 3}) == 14

    def test_multiple_skills(self):
        skills = {"bragging": 2, "precepts": 1, "commerce": 1}
        # bragging: 2+2=4, precepts: 2, commerce(adv): 4
        assert calculate_skill_xp(skills) == 10

    def test_zero_rank_skill_ignored(self):
        assert calculate_skill_xp({"bragging": 0}) == 0

    def test_unknown_skill_treated_as_advanced(self):
        # Unknown skill id defaults to advanced cost table
        assert calculate_skill_xp({"made_up_skill": 1}) == 4


class TestKnackXP:
    def test_all_at_rank_1_free(self):
        knacks = {"double_attack": 1, "feint": 1, "iaijutsu": 1}
        assert calculate_knack_xp(knacks) == 0

    def test_one_raised_to_2(self):
        knacks = {"double_attack": 2, "feint": 1, "iaijutsu": 1}
        # Rank 1->2 costs 4 (advanced table)
        assert calculate_knack_xp(knacks) == 4

    def test_one_raised_to_3(self):
        knacks = {"double_attack": 3, "feint": 1, "iaijutsu": 1}
        # 1->2=4, 2->3=6 => 10
        assert calculate_knack_xp(knacks) == 10

    def test_one_raised_to_5(self):
        knacks = {"double_attack": 5, "feint": 1, "iaijutsu": 1}
        # 4 + 6 + 8 + 10 = 28
        assert calculate_knack_xp(knacks) == 28

    def test_all_raised(self):
        knacks = {"double_attack": 2, "feint": 2, "iaijutsu": 2}
        # 3 knacks each 4 XP = 12
        assert calculate_knack_xp(knacks) == 12


class TestHonorXP:
    def test_default_honor_free(self):
        assert calculate_honor_xp(1.0) == 0

    def test_honor_1_5(self):
        assert calculate_honor_xp(1.5) == 1

    def test_honor_2_0(self):
        assert calculate_honor_xp(2.0) == 2

    def test_honor_5_0(self):
        # (5.0 - 1.0) / 0.5 = 8
        assert calculate_honor_xp(5.0) == 8

    def test_honor_below_start(self):
        assert calculate_honor_xp(0.5) == 0


class TestRankXP:
    def test_default_rank_free(self):
        assert calculate_rank_xp(1.0) == 0

    def test_rank_2_0(self):
        assert calculate_rank_xp(2.0) == 2

    def test_custom_campaign_default(self):
        # If campaign starts at 2.0, raising to 3.0 costs 2
        assert calculate_rank_xp(3.0, campaign_default=2.0) == 2

    def test_rank_below_default(self):
        assert calculate_rank_xp(0.5) == 0


class TestRecognitionXP:
    def test_recognition_at_start_free(self):
        assert calculate_recognition_xp(7.5, rank=7.5) == 0

    def test_recognition_above_start(self):
        # 1 XP per 1.0 above 7.5
        assert calculate_recognition_xp(8.5, rank=7.5) == 1

    def test_recognition_halved_gives_xp(self):
        # Halved base is 3.5, at 3.5 -> just the -3 bonus
        assert calculate_recognition_xp(3.5, rank=7.5, halved=True) == -3

    def test_recognition_halved_raised_above_base(self):
        # Halved base is 3.5, raised to 5.5 -> -3 + round((5.5 - 3.5) * 1) = -3 + 2 = -1
        assert calculate_recognition_xp(5.5, rank=7.5, halved=True) == -1

    def test_recognition_below_start_no_cost(self):
        assert calculate_recognition_xp(5.0, rank=7.5) == 0


class TestAdvantageXP:
    def test_no_advantages(self):
        assert calculate_advantage_xp([]) == 0

    def test_single_advantage(self):
        assert calculate_advantage_xp(["fierce"]) == 2

    def test_multiple_advantages(self):
        assert calculate_advantage_xp(["lucky", "fierce"]) == 7  # 5 + 2

    def test_unknown_advantage_ignored(self):
        assert calculate_advantage_xp(["nonexistent"]) == 0


class TestDisadvantageXP:
    def test_no_disadvantages(self):
        assert calculate_disadvantage_xp([]) == 0

    def test_single_disadvantage(self):
        # Proud gives 2 XP, returned as -2
        assert calculate_disadvantage_xp(["proud"]) == -2

    def test_multiple_disadvantages(self):
        assert calculate_disadvantage_xp(["proud", "vain"]) == -4  # -(2+2)

    def test_unknown_disadvantage_ignored(self):
        assert calculate_disadvantage_xp(["nonexistent"]) == 0


class TestTotalXP:
    def test_bare_minimum_character(self):
        data = make_character_data()
        result = calculate_total_xp(data)
        # All defaults, nothing raised above free values
        assert result["rings"] == 0
        assert result["skills"] == 0
        assert result["knacks"] == 0
        assert result["honor"] == 0
        assert result["rank"] == 0
        assert result["recognition"] == 0
        assert result["advantages"] == 0
        assert result["disadvantages"] == 0
        assert result["total"] == 0

    def test_character_with_investments(self):
        data = make_character_data(
            rings={"Air": 2, "Fire": 3, "Earth": 2, "Water": 3, "Void": 2},
            skills={"precepts": 3, "bragging": 1},
            knacks={"double_attack": 1, "feint": 2, "iaijutsu": 1},
            advantages=["fierce"],
            disadvantages=["proud", "vain"],
            honor=2.0,
        )
        result = calculate_total_xp(data)
        assert result["rings"] == 15     # Fire 2->3
        assert result["skills"] == 9     # precepts 7 + bragging 2
        assert result["knacks"] == 4     # feint 1->2
        assert result["honor"] == 2      # 1.0->2.0
        assert result["advantages"] == 2  # fierce
        assert result["disadvantages"] == -4  # proud + vain
        assert result["total"] == 28

    def test_disadvantages_reduce_total(self):
        base = make_character_data()
        with_dis = make_character_data(disadvantages=["discordant"])  # 12 XP
        base_total = calculate_total_xp(base)["total"]
        dis_total = calculate_total_xp(with_dis)["total"]
        assert dis_total == base_total - 12


class TestAvailableXP:
    def test_default(self):
        assert calculate_available_xp() == 150

    def test_with_earned(self):
        assert calculate_available_xp(earned_xp=30) == 180

    def test_custom_starting(self):
        assert calculate_available_xp(starting_xp=200, earned_xp=10) == 210


class TestValidation:
    def test_valid_minimal_character(self):
        data = make_character_data()
        assert validate_character(data) == []

    def test_ring_too_high(self):
        data = make_character_data(
            rings={"Air": 6, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}
        )
        errors = validate_character(data)
        assert any("Air" in e and "exceeds" in e for e in errors)

    def test_school_ring_can_reach_6(self):
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 6, "Void": 2},
            starting_xp=300,
        )
        errors = validate_character(data)
        assert not any("Water" in e and "exceeds" in e for e in errors)

    def test_skill_too_high(self):
        data = make_character_data(skills={"bragging": 6})
        errors = validate_character(data)
        assert any("bragging" in e and "exceeds" in e for e in errors)

    def test_knack_below_1(self):
        data = make_character_data(
            knacks={"double_attack": 0, "feint": 1, "iaijutsu": 1}
        )
        errors = validate_character(data)
        assert any("double_attack" in e and "at least 1" in e for e in errors)

    def test_honor_too_high(self):
        data = make_character_data(honor=5.5)
        errors = validate_character(data)
        assert any("Honor" in e and "exceeds" in e for e in errors)

    def test_recognition_too_high(self):
        data = make_character_data(rank=7.5, recognition=12.0)
        errors = validate_character(data)
        assert any("Recognition" in e and "exceeds" in e for e in errors)

    def test_xp_over_budget(self):
        data = make_character_data(
            rings={"Air": 5, "Fire": 5, "Earth": 5, "Water": 5, "Void": 5},
            starting_xp=10,
        )
        errors = validate_character(data)
        assert any("exceeds available" in e for e in errors)

    def test_wrong_knacks_for_school(self):
        data = make_character_data(
            knacks={"counterattack": 1, "feint": 1, "iaijutsu": 1}
        )
        errors = validate_character(data)
        assert any("Missing" in e or "Unknown" in e for e in errors)

    def test_recognition_halved_valid(self):
        data = make_character_data(
            recognition=3.5,
            recognition_halved=True,
        )
        errors = validate_character(data)
        assert not any("Recognition" in e for e in errors)

    def test_ring_below_minimum(self):
        data = make_character_data(
            rings={"Air": 1, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}
        )
        errors = validate_character(data)
        assert any("Air" in e and "below minimum" in e for e in errors)

    def test_skill_negative_rank(self):
        data = make_character_data(skills={"bragging": -1})
        errors = validate_character(data)
        assert any("bragging" in e and "negative" in e for e in errors)

    def test_knack_above_max(self):
        data = make_character_data(
            knacks={"double_attack": 6, "feint": 1, "iaijutsu": 1}
        )
        errors = validate_character(data)
        assert any("double_attack" in e and "exceeds" in e for e in errors)

    def test_honor_below_minimum(self):
        data = make_character_data(honor=0.5)
        errors = validate_character(data)
        assert any("Honor" in e and "below minimum" in e for e in errors)

    def test_recognition_below_minimum_not_halved(self):
        data = make_character_data(rank=7.5, recognition=5.0, recognition_halved=False)
        errors = validate_character(data)
        assert any("Recognition" in e and "below minimum" in e for e in errors)
