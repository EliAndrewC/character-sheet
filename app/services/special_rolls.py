"""Rolls that are not a formula from ``build_all_roll_formulas``: the Priest
bless rituals, the Ide Diplomat / Isawa Ishi 3rd Dan "spend 1 void point
for Xk1" roll, and the freeform NkM roll.

One definition, read by both the sheet (``pages.py`` renders the buttons from
it) and the server roller (``roll_sessions``), so what a button offers and
what the server will roll cannot disagree (server-rolls-design Phase 1).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.professions import holds_ability
from app.services.void_spend import school_dan

BLESS_RITUALS = {
    "topic": ("Bless conversation topic", "priest_conversation_blessing"),
    "research": ("Bless research", "priest_research_blessing"),
}

FREEFORM_MAX_DICE = 30


def performs_impaired_ritual(character: Any) -> bool:
    """The sick-or-impaired ritual: the Priest school has every ritual; a
    profession character has it only if they learned it."""
    return character.school == "priest" or holds_ability(character, "priest_ignore_penalties")


def can_bless(character: Any, ritual: str) -> bool:
    """A Priest has every ritual; a profession character holds it or not; a
    Kitsune Warden at 3rd Dan performs any, for a 3rd Dan free raise."""
    if ritual not in BLESS_RITUALS:
        return False
    return (character.school == "priest" or holds_ability(character, BLESS_RITUALS[ritual][1])
            or kitsune_rituals(character))


def kitsune_rituals(character: Any) -> bool:
    """Kitsune Warden 3rd Dan: "You may also perform priest rituals at the
    cost of one free raise per ritual" (rules/11-non_pc_schools.md)."""
    from app.services.void_spend import school_dan

    return character.school == "kitsune_warden" and school_dan(character.to_dict()) >= 3


def ritual_costs_a_raise(character: Any, ability_id: str) -> bool:
    """Whether performing this ritual spends a 3rd Dan free raise: only for a
    Kitsune Warden, and only for a ritual they do not hold some other way."""
    return (kitsune_rituals(character) and character.school != "priest"
            and not holds_ability(character, ability_id))


def ritual_raises_left(character: Any) -> int:
    """3rd Dan free raises left this adventure."""
    from app.services.per_adventure import per_adventure_abilities

    entry = next((a for a in per_adventure_abilities(character) if a["id"] == "adventure_raises"), None)
    if entry is None:
        return 0
    used = int((character.adventure_state or {}).get("adventure_raises_used", 0) or 0)
    return max(0, entry["max"] - used)


def spend_ritual_raise(character: Any, count: int = 1) -> None:
    """Spend (or, with a negative ``count``, give back) ritual free raises."""
    state = dict(character.adventure_state or {})
    state["adventure_raises_used"] = max(0, int(state.get("adventure_raises_used", 0) or 0) + count)
    character.adventure_state = state


def xk1_ability(char_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The 3rd Dan "spend 1 VP to add / subtract Xk1" roll, or None.

    Ide Diplomat: subtract Xk1 from someone's roll, X = tact. Isawa Ishi:
    add Xk1 to someone's roll, X = precepts.
    """
    school = char_data.get("school") or ""
    if school_dan(char_data) < 3:
        return None
    skills = char_data.get("skills") or {}
    if school == "ide_diplomat":
        return {"x": skills.get("tact", 0), "title": "Ide 3rd Dan", "verb": "subtract"}
    if school == "isawa_ishi":
        return {"x": skills.get("precepts", 0), "title": "Isawa Ishi 3rd Dan", "verb": "add"}
    return None


def xk1_formula(ability: Dict[str, Any]) -> Dict[str, Any]:
    """The formula ``xk1_ability``'s roll is rolled with: X kept 1, 10s
    rerolled. The sheet's button (``roll_sessions``) and the Discord boost
    commands both roll THIS, so the two cannot disagree. The void point is
    the roll's price, not dice on it - the caller charges it as an
    activation cost."""
    return {"label": ability["title"], "rolled": ability["x"], "kept": 1, "flat": 0,
            "reroll_tens": True, "bonuses": []}


def freeform_formula(rolled: Any, kept: Any, reroll_tens: Any) -> Dict[str, Any]:
    """A player's own NkM roll. Raises ValueError on a bad shape."""
    try:
        rolled, kept = int(rolled), int(kept)
    except (TypeError, ValueError):
        raise ValueError("rolled and kept must be whole numbers") from None
    if not 1 <= rolled <= FREEFORM_MAX_DICE:
        raise ValueError(f"roll between 1 and {FREEFORM_MAX_DICE} dice")
    kept = max(1, min(kept, rolled))
    reroll = bool(reroll_tens)
    return {
        "label": "Freeform Roll", "rolled": rolled, "kept": kept, "flat": 0,
        "reroll_tens": reroll, "no_reroll_reason": "" if reroll else "freeform",
        "bonuses": [],
    }
