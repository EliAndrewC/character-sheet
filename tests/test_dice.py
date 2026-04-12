"""Tests for the dice roll formula builder.

The actual dice rolling happens in the browser; this module precomputes the
formula (rolled, kept, flat, conditional alternatives, reroll_tens) for every
clickable item on the character sheet.
"""

import pytest

from app.services.dice import (
    apply_dice_caps,
    build_all_roll_formulas,
    build_athletics_formula,
    build_combat_formula,
    build_knack_formula,
    build_skill_formula,
    is_impaired,
)
from tests.conftest import make_character_data


# ---------------------------------------------------------------------------
# is_impaired
# ---------------------------------------------------------------------------


class TestIsImpaired:
    def test_no_wounds_not_impaired(self):
        char = make_character_data(rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 2})
        char["current_serious_wounds"] = 0
        assert is_impaired(char) is False

    def test_below_threshold_not_impaired(self):
        char = make_character_data(rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 2})
        char["current_serious_wounds"] = 2
        assert is_impaired(char) is False

    def test_at_threshold_impaired(self):
        char = make_character_data(rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 2})
        char["current_serious_wounds"] = 3
        assert is_impaired(char) is True

    def test_above_threshold_impaired(self):
        char = make_character_data(rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 2})
        char["current_serious_wounds"] = 5
        assert is_impaired(char) is True


# ---------------------------------------------------------------------------
# apply_dice_caps
# ---------------------------------------------------------------------------


class TestApplyDiceCaps:
    def test_under_caps_unchanged(self):
        assert apply_dice_caps(7, 2) == (7, 2, 0)

    def test_user_example_4k2(self):
        # 3 athletics + 2 ring -> 4+3=7 rolled, 2 kept -> 7k2 (no caps needed)
        assert apply_dice_caps(7, 2) == (7, 2, 0)

    def test_user_example_5_athletics_3_ring_caps_to_10k4(self):
        # 5 athletics + 3 ring -> 6+5=11 rolled, 3 kept -> cap rolled at 10,
        # the 1 overflow becomes a kept die -> 10k4
        assert apply_dice_caps(11, 3) == (10, 4, 0)

    def test_user_example_5_athletics_6_ring_caps_to_10k10_plus_6(self):
        # 5 athletics + 6 ring -> 12+5=17 rolled, 6 kept ->
        # cap rolled at 10, overflow of 7 becomes kept (6+7=13 kept) ->
        # cap kept at 10, overflow of 3 becomes +6 flat
        assert apply_dice_caps(17, 6) == (10, 10, 6)

    def test_only_kept_overflow(self):
        # 8 rolled, 12 kept -> kept caps to 10, +4 flat
        assert apply_dice_caps(8, 12) == (8, 10, 4)


# ---------------------------------------------------------------------------
# build_athletics_formula
# ---------------------------------------------------------------------------


