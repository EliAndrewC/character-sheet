#!/usr/bin/env python3
"""Audit production characters for likely orphaned ring auto-raises.

An "orphan auto-raise" is a non-school ring whose value matches the
school-ring auto-baseline (3 below Dan 4, 4 at Dan 4 or higher) AND
where the character is currently over their XP budget. The
combination is a strong signal that a past school-ring switch left
the old ring at its previous auto-raised value without paying for it.

The audit does not modify anything; it just prints a report. False
positives are likely (a player legitimately paid XP to raise a non-
school ring to 3 or 4 - and that's fine, the XP totals would still
balance). The over-budget check filters most of those out.

Usage on the Fly machine::

    fly ssh console -C "python3 /app/scripts/audit_orphan_rings.py"

Or locally against the dev database::

    python3 scripts/audit_orphan_rings.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``app`` importable from either the dev tree (parent of this
# file is the repo root) or the Fly machine (where the package lives
# under /app).
_repo_root = Path(__file__).resolve().parent.parent
for _candidate in (str(_repo_root), "/app", "/workspace"):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from app.database import SessionLocal
from app.models import Character
from app.services.rolls import compute_dan
from app.services.xp import calculate_total_xp, validate_character


def _xp_overspent(char: Character) -> int | None:
    data = char.to_dict()
    totals = calculate_total_xp(data)
    spent = totals.get("total", 0)
    available = (char.starting_xp or 0) + (char.earned_xp or 0)
    over = spent - available
    return over if over > 0 else None


def _orphan_candidates(char: Character) -> list[str]:
    """Names of non-school rings whose value matches the school-ring
    auto-baseline at the character's current Dan. Excludes the actual
    school ring."""
    sr = (char.school_ring_choice or "").strip()
    dan = compute_dan(char.knacks or {}) if char.knacks else 0
    auto_baseline = 4 if dan >= 4 else 3
    flagged: list[str] = []
    rings = {
        "Air": char.ring_air, "Fire": char.ring_fire,
        "Earth": char.ring_earth, "Water": char.ring_water,
        "Void": char.ring_void,
    }
    for ring_name, val in rings.items():
        if ring_name == sr:
            continue
        # Any non-school ring exactly at the school baseline is a
        # candidate. A ring well above (e.g. 5 at Dan 4) was almost
        # certainly paid for and is not flagged.
        if val == auto_baseline:
            flagged.append(f"{ring_name}={val}")
    return flagged


def main() -> int:
    s = SessionLocal()
    chars = s.query(Character).order_by(Character.id).all()
    print(f"Auditing {len(chars)} characters for orphan auto-raises...\n")

    high_confidence: list[Character] = []
    low_confidence: list[Character] = []
    for c in chars:
        candidates = _orphan_candidates(c)
        if not candidates:
            continue
        over = _xp_overspent(c)
        # Validation errors that mention rings are also a tell.
        ring_errors = [
            e for e in validate_character(c.to_dict())
            if "Ring" in e and ("exceeds" in e or "below" in e)
        ]
        bucket = high_confidence if (over or ring_errors) else low_confidence
        bucket.append((c, candidates, over, ring_errors))

    print(f"High-confidence orphans ({len(high_confidence)}):")
    print("  (non-school ring at school auto-baseline AND character is")
    print("  over XP budget or has a ring-validation error)\n")
    for c, candidates, over, errs in high_confidence:
        msg = f"  id={c.id:>4}  {c.name:30}  school={c.school:25}"
        msg += f" sr={(c.school_ring_choice or '-'):8}"
        msg += f"  rings_flagged={candidates}"
        if over:
            msg += f"  overspent={over}xp"
        if errs:
            msg += f"  ring_errors={errs}"
        print(msg)

    if not high_confidence:
        print("  (none)")

    print(f"\nLow-confidence (possible) orphans ({len(low_confidence)}):")
    print("  (non-school ring at school auto-baseline, XP balances -")
    print("  likely a legitimate paid raise, but worth a glance)\n")
    for c, candidates, over, errs in low_confidence:
        print(f"  id={c.id:>4}  {c.name:30}  "
              f"sr={(c.school_ring_choice or '-'):8}  rings_flagged={candidates}")

    if not low_confidence:
        print("  (none)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
