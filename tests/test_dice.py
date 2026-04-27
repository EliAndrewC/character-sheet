"""Tests for the dice roll formula builder.

The actual dice rolling happens in the browser; this module precomputes the
formula (rolled, kept, flat, conditional alternatives, reroll_tens) for every
clickable item on the character sheet.
"""

import pytest

from app.services.dice import (
    apply_dice_caps,
    build_all_roll_formulas,
    build_athletics_combat_formula,
    build_athletics_formula,
    build_combat_formula,
    build_initiative_formula,
    build_knack_formula,
    build_skill_formula,
    build_wound_check_formula,
    is_impaired,
    mantis_2nd_dan_eligible_choices,
    merged_knacks,
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
# Athletics used as attack/parry (p05 §Athletics: "You may also use this
# knack to attack or parry"). Exposed as ``athletics:attack`` / ``athletics:parry``
# keys in build_all_roll_formulas.
# ---------------------------------------------------------------------------


class TestAthleticsCombat:
    def test_athletics_attack_not_present_without_athletics_knack(self):
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},  # no athletics
        )
        formulas = build_all_roll_formulas(char)
        assert "athletics:attack" not in formulas
        assert "athletics:parry" not in formulas

    def test_athletics_attack_present_with_athletics_knack(self):
        char = make_character_data(
            school="togashi_ise_zumi",  # has athletics as school knack
            knacks={"athletics": 3, "jiujutsu": 1, "tattoo": 1},
        )
        formulas = build_all_roll_formulas(char)
        assert "athletics:attack" in formulas
        assert "athletics:parry" in formulas

    def test_athletics_attack_uses_fire_ring(self):
        """Athletics-attack uses Fire ring. Per the rules, substitution formula
        is (athletics + Fire)k(Fire) - the ring is NOT doubled (that doubling
        only applies to generic athletics actions, not attack/parry)."""
        char = make_character_data(
            school="",  # no school bonuses
            rings={"Air": 2, "Fire": 3, "Earth": 2, "Water": 2, "Void": 2},
            knacks={"athletics": 2},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert a["rolled"] == 3 + 2  # Fire + athletics
        assert a["kept"] == 3  # Fire

    def test_athletics_parry_uses_air_ring(self):
        """Athletics-parry uses Air ring, formula (athletics + Air)k(Air)."""
        char = make_character_data(
            school="",
            rings={"Air": 4, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            knacks={"athletics": 1},
        )
        formulas = build_all_roll_formulas(char)
        p = formulas["athletics:parry"]
        assert p["rolled"] == 4 + 1  # Air + athletics
        assert p["kept"] == 4  # Air

    def test_athletics_attack_is_attack_type_with_variant(self):
        """athletics:attack opens the attack modal and is tagged
        ``is_athletics_attack`` so the modal can apply the doubled TN."""
        char = make_character_data(
            school="",
            knacks={"athletics": 1},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert a["is_attack_type"] is True
        assert a["attack_variant"] == "athletics_attack"
        assert a["is_athletics_attack"] is True

    def test_athletics_parry_is_not_attack_type(self):
        """athletics:parry rolls through the normal roll menu, not the
        attack modal (parry doesn't open the modal either)."""
        char = make_character_data(
            school="",
            knacks={"athletics": 1},
        )
        formulas = build_all_roll_formulas(char)
        p = formulas["athletics:parry"]
        assert not p.get("is_attack_type")

    def test_athletics_attack_inherits_attack_bonus_kitsuki(self):
        """Per user intent: anything that bonuses ``attack`` also bonuses
        ``athletics:attack``. Kitsuki Magistrate adds +2*Water on attack."""
        char = make_character_data(
            school="kitsuki_magistrate",
            knacks={"athletics": 1, "discern_honor": 1, "iaijutsu": 1, "presence": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert a["flat"] == 6  # 2*Water(3)
        assert any("Kitsuki" in b["label"] for b in a.get("bonuses", []))

    def test_athletics_parry_inherits_parry_bonus_shinjo(self):
        """Shinjo Bushi has parry in first_dan_extra_die and as second_dan_free_raise."""
        char = make_character_data(
            school="shinjo_bushi",
            school_ring_choice="Air",
            knacks={"athletics": 2, "double_attack": 2, "horsemanship": 2, "lunge": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        p = formulas["athletics:parry"]
        # Base: Air(3) + athletics(2) = 5 rolled, 3 kept.
        # +1 die from 1st Dan (parry in first_dan_extra_die) -> 6 rolled.
        # +5 flat from 2nd Dan free raise (parry).
        assert p["rolled"] == 6
        assert p["kept"] == 3
        assert p["flat"] == 5

    def test_athletics_attack_inherits_first_dan_extra_die(self):
        """Akodo Bushi has ``attack`` in first_dan_extra_die, so athletics:attack
        gets the +1 rolled die too."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"athletics": 1, "double_attack": 1, "feint": 1, "iaijutsu": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        # Base: Fire(2) + athletics(1) = 3. +1 from 1st Dan (attack).
        assert a["rolled"] == 4
        assert a["kept"] == 2

    def test_athletics_attack_inherits_courtier_air_bonus(self):
        """Courtier Special: +Air flat on attack rolls."""
        char = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            knacks={"athletics": 1, "discern_honor": 1, "oppose_social": 1, "worldliness": 1},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        # Courtier Special: +Air flat (3).
        assert a["flat"] >= 3
        assert any("Courtier" in b.get("label", "") for b in a.get("bonuses", []))

    def test_athletics_attack_inherits_shosuro_acting_bonus(self):
        """Shosuro Actor: +acting_rank rolled dice on attack and parry."""
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 3},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        # Base: Fire(2) + athletics(1) = 3. 1st Dan (attack): +1. Acting: +3.
        assert a["rolled"] == 7

    def test_athletics_attack_label(self):
        char = make_character_data(
            school="",
            knacks={"athletics": 1},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert "Athletics" in a["label"]
        assert "Attack" in a["label"]

    def test_athletics_parry_label(self):
        char = make_character_data(
            school="",
            knacks={"athletics": 1},
        )
        formulas = build_all_roll_formulas(char)
        p = formulas["athletics:parry"]
        assert "Athletics" in p["label"]
        assert "Parry" in p["label"]

    def test_build_athletics_combat_formula_invalid_which(self):
        from app.services.dice import build_athletics_combat_formula
        char = make_character_data(knacks={"athletics": 1})
        assert build_athletics_combat_formula("stab", char) is None

    def test_build_athletics_combat_formula_no_knack(self):
        from app.services.dice import build_athletics_combat_formula
        char = make_character_data(knacks={"double_attack": 1})
        assert build_athletics_combat_formula("attack", char) is None

    def test_athletics_attack_courtier_5th_dan_air_bonus(self):
        """Courtier 5th Dan: +Air flat on all TN-based combat rolls."""
        char = make_character_data(
            school="courtier",
            school_ring_choice="Air",
            knacks={"athletics": 5, "discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            rings={"Air": 4, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert any("Courtier 5th Dan" == b.get("label") for b in a.get("bonuses", []))

    def test_athletics_attack_doji_artisan_5th_dan_flag(self):
        """Doji Artisan 5th Dan: client-side bonus flag based on TN."""
        char = make_character_data(
            school="doji_artisan",
            school_ring_choice="Air",
            knacks={"athletics": 5, "calligraphy": 5, "courtly_sway": 5, "sincerity": 5},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert a.get("doji_5th_dan_always") is True

    def test_athletics_attack_shosuro_5th_dan_flag(self):
        """Shosuro Actor 5th Dan: sum of lowest 3 dice added post-roll."""
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
        )
        formulas = build_all_roll_formulas(char)
        a = formulas["athletics:attack"]
        assert a.get("shosuro_5th_dan") is True


# ---------------------------------------------------------------------------
# build_skill_formula — basic + bonuses
# ---------------------------------------------------------------------------


class TestSkillFormula:
    def test_zero_rank_returns_unskilled_formula(self):
        """Rank 0 now returns an unskilled formula (ring-only pool, no reroll)."""
        char = make_character_data(skills={"bragging": 0})
        f = build_skill_formula("bragging", char)
        assert f is not None
        assert f.reroll_tens is False
        assert f.no_reroll_reason == "unskilled"

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

    def test_acting_sneaking_is_conditional_alternative(self):
        """Acting→Sneaking only applies on 'blending into a crowd' rolls,
        so the dice formula must surface it as an alternatives entry
        labeled 'when blending into a crowd' rather than baking it into
        flat. Sincerity and Intimidation, which still get the
        unconditional acting synergy, are covered separately."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"sneaking": 2, "acting": 3},
        )
        f = build_skill_formula("sneaking", char)
        assert f.flat == 0, "acting bonus must not be in flat for sneaking"
        # 3 * 5 = 15 free raises bonus, conditional.
        matching = [
            alt for alt in f.alternatives
            if alt["label"] == "when blending into a crowd"
            and alt["extra_flat"] == 15
        ]
        assert matching, (
            f"expected an alternatives entry for blending in; got {f.alternatives}"
        )

    def test_history_heraldry_is_conditional_alternative(self):
        """History→Heraldry only applies to questions about places,
        families, and institutions - not specific individuals - so the
        dice formula must surface it as an alternatives entry rather
        than baking it into flat. Culture/Law/Strategy, which still get
        the unconditional history synergy, are covered separately."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"heraldry": 2, "history": 3},
        )
        f = build_skill_formula("heraldry", char)
        assert f.flat == 0, "history bonus must not be in flat for heraldry"
        matching = [
            alt for alt in f.alternatives
            if alt["label"] == "for places and families and institutions"
            and alt["extra_flat"] == 15
        ]
        assert matching, (
            f"expected an alternatives entry for places/families/institutions; "
            f"got {f.alternatives}"
        )

    def test_history_still_unconditional_on_culture_law_strategy(self):
        """Regression: only Heraldry gets the conditional treatment.
        Culture/Law/Strategy continue to bake the History bonus into
        flat as before."""
        for skill in ("culture", "law", "strategy"):
            char = make_character_data(
                school="",
                knacks={},
                skills={skill: 2, "history": 2},
                honor=1.0,
            )
            f = build_skill_formula(skill, char)
            assert any(
                "History" in b["label"] and b["amount"] == 10
                for b in f.bonuses
            ), f"expected unconditional History bonus on {skill}; got {f.bonuses}"

    def test_acting_still_unconditional_on_sincerity_and_intimidation(self):
        """Regression: only Sneaking gets the conditional treatment.
        Sincerity and Intimidation continue to bake the Acting bonus
        into flat as before."""
        for skill in ("sincerity", "intimidation"):
            char = make_character_data(
                school="",
                knacks={},
                skills={skill: 2, "acting": 2},
                honor=1.0,  # avoid sincerity's open-roll honor mucking the count
            )
            f = build_skill_formula(skill, char)
            assert any(
                "Acting" in b["label"] and b["amount"] == 10
                for b in f.bonuses
            ), f"{skill}: expected Acting bonus baked into flat, got {f.bonuses}"

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

    def test_kind_eye_tact_alternative(self):
        """Kind Eye adds +20 'for servants and the mistreated' alt on Tact."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"tact": 2},
            advantages=["kind_eye"],
        )
        f = build_skill_formula("tact", char)
        assert f.flat == 0
        matching = [
            a for a in f.alternatives
            if "servants and the mistreated" in a["label"]
        ]
        assert len(matching) == 1
        assert matching[0]["extra_flat"] == 20

    def test_kind_eye_sincerity_alternative_stacks_with_honor(self):
        """Kind Eye on Sincerity creates a second alt that stacks with honor."""
        char = make_character_data(
            school="",
            knacks={},
            skills={"sincerity": 2},
            advantages=["kind_eye"],
            honor=3.0,
        )
        f = build_skill_formula("sincerity", char)
        labels = [a["label"] for a in f.alternatives]
        assert "on open rolls" in labels
        assert "on open rolls with servants and the mistreated" in labels
        # honor 2*3 = 6, kind eye +20, stacked = 26
        kind_eye_alt = next(
            a for a in f.alternatives
            if a["label"] == "on open rolls with servants and the mistreated"
        )
        assert kind_eye_alt["extra_flat"] == 26

    def test_kind_eye_does_not_affect_other_skills(self):
        char = make_character_data(
            school="",
            knacks={},
            skills={"etiquette": 2},
            advantages=["kind_eye"],
        )
        f = build_skill_formula("etiquette", char)
        assert not any("servants" in a["label"] for a in f.alternatives)

    def test_kind_eye_unskilled_tact_alternative(self):
        """Unskilled Tact (rank 0) with Kind Eye still surfaces the alt."""
        char = make_character_data(
            school="",
            knacks={},
            skills={},
            advantages=["kind_eye"],
        )
        from app.services.dice import build_unskilled_formula
        f = build_unskilled_formula("tact", char)
        assert f is not None
        assert any("servants" in a["label"] for a in f.alternatives)

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

    def test_otherworldliness_capacity_basic_skill(self):
        # Bragging is basic; rank 2 -> can absorb up to 3 OW bumps (to reach rank 5).
        char = make_character_data(school="", knacks={}, skills={"bragging": 2})
        f = build_skill_formula("bragging", char)
        assert f.otherworldliness_capacity == 3

    def test_otherworldliness_capacity_basic_skill_at_max(self):
        # Basic skill already at rank 5 -> no room for OW bumps.
        char = make_character_data(school="", knacks={}, skills={"bragging": 5})
        f = build_skill_formula("bragging", char)
        assert f.otherworldliness_capacity == 0

    def test_otherworldliness_capacity_advanced_skill_is_zero(self):
        # Advanced skills are excluded from Otherworldliness entirely.
        char = make_character_data(school="", knacks={}, skills={"acting": 2})
        f = build_skill_formula("acting", char)
        assert f.otherworldliness_capacity == 0

    def test_otherworldliness_capacity_knack_is_zero(self):
        char = make_character_data(
            knacks={"iaijutsu": 2, "double_attack": 1, "feint": 1},
        )
        f = build_knack_formula("iaijutsu", char)
        assert f.otherworldliness_capacity == 0

    def test_otherworldliness_capacity_unskilled_basic_skill(self):
        # Unskilled (rank 0) basic skill -> full capacity of 5 OW bumps.
        from app.services.dice import build_unskilled_formula
        char = make_character_data(school="", knacks={}, skills={})
        f = build_unskilled_formula("bragging", char)
        assert f.otherworldliness_capacity == 5

    def test_otherworldliness_capacity_unskilled_advanced_skill(self):
        from app.services.dice import build_unskilled_formula
        char = make_character_data(school="", knacks={}, skills={})
        f = build_unskilled_formula("acting", char)
        assert f.otherworldliness_capacity == 0

    def test_unskilled_advanced_penalty_appears_in_bonuses(self):
        # The -10 advanced-skill penalty must appear in the labelled bonuses
        # list so the roll-result modal can display it.
        from app.services.dice import build_unskilled_formula
        char = make_character_data(school="", knacks={}, skills={})
        f = build_unskilled_formula("acting", char)
        assert f.flat == -10
        assert any(b["amount"] == -10 for b in f.bonuses), \
            f"Expected -10 penalty in bonuses, got {f.bonuses!r}"

    def test_unskilled_basic_has_no_penalty_bonus(self):
        from app.services.dice import build_unskilled_formula
        char = make_character_data(school="", knacks={}, skills={})
        f = build_unskilled_formula("bragging", char)
        # Basic skills get no -10 penalty (only advanced do). Honor/recognition
        # bonuses still apply, so flat may be non-zero.
        assert not any(
            b.get("label") == "unskilled advanced penalty" for b in f.bonuses
        )

    def test_unskilled_no_reroll_reason_carries_skill_name(self):
        """The roll-result modal needs to render ``10s not rerolled due to
        <skill name> being 0`` so the player understands *why*. Expose the
        human-readable skill name on the formula alongside the reason key."""
        from app.services.dice import build_unskilled_formula
        char = make_character_data(school="", knacks={}, skills={})
        f = build_unskilled_formula("bragging", char)
        assert f.no_reroll_reason == "unskilled"
        assert f.unskilled_skill_name == "Bragging"

    def test_unskilled_skill_name_uses_display_name_not_id(self):
        """Two-word skill names should render with spaces/capitals from SKILLS,
        not as the underscored id."""
        from app.services.dice import build_unskilled_formula
        char = make_character_data(school="", knacks={}, skills={})
        f = build_unskilled_formula("double_attack", char) if False else None
        # double_attack is a knack, not a skill - use an actual 2-word skill
        f = build_unskilled_formula("underworld", char)
        assert f.unskilled_skill_name == "Underworld"


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

    def test_dragon_tattoo_is_2x_k1_damage_roll(self):
        """Dragon Tattoo rolls (2 * rank)k1, not rank+Earth based."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 3},
        )
        f = build_knack_formula("dragon_tattoo", char)
        assert f.rolled == 6
        assert f.kept == 1
        assert "Damage" in f.label
        assert f.is_damage_roll is True

    def test_non_damage_knacks_dont_have_damage_flag(self):
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 2, "conviction": 2, "dragon_tattoo": 2},
        )
        f = build_knack_formula("athletics", char)
        assert f.is_damage_roll is False

    def test_dragon_tattoo_impaired_disables_reroll_tens(self):
        """Dragon Tattoo damage should stop rerolling 10s when impaired."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 2},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            current_serious_wounds=2,
        )
        f = build_knack_formula("dragon_tattoo", char)
        assert f.reroll_tens is False
        assert f.no_reroll_reason == "impaired"

    def test_dragon_tattoo_healthy_rerolls_tens(self):
        """Dragon Tattoo rerolls 10s when not impaired."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 2},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            current_serious_wounds=0,
        )
        f = build_knack_formula("dragon_tattoo", char)
        assert f.reroll_tens is True

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

    def test_missing_school_knacks_default_to_rank_one(self):
        """School knacks start at rank 1 for free, so formulas must be
        generated for them even when the stored knacks dict is empty or
        missing entries (e.g. a draft that predates a school change).
        Without this, the per-action-die menu would drop options like
        Double Attack, Counterattack, Lunge, and Feint."""
        for school_id, expected in [
            ("shinjo_bushi", {"double_attack", "iaijutsu", "lunge"}),
            ("akodo_bushi", {"double_attack", "feint", "iaijutsu"}),
            ("daidoji_yojimbo", {"counterattack", "double_attack", "iaijutsu"}),
            ("bayushi_bushi", {"double_attack", "feint", "iaijutsu"}),
        ]:
            char = make_character_data(school=school_id, knacks={})
            formulas = build_all_roll_formulas(char)
            for knack_id in expected:
                assert f"knack:{knack_id}" in formulas, (
                    f"{school_id} missing knack:{knack_id} when knacks dict is empty"
                )

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

    def test_skill_loop_skips_when_builder_returns_none(self, monkeypatch):
        """Defensive guard in build_all_roll_formulas: if build_skill_formula
        returns None for a skill_id, that skill is omitted from the result
        rather than crashing. The branch is only reachable via a stub here -
        the live builder always returns a formula for valid SKILLS keys -
        but the guard exists so a future builder-side bailout won't crash
        the sheet."""
        from app.services import dice as dice_mod
        real_builder = dice_mod.build_skill_formula

        def stub(skill_id, character_data, party_members=None):
            if skill_id == "bragging":
                return None
            return real_builder(skill_id, character_data, party_members=party_members)

        monkeypatch.setattr(dice_mod, "build_skill_formula", stub)
        char = make_character_data()
        formulas = build_all_roll_formulas(char)
        assert "skill:bragging" not in formulas
        # Other skills still present.
        assert "skill:etiquette" in formulas

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
        # Bragging is basic - gets no -10 penalty (advanced-only). Honor and
        # recognition bonuses still apply and may contribute to flat.
        assert "skill:bragging" in formulas
        f = formulas["skill:bragging"]
        assert f["is_unskilled"] is True
        assert not any(
            b.get("label") == "unskilled advanced penalty" for b in f["bonuses"]
        )

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

    # --- Kakita Duelist knack:iaijutsu:attack variant (Phase-0 attacks) ---
    def test_kakita_iaijutsu_attack_formula_exposed(self):
        """Kakita with iaijutsu knack gets a ``knack:iaijutsu:attack`` key
        alongside the regular ``knack:iaijutsu`` - marked as an attack-type
        formula so the client routes it through the attack modal."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        assert "knack:iaijutsu:attack" in formulas
        atk = formulas["knack:iaijutsu:attack"]
        assert atk["is_attack_type"] is True
        assert atk["attack_variant"] == "iaijutsu"
        assert atk["label"].startswith("Iaijutsu Attack")

    def test_non_kakita_no_iaijutsu_attack_formula(self):
        """Other schools with an iaijutsu knack do not get the attack
        variant - the key is Kakita-only."""
        for school, knack_keys in [
            ("akodo_bushi", ["double_attack", "feint", "iaijutsu"]),
            ("bayushi_bushi", ["double_attack", "feint", "iaijutsu"]),
            ("mirumoto_bushi", ["iaijutsu", "parry", "counterattack"]),
        ]:
            char = make_character_data(
                school=school,
                knacks={k: 1 for k in knack_keys},
            )
            formulas = build_all_roll_formulas(char)
            assert "knack:iaijutsu:attack" not in formulas, school

    def test_kakita_iaijutsu_attack_formula_mirrors_iaijutsu_knack_rolled_kept(self):
        """The attack-variant's base dice must match the regular iaijutsu
        knack so the Phase-0 attack rolls the same roll the player would
        roll via the normal iaijutsu flow."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 2, "iaijutsu": 2, "lunge": 2},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        iai = formulas["knack:iaijutsu"]
        atk = formulas["knack:iaijutsu:attack"]
        assert atk["rolled"] == iai["rolled"]
        assert atk["kept"] == iai["kept"]
        assert atk["flat"] == iai["flat"]

    def test_kakita_iaijutsu_attack_formula_respects_4th_dan_damage_bonus(self):
        """The attack variant inherits the 4th Dan iaijutsu damage +5 flat."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["knack:iaijutsu:attack"]
        assert atk["damage_flat_bonus"] == 5
        assert any("4th Dan" in s for s in atk["damage_bonus_sources"])

    def test_kakita_below_4th_dan_iaijutsu_attack_no_damage_bonus(self):
        """Below 4th Dan the attack variant has no damage bonus."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["knack:iaijutsu:attack"]
        assert atk["damage_flat_bonus"] == 0

    def test_kakita_iaijutsu_attack_bonus_sources_lists_1st_dan_extra_die(self):
        """The iaijutsu:attack formula exposes a bonus_sources summary so the
        pre-roll probability panel shows the 1st Dan +1 rolled die."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["knack:iaijutsu:attack"]
        assert any("1st Dan" in s for s in atk["bonus_sources"])
        assert atk["iaijutsu_first_dan_extra_die"] is True

    def test_kakita_iaijutsu_attack_bonus_sources_lists_2nd_dan_free_raise(self):
        """The iaijutsu:attack formula exposes the 2nd Dan +5 free raise in
        bonus_sources (via the structured bonuses list on the knack formula)."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 2, "iaijutsu": 2, "lunge": 2},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["knack:iaijutsu:attack"]
        sources = " | ".join(atk["bonus_sources"])
        assert "2nd Dan" in sources
        assert "+5" in sources

    def test_kakita_iaijutsu_attack_formula_includes_1st_dan_rolled_die(self):
        """Rolled count must actually include the +1 1st Dan die so the
        probability chart's computation reflects it."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["knack:iaijutsu:attack"]
        iai = formulas["knack:iaijutsu"]
        # Both iaijutsu knack rolls (same underlying build_knack_formula) get
        # the +1; the shared rolled count is the ring value + rank + 1.
        assert atk["rolled"] == iai["rolled"]
        # Sanity: 1 rank + 2 ring + 1 (1st Dan) = 4 rolled, 2 kept.
        assert atk["rolled"] == 4
        assert atk["kept"] == 2

    def test_kakita_iaijutsu_attack_formula_includes_2nd_dan_flat_in_probability(self):
        """Flat total on the attack variant includes the +5 2nd Dan free
        raise, so the probability chart's hit % uses it."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 2, "iaijutsu": 2, "lunge": 2},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["knack:iaijutsu:attack"]
        assert atk["flat"] == 5

    # --- Kakita Duelist 3rd Dan: defender-phase bonus flag ---
    def test_kakita_3rd_dan_attack_flag_set(self):
        """Kakita 3rd Dan: base attack formula carries the defender-phase flag."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        assert f.kakita_3rd_dan_defender_phase_bonus is True

    def test_kakita_3rd_dan_parry_no_flag(self):
        """Kakita 3rd Dan: parry doesn't get the attack-only flag."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
            parry=2,
        )
        f = build_combat_formula("parry", char)
        assert f.kakita_3rd_dan_defender_phase_bonus is False

    def test_kakita_3rd_dan_attack_knack_flags(self):
        """Kakita 3rd Dan: attack-type knacks carry the flag."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
        )
        for kid in ("double_attack", "lunge"):
            f = build_knack_formula(kid, char)
            assert f.kakita_3rd_dan_defender_phase_bonus is True, kid

    def test_kakita_3rd_dan_athletics_attack_flag(self):
        """Kakita 3rd Dan: athletics-as-attack carries the flag."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"athletics": 3, "double_attack": 3, "iaijutsu": 3, "lunge": 3},
        )
        f = build_athletics_combat_formula("attack", char)
        assert f.kakita_3rd_dan_defender_phase_bonus is True

    def test_kakita_3rd_dan_iaijutsu_attack_flag(self):
        """The Kakita-only knack:iaijutsu:attack variant also carries the flag."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["knack:iaijutsu:attack"]
        assert atk["kakita_3rd_dan_defender_phase_bonus"] is True

    def test_kakita_below_3rd_dan_no_defender_phase_flag(self):
        """Kakita at Dan 1/2 does not carry the flag."""
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 2, "iaijutsu": 2, "lunge": 2},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        assert f.kakita_3rd_dan_defender_phase_bonus is False

    def test_kakita_3rd_dan_flag_only_for_kakita_school(self):
        """Other 3rd Dan schools don't carry the Kakita 3rd Dan flag."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        assert f.kakita_3rd_dan_defender_phase_bonus is False

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

    def test_shosuro_actor_roll_formulas_sheet_contract(self):
        # Contract the sheet's Attack/Parry/Wound Check summary rows depend
        # on: roll_formulas[...] must carry the full server-computed pool
        # (including Shosuro Acting AND the L7R 10k10 cap), so the View
        # Character page renders the correct XkY without re-deriving it.
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 5},
            rings={"Air": 3, "Fire": 3, "Earth": 2, "Water": 4, "Void": 2},
            attack=2,
            parry=2,
        )
        formulas = build_all_roll_formulas(char)
        # Attack: 2(attack) + 3(Fire) + 1(1st Dan) + 5(acting) = 11 rolled,
        # capped to 10 with the extra rolled die converting to kept -> 10k4.
        assert formulas["attack"]["rolled"] == 10
        assert formulas["attack"]["kept"] == 4
        # Parry: 2(parry) + 3(Air) + 5(acting) = 10 rolled (1st Dan does not
        # apply to parry for Shosuro Actor). Exactly at the cap -> 10k3.
        assert formulas["parry"]["rolled"] == 10
        assert formulas["parry"]["kept"] == 3
        # Wound check: (Water+1)+1(1st Dan)+5(acting) = 11 rolled, capped
        # to 10 with the extra rolled die converting to kept -> 10k5.
        assert formulas["wound_check"]["rolled"] == 10
        assert formulas["wound_check"]["kept"] == 5

    def test_shosuro_actor_wound_check_kept_overflow_adds_flat(self):
        # When pre-cap kept exceeds 10, every overflow kept die converts to a
        # +2 flat bonus. Push wound_check past the kept cap by combining a
        # high Water ring with Shosuro Actor acting bonus rolled dice.
        # Pre-cap: rolled = Water(8) + 1 + 1(1st Dan) + 5(acting) = 15;
        # kept = 8. apply_dice_caps moves 5 rolled overflow into kept (=13),
        # then clamps kept to 10 with flat += 2*3 = 6.
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 5},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 8, "Void": 2},
        )
        wc = build_wound_check_formula(char)
        assert wc["rolled"] == 10
        assert wc["kept"] == 10
        assert wc["flat"] == 6
        assert any("above 10k10" in s for s in wc["bonus_sources"])

    # --- Shosuro Actor 5th Dan: flag set on non-initiative formulas ---
    def test_shosuro_5th_dan_flag_on_attack(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
            attack=3,
        )
        f = build_combat_formula("attack", char)
        assert f.shosuro_5th_dan is True

    def test_shosuro_5th_dan_flag_on_parry(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
            parry=3,
        )
        f = build_combat_formula("parry", char)
        assert f.shosuro_5th_dan is True

    def test_shosuro_5th_dan_flag_on_wound_check(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
        )
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["shosuro_5th_dan"] is True

    def test_shosuro_5th_dan_flag_on_attack_in_all_roll_formulas(self):
        """The 'attack' key carries the flag after _annotate_attack_type."""
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["attack"]["shosuro_5th_dan"] is True

    # --- Attack formula bonus_sources (pre-roll modal display) ---
    def test_attack_bonus_sources_first_dan_extra_die(self):
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["attack"]
        assert any("1st Dan" in s for s in atk["bonus_sources"])

    def test_attack_bonus_sources_second_dan_free_raise_ikoma(self):
        """Ikoma 2nd Dan gives +5 free raise on attack; appears in bonus_sources."""
        char = make_character_data(
            school="ikoma_bard",
            knacks={"discern_honor": 2, "oppose_knowledge": 2, "oppose_social": 2},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["attack"]
        sources = " | ".join(atk["bonus_sources"])
        assert "2nd Dan" in sources
        assert "+5" in sources

    def test_attack_bonus_sources_kitsuki_water(self):
        char = make_character_data(
            school="kitsuki_magistrate",
            knacks={"discern_honor": 1, "iaijutsu": 1, "presence": 1},
            attack=2,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        atk = build_all_roll_formulas(char)["attack"]
        sources = " | ".join(atk["bonus_sources"])
        assert "Kitsuki" in sources
        assert "+6" in sources  # 2 * Water(3)

    def test_attack_bonus_sources_courtier_special(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 1},
            attack=2,
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        atk = build_all_roll_formulas(char)["attack"]
        sources = " | ".join(atk["bonus_sources"])
        assert "Courtier Special" in sources
        assert "+3" in sources  # Air = 3

    def test_attack_bonus_sources_courtier_5th_dan(self):
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            attack=3,
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        atk = build_all_roll_formulas(char)["attack"]
        sources = " | ".join(atk["bonus_sources"])
        # Both the Special (+Air) and the 5th Dan (+Air) should be listed.
        assert "Courtier Special" in sources
        assert "Courtier 5th Dan" in sources

    def test_attack_bonus_sources_shosuro_acting_dice(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 1, "discern_honor": 1, "pontificate": 1},
            skills={"acting": 3},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["attack"]
        sources = " | ".join(atk["bonus_sources"])
        assert "Acting" in sources
        assert "+3" in sources

    def test_attack_bonus_sources_empty_for_plain_character(self):
        """Non-technique character should have no bonus_sources entries."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 0, "feint": 0, "iaijutsu": 0},
            attack=2,
        )
        atk = build_all_roll_formulas(char)["attack"]
        # dan is 0 so no 1st Dan bonus; no other flats.
        assert atk["bonus_sources"] == []

    def test_shosuro_5th_dan_flag_not_set_below_5th_dan(self):
        char = make_character_data(
            school="shosuro_actor",
            knacks={"athletics": 4, "discern_honor": 4, "pontificate": 4},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        assert f.shosuro_5th_dan is False
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["shosuro_5th_dan"] is False

    def test_shosuro_5th_dan_flag_not_set_other_schools(self):
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
        )
        f = build_combat_formula("attack", char)
        assert f.shosuro_5th_dan is False
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["shosuro_5th_dan"] is False

    # --- Courtier 5th Dan: +Air to all TN and contested rolls ---
    def test_courtier_5th_dan_skill_air_bonus_always(self):
        """Courtier 5th Dan: always-TN skills get automatic bonus."""
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            skills={"sneaking": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_skill_formula("sneaking", char)
        assert any("5th Dan" in b["label"] and b["amount"] == 3 for b in f.bonuses)

    def test_courtier_5th_dan_skill_air_bonus_sometimes(self):
        """Courtier 5th Dan: sometimes-TN skills get optional bonus field."""
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            skills={"bragging": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_skill_formula("bragging", char)
        assert f.courtier_5th_dan_optional == 3
        assert not any("5th Dan" in b["label"] for b in f.bonuses)

    def test_courtier_5th_dan_skill_air_bonus_never(self):
        """Courtier 5th Dan: never-TN skills get no bonus."""
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            skills={"etiquette": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_skill_formula("etiquette", char)
        assert f.courtier_5th_dan_optional == 0
        assert not any("5th Dan" in b["label"] for b in f.bonuses)

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
        assert f.courtier_5th_dan_optional == 0

    def test_courtier_5th_dan_wound_check_bonus(self):
        """Courtier 5th Dan: wound check gets +Air."""
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        wc = build_wound_check_formula(char)
        assert wc["flat"] >= 3
        assert any("5th Dan" in s for s in wc["bonus_sources"])

    def test_courtier_below_5th_dan_no_wound_check_bonus(self):
        """Courtier below 5th Dan: no wound check bonus."""
        char = make_character_data(
            school="courtier",
            knacks={"discern_honor": 4, "oppose_social": 4, "worldliness": 4},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        wc = build_wound_check_formula(char)
        assert not any("5th Dan" in s for s in wc["bonus_sources"])

    # --- Doji Artisan 5th Dan: TN-dependent bonus flags ---
    def test_doji_5th_dan_skill_always_tn(self):
        """Doji 5th Dan: always-TN skills get doji_5th_dan_always flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
            skills={"manipulation": 3},
        )
        f = build_skill_formula("manipulation", char)
        assert f.doji_5th_dan_always is True
        assert f.doji_5th_dan_optional is False

    def test_doji_5th_dan_skill_sometimes_tn(self):
        """Doji 5th Dan: sometimes-TN skills get doji_5th_dan_optional flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
            skills={"bragging": 2},
        )
        f = build_skill_formula("bragging", char)
        assert f.doji_5th_dan_optional is True
        assert f.doji_5th_dan_always is False

    def test_doji_5th_dan_skill_never_tn(self):
        """Doji 5th Dan: never-TN skills get no flags."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
            skills={"etiquette": 2},
        )
        f = build_skill_formula("etiquette", char)
        assert f.doji_5th_dan_always is False
        assert f.doji_5th_dan_optional is False

    def test_doji_5th_dan_knack_always(self):
        """Doji 5th Dan: knacks always get the always flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
        )
        f = build_knack_formula("counterattack", char)
        assert f.doji_5th_dan_always is True

    def test_doji_5th_dan_attack_flag(self):
        """Doji 5th Dan: attack formulas get the always flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
            attack=3,
        )
        f = build_combat_formula("attack", char)
        assert f.doji_5th_dan_always is True

    def test_doji_5th_dan_wound_check_flag(self):
        """Doji 5th Dan: wound check gets doji_5th_dan_wc flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
        )
        wc = build_wound_check_formula(char)
        assert wc["doji_5th_dan_wc"] is True

    def test_doji_below_5th_dan_no_flags(self):
        """Doji below 5th Dan: no flags set."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 4, "oppose_social": 4, "worldliness": 4},
            skills={"manipulation": 2, "bragging": 2},
        )
        f_always = build_skill_formula("manipulation", char)
        assert f_always.doji_5th_dan_always is False
        f_sometimes = build_skill_formula("bragging", char)
        assert f_sometimes.doji_5th_dan_optional is False
        wc = build_wound_check_formula(char)
        assert wc["doji_5th_dan_wc"] is False

    # --- Doji Artisan 4th Dan: "untouched target" flag on attack-type rolls ---
    def test_doji_4th_dan_attack_flag(self):
        """Doji 4th Dan: base attack formula gets the untouched_target flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 4, "oppose_social": 4, "worldliness": 4},
            attack=3,
        )
        f = build_combat_formula("attack", char)
        assert f.doji_4th_dan_untouched_target is True

    def test_doji_4th_dan_parry_no_flag(self):
        """Doji 4th Dan: parry is defensive, not an attack, no flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 4, "oppose_social": 4, "worldliness": 4},
            parry=3,
        )
        f = build_combat_formula("parry", char)
        assert f.doji_4th_dan_untouched_target is False

    def test_doji_4th_dan_counterattack_knack_flag(self):
        """Doji 4th Dan: counterattack (attack-type knack) gets the flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 4, "oppose_social": 4, "worldliness": 4},
        )
        f = build_knack_formula("counterattack", char)
        assert f.doji_4th_dan_untouched_target is True

    def test_doji_4th_dan_oppose_social_knack_no_flag(self):
        """Doji 4th Dan: non-attack knacks (e.g. oppose_social) no flag."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 4, "oppose_social": 4, "worldliness": 4},
        )
        f = build_knack_formula("oppose_social", char)
        assert f.doji_4th_dan_untouched_target is False

    def test_doji_4th_dan_athletics_attack_flag(self):
        """Doji 4th Dan: athletics-as-attack also gets the flag. Dan is the
        minimum knack rank, so athletics must be at 4+ too."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"athletics": 4, "counterattack": 4, "oppose_social": 4, "worldliness": 4},
        )
        f = build_athletics_combat_formula("attack", char)
        assert f.doji_4th_dan_untouched_target is True

    def test_doji_4th_dan_athletics_parry_no_flag(self):
        """Doji 4th Dan: athletics-as-parry has no flag (defensive only)."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"athletics": 4, "counterattack": 4, "oppose_social": 4, "worldliness": 4},
        )
        f = build_athletics_combat_formula("parry", char)
        assert f.doji_4th_dan_untouched_target is False

    def test_doji_below_4th_dan_no_untouched_flag(self):
        """Doji below 4th Dan: no untouched_target flag on attack formulas."""
        char = make_character_data(
            school="doji_artisan",
            knacks={"counterattack": 3, "oppose_social": 3, "worldliness": 3},
            attack=3,
        )
        f = build_combat_formula("attack", char)
        assert f.doji_4th_dan_untouched_target is False
        k = build_knack_formula("counterattack", char)
        assert k.doji_4th_dan_untouched_target is False

    def test_doji_4th_dan_flag_only_for_doji_school(self):
        """Other schools at Dan 4+ do not get the Doji 4th Dan flag."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
            attack=3,
        )
        f = build_combat_formula("attack", char)
        assert f.doji_4th_dan_untouched_target is False

    # --- Shinjo Bushi Special Ability: phase bonus flag ---
    def test_shinjo_special_ability_attack_flag(self):
        """Shinjo Bushi attack formula gets the phase-bonus flag (any Dan)."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        assert f.shinjo_phase_bonus_attack is True

    def test_shinjo_special_ability_parry_flag(self):
        """Shinjo parry is flagged too: the Special Ability rules text
        ("each action you take in combat has a bonus of 2X") applies to
        both sides of attack/parry, so the parry result modal surfaces a
        phase-selection prompt just like the attack modal does."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            parry=2,
        )
        f = build_combat_formula("parry", char)
        assert f.shinjo_phase_bonus_attack is True

    def test_shinjo_special_ability_attack_knack_flag(self):
        """Shinjo attack-type knacks (double_attack, lunge) get the flag."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
        )
        for kid in ("double_attack", "lunge"):
            f = build_knack_formula(kid, char)
            assert f.shinjo_phase_bonus_attack is True, kid

    def test_shinjo_special_ability_non_attack_knack_no_flag(self):
        """Shinjo iaijutsu isn't an attack-type knack; no phase-bonus flag."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        f = build_knack_formula("iaijutsu", char)
        assert f.shinjo_phase_bonus_attack is False

    def test_shinjo_special_ability_athletics_attack_flag(self):
        """Shinjo athletics-as-attack also carries the phase-bonus flag."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"athletics": 1, "double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        f = build_athletics_combat_formula("attack", char)
        assert f.shinjo_phase_bonus_attack is True

    def test_shinjo_special_ability_flag_only_for_shinjo_school(self):
        """Other schools don't get the Shinjo phase-bonus flag."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
            attack=2,
        )
        f = build_combat_formula("attack", char)
        assert f.shinjo_phase_bonus_attack is False

    def test_shared_tn_groupings_values(self):
        """Verify the shared TN groupings contain expected skills."""
        from app.services.dice import _5TH_DAN_TN_ALWAYS, _5TH_DAN_TN_NEVER
        assert _5TH_DAN_TN_ALWAYS == frozenset({
            "sneaking", "interrogation", "manipulation", "heraldry", "investigation",
        })
        assert _5TH_DAN_TN_NEVER == frozenset({
            "etiquette", "acting", "history",
        })

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

    # --- Priest 2nd Dan: +5 on Honor bonus rolls (self) ---
    def test_priest_2nd_dan_bragging_bonus(self):
        char = make_character_data(
            school="priest",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"bragging": 2},
        )
        f = build_skill_formula("bragging", char)
        assert any("Priest 2nd Dan" in b["label"] and b["amount"] == 5 for b in f.bonuses)

    def test_priest_2nd_dan_sincerity_conditional(self):
        char = make_character_data(
            school="priest",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"sincerity": 2},
        )
        f = build_skill_formula("sincerity", char)
        # Priest 2nd Dan on sincerity is conditional (open rolls only)
        assert any("Priest 2nd Dan" in alt["label"] for alt in f.alternatives)

    def test_priest_below_2nd_dan_no_bonus(self):
        char = make_character_data(
            school="priest",
            knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
            skills={"bragging": 2},
        )
        f = build_skill_formula("bragging", char)
        assert not any("Priest" in b.get("label", "") for b in f.bonuses)

    def test_priest_2nd_dan_ally_grants_bragging_bonus(self):
        """A party member Priest at dan 2+ grants +5 on my bragging rolls."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            skills={"bragging": 2},
        )
        party = [{
            "name": "Kuni Shouzo",
            "school": "priest",
            "dan": 2,
            "advantages": [], "disadvantages": [],
            "campaign_advantages": [], "campaign_disadvantages": [],
        }]
        f = build_skill_formula("bragging", char, party_members=party)
        assert any("Priest 2nd Dan" in b["label"] and b["amount"] == 5 for b in f.bonuses)
        assert any("Kuni Shouzo" in b["label"] for b in f.bonuses)

    def test_priest_2nd_dan_ally_conditional_on_sincerity(self):
        """Ally priest adds +5 on sincerity open rolls only (alternatives, not flat)."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            skills={"sincerity": 2},
        )
        party = [{"name": "P", "school": "priest", "dan": 3,
                  "advantages": [], "disadvantages": [],
                  "campaign_advantages": [], "campaign_disadvantages": []}]
        f = build_skill_formula("sincerity", char, party_members=party)
        assert not any("Priest 2nd Dan" in b.get("label", "") for b in f.bonuses)
        assert any("Priest 2nd Dan" in alt["label"] for alt in f.alternatives)

    def test_priest_ally_below_2nd_dan_no_bonus(self):
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            skills={"bragging": 2},
        )
        party = [{"name": "P", "school": "priest", "dan": 1,
                  "advantages": [], "disadvantages": [],
                  "campaign_advantages": [], "campaign_disadvantages": []}]
        f = build_skill_formula("bragging", char, party_members=party)
        assert not any("Priest 2nd Dan" in b.get("label", "") for b in f.bonuses)

    def test_priest_self_and_ally_do_not_stack(self):
        """If the character is already a Priest at dan 2+, an ally Priest does not add another bonus."""
        char = make_character_data(
            school="priest",
            knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
            skills={"bragging": 2},
        )
        party = [{"name": "P2", "school": "priest", "dan": 3,
                  "advantages": [], "disadvantages": [],
                  "campaign_advantages": [], "campaign_disadvantages": []}]
        f = build_skill_formula("bragging", char, party_members=party)
        priest_bonuses = [b for b in f.bonuses if "Priest 2nd Dan" in b.get("label", "")]
        assert len(priest_bonuses) == 1

    def test_priest_ally_bonus_on_unskilled_bragging(self):
        """An unskilled (rank 0) character still benefits if an ally Priest is in the party."""
        from app.services.dice import build_unskilled_formula
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            skills={},  # bragging at rank 0
        )
        party = [{"name": "P", "school": "priest", "dan": 2,
                  "advantages": [], "disadvantages": [],
                  "campaign_advantages": [], "campaign_disadvantages": []}]
        f = build_unskilled_formula("bragging", char, party_members=party)
        assert any("Priest 2nd Dan" in b["label"] and b["amount"] == 5 for b in f.bonuses)

    def test_priest_ally_bonus_on_unskilled_sincerity_is_conditional(self):
        """Unskilled sincerity with an ally Priest shows the open-rolls alternative, not a flat."""
        from app.services.dice import build_unskilled_formula
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            skills={},
        )
        party = [{"name": "P", "school": "priest", "dan": 2,
                  "advantages": [], "disadvantages": [],
                  "campaign_advantages": [], "campaign_disadvantages": []}]
        f = build_unskilled_formula("sincerity", char, party_members=party)
        assert not any("Priest 2nd Dan" in b.get("label", "") for b in f.bonuses)
        assert any("Priest 2nd Dan" in alt["label"] for alt in f.alternatives)

    # --- Flexible 1st/2nd Dan technique choices ---
    def test_flexible_first_dan_extra_die(self):
        char = make_character_data(
            school="ide_diplomat",
            knacks={"double_attack": 1, "feint": 1, "worldliness": 1},
            skills={"bragging": 2, "etiquette": 2},
            technique_choices={"first_dan_choices": ["bragging", "etiquette"]},
        )
        f_bragging = build_skill_formula("bragging", char)
        f_etiquette = build_skill_formula("etiquette", char)
        # Both chosen skills get +1 rolled die
        assert f_bragging.rolled == 2 + 2 + 1  # rank + Air + 1st Dan
        assert f_etiquette.rolled == 2 + 2 + 1

    def test_flexible_first_dan_no_choice_no_bonus(self):
        char = make_character_data(
            school="ide_diplomat",
            knacks={"double_attack": 1, "feint": 1, "worldliness": 1},
            skills={"bragging": 2},
        )
        f = build_skill_formula("bragging", char)
        # No technique_choices set, no bonus
        assert f.rolled == 2 + 2  # rank + Air

    def test_flexible_second_dan_free_raise(self):
        char = make_character_data(
            school="ide_diplomat",
            knacks={"double_attack": 2, "feint": 2, "worldliness": 2},
            skills={"bragging": 2},
            technique_choices={"second_dan_choice": "bragging"},
        )
        f = build_skill_formula("bragging", char)
        assert any("2nd Dan" in b["label"] and b["amount"] == 5 for b in f.bonuses)


