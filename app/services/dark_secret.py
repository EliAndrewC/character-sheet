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
``text`` (the secret, owner + GM editable) and ``knower_character_id``
(the PC who knows; GM-only editable). A legacy ``player`` key (a
discord id from the old free-for-all dropdown) may still be present on
old rows and is displayed as a fallback when no character is chosen.
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
    """Human-readable name of whoever knows the secret, or ``""``.

    Prefers the chosen character's name; falls back to the legacy
    ``player`` discord id's display name for rows written before the
    knower became a GM-chosen character.
    """
    from app.models import Character, User

    if not detail:
        return ""
    cid = detail.get("knower_character_id")
    if cid:
        knower = db.query(Character).filter(Character.id == cid).first()
        if knower:
            return knower.name or ""
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
            "knower_character_id": None,
            "knower_name": "",
        }
    return {
        "can_view": True,
        "can_set_knower": can_set_knower,
        "text": detail.get("text") or "",
        "knower_character_id": detail.get("knower_character_id"),
        "knower_name": knower_display_name(detail, db),
    }


def knower_choices(character, db: Session) -> List[Dict[str, Any]]:
    """Candidate PCs the GM can pick as the one who knows the secret.

    Every other visible (non-hidden) character, with the members of this
    character's own gaming group listed first since that is almost always
    where the knower lives.
    """
    from app.models import Character

    others = [
        c for c in db.query(Character).all()
        if c.id != character.id and not c.is_hidden
    ]
    others.sort(key=lambda c: (
        0 if (character.gaming_group_id is not None
              and c.gaming_group_id == character.gaming_group_id) else 1,
        (c.name or "").lower(),
    ))
    return [
        {
            "id": c.id,
            "name": c.name or f"Character #{c.id}",
            "same_group": (
                character.gaming_group_id is not None
                and c.gaming_group_id == character.gaming_group_id
            ),
        }
        for c in others
    ]
