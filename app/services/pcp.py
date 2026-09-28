"""Spending a Player Character Point (rules/10).

Shared by ``POST /characters/{id}/spend-pcp`` and by the roll-session
actions that spend one (a PCP reroll, free raise or reroll of 10s on a roll
the server made, server-rolls-design Phase 4), so the count, the XP cost and
the auto-published version are the same wherever the point was spent.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import Character
from app.services.nights_rest import _void_max
from app.services.versions import publish_character
from app.services.xp import pcp_next_cost, pcp_total_cost

PCP_USE_LABELS = {
    "reroll": "reroll a roll",
    "reroll_tens": "reroll 10s while impaired",
    "free_raise": "a free raise",
    "void_refresh": "refresh a void point",
}


class PcpRefused(ValueError):
    """A PCP that cannot be spent right now. Nothing changed."""


def spend_pcp(db: Session, character: Character, use: str,
              author_discord_id: Optional[str]) -> Dict[str, Any]:
    """Bump ``pcp_count`` and publish a version recording the spend.

    The character must be published and clean, so the version captures only
    the spend. ``void_refresh`` also regains one spent void point. The caller
    commits.
    """
    if use not in PCP_USE_LABELS:
        raise PcpRefused("Invalid PCP use")
    if character.publish_status != "published":
        raise PcpRefused("Apply or discard your pending changes before "
                         "spending a Player Character Point.")
    new_count = (character.pcp_count or 0) + 1
    character.pcp_count = new_count
    cost = pcp_total_cost(new_count) - pcp_total_cost(new_count - 1)  # = new_count
    void_max = _void_max(character)
    if use == "void_refresh":
        character.current_void_points = min(void_max, (character.current_void_points or 0) + 1)
    version = publish_character(
        character, db,
        summary=f"Spent Player Character Point #{new_count} ({cost} XP): {PCP_USE_LABELS[use]}",
        author_discord_id=author_discord_id,
    )
    return {
        "use": use,
        "pcp_count": new_count,
        "pcp_total_cost": pcp_total_cost(new_count),
        "pcp_next_cost": pcp_next_cost(new_count),
        "version_number": version.version_number,
        "current_void_points": character.current_void_points,
        "void_max": void_max,
    }
