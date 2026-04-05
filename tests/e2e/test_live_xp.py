"""E2E: Verify client-side (Alpine.js) live XP calculation."""

from tests.e2e.helpers import select_school, click_plus


def test_xp_updates_on_ring_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    click_plus(page, "ring_fire", 1)  # 2->3 = 15 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "15"


def test_xp_updates_on_skill_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "skill_precepts", 3)  # basic: 2+2+3 = 7
    assert page.text_content('[x-text="grossSpent()"]').strip() == "7"


def test_xp_updates_on_advantage_toggle(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    page.check('input[name="adv_lucky"]')
    assert page.text_content('[x-text="grossSpent()"]').strip() == "5"
    page.uncheck('input[name="adv_lucky"]')
    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"


def test_xp_updates_on_disadvantage_toggle(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    page.check('input[name="dis_discordant"]')
    # Gross spent stays 0 (disadvantages increase budget, not reduce spent)
    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    # Budget increases: 150 + 12 = 162
    assert page.text_content('[x-text="budgetWithDis()"]').strip() == "162"


def test_remaining_goes_negative_on_overspend(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    # Max out all rings: each from 2->5 costs 15+20+25=60, school ring 3->5 costs 20+25=45
    # 4 * 60 + 45 = 285 XP, budget is 150, so remaining = -135
    for ring in ["air", "fire", "earth", "void"]:
        click_plus(page, f"ring_{ring}", 3)
    click_plus(page, "ring_water", 2)  # school ring 3->5

    remaining_el = page.locator('[x-text="remainingXp()"]')
    remaining_val = int(remaining_el.text_content().strip())
    assert remaining_val < 0
    parent = remaining_el.locator("..")
    assert "text-red-600" in (parent.get_attribute("class") or "")


def test_xp_honor_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "honor", 4)  # 1.0 -> 3.0 = 4 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "4"


def test_xp_updates_on_knack_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "knack_feint", 1)  # 1->2 = 4 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "4"


def test_xp_updates_on_combat_skill_change(page, live_server_url):
    page.goto(f"{live_server_url}/characters/new")
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 1)  # 1->2 = 4 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "4"
