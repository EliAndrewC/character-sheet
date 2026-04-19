"""Orphan cleanup for character-art S3 objects.

S3 "backup" of character art is free - every upload calls
``art_storage.upload_art`` and every delete calls
``art_storage.delete_art``. What we need in addition is a periodic
sweep that removes S3 objects no longer referenced by any Character
row: this catches races (delete failed), deployments that deleted a
character while S3 was unreachable, and the "old art replaced" case
if the delete-old-keys step failed during crop-save.

The sweep runs from the same startup background thread that takes
the SQLite backup (see ``app/main.py::_check_and_backup``): after the
DB snapshot lands, we call ``cleanup_orphans``. Failures are logged
and surface via the same admin-only banner as backup failures.
"""

from __future__ import annotations

import logging
from typing import Set

from sqlalchemy.orm import Session

from app.models import Character
from app.services import art_storage


log = logging.getLogger(__name__)


def _known_keys(db: Session) -> Set[str]:
    """Return every S3 key currently referenced by some Character row."""
    keys: Set[str] = set()
    rows = db.query(
        Character.art_s3_key, Character.headshot_s3_key,
    ).all()
    for full, head in rows:
        if full:
            keys.add(full)
        if head:
            keys.add(head)
    return keys


def cleanup_orphans(db: Session, *, bucket: str, region: str) -> dict:
    """Delete S3 objects under the art prefix not referenced in the DB.

    Returns a small summary dict so the caller can log counts. Any
    deletion failure is logged and counted but does not stop the
    sweep - orphans survive to the next run, which is fine.
    """
    known = _known_keys(db)
    orphans = art_storage.list_orphaned_keys(
        known, bucket=bucket, region=region,
    )
    deleted = 0
    errors = 0
    for key in orphans:
        try:
            art_storage.delete_art(bucket, region, key)
            deleted += 1
        except Exception as exc:
            errors += 1
            log.exception("Failed to delete orphan art %s: %s", key, exc)
    log.info(
        "Art orphan cleanup: scanned %d known, deleted %d, errors %d",
        len(known), deleted, errors,
    )
    return {"known": len(known), "deleted": deleted, "errors": errors}


__all__ = ["cleanup_orphans"]
