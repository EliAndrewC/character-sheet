"""Thin Discord HTTP + signature layer for the "L7R Character Sheet" bot.

Deliberately small, and deliberately not a Discord SDK: the same reasoning
as ``app/services/sheets.py`` (direct ``httpx`` calls rather than
``google-api-python-client``) applies here - a 512MB Fly machine should not
pay a library's import cost for four endpoints.

There is no gateway and no always-on process. Discord delivers slash
commands as signed HTTPS POSTs to the interactions endpoint registered on
the application, so the bot is just another route on this web app.

The credentials come from the environment:

- ``DISCORD_BOT_TOKEN`` - the BOT token, a different credential from the
  ``DISCORD_CLIENT_ID`` / ``DISCORD_CLIENT_SECRET`` pair used for website
  login. Needed only for outbound calls (registering commands); answering
  an interaction uses the interaction's own token.
- ``DISCORD_APPLICATION_ID`` - the application's snowflake, part of the
  follow-up webhook URL.
- ``DISCORD_PUBLIC_KEY`` - the application's Ed25519 ``verify_key``. NOT a
  secret (it only verifies), but it lives in the environment so a key
  rotation does not need a deploy.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx


log = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v10"

#: Discord asks that bots identify themselves; it is also what shows up in
#: their rate-limit tooling when something goes wrong.
USER_AGENT = (
    "DiscordBot (https://github.com/EliAndrewC/character-sheet, 1.0) "
    "l7r-character-sheet"
)

#: Outbound calls answer a user who is staring at a "thinking..." spinner,
#: so fail fast rather than hanging the background task.
TIMEOUT_SEC = 15

#: Backoff before re-attempting a follow-up edit, in seconds.
#:
#: Editing a deferred response races Discord: we start the follow-up as soon
#: as uvicorn has written the acknowledgement to the socket, but those bytes
#: still have to cross Fly's proxy and be processed on Discord's side before
#: the message we want to edit exists. Losing that race returns 404
#: "Unknown Webhook" (10015) even though the interaction token is perfectly
#: valid - which strands the invoker on "thinking..." forever, since the
#: placeholder message is only ever replaced by this call. Retrying costs a
#: few seconds against a 15-minute window.
FOLLOWUP_RETRY_DELAYS = (0.25, 0.5, 1.0, 2.0, 4.0)

#: Statuses worth another attempt: the 404 above, Discord rate limiting, and
#: transient server errors. A 400/401/403 is our bug and will not improve.
RETRYABLE_STATUSES = frozenset({404, 429, 500, 502, 503, 504})


def bot_token() -> str:
    return (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()


def application_id() -> str:
    return (os.environ.get("DISCORD_APPLICATION_ID") or "").strip()


def public_key() -> str:
    return (os.environ.get("DISCORD_PUBLIC_KEY") or "").strip()


def configured() -> bool:
    """Whether the interactions endpoint can do its job at all.

    The bot token is NOT required to answer an interaction (the follow-up
    uses the interaction token), so it is not checked here - only the two
    values the request path itself needs.
    """
    return bool(public_key() and application_id())


# ---------------------------------------------------------------------------
# Inbound: signature verification
# ---------------------------------------------------------------------------


def verify_signature(signature: str, timestamp: str, body: bytes) -> bool:
    """Verify Discord's Ed25519 signature over ``timestamp + body``.

    Every interaction POST carries ``X-Signature-Ed25519`` and
    ``X-Signature-Timestamp``. Discord rejects an application whose
    endpoint does not reject bad signatures, so this is both a security
    control and a registration requirement. Returns False - never raises -
    for a missing header, malformed hex, or a bad signature, so the route
    can answer 401 uniformly.
    """
    key = public_key()
    if not key or not signature or not timestamp:
        return False
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey

        VerifyKey(bytes.fromhex(key)).verify(
            timestamp.encode("utf-8") + body, bytes.fromhex(signature),
        )
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------


def _bot_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bot {bot_token()}",
        "User-Agent": USER_AGENT,
    }


def edit_original_response(
    interaction_token: str,
    content: str,
    png: Optional[bytes] = None,
    filename: str = "l7r-roll.png",
) -> bool:
    """Fill in a deferred interaction response.

    After a deferred acknowledgement the real answer is written by editing
    the original response, which stays available for 15 minutes. The
    webhook URL is authenticated by the interaction token itself, so this
    call needs no bot token.

    A PNG is attached via multipart, the same way the sheet's "Copy roll
    image" card reaches Discord today.

    Retries on the statuses in ``RETRYABLE_STATUSES`` (see
    ``FOLLOWUP_RETRY_DELAYS`` for why a fresh deferral reliably 404s once)
    and on transport errors. Returns True on success; a final failure is
    logged and swallowed, because the roll has already been recorded and
    there is nothing useful to raise at.
    """
    url = (
        f"{API_BASE}/webhooks/{application_id()}/{interaction_token}"
        f"/messages/@original"
    )
    body: Dict[str, Any] = {"content": content}
    if png:
        # An attachment has to go as multipart, with the JSON body in a
        # ``payload_json`` part and each file keyed by the id it is
        # referenced under in ``attachments``.
        body["attachments"] = [{"id": 0, "filename": filename}]

    last = ""
    for attempt, delay in enumerate((0.0,) + FOLLOWUP_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        succeeded, retryable, last = _attempt_edit(url, body, png, filename)
        if succeeded:
            if attempt:
                log.info(
                    "discord: follow-up edit succeeded on attempt %s", attempt + 1,
                )
            return True
        if not retryable:
            break
    log.warning("discord: editing the original response failed: %s", last)
    return False


def _attempt_edit(
    url: str, body: Dict[str, Any], png: Optional[bytes], filename: str,
) -> "tuple[bool, bool, str]":
    """One PATCH. Returns ``(succeeded, worth_retrying, description)``."""
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as http:
            if png:
                response = http.patch(
                    url,
                    data={"payload_json": json.dumps(body)},
                    files={"files[0]": (filename, png, "image/png")},
                    headers={"User-Agent": USER_AGENT},
                )
            else:
                response = http.patch(
                    url, json=body, headers={"User-Agent": USER_AGENT},
                )
    except httpx.HTTPError as exc:
        return False, True, f"transport error: {exc}"
    if response.status_code < 400:
        return True, False, ""
    return (
        False,
        response.status_code in RETRYABLE_STATUSES,
        f"HTTP {response.status_code}: {response.text[:300]}",
    )


def put_guild_commands(guild_id: str, commands: List[dict]) -> List[dict]:
    """Replace the application's command set in one guild (bulk overwrite).

    Guild-scoped commands appear instantly, where global ones take up to an
    hour to propagate - so this is what development and testing use. Raises
    on failure; the only caller is a script a human is watching.
    """
    url = f"{API_BASE}/applications/{application_id()}/guilds/{guild_id}/commands"
    with httpx.Client(timeout=TIMEOUT_SEC) as http:
        response = http.put(url, json=commands, headers=_bot_headers())
    response.raise_for_status()
    return response.json()


def set_interactions_endpoint_url(url: str) -> dict:
    """Point the application's interactions endpoint at ``url``.

    Discord validates the URL before saving it by sending a PING that the
    endpoint must answer with a correctly-signed PONG, so this fails - with
    Discord's own error text - if the app is not deployed and reachable.
    """
    with httpx.Client(timeout=TIMEOUT_SEC) as http:
        response = http.patch(
            f"{API_BASE}/applications/@me",
            json={"interactions_endpoint_url": url},
            headers=_bot_headers(),
        )
    response.raise_for_status()
    return response.json()
