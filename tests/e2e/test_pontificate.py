"""E2E: Pontificate "(as <skill>)" roll menu + result.

Clicking the Pontificate dice icon opens a menu whose main options (Roll /
Spend N void) each expand, on hover, into a submenu of eligible basic
skills. Rolling a submenu skill rolls "Pontificate (as <skill>)" with that
skill's bonuses; rolling a main option rolls plain Pontificate with none.
"""

import pytest

from tests.e2e.helpers import (
    apply_changes,
    select_school,
    start_new_character,
)

pytestmark = [pytest.mark.rolls]


def _create_shosuro(page, live_server_url, name="Pontiff"):
    """A Shosuro Actor (has the Pontificate knack). Default honor/recognition
    make bragging/precepts/sincerity eligible Pontificate skills."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "shosuro_actor")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")


def _open_pontificate_menu(page):
    page.locator('[data-roll-key="knack:pontificate"]').click()
    page.wait_for_selector('[data-pontificate-menu]', state='visible', timeout=3000)


def _wait_roll_done(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)


def test_pontificate_menu_has_skill_submenu(page, live_server_url):
    _create_shosuro(page, live_server_url, "PontMenu")
    _open_pontificate_menu(page)
    # Main "Roll Pontificate" option is present.
    assert page.locator('[data-pontificate-roll]').count() == 1
    # Hovering it reveals the skill submenu.
    page.locator('[data-pontificate-roll]').hover()
    page.wait_for_selector('[data-pontificate-submenu="roll"]', state='visible', timeout=3000)
    text = page.locator('[data-pontificate-submenu="roll"]').text_content()
    assert "as Bragging" in text
    assert "as Precepts" in text
    assert "as Sincerity" in text
    # Skills never rolled openly in conversation are excluded.
    assert "Sneaking" not in text
    assert "Heraldry" not in text
    assert "Investigation" not in text


def test_pontificate_as_skill_rolls_with_bonuses(page, live_server_url):
    _create_shosuro(page, live_server_url, "PontAs")
    _open_pontificate_menu(page)
    page.locator('[data-pontificate-roll]').hover()
    page.wait_for_selector('[data-pontificate-submenu="roll"]', state='visible', timeout=3000)
    page.locator('[data-pontificate-skill="bragging"]').click()
    _wait_roll_done(page)
    # Title records the substituted skill.
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Pontificate (as Bragging)" in title
    # The bragging bonuses (honor + recognition) appear in the breakdown.
    modal_text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "Recognition" in modal_text
    # The roll key carries the skill (so Roll History records it).
    rk = page.evaluate("() => window._diceRoller && window._diceRoller.currentRollKey")
    assert rk == "knack:pontificate:as:bragging"
    # The flat bonus is actually applied to the formula.
    flat = page.evaluate("() => window._diceRoller.formula.flat")
    assert flat >= 17  # honor(>=2) + recognition(2*7.5=15)


def test_plain_pontificate_has_no_skill_bonuses(page, live_server_url):
    _create_shosuro(page, live_server_url, "PontPlain")
    _open_pontificate_menu(page)
    # Click the main option directly (no skill submenu).
    page.locator('[data-pontificate-roll]').click()
    _wait_roll_done(page)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Pontificate" in title
    assert "as " not in title  # not a "(as <skill>)" roll
    bonus_count = page.evaluate(
        "() => (window._diceRoller.formula.bonuses || []).length"
    )
    assert bonus_count == 0
    flat = page.evaluate("() => window._diceRoller.formula.flat || 0")
    assert flat == 0


def test_pontificate_void_option_has_skill_submenu(page, live_server_url):
    """Each void option also expands into the skill submenu."""
    _create_shosuro(page, live_server_url, "PontVoid")
    page.evaluate("window._trackingBridge.voidPoints = 2; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _open_pontificate_menu(page)
    page.locator('[data-pontificate-vp="1"]').hover()
    page.wait_for_selector('[data-pontificate-submenu="v1"]', state='visible', timeout=3000)
    submenu = page.locator('[data-pontificate-submenu="v1"]')
    assert "as Bragging" in submenu.text_content()
    # Rolling a skill under a void option spends the void AND applies bonuses.
    page.locator('[data-pontificate-submenu="v1"] [data-pontificate-skill-vp="bragging:1"]').click()
    _wait_roll_done(page)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Pontificate (as Bragging)" in title
    assert page.evaluate("() => window._trackingBridge.voidPoints") == 1
