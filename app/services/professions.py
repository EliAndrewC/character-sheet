"""Profession selection, ability sanitizing and display helpers.

A profession is taken INSTEAD of a school (profession-design/design.md D1),
so both live behind the editor's single school ``<select>``. Profession
options carry a ``profession:`` prefix on their value; ``split_school_or_
profession`` is the one place that prefix is understood, and it is also the
allow-list: an unknown id, or a profession that is not yet selectable,
resolves to "no school and no profession" rather than being written through.

Abilities are stored as an id -> count map because an ability may be taken
more than once (D4); ``sanitize_profession_abilities`` is the server-side
clamp that a crafted POST cannot get past.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.game_data import PROFESSION_BY_ABILITY, PROFESSIONS, SCHOOLS

# Prefix distinguishing a profession from a school in the editor's single
# school dropdown. Asserted in tests to not collide with any school id.
PROFESSION_SELECT_PREFIX = "profession:"


def split_school_or_profession(value: str) -> Tuple[str, str]:
    """Resolve a school-dropdown value into ``(school_id, profession_id)``.

    Exactly one of the two is non-empty, or both are empty. Unknown ids and
    professions that are not yet selectable resolve to ``("", "")`` - the
    caller then clears both, which is the correct outcome for a crafted
    payload naming a school or profession that does not exist.
    """
    value = (value or "").strip()
    if not value:
        return "", ""
    if value.startswith(PROFESSION_SELECT_PREFIX):
        pid = value[len(PROFESSION_SELECT_PREFIX):]
        prof = PROFESSIONS.get(pid)
        if prof is not None and prof.selectable:
            return "", pid
        return "", ""
    if value in SCHOOLS:
        return value, ""
    return "", ""


def select_value_for(school_id: str, profession_id: str) -> str:
    """Inverse of :func:`split_school_or_profession`, for rendering."""
    if profession_id:
        return f"{PROFESSION_SELECT_PREFIX}{profession_id}"
    return school_id or ""


def sanitize_profession_abilities(profession_id: str, raw: Any) -> Dict[str, int]:
    """Clamp an incoming ability map to what the rules actually allow.

    Drops ids that don't exist, ids belonging to a different profession, and
    non-positive or non-integer counts; clamps each remaining count to the
    profession's ``max_per_ability`` (2 everywhere except Priest rituals,
    which are once-only). Does NOT enforce the XP allowance - that is a
    validation warning rather than a silent truncation, so the player can
    see they have overcommitted instead of having picks vanish.
    """
    prof = PROFESSIONS.get(profession_id or "")
    if prof is None or not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, int] = {}
    for aid, count in raw.items():
        if PROFESSION_BY_ABILITY.get(aid) != prof.id:
            continue
        # bool is an int subclass; a JSON `true` is not a count.
        if isinstance(count, bool) or not isinstance(count, int):
            continue
        if count < 1:
            continue
        cleaned[aid] = min(count, prof.max_per_ability)
    return cleaned


def ability_counts_for_display(
    profession_id: str, abilities: Any
) -> List[Dict[str, Any]]:
    """Rows for the editor and the view sheet, in rules order.

    One row per ability the profession has, whether or not it is taken, so
    both surfaces can render the full list with the untaken ones dimmed.
    """
    prof = PROFESSIONS.get(profession_id or "")
    if prof is None:
        return []
    counts = abilities if isinstance(abilities, dict) else {}
    return [
        {
            "id": a.id,
            "ordinal": a.ordinal,
            "name": a.name,
            "text": a.text,
            "implemented": a.implemented,
            "reference_only": a.reference_only,
            "money_bonus": a.money_bonus,
            "ritual_time": a.ritual_time,
            "count": max(0, min(int(counts.get(a.id, 0) or 0), prof.max_per_ability)),
            "max": prof.max_per_ability,
        }
        for a in prof.abilities
    ]


def ability_count(character_data: Any, ability_id: str) -> int:
    """How many copies of *ability_id* this character has (0, 1 or 2).

    Accepts either a ``character_data`` dict or anything with a
    ``profession_abilities`` attribute, so formula builders and route code
    can share one accessor. Returns 0 when the character has no profession,
    which is every character until they pick one.
    """
    if character_data is None:
        return 0
    if isinstance(character_data, dict):
        profession = character_data.get("profession") or ""
        abilities = character_data.get("profession_abilities") or {}
    else:  # pragma: no cover - attribute form is used by route code only
        profession = getattr(character_data, "profession", "") or ""
        abilities = getattr(character_data, "profession_abilities", {}) or {}
    if not profession or PROFESSION_BY_ABILITY.get(ability_id) != profession:
        return 0
    prof = PROFESSIONS[profession]
    try:
        raw = int(abilities.get(ability_id, 0) or 0)
    except (TypeError, ValueError):  # pragma: no cover - sanitized on write
        return 0
    return max(0, min(raw, prof.max_per_ability))
