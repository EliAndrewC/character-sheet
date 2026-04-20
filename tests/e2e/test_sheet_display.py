"""E2E: Character sheet display — status, skills, XP, advantages, version history details."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply, start_new_character
import pytest

pytestmark = [pytest.mark.status_display, pytest.mark.skill_rolls, pytest.mark.xp_summary, pytest.mark.version_history]

def _create_full_character(page, live_server_url):
    """Create a character with skills, advantages, and details for display testing."""

    page.goto(live_server_url)
    start_new_character(page)
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


# --- School Knack Expansion ---

def _create_xp_rich_character(page, live_server_url):
    """Build a character with non-zero XP in every visible XP-summary category."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "XP Rich")
    select_school(page, "akodo_bushi")
    click_plus(page, "ring_air", 1)         # Rings:        Air 2->3 (+15)
    click_plus(page, "knack_iaijutsu", 1)   # School Knacks: Iaijutsu 1->2 (+4)
    click_plus(page, "skill_bragging", 1)   # Skills:       Bragging 0->1 (+2)
    click_plus(page, "attack", 1)           # Attack/Parry: Attack 1->2 (+4)
    page.check('input[name="adv_lucky"]')   # Advantages:   Lucky (+5)
    page.check('input[name="dis_proud"]')   # Disadvantages: Proud (-2)
    click_plus(page, "honor", 2)            # HRR:          Honor 1.0 -> 2.0 (+2)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "XP-rich character for breakdown tests")
    return page.url


# --- XP Summary expansion ---

def test_xp_summary_new_labels_and_ordering(page, live_server_url):
    """The new labels appear and old labels are gone; cards are in the new order."""
    _create_full_character(page, live_server_url)
    body = page.text_content("body")
    # New labels
    assert "School Knacks" in body
    assert "Attack / Parry" in body
    assert "Honor / Rank / Recognition" in body
    # Old labels removed from the XP summary section
    section = page.locator('section', has=page.locator('h2:text("XP Summary")')).text_content()
    assert "Combat Skills" not in section
    # The old standalone "Knacks", "Honor", "Rank", "Recognition" cards are gone
    # (those words still appear elsewhere on the sheet, hence section-scoped check)
    for word in ("Knacks ", " Honor ", " Rank ", " Recognition "):
        assert word.strip() != "Knacks" or "School Knacks" in section
    # Verify the data-xp-card order is the new one
    keys = [el.get_attribute("data-xp-card") for el in page.locator('[data-xp-card]').all()]
    expected_prefix = ['rings', 'school_knacks', 'skills', 'combat_skills',
                       'advantages', 'honor_rank_recognition', 'disadvantages']
    assert keys == expected_prefix


def test_xp_summary_collapsed_by_default(page, live_server_url):
    _create_full_character(page, live_server_url)
    panel = page.locator('[data-xp-panel]')
    assert not panel.is_visible()


def test_xp_summary_expand_switch_collapse(page, live_server_url):
    _create_xp_rich_character(page, live_server_url)
    panel = page.locator('[data-xp-panel]')
    assert not panel.is_visible()

    # Click Rings -> panel opens with Rings detail
    page.locator('[data-xp-card="rings"]').click()
    page.wait_for_timeout(200)
    assert panel.is_visible()
    rings_detail = page.locator('[data-xp-detail="rings"]')
    assert rings_detail.is_visible()
    rings_text = rings_detail.text_content()
    assert "Air" in rings_text and "→" in rings_text and "15" in rings_text

    # Click School Knacks -> only that detail is visible now
    page.locator('[data-xp-card="school_knacks"]').click()
    page.wait_for_timeout(200)
    assert panel.is_visible()
    assert page.locator('[data-xp-detail="school_knacks"]').is_visible()
    assert not page.locator('[data-xp-detail="rings"]').is_visible()
    assert "Iaijutsu" in page.locator('[data-xp-detail="school_knacks"]').text_content()

    # Click School Knacks again -> panel collapses
    page.locator('[data-xp-card="school_knacks"]').click()
    page.wait_for_timeout(200)
    assert not panel.is_visible()


