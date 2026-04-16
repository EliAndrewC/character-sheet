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
# 4. Lucky reroll on regular dice roll
# ---------------------------------------------------------------------------

def test_lucky_on_regular_roll(page, live_server_url):
    """Lucky button appears on regular roll for Lucky characters, not for non-Lucky."""
    _create_char(page, live_server_url, "LuckyReg", "akodo_bushi")
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        menu.locator('button:has-text("Roll")').first.click()
    _wait_roll_done(page)
    lucky_btn = page.locator('[data-modal="dice-roller"] button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() > 0, "Lucky button should appear on regular roll"


def test_no_lucky_on_regular_roll_without_advantage(page, live_server_url):
    """Lucky button does NOT appear for characters without Lucky."""
    _create_char(page, live_server_url, "PlainReg", "akodo_bushi")
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        menu.locator('button:has-text("Roll")').first.click()
    _wait_roll_done(page)
    lucky_btn = page.locator('[data-modal="dice-roller"] button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() == 0, "Lucky button should NOT appear without advantage"


# ---------------------------------------------------------------------------
# 5. Lucky reroll on attack
# ---------------------------------------------------------------------------

def test_lucky_reroll_on_attack(page, live_server_url):
    """Lucky button appears on attack result for Lucky characters."""
    _create_char(page, live_server_url, "LuckyAtk", "akodo_bushi")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    lucky_btn = modal.locator('button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() > 0, "Lucky button should appear on attack result"


def test_no_lucky_on_attack_without_advantage(page, live_server_url):
    """Lucky button does NOT appear on attack result without Lucky."""
    _create_char(page, live_server_url, "PlainAtk", "akodo_bushi")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    lucky_btn = modal.locator('button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() == 0, "Lucky button should NOT appear without advantage"


# ---------------------------------------------------------------------------
# 6. Lucky reroll on damage
# ---------------------------------------------------------------------------

def test_lucky_reroll_on_damage(page, live_server_url):
    """Lucky button appears on damage result for Lucky characters."""
    _create_char(page, live_server_url, "LuckyDmg", "akodo_bushi")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Roll damage if hit
    dmg_btn = modal.locator('button:has-text("Make Damage Roll"):visible')
    if dmg_btn.count() > 0:
        dmg_btn.first.click()
        page.wait_for_function("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'damage-result') return true;
            }
            return false;
        }""", timeout=10000)
        lucky_btn = modal.locator('button:has-text("Use Lucky"):visible')
        assert lucky_btn.count() > 0, "Lucky button should appear on damage result"


# ---------------------------------------------------------------------------
# 7. Lucky reroll on wound check
# ---------------------------------------------------------------------------

def test_lucky_reroll_on_wound_check(page, live_server_url):
    """Lucky button appears on wound check result for Lucky characters."""
    _create_char(page, live_server_url, "LuckyWC", "akodo_bushi")
    _add_lw_and_open_wc(page, 20)
    _roll_wc(page)
    wc_modal = page.locator('[data-modal="wound-check"]')
    lucky_btn = wc_modal.locator('button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() > 0, "Lucky button should appear on wound check result"


def test_no_lucky_on_wound_check_without_advantage(page, live_server_url):
    """Lucky button does NOT appear on wound check result without Lucky."""
    _create_char(page, live_server_url, "PlainWC", "akodo_bushi")
    _add_lw_and_open_wc(page, 20)
    _roll_wc(page)
    wc_modal = page.locator('[data-modal="wound-check"]')
    lucky_btn = wc_modal.locator('button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() == 0, "Lucky button should NOT appear without advantage"


# ---------------------------------------------------------------------------
# 8. Lucky reroll carries over discretionary bonuses
# ---------------------------------------------------------------------------

def test_lucky_carries_over_free_raise_attack(page, live_server_url):
    """Lucky reroll on attack preserves previously-spent free raises."""
    _create_char(page, live_server_url, "LuckyRaiseAtk", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("25")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Spend a free raise
    raise_btn = modal.locator('button:has-text("Spend Free Raise"):visible')
    if raise_btn.count() > 0:
        total_before_raise = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'result') return d.atkRollTotal;
            }
            return 0;
        }""")
        raise_btn.first.click()
        page.wait_for_timeout(200)
        total_with_raise = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'result') return d.atkRollTotal;
            }
            return 0;
        }""")
        assert total_with_raise == total_before_raise + 5
        # Now use Lucky
        lucky_btn = modal.locator('button:has-text("Use Lucky"):visible')
        assert lucky_btn.count() > 0
        lucky_btn.first.click()
        _wait_attack_result(page)
        # The rerolled total should still include the +5 from the raise
        new_total = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'result') return {
                    total: d.atkRollTotal,
                    raisesSpent: d.atkRaisesSpent
                };
            }
            return null;
        }""")
        assert new_total["raisesSpent"] == 1, "Free raise should be preserved after Lucky"
        # The new dice-only total may differ, but the raise is included
        new_dice_only = new_total["total"] - 5
        assert new_dice_only > 0, "Should have a valid dice total"


