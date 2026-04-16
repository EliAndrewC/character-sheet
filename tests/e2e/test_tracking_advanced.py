"""E2E: Advanced tracking — per-adventure counters, toggles, reset, boundary conditions."""

from tests.e2e.helpers import select_school, click_plus, apply_changes
import pytest

pytestmark = pytest.mark.tracking

def _create_character_with_lucky(page, live_server_url):
    """Create and apply a character with the Lucky advantage."""

    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Lucky Character")
    select_school(page, "akodo_bushi")
    page.check('input[name="adv_lucky"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")


def test_serious_wounds_increment_decrement(page, live_server_url):
    """Serious wounds + and - work correctly."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    sw_row = page.locator('text="Serious Wounds"').locator('..')
    plus = sw_row.locator('button', has_text="+")
    minus = sw_row.locator('button', has_text="-")

    plus.click()
    plus.click()
    page.wait_for_timeout(500)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"

    minus.click()
    page.wait_for_timeout(500)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "1"


def test_serious_wounds_persist(page, live_server_url):
    """Serious wounds persist across reload."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    sw_row = page.locator('text="Serious Wounds"').locator('..')
    sw_row.locator('button', has_text="+").click()
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector('text="Serious Wounds"')
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "1"


def test_void_points_persist(page, live_server_url):
    """Void points persist across reload."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    # VP starts at 2 (full). Decrement to 1, reload, verify persistence.
    vp_row = page.locator('text="Void Points"').locator('..')
    vp_row.locator('button', has_text="-").click()
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector('text="Void Points"')
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "1"


def test_void_points_max_enforced(page, live_server_url):
    """Void points + button disabled at max (lowest ring)."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    vp_row = page.locator('text="Void Points"').locator('..')
    plus = vp_row.locator('button', has_text="+")
    # Default rings: Air=2, Fire=2, Earth=2, Water=3, Void=2 -> max = 2
    # VP starts at max, so + should already be disabled
    page.wait_for_timeout(300)
    assert plus.is_disabled()


def test_wound_minus_disabled_at_zero(page, live_server_url):
    """Wound - button disabled when at 0."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    light_minus = page.locator('[data-action="lw-minus"]')
    assert light_minus.is_disabled()
    serious_minus = page.locator('text="Serious Wounds"').locator('..').locator('button', has_text="-")
    assert serious_minus.is_disabled()


def test_lucky_toggle_works(page, live_server_url):
    """Lucky toggle shows 'unused' and can be marked as used."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    assert "unused" in section.text_content()
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)
    assert "used" in section.text_content()
    assert section.locator('button:text("Undo")').is_visible()


def test_lucky_toggle_persists(page, live_server_url):
    """Lucky toggle state persists across reload."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    assert section.locator('button:text("Undo")').is_visible()


def test_reset_per_adventure(page, live_server_url):
    """Reset button resets all per-adventure abilities."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')

    # Use the lucky toggle
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)

    # Reset - opens modal, then confirm
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=3000)
    page.locator('[data-action="confirm-reset"]').click()
    page.wait_for_timeout(500)

    # Should be back to unused
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    assert "unused" in section.text_content()


def test_reset_modal_lists_abilities_to_restore(page, live_server_url):
    """The reset modal lists which specific abilities will be restored."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    # Use lucky
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)
    # Open reset modal
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=3000)
    # The modal should list "Regain Lucky (re-roll)"
    body = page.text_content("body")
    assert "Regain" in body
    assert "Lucky" in body
    # Close without resetting
    page.keyboard.press("Escape")
