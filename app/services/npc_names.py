"""Name suggestions for generated NPCs, from gm-assistant (D10, D16, D26).

The used-name data (Obsidian Portal, the campaign's lineages, the GM's manual
list) is only reachable from gm-assistant, so name picking stays there; this
app asks ``GET {GM_ASSISTANT_URL}/api/names`` with a bearer token and gets
male given names back, from the peasant pool for Wave Men and the
samurai-eligible pool otherwise. gm-assistant learns this app's NPC names
from ``/api/characters`` (flagged ``is_npc``), so they count as used.

Anything going wrong - not configured, asleep past the timeout, an error, a
malformed answer - yields fewer names or none, and the caller falls back to
"Wave Man 1..N". A fight never waits on, or fails for, a name.
"""

from __future__ import annotations

import logging
import os
from typing import List, Sequence

import httpx

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 12.0  # gm-assistant sleeps when idle; a cold boot takes a few seconds


async def fetch_names(count: int, peasant: bool, avoid: Sequence[str] = ()) -> List[str]:
    base = os.environ.get("GM_ASSISTANT_URL", "").rstrip("/")
    token = os.environ.get("GM_ASSISTANT_NAMES_TOKEN", "")
    if count <= 0 or not base or not token:
        return []
    params = {"count": str(count), "peasant": "true" if peasant else "false"}
    if avoid:
        params["avoid"] = ",".join(avoid)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            resp = await http.get(
                f"{base}/api/names", params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        log.warning("gm-assistant names unavailable: %s", exc)
        return []
    if resp.status_code != 200:
        log.warning("gm-assistant names answered %s", resp.status_code)
        return []
    try:
        names = resp.json().get("names")
    except (ValueError, AttributeError):
        return []
    if not isinstance(names, list):
        return []
    return [n.strip()[:80] for n in names if isinstance(n, str) and n.strip()][:count]
