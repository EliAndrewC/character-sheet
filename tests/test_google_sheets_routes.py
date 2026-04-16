"""Unit tests for app.routes.google_sheets (Google OAuth + export routes)."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.conftest import make_character_data, query_db
from app.models import Character


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_character(client) -> int:
    """Create a character via POST and return its ID."""
    resp = client.post("/characters", data={"name": "Export Test", "player_name": "Tester"})
    assert resp.status_code in (200, 303)
    char = query_db(client).first()
    return char.id


# ---------------------------------------------------------------------------
# Export start endpoint
# ---------------------------------------------------------------------------

class TestExportStart:
    def test_redirects_to_google(self, client):
        char_id = _create_character(client)
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client-id"}):
            resp = client.get(f"/auth/google/export/{char_id}", follow_redirects=False)
        assert resp.status_code == 200
        body = resp.text
        assert "accounts.google.com" in body
        assert "test-client-id" in body

    def test_sets_cookies(self, client):
        char_id = _create_character(client)
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client-id"}):
            resp = client.get(f"/auth/google/export/{char_id}", follow_redirects=False)
        cookies = {c.name: c.value for c in resp.cookies.jar}
        assert "google_oauth_state" in cookies
        assert cookies.get("google_export_char_id") == str(char_id)

    def test_unauthenticated_redirects_to_login(self, engine):
        """Unauthenticated user gets redirected to Discord login."""
        from fastapi.testclient import TestClient
        from sqlalchemy.orm import sessionmaker
        from app.database import get_db
        from app.main import app

        connection = engine.connect()
        transaction = connection.begin()
        TestSession = sessionmaker(bind=connection)

        def _override():
            s = TestSession()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = _override
        # No X-Test-User header = unauthenticated
        with TestClient(app) as c:
            resp = c.get("/auth/google/export/1", follow_redirects=False)
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

        transaction.rollback()
        connection.close()
        app.dependency_overrides.clear()

    def test_character_not_found(self, client):
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client-id"}):
            resp = client.get("/auth/google/export/99999", follow_redirects=False)
        assert resp.status_code == 404

    def test_missing_google_credentials(self, client):
        char_id = _create_character(client)
        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": ""}, clear=False):
            resp = client.get(f"/auth/google/export/{char_id}", follow_redirects=False)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Callback endpoint
# ---------------------------------------------------------------------------

class TestCallback:
    def test_invalid_state_returns_error(self, client):
        char_id = _create_character(client)
        # Set cookies manually
        client.cookies.set("google_oauth_state", "correct-state")
        client.cookies.set("google_export_char_id", str(char_id))
        resp = client.get(
            "/auth/google/callback?code=test-code&state=wrong-state",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "sheets_error=expired" in resp.headers["location"]

    def test_missing_char_id_cookie(self, client):
        client.cookies.set("google_oauth_state", "test-state")
        # No google_export_char_id cookie
        resp = client.get(
            "/auth/google/callback?code=test-code&state=test-state",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "sheets_error=expired" in resp.headers["location"]

    def test_google_error_param(self, client):
        char_id = _create_character(client)
        client.cookies.set("google_oauth_state", "test-state")
        client.cookies.set("google_export_char_id", str(char_id))
        resp = client.get(
            "/auth/google/callback?error=access_denied&state=test-state",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "sheets_error=auth_failed" in resp.headers["location"]

    @patch("app.routes.google_sheets.httpx.AsyncClient")
    def test_token_exchange_failure(self, mock_client_cls, client):
        char_id = _create_character(client)
        state = "test-state"
        client.cookies.set("google_oauth_state", state)
        client.cookies.set("google_export_char_id", str(char_id))

        # Mock failed token exchange
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "invalid_grant"}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            resp = client.get(
                f"/auth/google/callback?code=bad-code&state={state}",
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert "sheets_error=auth_failed" in resp.headers["location"]

    @patch("app.routes.google_sheets.create_spreadsheet")
    @patch("app.routes.google_sheets.httpx.AsyncClient")
    def test_successful_export(self, mock_client_cls, mock_create, client):
        char_id = _create_character(client)
        state = "test-state"
        client.cookies.set("google_oauth_state", state)
        client.cookies.set("google_export_char_id", str(char_id))

        # Mock successful token exchange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "fake-token"}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        # Mock sheet creation
        mock_create.return_value = "https://docs.google.com/spreadsheets/d/abc123/edit"

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            resp = client.get(
                f"/auth/google/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert "sheets_url=" in resp.headers["location"]
        mock_create.assert_called_once()

    @patch("app.routes.google_sheets.create_spreadsheet")
    @patch("app.routes.google_sheets.httpx.AsyncClient")
    def test_stores_sheet_id(self, mock_client_cls, mock_create, client):
        char_id = _create_character(client)
        state = "test-state"
        client.cookies.set("google_oauth_state", state)
        client.cookies.set("google_export_char_id", str(char_id))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "fake-token"}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        mock_create.return_value = "https://docs.google.com/spreadsheets/d/sheet123/edit"

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            client.get(
                f"/auth/google/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )

        # Verify sheet ID and exported state were stored
        char = query_db(client).filter(Character.id == char_id).first()
        assert char.google_sheet_id == "sheet123"
        assert char.google_sheet_exported_state is not None
        assert "name" in char.google_sheet_exported_state
        # Immediately after export, sheet should not be stale
        assert char.google_sheet_is_stale is False

    @patch("app.routes.google_sheets.create_spreadsheet")
    @patch("app.routes.google_sheets.httpx.AsyncClient")
    def test_stale_after_change(self, mock_client_cls, mock_create, client):
        char_id = _create_character(client)
        state = "test-state"
        client.cookies.set("google_oauth_state", state)
        client.cookies.set("google_export_char_id", str(char_id))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "fake-token"}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        mock_create.return_value = "https://docs.google.com/spreadsheets/d/sheet456/edit"

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            client.get(
                f"/auth/google/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )

        # Modify the character
        char = query_db(client).filter(Character.id == char_id).first()
        char.name = "Changed Name"
        session = client._test_session_factory()
        session.merge(char)
        session.commit()

        # Re-query and check staleness
        char = query_db(client).filter(Character.id == char_id).first()
        assert char.google_sheet_is_stale is True

    @patch("app.routes.google_sheets.create_spreadsheet")
    @patch("app.routes.google_sheets.httpx.AsyncClient")
    def test_api_failure_returns_error(self, mock_client_cls, mock_create, client):
        char_id = _create_character(client)
        state = "test-state"
        client.cookies.set("google_oauth_state", state)
        client.cookies.set("google_export_char_id", str(char_id))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "fake-token"}

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        # Mock sheet creation failure
        mock_create.side_effect = Exception("Google API error")

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            resp = client.get(
                f"/auth/google/callback?code=valid-code&state={state}",
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert "sheets_error=api_failed" in resp.headers["location"]
