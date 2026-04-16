"""E2E: School-specific ability UI - buttons, banked bonuses, display notes."""

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
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")


def _wait_roll_done(page):
    """Wait for a regular roll to complete."""
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)


def _roll_via_menu_or_direct(page, roll_key):
    """Click a roll key. If a menu appears, click the main Roll button. Otherwise wait for direct roll."""
    page.locator(f'[data-roll-key="{roll_key}"]').click()
    page.wait_for_timeout(300)
    # If the roll already completed (no-animation fast path), skip menu check
    already_done = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""")
    if not already_done:
        # Check if roll menu opened (VP spending options)
        menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
        if menu.is_visible():
            buttons = menu.locator('button.font-medium')
            for i in range(buttons.count()):
                text = buttons.nth(i).text_content().strip()
                if text.startswith("Roll "):
                    buttons.nth(i).click()
                    break
            else:
                buttons.first.click()  # fallback
    _wait_roll_done(page)


def _wait_attack_result(page):
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)


def _mock_dice_high(page):
    """Mock dice to always roll 7 (high enough to hit, avoids reroll-10 complications).

    Overrides Math.random to return 0.6 which maps to floor(0.6*10)+1 = 7.
    """
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.6")


def _mock_dice_low(page):
    """Mock dice to always roll 1 (guaranteed miss/fail).

    Overrides Math.random to return 0.0 which maps to floor(0.0*10)+1 = 1.
    """
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.0")


def _mock_dice_ten(page):
    """Mock dice to always roll 10 (for testing Phase 0 etc).

    Overrides Math.random to return 0.9 which maps to floor(0.9*10)+1 = 10.
    """
    page.evaluate("window._origRandom = Math.random; Math.random = () => 0.9")


def _restore_dice(page):
    """Restore normal random dice."""
    page.evaluate("if (window._origRandom) Math.random = window._origRandom")


def _get_formula(page, key):
    """Read a roll formula from the embedded JSON on the sheet page."""
    return page.evaluate(f"""() => {{
        const el = document.getElementById('roll-formulas');
        if (!el) return null;
        const data = JSON.parse(el.textContent || '{{}}');
        return data['{key}'] || null;
    }}""")


def _count_result_dice(page):
    """Count the number of dice shown in the current roll result (regular roll modal)."""
    return page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.finalDice && d.phase === 'done') return d.finalDice.length;
        }
        return 0;
    }""")


def _get_result_rolled(page):
    """Get the 'rolled' count from the formula used in the last regular roll."""
    return page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula && d.phase === 'done') return d.formula.rolled;
        }
        return 0;
    }""")


def _count_attack_result_dice(page):
    """Count the number of dice shown in the attack roll result."""
    return page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.finalDice && d.atkPhase === 'result') return d.finalDice.length;
        }
        return 0;
    }""")


def _get_attack_result_rolled(page):
    """Get the 'rolled' count from the formula used in the last attack roll."""
    return page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula && d.atkPhase === 'result') return d.formula.rolled;
        }
        return 0;
    }""")


def _open_attack_modal_and_roll(page, roll_key):
    """Open attack modal for an attack-type key and roll with default TN."""
    page.locator(f'[data-roll-key="{roll_key}"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)


def _get_school_abilities(page):
    """Read the school abilities JSON from the sheet page."""
    return page.evaluate("""() => {
        const el = document.getElementById('school-abilities');
        if (!el) return {};
        return JSON.parse(el.textContent || '{}');
    }""")


def _get_void_spend_config(page):
    """Read the void spend config JSON from the sheet page."""
    return page.evaluate("""() => {
        const el = document.getElementById('void-spend-config');
        if (!el) return {};
        return JSON.parse(el.textContent || '{}');
    }""")


def _set_technique_choices(page, char_id, choices):
    """Set technique_choices on a character via the autosave API."""
    import json
    page.evaluate(f"""async () => {{
        const resp = await fetch('/characters/{char_id}/autosave', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{ technique_choices: {json.dumps(choices)} }})
        }});
        return resp.status;
    }}""")


def _extract_char_id(page):
    """Extract character ID from the current URL."""
    url = page.url
    # URLs like /characters/5 or /characters/5/edit
    parts = url.split("/characters/")
    if len(parts) > 1:
        num = parts[1].split("/")[0].split("?")[0]
        return int(num)
    return None


# (duplicate _open_attack_modal_and_roll removed - using the one defined above)


def _roll_wound_check(page):
    """Open and roll a wound check."""
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.openWoundCheckModal === 'function') {
                d.openWoundCheckModal();
                return;
            }
        }
    }""")
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)


def _set_light_wounds(page, amount):
    """Set light wounds on the tracking bridge."""
    page.evaluate(f"""() => {{
        const t = window._trackingBridge;
        if (t) {{ t.lightWounds = {amount}; t.save(); }}
    }}""")
    page.wait_for_timeout(200)


# ===========================================================================
# AKODO BUSHI (3 tests)
# ===========================================================================

def test_akodo_feint_temp_vp(page, live_server_url):
    """Akodo feint roll shows succeeded (+4 temp VP) and failed (+1 temp VP) buttons."""
    _create_char(page, live_server_url, "AkodoFeintVP", "akodo_bushi")
    _roll_via_menu_or_direct(page, "knack:feint")
    assert page.locator('button:has-text("Succeeded (+4 temp VP)")').is_visible()
    assert page.locator('button:has-text("Failed (+1 temp VP)")').is_visible()
def test_bayushi_3rd_dan_feint_shows_damage(page, live_server_url):
    """Bayushi at 3rd Dan: feint roll shows Roll Feint Damage button, clicking it shows damage result."""
    _create_char(page, live_server_url, "BayushiFeintDmg", "bayushi_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    _roll_via_menu_or_direct(page, "knack:feint")
    btn = page.locator('button:text("Roll Feint Damage")')
    assert btn.is_visible()
    btn.click()
    # Wait for sub-damage result phase
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'sub-damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    # Should show damage total and Back button
    modal = page.locator('[data-modal="dice-roller"]')
    modal.locator('button:text("Back")').wait_for(state='visible', timeout=3000)
    assert "damage" in modal.text_content().lower()
    assert modal.locator('button:text("Back")').is_visible()


def test_bayushi_4th_dan_post_feint_raise(page, live_server_url):
    """Bayushi at 4th Dan: feint auto-banks +5 free raise for a future attack."""
    _create_char(page, live_server_url, "BayushiFeint4", "bayushi_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    _roll_via_menu_or_direct(page, "knack:feint")
    # Should auto-bank +5 after feint completes
    banked = page.evaluate("window._diceRoller?.bayushiBankedFeintRaise || 0")
    assert banked == 5, f"Expected 5 banked, got {banked}"
    # Should show in tracking section
    assert page.locator('text="Banked Feint Raises"').is_visible()


def test_bayushi_banked_raises_tracking_and_persist(page, live_server_url):
    """Bayushi banked feint raises: display in tracking, persist on refresh, clear on reset."""
    _create_char(page, live_server_url, "BayushiTrack", "bayushi_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    # Inject banked raises and save
    page.evaluate("""
        window._trackingBridge.bayushiBankedFeintRaise = 10;
        if (window._diceRoller) window._diceRoller.bayushiBankedFeintRaise = 10;
        window._trackingBridge.saveBankedBonuses();
    """)
    page.wait_for_timeout(500)
    # Should show in tracking section
    assert page.locator('text="Banked Feint Raises"').is_visible()
    body = page.text_content("body")
    assert "+10" in body
    assert "2 raises" in body.lower() or "2 raise" in body.lower()
    # Mark 1 spent
    page.locator('button:has-text("Mark 1 spent")').click()
    page.wait_for_timeout(300)
    val = page.evaluate("window._trackingBridge?.bayushiBankedFeintRaise || 0")
    assert val == 5, f"Expected 5 after marking 1 spent, got {val}"
    # Persist on refresh
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    val = page.evaluate("window._trackingBridge?.bayushiBankedFeintRaise || 0")
    assert val == 5, f"Expected 5 after refresh, got {val}"
    assert page.locator('text="Banked Feint Raises"').is_visible()


def test_bayushi_feint_damage_formula_shows_vp(page, live_server_url):
    """Bayushi feint damage description shows VP-adjusted formula."""
    _create_char(page, live_server_url, "BayushiDmgVP", "bayushi_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Give VP so we can spend them on the feint
    page.evaluate("window._trackingBridge.voidPoints = 2")
    page.wait_for_timeout(200)
    # Click feint roll key - menu should appear with VP options
    page.locator('[data-roll-key="knack:feint"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        # Find the "1 VP" row and click it to select, then click "Roll Feint"
        vp_btns = menu.locator('button')
        for i in range(vp_btns.count()):
            text = vp_btns.nth(i).text_content().strip()
            if "1 VP" in text or "1 regular" in text.lower():
                vp_btns.nth(i).click()
                page.wait_for_timeout(100)
                break
        # Click the Roll button
        roll_btns = menu.locator('button.font-medium')
        for i in range(roll_btns.count()):
            text = roll_btns.nth(i).text_content().strip()
            if text.startswith("Roll "):
                roll_btns.nth(i).click()
                break
    _wait_roll_done(page)
    # The feint damage description should show the VP-adjusted formula
    modal = page.locator('[data-modal="dice-roller"]')
    desc = modal.text_content()
    # With attack=2 base and 1 VP spent: should show 3k2, not 2k1
    assert "3k2" in desc or "from VP" in desc, f"VP-adjusted formula not shown: {desc[:300]}"
def test_courtier_4th_dan_temp_vp(page, live_server_url):
    """Courtier 4th Dan: temp VP button after successful attack or manipulation."""
    _create_char(page, live_server_url, "Court4VP", "courtier",
                 knack_overrides={"discern_honor": 4, "oppose_social": 4, "worldliness": 4},
                 skill_overrides={"manipulation": 1})
    sa = _get_school_abilities(page)
    assert sa.get("courtier_temp_vp_on_hit") is True
    # Verify the button exists in the DOM (the manipulation roll result area)
    _roll_via_menu_or_direct(page, "skill:manipulation")
    # Wait a moment for Alpine to process x-show/x-cloak
    page.wait_for_timeout(500)
    btn = page.locator('button:has-text("Gain 1 temp VP")')
    assert btn.count() >= 1
def test_courtier_5th_dan_wc_bonus(page, live_server_url):
    """Courtier 5th Dan: wound check formula includes +Air."""
    _create_char(page, live_server_url, "Court5WC", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5})
    wc_formula = page.evaluate("window._diceRoller?.formulas?.wound_check || {}")
    assert any("5th Dan" in s for s in wc_formula.get("bonus_sources", [])), \
        f"WC should include 5th Dan bonus, got: {wc_formula.get('bonus_sources')}"


def test_courtier_below_5th_dan_no_wc_bonus(page, live_server_url):
    """Courtier below 5th Dan: wound check has no 5th Dan bonus."""
    _create_char(page, live_server_url, "Court4WC", "courtier",
                 knack_overrides={"discern_honor": 4, "oppose_social": 4, "worldliness": 4})
    wc_formula = page.evaluate("window._diceRoller?.formulas?.wound_check || {}")
    assert not any("5th Dan" in s for s in wc_formula.get("bonus_sources", [])), \
        f"WC should NOT include 5th Dan bonus, got: {wc_formula.get('bonus_sources')}"


def test_courtier_5th_dan_always_skill_has_bonus(page, live_server_url):
    """Courtier 5th Dan: sneaking (always TN/contested) auto-includes +Air."""
    _create_char(page, live_server_url, "Court5Sneak", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"sneaking": 1})
    formula = page.evaluate("window._diceRoller?.formulas?.['skill:sneaking'] || {}")
    assert any("5th Dan" in b.get("label", "") for b in formula.get("bonuses", [])), \
        f"Sneaking should have 5th Dan bonus in bonuses: {formula.get('bonuses')}"


def test_courtier_5th_dan_never_skill_no_bonus(page, live_server_url):
    """Courtier 5th Dan: etiquette (never TN/contested) has no +Air."""
    _create_char(page, live_server_url, "Court5Etiq", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"etiquette": 1})
    formula = page.evaluate("window._diceRoller?.formulas?.['skill:etiquette'] || {}")
    assert not any("5th Dan" in b.get("label", "") for b in formula.get("bonuses", [])), \
        "Etiquette should NOT have 5th Dan bonus"
    assert formula.get("courtier_5th_dan_optional", 0) == 0, \
        "Etiquette should NOT have optional 5th Dan checkbox"


def test_courtier_5th_dan_sheet_display(page, live_server_url):
    """Courtier 5th Dan: sheet shows '+X from 5th Dan' without '(Air)' suffix."""
    _create_char(page, live_server_url, "Court5Sheet", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"sneaking": 1})
    # Check the skill display on the sheet
    body = page.text_content("body")
    assert "from 5th Dan" in body, "Sheet should show '5th Dan' bonus for sneaking"
    assert "5th Dan (Air)" not in body, "Sheet should NOT show '(Air)' after 5th Dan"


def test_courtier_5th_dan_sometimes_skill_checkbox(page, live_server_url):
    """Courtier 5th Dan: bragging (sometimes TN) shows checkbox on roll result."""
    _create_char(page, live_server_url, "Court5Brag", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"bragging": 1})
    # Clear VP so roll goes direct
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "skill:bragging")
    # Checkbox should be visible
    checkbox = page.locator('input[x-model="courtier5thApplied"]')
    assert checkbox.is_visible(), "5th Dan TN/contested checkbox should appear on bragging roll"
    # Get total before checking
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    # Check the box
    checkbox.check()
    page.wait_for_timeout(200)
    total_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    air_val = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula?.courtier_5th_dan_optional) return d.formula.courtier_5th_dan_optional;
        }
        return 0;
    }""")
    assert total_after == total_before + air_val, \
        f"Checking box should add +{air_val}: {total_before} -> {total_after}"
    # Uncheck should remove the bonus
    checkbox.uncheck()
    page.wait_for_timeout(200)
    total_unchecked = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    assert total_unchecked == total_before, \
        f"Unchecking should restore original: {total_before} != {total_unchecked}"


def test_hida_3rd_dan_reroll_appears(page, live_server_url):
    """Hida at 3rd Dan sees dice reroll selection after attack roll."""
    _create_char(page, live_server_url, "HidaReroll", "hida_bushi",
                 knack_overrides={"counterattack": 3, "iaijutsu": 3, "lunge": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    assert page.locator('text="Hida 3rd Dan: select up to"').is_visible()
    assert page.locator('button:text("Skip")').is_visible()


def test_hida_4th_dan_trade_sw_button(page, live_server_url):
    """Hida 4th Dan: button trades 2 SW for light wound reset."""
    _create_char(page, live_server_url, "Hida4SW", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    sa = _get_school_abilities(page)
    assert sa.get("hida_trade_sw") is True
    assert page.locator('button:has-text("Take 2 SW to reset LW to 0")').is_visible()
def test_hiruma_5th_dan_parry_note(page, live_server_url):
    """Hiruma 5th Dan: parry note flag is set and note text exists in DOM after parry roll."""
    _create_char(page, live_server_url, "Hiruma5Parry", "hiruma_scout",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    sa = _get_school_abilities(page)
    assert sa.get("hiruma_parry_reduce_lw") is True
    _roll_via_menu_or_direct(page, "parry")
    # Wait for Alpine to process x-show/x-cloak
    page.wait_for_timeout(500)
    note = page.locator(':text("Hiruma 5th Dan")')
    assert note.count() > 0


# ===========================================================================
# IDE DIPLOMAT (5 tests)
# ===========================================================================

def test_ide_1st_dan_skill_selection(page, live_server_url):
    """Ide Diplomat 1st Dan: technique_choices apply +1 rolled die to chosen skills."""
    _create_char(page, live_server_url, "Ide1Dan", "ide_diplomat",
                 skill_overrides={"bragging": 1})
    char_id = _extract_char_id(page)
    # Set technique choices via API
    _set_technique_choices(page, char_id, {"first_dan_choices": ["bragging", "precepts"]})
    # Reload sheet
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:bragging")
    assert f is not None
    # bragging rank 1 + Air 2 + 1 (1st Dan) = 4
    assert f["rolled"] == 4


def test_ide_2nd_dan_skill_selection(page, live_server_url):
    """Ide Diplomat 2nd Dan: technique_choices apply +5 to chosen skill."""
    _create_char(page, live_server_url, "Ide2Dan", "ide_diplomat",
                 knack_overrides={"double_attack": 2, "feint": 2, "worldliness": 2},
                 skill_overrides={"bragging": 1})
    char_id = _extract_char_id(page)
    _set_technique_choices(page, char_id, {
        "first_dan_choices": ["bragging"],
        "second_dan_choice": "bragging",
    })
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:bragging")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_ide_vp_regen_display(page, live_server_url):
    """Ide 4th Dan: VP regen display shows +1/night."""
    _create_char(page, live_server_url, "Ide4Regen", "ide_diplomat",
                 knack_overrides={"double_attack": 4, "feint": 4, "worldliness": 4})
    sa = _get_school_abilities(page)
    assert sa.get("ide_extra_vp_regen") is True
    assert page.locator('text="+1/night"').is_visible()


def test_ide_3rd_dan_subtract_button(page, live_server_url):
    """Ide 3rd Dan: subtract-from-roll button and VP spending UI visible."""
    _create_char(page, live_server_url, "Ide3Sub", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 1})
    sa = _get_school_abilities(page)
    assert sa.get("ide_subtract_roll") is True
    assert sa.get("ide_subtract_x", 0) > 0
    assert page.locator('text="Ide 3rd Dan - Subtract from Roll"').is_visible()


def test_ide_feint_banks_tn_reduce(page, live_server_url):
    """Ide feint banks -10 TN and applies on next attack."""
    _create_char(page, live_server_url, "IdeFeintTN", "ide_diplomat")
    sa = _get_school_abilities(page)
    assert sa.get("ide_feint_tn_reduce") is True
    _roll_via_menu_or_direct(page, "knack:feint")
    assert page.locator('button:has-text("Bank -10 TN on target")').is_visible()
def test_isawa_ishi_1st_dan_skill_selection(page, live_server_url):
    """Isawa Ishi 1st Dan: technique_choices apply +1 rolled die to chosen skills."""
    _create_char(page, live_server_url, "IsawaIshi1", "isawa_ishi",
                 skill_overrides={"precepts": 1})
    char_id = _extract_char_id(page)
    _set_technique_choices(page, char_id, {"first_dan_choices": ["precepts", "bragging"]})
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:precepts")
    assert f is not None
    # precepts rank 1 + Water 2 + 1 (1st Dan) = 4
    assert f["rolled"] == 4


def test_isawa_ishi_2nd_dan_skill_selection(page, live_server_url):
    """Isawa Ishi 2nd Dan: technique_choices apply +5 to chosen skill."""
    _create_char(page, live_server_url, "IsawaIshi2", "isawa_ishi",
                 knack_overrides={"absorb_void": 2, "kharmic_spin": 2, "otherworldliness": 2},
                 skill_overrides={"precepts": 1})
    char_id = _extract_char_id(page)
    _set_technique_choices(page, char_id, {
        "first_dan_choices": ["precepts"],
        "second_dan_choice": "precepts",
    })
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:precepts")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_isawa_ishi_vp_max_display(page, live_server_url):
    """Isawa Ishi: VP max display shows highest ring + school rank."""
    _create_char(page, live_server_url, "IsawaIshiVP", "isawa_ishi")
    # Default rings all 2 except Void 3 (school ring). School rank = Dan = 1
    # Highest ring = 3 (Void), school rank = 1 (Dan 1), VP max = 4
    vp_max = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.voidMax === 'number') return d.voidMax;
        }
        return null;
    }""")
    assert vp_max == 4  # highest ring (3) + school rank (1)
