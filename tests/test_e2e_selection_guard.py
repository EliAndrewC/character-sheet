"""Unit tests for the clicktest large-selection guardrail.

The pytest hook itself lives in ``tests/e2e/conftest.py``; the decision it
makes lives in ``tests/e2e/selection_guard.py`` precisely so it can be tested
here, without running pytest inside pytest.
"""

import pytest

from tests.e2e import selection_guard as guard


def test_a_targeted_selection_passes_without_a_reason():
    assert guard.check_selection(10, 1379, reason="", limit=100) is None


def test_a_selection_exactly_at_the_limit_passes():
    assert guard.check_selection(100, 1379, reason="", limit=100) is None


def test_an_oversized_selection_is_refused():
    msg = guard.check_selection(782, 1379, reason="", limit=100)
    assert msg is not None
    assert "782" in msg
    assert "over the limit of 100" in msg
    assert "no reason given" in msg


def test_the_refusal_describes_the_slice_and_the_cost():
    """The numbers are the argument, so they have to be in the message."""
    msg = guard.check_selection(938, 1379, reason="", limit=100)
    assert "68% of the 1379 collected" in msg
    assert "~56 minutes" in msg  # 938 * 3.6s


def test_the_refusal_says_how_to_narrow_and_how_to_proceed():
    msg = guard.check_selection(782, 1379, reason="", limit=100)
    assert "-k" in msg
    assert "--collect-only" in msg  # how to measure a mark first
    assert guard.REASON_ENV in msg
    assert guard.MAX_TESTS_ENV in msg


def test_an_oversized_selection_with_a_real_reason_proceeds():
    reason = "Reworked base.html, so every page's chrome needs a pass."
    assert guard.check_selection(782, 1379, reason=reason, limit=100) is None


def test_a_too_short_reason_is_refused_and_says_so():
    msg = guard.check_selection(782, 1379, reason="why not", limit=100)
    assert msg is not None
    assert "7 characters" in msg
    assert str(guard.MIN_REASON_CHARS) in msg


def test_a_whitespace_only_reason_does_not_count():
    msg = guard.check_selection(782, 1379, reason="       ", limit=100)
    assert "no reason given" in msg


def test_total_collected_of_zero_omits_the_percentage():
    """Defensive: never divide by zero just to phrase a message."""
    msg = guard.check_selection(782, 0, reason="", limit=100)
    assert msg is not None
    assert "% of the" not in msg


# ---------------------------------------------------------------------------
# reason_problem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reason", [None, "", "   ", "\n"])
def test_reason_problem_for_an_empty_reason(reason):
    assert guard.reason_problem(reason) == "no reason given"


def test_reason_problem_for_a_long_enough_reason():
    assert guard.reason_problem("x" * guard.MIN_REASON_CHARS) is None


def test_reason_problem_measures_the_stripped_reason():
    padded = "  " + "x" * (guard.MIN_REASON_CHARS - 1) + "  "
    assert guard.reason_problem(padded) is not None


# ---------------------------------------------------------------------------
# The configurable limit
# ---------------------------------------------------------------------------


def test_limit_defaults_when_unset():
    assert guard.max_tests({}) == guard.DEFAULT_MAX_TESTS


def test_limit_reads_the_env_var():
    assert guard.max_tests({guard.MAX_TESTS_ENV: " 25 "}) == 25


@pytest.mark.parametrize("raw", ["", "lots", "0", "-5", "3.5"])
def test_a_malformed_or_useless_limit_falls_back(raw):
    """A typo in the env var must not silently disable the guardrail."""
    assert guard.max_tests({guard.MAX_TESTS_ENV: raw}) == guard.DEFAULT_MAX_TESTS


def test_check_selection_reads_the_env_limit_when_none_is_passed(monkeypatch):
    monkeypatch.setenv(guard.MAX_TESTS_ENV, "5")
    assert guard.check_selection(4, 10, reason="") is None
    assert guard.check_selection(6, 10, reason="") is not None


# ---------------------------------------------------------------------------
# Runtime estimate + the acknowledgement banner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("selected,expected", [
    (1, "1 minute"), (10, "1 minute"), (135, "8 minutes"),
    (782, "47 minutes"), (1379, "83 minutes"),
])
def test_estimated_runtime(selected, expected):
    """Calibrated against real runs: 782 tests actually took 47m02s."""
    assert guard.estimated_runtime(selected) == expected


def test_acknowledgement_puts_the_reason_on_record():
    banner = guard.acknowledgement(500, "  Reworked the sheet chrome.  ", 100)
    assert "500 tests (limit 100)" in banner
    assert "Reason given: Reworked the sheet chrome." in banner
