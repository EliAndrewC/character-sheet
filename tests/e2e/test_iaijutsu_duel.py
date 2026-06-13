"""E2E: Iaijutsu duel modal - setup, contested roll, focus/strike, damage."""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character

pytestmark = [pytest.mark.rolls]


def _create_duelist(page, live_server_url, name="Duelist", school="akodo_bushi",
                    foreign_knacks=()):
    """Create a character with iaijutsu knack (Akodo Bushi has it).

    ``foreign_knacks`` adds non-school knacks (rank 1) via the picker -
    e.g. ("conviction",) builds the iaijutsu+conviction combination that
    only exists through foreign knacks (no school has both natively).
    """
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    click_plus(page, "skill_bragging", 1)
    for kid in foreign_knacks:
        page.locator('[data-testid="add-foreign-knack-btn"]').click()
        page.wait_for_selector('[data-testid="foreign-knack-select"]', state="visible", timeout=2000)
        page.select_option('[data-testid="foreign-knack-select"]', kid)
        page.wait_for_selector(f'[data-testid="foreign-knack-row-{kid}"]', timeout=2000)
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
    page.wait_for_selector('[data-modal="iaijutsu-duel"]', state='visible', timeout=10000)


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
    menu.locator('button:text("Iaijutsu Duel")').wait_for(state="visible", timeout=5000)
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
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state="visible", timeout=5000)
    assert modal.locator('button:text("Roll Contested Iaijutsu")').is_visible()


def test_contested_roll_shows_result(page, live_server_url):
    """Rolling the contested iaijutsu shows a result with the roll total."""
    _create_duelist(page, live_server_url, "DuelContestRoll")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)
    # The phase poll can win the race against Alpine's DOM flush - wait
    # for the paint instead of asserting visibility instantly.
    modal.locator('text="Contested roll:"').wait_for(state="visible", timeout=5000)
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
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Strike!")').wait_for(state="visible", timeout=5000)
    assert modal.locator('button:text("Strike!")').is_visible()
    modal.locator('button:text("Focus (+5 to your TN)")').wait_for(state="visible", timeout=5000)
    assert modal.locator('button:text("Focus (+5 to your TN)")').is_visible()


def test_focus_alternation(page, live_server_url):
    """After focusing, the Focus button is disabled until opponent focuses."""
    _create_duelist(page, live_server_url, "DuelAlt")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=10000)
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
        assert modal.locator('button:text-is("Roll Damage")').is_visible()


def test_duel_strike_shows_opponent_input(page, live_server_url):
    """After a strike, opponent roll input is shown."""
    modal = _get_to_strike_result(page, live_server_url, "DuelOppInput")
    modal.locator('input[placeholder="Enter total"]').wait_for(state='visible', timeout=10000)
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
        modal.locator('button:text-is("Roll Damage")').click()
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
    page.wait_for_selector('input[placeholder="Damage"]', state='visible', timeout=10000)
    page.locator('button:text("Make Wound Check")').wait_for(state="visible", timeout=5000)
    assert page.locator('button:text("Make Wound Check")').is_visible()


def test_duel_opponent_hit_shows_player_tn(page, live_server_url):
    """When opponent hits, the player's TN is shown as reference."""
    _get_to_opponent_damage(page, live_server_url, "DuelOppTN")
    page.wait_for_selector('input[placeholder="Damage"]', state='visible', timeout=10000)
    page.locator('text="Your TN to be hit:"').wait_for(state="visible", timeout=5000)
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
    # The phase poll can win the race against Alpine's DOM flush - wait for
    # the painted result text instead of asserting visibility instantly.
    # Both result divs are always in the DOM (x-show toggles display), so
    # filter to the visible one; without the filter the locator strictly
    # resolves to the hidden PASSED div whenever the check failed.
    wc_modal.locator(
        'text=/Wound check (PASSED|FAILED)/ >> visible=true'
    ).wait_for(state="visible", timeout=5000)
    assert wc_modal.is_visible()


def test_duel_katana_weapon_default(page, live_server_url):
    """The duel setup shows Katana (4k2) instead of weapon input fields."""
    _create_duelist(page, live_server_url, "DuelKatana")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    assert modal.locator('text="Weapon: Katana (4k2)"').is_visible()