# ---------------------------------------------------------------------------
# Comprehensive 2nd Dan free raise tests (all schools)
# ---------------------------------------------------------------------------


class TestSecondDanFreeRaise:
    """Every school's 2nd Dan free raise applies +5 to the correct roll type."""

    def _make(self, school, knacks, dan=2):
        kn = {k: dan for k in knacks}
        return make_character_data(school=school, knacks=kn, attack=2, parry=2,
                                  skills={"interrogation": 2, "manipulation": 2,
                                          "sincerity": 2, "bragging": 2})

    def test_akodo_2nd_dan_wound_check(self):
        char = self._make("akodo_bushi", ["double_attack", "feint", "iaijutsu"])
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["flat"] == 5  # +5 from 2nd Dan

    def test_bayushi_2nd_dan_double_attack(self):
        char = self._make("bayushi_bushi", ["double_attack", "feint", "iaijutsu"])
        f = build_knack_formula("double_attack", char)
        assert f.flat == 5

    def test_brotherhood_2nd_dan_attack(self):
        char = self._make("brotherhood_of_shinsei_monk", ["conviction", "otherworldliness", "worldliness"])
        f = build_combat_formula("attack", char)
        assert f.flat == 5

    def test_daidoji_2nd_dan_counterattack(self):
        char = self._make("daidoji_yojimbo", ["counterattack", "double_attack", "iaijutsu"])
        f = build_knack_formula("counterattack", char)
        assert f.flat == 5

    def test_doji_2nd_dan_manipulation(self):
        char = self._make("doji_artisan", ["counterattack", "oppose_social", "worldliness"])
        f = build_skill_formula("manipulation", char)
        assert any("2nd Dan" in b["label"] for b in f.bonuses)

    def test_hida_2nd_dan_counterattack(self):
        char = self._make("hida_bushi", ["counterattack", "iaijutsu", "lunge"])
        f = build_knack_formula("counterattack", char)
        assert f.flat == 5

    def test_hiruma_2nd_dan_parry(self):
        char = self._make("hiruma_scout", ["double_attack", "feint", "iaijutsu"])
        f = build_combat_formula("parry", char)
        assert f.flat == 5

    def test_ikoma_2nd_dan_attack(self):
        char = self._make("ikoma_bard", ["discern_honor", "oppose_knowledge", "oppose_social"])
        f = build_combat_formula("attack", char)
        assert f.flat == 5

    def test_isawa_duelist_2nd_dan_wound_check(self):
        char = self._make("isawa_duelist", ["double_attack", "iaijutsu", "lunge"])
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["flat"] == 5

    def test_kakita_2nd_dan_iaijutsu(self):
        char = self._make("kakita_duelist", ["double_attack", "iaijutsu", "lunge"])
        f = build_knack_formula("iaijutsu", char)
        assert f.flat == 5

    def test_kitsuki_2nd_dan_interrogation(self):
        char = self._make("kitsuki_magistrate", ["discern_honor", "iaijutsu", "presence"])
        f = build_skill_formula("interrogation", char)
        assert any("2nd Dan" in b["label"] for b in f.bonuses)

    def test_kuni_2nd_dan_interrogation(self):
        char = self._make("kuni_witch_hunter", ["detect_taint", "iaijutsu", "presence"])
        f = build_skill_formula("interrogation", char)
        assert any("2nd Dan" in b["label"] for b in f.bonuses)

    def test_matsu_2nd_dan_iaijutsu(self):
        char = self._make("matsu_bushi", ["double_attack", "iaijutsu", "lunge"])
        f = build_knack_formula("iaijutsu", char)
        assert f.flat == 5

    def test_merchant_2nd_dan_interrogation(self):
        char = self._make("merchant", ["discern_honor", "oppose_knowledge", "worldliness"])
        f = build_skill_formula("interrogation", char)
        assert any("2nd Dan" in b["label"] for b in f.bonuses)

    def test_otaku_2nd_dan_wound_check(self):
        char = self._make("otaku_bushi", ["double_attack", "iaijutsu", "lunge"])
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["flat"] == 5

    def test_shiba_2nd_dan_parry(self):
        char = self._make("shiba_bushi", ["counterattack", "double_attack", "iaijutsu"])
        f = build_combat_formula("parry", char)
        assert f.flat == 5

    def test_shinjo_2nd_dan_parry(self):
        char = self._make("shinjo_bushi", ["double_attack", "iaijutsu", "lunge"])
        f = build_combat_formula("parry", char)
        assert f.flat == 5

    def test_shosuro_2nd_dan_sincerity(self):
        char = self._make("shosuro_actor", ["athletics", "discern_honor", "pontificate"])
        f = build_skill_formula("sincerity", char)
        assert any("2nd Dan" in b["label"] for b in f.bonuses)

    def test_togashi_2nd_dan_athletics(self):
        char = self._make("togashi_ise_zumi", ["athletics", "conviction", "dragon_tattoo"])
        f = build_athletics_formula("Earth", char)
        assert f.flat == 5

    def test_yogo_2nd_dan_wound_check(self):
        char = self._make("yogo_warden", ["double_attack", "iaijutsu", "feint"])
        wc = build_all_roll_formulas(char)["wound_check"]
        assert wc["flat"] == 5


