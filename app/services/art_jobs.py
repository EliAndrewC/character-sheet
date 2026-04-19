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
    source: str          # "upload" or "generated"
    # Bytes are populated by Phase 4 uploads immediately and by the
    # Phase 8 generation worker once Gemini returns. Phase 7's prompt-
    # review staging creates the slot with empty bytes and fills them
    # in when the user submits for generation.
    full_bytes: bytes = b""
    width: int = 0
    height: int = 0
    prompt: Optional[str] = None  # Set for generated art
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
    full_bytes: bytes = b"",
    width: int = 0,
    height: int = 0,
    source: str = "upload",
    prompt: Optional[str] = None,
) -> str:
    """Stash the image bytes under a new staging id and return the id.

    Phase 4 (upload) passes ``full_bytes`` + dimensions. Phase 7
    (generate-prompt-review) passes ``source="generated"`` and
    ``prompt=...`` with no bytes. Phase 8 updates the existing slot
    via ``update_staged_bytes`` once generation completes.
    """
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


def update_staged_bytes(
    staging_id: str,
    *,
    full_bytes: bytes,
    width: int,
    height: int,
) -> None:
    """Fill in the image bytes for an existing staging slot.

    Used by Phase 8 after Gemini returns an image: the prompt-review
    slot already exists, and we update it in place rather than
    allocating a new id, so the progress page can redirect straight to
    the crop page with the same id.
    """
    with _LOCK:
        record = _STAGED.get(staging_id)
        if record is None:  # pragma: no cover - the caller just created it
            return
        record.full_bytes = full_bytes
        record.width = width
        record.height = height


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
    "update_staged_bytes",
    "get_staged",
    "clear_staged",
]