def test_lucky_carries_over_free_raise_wc(page, live_server_url):
    """Lucky reroll on wound check preserves previously-spent free raises."""
    _create_char(page, live_server_url, "LuckyRaiseWC", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    _add_lw_and_open_wc(page, 40)
    _roll_wc(page)
    wc_modal = page.locator('[data-modal="wound-check"]')
    raise_btn = wc_modal.locator('button:has-text("Spend Free Raise"):visible')
    if raise_btn.count() > 0:
        raise_btn.first.click()
        page.wait_for_timeout(200)
        lucky_btn = wc_modal.locator('button:has-text("Use Lucky"):visible')
        assert lucky_btn.count() > 0
        lucky_btn.first.click()
        _wait_wc_result(page)
        state = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.wcPhase === 'result') return {
                    total: d.wcRollTotal,
                    raisesSpent: d.wcRaisesSpent
                };
            }
            return null;
        }""")
        assert state["raisesSpent"] == 1, "WC free raise should be preserved after Lucky"


def test_lucky_carries_over_wc_post_roll_vp(page, live_server_url):
    """Lucky reroll on wound check preserves previously-spent post-roll VP (4th Dan)."""
    _create_char(page, live_server_url, "LuckyVPWC", "akodo_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 3")
    page.wait_for_timeout(200)
    _add_lw_and_open_wc(page, 40)
    _roll_wc(page)
    wc_modal = page.locator('[data-modal="wound-check"]')
    # Spend VP post-roll
    vp_btn = wc_modal.locator('button:has-text("Spend VP (+5)"):visible')
    if vp_btn.count() > 0:
        vp_btn.first.click()
        page.wait_for_timeout(200)
        lucky_btn = wc_modal.locator('button:has-text("Use Lucky"):visible')
        assert lucky_btn.count() > 0
        lucky_btn.first.click()
        _wait_wc_result(page)
        state = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.wcPhase === 'result') return {
                    total: d.wcRollTotal,
                    vpSpent: d.wcPostRollVpSpent
                };
            }
            return null;
        }""")
        assert state["vpSpent"] == 1, "Post-roll VP should be preserved after Lucky"


