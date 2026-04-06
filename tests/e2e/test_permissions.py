"""E2E: Permission-based visibility — edit/delete buttons, version history, owner dropdown."""

from tests.e2e.helpers import create_and_apply
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


def test_tracking_functional_for_nonadmin(page, page_nonadmin, live_server_url):
    """Tracking section works for non-editor viewers."""
    url = create_and_apply(page, live_server_url, "Track By Anyone")
    page_nonadmin.goto(url)
    page_nonadmin.wait_for_selector('text="Tracking"')
    light = page_nonadmin.locator('text="Light Wounds"').locator('..').locator('span.text-2xl')
    assert light.text_content().strip() == "0"
    # Click + and verify it works
    page_nonadmin.locator('text="Light Wounds"').locator('..').locator('button', has_text="+").click()
    page_nonadmin.wait_for_timeout(500)
    assert light.text_content().strip() == "1"


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


def test_owner_dropdown_hidden_for_nonadmin(page, page_nonadmin, live_server_url):
    """Non-GM does not see owner dropdown on edit page."""
    # Create a character owned by nonadmin
    page_nonadmin.goto(live_server_url)
    page_nonadmin.locator('button:text("New Character")').click()
    page_nonadmin.wait_for_selector('input[name="name"]')
    # The owner dropdown should not be a select for non-admin
    assert not page_nonadmin.locator('select[name="owner_discord_id"]').is_visible()
