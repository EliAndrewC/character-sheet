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

A conversation has one or more NPCs (character-sheet#6), the first the
primary; the GM ruled that Discern Honor works on every one of them. Each
NPC carries its own told values.

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
    ConversationNpc,
    GamingGroup,
)


#: Longer than any session and shorter than the gap between two.
CONVERSATION_TTL = timedelta(hours=12)

MAX_ID_LENGTH = 128
MAX_NAME_LENGTH = 80

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


def _serialize_entries(npc: ConversationNpc) -> List[Dict[str, Any]]:
    return [
        {
            "character_id": entry.character_id,
            "told": entry.told,
            "asked_at": _iso_utc(entry.asked_at),
        }
        for entry in npc.entries
    ]


def serialize(conversation: Conversation) -> Dict[str, Any]:
    npcs = [
        {
            "npc_ref": npc.npc_ref,
            "name": npc.name,
            "present": npc.present,
            "discern_honor": _serialize_entries(npc),
        }
        for npc in conversation.npcs
    ]
    primary = conversation.npcs[0] if conversation.npcs else None
    return {
        "conversation_id": conversation.id,
        "group": conversation.gaming_group_id,
        "opened_at": _iso_utc(conversation.opened_at),
        "expires_at": _iso_utc(conversation.opened_at + CONVERSATION_TTL),
        "npcs": npcs,
        # The one-NPC shape the deployed REPL still reads: the primary NPC's.
        # Goes away with the old PUT shape once gm-assistant has switched.
        "npc_ref": primary.npc_ref if primary else "",
        "discern_honor": npcs[0]["discern_honor"] if npcs else [],
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


def _parse_text(raw: Any, what: str, allow_empty: bool, limit: int) -> str:
    if raw is None and allow_empty:
        return ""
    if not isinstance(raw, str):
        raise ConversationError(f"{what} must be a string")
    if (not raw.strip() and not allow_empty) or len(raw) > limit:
        raise ConversationError(f"{what} must be a string of 1-{limit} characters")
    return raw


def _parse_npcs(db: Session, body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The request's NPCs, in order, each ``{npc_ref, name, present,
    entries}``.

    The old one-NPC shape (top-level ``npc_ref`` + ``discern_honor``, no
    names) is read as a one-NPC list, so the deployed REPL keeps working
    until it switches; it is the only way to send an NPC without a name.
    """
    legacy = [key for key in ("npc_ref", "discern_honor") if key in body]
    if "npcs" not in body:
        return [{
            "npc_ref": _parse_text(body.get("npc_ref", ""), "npc_ref", True, MAX_ID_LENGTH),
            "name": "",
            "present": True,
            "entries": _parse_entries(db, body.get("discern_honor")),
        }]
    if legacy:
        raise ConversationError(
            "send either npcs or the old npc_ref / discern_honor, not both"
        )
    raw = body["npcs"]
    if not isinstance(raw, list):
        raise ConversationError("npcs must be a list")
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ConversationError("each npc must be an object")
        npc_ref = _parse_text(item.get("npc_ref"), "npc_ref", False, MAX_ID_LENGTH)
        if any(npc["npc_ref"] == npc_ref for npc in out):
            raise ConversationError(f"npc_ref {npc_ref} appears twice in npcs")
        present = item.get("present", True)
        if not isinstance(present, bool):
            raise ConversationError(f"present for {npc_ref} must be true or false")
        out.append({
            "npc_ref": npc_ref,
            "name": _parse_text(item.get("name"), "name", False, MAX_NAME_LENGTH).strip(),
            "present": present,
            "entries": _parse_entries(db, item.get("discern_honor")),
        })
    return out


def _check_present_names(npcs: List[Tuple[str, bool]]) -> None:
    """Two present NPCs may not share a name: ``/discern-honor npc:`` and
    its autocomplete pick by name. A departed NPC may share one."""
    seen = set()
    for name, present in npcs:
        key = name.casefold()
        if present and name and key in seen:
            raise ConversationError(
                f"two present NPCs are both called {name}; give them distinct names"
            )
        if present:
            seen.add(key)


def put_conversation(db: Session, body: Any) -> Conversation:
    """Open, resume or replace a group's conversation. Flushes, no commit.

    Everything is validated before anything is touched, so a refused PUT
    leaves the previous conversation exactly as it was.

    **The id that is already open keeps every existing entry's ``told`` and
    ``asked_at``**; NPCs are matched by ``npc_ref``, and only characters an
    NPC does not have yet are added to it. That is what makes a retried or
    crash-resumed open harmless: a value a player has already been shown can
    never change under them. An NPC's ``name`` and ``present`` and the
    conversation's ``opened_at`` take the request's values - they are the
    REPL's to state. A new NPC is appended; one the request leaves out is
    kept as it was (the REPL never drops one). A NEW id replaces the group's
    conversation outright, NPCs and all.
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
    opened_at = _parse_opened_at(body.get("opened_at"))
    requested = _parse_npcs(db, body)
    if db.query(GamingGroup).filter(GamingGroup.id == group_id).first() is None:
        raise ConversationError(f"unknown group: {group_id}", status=404)

    conversation = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if conversation is not None and conversation.gaming_group_id != group_id:
        raise ConversationError(
            f"conversation {conversation_id} belongs to another group", status=409,
        )
    stored = {npc.npc_ref: npc for npc in conversation.npcs} if conversation else {}
    by_ref = {npc["npc_ref"]: npc for npc in requested}
    _check_present_names(
        [
            (by_ref[ref]["name"], by_ref[ref]["present"]) if ref in by_ref
            else (npc.name, npc.present)
            for ref, npc in stored.items()
        ]
        + [(n["name"], n["present"]) for n in requested if n["npc_ref"] not in stored]
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

    conversation.opened_at = opened_at
    for item in requested:
        npc = stored.get(item["npc_ref"])
        if npc is None:
            npc = ConversationNpc(
                npc_ref=item["npc_ref"], position=len(conversation.npcs),
            )
            conversation.npcs.append(npc)
        npc.name = item["name"]
        npc.present = item["present"]
        have = {entry.character_id for entry in npc.entries}
        for character_id, told in item["entries"]:
            if character_id not in have:
                npc.entries.append(ConversationDiscernHonor(
                    conversation_id=conversation_id,
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


def _read(db: Session, npc: ConversationNpc, character: Character,
          now: Optional[datetime]) -> Optional[Any]:
    """The told value for this character on this NPC, or None. Stamps the
    FIRST ask's ``asked_at``; later asks leave it where it is."""
    entry = next((e for e in npc.entries if e.character_id == character.id), None)
    if entry is None:
        return None
    if entry.asked_at is None:
        entry.asked_at = now or utcnow()
        db.flush()
    return entry.told


def discern_honor_reply(
    db: Session, character: Character, npc: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """The private reply to ``/discern-honor [npc]``. Flushes, no commit.

    The success text is a function of the told values and the NPCs' names
    alone, so asking again is byte-identical; only the FIRST successful ask
    of each NPC sets that entry's ``asked_at``. It deliberately says nothing
    about how accurate a number is, how many conversations there have been,
    or whether it is final - the rule gives the player a number and no error
    bar. It never shows ``npc_ref``. Without ``npc`` it answers for every
    present NPC; with one present, in the words it always used.
    """
    if not has_discern_honor(character):
        return f"{character.name} does not have the Discern Honor knack."
    conversation = open_conversation(db, character.gaming_group_id, now)
    if conversation is None:
        return "No conversation is open right now - ask the GM."
    present = [n for n in conversation.npcs if n.present]
    wanted = str(npc or "").strip()
    if wanted:
        match = next(
            (n for n in present if n.name.casefold() == wanted.casefold()), None,
        )
        if match is None:
            names = ", ".join(n.name for n in present if n.name) or "nobody"
            return (
                f"No one called {wanted[:MAX_NAME_LENGTH]} is in this "
                f"conversation. Present: {names}."
            )
        told = _read(db, match, character, now)
        if told is None:
            return "The GM will have to tell you this one - ask the GM."
        return (
            f"{character.name}'s current read of {match.name}'s Honor is "
            f"**{format_told(told)}**."
        )
    if not present:
        return "No one in this conversation is still here - ask the GM."
    if len(present) == 1:
        told = _read(db, present[0], character, now)
        if told is None:
            return "The GM will have to tell you this one - ask the GM."
        return (
            f"{character.name}'s current read of this character's Honor is "
            f"**{format_told(told)}**."
        )
    lines = [f"{character.name}'s current read of their Honor:"]
    for n in present:
        told = _read(db, n, character, now)
        label = n.name or "this character"
        lines.append(
            f"- {label}: the GM will have to tell you this one" if told is None
            else f"- {label}: **{format_told(told)}**"
        )
    return "\n".join(lines)


def present_npc_names(db: Session, character: Character) -> List[str]:
    """The names ``/discern-honor``'s ``npc`` option offers: the present
    NPCs of the character's group's open conversation, in order."""
    conversation = open_conversation(db, character.gaming_group_id)
    if conversation is None:
        return []
    return [n.name for n in conversation.npcs if n.present and n.name]