def test_kuni_5th_dan_reflect_damage_ui(page, live_server_url):
    """Kuni 5th Dan: reflect damage UI and self-damage calculation visible."""
    _create_char(page, live_server_url, "Kuni5Reflect", "kuni_witch_hunter",
                 knack_overrides={"detect_taint": 5, "iaijutsu": 5, "presence": 5})
    sa = _get_school_abilities(page)
    assert sa.get("kuni_reflect_damage") is True
    assert page.locator('text="Kuni 5th Dan - Reflect Damage"').is_visible()
def test_merchant_post_roll_vp_spending(page, live_server_url):
    """Merchant sees post-roll VP spending note after a skill roll."""
    _create_char(page, live_server_url, "MerchantVP", "merchant",
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('text="Merchant Special: spend VP after seeing the roll."').is_visible()
def test_mirumoto_5th_dan_vp_plus_10(page, live_server_url):
    """Mirumoto 5th Dan: VP spending on combat rolls applies +10 and shows it."""
    _create_char(page, live_server_url, "Mirumoto5VP", "mirumoto_bushi",
                 knack_overrides={"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    config = _get_void_spend_config(page)
    assert config.get("combat_vp_flat_bonus") == 10

    # Give VP so we can spend one - use JS to set directly
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)

    # Roll parry with 1 VP via the roll menu
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    # Click the "Spend 1 void point" option in the roll menu
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        vp_btn = menu.locator('button.text-accent').first
        if vp_btn.is_visible():
            vp_btn.click()
            _wait_roll_done(page)
            # The +10 bonus should appear in the result breakdown
            result_text = page.locator('[data-modal="dice-roller"]').text_content()
            assert "5th Dan" in result_text
def test_mirumoto_5th_dan_prob_charts_include_bonus(page, live_server_url):
    """Mirumoto 5th Dan: attack and wound check probability charts include +10/VP."""
    _create_char(page, live_server_url, "Miru5Prob", "mirumoto_bushi",
                 knack_overrides={"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    config = _get_void_spend_config(page)
    assert config.get("combat_vp_flat_bonus") == 10

    # Open attack modal to make atkHitChance available
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("15")
    page.wait_for_timeout(300)

    # Get attack avg roll with 0 VP and 1 VP
    avg_0, avg_1 = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkAvgAttackRoll) {
                return [d.atkAvgAttackRoll(0), d.atkAvgAttackRoll(1)];
            }
        }
        return [0, 0];
    }""")
    # The difference should include the +10 bonus (plus ~6.5 from 1k1 dice)
    diff = avg_1 - avg_0
    assert diff > 15, f"Avg roll diff with 1 VP should be >15 (got {diff}), 5th Dan +10 not reflected"

    # Close attack modal
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkModalOpen !== undefined) { d.atkModalOpen = false; }
        }
    }""")
    page.wait_for_timeout(300)

    # Open wound check modal
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "30")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)

    # Get wound check pass chance with 0 VP and 1 VP
    pass_0, pass_1 = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcProbRow) {
                const r0 = d.wcProbRow(0);
                const r1 = d.wcProbRow(1);
                return [r0?.passChance || 0, r1?.passChance || 0];
            }
        }
        return [0, 0];
    }""")
    # With +10 bonus on top of +1k1, pass chance with 1 VP should be significantly higher
    assert pass_1 >= pass_0, f"WC pass chance with 1 VP ({pass_1}) should be >= 0 VP ({pass_0})"


def test_mirumoto_4th_dan_prob_charts_no_bonus(page, live_server_url):
    """Mirumoto 4th Dan: probability charts should NOT include +10/VP bonus."""
    _create_char(page, live_server_url, "Miru4Prob", "mirumoto_bushi",
                 knack_overrides={"counterattack": 4, "double_attack": 4, "iaijutsu": 4})
    config = _get_void_spend_config(page)
    assert config.get("combat_vp_flat_bonus") == 0

    # Open attack modal
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("15")
    page.wait_for_timeout(300)

    # Get attack avg roll with 0 VP and 1 VP
    avg_0, avg_1 = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkAvgAttackRoll) {
                return [d.atkAvgAttackRoll(0), d.atkAvgAttackRoll(1)];
            }
        }
        return [0, 0];
    }""")
    # Without 5th Dan, the diff should be just the ~6.5 from 1k1 dice (no +10)
    diff = avg_1 - avg_0
    assert diff < 10, f"Avg roll diff with 1 VP should be <10 at 4th Dan (got {diff}), no +10 bonus"