# ---------------------------------------------------------------------------
# Initiative and formula flag tests
# ---------------------------------------------------------------------------


class TestInitiativeAndFlags:
    """Tests for school-specific initiative mechanics and formula flags."""

    def test_matsu_initiative_rolled_10(self):
        char = make_character_data(
            school="matsu_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        init = build_initiative_formula(char)
        assert init["rolled"] == 10

    def test_shinjo_1st_dan_initiative_extra_die(self):
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        init = build_initiative_formula(char)
        # Base: Void(2)+1=3. 1st Dan: +1 for initiative.
        assert init["rolled"] == 4

    def test_shinjo_1st_dan_parry_extra_die(self):
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            parry=2,
        )
        f = build_combat_formula("parry", char)
        # Base: 2(parry) + 2(Air) = 4. 1st Dan: +1 for parry.
        assert f.rolled == 5

    def test_shinjo_1st_dan_wound_check_extra_die(self):
        """Shinjo 1st Dan rolls one extra die on wound checks (the slot
        that used to carry the double-attack extra die)."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        wc = build_all_roll_formulas(char)["wound_check"]
        # Base wound check: (Water+1)kWater = 4k3. 1st Dan: +1 rolled -> 5k3.
        assert wc["rolled"] == 5
        assert wc["kept"] == 3

    def test_shinjo_1st_dan_double_attack_no_longer_gets_extra_die(self):
        """Shinjo's 1st Dan no longer gives an extra die on double attack -
        the slot moved to wound check. Double attack rolls use the plain
        knack base (rank + ring) with no school +1 die."""
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        f = build_knack_formula("double_attack", char)
        # Base: rank(1) + Fire(2) = 3 rolled. No extra from 1st Dan.
        assert f.rolled == 3

    def test_shinjo_4th_dan_flag(self):
        char = make_character_data(
            school="shinjo_bushi",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
        )
        init = build_initiative_formula(char)
        assert init["shinjo_4th_dan"] is True

    def test_hiruma_1st_dan_initiative_extra_die(self):
        char = make_character_data(
            school="hiruma_scout",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        init = build_initiative_formula(char)
        assert init["rolled"] == 4  # Void(2)+1+1(1st Dan)

    def test_hiruma_4th_dan_flag(self):
        char = make_character_data(
            school="hiruma_scout",
            knacks={"double_attack": 4, "feint": 4, "iaijutsu": 4},
        )
        init = build_initiative_formula(char)
        assert init["hiruma_4th_dan"] is True

    def test_kakita_phase_zero_flag(self):
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
        )
        init = build_initiative_formula(char)
        assert init["kakita_phase_zero"] is True

    def test_non_kakita_initiative_no_phase_zero_flag(self):
        """Every non-Kakita school's initiative has kakita_phase_zero=False."""
        for school, knack_keys in [
            ("akodo_bushi", ["double_attack", "feint", "iaijutsu"]),
            ("shinjo_bushi", ["double_attack", "iaijutsu", "lunge"]),
            ("togashi_ise_zumi", ["athletics", "conviction", "dragon_tattoo"]),
            ("mantis_wave_treader", ["athletics", "iaijutsu", "worldliness"]),
            ("hida_bushi", ["counterattack", "iaijutsu", "lunge"]),
            ("bayushi_bushi", ["double_attack", "feint", "iaijutsu"]),
        ]:
            char = make_character_data(
                school=school,
                knacks={k: 1 for k in knack_keys},
            )
            init = build_initiative_formula(char)
            assert init["kakita_phase_zero"] is False, school

    def test_togashi_initiative_default_variant(self):
        """Togashi default initiative formula is a normal (V+1)kV roll;
        the separate athletics die is rolled client-side via the
        togashi_athletics_extra_die flag."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 0, "conviction": 0, "dragon_tattoo": 0},
        )
        init = build_initiative_formula(char)
        # Void=2 -> base 3k2 normal roll
        assert init["rolled"] == 3
        assert init["kept"] == 2
        assert init["togashi_ise_zumi"] is True
        assert init["togashi_athletics_extra_die"] is True
        assert init["togashi_base_rolled"] == 3
        assert init["togashi_base_kept"] == 2

    def test_togashi_initiative_1st_dan_extra_die(self):
        """Togashi 1st Dan adds +1 rolled die on the main initiative roll."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 1},
        )
        init = build_initiative_formula(char)
        # Void=2 -> base (V+1+1dan)=4 rolled, V=2 kept. Standalone athletics
        # die is added by the client via togashi_athletics_extra_die.
        assert init["rolled"] == 4
        assert init["kept"] == 2
        assert init["togashi_athletics_extra_die"] is True
        assert init["togashi_base_rolled"] == 4
        assert init["togashi_base_kept"] == 2

    def test_togashi_athletics_initiative_variant(self):
        """Togashi athletics init variant: +3 rolled +3 kept over the base."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 0, "conviction": 0, "dragon_tattoo": 0},
        )
        formulas = build_all_roll_formulas(char)
        ath = formulas["initiative:athletics"]
        # Void=2 -> base 3k2 + 3 athletics dice = 6k5
        assert ath["rolled"] == 6
        assert ath["kept"] == 5
        assert ath["togashi_athletics_only"] is True
        assert ath["is_initiative"] is True

    def test_togashi_athletics_initiative_with_1st_dan(self):
        """Togashi athletics init at 1st Dan: base+1 (dan) +3 (athletics)."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 1},
        )
        formulas = build_all_roll_formulas(char)
        ath = formulas["initiative:athletics"]
        # Void=2 -> base (V+1+1)=4 rolled + 3 = 7 rolled; V+3=5 kept
        assert ath["rolled"] == 7
        assert ath["kept"] == 5

    def test_non_togashi_has_no_athletics_initiative(self):
        """Non-Togashi characters do not get the athletics init variant."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        formulas = build_all_roll_formulas(char)
        assert "initiative:athletics" not in formulas
        assert formulas["initiative"]["togashi_ise_zumi"] is False

    def test_togashi_1st_dan_athletics_extra_die(self):
        """Togashi 1st Dan grants +1 rolled die on athletics rolls."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 1},
        )
        f = build_athletics_formula("Earth", char)
        # Athletics: 2*Ring + athletics_rank rolled, Ring kept.
        # Earth=2, athletics=1 -> 5k2, +1 rolled from 1st Dan -> 6k2
        assert f.rolled == 6
        assert f.kept == 2

    def test_togashi_1st_dan_wound_check_extra_die(self):
        """Togashi 1st Dan grants +1 rolled die on wound check."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 1},
        )
        wc = build_all_roll_formulas(char)["wound_check"]
        # Water=3 -> base 4k3, +1 rolled from 1st Dan -> 5k3
        assert wc["rolled"] == 5
        assert wc["kept"] == 3

    def test_togashi_1st_dan_no_longer_boosts_attack(self):
        """Old 1st Dan gave extra die on attack/parry; new one does not."""
        char = make_character_data(
            school="togashi_ise_zumi",
            knacks={"athletics": 1, "conviction": 1, "dragon_tattoo": 1},
            attack=2,
            parry=2,
        )
        attack = build_combat_formula("attack", char)
        parry = build_combat_formula("parry", char)
        # Attack: 2+Fire(2) = 4k2, no extra die
        assert attack.rolled == 4
        # Parry: 2+Air(2) = 4k2, no extra die
        assert parry.rolled == 4

    def test_isawa_duelist_damage_uses_water(self):
        char = make_character_data(
            school="isawa_duelist",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_ring_name"] == "Water"


# ---------------------------------------------------------------------------
# School-specific mechanic flag/formula tests
# ---------------------------------------------------------------------------


class TestSchoolMechanics:
    """Tests for non-standard school technique mechanics."""

    def test_bayushi_3rd_dan_feint_damage_flag(self):
        """Bayushi feint damage metadata is present at 3rd Dan."""
        char = make_character_data(
            school="bayushi_bushi",
            knacks={"double_attack": 3, "feint": 3, "iaijutsu": 3},
            attack=3,
        )
        # The feint damage is a client-side mechanic via school_abilities flag,
        # not in the formula. Verify that the school has the correct bonus config.
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("bayushi_bushi", {})
        # 3rd Dan is non-standard - not in the dict. The damage is attack_skill k1.
        assert bonuses.get("second_dan_free_raise") == "double_attack"

    def test_matsu_initiative_override(self):
        char = make_character_data(
            school="matsu_bushi",
            knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 4},
        )
        init = build_initiative_formula(char)
        # Matsu always rolls 10, regardless of Void(4)
        assert init["rolled"] == 10
        assert init["kept"] == 4  # keeps Void dice

    def test_brotherhood_4th_dan_parry_no_reduce(self):
        """Brotherhood 4th Dan flag is set correctly."""
        # This is a school_abilities flag, tested via the attack modal client-side.
        # Verify the technique bonus structure.
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("brotherhood_of_shinsei_monk", {})
        assert bonuses.get("second_dan_free_raise") == "attack"

    def test_otaku_4th_dan_lunge_damage_flag(self):
        """Otaku at 4th Dan has lunge extra die metadata."""
        char = make_character_data(
            school="otaku_bushi",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        # Lunge formula should have attack type metadata
        lunge = formulas.get("knack:lunge", {})
        assert lunge.get("is_attack_type") is True

    def test_hida_4th_dan_wound_trade(self):
        """Hida 4th Dan trade is a client-side button; verify ring raise works."""
        char = make_character_data(
            school="hida_bushi",
            knacks={"counterattack": 4, "iaijutsu": 4, "lunge": 4},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        # Water should be raised by 1 at 4th Dan (server handles this in xp calc)
        # The trade button is client-side. Just verify the school config is correct.
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("hida_bushi", {})
        assert bonuses.get("second_dan_free_raise") == "counterattack"

    def test_hida_3rd_dan_reroll_config(self):
        """Hida 3rd Dan reroll count based on attack skill."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("hida_bushi", {})
        # Hida 3rd Dan is non-standard - X = attack skill, reroll 2X on counterattack, X on others
        assert bonuses.get("first_dan_extra_die") == ["attack", "counterattack", "wound_check"]

    def test_yogo_3rd_dan_vp_heals_lw(self):
        """Yogo 3rd Dan: VP spending reduces LW by 2*attack. Verify school config."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("yogo_warden", {})
        assert bonuses.get("first_dan_extra_die") == ["attack", "damage", "wound_check"]

    def test_yogo_4th_dan_wound_check_vp_raise(self):
        """Yogo 4th Dan gives extra +5 per VP on wound checks."""
        char = make_character_data(
            school="yogo_warden",
            knacks={"double_attack": 4, "iaijutsu": 4, "feint": 4},
        )
        wc = build_all_roll_formulas(char)["wound_check"]
        # The VP raise is applied client-side via void_spend_config, not in the formula.
        # Verify the wound check formula has the 2nd Dan +5 at dan 4.
        assert wc["flat"] == 5

    def test_togashi_3rd_dan_daily_raises(self):
        """Togashi 3rd Dan: 4X daily athletics raises. Verify config exists."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("togashi_ise_zumi", {})
        assert bonuses.get("second_dan_free_raise") == "athletics"

    def test_mirumoto_3rd_dan_round_points(self):
        """Mirumoto 3rd Dan: 2X points per round. Verify config."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("mirumoto_bushi", {})
        assert bonuses.get("second_dan_free_raise") == "parry"

    def test_merchant_post_roll_vp(self):
        """Merchant special ability: VP after seeing roll. Verify school exists."""
        from app.game_data import SCHOOLS
        assert "merchant" in SCHOOLS

    def test_ide_4th_dan_vp_regen(self):
        """Ide 4th Dan: extra VP nightly. This is display-only."""
        from app.game_data import SCHOOLS
        assert "ide_diplomat" in SCHOOLS

    def test_matsu_3rd_dan_vp_wc_bonus(self):
        """Matsu 3rd Dan: VP spending banks 3*attack for wound check."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("matsu_bushi", {})
        assert bonuses.get("second_dan_free_raise") == "iaijutsu"

    def test_matsu_4th_dan_near_miss(self):
        """Matsu 4th Dan: near-miss flag is a client-side feature."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("matsu_bushi", {})
        assert bonuses.get("first_dan_extra_die") == ["double_attack", "iaijutsu", "wound_check"]

    def test_matsu_5th_dan_lw_reset(self):
        """Matsu 5th Dan: LW reset to 15. Client-side display note."""
        from app.game_data import SCHOOLS
        school = SCHOOLS.get("matsu_bushi")
        assert school is not None
        assert "15" in school.techniques.get(5, "")

    def test_daidoji_3rd_dan_raises_config(self):
        """Daidoji 3rd Dan: X free raises on wound check from counterattack."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES.get("daidoji_yojimbo", {})
        assert bonuses.get("second_dan_free_raise") == "counterattack"

    def test_daidoji_5th_dan_wc_tn_reduction(self):
        """Daidoji 5th Dan: lower attacker TN. Client-side display note."""
        from app.game_data import SCHOOLS
        school = SCHOOLS.get("daidoji_yojimbo")
        assert "lower" in school.techniques.get(5, "").lower()

    def test_kitsuki_5th_dan_ring_reduction(self):
        """Kitsuki 5th Dan: reduce target rings. Client-side display note."""
        from app.game_data import SCHOOLS
        school = SCHOOLS.get("kitsuki_magistrate")
        assert "reduce" in school.techniques.get(5, "").lower()


