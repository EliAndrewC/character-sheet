"""The schema of ``Character.adventure_state`` (server-rolls-design 4.2).

``adventure_state`` used to be stored verbatim: ``/track`` accepted any
blob, so a wrong value from a tab was as good as a right one. Every write now
goes through ``sanitize_adventure_state``, which keeps the keys the sheet
actually uses, coerces them to their type and bounds, and drops the rest
(logging what it dropped, so a key a future feature forgets to register
shows up in the logs rather than vanishing silently).

The keys, by kind:
- per-adventure / per-day counters: ``<id>_used`` for every counter the
  character has (``per_adventure_abilities``), 0..that counter's max;
- per-adventure toggles: ``<id>`` for every toggle the character has, bool;
- banked bonuses: lists of amounts, or single amounts;
- Mantis Wave-Treader's per-round posture tracker; Kakita 5th Dan's latch.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.per_adventure import per_adventure_abilities

log = logging.getLogger(__name__)

MAX_AMOUNT = 999
MAX_LIST = 50

BANK_LISTS = ("akodo_banked_bonuses", "matsu_banked_wc_bonuses", "banked_wc_excess")
BANK_AMOUNTS = (
    "hiruma_banked_attack_bonus", "bayushi_banked_feint_raise", "ide_banked_tn_reduce",
    "hida_banked_wc_bonus", "matsu_banked_wc_bonus",  # the last: legacy single Matsu bank
    "mantis_offensive_3rd_dan_accum", "mantis_defensive_3rd_dan_accum",
)
POSTURES = ("offensive", "defensive")


def _amount(value: Any, high: int = MAX_AMOUNT) -> int:
    try:
        return max(0, min(high, int(value)))
    except (TypeError, ValueError):
        return 0


def sanitize_adventure_state(character: Any, state: Any) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    abilities = per_adventure_abilities(character)
    counters = {a["id"] + "_used": a["max"] for a in abilities if a["type"] == "counter"}
    toggles = {a["id"] for a in abilities if a["type"] == "toggle"}
    out: Dict[str, Any] = {}
    dropped = []
    for key, value in state.items():
        if key in counters:
            out[key] = _amount(value, counters[key])
        elif key in toggles or key == "kakita_5th_dan_used":
            out[key] = bool(value)
        elif key in BANK_LISTS:
            items = value if isinstance(value, list) else [value]
            out[key] = [_amount(v) for v in items if isinstance(v, (int, float))][:MAX_LIST]
        elif key in BANK_AMOUNTS:
            out[key] = _amount(value)
        elif key == "mantis_posture_phase":
            out[key] = _amount(value, 11) or 1
        elif key == "mantis_posture_history":
            items = value if isinstance(value, list) else []
            out[key] = [v for v in items if v in POSTURES][:11]
        else:
            dropped.append(key)
    if dropped:
        log.warning("adventure_state: dropped unknown keys %s for character %s",
                    sorted(dropped), getattr(character, "id", None))
    return out
