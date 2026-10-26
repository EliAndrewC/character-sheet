"""Write a built NPC's stats back to Obsidian Portal, through gm-assistant.

After the GM generates, rebuilds, renames or brings back an NPC with XP, the
combat routes send its final stats to ``POST {GM_ASSISTANT_URL}/api/npc-numbers``
(gm-assistant feature 226, issue #4). gm-assistant finds the Obsidian Portal
character by name and merges the stats into the "NPC numbers:" block of its
GM-only notes: the sheet wins on every stat it sends, lines it does not send
stay, and a name with no record (most generated NPCs) writes nothing.

The call is made AFTER the route has committed, so a slow or failing
gm-assistant can never block or undo the NPC; anything going wrong becomes a
``failed`` outcome with a line for the GM. Not configured is ``off``, shown
as quietly as ``no_record``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Iterable, List

import httpx

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 12.0  # gm-assistant sleeps when idle; a cold boot takes a few seconds

STATUSES = ("written", "unchanged", "no_record", "ambiguous", "failed")
_RINGS = ("Air", "Earth", "Fire", "Water", "Void")


def npc_stats(npc: Any) -> Dict[str, int]:
    """All five rings, attack, parry, and every skill and knack at 1 or more,
    keyed by this app's ids. Profession abilities are not stats."""
    stats: Dict[str, int] = {ring: getattr(npc, f"ring_{ring.lower()}") for ring in _RINGS}
    stats["attack"] = npc.attack
    stats["parry"] = npc.parry
    for field in (npc.skills, npc.knacks, npc.foreign_knacks):
        stats.update({k: v for k, v in (field or {}).items() if v >= 1})
    return stats


def _outcome(name: str, status: str, message: str) -> Dict[str, str]:
    return {"name": name, "status": status, "message": message}


async def backport(npc: Any) -> Dict[str, str]:
    """``{name, status, message}`` for one NPC. Never raises."""
    name = npc.name
    base = os.environ.get("GM_ASSISTANT_URL", "").rstrip("/")
    token = os.environ.get("GM_ASSISTANT_NAMES_TOKEN", "")
    if not base or not token:
        return _outcome(name, "off", f"{name}: Obsidian Portal not updated (gm-assistant is not configured)")
    body = {"name": name, "stats": npc_stats(npc), "sheet_id": npc.id}
    failed = f"{name}: Obsidian Portal not updated"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            resp = await http.post(f"{base}/api/npc-numbers", json=body,
                                   headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        log.warning("gm-assistant npc-numbers unavailable for %s: %s", name, exc)
        return _outcome(name, "failed", f"{failed} (gm-assistant did not answer)")
    try:
        data = resp.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        data = {}
    if resp.status_code != 200:
        log.warning("gm-assistant npc-numbers answered %s for %s: %s", resp.status_code, name, data)
        error = data.get("error")
        detail = str(error)[:200] if error else f"gm-assistant answered {resp.status_code}"
        return _outcome(name, "failed", f"{failed} ({detail})")
    status, message = data.get("status"), data.get("message")
    if status not in STATUSES or not isinstance(message, str) or not message.strip():
        log.warning("gm-assistant npc-numbers gave a malformed answer for %s: %s", name, data)
        return _outcome(name, "failed", f"{failed} (gm-assistant gave a malformed answer)")
    log.info("npc-numbers backport %s: %s", status, message)
    return _outcome(name, status, message.strip()[:500])


async def backport_all(npcs: Iterable[Any]) -> List[Dict[str, str]]:
    """One outcome per NPC, in order, the calls made concurrently."""
    return list(await asyncio.gather(*(backport(n) for n in npcs)))
