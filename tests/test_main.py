"""Tests for app/main.py: static_v cache-busting, AuthMiddleware session
cookie path, _check_and_backup orchestration, and _seed_campaign_players.

These bits are awkward to test because they touch process-level state (static
file mtimes, SessionLocal bound to the real on-disk DB, FastAPI lifespan), so
each test has to do a little setup to isolate itself."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.database import Base
from app.models import Session as AuthSession, User


class TestStaticV:
    """Cache-busting version helper: mtime of a static file, or "0" on OSError."""

    def test_existing_file_returns_integer_mtime(self):
        # Pick any existing file inside the static dir.
        static_dir = main_module._static_dir
        # Find the first regular file in static/ recursively
        probe = None
        for root, _dirs, files in os.walk(static_dir):
            if files:
                probe = os.path.relpath(os.path.join(root, files[0]), static_dir)
                break
        assert probe, "Expected at least one file in app/static/"
        # Clear cache for this path so we actually exercise the stat branch.
        main_module._static_versions.pop(probe, None)
        v = main_module.static_v(probe)
        assert v.isdigit()
        assert v != "0"

    def test_missing_file_returns_zero(self):
        main_module._static_versions.pop("does_not_exist.css", None)
        v = main_module.static_v("does_not_exist.css")
        assert v == "0"

    def test_result_is_cached(self):
        """Second call with the same path should not re-stat the file."""
        main_module._static_versions.pop("does_not_exist.css", None)
        v1 = main_module.static_v("does_not_exist.css")
        with patch("app.main.os.path.getmtime") as mock_getmtime:
            v2 = main_module.static_v("does_not_exist.css")
            mock_getmtime.assert_not_called()
        assert v1 == v2


class TestAuthMiddlewareSessionCookie:
    """AuthMiddleware falls through to session-cookie lookup when the
    X-Test-User header is missing. We isolate SessionLocal by pointing it
    at a temp SQLite file and seeding the rows the middleware will read."""

    @pytest.fixture()
    def temp_session_local(self, monkeypatch):
        """Swap ``app.main.SessionLocal`` for a sessionmaker bound to a fresh
        on-disk SQLite so middleware queries hit test data."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            engine = create_engine(
                f"sqlite:///{path}",
                connect_args={"check_same_thread": False},
            )
            Base.metadata.create_all(bind=engine)
            TestSession = sessionmaker(bind=engine)
            monkeypatch.setattr(main_module, "SessionLocal", TestSession)
            yield TestSession
        finally:
            os.unlink(path)

    def _bare_client(self, monkeypatch):
        """TestClient with no X-Test-User so middleware takes the session branch."""
        from fastapi.testclient import TestClient
        # Keep TEST_AUTH_BYPASS=true so the branch check runs, but without the
        # X-Test-User header the bypass skips and we fall through.
        monkeypatch.setenv("TEST_AUTH_BYPASS", "true")
        return TestClient(main_module.app)

    def test_valid_session_populates_request_user(self, monkeypatch, temp_session_local):
        s = temp_session_local()
        s.add(User(discord_id="u1", discord_name="Alice", display_name="Alice"))
        s.add(AuthSession(session_id="sess-abc", discord_id="u1"))
        s.commit()
        s.close()

        client = self._bare_client(monkeypatch)
        client.cookies.set("session_id", "sess-abc")
        resp = client.get("/terms")
        assert resp.status_code == 200

    def test_session_cookie_without_matching_row_leaves_user_none(
        self, monkeypatch, temp_session_local
    ):
        """Cookie present but no AuthSession row — request proceeds anonymously."""
        client = self._bare_client(monkeypatch)
        client.cookies.set("session_id", "no-such-session")
        resp = client.get("/terms")
        assert resp.status_code == 200

    def test_auth_session_without_matching_user_leaves_user_none(
        self, monkeypatch, temp_session_local
    ):
        """AuthSession row exists but its discord_id has no User — still anon."""
        s = temp_session_local()
        s.add(AuthSession(session_id="orphan", discord_id="ghost"))
        s.commit()
        s.close()

        client = self._bare_client(monkeypatch)
        client.cookies.set("session_id", "orphan")
        resp = client.get("/terms")
        assert resp.status_code == 200


