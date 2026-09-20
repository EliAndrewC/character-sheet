"""Server-side execution of a roll: dice, kept set, and result payload.

The character sheet rolls in the browser (``app/static/js/dice.js`` +
``app/static/js/roll_math.js``); this module is the Python mirror of that
same arithmetic, needed because a Discord slash command has no browser to
roll in. It deliberately reuses ``build_all_roll_formulas`` for everything
that decides HOW MANY dice to roll and what bonuses apply - the formula
layer stays the single source of truth for L7R's rules, and this module
only turns a formula into dice and then into the payload shape that
``app/services/dice_card.py`` and ``RollHistory.payload`` already expect.

What IS duplicated here is the small display layer the browser keeps in
``roll_math.js``: the total cap, the "alternative totals" filtering, the
10k10 dice cap, and the initiative arithmetic (which dice are kept, and what
a school then does to them).
Those are a handful of ``min()`` calls with no rules content, and Python
cannot call the JS. Keep the two in step if either changes; the shared
contract is asserted by ``tests/test_roll_engine.py`` against the same
cases as ``tests/js/roll_math.test.js``.

Nothing here is Discord-specific - it takes a character dict and a roll
key and gives back a payload.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence

from app.services.dice import build_all_roll_formulas, is_impaired
from app.services.void_spend import school_dan


#: Guard against a pathological formula (or a crafted character row)
#: asking for an unbounded number of dice. The rules cap a pool at 10k10
#: via ``_finalize_caps``; this is defense in depth for the loop below.
MAX_DICE = 100

#: Ceiling on how many times a single die may explode. A d10 chain has a
#: 1-in-10 continuation chance, so 20 links is astronomically unlikely and
#: exists only so a broken RNG cannot hang the request.
MAX_CHAIN = 20


# ---------------------------------------------------------------------------
# Dice
# ---------------------------------------------------------------------------


def roll_one_die(reroll_tens: bool, rng: random.Random) -> Dict[str, Any]:
    """Roll one d10, exploding on 10 when ``reroll_tens``.

    Mirrors ``rollOneDie`` in ``app/static/js/dice.js``. Returns the
    dice-card cell shape - ``{"parts": [10, 7], "value": 17}`` - where
    ``parts`` is the chain in roll order and ``value`` is its sum.
    """
    parts = [rng.randint(1, 10)]
    if reroll_tens:
        while parts[-1] == 10 and len(parts) < MAX_CHAIN:
            parts.append(rng.randint(1, 10))
    return {"parts": parts, "value": sum(parts)}


def roll_dice(
    rolled: int, kept: int, reroll_tens: bool,
    rng: Optional[random.Random] = None,
    freed_tens: int = 0,
) -> Dict[str, Any]:
    """Roll ``rolled`` dice and keep the highest ``kept``.

    Mirrors the sheet's roll path: dice are sorted ascending by value and
    the tail is kept, so ties fall to whichever die sorted later - the
    kept SUM is unaffected either way. Returns
    ``{"kept": [cell...], "dropped": [cell...], "kept_sum": int}`` with
    the kept dice in the same ascending order the card renders them in.
    """
    rng = rng or random.SystemRandom()
    count = max(0, min(int(rolled), MAX_DICE))
    dice = [roll_one_die(reroll_tens, rng) for _ in range(count)]
    # Wave Man W5: "You may reroll 10s on a single die when impaired", one
    # die per copy. The die is selected automatically, so there is no
    # interactive choice for a slash command to skip - and this has to run
    # BEFORE the sort, since exploding a 10 can change which dice are kept.
    # Mirrors L7RRollMath.waveManExplodeTens, which takes the first
    # ``freed_tens`` dice showing a 10 in roll order.
    if freed_tens and not reroll_tens:
        budget = int(freed_tens)
        for die in dice:
            if budget <= 0:
                break
            if die["value"] != 10:
                continue
            budget -= 1
            while die["parts"][-1] == 10 and len(die["parts"]) < MAX_CHAIN:
                die["parts"].append(rng.randint(1, 10))
            die["value"] = sum(die["parts"])
    dice.sort(key=lambda d: d["value"])
    keep_count = max(0, min(int(kept), len(dice)))
    split = len(dice) - keep_count
    kept_dice = dice[split:]
    return {
        "kept": kept_dice,
        "dropped": dice[:split],
        "kept_sum": sum(d["value"] for d in kept_dice),
    }


# ---------------------------------------------------------------------------
# Display helpers - the Python mirror of roll_math.js
# ---------------------------------------------------------------------------


def apply_total_cap(total: int, max_total: Any) -> int:
    """Clamp a displayed total to a ceiling. 0 / None means uncapped.

    Withdrawn's "open etiquette and open sincerity rolls are never
    considered to be higher than 15" is the motivating case.
    """
    if not isinstance(max_total, int) or isinstance(max_total, bool):
        return total
    if max_total <= 0:
        return total
    return min(total, max_total)


def alt_cap(alt: Dict[str, Any], formula_max_total: Any) -> int:
    """The ceiling binding one alternative row.

    A row may carry its own (Withdrawn caps the OPEN roll while the
    formula's base contested roll is uncapped); otherwise it inherits the
    formula's, since a conditional bonus on a capped roll is still that
    capped roll. Returns 0 when uncapped.
    """
    own = (alt or {}).get("max_total")
    if isinstance(own, int) and not isinstance(own, bool):
        return own
    if isinstance(formula_max_total, int) and not isinstance(formula_max_total, bool):
        return formula_max_total
    return 0


def alt_total(base_total: int, alt: Dict[str, Any], formula_max_total: Any) -> int:
    """One alternative row's displayed value: base + delta, capped.

    A non-numeric delta counts as 0 rather than raising - the JS reads it
    through ``|| 0``, and a malformed row should drop out of the listing
    (which ``_alternatives_for_payload`` then does) instead of failing the
    whole roll.
    """
    extra = (alt or {}).get("extra_flat")
    if not isinstance(extra, int) or isinstance(extra, bool):
        extra = 0
    return apply_total_cap(base_total + extra, alt_cap(alt, formula_max_total))


def visible_alternatives(
    base_total: int, alts: Sequence[dict], formula_max_total: Any,
) -> List[dict]:
    """The alternative rows worth rendering.

    A row whose capped value equals the roll's own displayed total conveys
    nothing (a cap can swallow the conditional bonus entirely), so it is
    dropped - same rule the on-screen modal applies.
    """
    displayed = apply_total_cap(base_total, formula_max_total)
    return [
        a for a in (alts or [])
        if a and alt_total(base_total, a, formula_max_total) != displayed
    ]


def _alternatives_for_payload(
    formula: Dict[str, Any], base_total: int,
) -> List[Dict[str, Any]]:
    """Port of ``_alternativesForPayload`` in the sheet's Alpine layer.

    Keeps rows that carry a label and an integer delta; drops a zero-delta
    row UNLESS it carries a cap, because for those the cap is the entire
    point of the row.
    """
    out: List[Dict[str, Any]] = []
    max_total = formula.get("max_total")
    for a in visible_alternatives(base_total, formula.get("alternatives") or [], max_total):
        label = str(a.get("label") or "").strip()
        extra = a.get("extra_flat")
        if not label or not isinstance(extra, int) or isinstance(extra, bool):
            continue
        cap = alt_cap(a, max_total)
        capped = cap > 0
        if extra == 0 and not capped:
            continue
        row: Dict[str, Any] = {"label": label, "extra_flat": extra}
        if capped:
            row["max_total"] = cap
            source = a.get("max_total_source") or formula.get("max_total_source")
            if source:
                row["max_total_source"] = source
        out.append(row)
    return out


def _formula_text(formula: Dict[str, Any]) -> str:
    """The card's subtitle, e.g. ``"3k2 + 5 (etiquette skill: 1)"``.

    Mirrors the sheet exactly, including its convention of showing the
    flat bonus only when positive, so a card produced here is
    indistinguishable from one copied off the sheet. The skill-rank
    parenthetical is appended for basic / advanced skill rolls (the only
    formulas the server tags with ``skill_name``); it disambiguates a
    pool that a 1st Dan extra die has inflated.
    """
    rolled = formula.get("rolled") or 0
    kept = formula.get("kept") or 0
    flat = formula.get("flat") or 0
    text = f"{rolled}k{kept}" + (f" + {flat}" if flat > 0 else "")
    if formula.get("skill_name"):
        text += f" ({formula['skill_name']} skill: {formula.get('skill_rank') or 0})"
    return text


def _no_reroll_note(formula: Dict[str, Any], cells: List[Dict[str, Any]]) -> str:
    """The "10s not rerolled because ..." line for the card, or "".

    Mirrors ``_noRerollNote`` in the sheet's Alpine layer, wording included,
    so a card produced by a slash command reads identically to one copied off
    the sheet. Only worth saying when a 10 is actually sitting in the pool: a
    10 that DID reroll is a chain of two or more parts, so a single-part cell
    of 10 is precisely "a 10 that stayed a 10".
    """
    if formula.get("reroll_tens") or not formula.get("no_reroll_reason"):
        return ""
    if not any(c["parts"] == [10] for c in cells):
        return ""
    reason = formula["no_reroll_reason"]
    if reason == "iaijutsu_strike":
        return "10s not rerolled for the strike in an iaijutsu duel"
    if reason == "impaired":
        return "10s not rerolled due to being Impaired"
    if reason == "unskilled":
        name = formula.get("unskilled_skill_name") or "that skill"
        return f"10s not rerolled due to {name} being 0"
    return ""


def _bonuses_for_payload(formula: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The formula's labeled flat-bonus breakdown, zero rows dropped."""
    return [
        {"label": b["label"], "amount": b["amount"]}
        for b in (formula.get("bonuses") or [])
        if isinstance(b, dict) and b.get("amount") and b.get("label")
    ]


def apply_dice_cap(rolled: int, kept: int, flat: int) -> Dict[str, int]:
    """The 10k10 ceiling. Mirror of ``L7RRollMath.applyDiceCap``: rolled dice
    past 10 become kept dice, kept dice past 10 become +2 each."""
    overflow_flat = 0
    if rolled > 10:
        kept += rolled - 10
        rolled = 10
    if kept > 10:
        overflow_flat = 2 * (kept - 10)
        flat += overflow_flat
        kept = 10
    return {"rolled": rolled, "kept": kept, "flat": flat, "overflow_flat": overflow_flat}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def _spend_bullets(
    label: str, activation: int, void_spent: int, overflow: int,
) -> List[str]:
    """The DETAILS bullets a void spend earns, worded exactly as the sheet's
    ``_extraBonusBullets`` words them, so the card and the Roll History row
    read the same wherever the roll was made."""
    out: List[str] = []
    if activation > 0:
        out.append(f"{_plural(activation, 'void point')} spent to activate {label}")
    if void_spent > 0:
        out.append(
            f"Rolled +{void_spent}k{void_spent} from {void_spent} spent "
            f"void point{'s' if void_spent > 1 else ''}"
        )
    if overflow > 0:
        out.append(
            f"+{overflow} from rolling above 10k10 (+2 per extra die above 10)"
        )
    return out


def _adds_lowest_three(character_data: Dict[str, Any]) -> bool:
    """Shosuro Actor 5th Dan: the lowest 3 dice are added to the result."""
    return (
        character_data.get("school") == "shosuro_actor"
        and school_dan(character_data) >= 5
    )


# ---------------------------------------------------------------------------
# The whole roll
# ---------------------------------------------------------------------------


def execute_roll(
    character_data: Dict[str, Any],
    roll_key: str,
    party_members: Optional[List[dict]] = None,
    rng: Optional[random.Random] = None,
    void_spent: int = 0,
    formula: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Roll ``roll_key`` for a character and build the result payload.

    Returns the payload dict that ``dice_card.render_png`` renders and
    that is stored verbatim as ``RollHistory.payload`` - the same shape
    the browser posts - or ``None`` when the character has no such roll
    (an unknown key, or a knack they do not have).

    ``void_spent`` is the pre-roll +1k1-per-point spend. This function only
    ROLLS it - checking that the character can afford it and deducting the
    points is ``app/services/void_spend.py``'s job, and the caller does both
    in one transaction. ``formula`` lets a caller that already built the
    character's formula (to read its activation cost) pass it in rather than
    build the whole table twice.

    No Lucky reroll and no post-roll discretionary bonuses: those are
    choices made after seeing the dice, the player marks them on the sheet
    afterwards, and a slash command has nobody to ask.
    Everything the formula layer applies automatically - school
    techniques, advantages, Impaired suppressing the 10s reroll - is
    already baked into the formula and therefore into this roll.

    The Wave Man's W5 ("reroll 10s on a single die when impaired") reads
    like one of those interactive choices, but the freed die is selected
    automatically - every 10 is interchangeable at reroll time - so there
    is nothing to ask about, and it IS applied here. Skipping it would
    make the same roll come out differently depending on whether it was
    made on the sheet or through a slash command.
    """
    if formula is None:
        formula = build_all_roll_formulas(
            character_data, party_members=party_members,
        ).get(roll_key)
    if not formula:
        return None

    # A void point is +1k1. Same order as the sheet's executeRoll: add the
    # dice, then apply the 10k10 ceiling (whose overflow becomes flat).
    formula = dict(formula)
    void_spent = max(0, int(void_spent or 0))
    activation = 1 if formula.get("requires_void_point") else 0
    overflow = 0
    if void_spent:
        capped = apply_dice_cap(
            (formula.get("rolled") or 0) + void_spent,
            (formula.get("kept") or 0) + void_spent,
            formula.get("flat") or 0,
        )
        formula.update(
            rolled=capped["rolled"], kept=capped["kept"], flat=capped["flat"],
        )
        overflow = capped["overflow_flat"]

    dice = roll_dice(
        formula.get("rolled") or 0,
        formula.get("kept") or 0,
        bool(formula.get("reroll_tens")),
        rng,
        freed_tens=formula.get("wave_man_freed_dice") or 0,
    )
    # The payload's ``total`` is the CAPPED figure (matching the sheet's
    # ``cappedTotal()``), but the alternative rows are measured against the
    # UNCAPPED base - that is how the modal decides which rows still say
    # something once a ceiling is in play.
    base_total = dice["kept_sum"] + (formula.get("flat") or 0)

    label = formula.get("label") or roll_key
    extras = _spend_bullets(label, activation, void_spent, overflow)
    all_cells = dice["kept"] + dice["dropped"]
    if _adds_lowest_three(character_data):
        lowest = sum(sorted(c["value"] for c in all_cells)[:3])
        if lowest > 0:
            base_total += lowest
            extras.append(f"+{lowest} from 5th Dan (lowest 3 dice added to result)")
    # A roll whose 10s did not explode has to say so on the card.
    note = _no_reroll_note(formula, all_cells)
    if note:
        extras.append(note)
    max_total = formula.get("max_total")
    total = apply_total_cap(base_total, max_total)
    if total != base_total:
        source = formula.get("max_total_source") or "a disadvantage"
        extras.append(f"Capped at {max_total} by {source} (rolled {base_total})")

    payload: Dict[str, Any] = {
        "title": label,
        "formula": _formula_text(formula),
        "kept": [{"parts": d["parts"]} for d in dice["kept"]],
        "dropped": [{"parts": d["parts"]} for d in dice["dropped"]],
        "bonuses": _bonuses_for_payload(formula),
        "extras": extras,
        "kept_sum": dice["kept_sum"],
        "total": total,
        "alternatives": _alternatives_for_payload(formula, base_total),
    }
    return payload


# ---------------------------------------------------------------------------
# Initiative
# ---------------------------------------------------------------------------


def initiative_sort_value(value: int, kakita_phase_zero: bool) -> int:
    """Mirror of ``L7RRollMath.initiativeSortValue``: a Kakita's 10 is Phase
    0, so it sorts FIRST when choosing the lowest dice to keep."""
    return 0 if (kakita_phase_zero and value == 10) else value


def initiative_action_values(
    kept_values: Sequence[int], flags: Dict[str, Any],
) -> List[int]:
    """Kept initiative dice -> the phases the character acts in, ascending.

    Mirror of ``L7RRollMath.initiativeActionValues``; both run
    ``tests/shared/initiative_cases.json``. The order is part of the rule:
    Hiruma 4th Dan lowers every die by 2 (min 1), THEN Shinjo 4th Dan sets
    the highest to 1, THEN a Kakita 10 becomes Phase 0.
    """
    actions = sorted(kept_values or [])
    if flags.get("hiruma_4th_dan"):
        actions = [max(1, v - 2) for v in actions]
    if flags.get("shinjo_4th_dan") and actions:
        actions[-1] = 1
    if flags.get("kakita_phase_zero"):
        actions = [0 if v == 10 else v for v in actions]
    return sorted(actions)


def execute_initiative(
    character_data: Dict[str, Any],
    rng: Optional[random.Random] = None,
    party_members: Optional[List[dict]] = None,
) -> Optional[Dict[str, Any]]:
    """Roll initiative. Returns ``{"payload", "action_dice"}``.

    ``payload`` is the dice-card / ``RollHistory`` shape the sheet builds in
    ``_buildInitiativeImagePayload`` (KEPT row = the final action dice,
    ``show_total: false``); ``action_dice`` is what to hand
    ``tracking.start_combat_round``.

    Always the default variant - for a Togashi Ise Zumi that is the normal
    roll plus one separate athletics-only die, not the all-athletics
    ``initiative:athletics`` roll. A slash command has nobody to ask.
    """
    rng = rng or random.SystemRandom()
    formula = build_all_roll_formulas(
        character_data, party_members=party_members,
    ).get("initiative")
    if not formula:  # pragma: no cover - every character has an initiative formula
        return None

    kakita = bool(formula.get("kakita_phase_zero"))
    count = max(0, min(int(formula.get("rolled") or 0), MAX_DICE))
    # Initiative never rerolls 10s (rules/03-combat.md).
    cells = [roll_one_die(False, rng) for _ in range(count)]
    # Stable sort, so ties fall to roll order exactly as the sheet's
    # ``a.idx - b.idx`` tiebreak has them.
    cells.sort(key=lambda c: initiative_sort_value(c["value"], kakita))
    keep = max(0, min(int(formula.get("kept") or 0), len(cells)))
    kept, dropped = cells[:keep], cells[keep:]
    dropped.sort(key=lambda c: c["value"])

    action_dice: List[Dict[str, Any]] = [
        {"value": value}
        for value in initiative_action_values([c["value"] for c in kept], formula)
    ]
    if formula.get("togashi_athletics_extra_die"):
        action_dice.append({
            "value": roll_one_die(False, rng)["value"], "athletics_only": True,
        })
    if formula.get("mantis_4th_dan_athletics_die"):
        # Never rolled - always 1.
        action_dice.append(
            {"value": 1, "athletics_only": True, "mantis_4th_dan": True}
        )

    payload = {
        "title": formula.get("label") or "Initiative",
        "formula": _formula_text(formula),
        "kept": [{"parts": [d["value"]]} for d in action_dice],
        "dropped": [{"parts": c["parts"]} for c in dropped],
        "bonuses": [],
        "total": 0,
        "footer": "Action dice",
        "show_total": False,
    }
    return {"payload": payload, "action_dice": action_dice}


def impaired_now(character_data: Dict[str, Any]) -> bool:
    """Whether the character is Impaired, for ``RollHistory.impaired_at_roll``."""
    return bool(is_impaired(character_data))