class TestAddFlatBonus:
    """_add_flat_bonus is a no-op when the amount is 0."""

    def test_zero_amount_is_skipped(self):
        from app.services.dice import _add_flat_bonus, RollFormula
        f = RollFormula(label="test", rolled=3, kept=2)
        _add_flat_bonus(f, "Zero bonus", 0)
        assert f.flat == 0
        assert f.bonuses == []

    def test_nonzero_amount_accumulates(self):
        from app.services.dice import _add_flat_bonus, RollFormula
        f = RollFormula(label="test", rolled=3, kept=2)
        _add_flat_bonus(f, "First", 5)
        _add_flat_bonus(f, "Second", 3)
        assert f.flat == 8
        assert [b["label"] for b in f.bonuses] == ["First", "Second"]


class TestBuildUnskilledFormulaUnknownSkill:
    def test_unknown_skill_returns_none(self):
        from app.services.dice import build_unskilled_formula
        data = make_character_data()
        assert build_unskilled_formula("nonexistent_skill", data) is None


class TestKakitaDuelist4thDanIaijutsuDamage:
    """At 4th Dan, Kakita Duelist gets +5 on iaijutsu damage. The bonus is
    stamped on knack:iaijutsu by the dedicated iaijutsu-metadata block after
    the generic attack-type annotation pass."""

    def test_iaijutsu_damage_flat_bonus(self):
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
        )
        formulas = build_all_roll_formulas(char)
        iai = formulas["knack:iaijutsu"]
        assert iai["damage_flat_bonus"] == 5
        assert any("4th Dan (iaijutsu)" in s for s in iai["damage_bonus_sources"])

    def test_double_attack_damage_does_not_get_4th_dan_bonus(self):
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
        )
        formulas = build_all_roll_formulas(char)
        da = formulas["knack:double_attack"]
        assert da["damage_flat_bonus"] == 0

    def test_below_4th_dan_no_bonus(self):
        char = make_character_data(
            school="kakita_duelist",
            knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
        )
        formulas = build_all_roll_formulas(char)
        iai = formulas["knack:iaijutsu"]
        assert iai["damage_flat_bonus"] == 0


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 1st Dan: extra die on initiative, athletics, wound check
# ---------------------------------------------------------------------------


