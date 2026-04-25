"""E2E: Permission-based visibility — edit/delete buttons, version history, owner dropdown."""

from tests.e2e.helpers import create_and_apply, start_new_character
import pytest

pytestmark = pytest.mark.permissions

def test_edit_delete_visible_for_editor(page, live_server_url):
    """Edit and Delete buttons visible when viewer has edit permission."""

    create_and_apply(page, live_server_url, "Editable Char")
    assert page.locator('a:text-is("Edit")').is_visible()
    assert page.locator('button:text("Delete")').is_visible()


def test_edit_delete_hidden_for_nonadmin(page, page_nonadmin, live_server_url):
    """Edit and Delete buttons hidden for non-editor viewers."""
    url = create_and_apply(page, live_server_url, "Not My Char")
    page_nonadmin.goto(url)
    page_nonadmin.wait_for_selector("h1")
    assert "Not My Char" in page_nonadmin.text_content("h1")
    assert not page_nonadmin.locator('a:text-is("Edit")').is_visible()
    assert not page_nonadmin.locator('button:text("Delete")').is_visible()


def test_version_history_hidden_for_nonadmin(page, page_nonadmin, live_server_url):
    """Version history section hidden for non-editor viewers."""
    url = create_and_apply(page, live_server_url, "History Hidden")
    page_nonadmin.goto(url)
    page_nonadmin.wait_for_selector("h1")
    assert not page_nonadmin.locator('text="Version History"').is_visible()


def test_character_visible_to_nonadmin(page, page_nonadmin, live_server_url):
    """Character data still visible to non-editor viewers."""
    url = create_and_apply(page, live_server_url, "Viewable Char")
    page_nonadmin.goto(url)
    page_nonadmin.wait_for_selector("h1")
    assert "Viewable Char" in page_nonadmin.text_content("h1")


def test_tracking_buttons_local_only_for_nonadmin(page, page_nonadmin, live_server_url):
    """Read-only Roll Mode (Phases 2-4): Tracking +/- buttons RENDER for
    non-editor viewers, but mutations are client-local only - the
    Phase 1 save shim short-circuits the /track POST and the read-only
    banner partial is carried in the DOM for roll-result modals.

    The previous invariant (buttons hidden for non-editors) was replaced
    by the Phase 2-4 un-gating: viewers now drive their own rolls and
    resource spends without persisting anything. The backend 403 on
    /track is still enforced by
    ``test_track_endpoint_forbidden_for_nonadmin`` below as the
    defence-in-depth layer."""
    url = create_and_apply(page, live_server_url, "Track Read Only")
    page_nonadmin.goto(url)
    page_nonadmin.wait_for_selector('text="Tracking"')
    # Values still visible.
    serious = page_nonadmin.locator('text="Serious Wounds"').locator('..').locator('span.font-bold')
    assert serious.first.text_content().strip() == "0"
    # +/- buttons now render (un-gated in Phases 3-4).
    assert page_nonadmin.locator('text="Serious Wounds"').locator('..').locator('button', has_text="+").count() > 0
    assert page_nonadmin.locator('text="Light Wounds"').locator('..').locator('button', has_text="+").count() > 0
    # Read-only banner partial is present in the DOM (hidden until a
    # roll modal opens). Confirms the Phase 1 infrastructure is wired
    # for this viewer.
    banners = page_nonadmin.locator('[data-testid="readonly-roll-banner"]')
    assert banners.count() > 0
    for i in range(banners.count()):
        assert not banners.nth(i).is_visible()
    # canEdit flag on trackingData is false - save() short-circuits.
    assert page_nonadmin.evaluate("window._trackingBridge.canEdit") is False


def test_track_endpoint_forbidden_for_nonadmin(page, page_nonadmin, live_server_url):
    """The /track endpoint returns 403 for non-editors."""
    url = create_and_apply(page, live_server_url, "Track Endpoint Test")
    char_id = url.rstrip("/").split("/")[-1]
    page_nonadmin.goto(live_server_url)
    # Try to POST to /track via fetch
    result = page_nonadmin.evaluate("""async (charId) => {
        const resp = await fetch('/characters/' + charId + '/track', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({current_light_wounds: 5}),
        });
        return resp.status;
    }""", char_id)
    assert result == 403


def test_delete_confirmation_dialog(page, live_server_url):
    """Delete button shows confirmation dialog."""
    create_and_apply(page, live_server_url, "Delete Dialog Test")
    dialog_handled = []
    page.on("dialog", lambda d: (dialog_handled.append(d.message), d.dismiss()))
    page.locator('button:text("Delete")').click()
    page.wait_for_timeout(500)
    assert any("Delete" in m for m in dialog_handled)


def test_owner_dropdown_visible_for_admin(page, live_server_url):
    """GM sees owner dropdown on edit page."""
    create_and_apply(page, live_server_url, "Admin Dropdown")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    assert page.locator('select[name="owner_discord_id"]').is_visible()


def test_granted_user_can_access_edit_page(page, page_nonadmin, live_server_url):
    """User granted account-level access can load the edit page."""
    # Create a character as admin
    url = create_and_apply(page, live_server_url, "Shared Char")
    char_id = url.rstrip("/").split("/")[-1]

    # Grant access to test_user_1 (nonadmin) via profile page
    page.goto(f"{live_server_url}/profile")
    grant_cb = page.locator('input[name="grant_test_user_1"]')
    if not grant_cb.is_checked():
        grant_cb.check()
    page.locator('button[type="submit"]', has_text="Save").click()
    page.wait_for_load_state("networkidle")

    try:
        # Now nonadmin should be able to load the edit page
        page_nonadmin.goto(f"{live_server_url}/characters/{char_id}/edit")
        page_nonadmin.wait_for_selector('input[name="name"]', timeout=5000)
        assert page_nonadmin.input_value('input[name="name"]') == "Shared Char"
    finally:
        # Revoke the grant so later tests see a clean slate. The live_server
        # DB persists across tests, so leaving the grant in place makes the
        # admin's default editor list include Test User 1 for every later test.
        page.goto(f"{live_server_url}/profile")
        grant_cb = page.locator('input[name="grant_test_user_1"]')
        if grant_cb.is_checked():
            grant_cb.uncheck()
        page.locator('button[type="submit"]', has_text="Save").click()
        page.wait_for_load_state("networkidle")


def test_owner_dropdown_hidden_for_nonadmin(page, page_nonadmin, live_server_url):
    """Non-GM does not see owner dropdown on edit page."""
    # Create a character owned by nonadmin
    page_nonadmin.goto(live_server_url)
    start_new_character(page_nonadmin)
    page_nonadmin.wait_for_selector('input[name="name"]')
    # The owner dropdown should not be a select for non-admin
    assert not page_nonadmin.locator('select[name="owner_discord_id"]').is_visible()
