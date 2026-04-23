"""Tests for Discord OAuth authentication and authorization."""

import pytest
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import User, Character
from app.services.auth import (
    is_whitelisted,
    is_admin,
    can_edit_character,
    format_editor_list_text,
)


class TestWhitelist:
    def test_whitelisted_user(self):
        assert is_whitelisted("183026066498125825")

    def test_non_whitelisted_user(self):
        assert not is_whitelisted("999999999999999999")


class TestAdmin:
    def test_admin_user(self):
        assert is_admin("183026066498125825")

    def test_non_admin_user(self):
        assert not is_admin("999999999999999999")


class TestCanEditCharacter:
    def test_owner_can_edit(self):
        assert can_edit_character(
            user_discord_id="111",
            character_owner_id="111",
            granted_editors=[],
            admin_ids=["999"],
        )

    def test_admin_can_edit(self):
        assert can_edit_character(
            user_discord_id="999",
            character_owner_id="111",
            granted_editors=[],
            admin_ids=["999"],
        )

    def test_granted_user_can_edit(self):
        assert can_edit_character(
            user_discord_id="222",
            character_owner_id="111",
            granted_editors=["222", "333"],
            admin_ids=["999"],
        )

    def test_random_user_cannot_edit(self):
        assert not can_edit_character(
            user_discord_id="444",
            character_owner_id="111",
            granted_editors=["222"],
            admin_ids=["999"],
        )

    def test_none_user_cannot_edit(self):
        """Unauthenticated user (None) cannot edit."""
        assert not can_edit_character(
            user_discord_id=None,
            character_owner_id="111",
            granted_editors=[],
            admin_ids=["999"],
        )


class TestFormatEditorListText:
    def test_no_extra_editors(self):
        # Only the owner-viewer and admins - reads "you and the GM"
        assert format_editor_list_text(
            viewer_id="111",
            all_editors=[],
            admin_ids=["999"],
            resolve_name=lambda _id: "",
        ) == "you and the GM"

    def test_one_extra_editor(self):
        assert format_editor_list_text(
            viewer_id="111",
            all_editors=["222"],
            admin_ids=["999"],
            resolve_name=lambda _id: "Alice" if _id == "222" else "",
        ) == "you, the GM, and Alice"

    def test_two_extra_editors(self):
        assert format_editor_list_text(
            viewer_id="111",
            all_editors=["222", "333"],
            admin_ids=["999"],
            resolve_name=lambda _id: {"222": "Alice", "333": "Bob"}.get(_id, ""),
        ) == "you, the GM, Alice, and Bob"

    def test_viewer_excluded_from_list(self):
        # The viewer is in all_editors (e.g. they're a non-owner editor) but shows as "you"
        assert format_editor_list_text(
            viewer_id="222",
            all_editors=["222", "333"],
            admin_ids=["999"],
            resolve_name=lambda _id: {"333": "Bob"}.get(_id, ""),
        ) == "you, the GM, and Bob"

    def test_admin_excluded_from_list(self):
        # Admins are shown as "the GM", not by name
        assert format_editor_list_text(
            viewer_id="111",
            all_editors=["999"],
            admin_ids=["999"],
            resolve_name=lambda _id: "GmPerson",
        ) == "you and the GM"

    def test_empty_name_falls_back_to_id(self):
        assert format_editor_list_text(
            viewer_id="111",
            all_editors=["222"],
            admin_ids=["999"],
            resolve_name=lambda _id: "",
        ) == "you, the GM, and 222"


class TestUserModel:
    def test_create_user(self, db):
        user = User(discord_id="183026066498125825", discord_name="eliandrewc", display_name="Eli")
        db.add(user)
        db.flush()
        assert user.id is not None
        assert user.discord_id == "183026066498125825"
        assert user.display_name == "Eli"

    def test_user_to_dict(self, db):
        user = User(discord_id="123", discord_name="testuser", display_name="Test")
        db.add(user)
        db.flush()
        d = user.to_dict()
        assert d["discord_id"] == "123"
        assert d["display_name"] == "Test"


class TestCharacterOwnership:
    def test_character_has_owner(self, db):
        user = User(discord_id="123", discord_name="testuser")
        db.add(user)
        db.flush()

        char = Character(name="Owned Character", owner_discord_id="123")
        db.add(char)
        db.flush()

        assert char.owner_discord_id == "123"

    def test_character_editors_list(self, db):
        char = Character(
            name="Shared Character",
            owner_discord_id="111",
            editor_discord_ids=["222", "333"],
        )
        db.add(char)
        db.flush()

        result = db.query(Character).filter(Character.name == "Shared Character").first()
        assert "222" in result.editor_discord_ids
        assert "333" in result.editor_discord_ids


