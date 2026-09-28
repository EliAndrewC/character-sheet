"""Rolls the SERVER makes for the character sheet (server-rolls-design).

The sheet asks for a roll by key plus its pre-roll choices; this module
checks everything that can refuse, rolls, applies the spends, records, and
answers with what the browser needs to animate and display the result. It
follows the Discord / combat-tracker order - check, roll, apply, record,
one commit (by the caller) - and reuses their pieces: formulas from
``build_all_roll_formulas``, dice from ``roll_engine.execute_roll``, void
from ``void_spend``, recording from ``rolls_history``.

``simulate`` is Read-only Roll Mode (decision S1): a non-editor or anonymous
visitor gets the same roll, computed the same way, and nothing about the
character changes - no spend applied, no history row. The spend is still
CHECKED against the character's real pools, because those are the pools the
sheet showed them.

Phase 1 covers the generic roll (skills, knacks, rings, athletics). Keys
whose roll carries state-changing hooks - initiative, parry, feint - stay on
the browser path until their phase (``SERVER_ROLLED`` gates it).
"""

from __future__ import annotations

import random
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional

from sqlalchemy.orm import Session

from app.models import Character, RollHistory, RollSession
from app.services import special_rolls
from app.services.dice import build_all_roll_formulas, is_impaired
from app.services.party import party_member_data, visible_party_members
from app.services.per_adventure import per_adventure_abilities
from app.services.roll_engine import apply_dice_cap, execute_roll, impaired_now
from app.services.rolls_history import skill_rank_for_roll
from app.services.tracking import tracking_snapshot
from app.services.void_spend import VoidSpendRefused, apply_void_spend, plan_void_spend

SESSION_TTL = timedelta(hours=6)

# Anonymous visitors may test-drive a sheet (S1), rate-limited per address.
ANON_LIMIT = 60          # rolls
ANON_WINDOW = 60.0       # seconds
_anon_hits: Dict[str, Deque[float]] = defaultdict(deque)


_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


class ScriptedRng:
    """Test seam: every die comes up as the next of ``values``, cycling.

    Only reachable when the app runs with ``TEST_AUTH_BYPASS=true`` (the
    clicktest server), through the ``X-Test-Dice`` header - the server-side
    twin of the clicktests' old ``Math.random`` stubs, now that the server
    rolls the dice.
    """

    def __init__(self, values):
        self.values = list(values)
        self.i = 0

    def randint(self, a: int, b: int) -> int:
        v = self.values[self.i % len(self.values)]
        self.i += 1
        return max(a, min(b, v))


def scripted_rng_from_header(header: str) -> Optional["ScriptedRng"]:
    try:
        values = [int(v) for v in header.split(",") if v.strip()]
    except ValueError:
        return None
    return ScriptedRng(values) if values else None


class RollRefused(ValueError):
    """A roll the character cannot make as asked. Nothing changed."""


SPECIAL_KEYS = ("bless", "spend_vp_xk1", "freeform")


def server_rolled(roll_key: str) -> bool:
    """Whether the sheet's roll for this key is made here yet (Phase 1)."""
    if roll_key in SPECIAL_KEYS:
        return True
    if not roll_key or roll_key.startswith("initiative"):
        return False
    if roll_key in ("parry", "athletics:parry", "athletics:attack"):
        return False
    if roll_key == "knack:feint" or roll_key.startswith("knack:feint:"):
        return False
    kind = roll_key.split(":", 1)[0]
    return kind in ("skill", "knack", "ring", "athletics")


def anonymous_allowed(address: str, now: Optional[float] = None) -> bool:
    """A sliding-window limit on anonymous test-drive rolls per address."""
    now = time.monotonic() if now is None else now
    hits = _anon_hits[address]
    while hits and now - hits[0] > ANON_WINDOW:
        hits.popleft()
    if len(hits) >= ANON_LIMIT:
        return False
    hits.append(now)
    return True


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reap(db: Session) -> None:
    db.query(RollSession).filter(RollSession.created_at < _now() - SESSION_TTL).delete()


def _otherworldliness_left(character: Character) -> int:
    entry = next((a for a in per_adventure_abilities(character) if a["id"] == "otherworldliness"), None)
    if entry is None:
        return 0
    used = int((character.adventure_state or {}).get("otherworldliness_used", 0) or 0)
    return max(0, entry["max"] - used)


