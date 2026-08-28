"""Roll-history helper functions.

The actual REST endpoints live in ``app/routes/rolls.py``; this module
just encapsulates the auth predicate and the payload sanitizer.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from app.game_data import SCHOOL_KNACKS, SKILLS
from app.models import Character
from app.services.auth import (
    get_admin_ids,
    get_all_editors,
    is_owning_player,
)


# Maximum size of the JSON payload we'll accept on a single roll. A
# normal roll result with full bonus breakdown serializes to a few KB;
# this cap protects the table from a misbehaving / malicious client
# without rejecting any realistic payload.
MAX_PAYLOAD_BYTES = 32 * 1024

# Maximum length of the player annotation. 2000 chars matches the spec.
MAX_ANNOTATION_LEN = 2000


def should_record_roll(
    user_discord_id: Optional[str],
    character: Character,
    owner_granted_ids: list,
    admin_ids: Optional[list] = None,
) -> Tuple[bool, bool]:
    """Decide whether to persist a roll the user just made.

    Returns ``(record, is_owner_roll)``:
    - ``(True, True)``  - user IS the character's owner (whether or not
      they are also an admin). Recorded as an owner roll.
    - ``(True, False)`` - user is a NON-admin editor (in
      ``character.editor_discord_ids`` or in the owner's
      ``granted_account_ids``). Recorded as a non-owner-editor roll
      with the actor's discord id captured.
    - ``(False, False)`` - anonymous, any admin who is NOT the owner
      (regardless of editor-list membership), or any non-editor
      visitor. The route returns 204 in this case.

    The admin-blanket-exclusion rule: GMs / admins are always treated as
    test rollers on characters they don't own, even if they have been
    explicitly added to ``editor_discord_ids`` or granted account-level
    access. This matches the spec where the GM should never accidentally
    pollute someone else's roll history.

    ``owner_granted_ids`` is the owner's account-level grant list
    (typically ``owner.granted_account_ids``); pass ``[]`` when the
    owner row isn't loaded.
    """
    if not user_discord_id:
        return False, False
    if is_owning_player(user_discord_id, character.owner_discord_id):
        return True, True
    if admin_ids is None:
        admin_ids = get_admin_ids()
    if user_discord_id in admin_ids:
        # Admin who is NOT the owner: never record. Editor-list membership
        # is ignored - admins are always considered test rollers.
        return False, False
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner_granted_ids or [],
    )
    if user_discord_id in all_editors:
        return True, False
    return False, False


# Roll keys that are rolled off the ``attack`` combat skill. ``parry`` is
# the only key that maps to the parry skill, so it needs no set.
_ATTACK_ROLL_KEYS = frozenset({
    "attack", "double_attack", "counterattack", "lunge",
})


def skill_rank_for_roll(
    roll_key: Optional[str], character: Character,
) -> Optional[int]:
    """The character's rank in the skill / knack a ``roll_key`` names.

    Recorded into the roll payload at create time (see
    ``app.routes.rolls.create_roll``) so the GM API can report the rank the
    character HAD when the roll was made rather than the rank they have now.
    Contested rolls are scored partly on skill rank, and a ``7k3`` formula
    does not reveal it - trait and skill are already summed in the dice
    count - which is why players type ``38 Etiquette @3`` by hand today.

    Returns ``None`` for rolls that have no single governing rank (rings,
    wound checks, initiative, bless, freeform) and for any key naming an
    id that is not in the catalog. A known skill / knack the character has
    never bought returns ``0`` - "unskilled" is a real answer, not a
    missing one.
    """
    if not roll_key:
        return None
    if roll_key in _ATTACK_ROLL_KEYS:
        return int(character.attack or 0)
    if roll_key == "parry":
        return int(character.parry or 0)
    parts = roll_key.split(":")
    if len(parts) < 2:
        return None
    category, ident = parts[0], parts[1]
    if category == "skill":
        if ident not in SKILLS:
            return None
        return int((character.skills or {}).get(ident, 0))
    if category == "knack":
        if ident not in SCHOOL_KNACKS:
            return None
        knacks = character.knacks or {}
        if ident in knacks:
            return int(knacks[ident])
        return int((character.foreign_knacks or {}).get(ident, 0))
    return None


def coerce_payload(raw: Any) -> Dict[str, Any]:
    """Validate + size-cap the client roll payload.

    Returns a dict with whatever keys the client sent that survive
    sanitization. Mirrors the spirit of ``dice_card.parse_payload``
    (lenient on malformed input) but does NOT transform the shape
    because consumers (the readonly modal, the dice-card renderer)
    expect the raw JSON. If the payload exceeds MAX_PAYLOAD_BYTES
    we return ``{}`` rather than raise, so a misbehaving client
    silently loses the body without crashing the request.
    """
    if not isinstance(raw, dict):
        return {}
    try:
        encoded = json.dumps(raw)
    except (TypeError, ValueError):
        return {}
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return {}
    return raw


def coerce_action_die_spent(raw: Any) -> Optional[Dict[str, Any]]:
    """Validate the action_die_spent field. Accepts a dict with optional
    ``value`` (int 0-10) and ``source`` (string up to 200 chars), or None.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    out: Dict[str, Any] = {}
    if "value" in raw:
        try:
            v = int(raw["value"])
        except (TypeError, ValueError):
            v = 0
        out["value"] = max(0, min(10, v))
    if "source" in raw:
        s = raw["source"]
        if isinstance(s, str) and s:
            out["source"] = s[:200]
    return out or None


def coerce_tn(raw: Any) -> Optional[int]:
    """Validate the TN field. Returns int or None; clamps negative -> None."""
    if raw is None:
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    return v


def coerce_annotation(raw: Any) -> str:
    """Validate the annotation field. Returns trimmed string up to
    MAX_ANNOTATION_LEN characters. Non-string -> empty string."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if len(s) > MAX_ANNOTATION_LEN:
        s = s[:MAX_ANNOTATION_LEN]
    return s
