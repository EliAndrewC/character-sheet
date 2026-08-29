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
``roll_math.js``: the total cap and the "alternative totals" filtering.
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


# ---------------------------------------------------------------------------
# The whole roll
# ---------------------------------------------------------------------------


def execute_roll(
    character_data: Dict[str, Any],
    roll_key: str,
    party_members: Optional[List[dict]] = None,
    rng: Optional[random.Random] = None,
) -> Optional[Dict[str, Any]]:
    """Roll ``roll_key`` for a character and build the result payload.

    Returns the payload dict that ``dice_card.render_png`` renders and
    that is stored verbatim as ``RollHistory.payload`` - the same shape
    the browser posts - or ``None`` when the character has no such roll
    (an unknown key, or a knack they do not have).

    Only the unconditional roll is performed: no void spends, no Lucky
    reroll, no post-roll discretionary bonuses. Those are interactive
    choices that belong to the modal, and a slash command has nobody to
    ask. Everything the formula layer applies automatically - school
    techniques, advantages, Impaired suppressing the 10s reroll - is
    already baked into the formula and therefore into this roll.
    """
    formulas = build_all_roll_formulas(character_data, party_members=party_members)
    formula = formulas.get(roll_key)
    if not formula:
        return None

    dice = roll_dice(
        formula.get("rolled") or 0,
        formula.get("kept") or 0,
        bool(formula.get("reroll_tens")),
        rng,
    )
    # The payload's ``total`` is the CAPPED figure (matching the sheet's
    # ``cappedTotal()``), but the alternative rows are measured against the
    # UNCAPPED base - that is how the modal decides which rows still say
    # something once a ceiling is in play.
    base_total = dice["kept_sum"] + (formula.get("flat") or 0)

    # The card's DETAILS block. A slash-command roll has no interactive
    # spends to report, but it can still be a roll whose 10s did not
    # explode, and the card has to say so.
    note = _no_reroll_note(formula, dice["kept"] + dice["dropped"])

    return {
        "title": formula.get("label") or roll_key,
        "formula": _formula_text(formula),
        "kept": [{"parts": d["parts"]} for d in dice["kept"]],
        "dropped": [{"parts": d["parts"]} for d in dice["dropped"]],
        "bonuses": _bonuses_for_payload(formula),
        "extras": [note] if note else [],
        "kept_sum": dice["kept_sum"],
        "total": apply_total_cap(base_total, formula.get("max_total")),
        "alternatives": _alternatives_for_payload(formula, base_total),
    }


def impaired_now(character_data: Dict[str, Any]) -> bool:
    """Whether the character is Impaired, for ``RollHistory.impaired_at_roll``."""
    return bool(is_impaired(character_data))
