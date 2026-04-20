"""E2E: Attack modal - opens for attack types, probability table, damage roll."""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character

pytestmark = [pytest.mark.rolls]


def _create_attacker(page, live_server_url, name="Attacker", school="akodo_bushi"):
    """Create a character with attack rank 2 and bragging 1, apply, stay on sheet."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    click_plus(page, "attack", 1)  # 1 -> 2
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")


def _wait_alpine(page):
    """Wait for diceRoller Alpine component to initialize."""
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'idle') return true;
        }
        return false;
    }""", timeout=5000)


# ---------------------------------------------------------------------------
# Attack modal opens for attack types, not for others
# ---------------------------------------------------------------------------


def test_attack_opens_attack_modal(page, live_server_url):
    """Clicking attack opens the attack modal, not the dice roller."""
    _create_attacker(page, live_server_url, "AtkModal")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    assert page.locator('[data-modal="attack"] h3.text-accent').text_content().strip() != ""


def test_feint_does_not_open_attack_modal(page, live_server_url):
    """Feint uses the normal void dropdown, not the attack modal."""
    _create_attacker(page, live_server_url, "FeintTest")
    _wait_alpine(page)
    page.locator('[data-roll-key="knack:feint"]').click()
    page.wait_for_timeout(500)
    # Attack modal should NOT be open
    assert not page.locator('[data-modal="attack"]').is_visible()


def test_parry_does_not_open_attack_modal(page, live_server_url):
    """Parry is not an attack type and should not open attack modal."""
    _create_attacker(page, live_server_url, "ParryTest")
    _wait_alpine(page)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(500)
    assert not page.locator('[data-modal="attack"]').is_visible()


# ---------------------------------------------------------------------------
# Attack modal probability table
# ---------------------------------------------------------------------------


def test_attack_modal_shows_probability_table(page, live_server_url):
    """The attack modal shows a probability table with Hit % column."""
    _create_attacker(page, live_server_url, "AtkProb")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page.locator('[data-modal="attack"]')
    assert modal.locator('th:text("Hit %")').is_visible()
    assert modal.locator('td:text("None")').is_visible()


def test_attack_modal_shows_attack_roll_rk_column(page, live_server_url):
    """The attack probability table shows an 'Attack Roll' column with the (r)k(k) value per void level."""
    _create_attacker(page, live_server_url, "AtkRK")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page.locator('[data-modal="attack"]')
    assert modal.locator('th:text("Attack Roll")').is_visible()
    # The first row's Attack Roll cell should match attack_probs void_keys['0']
    import json
    probs = page.evaluate("""() => JSON.parse(document.getElementById('attack-probs').textContent)""")
    rk0 = probs['attack']['void_keys']['0'].replace(',', 'k')
    first_row_text = modal.locator('table tbody tr').first.text_content()
    assert rk0 in first_row_text


def test_attack_modal_tn_dropdown(page, live_server_url):
    """The TN dropdown shows common values."""
    _create_attacker(page, live_server_url, "AtkTN")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page.locator('[data-modal="attack"]')
    assert modal.locator('option[value="20"]').count() > 0


# ---------------------------------------------------------------------------
# Attack roll + damage
# ---------------------------------------------------------------------------


def test_attack_roll_shows_hit_or_miss(page, live_server_url):
    """Rolling an attack shows HIT or MISSED."""
    _create_attacker(page, live_server_url, "AtkRoll")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # Use a low TN to increase hit chance
    page.locator('[data-modal="attack"] select').first.select_option("5")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    # Wait for result
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    text = modal.text_content()
    assert "HIT" in text or "MISSED" in text


def test_attack_hit_shows_damage_roll_button(page, live_server_url):
    """When attack hits, a Make Damage Roll button appears."""
    _create_attacker(page, live_server_url, "AtkDmg")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # TN 5 should almost always hit
    page.locator('[data-modal="attack"] select').first.select_option("5")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    if "HIT" in modal.text_content():
        assert modal.locator('button:text("Make Damage Roll")').is_visible()