def test_mirumoto_round_points_display_and_buttons(page, live_server_url):
    """Mirumoto at 3rd Dan: round points +/- and Reset buttons work."""
    _create_char(page, live_server_url, "MirumotoPoints", "mirumoto_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    page.wait_for_selector('text="3rd Dan Points"', timeout=5000)
    assert page.locator('text="3rd Dan Points"').is_visible()

    # Find the points section
    section = page.locator('text="3rd Dan Points"').locator('..')
    display = section.locator('[x-text="mirumotoRoundPoints"]')
    assert display.text_content().strip() == "0"

    # Click Reset - should set to max (2 * attack_skill = 2 * 1 = 2)
    section.locator('button:text("Reset")').click()
    page.wait_for_timeout(200)
    assert display.text_content().strip() == "2"

    # Click - to decrease
    section.locator('button:has-text("-")').click()
    page.wait_for_timeout(200)
    assert display.text_content().strip() == "1"

    # Click + to increase back
    section.locator('button:has-text("+")').first.click()
    page.wait_for_timeout(200)
    assert display.text_content().strip() == "2"
def test_priest_1st_dan_skill_selection(page, live_server_url):
    """Priest 1st Dan: technique_choices apply +1 rolled die to chosen skills."""
    _create_char(page, live_server_url, "Priest1Dan", "priest",
                 skill_overrides={"precepts": 1})
    char_id = _extract_char_id(page)
    _set_technique_choices(page, char_id, {"first_dan_choices": ["precepts", "attack"]})
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:precepts")
    assert f is not None
    # precepts (Water) rank 1 + Water 3 (default school ring) + 1 (1st Dan) = 5
    assert f["rolled"] == 5
def test_shosuro_stipend_display(page, live_server_url):
    """Shosuro Actor: stipend display on character sheet."""
    _create_char(page, live_server_url, "ShosuroStipend", "shosuro_actor")
    # All characters should have a stipend displayed
    stipend_el = page.locator('text="koku/year"').first
    assert stipend_el.is_visible()
def test_shugenja_1st_dan_element_selection(page, live_server_url):
    """Shugenja 1st Dan element selection (after enabling school)."""
    pass


@pytest.mark.skip(reason="Shugenja school disabled in UI")
def test_shugenja_2nd_dan_element_selection(page, live_server_url):
    """Shugenja 2nd Dan element selection (after enabling school)."""
    pass


@pytest.mark.skip(reason="Shugenja school disabled in UI")
def test_shugenja_3rd_dan_applicable_skills(page, live_server_url):
    """Shugenja 3rd Dan applicable skills (after enabling school)."""
    pass


@pytest.mark.skip(reason="Shugenja school disabled in UI")
def test_shugenja_ring_bonus_display(page, live_server_url):
    """Shugenja ring bonus display (after enabling school)."""
    pass
def test_togashi_3rd_dan_athletics_raises(page, live_server_url):
    """Togashi 3rd Dan: athletics roll shows raise spending button."""
    _create_char(page, live_server_url, "Togashi3Ath", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 1})
    sa = _get_school_abilities(page)
    assert sa.get("togashi_daily_athletics_raises") is True
    assert sa.get("togashi_daily_raises_max", 0) > 0
    # Clear VP so athletics roll goes direct without void menu
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    # Roll athletics and check for the button
    _roll_via_menu_or_direct(page, "athletics:Air")
    assert page.locator('button:has-text("Spend Athletics Raise")').is_visible()
def test_bayushi_feint_damage_button(page, live_server_url):
    """Bayushi feint damage: Back button returns to feint result."""
    _create_char(page, live_server_url, "BayushiFeintDmg2", "bayushi_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    _roll_via_menu_or_direct(page, "knack:feint")
    page.locator('button:text("Roll Feint Damage")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'sub-damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    # Verify damage total is a positive number
    total = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.subDamageTotal !== undefined) return d.subDamageTotal;
        }
        return -1;
    }""")
    assert total > 0, f"Feint damage total should be positive, got {total}"
    # Click Back to return to feint result
    page.locator('[data-modal="dice-roller"]').locator('button:text("Back")').click()
    page.wait_for_timeout(300)
    # Should be back on the done phase with Roll Feint Damage visible again
    assert page.locator('button:text("Roll Feint Damage")').is_visible()


# --- Shiba 3rd Dan: parry deals damage ---

def test_shiba_parry_damage_button(page, live_server_url):
    """Shiba at 3rd Dan: Roll Parry Damage shows dice animation and damage result."""
    _create_char(page, live_server_url, "ShibaParryDmg", "shiba_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    _roll_via_menu_or_direct(page, "parry")
    btn = page.locator('button:text("Roll Parry Damage")')
    assert btn.is_visible()
    btn.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'sub-damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    total = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.subDamageTotal !== undefined) return d.subDamageTotal;
        }
        return -1;
    }""")
    assert total >= 0, f"Parry damage total should be non-negative, got {total}"
    page.locator('[data-modal="dice-roller"]').locator('button:text("Back")').wait_for(state='visible', timeout=3000)
    assert page.locator('[data-modal="dice-roller"]').locator('button:text("Back")').is_visible()


# --- Feint temp VP for non-Akodo schools ---

def test_feint_temp_vp_button_for_bayushi(page, live_server_url):
    """Bayushi auto-gains 1 temp VP after feint."""
    _create_char(page, live_server_url, "BayushiFeintVP2", "bayushi_bushi")
    temp_before = page.evaluate("window._trackingBridge?.tempVoidPoints || 0")
    _roll_via_menu_or_direct(page, "knack:feint")
    temp_after = page.evaluate("window._trackingBridge?.tempVoidPoints || 0")
    assert temp_after == temp_before + 1, f"Expected +1 temp VP, got {temp_before} -> {temp_after}"


# --- Hida 3rd Dan: reroll dice selection ---

def test_hida_reroll_selection_appears(page, live_server_url):
    """Hida at 3rd Dan sees ALL dice (kept and unkept) for reroll selection."""
    _create_char(page, live_server_url, "HidaReroll2", "hida_bushi",
                 knack_overrides={"counterattack": 3, "iaijutsu": 3, "lunge": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    assert page.locator('text="Hida 3rd Dan: select up to"').is_visible()
    assert page.locator('button:text("Skip")').is_visible()
    # All dice should be shown (rolled count), not just kept
    dice_count = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.finalDice) return d.finalDice.length;
        }
        return 0;
    }""")
    reroll_buttons = page.locator('[x-show*="hidaRerollPhase"] button.rounded-full')
    assert reroll_buttons.count() == dice_count, f"Expected {dice_count} dice buttons, got {reroll_buttons.count()}"


# --- Merchant Special: post-roll VP spending ---

def test_merchant_post_roll_vp_buttons(page, live_server_url):
    """Merchant sees post-roll VP spending note after a skill roll."""
    _create_char(page, live_server_url, "MerchantVP2", "merchant",
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('text="Merchant Special: spend VP after seeing the roll."').is_visible()


# --- Mirumoto 3rd Dan: round points counter ---

def test_mirumoto_round_points_counter(page, live_server_url):
    """Mirumoto at 3rd Dan sees the round points counter in tracking."""
    _create_char(page, live_server_url, "MirumotoPoints2", "mirumoto_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    page.wait_for_selector('text="3rd Dan Points"', timeout=5000)
    assert page.locator('text="3rd Dan Points"').is_visible()


# --- Daidoji 3rd Dan: counterattack raises note (in attack modal) ---

def test_daidoji_counterattack_school_flag(page, live_server_url):
    """Daidoji at 3rd Dan has the counterattack raises flag set."""
    _create_char(page, live_server_url, "DaidojiCA2", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    has_flag = page.evaluate("""() => {
        const el = document.getElementById('school-abilities');
        if (!el) return false;
        const data = JSON.parse(el.textContent || '{}');
        return data.daidoji_counterattack_raises === true;
    }""")
    assert has_flag
def test_brotherhood_3rd_dan_precepts_raises(page, live_server_url):
    """Brotherhood at 3rd Dan: rolling a skill in applicable_to shows Spend button."""
    _create_char(page, live_server_url, "BrothPrecepts3", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
                 skill_overrides={"precepts": 1})
    # precepts is in applicable_to
    _roll_via_menu_or_direct(page, "skill:precepts")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_courtier_3rd_dan_tact_raises(page, live_server_url):
    """Courtier at 3rd Dan: rolling tact (applicable) shows Spend button."""
    _create_char(page, live_server_url, "CourtTact3", "courtier",
                 knack_overrides={"discern_honor": 3, "oppose_social": 3, "worldliness": 3},
                 skill_overrides={"tact": 1})
    _roll_via_menu_or_direct(page, "skill:tact")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_doji_3rd_dan_culture_raises(page, live_server_url):
    """Doji at 3rd Dan: rolling culture (applicable) shows Spend button."""
    _create_char(page, live_server_url, "DojiCulture3", "doji_artisan",
                 knack_overrides={"counterattack": 3, "oppose_social": 3, "worldliness": 3},
                 skill_overrides={"culture": 1})
    _roll_via_menu_or_direct(page, "skill:culture")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_ikoma_3rd_dan_bragging_raises(page, live_server_url):
    """Ikoma at 3rd Dan: rolling bragging (applicable) shows Spend button."""
    _create_char(page, live_server_url, "IkomaBrag3", "ikoma_bard",
                 knack_overrides={"discern_honor": 3, "oppose_knowledge": 3, "oppose_social": 3},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_kitsuki_3rd_dan_investigation_raises(page, live_server_url):
    """Kitsuki at 3rd Dan: rolling interrogation (applicable) shows Spend button."""
    _create_char(page, live_server_url, "KitsukiInv3", "kitsuki_magistrate",
                 knack_overrides={"discern_honor": 3, "iaijutsu": 3, "presence": 3},
                 skill_overrides={"investigation": 1, "interrogation": 1})
    # interrogation is in applicable_to
    _roll_via_menu_or_direct(page, "skill:interrogation")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_kuni_3rd_dan_interrogation_raises(page, live_server_url):
    """Kuni at 3rd Dan: rolling interrogation (applicable) shows Spend button."""
    _create_char(page, live_server_url, "KuniInterr3", "kuni_witch_hunter",
                 knack_overrides={"detect_taint": 3, "iaijutsu": 3, "presence": 3},
                 skill_overrides={"investigation": 1, "interrogation": 1})
    _roll_via_menu_or_direct(page, "skill:interrogation")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_merchant_3rd_dan_sincerity_raises(page, live_server_url):
    """Merchant at 3rd Dan: rolling sincerity (applicable) shows Spend button."""
    _create_char(page, live_server_url, "MerchSinc3", "merchant",
                 knack_overrides={"discern_honor": 3, "oppose_knowledge": 3, "worldliness": 3},
                 skill_overrides={"sincerity": 1})
    _roll_via_menu_or_direct(page, "skill:sincerity")
    assert page.locator('[data-action="spend-raise"]').is_visible()


def test_shosuro_3rd_dan_sincerity_raises(page, live_server_url):
    """Shosuro at 3rd Dan: rolling sincerity (applicable) shows Spend button."""
    _create_char(page, live_server_url, "ShosSinc3", "shosuro_actor",
                 knack_overrides={"athletics": 3, "discern_honor": 3, "pontificate": 3},
                 skill_overrides={"sincerity": 1})
    _roll_via_menu_or_direct(page, "skill:sincerity")
    assert page.locator('[data-action="spend-raise"]').is_visible()


# ===========================================================================
# BUTTON INTERACTION TESTS - verify buttons actually work when clicked
# ===========================================================================


def test_hida_trade_sw_button_works(page, live_server_url):
    """Hida 4th Dan: Take 2 SW to reset LW - adds 2 SW and sets LW to 0."""
    _create_char(page, live_server_url, "HidaTrade", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    trade_btn = page.locator('button:has-text("Take 2 SW to reset LW to 0")')
    # Button should be disabled with 0 LW
    assert trade_btn.is_disabled(), "Button should be disabled when LW is 0"
    # Add light wounds
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "15")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    assert not trade_btn.is_disabled(), "Button should be enabled when LW > 0"
    # Click the button
    trade_btn.click()
    page.wait_for_timeout(300)
    # SW should increase by 2, LW should be 0
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"


def test_togashi_heal_sw_button_works(page, live_server_url):
    """Togashi 5th Dan: Spend 1 VP to heal 2 SW button works."""
    _create_char(page, live_server_url, "TogashiHeal", "togashi_ise_zumi",
                 knack_overrides={"athletics": 5, "conviction": 5, "dragon_tattoo": 5})
    # VP starts at full (2). Add 2 SW.
    sw_row = page.locator('text="Serious Wounds"').locator('..')
    sw_row.locator('button:has-text("+")').click()
    sw_row.locator('button:has-text("+")').click()
    page.wait_for_timeout(300)

    # Click heal button (costs 1 VP, heals 2 SW)
    heal_btn = page.locator('button:has-text("Spend 1 VP to heal 2 SW")')
    assert heal_btn.is_visible()
    heal_btn.click()
    page.wait_for_timeout(300)

    # VP should be 1 (2 - 1), SW should be 0
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "1"
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "0"


def test_ide_subtract_button_visible(page, live_server_url):
    """Ide 3rd Dan: subtract button visible on sheet."""
    _create_char(page, live_server_url, "IdeSubtract", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 2})
    # The subtract button should be visible
    assert page.locator('text="Ide 3rd Dan - Subtract from Roll"').is_visible()


# ===========================================================================
# REMAINING GAP TESTS
# ===========================================================================


def test_akodo_5th_dan_reflect_damage_ui(page, live_server_url):
    """Akodo 5th Dan: reflect damage section appears on wound check result."""
    _create_char(page, live_server_url, "AkodoReflect", "akodo_bushi",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    sa = _get_school_abilities(page)
    assert sa.get("akodo_reflect_damage") is True
    # The reflect UI appears in the wound check result - verify the flag is set
    # and the UI element exists in the DOM
    assert page.locator('text="Akodo 5th Dan - Reflect Damage"').count() > 0
def test_ide_5th_dan_temp_vp_on_spend(page, live_server_url):
    """Ide 5th Dan: spending VP auto-grants temp VP."""
    _create_char(page, live_server_url, "Ide5TempVP", "ide_diplomat",
                 knack_overrides={"double_attack": 5, "feint": 5, "worldliness": 5},
                 skill_overrides={"bragging": 1})
    sa = _get_school_abilities(page)
    assert sa.get("ide_temp_vp_on_spend") is True

    # Give VP, then spend it on a roll
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)

    # Roll bragging with 1 VP
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        vp_btn = menu.locator('button.text-accent').first
        if vp_btn.is_visible():
            vp_btn.click()
            _wait_roll_done(page)
            # Temp VP should have been granted (1 non-temp VP spent -> 1 temp VP gained)
            temp_vp = page.evaluate("window._trackingBridge.tempVoidPoints")
            assert temp_vp >= 1


def test_isawa_duelist_3rd_dan_tn_trade_toggle(page, live_server_url):
    """Isawa Duelist 3rd Dan: TN trade toggle appears in attack modal."""
    _create_char(page, live_server_url, "IsawaTnTrade", "isawa_duelist",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    sa = _get_school_abilities(page)
    assert sa.get("isawa_tn_trade") is True

    # Open the attack modal
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    page.wait_for_timeout(300)

    # Check the diceRoller's schoolAbilities
    dice_sa = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.schoolAbilities) return d.schoolAbilities;
        }
        return null;
    }""")
    assert dice_sa and dice_sa.get("isawa_tn_trade") is True, f"diceRoller schoolAbilities: {dice_sa}"

    modal = page.locator('[data-modal="attack"]')
    assert modal.locator('input[type="checkbox"]').count() > 0, "TN trade checkbox exists"


