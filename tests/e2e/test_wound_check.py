"""E2E: Wound check modal - button visibility, pre-roll probabilities,
rolling animation, post-roll result application."""

import pytest
from tests.e2e.helpers import (
    apply_changes,
    click_plus,
    dismiss_wc_modal,
    select_school,
    start_new_character,
)

pytestmark = [pytest.mark.rolls, pytest.mark.tracking]


def _create_character_with_wounds(page, live_server_url, name="WCTest",
                                   school="akodo_bushi", light_wounds=10):
    """Create a character, apply, then add light wounds on the sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    # Add light wounds via the + button
    lw_section = page.locator('text="Light Wounds"').locator('..')
    plus_btn = lw_section.locator('[data-action="lw-plus"]')
    plus_btn.click()
    page.wait_for_selector('input[placeholder]', timeout=3000)
    # Use the "set to total" input in the plus modal
    page.locator('input[placeholder="New total"]').fill(str(light_wounds))
    page.locator('button:text("Set")').last.click()
    page.wait_for_timeout(500)
    dismiss_wc_modal(page)
    return page.url


# ---------------------------------------------------------------------------
# Button visibility
# ---------------------------------------------------------------------------


def test_wound_check_button_visible_with_light_wounds(page, live_server_url):
    """Roll Wound Check button appears when light wounds > 0."""
    _create_character_with_wounds(page, live_server_url, "WCBtnVisible", light_wounds=5)
    btn = page.locator('[data-action="roll-wound-check"]')
    assert btn.is_visible()


def test_wound_check_button_hidden_with_zero_wounds(page, live_server_url):
    """Roll Wound Check button is hidden when light wounds = 0."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "WCBtnHidden")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    btn = page.locator('[data-action="roll-wound-check"]')
    assert not btn.is_visible()


# ---------------------------------------------------------------------------
# Pre-roll modal
# ---------------------------------------------------------------------------


def test_wound_check_modal_opens(page, live_server_url):
    """Clicking Roll Wound Check opens the pre-roll modal with probability table."""
    _create_character_with_wounds(page, live_server_url, "WCModalOpen", light_wounds=15)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    # Modal should be visible with the probability table
    modal = page.locator('[data-modal="wound-check"]')
    modal.locator('h3:text("Wound Check")').wait_for(state="visible", timeout=5000)
    assert modal.locator('h3:text("Wound Check")').is_visible()
    # Table should have at least the "None" (0 void) row
    assert modal.locator('td:text("None")').is_visible()


def test_wound_check_modal_shows_tn(page, live_server_url):
    """The modal shows the current light wound total as the TN."""
    _create_character_with_wounds(page, live_server_url, "WCTN", light_wounds=20)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    body = page.text_content('h3:text("Wound Check")').strip()
    # The TN value should appear in the modal
    modal = page.locator('h3:text("Wound Check")').locator('../..')
    modal_text = modal.text_content()
    assert "20" in modal_text  # TN = light wounds


# ---------------------------------------------------------------------------
# Dice animation during rolling
# ---------------------------------------------------------------------------


def test_wound_check_shows_dice_animation(page, live_server_url):
    """The wound check rolling phase displays dice in the animation tray."""
    _create_character_with_wounds(page, live_server_url, "WCAnim", light_wounds=10)
    # Re-enable animations for this specific test
    page.evaluate("if (window._diceRoller) window._diceRoller.prefs.dice_animation_enabled = true")
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    # Click Roll Wound Check in the modal
    page.locator('[data-action="roll-wound-check-go"]').click()
    # Wait for dice to appear in the wound check animation tray
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation-wc svg.die').length > 0",
        timeout=15000,
    )
    assert page.locator('#dice-animation-wc svg.die').count() > 0


def test_regular_roll_shows_dice_animation(page, live_server_url):
    """The regular dice roller also shows dice animation in its tray."""
    _create_character_with_wounds(page, live_server_url, "RegAnim", light_wounds=5)
    # Re-enable animations for this specific test
    page.evaluate("if (window._diceRoller) window._diceRoller.prefs.dice_animation_enabled = true")
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    # Dismiss roll menu if it appears
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl').first
    if menu.count() > 0 and menu.is_visible():
        menu.locator('button.font-medium').first.click()
    # Wait for dice to appear in the regular animation tray
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation svg.die').length > 0",
        timeout=15000,
    )
    assert page.locator('#dice-animation svg.die').count() > 0


# ---------------------------------------------------------------------------
# Post-roll result
# ---------------------------------------------------------------------------


def test_wound_check_result_shows_pass_or_fail(page, live_server_url):
    """After rolling, the modal shows either PASSED or FAILED."""
    _create_character_with_wounds(page, live_server_url, "WCResult", light_wounds=5)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check-go"]').click()
    # Wait for result phase
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    body = page.text_content("body")
    assert "PASSED" in body or "FAILED" in body