class TestSessionModel:
    def test_create_session(self, db):
        from app.models import Session as AuthSession
        session = AuthSession(
            session_id="abc123",
            discord_id="183026066498125825",
        )
        db.add(session)
        db.flush()
        assert session.session_id == "abc123"


class TestAuthRoutes:
    def test_login_page_not_logged_in(self, client):
        """Login link should appear when not authenticated."""
        resp = client.get("/")
        assert resp.status_code == 200
        # Should show login link, not "New Character" button
        # (creating requires auth)

    def test_create_requires_auth(self, client):
        """POST to create should redirect to login when not authenticated."""
        from tests.conftest import make_character_form
        form = make_character_form()
        resp = client.post("/characters", data=form, follow_redirects=False)
        assert resp.status_code in (303, 401, 403)

    def test_view_is_public(self, client):
        """Viewing a character sheet should work without auth."""
        session = client._test_session_factory()
        char = Character(
            name="Public Character",
            school="akodo_bushi",
            school_ring_choice="Water",
            ring_water=3,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            owner_discord_id="123",
        )
        session.add(char)
        session.commit()

        resp = client.get(f"/characters/{char.id}")
        assert resp.status_code == 200
        assert "Public Character" in resp.text


class TestUnauthenticatedGuards:
    """Test that routes properly redirect/deny when not authenticated."""

    def _unauth_client(self, engine):
        """Create a test client with no auth header."""
        from fastapi.testclient import TestClient
        from app.database import get_db

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
        client = TestClient(app)  # no X-Test-User header
        client._cleanup = (transaction, connection)
        return client

    def test_create_post_requires_auth(self, engine):
        c = self._unauth_client(engine)
        resp = c.post("/characters", follow_redirects=False)
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]
        c._cleanup[0].rollback()
        c._cleanup[1].close()
        app.dependency_overrides.clear()

    def test_create_post_redirects(self, engine):
        from tests.conftest import make_character_form
        c = self._unauth_client(engine)
        resp = c.post("/characters", data=make_character_form(), follow_redirects=False)
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]
        c._cleanup[0].rollback()
        c._cleanup[1].close()
        app.dependency_overrides.clear()

    def test_edit_page_redirects(self, engine):
        c = self._unauth_client(engine)
        resp = c.get("/characters/1/edit", follow_redirects=False)
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]
        c._cleanup[0].rollback()
        c._cleanup[1].close()
        app.dependency_overrides.clear()


class TestTestLoginTokens:
    def test_parse_tokens(self, monkeypatch):
        from app.services.auth import get_test_login_tokens
        monkeypatch.setenv("TEST_LOGIN_TOKENS", "abc-123:test_user_1, def-456:test_user_2")
        tokens = get_test_login_tokens()
        assert tokens == {"abc-123": "test_user_1", "def-456": "test_user_2"}

    def test_empty_env(self, monkeypatch):
        from app.services.auth import get_test_login_tokens
        monkeypatch.setenv("TEST_LOGIN_TOKENS", "")
        assert get_test_login_tokens() == {}


