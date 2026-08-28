"""Discord interactions endpoint - the HTTP half of the roll bot.

Discord delivers slash commands as signed HTTPS POSTs to a single
"Interactions Endpoint URL" registered on the application, so the bot needs
no gateway and no always-on process: it is this one route.

Two constraints shape the flow:

- **Every request must be signature-verified.** Discord will not even save
  an interactions URL that fails to reject a bad signature, so the 401 path
  is part of registration, not just security.
- **Acknowledge within 3 seconds.** The roll itself is a few DB queries and
  some arithmetic, so it happens inline - which lets a bad command answer
  privately and immediately, and guarantees the roll is recorded even if
  Discord is unreachable afterwards. Only the genuinely slow part,
  rasterizing the dice card and uploading it, is deferred: the route
  answers with a deferred acknowledgement and a background task edits the
  real message in (Discord allows up to 15 minutes for that).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.services import discord_api
from app.services.discord_commands import (
    CommandError,
    invoker_discord_id,
    run_roll_command,
)


log = logging.getLogger(__name__)

router = APIRouter(prefix="/discord", tags=["discord"])


# Interaction types we receive, and response types we send.
# https://discord.com/developers/docs/interactions/receiving-and-responding
TYPE_PING = 1
TYPE_APPLICATION_COMMAND = 2
RESPONSE_PONG = 1
RESPONSE_MESSAGE = 4
RESPONSE_DEFERRED_MESSAGE = 5

#: MessageFlags.EPHEMERAL - only the invoker sees it. Used for every error,
#: so a mistyped command or an unlinked account does not clutter the
#: channel the group is playing in.
FLAG_EPHEMERAL = 1 << 6


def _ephemeral(message: str) -> JSONResponse:
    return JSONResponse({
        "type": RESPONSE_MESSAGE,
        "data": {"content": message, "flags": FLAG_EPHEMERAL},
    })


def deliver_card(interaction_token: str, content: str, payload: dict) -> None:
    """Render the dice card and edit it into the deferred response.

    Runs after the response has been sent. A render failure is not fatal:
    the roll has already happened and been recorded, and the text line
    carries the total, so fall back to posting that alone rather than
    leaving the invoker staring at "thinking...".
    """
    png = None
    try:
        from app.services.dice_card import render_png

        png = render_png(payload)
    except Exception as exc:  # pragma: no cover - defensive; renderer is tested
        log.warning("discord: dice-card render failed: %s", exc)
    discord_api.edit_original_response(interaction_token, content, png)


@router.post("/interactions")
async def interactions(request: Request, db: Session = Depends(get_db)):
    """Receive one Discord interaction.

    Answers ``PONG`` to Discord's liveness PING, runs a registered roll
    command, and rejects anything unsigned. Unknown interaction types are
    acknowledged with an ephemeral note rather than an error status, so a
    future Discord feature we have not implemented does not surface as a
    red failure in the client.
    """
    if not discord_api.configured():
        return JSONResponse(
            {"error": "Discord integration is not configured"},
            status_code=503,
        )

    body = await request.body()
    if not discord_api.verify_signature(
        request.headers.get("X-Signature-Ed25519") or "",
        request.headers.get("X-Signature-Timestamp") or "",
        body,
    ):
        return JSONResponse(
            {"error": "invalid request signature"}, status_code=401,
        )

    try:
        interaction = json.loads(body)
    except ValueError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    if not isinstance(interaction, dict):
        return JSONResponse({"error": "Invalid interaction"}, status_code=400)

    kind = interaction.get("type")
    if kind == TYPE_PING:
        return JSONResponse({"type": RESPONSE_PONG})
    if kind != TYPE_APPLICATION_COMMAND:
        return _ephemeral("That interaction type is not supported yet.")

    discord_id = invoker_discord_id(interaction)
    if not discord_id:
        return _ephemeral("I could not tell who invoked that command.")

    name = (interaction.get("data") or {}).get("name") or ""
    try:
        content, payload = run_roll_command(db, name, discord_id)
    except CommandError as exc:
        return _ephemeral(str(exc))

    token = interaction.get("token") or ""
    return JSONResponse(
        {"type": RESPONSE_DEFERRED_MESSAGE},
        background=BackgroundTask(deliver_card, token, content, payload),
    )