def test_attack_damage_roll_produces_result(page, live_server_url):
    """After a hit, clicking Make Damage Roll shows a damage total."""
    _create_attacker(page, live_server_url, "AtkDmgResult")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] select').first.select_option("5")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    if "HIT" in modal.text_content():
        modal.locator('button:text("Make Damage Roll")').click()
        page.wait_for_function("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.atkPhase === 'damage-result') return true;
            }
            return false;
        }""", timeout=10000)
        assert "damage" in modal.text_content().lower()


def test_attack_dice_animation_visible(page, live_server_url):
    """Attack roll shows dice animation in the attack tray."""
    _create_attacker(page, live_server_url, "AtkAnim")
    _wait_alpine(page)
    # Re-enable animations for this specific test
    page.evaluate("if (window._diceRoller) window._diceRoller.prefs.dice_animation_enabled = true")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation-atk svg.die').length > 0",
        timeout=15000,
    )
    assert page.locator('#dice-animation-atk svg.die').count() > 0


# ---------------------------------------------------------------------------
# Missing-action-dice warning
# ---------------------------------------------------------------------------


def test_attack_modal_warns_when_no_initiative(page, live_server_url):
    """Attack modal's pre-roll page shows the no-init warning when the
    character has no action dice at all (never rolled initiative)."""
    _create_attacker(page, live_server_url, "AtkNoInit")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    warning = page.locator('[data-testid="attack-init-warning-no-init"]')
    assert warning.is_visible()
    text = warning.text_content()
    assert "Attack" in text
    assert "rolled initiative" in text
    # The "rolled initiative" link is a real button.
    assert warning.locator('button[data-action="roll-initiative-from-warning"]').count() == 1
    # The other warning variant is not visible.
    assert not page.locator('[data-testid="attack-init-warning-out-of-dice"]').is_visible()


def test_attack_modal_warns_when_out_of_action_dice(page, live_server_url):
    """Attack modal shows the out-of-dice warning when every action die is
    already spent."""
    _create_attacker(page, live_server_url, "AtkOutDice")
    _wait_alpine(page)
    # Seed two action dice, both spent. setActionDice force-resets spent to
    # false, so write directly to the reactive array.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [
            {value: 3, spent: true},
            {value: 5, spent: true},
        ];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    warning = page.locator('[data-testid="attack-init-warning-out-of-dice"]')
    assert warning.is_visible()
    text = warning.text_content()
    assert "out of action dice" in text
    assert "Attack" in text
    # The no-init variant is not visible.
    assert not page.locator('[data-testid="attack-init-warning-no-init"]').is_visible()


def test_attack_modal_hides_warning_when_dice_available(page, live_server_url):
    """With at least one unspent action die, neither warning variant shows."""
    _create_attacker(page, live_server_url, "AtkDiceOK")
    _wait_alpine(page)
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [
            {value: 3, spent: false},
            {value: 5, spent: true},
        ];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    assert not page.locator('[data-testid="attack-init-warning-no-init"]').is_visible()
    assert not page.locator('[data-testid="attack-init-warning-out-of-dice"]').is_visible()


def test_attack_modal_warning_button_triggers_initiative(page, live_server_url):
    """Clicking the warning's rolled-initiative button closes the attack
    modal and opens/rolls initiative."""
    _create_attacker(page, live_server_url, "AtkWarnInit")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-testid="attack-init-warning-no-init"]'
                 ' button[data-action="roll-initiative-from-warning"]').click()
    # Attack modal closes.
    page.wait_for_selector('[data-modal="attack"]', state='hidden', timeout=3000)
    # Initiative roll fires - action dice eventually populate the bridge.
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || []).length > 0",
        timeout=10000,
    )


def test_attack_modal_warning_reflects_athletics_attack_name(page, live_server_url):
    """The <name of action> placeholder in the warning is the modal's own
    action label, not hardcoded 'Attack'. Use Togashi (the school that
    exposes Athletics Attack from the regular Attack menu) to verify."""
    _create_attacker(page, live_server_url, "AtkAthName", school="togashi_ise_zumi")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-attack-choice-menu]', state='visible', timeout=3000)
    page.locator('[data-attack-choice="athletics_attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    warning = page.locator('[data-testid="attack-init-warning-no-init"]')
    assert warning.is_visible()
    # Label strips the parenthetical ring, e.g. "Athletics Attack (Fire)" -> "Athletics Attack".
    assert "Athletics Attack" in warning.text_content()
