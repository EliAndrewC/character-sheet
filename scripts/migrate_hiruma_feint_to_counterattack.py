#!/usr/bin/env python3
"""Rewrite a Hiruma Scout's ``feint`` school knack to ``counterattack``.

The Hiruma Scout school was changed (commit 3c657a5) to grant the
``counterattack`` knack instead of ``feint``. Characters built before
that change still carry ``feint`` in their stored build. This script
rewrites a SINGLE character and its full revision history in place so
it reads as if the character always had ``counterattack`` and never
had ``feint``:

  * ``characters.knacks``                ``{feint: N}``  -> ``{counterattack: N}``
  * ``characters.published_state.knacks``  same
  * ``character_versions.state.knacks``     same, for every version row
  * ``character_versions.summary``          literal "Feint" -> "Counterattack"

The rank at every point is preserved, so a feint 1 -> 2 -> 3 progression
across versions becomes a counterattack 1 -> 2 -> 3 progression. The
detailed per-version diff shown in the History drill-down is recomputed
from the (now-rewritten) ``state`` snapshots at read time, so fixing the
snapshots fixes it too; only the stored one-line ``summary`` needs a
text rewrite.

Deliberately NOT touched:
  * ``foreign_knacks`` - a ``feint`` there was bought from another
    school and is unrelated to the Hiruma school-knack change.
  * ``roll_history`` - a gameplay log of dice actually rolled; a past
    feint roll used feint mechanics and relabelling it would misrepresent
    what happened. (Surfaced in the report so a human can decide.)

Safety:
  * Dry-run by default. Pass ``--apply`` to commit.
  * Refuses to run unless the character's school is ``hiruma_scout``
    (other schools - Shosuro Courtier, Doji Artisan, Mirumoto Niten -
    legitimately still use ``feint``). Override with ``--force`` only if
    you really know what you're doing.
  * Skips (with a warning) any record that somehow holds BOTH ``feint``
    and ``counterattack`` so a human can reconcile it by hand.
  * Idempotent: re-running after a successful apply reports "nothing
    to do".

Usage on the Fly machine::

    # Dry run (prints what WOULD change, commits nothing):
    fly ssh console -C "python3 /app/scripts/migrate_hiruma_feint_to_counterattack.py --character-id 10"

    # Apply for real:
    fly ssh console -C "python3 /app/scripts/migrate_hiruma_feint_to_counterattack.py --character-id 10 --apply"

Or locally against the dev database (DATABASE_URL)::

    python3 scripts/migrate_hiruma_feint_to_counterattack.py --character-id 10 [--apply]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make ``app`` importable from either the dev tree (parent of this file
# is the repo root) or the Fly machine (where the package lives under
# /app).
_repo_root = Path(__file__).resolve().parent.parent
for _candidate in (str(_repo_root), "/app", "/character-sheet"):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

OLD_KNACK = "feint"
NEW_KNACK = "counterattack"
OLD_NAME = "Feint"
NEW_NAME = "Counterattack"
EXPECTED_SCHOOL = "hiruma_scout"


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested) - take plain data, return rewritten data plus a
# human-readable note, and never mutate their inputs in place.
# ---------------------------------------------------------------------------


def rename_in_knacks(
    knacks: Optional[Dict[str, int]],
    old: str = OLD_KNACK,
    new: str = NEW_KNACK,
) -> Tuple[Optional[Dict[str, int]], str]:
    """Return ``(new_knacks, note)``.

    ``new_knacks`` is ``None`` when nothing changed (the caller should
    leave the column untouched). Key order is preserved, swapping the
    ``old`` key for ``new`` in place so the dict reads naturally. Returns
    ``None`` + a warning note if both keys are present (ambiguous; left
    for a human)."""
    if not knacks or old not in knacks:
        return None, ""
    if new in knacks:
        return None, (
            f"SKIPPED: holds both '{old}' (rank {knacks[old]}) and "
            f"'{new}' (rank {knacks[new]}) - reconcile by hand"
        )
    rank = knacks[old]
    rebuilt: Dict[str, int] = {}
    for k, v in knacks.items():
        if k == old:
            rebuilt[new] = v
        else:
            rebuilt[k] = v
    return rebuilt, f"knack '{old}' (rank {rank}) -> '{new}' (rank {rank})"


def rename_in_state(
    state: Optional[Dict[str, Any]],
    old: str = OLD_KNACK,
    new: str = NEW_KNACK,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Rewrite ``state['knacks']`` within a snapshot dict (a version's
    ``state`` or a character's ``published_state``). Returns
    ``(new_state, note)`` with ``new_state`` ``None`` when unchanged. A
    shallow copy of ``state`` with a fresh ``knacks`` dict is returned so
    reassigning the column reliably marks it dirty for SQLAlchemy."""
    if not state:
        return None, ""
    new_knacks, note = rename_in_knacks(state.get("knacks"), old, new)
    if new_knacks is None:
        return None, note
    rebuilt = dict(state)
    rebuilt["knacks"] = new_knacks
    return rebuilt, note


