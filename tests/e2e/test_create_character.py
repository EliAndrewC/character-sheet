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


def test_new_character_starts_hidden_with_banner_and_button(page, live_server_url):
    """A brand-new character is hidden by default. The hidden-draft banner
    sits above Basics and the Make Draft Visible button sits in the sticky
    footer; both name the editor list."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    banner = page.locator('[data-testid="hidden-draft-banner"]')
    assert banner.is_visible()
    text = banner.text_content()
    assert "hidden" in text.lower()
    assert "you and the GM" in text
    # Button visible in the sticky footer
    btn = page.locator('[data-action="make-draft-visible"]')
    assert btn.is_visible()


def test_make_draft_visible_button_hides_banner_and_button(page, live_server_url):
    """Clicking 'Make Draft Visible' fires POST /show, then the Alpine flag
    flips so banner + button disappear without a page reload. After a
    reload, the elements stay gone (server-rendered Jinja gate)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('[data-action="make-draft-visible"]', timeout=3000)
    page.locator('[data-action="make-draft-visible"]').click()
    # Banner and button should disappear
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )
    assert page.locator('[data-action="make-draft-visible"]').is_visible() is False
    # After reload they're gone server-side too
    page.reload()
    page.wait_for_selector('input[name="name"]')
    assert page.locator('[data-testid="hidden-draft-banner"]').count() == 0
    assert page.locator('[data-action="make-draft-visible"]').count() == 0


def test_hidden_draft_not_listed_on_homepage_for_non_editor(page, page_nonadmin, live_server_url):
    """The admin creates a hidden draft. A non-admin visiting the homepage
    must not see it in any group section. After the admin clicks Make
    Draft Visible, the non-admin sees it on a fresh load."""
    # Admin creates a hidden character with a unique name
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "HiddenFromOthers Char")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Non-admin visits the homepage - the hidden char must not appear
    page_nonadmin.goto(live_server_url)
    body = page_nonadmin.text_content("body")
    assert "HiddenFromOthers Char" not in body

    # Admin clicks Make Draft Visible
    page.locator('[data-action="make-draft-visible"]').click()
    page.wait_for_selector(
        '[data-testid="hidden-draft-banner"]', state='hidden', timeout=3000,
    )

    # Non-admin reloads and should now see the character
    page_nonadmin.goto(live_server_url)
    body = page_nonadmin.text_content("body")
    assert "HiddenFromOthers Char" in body


def test_apply_changes_also_unhides_the_draft(page, live_server_url):
    """Apply Changes (the existing publish flow) also clears is_hidden, so
    the banner/button never reappear on later edits of a published char."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Apply Reveals Char")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")
    # Now go back to edit and confirm banner+button absent
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('input[name="name"]')
    assert page.locator('[data-testid="hidden-draft-banner"]').count() == 0
    assert page.locator('[data-action="make-draft-visible"]').count() == 0


def test_new_character_dropdown_shows_import_option_when_enabled(page, live_server_url):
    """When IMPORT_ENABLED is unset/true (the default), clicking 'New Character'
    opens a dropdown with both 'Create a character' and 'Import a character'
    options. The disabled-state UI is covered by unit tests because the env
    var is read at startup and can't be flipped per-clicktest."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    create_option = page.locator('[data-testid="new-character-option-create"]')
    import_option = page.locator('[data-testid="new-character-option-import"]')
    create_option.wait_for(state="visible", timeout=2000)
    assert create_option.is_visible()
    assert import_option.is_visible()
    # The Import link points at /import
    assert import_option.get_attribute("href") == "/import"
