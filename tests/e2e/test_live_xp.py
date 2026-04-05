"""E2E: Verify client-side (Alpine.js) live XP calculation."""

from tests.e2e.helpers import select_school, click_plus


def test_xp_updates_on_ring_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    assert page.text_content('[x-text="totalXp()"]').strip() == "0"
    click_plus(page, "ring_fire", 1)  # 2->3 = 15 XP
    assert page.text_content('[x-text="totalXp()"]').strip() == "15"


def test_xp_updates_on_skill_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "skill_precepts", 3)  # basic: 2+2+3 = 7
    assert page.text_content('[x-text="totalXp()"]').strip() == "7"


def test_xp_updates_on_advantage_toggle(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    page.check('input[name="adv_lucky"]')
    assert page.text_content('[x-text="totalXp()"]').strip() == "5"
    page.uncheck('input[name="adv_lucky"]')
    assert page.text_content('[x-text="totalXp()"]').strip() == "0"


def test_xp_updates_on_disadvantage_toggle(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    page.check('input[name="dis_discordant"]')
    assert page.text_content('[x-text="totalXp()"]').strip() == "-12"


def test_remaining_goes_negative_on_overspend(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    page.fill('input[name="starting_xp"]', "5")
    click_plus(page, "ring_fire", 1)  # 15 XP, budget 5

    remaining_el = page.locator('[x-text="remainingXp()"]')
    assert remaining_el.text_content().strip() == "-10"
    parent = remaining_el.locator("..")
    assert "text-red-600" in (parent.get_attribute("class") or "")


def test_xp_honor_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    page.select_option('select[name="honor"]', "3.0")  # 4 XP
    assert page.text_content('[x-text="totalXp()"]').strip() == "4"


def test_xp_updates_on_knack_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "knack_feint", 1)  # 1->2 = 4 XP
    assert page.text_content('[x-text="totalXp()"]').strip() == "4"


def test_xp_updates_on_combat_skill_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 1)  # 1->2 = 4 XP
    assert page.text_content('[x-text="totalXp()"]').strip() == "4"
