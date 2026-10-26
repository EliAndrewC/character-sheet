"""Builder rows from Obsidian Portal characters (combat-design D46-D47).

gm-assistant reads Obsidian Portal and serves a character's raw facts
(``GET {GM_ASSISTANT_URL}/api/op-character?ref=``, gm-assistant#4, the same
bearer token as ``/api/names``); this module turns them into a generate row:
the NPC type from the school line and tags, the earned XP, the traits and
the recorded stats. The GM sees the result on the combat page before
generating, because OP's free text cannot always be read: an unmapped school
leaves the type for the GM to pick, and every line that matched nothing is
shown, never dropped silently (a few records' first GM-info paragraph is
roll notes rather than traits).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.services import npc_generator as gen

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0  # gm-assistant may cold-boot, then fetch from Obsidian Portal

BROTHERHOOD = "brotherhood_of_shinsei_monk"
MANTIS = "mantis_wave_treader"
IMPERIAL_WORDS = ("seppun", "hantei", "imperial")
IMPERIAL_TAGS = ("seppun family", "hantei family")


class OpLookupError(Exception):
    """A lookup that produced no character. ``candidates`` lists the names an
    ambiguous ref matched, for the GM to pick from."""

    def __init__(self, message: str, candidates: Optional[List[str]] = None):
        super().__init__(message)
        self.candidates = candidates or []


async def fetch_op_character(ref: str) -> Dict[str, Any]:
    """gm-assistant's raw facts for ``ref`` (an OP URL, slug or name)."""
    base = os.environ.get("GM_ASSISTANT_URL", "").rstrip("/")
    token = os.environ.get("GM_ASSISTANT_NAMES_TOKEN", "")
    if not base or not token:
        raise OpLookupError(
            "Obsidian Portal lookups are off: GM_ASSISTANT_URL and "
            "GM_ASSISTANT_NAMES_TOKEN must both be set."
        )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
            resp = await http.get(
                f"{base}/api/op-character", params={"ref": ref},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        log.warning("gm-assistant op-character unavailable: %s", exc)
        raise OpLookupError("gm-assistant did not answer; try again in a moment.")
    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        body = {}
    if resp.status_code == 200 and isinstance(body.get("name"), str):
        return body
    if resp.status_code in (400, 404, 409) and isinstance(body.get("error"), str):
        candidates = body.get("candidates")
        candidates = [c for c in candidates if isinstance(c, str)] if isinstance(candidates, list) else []
        raise OpLookupError(body["error"], candidates)
    log.warning("gm-assistant op-character answered %s", resp.status_code)
    raise OpLookupError(f"gm-assistant answered {resp.status_code}; nothing was filled in.")


def npc_type_for(school_line: Optional[str], tags: List[str]) -> Tuple[Optional[str], str]:
    """``(npc type or None, why)`` from OP's ``<gender> <school>`` line and
    tags, by the GM's conventions (D46). None leaves the type to the GM."""
    school = (school_line or "").strip()
    low = school.lower()
    tag_set = {t.strip().lower() for t in tags if isinstance(t, str)}
    if any(w in low for w in IMPERIAL_WORDS) or tag_set & set(IMPERIAL_TAGS):
        return None, "Imperial families have no school to build from - pick a type, or leave this one out."
    if "peasant" in low:
        return gen.WAVE_MAN, f'"{school}": a peasant is a Wave Man.'
    if "mantis" in low and "bushi" in low:
        return MANTIS, f'"{school}": the Mantis Bushi line predates the Wave-Treader school.'
    labels = [(t, label) for t, label in gen.npc_type_options() if label.lower() in low]
    if len(labels) == 1:
        return labels[0][0], f'"{school}".'
    if school and labels:
        return None, f'"{school}" names more than one school - pick the type.'
    if "peasant" in tag_set:
        return gen.WAVE_MAN, "No school listed; tagged peasant, so a Wave Man."
    if "monk" in tag_set or any(t.startswith("order of ") for t in tag_set):
        return BROTHERHOOD, "No school listed; a monk or a member of an Order, so a Brotherhood monk."
    if school:
        return None, f'Could not tell the school from "{school}" - pick the type.'
    return None, "No school is listed on Obsidian Portal - pick the type."


def _trait_names(traits: Dict[str, Any]) -> List[str]:
    names = []
    for field, (catalog, _what) in gen._TRAIT_CATALOGS.items():
        names += [catalog[i].name for i in traits.get(field) or []]
    return names


def builder_row(facts: Dict[str, Any]) -> Dict[str, Any]:
    """What the combat page's builder row gets from the raw facts: the row's
    fields, plus what the GM should read before generating."""
    tags = facts.get("tags") if isinstance(facts.get("tags"), list) else []
    npc_type, why = npc_type_for(facts.get("school_line"), tags)
    trait_lines = [x for x in facts.get("trait_lines") or [] if isinstance(x, str)]
    stat_lines = [x for x in facts.get("stat_lines") or [] if isinstance(x, str)]
    traits, flavor = gen.match_trait_lines(trait_lines)
    recorded, unknown = gen.match_stat_lines(stat_lines)
    earned = facts.get("earned_xp")
    if isinstance(earned, bool) or not isinstance(earned, int):
        earned = None
    return {
        "name": facts["name"].strip()[:80],
        "npc_type": npc_type,
        "type_note": why,
        "earned_xp": earned,
        "traits": traits,
        "trait_names": _trait_names(traits),
        "recorded": recorded,
        "ignored": flavor + unknown,
    }
