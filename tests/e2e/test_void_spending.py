"""E2E: Void point spending on rolls - menu options, deduction, priority order."""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character

pytestmark = [pytest.mark.rolls, pytest.mark.tracking]


def _create_char_with_void(page, live_server_url, name="VoidTest",
                            void_points=2, temp_void=0):
    """Create a character, apply, then set void points via JS."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    # Set void points directly via JS (characters now start at full VP)
    page.evaluate(f"window._trackingBridge.voidPoints = {void_points}")
    if temp_void > 0:
        page.evaluate(f"window._trackingBridge.tempVoidPoints = {temp_void}")
    page.evaluate("window._trackingBridge.save()")
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_load_state("networkidle")


def _wait_alpine(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'idle') return true;
        }
        return false;
    }""", timeout=5000)


# ---------------------------------------------------------------------------
# Roll menu with void options
# ---------------------------------------------------------------------------


def test_roll_menu_shows_void_options(page, live_server_url):
    """When void points are available, the roll menu shows spending options."""
    _create_char_with_void(page, live_server_url, "VoidMenu", void_points=2)
    _wait_alpine(page)
    # Verify void is available via the bridge
    vp = page.evaluate("window._trackingBridge?.voidPoints")
    assert vp == 2, f"Expected 2 void points, got {vp}"
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(500)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    assert menu.is_visible(), "Roll menu should be visible"
    # Check menu has void option
    menu_text = menu.text_content()
    assert "Spend 1 void point" in menu_text, f"Menu text: {menu_text[:200]}"


def test_roll_menu_skipped_without_void(page, live_server_url):
    """With 0 void points, clicking a skill rolls directly (no menu)."""
    _create_char_with_void(page, live_server_url, "NoVoid", void_points=0)
    _wait_alpine(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    # Should roll directly - wait for result phase
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)


# ---------------------------------------------------------------------------
# Void deduction
# ---------------------------------------------------------------------------


def test_spending_void_deducts_from_counter(page, live_server_url):
    """After spending void on a roll, the void counter decreases."""
    _create_char_with_void(page, live_server_url, "VoidDeduct", void_points=2)
    _wait_alpine(page)
    # Check initial void count
    vp_before = page.evaluate("window._trackingBridge?.voidPoints")
    assert vp_before == 2, f"Expected 2, got {vp_before}"
    # Click skill and spend 1 void
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(500)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    menu.locator('text=Spend 1 void point').first.click()
    # Wait for roll to complete
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    # Verify void decreased
    vp_after = page.evaluate("window._trackingBridge?.voidPoints")
    assert vp_after == 1


def test_temp_void_deducted_before_regular(page, live_server_url):
    """Temporary void points are spent before regular void points."""
    _create_char_with_void(page, live_server_url, "TempFirst",
                            void_points=1, temp_void=1)
    _wait_alpine(page)
    temp_before = page.evaluate("window._trackingBridge?.tempVoidPoints")
    regular_before = page.evaluate("window._trackingBridge?.voidPoints")
    assert temp_before == 1, f"Expected 1 temp, got {temp_before}"
    assert regular_before == 1, f"Expected 1 regular, got {regular_before}"
    # Spend 1 void - should take from temp first
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(500)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    menu.locator('text=Spend 1 void point').first.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    temp_after = page.evaluate("window._trackingBridge?.tempVoidPoints")
    regular_after = page.evaluate("window._trackingBridge?.voidPoints")
    assert temp_after == 0, "Temp void should be spent first"
    assert regular_after == 1, "Regular void should be untouched"


# ---------------------------------------------------------------------------
# Otherworldliness submenu (priests / monks / Isawa Ishi)
# ---------------------------------------------------------------------------


def _create_priest_with_bragging(page, live_server_url):
    """Priest with OW knack rank 2 (pool = 4) and bragging rank 3 (OW capacity = 2)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "OWPriest")
    select_school(page, "priest")
    click_plus(page, "knack_conviction", 1)       # rank 2
    click_plus(page, "knack_otherworldliness", 1) # rank 2
    click_plus(page, "knack_pontificate", 1)      # rank 2
    click_plus(page, "skill_bragging", 3)         # rank 3
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup OW")


def test_ow_submenu_appears_for_basic_skill_with_ow_available(page, live_server_url):
    """Hovering a VP option on a basic skill reveals OW submenu options."""
    _create_priest_with_bragging(page, live_server_url)
    _wait_alpine(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    # Hover the "Roll" 0-VP row - submenu to the right should appear
    page.locator('[data-ow-submenu="roll"]').wait_for(state='attached', timeout=2000)
    page.locator('.fixed.z-50 >> text="Roll "').first.hover()
    page.wait_for_timeout(200)
    submenu = page.locator('[data-ow-submenu="roll"]')
    assert submenu.is_visible(), "OW submenu should be visible on hover"
    text = submenu.text_content()
    assert "Spend 1 Otherworldliness" in text
    assert "Spend 2 Otherworldliness" in text
    # Only 2 options: capacity = 5 - rank(3) = 2
    assert "Spend 3 Otherworldliness" not in text


def test_ow_spend_increases_rolled_and_decrements_pool(page, live_server_url):
    """Clicking an OW option rolls with +N rolled dice and deducts the pool."""
    _create_priest_with_bragging(page, live_server_url)
    _wait_alpine(page)
    ow_before = page.evaluate(
        "window._trackingBridge?.adventureState?.otherworldliness_used || 0"
    )
    assert ow_before == 0
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('.fixed.z-50 >> text="Roll "').first.hover()
    page.wait_for_timeout(200)
    page.locator('[data-ow-submenu="roll"] button:has-text("Spend 2 Otherworldliness")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    ow_after = page.evaluate("window._trackingBridge.adventureState.otherworldliness_used")
    assert ow_after == 2, f"Expected 2 OW used, got {ow_after}"
    # Verify the formula got the +2 rolled bump
    ow_spent = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return d.formula.ow_spent;
        }
        return null;
    }""")
    assert ow_spent == 2
    # Breakdown should phrase the effect as a skill raise, not a flat bonus
    modal_text = " ".join(
        page.locator('[data-modal="dice-roller"]').text_content().split()
    )
    assert "Skill raised by 2 by Otherworldliness" in modal_text
    assert "+2 from 2 spent Otherworldliness" not in modal_text
    assert "Rolled +2 from 2 spent Otherworldliness" not in modal_text