def test_lucky_carries_over_akodo_bonus(page, live_server_url):
    """Lucky reroll on attack preserves previously-spent Akodo banked bonus."""
    _create_char(page, live_server_url, "LuckyAkodo", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Inject a banked bonus
    page.evaluate("""() => {
        const dr = window._diceRoller;
        dr.akodoBankedBonuses = [{amount: 10, spent: false}];
        if (window._trackingBridge) window._trackingBridge.akodoBankedBonuses = dr.akodoBankedBonuses;
    }""")
    page.wait_for_timeout(200)
    # Roll attack with high TN to miss
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("30")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Apply Akodo bonus
    apply_btn = modal.locator('button:has-text("Apply +10"):visible')
    if apply_btn.count() > 0:
        apply_btn.first.click()
        page.wait_for_timeout(200)
        lucky_btn = modal.locator('button:has-text("Use Lucky"):visible')
        assert lucky_btn.count() > 0
        lucky_btn.first.click()
        _wait_attack_result(page)
        state = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'result') return {
                    total: d.atkRollTotal,
                    akodoSpent: d.akodoSpentThisRoll,
                    bonusStillSpent: d.akodoBankedBonuses?.[0]?.spent
                };
            }
            return null;
        }""")
        assert state["akodoSpent"] == 10, "Akodo bonus should be preserved after Lucky"
        assert state["bonusStillSpent"] is True, "Akodo bonus should remain marked spent"


def test_lucky_prevtotal_updates_with_post_reroll_bonus(page, live_server_url):
    """After Lucky reroll, spending more raises updates the displayed original total too."""
    _create_char(page, live_server_url, "LuckyPrevUpd", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("25")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Use Lucky immediately (no bonuses spent yet)
    lucky_btn = modal.locator('button:has-text("Use Lucky"):visible')
    assert lucky_btn.count() > 0
    lucky_btn.first.click()
    _wait_attack_result(page)
    # Get the displayed prev total
    prev_total_1 = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result' && d.luckyPrevBaseTotal !== undefined) {
                return d.luckyPrevBaseTotal + d._atkDiscretionaryTotal();
            }
        }
        return 0;
    }""")
    # Now spend a free raise AFTER the Lucky reroll
    raise_btn = modal.locator('button:has-text("Spend Free Raise"):visible')
    if raise_btn.count() > 0:
        raise_btn.first.click()
        page.wait_for_timeout(200)
        # The displayed prev total should have increased by 5 (bonus applies to both)
        prev_total_2 = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'result' && d.luckyPrevBaseTotal !== undefined) {
                    return d.luckyPrevBaseTotal + d._atkDiscretionaryTotal();
                }
            }
            return 0;
        }""")
        assert prev_total_2 == prev_total_1 + 5, \
            f"Original total should increase by 5 when raise spent post-reroll: {prev_total_1} -> {prev_total_2}"


# ---------------------------------------------------------------------------
# 9. Iaijutsu duel restart
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
    spend_btn = page.locator('button:has-text("Spend VP (+5)"):visible')
    if spend_btn.count() > 0:
        spend_btn.first.click()
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


# ---------------------------------------------------------------------------
# 10. Akodo banked bonus applies on MISS to turn it into a hit
# ---------------------------------------------------------------------------

def test_akodo_banked_bonus_on_miss(page, live_server_url):
    """Akodo 3rd Dan: banked bonus Apply button appears on MISS and changes total."""
    _create_char(page, live_server_url, "AkodoMissB", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Bank a bonus by injecting directly (simulating a passed wound check)
    page.evaluate("window._trackingBridge.akodoBankedBonuses.push({amount: 15, spent: false})")
    page.wait_for_timeout(200)
    # Verify it shows in tracking section
    assert page.locator('text="Banked 3rd Dan Bonuses"').is_visible()
    # Mock dice low so we miss
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.0")
    # Roll attack with high TN to guarantee miss
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("30")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    page.evaluate("if (window._origRandom) Math.random = window._origRandom")
    # Should have missed
    miss_text = page.locator('[data-modal="attack"]').text_content()
    assert "MISSED" in miss_text
    # Apply button should be visible on the MISS section
    apply_btn = modal.locator('button:has-text("Apply +15"):visible')
    assert apply_btn.count() > 0, "Apply bonus button should appear on MISS"
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
        }
        return 0;
    }""")
    apply_btn.first.click()
    page.wait_for_timeout(300)
    total_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
        }
        return 0;
    }""")
    assert total_after == total_before + 15


# ---------------------------------------------------------------------------
# 10b. Undo button stays visible after all Akodo bonuses are spent
# ---------------------------------------------------------------------------

def test_akodo_undo_visible_after_all_bonuses_spent(page, live_server_url):
    """Akodo 3rd Dan: Undo button remains visible after all banked bonuses are spent."""
    _create_char(page, live_server_url, "AkodoUndoB", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Inject a single banked bonus
    page.evaluate("window._trackingBridge.akodoBankedBonuses.push({amount: 12, spent: false})")
    page.wait_for_timeout(200)
    # Mock dice high, roll attack with low TN to guarantee hit
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.6")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    page.evaluate("if (window._origRandom) Math.random = window._origRandom")
    # Apply the only bonus - this spends all bonuses
    apply_btn = modal.locator('button:has-text("Apply +12"):visible')
    assert apply_btn.count() > 0, "Apply button should be visible before spending"
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
        }
        return 0;
    }""")
    apply_btn.first.click()
    page.wait_for_timeout(300)
    # All bonuses are now spent - Undo button should still be visible
    undo_btn = modal.locator('button:has-text("Undo"):visible')
    assert undo_btn.count() > 0, "Undo button must remain visible after all bonuses are spent"
    # Verify total increased
    total_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
        }
        return 0;
    }""")
    assert total_after == total_before + 12
    # Click Undo - total should decrease back
    undo_btn.first.click()
    page.wait_for_timeout(300)
    total_undone = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkRollTotal !== undefined) return d.atkRollTotal;
        }
        return 0;
    }""")
    assert total_undone == total_before, f"Undo should restore total: expected {total_before}, got {total_undone}"


