"""E2E: Combat skills (Attack and Parry) in the editor."""

from tests.e2e.helpers import select_school, click_plus, click_minus


def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('text="Publish Changes"')


def test_combat_skill_xp_live_calculation(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    click_plus(page, "attack", 2)  # 4+6 = 10 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "10"
    click_plus(page, "parry", 1)  # +4 = 14
    assert page.text_content('[x-text="grossSpent()"]').strip() == "14"


def test_parry_cannot_exceed_attack_plus_1(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "parry", 1)  # 1->2, attack still 1
    assert page.locator('input[name="parry"]').input_value() == "2"
    plus_btn = page.locator('input[name="parry"]').locator('..').locator('button:text("+")')
    assert plus_btn.is_disabled()


def test_attack_cannot_lower_below_parry_minus_1(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 1)
    click_plus(page, "parry", 1)

    minus_btn = page.locator('input[name="attack"]').locator('..').locator('button:text("-")')
    assert not minus_btn.is_disabled()
    click_minus(page, "attack", 1)
    assert minus_btn.is_disabled()


def test_create_with_combat_skills_and_publish(page, live_server_url):
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Combat Fighter")
    select_school(page, "akodo_bushi")
    click_plus(page, "attack", 2)
    click_plus(page, "parry", 1)

    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('button:text("Publish Changes")').click()
    page.wait_for_url("**/characters/*", timeout=10000)
    page.wait_for_selector("h1")

    body = page.text_content("body")
    assert "Combat Fighter" in body
    assert "Attack" in body
    assert "Parry" in body
