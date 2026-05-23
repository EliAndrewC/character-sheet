"""Monte Carlo percentile analysis for Shosuro Actor 5th Dan.

Companion to ``shosuro_fifth_dan_bonuses.py``. Where that script reads
the precomputed mean tables, this one runs a fresh simulation to
report what the Shosuro bonus (and the +1k0 deltas) *typically look
like* when the XkY roll lands at the 10th / 50th / 90th percentile
of its distribution.

Three regimes are produced, in the same order as the means script:

  skill_roll  - base = XkY unskilled (no reroll); +1k0 = (X+1)kY
                skilled (with reroll). The two scenarios share
                underlying raw d10 draws so the gain delta is a
                paired (variance-reduced) measurement.
  reroll_on   - both base and +1k0 use reroll-10s.
  reroll_off  - neither uses reroll.

This is NOT the marginal distribution of each metric. It's a
CONDITIONAL view: the "p90" column shows the average bonus on
trials whose XkY roll came out to the 90th-percentile value, not
the 90th-percentile value of the bonus distribution itself. So
for 3k3 (where roll == bonus by construction) the roll columns
and bonus columns are identical - a useful sanity check.

Per-trial structure: each trial samples ``rolled + 1`` dice (one for
the base pool, one extra for the "+1k0" comparison). The five tracked
quantities are computed on each trial:

  avg_roll        - sum of top ``kept`` of the base pool
  shosuro_bonus   - sum of bottom min(3, rolled) of the base pool
  gain_+1k0       - top-kept(full pool) - top-kept(base pool)
  shosuro_change  - bottom-3(full pool) - bottom-3(base pool)
  net_+1k0        - gain + shosuro_change, per-trial

Procedure for each (rolled, kept) cell:
  1. V_p = percentile(roll_distribution, p) for p in {10, 50, 90}
     via ``np.percentile(..., method='nearest')``, returning an
     actual observed integer roll value.
  2. For each metric M (bonus / gain / sh_change / net), report
     ``mean(M | roll == V_p)`` - the average of M over trials
     whose XkY roll came out to V_p.

So the roll columns are integers (observed sample values); the
other columns are conditional means and will typically be
fractional - that's real signal, not rounding noise.

Rolled=10 rows skip the +1k0 columns - the L7R overflow rule
("rolled > 10 -> kept += overflow") prevents an 11th rolled die.

Output (all written next to this script):
  - ``ShosuroFifthDanBonusesByPercentile.csv`` - machine-readable,
    one row per (reroll, rolled, kept) with 15 numeric columns
    (5 metrics x 3 percentiles).
  - ``ShosuroFifthDanBonusesByPercentile.md`` - GitHub-renderable
    Markdown tables with the same data.
  - stdout                                     - same as the .md file.

Run from the repo root:

    PYTHONPATH=. python3 analysis/shosuro_fifth_dan_bonuses_by_percentile.py
"""

import csv
import pathlib

import numpy as np

SEED = 1337
N_TRIALS = 200_000      # matches the existing Shosuro precompute count
ROLLED_CAP = 10         # L7R overflow rule converts rolled past 10 into kept
KEPT_RANGE = range(2, 11)
PERCENTILES = (10, 50, 90)

REGIMES = ("skill_roll", "reroll_on", "reroll_off")
REGIME_TITLES = {
    "skill_roll":  "Unimpaired skill rolls (skill 0 -> 1: unskilled "
                   "base, skilled +1k0)",
    "reroll_on":   "Rerolling 10s (skilled, unimpaired - both base "
                   "and +1k0 use reroll-10s)",
    "reroll_off":  "NOT rerolling 10s (initiative, iaijutsu strike, "
                   "impaired - neither uses reroll-10s)",
}


def regime_rerolls(regime):
    """Return (base_reroll, extra_reroll) for ``regime``."""
    if regime == "skill_roll":
        return False, True
    if regime == "reroll_on":
        return True, True
    if regime == "reroll_off":
        return False, False
    raise ValueError(regime)

HERE = pathlib.Path(__file__).resolve().parent
CSV_PATH = HERE / "ShosuroFifthDanBonusesByPercentile.csv"
MD_PATH = HERE / "ShosuroFifthDanBonusesByPercentile.md"

