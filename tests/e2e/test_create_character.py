"""E2E: Create a character end-to-end (new flow: POST creates blank, auto-saves)."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character
import pytest

pytestmark = pytest.mark.apply_changes

def test_create_and_edit_character(page, live_server_url):
    """Create a new character, edit it in the editor, and verify auto-save."""

    page.goto(live_server_url)

    # Click "New Character" button (now a form POST)
    start_new_character(page)
    # Should redirect to edit page
    page.wait_for_selector('input[name="name"]')
    assert "/edit" in page.url

    # Fill in details
    page.fill('input[name="name"]', "Akodo Toturi")

    select_school(page, "akodo_bushi")

    click_plus(page, "ring_fire", 1)
    click_plus(page, "skill_precepts", 3)
    click_plus(page, "skill_bragging", 1)

    click_plus(page, "honor", 2)  # 1.0 -> 2.0
    page.check('input[name="adv_fierce"]')

    # Wait for auto-save
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Apply changes — modal + redirect to view sheet
    apply_changes(page, "Initial character creation")
    assert "/edit" not in page.url

    body = page.text_content("body")
    assert "Akodo Toturi" in body
    assert "Akodo Bushi" in body
    assert "Fierce" in body


def test_create_minimal_character(page, live_server_url):
    """Create and publish a character with just a name and school."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')

    page.fill('input[name="name"]', "Minimal Samurai")
    select_school(page, "akodo_bushi")

    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")
    assert "/edit" not in page.url


def test_new_character_starts_hidden_with_banner_and_chip(page, live_server_url):
    """A brand-new character is hidden by default. The hidden-draft banner
    sits above Basics and the visibility chip in the title row reads
    'Hidden'."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    banner = page.locator('[data-testid="hidden-draft-banner"]')
    assert banner.is_visible()
    text = banner.text_content()
    assert "hidden" in text.lower()
    assert "you and the GM" in text
    chip = page.locator('[data-testid="visibility-toggle"]')
    assert chip.is_visible()
    assert chip.get_attribute("data-state") == "hidden"
    assert "Hidden" in chip.text_content()


def test_visibility_chip_toggles_hidden_to_visible(page, live_server_url):
    """Clicking the chip on a hidden character fires POST /show. The
    chip relabels to 'Visible' and the banner hides immediately. After
    a reload the chip stays visible (the saved state)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('[data-testid="visibility-toggle"]', timeout=3000)
    page.locator('[data-testid="visibility-toggle"]').click()
    # Banner hides instantly via x-show.
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )
    chip = page.locator('[data-testid="visibility-toggle"]')
    assert chip.get_attribute("data-state") == "visible"
    assert "Visible" in chip.text_content()
    # After reload the new state persists.
    page.reload()
    page.wait_for_selector('input[name="name"]')
    chip2 = page.locator('[data-testid="visibility-toggle"]')
    assert chip2.get_attribute("data-state") == "visible"
    assert page.locator('[data-testid="hidden-draft-banner"]').is_visible() is False


def test_visibility_chip_can_re_hide_a_visible_character(page, live_server_url):
    """The chip is bidirectional: clicking it on a visible character fires
    POST /hide and the banner reappears. This is the new behavior - the
    hidden flag is no longer one-way."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('[data-testid="visibility-toggle"]', timeout=3000)
    # First click: hidden -> visible.
    page.locator('[data-testid="visibility-toggle"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )
    # Second click: visible -> hidden.
    page.locator('[data-testid="visibility-toggle"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='visible', timeout=3000,
    )
    chip = page.locator('[data-testid="visibility-toggle"]')
    assert chip.get_attribute("data-state") == "hidden"


def test_hidden_draft_not_listed_on_homepage_for_non_editor(page, page_nonadmin, live_server_url):
    """The admin creates a hidden draft. A non-admin visiting the homepage
    must not see it. After the admin flips the chip to visible, the non-
    admin sees it on a fresh load."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "HiddenFromOthers Char")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)

    page_nonadmin.goto(live_server_url)
    body = page_nonadmin.text_content("body")
    assert "HiddenFromOthers Char" not in body

    page.locator('[data-testid="visibility-toggle"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )

    page_nonadmin.goto(live_server_url)
    body = page_nonadmin.text_content("body")
    assert "HiddenFromOthers Char" in body


def test_apply_changes_keeps_hidden_when_checkbox_unchecked(page, live_server_url):
    """Apply Changes no longer auto-reveals: leaving the modal's
    'make visible' checkbox unchecked publishes a version while the
    character stays hidden. The banner and chip remain on the next
    edit."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Hidden Through Publish")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial", make_visible=False)
    # Land on the sheet, then return to edit.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    chip = page.locator('[data-testid="visibility-toggle"]')
    assert chip.get_attribute("data-state") == "hidden"
    assert page.locator('[data-testid="hidden-draft-banner"]').is_visible()


def test_apply_changes_with_checkbox_makes_visible(page, live_server_url):
    """Ticking 'make visible' in the Apply Changes modal publishes the
    version AND clears is_hidden in one action."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Visible On Publish")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial", make_visible=True)
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    chip = page.locator('[data-testid="visibility-toggle"]')
    assert chip.get_attribute("data-state") == "visible"
    assert page.locator('[data-testid="hidden-draft-banner"]').is_visible() is False


