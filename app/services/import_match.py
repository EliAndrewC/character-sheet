"""Fuzzy-match "as-written" strings from the LLM to canonical IDs.

The Phase 4 LLM call returns strings like ``"Crane Duelist"`` or
``"iaijutsu"`` - whatever the source document said. Our game catalog
(``app/game_data.py``) uses IDs like ``"kakita_duelist"`` or
``"iaijutsu"``. This module bridges the two with a three-tier strategy:

  1. **Exact** match on normalised (lowercase, trimmed, punctuation-
     stripped) name.
  2. **Alias** match via a hand-written table of common alternate
     names (clan-based school renames, shorthand skill names, etc.).
  3. **Fuzzy** match via ``difflib.get_close_matches`` when the
     candidate is within edit-distance 2-ish of exactly one entry.

Anything that fails all three returns ``None`` and gets reported to
the user via Import Notes rather than silently invented.

Two design choices worth remembering:

  * **No LLM is consulted here.** The LLM already did its job; we
    resolve names deterministically so Phase 5 is reproducible and
    fully testable without mocking a model.
  * **The alias table is small and intentional.** If a real player
    writes something we can't match, the fix is to add one line to
    ``_SCHOOL_ALIASES`` (or similar), not to sprinkle new fuzzy
    heuristics across the codebase.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import get_close_matches
from typing import Dict, Iterable, List, Optional, Tuple

from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES,
    EXCLUSIVE_PAIRS,
    RING_NAMES,
    SCHOOL_KNACKS,
    SCHOOLS,
    SKILLS,
)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")


def _normalise(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Used to compare strings so that ``"Kakita  Duelist"`` and
    ``"kakita-duelist"`` both match ``"Kakita Duelist"``. NFKD
    decomposition strips accents so ``"Ecole"`` and ``"École"`` compare
    equal - not expected for L7R data but cheap to handle.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower().strip()
    depunct = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", depunct).strip()


# ---------------------------------------------------------------------------
# Confidence signal
# ---------------------------------------------------------------------------

EXACT = "exact"      # Name matched a canonical entry exactly.
ALIASED = "aliased"  # Name matched via the alias table.
FUZZY = "fuzzy"      # Name matched via edit-distance.


# ---------------------------------------------------------------------------
# School aliases
#
# Players commonly use clan-based shorthand ("Crane Duelist" for "Kakita
# Duelist") that predates the current canonical school names. This map is
# deliberately short and flat; grow it when a real player document reveals
# a new miss rather than pre-emptively.
# ---------------------------------------------------------------------------

_SCHOOL_ALIASES: Dict[str, str] = {
    # Crane
    "crane duelist": "kakita_duelist",
    "crane dueling academy": "kakita_duelist",
    "crane artisan": "doji_artisan",
    "crane yojimbo": "daidoji_yojimbo",
    "crane courtier": "doji_artisan",
    # Crab
    "crab bushi": "hida_bushi",
    "crab scout": "hiruma_scout",
    "crab witch hunter": "kuni_witch_hunter",
    # Lion
    "lion bushi": "akodo_bushi",
    "lion matsu bushi": "matsu_bushi",
    "lion bard": "ikoma_bard",
    # Scorpion
    "scorpion bushi": "bayushi_bushi",
    "scorpion actor": "shosuro_actor",
    "scorpion warden": "yogo_warden",
    # Phoenix
    "phoenix bushi": "shiba_bushi",
    "phoenix duelist": "isawa_duelist",
    "phoenix void adept": "isawa_ishi",
    "phoenix shugenja": "shugenja",
    # Dragon
    "dragon bushi": "mirumoto_bushi",
    "dragon tattooed monk": "togashi_ise_zumi",
    "tattooed monk": "togashi_ise_zumi",
    "ise zumi": "togashi_ise_zumi",
    "dragon magistrate": "kitsuki_magistrate",
    # Unicorn
    "unicorn bushi": "shinjo_bushi",
    "battle maiden": "otaku_bushi",
    "unicorn battle maiden": "otaku_bushi",
    "unicorn diplomat": "ide_diplomat",
    # Monks
    "shinsei monk": "brotherhood_of_shinsei_monk",
    "brotherhood monk": "brotherhood_of_shinsei_monk",
    "monk": "brotherhood_of_shinsei_monk",
}


# ---------------------------------------------------------------------------
# Skill / Knack / Advantage aliases
#
# Much smaller because the canonical names are short and unambiguous.
# ---------------------------------------------------------------------------

_SKILL_ALIASES: Dict[str, str] = {
    # 'Lore' is sometimes used colloquially for 'History' in L5R-flavoured docs.
    "lore": "history",
    "knowledge": "history",
}

_KNACK_ALIASES: Dict[str, str] = {
    "double strike": "double_attack",
    "iai": "iaijutsu",
    "counter attack": "counterattack",
    "tattoo": "dragon_tattoo",
}

# Advantages and disadvantages sometimes lose their suffix in casual
# notes. We resolve "Family Reckoning" at call time via the "bucket"
# parameter (positive -> Righteous Sting, negative -> Venomous Sting).
_ADVANTAGE_ALIASES: Dict[str, str] = {}
_DISADVANTAGE_ALIASES: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Generic single-bucket matcher
# ---------------------------------------------------------------------------


def _fuzzy_candidates(
    normalised_query: str,
    normalised_pool: Dict[str, str],
    *,
    cutoff: float = 0.82,
) -> Optional[str]:
    """Return the ID whose normalised name is the best fuzzy match,
    or None if no single candidate is close enough.

    ``normalised_pool`` maps normalised_name -> id.
    """
    if not normalised_query:
        return None
    matches = get_close_matches(
        normalised_query,
        list(normalised_pool.keys()),
        n=1,
        cutoff=cutoff,
    )
    if matches:
        return normalised_pool[matches[0]]
    return None


def _match_in_pool(
    name: str,
    id_to_canonical_name: Dict[str, str],
    alias_map: Dict[str, str],
) -> Tuple[Optional[str], Optional[str]]:
    """Generic matcher. Returns ``(id, confidence)`` or ``(None, None)``.

    ``id_to_canonical_name`` maps each ID to its display name so we can
    build the lookup dict internally.
    """
    query = _normalise(name)
    if not query:
        return None, None

    # 1. Exact (normalised) match against canonical names.
    name_to_id: Dict[str, str] = {
        _normalise(display): ident for ident, display in id_to_canonical_name.items()
    }
    if query in name_to_id:
        return name_to_id[query], EXACT

    # 1b. Exact match against the ID itself (LLM sometimes echoes the id).
    if query in id_to_canonical_name:
        return query, EXACT

    # 2. Alias match.
    if query in alias_map:
        return alias_map[query], ALIASED

    # 3. Fuzzy match against canonical names.
    fuzzy_id = _fuzzy_candidates(query, name_to_id)
    if fuzzy_id is not None:
        return fuzzy_id, FUZZY

    return None, None


# ---------------------------------------------------------------------------
# Public matchers
# ---------------------------------------------------------------------------


def match_school(name_as_written: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(school_id, confidence)`` or ``(None, None)`` if unmatched."""
    return _match_in_pool(
        name_as_written,
        {sid: s.name for sid, s in SCHOOLS.items()},
        _SCHOOL_ALIASES,
    )


