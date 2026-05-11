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
    """Subsequent versions have blank description.
    Edits a stat (Earned XP) since name is metadata and doesn't put the
    character into a draft state."""
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "First version")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="earned_xp"]', "5")
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


def test_lineage_metadata_full_lifecycle(page, live_server_url):
    """Lineage is metadata: the dropdown lives next to Age in Basics,
    picking a canonical lineage reveals a ``?`` help icon whose tooltip
    carries the description, picking ``Other`` reveals a free-form
    text input, and applying / reloading round-trips the value to the
    View Sheet's Player line (where hovering Lineage surfaces the
    description again). Like age, changing lineage on a published
    character does NOT flip the unpublished-changes flag."""
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "Initial - no lineage")

    # Validation issue surfaces on the View Sheet.
    body = page.text_content("body")
    assert "Validation Issues" in body
    assert "Lineage is not set" in body

    # Back to the editor; pick Kyo from the dropdown.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    dropdown = page.locator('[data-testid="lineage-dropdown"]')
    assert dropdown.is_visible()
    dropdown.select_option("Kyo")
    page.wait_for_timeout(150)
    # Help icon is now present; its tooltip-content carries the full
    # Kyo description (Kyoma appears in the text).
    help_icon = page.locator('[data-testid="lineage-help"]')
    assert help_icon.is_visible()
    assert "Kyoma" in help_icon.text_content()
    page.wait_for_selector('text="Saved"', timeout=5000)
    # Apply / Discard buttons do NOT appear - metadata-only change.
    assert not page.locator('[data-action="apply-changes"]').is_visible()
    assert not page.locator('[data-action="discard-changes"]').is_visible()

    # Reload, switch to Other + custom value, verify it persists.
    page.reload()
    page.wait_for_selector('input[name="name"]')
    assert dropdown.input_value() == "Kyo"
    dropdown.select_option("Other")
    page.wait_for_timeout(150)
    # Help icon disappears for free-form picks; the custom-text input
    # takes its place.
    assert not help_icon.is_visible()
    custom = page.locator('[data-testid="lineage-custom"]')
    assert custom.is_visible()
    custom.fill("Custom House")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.reload()
    page.wait_for_selector('input[name="name"]')
    # Round-trip: stored value "Custom House" -> dropdown lands on
    # Other with the text input pre-filled.
    assert dropdown.input_value() == "Other"
    assert custom.input_value() == "Custom House"

    # View Sheet shows the lineage on the Player line, and the
    # validation issue is cleared. Free-form lineages have no tooltip.
    page.locator('a:text-is("View Sheet"), [data-action="view-sheet"]').first.click()
    page.wait_for_selector("h1")
    body = page.text_content("body")
    assert "Custom House lineage" in body
    assert "Lineage is not set" not in body
    assert page.locator('[data-testid="lineage-tooltip"]').count() == 0


def test_lineage_tooltip_renders_on_view_sheet_for_canonical_pick(
    page, live_server_url,
):
    """A canonical lineage on the View Sheet wraps in a tooltip-trigger
    span whose hidden tooltip-content carries the full description."""
    _go_to_new_editor(page, live_server_url)
    page.locator('[data-testid="lineage-dropdown"]').select_option("Tsuruchi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Pick Tsuruchi")
    tip = page.locator('[data-testid="lineage-tooltip"]')
    assert tip.is_visible()
    # The tooltip-content lives inside the trigger span; pull its full
    # text content (which Playwright includes whether visible or not).
    full = tip.text_content()
    assert "Tsuruchi lineage" in full
    assert "original Shin lineage" in full


