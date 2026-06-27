"""Tests for the Dark Mode appearance preference.

Covers the ``dark_mode_enabled`` render helper (account preference with a
cookie fallback), the ``POST /profile`` persistence + cookie, and that
base.html actually emits the ``dark`` class on <html>.
"""

from types import SimpleNamespace

from app.main import dark_mode_enabled
from app.models import User

from tests.conftest import query_db


def _req(user=None, cookies=None):
    """Build a minimal stand-in for a Starlette Request for the helper."""
    return SimpleNamespace(
        state=SimpleNamespace(user=user),
        cookies=cookies or {},
    )


def _seed_user(client, discord_id, discord_name, preferences=None):
    session = client._test_session_factory()
    u = User(
        discord_id=discord_id,
        discord_name=discord_name,
        display_name=discord_name,
        preferences=preferences or {},
    )
    session.add(u)
    session.commit()
    return u


class TestDarkModeHelper:
    def test_account_pref_true_wins(self):
        req = _req(user={"preferences": {"dark_mode_enabled": True}})
        assert dark_mode_enabled(req) is True

    def test_account_pref_false_wins_over_cookie(self):
        # A real session knows the preference; a stale cookie must not flip it.
        req = _req(
            user={"preferences": {"dark_mode_enabled": False}},
            cookies={"dark_mode": "1"},
        )
        assert dark_mode_enabled(req) is False

    def test_account_pref_missing_key_defaults_off(self):
        req = _req(user={"preferences": {}})
        assert dark_mode_enabled(req) is False

    def test_cookie_fallback_when_prefs_unknown(self):
        # Test-bypass / logged-out: no preferences dict -> consult the cookie.
        req = _req(user={"discord_id": "1"}, cookies={"dark_mode": "1"})
        assert dark_mode_enabled(req) is True

    def test_cookie_off_when_prefs_unknown(self):
        req = _req(user={"discord_id": "1"}, cookies={"dark_mode": "0"})
        assert dark_mode_enabled(req) is False

    def test_logged_out_no_cookie_defaults_off(self):
        assert dark_mode_enabled(_req(user=None)) is False

    def test_logged_out_with_cookie(self):
        assert dark_mode_enabled(_req(user=None, cookies={"dark_mode": "1"})) is True


class TestProfileDarkModePersistence:
    def test_save_enables_dark_mode_and_sets_cookie(self, client):
        _seed_user(client, "183026066498125825", "testplayer")
        resp = client.post(
            "/profile",
            data={"display_name": "testplayer", "dark_mode": "on"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        assert user.preferences.get("dark_mode_enabled") is True
        # Cookie mirrors the choice for cookie-fallback rendering.
        assert resp.cookies.get("dark_mode") == "1"

    def test_save_disables_dark_mode_and_clears_cookie(self, client):
        _seed_user(
            client, "183026066498125825", "testplayer",
            preferences={"dark_mode_enabled": True},
        )
        # Submit the form without the dark_mode checkbox => unchecked.
        resp = client.post(
            "/profile",
            data={"display_name": "testplayer"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        assert user.preferences.get("dark_mode_enabled") is False
        assert resp.cookies.get("dark_mode") == "0"

    def test_dark_mode_does_not_clobber_dice_prefs(self, client):
        _seed_user(client, "183026066498125825", "testplayer")
        resp = client.post(
            "/profile",
            data={
                "display_name": "testplayer",
                "dark_mode": "on",
                "dice_animation": "on",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        user = query_db(client, User).filter(
            User.discord_id == "183026066498125825"
        ).first()
        assert user.preferences.get("dark_mode_enabled") is True
        assert user.preferences.get("dice_animation_enabled") is True
        assert user.preferences.get("dice_sound_enabled") is False


class TestProfileDarkModeUI:
    def test_checkbox_unchecked_by_default(self, client):
        _seed_user(client, "183026066498125825", "testplayer")
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert 'name="dark_mode"' in resp.text
        # No checked attribute on the dark_mode input when the pref is off.
        marker = resp.text.split('name="dark_mode"', 1)[1].split(">", 1)[0]
        assert "checked" not in marker

    def test_checkbox_checked_when_enabled(self, client):
        _seed_user(
            client, "183026066498125825", "testplayer",
            preferences={"dark_mode_enabled": True},
        )
        resp = client.get("/profile")
        assert resp.status_code == 200
        marker = resp.text.split('name="dark_mode"', 1)[1].split(">", 1)[0]
        assert "checked" in marker


class TestDarkClassRendering:
    def test_dark_class_present_with_cookie(self, client):
        client.cookies.set("dark_mode", "1")
        resp = client.get("/")
        assert resp.status_code == 200
        assert '<html lang="en" class="dark">' in resp.text

    def test_no_dark_class_without_cookie(self, client):
        client.cookies.set("dark_mode", "0")
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'class="dark"' not in resp.text
        assert '<html lang="en">' in resp.text

    def test_stylesheet_is_cache_busted(self, client):
        """app.css must be versioned so a rebuilt stylesheet (e.g. new dark-mode
        rules) isn't served from a stale browser cache."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "/static/css/app.css?v=" in resp.text