def rename_in_summary(
    summary: Optional[str],
    old_name: str = OLD_NAME,
    new_name: str = NEW_NAME,
) -> Tuple[Optional[str], str]:
    """Replace the whole-word knack display name in an auto-generated
    summary string (e.g. "Feint changed from 1 to 2"). Returns
    ``(new_summary, note)`` with ``new_summary`` ``None`` when unchanged.
    Both the capitalized display form and a bare lowercase form are
    handled, preserving case."""
    if not summary:
        return None, ""
    rewritten = re.sub(rf"\b{re.escape(old_name)}\b", new_name, summary)
    rewritten = re.sub(
        rf"\b{re.escape(old_name.lower())}\b", new_name.lower(), rewritten
    )
    if rewritten == summary:
        return None, ""
    return rewritten, f"summary: {summary!r} -> {rewritten!r}"


# ---------------------------------------------------------------------------
# DB driver
# ---------------------------------------------------------------------------


def migrate_character(
    db,
    character_id: int,
    apply: bool = False,
    force: bool = False,
    old_knack: str = OLD_KNACK,
    new_knack: str = NEW_KNACK,
    old_name: str = OLD_NAME,
    new_name: str = NEW_NAME,
) -> List[str]:
    """Run the rewrite for one character. Returns a list of report
    lines. Commits only when ``apply`` is True; otherwise the session is
    rolled back so a dry run leaves the DB untouched.

    Defaults to feint -> counterattack (the original use), but the
    old/new knack id + display name are parameterised so the same logic
    serves later Hiruma knack renames (e.g. counterattack -> lunge)."""
    from app.models import Character, CharacterVersion

    report: List[str] = []
    char = db.query(Character).filter(Character.id == character_id).first()
    if char is None:
        report.append(f"ERROR: no character with id={character_id}")
        return report

    report.append(
        f"Character id={char.id} name={char.name!r} school={char.school!r}"
    )
    if char.school != EXPECTED_SCHOOL and not force:
        report.append(
            f"ABORT: school is {char.school!r}, expected {EXPECTED_SCHOOL!r}. "
            f"Other schools legitimately use '{old_knack}'. Re-run with "
            f"--force only if you are certain."
        )
        return report

    changed = False

    # 1) Live knacks column.
    new_knacks, note = rename_in_knacks(char.knacks, old_knack, new_knack)
    if note.startswith("SKIPPED"):
        report.append(f"  knacks: {note}")
    elif new_knacks is not None:
        report.append(f"  knacks: {note}")
        char.knacks = new_knacks
        changed = True

    # 2) published_state snapshot on the character row.
    new_pub, note = rename_in_state(char.published_state, old_knack, new_knack)
    if note.startswith("SKIPPED"):
        report.append(f"  published_state: {note}")
    elif new_pub is not None:
        report.append(f"  published_state: {note}")
        char.published_state = new_pub
        changed = True

    # 3) Every version row: state snapshot + stored summary text.
    versions = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.character_id == character_id)
        .order_by(CharacterVersion.version_number)
        .all()
    )
    for v in versions:
        new_state, note = rename_in_state(v.state, old_knack, new_knack)
        if note.startswith("SKIPPED"):
            report.append(f"  v{v.version_number} state: {note}")
        elif new_state is not None:
            report.append(f"  v{v.version_number} state: {note}")
            v.state = new_state
            changed = True
        new_summary, snote = rename_in_summary(v.summary, old_name, new_name)
        if new_summary is not None:
            report.append(f"  v{v.version_number} {snote}")
            v.summary = new_summary
            changed = True

    # 4) Surface (but do not touch) gameplay roll-history references so a
    #    human can decide whether to clean those up separately.
    from app.models import RollHistory

    roll_hits = (
        db.query(RollHistory)
        .filter(
            RollHistory.character_id == character_id,
            RollHistory.roll_key == f"knack:{old_knack}",
        )
        .count()
    )
    if roll_hits:
        report.append(
            f"  NOTE: {roll_hits} roll_history row(s) with "
            f"roll_key='knack:{old_knack}' left untouched (gameplay log; "
            f"not part of the character build/revision history)."
        )

    if not changed:
        report.append(
            f"  nothing to do (no '{old_knack}' found in build/history)."
        )
        db.rollback()
        return report

    if apply:
        db.commit()
        report.append("  APPLIED and committed.")
    else:
        db.rollback()
        report.append("  DRY RUN - no changes committed. Re-run with --apply.")
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--character-id", type=int, default=10,
        help="Character id to migrate (default: 10).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Commit the changes. Without this it is a dry run.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Bypass the hiruma_scout school guard. Use with care.",
    )
    parser.add_argument(
        "--old-knack", default=OLD_KNACK,
        help=f"Knack id to rename FROM (default: {OLD_KNACK}).",
    )
    parser.add_argument(
        "--new-knack", default=NEW_KNACK,
        help=f"Knack id to rename TO (default: {NEW_KNACK}).",
    )
    parser.add_argument(
        "--old-name", default=None,
        help="Display name to rewrite in version summaries (default: "
             "the title-cased --old-knack).",
    )
    parser.add_argument(
        "--new-name", default=None,
        help="Replacement display name in summaries (default: the "
             "title-cased --new-knack).",
    )
    args = parser.parse_args(argv)
    old_name = args.old_name or args.old_knack.replace("_", " ").title()
    new_name = args.new_name or args.new_knack.replace("_", " ").title()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        report = migrate_character(
            db, args.character_id, apply=args.apply, force=args.force,
            old_knack=args.old_knack, new_knack=args.new_knack,
            old_name=old_name, new_name=new_name,
        )
    finally:
        db.close()

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
