"""Gaming-group party lookup shared by the sheet and the Discord bot.

Several L7R mechanics reach across a gaming group - Priest 2nd Dan grants
the whole party a free raise on bragging / precepts / open sincerity,
Daidoji 3rd Dan hands out counterattack raises - so
``build_all_roll_formulas`` takes a ``party_members`` list. Building that
list correctly involves a visibility rule that is easy to get subtly wrong,
which is why it lives here rather than being written out at each call site:
the sheet (``app/routes/pages.py``) and the Discord roll commands
(``app/services/discord_commands.py``) must agree, or the same roll would
come out differently depending on where it was made.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.game_data import SCHOOLS
from app.models import Character, User
from app.services.auth import can_view_drafts, get_admin_ids


def visible_party_members(
    db: Session, character: Character, viewer_discord_id: Optional[str],
) -> List[Character]:
    """The other characters in ``character``'s gaming group this viewer may see.

    Hidden party members are filtered out for viewers without edit access
    to them: their existence would otherwise leak through the party-effect
    lists built on top of this. Returns ``[]`` for a character with no
    gaming group.
    """
    if not character.gaming_group_id:
        return []
    party = (
        db.query(Character)
        .filter(
            Character.gaming_group_id == character.gaming_group_id,
            Character.id != character.id,
        )
        .all()
    )
    if not any(p.is_hidden for p in party):
        return party

    owner_ids = {p.owner_discord_id for p in party
                 if p.is_hidden and p.owner_discord_id}
    owners = (
        db.query(User).filter(User.discord_id.in_(owner_ids)).all()
        if owner_ids else []
    )
    grants = {u.discord_id: (u.granted_account_ids or []) for u in owners}
    admin_ids = get_admin_ids()
    return [
        p for p in party
        if not p.is_hidden
        or can_view_drafts(
            viewer_discord_id, p.owner_discord_id,
            grants.get(p.owner_discord_id, []), admin_ids,
        )
    ]


def party_member_dan(member: Character) -> int:
    """A party member's Dan: the lowest rank among their school knacks.

    Knacks start at rank 1 for free, so an unset knack counts as 1 rather
    than 0 - a character who simply has not had the rank written down is
    not a 0th Dan.
    """
    school = SCHOOLS.get(member.school)
    if not school:
        return 0
    ranks = [(member.knacks or {}).get(k, 1) for k in school.school_knacks]
    return min(ranks) if ranks else 0


def party_member_data(members: List[Character]) -> List[Dict[str, Any]]:
    """Shape party members into the dicts ``build_all_roll_formulas`` wants."""
    return [
        {
            "name": m.name,
            "school": m.school,
            "dan": party_member_dan(m),
            "advantages": m.advantages or [],
            "disadvantages": m.disadvantages or [],
            "campaign_advantages": m.campaign_advantages or [],
            "campaign_disadvantages": m.campaign_disadvantages or [],
        }
        for m in members
    ]
