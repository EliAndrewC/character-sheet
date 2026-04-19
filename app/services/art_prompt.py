"""Mad-libs prompt assembly for character-art generation.

Given the user's selections from the wizard, ``assemble_prompt``
produces the final natural-language string that gets POSTed to
Imagen in Phase 8. Kept as a pure function with no I/O so it can
be exhaustively unit-tested.

The Phase 7 UI doesn't call Gemini yet - step 3 just shows the
assembled prompt in an editable textarea so the user can tweak it
before submitting in Phase 8.
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

ARMOR_OPTIONS = [
    "",                          # "(none)" - no override
    "formal kimono",
    "everyday kimono",
    "traveling clothes",
    "samurai armor",
    "ceremonial armor",
]

# Base suffix appended to every prompt. Can be tuned as we learn what
# produces good Imagen output; kept in one place so the tuning edit is
# obvious in a diff. The user may edit the final prompt on the review
# page, so this is the starting point, not a hard rule.
PROMPT_SUFFIX = (
    "Make a colored, photo-realistic portrait painting in the style of "
    "a traditional Japanese period portrait. Natural lighting, neutral "
    "background, full face visible. No text, no watermark, no signature."
)

# Always appended for female characters. Not user-editable in the UI
# (per Eli's direction: avoids the "geisha problem" where the model
# over-stylises female faces with heavy makeup and styled hair).
FEMALE_SUFFIX_APPEND = "Completely unstyled hair and no makeup."


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _pronoun_subject(gender: str) -> str:
    return "She" if gender == "female" else "He"


def assemble_prompt(
    *,
    gender: str,
    clan: str,
    age: int,
    holding: Optional[str] = None,
    expression: Optional[str] = None,
    armor: Optional[str] = None,
    armor_modifier: Optional[str] = None,
) -> str:
    """Build the final prompt string from the wizard's field values.

    ``gender`` is ``"male"`` or ``"female"`` (the UI has only these two
    radios). Empty strings for optional fields are treated as omitted.

    Raises ``ValueError`` for unknown clans or out-of-range ages so the
    caller can render a clear error banner rather than generating a
    nonsense prompt.
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
    colors = CLAN_COLORS[clan]

    parts: list[str] = [
        f"A portrait of a {clan} clan noble.",
        f"{subj} is {age} years old and is wearing {colors}.",
    ]

    holding = (holding or "").strip()
    if holding:
        parts.append(f"{subj} is holding {holding}.")

    expression = (expression or "").strip()
    if expression:
        parts.append(f"{subj} has {expression}.")

    armor = (armor or "").strip()
    armor_modifier = (armor_modifier or "").strip()
    if armor:
        if armor_modifier:
            parts.append(f"{subj} is wearing {armor_modifier} {armor}.")
        else:
            parts.append(f"{subj} is wearing {armor}.")

    parts.append(PROMPT_SUFFIX)
    if gender == "female":
        parts.append(FEMALE_SUFFIX_APPEND)

    return " ".join(parts)


__all__ = [
    "ARMOR_OPTIONS",
    "AGE_MAX",
    "AGE_MIN",
    "CLAN_COLORS",
    "DEFAULT_AGE",
    "DEFAULT_CLAN",
    "FEMALE_SUFFIX_APPEND",
    "PROMPT_SUFFIX",
    "assemble_prompt",
]
