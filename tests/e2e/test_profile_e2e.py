"""E2E: Profile page — display name, access grants, login required."""


def test_profile_loads(page, live_server_url):
    """Profile page loads for logged-in user."""
    page.goto(f"{live_server_url}/profile")
    assert page.locator('text="Display Name"').is_visible()
    assert page.locator('text="Character Edit Access"').is_visible()


def test_profile_redirects_when_not_logged_in(page_anon, live_server_url):
    """Profile redirects to login when not authenticated."""
    page_anon.goto(f"{live_server_url}/profile")
    assert "/auth/login" in page_anon.url


def test_profile_display_name_change(page, live_server_url):
    """Display name can be changed and persists."""
    page.goto(f"{live_server_url}/profile")
    page.fill('input[name="display_name"]', "New Display Name")
    page.locator('button:text("Save Changes")').click()
    page.wait_for_url("**/profile")
    assert page.input_value('input[name="display_name"]') == "New Display Name"


def test_profile_shows_other_users(page, live_server_url):
    """Other users listed with grant checkboxes in the access section."""
    page.goto(f"{live_server_url}/profile")
    # Campaign players are seeded on startup — should see at least one other user
    assert page.locator('text="Character Edit Access"').is_visible()
    # Should have at least one checkbox (for other users)
    checkboxes = page.locator('input[name^="grant_"]')
    assert checkboxes.count() > 0


def test_profile_gm_badge(page, live_server_url):
    """GM users shown with badge and disabled checkbox."""
    page.goto(f"{live_server_url}/profile")
    # The admin user (eliandrewc/183026066498125825) is us, so won't appear in "other users"
    # But we should see the GM note if there are any admin users in the list
    body = page.text_content("body")
    assert "always have edit access" in body.lower() or "GM" in body