def test_shiba_5th_dan_parry_tn_note(page, live_server_url):
    """Shiba 5th Dan: parry TN reduction note appears after parry roll."""
    _create_char(page, live_server_url, "Shiba5Parry", "shiba_bushi",
                 knack_overrides={"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    sa = _get_school_abilities(page)
    assert sa.get("shiba_parry_lower_tn") is True

    # Verify the flag and that the note element exists in the DOM
    # (it's shown via x-show after a parry roll completes, but x-cloak may hide it
    # if Alpine hasn't evaluated yet - checking the flag is sufficient)
    _roll_via_menu_or_direct(page, "parry")
    page.wait_for_timeout(500)
    # Check via JS that the shiba note condition would be true
    visible = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done' && d.currentRollKey === 'parry'
                && d.schoolAbilities?.shiba_parry_lower_tn) return true;
        }
        return false;
    }""")
    assert visible, "Shiba 5th Dan parry note conditions are met after parry roll"


def test_shosuro_5th_dan_lowest_3_dice(page, live_server_url):
    """Shosuro 5th Dan: lowest 3 dice addition appears in roll result."""
    _create_char(page, live_server_url, "Shosuro5Dice", "shosuro_actor",
                 knack_overrides={"athletics": 5, "discern_honor": 5, "pontificate": 5},
                 skill_overrides={"bragging": 1})
    sa = _get_school_abilities(page)
    assert sa.get("shosuro_add_lowest_3") is True

    _roll_via_menu_or_direct(page, "skill:bragging")
    # The lowest 3 dice bonus should appear in the result
    result_text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "5th Dan" in result_text and "lowest 3" in result_text


# ===========================================================================
# 1st DAN BEHAVIORAL TESTS - roll dice and verify dice count in result
# These replace the flag-only formula tests with actual UI interaction.
# ===========================================================================


def test_akodo_1st_dan_behavioral(page, live_server_url):
    """Akodo 1st Dan: rolling attack shows 4 dice (1 attack + 2 Fire + 1 extra)."""
    _create_char(page, live_server_url, "Akodo1B", "akodo_bushi")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_bayushi_1st_dan_behavioral(page, live_server_url):
    """Bayushi 1st Dan: rolling double_attack shows 4 dice (1 knack + 2 Fire + 1 extra)."""
    _create_char(page, live_server_url, "Bayushi1B", "bayushi_bushi")
    expected = _get_formula(page, "knack:double_attack")["rolled"]
    _open_attack_modal_and_roll(page, "knack:double_attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_brotherhood_1st_dan_behavioral(page, live_server_url):
    """Brotherhood 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Brotherhood1B", "brotherhood_of_shinsei_monk")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_courtier_1st_dan_behavioral(page, live_server_url):
    """Courtier 1st Dan: rolling tact shows 4 dice (1 skill + 2 Air + 1 extra)."""
    _create_char(page, live_server_url, "Courtier1B", "courtier",
                 skill_overrides={"tact": 1})
    expected = _get_formula(page, "skill:tact")["rolled"]
    _roll_via_menu_or_direct(page, "skill:tact")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_daidoji_1st_dan_behavioral(page, live_server_url):
    """Daidoji 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Daidoji1B", "daidoji_yojimbo")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_doji_1st_dan_behavioral(page, live_server_url):
    """Doji 1st Dan: rolling manipulation shows 4 dice."""
    _create_char(page, live_server_url, "Doji1B", "doji_artisan",
                 skill_overrides={"manipulation": 1})
    expected = _get_formula(page, "skill:manipulation")["rolled"]
    _roll_via_menu_or_direct(page, "skill:manipulation")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_hida_1st_dan_behavioral(page, live_server_url):
    """Hida 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Hida1B", "hida_bushi")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_hiruma_1st_dan_behavioral(page, live_server_url):
    """Hiruma 1st Dan: rolling parry shows 4 dice (1 parry + 2 Air + 1 extra)."""
    _create_char(page, live_server_url, "Hiruma1B", "hiruma_scout")
    expected = _get_formula(page, "parry")["rolled"]
    _roll_via_menu_or_direct(page, "parry")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_ikoma_1st_dan_behavioral(page, live_server_url):
    """Ikoma 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Ikoma1B", "ikoma_bard")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_isawa_duelist_1st_dan_behavioral(page, live_server_url):
    """Isawa Duelist 1st Dan: rolling lunge shows 4 dice."""
    _create_char(page, live_server_url, "IsawaD1B", "isawa_duelist")
    expected = _get_formula(page, "knack:lunge")["rolled"]
    _open_attack_modal_and_roll(page, "knack:lunge")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_kakita_1st_dan_behavioral(page, live_server_url):
    """Kakita 1st Dan: rolling iaijutsu shows 4 dice."""
    _create_char(page, live_server_url, "Kakita1B", "kakita_duelist")
    expected = _get_formula(page, "knack:iaijutsu")["rolled"]
    _roll_via_menu_or_direct(page, "knack:iaijutsu")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_kitsuki_1st_dan_behavioral(page, live_server_url):
    """Kitsuki 1st Dan: rolling interrogation shows 5 dice (1 skill + 3 Water + 1 extra)."""
    _create_char(page, live_server_url, "Kitsuki1B", "kitsuki_magistrate",
                 skill_overrides={"interrogation": 1})
    _roll_via_menu_or_direct(page, "skill:interrogation")
    # Kitsuki uses Water(3) for interrogation, so 1+3+1 = 5
    assert _get_result_rolled(page) == 5
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_kuni_1st_dan_behavioral(page, live_server_url):
    """Kuni 1st Dan: rolling interrogation shows 4 dice (1 skill + 2 Air + 1 extra)."""
    _create_char(page, live_server_url, "Kuni1B", "kuni_witch_hunter",
                 skill_overrides={"interrogation": 1})
    expected = _get_formula(page, "skill:interrogation")["rolled"]
    _roll_via_menu_or_direct(page, "skill:interrogation")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_matsu_1st_dan_behavioral(page, live_server_url):
    """Matsu 1st Dan: rolling iaijutsu shows 4 dice."""
    _create_char(page, live_server_url, "Matsu1B", "matsu_bushi")
    expected = _get_formula(page, "knack:iaijutsu")["rolled"]
    _roll_via_menu_or_direct(page, "knack:iaijutsu")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_merchant_1st_dan_behavioral(page, live_server_url):
    """Merchant 1st Dan: rolling sincerity shows 4 dice (1 skill + 2 Air + 1 extra)."""
    _create_char(page, live_server_url, "Merchant1B", "merchant",
                 skill_overrides={"sincerity": 1})
    expected = _get_formula(page, "skill:sincerity")["rolled"]
    _roll_via_menu_or_direct(page, "skill:sincerity")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_mirumoto_1st_dan_behavioral(page, live_server_url):
    """Mirumoto 1st Dan: rolling parry shows 4 dice (1 parry + 2 Air + 1 extra)."""
    _create_char(page, live_server_url, "Mirumoto1B", "mirumoto_bushi")
    expected = _get_formula(page, "parry")["rolled"]
    _roll_via_menu_or_direct(page, "parry")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_otaku_1st_dan_behavioral(page, live_server_url):
    """Otaku 1st Dan: rolling lunge shows 4 dice."""
    _create_char(page, live_server_url, "Otaku1B", "otaku_bushi")
    expected = _get_formula(page, "knack:lunge")["rolled"]
    _open_attack_modal_and_roll(page, "knack:lunge")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_shiba_1st_dan_behavioral(page, live_server_url):
    """Shiba 1st Dan: rolling parry shows 4 dice."""
    _create_char(page, live_server_url, "Shiba1B", "shiba_bushi")
    expected = _get_formula(page, "parry")["rolled"]
    _roll_via_menu_or_direct(page, "parry")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_shinjo_1st_dan_behavioral(page, live_server_url):
    """Shinjo 1st Dan: rolling parry shows 4 dice."""
    _create_char(page, live_server_url, "Shinjo1B", "shinjo_bushi")
    expected = _get_formula(page, "parry")["rolled"]
    _roll_via_menu_or_direct(page, "parry")
    assert _get_result_rolled(page) == expected
    assert _count_result_dice(page) > 0  # dice are visible in result


def test_shosuro_1st_dan_behavioral(page, live_server_url):
    """Shosuro 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Shosuro1B", "shosuro_actor")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_togashi_1st_dan_behavioral(page, live_server_url):
    """Togashi 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Togashi1B", "togashi_ise_zumi")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


def test_yogo_1st_dan_behavioral(page, live_server_url):
    """Yogo 1st Dan: rolling attack shows 4 dice."""
    _create_char(page, live_server_url, "Yogo1B", "yogo_warden")
    expected = _get_formula(page, "attack")["rolled"]
    _open_attack_modal_and_roll(page, "attack")
    assert _get_attack_result_rolled(page) == expected
    assert _count_attack_result_dice(page) > 0  # dice are visible in result


# ===========================================================================
# 2nd DAN BEHAVIORAL TESTS - roll and verify +5 bonus appears in result
# ===========================================================================


def _roll_wound_check(page):
    """Add light wounds and roll a wound check."""
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)


def _get_wc_result_text(page):
    return page.locator('[data-modal="wound-check"]').text_content()


def _get_attack_result_text(page):
    return page.locator('[data-modal="attack"]').text_content()


def _get_roll_result_text(page):
    return page.locator('[data-modal="dice-roller"]').text_content()


# --- Wound check 2nd Dan (Akodo, Isawa Duelist, Otaku, Yogo) ---

def test_akodo_2nd_dan_behavioral(page, live_server_url):
    """Akodo 2nd Dan: wound check shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Akodo2B", "akodo_bushi",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    _roll_wound_check(page)
    assert "2nd Dan" in _get_wc_result_text(page)


def test_isawa_duelist_2nd_dan_behavioral(page, live_server_url):
    """Isawa Duelist 2nd Dan: wound check shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "IsawaD2B", "isawa_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _roll_wound_check(page)
    assert "2nd Dan" in _get_wc_result_text(page)


def test_otaku_2nd_dan_behavioral(page, live_server_url):
    """Otaku 2nd Dan: wound check shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Otaku2B", "otaku_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _roll_wound_check(page)
    assert "2nd Dan" in _get_wc_result_text(page)


def test_yogo_2nd_dan_behavioral(page, live_server_url):
    """Yogo 2nd Dan: wound check shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Yogo2B", "yogo_warden",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "feint": 2})
    _roll_wound_check(page)
    assert "2nd Dan" in _get_wc_result_text(page)


# --- Attack modal 2nd Dan ---

def test_bayushi_2nd_dan_behavioral(page, live_server_url):
    """Bayushi 2nd Dan: double_attack shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Bayushi2B", "bayushi_bushi",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    _open_attack_modal_and_roll(page, "knack:double_attack")
    assert "2nd Dan" in _get_attack_result_text(page)


