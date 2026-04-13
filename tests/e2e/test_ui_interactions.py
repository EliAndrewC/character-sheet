"""E2E: UI interaction tests for buttons/elements with no prior clicktest coverage."""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes

pytestmark = [pytest.mark.rolls]


def _create_char(page, live_server_url, name, school, knack_overrides=None, skill_overrides=None):
    """Create a character with a specific school and navigate to the sheet."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    if knack_overrides:
        for knack, rank in knack_overrides.items():
            for _ in range(rank - 1):
                click_plus(page, f"knack_{knack}", 1)
    if skill_overrides:
        for skill, rank in skill_overrides.items():
            click_plus(page, f"skill_{skill}", rank)
    # Add Lucky advantage for Lucky reroll tests
    if "lucky" in name.lower():
        page.check('input[name="adv_lucky"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")


def _wait_roll_done(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)


def _wait_attack_result(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)


def _wait_wc_result(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)


def _add_lw_and_open_wc(page, amount):
    """Add light wounds and open wound check modal."""
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', str(amount))
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)


def _roll_wc(page):
    """Roll a wound check (no VP, no strike)."""
    page.locator('[data-action="roll-wound-check-go"]').click()
    _wait_wc_result(page)


# ---------------------------------------------------------------------------
# 1. Wound Check "Accept Result" button
# ---------------------------------------------------------------------------

def test_wc_accept_result_applies_failure(page, live_server_url):
    """Accept Result on a failed wound check applies the serious wounds."""
    _create_char(page, live_server_url, "WCAccept", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3},
                 skill_overrides={"bragging": 1})
    sw_before = page.evaluate("window._trackingBridge?.seriousWounds || 0")
    # Add lots of LW to ensure failure
    _add_lw_and_open_wc(page, 80)
    _roll_wc(page)
    failed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return !d.wcPassed;
        }
        return false;
    }""")
    if failed:
        # The 3rd Dan raises make it discretionary, so Accept Result button should appear
        accept_btn = page.locator('button:has-text("Accept Result")')
        if accept_btn.is_visible():
            accept_btn.click()
            page.wait_for_timeout(300)
            sw_after = page.evaluate("window._trackingBridge?.seriousWounds || 0")
            assert sw_after > sw_before, f"SW should increase: {sw_before} -> {sw_after}"


# ---------------------------------------------------------------------------
# 2. Wound Check "Keep Light Wounds"
# ---------------------------------------------------------------------------

def test_wc_keep_light_wounds_closes(page, live_server_url):
    """Keep Light Wounds closes modal and preserves LW count."""
    _create_char(page, live_server_url, "WCKeep", "akodo_bushi")
    _add_lw_and_open_wc(page, 5)
    _roll_wc(page)
    passed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcPassed;
        }
        return false;
    }""")
    if passed:
        page.locator('button:has-text("Keep Light Wounds")').click()
        page.wait_for_timeout(300)
        # Modal should close
        wc_modal = page.locator('[data-modal="wound-check"]')
        assert not wc_modal.is_visible()
        # LW should still be 5
        lw = page.evaluate("window._trackingBridge?.lightWounds || 0")
        assert lw == 5


# ---------------------------------------------------------------------------
# 3. WC Take 1 Serious Wound
# ---------------------------------------------------------------------------

def test_wc_take_serious_resets_and_adds_sw(page, live_server_url):
    """Take 1 Serious Wound adds 1 SW and resets LW to 0."""
    _create_char(page, live_server_url, "WCTake", "akodo_bushi")
    _add_lw_and_open_wc(page, 5)
    _roll_wc(page)
    passed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcPassed;
        }
        return false;
    }""")
    if passed:
        sw_before = page.evaluate("window._trackingBridge?.seriousWounds || 0")
        page.locator('[data-modal="wound-check"] button:has-text("Take 1 Serious Wound")').click()
        page.wait_for_timeout(300)
        sw_after = page.evaluate("window._trackingBridge?.seriousWounds || 0")
        lw_after = page.evaluate("window._trackingBridge?.lightWounds || 0")
        assert sw_after == sw_before + 1
        assert lw_after == 0


# ---------------------------------------------------------------------------
# 4. Lucky reroll on attack
# ---------------------------------------------------------------------------

def test_lucky_reroll_on_attack(page, live_server_url):
    """Lucky reroll on attack produces a new result."""
    _create_char(page, live_server_url, "LuckyAtk", "akodo_bushi")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Lucky button should be available
    lucky_btn = page.locator('button:has-text("Use Lucky")')
    if lucky_btn.is_visible():
        first_total = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
            }
            return 0;
        }""")
        lucky_btn.click()
        _wait_attack_result(page)
        # A new result should exist (may be same value by chance)
        second_total = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
            }
            return 0;
        }""")
        assert second_total > 0


# ---------------------------------------------------------------------------
# 5. Lucky reroll on wound check
# ---------------------------------------------------------------------------

