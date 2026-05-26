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
    modal.locator('th:text("Hit %")').wait_for(state="visible", timeout=5000)
    assert modal.locator('th:text("Hit %")').is_visible()
    modal.locator('td:text("None")').wait_for(state="visible", timeout=5000)
    assert modal.locator('td:text("None")').is_visible()


def test_attack_modal_shows_attack_roll_rk_column(page, live_server_url):
    """The attack probability table shows an 'Attack Roll' column with the (r)k(k) value per void level."""
    _create_attacker(page, live_server_url, "AtkRK")
    _wait_alpine(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('th:text("Attack Roll")').wait_for(state="visible", timeout=5000)
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
    warning.wait_for(state="visible", timeout=5000)
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
    warning.wait_for(state="visible", timeout=5000)
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
    warning.wait_for(state="visible", timeout=5000)
    assert warning.is_visible()
    # Label strips the parenthetical ring, e.g. "Athletics Attack (Fire)" -> "Athletics Attack".
    assert "Athletics Attack" in warning.text_content()


# ---------------------------------------------------------------------------
# Pre-roll "Extra bonus" - GM-grant situational bonus
# ---------------------------------------------------------------------------


def _open_attack_modal(page):
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)


def test_extra_bonus_starts_unchecked_with_defaults(page, live_server_url):
    """Pre-roll extra-bonus toggle starts unchecked on every modal open.
    When checked, the number defaults to +15 and the label defaults
    to 'surrounding' (per the spec). The number / label inputs are
    hidden until the box is checked."""
    _create_attacker(page, live_server_url, "ExtraDefault")
    _wait_alpine(page)
    _open_attack_modal(page)
    toggle = page.locator('[data-testid="atk-extra-bonus-toggle"]')
    amount = page.locator('[data-testid="atk-extra-bonus-amount"]')
    label = page.locator('[data-testid="atk-extra-bonus-label"]')
    assert toggle.is_checked() is False
    assert amount.is_visible() is False
    toggle.check()
    page.wait_for_timeout(100)
    assert amount.is_visible() is True
    assert label.is_visible() is True
    assert amount.input_value() == "15"
    assert label.input_value() == "surrounding"


def test_extra_bonus_does_not_persist_between_modal_opens(page, live_server_url):
    """Checking the box on one attack must not carry over to the next.
    Spec: "This should not be checked by default, even if it was
    checked on the previous attack roll." """
    _create_attacker(page, live_server_url, "ExtraReset")
    _wait_alpine(page)
    _open_attack_modal(page)
    page.locator('[data-testid="atk-extra-bonus-toggle"]').check()
    # Close the modal by clicking the X.
    page.locator('[data-modal="attack"] button.text-ink\\/60').click()
    page.wait_for_timeout(150)
    _open_attack_modal(page)
    toggle = page.locator('[data-testid="atk-extra-bonus-toggle"]')
    assert toggle.is_checked() is False


def test_extra_bonus_lifts_hit_chance_in_probability_table(page, live_server_url):
    """The hit-chance column updates live as the bonus is toggled and
    as the amount field changes - the underlying ``atkHitChance``
    helper includes ``_atkExtraBonusFlat`` in its target offset."""
    _create_attacker(page, live_server_url, "ExtraHit")
    _wait_alpine(page)
    _open_attack_modal(page)
    # Force a TN where the base hit chance is well below 100% so the
    # bonus has room to move the needle.
    page.evaluate("window._diceRoller.atkTN = 30")
    page.wait_for_timeout(100)
    before = page.evaluate(
        "() => Math.round(window._diceRoller.atkHitChance(0) * 100)"
    )
    page.locator('[data-testid="atk-extra-bonus-toggle"]').check()
    page.wait_for_timeout(100)
    with_default = page.evaluate(
        "() => Math.round(window._diceRoller.atkHitChance(0) * 100)"
    )
    assert with_default > before, "Expected hit chance to rise with +15 bonus"
    # Editing the number to a much larger value should push it higher
    # again (or cap at 100%, which is also fine).
    page.locator('[data-testid="atk-extra-bonus-amount"]').fill("50")
    page.wait_for_timeout(100)
    with_larger = page.evaluate(
        "() => Math.round(window._diceRoller.atkHitChance(0) * 100)"
    )
    assert with_larger >= with_default


