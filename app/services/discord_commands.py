"""Discord slash commands that roll dice.

This is the domain half of the bot; ``app/routes/discord.py`` is the HTTP
half and ``app/services/discord_api.py`` is the wire. A roll made through a
slash command is born STRUCTURED - it writes its own ``RollHistory`` row
here rather than being reverse-engineered from a pasted PNG later - which
is exactly why this belongs in this repo rather than in the GM's tooling:
the dice math, the formula table and the authorization model are all
already here, and a second implementation elsewhere would drift.

**Command name -> roll.** Every basic and advanced skill in
``game_data.SKILLS`` is dispatchable by its own id, so ``/etiquette`` rolls
``skill:etiquette``. Only the commands actually registered with Discord are
reachable (see ``scripts/register_discord_commands.py``); this table is
what a registered name resolves to.

**Which character rolls.** In order:

1. ``DISCORD_ROLL_CHARACTER_OVERRIDES`` - a ``discord_id:character_id`` map
   for people whose slash commands should always target one specific
   character. The GM is the reason it exists: they own many NPCs and no
   single "their PC", so their rolls are pinned to a test character. It is
   an env var rather than a code constant so changing the pin is a Fly
   secret update, not a deploy.
2. Otherwise the character they OWN that belongs to a gaming group - that
   is the one they are actually playing. Ties (someone with two grouped
   characters) go to the most recently updated.

Anything else is an error the invoker sees privately, rather than a guess.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.game_data import SKILLS
from app.models import Character, RollHistory, User
from app.services.party import party_member_data, visible_party_members
from app.services.roll_engine import execute_roll, impaired_now
from app.services.rolls_history import should_record_roll, skill_rank_for_roll


log = logging.getLogger(__name__)

OVERRIDES_ENV_VAR = "DISCORD_ROLL_CHARACTER_OVERRIDES"


class CommandError(Exception):
    """A message to show the invoker privately instead of rolling."""


def character_overrides() -> Dict[str, int]:
    """Parse ``DISCORD_ROLL_CHARACTER_OVERRIDES`` into discord id -> char id.

    Format matches ``MAGIC_LOGIN_TOKENS``: comma-separated ``key:value``
    pairs. A malformed entry is skipped rather than raising - a typo in a
    secret should cost one person their pin, not take the bot down.
    """
    out: Dict[str, int] = {}
    for entry in (os.environ.get(OVERRIDES_ENV_VAR) or "").split(","):
        discord_id, sep, char_id = entry.strip().partition(":")
        if not sep or not discord_id.strip() or not char_id.strip().isdigit():
            continue
        out[discord_id.strip()] = int(char_id.strip())
    return out


def roll_key_for_command(name: str) -> Optional[str]:
    """The roll key a slash-command name maps to, or None if unknown."""
    ident = (name or "").strip().lower()
    return f"skill:{ident}" if ident in SKILLS else None


def resolve_character(db: Session, discord_id: str) -> Character:
    """Pick the character this Discord user rolls as. Raises CommandError."""
    pinned = character_overrides().get(discord_id)
    if pinned is not None:
        character = db.query(Character).filter(Character.id == pinned).first()
        if character is None:
            raise CommandError(
                f"Your rolls are pinned to character {pinned}, which no longer "
                "exists. Ask the GM to update the pin."
            )
        return character

    owned = (
        db.query(Character)
        .filter(
            Character.owner_discord_id == discord_id,
            Character.gaming_group_id.isnot(None),
        )
        .order_by(Character.updated_at.desc(), Character.id.desc())
        .all()
    )
    if not owned:
        raise CommandError(
            "I could not find a character for you. Rolls use the character you "
            "own that is assigned to a gaming group - set your group on the "
            "character's edit page, or ask the GM to pin a character to your "
            "Discord account."
        )
    return owned[0]


def run_roll_command(
    db: Session, command_name: str, discord_id: str,
) -> Tuple[str, Dict[str, Any]]:
    """Roll ``command_name`` for whoever invoked it.

    Returns ``(content, payload)`` - the message text and the dice-card
    payload to render - and records the roll. Raises ``CommandError`` with
    a message for the invoker when the command or the character cannot be
    resolved.
    """
    roll_key = roll_key_for_command(command_name)
    if roll_key is None:
        raise CommandError(f"I do not know how to roll `/{command_name}`.")

    character = resolve_character(db, discord_id)
    character_data = character.to_dict()
    party = party_member_data(
        visible_party_members(db, character, character.owner_discord_id)
    )

    payload = execute_roll(character_data, roll_key, party_members=party)
    if payload is None:  # pragma: no cover - every SKILLS id builds a formula
        raise CommandError(
            f"{character.name} has no {command_name} roll available."
        )

    # Stamp the governing rank the same way POST /characters/{id}/rolls
    # does, so a slash-command row is indistinguishable from a sheet row
    # to GET /api/rolls.
    rank = skill_rank_for_roll(roll_key, character)
    if rank is not None:
        payload["skill_rank"] = rank
    _record(db, character, roll_key, payload, discord_id, character_data)

    skill_name = SKILLS[command_name.strip().lower()].name
    suffix = "" if rank is None else f"@{rank}"
    content = f"**{character.name}**: **{payload['total']}** {skill_name}{suffix}"
    return content, payload


def _record(
    db: Session, character: Character, roll_key: str,
    payload: Dict[str, Any], discord_id: str, character_data: Dict[str, Any],
) -> Optional[int]:
    """Persist the roll, following the sheet's recording rules exactly.

    ``should_record_roll`` carries the blanket admin exclusion: a GM rolling
    on a character they do not own is a test roller and leaves no trace.
    That rule is about the character, not the interface, so a slash command
    honours it too - the roll still happens and still answers in Discord, it
    just is not written down. Returns the row id, or None if not recorded.
    """
    owner = (
        db.query(User)
        .filter(User.discord_id == character.owner_discord_id)
        .first()
    )
    grants = (owner.granted_account_ids or []) if owner else []
    record, is_owner_roll = should_record_roll(discord_id, character, grants)
    if not record:
        return None

    row = RollHistory(
        character_id=character.id,
        roll_key=roll_key,
        actor_discord_id=discord_id,
        is_owner_roll=is_owner_roll,
        impaired_at_roll=impaired_now(character_data),
        tn=None,
        payload=payload,
        action_die_spent=None,
    )
    db.add(row)
    db.commit()
    return row.id


def invoker_discord_id(interaction: Dict[str, Any]) -> Optional[str]:
    """The Discord id of whoever ran the command.

    In a guild the user is under ``member.user``; in a DM it is the
    top-level ``user``. Discord sends exactly one of the two.
    """
    member = interaction.get("member")
    if isinstance(member, dict) and isinstance(member.get("user"), dict):
        return member["user"].get("id")
    user = interaction.get("user")
    if isinstance(user, dict):
        return user.get("id")
    return None
