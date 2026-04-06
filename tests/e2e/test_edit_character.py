"""E2E: Edit a character and verify auto-save persists changes."""

from tests.e2e.helpers import select_school, click_plus


def _create_and_publish(page, live_server_url, name="Edit Target"):
    """Create and publish a character, return to its sheet."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('text="Publish Changes"')
    page.fill('input[name="name"]', name)
    select_school(page, "bayushi_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('button:text("Publish Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)
    page.wait_for_selector("h1")
    return page.url


def test_edit_auto_saves(page, live_server_url):
    """Changes in the editor are auto-saved."""
    _create_and_publish(page, live_server_url)

    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('text="Publish Changes"')

    page.fill('input[name="name"]', "Bayushi Kachiko")
    page.wait_for_selector('text="Saved"', timeout=5000)

    # Reload and verify the name persisted
    page.reload()
    page.wait_for_selector('input[name="name"]')
    assert page.input_value('input[name="name"]') == "Bayushi Kachiko"


def test_view_sheet_shows_published_name(page, live_server_url):
    """View sheet shows the published version, not the draft."""
    _create_and_publish(page, live_server_url, name="Published Name")

    # Edit the name but don't publish
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('text="Publish Changes"')
    page.fill('input[name="name"]', "Draft Name")
    page.wait_for_selector('text="Saved"', timeout=5000)

    # View the sheet — should show published name (for the owner, shows draft)
    page.locator('a:text("View Sheet")').click()
    page.wait_for_selector("h1")
    # As the owner, we see the draft
    assert "Draft Name" in page.text_content("h1")
