"""Per-user rate limit and kill-switch for the /import route.

Rate limit (design §5.3, default 10 per 24 hours): counts existing
characters the user owns whose ``sections`` list includes the Import
Notes label AND whose ``created_at`` is within the rolling window. This
lets us enforce a budget without adding a schema table just for audit -
consistent with the "no schema changes" decision in §11.

Kill switch (design §5.4): the ``IMPORT_ENABLED`` env var. When false
the route layer bails with a dedicated "feature temporarily unavailable"
response before any work happens.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Character
from app.services.import_reconcile import IMPORT_NOTES_LABEL


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:  # pragma: no cover - deploy bug
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def import_enabled() -> bool:
    return _env_bool("IMPORT_ENABLED", True)


def rate_limit_per_day() -> int:
    return _env_int("IMPORT_RATE_LIMIT_PER_DAY", 10)


def count_recent_imports(db: Session, user_id: str) -> int:
    """Return how many imports ``user_id`` has run in the last 24 hours.

    An "import" is any character the user owns whose ``sections`` list
    includes an entry labelled ``IMPORT_NOTES_LABEL``. If a user deletes
    the Import Notes section after import, their import no longer counts
    against the budget - that's fine; in practice the budget protects
    against abuse, not against legitimate users tidying up their sheets.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    # SQLAlchemy's default ``Character.created_at`` uses ``func.now()``
    # without a timezone, so we compare naively in UTC.
    cutoff_naive = cutoff.replace(tzinfo=None)

    candidates = (
        db.query(Character)
        .filter(Character.owner_discord_id == user_id)
        .filter(Character.created_at >= cutoff_naive)
        .all()
    )
    return sum(1 for c in candidates if _has_import_notes(c))


def _has_import_notes(character: Character) -> bool:
    sections = character.sections or []
    return any(
        isinstance(s, dict) and s.get("label") == IMPORT_NOTES_LABEL
        for s in sections
    )


def check_rate_limit(
    db: Session, user_id: str,
) -> Optional[str]:
    """Return ``None`` if the user is allowed to import, or a user-facing
    error message if they're over the limit."""
    limit = rate_limit_per_day()
    used = count_recent_imports(db, user_id)
    if used >= limit:
        return (
            f"You've imported {used} characters in the last 24 hours "
            f"(limit is {limit}). Please wait before importing another."
        )
    return None


__all__ = [
    "import_enabled",
    "rate_limit_per_day",
    "count_recent_imports",
    "check_rate_limit",
]
