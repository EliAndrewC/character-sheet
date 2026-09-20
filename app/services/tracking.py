"""Live tracking state: the revision check, and starting a combat round.

**Optimistic concurrency.** A sheet tab holds a whole copy of the character's
tracking state and posts all of it back on every change. Two tabs - or a tab
and a Discord roll command - therefore used to overwrite each other silently:
whoever saved last won, and a void point spent from Discord came back the
next time the player clicked anything on a sheet they had open.

``Character.tracking_rev`` closes that. It moves whenever any tracking column
changes (``models._bump_tracking_rev``, hooked at the ORM layer so every
writer participates without having to remember to). A whole-state write must
name the revision it was based on; ``is_stale`` says whether it may proceed,
and a refused writer is handed ``tracking_snapshot`` so it can adopt the
current values instead of making the player reload.

Field-level updates would also have solved this and were considered. They
were declined because the sheet's Alpine layer mutates its local copy and
then calls one ``save()`` from 45 call sites (measured 2026-09-20, plus the
setCount / setToggle helpers that fan out further); converting each to a
server operation is the larger end state, not a precondition for being
correct. The revision check makes the existing shape safe today, and leaves
any single operation free to move server-side later (as void spends and
initiative now have).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models import Character
from app.services.void_spend import school_dan


#: adventure_state keys that belong to ONE combat round. Rolling initiative
#: starts the next round, so these are cleared; everything else in
#: adventure_state is per-adventure or per-day and survives.
PER_ROUND_STATE_KEYS = (
    "mantis_posture_phase",
    "mantis_posture_history",
    "mantis_offensive_3rd_dan_accum",
    "mantis_defensive_3rd_dan_accum",
    "kakita_5th_dan_used",
)


def tracking_snapshot(character: Character) -> Dict[str, Any]:
    """The tracking state a sheet tab holds, plus the revision it is at."""
    return {
        "rev": character.tracking_rev or 0,
        "current_light_wounds": character.current_light_wounds or 0,
        "current_serious_wounds": character.current_serious_wounds or 0,
        "current_void_points": character.current_void_points or 0,
        "current_temp_void_points": character.current_temp_void_points or 0,
        "adventure_state": character.adventure_state or {},
        "action_dice": character.action_dice or [],
        "precepts_pool": character.precepts_pool or [],
    }


def is_stale(character: Character, claimed_rev: Any) -> bool:
    """Whether a writer claiming ``claimed_rev`` has NOT seen the current
    state. A missing or non-integer revision is stale by definition: a writer
    that cannot say what it saw has not shown that it saw anything."""
    if isinstance(claimed_rev, bool) or not isinstance(claimed_rev, int):
        return True
    return claimed_rev != (character.tracking_rev or 0)


def conviction_refreshes_each_round(character_data: Dict[str, Any]) -> bool:
    """Priest 5th Dan: the conviction pool refreshes every combat round.

    The sheet reads this as its ``priest_round_conviction_refresh`` flag, so
    the browser's round start and the server's agree on who qualifies.
    """
    return (
        character_data.get("school") == "priest"
        and school_dan(character_data) >= 5
    )


def start_combat_round(
    character: Character, action_dice: List[Dict[str, Any]],
) -> List[str]:
    """Begin a combat round with freshly rolled ``action_dice``.

    The server-side definition of what the sheet's ``setActionDice`` does:
    the new dice replace the old, all unspent; per-round state is cleared
    (``PER_ROUND_STATE_KEYS``); state that deliberately outlives a round -
    the Priest's ``precepts_pool``, banked bonuses, per-adventure counters -
    is left alone. A Priest at 5th Dan also gets their conviction back.
    Returns the player-facing notes about what refreshed. Does not commit.

    (Mirumoto 3rd Dan's round points also refresh each round on the sheet,
    but they are tab-local and never persisted, so there is nothing here to
    reset - a tab that loads after this runs already starts them at full.)
    """
    notes: List[str] = []
    dice: List[Dict[str, Any]] = []
    for die in action_dice or []:
        entry: Dict[str, Any] = {"value": int(die["value"]), "spent": False}
        if die.get("athletics_only"):
            entry["athletics_only"] = True
        if die.get("mantis_4th_dan"):
            entry["mantis_4th_dan"] = True
        dice.append(entry)
    character.action_dice = dice
    state = dict(character.adventure_state or {})
    for key in PER_ROUND_STATE_KEYS:
        state.pop(key, None)
    if conviction_refreshes_each_round(character.to_dict()) and state.get(
        "conviction_used"
    ):
        state["conviction_used"] = 0
        notes.append("Conviction pool refreshed for the new combat round")
    character.adventure_state = state
    return notes


def claimed_rev_from(body: Optional[Dict[str, Any]]) -> Any:
    """The revision a request body says it was based on."""
    return (body or {}).get("rev")
