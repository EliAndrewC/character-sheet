"""E2E: Edit a character and verify changes persist."""

from tests.e2e.helpers import select_school


def _create_character(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    page.fill('input[name="name"]', "Edit Target")
    select_school(page, "bayushi_bushi")
    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")
    return page.url


def test_edit_changes_persist(page, live_server_url):
    _create_character(page, live_server_url)

    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('text="Save Changes"')

    page.fill('input[name="name"]', "Bayushi Kachiko")
    page.fill('input[name="earned_xp"]', "50")
    page.select_option('select[name="honor"]', "3.0")

    page.click('button:text("Save Changes")')
    page.wait_for_selector("h1")

    assert "Bayushi Kachiko" in page.text_content("body")


def test_edit_cancel_returns_to_sheet(page, live_server_url):
    _create_character(page, live_server_url)

    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('text="Save Changes"')

    page.fill('input[name="name"]', "SHOULD NOT PERSIST")
    page.click("text=Cancel")
    page.wait_for_selector("h1")

    assert "Edit Target" in page.text_content("h1")
