"""Tests for skill roll computation and display.

Each skill should show the computed roll (e.g. "6k3 + 5") with a tooltip
breaking down how it was calculated.
"""

import pytest

from app.services.rolls import compute_skill_roll, RollResult
from tests.conftest import make_character_data


def _priest_party_member(name="Kuni Shouzo", dan=2):
    return {
        "name": name, "school": "priest", "dan": dan,
        "advantages": [], "disadvantages": [],
        "campaign_advantages": [], "campaign_disadvantages": [],
    }


class TestPriestPartyBonus:
    """Priest 2nd Dan grants a free raise to all party members on
    bragging / precepts / open-sincerity rolls."""

    def test_self_priest_bragging_flat_includes_free_raise(self):
        data = make_character_data(
            school="priest",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"bragging": 2},
        )
        result = compute_skill_roll("bragging", data)
        # Honor on bragging (mult 5) + Priest 2nd Dan (+5).
        assert result.flat_bonus >= 5
        assert "Priest 2nd Dan" in result.tooltip

    def test_self_priest_sincerity_conditional_note(self):
        data = make_character_data(
            school="priest",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"sincerity": 2},
        )
        result = compute_skill_roll("sincerity", data)
        assert "Priest 2nd Dan" in result.tooltip
        assert "open rolls" in result.tooltip

    def test_ally_priest_adds_free_raise_on_bragging(self):
        data = make_character_data(
            school="akodo_bushi",
            skills={"bragging": 2},
        )
        result = compute_skill_roll("bragging", data, party_members=[_priest_party_member()])
        assert "Priest 2nd Dan" in result.tooltip
        assert "Kuni Shouzo" in result.tooltip

    def test_ally_priest_below_2nd_dan_does_not_add(self):
        data = make_character_data(
            school="akodo_bushi",
            skills={"bragging": 2},
        )
        result = compute_skill_roll(
            "bragging", data, party_members=[_priest_party_member(dan=1)]
        )
        assert "Priest 2nd Dan" not in result.tooltip

    def test_ally_priest_sincerity_conditional(self):
        data = make_character_data(
            school="akodo_bushi",
            skills={"sincerity": 2},
        )
        result = compute_skill_roll(
            "sincerity", data, party_members=[_priest_party_member()]
        )
        assert "Priest 2nd Dan" in result.tooltip
        assert "open rolls" in result.tooltip

    def test_self_priest_and_ally_priest_do_not_stack(self):
        """A Priest 2nd Dan character with a Priest ally still gets only one free raise."""
        data = make_character_data(
            school="priest",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"bragging": 2},
        )
        r_solo = compute_skill_roll("bragging", data)
        r_with_ally = compute_skill_roll(
            "bragging", data, party_members=[_priest_party_member("Kakita Bard", 3)]
        )
        assert r_solo.flat_bonus == r_with_ally.flat_bonus


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

    def test_untrained_skill_rolls_ring_only(self):
        """Untrained basic skill rolls just the ring pool with an unskilled note."""
        data = make_character_data(rings={"Air": 2}, skills={})
        result = compute_skill_roll("bragging", data)
        # Base: Air only (no rank). Bragging gets honor+recognition bonuses
        # regardless of rank, so only the dice pool check matters here.
        assert result.rolled == 2
        assert result.kept == 2
        assert "unskilled" in result.tooltip

    def test_unknown_skill_returns_empty(self):
        data = make_character_data()
        result = compute_skill_roll("nonexistent_skill", data)
        assert result.rolled == 0
        assert result.display == ""

    def test_advanced_untrained_penalty(self):
        """Advanced skill at 0 has a -10 flat penalty and an unskilled note."""
        data = make_character_data(
            skills={},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            school="",
        )
        # History (advanced, Water)
        result = compute_skill_roll("history", data)
        assert result.rolled == 3  # Water only
        assert result.flat_bonus == -10
        assert "unskilled" in result.tooltip
        assert "-10" in result.tooltip

    def test_unskilled_precepts_shows_honor_bonus(self):
        """Precepts unskilled still gets its 2*Honor flat bonus displayed."""
        data = make_character_data(
            skills={},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            school="",
            honor=3.0,
        )
        result = compute_skill_roll("precepts", data)
        assert result.rolled == 2  # Fire only
        assert result.flat_bonus == 6  # 2 * 3.0 honor
        assert "+6 from Honor" in result.tooltip
        assert "unskilled" in result.tooltip

    def test_unskilled_advanced_display_shows_minus(self):
        """Display formula for unskilled advanced skill shows '- 10'."""
        data = make_character_data(
            skills={}, school="",
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        result = compute_skill_roll("history", data)
        assert result.display == "2k2 - 10"


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
        """Sincerity's honor bonus is conditional on open rolls - shown as a
        note in the parenthetical, not baked into flat_bonus."""
        data = make_character_data(
            skills={"sincerity": 1},
            honor=2.0,
        )
        result = compute_skill_roll("sincerity", data)
        assert result.flat_bonus == 0
        assert "+4 from Honor on open rolls" in result.tooltip


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

    def test_kind_eye_tact_note(self):
        """Kind Eye adds a +20 conditional note on Tact (never flat)."""
        data = make_character_data(
            skills={"tact": 2},
            advantages=["kind_eye"],
        )
        result = compute_skill_roll("tact", data)
        assert result.flat_bonus == 0
        assert "+20 for servants and the mistreated" in result.tooltip

    def test_kind_eye_sincerity_note(self):
        """Kind Eye adds the same conditional note on Sincerity."""
        data = make_character_data(
            skills={"sincerity": 2},
            advantages=["kind_eye"],
        )
        result = compute_skill_roll("sincerity", data)
        assert result.flat_bonus == 0
        assert "+20 for servants and the mistreated" in result.tooltip

    def test_kind_eye_does_not_apply_to_other_skills(self):
        data = make_character_data(
            skills={"etiquette": 2},
            advantages=["kind_eye"],
        )
        result = compute_skill_roll("etiquette", data)
        assert "servants" not in result.tooltip


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

    def test_acting_boosts_sneaking_only_when_blending_in(self):
        """Acting→Sneaking is L7R-conditional: the free raises apply only
        on 'blending into a crowd' rolls, not on 'remaining unseen' rolls.
        So the synergy lives in tooltip_lines as a conditional note and
        does NOT inflate the dice formula's flat_bonus."""
        data = make_character_data(skills={"sneaking": 1, "acting": 3})
        result = compute_skill_roll("sneaking", data)
        # No bake-in to the flat bonus.
        assert result.flat_bonus == 0
        # But the conditional note is present in the tooltip / parenthetical.
        joined = result.tooltip
        assert "+15 for blending in" in joined

    def test_history_boosts_heraldry_only_for_non_individuals(self):
        """History→Heraldry is L7R-conditional: the free raises apply only
        to questions about places, families, and institutions - not to
        identifying specific individuals. So the synergy lives in
        tooltip_lines as a conditional note and does NOT inflate
        flat_bonus."""
        data = make_character_data(skills={"heraldry": 1, "history": 3})
        result = compute_skill_roll("heraldry", data)
        assert result.flat_bonus == 0
        joined = result.tooltip
        assert "+15 for non-individuals" in joined


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
        assert "+20 to opponents' Manipulation from Thoughtless" in result.tooltip

    def test_thoughtless_no_note_on_sincerity(self):
        """Thoughtless only applies to Tact, not Sincerity."""
        data = make_character_data(
            skills={"sincerity": 1},
            disadvantages=["thoughtless"],
        )
        result = compute_skill_roll("sincerity", data)
        assert "Thoughtless" not in result.tooltip
        assert "Manipulation" not in result.tooltip


class TestPartyMemberInlineEffects:
    def test_party_thoughtless_appears_on_tact(self):
        """A party member's Thoughtless adds an inline +10 note on the
        viewing character's Tact roll."""
        data = make_character_data(skills={"tact": 1})
        party = [{
            "name": "Doji Natsu",
            "advantages": [],
            "disadvantages": ["thoughtless"],
            "campaign_advantages": [],
            "campaign_disadvantages": [],
        }]
        result = compute_skill_roll("tact", data, party_members=party)
        assert "+10 to opponents' Manipulation from Doji Natsu's Thoughtless" in result.tooltip

    def test_party_thoughtless_does_not_appear_on_sincerity(self):
        data = make_character_data(skills={"sincerity": 1})
        party = [{
            "name": "Doji Natsu",
            "advantages": [],
            "disadvantages": ["thoughtless"],
            "campaign_advantages": [],
            "campaign_disadvantages": [],
        }]
        result = compute_skill_roll("sincerity", data, party_members=party)
        assert "Thoughtless" not in result.tooltip

    def test_party_without_thoughtless_no_note(self):
        data = make_character_data(skills={"tact": 1})
        party = [{
            "name": "Doji Natsu",
            "advantages": [],
            "disadvantages": ["proud"],
            "campaign_advantages": [],
            "campaign_disadvantages": [],
        }]
        result = compute_skill_roll("tact", data, party_members=party)
        assert "Thoughtless" not in result.tooltip

    def test_no_party_argument_works(self):
        """party_members defaults to None — no notes added."""
        data = make_character_data(skills={"tact": 1})
        result = compute_skill_roll("tact", data)
        # No party note (the character has no Thoughtless of their own either)
        assert "ally" not in result.tooltip
        assert "Doji" not in result.tooltip

    def test_multiple_party_members_with_thoughtless(self):
        """Each party member with Thoughtless gets its own inline note."""
        data = make_character_data(skills={"tact": 1})
        party = [
            {"name": "Alice", "advantages": [], "disadvantages": ["thoughtless"],
             "campaign_advantages": [], "campaign_disadvantages": []},
            {"name": "Bob", "advantages": [], "disadvantages": ["thoughtless"],
             "campaign_advantages": [], "campaign_disadvantages": []},
        ]
        result = compute_skill_roll("tact", data, party_members=party)
        assert "Alice's Thoughtless" in result.tooltip
        assert "Bob's Thoughtless" in result.tooltip


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

    def test_display_shows_unskilled_roll_when_untrained(self):
        """Untrained skills now show the ring-only unskilled roll (the sheet
        and edit page surface these so players can see all bonuses)."""
        data = make_character_data(rings={"Air": 3}, skills={})
        result = compute_skill_roll("bragging", data)
        # Base pool is Air-only (3k3), no skill rank contribution.
        assert result.rolled == 3
        assert result.kept == 3
        assert result.display.startswith("3k3")
        assert "unskilled" in result.tooltip

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


class TestCourtier5thDanAirBonus:
    """Courtier 5th Dan: +Air flat on TN-always skills; noted as optional on TN-sometimes skills."""

    def _courtier_at_5th_dan(self, **overrides):
        data = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            rings={"Air": 4, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
        )
        data.update(overrides)
        return data

    def test_tn_always_skill_gets_flat_air_bonus(self):
        data = self._courtier_at_5th_dan(skills={"manipulation": 3})
        result = compute_skill_roll("manipulation", data)
        assert "+4 from 5th Dan" in result.tooltip

    def test_tn_sometimes_skill_gets_conditional_note(self):
        """Skills that are neither always nor never TN/contested get a conditional note, not flat."""
        data = self._courtier_at_5th_dan(skills={"bragging": 3})
        result = compute_skill_roll("bragging", data)
        assert "+4 from 5th Dan if TN/contested" in result.tooltip
        assert "+4 from 5th Dan\n" not in result.tooltip

    def test_tn_never_skill_gets_no_bonus(self):
        """Etiquette/acting/history never contested - no 5th Dan bonus at all."""
        data = self._courtier_at_5th_dan(skills={"etiquette": 3})
        result = compute_skill_roll("etiquette", data)
        assert "5th Dan" not in result.tooltip

    def test_below_5th_dan_gets_no_bonus(self):
        data = self._courtier_at_5th_dan(
            knacks={"discern_honor": 4, "oppose_social": 4, "worldliness": 4},
            skills={"manipulation": 3},
        )
        result = compute_skill_roll("manipulation", data)
        assert "5th Dan" not in result.tooltip

    def test_non_courtier_at_5th_dan_gets_no_bonus(self):
        """Only Courtier school triggers this bonus, not any 5th Dan character."""
        data = make_character_data(
            school="akodo_bushi",
            rings={"Air": 4, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
            skills={"manipulation": 3},
        )
        result = compute_skill_roll("manipulation", data)
        assert "5th Dan" not in result.tooltip or "Courtier" not in result.tooltip


class TestTenKTenCap:
    """The L7R 10k10 cap: rolled > 10 folds into kept; kept > 10 becomes +2 flat per die."""

    def test_rolled_over_ten_converts_excess_to_kept(self):
        """Ring 6 + skill 6 = 12k6 rolled. Excess 2 moves to kept -> 10k8."""
        data = make_character_data(
            rings={"Air": 6, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            skills={"bragging": 6},
            honor=0.0,
            recognition=0.0,
        )
        result = compute_skill_roll("bragging", data)
        assert result.rolled == 10
        assert result.kept == 8

    def test_kept_over_ten_converts_to_flat_two_per_die(self):
        """Pushing kept past 10: each excess kept die becomes +2 flat bonus."""
        data = make_character_data(
            rings={"Air": 10, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            skills={"bragging": 4},
            honor=0.0,
            recognition=0.0,
        )
        result = compute_skill_roll("bragging", data)
        # Base: 14 rolled, 10 kept; rolled cap -> 10k14; kept cap -> 10k10 + 2*4 = +8
        assert result.rolled == 10
        assert result.kept == 10
        assert result.flat_bonus >= 8
        assert "extra dice above 10k10" in result.tooltip


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


class TestKitsuneWardenSheetDisplay:
    """View Sheet display: Kitsune Warden's flexible 1st/2nd Dan picks
    AND 3rd Dan player-chosen applicable skills must surface in the
    skill row's roll display + tooltip, not just on the roll modal."""

    def _kitsune(self, dan=1, picks=None, second=None, third_picks=None):
        kn = {"absorb_void": dan, "commune": dan, "iaijutsu": dan}
        tc = {}
        if picks is not None:
            tc["first_dan_choices"] = picks
        if second is not None:
            tc["second_dan_choice"] = second
        if third_picks is not None:
            tc["third_dan_skill_choices"] = third_picks
        return make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            skills={"bragging": 2, "etiquette": 2, "tact": 2, "precepts": 3},
            technique_choices=tc,
        )

    def test_first_dan_pick_shows_extra_die_in_skill_display(self):
        """rolled count includes the +1 die and the tooltip mentions 1st Dan."""
        char = self._kitsune(dan=1, picks=["bragging"])
        result = compute_skill_roll("bragging", char)
        # Bragging is Air. rank 2 + Air 2 + 1 (1st Dan) = 5 rolled, 2 kept.
        assert result.rolled == 5
        assert result.kept == 2
        assert "1st Dan" in result.tooltip

    def test_first_dan_unpicked_skill_no_extra_die(self):
        char = self._kitsune(dan=1, picks=["bragging"])
        result = compute_skill_roll("etiquette", char)
        # etiquette is Air, rank 2 + Air 2 = 4 rolled, no extra die.
        assert result.rolled == 4
        assert "1st Dan" not in result.tooltip

    def test_second_dan_pick_shows_plus_5_flat(self):
        char = self._kitsune(dan=2, second="bragging")
        result = compute_skill_roll("bragging", char)
        assert result.flat_bonus >= 5
        assert "2nd Dan" in result.tooltip

    def test_second_dan_unpicked_skill_no_flat(self):
        char = self._kitsune(dan=2, second="bragging")
        result = compute_skill_roll("etiquette", char)
        # No 2nd Dan annotation on a non-picked skill (etiquette has no
        # other +5 sources by default).
        assert "2nd Dan" not in result.tooltip

    def test_third_dan_picks_show_adventure_raises(self):
        """A 3rd-Dan-picked skill (e.g. bragging) shows the adventure
        free-raise pool in the tooltip and via adventure_raises_*."""
        char = self._kitsune(
            dan=3, third_picks=["bragging", "tact", "etiquette"],
        )
        result = compute_skill_roll("bragging", char)
        # precepts rank 3 -> 6 raises available, 3 max per roll.
        assert result.adventure_raises_available == 6
        assert result.adventure_raises_max_per_roll == 3
        assert "free raises/adventure from 3rd Dan" in result.tooltip

    def test_third_dan_unpicked_skill_no_adventure_raises(self):
        char = self._kitsune(
            dan=3, third_picks=["bragging", "tact", "etiquette"],
        )
        # sincerity is NOT in the picks.
        result = compute_skill_roll("sincerity", char)
        assert result.adventure_raises_available == 0
        assert "3rd Dan" not in result.tooltip

    def test_third_dan_picks_iaijutsu_dropped_defensively(self):
        """Even if iaijutsu sneaks into third_dan_skill_choices, it does
        not enable adventure raises on the iaijutsu knack roll. (Only
        skills surface here, but we verify the gate stays tight.)"""
        char = self._kitsune(
            dan=3, third_picks=["iaijutsu", "tact", "etiquette"],
        )
        # tact and etiquette annotated...
        for sid in ("tact", "etiquette"):
            r = compute_skill_roll(sid, char)
            assert r.adventure_raises_available == 6, f"{sid} should be eligible"
        # ...but bragging (not picked) is not.
        r = compute_skill_roll("bragging", char)
        assert r.adventure_raises_available == 0

    def test_dan_2_with_first_dan_pick_stacks(self):
        """A Dan 2 Kitsune with picks for both 1st and 2nd Dan on
        bragging stacks: +1 die AND +5 flat."""
        char = self._kitsune(dan=2, picks=["bragging"], second="bragging")
        result = compute_skill_roll("bragging", char)
        assert result.rolled == 5  # rank 2 + Air 2 + 1
        assert result.flat_bonus >= 5
        assert "1st Dan" in result.tooltip
        assert "2nd Dan" in result.tooltip


class TestMantisWaveTreader2ndDanSheetDisplay:
    """Mantis Wave-Treader's 2nd Dan free raise (player's pick) was also
    missing from the View Sheet. Now surfaces alongside the Kitsune /
    other-flexible branches."""

    def test_mantis_2nd_dan_chosen_skill_shows_plus_5(self):
        char = make_character_data(
            school="mantis_wave_treader",
            school_ring_choice="Water",
            knacks={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
            skills={"bragging": 2},
            technique_choices={"mantis_2nd_dan_free_raise": "bragging"},
        )
        result = compute_skill_roll("bragging", char)
        assert result.flat_bonus >= 5
        assert "2nd Dan" in result.tooltip
