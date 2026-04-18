"""Authentication and authorization service.

Handles Discord OAuth whitelist checking, admin detection, and
character edit permissions.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional


def _get_list_from_env(key: str) -> List[str]:
    """Parse a comma-separated env var into a list of stripped strings."""
    val = os.environ.get(key, "")
    return [x.strip() for x in val.split(",") if x.strip()]


def get_whitelisted_ids() -> List[str]:
    return _get_list_from_env("DISCORD_WHITELIST_IDS")


def get_admin_ids() -> List[str]:
    return _get_list_from_env("ADMIN_DISCORD_IDS")


def get_test_login_tokens() -> Dict[str, str]:
    """Parse TEST_LOGIN_TOKENS env var into {token: discord_id} mapping.

    Format: ``uuid1:discord_id,uuid2:discord_id``
    """
    val = os.environ.get("TEST_LOGIN_TOKENS", "")
    result: Dict[str, str] = {}
    for entry in val.split(","):
        entry = entry.strip()
        if ":" in entry:
            token, discord_id = entry.split(":", 1)
            result[token.strip()] = discord_id.strip()
    return result


def is_whitelisted(discord_id: str) -> bool:
    return discord_id in get_whitelisted_ids()


def is_admin(discord_id: str) -> bool:
    return discord_id in get_admin_ids()


def can_view_drafts(
    viewer_discord_id: Optional[str],
    owner_discord_id: Optional[str],
    owner_granted_ids: List[str],
    admin_ids: Optional[List[str]] = None,
) -> bool:
    """Check if a user can view draft (unpublished) characters.

    Returns True if the user is:
    - The character's owner
    - An admin
    - Granted account-level access by the owner
    """
    if viewer_discord_id is None:
        return False
    if viewer_discord_id == owner_discord_id:
        return True
    if admin_ids is None:
        admin_ids = get_admin_ids()
    if viewer_discord_id in admin_ids:
        return True
    if viewer_discord_id in owner_granted_ids:
        return True
    return False


def get_all_editors(
    character_editor_ids: List[str],
    owner_granted_ids: List[str],
) -> List[str]:
    """Merge character-level editors with owner's account-level grants."""
    return list(set(character_editor_ids + owner_granted_ids))


def format_editor_list_text(
    viewer_id: str,
    all_editors: List[str],
    admin_ids: List[str],
    resolve_name: Callable[[str], str],
) -> str:
    """Build the "you and the GM" / "you, the GM, and Alice" label text.

    The viewer is always "you"; admins are collapsed into "the GM". Any
    other granted editors are listed by display name (falling back to the
    raw discord id if resolve_name returns an empty string).
    """
    extras = []
    seen = set()
    for editor_id in all_editors:
        if editor_id == viewer_id or editor_id in admin_ids or editor_id in seen:
            continue
        seen.add(editor_id)
        name = resolve_name(editor_id) or editor_id
        extras.append(name)

    if not extras:
        return "you and the GM"
    if len(extras) == 1:
        return f"you, the GM, and {extras[0]}"
    return "you, the GM, " + ", ".join(extras[:-1]) + f", and {extras[-1]}"


def can_edit_character(
    user_discord_id: Optional[str],
    character_owner_id: Optional[str],
    granted_editors: List[str],
    admin_ids: Optional[List[str]] = None,
) -> bool:
    """Check if a user can edit a character.

    Returns True if the user is:
    - The character's owner
    - An admin
    - In the granted_editors list (character-level or account-level)
    """
    if user_discord_id is None:
        return False
    if user_discord_id == character_owner_id:
        return True
    if admin_ids is None:
        admin_ids = get_admin_ids()
    if user_discord_id in admin_ids:
        return True
    if user_discord_id in granted_editors:
        return True
    return False
