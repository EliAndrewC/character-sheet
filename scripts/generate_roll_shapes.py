"""Generate ``app/data/roll_shapes.json``: the distributions of the three
school abilities that change the SHAPE of a roll, not just its position.

The roll-statistics modal (``probability-design/design.md``) draws an
ordinary roll from ``app/data/probabilities.py`` alone - that table is a
survival function per (rolled, kept, reroll 10s) cell, so the chance of
every total is one subtraction away. Three abilities break that, because
what they add is correlated with the dice:

- **Shosuro Actor 5th Dan** adds the lowest three dice (every
  non-initiative roll).
- **Hida Bushi 3rd Dan** rerolls up to N of the dice of an attack roll.
  The table follows the sheet's own pre-selection (``_dice_js.html``): the
  lowest dice showing 7 or less, at most N of them; each chosen die is
  REPLACED by a fresh die that explodes (``roll_sessions._hida_reroll``).
- **Merchant 5th Dan** rerolls any dice summing to at least 5 * (count - 1)
  (every non-initiative roll), replacing them, with the roll's own 10s rule
  (``roll_sessions._merchant_5th``). Which dice a player picks is a choice,
  so the table assumes a stated policy - ``merchant_choice`` below - that
  picks the dice that most raise the expected sum of all the dice.

For each cell the file holds the distribution of the roll's dice-derived
total (the flat bonuses are added by ``app/services/roll_stats.py``) and,
for each total, the average part of it the ability contributed. Monte
Carlo, fixed seed, so a rerun is byte-stable:

    python3 scripts/generate_roll_shapes.py            # a few minutes on 4 workers

Format: ``{"meta": {...}, "<family>": {"<r>,<k>,<reroll 0|1>[,<n>]":
{"start": t0, "pmf": [...], "bonus": [...]}}}`` where ``pmf[i]`` is the
chance (parts per million) of the total ``t0 + i`` and ``bonus[i]`` is the
mean ability part of that total, in tenths. Tails rarer than 1 ppm are
trimmed.
"""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np

