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


def test_double_attack_miss_shows_elevated_tn(page, live_server_url):
    """A missed double attack must report the effective TN (base + 20), not
    the base TN, so the 'needed X, rolled Y' banner lines up with the
    hit/miss calculation (which uses the elevated TN)."""
    _create_attacker(page, live_server_url, "DblAtkMiss")
    _wait_alpine(page)
    # Force dice to roll low so the attack misses even at a modest TN.
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.0")
    page.locator('[data-roll-key="knack:double_attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').first.select_option("20")
    modal.locator('[data-action="roll-attack"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    page.evaluate("Math.random = window._origRandom")
    miss_text = modal.locator('div:has-text("MISSED")').first.text_content()
    # Effective TN for a double attack at base TN 20 is 40.
    assert "needed 40" in miss_text, \
        f"Expected elevated double-attack TN (40) in miss banner, got: {miss_text!r}"
    assert "needed 20" not in miss_text, \
        f"Miss banner should NOT show the base TN (20) for a double attack: {miss_text!r}"


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


def test_damage_parts_include_10k10_overflow_bullet(page, live_server_url):
    """Regression: when a damage roll overflows 10k10 (kept > 10 after the
    rolled-cap cascade), each extra kept die converts to +2 flat. That +2N
    used to silently inflate the damage total with no line in the breakdown
    to explain it, so the bullets didn't sum to the displayed total. The
    overflow must now appear in ``atkDamageParts`` so the damage result
    modal renders a '+N bonus for rolling K die(s) past 10k10' bullet.
    Plural-dice path: two kept dice past 10k10 → +4 flat."""
    _create_attacker(page, live_server_url, "DmgOverflow")
    _wait_alpine(page)
    # Exercise atkComputeDamage directly. Going through the UI to hit
    # exactly this overflow state is brittle; this call enters the same
    # code path the UI would. 5k8 base weapon + Fire 5 + 4 bonus kept dice
    # = 5k12 before caps → 10k10 + (2 × 2 kept past cap) = +4 flat.
    parts = page.evaluate("""() => {
        const d = window._diceRoller;
        d.atkFormula = {
            damage_ring_val: 5, damage_ring_name: 'Fire',
            damage_extra_rolled: 0, damage_extra_kept: 4,
            damage_flat_bonus: 0,
        };
        d.atkWeaponRolled = 0;
        d.atkWeaponKept = 8;
        d.schoolAbilities = d.schoolAbilities || {};
        const r = d.atkComputeDamage(0, false, false, 0, false);
        return { parts: r.parts, flat: r.flat, rolled: r.rolled, kept: r.kept };
    }""")
    assert parts["rolled"] == 5 and parts["kept"] == 10, \
        f"Damage roll should cap kept at 10, got {parts['rolled']}k{parts['kept']}"
    overflow_parts = [p for p in parts["parts"] if "past 10k10" in p]
    assert len(overflow_parts) == 1, \
        f"Expected exactly one overflow bullet in parts, got: {parts['parts']}"
    assert "+4" in overflow_parts[0] and "2 dice past 10k10" in overflow_parts[0], \
        f"Overflow bullet wording off: {overflow_parts[0]!r}"


def test_damage_parts_overflow_singular_for_one_die(page, live_server_url):
    """The overflow bullet pluralizes correctly when only one extra die
    lands past 10k10 (the specific case the user hit - a '+2 bonus for
    rolling 1 die past 10k10' missing from the breakdown)."""
    _create_attacker(page, live_server_url, "DmgOverflowOne")
    _wait_alpine(page)
    # 0k8 weapon + Fire 5 + 3 extra kept = 5k11 before caps → 5k10 + 2 flat.
    parts = page.evaluate("""() => {
        const d = window._diceRoller;
        d.atkFormula = {
            damage_ring_val: 5, damage_ring_name: 'Fire',
            damage_extra_rolled: 0, damage_extra_kept: 3,
            damage_flat_bonus: 0,
        };
        d.atkWeaponRolled = 0;
        d.atkWeaponKept = 8;
        d.schoolAbilities = d.schoolAbilities || {};
        const r = d.atkComputeDamage(0, false, false, 0, false);
        return { parts: r.parts };
    }""")
    overflow_parts = [p for p in parts["parts"] if "past 10k10" in p]
    assert len(overflow_parts) == 1, f"Expected one overflow bullet: {parts['parts']}"
    assert "+2" in overflow_parts[0] and "1 die past 10k10" in overflow_parts[0], \
        f"Singular 'die' expected for a +2 overflow, got: {overflow_parts[0]!r}"


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
