"""Dark Secret privacy rules.

The Dark Secret disadvantage is the one piece of a character sheet that
is *not* public: only the character's owning player and the GM may read
the secret's description or see which other PC has been let in on it.
Other players - including players who hold edit access to the character
- never see either value, on any page or through any JSON endpoint.

Both values are **metadata**: editing them never flips the character to
Draft, never appears in revision-history diffs, is never captured in a
version snapshot, and is never overwritten by Discard / Revert. They are
written only through the dedicated ``POST /characters/{id}/dark-secret``
endpoint; the general autosave path ignores any ``dark_secret`` entry
the client sends and preserves whatever is persisted.

Storage: ``Character.advantage_details["dark_secret"]`` is a dict with
``text`` (the secret, owner + GM editable) and ``player`` (the discord
id of the other player whose character knows the secret; GM-only
editable - the owning player can see the pick but not change it).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.auth import get_admin_ids

DARK_SECRET_ID = "dark_secret"


def can_view_dark_secret(
    viewer_discord_id: Optional[str],
    owner_discord_id: Optional[str],
    admin_ids: Optional[List[str]] = None,
) -> bool:
    """Owner or GM only. Granted editors and account-level grantees are
    deliberately excluded - see the module docstring."""
    if not viewer_discord_id:
        return False
    if viewer_discord_id == owner_discord_id:
        return True
    if admin_ids is None:
        admin_ids = get_admin_ids()
    return viewer_discord_id in admin_ids


def can_set_dark_secret_knower(
    viewer_discord_id: Optional[str],
    admin_ids: Optional[List[str]] = None,
) -> bool:
    """Only the GM decides which other PC knows the secret."""
    if not viewer_discord_id:
        return False
    if admin_ids is None:
        admin_ids = get_admin_ids()
    return viewer_discord_id in admin_ids


def strip_dark_secret(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a copy of ``advantage_details`` with the dark secret removed.

    Used before any per-advantage details reach a page, a JSON payload,
    a version snapshot, or a diff. The *fact* that the character has the
    disadvantage stays in ``character.disadvantages`` and is public; only
    the secret itself and its knower are stripped.
    """
    if not details:
        return {}
    return {k: v for k, v in details.items() if k != DARK_SECRET_ID}


def merge_dark_secret(
    incoming: Optional[Dict[str, Any]],
    persisted: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Combine a client-supplied ``advantage_details`` dict with the
    persisted one so the client can never read, overwrite, or clear the
    dark secret through the general autosave path.

    The incoming dark_secret entry (if any) is discarded; the persisted
    entry (if any) is carried forward untouched.
    """
    merged = strip_dark_secret(incoming if isinstance(incoming, dict) else {})
    existing = (persisted or {}).get(DARK_SECRET_ID)
    if existing:
        merged[DARK_SECRET_ID] = existing
    return merged


def details_for_viewer(
    details: Optional[Dict[str, Any]],
    viewer_discord_id: Optional[str],
    owner_discord_id: Optional[str],
    admin_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """``advantage_details`` as a given viewer is allowed to see them."""
    if can_view_dark_secret(viewer_discord_id, owner_discord_id, admin_ids):
        return dict(details or {})
    return strip_dark_secret(details)


def knower_display_name(
    detail: Optional[Dict[str, Any]],
    db: Session,
) -> str:
    """Display name of the player whose character knows the secret, or
    ``""`` when the GM hasn't chosen yet (or the id no longer resolves)."""
    from app.models import User

    if not detail:
        return ""
    pid = detail.get("player")
    if pid:
        user = db.query(User).filter(User.discord_id == pid).first()
        if user:
            return user.display_name or user.discord_name or ""
    return ""


def dark_secret_view(
    character,
    db: Session,
    viewer_discord_id: Optional[str],
) -> Dict[str, Any]:
    """Everything the editor page needs to render the Dark Secret box and
    modal for this viewer. Values are blank unless the viewer may see them,
    so the payload is safe to embed in the page for any editor."""
    can_view = can_view_dark_secret(viewer_discord_id, character.owner_discord_id)
    can_set_knower = can_set_dark_secret_knower(viewer_discord_id)
    detail = (character.advantage_details or {}).get(DARK_SECRET_ID) or {}
    if not can_view:
        return {
            "can_view": False,
            "can_set_knower": False,
            "text": "",
            "knower_player_id": "",
            "knower_name": "",
        }
    return {
        "can_view": True,
        "can_set_knower": can_set_knower,
        "text": detail.get("text") or "",
        "knower_player_id": detail.get("player") or "",
        "knower_name": knower_display_name(detail, db),
    }


def knower_choices(character, db: Session) -> List[Dict[str, Any]]:
    """Players the GM can pick as the one whose character knows the
    secret: every registered user except the character's own owner,
    alphabetized by display name."""
    from app.models import User

    users = [
        u for u in db.query(User).all()
        if u.discord_id != character.owner_discord_id
    ]
    users.sort(key=lambda u: (u.display_name or u.discord_name or "").casefold())
    return [
        {"discord_id": u.discord_id, "name": u.display_name or u.discord_name or u.discord_id}
        for u in users
    ]