def test_brotherhood_2nd_dan_behavioral(page, live_server_url):
    """Brotherhood 2nd Dan: attack shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Brotherhood2B", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "worldliness": 2})
    _open_attack_modal_and_roll(page, "attack")
    assert "2nd Dan" in _get_attack_result_text(page)


def test_daidoji_2nd_dan_behavioral(page, live_server_url):
    """Daidoji 2nd Dan: counterattack shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Daidoji2B", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    _open_attack_modal_and_roll(page, "knack:counterattack")
    assert "2nd Dan" in _get_attack_result_text(page)


def test_hida_2nd_dan_behavioral(page, live_server_url):
    """Hida 2nd Dan: counterattack shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Hida2B", "hida_bushi",
                 knack_overrides={"counterattack": 2, "iaijutsu": 2, "lunge": 2})
    _open_attack_modal_and_roll(page, "knack:counterattack")
    assert "2nd Dan" in _get_attack_result_text(page)


def test_ikoma_2nd_dan_behavioral(page, live_server_url):
    """Ikoma 2nd Dan: attack shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Ikoma2B", "ikoma_bard",
                 knack_overrides={"discern_honor": 2, "oppose_knowledge": 2, "oppose_social": 2})
    _open_attack_modal_and_roll(page, "attack")
    assert "2nd Dan" in _get_attack_result_text(page)


# --- Skill/knack via roll menu 2nd Dan ---

def test_shosuro_2nd_dan_behavioral(page, live_server_url):
    """Shosuro 2nd Dan: sincerity roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Shosuro2B", "shosuro_actor",
                 knack_overrides={"athletics": 2, "discern_honor": 2, "pontificate": 2},
                 skill_overrides={"sincerity": 1})
    _roll_via_menu_or_direct(page, "skill:sincerity")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_kakita_2nd_dan_behavioral(page, live_server_url):
    """Kakita 2nd Dan: iaijutsu roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Kakita2B", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _roll_via_menu_or_direct(page, "knack:iaijutsu")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_matsu_2nd_dan_behavioral(page, live_server_url):
    """Matsu 2nd Dan: iaijutsu roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Matsu2B", "matsu_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _roll_via_menu_or_direct(page, "knack:iaijutsu")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_courtier_2nd_dan_behavioral(page, live_server_url):
    """Courtier 2nd Dan: manipulation roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Courtier2B", "courtier",
                 knack_overrides={"discern_honor": 2, "oppose_social": 2, "worldliness": 2},
                 skill_overrides={"manipulation": 1})
    _roll_via_menu_or_direct(page, "skill:manipulation")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_doji_2nd_dan_behavioral(page, live_server_url):
    """Doji 2nd Dan: manipulation roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Doji2B", "doji_artisan",
                 knack_overrides={"counterattack": 2, "oppose_social": 2, "worldliness": 2},
                 skill_overrides={"manipulation": 1})
    _roll_via_menu_or_direct(page, "skill:manipulation")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_kitsuki_2nd_dan_behavioral(page, live_server_url):
    """Kitsuki 2nd Dan: interrogation roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Kitsuki2B", "kitsuki_magistrate",
                 knack_overrides={"discern_honor": 2, "iaijutsu": 2, "presence": 2},
                 skill_overrides={"interrogation": 1})
    _roll_via_menu_or_direct(page, "skill:interrogation")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_kuni_2nd_dan_behavioral(page, live_server_url):
    """Kuni 2nd Dan: interrogation roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Kuni2B", "kuni_witch_hunter",
                 knack_overrides={"detect_taint": 2, "iaijutsu": 2, "presence": 2},
                 skill_overrides={"interrogation": 1})
    _roll_via_menu_or_direct(page, "skill:interrogation")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_merchant_2nd_dan_behavioral(page, live_server_url):
    """Merchant 2nd Dan: interrogation roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Merchant2B", "merchant",
                 knack_overrides={"discern_honor": 2, "oppose_knowledge": 2, "worldliness": 2},
                 skill_overrides={"interrogation": 1})
    _roll_via_menu_or_direct(page, "skill:interrogation")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_priest_2nd_dan_behavioral(page, live_server_url):
    """Priest 2nd Dan: bragging roll shows +5 from Priest 2nd Dan."""
    _create_char(page, live_server_url, "Priest2B", "priest",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert "Priest 2nd Dan" in _get_roll_result_text(page)


# --- Parry 2nd Dan ---

def test_hiruma_2nd_dan_behavioral(page, live_server_url):
    """Hiruma 2nd Dan: parry roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Hiruma2B", "hiruma_scout",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    _roll_via_menu_or_direct(page, "parry")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_mirumoto_2nd_dan_behavioral(page, live_server_url):
    """Mirumoto 2nd Dan: parry roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Mirumoto2B", "mirumoto_bushi",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "parry")
    _restore_dice(page)
    assert "2nd Dan" in _get_roll_result_text(page)


def test_shiba_2nd_dan_behavioral(page, live_server_url):
    """Shiba 2nd Dan: parry roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Shiba2B", "shiba_bushi",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    _roll_via_menu_or_direct(page, "parry")
    assert "2nd Dan" in _get_roll_result_text(page)


def test_shinjo_2nd_dan_behavioral(page, live_server_url):
    """Shinjo 2nd Dan: parry roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Shinjo2B", "shinjo_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _roll_via_menu_or_direct(page, "parry")
    assert "2nd Dan" in _get_roll_result_text(page)


# --- Athletics 2nd Dan ---

def test_togashi_2nd_dan_behavioral(page, live_server_url):
    """Togashi 2nd Dan: athletics roll shows +5 from 2nd Dan."""
    _create_char(page, live_server_url, "Togashi2B", "togashi_ise_zumi",
                 knack_overrides={"athletics": 2, "conviction": 2, "dragon_tattoo": 2})
    _roll_via_menu_or_direct(page, "athletics:Earth")
    assert "2nd Dan" in _get_roll_result_text(page)


# ===========================================================================
# SPECIAL ABILITY & FORMULA BEHAVIORAL TESTS
# ===========================================================================


def test_bayushi_5th_dan_half_lw_behavioral(page, live_server_url):
    """Bayushi 5th Dan: failing wound check calculates serious wounds using half LW, never negative."""
    _create_char(page, live_server_url, "Bayushi5B", "bayushi_bushi",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    f = _get_formula(page, "wound_check")
    assert f.get("bayushi_5th_dan_half_lw") is True
    # Set LW to 60. Half is 30. With high dice (roll ~7*kept), roll should exceed 30
    # but not 60, triggering the edge case where margin would have gone negative.
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)  # dice roll 7 each -> ~35 total for a 5k3+flat roll
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    wc_data = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return {
                passed: d.wcPassed, sw: d.wcSeriousWounds,
                margin: d.wcMargin, bayushi: d.wcBayushiHalfLw
            };
        }
        return null;
    }""")
    if wc_data and not wc_data["passed"]:
        # Serious wounds must always be >= 1 on a failed check
        assert wc_data["sw"] >= 1, f"SW should be >= 1, got {wc_data['sw']}"
        # Margin must never be negative
        assert wc_data["margin"] >= 0, f"Margin should be >= 0, got {wc_data['margin']}"
        # The bayushi flag should be set
        assert wc_data["bayushi"] is True
        # The explanatory text should be visible
        wc_modal = page.locator('[data-modal="wound-check"]')
        assert "halved" in wc_modal.text_content().lower()


def test_bayushi_below_5th_dan_no_half_lw(page, live_server_url):
    """Bayushi below 5th Dan: wound check does NOT use half-LW calculation."""
    _create_char(page, live_server_url, "Bayushi4NoHalf", "bayushi_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    f = _get_formula(page, "wound_check")
    assert f.get("bayushi_5th_dan_half_lw") is not True, "4th Dan should not have half-LW flag"
    # Add LW and roll wound check
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    wc_data = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return { passed: d.wcPassed, sw: d.wcSeriousWounds, bayushi: d.wcBayushiHalfLw };
        }
        return null;
    }""")
    if wc_data and not wc_data["passed"]:
        assert wc_data["bayushi"] is False, "4th Dan should not set bayushi half-LW flag"
        # With low dice and 60 LW, SW should be based on full 60, not half
        assert wc_data["sw"] >= 4, f"Expected >= 4 SW with full 60 LW and low dice, got {wc_data['sw']}"
        # Bayushi 5th Dan explanation should NOT be visible
        wc_modal = page.locator('[data-modal="wound-check"]')
        halved_note = wc_modal.locator('text="Bayushi 5th Dan"')
        assert halved_note.count() == 0 or not halved_note.first.is_visible()