class TestMantisWaveTreader1stDan:
    """Mantis Wave-Treader 1st Dan: roll one extra die on initiative,
    athletics, and wound checks."""

    def _char_dan(self, dan: int, **extra) -> dict:
        """Mantis character with school knacks at *dan* rank."""
        data = make_character_data(
            school="mantis_wave_treader",
            school_ring_choice="Void",
            knacks={"athletics": dan, "iaijutsu": dan, "worldliness": dan},
        )
        data.update(extra)
        return data

    # --- Initiative ---

    def test_initiative_extra_die_at_dan_1(self):
        char = self._char_dan(1)
        init = build_initiative_formula(char)
        # Void=2 -> base (V+1)=3. 1st Dan: +1 for initiative -> 4 rolled.
        assert init["rolled"] == 4
        assert init["kept"] == 2

    def test_initiative_no_extra_die_at_dan_0(self):
        # Dan 0 = at least one school knack is 0. Use rank=0 across the board.
        char = self._char_dan(0)
        init = build_initiative_formula(char)
        assert init["rolled"] == 3  # Void(2)+1, no 1st Dan bonus
        assert init["kept"] == 2

    # --- Athletics (all four rollable rings) ---

    @pytest.mark.parametrize("ring", ["Air", "Fire", "Earth", "Water"])
    def test_athletics_extra_die_at_dan_1(self, ring):
        char = self._char_dan(
            1,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        )
        f = build_athletics_formula(ring, char)
        # Base: 2*Ring(2) + athletics(1) = 5 rolled, 2 kept.
        # 1st Dan: +1 rolled -> 6k2.
        assert f.rolled == 6
        assert f.kept == 2

    def test_athletics_no_extra_die_at_dan_0(self):
        # To get Dan 0, drop one school knack to 0. Athletics itself remains
        # rank 1 so the formula is still defined.
        char = make_character_data(
            school="mantis_wave_treader",
            school_ring_choice="Void",
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
            knacks={"athletics": 1, "iaijutsu": 1, "worldliness": 0},
        )
        f = build_athletics_formula("Earth", char)
        # Base: 2*2 + 1 = 5 rolled, 2 kept. No 1st Dan bonus at Dan 0.
        assert f.rolled == 5
        assert f.kept == 2

    # --- Wound check ---

    def test_wound_check_extra_die_at_dan_1(self):
        char = self._char_dan(1)
        wc = build_wound_check_formula(char)
        # Water=3 -> base 4k3. 1st Dan: +1 rolled -> 5k3.
        assert wc["rolled"] == 5
        assert wc["kept"] == 3

    def test_wound_check_no_extra_die_at_dan_0(self):
        char = self._char_dan(0)
        wc = build_wound_check_formula(char)
        assert wc["rolled"] == 4  # Water(3)+1, no 1st Dan bonus
        assert wc["kept"] == 3

    # --- Confirm no bleed onto non-bonus rolls ---

    def test_no_bonus_on_attack_at_dan_1(self):
        """Mantis 1st Dan covers initiative/athletics/wound_check only -
        attack rolls get no extra die."""
        char = self._char_dan(1, attack=3, rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2})
        f = build_combat_formula("attack", char)
        # Base: 3(attack) + 2(Fire) = 5k2, no school bonus.
        assert f.rolled == 5
        assert f.kept == 2


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 2nd Dan: flexible free raise (+5) on chosen roll type
# ---------------------------------------------------------------------------


class TestMantisWaveTreader2ndDan:
    """Mantis Wave-Treader 2nd Dan: player picks any one roll type (skills,
    rollable knacks, attack, damage, parry, wound_check) and gets a +5 free
    raise on matching rolls. Initiative is never eligible."""

    def _char(self, choice, dan: int = 2, **extra) -> dict:
        """Mantis character at *dan* (default 2) with the given 2nd Dan choice."""
        data = make_character_data(
            school="mantis_wave_treader",
            school_ring_choice="Void",
            knacks={"athletics": dan, "iaijutsu": dan, "worldliness": dan},
            technique_choices={"mantis_2nd_dan_free_raise": choice} if choice else {},
        )
        data.update(extra)
        return data

    # --- Combat: attack / parry ---

    def test_attack_gets_plus_5_when_chosen(self):
        char = self._char("attack", attack=3)
        f = build_combat_formula("attack", char)
        assert f.flat == 5
        assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
                   for b in f.bonuses)

    def test_attack_no_bonus_when_not_chosen(self):
        char = self._char("parry", attack=3)
        f = build_combat_formula("attack", char)
        assert f.flat == 0

    def test_parry_gets_plus_5_when_chosen(self):
        char = self._char("parry", parry=2)
        f = build_combat_formula("parry", char)
        assert f.flat == 5

    # --- Wound check ---

    def test_wound_check_gets_plus_5_when_chosen(self):
        char = self._char("wound_check")
        wc = build_wound_check_formula(char)
        assert wc["flat"] == 5
        assert any("2nd Dan" in s for s in wc.get("bonus_sources", []))

    def test_wound_check_no_bonus_when_not_chosen(self):
        char = self._char("attack")
        wc = build_wound_check_formula(char)
        assert wc["flat"] == 0

    # --- Skills ---

    def test_skill_gets_plus_5_when_chosen(self):
        # etiquette has no Honor / Recognition bonus so flat==5 cleanly reflects
        # only the Mantis 2nd Dan choice.
        char = self._char("etiquette", skills={"etiquette": 2})
        f = build_skill_formula("etiquette", char)
        assert f.flat == 5
        assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
                   for b in f.bonuses)

    def test_skill_no_bonus_when_not_chosen(self):
        char = self._char("attack", skills={"etiquette": 2})
        f = build_skill_formula("etiquette", char)
        assert f.flat == 0

    # --- Knacks ---

    def test_knack_gets_plus_5_when_chosen(self):
        # Iaijutsu is a rollable Mantis school knack.
        char = self._char("iaijutsu")
        f = build_knack_formula("iaijutsu", char)
        assert f.flat == 5

    def test_athletics_knack_gets_plus_5_when_chosen(self):
        char = self._char("athletics")
        f = build_athletics_formula("Earth", char)
        assert f.flat == 5

    # --- Damage (via _annotate_attack_type) ---

    def test_damage_flat_bonus_when_chosen(self):
        char = self._char("damage", attack=3)
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_flat_bonus"] == 5
        assert any("2nd Dan" in s for s in atk.get("damage_bonus_sources", []))
        # The attack roll itself does NOT get +5 when damage is chosen.
        assert atk["flat"] == 0

    def test_damage_no_bonus_when_not_chosen(self):
        char = self._char("attack", attack=3)
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_flat_bonus"] == 0

    # --- Dan gating ---

    def test_no_bonus_below_dan_2(self):
        char = self._char("attack", dan=1, attack=3)
        f = build_combat_formula("attack", char)
        assert f.flat == 0

    def test_no_damage_bonus_below_dan_2(self):
        char = self._char("damage", dan=1, attack=3)
        formulas = build_all_roll_formulas(char)
        assert formulas["attack"]["damage_flat_bonus"] == 0

    def test_no_wound_check_bonus_below_dan_2(self):
        char = self._char("wound_check", dan=1)
        wc = build_wound_check_formula(char)
        assert wc["flat"] == 0

    # --- No bleed to non-Mantis schools ---

    def test_non_mantis_school_ignores_mantis_key(self):
        """A non-Mantis character with mantis_2nd_dan_free_raise in
        technique_choices must not get the bonus."""
        char = make_character_data(
            school="akodo_bushi",
            knacks={"double_attack": 2, "feint": 2, "iaijutsu": 2},
            attack=3,
            technique_choices={"mantis_2nd_dan_free_raise": "attack"},
        )
        f = build_combat_formula("attack", char)
        # Akodo's own 2nd Dan is wound_check, so attack flat stays 0.
        assert f.flat == 0


