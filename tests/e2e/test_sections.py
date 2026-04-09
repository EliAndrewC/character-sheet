"""E2E: rich-text sections on the character editor and sheet.

Sections replace the legacy single Notes textarea with multiple user-labelled
rich-text panels (Quill editor) that get sanitised on save and rendered as
HTML on the sheet.
"""

import pytest

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply

pytestmark = [pytest.mark.sections]


def _go_to_editor_for_new_character(page, live_server_url, name):
    """Create a new draft character and land on its editor."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial")
    # We're now on the sheet — go back to the editor
    page.goto(page.url + "/edit")
    page.wait_for_selector('#add-section-btn')


def _flush_autosave(page):
    """Force the debounced autosave to fire immediately and wait for it to settle."""
    page.evaluate(
        "(async () => {"
        "  const root = document.querySelector('[x-data=\"characterForm()\"]');"
        "  const data = window.Alpine.$data(root);"
        "  if (data._saveTimeout) clearTimeout(data._saveTimeout);"
        "  data._dirty = true;"
        "  await data.doSave();"
        "})()"
    )
    page.wait_for_timeout(200)


def _add_section(page, label, body_text):
    """Click Add Section, fill in label, type body via Quill, and flush autosave."""
    initial_count = page.locator('#sections-container > div').count()
    page.locator('#add-section-btn').click()
    # Wait for the new card to render and Quill to mount
    page.wait_for_function(
        f"document.querySelectorAll('#sections-container > div').length === {initial_count + 1}"
    )
    new_card = page.locator('#sections-container > div').nth(initial_count)
    new_card.locator('input.section-label').fill(label)
    # Quill renders a contenteditable div inside .quill-host
    new_card.locator('.ql-editor').click()
    new_card.locator('.ql-editor').fill(body_text)
    _flush_autosave(page)


def test_add_single_section_persists(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "Section1Char")
    _add_section(page, "Notes", "My adventure notes here.")
    page.reload()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    card = page.locator('#sections-container > div').first
    assert card.locator('input.section-label').input_value() == "Notes"
    assert "My adventure notes here." in card.locator('.ql-editor').text_content()


def test_section_label_can_be_anything(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "BackstoryChar")
    _add_section(page, "Backstory", "Born in the mountains.")
    _add_section(page, "Allies and Enemies", "Ally: Tanaka. Enemy: Kuwanan.")
    page.reload()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    cards = page.locator('#sections-container > div')
    assert cards.count() == 2
    assert cards.nth(0).locator('input.section-label').input_value() == "Backstory"
    assert cards.nth(1).locator('input.section-label').input_value() == "Allies and Enemies"


def test_section_renders_on_sheet(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "SheetRenderChar")
    _add_section(page, "Backstory", "I was born under the cherry blossoms.")
    # Navigate to the sheet
    sheet_url = page.url.replace("/edit", "")
    page.goto(sheet_url)
    body = page.text_content("body")
    assert "Backstory" in body
    assert "I was born under the cherry blossoms." in body


def test_delete_section(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "DeleteSectionChar")
    _add_section(page, "Section A", "First content.")
    _add_section(page, "Section B", "Second content.")
    cards = page.locator('#sections-container > div')
    assert cards.count() == 2

    # Override the JS confirm dialog to true and delete the first card
    page.evaluate("window.confirm = () => true")
    cards.nth(0).locator('button.delete').click()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length === 1")
    _flush_autosave(page)

    page.reload()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    cards = page.locator('#sections-container > div')
    assert cards.count() == 1
    assert cards.first.locator('input.section-label').input_value() == "Section B"


def test_reorder_sections_with_arrows(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "ReorderChar")
    _add_section(page, "First", "1st content.")
    _add_section(page, "Second", "2nd content.")
    _add_section(page, "Third", "3rd content.")

    # Move "Third" up to position 0 by clicking move-up twice
    cards = page.locator('#sections-container > div')
    cards.nth(2).locator('button.move-up').click()
    cards.nth(1).locator('button.move-up').click()
    _flush_autosave(page)

    page.reload()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    cards = page.locator('#sections-container > div')
    labels = [cards.nth(i).locator('input.section-label').input_value() for i in range(3)]
    assert labels == ["Third", "First", "Second"]


def test_move_up_disabled_at_top_and_move_down_disabled_at_bottom(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "ArrowDisabledChar")
    _add_section(page, "Only", "Lonely content.")
    card = page.locator('#sections-container > div').first
    assert card.locator('button.move-up').is_disabled()
    assert card.locator('button.move-down').is_disabled()


def test_empty_sections_list_shows_hint(page, live_server_url):
    _go_to_editor_for_new_character(page, live_server_url, "EmptyHintChar")
    hint = page.locator('#sections-empty-hint')
    assert hint.is_visible()
    _add_section(page, "Notes", "x")
    # Hint disappears after adding
    assert not hint.is_visible()


def test_dangerous_html_is_sanitized(page, live_server_url):
    """If somehow malicious HTML reaches the autosave endpoint, the saved value
    is sanitized. We use the page's request context to bypass Quill (which
    would already strip script tags client-side)."""
    _go_to_editor_for_new_character(page, live_server_url, "SanitizeChar")
    # Pull the character ID from the URL
    char_id = page.url.split('/characters/')[1].split('/')[0]

    # POST a section containing a script tag directly to the autosave endpoint
    resp = page.request.post(
        f"{live_server_url}/characters/{char_id}/autosave",
        headers={"Content-Type": "application/json", "X-Test-User": "183026066498125825:eliandrewc"},
        data='{"sections": [{"label": "Pwn", "html": "<p>safe</p><script>alert(1)</script>"}]}',
    )
    assert resp.ok

    # Reload the editor — the saved section should NOT contain the script
    page.reload()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    card = page.locator('#sections-container > div').first
    body_html = card.locator('.ql-editor').inner_html()
    assert "<script" not in body_html
    assert "alert(1)" not in body_html
    assert "safe" in card.locator('.ql-editor').text_content()


def test_section_with_formatting_persists(page, live_server_url):
    """Use Quill's toolbar to apply bold formatting and verify the HTML round-trips."""
    _go_to_editor_for_new_character(page, live_server_url, "BoldChar")
    page.locator('#add-section-btn').click()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    card = page.locator('#sections-container > div').first
    card.locator('input.section-label').fill("Bold Section")
    editor = card.locator('.ql-editor')
    editor.click()
    editor.fill("This is bold")
    # Select all
    editor.press("Control+a")
    # Click the bold button in the toolbar of THIS card
    card.locator('button.ql-bold').click()
    _flush_autosave(page)

    # Reload and verify the editor's HTML contains <strong>
    page.reload()
    page.wait_for_function("document.querySelectorAll('#sections-container > div').length > 0")
    card = page.locator('#sections-container > div').first
    inner = card.locator('.ql-editor').inner_html()
    assert "<strong>" in inner or "<b>" in inner

    # And on the sheet, the bold formatting is rendered
    sheet_url = page.url.replace("/edit", "")
    page.goto(sheet_url)
    sheet_html = page.locator('.rich-section').first.inner_html()
    assert "<strong>" in sheet_html or "<b>" in sheet_html