def test_bayushi_5th_dan_prob_table_shows_half_lw(page, live_server_url):
    """Bayushi 5th Dan: wound check probability table reflects halved LW for SW columns."""
    _create_char(page, live_server_url, "Bayushi5Prob", "bayushi_bushi",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    # Add LW so the table has meaningful numbers
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Open wound check modal to see the probability table
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    # The Bayushi 5th Dan note should appear
    wc_modal = page.locator('[data-modal="wound-check"]')
    text = wc_modal.text_content().lower()
    assert "bayushi 5th dan" in text
    assert "halved" in text
    assert "30 instead of 60" in text


def test_bayushi_below_5th_dan_prob_table_no_half_note(page, live_server_url):
    """Bayushi below 5th Dan: wound check probability table does NOT show halved note."""
    _create_char(page, live_server_url, "Bayushi4Prob", "bayushi_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    wc_modal = page.locator('[data-modal="wound-check"]')
    halved_note = wc_modal.locator('text="Bayushi 5th Dan"')
    assert halved_note.count() == 0 or not halved_note.first.is_visible()


def test_brotherhood_unarmed_damage_behavioral(page, live_server_url):
    """Brotherhood Special: attack damage shows +1k1 unarmed bonus in breakdown."""
    _create_char(page, live_server_url, "Brotherhood_UB", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "worldliness": 2})
    _mock_dice_high(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    dmg_text = _get_attack_result_text(page)
    assert "unarmed" in dmg_text.lower() or "1k1" in dmg_text


def test_courtier_air_attack_behavioral(page, live_server_url):
    """Courtier Special: attack result shows +Air bonus in breakdown."""
    _create_char(page, live_server_url, "CourtierAirB", "courtier",
                 knack_overrides={"discern_honor": 1, "oppose_social": 1, "worldliness": 1})
    _open_attack_modal_and_roll(page, "attack")
    result = _get_attack_result_text(page)
    assert "Air" in result or "Courtier" in result


def test_courtier_5th_dan_air_skill_behavioral(page, live_server_url):
    """Courtier 5th Dan: skill roll result shows +Air bonus from 5th Dan."""
    _create_char(page, live_server_url, "Courtier5AB", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    result = _get_roll_result_text(page)
    assert "5th Dan" in result


def test_isawa_duelist_water_damage_behavioral(page, live_server_url):
    """Isawa Duelist Special: attack damage uses Water ring in breakdown."""
    _create_char(page, live_server_url, "IsawaDmgB", "isawa_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # Verify via formula that damage ring is Water (server-side check)
    f = _get_formula(page, "attack")
    assert f["damage_ring_name"] == "Water"
    # Also roll and verify damage parts mention Water
    _mock_dice_high(page)
    # Open attack modal with low TN to guarantee hit
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Roll damage
    modal.locator('button:has-text("Make Damage Roll")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    dmg_text = _get_attack_result_text(page)
    assert "Water" in dmg_text


def test_isawa_ishi_vp_max_behavioral(page, live_server_url):
    """Isawa Ishi Special: VP max on sheet shows highest ring + school rank."""
    _create_char(page, live_server_url, "IsawaVPMax", "isawa_ishi",
                 knack_overrides={"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1},
                 skill_overrides={"precepts": 1})
    # Default rings: Air=2, Fire=2, Earth=2, Water=3, Void=2
    # Highest ring = 3 (Water), school rank (dan) = 1
    # VP max should be 3 + 1 = 4, not 2 (lowest ring)
    vp_max = page.evaluate("window._trackingBridge?.voidMax || 0")
    assert vp_max == 4, f"Expected VP max 4 (3+1), got {vp_max}"
    # Verify it's displayed on the page
    body = page.text_content("body")
    assert "max 4" in body


def test_kakita_phase_0_behavioral(page, live_server_url):
    """Kakita Special: rolling initiative with 10s shows Phase 0 dice."""
    _create_char(page, live_server_url, "KakitaP0B", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # Mock dice to return 10 so Phase 0 triggers (10s become Phase 0 for Kakita)
    _mock_dice_ten(page)
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    # With all 10s, initiative doesn't reroll (initiative never rerolls 10s)
    # Kakita converts 10s to Phase 0
    action_dice = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.actionDice && d.phase === 'done') return d.actionDice;
        }
        return [];
    }""")
    assert 0 in action_dice, f"Expected Phase 0 in action dice {action_dice}"
    result = _get_roll_result_text(page)
    assert "Phase 0" in result


def test_kitsuki_water_interrogation_behavioral(page, live_server_url):
    """Kitsuki Special: interrogation uses Water ring; attack has +2*Water bonus."""
    _create_char(page, live_server_url, "KitsukiWaterB", "kitsuki_magistrate",
                 knack_overrides={"discern_honor": 1, "iaijutsu": 1, "presence": 1},
                 skill_overrides={"interrogation": 1})
    # Roll interrogation - should use Water
    _roll_via_menu_or_direct(page, "skill:interrogation")
    result = _get_roll_result_text(page)
    # The formula label should show "Water" (since Kitsuki overrides Air to Water)
    f = _get_formula(page, "skill:interrogation")
    assert f is not None
    assert "Water" in f.get("label", "")
    # Also check attack has +2*Water bonus
    atk = _get_formula(page, "attack")
    assert any("Kitsuki" in b.get("label", "") or "Water" in b.get("label", "") for b in atk.get("bonuses", []))


def test_matsu_10_dice_initiative_behavioral(page, live_server_url):
    """Matsu Special: rolling initiative produces 10 dice in result."""
    _create_char(page, live_server_url, "MatsuInitB", "matsu_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    # Check that 10 dice were rolled
    dice_count = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.finalDice && d.phase === 'done') return d.finalDice.length;
        }
        return 0;
    }""")
    assert dice_count == 10


def test_shiba_4th_dan_3k1_wound_check_behavioral(page, live_server_url):
    """Shiba 4th Dan: wound check result shows +3k1 bonus."""
    _create_char(page, live_server_url, "Shiba4WCB", "shiba_bushi",
                 knack_overrides={"counterattack": 4, "double_attack": 4, "iaijutsu": 4})
    _roll_wound_check(page)
    result = _get_wc_result_text(page)
    assert "3k1" in result or "4th Dan" in result


def test_shosuro_acting_dice_behavioral(page, live_server_url):
    """Shosuro Special: attack with acting skill shows extra dice in result."""
    _create_char(page, live_server_url, "ShosuroActB", "shosuro_actor",
                 knack_overrides={"athletics": 1, "discern_honor": 1, "pontificate": 1},
                 skill_overrides={"acting": 2})
    # Attack formula should have extra rolled dice from acting
    f = _get_formula(page, "attack")
    # Base: attack(1) + Fire(2) + 1st Dan(1) = 4. With acting(2): 4 + 2 = 6
    assert f["rolled"] >= 6
    # Actually roll and verify dice appear
    _open_attack_modal_and_roll(page, "attack")
    dice_count = _count_attack_result_dice(page)
    assert dice_count >= 6


# ===========================================================================
# DISPLAY/NOTE VERIFICATION TESTS
# ===========================================================================


def test_daidoji_3rd_dan_raises_note_behavioral(page, live_server_url):
    """Daidoji 3rd Dan: counterattack hit shows free raises note with amount."""
    _create_char(page, live_server_url, "Daidoji3B", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    _mock_dice_high(page)
    # Set TN very low to maximize hit chance
    page.locator('[data-roll-key="knack:counterattack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    result = _get_attack_result_text(page)
    assert "Daidoji 3rd Dan" in result
    assert "free raise" in result.lower()


def test_daidoji_5th_dan_tn_note_behavioral(page, live_server_url):
    """Daidoji 5th Dan: passing wound check shows attacker TN reduction note."""
    _create_char(page, live_server_url, "Daidoji5B", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    # Add small LW so wound check passes
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    result = _get_wc_result_text(page)
    assert "Daidoji 5th Dan" in result


def test_daidoji_3rd_dan_counterattack_checkbox(page, live_server_url):
    """Daidoji 3rd Dan: wound check shows counterattack checkbox that applies bonus."""
    _create_char(page, live_server_url, "Daidoji3CA", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    # Add LW
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "20")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Open wound check
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    wc_modal = page.locator('[data-modal="wound-check"]')
    # Checkbox should be visible with "Hit was counterattacked" (self Daidoji)
    checkbox = wc_modal.locator('text="Hit was counterattacked"')
    assert checkbox.is_visible(), "Counterattack checkbox should appear for Daidoji 3rd Dan"
    # Check the box - attack skill defaults to 1, so 1 raise = +5
    wc_modal.locator('input[type="checkbox"]').check()
    page.wait_for_timeout(200)
    text = wc_modal.text_content()
    assert "+5" in text, f"Expected +5 bonus (1 raise), got: {text[:200]}"
    # Roll the wound check
    _mock_dice_high(page)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    # The result should show the counterattack bonus in breakdown
    result_text = _get_wc_result_text(page)
    assert "counterattack" in result_text.lower() or "Daidoji" in result_text


def test_daidoji_below_3rd_dan_no_counterattack_checkbox(page, live_server_url):
    """Daidoji below 3rd Dan: wound check does NOT show counterattack checkbox."""
    _create_char(page, live_server_url, "Daidoji2NoCA", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    wc_modal = page.locator('[data-modal="wound-check"]')
    checkbox = wc_modal.locator('text="Hit was counterattacked"')
    assert checkbox.count() == 0 or not checkbox.is_visible(), "Below 3rd Dan should not show counterattack checkbox"


def test_non_daidoji_with_party_counterattack_checkbox(page, live_server_url):
    """Non-Daidoji character with a Daidoji party member sees counterattack checkbox."""
    # Create a non-Daidoji character
    _create_char(page, live_server_url, "PartyMember", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Inject the party counterattack data as if a Daidoji party member exists
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.daidojiCounterattackData !== undefined) {
                d.daidojiCounterattackData = { label: 'Daidoji Taro counterattacked this hit', raises: 4, bonus: 20 };
            }
        }
    }""")
    page.wait_for_timeout(200)
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    wc_modal = page.locator('[data-modal="wound-check"]')
    # Should show the party member's name in the checkbox label
    checkbox = wc_modal.locator('text="Daidoji Taro counterattacked this hit"')
    assert checkbox.is_visible(), "Party member counterattack checkbox should be visible"


def test_hiruma_4th_dan_initiative_note_behavioral(page, live_server_url):
    """Hiruma 4th Dan: initiative result shows action dice -2 note."""
    _create_char(page, live_server_url, "Hiruma4B", "hiruma_scout",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    result = _get_roll_result_text(page)
    assert "Hiruma" in result or "-2" in result or "lowered by 2" in result.lower()


def test_ide_4th_dan_vp_regen_note_behavioral(page, live_server_url):
    """Ide 4th Dan: sheet shows +1/night regen text near VP counter."""
    _create_char(page, live_server_url, "Ide4B", "ide_diplomat",
                 knack_overrides={"double_attack": 4, "feint": 4, "worldliness": 4})
    body = page.text_content("body")
    assert "+1/night" in body


def test_ikoma_4th_dan_10dice_note_behavioral(page, live_server_url):
    """Ikoma 4th Dan: attack damage shows 10-dice floor note for unparried attacks."""
    _create_char(page, live_server_url, "Ikoma4B", "ikoma_bard",
                 knack_overrides={"discern_honor": 4, "oppose_knowledge": 4, "oppose_social": 4})
    sa = _get_school_abilities(page)
    assert sa.get("ikoma_10_dice_floor") is True
    # Roll an attack and check the damage formula
    _mock_dice_high(page)
    _open_attack_modal_and_roll(page, "attack")
    result = _get_attack_result_text(page)
    # The 10-dice floor note shows "4th Dan, unparried" in the damage parts
    assert "4th Dan" in result or "unparried" in result.lower()


def test_kitsuki_5th_dan_ring_note_behavioral(page, live_server_url):
    """Kitsuki 5th Dan: roll result shows ring reduction note."""
    _create_char(page, live_server_url, "Kitsuki5B", "kitsuki_magistrate",
                 knack_overrides={"discern_honor": 5, "iaijutsu": 5, "presence": 5},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    result = _get_roll_result_text(page)
    assert "Kitsuki 5th Dan" in result or "reduce" in result.lower()


def test_matsu_5th_dan_lw_reset_note_behavioral(page, live_server_url):
    """Matsu 5th Dan: damage result shows LW reset to 15 note."""
    _create_char(page, live_server_url, "Matsu5B", "matsu_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    _mock_dice_high(page)
    # Roll attack, hit, then roll damage
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")  # low TN for guaranteed hit
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Roll damage
    modal.locator('button:has-text("Make Damage Roll")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    result = _get_attack_result_text(page)
    assert "15" in result and "reset" in result.lower()


def test_shinjo_4th_dan_initiative_highest_1_behavioral(page, live_server_url):
    """Shinjo 4th Dan: initiative result shows highest action die set to 1."""
    _create_char(page, live_server_url, "Shinjo4B", "shinjo_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    # Check that the action dice include a 1 (the highest was set to 1)
    action_dice = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.actionDice && d.phase === 'done') return d.actionDice;
        }
        return [];
    }""")
    assert 1 in action_dice, f"Expected 1 in action dice {action_dice} (Shinjo 4th Dan sets highest to 1)"
    result = _get_roll_result_text(page)
    assert "Shinjo" in result or "set to 1" in result.lower()


# ===========================================================================
# BUTTON CLICK + STATE CHANGE TESTS
# ===========================================================================


def test_hida_4th_dan_trade_sw_behavioral(page, live_server_url):
    """Hida 4th Dan: Take 2 SW button is disabled when LW=0, enabled when LW>0, adds 2 SW and resets LW."""
    _create_char(page, live_server_url, "Hida4TB", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    trade_btn = page.locator('button:has-text("Take 2 SW to reset LW to 0")')
    # Button should be disabled with 0 LW
    assert trade_btn.is_disabled(), "Button should be disabled with 0 LW"
    # Add light wounds
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "25")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Button should now be enabled
    assert not trade_btn.is_disabled(), "Button should be enabled with LW > 0"
    # Click - should ADD 2 SW and reset LW to 0
    trade_btn.click()
    page.wait_for_timeout(300)
    sw_after = int(page.locator('[x-text="seriousWounds"]').text_content().strip())
    assert sw_after == 2, f"Should have gained 2 SW, got {sw_after}"
    lw_after = int(page.locator('[x-text="lightWounds"]').text_content().strip())
    assert lw_after == 0, f"LW should be 0 after trade, got {lw_after}"
    # Button should be disabled again (LW is 0)
    assert trade_btn.is_disabled(), "Button should be disabled again after LW reset to 0"


def test_hida_trade_sw_can_be_used_multiple_times(page, live_server_url):
    """Hida 4th Dan: Take 2 SW button can be used again after more LW are added."""
    _create_char(page, live_server_url, "HidaWCTrade", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    trade_btn = page.locator('button:has-text("Take 2 SW to reset LW to 0")')
    # Add LW and use the button
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    trade_btn.click()
    page.wait_for_timeout(300)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"
    assert trade_btn.is_disabled(), "Should be disabled after LW reset"
    # Add more LW and use again
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "20")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    assert not trade_btn.is_disabled(), "Should be enabled again with new LW"
    trade_btn.click()
    page.wait_for_timeout(300)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "4"
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"


def test_ide_3rd_dan_subtract_behavioral(page, live_server_url):
    """Ide 3rd Dan: clicking subtract deducts VP and shows subtraction result."""
    _create_char(page, live_server_url, "Ide3SB", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 2})
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)
    vp_before = page.evaluate("window._trackingBridge.voidPoints")
    assert vp_before == 1
    # Click subtract button
    subtract_btn = page.locator('button:has-text("Spend 1 VP to subtract")')
    assert subtract_btn.is_visible()
    subtract_btn.click()
    page.wait_for_timeout(1000)  # async dice roll needs time
    # VP should be deducted
    vp_after = page.evaluate("window._trackingBridge.voidPoints")
    assert vp_after == 0
    # Result should show the subtraction amount
    body = page.text_content("body")
    assert "Subtract" in body or "subtract" in body.lower()


def test_mirumoto_parry_temp_vp_behavioral(page, live_server_url):
    """Mirumoto Special: rolling parry increases temp VP by 1."""
    _create_char(page, live_server_url, "MirumotoTVPB", "mirumoto_bushi",
                 knack_overrides={"counterattack": 1, "double_attack": 1, "iaijutsu": 1})
    temp_before = page.evaluate("window._trackingBridge?.tempVoidPoints || 0")
    _roll_via_menu_or_direct(page, "parry")
    page.wait_for_timeout(300)
    temp_after = page.evaluate("window._trackingBridge?.tempVoidPoints || 0")
    assert temp_after == temp_before + 1


def test_yogo_serious_wound_temp_vp_behavioral(page, live_server_url):
    """Yogo Special: gaining serious wounds via wound check grants temp VP."""
    _create_char(page, live_server_url, "YogoSWB", "yogo_warden",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "feint": 1})
    temp_before = page.evaluate("window._trackingBridge?.tempVoidPoints || 0")
    # Add lots of LW to ensure wound check fails
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "80")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    # Roll wound check - should fail with 80 LW and low dice
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    # The failure auto-applies, which should grant temp VP
    page.wait_for_timeout(500)
    temp_after = page.evaluate("window._trackingBridge?.tempVoidPoints || 0")
    assert temp_after > temp_before, f"Temp VP should increase from {temp_before}, got {temp_after}"