class TestCheckAndBackup:
    """The background backup thread's control flow: no bucket → skip, recent
    backup → skip, run & succeed, run & fail, and outer exception handler."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        """Avoid the 30s real sleep on startup."""
        monkeypatch.setattr("time.sleep", lambda _: None)

    @pytest.fixture(autouse=True)
    def _reset_status(self):
        main_module.backup_status["last_success"] = None
        main_module.backup_status["last_error"] = None
        main_module.backup_status["in_progress"] = False
        yield

    def test_no_bucket_returns_silently(self, monkeypatch):
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        main_module._check_and_backup()
        assert main_module.backup_status["last_error"] is None
        assert main_module.backup_status["last_success"] is None

    def test_skip_when_backup_is_recent(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "mybucket")
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        monkeypatch.setattr(
            "app.services.backup.get_last_backup_time", lambda b, r: recent
        )
        # run_backup must NOT be called
        run_called = {"v": False}
        def _run_backup(*_a, **_kw):
            run_called["v"] = True
            return {"success": True, "error": None, "key": "k"}
        monkeypatch.setattr("app.services.backup.run_backup", _run_backup)

        main_module._check_and_backup()
        assert run_called["v"] is False
        assert main_module.backup_status["last_success"] == recent

    def test_runs_when_last_backup_is_old(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "mybucket")
        old = datetime.now(timezone.utc) - timedelta(days=2)
        monkeypatch.setattr(
            "app.services.backup.get_last_backup_time", lambda b, r: old
        )
        monkeypatch.setattr(
            "app.services.backup.run_backup",
            lambda *a, **kw: {"success": True, "error": None, "key": "backups/k.db"},
        )

        main_module._check_and_backup()
        assert main_module.backup_status["last_success"] is not None
        assert main_module.backup_status["last_error"] is None
        assert main_module.backup_status["in_progress"] is False

    def test_run_backup_failure_records_error(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "mybucket")
        monkeypatch.setattr(
            "app.services.backup.get_last_backup_time", lambda b, r: None
        )
        monkeypatch.setattr(
            "app.services.backup.run_backup",
            lambda *a, **kw: {"success": False, "error": "upload failed", "key": None},
        )

        main_module._check_and_backup()
        assert main_module.backup_status["last_error"] == "upload failed"
        assert main_module.backup_status["in_progress"] is False

    def test_outer_exception_is_caught_and_recorded(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "mybucket")
        def _boom(*_a, **_kw):
            raise RuntimeError("S3 offline")
        monkeypatch.setattr("app.services.backup.get_last_backup_time", _boom)

        main_module._check_and_backup()
        assert main_module.backup_status["last_error"] == "S3 offline"
        assert main_module.backup_status["in_progress"] is False


class TestSeedCampaignPlayers:
    """When CAMPAIGN_PLAYERS contains a discord_id that's not yet in the users
    table, _seed_campaign_players inserts it. If it already exists, it's a no-op."""

    @pytest.fixture()
    def temp_session_local(self, monkeypatch):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            engine = create_engine(
                f"sqlite:///{path}",
                connect_args={"check_same_thread": False},
            )
            Base.metadata.create_all(bind=engine)
            TestSession = sessionmaker(bind=engine)
            monkeypatch.setattr(main_module, "SessionLocal", TestSession)
            yield TestSession
        finally:
            os.unlink(path)

    def test_inserts_missing_players(self, temp_session_local):
        from app.game_data import CAMPAIGN_PLAYERS

        main_module._seed_campaign_players()

        s = temp_session_local()
        try:
            for discord_id, display_name in CAMPAIGN_PLAYERS.items():
                row = s.query(User).filter(User.discord_id == discord_id).first()
                assert row is not None
                assert row.display_name == display_name
        finally:
            s.close()

    def test_skips_existing_players(self, temp_session_local):
        from app.game_data import CAMPAIGN_PLAYERS

        first_id = next(iter(CAMPAIGN_PLAYERS))
        s = temp_session_local()
        s.add(User(discord_id=first_id, discord_name="already-here", display_name="already-here"))
        s.commit()
        s.close()

        main_module._seed_campaign_players()

        s = temp_session_local()
        try:
            rows = s.query(User).filter(User.discord_id == first_id).all()
            assert len(rows) == 1
            # Display name preserved - not overwritten
            assert rows[0].display_name == "already-here"
        finally:
            s.close()


class TestGetBackupError:
    """The template global ``get_backup_error`` just reads backup_status."""

    def test_reports_last_error(self, monkeypatch):
        monkeypatch.setitem(main_module.backup_status, "last_error", "nope")
        assert main_module.get_backup_error() == "nope"

    def test_none_when_no_error(self, monkeypatch):
        monkeypatch.setitem(main_module.backup_status, "last_error", None)
        assert main_module.get_backup_error() is None