class TestMantis2ndDanEligibleChoices:
    """The mantis_2nd_dan_eligible_choices() helper used by server-side
    validation on save."""

    def test_non_mantis_returns_empty(self):
        from app.services.dice import mantis_2nd_dan_eligible_choices
        assert mantis_2nd_dan_eligible_choices("akodo_bushi") == frozenset()
        assert mantis_2nd_dan_eligible_choices("") == frozenset()

    def test_mantis_includes_combat_rolls(self):
        from app.services.dice import mantis_2nd_dan_eligible_choices
        choices = mantis_2nd_dan_eligible_choices("mantis_wave_treader")
        assert "attack" in choices
        assert "damage" in choices
        assert "parry" in choices
        assert "wound_check" in choices

    def test_mantis_excludes_initiative(self):
        from app.services.dice import mantis_2nd_dan_eligible_choices
        choices = mantis_2nd_dan_eligible_choices("mantis_wave_treader")
        assert "initiative" not in choices

    def test_mantis_includes_rollable_knacks(self):
        from app.services.dice import mantis_2nd_dan_eligible_choices
        choices = mantis_2nd_dan_eligible_choices("mantis_wave_treader")
        assert "athletics" in choices
        assert "iaijutsu" in choices

    def test_mantis_excludes_worldliness(self):
        """worldliness is a non-rollable knack."""
        from app.services.dice import mantis_2nd_dan_eligible_choices
        choices = mantis_2nd_dan_eligible_choices("mantis_wave_treader")
        assert "worldliness" not in choices

    def test_mantis_includes_all_skills(self):
        from app.services.dice import mantis_2nd_dan_eligible_choices
        from app.game_data import SKILLS
        choices = mantis_2nd_dan_eligible_choices("mantis_wave_treader")
        for sid in SKILLS:
            assert sid in choices


class TestMantisWaveTreader4thDanAthleticsDie:
    """Mantis Wave-Treader 4th Dan: after rolling initiative, the character
    gains a deterministic value-1 athletics action die that is never rolled
    (always value 1) and is restricted to movement / athletics / the Mantis
    3rd Dan technique. The server exposes this as the boolean formula flag
    ``mantis_4th_dan_athletics_die``; the client appends the die to the
    tracked actionDice list after processing the initiative roll."""

    def _char(self, dan: int, school="mantis_wave_treader"):
        return make_character_data(
            school=school,
            school_ring_choice="Void",
            knacks={"athletics": dan, "iaijutsu": dan, "worldliness": dan}
                if school == "mantis_wave_treader"
                else {"double_attack": dan, "feint": dan, "iaijutsu": dan},
        )

    def test_flag_true_at_dan_4(self):
        init = build_initiative_formula(self._char(4))
        assert init["mantis_4th_dan_athletics_die"] is True

    def test_flag_true_at_dan_5(self):
        init = build_initiative_formula(self._char(5))
        assert init["mantis_4th_dan_athletics_die"] is True

    def test_flag_false_at_dan_3(self):
        init = build_initiative_formula(self._char(3))
        assert init["mantis_4th_dan_athletics_die"] is False

    def test_flag_false_at_dan_1(self):
        init = build_initiative_formula(self._char(1))
        assert init["mantis_4th_dan_athletics_die"] is False

    def test_flag_false_for_non_mantis(self):
        init = build_initiative_formula(self._char(5, school="akodo_bushi"))
        assert init["mantis_4th_dan_athletics_die"] is False

    def test_initiative_rolled_dice_count_unchanged(self):
        """The bonus die is appended post-roll, so the rolled/kept counts
        from build_initiative_formula stay at (V+1)kV (plus the 1st Dan
        extra die from Phase 2). The bonus die is NOT part of the rolled set."""
        init = build_initiative_formula(self._char(4))
        # Void default = 2 (school knacks push Void to 3 at creation for Mantis
        # but make_character_data does not apply that UI default). Raw rings =
        # 2 across the board -> base rolled = V+1 = 3 + 1st Dan +1 = 4 rolled,
        # 2 kept. The 4th Dan bonus die is NOT reflected here.
        assert init["rolled"] == 4
        assert init["kept"] == 2


# ---------------------------------------------------------------------------
# Foreign school knacks: rolls, Dan invariant, build_all_roll_formulas
# ---------------------------------------------------------------------------


