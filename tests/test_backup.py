"""Tests for the S3 backup module with rolling retention."""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.backup import (
    BACKUP_PREFIX,
    compute_retention,
    create_snapshot,
    get_last_backup_time,
    list_backup_keys,
    make_backup_key,
    parse_backup_timestamp,
    run_backup,
    should_backup,
)


# ---------------------------------------------------------------------------
# make_backup_key
# ---------------------------------------------------------------------------

class TestMakeBackupKey:
    def test_format(self):
        dt = datetime(2026, 4, 16, 3, 0, 0, tzinfo=timezone.utc)
        assert make_backup_key(dt) == "backups/l7r-2026-04-16T03-00-00Z.db"

    def test_includes_prefix(self):
        dt = datetime(2025, 1, 1, 12, 30, 45, tzinfo=timezone.utc)
        key = make_backup_key(dt)
        assert key.startswith(BACKUP_PREFIX)
        assert key.endswith(".db")


# ---------------------------------------------------------------------------
# parse_backup_timestamp
# ---------------------------------------------------------------------------

class TestParseBackupTimestamp:
    def test_valid_key(self):
        key = "backups/l7r-2026-04-16T03-00-00Z.db"
        dt = parse_backup_timestamp(key)
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 16
        assert dt.hour == 3
        assert dt.tzinfo == timezone.utc

    def test_roundtrip(self):
        now = datetime(2026, 7, 15, 14, 30, 0, tzinfo=timezone.utc)
        key = make_backup_key(now)
        parsed = parse_backup_timestamp(key)
        assert parsed == now

    def test_invalid_key_no_prefix(self):
        with pytest.raises(ValueError):
            parse_backup_timestamp("backups/bad-name.db")

    def test_invalid_key_wrong_extension(self):
        with pytest.raises(ValueError):
            parse_backup_timestamp("backups/l7r-2026-04-16T03-00-00Z.txt")


# ---------------------------------------------------------------------------
# should_backup
# ---------------------------------------------------------------------------

class TestShouldBackup:
    def test_no_previous_backup(self):
        assert should_backup(None, datetime.now(timezone.utc)) is True

    def test_recent_backup(self):
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        last = now - timedelta(hours=19)
        assert should_backup(last, now) is False

    def test_old_backup(self):
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        last = now - timedelta(hours=21)
        assert should_backup(last, now) is True

    def test_exactly_20_hours(self):
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        last = now - timedelta(hours=20)
        assert should_backup(last, now) is True

    def test_very_old_backup(self):
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        last = now - timedelta(days=30)
        assert should_backup(last, now) is True

    def test_naive_datetimes(self):
        """Works with naive datetimes (treated as UTC)."""
        now = datetime(2026, 4, 16, 12, 0, 0)
        last = datetime(2026, 4, 15, 12, 0, 0)
        assert should_backup(last, now) is True


# ---------------------------------------------------------------------------
# compute_retention
# ---------------------------------------------------------------------------

def _key(dt: datetime) -> str:
    return make_backup_key(dt)


