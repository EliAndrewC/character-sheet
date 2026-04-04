"""E2E: Create a character end-to-end."""


def test_create_character_full_workflow(page, live_server_url):
    """Fill out the create form, submit, and verify the character sheet renders."""
    page.goto(f"{live_server_url}/characters/new")

    # Fill basics
    page.fill('input[name="name"]', "Akodo Toturi")
    page.fill('input[name="player_name"]', "Eli")

    # Select school
    page.select_option('select[name="school"]', "akodo_bushi")
    # Wait for HTMX to load school details
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Verify school info appeared
    assert "Water" in page.text_content("#school-details")
    assert "feint" in page.text_content("#school-details").lower()

    # Set rings
    page.select_option('select[name="ring_fire"]', "3")
    page.select_option('select[name="ring_water"]', "3")  # school ring default

    # Set some skills
    page.select_option('select[name="skill_precepts"]', "3")
    page.select_option('select[name="skill_bragging"]', "1")
    page.select_option('select[name="skill_etiquette"]', "2")

    # Set honor
    page.select_option('select[name="honor"]', "2.0")

    # Check an advantage and disadvantage
    page.check('input[name="adv_fierce"]')
    page.check('input[name="dis_proud"]')

    # Add notes
    page.fill("textarea[name='notes']", "Leader of the Lion clan")

    # Submit
    page.click('button[type="submit"]')

    # Should redirect to character sheet
    page.wait_for_url("**/characters/*")
    assert "Akodo Toturi" in page.text_content("h1")
    assert "Akodo Bushi" in page.text_content("body")

    # Verify XP section exists and shows correct data
    assert "Total Spent" in page.text_content("body")
    assert "Remaining" in page.text_content("body")

    # Verify advantages/disadvantages show
    assert "Fierce" in page.text_content("body")
    assert "Proud" in page.text_content("body")

    # Verify notes
    assert "Leader of the Lion clan" in page.text_content("body")


def test_create_minimal_character(page, live_server_url):
    """Create a character with only required fields."""
    page.goto(f"{live_server_url}/characters/new")

    page.fill('input[name="name"]', "Minimal Samurai")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    page.click('button[type="submit"]')

    page.wait_for_url("**/characters/*")
    assert "Minimal Samurai" in page.text_content("h1")
