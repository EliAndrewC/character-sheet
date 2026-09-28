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
from app.services import combat_math as cm
from app.services.attack_rolls import (
    attack_flags, attack_outcome, build_attack, current_posture, offensive_count,
)
from app.services.combat_math import damage_flags
from app.services.duels import (
    DUEL_KEYS, KAKITA_5TH, duel_damage_pool, kakita_5th_damage_pool, kakita_5th_formula,
    restart_bonus, weapon_dice,
)
from app.services.tracking import set_serious_wounds
from app.services.wound_checks import (
    akodo_banked_bonus, build_wound_check, daidoji_counterattack, wound_check_flags,
)
from app.services.parry_feint import PARRY_KEYS, apply_post_roll_hooks, is_feint, parry_feint_flags
from app.services.pcp import PcpRefused, spend_pcp
from app.services.professions import holds_ability
from app.services.roll_engine import (
    _formula_text, _spend_bullets, apply_dice_cap, execute_roll, impaired_now, roll_dice,
    roll_initiative_dice, roll_one_die, score_initiative, score_roll,
)
from app.services.rolls_history import skill_rank_for_roll
from app.services.tracking import start_combat_round, tracking_snapshot
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
    """Whether the sheet's roll for this key is made here yet: the generic
    rolls (Phase 1), initiative (5), parry and feint (6)."""
    if roll_key in SPECIAL_KEYS:
        return True
    if roll_key in ("initiative", "initiative:athletics"):
        return True
    if not roll_key or roll_key.startswith("initiative"):
        return False
    if roll_key in PARRY_KEYS or roll_key in ("attack", "athletics:attack", "wound_check", KAKITA_5TH) \
            or roll_key in DUEL_KEYS:
        return True
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
    if roll_key.startswith("initiative"):
        if void or ow or choices.get("kitsune_swap"):
            raise RollRefused("initiative is rolled without spending void points")
        return _start_initiative(db, character, roll_key, char_data, party, viewer=viewer,
                                 live=live, record=record, is_owner_roll=is_owner_roll,
                                 rng=rng, request_id=request_id)
    record_key = roll_key
    activation = 0
    if roll_key in SPECIAL_KEYS:
        if void or ow or choices.get("kitsune_swap"):
            raise RollRefused(f"no void, otherworldliness or ring swap on a {roll_key} roll")
        formula, record_key, activation = _special(character, char_data, roll_key, choices)
    else:
        all_formulas = build_all_roll_formulas(char_data, party_members=party)
        formula = all_formulas.get(DUEL_KEYS.get(roll_key, roll_key))
        if roll_key == KAKITA_5TH:
            if void or ow or choices.get("kitsune_swap"):
                raise RollRefused("the Kakita 5th Dan contest takes no void")
            try:
                formula = kakita_5th_formula(character, all_formulas, choices)
            except ValueError as exc:
                raise RollRefused(str(exc)) from None
        if not formula:
            raise RollRefused(f"{character.name} has no {roll_key} roll")
        formula = dict(formula)
        if roll_key in DUEL_KEYS:
            formula = _duel_formula(roll_key, formula, choices, void, ow)
    label = formula.get("label") or roll_key

    # A parry declared before the attack is rolled: +5.
    if choices.get("predeclared"):
        if roll_key not in PARRY_KEYS:
            raise RollRefused("only a parry can be predeclared")
        formula["flat"] = (formula.get("flat") or 0) + 5
        formula["bonuses"] = list(formula.get("bonuses") or []) + [
            {"label": "predeclared parry", "amount": 5}]

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

    # An attack: the modal's situational inputs, and the banks it spends.
    consumes: list = []
    if formula.get("is_attack_type"):
        formula, consumes = _start_attack(character, formula, choices)
    if roll_key == "wound_check":
        formula, consumes = _start_wound_check(db, character, formula, choices, viewer, live, void, ow)

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
    notes: list = []
    if live:
        apply_void_spend(character, plan)
        if roll_key in PARRY_KEYS or is_feint(roll_key):
            notes = apply_post_roll_hooks(character, roll_key)
        if ow:
            state = dict(character.adventure_state or {})
            state["otherworldliness_used"] = int(state.get("otherworldliness_used", 0) or 0) + ow
            character.adventure_state = state
        if record:
            row = RollHistory(
                character_id=character.id, roll_key=record_key, actor_discord_id=viewer,
                is_owner_roll=is_owner_roll, impaired_at_roll=impaired_now(char_data),
                payload=payload, tn=effective.get("attack_tn"),
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
                 "kept": choices.get("kept"), "reroll_tens": choices.get("reroll_tens"),
                 "predeclared": bool(choices.get("predeclared")), "notes": notes,
                 "record": record, "is_owner_roll": is_owner_roll,
                 "base_total": payload["total"]},
        formula=effective, dice=out["dice"], payload=payload, actions=[], history_id=history_id,
    )
    if effective.get("is_attack_type"):
        _after_attack_roll(character, session, consumes, live)
        _write_payload(db, session)
    if roll_key in DUEL_KEYS or roll_key == KAKITA_5TH:
        _duel_state(session)
        if roll_key == KAKITA_5TH and live:
            # Once per combat round, latched the moment the contest is rolled.
            character.adventure_state = dict(character.adventure_state or {}, kakita_5th_dan_used=True)
    if roll_key == "wound_check":
        if live:
            state = dict(character.adventure_state or {})
            for key in consumes:
                state.pop(key, None)
            character.adventure_state = state
        _wc_state(session)
    db.add(session)
    db.flush()
    return _answer(session, character)