def _count(choices: Dict[str, Any], key: str) -> int:
    try:
        value = int(choices.get(key) or 0)
    except (TypeError, ValueError):
        raise RollRefused(f"{key} must be a whole number") from None
    if value < 0:
        raise RollRefused(f"{key} cannot be negative")
    return value


def start_roll(
    db: Session,
    character: Character,
    roll_key: str,
    choices: Dict[str, Any],
    *,
    viewer: Optional[str],
    live: bool,
    record: bool,
    is_owner_roll: bool,
    rng: Optional[random.Random] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Make one roll. ``choices``: ``void`` (points put into the roll),
    ``otherworldliness`` (points spent to add rolled dice), ``kitsune_swap``
    (roll with the school ring). Refusals raise ``RollRefused`` before any
    die is rolled or anything changes.

    ``request_id`` (32 hex characters, chosen by the browser) makes the
    request safe to retry (decision S6): it becomes the session id, and a
    request whose id already has a session gets that session's answer back
    instead of a second roll - so a roll whose reply was lost is never paid
    for twice.
    """
    if request_id is not None:
        if not _REQUEST_ID.match(request_id):
            raise RollRefused("request_id must be 32 hex characters")
        existing = db.get(RollSession, request_id)
        if existing is not None:
            if existing.character_id != character.id or existing.viewer_discord_id != viewer:
                raise RollRefused("request_id already used")
            return _answer(existing, character)
    if not server_rolled(roll_key):
        raise RollRefused(f"{roll_key} is not rolled on the server yet")
    void = _count(choices, "void")
    ow = _count(choices, "otherworldliness")
    char_data = character.to_dict()
    party = party_member_data(visible_party_members(db, character, viewer))
    record_key = roll_key
    activation = 0
    if roll_key in SPECIAL_KEYS:
        if void or ow or choices.get("kitsune_swap"):
            raise RollRefused(f"no void, otherworldliness or ring swap on a {roll_key} roll")
        formula, record_key, activation = _special(character, char_data, roll_key, choices)
    else:
        formula = build_all_roll_formulas(char_data, party_members=party).get(roll_key)
        if not formula:
            raise RollRefused(f"{character.name} has no {roll_key} roll")
        formula = dict(formula)
    label = formula.get("label") or roll_key

    # Kitsune Warden Special Ability: roll with the school ring instead.
    swap = formula.get("kitsune_swap")
    if choices.get("kitsune_swap"):
        if not swap:
            raise RollRefused(f"{label} cannot use the Kitsune ring swap")
        formula.update(
            rolled=swap["rolled"], kept=swap["kept"], label=swap["label"],
            kitsune_swap_from_ring=swap.get("kitsune_swap_from_ring"),
            kitsune_swap_to_ring=swap.get("kitsune_swap_to_ring"),
        )
        label = formula["label"]

    # Otherworldliness: +1 rolled die per point, up to the roll's capacity
    # and the pool; spending any on an unskilled roll grants the skill for
    # this roll, so its 10s reroll - unless the character is Impaired.
    if ow:
        capacity = formula.get("otherworldliness_capacity") or 0
        if ow > capacity:
            raise RollRefused(f"{label} can take at most {capacity} otherworldliness")
        if ow > _otherworldliness_left(character):
            raise RollRefused(f"{character.name} does not have {ow} otherworldliness left")
        formula["rolled"] = (formula.get("rolled") or 0) + ow
        formula["ow_spent"] = ow
        if formula.get("no_reroll_reason") == "unskilled":
            if is_impaired(char_data):
                formula["no_reroll_reason"] = "impaired"
            else:
                formula["reroll_tens"] = True
                formula["no_reroll_reason"] = ""

    # Void: the activation point first, then the +1k1 points (void_spend
    # checks the per-roll cap and the pools). Checked in simulate mode too:
    # those are the pools the sheet showed.
    if void and formula.get("void_blocked"):
        raise RollRefused(f"{character.name} cannot spend void points on {label}")
    activation = activation or (1 if formula.get("requires_void_point") else 0)
    try:
        plan = plan_void_spend(character, void, activation_cost=activation, roll_label=label)
    except VoidSpendRefused as exc:
        raise RollRefused(str(exc)) from None
    if activation:
        formula["void_activation_cost"] = activation
    if ow and not void:
        # execute_roll caps only when void is spent; otherworldliness dice
        # are capped the same way (the sheet's order: OW, then void, then cap).
        capped = apply_dice_cap(formula["rolled"], formula.get("kept") or 0, formula.get("flat") or 0)
        formula.update(rolled=capped["rolled"], kept=capped["kept"], flat=capped["flat"])
        formula["void_overflow_bonus"] = capped["overflow_flat"]

    out: Dict[str, Any] = {}
    payload = execute_roll(char_data, record_key, party_members=party, rng=rng,
                           void_spent=void, formula=formula, out=out)
    effective = out["formula"]
    if ow and not void:
        effective["void_overflow_bonus"] = formula.get("void_overflow_bonus", 0)
    rank = skill_rank_for_roll(record_key, character)
    if rank is not None:
        payload["skill_rank"] = rank

    history_id = None
    if live:
        apply_void_spend(character, plan)
        if ow:
            state = dict(character.adventure_state or {})
            state["otherworldliness_used"] = int(state.get("otherworldliness_used", 0) or 0) + ow
            character.adventure_state = state
        if record:
            row = RollHistory(
                character_id=character.id, roll_key=record_key, actor_discord_id=viewer,
                is_owner_roll=is_owner_roll, impaired_at_roll=impaired_now(char_data),
                payload=payload,
            )
            db.add(row)
            db.flush()
            history_id = row.id

    reap(db)
    session = RollSession(
        id=request_id or secrets.token_hex(16), character_id=character.id, viewer_discord_id=viewer,
        mode="live" if live else "simulate", roll_key=record_key,
        choices={"void": void, "otherworldliness": ow, "kitsune_swap": bool(choices.get("kitsune_swap")),
                 "ritual": choices.get("ritual"), "rolled": choices.get("rolled"),
                 "kept": choices.get("kept"), "reroll_tens": choices.get("reroll_tens")},
        formula=effective, dice=out["dice"], payload=payload, actions=[], history_id=history_id,
    )
    db.add(session)
    db.flush()
    return _answer(session, character)


def _special(character: Character, char_data: Dict[str, Any], roll_key: str,
             choices: Dict[str, Any]):
    """``(formula, key to record, activation void cost)`` for the rolls that
    are not a formula (special_rolls)."""
    if roll_key == "bless":
        ritual = str(choices.get("ritual") or "")
        if not special_rolls.can_bless(character, ritual):
            raise RollRefused(f"{character.name} cannot perform that ritual")
        title = special_rolls.BLESS_RITUALS[ritual][0]
        return ({"label": title, "rolled": 2, "kept": 1, "flat": 0, "reroll_tens": True,
                 "bonuses": [], "adventure_raises_max_per_roll": 0}, "bless", 0)
    if roll_key == "spend_vp_xk1":
        ability = special_rolls.xk1_ability(char_data)
        if ability is None or ability["x"] < 1:
            raise RollRefused(f"{character.name} has no 3rd Dan Xk1 roll")
        # The void point is the roll's price, not dice on it: drawn like an
        # activation cost (temp, then regular, then worldliness) and its
        # school consequences fire.
        return ({"label": ability["title"], "rolled": ability["x"], "kept": 1, "flat": 0,
                 "reroll_tens": True, "bonuses": []},
                f"spend_vp_xk1:{character.school or ''}", 1)
    try:
        formula = special_rolls.freeform_formula(
            choices.get("rolled"), choices.get("kept"), choices.get("reroll_tens", True))
    except ValueError as exc:
        raise RollRefused(str(exc)) from None
    return formula, "freeform", 0


def _answer(session: RollSession, character: Character) -> Dict[str, Any]:
    return {
        "session_id": session.id,
        "mode": session.mode,
        "formula": session.formula,
        "dice": session.dice,
        "total": (session.payload or {}).get("total"),
        "payload": session.payload,
        "history_id": session.history_id,
        "tracking": tracking_snapshot(character),
    }
