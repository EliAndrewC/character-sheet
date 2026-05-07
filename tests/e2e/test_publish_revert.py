"""E2E: Apply Changes redirects to view sheet, revert works via modal."""

from tests.e2e.helpers import select_school, apply_changes, start_new_character
import pytest

pytestmark = [pytest.mark.apply_changes, pytest.mark.version_history]

def _create_character(page, live_server_url, name="Test Character"):
    """Create a character, fill name and school, wait for autosave."""

    page.goto(live_server_url)
    start_new_character(page)
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
    """Reverting shows a modal asking for a reason, then reloads with old data.
    Uses Earned XP (a stat) to verify revert mechanic - name is metadata
    now and lives outside the version system."""
    _create_character(page, live_server_url, "Revert Test")

    # Apply v1
    apply_changes(page, "Initial character creation")

    # Edit a stat and apply v2
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="earned_xp"]', "25")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Earned some XP")

    # Expand version history
    page.locator('text="Version History"').click()

    # Click revert - fills in the modal reason
    page.locator('button:text("Revert")').first.click()
    page.wait_for_selector('input[placeholder="..."]', timeout=3000)
    page.fill('input[placeholder="..."]', "testing revert")
    page.locator('div.fixed button:text("Revert")').click()

    # Page reloads on the View Sheet; navigate back to the editor and check
    # the stat reverted.
    page.wait_for_timeout(2000)
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    assert page.locator('input[name="earned_xp"]').input_value() == "0"


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
