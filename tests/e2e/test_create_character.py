"""E2E: Create a character end-to-end (new flow: POST creates blank, auto-saves)."""

from tests.e2e.helpers import select_school, click_plus, apply_changes


def test_create_and_edit_character(page, live_server_url):
    """Create a new character, edit it in the editor, and verify auto-save."""
    page.goto(live_server_url)

    # Click "New Character" button (now a form POST)
    page.locator('button:text("New Character")').click()

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
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')

    page.fill('input[name="name"]', "Minimal Samurai")
    select_school(page, "akodo_bushi")

    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")
    assert "/edit" not in page.url
