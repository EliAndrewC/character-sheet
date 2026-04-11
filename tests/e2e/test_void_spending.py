"""E2E: Void point spending on rolls - menu options, deduction, priority order."""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes

pytestmark = [pytest.mark.rolls, pytest.mark.tracking]


def _create_char_with_void(page, live_server_url, name="VoidTest",
                            void_points=2, temp_void=0):
    """Create a character, apply, then set void points via tracking."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    # Set void points via the + button
    vp_section = page.locator('text="Void Points"').first.locator('..')
    for _ in range(void_points):
        vp_section.locator('button', has_text="+").click()
        page.wait_for_timeout(100)
    # Set temp void if applicable (Akodo Bushi has temp void)
    if temp_void > 0:
        tv_section = page.locator('text="Temp Void"').first.locator('..')
        for _ in range(temp_void):
            tv_section.locator('button', has_text="+").click()
            page.wait_for_timeout(100)
    page.wait_for_timeout(500)
    # Reload to ensure the tracking state is fresh in all Alpine scopes
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
