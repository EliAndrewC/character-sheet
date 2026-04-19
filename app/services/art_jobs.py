"""In-memory staging registry for character-art uploads.

Art uploads happen in two HTTP round trips:

  1. ``POST /characters/{id}/art/upload`` validates the bytes, stashes
     the decoded image (and the character id + uploading user id) in
     this registry, and redirects to the crop page.
  2. ``POST /characters/{id}/art/crop/{staging_id}`` reads back the
     staged bytes, runs ``build_headshot``, uploads both images to S3,
     and clears the staging slot.

The same pattern is used by ``import_jobs`` for import pipeline runs.
Entries have a short TTL so unused uploads don't pile up in process
memory. Single-process / single-machine only - if we scale past one
Fly machine this moves to a shared store.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


@dataclass
class StagedArt:
    id: str
    user_id: str         # Discord ID of the uploader (enforces owner-only crop)
    char_id: int         # Character the art is being staged for
    full_bytes: bytes    # Validated, EXIF-normalised WebP-ready image bytes
    width: int           # Dimensions after EXIF-transpose
    height: int
    source: str          # "upload" or "generated"
    prompt: Optional[str] = None  # Only set for "generated"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_STAGED: Dict[str, StagedArt] = {}
_LOCK = threading.Lock()

# Keep staged art for this long before it's reaped. 15 minutes is long
# enough for the user to crop, short enough that abandoned uploads
# don't leak memory.
STAGING_TTL = timedelta(minutes=15)


def _reap_expired() -> None:
    cutoff = datetime.now(timezone.utc) - STAGING_TTL
    with _LOCK:
        expired = [sid for sid, s in _STAGED.items() if s.created_at < cutoff]
        for sid in expired:
            del _STAGED[sid]


def stage_art(
    *,
    user_id: str,
    char_id: int,
    full_bytes: bytes,
    width: int,
    height: int,
    source: str = "upload",
    prompt: Optional[str] = None,
) -> str:
    """Stash the image bytes under a new staging id and return the id."""
    _reap_expired()
    staging_id = str(uuid.uuid4())
    record = StagedArt(
        id=staging_id,
        user_id=user_id,
        char_id=char_id,
        full_bytes=full_bytes,
        width=width,
        height=height,
        source=source,
        prompt=prompt,
    )
    with _LOCK:
        _STAGED[staging_id] = record
    return staging_id


def get_staged(staging_id: str) -> Optional[StagedArt]:
    """Return the staged record, or None if the id is unknown or expired."""
    _reap_expired()
    with _LOCK:
        return _STAGED.get(staging_id)


def clear_staged(staging_id: str) -> None:
    """Drop the staging slot once the crop has been committed."""
    with _LOCK:
        _STAGED.pop(staging_id, None)


__all__ = [
    "STAGING_TTL",
    "StagedArt",
    "stage_art",
    "get_staged",
    "clear_staged",
]
