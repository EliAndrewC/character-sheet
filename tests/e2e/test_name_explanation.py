"""E2E: name explanation icon, edit modal, and sheet tooltip."""

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character

pytestmark = [pytest.mark.name_generator]


def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def _open_explanation_modal(page):
    page.locator('[data-action="open-explanation-modal"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="visible", timeout=3000)


# ---------------------------------------------------------------------------
# Icon + modal basics
# ---------------------------------------------------------------------------


def test_explanation_icon_visible(page, live_server_url):
    _go_to_editor(page, live_server_url)
    assert page.locator('[data-action="open-explanation-modal"]').is_visible()


def test_modal_opens_with_intro_text_and_empty_textarea(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    modal = page.locator('[data-modal="name-explanation"]')
    assert "Rokugani choose their adult names" in modal.inner_text()
    assert page.locator('[data-field="name-explanation-text"]').input_value() == ""


def test_modal_closes_on_cancel(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    page.locator('[data-action="cancel-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)


def test_modal_closes_on_escape(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    page.keyboard.press("Escape")
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)


def test_cancel_reverts_unsaved_edits(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill("Typed but not saved.")
    page.locator('[data-action="cancel-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    # Reopen: textarea should be empty again (save never happened).
    _open_explanation_modal(page)
    assert page.locator('[data-field="name-explanation-text"]').input_value() == ""


# ---------------------------------------------------------------------------
# Save persists + icon highlights when explanation exists
# ---------------------------------------------------------------------------


def test_save_persists_and_reloads(page, live_server_url):
    """Save writes to the character (via autosave), survives a reload."""
    _go_to_editor(page, live_server_url)
    # Give the character a school + name so Apply Changes isn't blocked later.
    page.fill('input[name="name"]', "Isao")
    select_school(page, "akodo_bushi")
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill(
        "Chosen to honor a grandfather."
    )
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    # Let the debounced autosave flush.
    page.wait_for_timeout(2000)
    # Reload the editor to confirm the value came back from the server.
    page.reload()
    page.wait_for_selector('input[name="name"]')
    _open_explanation_modal(page)
    assert page.locator('[data-field="name-explanation-text"]').input_value() \
        == "Chosen to honor a grandfather."


def test_icon_highlights_when_explanation_exists(page, live_server_url):
    """The note icon switches to an accent style once the explanation has content."""
    _go_to_editor(page, live_server_url)
    btn = page.locator('[data-action="open-explanation-modal"]')
    # Before save: default muted style. border-ink/20 compiles to rgba ~ 20% opacity.
    initial_classes = btn.get_attribute("class") or ""
    assert "text-ink/70" in initial_classes
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill("A meaningful name.")
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    # After save: accent style.
    updated_classes = btn.get_attribute("class") or ""
    assert "text-accent" in updated_classes


# ---------------------------------------------------------------------------
# Sheet page tooltip
# ---------------------------------------------------------------------------


def test_sheet_shows_tooltip_icon_when_explanation_exists(page, live_server_url):
    """A character with a saved name explanation has a tooltip icon on the
    sheet; its contents are the explanation text."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Akodo Ginawa")
    select_school(page, "akodo_bushi")
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill(
        "Ginawa means 'honorable path'."
    )
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    apply_changes(page, "initial")
    # Apply redirects to the sheet. Verify tooltip marker is present and
    # carries the explanation as its inner text.
    page.wait_for_selector('[data-testid="name-explanation-tooltip"]', timeout=5000)
    tooltip = page.locator('[data-testid="name-explanation-tooltip"]')
    assert tooltip.is_visible()
    # tooltip-content is visibility:hidden until hover, so inner_text is
    # empty. Use text_content to read the hidden payload.
    assert "Ginawa means 'honorable path'." in (tooltip.text_content() or "")


def test_sheet_has_no_tooltip_icon_without_explanation(page, live_server_url):
    """No icon is rendered when the explanation is empty."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Akodo Ginawa")
    select_school(page, "akodo_bushi")
    apply_changes(page, "initial")
    # On the sheet, the marker element should not exist.
    assert page.locator('[data-testid="name-explanation-tooltip"]').count() == 0
