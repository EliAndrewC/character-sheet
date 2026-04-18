"""E2E: Iaijutsu duel modal - setup, contested roll, focus/strike, damage."""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character

pytestmark = [pytest.mark.rolls]


def _create_duelist(page, live_server_url, name="Duelist", school="akodo_bushi"):
    """Create a character with iaijutsu knack (Akodo Bushi has it)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")


def _wait_alpine(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'idle') return true;
        }
        return false;
    }""", timeout=5000)


def _open_duel_modal(page):
    """Click iaijutsu dice button, then select Iaijutsu Duel from the dropdown."""
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    # The roll menu should appear with "Iaijutsu Duel" option
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    if menu.is_visible():
        menu.locator('button:text("Iaijutsu Duel")').click()
    page.wait_for_selector('[data-modal="iaijutsu-duel"]', state='visible', timeout=3000)


# ---------------------------------------------------------------------------
# Duel modal basics
# ---------------------------------------------------------------------------


def test_duel_option_in_iaijutsu_menu(page, live_server_url):
    """The iaijutsu roll menu includes an 'Iaijutsu Duel' option."""
    _create_duelist(page, live_server_url, "DuelOption")
    _wait_alpine(page)
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    assert menu.locator('button:text("Iaijutsu Duel")').is_visible()


def test_duel_modal_opens_with_setup(page, live_server_url):
    """Iaijutsu Duel opens to the setup phase showing player TN."""
    _create_duelist(page, live_server_url, "DuelSetup")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    assert modal.locator('text="Your Duel TN"').is_visible()


def test_duel_player_tn_computed(page, live_server_url):
    """Player's duel TN = floor(total_xp / 10). Default starting XP is 150 -> TN 15."""
    _create_duelist(page, live_server_url, "DuelTN")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    # Starting XP 150 + 0 earned = 150 / 10 = 15
    assert "15" in modal.locator('text="Your Duel TN"').locator('..').text_content()


# ---------------------------------------------------------------------------
# Contested roll
# ---------------------------------------------------------------------------


def test_contested_roll_proceeds(page, live_server_url):
    """Entering opponent XP and clicking Proceed leads to contested roll phase."""
    _create_duelist(page, live_server_url, "DuelContest")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    page.wait_for_timeout(300)
    assert modal.locator('button:text("Roll Contested Iaijutsu")').is_visible()


def test_contested_roll_shows_result(page, live_server_url):
    """Rolling the contested iaijutsu shows a result with the roll total."""
    _create_duelist(page, live_server_url, "DuelContestRoll")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)
    assert modal.locator('text="Contested roll:"').is_visible()


# ---------------------------------------------------------------------------
# Focus / Strike
# ---------------------------------------------------------------------------


def test_focus_strike_phase_shows_buttons(page, live_server_url):
    """After contested roll, Focus and Strike buttons appear."""
    _create_duelist(page, live_server_url, "DuelFocus")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    page.wait_for_timeout(300)
    assert modal.locator('button:text("Strike!")').is_visible()
    assert modal.locator('button:text("Focus (+5 to your TN)")').is_visible()


def test_focus_alternation(page, live_server_url):
    """After focusing, the Focus button is disabled until opponent focuses."""
    _create_duelist(page, live_server_url, "DuelAlt")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    page.wait_for_timeout(300)
    # Focus should be enabled
    focus_btn = modal.locator('button:text("Focus (+5 to your TN)")')
    assert not focus_btn.is_disabled()
    focus_btn.click()
    page.wait_for_timeout(100)
    # Now Focus should be disabled
    assert focus_btn.is_disabled()
    # Opponent Focus should be enabled
    opp_btn = modal.locator('button:text("Opponent Focuses")')
    assert not opp_btn.is_disabled()


# ---------------------------------------------------------------------------
# Strike + dice animation
# ---------------------------------------------------------------------------


def test_strike_shows_dice_animation(page, live_server_url):
    """The Strike roll shows dice animation in the duel tray."""
    _create_duelist(page, live_server_url, "DuelStrike")
    _wait_alpine(page)
    # Re-enable animations for this specific test
    page.evaluate("if (window._diceRoller) window._diceRoller.prefs.dice_animation_enabled = true")
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Strike!")').click()
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation-duel svg.die').length > 0",
        timeout=15000,
    )
    assert page.locator('#dice-animation-duel svg.die').count() > 0


