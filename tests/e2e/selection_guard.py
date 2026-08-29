"""Guardrail: refuse to run a large clicktest selection without a reason.

The clicktests exist to be run in a TARGETED way. A focused selection is
seconds to a couple of minutes; the full suite is ~46 minutes, and the big
marks are not far off it (``rolls`` alone is 57% of the suite). Running a big
slice is almost always a mistake - it costs a lot of wall clock and tells you
nothing the targeted selection would not have.

Documentation did not prevent this: CLAUDE.md said "run only the relevant
mark(s)", which sounds targeted, and following it literally produced a
938-test / 57-minute "targeted" run - longer than the entire suite. So the
limit lives in the tooling instead, where it cannot be misread.

Over the threshold, the run fails immediately - before the server or browser
starts - unless the caller supplies a REASON, which has to be long enough to
be a real sentence. The point of the reason is not access control (anyone can
type one); it is the pause it forces, and the fact that it lands in the
transcript where it can be argued with.

The logic lives here, apart from the pytest hook, so it can be unit-tested
without running pytest inside pytest - see ``tests/test_e2e_selection_guard.py``.
"""

from __future__ import annotations

import os
from typing import Optional


#: Maximum tests a run may select without giving a reason. An ABSOLUTE count
#: rather than a percentage of the suite, deliberately:
#:
#: * The cost being guarded is wall clock, and wall clock tracks the count
#:   (~3.6s per test), not the fraction. A percentage would silently raise the
#:   ceiling in minutes every time the suite grew.
#: * A percentage misfires on small files: ``pytest tests/e2e/test_keepalive.py``
#:   selects 10 of the 10 tests it collected - 100% - and is a perfectly good
#:   targeted run.
#:
#: 100 lets every mark through except ``school_abilities`` (135) and ``rolls``
#: (782), and blocks every OR-ed combination of marks. Override with
#: ``E2E_MAX_TESTS``.
DEFAULT_MAX_TESTS = 100

#: A reason has to be long enough to be a sentence. Short enough not to be
#: obnoxious, long enough that "x" or "test" will not do.
MIN_REASON_CHARS = 30

#: Measured across this suite: 938 tests / 3410s, 779 / 2822, 135 / 508.
SECONDS_PER_TEST = 3.6

MAX_TESTS_ENV = "E2E_MAX_TESTS"
REASON_ENV = "E2E_REASON"


def max_tests(environ=None) -> int:
    """The configured ceiling. A malformed value falls back to the default."""
    raw = (environ if environ is not None else os.environ).get(MAX_TESTS_ENV, "")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_TESTS
    return value if value > 0 else DEFAULT_MAX_TESTS


def reason_problem(reason: Optional[str]) -> Optional[str]:
    """Why this reason is not acceptable, or None if it is.

    Only length is checked. A determined caller can always satisfy it; the
    friction is the feature, not the filter.
    """
    text = (reason or "").strip()
    if not text:
        return "no reason given"
    if len(text) < MIN_REASON_CHARS:
        return (
            f"the reason is {len(text)} characters; at least "
            f"{MIN_REASON_CHARS} are needed - say what this run covers that a "
            "targeted selection would not"
        )
    return None


def estimated_minutes(selected: int) -> int:
    return max(1, round(selected * SECONDS_PER_TEST / 60))


def estimated_runtime(selected: int) -> str:
    minutes = estimated_minutes(selected)
    return f"{minutes} minute" + ("" if minutes == 1 else "s")


def check_selection(
    selected: int,
    total_collected: int,
    reason: Optional[str] = None,
    limit: Optional[int] = None,
) -> Optional[str]:
    """The message to fail with, or None to let the run proceed.

    ``selected`` is how many tests survived ``-m`` / ``-k``;
    ``total_collected`` is how many were collected before deselection, used
    only to describe the slice.
    """
    limit = max_tests() if limit is None else limit
    if selected <= limit:
        return None

    problem = reason_problem(reason)
    if problem is None:
        return None

    share = (
        f" ({selected * 100 // total_collected}% of the {total_collected} collected)"
        if total_collected else ""
    )
    return (
        f"\nThis run selected {selected} clicktests{share}, over the limit of "
        f"{limit}. Estimated runtime: ~{estimated_runtime(selected)}.\n"
        f"\nStopped before starting the server, because {problem}.\n"
        "\nThis is usually a mistake. The clicktests are built to be run in a\n"
        "targeted way - a good gate is a handful of tests and under two\n"
        "minutes. Running a big slice rarely surfaces anything the targeted\n"
        "selection would not have, and a few OR-ed marks can easily cost more\n"
        "wall clock than the entire suite while still skipping a third of it.\n"
        "\nPrefer naming the tests that cover your change:\n"
        "    pytest tests/e2e/test_rolls.py -k \"impaired or exported_card\" --browser chromium\n"
        "Check what a mark actually costs first (fast, no browser):\n"
        "    pytest tests/e2e/ --collect-only -q -m <mark>\n"
        "\nIf you really do need this many, say why - it goes in the log where\n"
        f"someone can disagree with it - via the {REASON_ENV} environment\n"
        "variable or --e2e-reason:\n"
        f"    E2E_REASON=\"...\" pytest tests/e2e/ ...\n"
        f"\nSee CLAUDE.md, \"E2E clicktests\". The limit itself is {MAX_TESTS_ENV}.\n"
    )


def acknowledgement(selected: int, reason: str, limit: int) -> str:
    """Banner echoed when a large run is allowed, so the reason is on record."""
    return (
        f"\n{'=' * 70}\n"
        f"LARGE CLICKTEST RUN: {selected} tests (limit {limit}), "
        f"~{estimated_runtime(selected)} estimated.\n"
        f"Reason given: {reason.strip()}\n"
        f"{'=' * 70}\n"
    )