def test_ow_submenu_hidden_on_advanced_skill(page, live_server_url):
    """Advanced skills (e.g. acting) get no OW submenu even with OW available."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "OWAdvanced")
    select_school(page, "priest")
    click_plus(page, "knack_otherworldliness", 1)
    click_plus(page, "skill_acting", 1)  # advanced skill
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup advanced")
    _wait_alpine(page)
    # Character starts with 2 VP - menu will open
    page.locator('[data-roll-key="skill:acting"]').click()
    page.wait_for_timeout(300)
    # Roll row exists but submenu chevron should be hidden (no OW capacity)
    ow_cap = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.rollMenuOwCapacity === 'number') return d.rollMenuOwCapacity;
        }
        return null;
    }""")
    assert ow_cap == 0, f"Advanced skill should have OW capacity 0, got {ow_cap}"


def test_ow_spend_on_unskilled_roll_enables_reroll_tens(page, live_server_url):
    """Spending OW on an unskilled basic skill grants the skill for that roll,
    so 10s reroll and the unskilled no-reroll note disappears."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "OWRerollTens")
    select_school(page, "priest")
    click_plus(page, "knack_otherworldliness", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    _wait_alpine(page)
    # Bragging is basic & unranked; the unskilled formula starts with no_reroll_reason=unskilled
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('.fixed.z-50 >> text="Roll "').first.hover()
    page.wait_for_timeout(200)
    page.locator('[data-ow-submenu="roll"] button:has-text("Spend 1 Otherworldliness")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    formula_state = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return { reroll: d.formula.reroll_tens, reason: d.formula.no_reroll_reason };
        }
        return null;
    }""")
    assert formula_state["reroll"] is True
    assert formula_state["reason"] == ""


def test_ow_spend_on_unskilled_roll_while_impaired_keeps_no_reroll(page, live_server_url):
    """Impaired characters never reroll 10s, even if OW grants them the skill."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "OWImpaired")
    select_school(page, "priest")
    click_plus(page, "knack_otherworldliness", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup impaired")
    _wait_alpine(page)
    # Set serious wounds >= Earth ring (default 2) to become impaired
    page.evaluate("window._trackingBridge.seriousWounds = 3; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('.fixed.z-50 >> text="Roll "').first.hover()
    page.wait_for_timeout(200)
    page.locator('[data-ow-submenu="roll"] button:has-text("Spend 1 Otherworldliness")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    formula_state = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return { reroll: d.formula.reroll_tens, reason: d.formula.no_reroll_reason };
        }
        return null;
    }""")
    assert formula_state["reroll"] is False
    assert formula_state["reason"] == "impaired"


def test_ow_submenu_appears_for_unskilled_basic_skill(page, live_server_url):
    """OW submenu also appears when rolling a basic skill the character has no ranks in."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "OWUnskilled")
    select_school(page, "priest")
    click_plus(page, "knack_otherworldliness", 1)  # rank 2 -> pool 4
    # Do NOT add any skill ranks - bragging stays at 0 (unskilled)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup unskilled")
    _wait_alpine(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('.fixed.z-50 >> text="Roll "').first.hover()
    page.wait_for_timeout(200)
    submenu = page.locator('[data-ow-submenu="roll"]')
    assert submenu.is_visible(), "OW submenu should appear for unskilled basic skill"
    text = submenu.text_content()
    # Unskilled basic skill: capacity=5, pool=4, so 4 options (1..4)
    assert "Spend 1 Otherworldliness" in text
    assert "Spend 4 Otherworldliness" in text
    assert "Spend 5 Otherworldliness" not in text  # pool-limited


def test_ow_submenu_hidden_when_pool_exhausted(page, live_server_url):
    """When the OW pool is fully spent, the submenu does not appear."""
    _create_priest_with_bragging(page, live_server_url)
    _wait_alpine(page)
    # Exhaust the pool (rank 2 -> max 4)
    page.evaluate("window._trackingBridge.setCount('otherworldliness', 4)")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('.fixed.z-50 >> text="Roll "').first.hover()
    page.wait_for_timeout(200)
    submenu = page.locator('[data-ow-submenu="roll"]')
    assert not submenu.is_visible(), "OW submenu should be hidden when pool exhausted"
