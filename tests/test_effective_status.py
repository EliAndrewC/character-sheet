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
        data = make_character_data()
        status = compute_effective_status(data)
        assert status.stipend == 16  # campaign base rank 4 -> 4^2

    def test_stipend_ignores_actual_rank(self):
        data = make_character_data(rank=7.5)
        status = compute_effective_status(data)
        assert status.stipend == 16  # still 4^2, actual rank doesn't matter


class TestGMAwardedReputation:
    def test_gm_good_reputation_adds_rank_and_recognition(self):
        """A GM-awarded Good Reputation in rank_recognition_awards adds the
        same modifiers as the checkbox version, with the source text."""
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "good_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "heroism at White Stag"},
        ]
        status = compute_effective_status(data)
        assert any(
            m["value"] == 2.0 and "heroism at White Stag" in m["source"]
            for m in status.rank_modifiers
        )
        assert any(
            m["value"] == 1.0 and "heroism at White Stag" in m["source"]
            for m in status.recognition_modifiers
        )

    def test_gm_bad_reputation_adds_rank_and_recognition(self):
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "bad_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "cowardice at the bridge"},
        ]
        status = compute_effective_status(data)
        assert any(
            m["value"] == -1.5 and "cowardice" in m["source"]
            for m in status.rank_modifiers
        )

    def test_multiple_gm_reputations_stack(self):
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "good_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "valor"},
            {"id": "a2", "type": "good_reputation", "rank_delta": 0,
             "recognition_delta": 0, "source": "diplomacy"},
        ]
        status = compute_effective_status(data)
        good_rank = [m for m in status.rank_modifiers if "Good Reputation" in m["source"]]
        assert len(good_rank) == 2

    def test_numeric_award_does_not_add_reputation_modifier(self):
        data = make_character_data()
        data["rank_recognition_awards"] = [
            {"id": "a1", "type": "rank_recognition", "rank_delta": 1.0,
             "recognition_delta": 0.5, "source": "promotion"},
        ]
        status = compute_effective_status(data)
        assert not any("promotion" in m.get("source", "") for m in status.rank_modifiers)


class TestGoodReputation:
    def test_recognition_plus_1(self):
        data = make_character_data(
            recognition=2.0, rank=2.0, advantages=["good_reputation"]
        )
        status = compute_effective_status(data)
        assert any(
            m["context"] == "for identification" and m["field"] == "recognition"
            for m in status.recognition_modifiers
        )

    def test_rank_plus_2_with_familiar(self):
        data = make_character_data(rank=2.0, advantages=["good_reputation"])
        status = compute_effective_status(data)
        assert any(
            m["context"] == "with those familiar with your reputation"
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
            m["context"] == "for identification" and m["field"] == "recognition"
            for m in status.recognition_modifiers
        )

    def test_rank_minus_1_5_with_aware(self):
        data = make_character_data(rank=2.0, disadvantages=["bad_reputation"])
        status = compute_effective_status(data)
        assert any(
            m["value"] == -1.5 for m in status.rank_modifiers
        )


class TestWealthy:
    def test_wealthy_no_stipend_effect(self):
        """Wealthy is disabled for Wasp campaign — no stipend impact."""
        data = make_character_data(advantages=["wealthy"])
        status = compute_effective_status(data)
        assert status.stipend == 16  # still campaign base


class TestPoor:
    def test_poor_no_stipend_effect(self):
        """Poor is disabled for Wasp campaign — no stipend impact."""
        data = make_character_data(disadvantages=["poor"])
        status = compute_effective_status(data)
        assert status.stipend == 16  # still campaign base


class TestHouseholdWealth:
    def test_household_wealth_stipend(self):
        data = make_character_data(campaign_advantages=["household_wealth"])
        status = compute_effective_status(data)
        assert status.stipend == 100  # 10^2

    def test_household_wealth_with_merchant(self):
        data = make_character_data(
            school="merchant", campaign_advantages=["household_wealth"]
        )
        status = compute_effective_status(data)
        assert status.stipend == 225  # (10+5)^2

    def test_household_wealth_with_shosuro_actor(self):
        data = make_character_data(
            school="shosuro_actor", campaign_advantages=["household_wealth"]
        )
        status = compute_effective_status(data)
        assert status.stipend == 225  # (10+5)^2


class TestMerchantStipend:
    def test_merchant_school_stipend(self):
        data = make_character_data(school="merchant")
        status = compute_effective_status(data)
        assert status.stipend == 81  # (4+5)^2

    def test_shosuro_actor_stipend(self):
        data = make_character_data(school="shosuro_actor")
        status = compute_effective_status(data)
        assert status.stipend == 81  # (4+5)^2


class TestStipendModifiers:
    def test_base_has_modifier(self):
        data = make_character_data()
        status = compute_effective_status(data)
        assert len(status.stipend_modifiers) >= 1
        assert status.stipend_modifiers[0]["source"] == "Wasp campaign base"

    def test_household_wealth_modifier(self):
        data = make_character_data(campaign_advantages=["household_wealth"])
        status = compute_effective_status(data)
        sources = [m["source"] for m in status.stipend_modifiers]
        assert "Household Wealth" in sources

    def test_school_modifier(self):
        data = make_character_data(school="merchant")
        status = compute_effective_status(data)
        sources = [m["source"] for m in status.stipend_modifiers]
        assert "Merchant" in sources


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
