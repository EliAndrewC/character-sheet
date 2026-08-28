#!/usr/bin/env python3
"""Register the bot's slash commands, and point Discord at this app.

Two jobs, either or both per run:

* ``--commands`` does a bulk overwrite of the application's command set in
  ONE guild. Guild-scoped commands appear instantly, where global ones take
  up to an hour to propagate, so development and testing stay guild-scoped.
  Bulk overwrite means the guild ends up with exactly the commands named on
  the command line - anything previously registered there and not listed is
  removed.
* ``--endpoint`` sets the application's Interactions Endpoint URL. Discord
  validates it before saving by POSTing a PING that must come back as a
  correctly-signed PONG, so **the app has to be deployed and reachable
  first** or this fails with Discord's own error text.

Reads ``DISCORD_BOT_TOKEN`` and ``DISCORD_APPLICATION_ID`` from the
environment (both live in the gitignored ``.env``)::

    set -a && source .env && set +a
    python3 scripts/register_discord_commands.py --commands --guild 1543009570157236274
    python3 scripts/register_discord_commands.py --endpoint \\
        --url https://l7r-character-sheet.fly.dev/discord/interactions
    python3 scripts/register_discord_commands.py --list --guild 1543009570157236274

By default only ``/etiquette`` is registered. ``--skills all`` registers one
command per skill in ``game_data.SKILLS``; ``--skills etiquette,sincerity``
picks a subset. Discord's cap is 100 commands per application per scope, so
all 18 skills fit comfortably.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.game_data import SKILLS                    # noqa: E402
from app.services import discord_api                # noqa: E402


#: CHAT_INPUT - an ordinary slash command.
COMMAND_TYPE_CHAT_INPUT = 1

DEFAULT_SKILLS = ["etiquette"]


def command_for_skill(skill_id: str) -> dict:
    """One slash command definition for a skill.

    The name must be lowercase with no spaces, which every skill id already
    is. Discord fuzzy-matches in the command picker, so ``/eti`` finds
    ``/etiquette``.
    """
    skill = SKILLS[skill_id]
    return {
        "name": skill_id,
        "type": COMMAND_TYPE_CHAT_INPUT,
        "description": f"Roll {skill.name} for your character"[:100],
    }


def parse_skills(raw: str) -> list:
    if raw.strip().lower() == "all":
        return sorted(SKILLS)
    out = []
    for ident in raw.split(","):
        ident = ident.strip().lower()
        if not ident:
            continue
        if ident not in SKILLS:
            raise SystemExit(f"unknown skill: {ident}")
        out.append(ident)
    return out or DEFAULT_SKILLS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commands", action="store_true",
                        help="bulk-overwrite the guild's command set")
    parser.add_argument("--endpoint", action="store_true",
                        help="set the application's interactions endpoint URL")
    parser.add_argument("--list", action="store_true",
                        help="print the commands that would be registered")
    parser.add_argument("--guild", default=os.environ.get("DISCORD_TEST_GUILD_ID", ""),
                        help="guild id to register into (default $DISCORD_TEST_GUILD_ID)")
    parser.add_argument("--url", default="",
                        help="interactions endpoint URL, for --endpoint")
    parser.add_argument("--skills", default=",".join(DEFAULT_SKILLS),
                        help='"all", or a comma-separated list of skill ids')
    args = parser.parse_args()

    if not (args.commands or args.endpoint or args.list):
        parser.error("nothing to do: pass --commands, --endpoint, or --list")
    if not discord_api.application_id():
        parser.error("DISCORD_APPLICATION_ID is not set (source .env first)")
    if (args.commands or args.endpoint) and not discord_api.bot_token():
        parser.error("DISCORD_BOT_TOKEN is not set (source .env first)")

    commands = [command_for_skill(s) for s in parse_skills(args.skills)]

    if args.list:
        for command in commands:
            print(f"/{command['name']} - {command['description']}")

    if args.commands:
        if not args.guild:
            parser.error("--commands needs --guild (or $DISCORD_TEST_GUILD_ID)")
        registered = discord_api.put_guild_commands(args.guild, commands)
        print(f"registered {len(registered)} command(s) in guild {args.guild}:")
        for command in registered:
            print(f"  /{command['name']} (id {command['id']})")

    if args.endpoint:
        if not args.url:
            parser.error("--endpoint needs --url")
        result = discord_api.set_interactions_endpoint_url(args.url)
        print(
            "interactions endpoint is now "
            f"{result.get('interactions_endpoint_url')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
