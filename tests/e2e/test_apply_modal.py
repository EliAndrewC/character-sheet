"""E2E: Apply Changes modal — pre-population, quick-fill, disabled state."""

from tests.e2e.helpers import select_school, apply_changes
import pytest

pytestmark = pytest.mark.apply_changes

def _go_to_new_editor(page, live_server_url):
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Modal Test")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)


def test_first_version_prepopulates(page, live_server_url):
    """First version pre-populates with 'Initial character creation'."""

    _go_to_new_editor(page, live_server_url)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    val = page.locator('textarea[placeholder="Describe your changes..."]').input_value()
    assert val == "Initial character creation"


def test_subsequent_version_blank(page, live_server_url):
    """Subsequent versions have blank description."""
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "First version")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Modified")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    val = page.locator('textarea[placeholder="Describe your changes..."]').input_value()
    assert val == ""


def test_quickfill_adventure_xp(page, live_server_url):
    """Quick-fill button populates description."""
    _go_to_new_editor(page, live_server_url)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    # Clear the pre-populated text
    page.fill('textarea[placeholder="Describe your changes..."]', "")
    page.locator('button:text("Spending XP from the latest adventure")').click()
    val = page.locator('textarea[placeholder="Describe your changes..."]').input_value()
    assert val == "Spending XP from the latest adventure"


def test_quickfill_mid_adventure(page, live_server_url):
    """Second quick-fill button populates description."""
    _go_to_new_editor(page, live_server_url)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    page.fill('textarea[placeholder="Describe your changes..."]', "")
    page.locator('button:text("Spending some leftover XP mid-adventure")').click()
    val = page.locator('textarea[placeholder="Describe your changes..."]').input_value()
    assert val == "Spending some leftover XP mid-adventure"


def test_apply_disabled_when_empty(page, live_server_url):
    """Apply button disabled when description is empty."""
    _go_to_new_editor(page, live_server_url)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    page.fill('textarea[placeholder="Describe your changes..."]', "")
    page.wait_for_timeout(200)
    apply_btn = page.locator('div.fixed button:text("Apply Changes")')
    assert apply_btn.is_disabled()


def test_cancel_closes_modal(page, live_server_url):
    """Cancel button closes modal without applying."""
    _go_to_new_editor(page, live_server_url)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    page.locator('button:text("Cancel")').click()
    page.wait_for_timeout(300)
    assert not page.locator('textarea[placeholder="Describe your changes..."]').is_visible()
    assert "/edit" in page.url  # Still on edit page
