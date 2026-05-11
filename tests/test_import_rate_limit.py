"""Unit tests for app/services/import_rate_limit.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.models import Character
from app.services import import_rate_limit as rl
from app.services.import_reconcile import IMPORT_NOTES_LABEL


USER_ID = "183026066498125825"


def _add_char_with_import_notes(db, **overrides) -> Character:
    sections = overrides.pop("sections", [
        {"label": IMPORT_NOTES_LABEL,
         "html": "<p>Imported via the pipeline.</p>"},
    ])
    defaults = dict(
        name="Imported", owner_discord_id=USER_ID,
        school="kakita_duelist", sections=sections,
    )
    defaults.update(overrides)
    c = Character(**defaults)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _add_char_without_import_notes(db, **overrides) -> Character:
    return _add_char_with_import_notes(
        db, sections=[{"label": "Backstory", "html": "<p>A tale.</p>"}],
        **overrides,
    )


# ---------------------------------------------------------------------------
# Env-driven settings
# ---------------------------------------------------------------------------

def test_import_enabled_defaults_to_false(monkeypatch) -> None:
    """Fail-closed default: if the env var is unset the feature is OFF.
    A future .env that forgets the flag entirely leaves import disabled
    rather than silently re-enabling a feature we've intentionally
    gated behind config."""
    monkeypatch.delenv("IMPORT_ENABLED", raising=False)
    assert rl.import_enabled() is False


@pytest.mark.parametrize("value,expected", [
    ("0", False), ("false", False), ("FALSE", False), ("no", False),
    ("off", False), ("", False),
    ("1", True), ("true", True), ("yes", True), ("anything-else", True),
])
def test_import_enabled_parses_common_values(value, expected, monkeypatch):
    monkeypatch.setenv("IMPORT_ENABLED", value)
    assert rl.import_enabled() is expected


def test_rate_limit_defaults_to_10(monkeypatch) -> None:
    monkeypatch.delenv("IMPORT_RATE_LIMIT_PER_DAY", raising=False)
    assert rl.rate_limit_per_day() == 10


def test_rate_limit_override_respected(monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_RATE_LIMIT_PER_DAY", "3")
    assert rl.rate_limit_per_day() == 3


# ---------------------------------------------------------------------------
# count_recent_imports
# ---------------------------------------------------------------------------

def test_count_recent_imports_counts_only_tagged_characters(db) -> None:
    # A character with Import Notes section: counts.
    _add_char_with_import_notes(db)
    # A character without Import Notes: does NOT count.
    _add_char_without_import_notes(db)
    # A character owned by a different user: does NOT count.
    _add_char_with_import_notes(db, owner_discord_id="someone_else")

    assert rl.count_recent_imports(db, USER_ID) == 1


def test_count_recent_imports_ignores_old_characters(db) -> None:
    c = _add_char_with_import_notes(db)
    # Force an old created_at (> 24 hours ago).
    c.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)
    db.commit()
    assert rl.count_recent_imports(db, USER_ID) == 0


def test_count_recent_imports_returns_zero_for_new_user(db) -> None:
    assert rl.count_recent_imports(db, "brand_new_user") == 0


def test_count_recent_imports_ignores_malformed_sections(db) -> None:
    """Defensive: if sections somehow contains a non-dict entry (old
    code wrote a stray string), we must not crash."""
    c = _add_char_with_import_notes(db)
    c.sections = ["not a dict", {"label": "Other", "html": ""}]
    db.commit()
    assert rl.count_recent_imports(db, USER_ID) == 0


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------

def test_check_rate_limit_none_below_limit(db, monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_RATE_LIMIT_PER_DAY", "5")
    for _ in range(3):
        _add_char_with_import_notes(db)
    assert rl.check_rate_limit(db, USER_ID) is None


def test_check_rate_limit_blocks_at_limit(db, monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_RATE_LIMIT_PER_DAY", "2")
    for _ in range(2):
        _add_char_with_import_notes(db)
    msg = rl.check_rate_limit(db, USER_ID)
    assert msg is not None
    assert "limit is 2" in msg
    assert "2 characters" in msg


def test_check_rate_limit_blocks_above_limit(db, monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_RATE_LIMIT_PER_DAY", "2")
    for _ in range(5):
        _add_char_with_import_notes(db)
    msg = rl.check_rate_limit(db, USER_ID)
    assert msg is not None
    assert "5 characters" in msg
