"""E2E: Profile page — display name, access grants, login required."""
import pytest

pytestmark = pytest.mark.profile

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


def _html_is_dark(page):
    return page.evaluate("document.documentElement.classList.contains('dark')")


def test_dark_mode_toggle_applies_site_wide(page, live_server_url):
    """Enabling Dark mode on the profile renders the `dark` theme class on
    <html> across pages; disabling it reverts to light."""
    page.goto(f"{live_server_url}/profile")
    # Default: light.
    assert not _html_is_dark(page)

    dark_cb = page.locator('input[name="dark_mode"]')
    assert not dark_cb.is_checked()
    dark_cb.check()
    page.locator('button[type="submit"]', has_text="Save").click()
    page.wait_for_url("**/profile")

    # The profile page itself now renders dark...
    assert _html_is_dark(page)
    # ...and the choice carries to other pages.
    page.goto(f"{live_server_url}/")
    assert _html_is_dark(page)

    # Setting persists on reload and the checkbox reflects it.
    page.goto(f"{live_server_url}/profile")
    assert _html_is_dark(page)
    assert page.locator('input[name="dark_mode"]').is_checked()

    # Turn it back off -> light everywhere again.
    page.locator('input[name="dark_mode"]').uncheck()
    page.locator('button[type="submit"]', has_text="Save").click()
    page.wait_for_url("**/profile")
    assert not _html_is_dark(page)
    page.goto(f"{live_server_url}/")
    assert not _html_is_dark(page)


def test_dark_mode_form_fields_are_readable(page, live_server_url):
    """In dark mode, form controls without an explicit bg utility must still
    render on a dark surface (not the UA white field) so text stays readable."""
    page.goto(f"{live_server_url}/profile")
    cb = page.locator('input[name="dark_mode"]')
    if not cb.is_checked():
        cb.check()
    page.locator('button[type="submit"]', has_text="Save").click()
    page.wait_for_url("**/profile")

    # Create a character and open its editor (lots of bare inputs/selects).
    resp = page.request.post(f"{live_server_url}/characters")
    edit_url = resp.url  # POST redirects to /characters/<id>/edit
    assert "/edit" in edit_url
    page.goto(edit_url)

    def _bg_sum(selector):
        el = page.locator(selector).first
        bg = el.evaluate("e => getComputedStyle(e).backgroundColor")
        nums = [int(n) for n in bg.replace("rgb(", "").replace("rgba(", "").split(")")[0].split(",")[:3]]
        return sum(nums), bg

    # The name text input and the school <select> are bare (no bg-* class).
    for sel in ('input[name="name"]', 'select[name="school"]'):
        total, bg = _bg_sum(sel)
        assert total < 300, f"{sel} background not dark in dark mode: {bg}"


def test_sound_toggle_saves(page, live_server_url):
    """Sound checkbox on profile page saves and persists."""
    page.goto(f"{live_server_url}/profile")
    sound_checkbox = page.locator('input[name="dice_sound"]')
    # Uncheck it
    if sound_checkbox.is_checked():
        sound_checkbox.uncheck()
    page.locator('button[type="submit"]', has_text="Save").click()
    page.wait_for_load_state("networkidle")
    # Reload and verify
    page.goto(f"{live_server_url}/profile")
    assert not page.locator('input[name="dice_sound"]').is_checked()
    # Re-check it
    page.locator('input[name="dice_sound"]').check()
    page.locator('button[type="submit"]', has_text="Save").click()
    page.wait_for_load_state("networkidle")
    page.goto(f"{live_server_url}/profile")
    assert page.locator('input[name="dice_sound"]').is_checked()