def _get_to_strike_result(page, live_server_url, name):
    """Helper: create duelist, open duel, contested roll, proceed, strike."""
    _create_duelist(page, live_server_url, name)
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=3000)
    modal.locator('button:text("Strike!")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'strike-result') return true;
        }
        return false;
    }""", timeout=15000)
    return modal


def test_duel_strike_hit_shows_damage_button(page, live_server_url):
    """After a strike hit, Roll Damage button appears."""
    modal = _get_to_strike_result(page, live_server_url, "DuelDmgBtn")
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelStrikeHit !== undefined) return d.duelStrikeHit;
        }
        return false;
    }""")
    if hit:
        assert modal.locator('button:text("Roll Damage")').is_visible()


def test_duel_strike_shows_opponent_input(page, live_server_url):
    """After a strike, opponent roll input is shown."""
    modal = _get_to_strike_result(page, live_server_url, "DuelOppInput")
    modal.locator('input[placeholder="Enter total"]').wait_for(state='visible', timeout=3000)
    assert modal.locator('input[placeholder="Enter total"]').is_visible()


def _get_to_opponent_damage(page, live_server_url, name):
    """Helper: get to the 'opponent hit you' phase by entering a high opponent roll.

    Handles both cases: player hit (must roll damage first) and player missed.
    """
    modal = _get_to_strike_result(page, live_server_url, name)
    # Check if player hit (damage button visible) or missed
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelStrikeHit !== undefined) return d.duelStrikeHit;
        }
        return false;
    }""")
    if hit:
        # Player hit: roll damage first, then enter opponent roll in damage-result phase
        modal.locator('button:text("Roll Damage")').click()
        page.wait_for_function("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.duelPhase === 'damage-result') return true;
            }
            return false;
        }""", timeout=15000)
        page.wait_for_timeout(300)
        modal.locator('input[placeholder="Opponent\'s total"]').fill("999")
    else:
        # Player missed: enter opponent roll directly in strike-result phase
        modal.locator('input[placeholder="Enter total"]').fill("999")
    # Click the visible Apply Roll button
    modal.locator('button:text("Apply Roll"):visible').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'opponent-damage') return true;
        }
        return false;
    }""", timeout=5000)
    return modal


def test_duel_opponent_hit_shows_damage_input(page, live_server_url):
    """When opponent hits, the damage input and Make Wound Check button appear."""
    _get_to_opponent_damage(page, live_server_url, "DuelOppHit")
    # The opponent-damage phase should show damage input and wound check button
    page.wait_for_selector('input[placeholder="Damage"]', state='visible', timeout=3000)
    assert page.locator('button:text("Make Wound Check")').is_visible()


def test_duel_opponent_hit_shows_player_tn(page, live_server_url):
    """When opponent hits, the player's TN is shown as reference."""
    _get_to_opponent_damage(page, live_server_url, "DuelOppTN")
    page.wait_for_selector('input[placeholder="Damage"]', state='visible', timeout=3000)
    assert page.locator('text="Your TN to be hit:"').is_visible()


def test_duel_opponent_wound_check_opens(page, live_server_url):
    """Clicking Make Wound Check opens the wound check modal with dice animation."""
    _get_to_opponent_damage(page, live_server_url, "DuelOppWC")
    page.locator('input[placeholder="Damage"]').fill("20")
    page.locator('button:text("Make Wound Check")').click()
    # The wound check modal should open and show results
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=15000)
    wc_modal = page.locator('[data-modal="wound-check"]')
    assert wc_modal.is_visible()
    # Should show pass or fail result
    assert wc_modal.locator('text="Wound check PASSED"').is_visible() or \
           wc_modal.locator('text="Wound check FAILED"').is_visible()


def test_duel_katana_weapon_default(page, live_server_url):
    """The duel setup shows Katana (4k2) instead of weapon input fields."""
    _create_duelist(page, live_server_url, "DuelKatana")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    assert modal.locator('text="Weapon: Katana (4k2)"').is_visible()