def match_skill(name_as_written: str) -> Tuple[Optional[str], Optional[str]]:
    return _match_in_pool(
        name_as_written,
        {sid: s.name for sid, s in SKILLS.items()},
        _SKILL_ALIASES,
    )


def match_knack(name_as_written: str) -> Tuple[Optional[str], Optional[str]]:
    return _match_in_pool(
        name_as_written,
        {kid: k.name for kid, k in SCHOOL_KNACKS.items()},
        _KNACK_ALIASES,
    )


def match_ring_name(name_as_written: str) -> Optional[str]:
    """Return the canonical ring name (``"Fire"``) or ``None``."""
    query = _normalise(name_as_written)
    for ring in RING_NAMES:
        if query == _normalise(ring):
            return ring
    return None


# ---------------------------------------------------------------------------
# Advantage / disadvantage matching with campaign + bucket disambiguation
# ---------------------------------------------------------------------------


# A "bucket" is the user's placement: "advantages" or "disadvantages".
# We use it to resolve the Family Reckoning variant (and any future
# mutually-exclusive pair that shares a base name).
ADV_BUCKET = "advantages"
DIS_BUCKET = "disadvantages"

# Build the base-name index once at import time. When a base name is
# shared across the advantage and disadvantage catalogs (Family
# Reckoning), the bucket parameter is what tells us which side to pick.
_EXCLUSIVE_PAIRS_BY_BASE: Dict[str, Tuple[str, str]] = {}
for _aid, _an, _did, _dn in EXCLUSIVE_PAIRS:
    # Record by the shared base name; e.g. "family reckoning" for the
    # "family_reckoning_*" pair. We strip the ": Righteous Sting" suffix
    # by splitting on the first colon if present.
    base_a = _normalise(_an.split(":")[0])
    base_d = _normalise(_dn.split(":")[0])
    # Only store pairs where both sides share a base name (e.g.
    # "Family Reckoning"); the "Virtue"/"Unconventional" pair for example
    # has different base names so buckets already disambiguate.
    if base_a == base_d:
        _EXCLUSIVE_PAIRS_BY_BASE[base_a] = (_aid, _did)


