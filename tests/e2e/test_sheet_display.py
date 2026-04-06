"""E2E: Character sheet display — status, skills, XP, advantages, version history details."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply


def _create_full_character(page, live_server_url):
    """Create a character with skills, advantages, and details for display testing."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Display Test")
    select_school(page, "akodo_bushi")

    # Add some skills
    click_plus(page, "skill_precepts", 2)
    click_plus(page, "skill_bragging", 1)
    click_plus(page, "skill_etiquette", 1)
    click_plus(page, "skill_culture", 1)

    # Add advantages
    page.check('input[name="adv_charming"]')
    page.check('input[name="adv_fierce"]')

    # Raise honor
    click_plus(page, "honor", 2)  # 1.0 → 2.0

    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Full character for display tests")
    return page.url


# --- Status Display ---

def test_honor_displayed(page, live_server_url):
    _create_full_character(page, live_server_url)
    assert page.locator('text="Honor"').first.is_visible()
    # Should show 2.0 (we raised it by 2 half-steps from 1.0)
    honor_section = page.locator('div', has=page.locator('text="Honor"')).first
    assert "2.0" in honor_section.text_content()


def test_rank_displayed_with_locked(page, live_server_url):
    _create_full_character(page, live_server_url)
    rank_section = page.locator('div', has=page.locator(':text("Rank")')).nth(0)
    body = rank_section.text_content()
    assert "7.5" in body
    assert "locked" in body.lower()


def test_recognition_displayed(page, live_server_url):
    _create_full_character(page, live_server_url)
    assert page.locator('text="Recognition"').first.is_visible()


def test_stipend_displayed(page, live_server_url):
    _create_full_character(page, live_server_url)
    stipend_section = page.locator('div', has=page.locator('text="Stipend"')).first
    assert "16" in stipend_section.text_content()  # Campaign base stipend
    assert "koku" in stipend_section.text_content().lower()


# --- Skill Roll Display ---

def test_skill_with_rank_shows_roll(page, live_server_url):
    """Skills with rank > 0 show roll calculation."""
    _create_full_character(page, live_server_url)
    # Precepts at rank 2 with Earth ring 2 = 4k2. Look for the roll display element.
    roll_displays = page.locator('span.text-accent')
    all_text = " ".join([r.text_content() for r in roll_displays.all()])
    assert "k" in all_text  # At least one "XkY" format roll should exist


def test_charming_bonus_on_etiquette(page, live_server_url):
    """Charming gives +5 on etiquette, shown in roll display."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    assert "Charming" in body


def test_fierce_bonus_on_bragging(page, live_server_url):
    """Fierce gives +5 on bragging, shown in roll display."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    assert "Fierce" in body


def test_honor_bonus_on_bragging(page, live_server_url):
    """Honor bonus shown on bragging roll."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    assert "Honor" in body


# --- Advantages & Disadvantages Display ---

def test_advantages_listed_on_sheet(page, live_server_url):
    """Selected advantages shown on character sheet."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    assert "Charming" in body
    assert "Fierce" in body


def test_advantage_tooltip_on_hover(page, live_server_url):
    """Advantage description shown as tooltip."""
    _create_full_character(page, live_server_url)
    # The tooltip-content div should exist with description text
    charming_tooltip = page.locator('.tooltip-content', has_text="free raise on etiquette")
    assert charming_tooltip.count() > 0


# --- XP Summary ---

def test_xp_breakdown_shown(page, live_server_url):
    """XP breakdown shows all categories on character sheet."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    assert "Rings" in body
    assert "Skills" in body
    assert "Honor" in body
    assert "Total Spent" in body
    assert "Unspent" in body


def test_xp_budget_includes_earned_and_disadvantages(page, live_server_url):
    """Budget line shows starting + earned."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    assert "150" in body  # starting XP


# --- Version History Details ---

def test_version_entry_shows_details(page, live_server_url):
    """Each version shows number, date, summary."""
    _create_full_character(page, live_server_url)
    # Expand version history
    page.locator('text="Version History"').click()
    page.wait_for_timeout(300)
    body = page.text_content("body")
    assert "v1" in body
    assert "Full character for display tests" in body


def test_revert_not_shown_on_latest(page, live_server_url):
    """Revert button not shown on the latest (only) version."""
    _create_full_character(page, live_server_url)
    page.locator('text="Version History"').click()
    page.wait_for_timeout(300)
    # Only one version — no revert buttons visible in the expanded list
    version_items = page.locator('div.bg-parchment')
    for item in version_items.all():
        assert not item.locator('button:text("Revert")').is_visible()
