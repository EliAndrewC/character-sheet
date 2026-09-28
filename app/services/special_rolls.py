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


def can_bless(character: Any, ritual: str) -> bool:
    """A Priest has every ritual; a profession character holds it or not."""
    if ritual not in BLESS_RITUALS:
        return False
    return character.school == "priest" or holds_ability(character, BLESS_RITUALS[ritual][1])


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
