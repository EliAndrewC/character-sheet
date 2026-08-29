"""Profession selection, ability sanitizing and display helpers.

A profession is taken INSTEAD of a school (design doc D1), so both live
behind the editor's single school ``<select>``. There is exactly one
profession character type - "Profession" (part 2, P1) - and a profession
character draws abilities from every *available* profession and mixes them
freely: a wave man who settles in a city and picks up work, or who prays at
a temple often enough that the monks teach him a ritual.

``split_school_or_profession`` is the one place the dropdown's encoding is
understood, and it doubles as the allow-list.

Abilities are stored as an id -> count map because an ability may be taken
more than once (D4); ``sanitize_profession_abilities`` is the server-side
clamp that a crafted POST cannot get past. Each ability is clamped to ITS
OWN profession's ``max_per_ability``, so a Wave Man ability caps at 2 and a
Priest ritual at 1 in the same character (P7).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.game_data import (
    PROFESSION_ABILITIES,
    PROFESSION_BY_ABILITY,
    PROFESSION_CHARACTER_TYPE,
    PROFESSIONS,
    SCHOOLS,
)

# The dropdown value for "Profession". Asserted in tests to not collide with
# any school id.
PROFESSION_SELECT_VALUE = PROFESSION_CHARACTER_TYPE

# Legacy per-profession dropdown values (``profession:wave_man``). Kept for
# one release: an editor tab left open across the deploy will POST the old
# form, and resolving it to "no profession" would silently wipe that
# character's abilities. Which profession it named no longer matters - the
# character type is the same either way.
LEGACY_PROFESSION_SELECT_PREFIX = "profession:"


def split_school_or_profession(value: str) -> Tuple[str, str]:
    """Resolve a school-dropdown value into ``(school_id, profession_type)``.

    Exactly one of the two is non-empty, or both are empty. An unknown
    school id resolves to ``("", "")`` - the caller then clears both, which
    is the correct outcome for a crafted payload naming something that does
    not exist.
    """
    value = (value or "").strip()
    if not value:
        return "", ""
    if value == PROFESSION_SELECT_VALUE:
        return "", PROFESSION_CHARACTER_TYPE
    if value.startswith(LEGACY_PROFESSION_SELECT_PREFIX):
        # Any profession id, known or not: the type is what is being set.
        return "", PROFESSION_CHARACTER_TYPE
    if value in SCHOOLS:
        return value, ""
    return "", ""


def select_value_for(school_id: str, profession: str) -> str:
    """Inverse of :func:`split_school_or_profession`, for rendering."""
    if profession:
        return PROFESSION_SELECT_VALUE
    return school_id or ""


def is_profession_character(character_data: Any) -> bool:
    """Whether this character took a profession rather than a school."""
    if character_data is None:
        return False
    if isinstance(character_data, dict):
        return bool(character_data.get("profession"))
    return bool(getattr(character_data, "profession", ""))  # pragma: no cover


def ability_is_available(ability_id: str) -> bool:
    """Can *ability_id* be taken?

    Two gates, and both must pass: the profession has to be available, and
    the ability itself has to be. The second exists for abilities held back
    inside a live profession - the Worker's advanced-skills-as-basic is
    campaign-specific, so it is shown greyed out rather than hidden.

    The one place this is decided; every other caller comes through here or
    through :func:`max_for_ability`.
    """
    ability = PROFESSION_ABILITIES.get(ability_id)
    if ability is None or not ability.available:
        return False
    prof = PROFESSIONS.get(PROFESSION_BY_ABILITY.get(ability_id) or "")
    return prof is not None and prof.is_available


def max_for_ability(ability_id: str) -> int:
    """How many times *ability_id* may be taken, or 0 if it is unavailable.

    Reads the limit off the ability's OWN profession, which is what lets one
    character hold a twice-taken Wave Man ability beside a once-only Priest
    ritual.
    """
    if not ability_is_available(ability_id):
        return 0
    return PROFESSIONS[PROFESSION_BY_ABILITY[ability_id]].max_per_ability


def sanitize_profession_abilities(raw: Any) -> Dict[str, int]:
    """Clamp an incoming ability map to what the rules actually allow.

    Drops ids that don't exist, ids from professions that are not available
    (preview or hidden), and non-positive or non-integer counts; clamps each
    remaining count to that ability's own per-ability limit.

    Does NOT enforce the XP allowance - going over is a validation error
    rather than a silent truncation, so a player can see they have
    overcommitted instead of having picks vanish.
    """
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, int] = {}
    for ability_id, count in raw.items():
        limit = max_for_ability(ability_id)
        if not limit:
            continue
        # bool is an int subclass; a JSON `true` is not a count.
        if isinstance(count, bool) or not isinstance(count, int):
            continue
        if count < 1:
            continue
        cleaned[ability_id] = min(count, limit)
    return cleaned


def ability_counts_for_display(
    abilities: Any, *, include_untaken: bool
) -> List[Dict[str, Any]]:
    """Grouped rows for the editor and the View Sheet.

    One group per profession, in rules order. ``include_untaken`` is the
    difference between the two surfaces (P10): the editor passes True and
    gets every ability of every *visible* profession, so a player can see
    what is on offer; the View Sheet passes False and gets only what the
    character actually took, which keeps the panel to a handful of lines
    rather than thirty rows at 40% opacity.

    Hidden professions never appear either way.
    """
    counts = abilities if isinstance(abilities, dict) else {}
    groups: List[Dict[str, Any]] = []
    # Available professions first, then previews - a player should not have
    # to scroll past what they cannot take to reach what they can. Order
    # within each band follows the rules file.
    visible = sorted(
        (p for p in PROFESSIONS.values() if p.is_visible),
        key=lambda p: (not p.is_available, list(PROFESSIONS).index(p.id)),
    )
    for prof in visible:
        rows = []
        for ability in prof.abilities:
            takeable = prof.is_available and ability.available
            raw = counts.get(ability.id, 0) if takeable else 0
            try:
                count = max(0, min(int(raw or 0), prof.max_per_ability))
            except (TypeError, ValueError):  # pragma: no cover - sanitized on write
                count = 0
            if not count and not include_untaken:
                continue
            rows.append({
                "id": ability.id,
                "available": ability.available,
                "ordinal": ability.ordinal,
                "name": ability.name,
                "text": ability.text,
                "implemented": ability.implemented,
                "reference_only": ability.reference_only,
                "money_bonus": ability.money_bonus,
                "ritual_time": ability.ritual_time,
                "count": count,
                "max": prof.max_per_ability,
            })
        if not rows:
            continue
        groups.append({
            "profession_id": prof.id,
            "name": prof.name,
            "rules_anchor": prof.rules_anchor,
            "availability": prof.availability,
            "is_available": prof.is_available,
            "max_per_ability": prof.max_per_ability,
            "rows": rows,
        })
    return groups


def ability_count(character_data: Any, ability_id: str) -> int:
    """How many copies of *ability_id* this character has.

    Accepts either a ``character_data`` dict or anything with a
    ``profession_abilities`` attribute, so formula builders and route code
    can share one accessor. Returns 0 for a character with a school, and for
    any ability whose profession is not available.
    """
    if character_data is None:
        return 0
    if isinstance(character_data, dict):
        profession = character_data.get("profession") or ""
        abilities = character_data.get("profession_abilities") or {}
    else:  # pragma: no cover - attribute form is used by route code only
        profession = getattr(character_data, "profession", "") or ""
        abilities = getattr(character_data, "profession_abilities", {}) or {}
    if not profession:
        return 0
    limit = max_for_ability(ability_id)
    if not limit:
        return 0
    try:
        raw = int(abilities.get(ability_id, 0) or 0)
    except (TypeError, ValueError):  # pragma: no cover - sanitized on write
        return 0
    return max(0, min(raw, limit))


def profession_money_bonus(character_data: Any) -> int:
    """The character's accumulated money bonus, as a whole percentage.

    Several Worker and Merchant abilities carry one; the rules head the
    Worker list with "Money bonuses may or may not apply depending on the
    campaign", and in this campaign they do - the total multiplies the
    stipend (part 3, R9). Bonuses are additive into one figure and double
    with a second copy of an ability, like every other bonus.

    Abilities whose money bonus is the literal word "none", and abilities
    the character cannot take, contribute nothing.
    """
    total = 0
    for ability_id, ability in PROFESSION_ABILITIES.items():
        raw = (ability.money_bonus or "").strip().rstrip("%")
        if not raw.isdigit():
            continue
        total += int(raw) * ability_count(character_data, ability_id)
    return total


def holds_ability(character_data: Any, ability_id: str) -> bool:
    """Whether the character has taken *ability_id* at all.

    The readable form of ``ability_count(...) > 0`` for the many gates that
    only care whether a ritual was learned, not how deeply.
    """
    return ability_count(character_data, ability_id) > 0
