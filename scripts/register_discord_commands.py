#!/usr/bin/env python3
"""Register the bot's slash commands, and point Discord at this app.

Two jobs, either or both per run:

* ``--commands`` does a bulk overwrite of the application's command set,
  in ONE guild (``--guild``) or globally (``--global``). Guild-scoped
  commands appear instantly, where global ones take about an hour to
  propagate - so register in the test guild first and go global once it
  works. Bulk overwrite means the scope ends up with exactly the commands
  sent - anything previously registered there and not sent is removed.
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

The full set is registered by default and is never hand-maintained: it is
``discord_commands.command_definitions()`` - ``/roll``, one command per
non-combat skill in ``game_data.SKILLS``, the three allow-listed knacks and
``/initiative``. 23 commands against Discord's cap of 100 per scope.
``--only etiquette,roll`` registers a subset, for poking at one command.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import discord_api                # noqa: E402
from app.services.discord_commands import command_definitions  # noqa: E402


def select_commands(only: str) -> list:
    """The command definitions to send: all of them, or the named subset."""
    commands = command_definitions()
    wanted = [n.strip().lower() for n in (only or "").split(",") if n.strip()]
    if not wanted:
        return commands
    known = {c["name"] for c in commands}
    for name in wanted:
        if name not in known:
            raise SystemExit(f"unknown command: {name}")
    return [c for c in commands if c["name"] in wanted]


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
    parser.add_argument("--global", dest="global_scope", action="store_true",
                        help="register globally instead of in one guild")
    parser.add_argument("--only", default="",
                        help="comma-separated command names (default: all)")
    args = parser.parse_args()

    if not (args.commands or args.endpoint or args.list):
        parser.error("nothing to do: pass --commands, --endpoint, or --list")
    if not discord_api.application_id():
        parser.error("DISCORD_APPLICATION_ID is not set (source .env first)")
    if (args.commands or args.endpoint) and not discord_api.bot_token():
        parser.error("DISCORD_BOT_TOKEN is not set (source .env first)")

    commands = select_commands(args.only)

    if args.list:
        for command in commands:
            opts = " ".join(f"[{o['name']}]" for o in command["options"])
            print(f"/{command['name']} {opts}- {command['description']}")

    if args.commands:
        if args.global_scope:
            registered = discord_api.put_global_commands(commands)
            where = "globally (allow about an hour to propagate)"
        elif args.guild:
            registered = discord_api.put_guild_commands(args.guild, commands)
            where = f"in guild {args.guild}"
        else:
            parser.error(
                "--commands needs --guild (or $DISCORD_TEST_GUILD_ID), or --global"
            )
        print(f"registered {len(registered)} command(s) {where}:")
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
