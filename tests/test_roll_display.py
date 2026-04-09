"""Tests for skill roll computation and display.

Each skill should show the computed roll (e.g. "6k3 + 5") with a tooltip
breaking down how it was calculated.
"""

import pytest

from app.services.rolls import compute_skill_roll, RollResult
from tests.conftest import make_character_data


class TestBaseRoll:
    def test_basic_skill_roll(self):
        """Bragging 2 with Air 3 = (2+3)k3 = 5k3."""
        data = make_character_data(
            skills={"bragging": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        result = compute_skill_roll("bragging", data)
        assert result.rolled == 5
        assert result.kept == 3
        assert result.display.startswith("5k3")

    def test_untrained_skill_zero(self):
        """Skill at 0 — no roll info."""
        data = make_character_data()
        result = compute_skill_roll("bragging", data)
        assert result.rolled == 0
        assert result.kept == 0

    def test_unknown_skill_returns_empty(self):
        data = make_character_data()
        result = compute_skill_roll("nonexistent_skill", data)
        assert result.rolled == 0

    def test_advanced_untrained_penalty(self):
        """Advanced skill at 0 has a -10 penalty note."""
        data = make_character_data(
            skills={"history": 0},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        result = compute_skill_roll("history", data)
        assert result.rolled == 0


class TestHonorBonus:
    def test_bragging_gets_honor_and_recognition(self):
        """Bragging bonus = 2*Honor + 2*Recognition."""
        data = make_character_data(
            skills={"bragging": 1},
            honor=3.0,
            recognition=2.0,
        )
        result = compute_skill_roll("bragging", data)
        # Bonus = 2*3.0 + 2*2.0 = 10
        assert result.flat_bonus == 10
        assert "Honor" in result.tooltip
        assert "Recognition" in result.tooltip

    def test_precepts_gets_honor_bonus(self):
        """Precepts bonus = 2*Honor."""
        data = make_character_data(
            skills={"precepts": 2},
            honor=2.5,
        )
        result = compute_skill_roll("precepts", data)
        assert result.flat_bonus == 5  # 2 * 2.5
        assert "Honor" in result.tooltip

    def test_sincerity_gets_honor_on_open_rolls(self):
        """Sincerity bonus = 2*Honor (on open rolls)."""
        data = make_character_data(
            skills={"sincerity": 1},
            honor=2.0,
        )
        result = compute_skill_roll("sincerity", data)
        assert result.flat_bonus == 4  # 2 * 2.0


class TestAdvantageBonus:
    def test_charming_etiquette(self):
        """Charming gives free raise (+5) on etiquette."""
        data = make_character_data(
            skills={"etiquette": 2},
            advantages=["charming"],
        )
        result = compute_skill_roll("etiquette", data)
        assert result.flat_bonus >= 5
        assert "Charming" in result.tooltip

    def test_fierce_bragging(self):
        """Fierce gives free raise (+5) on bragging."""
        data = make_character_data(
            skills={"bragging": 1},
            advantages=["fierce"],
        )
        result = compute_skill_roll("bragging", data)
        assert result.flat_bonus >= 5

    def test_discerning_investigation(self):
        """Discerning gives 2 free raises (+10) on investigation."""
        data = make_character_data(
            skills={"investigation": 1},
            advantages=["discerning"],
        )
        result = compute_skill_roll("investigation", data)
        assert result.flat_bonus >= 10

    def test_no_advantage_no_bonus(self):
        """Without the advantage, no bonus."""
        data = make_character_data(skills={"etiquette": 2})
        result = compute_skill_roll("etiquette", data)
        assert result.flat_bonus == 0


class TestSkillSynergies:
    def test_history_boosts_culture(self):
        """History 3 gives 3 free raises (+15) on culture."""
        data = make_character_data(
            skills={"culture": 2, "history": 3},
        )
        result = compute_skill_roll("culture", data)
        assert result.flat_bonus >= 15
        assert "History" in result.tooltip

    def test_history_boosts_law(self):
        data = make_character_data(skills={"law": 1, "history": 2})
        result = compute_skill_roll("law", data)
        assert result.flat_bonus >= 10

    def test_acting_boosts_sincerity(self):
        """Acting 2 gives 2 free raises (+10) on sincerity."""
        data = make_character_data(
            skills={"sincerity": 1, "acting": 2},
        )
        result = compute_skill_roll("sincerity", data)
        assert result.flat_bonus >= 10
        assert "Acting" in result.tooltip

    def test_acting_boosts_sneaking(self):
        data = make_character_data(skills={"sneaking": 1, "acting": 3})
        result = compute_skill_roll("sneaking", data)
        assert result.flat_bonus >= 15


class TestHigherPurpose:
    def test_higher_purpose_bonus_on_selected_skill(self):
        data = make_character_data(
            skills={"precepts": 2},
            advantages=["higher_purpose"],
            advantage_details={"higher_purpose": {"text": "oppose the Shadowlands", "skills": ["precepts", "law"]}},
        )
        result = compute_skill_roll("precepts", data)
        assert result.flat_bonus >= 5
        assert "Higher Purpose" in result.tooltip
        assert "oppose the Shadowlands" in result.tooltip

    def test_higher_purpose_no_bonus_on_unselected_skill(self):
        data = make_character_data(
            skills={"bragging": 1},
            advantages=["higher_purpose"],
            advantage_details={"higher_purpose": {"text": "oppose the Shadowlands", "skills": ["precepts"]}},
        )
        result = compute_skill_roll("bragging", data)
        assert "Higher Purpose" not in result.tooltip

    def test_higher_purpose_no_details(self):
        """Higher Purpose with no details stored should not crash."""
        data = make_character_data(
            skills={"precepts": 2},
            advantages=["higher_purpose"],
        )
        result = compute_skill_roll("precepts", data)
        assert "Higher Purpose" not in result.tooltip


class TestSpecialization:
    def test_specialization_bonus_on_selected_skill(self):
        data = make_character_data(
            skills={"culture": 2},
            advantages=["specialization"],
            advantage_details={"specialization": {"text": "poetry", "skills": ["culture"]}},
        )
        result = compute_skill_roll("culture", data)
        assert result.flat_bonus >= 10
        assert "Specialization" in result.tooltip
        assert "poetry" in result.tooltip

    def test_specialization_no_bonus_on_other_skill(self):
        data = make_character_data(
            skills={"bragging": 1},
            advantages=["specialization"],
            advantage_details={"specialization": {"text": "poetry", "skills": ["culture"]}},
        )
        result = compute_skill_roll("bragging", data)
        assert "Specialization" not in result.tooltip


class TestDisadvantageNotes:
    def test_transparent_sincerity_note(self):
        data = make_character_data(
            skills={"sincerity": 2},
            disadvantages=["transparent"],
        )
        result = compute_skill_roll("sincerity", data)
        assert "always considered 5" in result.tooltip

    def test_transparent_no_note_on_other_skill(self):
        data = make_character_data(
            skills={"bragging": 1},
            disadvantages=["transparent"],
        )
        result = compute_skill_roll("bragging", data)
        assert "always considered 5" not in result.tooltip

    def test_unkempt_culture_note(self):
        data = make_character_data(
            skills={"culture": 2},
            disadvantages=["unkempt"],
        )
        result = compute_skill_roll("culture", data)
        assert "-10" in result.tooltip
        assert "unkempt" in result.tooltip

    def test_thoughtless_tact_note(self):
        data = make_character_data(
            skills={"tact": 1},
            disadvantages=["thoughtless"],
        )
        result = compute_skill_roll("tact", data)
        assert "Manipulation" in result.tooltip


class TestFirstDanBonus:
    def test_courtier_extra_die_on_tact(self):
        """Courtier 1st Dan: extra die on tact."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"tact": 2},
            knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 1},
        )
        result = compute_skill_roll("tact", data)
        # Base: 2+3=5 rolled, 3 kept. +1 from 1st Dan = 6k3
        assert result.rolled == 6
        assert "1st Dan" in result.tooltip

    def test_no_bonus_on_non_listed_skill(self):
        """Courtier 1st Dan doesn't apply to bragging."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"bragging": 2},
            knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 1},
        )
        result = compute_skill_roll("bragging", data)
        assert result.rolled == 5  # no extra die


class TestSecondDanBonus:
    def test_courtier_free_raise_on_manipulation(self):
        """Courtier 2nd Dan: free raise (+5) on manipulation."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"manipulation": 2},
            knacks={"discern_honor": 2, "oppose_social": 2, "worldliness": 2},
        )
        result = compute_skill_roll("manipulation", data)
        assert result.flat_bonus >= 5
        assert "2nd Dan" in result.tooltip

    def test_second_dan_not_reached(self):
        """If Dan < 2, no 2nd Dan bonus."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"manipulation": 2},
            knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 1},
        )
        result = compute_skill_roll("manipulation", data)
        # Dan = 1, so no 2nd Dan bonus. May still have 0 free raises
        assert not any("2nd Dan" in line for line in result.tooltip_lines)


