"""E2E: Apply Changes redirects to view sheet, revert works via modal."""

from tests.e2e.helpers import select_school, apply_changes
import pytest

pytestmark = [pytest.mark.apply_changes, pytest.mark.version_history]

def _create_character(page, live_server_url, name="Test Character"):
    """Create a character, fill name and school, wait for autosave."""

    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)


def test_apply_redirects_to_view_sheet(page, live_server_url):
    """Applying changes should show modal and redirect to the character sheet."""
    _create_character(page, live_server_url, "Apply Redirect Test")

    apply_changes(page, "Initial character creation")
    assert "/edit" not in page.url
    assert "Apply Redirect Test" in page.text_content("h1")


def test_apply_then_no_draft_banner(page, live_server_url):
    """After applying, the view sheet should NOT show draft changes banner."""
    _create_character(page, live_server_url, "No Banner Test")

    apply_changes(page, "Initial character creation")

    body = page.text_content("body")
    assert "Draft changes" not in body
    assert "no versions" not in body


def test_revert_with_reason(page, live_server_url):
    """Reverting shows a modal asking for a reason, then reloads with old data."""
    _create_character(page, live_server_url, "Version 1 Name")

    # Apply v1
    apply_changes(page, "Initial character creation")
    char_url = page.url

    # Edit and apply v2
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Version 2 Name")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Updated name")

    assert "Version 2 Name" in page.text_content("h1")

    # Expand version history
    page.locator('text="Version History"').click()

    # Click revert — fills in the modal reason
    page.locator('button:text("Revert")').first.click()
    page.wait_for_selector('input[placeholder="..."]', timeout=3000)
    page.fill('input[placeholder="..."]', "testing revert")
    page.locator('div.fixed button:text("Revert")').click()

    # Page should reload with v1 name
    page.wait_for_timeout(2000)
    assert "Version 1 Name" in page.text_content("h1")


def test_version_history_collapsed_by_default(page, live_server_url):
    """Version history section should be collapsed by default."""
    _create_character(page, live_server_url, "Collapse Test")
    apply_changes(page, "Initial character creation")

    # History heading should exist but content hidden
    assert page.locator('text="Version History"').is_visible()
    # Version entries should not be visible until clicked
    assert not page.locator('text="Initial character creation"').is_visible()

    # Click to expand
    page.locator('text="Version History"').click()
    page.wait_for_timeout(300)
    assert page.locator('text="Initial character creation"').is_visible()
