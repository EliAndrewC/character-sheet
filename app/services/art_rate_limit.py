"""Per-user rate limit and kill-switch for character-art generation.

Rate limit (per Eli's direction): 100 successful generations per user
per 24 hours. Implemented in-memory; single-machine Fly deployment
tolerates the restart-on-deploy reset (worst case a user gets a few
extra generations after a deploy, which is harmless).

Kill switch: ``ART_GEN_ENABLED`` env var. Fail-closed default (False)
so a missing secret doesn't silently turn the feature on.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


DEFAULT_RATE_LIMIT_PER_DAY = 100
RATE_WINDOW = timedelta(hours=24)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:  # pragma: no cover - deploy-time typo
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def art_gen_enabled() -> bool:
    """Fail-closed: default is False. Set ``ART_GEN_ENABLED=true`` to turn on."""
    return _env_bool("ART_GEN_ENABLED", False)


def rate_limit_per_day() -> int:
    return _env_int("ART_GEN_RATE_LIMIT_PER_DAY", DEFAULT_RATE_LIMIT_PER_DAY)


# ---------------------------------------------------------------------------
# In-memory sliding-window counter
# ---------------------------------------------------------------------------


_counts: Dict[str, List[datetime]] = {}
_lock = threading.Lock()


def _prune_expired(user_id: str, now: datetime) -> List[datetime]:
    """Drop timestamps older than ``RATE_WINDOW`` and return the surviving list."""
    cutoff = now - RATE_WINDOW
    stamps = _counts.get(user_id, [])
    survivors = [t for t in stamps if t > cutoff]
    if survivors:
        _counts[user_id] = survivors
    else:
        _counts.pop(user_id, None)
    return survivors


def count_recent(user_id: str, *, now: Optional[datetime] = None) -> int:
    """Return the number of generations ``user_id`` has run in the last 24h."""
    now = now or datetime.now(timezone.utc)
    with _lock:
        return len(_prune_expired(user_id, now))


def check_rate_limit(
    user_id: str, *, now: Optional[datetime] = None,
) -> Optional[str]:
    """Return ``None`` if the user is allowed to generate, or a user-facing
    error string if they're over the limit.

    Does NOT record a generation - call ``record_generation`` on success
    separately so the counter only increments for completed work.
    """
    limit = rate_limit_per_day()
    used = count_recent(user_id, now=now)
    if used >= limit:
        return (
            f"You've generated {used} images in the last 24 hours "
            f"(limit is {limit}). Please wait before generating another."
        )
    return None


def record_generation(user_id: str, *, now: Optional[datetime] = None) -> None:
    """Stamp a successful generation for ``user_id``."""
    now = now or datetime.now(timezone.utc)
    with _lock:
        _prune_expired(user_id, now)
        _counts.setdefault(user_id, []).append(now)


def reset_all() -> None:
    """Test helper - wipe the counter between tests."""
    with _lock:
        _counts.clear()


__all__ = [
    "DEFAULT_RATE_LIMIT_PER_DAY",
    "art_gen_enabled",
    "check_rate_limit",
    "count_recent",
    "rate_limit_per_day",
    "record_generation",
    "reset_all",
]
