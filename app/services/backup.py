"""S3 database backup with rolling retention.

Backs up the SQLite database to S3 on app startup if >= 20 hours have
passed since the last backup.  Retention policy:

- Keep the 7 most recent backups (daily tier)
- From the rest, keep 1 per calendar week for 4 most recent weeks (weekly tier)
- From the rest, keep 1 per calendar month for 12 most recent months (monthly tier)
- From the rest, keep 1 per calendar year forever (yearly tier)

All functions are designed to be called from a background thread so they
never block the main request-handling loop.  If AWS is unreachable the
caller catches the exception and records the error for the admin banner.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Set, Tuple

log = logging.getLogger(__name__)

BACKUP_PREFIX = "backups/"
BACKUP_INTERVAL_HOURS = 20
DAILY_KEEP = 7
WEEKLY_KEEP = 4
MONTHLY_KEEP = 12


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def make_backup_key(now: datetime) -> str:
    """Generate an S3 key like ``backups/l7r-2026-04-16T03-00-00Z.db``."""
    ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{BACKUP_PREFIX}l7r-{ts}.db"


def parse_backup_timestamp(key: str) -> datetime:
    """Extract a UTC datetime from a backup key.

    Raises ``ValueError`` if the key doesn't match the expected format.
    """
    # key looks like "backups/l7r-2026-04-16T03-00-00Z.db"
    filename = key.rsplit("/", 1)[-1]  # "l7r-2026-04-16T03-00-00Z.db"
    if not filename.startswith("l7r-") or not filename.endswith(".db"):
        raise ValueError(f"Unexpected backup key format: {key}")
    ts_str = filename[4:-3]  # "2026-04-16T03-00-00Z"
    return datetime.strptime(ts_str, "%Y-%m-%dT%H-%M-%SZ").replace(
        tzinfo=timezone.utc
    )


# ---------------------------------------------------------------------------
# Retention logic
# ---------------------------------------------------------------------------

def compute_retention(
    keys: list[str], now: datetime
) -> Tuple[Set[str], Set[str]]:
    """Decide which backup keys to keep and which to delete.

    Returns ``(keep, delete)`` sets of S3 keys.
    """
    if not keys:
        return set(), set()

    # Parse and sort newest-first
    parsed: list[tuple[str, datetime]] = []
    for k in keys:
        try:
            parsed.append((k, parse_backup_timestamp(k)))
        except ValueError:
            continue  # skip unparseable keys

    parsed.sort(key=lambda x: x[1], reverse=True)

    keep: set[str] = set()
    remaining: list[tuple[str, datetime]] = []

    # --- Daily tier: keep the N most recent ---
    for i, (k, ts) in enumerate(parsed):
        if i < DAILY_KEEP:
            keep.add(k)
        else:
            remaining.append((k, ts))

    # --- Weekly tier: keep newest per ISO week for last N weeks ---
    now_utc = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    weekly_cutoff = now_utc - timedelta(weeks=WEEKLY_KEEP)
    by_week: dict[tuple[int, int], list[tuple[str, datetime]]] = defaultdict(list)
    still_remaining: list[tuple[str, datetime]] = []

    for k, ts in remaining:
        if ts >= weekly_cutoff:
            iso = ts.isocalendar()
            by_week[(iso[0], iso[1])].append((k, ts))
        else:
            still_remaining.append((k, ts))

    for week_key in by_week:
        # Keep the newest backup in this week
        best = max(by_week[week_key], key=lambda x: x[1])
        keep.add(best[0])
        for k, ts in by_week[week_key]:
            if k != best[0]:
                still_remaining.append((k, ts))

    remaining = still_remaining

    # --- Monthly tier: keep newest per month for last N months ---
    monthly_cutoff = now_utc - timedelta(days=30 * MONTHLY_KEEP)
    by_month: dict[tuple[int, int], list[tuple[str, datetime]]] = defaultdict(list)
    still_remaining = []

    for k, ts in remaining:
        if ts >= monthly_cutoff:
            by_month[(ts.year, ts.month)].append((k, ts))
        else:
            still_remaining.append((k, ts))

    for month_key in by_month:
        best = max(by_month[month_key], key=lambda x: x[1])
        keep.add(best[0])
        for k, ts in by_month[month_key]:
            if k != best[0]:
                still_remaining.append((k, ts))

    remaining = still_remaining

    # --- Yearly tier: keep newest per year forever ---
    by_year: dict[int, list[tuple[str, datetime]]] = defaultdict(list)
    for k, ts in remaining:
        by_year[ts.year].append((k, ts))

    for year in by_year:
        best = max(by_year[year], key=lambda x: x[1])
        keep.add(best[0])

    # Everything not kept is deleted
    all_keys = {k for k, _ in parsed}
    delete = all_keys - keep

    return keep, delete


# ---------------------------------------------------------------------------
# SQLite snapshot
# ---------------------------------------------------------------------------

def create_snapshot(db_path: str) -> str:
    """Create a consistent copy of the SQLite database.

    Uses the SQLite backup API so it works safely even if the database is
    being written to concurrently.  Returns the path to the temporary copy.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tmp_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return tmp_path


# ---------------------------------------------------------------------------
# S3 operations
# ---------------------------------------------------------------------------

def _get_s3_client(region: str):
    """Create a boto3 S3 client."""
    import boto3
    return boto3.client("s3", region_name=region)


def list_backup_keys(bucket: str, region: str) -> list[str]:
    """List all backup keys in the S3 bucket."""
    client = _get_s3_client(region)
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=BACKUP_PREFIX):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def get_last_backup_time(
    bucket: str, region: str
) -> Optional[datetime]:
    """Return the timestamp of the most recent backup, or None."""
    keys = list_backup_keys(bucket, region)
    if not keys:
        return None
    latest_ts = None
    for k in keys:
        try:
            ts = parse_backup_timestamp(k)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
        except ValueError:
            continue
    return latest_ts


def should_backup(
    last_backup_time: Optional[datetime], now: datetime
) -> bool:
    """Return True if a new backup should be taken."""
    if last_backup_time is None:
        return True
    now_utc = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    last_utc = (
        last_backup_time.replace(tzinfo=timezone.utc)
        if last_backup_time.tzinfo is None
        else last_backup_time
    )
    return (now_utc - last_utc) >= timedelta(hours=BACKUP_INTERVAL_HOURS)


def run_backup(db_path: str, bucket: str, region: str) -> dict:
    """Take a backup and apply retention policy.

    Returns ``{"success": True/False, "error": str|None, "key": str|None}``.
    """
    now = datetime.now(timezone.utc)
    key = make_backup_key(now)
    tmp_path = None

    try:
        if not os.path.exists(db_path):
            return {"success": False, "error": f"Database not found: {db_path}", "key": None}

        # Create consistent snapshot
        tmp_path = create_snapshot(db_path)

        # Upload
        client = _get_s3_client(region)
        client.upload_file(tmp_path, bucket, key)
        log.info("Backup uploaded: s3://%s/%s", bucket, key)

        # Run retention cleanup
        all_keys = list_backup_keys(bucket, region)
        _keep, delete = compute_retention(all_keys, now)
        for dk in delete:
            client.delete_object(Bucket=bucket, Key=dk)
            log.info("Deleted old backup: %s", dk)

        return {"success": True, "error": None, "key": key}

    except Exception as e:
        log.error("Backup failed: %s", e)
        return {"success": False, "error": str(e), "key": None}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