def test_kitsune_warden_iaijutsu_duel_offers_no_special_ability_swap(page, live_server_url):
    """Regression guard: a Kitsune Warden opens the iaijutsu duel modal
    and does NOT see any Kitsune Warden ring-swap UI inside it. Iaijutsu
    is rules-excluded from the special ability; the duel modal's content
    is independent from the Kitsune swap blocks/checkboxes added in
    Phases 8-10."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K11Duel")
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    page.wait_for_timeout(200)
    # Bump Water to 4 so the swap WOULD be meaningful on non-iaijutsu
    # rolls; this confirms the duel UI still doesn't surface it.
    click_plus(page, "ring_water", 1)
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_water\"]')?.value === '4'",
        timeout=5000,
    )
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Kitsune iaijutsu duel")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    assert modal.is_visible()
    # No Kitsune-swap UI elements anywhere inside the duel modal.
    assert modal.locator('[data-testid="kitsune-skill-swap-block"]').count() == 0
    assert modal.locator('[data-testid="kitsune-attack-ring-swap"]').count() == 0
    assert modal.locator('[data-testid="kitsune-wc-ring-swap"]').count() == 0
    assert modal.locator('[data-testid="kitsune-parry-swap-block"]').count() == 0


def test_kitsune_warden_iaijutsu_strike_has_no_swap_in_roll_menu(page, live_server_url):
    """The roll menu for Kitsune's iaijutsu knack offers Iaijutsu Duel and
    Iaijutsu Strike but NO Kitsune-swap submenu (iaijutsu is rules-
    excluded server-side via _attach_kitsune_swaps)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K11IaiStrike")
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    page.wait_for_timeout(200)
    click_plus(page, "ring_water", 1)
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_water\"]')?.value === '4'",
        timeout=5000,
    )
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Kitsune iaijutsu strike menu")
    _wait_alpine(page)
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    # The Kitsune-skill-swap-block must NOT be present in this menu.
    block = page.locator('[data-testid="kitsune-skill-swap-block"]')
    assert not block.is_visible(), \
        "Kitsune swap block should not appear on the iaijutsu knack roll menu"


def _wait_duel_copy_ready(page, timeout=10000):
    page.wait_for_function(
        """() => {
            const modal = document.querySelector('[data-modal="iaijutsu-duel"]');
            if (!modal) return false;
            const btns = modal.querySelectorAll('[data-action="copy-roll-image"]');
            for (const b of btns) {
                if (b.getAttribute('data-state') === 'ready'
                        && b.offsetParent !== null) {
                    return true;
                }
            }
            return false;
        }""",
        timeout=timeout,
    )


def test_duel_contested_result_has_copy_as_image_button(page, live_server_url):
    """The duel's contested-result panel exposes a Copy-as-image
    button. Each duel sub-phase pre-renders its own card on
    transition, so contested / strike / damage each carry their own
    Copy at the right moment."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    _create_duelist(page, live_server_url, "DuelContestCopy")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(
        state='visible', timeout=10000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function(
        """() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.duelPhase === 'contested-result') return true;
            }
            return false;
        }""",
        timeout=15000,
    )
    _wait_duel_copy_ready(page)


def test_duel_strike_result_has_copy_as_image_button(page, live_server_url):
    """The duel's strike-result panel exposes its own Copy button
    pre-rendered from the strike roll."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    _create_duelist(page, live_server_url, "DuelStrikeCopy")
    _wait_alpine(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(
        state='visible', timeout=10000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function(
        """() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.duelPhase === 'contested-result') return true;
            }
            return false;
        }""",
        timeout=15000,
    )
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    page.wait_for_timeout(200)
    modal.locator('button:text("Strike!")').click()
    page.wait_for_function(
        """() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.duelPhase === 'strike-result') return true;
            }
            return false;
        }""",
        timeout=15000,
    )
    _wait_duel_copy_ready(page)


# ---------------------------------------------------------------------------
# Conviction during the strike portion (rules quirk: discretionary bonuses
# are banned on the strike, its wound checks, and its damage - EXCEPT the
# character's own Conviction. Only possible via foreign knacks, since no
# school has both iaijutsu and conviction natively.)
# ---------------------------------------------------------------------------


def _mock_dice_low(page):
    """Mock dice to always roll 1 (deterministic totals)."""
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.0")


def _duel_state(page, *fields):
    """Read duel/wc fields off the dice-roller Alpine component."""
    return page.evaluate("""(fields) => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase !== undefined) {
                const out = {};
                for (const f of fields) out[f] = d[f];
                return out;
            }
        }
        return null;
    }""", list(fields))


def _walk_to_strike_result(page, opponent_xp):
    """From the sheet, open the duel and walk to the strike-result phase."""
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill(str(opponent_xp))
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=10000)
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


def _walk_to_focus_strike(page, opponent_xp):
    """From the sheet, open the duel and walk to the focus/strike phase."""
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill(str(opponent_xp))
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
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
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=10000)
    return modal


