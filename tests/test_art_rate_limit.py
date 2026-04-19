"""Tests for the in-memory art-generation rate limit + kill-switch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import art_rate_limit


@pytest.fixture(autouse=True)
def _reset():
    art_rate_limit.reset_all()
    yield
    art_rate_limit.reset_all()


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


class TestArtGenEnabled:
    def test_default_is_disabled(self, monkeypatch):
        monkeypatch.delenv("ART_GEN_ENABLED", raising=False)
        assert art_rate_limit.art_gen_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on"])
    def test_truthy_values_enable(self, monkeypatch, val):
        monkeypatch.setenv("ART_GEN_ENABLED", val)
        assert art_rate_limit.art_gen_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_disable(self, monkeypatch, val):
        monkeypatch.setenv("ART_GEN_ENABLED", val)
        assert art_rate_limit.art_gen_enabled() is False


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_default_limit_is_25(self, monkeypatch):
        monkeypatch.delenv("ART_GEN_RATE_LIMIT_PER_DAY", raising=False)
        assert art_rate_limit.rate_limit_per_day() == 25

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_RATE_LIMIT_PER_DAY", "5")
        assert art_rate_limit.rate_limit_per_day() == 5

    def test_user_under_limit_returns_none(self):
        art_rate_limit.record_generation("u1")
        art_rate_limit.record_generation("u1")
        assert art_rate_limit.check_rate_limit("u1") is None

    def test_different_users_have_independent_buckets(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_RATE_LIMIT_PER_DAY", "2")
        art_rate_limit.record_generation("u1")
        art_rate_limit.record_generation("u1")
        # u1 is at the limit; u2 is not
        assert art_rate_limit.check_rate_limit("u1") is not None
        assert art_rate_limit.check_rate_limit("u2") is None

    def test_user_at_limit_returns_error_string(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_RATE_LIMIT_PER_DAY", "3")
        for _ in range(3):
            art_rate_limit.record_generation("u1")
        err = art_rate_limit.check_rate_limit("u1")
        assert err is not None
        assert "3" in err and "limit" in err.lower()

    def test_default_twenty_sixth_call_blocked(self, monkeypatch):
        """Per the plan: 25 generations allowed; 26th is blocked."""
        monkeypatch.delenv("ART_GEN_RATE_LIMIT_PER_DAY", raising=False)
        for _ in range(25):
            art_rate_limit.record_generation("u1")
        assert art_rate_limit.check_rate_limit("u1") is not None

    def test_expired_stamps_are_pruned(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=25)    # outside the 24h window
        recent = now - timedelta(hours=1)
        # Manually seed the counter with a stale entry + a fresh one
        with art_rate_limit._lock:
            art_rate_limit._counts["u1"] = [old, recent]
        assert art_rate_limit.count_recent("u1", now=now) == 1

    def test_record_generation_does_not_check_limit(self, monkeypatch):
        """``record_generation`` is the after-success stamp; it always records
        regardless of whether the user is technically over the limit. The
        caller gates on ``check_rate_limit`` BEFORE launching the work."""
        monkeypatch.setenv("ART_GEN_RATE_LIMIT_PER_DAY", "1")
        art_rate_limit.record_generation("u1")
        art_rate_limit.record_generation("u1")
        assert art_rate_limit.count_recent("u1") == 2


class TestPruningDuringReads:
    def test_count_recent_returns_zero_when_only_stale(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=25)
        with art_rate_limit._lock:
            art_rate_limit._counts["u1"] = [old]
        assert art_rate_limit.count_recent("u1", now=now) == 0

    def test_count_recent_zero_for_unknown_user(self):
        assert art_rate_limit.count_recent("never-seen") == 0
