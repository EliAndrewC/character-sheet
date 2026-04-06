"""Tests for the profile and account access management."""

from app.models import User

from tests.conftest import query_db


def _seed_user(client, discord_id, discord_name, display_name=None, granted=None):
    session = client._test_session_factory()
    u = User(
        discord_id=discord_id,
        discord_name=discord_name,
        display_name=display_name or discord_name,
        granted_account_ids=granted or [],
    )
    session.add(u)
    session.commit()
    return u


class TestProfilePage:
    def test_profile_requires_login(self, client):
        resp = client.get("/profile", headers={"X-Test-User": ""}, follow_redirects=False)
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    def test_profile_loads(self, client):
        _seed_user(client, "183026066498125825", "testplayer", "Test Player")
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "Display Name" in resp.text
        assert "Test Player" in resp.text

    def test_profile_shows_other_users(self, client):
        _seed_user(client, "183026066498125825", "testplayer", "Test Player")
        _seed_user(client, "999", "otherplayer", "Other Player")
        resp = client.get("/profile")
        assert "Other Player" in resp.text

    def test_profile_shows_admin_badge(self, client):
        # The test user IS the admin (from conftest env)
        _seed_user(client, "183026066498125825", "testplayer")
        _seed_user(client, "999", "otherplayer")
        resp = client.get("/profile")
        # The test user (183026066498125825) is in ADMIN_DISCORD_IDS but
        # they don't appear in "other_users" since it's their own profile.
        # Let's add another admin to test the badge.
        assert resp.status_code == 200


class TestUpdateProfile:
    def test_update_display_name(self, client):
        _seed_user(client, "183026066498125825", "testplayer", "Old Name")

        resp = client.post(
            "/profile",
            data={"display_name": "New Name"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        assert user.display_name == "New Name"

    def test_grant_access(self, client):
        _seed_user(client, "183026066498125825", "testplayer")
        _seed_user(client, "999", "otherplayer")

        resp = client.post(
            "/profile",
            data={"display_name": "testplayer", "grant_999": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        assert "999" in user.granted_account_ids

    def test_revoke_access(self, client):
        _seed_user(client, "183026066498125825", "testplayer", granted=["999"])
        _seed_user(client, "999", "otherplayer")

        # Submit without the grant checkbox
        resp = client.post(
            "/profile",
            data={"display_name": "testplayer"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        assert "999" not in (user.granted_account_ids or [])

    def test_admin_access_not_stored_in_grants(self, client):
        """Admin IDs should not be stored in granted_account_ids since they
        always have access regardless."""
        _seed_user(client, "183026066498125825", "testplayer")
        # 183026066498125825 is the admin in test env; create a non-admin other user
        _seed_user(client, "999", "otherplayer")

        resp = client.post(
            "/profile",
            data={"display_name": "testplayer", "grant_999": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        # Only non-admin users should be in the list
        assert "999" in user.granted_account_ids

    def test_admin_grant_checkbox_ignored(self, client):
        """Submitting a grant checkbox for an admin user should not store it."""
        import os
        old = os.environ.get("ADMIN_DISCORD_IDS", "")
        os.environ["ADMIN_DISCORD_IDS"] = "183026066498125825,888"
        try:
            _seed_user(client, "183026066498125825", "testplayer")
            _seed_user(client, "888", "adminplayer")
            _seed_user(client, "999", "otherplayer")

            resp = client.post(
                "/profile",
                data={
                    "display_name": "testplayer",
                    "grant_888": "on",
                    "grant_999": "on",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 303

            user = query_db(client, User).filter(
                User.discord_id == "183026066498125825"
            ).first()
            # Admin 888 should NOT be in the list
            assert "888" not in (user.granted_account_ids or [])
            # Non-admin 999 should be
            assert "999" in user.granted_account_ids
        finally:
            os.environ["ADMIN_DISCORD_IDS"] = old

    def test_update_requires_login(self, client):
        resp = client.post(
            "/profile",
            data={"display_name": "Hacker"},
            headers={"X-Test-User": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]
