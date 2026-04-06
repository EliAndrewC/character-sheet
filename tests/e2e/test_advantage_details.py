"""E2E: Advantage detail fields (text, skill selection) appear and auto-save."""

from tests.e2e.helpers import select_school, apply_changes


def test_higher_purpose_shows_detail_fields(page, live_server_url):
    """Checking Higher Purpose reveals text field and skill checkboxes."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Purpose Test")
    select_school(page, "akodo_bushi")

    # Check Higher Purpose
    page.check('input[name="adv_higher_purpose"]')

    # Detail fields should appear
    page.wait_for_selector('input[placeholder="What is your cause?"]', timeout=3000)
    page.fill('input[placeholder="What is your cause?"]', "oppose the Shadowlands")

    # Wait for auto-save
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Reload and verify persistence
    page.reload()
    page.wait_for_selector('input[name="name"]')
    assert page.input_value('input[placeholder="What is your cause?"]') == "oppose the Shadowlands"


def test_virtue_shows_text_field(page, live_server_url):
    """Checking Virtue reveals a text field for the specific virtue."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Virtue Test")
    select_school(page, "akodo_bushi")

    page.check('input[name="adv_virtue"]')
    page.wait_for_selector('input[placeholder="Which virtue?"]', timeout=3000)
    page.fill('input[placeholder="Which virtue?"]', "Courage")
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Publish and verify on sheet
    apply_changes(page, "Added virtue")
    body = page.text_content("body")
    assert "Virtue" in body
    assert "Courage" in body
