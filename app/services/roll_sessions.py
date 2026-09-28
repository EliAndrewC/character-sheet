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
from app.services.pcp import PcpRefused, spend_pcp
from app.services.professions import holds_ability
from app.services.roll_engine import (
    _formula_text, _spend_bullets, apply_dice_cap, execute_roll, impaired_now, roll_dice,
    roll_one_die, score_roll,
)
from app.services.rolls_history import skill_rank_for_roll
from app.services.tracking import tracking_snapshot
from app.services.void_spend import (
    VoidSpendRefused, apply_void_spend, plan_void_spend, school_dan, void_limits,
)

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


# ---------------------------------------------------------------------------
# Post-roll actions (Phase 3): number-only choices made after seeing the dice
# ---------------------------------------------------------------------------

# action -> (kind it counts toward, +amount per use); an "undo_" action
# removes one of its kind.
_NUMBER_ACTIONS = {
    "raise": ("raise", 5),
    "togashi_raise": ("togashi_raise", 5),
    "conviction": ("conviction", 1),
}
_POOLS = {"raise": "adventure_raises", "conviction": "conviction",
          "togashi_raise": "togashi_daily_athletics_raises"}


def _knack_rank(character: Character, knack: str) -> int:
    return int((character.knacks or {}).get(knack) or (character.foreign_knacks or {}).get(knack) or 0)


def _per_roll_cap(session: RollSession, character: Character, kind: str) -> int:
    if kind == "raise":
        return int((session.formula or {}).get("adventure_raises_max_per_roll") or 0)
    if kind == "conviction":
        return _knack_rank(character, "conviction")
    # Togashi Ise Zumi 3rd Dan: athletics rolls only, X = precepts per roll.
    if (character.school != "togashi_ise_zumi" or school_dan(character.to_dict()) < 3
            or not session.roll_key.startswith("athletics:")):
        return 0
    return int((character.skills or {}).get("precepts", 0) or 0)


def _pool_left(character: Character, kind: str) -> int:
    entry = next((a for a in per_adventure_abilities(character)
                  if a["id"] == _POOLS[kind] and a["type"] == "counter"), None)
    if entry is None:
        return 0
    used = int((character.adventure_state or {}).get(_POOLS[kind] + "_used", 0) or 0)
    return max(0, entry["max"] - used)


def _counts(session: RollSession) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for a in session.actions or []:
        out[a["kind"]] += a.get("count", 1)
    return out


def _session_total(session: RollSession) -> int:
    base = int((session.choices or {}).get("base_total", (session.payload or {}).get("total", 0)))
    extra = 0
    for a in session.actions or []:
        extra += a.get("amount", 0) * a.get("count", 1)
    return base + extra


_ROW_FIELDS = ("bonuses", "total", "kept", "dropped", "kept_sum", "extras", "alternatives",
               "formula", "lucky", "togashi_original_total")
_ACTION_LABELS = {"raise": "3rd Dan free raise", "togashi_raise": "Athletics raise (Togashi 3rd Dan)",
                  "conviction": "Conviction", "courtier_5th": "Courtier 5th Dan",
                  "pcp_raise": "Player Character Point free raise"}


def _write_payload(db: Session, session: RollSession) -> None:
    """The session's payload (and its history row) with the actions shown."""
    payload = dict(session.payload or {})
    base_bonuses = [b for b in payload.get("bonuses", []) if not b.get("post_roll")]
    for kind, count in _counts(session).items():
        amount = next(a.get("amount", 0) for a in session.actions if a["kind"] == kind)
        if amount:
            base_bonuses.append({"label": _ACTION_LABELS[kind], "amount": amount * count, "post_roll": True})
    payload["bonuses"] = base_bonuses
    payload["total"] = _session_total(session)
    session.payload = payload
    if session.history_id:
        row = db.get(RollHistory, session.history_id)
        if row is not None:
            row.payload = dict(row.payload or {}, **{k: payload[k] for k in _ROW_FIELDS if k in payload})