def _start_initiative(db: Session, character: Character, roll_key: str, char_data, party, *,
                      viewer, live, record, is_owner_roll, rng, request_id) -> Dict[str, Any]:
    """Initiative (either Togashi variant): roll, turn the kept dice into
    action dice, and - live - start the combat round (``start_combat_round``,
    the same definition the Discord /initiative command uses) and record."""
    formula = build_all_roll_formulas(char_data, party_members=party).get(roll_key)
    if not formula:
        raise RollRefused(f"{character.name} has no {roll_key} roll")
    formula = dict(formula, void_spent=0, void_overflow_bonus=0)
    dice = roll_initiative_dice(formula, rng or random.SystemRandom())
    scored = score_initiative(formula, dice["main"], dice["extra"])
    notes: list = []
    history_id = None
    if live:
        notes = start_combat_round(character, scored["action_dice"])
        if record:
            row = RollHistory(
                character_id=character.id, roll_key=roll_key, actor_discord_id=viewer,
                is_owner_roll=is_owner_roll, impaired_at_roll=impaired_now(char_data),
                payload=scored["payload"],
            )
            db.add(row)
            db.flush()
            history_id = row.id
    reap(db)
    session = RollSession(
        id=request_id or secrets.token_hex(16), character_id=character.id, viewer_discord_id=viewer,
        mode="live" if live else "simulate", roll_key=roll_key,
        choices={"extra": dice["extra"], "action_dice": scored["action_dice"], "notes": notes,
                 "base_total": 0},
        formula=formula, dice=dice["main"], payload=scored["payload"], actions=[],
        history_id=history_id,
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
    return dict(_initiative_fields(session), **{
        "session_id": session.id,
        "mode": session.mode,
        "formula": session.formula,
        "dice": session.dice,
        "total": (session.payload or {}).get("total"),
        "payload": session.payload,
        "history_id": session.history_id,
        "tracking": tracking_snapshot(character),
    })


def _initiative_fields(session: RollSession) -> Dict[str, Any]:
    """What the roll did by itself: an initiative roll's action dice, and the
    notes (round start, or a parry's / feint's school hooks)."""
    choices = session.choices or {}
    out: Dict[str, Any] = {"notes": choices.get("notes") or []}
    if (session.formula or {}).get("is_initiative"):
        out["action_dice"] = choices.get("action_dice", [])
    if "attack" in choices:
        out["attack"] = choices["attack"]
    if "wc" in choices:
        out["wc"] = choices["wc"]
    if "duel" in choices:
        out["duel"] = choices["duel"]
    return out


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
                  "pcp_raise": "Player Character Point free raise",
                  "mirumoto": "Mirumoto 3rd Dan points", "akodo_vp": "Akodo 4th Dan void raises",
                  "shinjo_phase": "Shinjo phases held",
                  "isawa": "Isawa 3rd Dan (-5 TN to be hit)", "wave_man": "Wave Man miss raises",
                  "akodo_bank": "Akodo 3rd Dan banked bonus", "bayushi_raise": "Bayushi 4th Dan banked raise",
                  "post_bonus": "post-roll bonus",
                  "wc_vp": "void points after the roll (4th Dan)", "matsu_bank": "Matsu 3rd Dan banked bonus",
                  "wc_excess": "banked wound check excess"}