def test_focus_strike_shows_odds_chart(page, live_server_url):
    """The focus/strike phase shows the strike odds chart: your hit/damage
    row pair plus three sample opponent pools with hit/damage/~SW, with no
    VP spending levels anywhere."""
    _create_duelist(page, live_server_url, "DuelChart")
    _wait_alpine(page)
    modal = _walk_to_focus_strike(page, 200)
    chart = modal.locator('[data-testid="duel-strike-chart"]')
    chart.wait_for(state="visible", timeout=5000)
    # Your strike rows: now + if-they-focus, TN 20 / 25 (opponent XP 200).
    yours_now = chart.locator('[data-testid="duel-chart-yours-now"]')
    yours_focused = chart.locator('[data-testid="duel-chart-yours-focused"]')
    assert "vs TN 20" in yours_now.text_content()
    assert "vs TN 25" in yours_focused.text_content()
    assert "%" in yours_now.text_content()
    # Three sample opponent pools.
    for pool in ("8k4", "10k5", "10k7"):
        row = chart.locator(f'[data-testid="duel-chart-opp-{pool}"]')
        row.wait_for(state="visible", timeout=5000)
        assert "%" in row.text_content()
    # No void-spend rows: the chart never mentions void points as an option.
    assert "void point" not in chart.locator("table").first.text_content().lower()
    # Unwounded duelist (0 LW): the ~SW caveat omits the light-wounds clause.
    # inner_text() (not text_content) so x-show=display:none text is excluded.
    assert "on top of your current" not in chart.inner_text()


def test_focus_strike_chart_sw_caveat_shows_light_wounds_when_wounded(page, live_server_url):
    """When the duelist has light wounds, the ~SW caveat names the current
    total; at 0 LW (the default) the clause is omitted."""
    _create_duelist(page, live_server_url, "DuelChartWounded")
    _wait_alpine(page)
    # Add 12 light wounds, dismissing the auto-opened wound-check modal.
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "12")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_timeout(300)
    wc = page.locator('[data-modal="wound-check"]')
    if wc.is_visible():
        wc.locator('button', has_text="×").first.click()
    modal = _walk_to_focus_strike(page, 200)
    chart = modal.locator('[data-testid="duel-strike-chart"]')
    chart.wait_for(state="visible", timeout=5000)
    assert "on top of your current total of 12 light wounds" in chart.inner_text()


def test_focus_strike_chart_reacts_to_focus_clicks(page, live_server_url):
    """Focusing updates the chart TNs live: opponent focusing raises their
    TN (your hit odds fall); you focusing raises yours (their listed TNs
    rise)."""
    _create_duelist(page, live_server_url, "DuelChartFocus")
    _wait_alpine(page)
    modal = _walk_to_focus_strike(page, 200)
    chart = modal.locator('[data-testid="duel-strike-chart"]')
    chart.wait_for(state="visible", timeout=5000)

    def yours_now_hit():
        txt = chart.locator('[data-testid="duel-chart-yours-now"]').text_content()
        return int(txt.split("%")[0].split()[-1])

    hit_before = yours_now_hit()
    modal.locator('button:text("Opponent Focuses")').click()
    page.wait_for_timeout(200)
    assert "vs TN 25" in chart.locator('[data-testid="duel-chart-yours-now"]').text_content()
    assert yours_now_hit() <= hit_before, \
        "raising the opponent's TN must not raise your hit odds"
    # Your own focus raises your TN: the opponent table's heading TNs shift.
    head_before = chart.locator("table").nth(1).text_content()
    assert "vs TN 15" in head_before  # default 150 XP -> TN 15
    modal.locator('button:text("Focus (+5 to your TN)")').click()
    page.wait_for_timeout(200)
    head_after = chart.locator("table").nth(1).text_content()
    assert "vs TN 20" in head_after