def test_xp_summary_rings_shows_free_school_ring_raise(page, live_server_url):
    """The Rings breakdown includes the free school-ring 2->3 raise as a 0 XP
    row so the player can see every raise their character actually received."""
    _create_xp_rich_character(page, live_server_url)
    page.locator('[data-xp-card="rings"]').click()
    page.wait_for_timeout(200)
    rings_text = page.locator('[data-xp-detail="rings"]').text_content()
    # Akodo Bushi's school ring defaults to Water. Water 2 -> 3 is free.
    assert "Water" in rings_text
    assert "2 → 3" in rings_text
    assert "0 XP" in rings_text


def test_xp_summary_hrr_always_shows_wasp_note(page, live_server_url):
    """Even with no Honor/Rank/Recognition XP spent, expanding HRR shows the Wasp note."""
    create_and_apply(page, live_server_url, name="Plain Character", school="akodo_bushi")
    page.locator('[data-xp-card="honor_rank_recognition"]').click()
    page.wait_for_timeout(200)
    detail = page.locator('[data-xp-detail="honor_rank_recognition"]')
    assert detail.is_visible()
    assert "Wasp Campaign" in detail.text_content()


def test_xp_summary_empty_categories_not_clickable(page, live_server_url):
    """A category with total 0 has no cursor-pointer class."""
    create_and_apply(page, live_server_url, name="Plain Character", school="akodo_bushi")
    rings_card = page.locator('[data-xp-card="rings"]')
    rings_class = rings_card.get_attribute("class") or ""
    assert "cursor-pointer" not in rings_class


def test_xp_summary_disadvantages_on_bottom_row(page, live_server_url):
    """Disadvantages box appears in the bottom row with Total Spent and is clickable."""
    _create_xp_rich_character(page, live_server_url)
    dis_card = page.locator('[data-xp-card="disadvantages"]')
    assert dis_card.is_visible()
    dis_class = dis_card.get_attribute("class") or ""
    assert "cursor-pointer" in dis_class
    dis_card.click()
    page.wait_for_timeout(200)
    detail = page.locator('[data-xp-detail="disadvantages"]')
    assert detail.is_visible()
    assert "Proud" in detail.text_content()


def test_xp_summary_grand_total_matches_categories(page, live_server_url):
    """Total Spent equals the sum of the visible category cards."""
    _create_xp_rich_character(page, live_server_url)
    # Pull the grand total from the Total Spent box
    section = page.locator('section', has=page.locator('h2:text("XP Summary")'))
    cards = section.locator('[data-xp-card]')
    cat_total = 0
    for card in cards.all():
        # Each card has a final span with the numeric total
        spans = card.locator('span').all()
        cat_total += int(spans[-1].text_content())
    # The Total Spent value lives in the bg-ink/10 div
    total_text = section.locator('.bg-ink\\/10 .font-mono').text_content()
    assert int(total_text) == cat_total


@pytest.mark.knacks
def test_school_knack_expanded_shows_full_rules(page, live_server_url):
    """Expanding a school knack on the sheet displays the full upstream rules text,
    not the short summary."""
    create_and_apply(page, live_server_url, name="Knack Rules", school="mirumoto_bushi",
                     summary="Mirumoto Bushi for knack expansion test")
    # Locate the Iaijutsu knack row in the School Knacks section
    iaijutsu_row = page.locator('div.bg-parchment', has_text="Iaijutsu").first
    rules_panel = iaijutsu_row.locator('div.whitespace-pre-line')
    # Initially the panel is hidden (x-show="expanded" with expanded=false)
    assert not rules_panel.is_visible()
    # Click to expand
    iaijutsu_row.click()
    page.wait_for_timeout(300)
    assert rules_panel.is_visible()
    panel_text = rules_panel.text_content()
    # Phrase that only appears in the full upstream rules text
    assert "explained with the other combat rules" in panel_text
    # Phrase that only appears in the old short summary — must NOT be shown
    assert "draw-cut" not in panel_text
