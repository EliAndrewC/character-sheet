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