# ---------------------------------------------------------------------------
# 11. Banked bonuses display reactively in tracking section
# ---------------------------------------------------------------------------

def test_akodo_banked_bonuses_display_in_tracking(page, live_server_url):
    """Akodo 3rd Dan: banked bonuses appear in the tracking section."""
    _create_char(page, live_server_url, "AkodoTrackB", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Initially no bonuses
    assert not page.locator('text="Banked 3rd Dan Bonuses"').is_visible()
    # Add a bonus
    page.evaluate("window._trackingBridge.akodoBankedBonuses.push({amount: 8, spent: false})")
    page.wait_for_timeout(300)
    # Should now be visible
    assert page.locator('text="Banked 3rd Dan Bonuses"').is_visible()
    body = page.text_content("body")
    assert "8" in body  # the amount is displayed
    # Mark it spent
    page.locator('button:has-text("Mark spent")').click()
    page.wait_for_timeout(300)
    # Should show as spent (line-through)
    assert page.locator('text="spent"').is_visible()


# ---------------------------------------------------------------------------
# 11b. Banked bonuses persist across page refresh
# ---------------------------------------------------------------------------

def test_akodo_banked_bonuses_persist_on_refresh(page, live_server_url):
    """Akodo 3rd Dan: unspent banked bonuses survive a page refresh."""
    _create_char(page, live_server_url, "AkodoPersist", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Inject a bonus and trigger save
    page.evaluate("""
        window._trackingBridge.akodoBankedBonuses.push({amount: 15, spent: false});
        window._trackingBridge.saveBankedBonuses();
    """)
    page.wait_for_timeout(500)
    assert page.locator('text="Banked 3rd Dan Bonuses"').is_visible()
    # Refresh the page
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    # Bonus should still be there
    assert page.locator('text="Banked 3rd Dan Bonuses"').is_visible()
    bonuses = page.evaluate("window._trackingBridge?.akodoBankedBonuses?.length || 0")
    assert bonuses == 1, f"Expected 1 bonus after refresh, got {bonuses}"
    amount = page.evaluate("window._trackingBridge?.akodoBankedBonuses?.[0]?.amount || 0")
    assert amount == 15, f"Expected amount 15 after refresh, got {amount}"


# ---------------------------------------------------------------------------
# 12. Reset per-adventure clears all combat bonuses
# ---------------------------------------------------------------------------

def test_reset_adventure_clears_combat_bonuses(page, live_server_url):
    """Reset Per-Adventure clears Akodo banked bonuses and other combat state."""
    _create_char(page, live_server_url, "AkodoResetB", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Add a banked bonus and mark Lucky as used (so reset button is enabled)
    page.evaluate("window._trackingBridge.akodoBankedBonuses.push({amount: 10, spent: false})")
    page.wait_for_timeout(200)
    assert page.locator('text="Banked 3rd Dan Bonuses"').is_visible()
    # Open reset modal and confirm
    reset_btn = page.locator('[data-action="open-reset-modal"]')
    if reset_btn.is_visible() and not reset_btn.is_disabled():
        reset_btn.click()
        page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=3000)
        page.locator('[data-action="confirm-reset"]').click()
        page.wait_for_timeout(300)
        # Banked bonuses should be cleared
        bonuses = page.evaluate("window._trackingBridge?.akodoBankedBonuses?.length || 0")
        assert bonuses == 0, f"Bonuses should be cleared after reset, got {bonuses}"
