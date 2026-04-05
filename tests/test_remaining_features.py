"""Tests for 4th Dan auto-raise, variable school rings, and campaign advantages."""

import pytest
from app.game_data import (
    SCHOOLS, SCHOOL_RING_OPTIONS, CAMPAIGN_ADVANTAGES, CAMPAIGN_DISADVANTAGES,
)
from app.services.xp import validate_character, calculate_total_xp
from app.services.rolls import compute_dan
from tests.conftest import make_character_data


class TestSchoolRingOptions:
    def test_fixed_ring_schools(self):
        """Schools with a fixed ring should have exactly one option."""
        opts = SCHOOL_RING_OPTIONS["akodo_bushi"]
        assert opts == ["Water"]

    def test_any_non_void_schools(self):
        """'any non-Void' schools should have Air, Fire, Earth, Water."""
        opts = SCHOOL_RING_OPTIONS["brotherhood_of_shinsei_monk"]
        assert set(opts) == {"Air", "Fire", "Earth", "Water"}

    def test_air_or_water_school(self):
        """Doji Artisan has 'Air or Water'."""
        opts = SCHOOL_RING_OPTIONS["doji_artisan"]
        assert set(opts) == {"Air", "Water"}

    def test_all_schools_have_options(self):
        for sid in SCHOOLS:
            assert sid in SCHOOL_RING_OPTIONS, f"Missing ring options for {sid}"


class TestFourthDanAutoRaise:
    def test_dan_4_ring_min_is_4(self):
        """At 4th Dan, school ring cannot be below 4."""
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
        )
        errors = validate_character(data)
        assert any("Water" in e and ("4" in e or "below" in e) for e in errors)

    def test_dan_3_ring_min_is_3(self):
        """At 3rd Dan, school ring minimum is still 3 (no auto-raise)."""
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
        )
        errors = validate_character(data)
        assert not any("Water" in e and "below" in e for e in errors)

    def test_dan_4_ring_at_4_valid(self):
        """School ring at 4 with Dan 4 is valid."""
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
            starting_xp=500,
        )
        errors = validate_character(data)
        assert not any("Water" in e and "below" in e for e in errors)

    def test_dan_4_auto_raise_is_free(self):
        """4th Dan auto-raises school ring to 4 for free."""
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
            starting_xp=500,
        )
        result = calculate_total_xp(data)
        # Water 3->4 is free from 4th Dan technique
        assert result["rings"] == 0

    def test_dan_4_xp_discount_on_further_raises(self):
        """4th Dan gives 5 XP discount on school ring raises above 4."""
        data = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 5, "Void": 2},
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
            starting_xp=500,
        )
        result = calculate_total_xp(data)
        # Water 4->5: normally 25, with 5 discount = 20
        assert result["rings"] == 20


class TestCampaignAdvantages:
    def test_campaign_advantages_exist(self):
        assert len(CAMPAIGN_ADVANTAGES) > 0

    def test_streetwise_exists(self):
        assert "streetwise" in CAMPAIGN_ADVANTAGES
        assert CAMPAIGN_ADVANTAGES["streetwise"].xp_cost == 5

    def test_household_wealth_exists(self):
        assert "household_wealth" in CAMPAIGN_ADVANTAGES
        assert CAMPAIGN_ADVANTAGES["household_wealth"].xp_cost == 4

    def test_campaign_disadvantages_exist(self):
        assert len(CAMPAIGN_DISADVANTAGES) > 0

    def test_crane_indebted_exists(self):
        assert "crane_indebted" in CAMPAIGN_DISADVANTAGES
        assert CAMPAIGN_DISADVANTAGES["crane_indebted"].xp_value == 4

    def test_lion_enmity_exists(self):
        assert "lion_enmity" in CAMPAIGN_DISADVANTAGES
        assert CAMPAIGN_DISADVANTAGES["lion_enmity"].xp_value == 4

    def test_minor_clan_ally_exists(self):
        """Minor Clan Major Ally has variable cost (stored as base 2)."""
        assert "minor_clan_major_ally_sparrow" in CAMPAIGN_ADVANTAGES
        assert "minor_clan_major_ally_fox" in CAMPAIGN_ADVANTAGES
        assert "minor_clan_major_ally_mantis" in CAMPAIGN_ADVANTAGES
        assert CAMPAIGN_ADVANTAGES["minor_clan_major_ally_sparrow"].xp_cost == 2
        assert CAMPAIGN_ADVANTAGES["minor_clan_major_ally_fox"].xp_cost == 4
        assert CAMPAIGN_ADVANTAGES["minor_clan_major_ally_mantis"].xp_cost == 6

    def test_campaign_xp_calculation(self):
        """Campaign advantages/disadvantages should be included in XP total."""
        data = make_character_data(
            campaign_advantages=["streetwise"],
            campaign_disadvantages=["crane_indebted"],
        )
        result = calculate_total_xp(data)
        assert result["campaign_advantages"] == 5
        assert result["campaign_disadvantages"] == -4