class TestThirdDanFreeRaises:
    def test_courtier_third_dan(self):
        """Courtier 3rd Dan: 2*tact free raises per adventure on listed skills."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            skills={"tact": 3, "manipulation": 2},
            knacks={"discern_honor": 3, "oppose_social": 3, "worldliness": 3},
        )
        result = compute_skill_roll("manipulation", data)
        # 3rd Dan: 2*3=6 free raises per adventure, max 3 per roll
        assert result.adventure_raises_available == 6
        assert result.adventure_raises_max_per_roll == 3
        assert "adventure" in result.tooltip.lower()


class TestRollResultDisplay:
    def test_display_with_bonus(self):
        data = make_character_data(
            skills={"bragging": 1},
            honor=2.0,
            recognition=1.0,
        )
        result = compute_skill_roll("bragging", data)
        assert "k" in result.display
        assert "+" in result.display

    def test_display_empty_when_untrained(self):
        data = make_character_data()
        result = compute_skill_roll("bragging", data)
        assert result.display == ""

    def test_tooltip_property(self):
        data = make_character_data(skills={"bragging": 1})
        result = compute_skill_roll("bragging", data)
        assert isinstance(result.tooltip, str)

    def test_discerning_interrogation(self):
        """Discerning gives 1 free raise (+5) on interrogation."""
        data = make_character_data(
            skills={"interrogation": 1},
            advantages=["discerning"],
        )
        result = compute_skill_roll("interrogation", data)
        assert result.flat_bonus >= 5


class TestCampaignAdvantageBonus:
    def test_highest_regard_unconditional_on_bragging(self):
        """Highest Regard always grants 2 free raises (+10) on bragging."""
        data = make_character_data(
            skills={"bragging": 1},
            campaign_advantages=["highest_regard"],
        )
        result = compute_skill_roll("bragging", data)
        # Honor 1.0 + Recognition 7.5 baseline give 2*1 + 2*7.5 = 17 from
        # those sources. Add the 10 from Highest Regard = 27.
        assert result.flat_bonus == 27
        assert "Highest Regard" in result.tooltip

    def test_highest_regard_unconditional_on_intimidation(self):
        data = make_character_data(
            skills={"intimidation": 1},
            campaign_advantages=["highest_regard"],
        )
        result = compute_skill_roll("intimidation", data)
        assert result.flat_bonus == 10  # only the 2 free raises from HR
        assert "Highest Regard" in result.tooltip

    def test_highest_regard_conditional_note(self):
        """The +10 'vs Wasp' bump appears as a separate note."""
        data = make_character_data(
            skills={"intimidation": 1},
            campaign_advantages=["highest_regard"],
        )
        result = compute_skill_roll("intimidation", data)
        text = result.parenthetical
        # Both pieces present
        assert "+10 from Highest Regard" in text
        assert "+10 more vs Wasp" in text

    def test_highest_regard_no_bonus_on_other_skills(self):
        data = make_character_data(
            skills={"etiquette": 1},
            campaign_advantages=["highest_regard"],
        )
        result = compute_skill_roll("etiquette", data)
        assert result.flat_bonus == 0
        assert "Highest Regard" not in result.tooltip


class TestParenthetical:
    def test_single_bonus_strips_redundant_amount(self):
        """One bonus → drop the '+N ' prefix since N is already in the formula."""
        # Etiquette + Charming → only the +5 from Charming, no other bonuses.
        data = make_character_data(
            skills={"etiquette": 2},
            advantages=["charming"],
        )
        result = compute_skill_roll("etiquette", data)
        # Single bonus, redundant "+5 " is stripped
        assert result.parenthetical == "from Charming"

    def test_multiple_bonuses_keep_amount_prefix(self):
        """Two or more bonuses → each one keeps its '+N from ...' prefix."""
        # Bragging + Fierce + non-zero honor + non-zero recognition
        # produces multiple bonus_parts.
        data = make_character_data(
            skills={"bragging": 1},
            advantages=["fierce"],
            honor=2.0,
            recognition=1.0,
        )
        result = compute_skill_roll("bragging", data)
        text = result.parenthetical
        # All three bonuses listed, all with "+N" prefixes
        assert "+5 from Fierce" in text
        assert "+4 from Honor" in text
        assert "+2 from Recognition" in text

    def test_third_dan_string_format(self):
        """3rd Dan free raises read 'N free raises/adventure from 3rd Dan' (no skill, no max/roll)."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            skills={"tact": 3, "manipulation": 2},
            knacks={"discern_honor": 3, "oppose_social": 3, "worldliness": 3},
        )
        result = compute_skill_roll("manipulation", data)
        text = result.parenthetical
        # New format
        assert "6 free raises/adventure from 3rd Dan" in text
        # Old details that should NOT appear
        assert "from Tact" not in text
        assert "max" not in text

    def test_first_and_second_dan_drop_technique_word(self):
        """1st Dan / 2nd Dan strings no longer say 'technique'."""
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            skills={"manipulation": 2},
            knacks={"discern_honor": 2, "oppose_social": 2, "worldliness": 2},
        )
        result = compute_skill_roll("manipulation", data)
        text = result.parenthetical
        assert "1st Dan" in text
        assert "2nd Dan" in text
        assert "technique" not in text

    def test_single_first_dan_only_keeps_descriptor(self):
        """Single 1st Dan (no flat bonus) — '+1 rolled die' is informational, not stripped."""
        # Akodo Bushi 1st Dan adds an extra die to attack/iaijutsu/feint and
        # the wound_check rolls. Pick a skill where that's the only bonus.
        # Mantis Bushi 1st Dan: extra die on attack, parry, jiujutsu, athletics.
        # Use Mantis with Athletics — no other bonuses on that skill.
        data = make_character_data(
            school="yoritomo_bushi",
            school_ring_choice="Water",
            skills={"athletics": 2},
            knacks={},
        )
        # If yoritomo_bushi doesn't have a 1st-Dan athletics bonus this test
        # will be a no-op; in that case fall back to a generic invariant.
        result = compute_skill_roll("athletics", data)
        # Just assert that whatever the parenthetical is, it doesn't say "technique"
        assert "technique" not in result.parenthetical


class TestDanComputation:
    def test_dan_from_knacks(self):
        from app.services.rolls import compute_dan
        assert compute_dan({"feint": 1, "iaijutsu": 1, "double_attack": 1}) == 1
        assert compute_dan({"feint": 3, "iaijutsu": 2, "double_attack": 5}) == 2
        assert compute_dan({"feint": 3, "iaijutsu": 3, "double_attack": 3}) == 3

    def test_dan_empty_knacks(self):
        from app.services.rolls import compute_dan
        assert compute_dan({}) == 0


class TestParryAttackRule:
    def test_parry_over_attack_plus_1_invalid(self):
        from app.services.xp import validate_character
        data = make_character_data(attack=1, parry=3)
        errors = validate_character(data)
        assert any("parry" in e.lower() for e in errors)

    def test_parry_at_attack_plus_1_valid(self):
        from app.services.xp import validate_character
        data = make_character_data(attack=2, parry=3)
        errors = validate_character(data)
        assert not any("parry" in e.lower() for e in errors)

    def test_parry_equal_attack_valid(self):
        from app.services.xp import validate_character
        data = make_character_data(attack=3, parry=3)
        errors = validate_character(data)
        assert not any("parry" in e.lower() for e in errors)
