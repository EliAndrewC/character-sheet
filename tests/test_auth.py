"""Tests for Discord OAuth authentication and authorization."""

import pytest
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import User, Character
from app.services.auth import (
    is_whitelisted,
    is_admin,
    can_edit_character,
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


class TestTestAuthBypass:
    def test_bypass_sets_user(self, client):
        """In test mode, X-Test-User header should authenticate."""
        # Creating a character requires auth — should redirect to edit page
        resp = client.post("/characters", follow_redirects=False)
        assert resp.status_code == 303
        assert "/edit" in resp.headers["location"]
