"""E2E: Verify client-side (Alpine.js) live XP calculation."""

from tests.e2e.helpers import select_school, click_plus


def _go_to_editor(page, live_server_url):
    """Create a new character and go to the editor."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('text="Publish Changes"')


def test_xp_updates_on_ring_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    click_plus(page, "ring_fire", 1)  # 2->3 = 15 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "15"


def test_xp_updates_on_skill_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "skill_precepts", 3)  # basic: 2+2+3 = 7
    assert page.text_content('[x-text="grossSpent()"]').strip() == "7"


def test_xp_updates_on_advantage_toggle(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    page.check('input[name="adv_lucky"]')
    assert page.text_content('[x-text="grossSpent()"]').strip() == "5"
    page.uncheck('input[name="adv_lucky"]')
    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"


def test_xp_updates_on_disadvantage_toggle(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    page.check('input[name="dis_discordant"]')
    assert page.text_content('[x-text="grossSpent()"]').strip() == "0"
    assert page.text_content('[x-text="budgetWithDis()"]').strip() == "162"


def test_remaining_goes_negative_on_overspend(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    for ring in ["air", "fire", "earth", "void"]:
        click_plus(page, f"ring_{ring}", 3)
    click_plus(page, "ring_water", 2)

    remaining_el = page.locator('[x-text="remainingXp()"]')
    remaining_val = int(remaining_el.text_content().strip())
    assert remaining_val < 0
    parent = remaining_el.locator("..")
    assert "text-red-600" in (parent.get_attribute("class") or "")


def test_xp_honor_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "honor", 4)  # 1.0 -> 3.0 = 4 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "4"


def test_xp_updates_on_knack_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "knack_feint", 1)  # 1->2 = 4 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "4"


def test_xp_updates_on_combat_skill_change(page, live_server_url):
    _go_to_editor(page, live_server_url)
    select_school(page, "akodo_bushi")

    click_plus(page, "attack", 1)  # 1->2 = 4 XP
    assert page.text_content('[x-text="grossSpent()"]').strip() == "4"