def test_homepage_card_styled_differently_when_hidden(page, live_server_url):
    """Editors see hidden characters on the homepage with a dashed gray
    outline and a 'Hidden' pill, distinct from the regular Draft styling."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "HiddenCardStyle")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(live_server_url)
    # Locate this specific card via its name + the data-hidden attribute.
    card = page.locator('a[data-hidden="true"]:has-text("HiddenCardStyle")')
    assert card.is_visible()
    # Hidden pill renders inside the card.
    assert card.locator('[data-testid="card-hidden-badge"]').is_visible()


def test_homepage_visible_card_omits_hidden_styling(page, live_server_url):
    """A visible character's card does not carry the data-hidden marker
    or the Hidden pill - they appear only on hidden cards."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "VisibleCardStyle")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    # Make visible via the chip before navigating home.
    page.locator('[data-testid="visibility-toggle"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )
    page.goto(live_server_url)
    # The card exists (with its data attribute absent) and has no hidden pill.
    card = page.locator('a:has-text("VisibleCardStyle")').first
    assert card.is_visible()
    assert card.get_attribute("data-hidden") is None
    assert card.locator('[data-testid="card-hidden-badge"]').count() == 0


def test_sheet_view_shows_hidden_indicator_next_to_name(page, live_server_url):
    """The View Sheet page renders a 'Hidden' pill next to the character
    name when the character is hidden. Hides when toggled to visible."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "SheetHiddenIndicator")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial", make_visible=False)
    # Now on the sheet for a hidden char.
    indicator = page.locator('[data-testid="sheet-hidden-indicator"]')
    assert indicator.is_visible()
    assert "Hidden" in indicator.text_content()
    # Toggle to visible from the editor, return to the sheet, indicator gone.
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('[data-testid="visibility-toggle"]', timeout=3000)
    page.locator('[data-testid="visibility-toggle"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )
    page.locator('[data-action="view-sheet"]').click()
    page.wait_for_selector('h1', timeout=5000)
    assert page.locator('[data-testid="sheet-hidden-indicator"]').count() == 0


def test_apply_changes_modal_omits_checkbox_when_already_visible(page, live_server_url):
    """Once a character is visible the Apply Changes modal does not show
    the checkbox row at all - there is no opt-in for re-revealing
    something already visible."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('[data-testid="visibility-toggle"]', timeout=3000)
    # Make visible via the chip.
    page.locator('[data-testid="visibility-toggle"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )
    page.fill('input[name="name"]', "Already Visible")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    # Open the Apply Changes modal directly - the checkbox row must not
    # be visible (x-show=isHidden hides it for already-public chars).
    page.locator('[data-action="apply-changes"]').click()
    page.wait_for_selector('textarea[placeholder="Describe your changes..."]', timeout=5000)
    assert page.locator('[data-testid="apply-make-visible-row"]').is_visible() is False


def test_new_character_dropdown_shows_import_option_when_enabled(page, live_server_url):
    """The live-server harness sets IMPORT_ENABLED=true so the import flow
    can be exercised. Under that setup, clicking 'New Character' opens a
    dropdown with both 'Create a character' and 'Import a character'
    options. Production defaults to fail-closed (IMPORT_ENABLED unset =
    feature OFF); that path is covered by unit tests because the env var
    is read at startup and can't be flipped per-clicktest."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    create_option = page.locator('[data-testid="new-character-option-create"]')
    import_option = page.locator('[data-testid="new-character-option-import"]')
    create_option.wait_for(state="visible", timeout=2000)
    assert create_option.is_visible()
    assert import_option.is_visible()
    # The Import link points at /import
    assert import_option.get_attribute("href") == "/import"