MD_INTRO = f"""\
# Shosuro Actor 5th Dan: conditional value given the XkY roll percentile

Companion to `ShosuroFifthDan.md`, which shows unconditional means.
This file answers a different question:

> *"When my XkY roll lands at the 10th / 50th / 90th percentile of
> its distribution, what does the Shosuro bonus (and the +1k0
> deltas) typically look like?"*

This is a **conditional** view, not a marginal one. The `bonus p90`
column does NOT mean "the 90th-percentile of the Shosuro bonus
distribution"; it means "the average Shosuro bonus on trials
whose XkY roll equals the 90th-percentile roll value". Conditioning
on the roll lets you see how the bonus varies with how lucky your
underlying roll was.

Three tables follow, one per L7R regime:

- **Unimpaired skill rolls (skill 0 -> 1)** - leading table.
  Base = `XkY` *unskilled* (no reroll-10s). `+1k0` = `(X+1)kY`
  *skilled* (with reroll-10s, because buying the rank turns it
  on). Most game-relevant: this is the table to consult when
  asking "is buying the first rank of this skill worth it?".
- **Rerolling 10s** - both base and `+1k0` use reroll-10s.
  Applies to skill 1 -> 2 -> 3 -> ... transitions, or any
  already-skilled unimpaired roll.
- **NOT rerolling 10s** - neither uses reroll. Initiative,
  iaijutsu strikes, impaired rolls.

For each `(rolled, kept)` dice pool the table below shows:

- **roll p10 / p50 / p90** - actual observed roll values at the
  10th, 50th, 90th percentile of the (base, unskilled-where-
  applicable) XkY distribution (integer).
- **bonus p10 / p50 / p90** - mean Shosuro bonus across trials
  whose base roll equals the corresponding roll percentile value.
- **gain p10 / p50 / p90** - mean of `top-kept(+1k0) - top-kept(base)`
  conditional on the base roll's percentile.
- **sh chg p10 / p50 / p90** - mean change in the Shosuro bonus
  from the `+1k0` transition, conditional on the base roll.
- **net p10 / p50 / p90** - sum of `gain` and `sh chg`, same
  conditioning.

For `3k3` in either regime where the base has no reroll, the roll
columns and the bonus columns are identical because keeping all
3 of 3 dice means the bonus (sum of all 3 lowest) equals the
roll exactly - a sanity check that the conditioning is wired right.

The `rolled = 10` rows have no `+1k0` columns: the L7R overflow
rule (`rolled > 10 -> kept += overflow`) prevents an 11th rolled
die.

For the skill_roll regime the simulation generates each trial's
underlying raw d10 values once and applies reroll-10s only to the
`+1k0` scenario, so the base and `+1k0` share underlying
randomness (paired comparison, lower variance on the delta).

Generated by `analysis/shosuro_fifth_dan_bonuses_by_percentile.py`
with {N_TRIALS:,} trials per cell, seed = {SEED}.
"""


def chain_reroll(rng, dice):
    """Apply L7R reroll-10s in place: any 10 rerolls and the new
    value is added to the running total; rerolled 10s chain. The
    50-iter ceiling is a safety bound; P(50 consecutive 10s on the
    same die) < 10^-50."""
    active = dice == 10
    for _ in range(50):
        if not active.any():
            break
        new = rng.integers(1, 11, size=dice.shape).astype(np.int64)
        dice = dice + np.where(active, new, 0)
        active = active & (new == 10)
    return dice


def simulate_cell(rng, regime, rolled, kept, n_trials):
    """Returns a dict of per-trial int64 arrays for one
    (regime, rolled, kept) cell. ``gain``, ``sh_change``, ``net``
    are absent when rolled == ROLLED_CAP.

    Same underlying raw d10 draws drive both the base and the +1k0
    scenario so the per-trial gain delta is paired (variance-reduced)
    when the two scenarios have different reroll rules. For the
    skill_roll regime the base sees the raw 10s as 10s (no chain),
    while the +1k0 sees the full N+1 dice with chains applied.
    """
    has_extra = rolled < ROLLED_CAP
    n_total = rolled + (1 if has_extra else 0)
    base_reroll, extra_reroll = regime_rerolls(regime)
    raw = rng.integers(1, 11, size=(n_trials, n_total)).astype(np.int64)
    # Compute the base pool: first ``rolled`` raw dice, chained if
    # the regime says so.
    if base_reroll:
        # Chain over the full N+1 raw, then take the first N. This
        # keeps the base's first-N chained values consistent with
        # the full's first-N when the full is also chained.
        full = chain_reroll(rng, raw.copy())
        base = full[:, :rolled]
    else:
        base = raw[:, :rolled]
        # The full pool may still need chains (skill_roll regime);
        # compute it independently of the base.
        full = chain_reroll(rng, raw.copy()) if extra_reroll else raw
    base_desc = -np.sort(-base, axis=1)
    base_asc = np.sort(base, axis=1)
    base_roll = base_desc[:, :kept].sum(axis=1)
    base_shosuro = base_asc[:, :min(3, rolled)].sum(axis=1)
    out = {"avg_roll": base_roll, "shosuro_bonus": base_shosuro}
    if has_extra:
        full_desc = -np.sort(-full, axis=1)
        full_asc = np.sort(full, axis=1)
        full_roll = full_desc[:, :kept].sum(axis=1)
        full_shosuro = full_asc[:, :min(3, rolled + 1)].sum(axis=1)
        out["gain"] = full_roll - base_roll
        out["sh_change"] = full_shosuro - base_shosuro
        out["net"] = out["gain"] + out["sh_change"]
    return out


