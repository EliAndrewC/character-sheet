"""E2E: Publish redirects to view sheet, revert works via AJAX."""

from tests.e2e.helpers import select_school


def _create_character(page, live_server_url, name="Test Character"):
    """Create a character, fill name and school, wait for autosave."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('text="Publish Changes"')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)


def test_publish_redirects_to_view_sheet(page, live_server_url):
    """Publishing should show overlay and redirect to the character sheet."""
    _create_character(page, live_server_url, "Publish Redirect Test")

    page.locator('button:text("Publish Changes")').click()

    # Should redirect to view sheet (not edit page)
    page.wait_for_url("**/characters/*", timeout=10000)
    assert "/edit" not in page.url
    assert "Publish Redirect Test" in page.text_content("h1")


def test_publish_then_no_unpublished_banner(page, live_server_url):
    """After publishing, the view sheet should NOT show unpublished changes banner."""
    _create_character(page, live_server_url, "No Banner Test")

    page.locator('button:text("Publish Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)

    body = page.text_content("body")
    assert "Unpublished changes" not in body
    assert "has not been published" not in body


def test_revert_reloads_page(page, live_server_url):
    """Reverting to a previous version should reload the page with old data."""
    _create_character(page, live_server_url, "Version 1 Name")

    # Publish v1
    page.locator('button:text("Publish Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)
    char_url = page.url

    # Edit and publish v2 with a new name
    page.locator('a:text-is("Edit")').click()
    page.wait_for_selector('text="Publish Changes"')
    page.fill('input[name="name"]', "Version 2 Name")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('button:text("Publish Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)

    assert "Version 2 Name" in page.text_content("h1")

    # Revert to v1 — click the Revert button and accept the confirm dialog
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator('button:text("Revert")').first.click()

    # Page should reload and show v1 name
    page.wait_for_timeout(2000)
    assert "Version 1 Name" in page.text_content("h1")