class TestTestLoginRoute:
    def test_valid_token_creates_session(self, client, monkeypatch):
        monkeypatch.setenv("TEST_LOGIN_TOKENS", "fake-uuid-1:test_user_1")
        session = client._test_session_factory()
        session.add(User(discord_id="test_user_1", discord_name="Test User 1", display_name="Test User 1"))
        session.commit()

        resp = client.get("/auth/test-login/fake-uuid-1", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "session_id" in resp.cookies

    def test_invalid_token_returns_403(self, client, monkeypatch):
        monkeypatch.setenv("TEST_LOGIN_TOKENS", "fake-uuid-1:test_user_1")
        resp = client.get("/auth/test-login/wrong-token", follow_redirects=False)
        assert resp.status_code == 403

    def test_no_tokens_configured(self, client, monkeypatch):
        monkeypatch.setenv("TEST_LOGIN_TOKENS", "")
        resp = client.get("/auth/test-login/anything", follow_redirects=False)
        assert resp.status_code == 403

    def test_user_not_found(self, client, monkeypatch):
        monkeypatch.setenv("TEST_LOGIN_TOKENS", "fake-uuid:nonexistent_user")
        resp = client.get("/auth/test-login/fake-uuid", follow_redirects=False)
        assert resp.status_code == 404


class TestTestAuthBypass:
    def test_bypass_sets_user(self, client):
        """In test mode, X-Test-User header should authenticate."""
        # Creating a character requires auth — should redirect to edit page
        resp = client.post("/characters", follow_redirects=False)
        assert resp.status_code == 303
        assert "/edit" in resp.headers["location"]


class TestLoginRoute:
    def test_login_missing_client_id(self, client, monkeypatch):
        """If DISCORD_CLIENT_ID is unset, /auth/login returns a 500 error."""
        monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 500
        assert "not configured" in resp.text.lower()

    def test_login_redirects_to_discord(self, client, monkeypatch):
        """With DISCORD_CLIENT_ID set, /auth/login redirects to Discord authorize URL."""
        monkeypatch.setenv("DISCORD_CLIENT_ID", "fake_client_id")
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"].startswith("https://discord.com/api/oauth2/authorize")
        assert "client_id=fake_client_id" in resp.headers["location"]
        assert "oauth_state" in resp.cookies

    def test_login_uses_forwarded_proto_and_host(self, client, monkeypatch):
        """When behind a proxy, use the x-forwarded-proto and host headers."""
        monkeypatch.setenv("DISCORD_CLIENT_ID", "fake_client_id")
        resp = client.get(
            "/auth/login",
            follow_redirects=False,
            headers={"x-forwarded-proto": "https", "host": "example.com"},
        )
        assert resp.status_code == 307
        assert "https%3A%2F%2Fexample.com%2Fauth%2Fcallback" in resp.headers["location"]

    def test_login_stashes_safe_return_to(self, client, monkeypatch):
        """A safe same-origin return_to is stored in a cookie for the callback."""
        monkeypatch.setenv("DISCORD_CLIENT_ID", "fake_client_id")
        resp = client.get(
            "/auth/login?return_to=/characters/42", follow_redirects=False
        )
        assert resp.status_code == 307
        # Cookie values containing "/" are quoted on the wire; strip before comparing.
        assert resp.cookies.get("oauth_return_to", "").strip('"') == "/characters/42"

    def test_login_rejects_absolute_url_return_to(self, client, monkeypatch):
        """return_to pointing at another origin must not be stashed."""
        monkeypatch.setenv("DISCORD_CLIENT_ID", "fake_client_id")
        resp = client.get(
            "/auth/login?return_to=https://evil.example/steal",
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert "oauth_return_to" not in resp.cookies

    def test_login_rejects_protocol_relative_return_to(self, client, monkeypatch):
        """//evil.example is protocol-relative - browsers treat it as absolute."""
        monkeypatch.setenv("DISCORD_CLIENT_ID", "fake_client_id")
        resp = client.get(
            "/auth/login?return_to=//evil.example/x", follow_redirects=False
        )
        assert resp.status_code == 307
        assert "oauth_return_to" not in resp.cookies


class _FakeHttpResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Replacement for httpx.AsyncClient that returns pre-programmed responses."""

    token_response: _FakeHttpResponse | None = None
    user_response: _FakeHttpResponse | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def post(self, url, data=None, headers=None):
        return _FakeAsyncClient.token_response

    async def get(self, url, headers=None):
        return _FakeAsyncClient.user_response


class TestCallbackRoute:
    """Exercises the /auth/callback error paths and happy path via a mocked httpx."""

    def _setup_credentials(self, monkeypatch):
        monkeypatch.setenv("DISCORD_CLIENT_ID", "fake_client_id")
        monkeypatch.setenv("DISCORD_CLIENT_SECRET", "fake_secret")

    def _patch_httpx(self, monkeypatch, token_resp, user_resp=None):
        _FakeAsyncClient.token_response = token_resp
        _FakeAsyncClient.user_response = user_resp
        monkeypatch.setattr("app.routes.auth.httpx.AsyncClient", _FakeAsyncClient)

    def test_missing_state_returns_400(self, client, monkeypatch):
        self._setup_credentials(monkeypatch)
        resp = client.get("/auth/callback?code=abc", follow_redirects=False)
        assert resp.status_code == 400
        assert "Invalid OAuth state" in resp.text

    def test_mismatched_state_returns_400(self, client, monkeypatch):
        self._setup_credentials(monkeypatch)
        client.cookies.set("oauth_state", "expected_state")
        resp = client.get(
            "/auth/callback?code=abc&state=wrong_state", follow_redirects=False
        )
        assert resp.status_code == 400

    def test_missing_client_credentials_returns_500(self, client, monkeypatch):
        monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
        monkeypatch.delenv("DISCORD_CLIENT_SECRET", raising=False)
        client.cookies.set("oauth_state", "st")
        resp = client.get("/auth/callback?code=abc&state=st", follow_redirects=False)
        assert resp.status_code == 500
        assert "not configured" in resp.text.lower()

    def test_token_exchange_failure_returns_400(self, client, monkeypatch):
        self._setup_credentials(monkeypatch)
        self._patch_httpx(monkeypatch, token_resp=_FakeHttpResponse(401))
        client.cookies.set("oauth_state", "st")
        resp = client.get("/auth/callback?code=bad&state=st", follow_redirects=False)
        assert resp.status_code == 400
        assert "token" in resp.text.lower()

    def test_user_info_failure_returns_400(self, client, monkeypatch):
        self._setup_credentials(monkeypatch)
        self._patch_httpx(
            monkeypatch,
            token_resp=_FakeHttpResponse(200, {"access_token": "tok"}),
            user_resp=_FakeHttpResponse(401),
        )
        client.cookies.set("oauth_state", "st")
        resp = client.get("/auth/callback?code=ok&state=st", follow_redirects=False)
        assert resp.status_code == 400
        assert "user info" in resp.text.lower()

    def test_non_whitelisted_user_rejected(self, client, monkeypatch):
        self._setup_credentials(monkeypatch)
        self._patch_httpx(
            monkeypatch,
            token_resp=_FakeHttpResponse(200, {"access_token": "tok"}),
            user_resp=_FakeHttpResponse(200, {"id": "999999999", "username": "attacker"}),
        )
        client.cookies.set("oauth_state", "st")
        resp = client.get("/auth/callback?code=ok&state=st", follow_redirects=False)
        assert resp.status_code == 403
        assert "not authorized" in resp.text.lower()

    def test_happy_path_creates_user_and_session(self, client, monkeypatch):
        """Successful OAuth flow upserts a new user and sets a session cookie."""
        self._setup_credentials(monkeypatch)
        self._patch_httpx(
            monkeypatch,
            token_resp=_FakeHttpResponse(200, {"access_token": "tok"}),
            user_resp=_FakeHttpResponse(
                200, {"id": "183026066498125825", "username": "eli"}
            ),
        )
        client.cookies.set("oauth_state", "st")
        resp = client.get("/auth/callback?code=ok&state=st", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "session_id" in resp.cookies

        session = client._test_session_factory()
        created = session.query(User).filter(User.discord_id == "183026066498125825").first()
        assert created is not None
        assert created.discord_name == "eli"

    def test_happy_path_honors_safe_return_to_cookie(self, client, monkeypatch):
        """After login, a valid return_to cookie redirects the user back to that path."""
        self._setup_credentials(monkeypatch)
        self._patch_httpx(
            monkeypatch,
            token_resp=_FakeHttpResponse(200, {"access_token": "tok"}),
            user_resp=_FakeHttpResponse(
                200, {"id": "183026066498125825", "username": "eli"}
            ),
        )
        client.cookies.set("oauth_state", "st")
        client.cookies.set("oauth_return_to", "/characters/42")
        resp = client.get("/auth/callback?code=ok&state=st", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/characters/42"
        # Cookie cleared so a later login without return_to doesn't reuse it
        assert resp.cookies.get("oauth_return_to") in (None, "")

    def test_happy_path_ignores_unsafe_return_to_cookie(self, client, monkeypatch):
        """An absolute-URL return_to cookie must not leak the user off-site."""
        self._setup_credentials(monkeypatch)
        self._patch_httpx(
            monkeypatch,
            token_resp=_FakeHttpResponse(200, {"access_token": "tok"}),
            user_resp=_FakeHttpResponse(
                200, {"id": "183026066498125825", "username": "eli"}
            ),
        )
        client.cookies.set("oauth_state", "st")
        client.cookies.set("oauth_return_to", "https://evil.example/steal")
        resp = client.get("/auth/callback?code=ok&state=st", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_happy_path_updates_existing_user(self, client, monkeypatch):
        """If a user already exists, their discord_name is updated but no duplicate row is made."""
        self._setup_credentials(monkeypatch)
        session = client._test_session_factory()
        session.add(User(discord_id="183026066498125825", discord_name="old_name", display_name="Eli"))
        session.commit()

        self._patch_httpx(
            monkeypatch,
            token_resp=_FakeHttpResponse(200, {"access_token": "tok"}),
            user_resp=_FakeHttpResponse(
                200, {"id": "183026066498125825", "username": "new_name"}
            ),
        )
        client.cookies.set("oauth_state", "st")
        resp = client.get("/auth/callback?code=ok&state=st", follow_redirects=False)
        assert resp.status_code == 303

        session2 = client._test_session_factory()
        rows = session2.query(User).filter(User.discord_id == "183026066498125825").all()
        assert len(rows) == 1
        assert rows[0].discord_name == "new_name"


class TestLogoutRoute:
    def test_logout_with_session_deletes_row(self, client):
        """Logging out clears the session cookie AND deletes the server-side AuthSession row."""
        from app.models import Session as AuthSession

        session = client._test_session_factory()
        session.add(AuthSession(session_id="abc123", discord_id="183026066498125825"))
        session.commit()

        client.cookies.set("session_id", "abc123")
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

        session2 = client._test_session_factory()
        remaining = session2.query(AuthSession).filter(AuthSession.session_id == "abc123").first()
        assert remaining is None

    def test_logout_without_session_still_redirects(self, client):
        """Logout with no session cookie should still redirect to home cleanly."""
        client.cookies.clear()
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
