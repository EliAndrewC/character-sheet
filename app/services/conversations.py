"""The GM's open conversation, and what Discern Honor reads out of it.

Discern Honor has no dice roll: the GM tells the player a number. The true
Honor lives on Obsidian Portal, which only the GM's ``gm-assistant`` REPL can
read, and only the REPL knows which NPC is being talked to and when the
conversation starts and ends. So the REPL computes, when the GM opens a
conversation, what each character with the knack would be told, and hands
this app ONLY those told values. ``/discern-honor`` is then a lookup.

**That is the whole design: nothing here computes anything, so asking twice
in one conversation cannot give two answers.** No true Honor value is ever
sent here, and ``told`` is stored and returned exactly as it arrived. If a
change to this module finds itself doing arithmetic on ``told``, the design
has gone wrong.

One open conversation per gaming group. A conversation left open for more
than ``CONVERSATION_TTL`` is treated as not open, lazily at read time: the
REPL can die mid-session without closing anything, and the failure to avoid
is the bot confidently answering about an NPC who left the scene yesterday.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import (
    Character,
    Conversation,
    ConversationDiscernHonor,
    GamingGroup,
)


#: Longer than any session and shorter than the gap between two.
CONVERSATION_TTL = timedelta(hours=12)

MAX_ID_LENGTH = 128

DISCERN_HONOR_KNACK = "discern_honor"


class ConversationError(Exception):
    """A refused write. ``status`` is the HTTP status the route answers with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utcnow() -> datetime:
    """Naive UTC, to match what SQLite's ``func.now()`` stores elsewhere."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else dt.isoformat() + "Z"


def is_expired(conversation: Conversation, now: Optional[datetime] = None) -> bool:
    return (now or utcnow()) - conversation.opened_at > CONVERSATION_TTL


def open_conversation(
    db: Session, group_id: Optional[int], now: Optional[datetime] = None,
) -> Optional[Conversation]:
    """The group's open, unexpired conversation, or None."""
    if group_id is None:
        return None
    conversation = (
        db.query(Conversation)
        .filter(Conversation.gaming_group_id == group_id)
        .first()
    )
    if conversation is None or is_expired(conversation, now):
        return None
    return conversation


def serialize(conversation: Conversation) -> Dict[str, Any]:
    return {
        "conversation_id": conversation.id,
        "group": conversation.gaming_group_id,
        "npc_ref": conversation.npc_ref or "",
        "opened_at": _iso_utc(conversation.opened_at),
        "expires_at": _iso_utc(conversation.opened_at + CONVERSATION_TTL),
        "discern_honor": [
            {
                "character_id": entry.character_id,
                "told": entry.told,
                "asked_at": _iso_utc(entry.asked_at),
            }
            for entry in conversation.entries
        ],
    }


# ---------------------------------------------------------------------------
# Opening (PUT /api/conversation)
# ---------------------------------------------------------------------------