def roll_percentile_values(base_roll):
    """The observed XkY roll value at the 10th / 50th / 90th
    percentile of the roll distribution. ``method='nearest'``
    guarantees we land on an actual sample value (an integer),
    which we then use to slice trials for the conditional means."""
    return tuple(
        int(v) for v in np.percentile(base_roll, PERCENTILES, method="nearest")
    )


def conditional_means(metric_arr, base_roll, roll_pvals):
    """For each roll percentile value V in ``roll_pvals``, return
    the mean of ``metric_arr`` over trials whose ``base_roll == V``.
    Returns a triple of floats."""
    out = []
    for v in roll_pvals:
        mask = base_roll == v
        # Every V is an actual observed roll value, so at least one
        # trial matches; no guard needed.
        out.append(float(metric_arr[mask].mean()))
    return tuple(out)


def build_rows():
    rng = np.random.default_rng(SEED)
    rows = []
    for regime in REGIMES:
        for kept in KEPT_RANGE:
            for rolled in range(kept, ROLLED_CAP + 1):
                cell = simulate_cell(rng, regime, rolled, kept, N_TRIALS)
                base_roll = cell["avg_roll"]
                roll_pvals = roll_percentile_values(base_roll)
                row = {
                    "regime": regime,
                    "rolled": rolled,
                    "kept": kept,
                    "avg_roll": roll_pvals,
                    "shosuro_bonus": conditional_means(
                        cell["shosuro_bonus"], base_roll, roll_pvals
                    ),
                }
                if "gain" in cell:
                    row["gain"] = conditional_means(
                        cell["gain"], base_roll, roll_pvals
                    )
                    row["sh_change"] = conditional_means(
                        cell["sh_change"], base_roll, roll_pvals
                    )
                    row["net"] = conditional_means(
                        cell["net"], base_roll, roll_pvals
                    )
                else:
                    row["gain"] = row["sh_change"] = row["net"] = (
                        None, None, None,
                    )
                rows.append(row)
    return rows


def write_csv(rows, path):
    def fmt_int(v):
        return "" if v is None else str(v)
    def fmt_float(v):
        return "" if v is None else f"{v:.3f}"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        header = ["regime", "rolled", "kept"]
        for col in ("avg_roll", "shosuro_bonus",
                    "gain_from_plus_1k0",
                    "shosuro_change_per_plus_1_rolled",
                    "net_plus_1k0"):
            for p in PERCENTILES:
                header.append(f"{col}_p{p}")
        w.writerow(header)
        for r in rows:
            row = [r["regime"], r["rolled"], r["kept"]]
            for v in r["avg_roll"]:
                row.append(fmt_int(v))
            for key in ("shosuro_bonus", "gain", "sh_change", "net"):
                for v in r[key]:
                    row.append(fmt_float(v))
            w.writerow(row)


def format_markdown(rows):
    """Return the full Markdown document - intro + both per-reroll
    tables - as a single string. Used for both the file write and
    stdout, so they stay in lockstep.

    The roll columns (avg_roll p10/p50/p90) are integer-valued
    observed sample values; every other column is a conditional
    mean and renders with one decimal place.
    """
    def cell_int(v, signed=False):
        if v is None:
            return "—"
        return f"{v:+d}" if signed else f"{v:d}"
    def cell_float(v, signed=False):
        if v is None:
            return "—"
        return f"{v:+.1f}" if signed else f"{v:.1f}"
    header_cols = ["rolled", "kept"]
    align_cols = ["-------:", "-----:"]
    metric_specs = [
        ("roll", False, False),   # int, unsigned
        ("bonus", True, False),   # float, unsigned
        ("gain", True, True),     # float, signed
        ("sh chg", True, True),
        ("net", True, True),
    ]
    for prefix, _is_float, _signed in metric_specs:
        for p in PERCENTILES:
            header_cols.append(f"{prefix} p{p}")
            align_cols.append("------:")
    out = [MD_INTRO]
    for regime in REGIMES:
        out.append(f"\n## {REGIME_TITLES[regime]}\n")
        out.append("| " + " | ".join(header_cols) + " |")
        out.append("|" + "|".join(align_cols) + "|")
        for r in rows:
            if r["regime"] != regime:
                continue
            row_cells = [str(r["rolled"]), str(r["kept"])]
            for metric_key, (_, is_float, signed) in zip(
                ["avg_roll", "shosuro_bonus", "gain", "sh_change", "net"],
                metric_specs,
            ):
                for v in r[metric_key]:
                    if is_float:
                        row_cells.append(cell_float(v, signed=signed))
                    else:
                        row_cells.append(cell_int(v, signed=signed))
            out.append("| " + " | ".join(row_cells) + " |")
    return "\n".join(out) + "\n"


def write_markdown(rows, path):
    path.write_text(format_markdown(rows))


def main():
    rows = build_rows()
    write_csv(rows, CSV_PATH)
    write_markdown(rows, MD_PATH)
    print(f"wrote {CSV_PATH}")
    print(f"wrote {MD_PATH}")
    print(f"({len(rows)} data rows)")
    print(format_markdown(rows))


if __name__ == "__main__":
    main()
