"""E2E: Combat skills (Attack and Parry) in create, edit, and character sheet."""


def test_create_with_combat_skills(page, live_server_url):
    """Create a character with raised Attack/Parry and verify on the sheet."""
    page.goto(f"{live_server_url}/characters/new")

    page.fill('input[name="name"]', "Combat Fighter")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    # Raise Attack to 3 and Parry to 2
    page.select_option('select[name="attack"]', "3")
    page.select_option('select[name="parry"]', "2")

    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")

    body = page.text_content("body")
    assert "Combat Fighter" in body
    assert "Attack" in body
    assert "Parry" in body


def test_combat_skill_xp_live_calculation(page, live_server_url):
    """Raising Attack/Parry should update XP in real time via Alpine.js."""
    page.goto(f"{live_server_url}/characters/new")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    initial = page.text_content('[x-text="totalXp()"]').strip()
    assert initial == "0"

    # Raise Attack to 3 (advanced costs: rank 2=4, rank 3=6 => 10 XP)
    page.select_option('select[name="attack"]', "3")
    spent = page.text_content('[x-text="totalXp()"]').strip()
    assert spent == "10"

    # Also raise Parry to 2 (advanced cost: rank 2=4 => +4 XP)
    page.select_option('select[name="parry"]', "2")
    spent = page.text_content('[x-text="totalXp()"]').strip()
    assert spent == "14"


def test_character_sheet_shows_tn_to_hit(page, live_server_url):
    """Character sheet should show TN to be hit based on actual Parry skill."""
    page.goto(f"{live_server_url}/characters/new")

    page.fill('input[name="name"]', "TN Tester")
    page.select_option('select[name="school"]', "akodo_bushi")
    page.wait_for_selector("#school-details :text('Special Ability')")

    page.select_option('select[name="parry"]', "3")

    page.click('button[type="submit"]')
    page.wait_for_url("**/characters/*")

    # TN to be hit = 5 + 5*3 = 20
    body = page.text_content("body")
    assert "20" in body
    assert "parry 3" in body