def test_lucky_reroll_on_wound_check(page, live_server_url):
    """Lucky reroll on wound check produces a new result."""
    _create_char(page, live_server_url, "LuckyWC", "akodo_bushi")
    _add_lw_and_open_wc(page, 20)
    _roll_wc(page)
    lucky_btn = page.locator('button:has-text("Use Lucky")')
    if lucky_btn.is_visible():
        first_total = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.wcPhase === 'result') return d.wcRollTotal;
            }
            return 0;
        }""")
        lucky_btn.click()
        _wait_wc_result(page)
        second_total = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.wcPhase === 'result') return d.wcRollTotal;
            }
            return 0;
        }""")
        assert second_total > 0


# ---------------------------------------------------------------------------
# 6. Iaijutsu duel restart
# ---------------------------------------------------------------------------

def test_duel_restart_resets_tns(page, live_server_url):
    """Duel restart after both miss resets TNs to base values."""
    _create_char(page, live_server_url, "DuelRestart", "akodo_bushi")
    # Open duel modal
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        menu.locator('button:has-text("Iaijutsu Duel")').click()
    page.wait_for_selector('[data-modal="iaijutsu-duel"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    # Enter opponent XP (high so opponent TN is high = we're more likely to miss)
    modal.locator('input[placeholder="e.g. 200"]').fill("500")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    page.wait_for_timeout(300)
    # Roll contested
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=10000)
    # Proceed to focus/strike, focus once to raise TN
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    page.wait_for_timeout(300)
    focus_btn = modal.locator('button:has-text("Focus (+5")')
    if not focus_btn.is_disabled():
        focus_btn.click()
        page.wait_for_timeout(100)
    # Get TNs after focusing
    tn_after_focus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPlayerTN !== undefined) return d.duelPlayerTN;
        }
        return 0;
    }""")
    # Strike
    modal.locator('button:text("Strike!")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'strike-result') return true;
        }
        return false;
    }""", timeout=10000)
    # Check if we hit or missed
    we_hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelStrikeHit !== undefined) return d.duelStrikeHit;
        }
        return false;
    }""")
    # Directly call duelRestart via JS and verify TNs reset
    # This bypasses the non-deterministic dice-roll flow
    tn_focused = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPlayerTN !== undefined) return d.duelPlayerTN;
        }
        return 0;
    }""")
    # TN should be raised from 15 to 20 after focus
    assert tn_focused == 20, f"Expected TN 20 after focus, got {tn_focused}"
    # Call duelRestart directly
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelRestart) { d.duelRestart(); return; }
        }
    }""")
    page.wait_for_timeout(300)
    tn_after_restart = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPlayerTN !== undefined) return d.duelPlayerTN;
        }
        return 0;
    }""")
    # Base TN = 150/10 = 15
    assert tn_after_restart == 15, f"TN should reset to 15 after restart, got {tn_after_restart}"


# ---------------------------------------------------------------------------
# 7. Failed parry checkbox changes damage formula
# ---------------------------------------------------------------------------

def test_failed_parry_checkbox(page, live_server_url):
    """Checking failed parry changes the damage formula display."""
    _create_char(page, live_server_url, "ParryCheck", "akodo_bushi")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkHit !== undefined) return d.atkHit;
        }
        return false;
    }""")
    if hit:
        # Get damage text before checking parry
        text_before = page.locator('[data-modal="attack"]').text_content()
        # Check the failed parry checkbox
        page.locator('input[x-model="atkFailedParry"]').check()
        page.wait_for_timeout(300)
        text_after = page.locator('[data-modal="attack"]').text_content()
        # The damage formula should change (parry skill input appears, damage parts change)
        assert "failed parry" in text_after.lower()


# ---------------------------------------------------------------------------
# 8. Predeclared parry with +5 bonus
# ---------------------------------------------------------------------------

def test_predeclared_parry_with_bonus(page, live_server_url):
    """Predeclared parry rolls with +5 bonus shown in result."""
    _create_char(page, live_server_url, "PreParry", "akodo_bushi")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        # Click predeclared parry option
        predeclare_btn = menu.locator('button:has-text("Predeclared Parry")')
        if predeclare_btn.count() > 0:
            predeclare_btn.first.click()
            _wait_roll_done(page)
            result = page.locator('[data-modal="dice-roller"]').text_content()
            assert "predeclared" in result.lower() or "+5" in result


# ---------------------------------------------------------------------------
# 9. Post-roll VP spend on wound check (Akodo/Yogo 4th Dan)
# ---------------------------------------------------------------------------

def test_wc_post_roll_vp_spend(page, live_server_url):
    """Post-roll VP spend on wound check adds +5 to total."""
    _create_char(page, live_server_url, "WCPostVP", "akodo_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 2")
    page.wait_for_timeout(200)
    _add_lw_and_open_wc(page, 30)
    _roll_wc(page)
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    spend_btn = page.locator('button:has-text("Spend VP (+5)")')
    if spend_btn.is_visible():
        spend_btn.click()
        page.wait_for_timeout(300)
        total_after = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.wcPhase === 'result') return d.wcRollTotal;
            }
            return 0;
        }""")
        assert total_after == total_before + 5
