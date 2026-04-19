"""Unit tests for the prompt assembly helper."""

from __future__ import annotations

import pytest

from app.game_data import CLAN_COLORS
from app.services.art_prompt import (
    AGE_MAX,
    AGE_MIN,
    ARMOR_CHOICE_KIMONO,
    ARMOR_CHOICE_SAMURAI,
    ARMOR_CHOICES,
    DEFAULT_AGE,
    DEFAULT_CLAN,
    FEMALE_SUFFIX_APPEND,
    PROMPT_SUFFIX,
    assemble_prompt,
    build_prefix,
)


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


def test_default_clan_is_wasp():
    """Wasp is the default because this is the Wasp campaign - a Wasp
    character often trained at another clan's school, so auto-detecting
    from the character's school would be wrong more often than right."""
    assert DEFAULT_CLAN == "Wasp"
    assert "Wasp" in CLAN_COLORS


def test_default_age_is_twenty():
    assert DEFAULT_AGE == 20


def test_age_range_is_15_to_55():
    assert AGE_MIN == 15
    assert AGE_MAX == 55


def test_armor_choices_are_exactly_the_two_specified():
    """Per Eli's spec: exactly two dropdown options for the armor row."""
    assert ARMOR_CHOICES == [ARMOR_CHOICE_KIMONO, ARMOR_CHOICE_SAMURAI]
    assert ARMOR_CHOICE_KIMONO == "is not wearing armor and has on a kimono"
    assert ARMOR_CHOICE_SAMURAI == "is wearing samurai armor"


# ---------------------------------------------------------------------------
# build_prefix
# ---------------------------------------------------------------------------


class TestBuildPrefix:
    def test_wasp_prefix(self):
        assert build_prefix("Wasp") == (
            "A portrait of a Wasp clan noble wearing black and gold."
        )

    def test_scorpion_prefix(self):
        assert build_prefix("Scorpion") == (
            "A portrait of a Scorpion clan noble wearing black and dark red."
        )

    def test_unknown_clan_raises(self):
        with pytest.raises(ValueError, match="Unknown clan"):
            build_prefix("Goblin")


# ---------------------------------------------------------------------------
# Happy-path assembly - mandatory rows only
# ---------------------------------------------------------------------------