def _write_payload(db: Session, session: RollSession) -> None:
    """The session's payload (and its history row) with the actions shown."""
    payload = dict(session.payload or {})
    base_bonuses = [b for b in payload.get("bonuses", []) if not b.get("post_roll")]
    for kind in _counts(session):
        amount = sum(a.get("amount", 0) * a.get("count", 1) for a in session.actions if a["kind"] == kind)
        if amount:
            base_bonuses.append({"label": _ACTION_LABELS[kind], "amount": amount, "post_roll": True})
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
    if choices.get("resolved"):
        raise RollRefused("this wound check is already resolved")
    if (session.formula or {}).get("iaijutsu_strike") and name in (
            "raise", "togashi_raise", "wc_vp", "matsu_bank", "wc_excess", "pcp_free_raise"):
        raise RollRefused("only Conviction may be spent on an iaijutsu strike's wound check")

    if action in REROLLS:
        extra = REROLLS[action](db, session, character, args, rng or random.SystemRandom())
        actions = list(session.actions or [])
    elif name in UNDOABLE:
        extra = UNDOABLE[name](db, session, character, args, rng, undo=undo)
        actions = list(session.actions or [])
    elif (session.formula or {}).get("is_initiative"):
        raise RollRefused("initiative takes no bonuses")
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
    if _is_attack(session):
        _attack_state(character, session)
    if session.roll_key == "wound_check":
        _wc_state(session)
    if session.roll_key in DUEL_KEYS:
        _duel_state(session)
    _write_payload(db, session)
    db.flush()
    return dict(extra, **_initiative_fields(session), **{
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
    if (session.formula or {}).get("is_initiative"):
        _rescore_initiative(character, session, cells)
        return
    session.dice = cells
    scored = score_roll(character.to_dict(), session.formula or {}, cells,
                        _extras(character, session))
    session.payload = dict(session.payload or {}, **scored)
    session.choices = dict(session.choices or {}, base_total=scored["total"])
    if _is_attack(session):
        _attack_state(character, session, redo_w1=True)
    if session.roll_key == "wound_check":
        _wc_state(session)


def _rescore_initiative(character: Character, session: RollSession, cells: list) -> None:
    """New initiative dice are new action dice: a live reroll starts the
    round over with them (the reroll replaces the first set)."""
    choices = dict(session.choices or {})
    scored = score_initiative(session.formula or {}, cells, choices.get("extra") or [])
    session.dice = cells
    session.payload = dict(session.payload or {}, **scored["payload"])
    choices["action_dice"] = scored["action_dice"]
    if session.mode == "live":
        choices["notes"] = list(choices.get("notes") or []) + [
            n for n in start_combat_round(character, scored["action_dice"])
            if n not in (choices.get("notes") or [])]
    session.choices = choices


def _half(session: RollSession) -> Dict[str, Any]:
    p = session.payload or {}
    if (session.formula or {}).get("is_initiative"):
        return {"kept": p.get("kept", []), "dropped": p.get("dropped", []), "total": 0,
                "show_total": False, "action_dice": [
                    {"value": d["value"]} for d in (session.choices or {}).get("action_dice", [])]}
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
    # Initiative has no total to compare: the reroll stands.
    keep_reroll = (bool((session.formula or {}).get("is_initiative"))
                   or reroll["total"] >= original["total"])
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
    if f.get("is_initiative"):
        dice = roll_initiative_dice(f, rng)
        session.choices = dict(session.choices or {}, extra=dice["extra"])
        return dice["main"]
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


def _not_on_initiative(session: RollSession, what: str) -> None:
    if (session.formula or {}).get("is_initiative"):
        raise RollRefused(f"{what} cannot be used on initiative")


def _impaired_tens(session: RollSession) -> list:
    f = session.formula or {}
    _not_on_initiative(session, "rerolling 10s")
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
    _not_on_initiative(session, "a free raise")
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
    _not_on_initiative(session, "the business reroll")
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
    _not_on_initiative(session, "the Merchant 5th Dan reroll")
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
    _not_on_initiative(session, "a void point after the roll")
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


# ---------------------------------------------------------------------------
# Parry and feint (Phase 6): the result panel's choices
# ---------------------------------------------------------------------------

_AKODO_VP_KEYS = ("parry", "athletics:parry", "knack:feint", "knack:iaijutsu", "knack:iaijutsu:evaluate",
                  "iaijutsu:contested")


def _flags(character: Character) -> Dict[str, Any]:
    return parry_feint_flags(character.to_dict())


def _once(session: RollSession, kind: str, what: str) -> None:
    if _flag(session, kind):
        raise RollRefused(f"{what} has already been used on this roll")


def _mirumoto_point(db, session, character, args, rng, undo=False):
    """Mirumoto 3rd Dan: +2 per point, from the points left this round."""
    if not _flags(character)["mirumoto_round_points"] or not (session.roll_key == "parry" or _is_attack(session)):
        raise RollRefused("no 3rd Dan points on this roll")
    spent = sum(1 for a in session.actions or [] if a["kind"] == "mirumoto")
    if undo:
        if not spent:
            raise RollRefused("no 3rd Dan point to undo")
        actions = list(session.actions)
        actions.pop(max(i for i, a in enumerate(actions) if a["kind"] == "mirumoto"))
        session.actions = actions
    else:
        left = int((character.adventure_state or {}).get("mirumoto_round_points") or 0)
        if left - (0 if session.mode == "live" else spent) <= 0:
            raise RollRefused("no 3rd Dan points left this round")
        session.actions = list(session.actions or []) + [{"kind": "mirumoto", "amount": 2}]
    if session.mode == "live":
        state = dict(character.adventure_state or {})
        state["mirumoto_round_points"] = max(0, int(state.get("mirumoto_round_points") or 0)
                                             + (1 if undo else -1))
        character.adventure_state = state
    return {}


def _akodo_vp(db, session, character, args, rng, undo=False):
    """Akodo 4th Dan: a void point after the roll for +5 on a combat roll -
    not bound by the per-roll cap. Drawn (and consequences applied) like any
    spend; undo returns the point to the pool it came from."""
    if not _flags(character)["akodo_combat_vp_free_raise"] or not (
            session.roll_key in _AKODO_VP_KEYS or _is_attack(session)):
        raise RollRefused("no Akodo 4th Dan void raise on this roll")
    return _void_raise(session, character, undo, "akodo_vp", "the 4th Dan raise")


def _akodo_feint(db, session, character, args, rng):
    """Akodo Special: a feint gives 4 temp VP if it succeeded, 1 if not."""
    if not _flags(character)["akodo_temp_vp_on_feint"] or session.roll_key != "knack:feint":
        raise RollRefused("no Akodo feint void points on this roll")
    _once(session, "akodo_feint", "the Akodo feint")
    gain = 4 if args.get("succeeded") else 1
    _add_flag(session, "akodo_feint", gain=gain)
    if session.mode == "live":
        character.current_temp_void_points = (character.current_temp_void_points or 0) + gain
    return {"gained": gain}


def _ide_bank(db, session, character, args, rng):
    """Ide Special: a feint banks -10 to the target's TN for the next attack."""
    if not _flags(character)["ide_feint_tn_reduce"] or session.roll_key != "knack:feint":
        raise RollRefused("no Ide TN bank on this roll")
    _once(session, "ide_bank", "the Ide TN bank")
    _add_flag(session, "ide_bank")
    if session.mode == "live":
        state = dict(character.adventure_state or {})
        state["ide_banked_tn_reduce"] = int(state.get("ide_banked_tn_reduce") or 0) + 10
        character.adventure_state = state
    return {}


def _shinjo_bank(db, session, character, args, rng):
    """Shinjo 5th Dan: bank how far this parry beat the attack roll."""
    if not _flags(character)["shinjo_bank_parry_excess"] or session.roll_key != "parry":
        raise RollRefused("no Shinjo 5th Dan bank on this roll")
    _once(session, "shinjo_bank", "the Shinjo 5th Dan bank")
    try:
        opponent = max(0, int(args.get("opponent") or 0))
    except (TypeError, ValueError):
        raise RollRefused("opponent must be a whole number") from None
    banked = max(0, _session_total(session) - opponent)
    _add_flag(session, "shinjo_bank", banked=banked)
    if session.mode == "live" and banked:
        state = dict(character.adventure_state or {})
        state["banked_wc_excess"] = list(state.get("banked_wc_excess") or []) + [banked]
        character.adventure_state = state
    return {"banked": banked}


def _shinjo_phase(db, session, character, args, rng):
    """Shinjo Special on a parry: +2 per phase the spent action die was held."""
    if character.school != "shinjo_bushi" or session.roll_key not in PARRY_KEYS:
        raise RollRefused("no Shinjo phase bonus on this roll")
    try:
        phase = max(0, min(10, int(args.get("phase") or 0)))
        die = max(0, min(10, int(args.get("die_value") or 0)))
    except (TypeError, ValueError):
        raise RollRefused("phase and die_value must be whole numbers") from None
    amount = 2 * max(0, phase - die) if phase > 0 else 0
    session.actions = [a for a in session.actions or [] if a["kind"] != "shinjo_phase"]
    if amount:
        session.actions = session.actions + [{"kind": "shinjo_phase", "amount": amount}]
    return {}


def _sub_damage(db, session, character, args, rng):
    """Shiba 3rd Dan parry damage / Bayushi 3rd Dan feint damage: a damage
    roll of its own, recorded (settles 5.5)."""
    flags = _flags(character)
    f = session.formula or {}
    if session.roll_key == "parry" and flags["shiba_parry_damage"]:
        rolled, kept, key = flags["shiba_parry_damage_rolled"], 1, "damage:shiba_parry"
        label = f"Shiba 3rd Dan parry damage ({rolled}k1)"
    elif session.roll_key == "knack:feint" and flags["bayushi_feint_damage"]:
        extra = int(f.get("void_spent") or 0) if damage_flags(character.to_dict())["bayushi_vp_damage"] else 0
        rolled, kept, key = flags["bayushi_feint_damage_rolled"] + extra, 1 + extra, "damage:bayushi_feint"
        label = f"Bayushi 3rd Dan feint damage ({rolled}k{kept})"
    else:
        raise RollRefused("no damage roll on this roll")
    _once(session, "sub_damage", "the damage roll")
    capped = apply_dice_cap(rolled, kept, 0)
    dice = roll_dice(capped["rolled"], capped["kept"], True, rng)
    total = dice["kept_sum"] + capped["flat"]
    payload = {
        "title": label, "formula": _formula_text({"rolled": capped["rolled"], "kept": capped["kept"],
                                                   "flat": capped["flat"]}),
        "kept": [{"parts": d["parts"]} for d in dice["kept"]],
        "dropped": [{"parts": d["parts"]} for d in dice["dropped"]],
        "bonuses": [], "extras": [], "kept_sum": dice["kept_sum"], "total": total,
    }
    history_id = None
    choices = session.choices or {}
    if session.mode == "live" and choices.get("record"):
        row = RollHistory(character_id=character.id, roll_key=key,
                          actor_discord_id=session.viewer_discord_id,
                          is_owner_roll=bool(choices.get("is_owner_roll")),
                          impaired_at_roll=impaired_now(character.to_dict()), payload=payload)
        db.add(row)
        db.flush()
        history_id = row.id
    _add_flag(session, "sub_damage", total=total)
    return {"sub_damage": {"label": label, "dice": dice["in_order"], "total": total,
                           "kept": capped["kept"], "history_id": history_id}}


REROLLS.update({
    "akodo_feint": _akodo_feint,
    "ide_bank": _ide_bank,
    "shinjo_bank": _shinjo_bank,
    "shinjo_phase": _shinjo_phase,
    "sub_damage": _sub_damage,
})
# Actions with an undo form (the number buttons with their own rules).
UNDOABLE = {"mirumoto_point": _mirumoto_point, "akodo_vp": _akodo_vp}



# ---------------------------------------------------------------------------
# Attacks (Phase 7)
# ---------------------------------------------------------------------------

def _is_attack(session: RollSession) -> bool:
    return bool((session.formula or {}).get("is_attack_type"))


def attack_specs(character: Character) -> list:
    """The Attack specializations the modal offers as +10 boxes."""
    return [{"text": s.get("text") or ""} for s in (character.specializations or [])
            if "attack" in (s.get("skills") or [])]


def _attack_state(character: Character, session: RollSession, redo_w1: bool = False) -> Dict[str, Any]:
    """Judge the attack at its current total (Wave Man W1 is re-applied when
    the dice changed) and keep the result on the session."""
    f = session.formula or {}
    flags = attack_flags(character.to_dict())
    if redo_w1:
        session.actions = [a for a in session.actions or [] if a["kind"] != "wave_man"]
        copies = int(f.get("wave_man_miss_raise") or 0)
        eff = attack_outcome(f, 0)["effective_tn"]
        total = _session_total(session)
        if copies and total < eff:
            used = cm.wave_man_miss_raise(total, eff, copies)["raises_used"]
            if used:
                session.actions = session.actions + [{"kind": "wave_man", "amount": 5 * used}]
    raised = sum(a["amount"] for a in session.actions or [] if a["kind"] == "wave_man")
    out = attack_outcome(f, _session_total(session), raised, flags["matsu_near_miss"])
    out["wave_man_raises"] = raised // 5
    session.choices = dict(session.choices or {}, attack=out)
    return out


def _start_attack(character: Character, formula: Dict[str, Any], choices: Dict[str, Any]):
    try:
        built = build_attack(character, formula, choices, attack_specs(character))
    except ValueError as exc:
        raise RollRefused(str(exc)) from None
    return built["formula"], built["consumes"]


def _after_attack_roll(character: Character, session: RollSession, consumes: list, live: bool) -> None:
    """What making the attack does: the Isawa trade (on by default, the
    player may take it back), the banks it spends, Hida 5th Dan's bank."""
    flags = attack_flags(character.to_dict())
    if flags["isawa_tn_trade"] and flags["isawa_tn_trade_bonus"]:
        session.actions = list(session.actions or []) + [
            {"kind": "isawa", "amount": flags["isawa_tn_trade_bonus"]}]
    pre_w1 = _session_total(session)
    out = _attack_state(character, session, redo_w1=True)
    if not live:
        return
    state = dict(character.adventure_state or {})
    for key in consumes:
        state.pop(key, None)
    excess = pre_w1 - out["effective_tn"]
    if (flags["hida_counterattack_wc_bonus"] and out["hit"]
            and (session.formula or {}).get("attack_variant") == "counterattack" and excess > 0):
        state["hida_banked_wc_bonus"] = int(state.get("hida_banked_wc_bonus") or 0) + excess
    character.adventure_state = state


def _attack_only(session: RollSession, what: str) -> None:
    if not _is_attack(session):
        raise RollRefused(f"{what} is only for an attack")


def _akodo_bank(db, session, character, args, rng, undo=False):
    """Akodo 3rd Dan: spend a banked wound-check bonus on this attack."""
    _attack_only(session, "an Akodo banked bonus")
    if not attack_flags(character.to_dict())["akodo_wc_attack_bonus"]:
        raise RollRefused(f"{character.name} has no Akodo banked bonuses")
    mine = [i for i, a in enumerate(session.actions or []) if a["kind"] == "akodo_bank"]
    live = session.mode == "live"
    state = dict(character.adventure_state or {})
    bank = list(state.get("akodo_banked_bonuses") or [])
    if undo:
        if not mine:
            raise RollRefused("no banked bonus to put back")
        actions = list(session.actions)
        entry = actions.pop(mine[-1])
        session.actions = actions
        if live:
            state["akodo_banked_bonuses"] = bank + [entry["amount"]]
            character.adventure_state = state
        return {}
    try:
        amount = int(args.get("amount"))
    except (TypeError, ValueError):
        raise RollRefused("amount must be a whole number") from None
    used = 0 if live else sum(1 for i in mine if session.actions[i]["amount"] == amount)
    if bank.count(amount) - used <= 0:
        raise RollRefused(f"no banked +{amount} to spend")
    if live:
        bank.remove(amount)
        state["akodo_banked_bonuses"] = bank
        character.adventure_state = state
    session.actions = list(session.actions or []) + [{"kind": "akodo_bank", "amount": amount}]
    return {}


def _bayushi_raise(db, session, character, args, rng, undo=False):
    """Bayushi 4th Dan: spend a feint's banked free raise on this attack."""
    _attack_only(session, "a Bayushi banked raise")
    mine = sum(1 for a in session.actions or [] if a["kind"] == "bayushi_raise")
    live = session.mode == "live"
    state = dict(character.adventure_state or {})
    banked = int(state.get("bayushi_banked_feint_raise") or 0)
    if undo:
        if not mine:
            raise RollRefused("no banked raise to put back")
        actions = list(session.actions)
        actions.pop(max(i for i, a in enumerate(actions) if a["kind"] == "bayushi_raise"))
        session.actions = actions
        delta = 5
    else:
        if banked - (0 if live else 5 * mine) < 5:
            raise RollRefused("no banked raise to spend")
        session.actions = list(session.actions or []) + [{"kind": "bayushi_raise", "amount": 5}]
        delta = -5
    if live:
        state["bayushi_banked_feint_raise"] = banked + delta
        character.adventure_state = state
    return {}


def _isawa(db, session, character, args, rng):
    """Isawa 3rd Dan: the TN trade is on by default; the player may take it
    back (or put it back) after seeing the roll."""
    _attack_only(session, "the Isawa trade")
    flags = attack_flags(character.to_dict())
    if not flags["isawa_tn_trade"]:
        raise RollRefused(f"{character.name} has no Isawa trade")
    session.actions = [a for a in session.actions or [] if a["kind"] != "isawa"]
    if args.get("on"):
        session.actions = session.actions + [{"kind": "isawa", "amount": flags["isawa_tn_trade_bonus"]}]
    return {}


def _post_bonus(db, session, character, args, rng):
    """A bonus the GM grants after the roll: the modal's "post-roll bonus"."""
    _attack_only(session, "a post-roll bonus")
    try:
        amount = max(-999, min(999, int(args.get("amount") or 0)))
    except (TypeError, ValueError):
        raise RollRefused("amount must be a whole number") from None
    session.actions = [a for a in session.actions or [] if a["kind"] != "post_bonus"]
    if amount:
        session.actions = session.actions + [{"kind": "post_bonus", "amount": amount}]
    return {}


def _courtier_vp(db, session, character, args, rng):
    """Courtier 4th Dan: a temp void point after a successful attack."""
    _attack_only(session, "the Courtier void point")
    if not attack_flags(character.to_dict())["courtier_temp_vp_on_hit"]:
        raise RollRefused(f"{character.name} gains no void point from an attack")
    if not _attack_state(character, session)["hit"]:
        raise RollRefused("only a successful attack gives the void point")
    _once(session, "courtier_vp", "the Courtier void point")
    _add_flag(session, "courtier_vp")
    if session.mode == "live":
        character.current_temp_void_points = (character.current_temp_void_points or 0) + 1
    return {}


def _hida_reroll(db, session, character, args, rng):
    """Hida 3rd Dan: reroll up to X dice (2X on a counterattack, half when
    Impaired); the new dice explode. Every bonus on the roll stays (S3,
    settling 5.2)."""
    _attack_only(session, "the Hida reroll")
    flags = attack_flags(character.to_dict())
    if not flags["hida_reroll"]:
        raise RollRefused(f"{character.name} has no Hida 3rd Dan reroll")
    _once(session, "hida_reroll", "the Hida reroll")
    is_counter = (session.formula or {}).get("attack_variant") == "counterattack"
    top = 2 * flags["hida_reroll_x"] if is_counter else flags["hida_reroll_x"]
    if is_impaired(character.to_dict()):
        top = -(-top // 2)
    values = args.get("values")
    if not isinstance(values, list) or not values:
        raise RollRefused("choose at least one die")
    if len(values) > top:
        raise RollRefused(f"at most {top} dice may be rerolled")
    cells = [dict(d) for d in session.dice or []]
    chosen: list = []
    for v in values:
        i = next((j for j, d in enumerate(cells) if d["value"] == v and j not in chosen), None)
        if i is None:
            raise RollRefused(f"there is no {v} to reroll")
        chosen.append(i)
    for i in chosen:
        cells[i] = roll_one_die(True, rng)
    _add_flag(session, "hida_reroll")
    _rescore(character, session, cells)
    return {}


def _damage(db, session, character, args, rng):
    """Roll the damage for a hit: a session of its own (so it can be rerolled
    and take Conviction), built by the one damage assembler, recorded as
    ``<attack key>:damage``."""
    _attack_only(session, "damage")
    if args.get("tn") is not None:
        # The TN may be corrected after the roll; the hit is judged at it.
        try:
            session.formula = dict(session.formula, attack_tn=max(0, int(args["tn"])))
        except (TypeError, ValueError):
            raise RollRefused("tn must be a whole number") from None
    out = _attack_state(character, session)
    if not out["hit"]:
        raise RollRefused("only a hit rolls damage")
    _once(session, "damage", "the damage roll")
    f = session.formula or {}
    data = character.to_dict()
    flags = attack_flags(data)
    try:
        parry_skill = max(0, min(10, int(args.get("parry_skill") or 0)))
        weapon = (max(0, min(10, int(args.get("weapon_rolled", 4)))),
                  max(1, min(10, int(args.get("weapon_kept", 2)))))
    except (TypeError, ValueError):
        raise RollRefused("parry skill and weapon dice must be whole numbers") from None
    trade = 0
    if args.get("trade"):
        if not flags["otaku_trade_dice_for_sw"]:
            raise RollRefused(f"{character.name} cannot trade damage dice")
        trade = 10
    state = character.adventure_state or {}
    extra_flats = []
    if current_posture(state) == "offensive":
        extra_flats.append(("offensive posture", 5))
    if flags["mantis_posture_accumulation"] and offensive_count(state):
        extra_flats.append(("Mantis 5th Dan (offensive posture count)", offensive_count(state)))
    accum = int(state.get("mantis_offensive_3rd_dan_accum") or 0)
    if flags["mantis_3rd_dan_offensive"] and accum:
        extra_flats.append(("Mantis 3rd Dan (offensive)", accum))
    pool = cm.damage_pool(
        f, extra_dice=out["extra_dice"], failed_parry=bool(args.get("failed_parry")),
        parry_skill=parry_skill, flags=damage_flags(data), weapon_dice=weapon,
        extra_flats=tuple(extra_flats), wave_man_recover=bool(args.get("wave_man_recover", True)),
        trade_dice=trade,
    )
    variant = (f.get("attack_variant") or "attack").replace("_", " ").title()
    dformula = {
        "label": f"{variant} damage", "rolled": pool["rolled"], "kept": pool["kept"],
        "flat": pool["flat"], "reroll_tens": True, "is_damage_roll": True, "bonuses": [],
        "damage_parts": pool["parts"], "void_spent": 0, "void_overflow_bonus": 0,
        "wave_man_round_damage": f.get("wave_man_round_damage") or 0,
        "shosuro_5th_dan": bool(f.get("shosuro_5th_dan")), "traded_for_sw": bool(trade),
    }
    dice = roll_dice(pool["rolled"], pool["kept"], True, rng)["in_order"]
    scored = score_roll(data, dformula, dice, list(pool["parts"]))
    payload = dict(scored, title=dformula["label"], formula=_formula_text(dformula))
    key = session.roll_key + ":damage"
    history_id = None
    choices = session.choices or {}
    if session.mode == "live" and choices.get("record"):
        row = RollHistory(character_id=character.id, roll_key=key,
                          actor_discord_id=session.viewer_discord_id,
                          is_owner_roll=bool(choices.get("is_owner_roll")),
                          impaired_at_roll=impaired_now(data), payload=payload)
        db.add(row)
        db.flush()
        history_id = row.id
    child = RollSession(
        id=secrets.token_hex(16), character_id=character.id, viewer_discord_id=session.viewer_discord_id,
        mode=session.mode, roll_key=key, formula=dformula, dice=dice, payload=payload, actions=[],
        choices={"base_total": scored["total"], "record": choices.get("record"),
                 "is_owner_roll": choices.get("is_owner_roll"), "parent": session.id},
        history_id=history_id,
    )
    db.add(child)
    db.flush()
    _add_flag(session, "damage", session_id=child.id)
    return {"damage": _answer(child, character)}


REROLLS.update({
    "isawa": _isawa,
    "post_bonus": _post_bonus,
    "courtier_vp": _courtier_vp,
    "hida_reroll": _hida_reroll,
    "damage": _damage,
})
UNDOABLE.update({"akodo_bank": _akodo_bank, "bayushi_raise": _bayushi_raise})



# ---------------------------------------------------------------------------
# Wound checks (Phase 8)
# ---------------------------------------------------------------------------

def _start_wound_check(db, character, formula, choices, viewer, live, void, ow):
    strike = bool(choices.get("strike"))
    if strike and (void or ow or choices.get("kitsune_swap")):
        raise RollRefused("an iaijutsu strike's wound check takes no void and no ring swap")
    lw = int(character.current_light_wounds or 0)
    if not live and choices.get("light_wounds"):
        # A test-drive against a scenario amount (Read-only Roll Mode).
        lw = _count(choices, "light_wounds")
    if lw <= 0:
        raise RollRefused(f"{character.name} has no light wounds to check")
    daidoji = None
    if choices.get("daidoji"):
        daidoji = daidoji_counterattack(character, visible_party_members(db, character, viewer))
        if daidoji is None:
            raise RollRefused("no Daidoji counterattacked this hit")
    built = build_wound_check(character, formula, lw, strike=strike, daidoji=daidoji)
    return built["formula"], built["consumes"]


def _wc_state(session: RollSession) -> Dict[str, Any]:
    f = session.formula or {}
    out = cm.wound_check_result(_session_total(session), int(f.get("light_wounds") or 0),
                                bool(f.get("bayushi_5th_dan_half_lw")))
    out["light_wounds"] = int(f.get("light_wounds") or 0)
    session.choices = dict(session.choices or {}, wc=out)
    return out


def _wc_only(session: RollSession, what: str) -> None:
    if session.roll_key != "wound_check":
        raise RollRefused(f"{what} is only for a wound check")


def _void_raise(session, character, undo, kind, what):
    """A void point after the roll for +5, drawn in the usual order with its
    school consequences; undo returns it to the pool it came from."""
    mine = [i for i, a in enumerate(session.actions or []) if a["kind"] == kind]
    live = session.mode == "live"
    if undo:
        if not mine:
            raise RollRefused(f"no {what} to undo")
        actions = list(session.actions)
        entry = actions.pop(mine[-1])
        session.actions = actions
        if live:
            if entry["source"] == "temp":
                character.current_temp_void_points = (character.current_temp_void_points or 0) + 1
            elif entry["source"] == "regular":
                character.current_void_points = (character.current_void_points or 0) + 1
            else:
                state = dict(character.adventure_state or {})
                state["worldliness_used"] = max(0, int(state.get("worldliness_used") or 0) - 1)
                character.adventure_state = state
        return {}
    try:
        if live:
            plan = plan_void_spend(character, 0, activation_cost=1, roll_label=what)
            apply_void_spend(character, plan)
            a = plan.activation
            source = "temp" if a.from_temp else ("regular" if a.from_regular else "worldliness")
        else:
            f = session.formula or {}
            plan_void_spend(character, 0, activation_cost=int(f.get("void_spent") or 0)
                            + int(f.get("void_activation_cost") or 0) + len(mine) + 1, roll_label=what)
            source = "simulated"
    except VoidSpendRefused as exc:
        raise RollRefused(str(exc)) from None
    session.actions = list(session.actions or []) + [{"kind": kind, "amount": 5, "source": source}]
    return {}


def _wc_vp(db, session, character, args, rng, undo=False):
    """Akodo / Yogo 4th Dan: +5 per void point spent after a wound check."""
    _wc_only(session, "a 4th Dan void raise")
    if not wound_check_flags(character.to_dict())["wc_vp_free_raise"]:
        raise RollRefused(f"{character.name} has no 4th Dan void raise on wound checks")
    return _void_raise(session, character, undo, "wc_vp", "the 4th Dan raise")


def _spend_bank(session, character, args, undo, kind, key, what):
    """Spend (or put back) one amount from a banked list in adventure_state."""
    mine = [i for i, a in enumerate(session.actions or []) if a["kind"] == kind]
    live = session.mode == "live"
    state = dict(character.adventure_state or {})
    bank = list(state.get(key) or [])
    if undo:
        if not mine:
            raise RollRefused(f"no {what} to put back")
        actions = list(session.actions)
        entry = actions.pop(mine[-1])
        session.actions = actions
        if live:
            state[key] = bank + [entry["amount"]]
            character.adventure_state = state
        return {}
    try:
        amount = int(args.get("amount"))
    except (TypeError, ValueError):
        raise RollRefused("amount must be a whole number") from None
    used = 0 if live else sum(1 for i in mine if session.actions[i]["amount"] == amount)
    if bank.count(amount) - used <= 0:
        raise RollRefused(f"no {what} of +{amount} to spend")
    if live:
        bank.remove(amount)
        state[key] = bank
        character.adventure_state = state
    session.actions = list(session.actions or []) + [{"kind": kind, "amount": amount}]
    return {}


def _matsu_bank(db, session, character, args, rng, undo=False):
    """Matsu 3rd Dan: a bonus banked by a void point, spent on a wound check."""
    _wc_only(session, "a Matsu banked bonus")
    return _spend_bank(session, character, args, undo, "matsu_bank", "matsu_banked_wc_bonuses",
                       "Matsu banked bonus")


def _wc_excess(db, session, character, args, rng, undo=False):
    """A banked excess (Isawa 5th Dan wound check, Shinjo 5th Dan parry)."""
    _wc_only(session, "a banked excess")
    return _spend_bank(session, character, args, undo, "wc_excess", "banked_wc_excess",
                       "banked excess")


def _wc_resolve(db, session, character, args, rng):
    """The wound check's outcome, applied: ``fail`` (take the serious
    wounds), or on a pass ``keep`` (keep the light wounds - Isawa 5th Dan and
    Akodo 3rd Dan bank the margin) or ``take_sw`` (1 serious wound, light
    wounds back to 0). A Yogo Warden gains a temp void point per serious
    wound taken."""
    _wc_only(session, "resolving")
    out = _wc_state(session)
    choice = args.get("choice")
    if choice == "fail" and out["passed"]:
        raise RollRefused("a passed wound check is not a failure")
    if choice in ("keep", "take_sw") and not out["passed"]:
        raise RollRefused("a failed wound check takes its serious wounds")
    if choice not in ("fail", "keep", "take_sw"):
        raise RollRefused("choice must be fail, keep or take_sw")
    session.choices = dict(session.choices or {}, resolved=choice)
    if session.mode != "live":
        return {"resolved": choice}
    flags = wound_check_flags(character.to_dict())
    taken = out["serious_wounds"] if choice == "fail" else (1 if choice == "take_sw" else 0)
    if taken:
        set_serious_wounds(character, (character.current_serious_wounds or 0) + taken)
        character.current_light_wounds = 0
        if flags["yogo_temp_vp_on_sw"]:
            character.current_temp_void_points = (character.current_temp_void_points or 0) + taken
    elif out["margin"] > 0:
        state = dict(character.adventure_state or {})
        if flags["isawa_bank_wc_excess"]:
            state["banked_wc_excess"] = list(state.get("banked_wc_excess") or []) + [out["margin"]]
        bonus = akodo_banked_bonus(out["margin"], flags["akodo_attack_skill"])
        if bonus:
            state["akodo_banked_bonuses"] = list(state.get("akodo_banked_bonuses") or []) + [bonus]
        character.adventure_state = state
    return {"resolved": choice}


REROLLS.update({"wc_resolve": _wc_resolve})
UNDOABLE.update({"wc_vp": _wc_vp, "matsu_bank": _matsu_bank, "wc_excess": _wc_excess})



# ---------------------------------------------------------------------------
# The iaijutsu duel and Kakita 5th Dan (Phase 9)
# ---------------------------------------------------------------------------

def _duel_formula(roll_key, formula, choices, void, ow):
    """The contested roll or the strike, with the duel's restart bonus. The
    strike takes no void and never rerolls 10s; its opponent's TN is judged."""
    try:
        bonus = restart_bonus(choices)
    except ValueError as exc:
        raise RollRefused(str(exc)) from None
    if bonus:
        formula["flat"] = (formula.get("flat") or 0) + bonus
        formula["bonuses"] = list(formula.get("bonuses") or []) + [{"label": "duel restart", "amount": bonus}]
    formula["label"] = "Iaijutsu Contested" if roll_key == "iaijutsu:contested" else "Iaijutsu Strike"
    if roll_key == "iaijutsu:strike":
        if void or ow or choices.get("kitsune_swap"):
            raise RollRefused("no void may be spent on the strike")
        try:
            formula["opponent_tn"] = max(0, int(choices.get("opponent_tn") or 0))
        except (TypeError, ValueError):
            raise RollRefused("opponent_tn must be a whole number") from None
        formula.update(reroll_tens=False, no_reroll_reason="iaijutsu_strike")
    return formula


def _duel_state(session: RollSession) -> None:
    """The strike's hit and excess over the opponent's TN (recomputed after
    Conviction and rerolls)."""
    f = session.formula or {}
    if session.roll_key != "iaijutsu:strike":
        session.choices = dict(session.choices or {}, duel={"total": _session_total(session)})
        return
    excess = _session_total(session) - int(f.get("opponent_tn") or 0)
    session.choices = dict(session.choices or {}, duel={"hit": excess >= 0, "excess": excess})


def _child_damage(db, session, character, key, label, rolled, kept, flat, rng, extras):
    """A damage roll chained to its parent, recorded, as a session of its own."""
    data = character.to_dict()
    dformula = {"label": label, "rolled": rolled, "kept": kept, "flat": flat, "reroll_tens": True,
                "is_damage_roll": True, "bonuses": [], "damage_parts": list(extras),
                "void_spent": 0, "void_overflow_bonus": 0}
    dice = roll_dice(rolled, kept, True, rng)["in_order"] if rolled and kept else []
    scored = score_roll(data, dformula, dice, list(extras))
    payload = dict(scored, title=label, formula=_formula_text(dformula))
    history_id = None
    choices = session.choices or {}
    if session.mode == "live" and choices.get("record"):
        row = RollHistory(character_id=character.id, roll_key=key,
                          actor_discord_id=session.viewer_discord_id,
                          is_owner_roll=bool(choices.get("is_owner_roll")),
                          impaired_at_roll=impaired_now(data), payload=payload)
        db.add(row)
        db.flush()
        history_id = row.id
    child = RollSession(
        id=secrets.token_hex(16), character_id=character.id, viewer_discord_id=session.viewer_discord_id,
        mode=session.mode, roll_key=key, formula=dformula, dice=dice, payload=payload, actions=[],
        choices={"base_total": scored["total"], "record": choices.get("record"),
                 "is_owner_roll": choices.get("is_owner_roll"), "parent": session.id},
        history_id=history_id,
    )
    db.add(child)
    db.flush()
    _add_flag(session, "damage", session_id=child.id)
    return {"damage": _answer(child, character)}


def _duel_damage(db, session, character, args, rng):
    """The strike's damage, when it hit: a die per point of excess."""
    if session.roll_key != "iaijutsu:strike":
        raise RollRefused("duel damage is only for a strike")
    _duel_state(session)
    duel = session.choices["duel"]
    if not duel["hit"]:
        raise RollRefused("only a strike that hit rolls damage")
    _once(session, "damage", "the damage roll")
    try:
        weapon = weapon_dice(args)
    except ValueError as exc:
        raise RollRefused(str(exc)) from None
    base = build_all_roll_formulas(character.to_dict()).get("knack:iaijutsu") or {}
    pool = duel_damage_pool(base, weapon, duel["excess"])
    extras = [f"{weapon[0]}k{weapon[1]} weapon", f"+{max(0, duel['excess'])}k0 from the strike's excess"]
    return _child_damage(db, session, character, "iaijutsu:damage", "Iaijutsu Damage",
                         pool["rolled"], pool["kept"], pool["flat"], rng, extras)


def _kakita_5th_damage(db, session, character, args, rng):
    """Kakita 5th Dan's damage: +/- a rolled die per 5 the contest was won or
    lost by. Recorded (settles 5.5)."""
    if session.roll_key != KAKITA_5TH:
        raise RollRefused("this damage is only for the Kakita 5th Dan contest")
    _once(session, "damage", "the damage roll")
    try:
        weapon = weapon_dice(args)
        opponent = int(args.get("opponent_roll") or 0)
    except (TypeError, ValueError):
        raise RollRefused("the opponent's roll and weapon dice must be whole numbers") from None
    pool = kakita_5th_damage_pool(session.formula or {}, weapon, _session_total(session) - opponent)
    extras = [f"{weapon[0]}k{weapon[1]} weapon", f"{pool['adjust']:+d}k0 from the contest"]
    if pool["rolled"] <= 0 or pool["kept"] <= 0:
        pool.update(rolled=0, kept=0)
    return _child_damage(db, session, character, "kakita_5th_dan:damage", "Kakita 5th Dan damage",
                         pool["rolled"], pool["kept"], pool["flat"], rng, extras)


REROLLS.update({"duel_damage": _duel_damage, "kakita_5th_damage": _kakita_5th_damage})