def test_extra_bonus_surfaces_on_breakdown_after_roll(page, live_server_url):
    """After committing the attack roll, the extra bonus appears in
    the post-roll breakdown carrying its label verbatim."""
    _create_attacker(page, live_server_url, "ExtraBreakdown")
    _wait_alpine(page)
    _open_attack_modal(page)
    page.locator('[data-testid="atk-extra-bonus-toggle"]').check()
    page.locator('[data-testid="atk-extra-bonus-amount"]').fill("7")
    page.locator('[data-testid="atk-extra-bonus-label"]').fill("high ground")
    # Commit the roll.
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.atkPhase === 'result'",
        timeout=5000,
    )
    breakdown = page.locator('[data-modal="attack"]').text_content() or ""
    assert "+7 from high ground" in breakdown


def test_extra_bonus_blank_label_falls_back_gracefully(page, live_server_url):
    """A user can clear the label - the breakdown then falls back to
    ``extra bonus`` rather than rendering ``+N from ``."""
    _create_attacker(page, live_server_url, "ExtraBlank")
    _wait_alpine(page)
    _open_attack_modal(page)
    page.locator('[data-testid="atk-extra-bonus-toggle"]').check()
    page.locator('[data-testid="atk-extra-bonus-label"]').fill("")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.atkPhase === 'result'",
        timeout=5000,
    )
    breakdown = page.locator('[data-modal="attack"]').text_content() or ""
    assert "+15 from extra bonus" in breakdown


# ---------------------------------------------------------------------------
# Post-roll "Extra bonus" - adjusts attack total + damage extra dice
# ---------------------------------------------------------------------------


def _roll_attack_and_wait(page):
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.atkPhase === 'result'",
        timeout=5000,
    )


def test_post_roll_bonus_starts_unchecked_with_default_5(page, live_server_url):
    """The post-roll extra-bonus checkbox starts unchecked. When the
    box is checked, the number field comes up at +5 (the spec'd
    default for this field; the pre-roll field defaults to +15). No
    breakdown row renders until the box is on."""
    _create_attacker(page, live_server_url, "PostRollDefault")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    toggle = page.locator('[data-testid="atk-post-roll-bonus-toggle"]')
    amount = page.locator('[data-testid="atk-post-roll-bonus-amount"]')
    assert toggle.is_checked() is False
    # Breakdown row only renders when applied != 0; not yet.
    assert page.locator(
        '[data-testid="atk-post-roll-bonus-breakdown"]'
    ).is_visible() is False
    # Checking the box reveals the field pre-populated with the
    # default amount.
    toggle.check()
    page.wait_for_timeout(150)
    assert amount.input_value() == "5"


def test_post_roll_bonus_focuses_input_when_toggled(page, live_server_url):
    """Checking the post-roll extra-bonus auto-focuses the number
    field so the player can start typing immediately."""
    _create_attacker(page, live_server_url, "PostRollFocus")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').check()
    page.wait_for_timeout(150)
    focused_id = page.evaluate("() => document.activeElement?.dataset?.testid")
    assert focused_id == "atk-post-roll-bonus-amount"


def test_post_roll_bonus_updates_attack_total_live(page, live_server_url):
    """Editing the post-roll number field updates atkRollTotal and
    baseTotal by the typed amount."""
    _create_attacker(page, live_server_url, "PostRollLive")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    before = page.evaluate("() => window._diceRoller.atkRollTotal")
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').check()
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').fill("8")
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').dispatch_event("input")
    page.wait_for_function(
        "(prev) => window._diceRoller.atkRollTotal === prev + 8",
        arg=before,
        timeout=2000,
    )
    # Editing to a different value diffs correctly (no double-counting).
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').fill("3")
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').dispatch_event("input")
    page.wait_for_function(
        "(prev) => window._diceRoller.atkRollTotal === prev + 3",
        arg=before,
        timeout=2000,
    )


def test_post_roll_bonus_toggle_off_subtracts_back(page, live_server_url):
    """Unchecking the post-roll extra bonus returns atkRollTotal to
    its pre-toggle value (no residual delta)."""
    _create_attacker(page, live_server_url, "PostRollUndo")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    before = page.evaluate("() => window._diceRoller.atkRollTotal")
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').check()
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').fill("10")
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').dispatch_event("input")
    page.wait_for_timeout(100)
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').uncheck()
    page.wait_for_function(
        "(prev) => window._diceRoller.atkRollTotal === prev",
        arg=before,
        timeout=2000,
    )