def test_wound_check_pass_shows_keep_and_take_buttons(page, live_server_url):
    """When wound check passes, both Keep and Take buttons appear."""
    # Use very low light wounds (1) so pass is almost guaranteed
    _create_character_with_wounds(page, live_server_url, "WCPass", light_wounds=1)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    # With LW=1, pass is virtually guaranteed on any Water+1 roll
    modal = page.locator('[data-modal="wound-check"]')
    if "PASSED" in modal.text_content():
        assert modal.locator('button:text("Keep Light Wounds")').is_visible()
        assert modal.locator('button:text("Take 1 Serious Wound")').is_visible()


def test_wound_check_take_serious_resets_light(page, live_server_url):
    """Choosing 'Take 1 Serious Wound' after a pass resets light wounds to 0."""
    _create_character_with_wounds(page, live_server_url, "WCTake", light_wounds=1)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    modal = page.locator('[data-modal="wound-check"]')
    if "PASSED" in modal.text_content():
        modal.locator('button:text("Take 1 Serious Wound")').click()
        page.wait_for_timeout(500)
        # Light wounds should be 0, serious should be 1
        lw = page.evaluate("window._trackingBridge?.lightWounds")
        sw = page.evaluate("window._trackingBridge?.seriousWounds")
        assert lw == 0
        assert sw == 1


# ---------------------------------------------------------------------------
# Iaijutsu strike wound check
# ---------------------------------------------------------------------------


def test_iaijutsu_strike_wound_check_available(page, live_server_url):
    """The Iaijutsu Strike Wound Check button is present in the modal."""
    _create_character_with_wounds(page, live_server_url, "WCStrike", light_wounds=10)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check-strike"]').wait_for(state="visible", timeout=5000)
    assert page.locator('[data-action="roll-wound-check-strike"]').is_visible()


def test_wound_check_result_has_copy_as_image_button(page, live_server_url):
    """The wound-check result panel now carries a Copy-as-image button
    alongside the Total line. Verifies the partial fires and reaches
    the ``ready`` state once the prerender lands."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    _create_character_with_wounds(page, live_server_url, "WCCopy",
                                  light_wounds=10)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.wcPhase === 'result'",
        timeout=10000,
    )
    page.wait_for_function(
        """() => {
            const modal = document.querySelector('[data-modal="wound-check"]');
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
        timeout=10000,
    )


def test_wc_image_payload_uses_wc_formula_not_prior_roll(page, live_server_url):
    """The Copy-as-image payload's formula subtitle must reflect the
    wound check's own ``rolled``k``kept`` shape, not whatever the
    previous skill roll happened to leave in ``this.formulaText``.

    Regression: ``_buildWoundCheckImagePayload`` used to read
    ``this.formulaText``, which only the regular-skill-roll path
    stamped. After a 6k3 Bragging roll the WC card would display
    "6k3 + 5" even though the actual wound check rolled 4k3, making
    the rendered card show the wrong number of dice in its subtitle.
    """
    sheet_url = _create_character_with_wounds(
        page, live_server_url, "WCFormulaText", light_wounds=10,
    )
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(150)

    # First roll: a regular skill that bakes a "6k3 + something"
    # formulaText into the shared state.
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.phase === 'done'",
        timeout=10000,
    )
    skill_formula_text = page.evaluate("() => window._diceRoller.formulaText")
    assert skill_formula_text, "skill roll should have stamped formulaText"
    # Close the skill roll modal.
    page.locator('[data-modal="dice-roller"] button:has-text("Close")').first.click()
    page.wait_for_timeout(200)

    # Capture the next /roll-image POST so we can inspect what the WC
    # builder sent. Install the hook BEFORE triggering the WC roll.
    page.evaluate("""() => {
        window.__lastRollImagePayload = null;
        const origFetch = window.fetch;
        window.fetch = function(url, opts) {
            if (typeof url === 'string'
                    && url.indexOf('/roll-image') !== -1
                    && opts && opts.body) {
                try { window.__lastRollImagePayload = JSON.parse(opts.body); }
                catch (e) { /* ignore */ }
            }
            return origFetch.apply(this, arguments);
        };
    }""")

    # Now roll a wound check via its data-action selector.
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.wcPhase === 'result'",
        timeout=10000,
    )
    page.wait_for_function(
        "() => window.__lastRollImagePayload !== null",
        timeout=3000,
    )
    payload = page.evaluate("() => window.__lastRollImagePayload")
    assert payload["title"] == "Wound Check", (
        f"Expected the WC payload, got: {payload!r}"
    )
    # The subtitle must match the WC's *own* ``{rolled}k{kept}[+flat]``,
    # not whatever the prior skill roll left in ``this.formulaText``.
    wc_formula = page.evaluate("""() => {
        const f = window._diceRoller.formula || {};
        return { rolled: f.rolled, kept: f.kept, flat: f.flat || 0 };
    }""")
    expected_subtitle = f"{wc_formula['rolled']}k{wc_formula['kept']}"
    if wc_formula["flat"] > 0:
        expected_subtitle += f" + {wc_formula['flat']}"
    assert payload["formula"] == expected_subtitle, (
        f"WC card subtitle should be {expected_subtitle!r}, got: "
        f"{payload['formula']!r}. (Prior skill roll formulaText was: "
        f"{skill_formula_text!r})"
    )
    # And specifically must NOT carry the prior roll's formula.
    assert payload["formula"] != skill_formula_text
