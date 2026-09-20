"""Discord slash commands that roll dice.

This is the domain half of the bot; ``app/routes/discord.py`` is the HTTP
half and ``app/services/discord_api.py`` is the wire. A roll made through a
slash command is born STRUCTURED - it writes its own ``RollHistory`` row
here rather than being reverse-engineered from a pasted PNG later - which
is exactly why this belongs in this repo rather than in the GM's tooling:
the dice math, the formula table and the authorization model are all
already here, and a second implementation elsewhere would drift.

**The command set** is DERIVED, never hand-maintained (``command_definitions``
is what the registration script sends to Discord):

- one command per id in ``game_data.SKILLS`` - ``/etiquette`` rolls
  ``skill:etiquette``. That table holds exactly the non-combat skills;
  attack and parry live in ``COMBAT_SKILLS`` and iaijutsu is a knack, so
  combat is excluded by construction rather than by a filter somebody has to
  remember.
- ``/roll``, the same rolls behind one autocompleting ``skill`` option.
- ``KNACK_COMMANDS`` - an explicit allow-list of exactly three rolled knacks.
  The GM held every other school knack and school ability back by name for a
  later feature, so a fourth must not appear here by being rollable.
- ``/initiative``.

``tests/test_discord_bot.py`` guards all of that: a future move of attack
into ``SKILLS``, or a knack added casually, turns the gate red instead of
quietly registering a command.

**These commands WRITE.** A ``void`` option really spends the character's
void points, and ``/initiative`` really starts their combat round. Both go
through the same server-side operations the rest of the app uses
(``void_spend``, ``tracking``); no rule is reimplemented here. Everything
about one command happens in one transaction - the spend, the round, the
``RollHistory`` row - so a refusal leaves no trace at all.

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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.game_data import SCHOOL_KNACKS, SKILLS
from app.models import Character, RollHistory, User
from app.services.auth import can_edit_character, get_all_editors
from app.services.dice import build_all_roll_formulas
from app.services.party import party_member_data, visible_party_members
from app.services.roll_engine import execute_initiative, execute_roll, impaired_now
from app.services.rolls_history import should_record_roll, skill_rank_for_roll
from app.services.tracking import start_combat_round
from app.services.void_spend import (
    VoidSpendRefused,
    apply_void_spend,
    plan_void_spend,
)


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


#: CHAT_INPUT command, and the option types used below.
COMMAND_TYPE_CHAT_INPUT = 1
OPTION_TYPE_STRING = 3
OPTION_TYPE_INTEGER = 4

ROLL_COMMAND = "roll"
INITIATIVE_COMMAND = "initiative"

#: Slash-command name -> knack id. Discord requires lowercase names with no
#: spaces, so the commands are hyphenated while the roll keys stay
#: underscored: ``/oppose-social`` rolls ``knack:oppose_social``.
KNACK_COMMANDS: Dict[str, str] = {
    "oppose-social": "oppose_social",
    "oppose-knowledge": "oppose_knowledge",
    "commune": "commune",
}

#: Discord's ceiling on autocomplete choices. All 18 skills fit under it.
MAX_AUTOCOMPLETE_CHOICES = 25


def _void_option(description: str) -> Dict[str, Any]:
    return {
        "name": "void",
        "description": description,
        "type": OPTION_TYPE_INTEGER,
        "required": False,
        "min_value": 0,
        "max_value": 10,
    }


_VOID = "Void points to spend on the roll (+1k1 each)"


def command_definitions() -> List[Dict[str, Any]]:
    """Every slash command, in the shape Discord's bulk overwrite takes."""

    def chat(name: str, description: str, options: List[dict]) -> Dict[str, Any]:
        return {
            "name": name,
            "type": COMMAND_TYPE_CHAT_INPUT,
            "description": description[:100],
            "options": options,
        }

    commands = [
        chat(ROLL_COMMAND, "Roll any skill for your character", [
            {
                "name": "skill",
                "description": "Which skill to roll",
                "type": OPTION_TYPE_STRING,
                "required": True,
                "autocomplete": True,
            },
            _void_option(_VOID),
        ]),
    ]
    for skill_id in sorted(SKILLS):
        commands.append(chat(
            skill_id, f"Roll {SKILLS[skill_id].name} for your character",
            [_void_option(_VOID)],
        ))
    for name, knack_id in KNACK_COMMANDS.items():
        knack = SCHOOL_KNACKS[knack_id]
        extra = (
            "Void points to spend on top of the one Commune costs"
            if knack_id == "commune" else _VOID
        )
        commands.append(chat(
            name, f"Roll {knack.name} for your character", [_void_option(extra)],
        ))
    # No void option: "You begin each round by rolling dice equal to your
    # Void Ring plus 1 without spending void points" (rules/03-combat.md).
    commands.append(chat(
        INITIATIVE_COMMAND,
        "Roll initiative and start your character's combat round", [],
    ))
    return commands


