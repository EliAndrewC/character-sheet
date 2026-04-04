"""E2E: Edit a character and verify changes persist."""


def _create_character(page, live_server_url):
    """Helper: create a character and return its sheet URL."""
    page.goto(f"{live_server_url}/characters/new")
    page.fill('input[name="name"]', "Edit Target")
    page.select_option('select[name="school"]', "bayushi_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")
    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")
    return page.url


def test_edit_changes_persist(page, live_server_url):
    """Edit a character's stats and verify the changes show on the sheet."""
    char_url = _create_character(page, live_server_url)

    # Go to edit page via the Edit link
    edit_link = page.locator('a:text-is("Edit")')
    edit_link.click()
    page.wait_for_selector('text="Save Changes"')

    # Change name
    page.fill('input[name="name"]', "Bayushi Kachiko")

    # Raise a ring
    page.select_option('select[name="ring_air"]', "4")

    # Add a skill
    page.select_option('select[name="skill_sincerity"]', "3")

    # Raise honor
    page.select_option('select[name="honor"]', "3.0")

    # Add earned XP
    page.fill('input[name="earned_xp"]', "50")

    # Save
    page.click('button:text("Save Changes")')
    page.wait_for_selector("h1")

    # Verify changes on the sheet
    body = page.text_content("body")
    assert "Bayushi Kachiko" in body
    assert "Earned" in body


def test_edit_cancel_returns_to_sheet(page, live_server_url):
    """Clicking cancel returns to the character sheet without saving."""
    char_url = _create_character(page, live_server_url)

    # Go to edit page
    edit_link = page.locator('a:text-is("Edit")')
    edit_link.click()
    page.wait_for_selector('text="Save Changes"')

    # Change name but don't save
    page.fill('input[name="name"]', "SHOULD NOT PERSIST")

    # Cancel
    page.click("text=Cancel")
    page.wait_for_selector("h1")

    # Original name should still be there
    assert "Edit Target" in page.text_content("h1")