TRIALS = 200_000
SEED = 20261017
MAX_CHAIN = 20  # app.services.roll_engine.MAX_CHAIN
HIDA_THRESHOLD = 7  # the sheet pre-selects dice showing 7 or less
# Hida's N is the attack skill X (1..5), 2X on a counterattack, halved
# (rounded up) when Impaired: {ceil(X/2), X, 2X}.
HIDA_COUNTS = sorted({c for x in range(1, 6) for c in (-(-x // 2), x, 2 * x)})
OUT = os.path.join(os.path.dirname(__file__), "..", "app", "data", "roll_shapes.json")


def cells():
    return [(r, k) for r in range(1, 11) for k in range(1, r + 1)]


def roll(rng, shape, reroll_tens):
    """Exploding d10s (``roll_engine.roll_one_die``), as an int array."""
    dice = rng.integers(1, 11, size=shape)
    if not reroll_tens:
        return dice
    total = dice.copy()
    live = dice == 10
    for _ in range(MAX_CHAIN - 1):
        if not live.any():
            break
        nxt = rng.integers(1, 11, size=shape)
        total = np.where(live, total + nxt, total)
        live = live & (nxt == 10)
    return total


def kept_sum(dice, k):
    return np.sort(dice, axis=1)[:, -k:].sum(axis=1)


def pack(totals, bonus):
    """Distribution of ``totals`` and the mean ``bonus`` at each total."""
    totals = totals.astype(np.int64)
    lo, hi = int(totals.min()), int(totals.max())
    idx = totals - lo
    counts = np.bincount(idx, minlength=hi - lo + 1)
    sums = np.bincount(idx, weights=bonus.astype(np.float64), minlength=hi - lo + 1)
    pmf = np.rint(counts * 1_000_000 / len(totals)).astype(int)
    means = np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)
    nz = np.nonzero(pmf)[0]
    a, b = int(nz[0]), int(nz[-1]) + 1
    return {
        "start": lo + a,
        "pmf": pmf[a:b].tolist(),
        "bonus": np.rint(means[a:b] * 10).astype(int).tolist(),
    }


def shosuro(args):
    r, k, rr = args
    rng = np.random.default_rng([SEED, 1, r, k, rr])
    dice = roll(rng, (TRIALS, r), rr)
    base = kept_sum(dice, k)
    bonus = np.sort(dice, axis=1)[:, :3].sum(axis=1)
    return f"{r},{k},{rr}", pack(base + bonus, bonus)


def hida(args):
    r, k, rr, n = args
    rng = np.random.default_rng([SEED, 2, r, k, rr, n])
    dice = np.sort(roll(rng, (TRIALS, r), rr), axis=1)
    base = dice[:, -k:].sum(axis=1)
    pos = np.arange(r)[None, :]
    chosen = (pos < n) & (dice <= HIDA_THRESHOLD)
    fresh = roll(rng, (TRIALS, r), True)  # the rerolled dice always explode
    after = kept_sum(np.where(chosen, fresh, dice), k)
    return f"{r},{k},{rr},{n}", pack(after, after - base)


@lru_cache(maxsize=None)
def merchant_choice(values: tuple, mean_die: float) -> tuple:
    """Which sorted positions to reroll, for sorted die ``values``.

    Policy: among the subsets the rule allows (the chosen dice sum to at
    least 5 * (count - 1)), take the one with the largest expected gain
    sum(mean_die - v). For each size s, start from the s lowest dice and,
    while they sum too low, trade the highest chosen die for the lowest
    unchosen die above it - the smallest step up in sum. Nothing is
    rerolled when no subset gains."""
    best, best_gain = (), 0.0
    n = len(values)
    for s in range(1, n + 1):
        chosen = list(range(s))
        while sum(values[i] for i in chosen) < 5 * (s - 1):
            # Raise the sum: move the highest chosen die that can move
            # to the next free position above it.
            moved = False
            for j in range(s - 1, -1, -1):
                nxt = chosen[j] + 1
                if nxt < n and (j == s - 1 or nxt < chosen[j + 1]):
                    chosen[j] = nxt
                    moved = True
                    break
            if not moved:
                break
        if sum(values[i] for i in chosen) < 5 * (s - 1):
            continue
        gain = sum(mean_die - values[i] for i in chosen)
        if gain > best_gain + 1e-9:
            best, best_gain = tuple(chosen), gain
    return best


def merchant(args):
    r, k, rr = args
    rng = np.random.default_rng([SEED, 3, r, k, rr])
    dice = np.sort(roll(rng, (TRIALS, r), rr), axis=1)
    base = dice[:, -k:].sum(axis=1)
    mean_die = 5.5 * 10 / 9 if rr else 5.5
    # Dice above 11 behave like 11 for the choice (never worth rerolling
    # except as padding, where 11 is already ample), so collapse them to
    # memoize the policy over far fewer distinct rows. Every die is a
    # candidate, dropped ones included: a low dropped die rerolled often
    # lands among the kept (restricting the choice to the kept dice cut a
    # 5k3's average gain from +4.4 to +1.9).
    clipped = np.minimum(dice, 11)
    uniq, inverse = np.unique(clipped, axis=0, return_inverse=True)
    masks = np.zeros(uniq.shape, dtype=bool)
    for row, vals in enumerate(uniq):
        for i in merchant_choice(tuple(int(v) for v in vals), mean_die):
            masks[row, i] = True
    chosen = masks[inverse.reshape(-1)]
    fresh = roll(rng, (TRIALS, r), rr)
    after = kept_sum(np.where(chosen, fresh, dice), k)
    return f"{r},{k},{rr}", pack(after, after - base)


def main():
    jobs = {
        "shosuro": (shosuro, [(r, k, rr) for r, k in cells() for rr in (1, 0)]),
        # A Hida attack always rerolls its 10s (3rd Dan restores them while
        # Impaired), so only the reroll cells are needed.
        "hida": (hida, [(r, k, 1, n) for r, k in cells() for n in HIDA_COUNTS]),
        "merchant": (merchant, [(r, k, rr) for r, k in cells() for rr in (1, 0)]),
    }
    out = {"meta": {
        "trials": TRIALS, "seed": SEED, "hida_threshold": HIDA_THRESHOLD,
        "hida_counts": HIDA_COUNTS,
        "generator": "scripts/generate_roll_shapes.py",
    }}
    # Four workers: the dev containers share a memory cap, and one worker
    # per core (~100 MB each) once tripped it.
    with Pool(4) as pool:
        for family, (fn, args) in jobs.items():
            out[family] = dict(sorted(pool.map(fn, args)))
            print(f"{family}: {len(args)} cells", file=sys.stderr)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print(f"wrote {os.path.relpath(OUT)} ({os.path.getsize(OUT) // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