def _parse_opened_at(raw: Any) -> datetime:
    """ISO-8601 with an explicit offset -> naive UTC. A naive value is
    refused rather than assumed to be UTC, for the reason ``since`` on
    ``/api/rolls`` is: a wrong guess here would silently shift the expiry."""
    if not isinstance(raw, str) or not raw.strip():
        raise ConversationError(
            "opened_at is required (ISO-8601 with an explicit timezone)"
        )
    text = raw.strip()
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ConversationError("opened_at is not a valid ISO-8601 timestamp")
    if parsed.tzinfo is None:
        raise ConversationError("opened_at must carry an explicit timezone offset")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_entries(db: Session, raw: Any) -> List[Tuple[int, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConversationError("discern_honor must be a list")
    out: List[Tuple[int, Any]] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict) or not _is_int(item.get("character_id")):
            raise ConversationError(
                "each discern_honor entry needs an integer character_id"
            )
        character_id = item["character_id"]
        told = item.get("told")
        if (
            isinstance(told, bool) or not isinstance(told, (int, float))
            or not math.isfinite(told)
        ):
            raise ConversationError(
                f"told for character {character_id} must be a number"
            )
        if character_id in seen:
            raise ConversationError(
                f"character {character_id} appears twice in discern_honor"
            )
        seen.add(character_id)
        out.append((character_id, told))
    if seen:
        known = {
            row[0] for row in
            db.query(Character.id).filter(Character.id.in_(seen)).all()
        }
        missing = sorted(seen - known)
        if missing:
            raise ConversationError(
                "unknown character_id: " + ", ".join(str(m) for m in missing)
            )
    return out


def put_conversation(db: Session, body: Any) -> Conversation:
    """Open, resume or replace a group's conversation. Flushes, no commit.

    Everything is validated before anything is touched, so a refused PUT
    leaves the previous conversation exactly as it was.

    **The id that is already open keeps every existing entry's ``told`` and
    ``asked_at``**; only characters not yet present are added. That is what
    makes a retried or crash-resumed open harmless: a value a player has
    already been shown can never change under them. ``npc_ref`` and
    ``opened_at`` take the request's values - they are the REPL's to state,
    and a retry sends the same ones. A NEW id replaces the group's
    conversation outright, entries and all.
    """
    if not isinstance(body, dict):
        raise ConversationError("the body must be a JSON object")
    conversation_id = body.get("conversation_id")
    if (
        not isinstance(conversation_id, str) or not conversation_id.strip()
        or len(conversation_id) > MAX_ID_LENGTH
    ):
        raise ConversationError(
            f"conversation_id must be a string of 1-{MAX_ID_LENGTH} characters"
        )
    group_id = body.get("group")
    if not _is_int(group_id):
        raise ConversationError("group must be an integer gaming_groups.id")
    npc_ref = body.get("npc_ref", "")
    if npc_ref is None:
        npc_ref = ""
    if not isinstance(npc_ref, str):
        raise ConversationError("npc_ref must be a string")
    opened_at = _parse_opened_at(body.get("opened_at"))
    entries = _parse_entries(db, body.get("discern_honor"))
    if db.query(GamingGroup).filter(GamingGroup.id == group_id).first() is None:
        raise ConversationError(f"unknown group: {group_id}", status=404)

    conversation = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if conversation is not None and conversation.gaming_group_id != group_id:
        raise ConversationError(
            f"conversation {conversation_id} belongs to another group", status=409,
        )
    if conversation is None:
        previous = (
            db.query(Conversation)
            .filter(Conversation.gaming_group_id == group_id)
            .first()
        )
        if previous is not None:
            db.delete(previous)
            # The group column is unique, so the old row has to be gone
            # before the new one is inserted.
            db.flush()
        conversation = Conversation(id=conversation_id, gaming_group_id=group_id)
        db.add(conversation)

    conversation.npc_ref = npc_ref
    conversation.opened_at = opened_at
    present = {entry.character_id for entry in conversation.entries}
    for character_id, told in entries:
        if character_id not in present:
            conversation.entries.append(ConversationDiscernHonor(
                character_id=character_id, told=told,
            ))
    db.flush()
    return conversation


# ---------------------------------------------------------------------------
# Asking (/discern-honor)
# ---------------------------------------------------------------------------


def has_discern_honor(character: Character) -> bool:
    """School knack or foreign knack - the same merge ``/api/characters``
    reports, which is what the REPL picked its entries from."""
    knacks = dict(character.knacks or {})
    knacks.update(character.foreign_knacks or {})
    try:
        return int(knacks.get(DISCERN_HONOR_KNACK) or 0) >= 1
    except (TypeError, ValueError):
        return False


def format_told(told: Any) -> str:
    """One decimal place, as the rule states Honor. Formatting only."""
    return f"{told:.1f}"


def discern_honor_reply(
    db: Session, character: Character, now: Optional[datetime] = None,
) -> str:
    """The private reply to ``/discern-honor``. Flushes, no commit.

    The success text is a function of ``told`` alone, so asking again is
    byte-identical; only the FIRST successful ask sets ``asked_at``. It
    deliberately says nothing about how accurate the number is, how many
    conversations there have been, or whether it is final - the rule gives
    the player a number and no error bar - and it never names the NPC,
    because this app is never told who it is.
    """
    if not has_discern_honor(character):
        return f"{character.name} does not have the Discern Honor knack."
    conversation = open_conversation(db, character.gaming_group_id, now)
    if conversation is None:
        return "No conversation is open right now - ask the GM."
    entry = next(
        (e for e in conversation.entries if e.character_id == character.id), None,
    )
    if entry is None:
        return "The GM will have to tell you this one - ask the GM."
    if entry.asked_at is None:
        entry.asked_at = now or utcnow()
        db.flush()
    return (
        f"{character.name}'s current read of this character's Honor is "
        f"**{format_told(entry.told)}**."
    )