def test_post_roll_bonus_can_flip_miss_into_hit(page, live_server_url):
    """A large enough post-roll bonus can push a missed attack across
    the TN. The HIT/MISS branch is reactive so the result panel
    re-renders when atkHit flips true."""
    _create_attacker(page, live_server_url, "PostRollFlip")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    # Manufacture a miss scenario by setting TN above the rolled total.
    page.evaluate("""() => {
        const r = window._diceRoller;
        r.atkTN = r.atkRollTotal + 5;
        r._atkUpdateHitState();
    }""")
    assert page.evaluate("() => window._diceRoller.atkHit") is False
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').check()
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').fill("5")
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').dispatch_event("input")
    page.wait_for_function(
        "() => window._diceRoller.atkHit === true",
        timeout=2000,
    )


def test_post_roll_bonus_updates_extra_damage_dice(page, live_server_url):
    """Each 5 of post-roll bonus above the TN grants another rolled
    damage die. Pinning a hit scenario and bumping the bonus by 5
    increments ``atkExtraDice`` by 1."""
    _create_attacker(page, live_server_url, "PostRollDmgDice")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    # Force a clean hit-by-exactly-TN starting point so each +5 of
    # post-roll bonus translates to exactly +1 extra damage die.
    page.evaluate("""() => {
        const r = window._diceRoller;
        r.atkTN = r.atkRollTotal;
        r._atkUpdateHitState();
    }""")
    base_dice = page.evaluate("() => window._diceRoller.atkExtraDice")
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').check()
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').fill("5")
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').dispatch_event("input")
    page.wait_for_function(
        "(base) => window._diceRoller.atkExtraDice === base + 1",
        arg=base_dice,
        timeout=2000,
    )


def test_post_roll_bonus_breakdown_row_shows_when_active(page, live_server_url):
    """The "+N extra bonus" line appears in the breakdown panel only
    when the bonus is non-zero and the box is checked."""
    _create_attacker(page, live_server_url, "PostRollBreakdown")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    row = page.locator('[data-testid="atk-post-roll-bonus-breakdown"]')
    assert row.is_visible() is False
    page.locator('[data-testid="atk-post-roll-bonus-toggle"]').check()
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').fill("4")
    page.locator('[data-testid="atk-post-roll-bonus-amount"]').dispatch_event("input")
    page.wait_for_timeout(100)
    assert row.is_visible() is True
    assert "+4 extra bonus" in row.text_content()


# ---------------------------------------------------------------------------
# Copy-as-image surfaces on the attack roll result + damage result panels
# ---------------------------------------------------------------------------


def _wait_atk_copy_ready(page, timeout=10000):
    page.wait_for_function(
        """() => {
            const modal = document.querySelector('[data-modal="attack"]');
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


def test_attack_result_has_copy_as_image_button(page, live_server_url):
    """The attack-roll result panel exposes the Copy-as-image button
    once the roll lands."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    _create_attacker(page, live_server_url, "AtkCopy")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    _wait_atk_copy_ready(page)


def test_attack_damage_result_has_copy_as_image_button(page, live_server_url):
    """After rolling damage, the damage-result panel exposes its own
    Copy-as-image button (a fresh render reflecting damage dice +
    damage total, not the attack snapshot)."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    _create_attacker(page, live_server_url, "AtkDmgCopy")
    _wait_alpine(page)
    _open_attack_modal(page)
    _roll_attack_and_wait(page)
    # Force a guaranteed hit so the damage roll button appears.
    page.evaluate("""() => {
        const r = window._diceRoller;
        r.atkTN = 0;
        r._atkUpdateHitState();
    }""")
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.atkHit === true",
        timeout=2000,
    )
    page.locator('[data-modal="attack"] button:has-text("Make Damage Roll")').click()
    page.wait_for_function(
        "() => window._diceRoller && window._diceRoller.atkPhase === 'damage-result'",
        timeout=5000,
    )
    _wait_atk_copy_ready(page)
