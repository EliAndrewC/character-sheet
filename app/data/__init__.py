"""Probability lookup tables for L7R dice rolls and wound checks.

Downloaded from EliAndrewC/claude-assisted-l7r-combat-simulator. These are
Monte Carlo simulation results stored as Python dicts.

Usage:
    from app.data import prob, wound_table

    # Probability of 4k3 rolling at least 20 (rerolling 10s)
    prob[True][4, 3, 20]  # -> float 0.0-1.0

    # Probability of 4k3 rolling at least 20 (no reroll)
    prob[False][4, 3, 20]

    # Expected serious wounds from 25 light on 4k3
    wound_table[25, 4, 3]  # -> float

Missing keys return 0 (probabilities) or 0.0 (wound table).
"""

from collections import defaultdict

from app.data.probabilities import prob
from app.data.wound_table import wound_table

for reroll in [True, False]:
    d = defaultdict(int)
    d.update(prob[reroll])
    prob[reroll] = d

wound_table = defaultdict(float, wound_table)
