"""E2E: Verify client-side (Alpine.js) live XP calculation."""


def test_xp_updates_on_ring_change(page, live_server_url):
    """Changing a ring dropdown should instantly update the XP display."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Read initial XP
    initial_spent = page.text_content('[x-text="totalXp()"]')
    assert initial_spent.strip() == "0"

    # Raise Fire from 2 to 3 (costs 15 XP)
    page.select_option('select[name="ring_fire"]', "3")

    # Alpine should update immediately — no server round-trip needed
    spent_after = page.text_content('[x-text="totalXp()"]')
    assert spent_after.strip() == "15"


def test_xp_updates_on_skill_change(page, live_server_url):
    """Changing a skill dropdown should update XP."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Raise Precepts to 3 (basic skill: 2+2+3 = 7 XP)
    page.select_option('select[name="skill_precepts"]', "3")

    spent = page.text_content('[x-text="totalXp()"]')
    assert spent.strip() == "7"


def test_xp_updates_on_advantage_toggle(page, live_server_url):
    """Checking/unchecking an advantage updates XP."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Check Lucky (costs 5 XP)
    page.check('input[name="adv_lucky"]')
    spent = page.text_content('[x-text="totalXp()"]')
    assert spent.strip() == "5"

    # Uncheck it
    page.uncheck('input[name="adv_lucky"]')
    spent = page.text_content('[x-text="totalXp()"]')
    assert spent.strip() == "0"


def test_xp_updates_on_disadvantage_toggle(page, live_server_url):
    """Disadvantages should reduce total XP spent."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Check Discordant (gives 12 XP back)
    page.check('input[name="dis_discordant"]')
    spent = page.text_content('[x-text="totalXp()"]')
    assert spent.strip() == "-12"


def test_remaining_goes_negative_on_overspend(page, live_server_url):
    """When spending exceeds budget, remaining should go negative and show red."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Set starting XP very low
    page.fill('input[name="starting_xp"]', "5")

    # Raise Fire to 3 (costs 15 XP, budget is 5)
    page.select_option('select[name="ring_fire"]', "3")

    remaining_el = page.locator('[x-text="remainingXp()"]')
    assert remaining_el.text_content().strip() == "-10"

    # The parent span should have the red class
    parent = remaining_el.locator("..")
    assert "text-red-600" in (parent.get_attribute("class") or "")


def test_xp_honor_change(page, live_server_url):
    """Raising honor should cost XP."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Raise honor to 3.0 (costs 4 XP: 4 increments of 0.5 above 1.0)
    page.select_option('select[name="honor"]', "3.0")

    spent = page.text_content('[x-text="totalXp()"]')
    assert spent.strip() == "4"
