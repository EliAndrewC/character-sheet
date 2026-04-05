"""E2E: Create a character end-to-end."""

from tests.e2e.helpers import select_school, click_plus


def test_create_character_full_workflow(page, live_server_url):
    """Fill out the create form, submit, and verify the character sheet renders."""
    page.goto(f"{live_server_url}/characters/new")

    page.fill('input[name="name"]', "Akodo Toturi")
    page.fill('input[name="player_name"]', "Eli")

    select_school(page, "akodo_bushi")

    click_plus(page, "ring_fire", 1)
    click_plus(page, "skill_precepts", 3)
    click_plus(page, "skill_bragging", 1)
    click_plus(page, "skill_etiquette", 2)

    click_plus(page, "honor", 2)  # 1.0 -> 2.0 (two +0.5 clicks)
    page.check('input[name="adv_fierce"]')
    page.check('input[name="dis_proud"]')
    page.fill("textarea[name='notes']", "Leader of the Lion clan")

    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")

    body = page.text_content("body")
    assert "Akodo Toturi" in body
    assert "Akodo Bushi" in body
    assert "Total Spent" in body
    assert "Fierce" in body
    assert "Proud" in body
    assert "Leader of the Lion clan" in body


def test_create_minimal_character(page, live_server_url):
    """Create a character with only required fields."""
    page.goto(f"{live_server_url}/characters/new")

    page.fill('input[name="name"]', "Minimal Samurai")
    select_school(page, "akodo_bushi")

    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")
    assert "Minimal Samurai" in page.text_content("h1")