def act(db: Session, session: RollSession, character: Character, action: str,
        args: Dict[str, Any], rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """Apply one post-roll action to a session (and, live, to the pools)."""
    live = session.mode == "live"
    choices = dict(session.choices or {})
    choices.setdefault("base_total", (session.payload or {}).get("total", 0))
    session.choices = choices
    actions = list(session.actions or [])
    counts = _counts(session)
    undo = action.startswith("undo_")
    name = action[5:] if undo else action
    extra: Dict[str, Any] = {}

    if action in REROLLS:
        extra = REROLLS[action](db, session, character, args, rng or random.SystemRandom())
        actions = list(session.actions or [])
    elif name == "courtier_5th":
        amount = int((session.formula or {}).get("courtier_5th_dan_optional") or 0)
        if amount <= 0:
            raise RollRefused("this roll has no Courtier 5th Dan bonus")
        on = bool(args.get("on"))
        actions = [a for a in actions if a["kind"] != "courtier_5th"]
        if on:
            actions.append({"kind": "courtier_5th", "amount": amount})
    elif name in _NUMBER_ACTIONS:
        kind, amount = _NUMBER_ACTIONS[name]
        if undo:
            if counts.get(kind, 0) <= 0:
                raise RollRefused(f"no {name} to undo")
            for i in range(len(actions) - 1, -1, -1):
                if actions[i]["kind"] == kind:
                    actions.pop(i)
                    break
        else:
            cap = _per_roll_cap(session, character, kind)
            if counts.get(kind, 0) >= cap:
                raise RollRefused(f"no more {_ACTION_LABELS[kind]} on this roll")
            # Simulate mode never touches the pools, so this roll's own
            # spends count against what is left.
            left = _pool_left(character, kind) - (0 if live else counts.get(kind, 0))
            if left <= 0:
                raise RollRefused(f"no {_ACTION_LABELS[kind]} left")
            actions.append({"kind": kind, "amount": amount})
        if live:
            state = dict(character.adventure_state or {})
            key = _POOLS[kind] + "_used"
            state[key] = max(0, int(state.get(key, 0) or 0) + (-1 if undo else 1))
            character.adventure_state = state
    else:
        raise RollRefused(f"unknown action {action!r}")

    session.actions = actions
    _write_payload(db, session)
    db.flush()
    return dict(extra, **{
        "session_id": session.id,
        "total": session.payload["total"],
        "payload": session.payload,
        "dice": session.dice,
        "formula": session.formula,
        "tracking": tracking_snapshot(character),
    })


# ---------------------------------------------------------------------------
# Rerolls (Phase 4): new dice on a roll already made
# ---------------------------------------------------------------------------
#
# Every reroll keeps the roll's post-roll bonuses (decision S3): the actions
# list is untouched and the total is the rescored dice plus the same actions.
# Lucky, the PCP reroll and the Merchant's business reroll share ONE lock -
# a roll gets at most one of them - and each keeps the higher of the two
# totals. The Togashi 4th Dan reroll must take the new result.

REROLL_LOCK = ("lucky", "pcp_reroll", "merchant_reroll")
# Rolls a Togashi 4th Dan reroll is never offered on: they are not contested.
_NOT_CONTESTED = ("skill:etiquette", "skill:heraldry", "parry", "athletics:parry")

_NOTES = {
    "lucky": "Lucky reroll used",
    "pcp_reroll": "Player Character Point reroll used",
    "pcp_tens": "Rerolled 10s while impaired by spending a Player Character Point",
    "merchant_reroll": "Rerolled a business roll for a void point (Merchant)",
    "togashi_4th": "Togashi reroll used",
}


def _flag(session: RollSession, kind: str) -> bool:
    return any(a["kind"] == kind for a in session.actions or [])


def _add_flag(session: RollSession, kind: str, **fields: Any) -> None:
    session.actions = list(session.actions or []) + [dict(fields, kind=kind, amount=0)]


def _extras(character: Character, session: RollSession) -> list:
    f = session.formula or {}
    out = _spend_bullets(f.get("label") or session.roll_key, int(f.get("void_activation_cost") or 0),
                         int(f.get("void_spent") or 0), int(f.get("void_overflow_bonus") or 0))
    for a in session.actions or []:
        if a["kind"] in _NOTES:
            out.append(_NOTES[a["kind"]])
        elif a["kind"] == "merchant_5th":
            out.append(f"{a['delta']:+d} from Merchant 5th Dan reroll")
        elif a["kind"] == "priest_ritual":
            out.append(f"Impaired 10s rerolled ({a['priest']} performed the ritual)")
    merchant_vp = int(f.get("merchant_vp_spent") or 0)
    if merchant_vp:
        out.append(f"{_plural_points(merchant_vp)} spent after the roll (Merchant)")
    return out


def _plural_points(n: int) -> str:
    return f"{n} void point{'s' if n != 1 else ''}"


def _rescore(character: Character, session: RollSession, cells: list) -> None:
    """Put ``cells`` on the session and rescore it (the actions carry over)."""
    session.dice = cells
    scored = score_roll(character.to_dict(), session.formula or {}, cells,
                        _extras(character, session))
    session.payload = dict(session.payload or {}, **scored)
    session.choices = dict(session.choices or {}, base_total=scored["total"])


def _half(session: RollSession) -> Dict[str, Any]:
    p = session.payload or {}
    return {"kept": p.get("kept", []), "dropped": p.get("dropped", []),
            "total": _session_total(session), "show_total": True}


def _keep_higher(character: Character, session: RollSession, cells: list, source: str) -> None:
    """Reroll the whole roll and keep whichever total is higher (Lucky, PCP,
    Merchant). The pair is recorded as ``payload.lucky`` for the result panel,
    Roll History and the dice card."""
    before = (session.dice, dict(session.payload or {}), dict(session.choices or {}))
    original = _half(session)
    _rescore(character, session, cells)
    reroll = _half(session)
    keep_reroll = reroll["total"] >= original["total"]
    if not keep_reroll:
        session.dice, session.payload, session.choices = before[0], before[1], before[2]
        # The original dice stand, but the note that a reroll happened is new.
        _rescore(character, session, session.dice)
    session.payload = dict(session.payload, lucky={
        "kept": "reroll" if keep_reroll else "original",
        "original": original, "reroll": reroll, "source": source,
    })


def _whole(session: RollSession, rng) -> list:
    f = session.formula or {}
    return roll_dice(f.get("rolled") or 0, f.get("kept") or 0, bool(f.get("reroll_tens")),
                     rng, freed_tens=f.get("wave_man_freed_dice") or 0)["in_order"]


def _check_lock(session: RollSession) -> None:
    if any(_flag(session, k) for k in REROLL_LOCK):
        raise RollRefused("this roll has already been rerolled")


def _pcp(db: Session, session: RollSession, character: Character, use: str) -> Dict[str, Any]:
    """Pay a PCP for a live roll (simulate mode never pays). Called after
    every other check, so a refusal changes nothing."""
    if session.mode != "live":
        return {}
    try:
        return {"pcp": spend_pcp(db, character, use, session.viewer_discord_id)}
    except PcpRefused as exc:
        raise RollRefused(str(exc)) from None


def _void_point(db: Session, session: RollSession, character: Character, label: str) -> None:
    """One void point, drawn in the usual order with its school consequences.
    Simulate mode checks the pools net of this roll's own simulated spends."""
    f = session.formula or {}
    spent = (int(f.get("void_activation_cost") or 0) + int(f.get("void_spent") or 0)
             + sum(1 for a in session.actions or [] if a["kind"] == "merchant_reroll"))
    try:
        if session.mode == "live":
            apply_void_spend(character, plan_void_spend(character, 0, activation_cost=1,
                                                        roll_label=label))
        else:
            plan_void_spend(character, 0, activation_cost=spent + 1, roll_label=label)
    except VoidSpendRefused as exc:
        raise RollRefused(str(exc)) from None


def _impaired_tens(session: RollSession) -> list:
    f = session.formula or {}
    if f.get("no_reroll_reason") != "impaired" or f.get("is_unskilled"):
        raise RollRefused("only an Impaired roll's 10s can be rerolled")
    tens = [i for i, d in enumerate(session.dice or []) if d["value"] == 10]
    if not tens:
        raise RollRefused("there is no 10 to reroll")
    return tens


def _explode(cells: list, indices: list, rng) -> list:
    """Each die at ``indices`` (a 10 that did not explode) explodes now."""
    out = [dict(d, parts=list(d["parts"])) for d in cells]
    for i in indices:
        chain = roll_one_die(True, rng)
        out[i]["parts"] = [10] + chain["parts"]
        out[i]["value"] = 10 + chain["value"]
    return out


def _lucky_reroll(db, session, character, args, rng):
    _check_lock(session)
    live = session.mode == "live"
    if not any(a["id"] == "lucky_used" for a in per_adventure_abilities(character)):
        raise RollRefused(f"{character.name} is not Lucky")
    if (character.adventure_state or {}).get("lucky_used"):
        raise RollRefused("Lucky has already been used this adventure")
    _add_flag(session, "lucky")
    _keep_higher(character, session, _whole(session, rng), "lucky")
    if live:
        character.adventure_state = dict(character.adventure_state or {}, lucky_used=True)
    return {}


def _pcp_reroll(db, session, character, args, rng):
    _check_lock(session)
    paid = _pcp(db, session, character, "reroll")
    _add_flag(session, "pcp_reroll")
    _keep_higher(character, session, _whole(session, rng), "pcp")
    return paid


def _pcp_free_raise(db, session, character, args, rng):
    if _flag(session, "pcp_raise"):
        raise RollRefused("a Player Character Point free raise has already been taken on this roll")
    paid = _pcp(db, session, character, "free_raise")
    session.actions = list(session.actions or []) + [{"kind": "pcp_raise", "amount": 5}]
    return paid


def _pcp_reroll_tens(db, session, character, args, rng):
    if _flag(session, "pcp_tens"):
        raise RollRefused("this roll's 10s have already been rerolled")
    tens = _impaired_tens(session)
    paid = _pcp(db, session, character, "reroll_tens")
    _add_flag(session, "pcp_tens")
    _rescore(character, session, _explode(session.dice, tens, rng))
    return paid


def _priest_ritual(db, session, character, args, rng):
    """The Priest's sick-or-impaired ritual, performed in advance by the
    character (school or learned ritual) or a visible party member: the
    Impaired 10s on this roll are rerolled, and the new dice explode."""
    tens = _impaired_tens(session)
    try:
        priest_id = int(args.get("priest_id"))
    except (TypeError, ValueError):
        raise RollRefused("priest_id must be a character id") from None
    candidates = [character] + visible_party_members(db, character, session.viewer_discord_id)
    priest = next((c for c in candidates if c.id == priest_id and special_rolls.performs_impaired_ritual(c)),
                  None)
    if priest is None:
        raise RollRefused("that character cannot perform the ritual for this roll")
    fresh = [dict(roll_one_die(True, rng)) for _ in tens]
    cells = [dict(d) for d in session.dice]
    for i, die in zip(tens, fresh):
        cells[i] = die
    _add_flag(session, "priest_ritual", priest=priest.name)
    _rescore(character, session, cells)
    return {}


def _merchant_reroll(db, session, character, args, rng):
    """Merchant: a void point to reroll a roll relating to the business; the
    higher total stands."""
    if not holds_ability(character, "merchant_void_reroll"):
        raise RollRefused(f"{character.name} cannot reroll a business roll")
    _check_lock(session)
    _void_point(db, session, character, "the business reroll")
    _add_flag(session, "merchant_reroll")
    _keep_higher(character, session, _whole(session, rng), "merchant")
    return {}


def _merchant_5th(db, session, character, args, rng):
    """Merchant 5th Dan: reroll any dice whose values sum to at least
    5 * (count - 1); once per roll. ``values`` names the dice by value
    (dice of one value are interchangeable)."""
    if character.school != "merchant" or school_dan(character.to_dict()) < 5:
        raise RollRefused(f"{character.name} has no Merchant 5th Dan reroll")
    if _flag(session, "merchant_5th"):
        raise RollRefused("the Merchant 5th Dan reroll has already been used on this roll")
    values = args.get("values")
    if not isinstance(values, list) or not values:
        raise RollRefused("choose at least one die")
    cells = [dict(d) for d in session.dice or []]
    chosen = []
    for v in values:
        i = next((j for j, d in enumerate(cells) if d["value"] == v and j not in chosen), None)
        if i is None:
            raise RollRefused(f"there is no {v} to reroll")
        chosen.append(i)
    if sum(cells[i]["value"] for i in chosen) < 5 * (len(chosen) - 1):
        raise RollRefused(f"those dice must sum to at least {5 * (len(chosen) - 1)}")
    before = int((session.choices or {}).get("base_total", 0))
    reroll_tens = bool((session.formula or {}).get("reroll_tens"))
    for i in chosen:
        cells[i] = roll_one_die(reroll_tens, rng)
    _add_flag(session, "merchant_5th", delta=0)
    _rescore(character, session, cells)
    delta = int(session.choices["base_total"]) - before
    session.actions[-1] = dict(session.actions[-1], delta=delta)
    session.formula = dict(session.formula, merchant_5th_dan_used=True, merchant_5th_dan_bonus=delta)
    _rescore(character, session, cells)
    return {}


def _merchant_vp(db, session, character, args, rng):
    """Merchant Special Ability: a void point after seeing the roll is +1k1
    (a new die), within the roll's usual per-roll void cap."""
    if character.school not in ("merchant", "suzume_overseer"):
        raise RollRefused(f"{character.name} cannot spend void points after the roll")
    f = dict(session.formula or {})
    cap = void_limits(character.to_dict())["cap"]
    if int(f.get("void_spent") or 0) + 1 > cap:
        raise RollRefused(f"{character.name} can spend at most {_plural_points(cap)} on a single roll")
    _void_point(db, session, character, "a void point after the roll")
    capped = apply_dice_cap((f.get("rolled") or 0) + 1, (f.get("kept") or 0) + 1, f.get("flat") or 0)
    cells = [dict(d) for d in session.dice or []]
    if capped["rolled"] > len(cells):
        cells.append(roll_one_die(bool(f.get("reroll_tens")), rng))
    f.update(rolled=capped["rolled"], kept=capped["kept"], flat=capped["flat"],
             void_spent=int(f.get("void_spent") or 0) + 1,
             merchant_vp_spent=int(f.get("merchant_vp_spent") or 0) + 1,
             void_overflow_bonus=int(f.get("void_overflow_bonus") or 0) + capped["overflow_flat"])
    session.formula = f
    _rescore(character, session, cells)
    session.payload = dict(session.payload, formula=_formula_text(f))
    return {}


def _togashi_4th(db, session, character, args, rng):
    """Togashi Ise Zumi 4th Dan: reroll a contested roll; the new result
    stands. Keeps every bonus already on the roll (S3, settling 5.1) and
    stays one roll - one history row."""
    if character.school != "togashi_ise_zumi" or school_dan(character.to_dict()) < 4:
        raise RollRefused(f"{character.name} has no Togashi 4th Dan reroll")
    f = session.formula or {}
    if (_flag(session, "togashi_4th") or _flag(session, "lucky") or f.get("is_initiative")
            or f.get("is_damage_roll") or session.roll_key in _NOT_CONTESTED):
        raise RollRefused("this roll cannot take the Togashi 4th Dan reroll")
    original = _session_total(session)
    _add_flag(session, "togashi_4th", original_total=original)
    _rescore(character, session, _whole(session, rng))
    session.payload = dict(session.payload, togashi_original_total=original)
    return {}


REROLLS = {
    "lucky_reroll": _lucky_reroll,
    "pcp_reroll": _pcp_reroll,
    "pcp_free_raise": _pcp_free_raise,
    "pcp_reroll_tens": _pcp_reroll_tens,
    "priest_ritual": _priest_ritual,
    "merchant_reroll": _merchant_reroll,
    "merchant_5th": _merchant_5th,
    "merchant_vp": _merchant_vp,
    "togashi_4th": _togashi_4th,
}
