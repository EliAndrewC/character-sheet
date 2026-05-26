# School feature docs - what these are (and aren't)

One file per school. They capture the **design and rules intent** of each school's
abilities - the things that are *not* derivable from the code or the tests:

- the rules text for each ability (Special + 1st-5th Dan),
- implementation **status** and the **rationale** behind it - especially *why*
  something is out of scope, partially implemented, or deferred,
- deliberate **scope decisions** and rules interpretations,
- **open questions** about ambiguous rules.

They were invaluable during the initial school-by-school build-out and remain the
home for that intent.

## What they are NOT

These are **not** a coverage tracker or an implementation index, and they should
not be kept "in sync" as one - that duplicates the source of truth and rots.

- **"What's implemented, where?"** -> the code is the truth. `grep` for the school
  id (`school_id == "..."`), look at `SCHOOL_TECHNIQUE_BONUSES` in
  `app/game_data.py`, and the formula builders in `app/services/dice.py`.
- **"What's tested?"** -> the test suite is the truth. The tests are named after
  the school (`grep -rn kuni_witch_hunter tests/`), and `pytest --cov` shows line
  coverage. e2e coverage lives in `tests/e2e/COVERAGE.md`.

File/function references here are **pointers, not pins**: name the file and (where
helpful) the function, never a line number. Line numbers and per-ability test
lists were removed in 2026-05 because they had drifted badly and were actively
misleading (claiming tests that didn't assert what they said, and pointing at
line numbers ~700 lines stale). If you add detail, keep it to intent and
rationale; let the code and tests speak for implementation and coverage.
