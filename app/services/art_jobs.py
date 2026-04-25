"""Disk-backed staging registry for character-art uploads and generations.

Art uploads and generations happen in two HTTP round trips:

  1. ``POST /characters/{id}/art/upload`` (or ``art/generate/...``)
     stages the bytes (and the character id + uploading user id) here
     and redirects the user to the crop page.
  2. ``POST /characters/{id}/art/crop/{staging_id}`` reads the staged
     bytes back, runs ``build_headshot``, uploads to S3, and clears
     the staging slot.

Records persist on the Fly volume under ``$STAGED_ART_DIR`` (one
directory per staging id, with ``meta.json`` + an image file). That
keeps in-flight art alive across machine restarts and arbitrarily
long cropping sessions; the ``cleanup_older_than`` helper purges
abandoned slots after 24h via a background sweep in ``app.main``.

Single-process / single-machine. The Fly volume is mounted on one
machine; if we scale past one this needs to move to a shared store.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


@dataclass
class StagedArt:
    id: str
    user_id: str         # Discord ID of the uploader (enforces owner-only crop)
    char_id: int         # Character the art is being staged for
    source: str          # "upload" or "generated"
    # Bytes are populated by uploads immediately and by the generation
    # worker once Gemini returns. Prompt-review staging creates the
    # slot with empty bytes and fills them in later.
    full_bytes: bytes = b""
    width: int = 0
    height: int = 0
    prompt: Optional[str] = None  # Set for generated art
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()

_META_FILENAME = "meta.json"
_IMAGE_FILENAME = "image.bin"


def _staging_root() -> Path:
    """Return the directory where staged art lives.

    Read at call time so tests can override via ``STAGED_ART_DIR``
    without monkey-patching module state. Defaults to ``staged_art``
    relative to the working directory for local dev; production sets
    it to ``/data/staged_art`` via ``fly.toml``."""
    path = Path(os.environ.get("STAGED_ART_DIR", "staged_art"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_dir(staging_id: str) -> Path:
    return _staging_root() / staging_id


def _atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via tempfile + rename so a crash
    mid-write can't leave a torn file."""
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:  # pragma: no cover - racy cleanup; another thread already unlinked
            pass
        raise


def _write_meta(stage_dir: Path, record: StagedArt) -> None:
    payload = {
        "id": record.id,
        "user_id": record.user_id,
        "char_id": record.char_id,
        "source": record.source,
        "width": record.width,
        "height": record.height,
        "prompt": record.prompt,
        "created_at": record.created_at.isoformat(),
    }
    _atomic_write(
        stage_dir / _META_FILENAME,
        json.dumps(payload).encode("utf-8"),
    )


def _read_meta(stage_dir: Path) -> Optional[dict]:
    try:
        return json.loads((stage_dir / _META_FILENAME).read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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

    Upload calls pass ``full_bytes`` + dimensions immediately. The
    generate-prompt-review path passes ``source="generated"`` and
    ``prompt=...`` with no bytes; the generation worker fills them in
    later via ``update_staged_bytes``."""
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
    stage_dir = _stage_dir(staging_id)
    with _LOCK:
        stage_dir.mkdir(parents=True, exist_ok=True)
        if full_bytes:
            _atomic_write(stage_dir / _IMAGE_FILENAME, full_bytes)
        _write_meta(stage_dir, record)
    return staging_id


def update_staged_prompt(staging_id: str, prompt: str) -> None:
    """Overwrite the recorded prompt on an existing staging slot.

    Called by the generate-submit route when the user has edited the
    prompt in the review textarea before kicking off the Imagen job.
    No-op if the slot doesn't exist."""
    stage_dir = _stage_dir(staging_id)
    with _LOCK:
        meta = _read_meta(stage_dir)
        if meta is None:
            return
        meta["prompt"] = prompt
        _atomic_write(
            stage_dir / _META_FILENAME,
            json.dumps(meta).encode("utf-8"),
        )


def update_staged_bytes(
    staging_id: str,
    *,
    full_bytes: bytes,
    width: int,
    height: int,
) -> None:
    """Fill in the image bytes for an existing staging slot.

    Used by the generation worker after Gemini returns: the prompt-
    review slot already exists, and we update it in place rather than
    allocating a new id, so the progress page can redirect straight
    to the crop page with the same id."""
    stage_dir = _stage_dir(staging_id)
    with _LOCK:
        meta = _read_meta(stage_dir)
        if meta is None:
            return
        _atomic_write(stage_dir / _IMAGE_FILENAME, full_bytes)
        meta["width"] = width
        meta["height"] = height
        _atomic_write(
            stage_dir / _META_FILENAME,
            json.dumps(meta).encode("utf-8"),
        )


def get_staged(staging_id: str) -> Optional[StagedArt]:
    """Return the staged record, or ``None`` if the id is unknown."""
    stage_dir = _stage_dir(staging_id)
    with _LOCK:
        meta = _read_meta(stage_dir)
        if meta is None:
            return None
        try:
            full_bytes = (stage_dir / _IMAGE_FILENAME).read_bytes()
        except FileNotFoundError:
            full_bytes = b""
        return StagedArt(
            id=meta["id"],
            user_id=meta["user_id"],
            char_id=meta["char_id"],
            source=meta["source"],
            full_bytes=full_bytes,
            width=meta["width"],
            height=meta["height"],
            prompt=meta.get("prompt"),
            created_at=datetime.fromisoformat(meta["created_at"]),
        )


def clear_staged(staging_id: str) -> None:
    """Drop the staging slot once the crop has been committed."""
    stage_dir = _stage_dir(staging_id)
    with _LOCK:
        if stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=True)


def cleanup_older_than(cutoff: datetime) -> int:
    """Delete staging dirs whose recorded ``created_at`` is older than
    ``cutoff``. Returns the count purged.

    Called by the background sweep thread in ``app.main`` once a day
    with ``cutoff = now - 24h``. Dirs with missing or malformed
    metadata are skipped - leaking a stray dir is preferable to
    deleting data we don't understand."""
    root = _staging_root()
    purged = 0
    with _LOCK:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            meta = _read_meta(child)
            if meta is None:
                continue
            try:
                created = datetime.fromisoformat(meta["created_at"])
            except (KeyError, ValueError, TypeError):
                continue
            if created < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                purged += 1
    return purged


__all__ = [
    "StagedArt",
    "stage_art",
    "update_staged_prompt",
    "update_staged_bytes",
    "get_staged",
    "clear_staged",
    "cleanup_older_than",
]