def test_duel_strike_conviction_spend_flips_miss_to_hit(page, live_server_url):
    """A duelist with (foreign) conviction sees Spend Conviction on the
    strike result; spending +1 updates the strike total, hit state, and
    excess - here flipping a miss-by-1 into a hit. Undo reverses it."""
    _create_duelist(page, live_server_url, "DuelConvStrike",
                    foreign_knacks=("conviction",))
    _wait_alpine(page)
    _mock_dice_low(page)
    # With all dice mocked to 1, the strike total is deterministic:
    # min(kept, rolled) * 1 + flat. Pick opponent XP so their TN is
    # exactly total+1 - a miss by 1 that one conviction point flips.
    f = page.evaluate("""() => {
        const data = JSON.parse(document.getElementById('roll-formulas').textContent || '{}');
        return data['knack:iaijutsu:strike'] || null;
    }""")
    assert f is not None, "strike formula must exist for an iaijutsu character"
    total = min(f["kept"], f["rolled"]) + (f.get("flat") or 0)
    modal = _walk_to_strike_result(page, (total + 1) * 10)

    modal.locator('text="MISSED"').wait_for(state="visible", timeout=5000)
    spend = modal.locator('[data-action="spend-conviction-duel-strike"]')
    spend.wait_for(state="visible", timeout=5000)
    assert spend.is_visible(), \
        "Spend Conviction must be offered on the duel strike result"
    # No priest-ally conviction anywhere in the duel modal.
    assert modal.locator('[data-action^="spend-priest-ally"]').count() == 0

    before = _duel_state(page, "duelStrikeRoll", "duelStrikeHit", "duelStrikeExcess")
    assert before["duelStrikeRoll"] == total
    assert before["duelStrikeExcess"] == -1
    spend.click()
    page.wait_for_timeout(150)
    after = _duel_state(page, "duelStrikeRoll", "duelStrikeHit", "duelStrikeExcess",
                        "convictionSpentThisRoll")
    assert after["duelStrikeRoll"] == total + 1
    assert after["convictionSpentThisRoll"] == 1
    assert after["duelStrikeHit"] is True, "spending conviction should flip the miss to a hit"
    assert after["duelStrikeExcess"] == 0
    assert "HIT - exceeded TN by" in modal.text_content()
    # Breakdown line appears.
    assert "Conviction point" in modal.text_content()

    modal.locator('[data-action="undo-conviction-duel-strike"]').click()
    page.wait_for_timeout(150)
    undone = _duel_state(page, "duelStrikeRoll", "duelStrikeHit", "convictionSpentThisRoll")
    assert undone["duelStrikeRoll"] == total
    assert undone["duelStrikeHit"] is False
    assert undone["convictionSpentThisRoll"] == 0


