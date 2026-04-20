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
    calculate_xp_breakdown,
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


class TestMantisFourthDanRingRaise:
    """Mantis Wave-Treader picks its school ring from the "Any" option.
    The 4th Dan technique raises the chosen ring's floor to 4 (free +1) and
    discounts every subsequent raise of that ring by 5 XP. These tests pin
    the behaviour across all five possible school-ring choices.
    """

    @pytest.mark.parametrize("school_ring", ["Air", "Fire", "Earth", "Water", "Void"])
    def test_dan_4_auto_raises_school_ring_to_4_for_free(self, school_ring):
        """The auto-raise at Dan 4 is free, so sitting at rank 4 costs 0."""
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}
        # School ring starts at 3 (free), auto-raises to 4 at Dan 4 (free).
        rings[school_ring] = 4
        assert calculate_ring_xp(rings, school_ring=school_ring, dan=4) == 0

    @pytest.mark.parametrize("school_ring", ["Air", "Fire", "Earth", "Water", "Void"])
    def test_dan_4_discounts_school_ring_above_4(self, school_ring):
        """Raising the school ring from 4 -> 5 at Dan 4 costs 5 less (20 -> 15)."""
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}
        rings[school_ring] = 5
        # Free 3->4, then 4->5 normally 25 - 5 discount = 20.
        assert calculate_ring_xp(rings, school_ring=school_ring, dan=4) == 20

    @pytest.mark.parametrize("school_ring", ["Air", "Fire", "Earth", "Water", "Void"])
    def test_dan_4_school_ring_to_5_from_6(self, school_ring):
        """Going up to 6 (4th Dan's expanded cap) stacks the per-raise discount."""
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}
        rings[school_ring] = 6
        # Free 3->4, then 4->5 (25-5=20), then 5->6 (30-5=25) = 45 total.
        assert calculate_ring_xp(rings, school_ring=school_ring, dan=4) == 45

    @pytest.mark.parametrize("school_ring", ["Air", "Fire", "Earth", "Water", "Void"])
    def test_dan_3_does_not_discount(self, school_ring):
        """At Dan 3 the school ring still starts at 3 but there's no discount."""
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}
        rings[school_ring] = 4
        # Dan 3 -> 3->4 costs 20 (no discount).
        assert calculate_ring_xp(rings, school_ring=school_ring, dan=3) == 20

    @pytest.mark.parametrize("school_ring", ["Air", "Fire", "Earth", "Water", "Void"])
    def test_dan_4_does_not_discount_non_school_rings(self, school_ring):
        """The Dan 4 discount applies ONLY to the school ring - any other ring
        costs the normal 5 * (new_rank) per raise."""
        # Raise a non-school ring from 2 -> 3.
        non_school = next(r for r in ["Air", "Fire", "Earth", "Water", "Void"] if r != school_ring)
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}
        rings[school_ring] = 4  # school ring auto-raised (free).
        rings[non_school] = 3   # non-school ring 2->3 = 15 XP.
        assert calculate_ring_xp(rings, school_ring=school_ring, dan=4) == 15


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


# ---------------------------------------------------------------------------
# Per-item breakdown for the expandable XP Summary (calculate_xp_breakdown)
# ---------------------------------------------------------------------------


class TestDetailFieldValidation:
    """Advantages/disadvantages with ADVANTAGE_DETAIL_FIELDS entries require
    a non-empty text description."""

    def test_missing_detail_text_produces_error(self):
        data = make_character_data(advantages=["good_reputation"])
        errors = validate_character(data)
        assert any("Good Reputation" in e and "requires" in e for e in errors)

    def test_filled_detail_text_no_error(self):
        data = make_character_data(
            advantages=["good_reputation"],
            advantage_details={"good_reputation": {"text": "brave warrior"}},
        )
        errors = validate_character(data)
        assert not any("Good Reputation" in e for e in errors)

    def test_disadvantage_missing_detail_text(self):
        data = make_character_data(disadvantages=["driven"])
        errors = validate_character(data)
        assert any("Driven" in e and "requires" in e for e in errors)

    def test_disadvantage_filled_detail_text(self):
        data = make_character_data(
            disadvantages=["driven"],
            advantage_details={"driven": {"text": "become shogun"}},
        )
        errors = validate_character(data)
        assert not any("Driven" in e for e in errors)

    def test_advantage_without_detail_field_no_error(self):
        """Advantages without an ADVANTAGE_DETAIL_FIELDS entry should not
        trigger a 'requires description' error."""
        data = make_character_data(advantages=["lucky"])
        errors = validate_character(data)
        assert not any("requires" in e for e in errors)


