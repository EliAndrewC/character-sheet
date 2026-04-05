"""Tests for effective Honor/Rank/Recognition computation with advantage modifiers."""

from app.services.status import compute_effective_status, EffectiveStatus
from tests.conftest import make_character_data


class TestBaseStatus:
    def test_no_advantages_no_modifiers(self):
        data = make_character_data(rank=2.0, recognition=2.0, honor=2.0)
        status = compute_effective_status(data)
        assert status.rank == 2.0
        assert status.recognition == 2.0
        assert status.rank_modifiers == []

    def test_stipend_base(self):
        data = make_character_data(rank=3.0)
        status = compute_effective_status(data)
        assert status.stipend == 9.0  # 3.0 ** 2


class TestGoodReputation:
    def test_recognition_plus_1(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, advantages=["good_reputation"]
        )
        status = compute_effective_status(data)
        assert any(
            m["context"] == "identification" and m["field"] == "recognition"
            for m in status.recognition_modifiers
        )

    def test_rank_plus_2_with_familiar(self):
        data = make_character_data(rank=2.0, advantages=["good_reputation"])
        status = compute_effective_status(data)
        assert any(
            m["context"] == "those familiar with your reputation"
            and m["value"] == 2.0
            for m in status.rank_modifiers
        )


class TestImperialFavor:
    def test_rank_plus_3_imperial_family(self):
        data = make_character_data(rank=2.0, advantages=["imperial_favor"])
        status = compute_effective_status(data)
        assert any(
            "Imperial family" in m["context"] and m["value"] == 3.0
            for m in status.rank_modifiers
        )

    def test_recognition_plus_3_imperial_family(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, advantages=["imperial_favor"]
        )
        status = compute_effective_status(data)
        assert any(
            "Imperial family" in m["context"] and m["value"] == 3.0
            for m in status.recognition_modifiers
        )

    def test_rank_plus_1_imperial_post(self):
        data = make_character_data(rank=2.0, advantages=["imperial_favor"])
        status = compute_effective_status(data)
        assert any(
            "Imperial post" in m["context"] and m["value"] == 1.0
            for m in status.rank_modifiers
        )


class TestBadReputation:
    def test_recognition_plus_1_identification(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, disadvantages=["bad_reputation"]
        )
        status = compute_effective_status(data)
        assert any(
            m["context"] == "identification" and m["field"] == "recognition"
            for m in status.recognition_modifiers
        )

    def test_rank_minus_1_5_with_aware(self):
        data = make_character_data(rank=2.0, disadvantages=["bad_reputation"])
        status = compute_effective_status(data)
        assert any(
            m["value"] == -1.5 for m in status.rank_modifiers
        )


class TestWealthy:
    def test_stipend_rank_plus_3(self):
        data = make_character_data(rank=2.0, advantages=["wealthy"])
        status = compute_effective_status(data)
        # Stipend uses rank+3 = 5.0, so 5.0^2 = 25.0
        assert status.stipend == 25.0


class TestPoor:
    def test_stipend_rank_halved(self):
        data = make_character_data(rank=4.0, disadvantages=["poor"])
        status = compute_effective_status(data)
        # Stipend uses rank/2 = 2.0, so 2.0^2 = 4.0
        assert status.stipend == 4.0


class TestCombined:
    def test_multiple_rank_modifiers(self):
        data = make_character_data(
            rank=2.0,
            advantages=["good_reputation", "imperial_favor"],
        )
        status = compute_effective_status(data)
        # Should have modifiers from both
        assert len(status.rank_modifiers) >= 3  # good_rep(+2) + imperial(+3, +1)


class TestSchoolRingMinimum:
    def test_school_ring_min_3_in_validation(self):
        """School ring cannot be lowered below 3."""
        from app.services.xp import validate_character
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            school_ring_choice="Water",
        )
        errors = validate_character(data)
        assert any("school ring" in e.lower() or ("Water" in e and "below" in e) for e in errors)


class TestXpBudgetDisplay:
    def test_disadvantage_xp_separate(self):
        """Total XP breakdown should separate disadvantage XP from budget."""
        from app.services.xp import calculate_total_xp
        data = make_character_data(
            disadvantages=["proud", "vain"],  # 2 + 2 = 4 XP
            skills={"bragging": 2},  # 4 XP
        )
        result = calculate_total_xp(data)
        assert result["disadvantages"] == -4
        # The "spent" (before disadvantages) should be computable
        spent_before_dis = result["total"] - result["disadvantages"]
        assert spent_before_dis == 4  # just the skill cost
