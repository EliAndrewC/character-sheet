"""Tests for ``app.services.art_backup.cleanup_orphans`` and the
character-delete integration that removes S3 keys on hard-delete."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Character
from app.services import art_backup


USER_ID = "183026066498125825"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def s3_client():
    with patch("app.services.art_storage._get_s3_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client


def _stub_pagination(s3_client: MagicMock, keys: list[str]) -> None:
    """Make ``list_objects_v2`` return ``keys`` in a single page."""
    paginator = MagicMock()
    s3_client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"Contents": [{"Key": k} for k in keys]},
    ]


# ---------------------------------------------------------------------------
# cleanup_orphans
# ---------------------------------------------------------------------------


class TestCleanupOrphans:
    def test_deletes_keys_not_referenced_by_any_character(self, client, s3_client):
        """Two characters each own one (full, headshot) pair; S3 has those four
        plus two stale keys. The sweep deletes exactly the two stale keys."""
        session = client._test_session_factory()
        session.add(Character(
            name="A", owner_discord_id=USER_ID,
            art_s3_key="character_art/1/full-a.webp",
            headshot_s3_key="character_art/1/head-a.webp",
        ))
        session.add(Character(
            name="B", owner_discord_id=USER_ID,
            art_s3_key="character_art/2/full-b.webp",
            headshot_s3_key="character_art/2/head-b.webp",
        ))
        session.commit()

        _stub_pagination(s3_client, [
            # Known
            "character_art/1/full-a.webp",
            "character_art/1/head-a.webp",
            "character_art/2/full-b.webp",
            "character_art/2/head-b.webp",
            # Orphans
            "character_art/1/full-old.webp",
            "character_art/99/full-deleted-char.webp",
        ])

        summary = art_backup.cleanup_orphans(
            session, bucket="bucket", region="us-east-1",
        )
        session.close()

        assert summary == {"known": 4, "deleted": 2, "errors": 0}
        deleted_keys = {
            c.kwargs["Key"] for c in s3_client.delete_object.call_args_list
        }
        assert deleted_keys == {
            "character_art/1/full-old.webp",
            "character_art/99/full-deleted-char.webp",
        }

    def test_nothing_to_do_when_s3_matches_db(self, client, s3_client):
        session = client._test_session_factory()
        session.add(Character(
            name="Only",
            owner_discord_id=USER_ID,
            art_s3_key="character_art/1/full.webp",
            headshot_s3_key="character_art/1/head.webp",
        ))
        session.commit()
        _stub_pagination(s3_client, [
            "character_art/1/full.webp",
            "character_art/1/head.webp",
        ])
        summary = art_backup.cleanup_orphans(
            session, bucket="b", region="us-east-1",
        )
        session.close()
        assert summary == {"known": 2, "deleted": 0, "errors": 0}
        s3_client.delete_object.assert_not_called()

    def test_all_orphans_when_db_has_no_art(self, client, s3_client):
        """Empty DB art columns + non-empty S3 prefix -> everything deletes."""
        session = client._test_session_factory()
        session.add(Character(name="NoArt", owner_discord_id=USER_ID))
        session.commit()
        _stub_pagination(s3_client, [
            "character_art/1/full-dangling.webp",
            "character_art/1/head-dangling.webp",
        ])
        summary = art_backup.cleanup_orphans(
            session, bucket="b", region="us-east-1",
        )
        session.close()
        assert summary["known"] == 0
        assert summary["deleted"] == 2
        assert summary["errors"] == 0

    def test_delete_failure_counted_not_raised(self, client, s3_client):
        """A per-key delete failure is logged + counted but the sweep
        keeps going so the next orphan still gets deleted."""
        session = client._test_session_factory()
        session.add(Character(name="N", owner_discord_id=USER_ID))
        session.commit()
        _stub_pagination(s3_client, [
            "character_art/1/full-first.webp",
            "character_art/2/full-second.webp",
        ])
        calls = {"n": 0}

        def flaky_delete(**kwargs):
            calls["n"] += 1
            if kwargs["Key"].endswith("first.webp"):
                raise Exception("s3 down")
            return None

        s3_client.delete_object.side_effect = flaky_delete

        summary = art_backup.cleanup_orphans(
            session, bucket="b", region="us-east-1",
        )
        session.close()

        assert summary == {"known": 0, "deleted": 1, "errors": 1}
        # Second key was still attempted despite the first failure
        assert calls["n"] == 2

    def test_ignores_null_keys_in_db(self, client, s3_client):
        """Characters with no art should contribute no known keys - and
        therefore no false-positive retention."""
        session = client._test_session_factory()
        session.add(Character(
            name="HasArt", owner_discord_id=USER_ID,
            art_s3_key="character_art/1/full.webp",
            headshot_s3_key="character_art/1/head.webp",
        ))
        session.add(Character(name="NoArt", owner_discord_id=USER_ID))
        session.commit()
        _stub_pagination(s3_client, [
            "character_art/1/full.webp",
            "character_art/1/head.webp",
        ])
        summary = art_backup.cleanup_orphans(
            session, bucket="b", region="us-east-1",
        )
        session.close()
        assert summary == {"known": 2, "deleted": 0, "errors": 0}


# ---------------------------------------------------------------------------
# Character-delete integration
# ---------------------------------------------------------------------------


class TestCharacterDeleteRemovesArt:
    @patch("app.services.art_storage._get_s3_client")
    def test_delete_character_deletes_art_s3_keys(
        self, mock_client_factory, client, monkeypatch,
    ):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "test-bucket")
        monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")
        s3 = MagicMock()
        mock_client_factory.return_value = s3

        session = client._test_session_factory()
        c = Character(
            name="With Art", owner_discord_id=USER_ID,
            art_s3_key="character_art/5/full-x.webp",
            headshot_s3_key="character_art/5/head-x.webp",
        )
        session.add(c)
        session.commit()
        cid = c.id
        session.close()

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303

        deleted_keys = {
            call.kwargs["Key"] for call in s3.delete_object.call_args_list
        }
        assert deleted_keys == {
            "character_art/5/full-x.webp",
            "character_art/5/head-x.webp",
        }

        # Character row is gone
        session = client._test_session_factory()
        assert session.query(Character).filter(Character.id == cid).first() is None
        session.close()

    @patch("app.services.art_storage._get_s3_client")
    def test_delete_character_without_art_skips_s3(
        self, mock_client_factory, client, monkeypatch,
    ):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "test-bucket")
        session = client._test_session_factory()
        c = Character(name="No Art", owner_discord_id=USER_ID)
        session.add(c)
        session.commit()
        cid = c.id
        session.close()

        client.post(f"/characters/{cid}/delete")
        mock_client_factory.assert_not_called()

    @patch("app.services.art_storage._get_s3_client")
    def test_delete_character_s3_failure_is_non_fatal(
        self, mock_client_factory, client, monkeypatch,
    ):
        """If S3 delete throws, the character row still gets removed so
        the UI is consistent. Orphan cleanup will sweep the leftover
        bytes on the next startup."""
        monkeypatch.setenv("S3_BACKUP_BUCKET", "test-bucket")
        s3 = MagicMock()
        s3.delete_object.side_effect = Exception("s3 unavailable")
        mock_client_factory.return_value = s3

        session = client._test_session_factory()
        c = Character(
            name="Flaky", owner_discord_id=USER_ID,
            art_s3_key="k1", headshot_s3_key="k2",
        )
        session.add(c)
        session.commit()
        cid = c.id
        session.close()

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303

        session = client._test_session_factory()
        assert session.query(Character).filter(Character.id == cid).first() is None
        session.close()

    @patch("app.services.art_storage._get_s3_client")
    def test_delete_character_skips_s3_when_bucket_unconfigured(
        self, mock_client_factory, client, monkeypatch,
    ):
        """With no bucket configured we don't even try - skip silently.
        (Local dev / test-runner case.)"""
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)

        session = client._test_session_factory()
        c = Character(
            name="LocalDev", owner_discord_id=USER_ID,
            art_s3_key="k1", headshot_s3_key="k2",
        )
        session.add(c)
        session.commit()
        cid = c.id
        session.close()

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303
        mock_client_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Startup-thread integration
# ---------------------------------------------------------------------------


class TestStartupThreadSweep:
    def test_sweep_art_orphans_runs_in_startup_path(self, monkeypatch):
        """``_sweep_art_orphans`` opens a DB session, calls cleanup_orphans
        with the bucket/region it's given, and closes the session. A
        cleanup failure is recorded on ``backup_status``."""
        from app import main

        monkeypatch.setattr(main, "backup_status", {
            "last_success": None, "last_error": None, "in_progress": False,
        })

        calls = {"n": 0}

        def fake_cleanup(db, *, bucket, region):
            calls["n"] += 1
            calls["bucket"] = bucket
            calls["region"] = region
            return {"known": 5, "deleted": 0, "errors": 0}

        monkeypatch.setattr(
            "app.services.art_backup.cleanup_orphans", fake_cleanup,
        )
        main._sweep_art_orphans("bucket-x", "us-east-1")
        assert calls["n"] == 1
        assert calls["bucket"] == "bucket-x"
        assert main.backup_status["last_error"] is None

    def test_sweep_art_orphans_records_failure_on_backup_status(
        self, monkeypatch,
    ):
        from app import main
        monkeypatch.setattr(main, "backup_status", {
            "last_success": None, "last_error": None, "in_progress": False,
        })

        def exploding(db, *, bucket, region):
            raise Exception("permissions error")

        monkeypatch.setattr(
            "app.services.art_backup.cleanup_orphans", exploding,
        )
        main._sweep_art_orphans("bucket-x", "us-east-1")
        assert "Art orphan cleanup failed" in main.backup_status["last_error"]
        assert "permissions error" in main.backup_status["last_error"]


class TestSweepStagedArt:
    def test_calls_cleanup_with_24h_cutoff(self, monkeypatch):
        """``_sweep_staged_art`` calls ``art_jobs.cleanup_older_than``
        with a cutoff ~24h in the past. We assert on the cutoff being
        in the right window rather than an exact value, so the test
        doesn't get flaky on slow CI."""
        from datetime import datetime, timedelta, timezone
        from app import main

        captured = {}

        def fake_cleanup(cutoff):
            captured["cutoff"] = cutoff
            return 3

        monkeypatch.setattr(
            "app.services.art_jobs.cleanup_older_than", fake_cleanup,
        )
        main._sweep_staged_art()

        # The recorded cutoff should be very close to 24h ago. Allow
        # a generous 5-minute window for slow runners.
        target = datetime.now(timezone.utc) - timedelta(hours=24)
        assert abs((captured["cutoff"] - target).total_seconds()) < 300

    def test_swallows_cleanup_errors(self, monkeypatch):
        """A sweep failure must not raise - the rest of startup keeps
        running. The error gets logged."""
        from app import main

        def boom(_cutoff):
            raise RuntimeError("disk full")

        monkeypatch.setattr(
            "app.services.art_jobs.cleanup_older_than", boom,
        )
        # Must not raise.
        main._sweep_staged_art()

    def test_runs_during_check_and_backup_before_bucket_short_circuit(
        self, monkeypatch,
    ):
        """Even when ``S3_BACKUP_BUCKET`` is unset (local dev / no
        backups), the staged-art sweep still runs. The backup branch
        below it short-circuits, but the sweep above it does not."""
        from app import main

        monkeypatch.setattr("time.sleep", lambda _seconds: None)
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)

        called = {"n": 0}

        def fake_sweep():
            called["n"] += 1

        monkeypatch.setattr(main, "_sweep_staged_art", fake_sweep)
        main._check_and_backup()
        assert called["n"] == 1