def _build_adv_disadv_pool(bucket: str) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
    """Return (base_id_to_name, campaign_id_to_name, base_aliases, campaign_aliases)
    for the given bucket."""
    if bucket == ADV_BUCKET:
        return (
            {aid: a.name for aid, a in ADVANTAGES.items()},
            {aid: a.name for aid, a in CAMPAIGN_ADVANTAGES.items()},
            _ADVANTAGE_ALIASES,
            _ADVANTAGE_ALIASES,
        )
    else:
        return (
            {did: d.name for did, d in DISADVANTAGES.items()},
            {did: d.name for did, d in CAMPAIGN_DISADVANTAGES.items()},
            _DISADVANTAGE_ALIASES,
            _DISADVANTAGE_ALIASES,
        )


def match_advantage_or_disadvantage(
    name_as_written: str,
    *,
    bucket: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Match a user-written advantage/disadvantage name.

    Returns ``(id, catalog, confidence)`` where ``catalog`` is one of
    ``"base"``, ``"campaign"`` and ``confidence`` is ``EXACT``/
    ``ALIASED``/``FUZZY``. Returns all-``None`` if unmatched.

    ``bucket`` must be :data:`ADV_BUCKET` or :data:`DIS_BUCKET`; it
    controls which side of mutually-exclusive pairs we prefer for
    ambiguous base names (the "Family Reckoning" disambiguation).
    """
    if bucket not in (ADV_BUCKET, DIS_BUCKET):
        raise ValueError(f"bucket must be one of {ADV_BUCKET!r}/{DIS_BUCKET!r}")

    query = _normalise(name_as_written)

    # 1. If the query normalises to a shared base name (e.g. "family
    # reckoning"), the bucket is authoritative.
    if query in _EXCLUSIVE_PAIRS_BY_BASE:
        adv_id, dis_id = _EXCLUSIVE_PAIRS_BY_BASE[query]
        picked = adv_id if bucket == ADV_BUCKET else dis_id
        catalog = _locate_in_catalogs(picked)
        return picked, catalog, ALIASED

    base_map, campaign_map, base_aliases, _camp_aliases = _build_adv_disadv_pool(bucket)

    # 2. Try base catalog first, then campaign.
    for pool, catalog in ((base_map, "base"), (campaign_map, "campaign")):
        mid, conf = _match_in_pool(name_as_written, pool, base_aliases)
        if mid is not None:
            return mid, catalog, conf

    return None, None, None


def _locate_in_catalogs(ident: str) -> str:
    """Return ``"base"`` or ``"campaign"`` for any advantage/disadvantage id."""
    if ident in ADVANTAGES or ident in DISADVANTAGES:
        return "base"
    return "campaign"


__all__ = [
    "match_school",
    "match_skill",
    "match_knack",
    "match_ring_name",
    "match_advantage_or_disadvantage",
    "ADV_BUCKET",
    "DIS_BUCKET",
    "EXACT",
    "ALIASED",
    "FUZZY",
]