def test_age_metadata_does_not_count_as_unapplied_changes(page, live_server_url):
    """Age is metadata - changing it on a published character must NOT
    flip the character to "unpublished changes" or surface in the
    Discard modal's diff list. The Validation Issues block on the View
    Sheet flags an unset age, which clears once the player sets it."""
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "Initial - no age")

    # On the View Sheet, age unset -> validation issue.
    body = page.text_content("body")
    assert "Validation Issues" in body
    assert "Age is not set" in body

    # Re-enter the editor and set the age.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="age"]', "28")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.wait_for_timeout(200)

    # Apply / Discard buttons must NOT appear - age is not a stat.
    assert not page.locator('[data-action="apply-changes"]').is_visible()
    assert not page.locator('[data-action="discard-changes"]').is_visible()

    # Reload and verify age persisted + validation issue cleared on View Sheet.
    page.reload()
    page.wait_for_selector('input[name="name"]')
    assert page.locator('input[name="age"]').input_value() == "28"
    page.locator('a:text-is("View Sheet"), [data-action="view-sheet"]').first.click()
    page.wait_for_selector("h1")
    body = page.text_content("body")
    assert "Age: 28" in body
    assert "Age is not set" not in body


def test_apply_button_visible_on_revisit_of_never_applied_draft(page, live_server_url):
    """Reload-the-editor case: a draft that was created but never had
    Apply Changes clicked must STILL show the Apply button on subsequent
    visits, otherwise the user can never make their first version.

    Regression: ``has_unpublished_changes`` returns False for an
    unpublished character (no ``published_state`` baseline to diff
    against), so gating Apply solely on that flag hid the button on
    page reload."""
    _go_to_new_editor(page, live_server_url)
    # Force the in-memory hasUnpublishedChanges flag back to false so we
    # mirror what the page sees on a fresh GET of an unpublished draft
    # (no autosave yet -> server says False -> Alpine inits False).
    page.evaluate(
        "Alpine.$data(document.querySelector('[x-data=\"characterForm()\"]')).hasUnpublishedChanges = false"
    )
    page.wait_for_timeout(150)
    apply_btn = page.locator('[data-action="apply-changes"]')
    assert apply_btn.is_visible(), (
        "Apply Changes must remain visible for unpublished drafts even when "
        "the server-side has_unpublished_changes flag is False"
    )
    # Discard, however, stays hidden - there's no published version to
    # revert to.
    assert not page.locator('[data-action="discard-changes"]').is_visible()


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
    2. Make a stat edit; Apply + Discard buttons re-appear.
    3. Click Discard; modal opens with a diff line for the change.
    4. Confirm; page reloads with the stat reverted to the published value.

    Uses Earned XP since name is metadata and doesn't trigger draft
    state.
    """
    _go_to_new_editor(page, live_server_url)
    apply_changes(page, "Initial")
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')

    # Edit a stat -> autosave -> both buttons appear.
    page.fill('input[name="earned_xp"]', "12")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.wait_for_timeout(200)
    assert page.locator('[data-action="apply-changes"]').is_visible()
    discard_btn = page.locator('[data-action="discard-changes"]')
    assert discard_btn.is_visible()

    # Open modal -> diff line for the change shows up.
    discard_btn.click()
    page.wait_for_selector('[data-modal="discard-changes"]', timeout=3000)
    page.wait_for_selector('[data-testid="discard-diff-lines"]', timeout=5000)
    diff_text = page.locator('[data-testid="discard-diff-lines"]').text_content()
    assert "Earned XP" in diff_text or "12" in diff_text

    # Cancel keeps the draft.
    page.locator('[data-action="cancel-discard"]').click()
    page.wait_for_timeout(150)
    assert page.locator('input[name="earned_xp"]').input_value() == "12"

    # Re-open and confirm.
    discard_btn.click()
    page.wait_for_selector('[data-modal="discard-changes"]', timeout=3000)
    page.locator('[data-action="confirm-discard"]').click()

    # Page reloads; the stat reverts to the published value.
    page.wait_for_selector('input[name="name"]', timeout=10_000)
    page.wait_for_timeout(300)
    assert page.locator('input[name="earned_xp"]').input_value() == "0"
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
