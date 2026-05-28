# analysis/ - L7R probability & balance studies

This directory holds **standalone probability/balance analyses** for L7R rules
work. They are design and advisory artifacts: nothing here is imported by the
app at runtime, and an analysis may cover rules that are not yet (or never)
implemented in the character sheet. The point is to answer "is this bonus too
big?", "how lethal is this?", "is this distance realistic?" with numbers before
any code touches `app/`.

## The shape of an analysis entry

Each analysis is **one reproducible Python script** plus the **two output files
it generates**:

| artifact | name style | purpose |
|---|---|---|
| the script | `snake_case.py` | reads canonical inputs, computes, writes the outputs |
| the data | `PascalCase.csv` | machine-readable, fixed precision, one row per case, a key column identifying the row |
| the writeup | `PascalCase.md` | GitHub-renderable: an intro (model, assumptions, columns) followed by formatted tables and prose analysis |

The script also prints the Markdown to **stdout**, byte-identical to the `.md`
file, so a run is self-documenting. Existing entries to copy the style from:
`shosuro_fifth_dan_bonuses.py` -> `ShosuroFifthDan.{csv,md}` and the
`...ByPercentile` companion.

## Conventions

- **Run from the repo root** so the `app` package imports resolve:
  `PYTHONPATH=. python3 analysis/<script>.py`. Put that line in the docstring.
- **Be deterministic.** Prefer the precomputed Monte-Carlo tables over live RNG
  so a rerun is byte-stable and reviewable in a diff. If you must roll live, set
  a fixed seed and say so.
- **Use the canonical data sources** (see below) rather than re-deriving dice
  math, so every analysis agrees with the app and with each other.
- **Document assumptions and limitations** in the `.md` intro. If a table cannot
  capture something (an edge case, a rule still under discussion), say so in the
  prose rather than silently approximating.
- **CSV**: fixed decimals (4 is the house default), empty string for N/A, a
  leading column or two that uniquely key the row.
- **Markdown**: an intro explaining every column and the model, then one section
  per table. Use `—` for N/A. Right-align numeric columns.
- **House style**: hyphens, never em-dashes or en-dashes (matches the app).

## Canonical data sources (in `app/data/`, see `app/data/__init__.py`)

```python
from app.data import prob, wound_table

prob[reroll][(rolled, kept)]              # mean of an XkY roll (reroll True/False)
prob[reroll][(rolled, kept, threshold)]   # P(XkY roll >= threshold)
wound_table[(light_wounds, rolled, kept)] # expected serious wounds from a wound
                                          # check of (rolled)k(kept) vs that many
                                          # light wounds (standard reroll-on check)
```

Both are `defaultdict`, so a missing key returns `0` / `0.0` - guard the tails
(very high thresholds, light wounds past the table's ceiling) yourself. The L7R
10k10 cap (rolled past 10 convert to kept, kept past 10 to +2 flat each) must be
applied before looking a pool up, since the tables only hold `rolled <= 10`.

For rules constants (TN formulas, weapon dice, wound thresholds, school knacks)
read `app/game_data.py` (`COMBAT_REFERENCE`, `COMBAT_SKILLS`, etc.). For roll
arithmetic semantics, `app/static/js/roll_math.js` is the authority.
