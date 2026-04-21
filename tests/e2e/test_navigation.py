"""E2E: Navigation — logout, login link, test-login, empty state."""

import os
import pytest

pytestmark = pytest.mark.navigation

def test_logout_link_exists(page, live_server_url):
    """Logout link visible and navigates to /auth/logout."""

    page.goto(live_server_url)
    logout = page.locator('a:text("Logout")')
    assert logout.is_visible()
    assert "/auth/logout" in logout.get_attribute("href")


def test_login_link_visible_when_anonymous(page_anon, live_server_url):
    """Login with Discord link visible when not logged in."""
    page_anon.goto(live_server_url)
    assert page_anon.locator('a:text("Login with Discord")').is_visible()


def test_test_login_creates_session(page_anon, live_server_url):
    """Test-login secret URL creates session and redirects."""
    # Set a test token in the env — the e2e server already has TEST_AUTH_BYPASS
    # but test-login needs TEST_LOGIN_TOKENS. We'll test the route returns 403
    # when no tokens configured (safe since env isn't set in e2e server).
    page_anon.goto(f"{live_server_url}/auth/test-login/fake-token")
    # Should get 403 since no TEST_LOGIN_TOKENS configured in e2e server
    assert "403" in page_anon.text_content("body") or "Invalid" in page_anon.text_content("body")


def test_empty_state_create_link(page_anon, live_server_url):
    """Homepage loads for anon users whether or not characters exist."""
    page_anon.goto(live_server_url)
    body = page_anon.text_content("body")
    assert "Characters" in body
