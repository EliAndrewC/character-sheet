"""Roll statistics: the average of every roll and its distribution, for the
optional statistics modal (``probability-design/design.md``).

Everything here is a lookup into pre-computed tables; nothing is simulated
at request time.

- An ordinary roll is one cell of ``app/data/probabilities.py`` - a survival
  function per (rolled, kept, reroll 10s), so the chance of each total is one
  subtraction - shifted by the formula's flat bonus.
- Three school abilities change the curve's SHAPE, because what they add is
  correlated with the dice (Shosuro Actor 5th Dan, Hida Bushi 3rd Dan,
  Merchant 5th Dan). Their cells come from ``app/data/roll_shapes.json``
  (``scripts/generate_roll_shapes.py``), which also records how much of each
  total the ability contributed, so a bar can say "dice ~38, 5th Dan ~12".

Post-roll flat bonuses (3rd Dan free raises, Conviction, ...) are left out on
purpose - they move the curve without changing its shape - and come back as
one-line ``notes``.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.data import prob
from app.services.attack_rolls import attack_flags
from app.services.dice import is_impaired
from app.services.roll_engine import formula_with_void
from app.services.void_spend import school_dan, void_limits

BIN = 5
# The chart spans the totals between these two tail probabilities; whatever
# lies beyond folds into the first and last bars ("14 or less", "60+").
TAIL = 0.001
SHAPES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "roll_shapes.json")

ABILITY_LABELS = {
    "shosuro": "5th Dan (lowest three dice)",
    "hida": "3rd Dan reroll",
    "merchant": "5th Dan reroll",
}
ABILITY_ASSUMPTIONS = {
    "shosuro": None,
    "hida": ("Assumes you reroll the lowest dice showing 7 or less, up to {n} of them "
             "(the dice the reroll pre-selects)."),
    "merchant": ("Assumes you reroll the dice that most raise your expected total, "
                 "within the 5 x (dice - 1) rule."),
}
KEEP_BETTER_ASSUMPTION = (
    "Rolling twice and keeping the higher total, as Lucky, a PCP reroll or the "
    "Merchant's business reroll allow - if you always used it.")


@lru_cache(maxsize=1)
def _shapes() -> Dict[str, Any]:
    with open(SHAPES_PATH) as f:
        return json.load(f)


def stat_keys(formulas: Dict[str, dict]) -> List[str]:
    """The roll keys that get statistics: everything with a single total.
    Initiative makes action dice, not a total."""
    return [k for k in formulas if not k.startswith("initiative")]


def _ability(character_data: Dict[str, Any], formula: Dict[str, Any]) -> Tuple[Optional[str], int]:
    """``(family, n)`` for the shape-changing ability on this roll, if any."""
    school = character_data.get("school") or ""
    dan = school_dan(character_data)
    if school == "shosuro_actor" and dan >= 5:
        return "shosuro", 0
    if school == "merchant" and dan >= 5:
        return "merchant", 0
    flags = attack_flags(character_data)
    if flags["hida_reroll"] and formula.get("is_attack_type") and formula.get("reroll_tens"):
        n = flags["hida_reroll_x"]
        if formula.get("attack_variant") == "counterattack":
            n *= 2
        if is_impaired(character_data):
            n = -(-n // 2)
        if n > 0:
            return "hida", n
    return None, 0


def dice_distribution(rolled: int, kept: int, reroll: bool,
                      family: Optional[str] = None, n: int = 0):
    """``(start, pmf, ability)`` for the dice-derived total of a roll:
    ``pmf[i]`` is the chance of ``start + i`` and ``ability[i]`` the mean
    part of that total the ability added (all 0 without one)."""
    rolled = max(0, min(10, int(rolled or 0)))
    kept = max(0, min(rolled, int(kept or 0)))
    if rolled == 0 or kept == 0:
        return 0, [1.0], [0.0]
    if family:
        key = f"{rolled},{kept},1,{n}" if family == "hida" else f"{rolled},{kept},{int(reroll)}"
        cell = _shapes()[family][key]
        total = sum(cell["pmf"])
        return (cell["start"], [p / total for p in cell["pmf"]],
                [b / 10 for b in cell["bonus"]])
    table = prob[bool(reroll)]
    survival = []
    x = 0
    while True:
        s = 1.0 if x == 0 else table[rolled, kept, x]
        survival.append(s)
        if x > 0 and s == 0:
            break
        x += 1
    pmf = [survival[i] - survival[i + 1] for i in range(len(survival) - 1)]
    start = next(i for i, p in enumerate(pmf) if p > 0)
    pmf = pmf[start:]
    total = sum(pmf)
    pmf = [p / total for p in pmf]
    return start, pmf, [0.0] * len(pmf)


def keep_better(pmf: List[float]) -> List[float]:
    """The better of two independent rolls: P(max <= x) = P(X <= x)^2. The
    ability's share of a given total does not change - whichever roll was
    kept, it was a roll that came out at that total."""
    out, cdf, prev = [], 0.0, 0.0
    for p in pmf:
        cdf += p
        sq = min(1.0, cdf) ** 2
        out.append(sq - prev)
        prev = sq
    return out


def _quantile(start: int, pmf: List[float], q: float) -> int:
    """The smallest total whose cumulative chance reaches ``q``."""
    acc = 0.0
    for i, p in enumerate(pmf[:-1]):
        acc += p
        if acc >= q - 1e-9:
            return start + i
    return start + len(pmf) - 1


def _view(start: int, pmf: List[float], ability: List[float], flat: int,
          flats: List[dict], ability_label: Optional[str], cap: int) -> Dict[str, Any]:
    """Summary numbers and 5-wide bars for one distribution of totals
    (``start`` and ``pmf`` are dice-derived; ``flat`` is added here)."""
    totals = [start + i + flat for i in range(len(pmf))]
    ability_mean = sum(p * a for p, a in zip(pmf, ability))
    uncapped_mean = sum(p * t for p, t in zip(pmf, totals))
    capped = [min(t, cap) if cap else t for t in totals]
    mean = sum(p * t for p, t in zip(pmf, capped))
    parts = [{"label": "Dice", "value": round(uncapped_mean - flat - ability_mean, 1)}]
    if ability_label:
        parts.append({"label": ability_label, "value": round(ability_mean, 1)})
    parts += [{"label": b["label"], "value": b["amount"]} for b in flats]
    if cap and mean < uncapped_mean - 0.05:
        parts.append({"label": f"Capped at {cap}", "value": round(mean - uncapped_mean, 1)})

    # Fold the totals into bins of 5 aligned on multiples of 5, the tails
    # beyond TAIL into the outermost bars.
    cdf, acc = [], 0.0
    for p in pmf:
        acc += p
        cdf.append(acc)
    lo_total = next(c for c, q in zip(capped, cdf) if q >= TAIL)
    hi_total = next(c for c, q in zip(capped, cdf) if q >= 1 - TAIL)
    first = (lo_total // BIN) * BIN
    last = (hi_total // BIN) * BIN
    bins: Dict[int, List[float]] = {}
    for p, t, a in zip(pmf, capped, ability):
        b = min(max((t // BIN) * BIN, first), last)
        acc_b = bins.setdefault(b, [0.0, 0.0, 0.0])
        acc_b[0] += p
        acc_b[1] += p * a
        acc_b[2] += p * t
    out_bins = []
    at_least = 1.0
    for b in range(first, last + BIN, BIN):
        p, pa, pt = bins.get(b, [0.0, 0.0, 0.0])
        entry = {
            "lo": b, "hi": b + BIN - 1, "p": round(p, 5),
            "at_least": round(max(0.0, at_least), 5),
            "open_low": b == first and lo_total > min(capped),
            "open_high": b == last and max(capped) > b + BIN - 1,
        }
        if p > 0:
            entry["dice"] = round(pt / p - flat - pa / p, 1)
            if ability_label:
                entry["ability"] = round(pa / p, 1)
        out_bins.append(entry)
        at_least -= p

    def q(level: float) -> int:
        t = _quantile(start, pmf, level) + flat
        return min(t, cap) if cap else t

    return {
        "mean": round(mean, 1),
        "median": q(0.5),
        "p10": q(0.1),
        "p90": q(0.9),
        "parts": parts,
        "ability_label": ability_label,
        "bins": out_bins,
    }


def _flats(formula: Dict[str, Any], overflow: int, void: int, combat_vp: int) -> List[dict]:
    rows = [dict(b) for b in formula.get("bonuses") or [] if b.get("amount")]
    if overflow:
        rows.append({"label": "extra dice above 10k10", "amount": overflow})
    if void and combat_vp:
        rows.append({"label": "5th Dan (+10 per void point)", "amount": void * combat_vp})
    return rows


def void_max(character_data: Dict[str, Any], formula: Dict[str, Any]) -> int:
    """How far the modal's void stepper goes: the per-roll cap less any
    activation point; 0 where void cannot be spent on the roll. Hypothetical:
    it ignores how many points the character holds right now."""
    if formula.get("void_blocked") or formula.get("no_reroll_reason") == "iaijutsu_strike":
        return 0
    activation = 1 if formula.get("requires_void_point") else 0
    return max(0, void_limits(character_data)["cap"] - activation)


def level(character_data: Dict[str, Any], formula: Dict[str, Any], void: int,
          better: bool = False) -> Dict[str, Any]:
    """One void level of one roll: the effective dice and its view."""
    family, n = _ability(character_data, formula)
    f, overflow, combat_vp = formula_with_void(character_data, formula, void)
    start, pmf, ability = dice_distribution(
        f.get("rolled") or 0, f.get("kept") or 0, bool(f.get("reroll_tens")), family, n)
    if better:
        pmf = keep_better(pmf)
    view = _view(start, pmf, ability, f.get("flat") or 0,
                 _flats(formula, overflow, void, combat_vp),
                 ABILITY_LABELS.get(family), int(f.get("max_total") or 0))
    view["dice_label"] = f"{f.get('rolled') or 0}k{f.get('kept') or 0}"
    return view


def notes(character_data: Dict[str, Any], formula: Dict[str, Any]) -> List[str]:
    """One line per post-roll bonus available on this roll (P3): not in the
    chart, because each only moves it."""
    out = []
    n = formula.get("adventure_raises_max_per_roll") or 0
    if n:
        out.append(f"3rd Dan free raises after the roll: +5 each, up to {n} on this roll.")
    if formula.get("courtier_5th_dan_optional"):
        out.append(f"Courtier 5th Dan: +{formula['courtier_5th_dan_optional']} when it applies.")
    if formula.get("doji_5th_dan_always") or formula.get("doji_5th_dan_optional"):
        out.append("Doji 5th Dan: +1 for every 5 the TN exceeds 10.")
    for alt in formula.get("alternatives") or []:
        if alt.get("extra_flat"):
            out.append(f"+{alt['extra_flat']} {alt.get('label', '')}".rstrip() + ".")
    knacks = dict(character_data.get("foreign_knacks") or {})
    knacks.update(character_data.get("knacks") or {})
    if knacks.get("conviction"):
        out.append(f"Conviction: up to +{knacks['conviction']} after the roll.")
    return out


def assumptions(character_data: Dict[str, Any], formula: Dict[str, Any]) -> List[str]:
    family, n = _ability(character_data, formula)
    out = []
    text = ABILITY_ASSUMPTIONS.get(family) if family else None
    if text:
        out.append(text.format(n=n))
    school = character_data.get("school") or ""
    if school == "merchant":
        out.append("You spend void after seeing the roll; the chart shows each point as if spent before it.")
    if formula.get("wave_man_freed_dice") and not formula.get("reroll_tens"):
        out.append("Wave Man's freed 10s are not counted: the chart rolls no 10s again.")
    return out


def roll_stats(character_data: Dict[str, Any], formulas: Dict[str, dict], key: str) -> Optional[Dict[str, Any]]:
    """Every void level of one roll, with and without keeping the better of
    two rolls. ``None`` for a key the character has no statistics for."""
    formula = formulas.get(key)
    if not formula or key not in stat_keys(formulas):
        return None
    top = void_max(character_data, formula)
    return {
        "key": key,
        "label": formula.get("label") or key,
        "void_max": top,
        "levels": [
            {"void": v,
             "normal": level(character_data, formula, v),
             "better": level(character_data, formula, v, better=True)}
            for v in range(top + 1)
        ],
        "notes": notes(character_data, formula),
        "assumptions": assumptions(character_data, formula),
        "keep_better_text": KEEP_BETTER_ASSUMPTION,
    }


def averages(character_data: Dict[str, Any], formulas: Dict[str, dict]) -> Dict[str, Dict[str, Any]]:
    """``{key: {"label", "mean"}}`` with no void spent: the sheet's badges."""
    return {
        key: {"label": formulas[key].get("label") or key,
              "mean": level(character_data, formulas[key], 0)["mean"]}
        for key in stat_keys(formulas)
    }