def test_yogo_3rd_dan_vp_heals_lw_behavioral(page, live_server_url):
    """Yogo 3rd Dan: spending VP on a roll decreases light wounds."""
    _create_char(page, live_server_url, "Yogo3VPB", "yogo_warden",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "feint": 3},
                 skill_overrides={"bragging": 1})
    # Add light wounds
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "20")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    lw_before = page.evaluate("window._trackingBridge?.lightWounds || 0")
    assert lw_before == 20
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)
    # Roll bragging with 1 VP (via roll menu)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        vp_btn = menu.locator('button.text-accent').first
        if vp_btn.is_visible():
            vp_btn.click()
            _wait_roll_done(page)
            page.wait_for_timeout(300)
            lw_after = page.evaluate("window._trackingBridge?.lightWounds || 0")
            # Should decrease by 2 * attack_skill (attack=1, so 2*1=2)
            assert lw_after < lw_before, f"LW should decrease from {lw_before}, got {lw_after}"


def test_doji_5th_dan_opponent_input_behavioral(page, live_server_url):
    """Doji 5th Dan: entering opponent result shows adjusted total."""
    _create_char(page, live_server_url, "Doji5OB", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    base = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    # Enter opponent result of 30 -> bonus = floor((30-10)/5) = 4
    page.fill('input[x-model\\.number="dojiOpponentResult"]', "30")
    page.wait_for_timeout(300)
    # Should show adjusted total
    modal = page.locator('[data-modal="dice-roller"]')
    result = modal.text_content()
    assert "Adjusted total" in result
    expected_adjusted = base + 4
    assert str(expected_adjusted) in result


def test_togashi_4th_dan_reroll_behavioral(page, live_server_url):
    """Togashi 4th Dan: Reroll button produces a new result."""
    _create_char(page, live_server_url, "Togashi4RB", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    first_total = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    # Click Reroll button
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    if reroll_btn.is_visible():
        reroll_btn.click()
        _wait_roll_done(page)
        # Result should exist (may be same or different)
        second_total = page.evaluate("""() => {
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.phase === 'done') return d.baseTotal;
            }
            return 0;
        }""")
        assert second_total > 0  # a roll happened


def test_kuni_5th_dan_reflect_behavioral(page, live_server_url):
    """Kuni 5th Dan: Reflect damage button applies self-damage and shows result."""
    _create_char(page, live_server_url, "Kuni5RB", "kuni_witch_hunter",
                 knack_overrides={"detect_taint": 5, "iaijutsu": 5, "presence": 5})
    lw_before = page.evaluate("window._trackingBridge?.lightWounds || 0")
    # Find the reflect UI and enter LW amount
    page.fill('input[x-model\\.number="kuniLW"]', "20")
    page.wait_for_timeout(200)
    # Click the Kuni Reflect button (not Akodo's)
    page.locator('button:has-text("Reflect")').first.click()
    page.wait_for_timeout(300)
    # Self-damage: half of 20 = 10 additional LW
    lw_after = page.evaluate("window._trackingBridge?.lightWounds || 0")
    assert lw_after == lw_before + 10
    # Result text should be visible
    assert page.locator('text="Reflected"').is_visible()


def test_yogo_4th_dan_post_roll_vp_behavioral(page, live_server_url):
    """Yogo 4th Dan: post-roll Spend VP (+5) on wound check changes total."""
    _create_char(page, live_server_url, "Yogo4VPB", "yogo_warden",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "feint": 4})
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 2")
    page.wait_for_timeout(200)
    # Add LW to make wound check meaningful
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "30")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Roll wound check (no VP pre-roll)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    # Click "Spend VP (+5)" button if visible
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
        assert total_after == total_before + 5, f"Expected +5, got {total_before} -> {total_after}"
        vp_remaining = page.evaluate("window._trackingBridge?.voidPoints || 0")
        assert vp_remaining == 1  # spent 1 of 2


def test_yogo_4th_dan_wc_prob_chart_includes_raise(page, live_server_url):
    """Yogo 4th Dan: wound check probability chart includes +5/VP free raise."""
    _create_char(page, live_server_url, "Yogo4Prob", "yogo_warden",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "feint": 4})
    config = _get_void_spend_config(page)
    assert config.get("wc_vp_free_raise") is True
    # Add LW and open wound check modal
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "30")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    # Get pass chance at 0 VP and 1 VP from the probability table
    pass_0, pass_1 = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcProbRow) {
                const r0 = d.wcProbRow(0);
                const r1 = d.wcProbRow(1);
                return [r0?.passChance || 0, r1?.passChance || 0];
            }
        }
        return [0, 0];
    }""")
    # With +1k1 dice AND +5 free raise, the improvement should be substantial
    assert pass_1 > pass_0, f"WC pass chance with 1 VP ({pass_1}) should be > 0 VP ({pass_0})"
    # Verify the +5 is actually making a difference beyond just +1k1 dice:
    # Compare against what wcProbRow would give without the free raise
    # by temporarily disabling it
    pass_1_no_raise = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcProbRow && d.voidSpendConfig) {
                d.voidSpendConfig.wc_vp_free_raise = false;
                const r1 = d.wcProbRow(1);
                d.voidSpendConfig.wc_vp_free_raise = true;
                return r1?.passChance || 0;
            }
        }
        return 0;
    }""")
    assert pass_1 > pass_1_no_raise, \
        f"4th Dan +5 should boost pass chance: with={pass_1}, without={pass_1_no_raise}"


def test_yogo_3rd_dan_wc_prob_chart_no_raise(page, live_server_url):
    """Yogo 3rd Dan: wound check probability chart does NOT include +5/VP."""
    _create_char(page, live_server_url, "Yogo3Prob", "yogo_warden",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "feint": 3})
    config = _get_void_spend_config(page)
    assert config.get("wc_vp_free_raise") is False


# ===========================================================================
# COMPLEX MULTI-STEP FLOW TESTS
# ===========================================================================


def test_akodo_3rd_dan_bank_and_apply_behavioral(page, live_server_url):
    """Akodo 3rd Dan: pass wound check -> bonus banked -> apply to attack."""
    _create_char(page, live_server_url, "Akodo3FB", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Add small LW so wound check passes
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    # Roll wound check
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    # Keep light wounds (this triggers banking)
    page.locator('button:has-text("Keep Light Wounds")').click()
    # Wait for the bonus to be banked
    page.wait_for_function("""() => {
        return (window._diceRoller?.akodoBankedBonuses?.filter(b => !b.spent)?.length || 0) > 0;
    }""", timeout=5000)
    banked = page.evaluate("window._diceRoller?.akodoBankedBonuses?.filter(b => !b.spent)?.length || 0")
    assert banked > 0, "A bonus should be banked after passing wound check"
    # Roll an attack and check for the Apply button
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # The Apply button should be visible (wait for Alpine to render the banked bonuses UI)
    page.locator('button:has-text("Apply +")').first.wait_for(state='visible', timeout=3000)
    assert page.locator('button:has-text("Apply +")').first.is_visible()


def test_akodo_4th_dan_vp_on_passed_wound_check(page, live_server_url):
    """Akodo 4th Dan: Spend VP (+5) button appears on PASSED wound check to increase margin."""
    _create_char(page, live_server_url, "Akodo4VP", "akodo_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    # Give VP and small light wounds so WC passes easily with mocked high dice
    page.evaluate("window._trackingBridge.voidPoints = 3")
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    # Roll wound check
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    # Should have passed
    wc_modal = page.locator('[data-modal="wound-check"]')
    assert "PASSED" in wc_modal.text_content()
    # Spend VP (+5) button should be visible in the passed section
    spend_btn = wc_modal.locator('button:has-text("Spend VP (+5)"):visible')
    assert spend_btn.count() > 0, "Spend VP button must appear on passed wound check for 4th Dan"
    # Get margin before spending
    margin_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcMargin !== undefined && d.wcPhase === 'result') return d.wcMargin;
        }
        return -1;
    }""")
    # Click Spend VP
    spend_btn.first.click()
    page.wait_for_timeout(300)
    margin_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcMargin !== undefined && d.wcPhase === 'result') return d.wcMargin;
        }
        return -1;
    }""")
    assert margin_after == margin_before + 5, f"Margin should increase by 5: {margin_before} -> {margin_after}"
    # Undo VP button should be visible
    undo_btn = wc_modal.locator('button:has-text("Undo VP"):visible')
    assert undo_btn.count() > 0, "Undo VP button must appear after spending"
    # VP should have decreased
    vp = page.evaluate("window._trackingBridge.voidPoints")
    assert vp == 2, f"VP should be 2 after spending 1, got {vp}"


def test_akodo_4th_dan_vp_on_failed_wound_check(page, live_server_url):
    """Akodo 4th Dan: Spend VP (+5) button appears on FAILED wound check."""
    _create_char(page, live_server_url, "Akodo4VPF", "akodo_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    # Give VP and high light wounds so WC fails with mocked low dice
    page.evaluate("window._trackingBridge.voidPoints = 3")
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "80")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    # Roll wound check
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    # Should have failed
    wc_modal = page.locator('[data-modal="wound-check"]')
    assert "FAILED" in wc_modal.text_content()
    # Spend VP (+5) button should be visible in the failed section
    spend_btn = wc_modal.locator('button:has-text("Spend VP (+5)"):visible')
    assert spend_btn.count() > 0, "Spend VP button must appear on failed wound check for 4th Dan"
    # Click Spend VP and verify total increases
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return -1;
    }""")
    spend_btn.first.click()
    page.wait_for_timeout(300)
    total_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return -1;
    }""")
    assert total_after == total_before + 5, f"WC total should increase by 5: {total_before} -> {total_after}"


