"""Tests for the corrected roll display format and rank-locked XP behavior."""

from app.services.rolls import compute_skill_roll
from app.services.xp import calculate_total_xp
from tests.conftest import make_character_data


class TestRollDisplayFormat:
    def test_bragging_ikoma_bard_format(self):
        """Bragging 1, Air 2, honor 1.0, recognition 1.0, fierce, 1st dan extra die.
        Should display: 4k2 + 9 with breakdown."""
        data = make_character_data(
            school="ikoma_bard",
            school_ring_choice="Air",
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"bragging": 1},
            knacks={"discern_honor": 1, "oppose_knowledge": 1, "oppose_social": 1},
            advantages=["fierce"],
            honor=1.0,
            recognition=1.0,
        )
        result = compute_skill_roll("bragging", data)
        # Base: 1+2=3, +1 from 1st dan = 4 rolled, 2 kept
        assert result.rolled == 4
        assert result.kept == 2
        # Fierce = free raise = +5, honor = +2, recognition = +2 => total flat = 9
        assert result.flat_bonus == 9
        # Display should be "4k2 + 9"
        assert result.display == "4k2 + 9"
        # Tooltip should break down each bonus source
        assert "1st Dan" in result.tooltip
        assert "Fierce" in result.tooltip
        assert "Honor" in result.tooltip or "honor" in result.tooltip
        assert "Recognition" in result.tooltip or "recognition" in result.tooltip

    def test_free_raise_is_plus_5(self):
        """A free raise from Charming on etiquette should add +5 to flat bonus."""
        data = make_character_data(
            skills={"etiquette": 1},
            advantages=["charming"],
        )
        result = compute_skill_roll("etiquette", data)
        assert result.flat_bonus == 5  # 1 free raise = +5

    def test_history_synergy_is_plus_5_per_rank(self):
        """History 2 gives 2 free raises on culture = +10."""
        data = make_character_data(
            skills={"culture": 1, "history": 2},
        )
        result = compute_skill_roll("culture", data)
        assert result.flat_bonus == 10  # 2 free raises * 5 = 10

    def test_discerning_investigation_2_raises(self):
        """Discerning gives 2 free raises on investigation = +10."""
        data = make_character_data(
            skills={"investigation": 1},
            advantages=["discerning"],
        )
        result = compute_skill_roll("investigation", data)
        assert result.flat_bonus == 10

    def test_tooltip_shows_source_amounts(self):
        """Tooltip should show each bonus with its amount and source."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"tact": 2},
            knacks={"discern_honor": 2, "oppose_social": 2, "worldliness": 2},
        )
        result = compute_skill_roll("tact", data)
        # 1st Dan: +1 rolled die, 2nd Dan doesn't apply (tact isn't 2nd dan target)
        # No free raises, no honor bonus on tact
        assert result.rolled == 6  # 2+3+1(1st dan)
        assert "+1 rolled die" in result.tooltip


class TestRankLockedXP:
    def test_rank_locked_costs_zero(self):
        """When rank_locked=True, rank XP should be 0 regardless of rank value."""
        data = make_character_data(rank=7.5, rank_locked=True)
        result = calculate_total_xp(data)
        assert result["rank"] == 0

    def test_rank_unlocked_costs_normally(self):
        data = make_character_data(rank=9.0, rank_locked=False)
        result = calculate_total_xp(data)
        assert result["rank"] == 3  # (9.0 - 7.5) / 0.5 = 3

    def test_rank_locked_high_value(self):
        """Even rank 9.0 costs 0 when locked."""
        data = make_character_data(rank=9.0, rank_locked=True, starting_xp=150)
        result = calculate_total_xp(data)
        assert result["rank"] == 0
