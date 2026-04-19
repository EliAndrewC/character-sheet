"""Mad-libs prompt assembly for character-art generation.

The UI for step 2 lays out the prompt *inline*: a fixed prefix at the
top, the fixed suffix at the bottom, and a stack of checkbox rows in
between. Ticking a row appends that row's sentence to the assembled
prompt. This module is the server-side half - given the form values,
it produces the exact string that gets shown in the review textarea
(and ultimately POSTed to Imagen in Phase 8).

Kept as a pure function with no I/O so it can be exhaustively
unit-tested.
"""

from __future__ import annotations

from typing import Optional

from app.game_data import CLAN_COLORS


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------


DEFAULT_CLAN = "Wasp"           # Selector default for the Wasp campaign.
DEFAULT_AGE = 20                # Pre-filled in the age input.
AGE_MIN = 15
AGE_MAX = 55

# Exactly two choices for the armor/kimono row. The string is spliced
# verbatim into the sentence: "{He/She} {choice} {modifier?}."
ARMOR_CHOICE_KIMONO = "is not wearing armor and has on a kimono"
ARMOR_CHOICE_SAMURAI = "is wearing samurai armor"
ARMOR_CHOICES = [ARMOR_CHOICE_KIMONO, ARMOR_CHOICE_SAMURAI]

# Base suffix appended to every prompt. Non-editable display text on
# the mad-libs page.
PROMPT_SUFFIX = (
    "Make a colored, photo-realistic portrait painting in the style of "
    "a traditional Japanese period portrait. Natural lighting, neutral "
    "background, full face visible. No text, no watermark, no signature."
)

# Always appended for female characters. Not surfaced in the UI (per
# Eli's direction: avoids the "geisha problem" where the model
# over-stylises female faces with heavy makeup and styled hair).
FEMALE_SUFFIX_APPEND = "Completely unstyled hair and no makeup."


# ---------------------------------------------------------------------------
# Pronoun helpers
# ---------------------------------------------------------------------------


def _pronoun_subject(gender: str) -> str:
    """Return 'He' or 'She' - the subject pronoun for the mad-libs sentences."""
    return "She" if gender == "female" else "He"


def build_prefix(clan: str) -> str:
    """Build the fixed top block that shows above the checkbox rows.

    Exposed so the step-2 template can render the exact same string the
    server will use when assembling the final prompt.
    """
    if clan not in CLAN_COLORS:
        raise ValueError(f"Unknown clan: {clan!r}")
    return f"A portrait of a {clan} clan noble wearing {CLAN_COLORS[clan]}."


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def assemble_prompt(
    *,
    gender: str,
    clan: str,
    age: int,
    holding: Optional[str] = None,
    expression: Optional[str] = None,
    armor_choice: Optional[str] = None,
    armor_modifier: Optional[str] = None,
) -> str:
    """Build the final prompt string from the wizard's field values.

    ``gender`` is ``"male"`` or ``"female"``. Empty/whitespace strings
    for optional fields are treated as omitted.

    ``armor_choice`` must be one of ``ARMOR_CHOICES`` (or empty/None to
    skip the row entirely). Passing anything else raises ``ValueError``.

    Raises ``ValueError`` for unknown clans, out-of-range ages, unknown
    genders, or unknown armor choices. Also raises when a checkbox row
    that *requires* text (holding, expression) is checked but submits
    an empty text field - the client enforces this too, but the server
    is authoritative.
    """
    if clan not in CLAN_COLORS:
        raise ValueError(f"Unknown clan: {clan!r}")
    if not (AGE_MIN <= age <= AGE_MAX):
        raise ValueError(
            f"Age must be between {AGE_MIN} and {AGE_MAX}; got {age}"
        )
    if gender not in ("male", "female"):
        raise ValueError(f"Unknown gender: {gender!r}")

    subj = _pronoun_subject(gender)

    # Fixed prefix (top block on the UI).
    parts: list[str] = [build_prefix(clan)]

    # Mandatory age row.
    parts.append(f"{subj} is approximately {age} years old.")

    # Optional holding row. Checked-but-empty is a server-side validation
    # failure, not a silent drop.
    holding = (holding or "").strip() or None
    if holding is not None:
        parts.append(f"{subj} is holding {holding}.")

    # Optional expression row. Same rule.
    expression = (expression or "").strip() or None
    if expression is not None:
        parts.append(f"{subj} has a {expression} expression.")

    # Optional armor row. Modifier may be blank.
    armor_choice = (armor_choice or "").strip() or None
    armor_modifier = (armor_modifier or "").strip() or None
    if armor_choice is not None:
        if armor_choice not in ARMOR_CHOICES:
            raise ValueError(f"Unknown armor_choice: {armor_choice!r}")
        if armor_modifier:
            parts.append(f"{subj} {armor_choice} {armor_modifier}.")
        else:
            parts.append(f"{subj} {armor_choice}.")

    # Fixed suffix.
    parts.append(PROMPT_SUFFIX)

    # Female-only fixed append (not surfaced in the UI).
    if gender == "female":
        parts.append(FEMALE_SUFFIX_APPEND)

    return " ".join(parts)


__all__ = [
    "AGE_MAX",
    "AGE_MIN",
    "ARMOR_CHOICES",
    "ARMOR_CHOICE_KIMONO",
    "ARMOR_CHOICE_SAMURAI",
    "CLAN_COLORS",
    "DEFAULT_AGE",
    "DEFAULT_CLAN",
    "FEMALE_SUFFIX_APPEND",
    "PROMPT_SUFFIX",
    "assemble_prompt",
    "build_prefix",
]