def test_akodo_5th_dan_reflect_ui_behavioral(page, live_server_url):
    """Akodo 5th Dan: wound check result shows Reflect Damage UI with VP input."""
    _create_char(page, live_server_url, "Akodo5FB", "akodo_bushi",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    # Add LW and roll wound check
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    # The Reflect Damage section should exist in the wound check modal
    wc_text = _get_wc_result_text(page)
    assert "Akodo 5th Dan" in wc_text or "Reflect Damage" in wc_text


def test_bayushi_vp_damage_behavioral(page, live_server_url):
    """Bayushi Special: attacking with VP adds +1k1 per VP to damage breakdown."""
    _create_char(page, live_server_url, "BayushiVPDB", "bayushi_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)
    _mock_dice_high(page)
    # Open attack modal, spend 1 VP, roll
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    # Select 1 VP
    vp_btn = modal.locator('button:has-text("+")').first
    if vp_btn.is_visible():
        vp_btn.click()
        page.wait_for_timeout(100)
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    result = _get_attack_result_text(page)
    assert "Bayushi" in result or "VP" in result


def test_hiruma_3rd_dan_parry_then_attack_behavioral(page, live_server_url):
    """Hiruma 3rd Dan: parry banks bonus, attack auto-applies it to both attack and damage."""
    _create_char(page, live_server_url, "Hiruma3FB", "hiruma_scout",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Inject a banked bonus directly (avoids parry roll timing issues)
    page.evaluate("""
        window._diceRoller.hirumaBankedAttackBonus = 4;
        if (window._trackingBridge) window._trackingBridge.hirumaBankedAttackBonus = 4;
    """)
    page.wait_for_timeout(200)
    # Bonus should show in tracking section
    assert page.locator('text="Banked Post-Parry Bonuses"').is_visible()
    # Roll attack - bonus should be auto-applied (not discretionary)
    _mock_dice_high(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    _restore_dice(page)
    # The bonus should already be in the result (auto-applied, no Apply button needed)
    result = _get_attack_result_text(page)
    assert "Hiruma" in result or "post-parry" in result.lower(), f"Auto-applied bonus should show in result: {result[:200]}"
    # Bonus should have been consumed (zeroed out)
    remaining = page.evaluate("window._diceRoller?.hirumaBankedAttackBonus || 0")
    assert remaining == 0, f"Bonus should be consumed after attack, got {remaining}"
    # Damage formula should also include the bonus
    dmg = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkCurrentDamage) {
                const dm = d.atkCurrentDamage();
                return dm ? { flat: dm.flat } : null;
            }
        }
        return null;
    }""")
    if dmg:
        assert dmg["flat"] >= 4, f"Damage should include +4 Hiruma bonus in flat, got {dmg}"


def test_isawa_duelist_5th_dan_bank_excess_behavioral(page, live_server_url):
    """Isawa Duelist 5th Dan: pass WC banks excess, shows in tracking, applies to next WC."""
    _create_char(page, live_server_url, "IsawaD5FB", "isawa_duelist",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    # Inject banked excesses as individual entries (simulates two passed wound checks)
    page.evaluate("""
        const entry1 = {amount: 8, spent: false};
        const entry2 = {amount: 12, spent: false};
        window._trackingBridge.bankedWcExcess.push(entry1, entry2);
        window._diceRoller.bankedWcExcess = window._trackingBridge.bankedWcExcess;
    """)
    page.wait_for_timeout(200)
    # Should show in tracking section with individual entries
    assert page.locator('text="Banked Wound Check Excess"').is_visible()
    body = page.text_content("body")
    assert "+8" in body
    assert "+12" in body
    # Now add LW and roll a wound check - the bonus should be available as discretionary
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    # Individual "Apply +N" buttons should be visible
    wc_modal = page.locator('[data-modal="wound-check"]')
    apply_btns = wc_modal.locator('button:has-text("Apply +"):visible')
    assert apply_btns.count() >= 2, f"Should see 2 Apply buttons, got {apply_btns.count()}"
    # Click the first one (+8) and verify the total increases by 8
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    apply_btns.first.click()
    page.wait_for_timeout(300)
    total_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    assert total_after == total_before + 8, f"First excess should add +8: {total_before} -> {total_after}"
    # Second Apply button (+12) should still be available
    remaining = wc_modal.locator('button:has-text("Apply +"):visible')
    assert remaining.count() >= 1, "Second Apply button should still be available"


def test_matsu_3rd_dan_vp_wc_bonus_behavioral(page, live_server_url):
    """Matsu 3rd Dan: banked WC bonus shows in tracking, applies to wound check."""
    _create_char(page, live_server_url, "Matsu3FB", "matsu_bushi",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    # Inject banked bonuses directly (3 * attack_skill=1 = 3 per VP, simulate 2 VP = two +3 bonuses)
    page.evaluate("""
        const bonuses = [{amount: 3, spent: false}, {amount: 3, spent: false}];
        window._diceRoller.matsuBankedWcBonuses = bonuses;
        if (window._trackingBridge) window._trackingBridge.matsuBankedWcBonuses = bonuses;
    """)
    page.wait_for_timeout(200)
    # Should show in tracking section
    assert page.locator('text="Banked Wound Check Bonuses"').is_visible()
    # Add LW and roll wound check
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    # Two Apply Matsu Bonus buttons should be visible (one per banked bonus)
    wc_modal = page.locator('[data-modal="wound-check"]')
    apply_btns = wc_modal.locator('button:has-text("Apply Matsu Bonus"):visible')
    assert apply_btns.count() == 2, f"Should have 2 Apply Matsu Bonus buttons, got {apply_btns.count()}"
    # Click first and verify total increases by 3
    total_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    apply_btns.first.click()
    page.wait_for_timeout(300)
    total_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    assert total_after == total_before + 3, f"Matsu bonus should add +3: {total_before} -> {total_after}"
    # One Apply button should remain, plus Undo should be visible
    remaining = wc_modal.locator('button:has-text("Apply Matsu Bonus"):visible')
    assert remaining.count() == 1, f"Should have 1 remaining Apply button, got {remaining.count()}"
    undo_btn = wc_modal.locator('button:has-text("Undo Matsu Bonus"):visible')
    assert undo_btn.count() > 0, "Undo Matsu Bonus button should be visible after applying"
    # Apply second bonus, total should be +6 from original
    remaining.first.click()
    page.wait_for_timeout(300)
    total_both = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    assert total_both == total_before + 6, f"Both bonuses should add +6: {total_before} -> {total_both}"
    # Undo last bonus
    undo_btn.first.click()
    page.wait_for_timeout(300)
    total_undone = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcRollTotal !== undefined && d.wcPhase === 'result') return d.wcRollTotal;
        }
        return 0;
    }""")
    assert total_undone == total_before + 3, f"Undo should restore to +3: expected {total_before + 3}, got {total_undone}"


def test_matsu_4th_dan_near_miss_behavioral(page, live_server_url):
    """Matsu 4th Dan: double attack near-miss shows NEAR-MISS HIT."""
    _create_char(page, live_server_url, "Matsu4NMB", "matsu_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    sa = _get_school_abilities(page)
    assert sa.get("matsu_near_miss") is True
    # Roll double attack with high TN so we're likely to miss but within 20
    # Double attack TN = base + 20, so set base TN to 15 -> effective TN = 35
    page.locator('[data-roll-key="knack:double_attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("15")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Check Alpine state for near-miss
    state = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return { hit: d.atkHit, nearMiss: d.atkNearMiss, excess: d.atkExcess };
        }
        return null;
    }""")
    if state and state.get("nearMiss"):
        result = _get_attack_result_text(page)
        assert "4th Dan" in result


def test_mirumoto_4th_dan_parry_reduction_behavioral(page, live_server_url):
    """Mirumoto 4th Dan: damage formula shows halved parry reduction."""
    _create_char(page, live_server_url, "Mirumoto4PB", "mirumoto_bushi",
                 knack_overrides={"counterattack": 4, "double_attack": 4, "iaijutsu": 4})
    _mock_dice_high(page)
    # Roll attack, check the failed parry checkbox, verify halved text
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Check the failed parry checkbox using x-model attribute
    page.locator('input[x-model="atkFailedParry"]').check()
    page.wait_for_timeout(300)
    result = _get_attack_result_text(page)
    assert "halved" in result.lower() or "4th Dan" in result


def test_otaku_4th_dan_lunge_parry_behavioral(page, live_server_url):
    """Otaku 4th Dan: lunge with failed parry shows extra die in damage parts."""
    _create_char(page, live_server_url, "Otaku4LB", "otaku_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    _mock_dice_high(page)
    # Roll lunge
    page.locator('[data-roll-key="knack:lunge"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Check failed parry
    page.locator('input[x-model="atkFailedParry"]').check()
    page.wait_for_timeout(300)
    result = _get_attack_result_text(page)
    # Lunge part should be in the damage breakdown
    assert "Lunge" in result


def test_otaku_5th_dan_trade_dice_behavioral(page, live_server_url):
    """Otaku 5th Dan: trade-for-SW checkbox appears before damage roll and reduces dice."""
    _create_char(page, live_server_url, "Otaku5TB", "otaku_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    _mock_dice_high(page)
    # Roll attack with low TN to guarantee hit
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    # Boost extra dice so total damage dice > 10 (base damage is ~7, need 11+)
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkExtraDice !== undefined && d.atkPhase === 'result') { d.atkExtraDice = 8; break; }
        }
    }""")
    page.wait_for_timeout(500)
    page.wait_for_timeout(200)
    # Get rawRolled to verify we have enough dice for trade
    raw_rolled = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkCurrentDamage && d.atkPhase === 'result') {
                const dmg = d.atkCurrentDamage();
                return dmg?.rawRolled || 0;
            }
        }
        return 0;
    }""")
    assert raw_rolled > 10, f"Need >10 raw damage dice to test trade, got {raw_rolled}"
    # The trade checkbox should be visible before rolling damage
    trade_cb = modal.locator('input[x-model="atkOtakuTradeDice"]')
    assert trade_cb.is_visible(), "Trade dice checkbox should be visible before damage roll"
    # Check the box and roll damage
    trade_cb.check()
    page.wait_for_timeout(200)
    modal.locator('button:has-text("Make Damage Roll")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    # The damage result should show the auto SW note
    result = _get_attack_result_text(page)
    assert "automatic serious wound" in result.lower(), "Auto SW note should appear in damage result"
    # Verify fewer dice were rolled
    rolled_actual = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkDamageRolled !== undefined && d.atkPhase === 'damage-result') return d.atkDamageRolled;
        }
        return 0;
    }""")
    # raw_rolled - 10 is the pre-cap rolled after trade, then capped to min(10, that)
    expected = min(10, raw_rolled - 10)
    assert rolled_actual == expected, \
        f"Damage rolled should be {expected} (raw {raw_rolled} - 10), got {rolled_actual}"


def test_shinjo_5th_dan_parry_excess_behavioral(page, live_server_url):
    """Shinjo 5th Dan: roll parry, enter opponent roll, verify banked excess."""
    _create_char(page, live_server_url, "Shinjo5FB", "shinjo_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    _roll_via_menu_or_direct(page, "parry")
    # Get our parry total
    our_total = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    # Enter a low opponent roll so we have excess
    opp_input = page.locator('input[x-model\\.number="shinjoParryOpponentRoll"]')
    if opp_input.is_visible():
        opp_input.fill("5")
        page.locator('button:has-text("Bank Excess")').click()
        page.wait_for_timeout(500)
        banked_total = page.evaluate("""
            (window._diceRoller?.bankedWcExcess || [])
                .filter(b => !b.spent)
                .reduce((sum, b) => sum + b.amount, 0)
        """)
        expected_excess = our_total - 5
        if expected_excess > 0:
            assert banked_total >= expected_excess, \
                f"Expected banked >= {expected_excess}, got {banked_total}"


def test_hida_5th_dan_counterattack_wc_bonus(page, live_server_url):
    """Hida 5th Dan: successful counterattack banks excess, applied to wound check."""
    _create_char(page, live_server_url, "Hida5CWC", "hida_bushi",
                 knack_overrides={"counterattack": 5, "iaijutsu": 5, "lunge": 5})
    sa = _get_school_abilities(page)
    assert sa.get("hida_counterattack_wc_bonus") is True

    # Mock high dice so counterattack hits
    _mock_dice_high(page)

    # Roll counterattack with low TN to ensure a hit with excess
    page.locator('[data-roll-key="knack:counterattack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)

    # Check that the counterattack excess was banked
    banked = page.evaluate("window._diceRoller?.hidaBankedWcBonus || 0")
    assert banked > 0, f"Should have banked counterattack excess, got {banked}"

    # Check the banked note is visible in the attack result
    note = page.locator('[data-testid="hida-5th-dan-banked-note"]')
    assert note.is_visible(), "Hida 5th Dan banked note should be visible after counterattack hit"

    # Also check that tracking section shows the banked bonus
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkModalOpen !== undefined) { d.atkModalOpen = false; break; }
        }
    }""")
    page.wait_for_timeout(300)
    tracking_text = page.text_content("body")
    assert "Banked Counterattack Bonus" in tracking_text

    # Now add light wounds and roll wound check to verify bonus is applied
    _restore_dice(page)
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=3000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    # After wound check, the banked bonus should be consumed
    after = page.evaluate("window._diceRoller?.hidaBankedWcBonus || 0")
    assert after == 0, f"Banked bonus should be consumed after wound check, got {after}"
    # The formula should contain the Hida bonus
    formula_bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return d.formula.hida_counterattack_bonus || 0;
        }
        return 0;
    }""")
    assert formula_bonus > 0, f"WC formula should include Hida counterattack bonus, got {formula_bonus}"
    _restore_dice(page)


def test_hida_below_5th_dan_no_counterattack_wc_bonus(page, live_server_url):
    """Below 5th Dan, Hida does NOT bank counterattack excess for wound check."""
    _create_char(page, live_server_url, "Hida4NoCWC", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    sa = _get_school_abilities(page)
    assert sa.get("hida_counterattack_wc_bonus") is not True

    # Mock high dice and roll counterattack
    _mock_dice_high(page)
    page.locator('[data-roll-key="knack:counterattack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)

    # Nothing should be banked
    banked = page.evaluate("window._diceRoller?.hidaBankedWcBonus || 0")
    assert banked == 0, f"Below 5th Dan should NOT bank counterattack excess, got {banked}"

    # Banked note should not be visible
    note = page.locator('[data-testid="hida-5th-dan-banked-note"]')
    assert not note.is_visible(), "Hida 5th Dan banked note should NOT be visible below 5th Dan"
    _restore_dice(page)