def test_duel_contested_conviction_spend_and_pool_carry(page, live_server_url):
    """The contested iaijutsu roll is a normal roll, so own conviction may
    be spent on it (+1 each, with undo) - but never a party priest's pool.
    Points spent there come out of the same daily pool as the strike's,
    and the per-roll counter resets when the strike is rolled."""
    _create_duelist(page, live_server_url, "DuelConvContested",
                    foreign_knacks=("conviction",))
    _wait_alpine(page)
    _mock_dice_low(page)
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("10")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    modal.locator('button:text("Roll Contested Iaijutsu")').wait_for(state='visible', timeout=10000)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'contested-result') return true;
        }
        return false;
    }""", timeout=15000)

    spend = modal.locator('[data-action="spend-conviction-duel-contested"]')
    spend.wait_for(state="visible", timeout=5000)
    assert modal.locator('[data-action^="spend-priest-ally"]').count() == 0, \
        "priest-ally conviction must never be offered inside the duel modal"

    before = _duel_state(page, "duelContestedRoll")
    spend.click()
    page.wait_for_timeout(150)
    after = _duel_state(page, "duelContestedRoll", "convictionSpentThisRoll")
    assert after["duelContestedRoll"] == before["duelContestedRoll"] + 1
    assert after["convictionSpentThisRoll"] == 1
    assert "Conviction point" in modal.text_content()

    # Undo, then re-spend: end the phase with 1 point spent on the contested.
    modal.locator('[data-action="undo-conviction-duel-contested"]').click()
    page.wait_for_timeout(150)
    undone = _duel_state(page, "duelContestedRoll", "convictionSpentThisRoll")
    assert undone["duelContestedRoll"] == before["duelContestedRoll"]
    assert undone["convictionSpentThisRoll"] == 0
    spend.click()
    page.wait_for_timeout(150)

    # Proceed to the strike: the per-roll counter resets, the contested
    # spend stays deducted from the daily pool (rank 1 -> pool 2, 1 left).
    modal.locator('button:text("Proceed to Focus / Strike")').click()
    modal.locator('button:text("Strike!")').wait_for(state='visible', timeout=10000)
    modal.locator('button:text("Strike!")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'strike-result') return true;
        }
        return false;
    }""", timeout=15000)
    strike = _duel_state(page, "convictionSpentThisRoll")
    assert strike["convictionSpentThisRoll"] == 0
    pool_left = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase !== undefined) return d.convictionPoolAvail();
        }
        return null;
    }""")
    assert pool_left == 1, f"contested spend must deduct from the daily pool; got {pool_left}"


def test_duel_strike_no_conviction_no_spend_block(page, live_server_url):
    """A duelist without the conviction knack sees no conviction controls
    on the strike result."""
    modal = _get_to_strike_result(page, live_server_url, "DuelNoConv")
    assert not modal.locator('[data-action="spend-conviction-duel-strike"]').is_visible()


def test_duel_damage_conviction_spend_increments_total(page, live_server_url):
    """Conviction can be spent on the strike's damage roll: +1 to the
    damage total per point, with an undo."""
    _create_duelist(page, live_server_url, "DuelConvDmg",
                    foreign_knacks=("conviction",))
    _wait_alpine(page)
    _mock_dice_low(page)
    # Opponent XP 10 -> TN 1: even all-1 dice hit, guaranteeing the
    # damage phase is reachable.
    modal = _walk_to_strike_result(page, 10)
    modal.locator('button:text-is("Roll Damage")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.duelPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=15000)
    spend = modal.locator('[data-action="spend-conviction-duel-damage"]')
    spend.wait_for(state="visible", timeout=5000)
    assert spend.is_visible(), \
        "Spend Conviction must be offered on the duel damage result"
    before = _duel_state(page, "duelDamageTotal")
    spend.click()
    page.wait_for_timeout(150)
    after = _duel_state(page, "duelDamageTotal", "convictionSpentThisRoll")
    assert after["duelDamageTotal"] == before["duelDamageTotal"] + 1
    assert after["convictionSpentThisRoll"] == 1
    assert "Conviction point" in modal.text_content()
    modal.locator('[data-action="undo-conviction-duel-damage"]').click()
    page.wait_for_timeout(150)
    undone = _duel_state(page, "duelDamageTotal", "convictionSpentThisRoll")
    assert undone["duelDamageTotal"] == before["duelDamageTotal"]
    assert undone["convictionSpentThisRoll"] == 0


def test_duel_strike_wound_check_conviction_only_discretionary(page, live_server_url):
    """The wound check caused by the opponent's strike offers ONLY the
    character's own conviction: no raises, no priest-ally buttons, no
    auto-apply until the player accepts the result."""
    _create_duelist(page, live_server_url, "DuelConvWC",
                    foreign_knacks=("conviction",))
    _wait_alpine(page)
    _mock_dice_low(page)
    modal = _walk_to_strike_result(page, 200)
    # Mocked-low dice always miss TN 20; opponent roll 999 always hits us.
    modal.locator('input[placeholder="Enter total"]').fill("999")
    modal.locator('button:text("Apply Roll"):visible').click()
    page.wait_for_selector('input[placeholder="Damage"]', state='visible', timeout=10000)
    page.locator('input[placeholder="Damage"]').fill("40")
    page.locator('button:text("Make Wound Check")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=15000)
    wc = page.locator('[data-modal="wound-check"]')
    wc.locator('text="Wound check FAILED"').wait_for(state="visible", timeout=5000)

    state = _duel_state(page, "wcResultApplied", "wcRollTotal")
    assert state["wcResultApplied"] is False, \
        "a failed strike WC must NOT auto-apply while conviction is spendable"
    # Only the strike conviction block; none of the banned discretionary controls.
    assert wc.locator('[data-action="spend-conviction-wc-strike"]').is_visible()
    assert not wc.locator('[data-action="spend-conviction-wc"]').is_visible()
    assert not wc.locator('button:text("Spend Free Raise (+5)")').is_visible()
    assert wc.locator('[data-action^="spend-priest-ally"]:visible').count() == 0

    wc.locator('[data-action="spend-conviction-wc-strike"]').click()
    page.wait_for_timeout(150)
    after = _duel_state(page, "wcRollTotal", "convictionSpentThisRoll")
    assert after["wcRollTotal"] == state["wcRollTotal"] + 1
    assert after["convictionSpentThisRoll"] == 1

    wc.locator('[data-action="wc-strike-accept-result"]').click()
    page.wait_for_timeout(300)
    applied = _duel_state(page, "wcResultApplied")
    assert applied["wcResultApplied"] is True
    # The failure landed on the sheet: serious wounds taken, LW reset.
    sw = page.evaluate("() => window._trackingBridge?.seriousWounds")
    lw = page.evaluate("() => window._trackingBridge?.lightWounds")
    assert sw >= 1
    assert lw == 0


def test_duel_strike_wound_check_auto_applies_without_conviction(page, live_server_url):
    """Without conviction, a failed strike wound check keeps its original
    behavior: the failure is applied immediately, no discretionary UI."""
    _create_duelist(page, live_server_url, "DuelNoConvWC")
    _wait_alpine(page)
    _mock_dice_low(page)
    # Take light wounds, then use the manual Iaijutsu Strike Wound Check
    # button (same rollWoundCheck path as the duel's).
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_selector('[data-action="roll-wound-check-strike"]', state='visible', timeout=10000)
    page.locator('[data-action="roll-wound-check-strike"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=15000)
    wc = page.locator('[data-modal="wound-check"]')
    wc.locator('text="Wound check FAILED"').wait_for(state="visible", timeout=5000)
    state = _duel_state(page, "wcResultApplied")
    assert state["wcResultApplied"] is True, \
        "strike WC with no conviction must auto-apply as before"
    assert not wc.locator('[data-action="spend-conviction-wc-strike"]').is_visible()


def test_manual_strike_wound_check_offers_conviction(page, live_server_url):
    """The manual 'Iaijutsu Strike Wound Check' button (outside the duel
    modal) also offers own conviction and suppresses everything else."""
    _create_duelist(page, live_server_url, "ManualStrikeWC",
                    foreign_knacks=("conviction",))
    _wait_alpine(page)
    _mock_dice_low(page)
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button', has_text="Add").click()
    page.wait_for_selector('[data-action="roll-wound-check-strike"]', state='visible', timeout=10000)
    page.locator('[data-action="roll-wound-check-strike"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=15000)
    wc = page.locator('[data-modal="wound-check"]')
    wc.locator('[data-action="spend-conviction-wc-strike"]').wait_for(state="visible", timeout=5000)
    assert not wc.locator('[data-action="spend-conviction-wc"]').is_visible()
    state = _duel_state(page, "wcResultApplied")
    assert state["wcResultApplied"] is False
