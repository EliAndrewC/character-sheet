"""E2E: Apply Changes modal — pre-population, quick-fill, disabled state."""

from tests.e2e.helpers import select_school, apply_changes, start_new_character
import pytest

pytestmark = pytest.mark.apply_changes

def _go_to_new_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
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


def test_apply_disabled_without_school(page, live_server_url):
    """Apply Changes button is disabled when no school is selected."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "No School")
    page.wait_for_timeout(300)
    apply_btn = page.locator('[data-action="apply-changes"]')
    assert apply_btn.is_disabled(), "Apply Changes should be disabled without a school"
    # Select a school and verify it becomes enabled
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    assert not apply_btn.is_disabled(), "Apply Changes should be enabled after selecting a school"


def test_school_locked_after_publish(page, live_server_url):
    """School select is disabled after character has been published."""
    _go_to_new_editor(page, live_server_url)
    # Before publishing, school select should be enabled
    school_select = page.locator('select[name="school"]')
    assert not school_select.is_disabled(), "School should be editable before first publish"
    # Publish
    apply_changes(page, "First version")
    # Go back to edit
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    # School select should now be disabled
    school_select = page.locator('select[name="school"]')
    assert school_select.is_disabled(), "School should be locked after publishing"
    # The explanatory text should be visible
    assert page.locator('text="School cannot be changed after character creation."').is_visible()


def test_discard_button_hidden_for_never_applied_draft(page, live_server_url):
    """A draft that has never been Applied has nothing to revert to, so
    the Discard button must not appear. Apply still appears (so the
    initial publish is reachable)."""
    _go_to_new_editor(page, live_server_url)
    # Apply button visible (the user has unsaved work).
    assert page.locator('[data-action="apply-changes"]').is_visible()
    # Discard button NOT visible (no published_state to revert to).
    assert page.locator('[data-action="discard-changes"]').count() == 0 \
        or not page.locator('[data-action="discard-changes"]').is_visible()


def test_neither_button_visible_when_no_unapplied_changes(page, live_server_url):
    """After Apply Changes, both buttons disappear until the user makes a
    new edit."""
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "Initial")
    # Re-enter the editor; no further changes have been made.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.wait_for_timeout(200)
    assert not page.locator('[data-action="apply-changes"]').is_visible()
    assert not page.locator('[data-action="discard-changes"]').is_visible()


def test_discard_full_flow_modal_diff_and_revert(page, live_server_url):
    """End-to-end Discard flow:
    1. Apply an initial version.
    2. Make an edit; Apply + Discard buttons re-appear.
    3. Click Discard; modal opens with a diff line for the change.
    4. Confirm; page reloads with the original state restored.
    """
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "Initial")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')

    # Edit the name -> autosave -> both buttons appear.
    page.fill('input[name="name"]', "Discard Me")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.wait_for_timeout(200)
    assert page.locator('[data-action="apply-changes"]').is_visible()
    discard_btn = page.locator('[data-action="discard-changes"]')
    assert discard_btn.is_visible()

    # Open modal -> diff line for the name change shows up.
    discard_btn.click()
    page.wait_for_selector('[data-modal="discard-changes"]', timeout=3000)
    page.wait_for_selector('[data-testid="discard-diff-lines"]', timeout=5000)
    diff_text = page.locator('[data-testid="discard-diff-lines"]').text_content()
    # The summary is something like "Name changed from Modal Test to Discard Me"
    assert "Discard Me" in diff_text

    # Cancel keeps the draft.
    page.locator('[data-action="cancel-discard"]').click()
    page.wait_for_timeout(150)
    assert page.locator('input[name="name"]').input_value() == "Discard Me"

    # Re-open and confirm.
    discard_btn.click()
    page.wait_for_selector('[data-modal="discard-changes"]', timeout=3000)
    page.locator('[data-action="confirm-discard"]').click()

    # Page reloads; name reverts to the published value.
    page.wait_for_selector('input[name="name"]', timeout=10_000)
    page.wait_for_timeout(300)
    assert page.locator('input[name="name"]').input_value() == "Modal Test"
    # Both action buttons are gone again.
    assert not page.locator('[data-action="apply-changes"]').is_visible()
    assert not page.locator('[data-action="discard-changes"]').is_visible()


def test_cancel_closes_modal(page, live_server_url):
    """Cancel button closes modal without applying."""
    _go_to_new_editor(page, live_server_url)
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=3000)
    page.locator('[data-action="cancel-apply"]').click()
    page.wait_for_timeout(300)
    assert not page.locator('textarea[placeholder="Describe your changes..."]').is_visible()
    assert "/edit" in page.url  # Still on edit page