class TestXpBreakdown:
    """The rich per-item breakdown used by the sheet's expandable XP Summary."""

    def test_default_character_has_only_wasp_note(self):
        """A fresh character has the free school-ring raise as a 0 XP row,
        empty per-category rows elsewhere, and the HRR Wasp note."""
        breakdown = calculate_xp_breakdown(make_character_data())
        # Default character has Water=3 (school ring) -> free 2->3 raise shown.
        assert breakdown["rings"]["rows"] == [
            {"xp": 0, "label": "Water", "from_val": 2, "to_val": 3},
        ]
        assert breakdown["rings"]["total"] == 0
        assert breakdown["school_knacks"]["rows"] == []
        assert breakdown["skills"]["subsections"][0]["rows"] == []
        assert breakdown["skills"]["subsections"][1]["rows"] == []
        assert breakdown["combat_skills"]["rows"] == []
        assert breakdown["advantages"]["rows"] == []
        assert breakdown["disadvantages"]["rows"] == []
        # HRR has the note even when totals are zero
        hrr_rows = breakdown["honor_rank_recognition"]["rows"]
        assert len(hrr_rows) == 1
        assert hrr_rows[0]["note"] is True
        assert "7.5 Rank" in hrr_rows[0]["label"]
        assert breakdown["honor_rank_recognition"]["total"] == 0
        assert breakdown["grand_total"] == 0

    def test_section_labels(self):
        """Display labels are user-facing and use the new naming."""
        breakdown = calculate_xp_breakdown(make_character_data())
        assert breakdown["rings"]["label"] == "Rings"
        assert breakdown["school_knacks"]["label"] == "School Knacks"
        assert breakdown["skills"]["label"] == "Skills"
        assert breakdown["combat_skills"]["label"] == "Attack / Parry"
        assert breakdown["advantages"]["label"] == "Advantages"
        assert breakdown["honor_rank_recognition"]["label"] == "Honor / Rank / Recognition"
        assert breakdown["disadvantages"]["label"] == "Disadvantages"

    def test_ring_rows_emit_each_raise(self):
        data = make_character_data(
            rings={"Air": 4, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
        )
        rows = calculate_xp_breakdown(data)["rings"]["rows"]
        # school_ring=Water, so Water's 2->3 is a free 0 XP row and only its
        # 3->4 raise costs. Sorted by (from_val, label):
        #   (2, "Air"), (2, "Water"), (3, "Air"), (3, "Water").
        assert [(r["label"], r["from_val"], r["to_val"], r["xp"]) for r in rows] == [
            ("Air", 2, 3, 15),
            ("Water", 2, 3, 0),
            ("Air", 3, 4, 20),
            ("Water", 3, 4, 20),
        ]

    def test_school_knack_rows(self):
        data = make_character_data(
            knacks={"double_attack": 3, "feint": 1, "iaijutsu": 1},
        )
        rows = calculate_xp_breakdown(data)["school_knacks"]["rows"]
        # Double Attack: 1->2 (4), 2->3 (6). Other knacks at rank 1 produce nothing.
        assert [(r["label"], r["from_val"], r["to_val"], r["xp"]) for r in rows] == [
            ("Double Attack", 1, 2, 4),
            ("Double Attack", 2, 3, 6),
        ]

    def test_skill_rows_split_basic_advanced(self):
        data = make_character_data(
            skills={"bragging": 2, "acting": 1},  # Bragging is basic, Acting is advanced
        )
        skills = calculate_xp_breakdown(data)["skills"]
        assert skills["subsections"][0]["label"] == "Basic Skills"
        assert skills["subsections"][1]["label"] == "Advanced Skills"
        basic = skills["subsections"][0]["rows"]
        advanced = skills["subsections"][1]["rows"]
        assert [(r["label"], r["from_val"], r["to_val"], r["xp"]) for r in basic] == [
            ("Bragging", 0, 1, 2),
            ("Bragging", 1, 2, 2),
        ]
        assert [(r["label"], r["from_val"], r["to_val"], r["xp"]) for r in advanced] == [
            ("Acting", 0, 1, 4),
        ]
        assert skills["total"] == 8  # 2+2+4

    def test_combat_skill_rows_interleaved_by_from_rank(self):
        """Sort is by (from_val, label) so Attack 1->2 comes before Parry 1->2,
        then Attack 2->3 before Parry 2->3, etc."""
        data = make_character_data(attack=3, parry=4)
        rows = calculate_xp_breakdown(data)["combat_skills"]["rows"]
        assert [(r["label"], r["from_val"]) for r in rows] == [
            ("Attack", 1),
            ("Parry", 1),
            ("Attack", 2),
            ("Parry", 2),
            ("Parry", 3),
        ]

    def test_advantage_rows_merge_campaign(self):
        data = make_character_data(
            advantages=["lucky"],
            campaign_advantages=["streetwise"],
        )
        section = calculate_xp_breakdown(data)["advantages"]
        labels = [r["label"] for r in section["rows"]]
        assert "Lucky" in labels
        assert "Streetwise" in labels
        # Total covers both
        assert section["total"] == sum(r["xp"] for r in section["rows"])

    def test_disadvantage_rows_merge_campaign(self):
        data = make_character_data(
            disadvantages=["proud"],
            campaign_disadvantages=["crane_indebted"],
        )
        section = calculate_xp_breakdown(data)["disadvantages"]
        labels = [r["label"] for r in section["rows"]]
        assert "Proud" in labels
        assert any("Crane" in lbl or "Indebted" in lbl for lbl in labels)
        assert section["total"] < 0  # disadvantages give XP back

    def test_hrr_honor_row(self):
        data = make_character_data(honor=2.5)
        rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
        non_note = [r for r in rows if not r.get("note")]
        assert len(non_note) == 1
        assert non_note[0]["label"] == "Honor"
        assert non_note[0]["from_val"] == 1.0
        assert non_note[0]["to_val"] == 2.5
        assert non_note[0]["xp"] == 3  # (2.5-1.0)/0.5 = 3 steps

    def test_hrr_rank_row_when_unlocked(self):
        data = make_character_data(rank=8.5, rank_locked=False)
        rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
        rank_rows = [r for r in rows if not r.get("note") and r["label"] == "Rank"]
        assert len(rank_rows) == 1
        assert rank_rows[0]["from_val"] == 7.5
        assert rank_rows[0]["to_val"] == 8.5
        assert rank_rows[0]["xp"] == 2  # (8.5-7.5)/0.5 = 2 steps

    def test_hrr_rank_locked_emits_no_rank_row(self):
        data = make_character_data(rank=8.5, rank_locked=True)
        rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
        rank_rows = [r for r in rows if not r.get("note") and r["label"] == "Rank"]
        assert rank_rows == []

    def test_hrr_recognition_row(self):
        data = make_character_data(recognition=8.5)
        rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
        rec_rows = [r for r in rows if not r.get("note") and r["label"] == "Recognition"]
        assert len(rec_rows) == 1
        assert rec_rows[0]["from_val"] == 7.5
        assert rec_rows[0]["to_val"] == 8.5
        assert rec_rows[0]["xp"] == 1

    def test_hrr_recognition_halved(self):
        data = make_character_data(recognition=3.5, recognition_halved=True)
        rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
        # Should have a "Recognition halved" row with -3 XP and the Wasp note
        halved_rows = [r for r in rows if r.get("label") == "Recognition halved"]
        assert len(halved_rows) == 1
        assert halved_rows[0]["xp"] == -3

    def test_hrr_recognition_halved_then_raised(self):
        data = make_character_data(recognition=5.5, recognition_halved=True)
        rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
        # halved -3 row, plus a Recognition raise row from 3.5 -> 5.5 (+2 XP)
        labels = [r.get("label") for r in rows]
        assert "Recognition halved" in labels
        rec_raise = [r for r in rows if r.get("label") == "Recognition" and r.get("from_val") is not None]
        assert len(rec_raise) == 1
        assert rec_raise[0]["xp"] == 2

    def test_wasp_note_always_present_in_hrr(self):
        for data in [
            make_character_data(),                              # zero everything
            make_character_data(honor=3.0),                     # honor only
            make_character_data(rank=8.5, rank_locked=False),   # rank only
            make_character_data(recognition=10.0),              # recognition only
        ]:
            rows = calculate_xp_breakdown(data)["honor_rank_recognition"]["rows"]
            note_rows = [r for r in rows if r.get("note")]
            assert len(note_rows) == 1
            assert "Wasp" in note_rows[0]["label"]

    def test_grand_total_invariant(self):
        """grand_total must equal calculate_total_xp(...)['total'] for any character."""
        cases = [
            make_character_data(),
            make_character_data(
                rings={"Air": 4, "Fire": 3, "Earth": 2, "Water": 4, "Void": 2},
                skills={"bragging": 3},
                knacks={"double_attack": 2, "feint": 1, "iaijutsu": 3},
                attack=3, parry=2,
                advantages=["lucky"],
                disadvantages=["proud"],
                honor=2.0,
                recognition=8.5,
            ),
            make_character_data(
                campaign_advantages=["streetwise"],
                campaign_disadvantages=["crane_indebted"],
            ),
            make_character_data(
                rank=8.5, rank_locked=False,
                recognition=3.5, recognition_halved=True,
            ),
        ]
        for data in cases:
            breakdown = calculate_xp_breakdown(data)
            totals = calculate_total_xp(data)
            assert breakdown["grand_total"] == totals["total"], (
                f"grand_total mismatch for {data}: "
                f"breakdown={breakdown['grand_total']} totals={totals['total']}"
            )

    def test_section_total_matches_row_sum(self):
        """Each non-skills section total equals sum of its rows' xp."""
        data = make_character_data(
            rings={"Air": 4, "Fire": 2, "Earth": 2, "Water": 5, "Void": 2},
            knacks={"double_attack": 4, "feint": 1, "iaijutsu": 1},
            attack=4, parry=3,
            advantages=["lucky", "fierce"],
            disadvantages=["proud"],
        )
        breakdown = calculate_xp_breakdown(data)
        for key in ("rings", "school_knacks", "combat_skills", "advantages", "disadvantages"):
            section = breakdown[key]
            assert section["total"] == sum(r["xp"] for r in section["rows"]), (
                f"{key} total mismatch"
            )

    def test_skills_total_matches_subsection_sums(self):
        data = make_character_data(
            skills={"bragging": 2, "spellcraft": 3},  # basic + advanced
        )
        skills = calculate_xp_breakdown(data)["skills"]
        basic_sum = sum(r["xp"] for r in skills["subsections"][0]["rows"])
        advanced_sum = sum(r["xp"] for r in skills["subsections"][1]["rows"])
        assert skills["total"] == basic_sum + advanced_sum

    def test_skill_rows_use_display_names(self):
        """Skill row labels use the human-readable name from SKILLS, not the id."""
        data = make_character_data(skills={"bragging": 1})
        breakdown = calculate_xp_breakdown(data)
        basic_rows = breakdown["skills"]["subsections"][0]["rows"]
        assert basic_rows[0]["label"] == "Bragging"

    def test_unknown_skill_falls_back_to_id_label(self):
        """A skill id not in SKILLS still appears (treated as advanced) with its id as label."""
        data = make_character_data(skills={"nonexistent_skill": 2})
        breakdown = calculate_xp_breakdown(data)
        advanced_rows = breakdown["skills"]["subsections"][1]["rows"]
        labels = [r["label"] for r in advanced_rows]
        assert "nonexistent_skill" in labels

    def test_unknown_knack_falls_back_to_id_label(self):
        data = make_character_data(knacks={"made_up_knack": 2})
        breakdown = calculate_xp_breakdown(data)
        rows = breakdown["school_knacks"]["rows"]
        assert any(r["label"] == "made_up_knack" for r in rows)

    def test_4th_dan_school_ring_discount(self):
        """4th Dan: school-ring 2->3 free (base), 3->4 free (4th Dan), and the
        remaining raises get a -5 XP discount."""
        data = make_character_data(
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},  # min knack=4 -> dan 4
            school_ring_choice="Water",
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 5, "Void": 2},
        )
        breakdown = calculate_xp_breakdown(data)
        rings_rows = breakdown["rings"]["rows"]
        water_rows = [r for r in rings_rows if r["label"] == "Water"]
        assert [(r["from_val"], r["to_val"], r["xp"]) for r in water_rows] == [
            (2, 3, 0),    # free school-ring raise
            (3, 4, 0),    # free 4th Dan raise
            (4, 5, 20),   # 25 - 5 discount
        ]

    def test_unknown_advantage_ignored(self):
        data = make_character_data(advantages=["nonexistent_advantage"])
        breakdown = calculate_xp_breakdown(data)
        assert breakdown["advantages"]["rows"] == []

    def test_unknown_disadvantage_ignored(self):
        data = make_character_data(disadvantages=["nonexistent_disadvantage"])
        breakdown = calculate_xp_breakdown(data)
        assert breakdown["disadvantages"]["rows"] == []

    def test_unknown_campaign_advantage_ignored(self):
        data = make_character_data(campaign_advantages=["nonexistent"])
        breakdown = calculate_xp_breakdown(data)
        assert breakdown["advantages"]["rows"] == []

    def test_unknown_campaign_disadvantage_ignored(self):
        data = make_character_data(campaign_disadvantages=["nonexistent"])
        breakdown = calculate_xp_breakdown(data)
        assert breakdown["disadvantages"]["rows"] == []

    def test_zero_rank_skill_skipped(self):
        """Skills with rank 0 or below produce no rows."""
        data = make_character_data(skills={"bragging": 0})
        breakdown = calculate_xp_breakdown(data)
        assert breakdown["skills"]["subsections"][0]["rows"] == []
        assert breakdown["skills"]["subsections"][1]["rows"] == []