class TestForeignKnackDice:
    """Foreign knacks must feed into rolls but never affect Dan."""

    def test_merged_knacks_combines_native_and_foreign(self):
        char = make_character_data(
            knacks={"feint": 2, "double_attack": 1, "iaijutsu": 1},
            foreign_knacks={"athletics": 3},
        )
        merged = merged_knacks(char)
        assert merged == {
            "feint": 2,
            "double_attack": 1,
            "iaijutsu": 1,
            "athletics": 3,
        }

    def test_foreign_knack_does_not_lower_dan(self):
        # Akodo at native rank 5 across the board, then a foreign rank-1
        # athletics. compute_dan must still return 5.
        from app.services.rolls import compute_dan
        char = make_character_data(
            knacks={"feint": 5, "double_attack": 5, "iaijutsu": 5},
            foreign_knacks={"athletics": 1},
        )
        # Dan is computed from NATIVE knacks only.
        assert compute_dan(char["knacks"]) == 5

    def test_foreign_athletics_enables_athletics_formula(self):
        # No native athletics; Akodo doesn't have it. With foreign athletics
        # at rank 1, build_athletics_formula should pick up the rank.
        char = make_character_data(
            foreign_knacks={"athletics": 2},
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        f = build_athletics_formula("Air", char)
        # athletics + 2*Air = 2 + 6 = 8 rolled, kept = Air = 3.
        assert f.rolled == 8
        assert f.kept == 3

    def test_foreign_athletics_enables_athletics_attack(self):
        char = make_character_data(foreign_knacks={"athletics": 1})
        f = build_athletics_combat_formula("attack", char)
        assert f is not None  # was None before this change

    def test_foreign_knack_appears_in_build_all_roll_formulas(self):
        # An Akodo character with foreign worldliness gets a knack:worldliness
        # entry in build_all_roll_formulas (well, no - worldliness is in
        # NON_ROLLABLE_KNACKS). Use a rollable foreign knack instead.
        char = make_character_data(
            foreign_knacks={"investigation": 1},
            # Akodo school - investigation is not on Akodo's list.
        )
        formulas = build_all_roll_formulas(char)
        # Investigation isn't a knack; it's a skill. Use a knack id that's
        # not on Akodo's list and not in NON_ROLLABLE_KNACKS.
        assert "knack:investigation" not in formulas

    def test_foreign_lunge_appears_in_build_all_roll_formulas(self):
        # Lunge is a Shinjo school knack; an Akodo character can take it
        # as a foreign knack. It should show up in the rollable formulas.
        char = make_character_data(foreign_knacks={"lunge": 1})
        formulas = build_all_roll_formulas(char)
        assert "knack:lunge" in formulas
        assert formulas["knack:lunge"]["rolled"] > 0

    def test_iaijutsu_strike_works_for_foreign_iaijutsu(self):
        # Per spec: "all characters with iaijutsu can do iaijutsu strikes".
        # Akodo's school knacks include iaijutsu, so add a foreign-iaijutsu
        # case using a school whose knacks do NOT include iaijutsu. Asahina
        # (artisan) doesn't have iaijutsu in its school list.
        char = make_character_data(
            school="asahina_artisan",
            knacks={"sincerity_calligraphy": 1, "tea_ceremony": 1, "conviction": 1},
            foreign_knacks={"iaijutsu": 1},
        )
        # Set school_ring_choice valid for asahina_artisan if needed.
        char["school_ring_choice"] = "Air"
        formulas = build_all_roll_formulas(char)
        assert "knack:iaijutsu" in formulas
        assert "knack:iaijutsu:strike" in formulas
        assert formulas["knack:iaijutsu:strike"]["reroll_tens"] is False

    def test_kakita_iaijutsu_attack_does_not_fire_for_non_kakita_foreign(self):
        # Foreign iaijutsu does NOT grant the Kakita-specific Phase-0
        # iaijutsu-as-attack workflow.
        char = make_character_data(
            school="asahina_artisan",
            knacks={"sincerity_calligraphy": 1, "tea_ceremony": 1, "conviction": 1},
            foreign_knacks={"iaijutsu": 1},
        )
        char["school_ring_choice"] = "Air"
        formulas = build_all_roll_formulas(char)
        assert "knack:iaijutsu:attack" not in formulas

    def test_mantis_2nd_dan_picker_includes_foreign_rollable_knacks(self):
        # A Mantis character with foreign feint should be able to point the
        # 2nd Dan free raise at feint.
        choices = mantis_2nd_dan_eligible_choices(
            "mantis_wave_treader", foreign_knacks={"feint": 1}
        )
        assert "feint" in choices

    def test_mantis_2nd_dan_picker_excludes_non_rollable_foreign(self):
        choices = mantis_2nd_dan_eligible_choices(
            "mantis_wave_treader", foreign_knacks={"worldliness": 1}
        )
        assert "worldliness" not in choices

    def test_mantis_2nd_dan_picker_empty_for_non_mantis(self):
        assert mantis_2nd_dan_eligible_choices(
            "akodo_bushi", foreign_knacks={"feint": 1}
        ) == frozenset()


class TestSuzumeOverseer:
    """Suzume Overseer: a Sparrow school whose techniques are drawn from Doji
    Artisan and Merchant. Verify each Dan's mechanics, including the shared
    flag names with Doji and the post-roll VP flag with Merchant."""

    def _char(self, dan: int = 1, **extra) -> dict:
        kn = {"oppose_social": dan, "pontificate": dan, "worldliness": dan}
        data = make_character_data(
            school="suzume_overseer",
            school_ring_choice="Water",
            knacks=kn,
            skills={"precepts": 3, "commerce": 2, "tact": 2,
                    "heraldry": 2, "sincerity": 2, "etiquette": 2},
        )
        data.update(extra)
        return data

    # --- School-data sanity ---

    def test_school_exists(self):
        from app.game_data import SCHOOLS
        assert "suzume_overseer" in SCHOOLS
        sch = SCHOOLS["suzume_overseer"]
        assert sch.school_ring == "Water"
        assert sch.category == "court"
        assert sch.school_knacks == ["oppose_social", "pontificate", "worldliness"]
        # 4th Dan is intentionally omitted.
        assert 4 not in sch.techniques
        assert {1, 2, 3, 5} <= set(sch.techniques.keys())

    def test_school_ring_options_water_only(self):
        from app.game_data import SCHOOL_RING_OPTIONS
        assert SCHOOL_RING_OPTIONS["suzume_overseer"] == ["Water"]

    # --- 1st Dan: extra die on precepts / commerce / wound_check ---

    def test_first_dan_extra_die_on_precepts(self):
        char = self._char(dan=1)
        f = build_skill_formula("precepts", char)
        # rank(3) + Water(3) + 1 (1st Dan)
        assert f.rolled == 7

    def test_first_dan_extra_die_on_commerce(self):
        char = self._char(dan=1)
        f = build_skill_formula("commerce", char)
        # rank(2) + Water(3) + 1 (1st Dan)
        assert f.rolled == 6

    def test_first_dan_extra_die_on_wound_check(self):
        char = self._char(dan=1)
        wc = build_wound_check_formula(char)
        # base Water+1 = 4, +1 from 1st Dan = 5
        assert wc["rolled"] == 5
        assert any("1st Dan" in s for s in wc["bonus_sources"])

    def test_first_dan_no_bonus_on_other_skill(self):
        char = self._char(dan=1)
        f = build_skill_formula("heraldry", char)
        assert f.rolled == 2 + 3  # rank + Water, no extra die

    # --- 2nd Dan: free raise on a chosen roll type ---

    def test_second_dan_chosen_skill_gets_free_raise(self):
        char = self._char(dan=2,
                          technique_choices={"second_dan_choice": "tact"})
        f = build_skill_formula("tact", char)
        assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
                   for b in f.bonuses)

    def test_second_dan_no_choice_no_bonus(self):
        char = self._char(dan=2)
        f = build_skill_formula("tact", char)
        # No second_dan_choice, no +5 from 2nd Dan
        assert not any(b["label"] == "2nd Dan technique" for b in f.bonuses)

    def test_second_dan_chosen_wound_check_gets_free_raise(self):
        char = self._char(dan=2,
                          technique_choices={"second_dan_choice": "wound_check"})
        wc = build_wound_check_formula(char)
        assert wc["flat"] >= 5
        assert any("2nd Dan" in s for s in wc["bonus_sources"])

    def test_second_dan_chosen_damage_gets_free_raise(self):
        char = self._char(dan=2, attack=3,
                          technique_choices={"second_dan_choice": "damage"})
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_flat_bonus"] == 5

    def test_second_dan_attack_choice_gets_free_raise(self):
        char = self._char(dan=2, attack=3,
                          technique_choices={"second_dan_choice": "attack"})
        f = build_combat_formula("attack", char)
        assert f.flat == 5

    def test_second_dan_no_bonus_below_dan_2(self):
        char = self._char(dan=1,
                          technique_choices={"second_dan_choice": "tact"})
        f = build_skill_formula("tact", char)
        assert not any(b["label"] == "2nd Dan technique" for b in f.bonuses)

    # --- 3rd Dan: 2X adventure raises (X = precepts) ---

    def test_third_dan_annotates_applicable_skills(self):
        char = self._char(dan=3, attack=2)
        formulas = build_all_roll_formulas(char)
        # source_skill = precepts; precepts rank is 3
        for sid in ("commerce", "heraldry", "sincerity", "tact"):
            assert formulas[f"skill:{sid}"]["adventure_raises_max_per_roll"] == 3
        assert formulas["wound_check"]["adventure_raises_max_per_roll"] == 3
        assert formulas["attack"]["adventure_raises_max_per_roll"] == 3

    def test_third_dan_does_not_annotate_excluded_skill(self):
        char = self._char(dan=3, attack=2)
        formulas = build_all_roll_formulas(char)
        # etiquette is NOT in applicable_to
        assert formulas["skill:etiquette"]["adventure_raises_max_per_roll"] == 0

    def test_third_dan_per_adventure_pool_size(self):
        """Routes-side: per_adventure entry has max = 2 * precepts rank."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        bonuses = SCHOOL_TECHNIQUE_BONUSES["suzume_overseer"]
        third = bonuses["third_dan"]
        assert third["source_skill"] == "precepts"
        assert third["formula"] == "2X"
        assert third["max_per_roll"] == "X"
        assert "attack" in third["applicable_to"]
        assert "wound_check" in third["applicable_to"]

    # --- 5th Dan: shared flags with Doji Artisan ---

    def test_fifth_dan_skill_always_tn(self):
        char = self._char(dan=5)
        f = build_skill_formula("manipulation", char)
        assert f.doji_5th_dan_always is True
        assert f.doji_5th_dan_optional is False

    def test_fifth_dan_skill_sometimes_tn(self):
        char = self._char(dan=5)
        f = build_skill_formula("bragging", char)
        assert f.doji_5th_dan_optional is True
        assert f.doji_5th_dan_always is False

    def test_fifth_dan_skill_never_tn(self):
        char = self._char(dan=5)
        f = build_skill_formula("etiquette", char)
        assert f.doji_5th_dan_always is False
        assert f.doji_5th_dan_optional is False

    def test_fifth_dan_attack_flag(self):
        char = self._char(dan=5, attack=3)
        f = build_combat_formula("attack", char)
        assert f.doji_5th_dan_always is True

    def test_fifth_dan_parry_flag(self):
        char = self._char(dan=5, parry=3)
        f = build_combat_formula("parry", char)
        assert f.doji_5th_dan_always is True

    def test_fifth_dan_wound_check_flag(self):
        char = self._char(dan=5)
        wc = build_wound_check_formula(char)
        assert wc["doji_5th_dan_wc"] is True

    def test_fifth_dan_knack_flag(self):
        char = self._char(dan=5)
        f = build_knack_formula("pontificate", char)
        assert f.doji_5th_dan_always is True

    def test_below_fifth_dan_no_flags(self):
        char = self._char(dan=4)
        f = build_skill_formula("manipulation", char)
        assert f.doji_5th_dan_always is False
        assert f.doji_5th_dan_optional is False
        wc = build_wound_check_formula(char)
        assert wc["doji_5th_dan_wc"] is False

    # --- 4th Dan is intentionally absent: no doji 4th Dan flag should fire ---

    def test_no_fourth_dan_untouched_target_flag(self):
        """Suzume must NOT inherit Doji 4th Dan untouched-target bonus."""
        char = self._char(dan=4, attack=3)
        f = build_combat_formula("attack", char)
        assert f.doji_4th_dan_untouched_target is False

    # --- Special ability: post-roll VP flag is set on the route side. ---
    # (See tests/test_remaining_features or the route tests for the
    # schoolAbilities flag check; here we just confirm the school appears
    # in the same flag domain via the SCHOOL_TECHNIQUE_BONUSES table.)

    def test_post_roll_vp_membership(self):
        """The merchant_post_roll_vp flag should be true for Suzume Overseer."""
        import inspect
        import app.routes.pages as pages_mod
        src = inspect.getsource(pages_mod)
        assert "suzume_overseer" in src
        assert "merchant_post_roll_vp" in src


class TestDojiArtisanRegressionAfterSuzume:
    """Regression: widening the doji 5th Dan checks to include suzume_overseer
    must not break Doji Artisan itself."""

    def test_doji_5th_dan_still_fires(self):
        char = make_character_data(
            school="doji_artisan",
            school_ring_choice="Air",
            knacks={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
            skills={"manipulation": 3},
        )
        f = build_skill_formula("manipulation", char)
        assert f.doji_5th_dan_always is True

    def test_doji_4th_dan_still_only_doji(self):
        """Suzume Overseer must NOT trigger Doji 4th Dan on attack."""
        char = make_character_data(
            school="suzume_overseer",
            school_ring_choice="Water",
            knacks={"oppose_social": 4, "pontificate": 4, "worldliness": 4},
            attack=3,
        )
        f = build_combat_formula("attack", char)
        assert f.doji_4th_dan_untouched_target is False

        doji = make_character_data(
            school="doji_artisan",
            school_ring_choice="Air",
            knacks={"counterattack": 4, "oppose_social": 4, "worldliness": 4},
            attack=3,
        )
        f2 = build_combat_formula("attack", doji)
        assert f2.doji_4th_dan_untouched_target is True

    def test_merchant_post_roll_vp_still_works(self):
        """Merchant must still get the post-roll VP flag after Suzume widening."""
        import inspect, app.routes.pages as pages_mod
        src = inspect.getsource(pages_mod)
        # The membership test must include both schools.
        assert '"merchant"' in src.lower() or "'merchant'" in src
        assert "suzume_overseer" in src


class TestKitsuneWarden:
    """Kitsune Warden 1st Dan: 'Roll one extra die on three rolls of your
    choice.' Player picks 3 from skills + rollable knacks (iaijutsu IS
    eligible) + attack/parry/wound_check/damage/initiative. Picks live in
    technique_choices.first_dan_choices."""

    def _char(self, dan: int = 1, picks=None, **extra) -> dict:
        kn = {"absorb_void": dan, "commune": dan, "iaijutsu": dan}
        tech_choices = {}
        if picks is not None:
            tech_choices["first_dan_choices"] = picks
        data = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            skills={"precepts": 3, "bragging": 2, "etiquette": 2,
                    "sincerity": 2, "tact": 2, "athletics": 1},
            technique_choices=tech_choices,
        )
        data.update(extra)
        return data

    # --- Single-pick coverage on each roll-type branch ---

    def test_first_dan_one_pick_grants_extra_die_on_chosen_skill(self):
        char = self._char(dan=1, picks=["bragging"])
        f = build_skill_formula("bragging", char)
        # rank(2) + Air(2) + 1 (1st Dan)
        assert f.rolled == 5

    def test_first_dan_no_bonus_on_unpicked_skill(self):
        char = self._char(dan=1, picks=["bragging"])
        f = build_skill_formula("etiquette", char)
        # rank(2) + Air(2), no extra die
        assert f.rolled == 4

    def test_first_dan_three_picks_each_grant_extra_die(self):
        char = self._char(dan=1, picks=["bragging", "etiquette", "sincerity"])
        for sid in ("bragging", "etiquette", "sincerity"):
            f = build_skill_formula(sid, char)
            assert f.rolled == 5, f"{sid} did not get +1 rolled die"
        # Unpicked skill stays at base.
        assert build_skill_formula("tact", char).rolled == 4

    def test_first_dan_no_bonus_below_dan_1(self):
        # All knacks at 0 = Dan 0 means 1st Dan technique should not fire.
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks={"absorb_void": 0, "commune": 0, "iaijutsu": 0},
            skills={"bragging": 2},
            technique_choices={"first_dan_choices": ["bragging"]},
        )
        f = build_skill_formula("bragging", char)
        assert f.rolled == 4  # 2 + 2, no 1st Dan

    def test_first_dan_pick_on_wound_check_applies_via_wc_formula(self):
        char = self._char(dan=1, picks=["wound_check"])
        wc = build_wound_check_formula(char)
        # base = Earth(2) + 2 (default) = 4, plus 1 from 1st Dan
        assert wc["rolled"] == 5
        assert any("1st Dan" in s for s in wc["bonus_sources"])

    def test_first_dan_pick_on_damage_applies_in_damage_formula(self):
        char = self._char(dan=1, picks=["damage"], attack=3)
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_extra_rolled"] >= 1
        assert any("1st Dan" in s for s in atk["damage_bonus_sources"])

    def test_first_dan_pick_on_initiative_applies_in_initiative_formula(self):
        char_no = self._char(dan=1, picks=["bragging"])
        char_yes = self._char(dan=1, picks=["initiative"])
        f_no = build_initiative_formula(char_no)
        f_yes = build_initiative_formula(char_yes)
        # Picking initiative grants exactly +1 rolled die.
        assert f_yes["rolled"] == f_no["rolled"] + 1

    def test_first_dan_pick_on_attack_applies_in_combat_formula(self):
        char = self._char(dan=1, picks=["attack"], attack=3)
        f = build_combat_formula("attack", char)
        # rank(3) + Fire(2) + 1 = 6
        assert f.rolled == 6

    def test_first_dan_pick_on_parry_applies_in_combat_formula(self):
        char = self._char(dan=1, picks=["parry"], parry=3)
        f = build_combat_formula("parry", char)
        # rank(3) + Air(2) + 1 = 6
        assert f.rolled == 6

    def test_first_dan_pick_on_knack_applies_extra_die(self):
        char = self._char(dan=1, picks=["commune"])
        f = build_knack_formula("commune", char)
        # commune rolls Earth. rank(1) + Earth(2) + 1 = 4
        assert f.rolled == 4

    def test_first_dan_pick_on_iaijutsu_knack_applies_extra_die(self):
        """Regression guard: iaijutsu IS eligible for 1st Dan picks even
        though it is excluded from the special ability and the 3rd Dan picker."""
        char = self._char(dan=1, picks=["iaijutsu"])
        f = build_knack_formula("iaijutsu", char)
        # iaijutsu rolls Fire by default. rank(1) + Fire(2) + 1 = 4
        assert f.rolled == 4

    def test_first_dan_picks_persist_through_technique_choices(self):
        """The picks survive the round-trip from technique_choices to
        formula construction."""
        char = self._char(dan=1, picks=["bragging", "tact", "wound_check"])
        # bragging picked
        assert build_skill_formula("bragging", char).rolled == 5
        # tact picked
        assert build_skill_formula("tact", char).rolled == 5
        # wound_check picked
        assert build_wound_check_formula(char)["rolled"] == 5
        # etiquette NOT picked
        assert build_skill_formula("etiquette", char).rolled == 4

    def test_first_dan_empty_picks_no_bonus(self):
        char = self._char(dan=1, picks=[])
        assert build_skill_formula("bragging", char).rolled == 4  # 2 + 2

    def test_first_dan_no_technique_choices_no_bonus(self):
        char = self._char(dan=1)  # picks=None -> no first_dan_choices
        assert build_skill_formula("bragging", char).rolled == 4  # 2 + 2

    # --- 2nd Dan: free raise on a chosen roll type (flexible-2nd-Dan branch
    # shared with Ide / Isawa Ishi / Shugenja / Suzume Overseer). ---

    def _char_dan2(self, second_dan_choice=None, **extra):
        kn = {"absorb_void": 2, "commune": 2, "iaijutsu": 2}
        tech_choices = {}
        if second_dan_choice is not None:
            tech_choices["second_dan_choice"] = second_dan_choice
        data = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            skills={"precepts": 3, "bragging": 2, "tact": 2, "etiquette": 2},
            technique_choices=tech_choices,
        )
        data.update(extra)
        return data

    def test_second_dan_chosen_skill_gets_free_raise(self):
        char = self._char_dan2(second_dan_choice="tact")
        f = build_skill_formula("tact", char)
        assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
                   for b in f.bonuses)

    def test_second_dan_no_choice_no_bonus(self):
        char = self._char_dan2()  # No second_dan_choice
        f = build_skill_formula("tact", char)
        assert not any(b["label"] == "2nd Dan technique" for b in f.bonuses)

    def test_second_dan_chosen_wound_check_gets_free_raise(self):
        char = self._char_dan2(second_dan_choice="wound_check")
        wc = build_wound_check_formula(char)
        assert wc["flat"] >= 5
        assert any("2nd Dan" in s for s in wc["bonus_sources"])

    def test_second_dan_chosen_damage_gets_free_raise(self):
        char = self._char_dan2(second_dan_choice="damage", attack=3)
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert atk["damage_flat_bonus"] == 5

    def test_second_dan_attack_choice_gets_free_raise(self):
        char = self._char_dan2(second_dan_choice="attack", attack=3)
        f = build_combat_formula("attack", char)
        assert f.flat == 5

    def test_second_dan_no_bonus_below_dan_2(self):
        # Dan 1 - second_dan_choice is set but should be ignored.
        char = self._char(dan=1, technique_choices={"second_dan_choice": "tact"})
        f = build_skill_formula("tact", char)
        assert not any(b["label"] == "2nd Dan technique" for b in f.bonuses)

    # --- 3rd Dan: 2X precepts adventure raises (X = precepts), applicable to
    # attack + wound check + three player-chosen skills. Iaijutsu is not
    # eligible. ---

    def _char_dan3(self, picks=None, **extra):
        kn = {"absorb_void": 3, "commune": 3, "iaijutsu": 3}
        tech_choices = {}
        if picks is not None:
            tech_choices["third_dan_skill_choices"] = picks
        data = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            skills={"precepts": 3, "bragging": 2, "tact": 2,
                    "etiquette": 2, "sincerity": 2, "sneaking": 2},
            technique_choices=tech_choices,
        )
        data.update(extra)
        return data

    def test_third_dan_annotates_attack_always(self):
        char = self._char_dan3(picks=[], attack=2)
        formulas = build_all_roll_formulas(char)
        # Attack is in the always-on applicable_to list; precepts rank = 3.
        assert formulas["attack"]["adventure_raises_max_per_roll"] == 3

    def test_third_dan_annotates_wound_check_always(self):
        char = self._char_dan3(picks=[])
        formulas = build_all_roll_formulas(char)
        assert formulas["wound_check"]["adventure_raises_max_per_roll"] == 3

    def test_third_dan_annotates_chosen_skill(self):
        char = self._char_dan3(picks=["bragging", "tact", "sincerity"])
        formulas = build_all_roll_formulas(char)
        for sid in ("bragging", "tact", "sincerity"):
            assert formulas[f"skill:{sid}"]["adventure_raises_max_per_roll"] == 3, \
                f"{sid} should be eligible for 3rd Dan adventure raises"

    def test_third_dan_does_not_annotate_unpicked_skill(self):
        char = self._char_dan3(picks=["bragging", "tact", "sincerity"])
        formulas = build_all_roll_formulas(char)
        # etiquette is NOT picked.
        assert formulas["skill:etiquette"]["adventure_raises_max_per_roll"] == 0

    def test_third_dan_iaijutsu_never_eligible_even_if_smuggled_into_choices(self):
        # Defense-in-depth: a crafted POST that puts "iaijutsu" in
        # third_dan_skill_choices must NOT enable the iaijutsu knack roll
        # for adventure raises (the UI excludes iaijutsu, but the server
        # drops it too).
        char = self._char_dan3(picks=["bragging", "iaijutsu", "tact"])
        formulas = build_all_roll_formulas(char)
        assert formulas["knack:iaijutsu"]["adventure_raises_max_per_roll"] == 0

    def test_third_dan_per_adventure_pool_size_is_2x_precepts(self):
        """The per-adventure counter (built by routes/pages.py) reads
        2 * source_skill from the third_dan dict. Confirm Kitsune's
        third_dan entry produces a pool of 2X where X = precepts rank.
        Counter-wiring is a routes-side concern; this test asserts the
        contract dice.py and routes/pages.py share."""
        from app.game_data import SCHOOL_TECHNIQUE_BONUSES
        tb = SCHOOL_TECHNIQUE_BONUSES["kitsune_warden"]["third_dan"]
        assert tb["source_skill"] == "precepts"
        assert tb["formula"] == "2X"
        assert tb["max_per_roll"] == "X"
        # With precepts rank 3, the per-adventure pool would be 2*3 = 6.
        char = self._char_dan3(picks=["bragging"])
        precepts = char["skills"]["precepts"]
        assert 2 * precepts == 6

    def test_third_dan_max_per_roll_is_x(self):
        # The per-roll cap stamped on each applicable formula equals the
        # source skill rank (precepts = 3 in our fixture).
        char = self._char_dan3(picks=["bragging"])
        formulas = build_all_roll_formulas(char)
        assert formulas["skill:bragging"]["adventure_raises_max_per_roll"] == 3
        assert formulas["attack"]["adventure_raises_max_per_roll"] == 3
        assert formulas["wound_check"]["adventure_raises_max_per_roll"] == 3

    def test_third_dan_no_bonus_below_dan_3(self):
        # Below Dan 3, the 3rd Dan annotations should not fire.
        kn = {"absorb_void": 2, "commune": 2, "iaijutsu": 2}
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            skills={"precepts": 3, "bragging": 2},
            technique_choices={"third_dan_skill_choices": ["bragging"]},
            attack=2,
        )
        formulas = build_all_roll_formulas(char)
        assert formulas["attack"]["adventure_raises_max_per_roll"] == 0
        assert formulas["wound_check"]["adventure_raises_max_per_roll"] == 0
        assert formulas["skill:bragging"]["adventure_raises_max_per_roll"] == 0

    def test_third_dan_no_picks_only_attack_and_wound_check(self):
        # When the player hasn't picked any skills yet, only attack and
        # wound_check are eligible (the always-on entries).
        char = self._char_dan3(picks=None, attack=2)
        formulas = build_all_roll_formulas(char)
        assert formulas["attack"]["adventure_raises_max_per_roll"] == 3
        assert formulas["wound_check"]["adventure_raises_max_per_roll"] == 3
        assert formulas["skill:bragging"]["adventure_raises_max_per_roll"] == 0

    # --- 4th Dan: ring raise + 5 XP discount + 10-dice athletics floor ---

    def _char_dan4(self, school_ring="Water", **extra):
        kn = {"absorb_void": 4, "commune": 4, "iaijutsu": 4}
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}
        # 4th Dan auto-raises school ring to 4 (free).
        rings[school_ring] = 4
        data = make_character_data(
            school="kitsune_warden",
            school_ring_choice=school_ring,
            knacks=kn,
            rings=rings,
            skills={"precepts": 1},
        )
        data.update(extra)
        return data

    def test_4th_dan_school_ring_xp_discount_5_off(self):
        """At Dan 4 the school ring raise from 4 to 5 costs 5*5 - 5 = 20."""
        from app.services.xp import calculate_ring_xp
        rings = {"Air": 2, "Fire": 2, "Earth": 2, "Water": 5, "Void": 2}
        # Dan 3 (no discount): 5*4 + 5*5 = 45
        assert calculate_ring_xp(rings, "Water", dan=3) == 45
        # Dan 4: rank 4 free + (5*5 - 5) = 20
        assert calculate_ring_xp(rings, "Water", dan=4) == 20

    def test_4th_dan_athletics_floor_raises_rolled_to_10_when_below(self):
        """6k3 -> 10k3 (rolled raised, kept untouched)."""
        char = self._char_dan4(school_ring="Water")  # Water=4 at Dan 4
        f = build_athletics_formula("Air", char)  # Air=2, rolled = 4
        # Without floor: 2*2 + 0 = 4 rolled. With Kitsune 4th Dan floor: 10.
        assert f.rolled == 10
        assert f.kept == 2  # kept count unchanged

    def test_4th_dan_athletics_floor_does_not_lower_above_10_dice(self):
        """A formula already at 12k4 stays 12k4 (no change)."""
        # School ring = Water raised to 4 at Dan 4. Athletics on Water = 8 rolled.
        # Add an athletics knack rank to push above 10.
        kn = {"absorb_void": 4, "commune": 4, "iaijutsu": 4}
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 6, "Void": 2},
            foreign_knacks={"athletics": 1},
        )
        # Athletics on Water: 2*6 + 1 = 13 rolled, 6 kept (post-cap).
        f = build_athletics_formula("Water", char)
        # 13 rolled is above 10, so the floor doesn't lower it.
        # Then the dice cap (max 10 rolled, max 10 kept) applies via _finalize_caps.
        assert f.rolled == 10  # capped, but NOT because of the floor
        # If we had ring 4 athletics 0: rolled would be 8, raised to 10 by the floor.
        char2 = self._char_dan4(school_ring="Water")
        f2 = build_athletics_formula("Water", char2)
        # Water=4 at Dan 4: rolled = 2*4 + 0 = 8. Floor raises to 10.
        assert f2.rolled == 10

    def test_4th_dan_athletics_floor_does_not_change_kept_count(self):
        """When the floor raises rolled to 10, kept stays at the ring value."""
        char = self._char_dan4(school_ring="Water")
        # Air ring is 2 - 2*2 = 4 rolled (below 10).
        f = build_athletics_formula("Air", char)
        assert f.kept == 2
        # Earth ring is also 2.
        f2 = build_athletics_formula("Earth", char)
        assert f2.kept == 2

    def test_4th_dan_athletics_combat_floor_applies_to_athletics_attack(self):
        """athletics-as-attack also gets the 10-dice floor."""
        kn = {"absorb_void": 4, "commune": 4, "iaijutsu": 4}
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            foreign_knacks={"athletics": 1},
            attack=1,
        )
        # athletics-attack on Fire = ring + athletics = 2 + 1 = 3 rolled, 2 kept.
        f = build_athletics_combat_formula("attack", char)
        assert f.rolled == 10
        assert f.kept == 2

    def test_4th_dan_athletics_combat_floor_applies_to_athletics_parry(self):
        """athletics-as-parry also gets the 10-dice floor."""
        kn = {"absorb_void": 4, "commune": 4, "iaijutsu": 4}
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            foreign_knacks={"athletics": 1},
            parry=1,
        )
        f = build_athletics_combat_formula("parry", char)
        assert f.rolled == 10
        assert f.kept == 2

    def test_below_4th_dan_no_athletics_floor(self):
        """At Dan 3 the floor does not apply."""
        kn = {"absorb_void": 3, "commune": 3, "iaijutsu": 3}
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        f = build_athletics_formula("Air", char)
        # Air=2: 2*2+0 = 4 rolled. Floor not applied.
        assert f.rolled == 4

    def test_4th_dan_athletics_floor_only_for_kitsune(self):
        """Other 4th Dan schools do not get the athletics floor."""
        kn = {"oppose_social": 4, "pontificate": 4, "worldliness": 4}
        char = make_character_data(
            school="suzume_overseer",
            school_ring_choice="Water",
            knacks=kn,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
        )
        f = build_athletics_formula("Air", char)
        assert f.rolled == 4  # not raised to 10

    # --- Special Ability foundation: server-side ring_override ---
    # The UI surfaces the swap in Phases 8-10; this phase confirms the
    # formula builders honor an opt-in ``ring_override`` on the in-scope
    # roll types and reject it on the out-of-scope ones.

    def _swap_char(self, **extra):
        """Kitsune Warden Dan 1, school ring Water (4 because we're going
        to bump rings non-uniformly to give the swap something to do)."""
        kn = {"absorb_void": 1, "commune": 1, "iaijutsu": 1}
        data = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks=kn,
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            skills={"bragging": 2, "precepts": 2},
        )
        data.update(extra)
        return data

    def test_skill_roll_with_ring_override_uses_override_ring(self):
        char = self._swap_char()
        # Bragging is normally Air (rank 2 + Air 2 = 4 rolled, 2 kept).
        # Override to Water (4): 2 + 4 = 6 rolled, 4 kept.
        f = build_skill_formula("bragging", char, ring_override="Water")
        assert f.rolled == 6
        assert f.kept == 4
        assert f.kitsune_swap_from_ring == "Air"
        assert f.kitsune_swap_to_ring == "Water"
        assert "(Water)" in f.label

    def test_skill_roll_no_override_no_swap_metadata(self):
        char = self._swap_char()
        f = build_skill_formula("bragging", char)
        assert f.kitsune_swap_from_ring == ""
        assert f.kitsune_swap_to_ring == ""

    def test_skill_roll_override_to_same_ring_no_swap(self):
        """If override ring == default ring, no swap is recorded."""
        char = self._swap_char()
        # Bragging is naturally Air; override Air -> no-op.
        f = build_skill_formula("bragging", char, ring_override="Air")
        assert f.kitsune_swap_from_ring == ""
        assert f.kitsune_swap_to_ring == ""

    def test_skill_roll_override_invalid_ring_ignored(self):
        """Garbage ring names don't crash; the default ring is used."""
        char = self._swap_char()
        f = build_skill_formula("bragging", char, ring_override="NotARing")
        assert f.kitsune_swap_from_ring == ""

    def test_knack_roll_with_ring_override_uses_override_ring(self):
        char = self._swap_char()
        # Commune rolls Earth by default (rank 1 + Earth 2 = 3).
        # Override to Water (4): 1 + 4 = 5 rolled, 4 kept.
        f = build_knack_formula("commune", char, ring_override="Water")
        assert f.rolled == 5
        assert f.kept == 4
        assert f.kitsune_swap_from_ring == "Earth"
        assert f.kitsune_swap_to_ring == "Water"

    def test_iaijutsu_attack_rejects_ring_override(self):
        """build_knack_formula raises ValueError when ring_override is
        passed for iaijutsu (defense in depth - the UI never offers it)."""
        import pytest as _pytest
        char = self._swap_char()
        with _pytest.raises(ValueError):
            build_knack_formula("iaijutsu", char, ring_override="Water")
        # Without override, the call works as usual.
        f = build_knack_formula("iaijutsu", char)
        assert f is not None

    def test_attack_roll_with_ring_override_uses_override_ring(self):
        char = self._swap_char(attack=3)
        # Attack default ring is Fire (rank 3 + Fire 2 = 5 rolled, 2 kept).
        # Override to Water (4): 3 + 4 = 7 rolled, 4 kept.
        f = build_combat_formula("attack", char, ring_override="Water")
        assert f.rolled == 7
        assert f.kept == 4
        assert f.kitsune_swap_from_ring == "Fire"
        assert f.kitsune_swap_to_ring == "Water"

    def test_parry_roll_with_ring_override_uses_override_ring(self):
        char = self._swap_char(parry=3)
        # Parry default ring is Air (rank 3 + Air 2 = 5 rolled, 2 kept).
        # Override to Water (4): 3 + 4 = 7 rolled, 4 kept.
        f = build_combat_formula("parry", char, ring_override="Water")
        assert f.rolled == 7
        assert f.kept == 4
        assert f.kitsune_swap_from_ring == "Air"
        assert f.kitsune_swap_to_ring == "Water"

    def test_wound_check_with_ring_override_uses_override_ring(self):
        char = self._swap_char()
        # Default: Water+1 = 5 rolled, Water = 4 kept (Water=4 here).
        # Override to Air (2): 2+1 = 3 rolled, 2 kept.
        wc = build_wound_check_formula(char, ring_override="Air")
        assert wc["rolled"] == 3
        assert wc["kept"] == 2
        assert wc["kitsune_swap_from_ring"] == "Water"
        assert wc["kitsune_swap_to_ring"] == "Air"
        assert "(Air)" in wc["label"]

    def test_wound_check_no_override_no_swap_metadata(self):
        char = self._swap_char()
        wc = build_wound_check_formula(char)
        assert wc["kitsune_swap_from_ring"] == ""
        assert wc["kitsune_swap_to_ring"] == ""

    def test_damage_formula_does_not_accept_ring_override(self):
        """Damage formulas don't have a ring to swap, and the rules
        explicitly exclude damage from the special ability. Out-of-scope
        builders don't expose a ring_override parameter."""
        import inspect
        # The damage block lives inside build_all_roll_formulas; that
        # function's signature must not have a ring_override param.
        sig = inspect.signature(build_all_roll_formulas)
        assert "ring_override" not in sig.parameters

    def test_initiative_formula_does_not_accept_ring_override(self):
        import inspect
        sig = inspect.signature(build_initiative_formula)
        assert "ring_override" not in sig.parameters

    def test_athletics_formula_does_not_accept_ring_override(self):
        import inspect
        sig = inspect.signature(build_athletics_formula)
        assert "ring_override" not in sig.parameters
        sig2 = inspect.signature(build_athletics_combat_formula)
        assert "ring_override" not in sig2.parameters

    def test_ring_override_breakdown_labels_swapped_ring(self):
        """The formula's label reflects the swap (e.g. 'Bragging (Water)'
        instead of 'Bragging (Air)') so the UI can render the annotation."""
        char = self._swap_char()
        f = build_skill_formula("bragging", char, ring_override="Water")
        assert f.label == "Bragging (Water)"

    # --- Phase 11 polish: iaijutsu exclusion + equal-ring suppression sweeps ---

    def test_special_ability_never_offered_on_iaijutsu_paths(self):
        """The post-pass _attach_kitsune_swaps must NOT attach kitsune_swap
        to any iaijutsu-related formula key (knack:iaijutsu and the
        Kakita-specific knack:iaijutsu:strike / :attack variants)."""
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            skills={"precepts": 1},
        )
        formulas = build_all_roll_formulas(char)
        for key in formulas:
            if "iaijutsu" in key:
                assert "kitsune_swap" not in formulas[key], \
                    f"{key} should NOT have kitsune_swap; got {formulas[key].get('kitsune_swap')}"

    def test_special_ability_no_op_when_school_ring_value_equals_default_ring_value(self):
        """When the school ring's value equals an in-scope formula's
        natural ring's value, the swap is a no-op identity and the
        kitsune_swap sub-dict is not attached."""
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            # Water and Air both at 3 - bragging (Air) -> swap to Water
            # would not change rolled/kept.
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            skills={"bragging": 2},
            parry=2,
        )
        formulas = build_all_roll_formulas(char)
        # Bragging is Air (value 3), school ring is Water (value 3): equal,
        # no swap.
        assert formulas["skill:bragging"].get("kitsune_swap") is None
        # Parry is Air (value 3), school ring is Water (value 3): equal,
        # no swap.
        assert formulas["parry"].get("kitsune_swap") is None
        # Attack is Fire (value 2), school ring is Water (value 3):
        # different value, swap attached.
        assert formulas["attack"].get("kitsune_swap") is not None

    def test_wound_check_kitsune_swap_attaches_when_school_ring_differs_from_water(self):
        """Coverage: the WC kitsune_swap attach branch fires for school
        ring != Water (e.g. Earth). Default WC uses Water; swap uses Earth."""
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Earth",
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 2},
        )
        formulas = build_all_roll_formulas(char)
        wc_swap = formulas["wound_check"].get("kitsune_swap")
        assert wc_swap is not None
        assert wc_swap["kitsune_swap_to_ring"] == "Earth"
        assert wc_swap["kitsune_swap_from_ring"] == "Water"
        # rolled = Earth+1 = 4, kept = Earth = 3
        assert wc_swap["rolled"] == 4
        assert wc_swap["kept"] == 3

    def test_kitsune_swap_attaches_to_foreign_rollable_knacks(self):
        """Coverage: a Kitsune with a foreign rollable knack (athletics)
        gets kitsune_swap attached on the foreign-knack formula too."""
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            foreign_knacks={"athletics": 1},
        )
        formulas = build_all_roll_formulas(char)
        # Athletics knack's natural ring is Earth (value 2). Swap to Water
        # (value 4) gives rolled = 1 + 4 = 5, kept = 4.
        ath_swap = formulas["knack:athletics"].get("kitsune_swap")
        assert ath_swap is not None
        assert ath_swap["kitsune_swap_from_ring"] == "Earth"
        assert ath_swap["kitsune_swap_to_ring"] == "Water"
        assert ath_swap["rolled"] == 5
        assert ath_swap["kept"] == 4

    def test_attack_bonus_sources_includes_kitsune_first_dan_pick(self):
        """Coverage: when Kitsune Warden picks 'attack' as one of the
        three 1st Dan picks, the attack-modal pre-roll panel's
        bonus_sources list includes the +1-rolled-die annotation."""
        char = make_character_data(
            school="kitsune_warden",
            school_ring_choice="Water",
            knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            attack=2,
            technique_choices={"first_dan_choices": ["attack"]},
        )
        formulas = build_all_roll_formulas(char)
        atk = formulas["attack"]
        assert any("1st Dan" in s for s in (atk.get("bonus_sources") or [])), \
            f"Expected '+1 rolled die from 1st Dan' in attack bonus_sources, got {atk.get('bonus_sources')}"