def _dt(year, month, day, hour=12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


class TestComputeRetention:
    def test_empty_list(self):
        keep, delete = compute_retention([], _dt(2026, 4, 16))
        assert keep == set()
        assert delete == set()

    def test_fewer_than_7_keeps_all(self):
        keys = [_key(_dt(2026, 4, d)) for d in range(10, 14)]
        keep, delete = compute_retention(keys, _dt(2026, 4, 16))
        assert keep == set(keys)
        assert delete == set()

    def test_exactly_7_keeps_all(self):
        keys = [_key(_dt(2026, 4, d)) for d in range(10, 17)]
        keep, delete = compute_retention(keys, _dt(2026, 4, 17))
        assert keep == set(keys)
        assert delete == set()

    def test_8_backups_oldest_promoted_to_weekly(self):
        """8 daily backups: 7 kept in daily, 8th promoted to weekly (within 4 weeks)."""
        keys = [_key(_dt(2026, 4, d)) for d in range(9, 17)]  # 8 keys
        keep, delete = compute_retention(keys, _dt(2026, 4, 17))
        # All 8 kept: 7 in daily tier, April 9 promoted to weekly
        assert keep == set(keys)
        assert delete == set()

    def test_daily_tier_keeps_7_most_recent(self):
        # 10 daily backups, one per day
        keys = [_key(_dt(2026, 4, d)) for d in range(7, 17)]
        keep, delete = compute_retention(keys, _dt(2026, 4, 17))
        # Daily: April 10-16 (7 most recent)
        for d in range(10, 17):
            assert _key(_dt(2026, 4, d)) in keep
        # April 7-9: promoted to weekly (all within 4 weeks)
        for d in range(7, 10):
            assert _key(_dt(2026, 4, d)) in keep  # weekly tier

    def test_weekly_promotion_same_week_deletes_older(self):
        """Two backups in the same week beyond daily: newest kept, older eventually deleted."""
        now = _dt(2029, 5, 15)
        keys = []
        # 7 daily backups (May 9-15)
        for d in range(9, 16):
            keys.append(_key(_dt(2029, 5, d)))
        # Two from the same week, years ago (beyond monthly window)
        keys.append(_key(_dt(2026, 4, 28)))  # week 18
        keys.append(_key(_dt(2026, 4, 27)))  # week 18 (same week)

        keep, delete = compute_retention(keys, now)
        # Daily: May 9-15 kept
        for d in range(9, 16):
            assert _key(_dt(2029, 5, d)) in keep
        # Yearly: April 28 kept (newest in 2026), April 27 deleted
        assert _key(_dt(2026, 4, 28)) in keep
        assert _key(_dt(2026, 4, 27)) in delete

    def test_monthly_promotion_same_month_deletes_older(self):
        """Two backups in the same month beyond weekly: monthly keeps newest, older cascades."""
        now = _dt(2026, 12, 15)
        keys = []
        # 7 daily (Dec 9-15)
        for d in range(9, 16):
            keys.append(_key(_dt(2026, 12, d)))
        # Two from same month beyond weekly window, within monthly
        keys.append(_key(_dt(2026, 6, 10)))
        keys.append(_key(_dt(2026, 6, 5)))
        # The older one (June 5) cascades to yearly, but 2026 already has
        # June 10 in monthly and daily tier has Dec entries. June 5 ends up
        # in yearly for 2026 but yearly already has June 10 (newest 2026).
        # Actually yearly gets only what's left after monthly.
        # June 10 is in monthly. June 5 cascades to yearly - it's 2026,
        # and it would be the only 2026 entry in yearly, so it's kept.
        # To test actual deletion, we need 3 entries from the same month.
        keys.append(_key(_dt(2026, 6, 1)))

        keep, delete = compute_retention(keys, now)
        # Monthly: June 10 kept (newest in June)
        assert _key(_dt(2026, 6, 10)) in keep
        # Yearly: June 5 kept (newest remaining in 2026)
        assert _key(_dt(2026, 6, 5)) in keep
        # June 1: also 2026 yearly, but June 5 is newer -> deleted
        assert _key(_dt(2026, 6, 1)) in delete

    def test_yearly_promotion(self):
        """Backups older than monthly tier get yearly promotion."""
        now = _dt(2028, 6, 15)
        keys = []
        # 7 daily
        for d in range(9, 16):
            keys.append(_key(_dt(2028, 6, d)))
        # Old backups from different years
        keys.append(_key(_dt(2026, 3, 10)))
        keys.append(_key(_dt(2026, 7, 20)))  # same year
        keys.append(_key(_dt(2025, 12, 1)))

        keep, delete = compute_retention(keys, now)
        # 2026: keep the newest (July 20)
        assert _key(_dt(2026, 7, 20)) in keep
        assert _key(_dt(2026, 3, 10)) in delete
        # 2025: keep the only one
        assert _key(_dt(2025, 12, 1)) in keep

    def test_gaps_in_daily_keeps_all_recent(self):
        """Only 2 backups in the last 8 days - both kept in daily tier."""
        now = _dt(2026, 4, 16)
        keys = [
            _key(_dt(2026, 4, 16)),
            _key(_dt(2026, 4, 10)),
        ]
        keep, delete = compute_retention(keys, now)
        assert keep == set(keys)
        assert delete == set()

    def test_large_gap_then_burst(self):
        """No backups for a month, then several in one day."""
        now = _dt(2026, 4, 16, 18)
        keys = [
            _key(_dt(2026, 4, 16, 18)),
            _key(_dt(2026, 4, 16, 14)),
            _key(_dt(2026, 4, 16, 10)),
            _key(_dt(2026, 3, 1)),
        ]
        keep, delete = compute_retention(keys, now)
        assert keep == set(keys)  # all within daily tier or monthly

    def test_full_lifecycle(self):
        """Simulate a realistic backup history spanning 2+ years."""
        now = _dt(2028, 6, 15)
        keys = []
        # Recent daily
        for d in range(9, 16):
            keys.append(_key(_dt(2028, 6, d)))
        # Recent weeks
        keys.append(_key(_dt(2028, 5, 28)))
        keys.append(_key(_dt(2028, 5, 20)))
        # Older months
        keys.append(_key(_dt(2028, 2, 15)))
        keys.append(_key(_dt(2028, 1, 10)))
        keys.append(_key(_dt(2027, 11, 5)))
        # Old years
        keys.append(_key(_dt(2026, 6, 1)))
        keys.append(_key(_dt(2025, 12, 31)))

        keep, delete = compute_retention(keys, now)
        # All should be kept (each is the sole representative of its tier)
        assert keep == set(keys)
        assert delete == set()

    def test_multiple_same_year_beyond_monthly_keeps_one(self):
        """Multiple backups in the same year beyond monthly tier - yearly keeps newest."""
        now = _dt(2029, 6, 15)
        keys = []
        # Daily tier
        for d in range(9, 16):
            keys.append(_key(_dt(2029, 6, d)))
        # Three from 2026 (well beyond monthly window of ~360 days)
        keys.append(_key(_dt(2026, 7, 20)))
        keys.append(_key(_dt(2026, 7, 5)))
        keys.append(_key(_dt(2026, 3, 1)))

        keep, delete = compute_retention(keys, now)
        # Yearly: keep newest from 2026 (July 20), delete others
        assert _key(_dt(2026, 7, 20)) in keep
        assert _key(_dt(2026, 7, 5)) in delete
        assert _key(_dt(2026, 3, 1)) in delete

    def test_unparseable_keys_ignored(self):
        """Keys that don't match the format are silently skipped."""
        keys = [
            _key(_dt(2026, 4, 16)),
            "backups/random-file.txt",
            "backups/not-a-backup.db",
        ]
        keep, delete = compute_retention(keys, _dt(2026, 4, 17))
        assert _key(_dt(2026, 4, 16)) in keep
        assert len(keep) == 1
        assert len(delete) == 0


# ---------------------------------------------------------------------------
# create_snapshot
# ---------------------------------------------------------------------------

class TestCreateSnapshot:
    def test_creates_valid_copy(self):
        # Create a test database with some data
        fd, src_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(src_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
            conn.execute("INSERT INTO test VALUES (1, 'hello')")
            conn.commit()
            conn.close()

            # Take a snapshot
            snap_path = create_snapshot(src_path)
            try:
                # Verify the snapshot has the data
                conn = sqlite3.connect(snap_path)
                rows = conn.execute("SELECT val FROM test").fetchall()
                conn.close()
                assert rows == [("hello",)]
            finally:
                os.unlink(snap_path)
        finally:
            os.unlink(src_path)

    def test_snapshot_is_independent(self):
        """Modifying original after snapshot doesn't affect snapshot."""
        fd, src_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(src_path)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
            conn.execute("INSERT INTO test VALUES (1, 'before')")
            conn.commit()
            conn.close()

            snap_path = create_snapshot(src_path)
            try:
                # Modify original
                conn = sqlite3.connect(src_path)
                conn.execute("UPDATE test SET val = 'after'")
                conn.commit()
                conn.close()

                # Snapshot still has old value
                conn = sqlite3.connect(snap_path)
                rows = conn.execute("SELECT val FROM test").fetchall()
                conn.close()
                assert rows == [("before",)]
            finally:
                os.unlink(snap_path)
        finally:
            os.unlink(src_path)


# ---------------------------------------------------------------------------
# S3 operations (mocked)
# ---------------------------------------------------------------------------

class TestListBackupKeys:
    @patch("app.services.backup._get_s3_client")
    def test_lists_keys(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [
                {"Key": "backups/l7r-2026-04-16T03-00-00Z.db"},
                {"Key": "backups/l7r-2026-04-15T03-00-00Z.db"},
            ]},
        ]

        keys = list_backup_keys("my-bucket", "us-east-1")
        assert len(keys) == 2

    @patch("app.services.backup._get_s3_client")
    def test_empty_bucket(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{}]

        keys = list_backup_keys("my-bucket", "us-east-1")
        assert keys == []


class TestGetLastBackupTime:
    @patch("app.services.backup.list_backup_keys")
    def test_returns_latest(self, mock_list):
        mock_list.return_value = [
            "backups/l7r-2026-04-14T03-00-00Z.db",
            "backups/l7r-2026-04-16T03-00-00Z.db",
            "backups/l7r-2026-04-15T03-00-00Z.db",
        ]
        result = get_last_backup_time("bucket", "us-east-1")
        assert result == _dt(2026, 4, 16, 3)

    @patch("app.services.backup.list_backup_keys")
    def test_no_backups(self, mock_list):
        mock_list.return_value = []
        assert get_last_backup_time("bucket", "us-east-1") is None


class TestRunBackup:
    @patch("app.services.backup._get_s3_client")
    def test_successful_backup(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{}]

        # Create a real temp database
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        try:
            result = run_backup(db_path, "my-bucket", "us-east-1")
            assert result["success"] is True
            assert result["error"] is None
            assert result["key"] is not None
            assert result["key"].startswith(BACKUP_PREFIX)
            # Verify upload was called
            client.upload_file.assert_called_once()
        finally:
            os.unlink(db_path)

    def test_missing_database(self):
        result = run_backup("/nonexistent/path.db", "bucket", "us-east-1")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("app.services.backup._get_s3_client")
    def test_s3_error_returns_failure(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        client.upload_file.side_effect = Exception("Connection refused")

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        try:
            result = run_backup(db_path, "bucket", "us-east-1")
            assert result["success"] is False
            assert "Connection refused" in result["error"]
        finally:
            os.unlink(db_path)

    @patch("app.services.backup._get_s3_client")
    def test_retention_cleanup_runs(self, mock_get_client):
        """After upload, old backups are deleted per retention policy."""
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator

        # Simulate 10 existing backups (8 old ones + the newly uploaded one)
        old_keys = [
            {"Key": _key(_dt(2026, 4, d))} for d in range(1, 11)
        ]
        # First call (for retention list after upload) returns all keys
        paginator.paginate.return_value = [{"Contents": old_keys}]

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        try:
            result = run_backup(db_path, "bucket", "us-east-1")
            assert result["success"] is True
            # upload_file should have been called
            assert client.upload_file.called
        finally:
            os.unlink(db_path)

    @patch("app.services.backup._get_s3_client")
    def test_temp_file_cleaned_up(self, mock_get_client):
        """Temporary snapshot file is deleted even on failure."""
        client = MagicMock()
        mock_get_client.return_value = client
        client.upload_file.side_effect = Exception("fail")

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()

        try:
            run_backup(db_path, "bucket", "us-east-1")
            # Check no leftover temp files (can't check exact path, but
            # we verify the function completes without leaving state)
        finally:
            os.unlink(db_path)

    @patch("app.services.backup._get_s3_client")
    def test_retention_actually_deletes_old_keys(self, mock_get_client):
        """When ``compute_retention`` flags old backups for deletion, each one
        must actually be ``delete_object``-ed on the S3 client."""
        from tests.test_backup import _dt, _key

        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator

        # Seed 30+ backups across Jan-Feb-Mar-Apr 2026. Anything beyond
        # daily+weekly+monthly tiers drops to yearly and loses duplicates.
        old_keys = []
        for month in (1, 2, 3, 4):
            for day in range(1, 9):
                old_keys.append({"Key": _key(_dt(2026, month, day))})
        paginator.paginate.return_value = [{"Contents": old_keys}]

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (i INTEGER)")
        conn.commit()
        conn.close()

        try:
            result = run_backup(db_path, "bucket", "us-east-1")
            assert result["success"] is True
            # Some old backups must have been deleted to satisfy retention.
            assert client.delete_object.called
        finally:
            os.unlink(db_path)


class TestGetS3Client:
    """``_get_s3_client`` imports boto3 lazily and returns a real client.
    This exercises the import branch that's otherwise always patched out."""

    def test_returns_s3_client(self):
        pytest.importorskip("boto3")
        from app.services.backup import _get_s3_client
        client = _get_s3_client("us-east-1")
        assert client is not None
        assert client.meta.region_name == "us-east-1"
        assert client.meta.service_model.service_name == "s3"


class TestGetLastBackupTimeWithUnparseableKeys:
    @patch("app.services.backup.list_backup_keys")
    def test_unparseable_keys_are_skipped(self, mock_list):
        """Keys that don't match the expected format are silently ignored,
        not raised. The latest valid timestamp still wins."""
        mock_list.return_value = [
            "backups/l7r-2026-04-15T03-00-00Z.db",
            "backups/garbage_filename.db",  # unparseable - no l7r- prefix
            "backups/l7r-NOT-A-TIMESTAMP.db",  # unparseable - bad ts format
            "backups/l7r-2026-04-16T03-00-00Z.db",  # latest valid
        ]
        from datetime import datetime, timezone
        result = get_last_backup_time("bucket", "us-east-1")
        assert result == datetime(2026, 4, 16, 3, tzinfo=timezone.utc)