class TestMaleMinimalPrompt:
    def test_includes_clan_prefix(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert "A portrait of a Wasp clan noble wearing black and gold." in out

    def test_age_sentence_uses_approximately_and_he(self):
        """Exact wording from Eli's spec: 'He is approximately N years old.'"""
        out = assemble_prompt(gender="male", clan="Wasp", age=27)
        assert "He is approximately 27 years old." in out

    def test_no_she_for_male(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert "She " not in out

    def test_no_female_append_for_male(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert FEMALE_SUFFIX_APPEND not in out

    def test_base_suffix_always_present(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert PROMPT_SUFFIX in out


class TestFemaleMinimalPrompt:
    def test_age_sentence_uses_approximately_and_she(self):
        out = assemble_prompt(gender="female", clan="Crane", age=24)
        assert "She is approximately 24 years old." in out

    def test_no_he_for_female(self):
        out = assemble_prompt(gender="female", clan="Crane", age=24)
        assert "He " not in out
        assert "He is " not in out

    def test_appends_female_suffix_for_female(self):
        out = assemble_prompt(gender="female", clan="Crane", age=24)
        assert FEMALE_SUFFIX_APPEND in out
        # After the base suffix, not before.
        assert out.rfind(FEMALE_SUFFIX_APPEND) > out.rfind(PROMPT_SUFFIX)


# ---------------------------------------------------------------------------
# Optional rows
# ---------------------------------------------------------------------------


class TestHoldingRow:
    def test_appears_when_set(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, holding="a katana",
        )
        assert "He is holding a katana." in out

    def test_omitted_when_empty(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, holding="",
        )
        assert "holding" not in out

    def test_omitted_when_whitespace(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, holding="   ",
        )
        assert "holding" not in out


class TestExpressionRow:
    def test_uses_has_a_X_expression_wording(self):
        """Exact wording from Eli's spec: 'He has a <X> expression.'"""
        out = assemble_prompt(
            gender="female", clan="Wasp", age=20, expression="serene",
        )
        assert "She has a serene expression." in out

    def test_omitted_when_empty(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, expression="",
        )
        assert "expression" not in out


class TestArmorRow:
    def test_samurai_armor_no_modifier(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20,
            armor_choice=ARMOR_CHOICE_SAMURAI,
        )
        assert "He is wearing samurai armor." in out

    def test_kimono_no_modifier(self):
        out = assemble_prompt(
            gender="female", clan="Wasp", age=20,
            armor_choice=ARMOR_CHOICE_KIMONO,
        )
        assert "She is not wearing armor and has on a kimono." in out

    def test_samurai_armor_with_modifier(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20,
            armor_choice=ARMOR_CHOICE_SAMURAI, armor_modifier="ornate",
        )
        assert "He is wearing samurai armor ornate." in out

    def test_kimono_with_modifier(self):
        out = assemble_prompt(
            gender="female", clan="Wasp", age=20,
            armor_choice=ARMOR_CHOICE_KIMONO, armor_modifier="with a red obi",
        )
        assert "She is not wearing armor and has on a kimono with a red obi." in out

    def test_modifier_alone_is_ignored(self):
        """A modifier without an armor_choice should be silently omitted,
        not spliced into a half-sentence."""
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20,
            armor_choice="", armor_modifier="ornate",
        )
        assert "ornate" not in out

    def test_unknown_armor_choice_raises(self):
        with pytest.raises(ValueError, match="Unknown armor_choice"):
            assemble_prompt(
                gender="male", clan="Wasp", age=20,
                armor_choice="leather jerkin",
            )


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------


class TestEveryFieldCombined:
    def test_order_prefix_age_holding_expression_armor_suffix_female(self):
        """Row order must be: prefix -> age -> holding -> expression ->
        armor -> base suffix -> female append."""
        out = assemble_prompt(
            gender="female", clan="Scorpion", age=32,
            holding="a fan", expression="cold",
            armor_choice=ARMOR_CHOICE_KIMONO, armor_modifier="dark",
        )
        positions = [
            out.find("A portrait of a Scorpion clan noble wearing"),
            out.find("She is approximately 32 years old."),
            out.find("She is holding a fan."),
            out.find("She has a cold expression."),
            out.find("She is not wearing armor and has on a kimono dark."),
            out.find(PROMPT_SUFFIX),
            out.find(FEMALE_SUFFIX_APPEND),
        ]
        assert all(p >= 0 for p in positions), f"missing piece: {positions}"
        assert positions == sorted(positions), f"wrong order: {positions}"

    def test_clan_colors_come_from_game_data_map(self):
        """Changing CLAN_COLORS should flow through to the prompt without
        a second edit."""
        for clan, color in CLAN_COLORS.items():
            out = assemble_prompt(gender="male", clan=clan, age=20)
            assert f"{clan} clan noble wearing {color}." in out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unknown_clan_raises(self):
        with pytest.raises(ValueError, match="Unknown clan"):
            assemble_prompt(gender="male", clan="Goblin", age=20)

    @pytest.mark.parametrize("bad_age", [14, 56, -1, 100, 0])
    def test_out_of_range_age_raises(self, bad_age):
        with pytest.raises(ValueError, match="Age must be"):
            assemble_prompt(gender="male", clan="Wasp", age=bad_age)

    def test_boundary_ages_accepted(self):
        assemble_prompt(gender="male", clan="Wasp", age=AGE_MIN)
        assemble_prompt(gender="female", clan="Wasp", age=AGE_MAX)

    def test_unknown_gender_raises(self):
        with pytest.raises(ValueError, match="Unknown gender"):
            assemble_prompt(gender="nonbinary", clan="Wasp", age=20)