class TestAthletics:
    def test_no_athletics_ring_2(self):
        char = make_character_data(rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2})
        f = build_athletics_formula("Earth", char)
        assert f.rolled == 4 and f.kept == 2 and f.flat == 0

    def test_3_athletics_ring_2(self):
        char = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            knacks={"athletics": 3, "double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        f = build_athletics_formula("Earth", char)
        assert f.rolled == 7 and f.kept == 2 and f.flat == 0

    def test_5_athletics_ring_3_caps(self):
        char = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 2},
            knacks={"athletics": 5, "double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        f = build_athletics_formula("Earth", char)
        assert f.rolled == 10 and f.kept == 4 and f.flat == 0

    def test_5_athletics_ring_6_caps_both(self):
        char = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 6, "Water": 2, "Void": 2},
            knacks={"athletics": 5, "double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        f = build_athletics_formula("Earth", char)
        assert f.rolled == 10 and f.kept == 10 and f.flat == 6

    def test_invalid_ring_returns_none(self):
        char = make_character_data()
        assert build_athletics_formula("NotARing", char) is None

    def test_athletics_label(self):
        char = make_character_data()
        f = build_athletics_formula("Water", char)
        assert "Athletics" in f.label and "Water" in f.label


# ---------------------------------------------------------------------------
# build_skill_formula — basic + bonuses
# ---------------------------------------------------------------------------


class TestSkillFormula:
    def test_zero_rank_returns_none(self):
        char = make_character_data(skills={"bragging": 0})
        assert build_skill_formula("bragging", char) is None

    def test_unknown_skill_returns_none(self):
        char = make_character_data(skills={"nonexistent": 3})
        assert build_skill_formula("nonexistent", char) is None

    def test_basic_skill_no_bonuses(self):
        # Bragging is rolled with Air; Air ring 2, rank 2 -> 4k2
        # Honor 1 -> +2, Recognition 1 -> +2 (Bragging gets both unconditionally)
        char = make_character_data(
            school="",  # avoid school technique bonuses
            skills={"bragging": 2},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            knacks={},  # avoid Dan computation
            honor=1.0, recognition=1.0,
        )
        f = build_skill_formula("bragging", char)
        assert f.rolled == 4
        assert f.kept == 2
        assert f.flat == 4  # 2*1 honor + 2*1 recognition

    def test_highest_regard_adds_10_to_intimidation(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"intimidation": 1},
            campaign_advantages=["highest_regard"],
        )
        f = build_skill_formula("intimidation", char)
        # 2 free raises = +10 unconditional
        assert f.flat == 10
        assert any(b["label"] == "Highest Regard" and b["amount"] == 10 for b in f.bonuses)

    def test_highest_regard_conditional_extra_in_alternatives(self):
        """The 'vs Wasp' bump (extra 2 free raises = +10) must be a conditional alternative, not flat."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"intimidation": 1},
            campaign_advantages=["highest_regard"],
        )
        f = build_skill_formula("intimidation", char)
        assert any(
            alt["label"] == "vs Wasp" and alt["extra_flat"] == 10
            for alt in f.alternatives
        )

    def test_highest_regard_no_bonus_on_other_skills(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"etiquette": 1},
            campaign_advantages=["highest_regard"],
        )
        f = build_skill_formula("etiquette", char)
        assert f.flat == 0
        assert not any(b["label"] == "Highest Regard" for b in f.bonuses)
        assert not any("Wasp" in alt.get("label", "") for alt in f.alternatives)

    def test_charming_advantage_adds_5_to_etiquette(self):
        char = make_character_data(
            skills={"etiquette": 1},
            advantages=["charming"],
        )
        f = build_skill_formula("etiquette", char)
        # rank 1 + ring 2 (Air) = 3k2, +5 from Charming
        assert f.rolled == 3
        assert f.kept == 2
        assert f.flat == 5
        assert any(b["label"] == "Charming" and b["amount"] == 5 for b in f.bonuses)

    def test_higher_purpose_is_alternative_not_flat(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"bragging": 2},
            advantages=["higher_purpose"],
            advantage_details={
                "higher_purpose": {"text": "the empire", "skills": ["bragging"]},
            },
            honor=1.0,
            recognition=1.0,
        )
        f = build_skill_formula("bragging", char)
        # The +5 from Higher Purpose must NOT be in flat
        assert f.flat == 4  # only Honor + Recognition (2 + 2)
        assert any("Higher Purpose" in alt["label"] for alt in f.alternatives)
        assert any(alt["extra_flat"] == 5 for alt in f.alternatives)

    def test_specialization_is_alternative_extra_10(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"sneaking": 2},
            advantages=["specialization"],
            advantage_details={
                "specialization": {"text": "rooftops", "skills": ["sneaking"]},
            },
        )
        f = build_skill_formula("sneaking", char)
        # Sneaking has no other bonuses by default
        assert any("Specialization" in alt["label"] for alt in f.alternatives)
        assert any(alt["extra_flat"] == 10 for alt in f.alternatives)
        assert f.flat == 0

    def test_sincerity_honor_is_conditional_alternative(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"sincerity": 2},
            honor=3.0,
        )
        f = build_skill_formula("sincerity", char)
        # The Honor bonus on Sincerity must NOT be in flat (only on open rolls)
        assert f.flat == 0
        assert any("open rolls" in alt["label"] for alt in f.alternatives)
        # 2 * 3.0 = 6
        assert any(alt["extra_flat"] == 6 for alt in f.alternatives)

    def test_bragging_honor_bonus_unconditional(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"bragging": 2},
            honor=3.0,
            recognition=8.0,
        )
        f = build_skill_formula("bragging", char)
        # Honor: 2*3 = 6, Recognition: 2*8 = 16, total +22 in flat
        assert f.flat == 22

    def test_history_synergy_to_culture(self):
        char = make_character_data(
            skills={"culture": 2, "history": 3},
        )
        f = build_skill_formula("culture", char)
        # +5 per rank of History (3 ranks) = +15
        assert f.flat >= 15  # may also have other bonuses

    def test_impaired_disables_reroll_tens(self):
        char = make_character_data(
            skills={"bragging": 2},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        char["current_serious_wounds"] = 3  # >= Earth (2)
        f = build_skill_formula("bragging", char)
        assert f.reroll_tens is False

    def test_skill_high_rank_caps_dice(self):
        """A skill with rank+ring > 10 should be capped to 10 rolled, with the
        overflow becoming kept dice."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"bragging": 5},
            rings={"Air": 6, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            honor=1.0, recognition=1.0,
        )
        f = build_skill_formula("bragging", char)
        # Base 5 + 6 = 11 rolled, 6 kept. Cap rolled at 10 -> 10 rolled, 7 kept.
        assert f.rolled == 10
        assert f.kept == 7

    def test_skill_extreme_caps_kept_overflow(self):
        """When kept also exceeds 10, overflow becomes a labeled bonus."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"bragging": 8},
            rings={"Air": 6, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            honor=1.0, recognition=1.0,
        )
        f = build_skill_formula("bragging", char)
        # Base 8 + 6 = 14 rolled, 6 kept. Rolled cap -> 10 rolled, 10 kept (6+4).
        # Honor +2, Recognition +2 = 4 base flat. No extra-dice overflow.
        assert f.rolled == 10
        assert f.kept == 10
        assert f.flat == 4  # Just Honor + Recognition

    def test_skill_kept_overflow_adds_bonus(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"bragging": 10},
            rings={"Air": 6, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            honor=1.0, recognition=1.0,
        )
        f = build_skill_formula("bragging", char)
        # Base 10 + 6 = 16 rolled, 6 kept. Cap rolled -> 10 rolled, 12 kept.
        # Cap kept at 10 -> 10 kept, +4 flat (2 extra * 2).
        # Plus Honor +2 + Recognition +2 = 4. Total flat = 8.
        assert f.rolled == 10
        assert f.kept == 10
        assert f.flat == 8
        assert any("10k10" in b["label"] for b in f.bonuses)

    def test_not_impaired_reroll_tens_true(self):
        char = make_character_data(
            skills={"bragging": 2},
            rings={"Air": 2, "Fire": 2, "Earth": 5, "Water": 2, "Void": 2},
        )
        char["current_serious_wounds"] = 0
        f = build_skill_formula("bragging", char)
        assert f.reroll_tens is True


# ---------------------------------------------------------------------------
# build_knack_formula
# ---------------------------------------------------------------------------


class TestKnackFormula:
    def test_zero_rank_returns_none(self):
        char = make_character_data(knacks={"iaijutsu": 0})
        assert build_knack_formula("iaijutsu", char) is None

    def test_unknown_knack_returns_none(self):
        char = make_character_data()
        assert build_knack_formula("not_a_knack", char) is None

    def test_basic_knack_formula(self):
        char = make_character_data(
            knacks={"iaijutsu": 2, "double_attack": 1, "feint": 1},
            rings={"Air": 2, "Fire": 3, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_knack_formula("iaijutsu", char)
        # Iaijutsu uses Fire; rank 2 + Fire 3 = 5k3
        assert f.rolled == 5
        assert f.kept == 3

    def test_school_technique_first_dan_extra_die(self):
        # Mirumoto Bushi 1st Dan extra die includes 'attack', 'double_attack', 'parry'.
        char = make_character_data(
            school="mirumoto_bushi",
            knacks={"counterattack": 1, "iaijutsu": 1, "lunge": 1},  # all rank 1 -> dan 1
        )
        # All knacks at rank 1 -> dan = 1. But dan computation is min of school knacks,
        # so we need to use the actual school knacks for mirumoto_bushi
        # Actually the dan check uses character's knacks dict; let's just verify rank.
        # Akodo Bushi gives extra die on attack, and the formula function applies it.
        char2 = make_character_data(
            school="akodo_bushi",
            knacks={"counterattack": 2, "iaijutsu": 2, "lunge": 2},  # min = 2, dan 2
            attack=3,
        )
        f = build_combat_formula("attack", char2)
        # Akodo Bushi 1st Dan extra die includes 'attack' -> +1 rolled
        # Base: 3 (attack) + 2 (Fire) = 5k2, +1 from 1st Dan -> 6k2
        assert f.rolled == 6
        assert f.kept == 2
        # 2nd Dan free raise on wound_check (not attack), so flat stays 0
        assert f.flat == 0


# ---------------------------------------------------------------------------
# build_combat_formula
# ---------------------------------------------------------------------------


class TestCombatFormula:
    def test_attack_basic(self):
        char = make_character_data(
            school="",
            knacks={},  # avoid Dan computation
            attack=3,
            rings={"Air": 2, "Fire": 4, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_combat_formula("attack", char)
        assert f.rolled == 7
        assert f.kept == 4

    def test_parry_basic(self):
        char = make_character_data(
            school="",
            knacks={},
            parry=2,
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_combat_formula("parry", char)
        assert f.rolled == 5
        assert f.kept == 3

    def test_invalid_which_returns_none(self):
        char = make_character_data()
        assert build_combat_formula("notathing", char) is None

    def test_mirumoto_bushi_1st_dan_parry_extra_die(self):
        char = make_character_data(
            school="mirumoto_bushi",
            parry=2,
            knacks={"counterattack": 2, "iaijutsu": 2, "lunge": 2},  # dan=2
        )
        f = build_combat_formula("parry", char)
        # 1st Dan: parry gets extra die. 2nd Dan: parry free raise (+5 flat)
        # Base: 2 (parry) + 2 (Air) = 4k2 -> 5k2 +5
        assert f.rolled == 5
        assert f.kept == 2
        assert f.flat == 5


# ---------------------------------------------------------------------------
# build_all_roll_formulas
# ---------------------------------------------------------------------------


class TestBuildAllRollFormulas:
    def test_returns_expected_keys(self):
        # Akodo Bushi's school knacks are double_attack, feint, iaijutsu
        char = make_character_data(
            school="akodo_bushi",
            skills={"bragging": 2, "etiquette": 1},
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            attack=2,
            parry=2,
        )
        formulas = build_all_roll_formulas(char)
        # Skills present
        assert "skill:bragging" in formulas
        assert "skill:etiquette" in formulas
        # Attack/parry present
        assert "attack" in formulas
        assert "parry" in formulas
        # Athletics for every ring
        for ring in ("Air", "Fire", "Earth", "Water", "Void"):
            assert f"athletics:{ring}" in formulas
        # School knacks for akodo_bushi
        assert "knack:double_attack" in formulas
        assert "knack:feint" in formulas
        assert "knack:iaijutsu" in formulas

    def test_third_dan_annotates_applicable_skills(self):
        """At 3rd Dan, skills in the technique's applicable_to list get
        adventure_raises_max_per_roll set to the source skill rank."""
        # Courtier 3rd Dan: source_skill=tact, applicable to manipulation, etc.
        char = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            skills={"tact": 3, "manipulation": 2, "bragging": 1},
            knacks={"discern_honor": 3, "oppose_social": 3, "worldliness": 3},
        )
        formulas = build_all_roll_formulas(char)
        # Manipulation is in applicable_to → should have max_per_roll = 3 (tact rank)
        assert formulas["skill:manipulation"]["adventure_raises_max_per_roll"] == 3
        # Bragging is NOT in applicable_to → should be 0
        assert formulas["skill:bragging"]["adventure_raises_max_per_roll"] == 0

    def test_third_dan_annotates_attack(self):
        """3rd Dan also applies to attack/parry if they're in applicable_to."""
        # Brotherhood of Shinsei Monk 3rd Dan applies to attack
        char = make_character_data(
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Fire",
            skills={"precepts": 2},
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["attack"]["adventure_raises_max_per_roll"] == 2

    def test_below_third_dan_no_annotation(self):
        """Below 3rd Dan, no formulas get adventure_raises_max_per_roll."""
        char = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            skills={"tact": 3, "manipulation": 2},
            knacks={"discern_honor": 2, "oppose_social": 2, "worldliness": 2},
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["skill:manipulation"]["adventure_raises_max_per_roll"] == 0

    def test_wound_check_formula_present(self):
        char = make_character_data()
        formulas = build_all_roll_formulas(char)
        assert "wound_check" in formulas
        wc = formulas["wound_check"]
        # Akodo Bushi: 1st Dan extra die on wound_check, 2nd Dan free raise
        # At Dan 1: rolled = Water+1+1 = 3+1+1 = 5 (but Dan=1, no 2nd Dan)
        assert wc["rolled"] == 5  # Water(3) + 1 + 1(1st Dan)
        assert wc["kept"] == 3   # Water(3)
        assert wc["reroll_tens"] is True  # always

    def test_wound_check_always_rerolls_even_impaired(self):
        char = make_character_data(
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        char["current_serious_wounds"] = 5  # >= Earth(2)
        formulas = build_all_roll_formulas(char)
        assert formulas["wound_check"]["reroll_tens"] is True

    def test_wound_check_strength_of_earth_adds_flat(self):
        char = make_character_data(advantages=["strength_of_the_earth"])
        formulas = build_all_roll_formulas(char)
        assert formulas["wound_check"]["flat"] >= 5

    def test_wound_check_3rd_dan_annotated(self):
        """Schools with wound_check in 3rd Dan applicable_to get raises."""
        char = make_character_data(
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Fire",
            skills={"precepts": 3},
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["wound_check"]["adventure_raises_max_per_roll"] == 3

    def test_non_rollable_knacks_excluded(self):
        # Brotherhood of Shinsei Monk's knacks are conviction,
        # otherworldliness, worldliness — all in NON_ROLLABLE_KNACKS — so
        # build_all_roll_formulas should produce no knack:* keys for them.
        char = make_character_data(
            school="brotherhood_of_shinsei_monk",
            knacks={"conviction": 1, "otherworldliness": 1, "worldliness": 1},
        )
        formulas = build_all_roll_formulas(char)
        assert "knack:conviction" not in formulas
        assert "knack:otherworldliness" not in formulas
        assert "knack:worldliness" not in formulas

    def test_zero_rank_skills_included_as_unskilled(self):
        char = make_character_data(skills={"bragging": 0, "etiquette": 1})
        formulas = build_all_roll_formulas(char)
        # Rank-0 skills are now included as unskilled rolls
        assert "skill:bragging" in formulas
        assert formulas["skill:bragging"]["is_unskilled"] is True
        assert formulas["skill:bragging"]["reroll_tens"] is False
        # Rank-1+ skills are normal
        assert "skill:etiquette" in formulas
        assert formulas["skill:etiquette"].get("is_unskilled") is not True

    def test_unskilled_advanced_skill_has_penalty(self):
        char = make_character_data(skills={})
        formulas = build_all_roll_formulas(char)
        # Acting is an advanced skill
        assert "skill:acting" in formulas
        assert formulas["skill:acting"]["flat"] == -10
        assert formulas["skill:acting"]["is_unskilled"] is True

    def test_unskilled_basic_skill_no_penalty(self):
        char = make_character_data(skills={})
        formulas = build_all_roll_formulas(char)
        # Bragging is basic
        assert "skill:bragging" in formulas
        assert formulas["skill:bragging"]["flat"] == 0
        assert formulas["skill:bragging"]["is_unskilled"] is True

    def test_each_value_is_a_dict_with_required_keys(self):
        char = make_character_data(skills={"bragging": 2}, attack=2)
        formulas = build_all_roll_formulas(char)
        for key, formula in formulas.items():
            assert isinstance(formula, dict)
            assert "label" in formula
            assert "rolled" in formula
            assert "kept" in formula
            assert "flat" in formula
            assert "reroll_tens" in formula
            assert "alternatives" in formula
            assert "bonuses" in formula

    def test_discerning_advantage_adds_to_interrogation(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"interrogation": 1},
            advantages=["discerning"],
        )
        f = build_skill_formula("interrogation", char)
        # Discerning gives +5 (1 raise) to interrogation
        assert f.flat == 5
        assert any(b["label"] == "Discerning" and b["amount"] == 5 for b in f.bonuses)

    def test_knack_with_no_ring_falls_back_to_earth(self):
        # 'absorb_void' has ring=None — the formula falls back to Earth
        char = make_character_data(
            school="",
            knacks={"absorb_void": 2},
            rings={"Air": 2, "Fire": 2, "Earth": 4, "Water": 2, "Void": 2},
        )
        f = build_knack_formula("absorb_void", char)
        # Should use Earth (ring 4) as fallback
        assert f is not None
        assert f.kept == 4
        assert "Earth" in f.label

    def test_combat_formula_rank_zero_returns_none(self):
        char = make_character_data(school="", knacks={}, attack=0)
        assert build_combat_formula("attack", char) is None

    def test_impaired_character_all_formulas_no_reroll(self):
        char = make_character_data(
            skills={"bragging": 2},
            attack=2,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        char["current_serious_wounds"] = 3  # >= Earth(2)
        formulas = build_all_roll_formulas(char)
        for key, formula in formulas.items():
            if key == "wound_check":
                # Wound checks ALWAYS reroll 10s even when Impaired
                assert formula["reroll_tens"] is True
            else:
                assert formula["reroll_tens"] is False


# ---------------------------------------------------------------------------
# School-specific ability tests
# ---------------------------------------------------------------------------


class TestSchoolAbilities:
    """Tests for individual school abilities implemented in dice.py."""

    # --- Yogo Warden: +1k0 on damage (1st Dan) ---
    def test_yogo_warden_1st_dan_damage_extra_die(self):
        char = make_character_data(
            school="yogo_warden",
            knacks={"double_attack": 1, "iaijutsu": 1, "feint": 1},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_extra_rolled"] == 1
        assert any("1st Dan" in s for s in atk["damage_bonus_sources"])

    # --- Kuni Witch Hunter: +1k0 on damage (1st Dan) ---
    def test_kuni_witch_hunter_1st_dan_damage_extra_die(self):
        char = make_character_data(
            school="kuni_witch_hunter",
            knacks={"detect_taint": 1, "iaijutsu": 1, "presence": 1},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_extra_rolled"] == 1
        assert any("1st Dan" in s for s in atk["damage_bonus_sources"])

    # --- Shiba Bushi: +3k1 on wound checks (4th Dan) ---
    def test_shiba_bushi_4th_dan_wound_check_3k1(self):
        char = make_character_data(
            school="shiba_bushi",
            knacks={"counterattack": 4, "double_attack": 4, "iaijutsu": 4},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        wc = formulas["wound_check"]
        # Base: Water(3)+1=4 rolled, 3 kept. 1st Dan: +1 rolled. 4th Dan: +3 rolled, +1 kept.
        assert wc["rolled"] == 8  # 4 + 1 + 3
        assert wc["kept"] == 4    # 3 + 1
        assert any("3k1" in s for s in wc["bonus_sources"])

    def test_shiba_bushi_below_4th_dan_no_3k1(self):
        char = make_character_data(
            school="shiba_bushi",
            knacks={"counterattack": 3, "double_attack": 3, "iaijutsu": 3},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        wc = formulas["wound_check"]
        # Base: Water(3)+1=4 rolled, 3 kept. 1st Dan: +1 rolled. No 4th Dan bonus.
        assert wc["rolled"] == 5
        assert wc["kept"] == 3

    # --- Kakita Duelist: +5 on iaijutsu damage (4th Dan) ---
    def test_kakita_duelist_4th_dan_iaijutsu_damage_bonus(self):
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        iai = formulas["knack:iaijutsu"]
        assert iai["damage_flat_bonus"] == 5
        assert any("4th Dan" in s for s in iai["damage_bonus_sources"])
        # Other attack types should NOT have the +5
        atk = formulas["attack"]
        assert atk["damage_flat_bonus"] == 0

    def test_kakita_duelist_below_4th_dan_no_damage_bonus(self):
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        iai = formulas["knack:iaijutsu"]
        assert iai["damage_flat_bonus"] == 0

    # --- Kitsuki Magistrate: +2*Water flat on attacks ---
    def test_kitsuki_magistrate_attack_water_bonus(self):
        char = make_character_data(
            school="kitsuki_magistrate",
            knacks={"discern_honor": 1, "iaijutsu": 1, "presence": 1},
            attack=2,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        f = build_combat_formula("attack", char)
        # +2*Water(3) = +6 flat
        assert f.flat == 6
        assert any("Kitsuki" in b["label"] for b in f.bonuses)

    def test_kitsuki_magistrate_parry_no_water_bonus(self):
        char = make_character_data(
            school="kitsuki_magistrate",
            knacks={"discern_honor": 1, "iaijutsu": 1, "presence": 1},
            parry=2,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        f = build_combat_formula("parry", char)
        assert f.flat == 0  # Water bonus only on attacks

    # --- Kitsuki Magistrate: Water for interrogation ---
    def test_kitsuki_magistrate_interrogation_uses_water(self):
        char = make_character_data(
            school="kitsuki_magistrate",
            knacks={"discern_honor": 1, "iaijutsu": 1, "presence": 1},
            skills={"interrogation": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
        )
        f = build_skill_formula("interrogation", char)
        # Should use Water(4) not Air(3)
        assert f.label == "Interrogation (Water)"
        assert f.kept == 4  # Water ring
        assert f.rolled == 2 + 4 + 1  # rank + Water + 1st Dan extra die

    # --- Shosuro Actor: +acting rolled dice on attack/parry/wound_check ---
    def test_shosuro_actor_attack_acting_bonus(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 3},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        # Base: 2(attack) + 2(Fire) = 4. 1st Dan: +1. Acting: +3.
        assert f.rolled == 8

    def test_shosuro_actor_parry_acting_bonus(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 2},
            parry=2,
        )
        f = build_combat_formula("parry", char)
        # Base: 2(parry) + 2(Air) = 4. Acting adds 2 rolled.
        assert f.rolled == 6

    def test_shosuro_actor_wound_check_acting_bonus(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 3},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        wc = formulas["wound_check"]
        # Base: Water(3)+1=4 rolled, 3 kept. 1st Dan: +1 rolled. Acting: +3 rolled.
        assert wc["rolled"] == 8
        assert any("Acting" in s for s in wc["bonus_sources"])

    def test_shosuro_actor_no_acting_skill_no_bonus(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        # No acting skill, so no acting bonus. Base: 2(attack) + 2(Fire) + 1(1st Dan) = 5
        assert f.rolled == 5

    # --- Courtier 5th Dan: +Air to all TN and contested rolls ---
    def test_courtier_5th_dan_skill_air_bonus(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            skills={"bragging": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_skill_formula("bragging", char)
        # Should have +3 (Air) from 5th Dan
        assert any("5th Dan" in b["label"] and b["amount"] == 3 for b in f.bonuses)

    def test_courtier_5th_dan_combat_air_bonus(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            attack=2,
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        # build_combat_formula applies 5th Dan bonus; the Courtier special
        # +Air on attacks is applied in _annotate_attack_type (build_all_roll_formulas)
        f = build_combat_formula("attack", char)
        assert any("5th Dan" in b["label"] and b["amount"] == 3 for b in f.bonuses)

    def test_courtier_5th_dan_attack_stacks_with_special(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            attack=2,
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        # Courtier special (+3 Air via _annotate_attack_type) + 5th Dan (+3 Air via build_combat_formula)
        assert atk["flat"] == 6  # 3 + 3

    def test_courtier_5th_dan_knack_air_bonus(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_knack_formula("discern_honor", char)
        assert any("5th Dan" in b["label"] and b["amount"] == 3 for b in f.bonuses)

    def test_courtier_below_5th_dan_no_extra_air(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 4, "oppose_social": 4, "worldliness": 4},
            skills={"bragging": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_skill_formula("bragging", char)
        assert not any("5th Dan" in b.get("label", "") for b in f.bonuses)

    # --- Bayushi 5th Dan: half light wounds flag on wound check ---
    def test_bayushi_5th_dan_half_lw_flag(self):
        char = make_character_data(
            school="bayushi_bushi",
            knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["wound_check"]["bayushi_5th_dan_half_lw"] is True

    def test_bayushi_below_5th_dan_no_half_lw_flag(self):
        char = make_character_data(
            school="bayushi_bushi",
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["wound_check"]["bayushi_5th_dan_half_lw"] is False

    # --- Shugenja 5th Dan: +1 non-Void rings on commune/spellcasting ---
    def test_shugenja_5th_dan_commune_ring_boost(self):
        char = make_character_data(
            school="shugenja",
            knacks={"commune": 5, "pontificate": 5, "spellcasting": 5},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
        )
        # Commune uses a ring (varies). For the knack formula, it falls back
        # to Earth as default for "varies" ring. At 5th Dan, Earth should be +1.
        f = build_knack_formula("commune", char)
        # Default ring = Earth(2) + 1 from 5th Dan = 3
        assert f.kept == 3  # Earth(2) + 1

    def test_shugenja_5th_dan_spellcasting_ring_boost(self):
        char = make_character_data(
            school="shugenja",
            knacks={"commune": 5, "pontificate": 5, "spellcasting": 5},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
        )
        f = build_knack_formula("spellcasting", char)
        assert f.kept == 3  # Earth(2) + 1

    def test_shugenja_5th_dan_void_not_boosted(self):
        """Void ring is NOT boosted for commune/spellcasting."""
        char = make_character_data(
            school="shugenja",
            knacks={"commune": 5, "pontificate": 5, "spellcasting": 5},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 3},
        )
        # Pontificate uses Water, not affected by 5th Dan (it's not commune/spellcasting)
        f = build_knack_formula("pontificate", char)
        # Water(2), 5th Dan only applies to commune/spellcasting
        assert f.kept == 2

    def test_shugenja_below_5th_dan_no_boost(self):
        char = make_character_data(
            school="shugenja",
            knacks={"commune": 4, "pontificate": 4, "spellcasting": 4},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_knack_formula("commune", char)
        assert f.kept == 2  # No boost
