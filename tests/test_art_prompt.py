"""Unit tests for the prompt assembly helper."""

from __future__ import annotations

import pytest

from app.game_data import CLAN_COLORS
from app.services.art_prompt import (
    AGE_MAX,
    AGE_MIN,
    ARMOR_OPTIONS,
    DEFAULT_AGE,
    DEFAULT_CLAN,
    FEMALE_SUFFIX_APPEND,
    PROMPT_SUFFIX,
    assemble_prompt,
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


def test_armor_options_first_is_empty_for_none():
    """The (none) / no-armor option is the empty string so an unselected
    dropdown submits nothing via Alpine's `:disabled` binding."""
    assert ARMOR_OPTIONS[0] == ""


# ---------------------------------------------------------------------------
# Happy-path assembly
# ---------------------------------------------------------------------------


class TestMaleMinimalPrompt:
    """Mandatory fields only, male pronouns."""

    def test_includes_clan_prefix(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert "A portrait of a Wasp clan noble." in out

    def test_uses_he_pronoun(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert " He " in out
        assert " She " not in out

    def test_includes_age(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=27)
        assert "27 years old" in out

    def test_includes_clan_colors_from_map(self):
        # Scorpion colors must be pulled from CLAN_COLORS, not hardcoded.
        out = assemble_prompt(gender="male", clan="Scorpion", age=20)
        assert CLAN_COLORS["Scorpion"] in out

    def test_no_female_append_for_male(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert FEMALE_SUFFIX_APPEND not in out

    def test_base_suffix_always_present(self):
        out = assemble_prompt(gender="male", clan="Wasp", age=20)
        assert PROMPT_SUFFIX in out


class TestFemaleMinimalPrompt:
    """Mandatory fields only, female pronouns - also verifies the
    always-on 'unstyled hair, no makeup' append."""

    def test_uses_she_pronoun(self):
        out = assemble_prompt(gender="female", clan="Crane", age=24)
        assert " She " in out
        assert " He " not in out

    def test_appends_female_suffix_for_female(self):
        out = assemble_prompt(gender="female", clan="Crane", age=24)
        assert FEMALE_SUFFIX_APPEND in out
        # The append comes AFTER the base suffix so model ordering is
        # consistent - base style, then the override.
        assert out.rfind(FEMALE_SUFFIX_APPEND) > out.rfind(PROMPT_SUFFIX)


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


class TestOptionalFields:
    def test_holding_appears_when_set(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, holding="a katana",
        )
        assert "is holding a katana" in out

    def test_holding_omitted_when_empty_string(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, holding="",
        )
        assert "holding" not in out

    def test_holding_omitted_when_whitespace_only(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, holding="   ",
        )
        assert "holding" not in out

    def test_expression_appears_when_set(self):
        out = assemble_prompt(
            gender="female", clan="Wasp", age=20,
            expression="a serene expression",
        )
        assert "has a serene expression" in out

    def test_armor_without_modifier(self):
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20, armor="samurai armor",
        )
        assert "is wearing samurai armor" in out

    def test_armor_with_modifier(self):
        out = assemble_prompt(
            gender="female", clan="Wasp", age=20,
            armor="formal kimono", armor_modifier="ornate",
        )
        assert "is wearing ornate formal kimono" in out

    def test_armor_modifier_alone_does_nothing(self):
        """A modifier without an armor choice should be silently ignored,
        not pasted into the prompt on its own."""
        out = assemble_prompt(
            gender="male", clan="Wasp", age=20,
            armor="", armor_modifier="ornate",
        )
        assert "ornate" not in out


class TestEveryFieldCombined:
    def test_full_prompt_contains_every_part(self):
        out = assemble_prompt(
            gender="female", clan="Scorpion", age=32,
            holding="a fan", expression="a cold smile",
            armor="formal kimono", armor_modifier="muted",
        )
        # Order: prefix -> age -> holding -> expression -> armor ->
        # base suffix -> female append.
        positions = [
            out.find("A portrait of a Scorpion clan noble."),
            out.find("32 years old"),
            out.find("is holding a fan."),
            out.find("has a cold smile."),
            out.find("is wearing muted formal kimono."),
            out.find(PROMPT_SUFFIX),
            out.find(FEMALE_SUFFIX_APPEND),
        ]
        assert all(p >= 0 for p in positions), f"missing piece: {positions}"
        assert positions == sorted(positions), f"wrong order: {positions}"


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
        # AGE_MIN and AGE_MAX must both be valid (inclusive).
        assemble_prompt(gender="male", clan="Wasp", age=AGE_MIN)
        assemble_prompt(gender="female", clan="Wasp", age=AGE_MAX)

    def test_unknown_gender_raises(self):
        with pytest.raises(ValueError, match="Unknown gender"):
            assemble_prompt(gender="nonbinary", clan="Wasp", age=20)