def command_names() -> List[str]:
    return [c["name"] for c in command_definitions()]


def _options(data: Dict[str, Any]) -> Dict[str, Any]:
    """``{option name: value}`` for a command's submitted options."""
    out: Dict[str, Any] = {}
    for opt in (data or {}).get("options") or []:
        if isinstance(opt, dict) and isinstance(opt.get("name"), str):
            out[opt["name"]] = opt.get("value")
    return out


def _skill_id_from_text(raw: Any) -> Optional[str]:
    """A skill id from what ``/roll`` was given. Autocomplete sends the id,
    but a player can ignore the completions and type, so the display name
    is accepted too - any case, spaces or hyphens for underscores. Anything
    else is None."""
    text = "_".join(str(raw or "").strip().lower().replace("-", " ").split())
    return text if text in SKILLS else None


def roll_key_for_command(
    name: str, options: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """The roll key a slash command maps to, or None if there is none."""
    ident = (name or "").strip().lower()
    if ident == ROLL_COMMAND:
        skill_id = _skill_id_from_text((options or {}).get("skill"))
        return f"skill:{skill_id}" if skill_id else None
    if ident in SKILLS:
        return f"skill:{ident}"
    if ident in KNACK_COMMANDS:
        return f"knack:{KNACK_COMMANDS[ident]}"
    if ident == INITIATIVE_COMMAND:
        return "initiative"
    return None


def autocomplete_skills(typed: Any) -> List[Dict[str, str]]:
    """Choices for ``/roll``'s ``skill`` option.

    Case-insensitive over skill NAMES, prefix matches first and then
    substring matches, each group alphabetical. Skills only - the three
    rolled knacks have their own commands, and listing any knack here would
    advertise a category these commands do not cover. Never raises: an
    autocomplete cannot be deferred and must not error at the player, so
    any failure returns the plain list.
    """
    skills = sorted(SKILLS.values(), key=lambda s: s.name.lower())
    everything = [{"name": s.name, "value": s.id} for s in skills]
    try:
        needle = str(typed or "").strip().lower()
        if not needle:
            return everything[:MAX_AUTOCOMPLETE_CHOICES]
        prefix = [s for s in skills if s.name.lower().startswith(needle)]
        inside = [
            s for s in skills
            if needle in s.name.lower() and s not in prefix
        ]
        return [
            {"name": s.name, "value": s.id} for s in prefix + inside
        ][:MAX_AUTOCOMPLETE_CHOICES]
    except Exception:
        return everything[:MAX_AUTOCOMPLETE_CHOICES]


def focused_option_value(data: Dict[str, Any]) -> Any:
    """What the player has typed so far into the option being completed."""
    for opt in (data or {}).get("options") or []:
        if isinstance(opt, dict) and opt.get("focused"):
            return opt.get("value")
    return ""


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


def _require_edit_access(db: Session, character: Character, discord_id: str) -> None:
    """These commands write, so the invoker must be someone who could make
    the same change on the sheet. Resolution only ever returns an owned or
    GM-pinned character, which already implies this - but that is a property
    of today's resolution rules, and this check is what keeps a later change
    to them from quietly becoming a write hole."""
    owner = (
        db.query(User)
        .filter(User.discord_id == character.owner_discord_id)
        .first()
    )
    editors = get_all_editors(
        character.editor_discord_ids or [],
        (owner.granted_account_ids or []) if owner else [],
    )
    if not can_edit_character(discord_id, character.owner_discord_id, editors):
        raise CommandError(
            f"You do not have edit access to {character.name}, so you cannot "
            "roll for them from Discord."
        )


def _void_count(options: Dict[str, Any]) -> int:
    raw = options.get("void")
    if raw is None or isinstance(raw, bool):
        return 0
    try:
        count = int(raw)
    except (TypeError, ValueError, OverflowError):
        raise CommandError("`void` must be a whole number of void points.")
    if count < 0:
        raise CommandError("`void` cannot be negative.")
    return count


def _void_suffix(activation: int, spent: int) -> str:
    """The spend annotation on the posted line.

    ALWAYS inside parentheses: gm-assistant's roll capture strips ``(...)``
    spans before parsing, so a bracketed void note cannot be misread as a
    second roll. It pins these shapes with fixtures - change one and say so.
    """
    parts = []
    if activation:
        parts.append(f"{activation} void to activate")
    if spent:
        parts.append(f"{spent} void")
    return f" ({', '.join(parts)})" if parts else ""


def run_command(
    db: Session, data: Dict[str, Any], discord_id: str,
) -> Tuple[str, Dict[str, Any]]:
    """Run one slash command for whoever invoked it.

    ``data`` is the interaction's ``data`` object (command name + options).
    Returns ``(content, payload)`` - the message text and the dice-card
    payload to render. Raises ``CommandError`` with a private message for
    the invoker when the command cannot be run; in that case NOTHING has
    happened - no dice, no void spent, no row written.
    """
    command_name = str((data or {}).get("name") or "").strip().lower()
    options = _options(data)
    roll_key = roll_key_for_command(command_name, options)
    if roll_key is None:
        if command_name == ROLL_COMMAND:
            raise CommandError(
                f"I do not know a skill called `{options.get('skill') or ''}`. "
                "Pick one from the list `/roll` offers."
            )
        raise CommandError(f"I do not know how to roll `/{command_name}`.")

    character = resolve_character(db, discord_id)
    _require_edit_access(db, character, discord_id)
    # All-or-nothing by construction: every check that can refuse runs
    # BEFORE anything is changed, and each command commits exactly once, at
    # the end. An unexpected failure in between leaves only uncommitted
    # changes on a request-scoped session, which are discarded with it.
    if roll_key == "initiative":
        return _run_initiative(db, character, discord_id)
    return _run_roll(db, character, discord_id, roll_key, _void_count(options))


def _run_roll(
    db: Session, character: Character, discord_id: str,
    roll_key: str, void_requested: int,
) -> Tuple[str, Dict[str, Any]]:
    character_data = character.to_dict()
    party = party_member_data(
        visible_party_members(db, character, character.owner_discord_id)
    )
    formula = build_all_roll_formulas(
        character_data, party_members=party,
    ).get(roll_key)
    kind, _, ident = roll_key.partition(":")
    if not formula:
        # build_all_roll_formulas emits a knack formula only for a knack the
        # character holds, so "no formula" IS "does not have it".
        name = SCHOOL_KNACKS[ident].name if kind == "knack" else ident
        raise CommandError(f"{character.name} does not have the {name} knack.")
    label = formula.get("label") or roll_key

    # Discordant: no void on skills or knacks. The flag is the formula
    # layer's; the activation point below is a cost, not a spend ON the
    # roll, and the sheet still charges it, so it is not refused here.
    if void_requested and formula.get("void_blocked"):
        raise CommandError(
            f"{character.name} is Discordant and cannot spend void points on "
            f"{label}. Nothing was rolled."
        )

    # Check the spend BEFORE rolling. The activation point comes first:
    # Commune reserves one point via the formula's ``requires_void_point``
    # and the optional ``void`` is checked against what REMAINS (see
    # plan_void_spend). Do not reorder - a roll that was made and then
    # could not be paid for is exactly what this must never produce.
    activation = 1 if formula.get("requires_void_point") else 0
    try:
        plan = plan_void_spend(
            character, void_requested, activation_cost=activation,
            roll_label=label,
        )
    except VoidSpendRefused as exc:
        raise CommandError(f"{exc} Nothing was rolled.")

    payload = execute_roll(
        character_data, roll_key, party_members=party,
        void_spent=void_requested, formula=formula,
    )
    # Stamp the governing rank the same way POST /characters/{id}/rolls
    # does, so a slash-command row is indistinguishable from a sheet row
    # to GET /api/rolls.
    rank = skill_rank_for_roll(roll_key, character)
    if rank is not None:
        payload["skill_rank"] = rank

    # The spend and the record land in ONE commit. A GM rolling on a pinned
    # test character still spends that character's void even though the
    # roll leaves no history row - the no-history rule is about the record,
    # not about the dice.
    apply_void_spend(character, plan)
    _record(db, character, roll_key, payload, discord_id, character_data)
    db.commit()

    if kind == "skill":
        shown = SKILLS[ident].name + ("" if rank is None else f"@{rank}")
    else:
        shown = label
    content = (
        f"**{character.name}**: **{payload['total']}** {shown}"
        f"{_void_suffix(activation, void_requested)}"
    )
    return content, payload


def _run_initiative(
    db: Session, character: Character, discord_id: str,
) -> Tuple[str, Dict[str, Any]]:
    character_data = character.to_dict()
    party = party_member_data(
        visible_party_members(db, character, character.owner_discord_id)
    )
    result = execute_initiative(character_data, party_members=party)
    payload = result["payload"]
    start_combat_round(character, result["action_dice"])
    _record(db, character, "initiative", payload, discord_id, character_data)
    db.commit()

    # No bare number directly before a word here, on purpose: gm-assistant
    # parses "<number> <Skill>" out of these lines, and this is not a roll
    # total. Keep it that way if the wording changes.
    dice = ", ".join(str(d["value"]) for d in result["action_dice"]) or "none"
    content = f"**{character.name}** rolls initiative - action dice: {dice}"
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

    Flushes but does not commit: the caller commits the row together with
    whatever the command changed on the character.
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
    db.flush()
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
