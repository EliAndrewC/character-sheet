"""E2E: Combat skills (Attack and Parry) in create, edit, and character sheet."""

from tests.e2e.helpers import select_school, click_plus, click_minus


def test_create_with_combat_skills(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    page.fill('input[name="name"]', "Combat Fighter")
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 2)  # 1->3
    click_plus(page, "parry", 1)   # 1->2

    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")

    body = page.text_content("body")
    assert "Combat Fighter" in body
    assert "Attack" in body
    assert "Parry" in body


def test_combat_skill_xp_live_calculation(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    click_plus(page, "attack", 2)  # 4+6 = 10 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "10"
    click_plus(page, "parry", 1)  # +4 = 14
    assert page.text_content('[x-text="grossSpent()"]').strip() == "14"


def test_parry_cannot_exceed_attack_plus_1(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "parry", 1)  # 1->2, attack still 1
    assert page.locator('input[name="parry"]').input_value() == "2"

    # Parry + should now be disabled (parry=2 = attack+1)
    plus_btn = page.locator('input[name="parry"]').locator('..').locator('button:text("+")')
    assert plus_btn.is_disabled()


def test_attack_cannot_lower_below_parry_minus_1(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 1)  # 1->2
    click_plus(page, "parry", 1)   # 1->2

    # attack=2, parry=2. Lowering attack to 1 is fine (parry=2 = 1+1)
    minus_btn = page.locator('input[name="attack"]').locator('..').locator('button:text("-")')
    assert not minus_btn.is_disabled()
    click_minus(page, "attack", 1)

    # attack=1, parry=2. Cannot lower further
    assert minus_btn.is_disabled()


def test_character_sheet_shows_tn_to_hit(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    page.fill('input[name="name"]', "TN Tester")
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 2)  # 1->3
    click_plus(page, "parry", 2)   # 1->3

    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")

    body = page.text_content("body")
    assert "20" in body  # 5 + 5*3
    assert "parry 3" in body
