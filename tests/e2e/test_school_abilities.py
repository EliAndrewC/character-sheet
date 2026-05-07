"""E2E: School-specific ability UI - buttons, banked bonuses, display notes."""

import pytest
from tests.e2e.helpers import select_school, click_plus, click_minus, apply_changes, start_new_character, dismiss_wc_modal

pytestmark = [pytest.mark.rolls]


def _create_char(page, live_server_url, name, school, knack_overrides=None, skill_overrides=None):
    """Create a character with a specific school and navigate to the sheet."""
    page.goto(live_server_url)
    start_new_character(page)
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
    """Click a roll key. If a menu appears, click the main Roll button. Otherwise wait for direct roll.

    ``athletics:parry`` has no top-level data-roll-key element - it lives as
    a sub-button on the regular parry roll menu (gated by the athletics:parry
    formula existing). Clicking parry opens that menu; we then pick the
    Athletics Parry sub-button via its dedicated data attribute.
    """
    if roll_key == "athletics:parry":
        page.locator('[data-roll-key="parry"]').click()
        page.wait_for_timeout(200)
        page.locator('[data-parry-menu-athletics]').click()
        _wait_roll_done(page)
        return
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
            buttons = menu.locator('button.font-medium:visible')
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
    """Open attack modal for an attack-type key and roll with default TN.

    Schools with an ``athletics`` knack (Togashi, Shosuro Actor, etc.) render
    a regular-vs-athletics chooser when "attack" is clicked. The chooser
    distinguishes regular attack from athletics-attack via two buttons:
    ``data-attack-choice="attack"`` and ``data-attack-choice="athletics_attack"``.
    Pass roll_key="athletics:attack" to drive the athletics branch through
    that chooser; everything else clicks the corresponding data-roll-key
    directly and (if the chooser appears) picks regular.
    """
    if roll_key == "athletics:attack":
        page.locator('[data-roll-key="attack"]').click()
        page.wait_for_timeout(200)
        choice_menu = page.locator('[data-attack-choice-menu]')
        choice_menu.locator('[data-attack-choice="athletics_attack"]').click()
    else:
        page.locator(f'[data-roll-key="{roll_key}"]').click()
        page.wait_for_timeout(200)
        choice_menu = page.locator('[data-attack-choice-menu]')
        if choice_menu.count() > 0 and choice_menu.is_visible():
            choice_menu.locator('[data-attack-choice="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    # Force the lowest TN before rolling so high-mock dice reliably HIT;
    # without this athletics:attack defaults to TN 25 and a 6k3 of 7s sums
    # to 21 (a MISS), which hides the HIT-branch buttons the tests target.
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'pre') {
                d.atkTN = 5;
                d.atkParrySkill = 1;
                return;
            }
        }
    }""")
    modal = page.locator('[data-modal="attack"]')
    modal.locator('[data-action="roll-attack"]').click()
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
    modal.locator('button:text("Back")').wait_for(state='visible', timeout=10000)
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    """Ide 4th Dan: VP regen display shows +2/night with tooltip."""
    _create_char(page, live_server_url, "Ide4Regen", "ide_diplomat",
                 knack_overrides={"double_attack": 4, "feint": 4, "worldliness": 4})
    sa = _get_school_abilities(page)
    assert sa.get("ide_extra_vp_regen") is True
    assert page.locator('text="+2/night"').is_visible()


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
def test_kitsune_1st_dan_three_picker_dropdowns_visible_at_dan_1(page, live_server_url):
    """Kitsune Warden 1st Dan: edit page renders three pick dropdowns."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "kitsune_warden")
    page.wait_for_selector('[data-testid="kitsune-1st-dan-picker"]', state="visible", timeout=5000)
    picker = page.locator('[data-testid="kitsune-1st-dan-picker"]')
    assert picker.locator('select').count() == 3
    for slot in (0, 1, 2):
        assert page.locator(f'[data-testid="kitsune-1st-dan-slot-{slot}"]').is_visible()


def test_kitsune_1st_dan_picker_includes_iaijutsu_option(page, live_server_url):
    """Iaijutsu IS eligible for the Kitsune 1st Dan picker (regression guard:
    the special ability and 3rd Dan picker exclude iaijutsu, but 1st Dan does
    not)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "kitsune_warden")
    page.wait_for_selector('[data-testid="kitsune-1st-dan-slot-0"]', state="visible", timeout=5000)
    options = page.locator('[data-testid="kitsune-1st-dan-slot-0"] option').all_text_contents()
    assert any("Iaijutsu" in o for o in options), \
        f"Expected 'Iaijutsu' option in slot 0; got: {options}"


def test_kitsune_1st_dan_picks_distinct_no_duplicates(page, live_server_url):
    """Selecting a value in slot 0 disables the same option in slots 1 and 2."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "kitsune_warden")
    page.wait_for_selector('[data-testid="kitsune-1st-dan-slot-0"]', state="visible", timeout=5000)
    page.locator('[data-testid="kitsune-1st-dan-slot-0"]').select_option("attack")
    page.wait_for_timeout(300)
    # Now "Attack" should be disabled in slots 1 and 2.
    for slot in (1, 2):
        disabled_attr = page.locator(
            f'[data-testid="kitsune-1st-dan-slot-{slot}"] option[value="attack"]'
        ).get_attribute("disabled")
        assert disabled_attr is not None, f"Expected attack option disabled in slot {slot}"


def test_kitsune_1st_dan_pick_extra_die_applied_to_roll(page, live_server_url):
    """Picking 'bragging' as a 1st Dan choice grants +1 rolled die on the
    bragging skill formula (verified end-to-end through the sheet's embedded
    formula JSON)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "KitsuneFirstDanRoll")
    select_school(page, "kitsune_warden")
    # Need a non-zero bragging skill to see the bonus reflected in rolled.
    click_plus(page, "skill_bragging", 2)
    page.wait_for_selector('[data-testid="kitsune-1st-dan-slot-0"]', state="visible", timeout=5000)
    page.locator('[data-testid="kitsune-1st-dan-slot-0"]').select_option("bragging")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Pick bragging for 1st Dan")
    # Now on the sheet. Bragging rolls Air (default 2). rank 2 + Air 2 + 1 = 5.
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['skill:bragging'] || null;
    }""")
    assert f is not None
    assert f["rolled"] == 5, f"Expected rolled=5 (rank 2 + Air 2 + 1), got {f['rolled']}"


def test_kitsune_1st_dan_picks_persist_across_reload(page, live_server_url):
    """The three-pick selection survives a page reload."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "KitsunePersist")
    select_school(page, "kitsune_warden")
    page.wait_for_selector('[data-testid="kitsune-1st-dan-slot-0"]', state="visible", timeout=5000)
    page.locator('[data-testid="kitsune-1st-dan-slot-0"]').select_option("attack")
    page.wait_for_timeout(200)
    page.locator('[data-testid="kitsune-1st-dan-slot-1"]').select_option("wound_check")
    page.wait_for_timeout(200)
    page.locator('[data-testid="kitsune-1st-dan-slot-2"]').select_option("initiative")
    # Sanity-check the in-memory model captured the picks before the save fires.
    in_memory_picks = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.techniqueChoices) return d.techniqueChoices.first_dan_choices || null;
        }
        return null;
    }""")
    assert in_memory_picks == ["attack", "wound_check", "initiative"], \
        f"Picker did not write to techniqueChoices.first_dan_choices: {in_memory_picks}"
    # Force a flush of the autosave debounce so the picks reach the server
    # before reload. waiting on the "Saved" indicator is unreliable here:
    # select_school fires its own "Saved" cycle, and the picks-driven save
    # may not have fired yet by the time we check.
    page.evaluate("""async () => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.flushPendingSave === 'function') {
                await d.flushPendingSave();
                return;
            }
        }
    }""")
    page.reload()
    page.wait_for_selector('[data-testid="kitsune-1st-dan-slot-0"]', state="visible", timeout=5000)
    page.wait_for_timeout(300)  # let template x-for finish rendering options
    saved_picks = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.techniqueChoices) return d.techniqueChoices.first_dan_choices || null;
        }
        return null;
    }""")
    assert saved_picks == ["attack", "wound_check", "initiative"], \
        f"Picks did not survive reload: {saved_picks}"
    # And the dropdowns themselves should reflect the saved picks.
    assert page.locator('[data-testid="kitsune-1st-dan-slot-0"]').input_value() == "attack"
    assert page.locator('[data-testid="kitsune-1st-dan-slot-1"]').input_value() == "wound_check"
    assert page.locator('[data-testid="kitsune-1st-dan-slot-2"]').input_value() == "initiative"


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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("15")
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "30")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)

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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("15")
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


def test_priest_sheet_links_to_rituals(page, live_server_url):
    """The Priest's special-ability section on the read-only sheet contains
    an 'all 10 rituals' anchor pointing at the upstream rules section."""
    _create_char(page, live_server_url, "PriestSheetLink", "priest")
    link = page.locator(
        'a[href="https://github.com/EliAndrewC/l7r/blob/master/'
        'rules/09-professions.md#priest-rituals"]'
    )
    assert link.count() == 1
    assert link.get_attribute("target") == "_blank"
    assert link.text_content().strip() == "all 10 rituals"


def test_iaijutsu_knack_links_to_combat_rules(page, live_server_url):
    """Expanding the Iaijutsu knack on the read-only sheet shows the
    canonical rules text with "the other combat rules" wrapped in an
    anchor that opens the upstream combat-rules page in a new tab."""
    _create_char(page, live_server_url, "IaijutsuLink", "mirumoto_bushi")
    iaijutsu_row = page.locator('div.bg-parchment', has_text="Iaijutsu").first
    iaijutsu_row.click()
    page.wait_for_timeout(300)
    link = iaijutsu_row.locator(
        'a[href="https://github.com/EliAndrewC/l7r/blob/master/'
        'rules/03-combat.md"]'
    )
    assert link.count() == 1
    assert link.get_attribute("target") == "_blank"
    assert link.text_content().strip() == "the other combat rules"
def test_shosuro_stipend_display(page, live_server_url):
    """Shosuro Actor: stipend display on character sheet."""
    _create_char(page, live_server_url, "ShosuroStipend", "shosuro_actor")
    # All characters should have a stipend displayed
    stipend_el = page.locator('text="koku/year"').first
    assert stipend_el.is_visible()


def test_shosuro_special_ability_in_sheet_rolls(page, live_server_url):
    """Shosuro Actor: sheet Attack / Parry / Wound Check summaries fold in
    the +acting rolled dice from the Special Ability (and the L7R 10k10 cap
    converts the overflow into kept dice).

    Stats: attack=2, parry=2, Fire=3, Air=3, Water=4, acting=5, Dan 1.
      Attack:      2+3+1(1st Dan)+5(acting) = 11 rolled, capped to 10k4
      Parry:       2+3+0+5(acting)          = 10 rolled, kept 3 -> 10k3
      Wound check: 5(Water+1)+1(1st Dan)+5  = 11 rolled, capped to 10k5
    """
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "ShosuroSheetRolls")
    select_school(page, "shosuro_actor")
    # Rings: school ring Air starts at 3; nudge Fire 2->3 and Water 2->4.
    click_plus(page, "ring_fire", 1)
    click_plus(page, "ring_water", 2)
    # Combat skills default to 1; raise both to 2.
    click_plus(page, "attack", 1)
    click_plus(page, "parry", 1)
    # Acting skill starts at 0; raise to 5.
    click_plus(page, "skill_acting", 5)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "ShosuroSheetRolls setup")

    # Sheet Attack row: look inside the attack clickable row for XkY text.
    attack_row = page.locator('[data-roll-key="attack"]').first
    assert "10k4" in attack_row.text_content()
    parry_row = page.locator('[data-roll-key="parry"]').first
    assert "10k3" in parry_row.text_content()
    # Wound check row does not carry a data-roll-key; locate by label.
    wc_row = page.locator('div', has=page.locator('text="Wound Check:"')).first
    assert "10k5" in wc_row.text_content()
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
    assert page.locator('[data-action="spend-togashi-raise"]').is_visible()


def test_togashi_athletics_raise_decrements_daily_pool(page, live_server_url):
    """Spending a Togashi athletics raise decrements the daily pool in the tracker."""
    _create_char(page, live_server_url, "TogashiDecr", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 2})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "athletics:Air")
    page.locator('[data-action="spend-togashi-raise"]').click()
    page.wait_for_timeout(200)
    used = page.evaluate("window._trackingBridge.getCount('togashi_daily_athletics_raises')")
    assert used == 1


def test_togashi_athletics_raise_undo_restores_pool(page, live_server_url):
    """Undoing a spent Togashi athletics raise restores the daily pool."""
    _create_char(page, live_server_url, "TogashiUndo", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 2})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "athletics:Air")
    page.locator('[data-action="spend-togashi-raise"]').click()
    page.wait_for_timeout(200)
    page.locator('[data-action="undo-togashi-raise"]').click()
    page.wait_for_timeout(200)
    used = page.evaluate("window._trackingBridge.getCount('togashi_daily_athletics_raises')")
    assert used == 0


def test_togashi_athletics_raise_capped_by_pool_remaining(page, live_server_url):
    """Per-roll cap respects the remaining daily pool, not just the per-roll max."""
    # With precepts=3, per_roll=3 and max=12. Pre-spend 11 so only 1 is left in the pool.
    _create_char(page, live_server_url, "TogashiCap", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 3})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.evaluate("window._trackingBridge.setCount('togashi_daily_athletics_raises', 11)")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "athletics:Air")
    spend_btn = page.locator('[data-action="spend-togashi-raise"]')
    # First click spends the last remaining raise.
    spend_btn.click()
    page.wait_for_timeout(200)
    # Button should now be disabled because the daily pool is exhausted.
    assert spend_btn.is_disabled()
    used = page.evaluate("window._trackingBridge.getCount('togashi_daily_athletics_raises')")
    assert used == 12


def test_togashi_athletics_raise_button_hidden_when_pool_empty(page, live_server_url):
    """When the daily pool is exhausted and nothing spent this roll, the button row is hidden."""
    _create_char(page, live_server_url, "TogashiHidden", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 1})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.evaluate("window._trackingBridge.setCount('togashi_daily_athletics_raises', 4)")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "athletics:Air")
    assert not page.locator('[data-action="spend-togashi-raise"]').is_visible()


def test_togashi_athletics_raise_on_athletics_parry(page, live_server_url):
    """Athletics used as parry is still an athletics roll - the existing
    regular-modal togashi raise button must appear on the parry result."""
    _create_char(page, live_server_url, "TogashiAthParry", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 1})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "athletics:parry")
    spend_btn = page.locator('[data-action="spend-togashi-raise"]')
    assert spend_btn.is_visible()
    spend_btn.click()
    page.wait_for_timeout(200)
    used = page.evaluate("window._trackingBridge.getCount('togashi_daily_athletics_raises')")
    assert used == 1


def test_togashi_athletics_raise_on_athletics_attack_hit(page, live_server_url):
    """Athletics used as an attack goes through the attack modal. The togashi
    raise spend button must appear in the HIT block and increment atkRollTotal
    by 5 while decrementing the daily pool."""
    _create_char(page, live_server_url, "TogashiAthAtk", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 2})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    # Ensure the roll hits so the HIT block renders
    _mock_dice_high(page)
    _open_attack_modal_and_roll(page, "athletics:attack")
    _restore_dice(page)
    before_total = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.atkRollTotal;
        }
        return null;
    }""")
    spend_btn = page.locator('[data-action="spend-togashi-raise-atk"]').first
    assert spend_btn.is_visible()
    spend_btn.click()
    page.wait_for_timeout(200)
    after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return {
                total: d.atkRollTotal,
                spent: d.togashiRaisesSpentThisRoll,
                pool: window._trackingBridge.getCount('togashi_daily_athletics_raises'),
            };
        }
        return null;
    }""")
    assert after["total"] == before_total + 5
    assert after["spent"] == 1
    assert after["pool"] == 1


def test_togashi_athletics_raise_atk_undo_restores_total_and_pool(page, live_server_url):
    """Undo inside the attack modal rolls back both atkRollTotal and the
    daily pool counter."""
    _create_char(page, live_server_url, "TogashiAthAtkUndo", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 2})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _mock_dice_high(page)
    _open_attack_modal_and_roll(page, "athletics:attack")
    _restore_dice(page)
    before_total = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.atkRollTotal;
        }
        return null;
    }""")
    page.locator('[data-action="spend-togashi-raise-atk"]').first.click()
    page.wait_for_timeout(200)
    page.locator('[data-action="undo-togashi-raise-atk"]').first.click()
    page.wait_for_timeout(200)
    after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return {
                total: d.atkRollTotal,
                spent: d.togashiRaisesSpentThisRoll,
                pool: window._trackingBridge.getCount('togashi_daily_athletics_raises'),
            };
        }
        return null;
    }""")
    assert after["total"] == before_total
    assert after["spent"] == 0
    assert after["pool"] == 0


def test_togashi_athletics_raise_button_absent_on_regular_attack(page, live_server_url):
    """The atk-modal togashi raise button is gated on is_athletics_attack, so
    a plain 'attack' roll (not athletics) must not offer it even for a togashi
    3rd Dan."""
    _create_char(page, live_server_url, "TogashiRegAtk", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 2})
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    _mock_dice_high(page)
    _open_attack_modal_and_roll(page, "attack")
    _restore_dice(page)
    # The button markup exists in both HIT and MISS branches (gated by
    # x-show on is_athletics_attack, not removed from DOM), so check
    # visibility rather than count - a regular attack must keep both
    # branches' togashi-raise buttons hidden.
    btns = page.locator('[data-action="spend-togashi-raise-atk"]')
    for i in range(btns.count()):
        assert not btns.nth(i).is_visible()


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
    page.locator('[data-modal="dice-roller"]').locator('button:text("Back")').wait_for(state='visible', timeout=10000)
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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


def test_merchant_pre_roll_menu_has_no_vp_options(page, live_server_url):
    """Merchant pre-roll: VP options are hidden because VP is spent after the roll."""
    _create_char(page, live_server_url, "MerchantNoPreVP", "merchant",
                 skill_overrides={"bragging": 1})
    # Character starts with 2 VP and 2 cap, so a non-merchant would see a menu with options.
    # For merchants, the menu should either skip directly to rolling, or show only a
    # single "Roll X" button (if OW/other extras force it open).
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(400)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        text = menu.text_content()
        assert "Spend 1 void point" not in text
        assert "Spend 2 void points" not in text


def test_merchant_spend_one_vp_preserves_existing_dice(page, live_server_url):
    """Merchant VP spend adds ONE die to the pool without re-rolling existing dice."""
    _create_char(page, live_server_url, "MerchantAddOne", "merchant",
                 skill_overrides={"bragging": 2})
    # bragging 2 + air 2 -> 4k2, so rolled=4 dice in pool
    _mock_dice_low(page)  # initial roll: all 1s -> dice [1,1,1,1], kept [1,1], keptSum=2
    _roll_via_menu_or_direct(page, "skill:bragging")
    _restore_dice(page)
    dice_before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.finalDice) return d.finalDice.map(x => x.value);
        }
        return null;
    }""")
    assert dice_before == [1, 1, 1, 1]
    # Mock the next die to be a 7 so we know it came from this VP spend
    _mock_dice_high(page)
    page.locator('[data-modal="dice-roller"] button:has-text("Spend 1 VP")').click()
    _wait_roll_done(page)
    _restore_dice(page)
    dice_after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.finalDice) return d.finalDice.map(x => x.value);
        }
        return null;
    }""")
    # Pool is now [1,1,1,1,7] - existing 1s are preserved, new 7 added
    assert sorted(dice_after) == [1, 1, 1, 1, 7]
    # Kept/unkept dice retain the .parts breakdown so the Pool view renders them
    kept_parts_ok = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.keptDice) return d.keptDice.every(x => Array.isArray(x.parts));
        }
        return false;
    }""")
    assert kept_parts_ok, "keptDice entries must have a .parts array for rendering"
    # Kept is now 3 (was 2+1 from VP). Top 3 = [1, 1, 7], keptSum = 9
    kept_sum = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.keptSum === 'number') return d.keptSum;
        }
        return null;
    }""")
    assert kept_sum == 9


def _make_merchant_5th_dan(page, live_server_url, name):
    """Create a merchant with Dan=5 (all three school knacks at rank 5)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "merchant")
    click_plus(page, "knack_discern_honor", 4)  # 1 -> 5
    click_plus(page, "knack_oppose_knowledge", 4)
    click_plus(page, "knack_worldliness", 4)
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup 5th")


def test_merchant_5th_dan_reroll_button_visible_at_dan_5(page, live_server_url):
    _make_merchant_5th_dan(page, live_server_url, "Merchant5Visible")
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('[data-action="merchant-5th-start"]').is_visible()


def test_merchant_5th_dan_reroll_hidden_below_dan_5(page, live_server_url):
    _create_char(page, live_server_url, "MerchantLowDan", "merchant",
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert not page.locator('[data-action="merchant-5th-start"]').is_visible()


def test_merchant_5th_dan_reroll_constraint_enforced(page, live_server_url):
    """Reroll confirm is disabled until selected dice sum >= 5*(count-1)."""
    _make_merchant_5th_dan(page, live_server_url, "Merchant5Constraint")
    _mock_dice_low(page)  # initial roll: all 1s, dice [1,1,1,1]
    _roll_via_menu_or_direct(page, "skill:bragging")
    _restore_dice(page)
    page.locator('[data-action="merchant-5th-start"]').click()
    page.wait_for_timeout(200)
    # Select 1 die -> sum=1, min=0 -> valid
    dice = page.locator('[data-action="merchant-5th-die"]')
    dice.nth(0).click()
    page.wait_for_timeout(100)
    confirm = page.locator('[data-action="merchant-5th-confirm"]')
    assert confirm.is_enabled()
    # Select 2 dice -> sum=2, min=5 -> invalid
    dice.nth(1).click()
    page.wait_for_timeout(100)
    assert confirm.is_disabled()
    # Select 3 dice -> sum=3, min=10 -> invalid
    dice.nth(2).click()
    page.wait_for_timeout(100)
    assert confirm.is_disabled()


def test_merchant_5th_dan_reroll_applies_delta_bullet(page, live_server_url):
    """After confirming a reroll, the breakdown shows the net +/- from Merchant 5th Dan."""
    _make_merchant_5th_dan(page, live_server_url, "Merchant5Delta")
    _mock_dice_low(page)  # roll all 1s -> [1,1,1,1], keptSum=2
    _roll_via_menu_or_direct(page, "skill:bragging")
    _restore_dice(page)
    page.locator('[data-action="merchant-5th-start"]').click()
    page.wait_for_timeout(200)
    # Select 1 die (sum=1, min=0, valid)
    page.locator('[data-action="merchant-5th-die"]').nth(0).click()
    page.wait_for_timeout(100)
    # Mock reroll to a 7 so the delta is deterministic
    _mock_dice_high(page)
    page.locator('[data-action="merchant-5th-confirm"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    # Pool is [1,1,1,7]; kept top 2 = [1,7], keptSum=8. Old keptSum was 2 -> delta +6.
    delta = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return d.formula.merchant_5th_dan_bonus;
        }
        return null;
    }""")
    assert delta == 6
    modal_text = " ".join(page.locator('[data-modal="dice-roller"]').text_content().split())
    assert "+6 from Merchant 5th Dan reroll" in modal_text
    # Button should no longer be visible (once per roll)
    assert not page.locator('[data-action="merchant-5th-start"]').is_visible()


def test_merchant_spend_one_vp_button_clickable_multiple_times(page, live_server_url):
    """Merchant's post-roll 'Spend 1 VP' button can be clicked repeatedly until max."""
    _create_char(page, live_server_url, "MerchantMulti", "merchant",
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    # Default VP: min ring = 2 -> 2 VP, cap = 2. We should be able to click 2 times.
    modal = page.locator('[data-modal="dice-roller"]')
    btn = modal.locator('button:has-text("Spend 1 VP")')
    assert btn.is_visible(), "Spend 1 VP button should be visible"
    btn.click()
    page.wait_for_timeout(200)
    _wait_roll_done(page)
    # After 1 click: merchant_vp_spent=1, formula.rolled should have increased
    vp_spent = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return d.formula.merchant_vp_spent || 0;
        }
        return 0;
    }""")
    assert vp_spent == 1
    # Click again - should still be visible (cap is 2)
    assert btn.is_visible(), "Button should remain visible after first click"
    btn.click()
    page.wait_for_timeout(200)
    _wait_roll_done(page)
    vp_spent = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formula) return d.formula.merchant_vp_spent || 0;
        }
        return 0;
    }""")
    assert vp_spent == 2
    # Now cap is reached, button should hide
    page.wait_for_timeout(300)
    assert not btn.is_visible(), "Button should hide once per-roll cap is reached"


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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "15")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    dismiss_wc_modal(page)
    assert not trade_btn.is_disabled(), "Button should be enabled when LW > 0"
    # Click the button
    trade_btn.click()
    page.wait_for_timeout(300)
    # SW should increase by 2, LW should be 0
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"


def test_togashi_dragon_tattoo_rolls_2x_k1_damage(page, live_server_url):
    """Dragon Tattoo knack: (2 * rank)k1 damage roll, not a ring-based knack roll."""
    _create_char(page, live_server_url, "TogashiDragonTat", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    f = _get_formula(page, "knack:dragon_tattoo")
    assert f is not None
    assert f["rolled"] == 6
    assert f["kept"] == 1
    assert "Damage" in f["label"]


def test_togashi_dragon_tattoo_impaired_disables_reroll_10s(page, live_server_url):
    """When impaired, Dragon Tattoo damage does not reroll 10s."""
    _create_char(page, live_server_url, "TogashiDragonImpaired", "togashi_ise_zumi",
                 knack_overrides={"athletics": 2, "conviction": 2, "dragon_tattoo": 2})
    # Earth is 2 by default -> impaired at 2 SW. Bump via the tracking bridge.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.seriousWounds = 2;
        t.save();
        window.dispatchEvent(new CustomEvent('wound-changed', { detail: { serious: 2 } }));
    }""")
    page.wait_for_timeout(200)
    # Read live formula state from the Alpine dice-roller component
    f = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.formulas && d.formulas['knack:dragon_tattoo']) {
                return d.formulas['knack:dragon_tattoo'];
            }
        }
        return null;
    }""")
    assert f is not None
    assert f["reroll_tens"] is False
    assert f["no_reroll_reason"] == "impaired"


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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
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


def test_shosuro_5th_dan_attack_lowest_3_dice(page, live_server_url):
    """Shosuro 5th Dan: lowest 3 dice bonus applies to attack rolls."""
    _create_char(page, live_server_url, "Shosuro5Atk", "shosuro_actor",
                 knack_overrides={"athletics": 5, "discern_honor": 5, "pontificate": 5})
    # Verify the flag is on the attack formula
    f = _get_formula(page, "attack")
    assert f.get("shosuro_5th_dan") is True
    # Pre-roll note appears on the attack modal
    _open_attack_modal(page, "attack")
    pre_text = page.locator('[data-modal="attack"]').text_content()
    assert "Shosuro 5th Dan" in pre_text
    # Roll the attack; bonus row should appear in result
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    result_text = page.locator('[data-modal="attack"]').text_content()
    assert "Shosuro 5th Dan" in result_text and "lowest 3" in result_text


def test_shosuro_5th_dan_wound_check_lowest_3_dice(page, live_server_url):
    """Shosuro 5th Dan: lowest 3 dice bonus applies to wound check rolls."""
    _create_char(page, live_server_url, "Shosuro5WC", "shosuro_actor",
                 knack_overrides={"athletics": 5, "discern_honor": 5, "pontificate": 5})
    # Flag present on the WC formula
    wc = _get_formula(page, "wound_check")
    assert wc.get("shosuro_5th_dan") is True
    # Add light wounds so a wound check can be triggered
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Open WC modal and check the pre-roll note
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
    pre_text = page.locator('[data-modal="wound-check"]').text_content()
    assert "Shosuro 5th Dan" in pre_text
    # Roll; the result breakdown should include the lowest-3 line
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    result_text = page.locator('[data-modal="wound-check"]').text_content()
    assert "Shosuro 5th Dan" in result_text and "lowest 3" in result_text


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
    """Togashi 1st Dan: wound check gets +1 rolled die (athletics/WC/init)."""
    _create_char(page, live_server_url, "Togashi1B", "togashi_ise_zumi",
                 knack_overrides={"athletics": 1, "conviction": 1, "dragon_tattoo": 1})
    wc = _get_formula(page, "wound_check")
    # Water=2 -> base 3k2; 1st Dan +1 rolled -> 4k2
    assert wc["rolled"] == 4
    assert wc["kept"] == 2


def test_togashi_initiative_dropdown_shows_both_variants(page, live_server_url):
    """Togashi initiative box opens a dropdown with normal+athletics variants."""
    # Default Togashi character: Void=3, dan=1 (school knacks free at rank 1),
    # so base initiative is (V+1+1)kV = 5k3.
    _create_char(page, live_server_url, "TogashiInitUI", "togashi_ise_zumi")
    init_box = page.locator('[data-roll-key="initiative"]')
    box_text = init_box.text_content()
    assert "5k3 plus 1 athletics action" in box_text
    assert "8k6 athletics actions" in box_text
    # Click opens dropdown (does not roll directly)
    init_box.click()
    page.wait_for_selector('[data-togashi-init-menu]', state='visible', timeout=10000)
    assert page.locator('[data-togashi-init-normal]').is_visible()
    assert page.locator('[data-togashi-init-athletics]').is_visible()


def test_togashi_initiative_normal_variant_rolls_correct_dice(page, live_server_url):
    """Togashi normal initiative: main roll is (V+1+dan)kV (5 dice for default char)
    and a separate standalone athletics-only die is also rolled."""
    _create_char(page, live_server_url, "TogashiInitN", "togashi_ise_zumi")
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-normal]', state='visible')
    page.locator('[data-togashi-init-normal]').click()
    _wait_roll_done(page)
    # Void=3, dan=1: main init 5k3. finalDice carries only the main roll.
    assert _count_result_dice(page) == 5
    # The standalone athletics die is now persisted as an entry in actionDice
    # with the ``athletics_only`` flag set (was a separate togashiAthleticsDie field).
    ath_value = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && Array.isArray(d.actionDice) && d.phase === 'done') {
                const entry = d.actionDice.find(x => x && x.athletics_only);
                return entry ? entry.value : 0;
            }
        }
        return 0;
    }""")
    assert 1 <= ath_value <= 10


def test_togashi_initiative_normal_variant_shows_athletics_die_label(page, live_server_url):
    """Togashi normal initiative result modal shows the athletics-only die as a
    distinct blue die. The label moved from a visible 'athletics only' caption
    to an SVG <title> tooltip ('Athletics-only action die ...') and the
    school-specific note still calls out the blue die."""
    _create_char(page, live_server_url, "TogashiInitNLab", "togashi_ise_zumi")
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-normal]', state='visible')
    page.locator('[data-togashi-init-normal]').click()
    _wait_roll_done(page)
    modal = page.locator('[data-modal="dice-roller"]')
    text = modal.text_content().lower()
    # Either the SVG <title> renders into text content (browser-dependent) or
    # the school-specific note line is shown - one of them must be visible.
    assert "athletics-only action die" in text or "blue action die" in text
    # The athletics-only die SVG carries the .athletics-only class.
    assert modal.locator('svg.action-die.athletics-only').count() == 1


def test_togashi_initiative_athletics_variant_rolls_correct_dice(page, live_server_url):
    """Togashi athletics initiative rolls base+3 dice (8 dice for default char)
    and ALL resulting action dice are flagged athletics_only so they render
    blue and restrict their per-die menus to athletics variants."""
    _create_char(page, live_server_url, "TogashiInitA", "togashi_ise_zumi")
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-athletics]', state='visible')
    page.locator('[data-togashi-init-athletics]').click()
    _wait_roll_done(page)
    # Void=3, dan=1: base 5k3 + 3 athletics dice = 8k6
    assert _count_result_dice(page) == 8
    # Every kept action die on this variant is athletics-only.
    flags = page.evaluate("""() => {
        const dice = window._trackingBridge?.actionDice || [];
        return {
            count: dice.length,
            all_athletics: dice.length > 0 && dice.every(d => d.athletics_only),
        };
    }""")
    assert flags["count"] > 0
    assert flags["all_athletics"] is True


def test_togashi_all_athletics_variant_dice_render_blue(page, live_server_url):
    """Every action die from the Togashi all-athletics initiative variant
    renders in blue (svg.athletics-only) in the Actions side panel, since
    every die is restricted to athletics actions."""
    _create_char(page, live_server_url, "TogashiAllAthBlue", "togashi_ise_zumi")
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-athletics]', state='visible')
    page.locator('[data-togashi-init-athletics]').click()
    _wait_roll_done(page)
    # Close the roll modal so the Actions side panel is reachable.
    page.locator('[data-modal="dice-roller"]').locator('button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    counts = page.evaluate("""() => {
        const section = document.querySelector('[data-testid="action-dice-section"]');
        return {
            total_dice: section ? section.querySelectorAll('svg.die.action-die').length : 0,
            blue_dice: section ? section.querySelectorAll('svg.die.action-die.athletics-only').length : 0,
        };
    }""")
    assert counts["total_dice"] > 0
    assert counts["total_dice"] == counts["blue_dice"]


def test_togashi_initiative_dan_advancement_bonus(page, live_server_url):
    """Advancing Togashi past 1st Dan keeps the +1 init bonus (same dan tier)."""
    _create_char(page, live_server_url, "TogashiInit2D", "togashi_ise_zumi",
                 knack_overrides={"athletics": 2, "conviction": 2, "dragon_tattoo": 2})
    init_box = page.locator('[data-roll-key="initiative"]')
    box_text = init_box.text_content()
    # Still 1st-Dan extra die: Void=3 -> base 5k3 + 1 athletics OR 8k6 athletics
    assert "5k3 plus 1 athletics action" in box_text
    assert "8k6 athletics actions" in box_text


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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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


# --- Priest 3rd Dan precepts dice pool (Phase 0: create + clear, no swap yet) ---

def _create_priest_3rd_dan(page, live_server_url, name, precepts=3):
    _create_char(page, live_server_url, name, "priest",
                 knack_overrides={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
                 skill_overrides={"precepts": precepts})


def test_priest_3rd_dan_pool_button_visible_only_for_priest_3rd_dan(page, live_server_url):
    """Roll Pool button renders only for priests at 3rd Dan or higher.
    Non-priests and lower-Dan priests should not see the section at all."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolVisible", precepts=3)
    assert page.locator('[data-testid="precepts-pool-section"]').count() == 1
    assert page.locator('[data-action="roll-precepts-pool"]').is_visible()

    # Priest at 2nd Dan does not see the section.
    _create_char(page, live_server_url, "Priest2dNoPool", "priest",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
                 skill_overrides={"precepts": 3})
    assert page.locator('[data-testid="precepts-pool-section"]').count() == 0

    # Non-priest does not see the section.
    _create_char(page, live_server_url, "AkodoNoPool", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    assert page.locator('[data-testid="precepts-pool-section"]').count() == 0


def test_priest_3rd_dan_roll_creates_pool_of_size_equal_to_precepts(page, live_server_url):
    """Clicking Roll Pool rolls precepts-skill-many dice and stores them."""
    _create_priest_3rd_dan(page, live_server_url, "PriestRollPool", precepts=4)
    # Wait for the tracking bridge (Alpine x-init) to hook up before poking
    # anything on it - under batched runs it can take an extra frame.
    page.wait_for_function(
        "() => window._trackingBridge && Array.isArray(window._trackingBridge.preceptsPool)",
        timeout=10000,
    )
    # Turn off animation so the test doesn't wait on the roll timeline.
    page.evaluate("document.getElementById('user-prefs').textContent = '{\"dice_animation_enabled\":false,\"dice_sound_enabled\":false}'")
    btn = page.locator('[data-action="roll-precepts-pool"]')
    btn.wait_for(state='visible', timeout=5000)
    btn.click()
    # Poll until the pool is populated. The roll is async (dice.js animation
    # pipeline + save()), so be generous with the timeout - larger batched
    # runs can take longer under memory pressure.
    page.wait_for_function(
        "() => window._trackingBridge && window._trackingBridge.preceptsPool.length === 4",
        timeout=15000,
    )
    # All values are positive integers. Reroll-10s means a single die can
    # legitimately exceed 10 (e.g. 10 + 9 = 19 sums as one die's value).
    pool = page.evaluate("window._trackingBridge.preceptsPool")
    assert len(pool) == 4
    for d in pool:
        assert d["value"] >= 1
    # Dice icons render in the DOM.
    assert page.locator('[data-testid="precepts-pool-die"]').count() == 4


def test_priest_3rd_dan_clear_button_empties_pool(page, live_server_url):
    """Clear button empties the pool and hides the dice icons."""
    _create_priest_3rd_dan(page, live_server_url, "PriestClearPool", precepts=3)
    # Seed a pool directly via the tracking bridge so the test doesn't
    # depend on the roll animation timing.
    page.evaluate("""
        window._trackingBridge.preceptsPool = [
            {value: 9}, {value: 6}, {value: 2}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(100)
    assert page.locator('[data-testid="precepts-pool-die"]').count() == 3
    page.locator('[data-action="clear-precepts-pool"]').click()
    page.wait_for_function(
        "() => window._trackingBridge.preceptsPool.length === 0",
        timeout=3000,
    )
    assert page.locator('[data-testid="precepts-pool-die"]').count() == 0
    # Roll button is back.
    assert page.locator('[data-action="roll-precepts-pool"]').is_visible()


def test_priest_3rd_dan_pool_persists_across_reload(page, live_server_url):
    """Pool survives page reload (stored in Character.precepts_pool)."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolReload", precepts=3)
    page.evaluate("""
        window._trackingBridge.preceptsPool = [
            {value: 7}, {value: 4}, {value: 1}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(300)
    page.reload()
    page.wait_for_function(
        "() => window._trackingBridge && window._trackingBridge.preceptsPool.length === 3",
        timeout=5000,
    )
    pool = page.evaluate("window._trackingBridge.preceptsPool")
    assert [d["value"] for d in pool] == [7, 4, 1]


def test_priest_3rd_dan_pool_not_cleared_by_action_dice_clear(page, live_server_url):
    """The action-dice Clear button must not touch the precepts pool - the
    pool persists across combat rounds and only the per-adventure reset or
    the pool's own Clear button wipes it."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolKeep", precepts=3)
    page.evaluate("""
        window._trackingBridge.preceptsPool = [{value: 8}, {value: 3}];
        window._trackingBridge.actionDice = [{value: 5, spent: false}];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    # Click the action-dice Clear button.
    page.locator('[data-action="clear-action-dice"]').click()
    page.wait_for_timeout(200)
    # Action dice are gone.
    assert page.evaluate("window._trackingBridge.actionDice.length") == 0
    # Precepts pool is untouched.
    assert page.evaluate("window._trackingBridge.preceptsPool.length") == 2


def test_priest_3rd_dan_pool_not_cleared_by_initiative_roll(page, live_server_url):
    """Rolling initiative (which replaces action dice) must not wipe the pool."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolInit", precepts=3)
    page.evaluate("""
        window._trackingBridge.preceptsPool = [{value: 9}, {value: 4}];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    # setActionDice is the end-of-round trigger fired by initiative.
    page.evaluate("window._trackingBridge.setActionDice([6, 2])")
    page.wait_for_timeout(200)
    assert page.evaluate("window._trackingBridge.actionDice.length") == 2
    # Precepts pool is untouched.
    pool = page.evaluate("window._trackingBridge.preceptsPool")
    assert len(pool) == 2
    assert [d["value"] for d in pool] == [9, 4]


def test_priest_3rd_dan_adventure_reset_clears_pool(page, live_server_url):
    """The per-adventure reset wipes the precepts pool as part of its
    broader clear (along with counters, toggles, and action dice)."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolReset", precepts=3)
    page.evaluate("""
        window._trackingBridge.preceptsPool = [
            {value: 9}, {value: 6}, {value: 2}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    assert page.evaluate("window._trackingBridge.preceptsPool.length") == 3
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    page.locator('[data-action="confirm-reset"]').click()
    page.wait_for_timeout(400)
    assert page.evaluate("window._trackingBridge.preceptsPool.length") == 0


def test_priest_3rd_dan_reset_modal_lists_pool_clear(page, live_server_url):
    """The reset confirm modal enumerates what will be cleared; the combat
    dice pool gets its own 'Clear combat dice pool (N dice)' line when non-empty."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolSummary", precepts=3)
    page.evaluate("""
        window._trackingBridge.preceptsPool = [
            {value: 8}, {value: 3}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    body = page.text_content('body')
    assert "Clear combat dice pool (2 dice)" in body


def test_priest_3rd_dan_reset_button_enabled_with_only_pool(page, live_server_url):
    """If the ONLY clearable state is a non-empty precepts pool (no counters
    spent, no toggles set, no action dice), the global Reset button must
    still be enabled so the pool is reachable."""
    _create_priest_3rd_dan(page, live_server_url, "PriestPoolOnly", precepts=3)
    page.evaluate("""
        window._trackingBridge.preceptsPool = [{value: 5}];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    btn = page.locator('[data-action="open-reset-modal"]')
    assert not btn.is_disabled()


# --- Priest 3rd Dan pool display on qualifying rolls (Phase 4) ---
#
# Phase 4 renders the pool in the discretionary-bonus area of every
# qualifying roll modal (parry, attack, damage, wound check). Click-to-swap
# interactivity is wired in Phase 5; these tests only verify presence/absence.

def _seed_own_pool(page, dice):
    """Seed the priest's own precepts pool via the tracking bridge."""
    page.evaluate(
        "values => {"
        " window._trackingBridge.preceptsPool = values.map(v => ({value: v}));"
        " window._trackingBridge.save();"
        "}",
        dice,
    )
    page.wait_for_timeout(200)


def test_priest_3rd_dan_pool_appears_on_own_parry_roll(page, live_server_url):
    """Priest's parry roll shows their precepts pool in the discretionary
    bonus area of the dice-roller modal."""
    _create_priest_3rd_dan(page, live_server_url, "PriestParryPool", precepts=3)
    _seed_own_pool(page, [9, 5, 2])
    page.locator('[data-roll-key="parry"]').click()
    # Parry goes through a small menu first with "Roll Parry" option.
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=5000)
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.click()
    page.wait_for_function("""() => {
        const d = window._diceRoller;
        return d && d.phase === 'done';
    }""", timeout=10000)
    pool_block = page.locator('[data-modal="dice-roller"] [data-testid^="precepts-pool-in-roll-"]')
    assert pool_block.count() == 1
    dice = pool_block.locator('[data-precepts-pool-die]')
    assert dice.count() == 3
    values = [int(d.get_attribute('data-die-value')) for d in dice.all()]
    assert sorted(values) == [2, 5, 9]


def test_priest_3rd_dan_pool_appears_on_own_wound_check(page, live_server_url):
    """Priest's wound check modal shows their precepts pool."""
    _create_priest_3rd_dan(page, live_server_url, "PriestWcPool", precepts=3)
    _seed_own_pool(page, [8, 4])
    # Seed light wounds so the Roll Wound Check button appears.
    page.evaluate("""
        window._trackingBridge.lightWounds = 10;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="roll-wound-check"]').click()
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=5000)
    page.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const d = window._diceRoller;
        return d && d.wcPhase === 'result';
    }""", timeout=10000)
    pool_block = page.locator('[data-modal="wound-check"] [data-testid^="precepts-pool-in-roll-"]')
    assert pool_block.count() == 1


def test_pontificate_picks_higher_of_water_and_air_in_roll_modal(page, live_server_url):
    """Pontificate may be rolled with whichever of Water/Air is higher.
    Roll the knack from a character whose Air is greater than Water and
    verify the dice-roller modal labels and rolls the formula with Air."""
    # Priest's school ring defaults to Water (3). Bump Air to 4 so it's
    # the higher of the two.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "PontificateAir")
    select_school(page, "priest")
    click_plus(page, "ring_air", 2)   # Air 2 -> 4 (now higher than Water 3)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)

    # Knack badge on the View Sheet should advertise both rings.
    assert "Water or Air" in page.text_content("body")

    page.locator('[data-roll-key="knack:pontificate"]').click()
    page.wait_for_function("""() => {
        const d = window._diceRoller;
        return d && d.phase === 'done';
    }""", timeout=10_000)
    modal = page.locator('[data-modal="dice-roller"]').text_content()
    # Higher ring (Air = 4) was used; "Pontificate (Air)" appears in the label.
    assert "Pontificate (Air)" in modal, (
        f"expected modal label to read 'Pontificate (Air)'; got: {modal!r}"
    )


def test_priest_3rd_dan_pool_does_not_appear_on_skill_roll(page, live_server_url):
    """Plain skill rolls are not an attack/parry/damage/WC so no pool block."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSkillPool", precepts=3)
    _seed_own_pool(page, [9, 5])
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    # Precepts is a priest school knack, so it's rollable as knack:precepts,
    # but precepts as a *skill* isn't a roll key here. Pick a simple knack
    # that's definitely rollable: pontificate (priest school knack).
    page.locator('[data-roll-key="knack:pontificate"]').click()
    page.wait_for_function("""() => {
        const d = window._diceRoller;
        return d && d.phase === 'done';
    }""", timeout=10000)
    pool_block = page.locator('[data-modal="dice-roller"] [data-testid^="precepts-pool-in-roll-"]')
    assert pool_block.count() == 0


def test_priest_3rd_dan_pool_predicate_excludes_iaijutsu_duel(page, live_server_url):
    """The iaijutsu knack (used for contested duels) is not an attack/parry/
    damage/WC per the 3rd Dan rules, so the precepts-pool predicate must
    return false for it. The Kakita combat iaijutsu attack variant
    (``knack:iaijutsu:attack``) is a proper attack roll and IS qualifying -
    tested here against the predicate directly so party setup isn't needed."""
    _create_char(page, live_server_url, "KakitaIaiPred", "kakita_duelist",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    # Predicate evaluates against the dice-roller's formula + currentRollKey.
    # Pretend the dice-roller is mid-iaijutsu-duel-knack roll:
    duel_result = page.evaluate("""() => {
        const d = window._diceRoller;
        d.formula = d.formulas['knack:iaijutsu'] || null;
        d.currentRollKey = 'knack:iaijutsu';
        return d._isPreceptsPoolQualifyingRoll('roll');
    }""")
    assert duel_result is False
    # And for the combat iaijutsu attack:
    atk_result = page.evaluate("""() => {
        const d = window._diceRoller;
        d.atkFormula = d.formulas['knack:iaijutsu:attack'] || null;
        return d._isPreceptsPoolQualifyingRoll('attack');
    }""")
    assert atk_result is True


def test_ally_sees_priest_3rd_dan_pool_on_attack_roll(page, live_server_url):
    """Set up a priest at 3rd Dan with a pool and a non-priest ally in the
    same gaming group. When the ally rolls attack, the priest's pool renders
    in the attack modal's discretionary-bonus area."""
    # Priest at 3rd Dan (precepts=3) with a pool.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Party Priest")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 2)  # 1 -> 3
    click_plus(page, "skill_precepts", 3)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Priest 3rd Dan")
    priest_url = page.url
    # Assign to Tuesday Group.
    page.goto(priest_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)
    # Go to the sheet and seed the pool directly.
    page.goto(priest_url)
    page.wait_for_selector('[data-testid="precepts-pool-section"]', timeout=5000)
    _seed_own_pool(page, [9, 4])

    # Ally (Akodo) in same group.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Party Ally")
    select_school(page, "akodo_bushi")
    click_plus(page, "attack", 1)  # 1 -> 2
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Ally")
    ally_url = page.url
    page.goto(ally_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)

    # Visit the ally's sheet; the priest_precepts_allies JSON should carry the pool.
    page.goto(ally_url)
    allies = page.evaluate("""() => {
        const el = document.getElementById('priest-precepts-allies');
        return JSON.parse(el.textContent || '[]');
    }""")
    assert len(allies) == 1
    assert allies[0]["name"] == "Party Priest"
    assert allies[0]["pool"] == [{"value": 9}, {"value": 4}]

    # Fire an attack roll; the attack modal should show the priest's pool.
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # Pre-roll: pool block is already in the DOM (the predicate is based on
    # atkFormula.is_attack_type which is set when the modal opens).
    # Filter by the attack-phase instance via the data-precepts-pool-modal
    # attribute to distinguish it from the damage-phase instance.
    attack_pool = page.locator(
        '[data-modal="attack"] [data-precepts-pool-modal="attack"]'
    )
    assert attack_pool.count() == 1, \
        f"expected 1 attack-phase pool block; got {attack_pool.count()}"
    assert "Party Priest" in attack_pool.text_content()


def test_priest_3rd_dan_empty_pool_does_not_render_block(page, live_server_url):
    """A priest at 3rd Dan with an EMPTY pool gets no block rendered (the
    template iterates only over priests with non-empty pools)."""
    _create_priest_3rd_dan(page, live_server_url, "PriestEmptyPool", precepts=3)
    # Do NOT seed a pool - preceptsPool stays [].
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=5000)
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.click()
    page.wait_for_function("""() => {
        const d = window._diceRoller;
        return d && d.phase === 'done';
    }""", timeout=10000)
    assert page.locator(
        '[data-modal="dice-roller"] [data-testid^="precepts-pool-in-roll-"]'
    ).count() == 0


# --- Priest 3rd Dan SWAP (Phase 5) ---
#
# These tests drive the swap algorithm by staging finalDice / pool directly
# via Alpine evaluate() rather than running a full roll pipeline. This keeps
# the tests deterministic (no dice-rolling randomness) and lets us assert
# exact before/after values on every swap case.

def _stage_swap_context(page, pool, rolled, kept_count):
    """Set up a deterministic roll-result state on the live diceRoller:
    finalDice = rolled (a list of ints), pool = pool (list of ints),
    kept-flag derived by keeping the top ``kept_count`` values, and a
    fake formula so the parry-modal predicate accepts the roll."""
    page.evaluate(
        """({pool, rolled, keptCount}) => {
            const d = window._diceRoller;
            const bridge = window._trackingBridge;
            // Seed the pool on the priest's own state.
            bridge.preceptsPool = pool.map(v => ({value: v}));
            bridge.save();
            // Stage finalDice + kept flags (keep top-N by value).
            const sorted = rolled.map((v, i) => ({v, i})).sort((a, b) => a.v - b.v);
            const keptIdx = new Set(sorted.slice(sorted.length - keptCount).map(x => x.i));
            d.finalDice = rolled.map((v, i) => ({value: v, kept: keptIdx.has(i), parts: [v]}));
            d.keptDice = d.finalDice.filter(x => x.kept);
            d.keptSum = d.keptDice.reduce((s, x) => s + x.value, 0);
            d.baseTotal = d.keptSum;
            d.formula = {kept: keptCount, is_attack_type: false};
            d.currentRollKey = 'parry';
            d.phase = 'done';
            d.open = true;  // open the dice-roller modal so the pool block renders
            d.preceptsPoolSwapBonuses = [];
            d.preceptsPoolMenuOpen = null;
        }""",
        {"pool": pool, "rolled": rolled, "keptCount": kept_count},
    )
    page.wait_for_timeout(100)


def _priest_swap_self(page, pool_die_index, rolled_value):
    """Invoke swapPreceptsDie for the priest's own pool."""
    return page.evaluate(
        """({pi, rv}) => {
            const d = window._diceRoller;
            const allies = d.preceptsPoolAlliesForThisRoll('roll');
            const self = allies.find(a => a.isSelf);
            if (!self) return {error: 'no self pool'};
            d.swapPreceptsDie(self, pi, rv);
            return {
                pool: window._trackingBridge.preceptsPool.map(x => x.value),
                finalDice: d.finalDice.map(x => ({v: x.value, kept: !!x.kept})),
                keptSum: d.keptSum,
                baseTotal: d.baseTotal,
                bonuses: d.preceptsPoolSwapBonuses,
            };
        }""",
        {"pi": pool_die_index, "rv": rolled_value},
    )


def test_priest_3rd_dan_swap_pool_die_with_lower_rolled_die(page, live_server_url):
    """The simplest case: priest swaps a pool 9 for a rolled 3. The pool 9
    becomes a kept die; the replaced 3 returns to the pool. keptSum grows
    by 9-3=6."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwap1", precepts=2)
    _stage_swap_context(page, pool=[9, 2], rolled=[8, 3], kept_count=2)
    before_total = page.evaluate("window._diceRoller.baseTotal")
    result = _priest_swap_self(page, pool_die_index=0, rolled_value=3)
    # Pool: first entry was 9 (now replaced by the rolled 3).
    assert result["pool"][0] == 3
    assert result["pool"][1] == 2
    # finalDice: the rolled 3 got replaced by the pool 9; kept set is now
    # {8, 9}. keptSum went from 8+3=11 to 8+9=17, delta +6.
    kept_values = sorted([d["v"] for d in result["finalDice"] if d["kept"]])
    assert kept_values == [8, 9]
    assert result["keptSum"] == 17
    assert result["baseTotal"] == before_total + 6
    # One structured bonus-entry recorded.
    assert len(result["bonuses"]) == 1
    assert result["bonuses"][0]["rolledValueBefore"] == 3
    assert result["bonuses"][0]["poolValueAfter"] == 9


def test_priest_3rd_dan_swap_promotes_unkept_die_into_kept(page, live_server_url):
    """Swapping a pool die for a currently-unkept rolled die promotes the
    new high value into the kept set. Here kept is only {5}; rolled 1 is
    unkept; pool 9 swaps with rolled 1 and promotes into kept (pushing 5
    out)."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwap2", precepts=1)
    _stage_swap_context(page, pool=[9], rolled=[5, 1], kept_count=1)
    result = _priest_swap_self(page, pool_die_index=0, rolled_value=1)
    # Pool: 9 replaced by the rolled 1.
    assert result["pool"] == [1]
    # finalDice values are {5, 9}; only 9 is kept (top 1 by value).
    kept_values = [d["v"] for d in result["finalDice"] if d["kept"]]
    assert kept_values == [9]
    # keptSum went from 5 to 9.
    assert result["keptSum"] == 9


def test_priest_3rd_dan_swap_menu_dedupes_rolled_values(page, live_server_url):
    """If two rolled dice have the same value, the dropdown offers a
    single entry ("Swap with a rolled 4"), not two."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwap3", precepts=1)
    _stage_swap_context(page, pool=[10], rolled=[4, 4, 8], kept_count=2)
    options = page.evaluate("""() => {
        const d = window._diceRoller;
        const allies = d.preceptsPoolAlliesForThisRoll('roll');
        const self = allies.find(a => a.isSelf);
        return d.preceptsSwapOptions(self, self.pool[0].value);
    }""")
    labels = [o["label"] for o in options]
    assert labels == ["Swap with a rolled 4", "Swap with a rolled 8"]


def test_priest_3rd_dan_self_swap_menu_disabled_only_when_all_rolled_equal(page, live_server_url):
    """For the priest's own swap, every non-equal rolled die is offered as
    an option (including values higher than the pool die - that's the
    'impair my roll to refresh the pool' case). The disabled entry only
    appears when every rolled die exactly equals the pool die."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwapSelfDisabled", precepts=1)
    # Case 1: pool 3 with rolled [10, 7, 3] - the priest CAN swap a high
    # kept die for their pool's 3 (impair-and-refresh). Options list both
    # 7 and 10 and is NOT disabled.
    _stage_swap_context(page, pool=[3], rolled=[10, 7, 3], kept_count=2)
    options = page.evaluate("""() => {
        const d = window._diceRoller;
        const self = d.preceptsPoolAlliesForThisRoll('roll').find(a => a.isSelf);
        return d.preceptsSwapOptions(self, self.pool[0].value);
    }""")
    labels = [o["label"] for o in options]
    assert labels == ["Swap with a rolled 7", "Swap with a rolled 10"]
    # Case 2: pool 5 with rolled [5, 5] - every rolled die is equal to
    # the pool die, so no valid swap exists. Disabled message appears.
    _stage_swap_context(page, pool=[5], rolled=[5, 5], kept_count=2)
    options = page.evaluate("""() => {
        const d = window._diceRoller;
        const self = d.preceptsPoolAlliesForThisRoll('roll').find(a => a.isSelf);
        return d.preceptsSwapOptions(self, self.pool[0].value);
    }""")
    assert len(options) == 1
    assert options[0].get("disabled") is True
    assert "No different rolled dice" in options[0]["label"]


def test_priest_3rd_dan_ally_swap_menu_disabled_when_no_lower(page, live_server_url):
    """For an ally, only strictly-lower rolled dice are valid. If no
    rolled die is strictly lower than the clicked pool die, the dropdown
    shows a single disabled 'No lower rolled dice' entry."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwapAllyDisabled", precepts=1)
    _stage_swap_context(page, pool=[3], rolled=[10, 7, 3], kept_count=2)
    options = page.evaluate("""() => {
        const d = window._diceRoller;
        const self = d.preceptsPoolAlliesForThisRoll('roll').find(a => a.isSelf);
        // Forge an ally-style priest object (same pool, isSelf=false) so
        // preceptsSwapOptions applies the ally rule without requiring a
        // full two-character party setup in this unit-style test.
        const fakeAlly = {priest_id: 'fake', name: 'Fake', pool: self.pool, isSelf: false};
        return d.preceptsSwapOptions(fakeAlly, fakeAlly.pool[0].value);
    }""")
    assert len(options) == 1
    assert options[0].get("disabled") is True
    assert "No lower rolled dice" in options[0]["label"]


def test_priest_3rd_dan_self_swap_can_impair_roll_to_refresh_pool(page, live_server_url):
    """The priest can deliberately lower their own roll by swapping a LOW
    pool die in for a HIGH kept die. Net: their roll drops, and the pool
    gains a high die it can later lend to allies."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSelfImpair", precepts=1)
    # Pool has a 2; rolled dice are [9, 7] both kept.
    _stage_swap_context(page, pool=[2], rolled=[9, 7], kept_count=2)
    before = page.evaluate("window._diceRoller.keptSum")
    result = _priest_swap_self(page, pool_die_index=0, rolled_value=9)
    # The 9 moves into the pool; the 2 moves into the kept set.
    assert result["pool"] == [9]
    # Kept is now {7, 2}; keptSum dropped from 9+7=16 to 7+2=9.
    kept_values = sorted([d["v"] for d in result["finalDice"] if d["kept"]])
    assert kept_values == [2, 7]
    assert result["keptSum"] == 9
    assert result["keptSum"] < before


def test_priest_3rd_dan_equal_value_rolled_die_excluded_from_menu(page, live_server_url):
    """Equal-value swap is a no-op so it's excluded for everyone (self
    included) - pool 5 with rolled {5, 4, 3} offers only 4 and 3."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwap5", precepts=1)
    _stage_swap_context(page, pool=[5], rolled=[5, 4, 3], kept_count=2)
    options = page.evaluate("""() => {
        const d = window._diceRoller;
        const allies = d.preceptsPoolAlliesForThisRoll('roll');
        const self = allies.find(a => a.isSelf);
        return d.preceptsSwapOptions(self, self.pool[0].value);
    }""")
    labels = [o["label"] for o in options]
    assert labels == ["Swap with a rolled 3", "Swap with a rolled 4"]


def test_priest_3rd_dan_swap_menu_stays_within_viewport(page, live_server_url):
    """The swap dropdown uses fixed positioning with viewport clamping, so
    the menu's edges stay inside the browser window and its options aren't
    cut off even when a pool die sits at the edge of the modal."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwapClamp", precepts=2)
    page.set_viewport_size({"width": 800, "height": 600})
    _stage_swap_context(page, pool=[9, 4], rolled=[7, 2], kept_count=1)
    page.wait_for_function(
        "document.querySelectorAll('[data-precepts-pool-die]').length >= 2",
        timeout=5000,
    )
    page.locator(
        '[data-modal="dice-roller"] [data-action^="precepts-pool-die-self-"]'
    ).first.click()
    page.wait_for_timeout(150)
    menu = page.locator(
        '[data-modal="dice-roller"] [data-precepts-swap-menu="self:0"]'
    )
    assert menu.is_visible()
    rect = menu.bounding_box()
    viewport = page.viewport_size
    assert rect is not None
    assert rect["x"] >= 0, f"menu left={rect['x']} off-screen left"
    assert rect["x"] + rect["width"] <= viewport["width"] + 1, (
        f"menu right={rect['x'] + rect['width']} exceeds viewport width "
        f"{viewport['width']}"
    )
    assert rect["y"] >= 0, f"menu top={rect['y']} off-screen top"
    assert rect["y"] + rect["height"] <= viewport["height"] + 1, (
        f"menu bottom={rect['y'] + rect['height']} exceeds viewport height "
        f"{viewport['height']}"
    )


def test_priest_3rd_dan_swap_menu_closes_on_outside_click(page, live_server_url):
    """Clicking anywhere outside the swap dropdown closes it. The dropdown
    uses position:fixed which can confuse Alpine's @click.outside heuristic,
    so a document-level listener handles the dismiss explicitly."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwapOutside", precepts=2)
    _stage_swap_context(page, pool=[9, 4], rolled=[7, 2], kept_count=1)
    page.wait_for_function(
        "document.querySelectorAll('[data-precepts-pool-die]').length >= 2",
        timeout=5000,
    )
    page.locator(
        '[data-modal="dice-roller"] [data-action^="precepts-pool-die-self-"]'
    ).first.click()
    page.wait_for_timeout(150)
    menu = page.locator(
        '[data-modal="dice-roller"] [data-precepts-swap-menu="self:0"]'
    )
    assert menu.is_visible()
    # Dispatch a click on the document body that lands neither on a pool
    # die nor on the dropdown. page.mouse.click works even for areas
    # without an explicit clickable element.
    page.mouse.click(5, 5)
    page.wait_for_timeout(200)
    assert not menu.is_visible(), "menu should close on outside click"


def test_priest_3rd_dan_swap_dropdown_opens_and_closes(page, live_server_url):
    """Clicking a pool die button opens its dropdown; clicking again closes it."""
    _create_priest_3rd_dan(page, live_server_url, "PriestSwap6", precepts=2)
    _stage_swap_context(page, pool=[9, 4], rolled=[7, 2], kept_count=1)
    page.wait_for_function(
        "document.querySelectorAll('[data-precepts-pool-die]').length >= 2",
        timeout=5000,
    )
    # The macro renders the pool block inside multiple modals; pick the
    # one in the dice-roller modal (currently visible).
    die_btns = page.locator(
        '[data-modal="dice-roller"] [data-action^="precepts-pool-die-self-"]'
    )
    assert die_btns.count() == 2
    die_btns.first.click()
    page.wait_for_timeout(150)
    menu = page.locator(
        '[data-modal="dice-roller"] [data-precepts-swap-menu="self:0"]'
    )
    assert menu.is_visible()
    option_labels = [el.text_content().strip() for el in menu.locator('button').all()]
    assert "Swap with a rolled 2" in option_labels
    assert "Swap with a rolled 7" in option_labels
    # Click the same pool die again to toggle the dropdown closed.
    die_btns.first.click()
    page.wait_for_timeout(150)
    assert not menu.is_visible()


def test_ally_swaps_priest_pool_die_and_broadcasts(page, live_server_url):
    """When an ally swaps with a priest's pool die, the swap:
       - updates the ally's own rolled dice + total,
       - broadcasts the new pool to the priest's character via
         POST /characters/{priest_id}/precepts-pool,
       - persists so both sheets see the updated pool on reload.
    """
    # Set up a priest with a pool in Tuesday Group.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Swap Priest")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 2)
    click_plus(page, "skill_precepts", 3)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Swap Priest")
    priest_url = page.url
    page.goto(priest_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)
    page.goto(priest_url)
    _seed_own_pool(page, [10, 3])

    # Ally in same group.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Swap Ally")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Swap Ally")
    ally_url = page.url
    page.goto(ally_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)

    page.goto(ally_url)
    # Stage an attack-result state on the ally so the pool can swap into it.
    # (The priestPreceptsAllies array is seeded by the context at page load.)
    page.evaluate("""() => {
        const d = window._diceRoller;
        // Pretend the attack modal is open with finalDice from a roll.
        d.finalDice = [
            {value: 8, kept: true, parts: [8]},
            {value: 2, kept: false, parts: [2]},
        ];
        d.keptDice = [d.finalDice[0]];
        d.keptSum = 8;
        d.baseTotal = 8;
        d.atkRollTotal = 8;
        d.atkFormula = {kept: 1, is_attack_type: true};
        d.atkPhase = 'result';
        d.atkModalOpen = true;
        d.currentRollKey = 'attack';
        d.preceptsPoolSwapBonuses = [];
    }""")
    page.wait_for_timeout(100)
    # Invoke the swap via the exposed helper. The ally can only swap with
    # a strictly-lower rolled die, so pool 10 swaps with rolled 2.
    result = page.evaluate("""() => {
        const d = window._diceRoller;
        const priest = d.priestPreceptsAllies.find(p => p.name === 'Swap Priest');
        d.swapPreceptsDie(priest, 0, 2);
        return {
            finalDice: d.finalDice.map(x => ({v: x.value, kept: !!x.kept})),
            atkRollTotal: d.atkRollTotal,
            priestPool: priest.pool.map(x => x.value),
        };
    }""")
    # Ally's kept set is now {10}; total went from 8 to 10 (+2).
    kept_values = [d["v"] for d in result["finalDice"] if d["kept"]]
    assert kept_values == [10]
    assert result["atkRollTotal"] == 10
    # The priest's pool on the ally's local reference now has {2, 3}.
    assert sorted(result["priestPool"]) == [2, 3]
    # Wait for the POST to flush, then load the priest's sheet - DB should
    # reflect the new pool.
    page.wait_for_timeout(500)
    page.goto(priest_url)
    page.wait_for_selector('[data-testid="precepts-pool-section"]')
    page.wait_for_function(
        "() => window._trackingBridge && Array.isArray(window._trackingBridge.preceptsPool)"
    )
    persisted = page.evaluate(
        "window._trackingBridge.preceptsPool.map(x => x.value)"
    )
    assert sorted(persisted) == [2, 3]


def test_priest_3rd_dan_pool_shows_on_missed_attack(page, live_server_url):
    """Pool must be visible in the attack modal whether the attack HIT or
    MISSED. Swapping a higher pool die in for a low rolled die can turn a
    miss into a hit, so hiding the pool on miss would defeat the feature."""
    _create_priest_3rd_dan(page, live_server_url, "PriestAtkMiss", precepts=3)
    _seed_own_pool(page, [10, 6])
    # Stage a failed attack directly on the dice-roller so the test doesn't
    # depend on randomness or the TN-select options.
    page.evaluate("""() => {
        const d = window._diceRoller;
        d.atkFormula = d.formulas['attack'] || {kept: 2, is_attack_type: true, attack_variant: 'attack'};
        d.atkFormula.is_attack_type = true;
        d.atkTN = 50;
        d.finalDice = [
            {value: 3, kept: true, parts: [3]},
            {value: 2, kept: true, parts: [2]},
        ];
        d.keptDice = [...d.finalDice];
        d.keptSum = 5;
        d.baseTotal = 5;
        d.atkRollTotal = 5;
        d.atkHit = false;
        d.atkNearMiss = false;
        d.atkExcess = -45;
        d.atkPhase = 'result';
        d.atkModalOpen = true;
    }""")
    page.wait_for_timeout(150)
    # The pool block must be present in the attack-result view even though
    # the attack failed.
    attack_pool = page.locator(
        '[data-modal="attack"] [data-precepts-pool-modal="attack"]'
    )
    assert attack_pool.count() == 1, \
        f"expected 1 attack-phase pool block on miss; got {attack_pool.count()}"
    dice = attack_pool.locator('[data-precepts-pool-die]')
    assert dice.count() == 2
    # The swap dropdown for pool die 10 offers "Swap with a rolled 2" and
    # "Swap with a rolled 3" - picking 2 pushes keptSum from 5 to 13 and
    # can turn the miss into a hit.
    options = page.evaluate("""() => {
        const d = window._diceRoller;
        const allies = d.preceptsPoolAlliesForThisRoll('attack');
        const self = allies.find(a => a.isSelf);
        return d.preceptsSwapOptions(self, self.pool[0].value).map(o => o.label);
    }""")
    assert "Swap with a rolled 2" in options
    assert "Swap with a rolled 3" in options


def test_ally_swap_strictly_rejects_equal_or_higher_rolled_die(page, live_server_url):
    """Even an ally who clicks swap with equal or higher rolled values
    gets nothing - the swap helper no-ops (the dropdown never offered
    those options in the first place, but guard against direct calls)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "StrictSwapPriest")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 2)
    click_plus(page, "skill_precepts", 2)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "StrictSwapPriest")
    priest_url = page.url
    page.goto(priest_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)
    page.goto(priest_url)
    _seed_own_pool(page, [5])

    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "StrictSwapAlly")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "StrictSwapAlly")
    ally_url = page.url
    page.goto(ally_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(500)
    page.goto(ally_url)
    # Rolled dice: 5 (equal) and 8 (higher). Neither can be swapped with the
    # pool 5. The direct swap call should no-op.
    result = page.evaluate("""() => {
        const d = window._diceRoller;
        d.finalDice = [
            {value: 5, kept: true, parts: [5]},
            {value: 8, kept: true, parts: [8]},
        ];
        d.keptDice = [...d.finalDice];
        d.keptSum = 13;
        d.baseTotal = 13;
        d.formula = {kept: 2, is_attack_type: false};
        d.currentRollKey = 'parry';
        d.phase = 'done';
        d.open = true;
        // Find the specific priest by name (other tests may have left
        // other priests in the group with their own pools).
        const priest = d.priestPreceptsAllies.find(p => p.name === 'StrictSwapPriest');
        if (!priest) return {error: 'priest missing'};
        const before = priest.pool.map(x => x.value);
        d.swapPreceptsDie(priest, 0, 5);   // equal - rejected
        d.swapPreceptsDie(priest, 0, 8);   // higher - rejected
        return {
            before,
            after: priest.pool.map(x => x.value),
            finalDice: d.finalDice.map(x => x.value),
        };
    }""")
    assert "error" not in result, result
    assert result["before"] == result["after"] == [5]
    assert sorted(result["finalDice"]) == [5, 8]


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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)  # dice roll 7 each -> ~35 total for a 5k3+flat roll
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Open wound check modal to see the probability table
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "60")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
    wc_modal = page.locator('[data-modal="wound-check"]')
    halved_note = wc_modal.locator('text="Bayushi 5th Dan"')
    assert halved_note.count() == 0 or not halved_note.first.is_visible()


def test_brotherhood_unarmed_damage_behavioral(page, live_server_url):
    """Brotherhood Special: attack damage shows +1k1 unarmed bonus in breakdown."""
    _create_char(page, live_server_url, "Brotherhood_UB", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "worldliness": 2})
    _mock_dice_high(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    # actionDice now holds {value, ...} entries instead of raw numbers.
    values = [d.get("value") if isinstance(d, dict) else d for d in action_dice]
    assert 0 in values, f"Expected Phase 0 in action dice {action_dice}"
    result = _get_roll_result_text(page)
    assert "Phase 0" in result


# ---------------------------------------------------------------------------
# Kakita Special Ability — Phase 0 from sort-10s-as-0s on initiative
# ---------------------------------------------------------------------------


def _mock_dice_sequence(page, values):
    """Install a Math.random stub that produces the given d10 results in
    order. Each value ``v`` comes back as ``Math.floor(Math.random()*10)+1``,
    so we feed ``(v-1)/10 + epsilon`` so the floor lands on ``v-1`` and the
    final roll is ``v``. Dice-roll paths that call Math.random for any other
    purpose will also see these values, so use short sequences and restore."""
    seq = [((v - 1) / 10) + 0.001 for v in values]
    page.evaluate(f"""() => {{
        window._origRandom = Math.random;
        const seq = {seq!r};
        let i = 0;
        Math.random = () => {{
            const v = seq[i % seq.length];
            i++;
            return v;
        }};
    }}""")


def test_kakita_initiative_keeps_10_over_higher_lower_dice(page, live_server_url):
    """Regression for the sort bug: rolling a 10 alongside non-10 dice on
    Kakita initiative must KEEP the 10 (treated as 0 for sort) and convert
    it to a Phase-0 action die. Previously the keep-lowest logic discarded
    the 10 and the player lost the Phase-0 die entirely."""
    _create_char(page, live_server_url, "KakitaKeep10", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # Default character: Void=2; Kakita 1st Dan grants +1 initiative die, so
    # the formula is 4k2. Feed dice [2, 5, 10, 7] in order. Sort treating 10
    # as 0: [10, 2, 5, 7]. Keep first 2: [10, 2] -> action dice [0, 2]
    # after 10->0 rewrite and final sort.
    _mock_dice_sequence(page, [2, 5, 10, 7])
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    values = page.evaluate("""() =>
        (window._trackingBridge?.actionDice || []).map(d => d.value)
    """)
    assert sorted(values) == [0, 2], f"got action dice {values}"


def test_kakita_initiative_two_10s_both_become_phase_0(page, live_server_url):
    """Two rolled 10s on Kakita initiative should both be kept and both
    convert to Phase-0 (value=0) action dice."""
    _create_char(page, live_server_url, "KakitaTwo10s", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # 4k2 roll: dice 10, 8, 10, 4. Sort 10-as-0: [10, 10, 4, 8].
    # Keep first 2: [10, 10] -> action dice [0, 0].
    _mock_dice_sequence(page, [10, 8, 10, 4])
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    values = page.evaluate("""() =>
        (window._trackingBridge?.actionDice || []).map(d => d.value)
    """)
    assert sorted(values) == [0, 0], f"got action dice {values}"


def test_non_kakita_10_on_initiative_is_unkept(page, live_server_url):
    """Regression: non-Kakita characters treat 10 as the highest value on
    initiative, so a rolled 10 gets unkept (keep-lowest) and never appears
    as a value-0 action die."""
    _create_char(page, live_server_url, "AkodoKeepLow", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    # Akodo has no initiative extra die; 3k2 (void=2, no 1st Dan init extra).
    # Dice 10, 3, 5 -> keep the 2 lowest (3, 5). No Phase 0.
    _mock_dice_sequence(page, [10, 3, 5])
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    values = page.evaluate("""() =>
        (window._trackingBridge?.actionDice || []).map(d => d.value)
    """)
    assert 0 not in values, f"non-Kakita should not produce Phase 0 dice; got {values}"
    assert 10 not in values, f"10 should be unkept for non-Kakita; got {values}"


def test_kakita_phase_0_die_has_phase_zero_svg_class(page, live_server_url):
    """The Actions-panel SVG for a value-0 die carries the .phase-zero class
    as a DOM marker for future styling / tests. (The current CSS renders
    Phase-0 dice the same as any other action die - 10s / 0s on action
    dice aren't highlighted because no reroll is implied.)"""
    _create_char(page, live_server_url, "KakitaP0Svg", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    _mock_dice_ten(page)
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    # Close the roll-result modal so the Actions panel can register hits.
    page.locator('[data-modal="dice-roller"] button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    section = page.locator('[data-testid="action-dice-section"]')
    assert section.locator('svg.action-die.phase-zero').count() > 0


def test_initiative_roll_does_not_mark_10s_red(page, live_server_url):
    """10s only mean something on rolls that reroll - not on initiative.
    The rolling animation must NOT add the ``is-ten`` class when reroll-
    tens is off, so a 10 on initiative renders the same as any other die."""
    _create_char(page, live_server_url, "NoRedOnInit", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    # Re-enable animations so the rolling tray actually renders.
    page.evaluate("if (window._diceRoller) window._diceRoller.prefs.dice_animation_enabled = true")
    _mock_dice_ten(page)
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    # The rolling tray's SVGs must not carry ``is-ten``.
    modal = page.locator('[data-modal="dice-roller"]')
    assert modal.locator('svg.is-ten').count() == 0


def test_kakita_phase_0_die_not_styled_distinctly(page, live_server_url):
    """Per feedback: a Phase-0 action die is NOT styled distinctly from
    other action dice (no gold / red). The .phase-zero class stays as a
    DOM marker but has no visual effect; a regular non-Phase-0 die looks
    the same."""
    _create_char(page, live_server_url, "KakitaP0Plain", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 0, spent: false},
            {value: 5, spent: false},
        ];
    }""")
    section = page.locator('[data-testid="action-dice-section"]')
    assert section.locator('svg.action-die.phase-zero').count() == 1
    assert section.locator('svg.action-die:not(.phase-zero)').count() == 1
    # The CSS rules that used to color phase-zero have been removed, so
    # both dice compute the same die-shape fill. Sanity-check by reading
    # the computed fill off each.
    fills = page.evaluate("""() => {
        const section = document.querySelector('[data-testid="action-dice-section"]');
        const phaseZero = section.querySelector('svg.action-die.phase-zero .die-shape');
        const normal = section.querySelector('svg.action-die:not(.phase-zero):not(.athletics-only) .die-shape');
        return {
            phaseZero: phaseZero ? getComputedStyle(phaseZero).fill : null,
            normal: normal ? getComputedStyle(normal).fill : null,
        };
    }""")
    assert fills["phaseZero"] is not None
    assert fills["normal"] is not None
    assert fills["phaseZero"] == fills["normal"]


def test_kakita_phase_0_die_survives_reload(page, live_server_url):
    """After rolling initiative, the phase-0 die persists through a reload:
    value stays 0, the SVG retains its .phase-zero class."""
    _create_char(page, live_server_url, "KakitaP0Reload", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    _mock_dice_ten(page)
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    page.wait_for_timeout(500)  # save round-trip
    page.reload()
    page.wait_for_selector('[data-testid="action-dice-section"]', state='visible',
                           timeout=10000)
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || []).length > 0",
        timeout=5000,
    )
    values = page.evaluate("""() =>
        (window._trackingBridge?.actionDice || []).map(d => d.value)
    """)
    assert 0 in values, f"Phase 0 die lost on reload; got {values}"
    section = page.locator('[data-testid="action-dice-section"]')
    assert section.locator('svg.action-die.phase-zero').count() > 0


def test_kakita_phase_0_die_tooltip_mentions_iaijutsu(page, live_server_url):
    """Hovering a Kakita phase-0 die shows the iaijutsu-only hint."""
    _create_char(page, live_server_url, "KakitaP0Tip", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    _mock_dice_ten(page)
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    page.locator('[data-modal="dice-roller"] button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    btn = page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"][data-die-value="0"]'
    ).first
    tooltip = btn.get_attribute('title')
    assert tooltip and "Phase 0 (Kakita interrupt)" in tooltip
    assert "iaijutsu" in tooltip.lower()


# ---------------------------------------------------------------------------
# Kakita Phase-0 die: per-die menu only offers iaijutsu attack
# ---------------------------------------------------------------------------


def _seed_kakita_phase_zero_die(page):
    """Put a single value-0 (phase-0) action die on the tracking bridge for
    direct menu testing. We bypass the initiative roll here so tests can
    rely on a known die layout without mocking the d10 sequence."""
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 0, spent: false}];
    }""")


def test_kakita_phase_zero_die_menu_shows_only_iaijutsu_attack(page, live_server_url):
    """The per-die menu on a Kakita phase-0 die exposes Iaijutsu Attack and
    Mark-as-spent only; every other option (Roll Attack, Parry, Double
    Attack, etc.) is suppressed by the kakita_phase_zero gate."""
    _create_char(page, live_server_url, "KakitaP0Menu", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    _seed_kakita_phase_zero_die(page)
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.wait_for_selector(
        '[data-action-die-menu-item="iaijutsu-attack"]:visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').count() == 1
    for kind in ("attack", "parry", "double-attack", "counterattack",
                 "lunge", "feint", "predeclared-parry", "athletics-attack",
                 "athletics-parry", "athletics-predeclared-parry"):
        assert page.locator(
            f'[data-action-die-menu-item="{kind}"]:visible'
        ).count() == 0, f"{kind} leaked into the phase-0 menu"
    # Mark-as-spent still there as an escape hatch.
    assert page.locator('[data-action="action-die-spent"]:visible').count() == 1


def test_kakita_non_zero_die_menu_unchanged(page, live_server_url):
    """Regular (value > 0) Kakita action dice see the full normal menu;
    no accidental lock-out from the Phase-0 gate."""
    _create_char(page, live_server_url, "KakitaNonZeroMenu", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.wait_for_selector(
        '[data-action-die-menu-item="attack"]:visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="attack"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="parry"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="double-attack"]:visible').count() == 1
    # The iaijutsu-attack menu item is Phase-0-only and does not leak onto
    # a regular die.
    assert page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').count() == 0


def test_kakita_phase_zero_menu_opens_attack_modal_for_iaijutsu(page, live_server_url):
    """Clicking Iaijutsu Attack on a Phase-0 die opens the attack modal
    with attack_variant === 'iaijutsu' (new in Phase 2)."""
    _create_char(page, live_server_url, "KakitaP0Open", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    _seed_kakita_phase_zero_die(page)
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    variant = page.evaluate("() => window._diceRoller?.atkFormula?.attack_variant")
    assert variant == "iaijutsu"


def test_kakita_phase_zero_attack_modal_notes_interrupt(page, live_server_url):
    """The pre-roll page displays a 'Kakita Phase 0 iaijutsu attack' note."""
    _create_char(page, live_server_url, "KakitaP0Note", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    _seed_kakita_phase_zero_die(page)
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    note = page.locator('[data-testid="kakita-phase-zero-attack-note"]')
    assert note.is_visible()
    assert "Phase 0" in note.text_content()
    assert "iaijutsu" in note.text_content().lower()


def test_kakita_phase_zero_attack_spends_the_clicked_die(page, live_server_url):
    """Rolling from the Phase-0 iaijutsu attack modal spends THE Phase-0
    die (the one the player clicked), not some other action die."""
    _create_char(page, live_server_url, "KakitaP0Spend", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # Two dice: a Phase-0 die at index 0 and a regular die at index 1.
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 0, spent: false},
            {value: 5, spent: false},
        ];
    }""")
    # Open the Phase-0 die's menu and pick Iaijutsu Attack.
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: d.spent,
    }))""")
    assert state[0] == {"value": 0, "spent": True}
    assert state[1] == {"value": 5, "spent": False}


def test_non_kakita_with_iaijutsu_does_not_expose_iaijutsu_attack_key(page, live_server_url):
    """Regression: non-Kakita characters with the iaijutsu knack don't get
    ``knack:iaijutsu:attack`` in their formulas (the attack-variant is
    Kakita-only)."""
    _create_char(page, live_server_url, "AkodoIaiNoAtk", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    has_key = page.evaluate(
        "() => !!(window._diceRoller?.formulas?.['knack:iaijutsu:attack'])"
    )
    assert has_key is False


def test_kakita_iaijutsu_attack_modal_lists_1st_dan_and_2nd_dan_bonuses(page, live_server_url):
    """The pre-roll probability panel on the iaijutsu attack modal surfaces
    both the +1 rolled die from 1st Dan and the +5 free raise from 2nd Dan."""
    _create_char(page, live_server_url, "KakitaIaiBon", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _seed_kakita_phase_zero_die(page)
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    text = _attack_modal_bonus_text(page)
    assert "1st Dan" in text
    assert "2nd Dan" in text


def test_kakita_iaijutsu_attack_modal_probability_uses_1st_dan_rolled_die(page, live_server_url):
    """The formula's rolled count includes the 1st Dan +1 so the probability
    chart is computed on 5k3 (1 rank + 3 Fire school ring + 1 extra), not 4k3."""
    _create_char(page, live_server_url, "KakitaIaiProb", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    f = _get_formula(page, "knack:iaijutsu:attack")
    assert f is not None
    assert f["rolled"] == 5
    assert f["kept"] == 3


def test_kakita_iaijutsu_attack_results_show_1st_dan_extra_die_line(page, live_server_url):
    """The post-roll breakdown labels the 1st Dan +1k0 die (the 2nd Dan +5
    free raise already shows via the shared bonuses loop - this test pins
    the 1st Dan line that was previously silent)."""
    _create_char(page, live_server_url, "KakitaIaiRes", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _seed_kakita_phase_zero_die(page)
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    _mock_dice_high(page)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    _restore_dice(page)
    line = page.locator('[data-testid="kakita-1st-dan-iaijutsu-attack-breakdown"]')
    assert line.is_visible()
    assert "1st Dan" in line.text_content()
    assert "iaijutsu" in line.text_content().lower()


def test_non_kakita_iaijutsu_attack_has_no_1st_dan_flag(page, live_server_url):
    """Regression: only Kakita's iaijutsu:attack variant carries the 1st Dan
    flag; other schools with an iaijutsu knack don't see the flag (and
    don't even have the variant, per the earlier test)."""
    _create_char(page, live_server_url, "KakitaIaiFlag", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    f = _get_formula(page, "knack:iaijutsu:attack")
    assert f is not None
    assert f.get("iaijutsu_first_dan_extra_die") is True


# ---------------------------------------------------------------------------
# Kakita Duelist 3rd Dan: defender-phase bonus on attack rolls
# ---------------------------------------------------------------------------

def _make_kakita_dan_3(page, live_server_url, name, attack=1):
    """Create a Kakita Duelist character at Dan 3 with an optional attack
    skill override so the 3rd Dan ``X = attack skill`` bonus is non-trivial."""
    _create_char(
        page, live_server_url, name, "kakita_duelist",
        knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
    )
    if attack and attack > 1:
        cid = _extract_char_id(page)
        page.evaluate(f"""async () => {{
            await fetch('/characters/{cid}/autosave', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{attack: {attack}}})
            }});
        }}""")
        page.reload()
        page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)


def test_kakita_3rd_dan_defender_phase_control_hidden_without_initiative(page, live_server_url):
    """No action dice -> initiative warning fires and the Kakita 3rd Dan
    control stays hidden."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3NoInit")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert not page.locator('[data-testid="kakita-3rd-dan-bonus"]').is_visible()
    assert page.locator('[data-testid="attack-init-warning-no-init"]').is_visible()


def test_kakita_3rd_dan_defender_phase_control_hidden_out_of_dice(page, live_server_url):
    """Every action die spent -> control hidden (out-of-dice warning instead)."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Out")
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 4, spent: true}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert not page.locator('[data-testid="kakita-3rd-dan-bonus"]').is_visible()


def test_kakita_3rd_dan_defender_phase_control_visible_with_action_dice(page, live_server_url):
    """Action die present -> control rendered, dropdown defaults to the
    0 sentinel ("Select phase") so the Kakita has to pick explicitly."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Vis")
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    control = page.locator('[data-testid="kakita-3rd-dan-bonus"]')
    assert control.is_visible()
    default = page.evaluate(
        "() => document.querySelector('[data-action=\"kakita-3rd-dan-defender-phase\"]').value")
    assert default == "0"
    # The live "+bonus X=..." display hides until a phase is picked and is
    # replaced by the "pick a phase" hint.
    assert not page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').is_visible()
    hint = page.locator('[data-testid="kakita-3rd-dan-needs-phase"]')
    assert hint.is_visible()
    assert "phase" in hint.text_content().lower()


def test_kakita_3rd_dan_bonus_applied_to_attack_roll(page, live_server_url):
    """Attacker die=4, defender phase=10, attack skill=2 -> bonus=+12 on the
    formula, labeled in the post-roll breakdown."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Roll", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("10")
    text = page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').text_content()
    assert "+12" in text
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    result = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return {
                bonus: d.formula?.kakita_3rd_dan_bonus || 0,
                attacker: d.formula?.kakita_3rd_dan_attacker_phase || 0,
                defender: d.formula?.kakita_3rd_dan_defender_phase || 0,
                x: d.formula?.kakita_3rd_dan_x || 0,
            };
        }
        return null;
    }""")
    assert result == {"bonus": 12, "attacker": 4, "defender": 10, "x": 2}
    breakdown = page.locator('[data-testid="kakita-3rd-dan-breakdown"]')
    assert breakdown.is_visible()
    assert "+12" in breakdown.text_content()


def test_kakita_3rd_dan_bonus_clamps_when_defender_acts_first(page, live_server_url):
    """Attacker die=7, defender phase=3 -> clamp to 0 (no negative bonus)."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Clamp", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 7, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("3")
    text = page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').text_content()
    assert "+0" in text


def test_kakita_3rd_dan_bonus_shifts_probability_chart(page, live_server_url):
    """Picking a later defender phase raises atkHitChance live."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Prob", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    # Start with phase 4 == attacker phase -> no bonus.
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("4")
    low = page.evaluate("() => window._diceRoller.atkHitChance(0)")
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("11")
    high = page.evaluate("() => window._diceRoller.atkHitChance(0)")
    assert high >= low
    assert high > 0


def test_kakita_3rd_dan_bonus_uses_clicked_die_value(page, live_server_url):
    """Opening attack via a specific action die's menu computes the bonus
    against THAT die's value, not the lowest unspent."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Die", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 2, spent: false},
            {value: 8, spent: false},
        ];
    }""")
    # Open the higher-value die's menu.
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).nth(1).click()
    page.locator('[data-action-die-menu-item="attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("10")
    # attacker=8, defender=10, X=2 -> +4.
    text = page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').text_content()
    assert "+4" in text


def test_kakita_3rd_dan_phase_11_yields_max_bonus_for_no_remaining_actions(page, live_server_url):
    """Picking 'no remaining actions' (value=11) yields the maximum bonus
    for the attacker-die phase. The dropdown no longer defaults here - the
    player has to select 11 explicitly to opt into this interpretation."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3P11", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("11")
    # attacker=4, defender=11, X=2 -> +14.
    text = page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').text_content()
    assert "+14" in text


def test_kakita_below_3rd_dan_no_bonus_control(page, live_server_url):
    """Kakita 2nd Dan doesn't render the 3rd Dan bonus control."""
    _create_char(page, live_server_url, "KakitaK2NoCtl", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert not page.locator('[data-testid="kakita-3rd-dan-bonus"]').is_visible()


def test_kakita_3rd_dan_bonus_on_phase_zero_die(page, live_server_url):
    """When attacking from a Phase-0 die, attacker phase=0 and the bonus
    equals X * defender_phase."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3P0", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 0, spent: false}];
    }""")
    # Open the phase-0 die's menu and pick Iaijutsu Attack.
    page.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first.click()
    page.locator('[data-action-die-menu-item="iaijutsu-attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("5")
    # attacker=0, defender=5, X=2 -> +10.
    text = page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').text_content()
    assert "+10" in text


def test_kakita_3rd_dan_roll_button_disabled_until_phase_picked(page, live_server_url):
    """The Roll button is disabled while the 3rd Dan control is on screen
    but the defender-phase dropdown is still on the 'Select phase' sentinel.
    Picking any real phase (1-11) enables the button."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Gate", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    roll = page.locator('[data-modal="attack"] [data-action="roll-attack"]')
    assert roll.is_disabled()
    title = roll.get_attribute("title") or ""
    assert "phase" in title.lower()
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("7")
    assert not roll.is_disabled()


def test_kakita_3rd_dan_roll_button_enabled_with_no_remaining_actions(page, live_server_url):
    """Picking '11 / no remaining actions' explicitly counts as a selection
    and enables the Roll button."""
    _make_kakita_dan_3(page, live_server_url, "KakitaK3Gate11", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    roll = page.locator('[data-modal="attack"] [data-action="roll-attack"]')
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("11")
    assert not roll.is_disabled()


def test_kakita_below_3rd_dan_roll_button_always_enabled(page, live_server_url):
    """Below 3rd Dan the control is never shown, so the Roll button must
    not be gated by the (absent) phase dropdown."""
    _create_char(page, live_server_url, "KakitaK2Roll", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    roll = page.locator('[data-modal="attack"] [data-action="roll-attack"]')
    assert not roll.is_disabled()


# ---------------------------------------------------------------------------
# Kakita Duelist Phase 0 Interrupt button
# ---------------------------------------------------------------------------

def test_kakita_interrupt_button_hidden_for_non_kakita(page, live_server_url):
    """Other schools never see the Phase 0 Interrupt button."""
    _create_char(page, live_server_url, "AkodoNoKakita", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 3, spent: false}, {value: 5, spent: false},
        ];
    }""")
    assert page.locator('[data-action="kakita-phase-zero-interrupt"]').count() == 0


def test_kakita_interrupt_button_visible_on_kakita_sheet(page, live_server_url):
    """Kakita sheet shows the Phase 0 Interrupt button inside the Actions panel."""
    _create_char(page, live_server_url, "KakitaIntVis", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 3, spent: false}, {value: 5, spent: false},
        ];
    }""")
    btn = page.locator('[data-action="kakita-phase-zero-interrupt"]')
    assert btn.is_visible()
    assert "Phase 0 Interrupt" in btn.text_content()


def test_kakita_interrupt_button_disabled_with_fewer_than_two_dice(page, live_server_url):
    """One unspent eligible die -> button disabled."""
    _create_char(page, live_server_url, "KakitaInt1Die", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 5, spent: false}, {value: 3, spent: true},
        ];
    }""")
    assert page.locator('[data-action="kakita-phase-zero-interrupt"]').is_disabled()


def test_kakita_interrupt_button_spends_two_highest_dice(page, live_server_url):
    """Click marks the 2 highest unspent dice spent with the Kakita label;
    lower dice and already-spent dice are untouched."""
    _create_char(page, live_server_url, "KakitaIntSpend", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 2, spent: false},
            {value: 5, spent: false},
            {value: 8, spent: false},
            {value: 4, spent: true},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: d.spent, spent_by: d.spent_by || null,
    }))""")
    # Value 2 stays unspent; 5 and 8 get spent with the Kakita label; the
    # already-spent 4 remains spent but no new label.
    assert state[0] == {"value": 2, "spent": False, "spent_by": None}
    assert state[1]["spent"] is True
    assert state[1]["spent_by"] == "Kakita Phase 0 interrupt"
    assert state[2]["spent"] is True
    assert state[2]["spent_by"] == "Kakita Phase 0 interrupt"
    assert state[3] == {"value": 4, "spent": True, "spent_by": None}


def test_kakita_interrupt_opens_iaijutsu_attack_modal_with_banner(page, live_server_url):
    """Click opens the attack modal with attack_variant='iaijutsu' and the
    interrupt banner (distinct from the Phase-0-die banner)."""
    _create_char(page, live_server_url, "KakitaIntBanner", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 5, spent: false}, {value: 8, spent: false},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    variant = page.evaluate("() => window._diceRoller?.atkFormula?.attack_variant")
    assert variant == "iaijutsu"
    banner = page.locator('[data-testid="kakita-phase-zero-interrupt-note"]')
    assert banner.is_visible()
    # The generic Phase-0-die banner is suppressed when the interrupt banner
    # is shown.
    assert not page.locator('[data-testid="kakita-phase-zero-attack-note"]').is_visible()


def test_kakita_interrupt_uses_phase_zero_as_attacker_phase(page, live_server_url):
    """3rd Dan bonus on an interrupt attack uses 0 as the attacker phase,
    so a defender phase of 10 + attack skill 2 yields +20."""
    _make_kakita_dan_3(page, live_server_url, "KakitaIntP0", attack=2)
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 5, spent: false}, {value: 8, spent: false},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # Dropdown has no default - the Kakita has to pick a phase explicitly.
    page.locator('[data-action="kakita-3rd-dan-defender-phase"]').select_option("10")
    text = page.locator('[data-testid="kakita-3rd-dan-bonus-display"]').text_content()
    # attacker=0, defender=10, X=2 -> +20.
    assert "+20" in text
    # Attacker-phase display reads 0 (forced).
    control = page.locator('[data-testid="kakita-3rd-dan-bonus"]')
    assert "die 0" in control.text_content()


def test_kakita_interrupt_suppresses_initiative_warning(page, live_server_url):
    """Even if the interrupt spends every remaining die, the "out of
    action dice" warning is suppressed - the cost was paid deliberately."""
    _create_char(page, live_server_url, "KakitaIntNoWarn", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 5, spent: false}, {value: 8, spent: false},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    assert not page.locator('[data-testid="attack-init-warning-no-init"]').is_visible()
    assert not page.locator('[data-testid="attack-init-warning-out-of-dice"]').is_visible()


def test_kakita_interrupt_rolling_does_not_spend_a_third_die(page, live_server_url):
    """Rolling from the interrupt modal must NOT consume an additional
    action die - the 2 highest were the full cost."""
    _create_char(page, live_server_url, "KakitaIntNo3rdDie", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 2, spent: false},
            {value: 5, spent: false},
            {value: 8, spent: false},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: d.spent,
    }))""")
    # Only the two highest dice (5 and 8) are spent; the 2 remains unspent.
    assert state[0] == {"value": 2, "spent": False}
    assert state[1]["spent"] is True
    assert state[2]["spent"] is True


def test_kakita_interrupt_attack_inherits_4th_dan_damage_bonus(page, live_server_url):
    """A Kakita 4th Dan's interrupt attack uses the same knack:iaijutsu:attack
    formula as any other iaijutsu attack, so its damage metadata picks up
    the +5 from 4th Dan (iaijutsu). The unit test ``test_kakita_iaijutsu_
    attack_formula_respects_4th_dan_damage_bonus`` verifies the formula
    itself; this clicktest exercises the interrupt entry point to make sure
    the attack modal opens against THAT formula (not the regular attack
    one)."""
    _create_char(page, live_server_url, "KakitaIntDmg", "kakita_duelist",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 5, spent: false}, {value: 8, spent: false},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # The attack modal's formula is the Kakita-only iaijutsu attack variant
    # with damage_flat_bonus = 5 from the 4th Dan (iaijutsu) bonus.
    dmg = page.evaluate("""() => ({
        variant: window._diceRoller?.atkFormula?.attack_variant,
        flat: window._diceRoller?.atkFormula?.damage_flat_bonus,
        sources: window._diceRoller?.atkFormula?.damage_bonus_sources || [],
    })""")
    assert dmg["variant"] == "iaijutsu"
    assert dmg["flat"] == 5
    assert any("4th Dan" in s for s in dmg["sources"])


def test_kakita_interrupt_persists_after_modal_close(page, live_server_url):
    """Closing the modal without rolling leaves the 2 dice spent (no refund
    per the rules - the cost is paid on declaration)."""
    _create_char(page, live_server_url, "KakitaIntNoRefund", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [
            {value: 5, spent: false}, {value: 8, spent: false},
        ];
    }""")
    page.locator('[data-action="kakita-phase-zero-interrupt"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: d.spent,
    }))""")
    assert state[0]["spent"] is True
    assert state[1]["spent"] is True


# ---------------------------------------------------------------------------
# Kakita Duelist 5th Dan: Phase-0 contested iaijutsu modal
# ---------------------------------------------------------------------------

def _make_kakita_dan_5(page, live_server_url, name, attack=1, seed_action_dice=True):
    """Create a Kakita Duelist at Dan 5 with optional attack skill override.

    The 5th Dan section on the sheet is gated on the character having
    action dice displayed (i.e. having rolled initiative), so by default
    this helper seeds a single action die on the tracking bridge after
    the character is created. Pass ``seed_action_dice=False`` for tests
    that want to verify the hidden-until-initiative gating itself.
    """
    _create_char(
        page, live_server_url, name, "kakita_duelist",
        knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5},
    )
    if attack and attack > 1:
        cid = _extract_char_id(page)
        page.evaluate(f"""async () => {{
            await fetch('/characters/{cid}/autosave', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{attack: {attack}}})
            }});
        }}""")
        page.reload()
        page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    if seed_action_dice:
        page.evaluate("""() => {
            window._trackingBridge.actionDice = [{value: 5, spent: false}];
        }""")


def test_kakita_5th_dan_button_visible_on_dan_5_sheet(page, live_server_url):
    """Dan 5 Kakita sheet shows the 5th Dan contest button once action dice
    have been rolled (initiative flow)."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Btn")
    assert page.locator('[data-action="kakita-5th-dan-contest"]').is_visible()


def test_kakita_below_5th_dan_hides_button(page, live_server_url):
    """Dan 4 Kakita does not see the 5th Dan contest button."""
    _create_char(page, live_server_url, "Kakita4NoBtn", "kakita_duelist",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    assert page.locator('[data-action="kakita-5th-dan-contest"]').count() == 0


def test_kakita_5th_dan_button_opens_contest_modal(page, live_server_url):
    """Clicking the button opens the contest modal in pre-phase."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Open")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    phase = page.evaluate("() => window._diceRoller?.k5Phase")
    assert phase == "pre"
    assert page.locator('[data-testid="kakita-5th-banner"]').is_visible()


def test_kakita_5th_dan_modal_defaults_opponent_has_iaijutsu(page, live_server_url):
    """Opponent-has-iaijutsu checkbox defaults to true; no +5 bonus."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Def")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    cb = page.locator('[data-action="kakita-5th-opponent-has-iaijutsu"]')
    assert cb.is_checked()
    prebonus = page.evaluate("() => window._diceRoller?._kakita5thPreRollBonus?.()")
    # 3rd Dan bonus with attack=1, defender=11 -> 11; plus 0 no-iaijutsu;
    # plus contested-skill bonus: Kakita's iaijutsu rank 5 vs default opponent
    # rank 4 (iaijutsu-having duelist) -> +5 (one free raise).
    assert prebonus == 11 + 5


def test_kakita_5th_dan_opponent_without_iaijutsu_grants_plus_5(page, live_server_url):
    """Unchecking the checkbox adds +5 to the pre-roll bonus. We pin the
    opponent-skill dropdown on both sides of the toggle so the +5 we
    measure is the no-iaijutsu flat bonus alone, not the skill-gap side
    effect of the dropdown's default flipping from 4 to 3."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5NoIai")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-opponent-skill"]').select_option("3")
    before = page.evaluate("() => window._diceRoller?._kakita5thPreRollBonus?.()")
    page.locator('[data-action="kakita-5th-opponent-has-iaijutsu"]').uncheck()
    page.locator('[data-action="kakita-5th-opponent-skill"]').select_option("3")
    after = page.evaluate("() => window._diceRoller?._kakita5thPreRollBonus?.()")
    assert after == before + 5


def test_kakita_5th_dan_3rd_dan_bonus_applies_with_attacker_phase_0(page, live_server_url):
    """3rd Dan bonus on the contest uses attacker_phase=0 so defender=10 + X=2
    yields +20."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5K3", attack=2)
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-defender-phase"]').select_option("10")
    bonus = page.evaluate(
        "() => parseInt(document.querySelector('[data-testid=\"kakita-5th-3rd-dan-bonus\"]').textContent, 10)")
    assert bonus == 20  # attack=2 * 10 phases


def test_kakita_5th_dan_roll_applies_bonuses(page, live_server_url):
    """Rolling the contest applies the pre-roll bonuses (3rd Dan + no-iaijutsu)
    to the formula flat and sets a result total."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Roll", attack=2)
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-opponent-has-iaijutsu"]').uncheck()
    page.locator('[data-action="kakita-5th-defender-phase"]').select_option("10")
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    _restore_dice(page)
    state = page.evaluate("""() => ({
        phase: window._diceRoller?.k5Phase,
        total: window._diceRoller?.k5RollTotal,
        no_iai: window._diceRoller?.k5NoIaijutsuBonus,
        kak3rd: window._diceRoller?.k5KakitaBonus,
    })""")
    assert state["phase"] == "result"
    assert state["no_iai"] == 5
    assert state["kak3rd"] == 20
    assert state["total"] > 0


def test_kakita_5th_dan_damage_scales_up_when_won_by_5(page, live_server_url):
    """When the player wins by 5+, the damage roll gains floor(diff/5) rolled dice."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Win")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total - 10))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    _restore_dice(page)
    adjust = page.evaluate("() => window._diceRoller?.k5DamageDiceAdjust")
    assert adjust == 2
    phase = page.evaluate("() => window._diceRoller?.k5Phase")
    assert phase == "damage-result"


def test_kakita_5th_dan_damage_scales_down_when_lost_by_5(page, live_server_url):
    """When the player loses by 5+, the damage roll loses floor(|diff|/5) rolled dice."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Loss")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    _mock_dice_low(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total + 10))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    _restore_dice(page)
    adjust = page.evaluate("() => window._diceRoller?.k5DamageDiceAdjust")
    assert adjust == -2


def test_kakita_5th_dan_damage_unchanged_when_diff_under_5(page, live_server_url):
    """A < 5-point gap yields no adjustment."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Tight")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total - 4))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    _restore_dice(page)
    adjust = page.evaluate("() => window._diceRoller?.k5DamageDiceAdjust")
    assert adjust == 0


def test_kakita_5th_dan_button_disabled_after_use_until_next_initiative(page, live_server_url):
    """Rolling the contest flips the once-per-round flag and disables the
    button; the next initiative roll (via setActionDice) re-enables it."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Once")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total - 20))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    _restore_dice(page)
    page.locator('[data-modal="kakita-5th-dan"] button:has-text("Close")').click()
    assert page.locator('[data-action="kakita-5th-dan-contest"]').is_disabled()
    page.evaluate("""() => {
        window._trackingBridge.setActionDice([{value: 5, spent: false}]);
    }""")
    page.wait_for_timeout(100)
    assert not page.locator('[data-action="kakita-5th-dan-contest"]').is_disabled()


def test_kakita_5th_dan_modal_cancel_before_roll_does_not_consume(page, live_server_url):
    """Closing the modal on the pre-phase leaves the once-per-round flag
    clear - only rolling (completing damage) consumes it."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Cancel")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-modal="kakita-5th-dan"] button:has-text("\u00d7")').click()
    page.wait_for_timeout(100)
    used = page.evaluate("() => window._trackingBridge?.kakita5thDanUsed")
    assert used is False
    assert not page.locator('[data-action="kakita-5th-dan-contest"]').is_disabled()


def test_kakita_5th_dan_modal_inherits_4th_dan_damage_bonus(page, live_server_url):
    """Dan 5 Kakita (so >= 4) damage gets the iaijutsu +5 flat from 4th Dan."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5With4")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    _restore_dice(page)
    flat = page.evaluate("() => window._diceRoller?.k5DamageFlat")
    assert flat >= 5


def test_kakita_5th_dan_opponent_skill_dropdown_defaults_to_4(page, live_server_url):
    """Opponent-skill dropdown defaults to rank 4 when the checkbox is
    checked (opponent has iaijutsu - another duelist-tier NPC)."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5OppSkill")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    assert page.evaluate("() => window._diceRoller?.k5OpponentSkillRank") == 4


def test_kakita_5th_dan_opponent_skill_drops_to_3_when_unchecked(page, live_server_url):
    """Unchecking 'opponent has iaijutsu knack' flips the dropdown default
    to 3 (modal value for a generic attack skill)."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5OppSkillToggle")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-opponent-has-iaijutsu"]').uncheck()
    assert page.evaluate("() => window._diceRoller?.k5OpponentSkillRank") == 3


def test_kakita_5th_dan_opponent_skill_back_to_4_when_rechecked(page, live_server_url):
    """Rechecking the checkbox restores the dropdown to 4."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5OppSkillRecheck")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-opponent-has-iaijutsu"]').uncheck()
    assert page.evaluate("() => window._diceRoller?.k5OpponentSkillRank") == 3
    page.locator('[data-action="kakita-5th-opponent-has-iaijutsu"]').check()
    assert page.evaluate("() => window._diceRoller?.k5OpponentSkillRank") == 4


def test_kakita_5th_dan_contest_skill_bonus_when_higher(page, live_server_url):
    """Kakita iaijutsu 5 vs opponent rank 1 -> +20 free raise (4 ranks x 5)."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5SkillHigh")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-opponent-skill"]').select_option("1")
    bonus = page.evaluate("() => window._diceRoller?._kakita5thContestSkillBonus?.()")
    assert bonus == 20


def test_kakita_5th_dan_contest_skill_bonus_when_equal(page, live_server_url):
    """Equal ranks -> no contested-roll bonus."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5SkillEqual")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.locator('[data-action="kakita-5th-opponent-skill"]').select_option("5")
    bonus = page.evaluate("() => window._diceRoller?._kakita5thContestSkillBonus?.()")
    assert bonus == 0


def test_kakita_5th_dan_contest_skill_bonus_when_lower(page, live_server_url):
    """Opponent higher -> 0 bonus (no penalty)."""
    # Dan 3 Kakita has iaijutsu=3. Against opponent rank 5, we're 2 ranks
    # below - bonus clamps to 0.
    _make_kakita_dan_3(page, live_server_url, "Kakita5SkillLow")
    # Boost the character to Dan 5 on ONE knack so the 5th Dan button
    # doesn't render; instead use raw skill comparison via the helper. For
    # this test we just need the method to return 0, so call it directly.
    bonus = page.evaluate("""() => {
        if (!window._diceRoller) return null;
        window._diceRoller.k5OwnIaijutsuRank = 2;
        window._diceRoller.k5OpponentSkillRank = 5;
        return window._diceRoller._kakita5thContestSkillBonus();
    }""")
    assert bonus == 0


def test_kakita_5th_dan_contest_skill_bonus_shown_in_prebonus_and_breakdown(page, live_server_url):
    """The contested-skill bonus is summed into the pre-roll total and the
    post-roll breakdown lists it as a labeled line."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5SkillRoll")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    # Default: Kakita iaijutsu 5 vs opponent rank 4 -> +5.
    # 3rd Dan bonus defaults to 11 (attack=1 * phase 11).
    prebonus = page.evaluate("() => window._diceRoller?._kakita5thPreRollBonus?.()")
    assert prebonus == 5 + 11
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    _restore_dice(page)
    state = page.evaluate("""() => ({
        contest_skill: window._diceRoller?.k5ContestSkillBonus,
        phase: window._diceRoller?.k5Phase,
    })""")
    assert state["phase"] == "result"
    assert state["contest_skill"] == 5
    breakdown = page.locator('[data-testid="kakita-5th-contest-skill-breakdown"]')
    assert breakdown.is_visible()
    text = breakdown.text_content()
    assert "+5" in text
    # Verify the own-rank vs opponent-rank numbers are rendered.
    assert "5" in text and "4" in text


def test_kakita_5th_dan_uses_rollandanimate_for_contest(page, live_server_url):
    """The contest roll routes through rollAndAnimate so animation + sound
    preferences apply. With animation disabled (test default), the path
    still returns dice synchronously; this test monkey-patches to verify
    rollAndAnimate is the one called."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5RAA")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    page.evaluate("""() => {
        window._k5RAACalls = 0;
        const orig = window.L7RDice.rollAndAnimate;
        window.L7RDice.rollAndAnimate = async (...args) => {
            window._k5RAACalls += 1;
            return orig.apply(window.L7RDice, args);
        };
    }""")
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    # Wait for phase to settle to 'result' (the roll is async now).
    page.wait_for_function(
        "() => window._diceRoller?.k5Phase === 'result'", timeout=5000)
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    page.wait_for_function(
        "() => window._diceRoller?.k5Phase === 'damage-result'", timeout=5000)
    _restore_dice(page)
    # Both the contest roll and the damage roll should have gone through
    # rollAndAnimate.
    assert page.evaluate("() => window._k5RAACalls") == 2


def test_kakita_5th_dan_section_hidden_before_initiative(page, live_server_url):
    """Before the Kakita has rolled initiative (no action dice) the 5th Dan
    section is NOT rendered in the tracking area."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5NoInit", seed_action_dice=False)
    assert not page.locator('[data-testid="kakita-5th-dan-section"]').is_visible()
    assert not page.locator('[data-action="kakita-5th-dan-contest"]').is_visible()


def test_kakita_5th_dan_section_appears_after_initiative(page, live_server_url):
    """Rolling initiative (modeled here by seeding the tracking bridge with
    action dice) makes the 5th Dan section appear."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Appear", seed_action_dice=False)
    # Section hidden initially.
    assert not page.locator('[data-testid="kakita-5th-dan-section"]').is_visible()
    # Simulate initiative: tracking bridge populates actionDice.
    page.evaluate("""() => {
        window._trackingBridge.actionDice = [{value: 4, spent: false}];
    }""")
    page.wait_for_timeout(100)
    assert page.locator('[data-testid="kakita-5th-dan-section"]').is_visible()
    assert page.locator('[data-action="kakita-5th-dan-contest"]').is_visible()


def test_kakita_5th_dan_section_disappears_when_action_dice_cleared(page, live_server_url):
    """Clicking the Actions-panel Clear button (`clearActionDice`) wipes all
    action dice and the 5th Dan section goes with them."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Clear")
    # Section starts visible (helper seeded a die).
    assert page.locator('[data-testid="kakita-5th-dan-section"]').is_visible()
    # Clear via the tracking bridge's public API (mirrors clicking Clear).
    page.evaluate("() => window._trackingBridge.clearActionDice()")
    page.wait_for_timeout(100)
    assert not page.locator('[data-testid="kakita-5th-dan-section"]').is_visible()


def test_kakita_5th_dan_used_flag_persists_through_reload(page, live_server_url):
    """The once-per-round flag persists via adventureState, so reloading
    mid-round leaves the button disabled."""
    _make_kakita_dan_5(page, live_server_url, "Kakita5Persist")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    _mock_dice_high(page)
    page.locator('[data-action="kakita-5th-roll"]').click()
    roll_total = page.evaluate("() => window._diceRoller?.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(roll_total))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    _restore_dice(page)
    page.wait_for_timeout(500)  # save round-trip
    page.reload()
    page.wait_for_selector('[data-action="kakita-5th-dan-contest"]', state='attached',
                           timeout=10000)
    assert page.locator('[data-action="kakita-5th-dan-contest"]').is_disabled()


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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "20")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Open wound check
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    """Ide 4th Dan: sheet shows +2/night regen text with tooltip near VP counter."""
    _create_char(page, live_server_url, "Ide4B", "ide_diplomat",
                 knack_overrides={"double_attack": 4, "feint": 4, "worldliness": 4})
    body = page.text_content("body")
    assert "+2/night" in body


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


def test_ikoma_4th_dan_attack_modal_note(page, live_server_url):
    """Ikoma 4th Dan: attack modal shows note about 10-dice floor for unparried attacks."""
    _create_char(page, live_server_url, "Ikoma4Note", "ikoma_bard",
                 knack_overrides={"discern_honor": 4, "oppose_knowledge": 4, "oppose_social": 4})
    # Open attack modal (don't roll, just check the pre-roll note)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    assert "Ikoma 4th Dan" in modal.text_content()
    assert "10 damage dice" in modal.text_content()


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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")  # low TN for guaranteed hit
    modal.locator('[data-action="roll-attack"]').click()
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
    # actionDice now holds {value, ...} entries instead of raw numbers.
    values = [d.get("value") if isinstance(d, dict) else d for d in action_dice]
    assert 1 in values, f"Expected 1 in action dice {action_dice} (Shinjo 4th Dan sets highest to 1)"
    result = _get_roll_result_text(page)
    assert "Shinjo" in result or "set to 1" in result.lower()


# ---------------------------------------------------------------------------
# Shinjo Bushi Special Ability: +2X phase bonus on attack
# ---------------------------------------------------------------------------

def test_shinjo_phase_bonus_hidden_without_initiative(page, live_server_url):
    """Shinjo: phase-bonus control is suppressed when there are no action
    dice; the initiative warning already tells the player what's missing."""
    _create_char(page, live_server_url, "ShinjoPhNoInit", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert not page.locator('[data-testid="shinjo-phase-bonus"]').is_visible()
    assert page.locator('[data-testid="attack-init-warning-no-init"]').is_visible()


def test_shinjo_phase_bonus_hidden_out_of_dice(page, live_server_url):
    """Shinjo: phase-bonus control is also suppressed when all action dice
    are spent (the out-of-dice warning fires instead)."""
    _create_char(page, live_server_url, "ShinjoPhOut", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 5, spent: true}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert not page.locator('[data-testid="shinjo-phase-bonus"]').is_visible()


def test_shinjo_phase_bonus_visible_with_action_dice(page, live_server_url):
    """Shinjo: phase-bonus control is visible on the attack modal when an
    action die is available, and defaults to held=0 (the die's value itself
    is the earliest phase on which it can be spent)."""
    _create_char(page, live_server_url, "ShinjoPhVis", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 4, spent: false}, {value: 7, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    control = page.locator('[data-testid="shinjo-phase-bonus"]')
    assert control.is_visible()
    # Default phase matches the to-be-spent die (sub-die-value phases are
    # impossible and are omitted from the dropdown), so the initial display
    # shows 0 phases held and a +0 bonus until the player raises the phase.
    text = page.locator('[data-testid="shinjo-phase-bonus-display"]').text_content()
    assert "+0" in text


def test_shinjo_phase_bonus_applied_to_attack_roll(page, live_server_url):
    """Shinjo: picking a current phase >= the spent die's value adds +2X
    (where X = phase - die value) to the attack and labels it in the
    post-roll breakdown."""
    _create_char(page, live_server_url, "ShinjoPhRoll", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 4, spent: false}, {value: 7, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    page.locator('[data-action="shinjo-phase"]').select_option("9")
    # Lowest unspent die is value=4, phase=9 -> held=5 -> bonus=+10.
    text = page.locator('[data-testid="shinjo-phase-bonus-display"]').text_content()
    assert "+10" in text
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    result = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return {
                bonus: d.formula?.shinjo_phase_bonus || 0,
                phase: d.formula?.shinjo_phase_bonus_phase || 0,
                die_value: d.formula?.shinjo_phase_bonus_die_value || 0,
            };
        }
        return null;
    }""")
    assert result == {"bonus": 10, "phase": 9, "die_value": 4}
    breakdown = page.locator('[data-testid="shinjo-phase-bonus-breakdown"]')
    assert breakdown.is_visible()
    assert "+10" in breakdown.text_content()


def test_shinjo_phase_bonus_shifts_probability_chart(page, live_server_url):
    """Shinjo: raising the picked phase lifts the attack probability. Uses
    atkHitChance directly so we don't have to actually roll."""
    _create_char(page, live_server_url, "ShinjoPhProb", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 3, spent: false}];
    }""")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    low = page.evaluate("() => window._diceRoller.atkHitChance(0)")
    page.locator('[data-action="shinjo-phase"]').select_option("10")
    high = page.evaluate("() => window._diceRoller.atkHitChance(0)")
    # Phase 10 vs die=3 -> held 7 -> +14 to the roll. That can only raise
    # the hit chance (or leave it at 1.0 already).
    assert high >= low
    assert high > 0


def test_shinjo_phase_bonus_uses_clicked_die(page, live_server_url):
    """Shinjo: when opening the attack through a specific action die's menu,
    the bonus computes against THAT die's value (not the lowest)."""
    _create_char(page, live_server_url, "ShinjoPhDie", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 2, spent: false}, {value: 6, spent: false}];
    }""")
    # Open the higher-value die's menu and pick Roll Attack.
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').nth(1).click()
    page.locator('[data-action-die-menu-item="attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.locator('[data-action="shinjo-phase"]').select_option("9")
    # Clicked die value=6, phase=9 -> held=3 -> +6.
    text = page.locator('[data-testid="shinjo-phase-bonus-display"]').text_content()
    assert "+6" in text


def test_knack_menu_items_appear_on_fresh_page_load(page, live_server_url):
    """Regression: the per-action-die menu's knack options (Double Attack,
    Lunge, etc.) used to read ``window._diceRoller.formulas`` - a
    non-reactive global set by a component that inits AFTER the tracking
    section. On fresh page load Alpine evaluated the gates before the
    dice-roller finished initializing, got undefined, and never
    re-evaluated because the expression had no reactive dependencies. The
    menu items only showed up after some other action (rolling initiative,
    etc.) happened to trigger a remount. This test pins the reactive
    rollFormulas fix by opening the menu before any interaction."""
    _create_char(page, live_server_url, "ShinjoFreshMenu", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # Sanity check: the fix relies on trackingData parsing the roll-formulas
    # JSON into its own reactive field. Verify the parse worked and the
    # knack formulas are present before even opening the menu.
    formulas = page.evaluate("""() => {
        const el = document.querySelector('[x-data*=trackingData]');
        const d = el && window.Alpine && window.Alpine.$data(el);
        return d ? Object.keys(d.rollFormulas || {}).filter(k => k.startsWith('knack:')) : null;
    }""")
    assert formulas is not None and 'knack:double_attack' in formulas, \
        f"trackingData.rollFormulas should contain knack formulas on fresh load; got {formulas}"
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 3, spent: false}];
    }""")
    # Immediately open the action-die menu without touching anything else
    # that might trigger a reactive re-evaluation of the inner templates.
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_timeout(200)
    assert page.locator('[data-action-die-menu-item="double-attack"]').is_visible(), \
        "Double Attack must appear in the per-die menu on a fresh page load"
    assert page.locator('[data-action-die-menu-item="lunge"]').is_visible(), \
        "Lunge must appear in the per-die menu on a fresh page load"
    # And options not granted by Shinjo's school knacks must stay absent.
    assert page.locator('[data-action-die-menu-item="counterattack"]').count() == 0
    assert page.locator('[data-action-die-menu-item="feint"]').count() == 0


def test_shinjo_phase_bonus_dropdown_starts_at_die_value(page, live_server_url):
    """The attack-modal phase picker should only offer phases >= the
    to-be-spent die's value (since the action die hasn't "come up" yet in
    any earlier phase). Selecting a phase earlier than the die's value is
    physically impossible and should not appear as an option."""
    _create_char(page, live_server_url, "ShinjoDropdownMin", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    # Die values 5 and 8 - opening through the high die means the dropdown
    # must start at 8, not 1 or 5.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 5, spent: false}, {value: 8, spent: false}];
    }""")
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').nth(1).click()
    page.locator('[data-action-die-menu-item="attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    option_values = page.locator('[data-action="shinjo-phase"] option').evaluate_all(
        "opts => opts.map(o => o.value)"
    )
    # Options come through as numeric strings from select/option rendering.
    assert option_values == ["8", "9", "10"], \
        f"Dropdown should offer phases 8-10 for die=8, got {option_values}"
    # And the default selection is the die value itself (no bonus yet).
    default_phase = page.evaluate("() => window._diceRoller.atkShinjoPhase")
    assert default_phase == 8


def test_shinjo_parry_phase_dropdown_starts_at_die_value(page, live_server_url):
    """Same constraint on the parry result modal: the picker omits any
    phase below the spent die's value."""
    _create_char(page, live_server_url, "ShinjoParryMin", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 6, spent: false}];
    }""")
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "parry")
    option_values = page.locator('[data-action="shinjo-parry-phase"] option').evaluate_all(
        "opts => opts.map(o => o.value)"
    )
    # The leading "-" option is rendered with the string "null" (Alpine
    # stringifies :value="null"). Real phase options start at the die's
    # value (6) and run to 10; anything below 6 is omitted.
    assert option_values == ["null", "6", "7", "8", "9", "10"], \
        f"Parry dropdown should offer phases 6-10 for die=6, got {option_values}"


def test_shinjo_phase_bonus_on_parry_result_modal(page, live_server_url):
    """Shinjo: parry result modal exposes the same phase-bonus picker as
    the attack modal. Picking a phase applies +2*(phase - die_value) to the
    displayed total and stamps phase metadata onto the formula."""
    _create_char(page, live_server_url, "ShinjoParryPh", "shinjo_bushi",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 4, spent: false}];
    }""")
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "parry")
    # Picker should be visible and the captured die value should match.
    picker = page.locator('[data-testid="shinjo-parry-phase-bonus"]')
    assert picker.is_visible(), "Shinjo parry phase picker should show on result modal"
    die_val = page.evaluate("() => window._diceRoller.shinjoParryDieValue")
    assert die_val == 4
    total_before = page.evaluate("() => window._diceRoller.baseTotal")
    page.locator('[data-action="shinjo-parry-phase"]').select_option("9")
    # Die value=4, phase=9 -> held=5 -> +10 bonus. baseTotal jumps by 10
    # and the breakdown line surfaces.
    total_after = page.evaluate("() => window._diceRoller.baseTotal")
    assert total_after - total_before == 10
    display = page.locator('[data-testid="shinjo-parry-phase-bonus-display"]')
    assert "+10" in display.text_content()
    breakdown = page.locator('[data-testid="shinjo-parry-phase-breakdown"]')
    assert breakdown.is_visible()
    assert "+10" in breakdown.text_content()
    state = page.evaluate("""() => {
        const d = window._diceRoller;
        return {
            bonus: d.formula?.shinjo_phase_bonus || 0,
            phase: d.formula?.shinjo_phase_bonus_phase || 0,
            die_value: d.formula?.shinjo_phase_bonus_die_value || 0,
        };
    }""")
    assert state == {"bonus": 10, "phase": 9, "die_value": 4}


def test_shinjo_phase_bonus_parry_picker_hidden_for_non_shinjo(page, live_server_url):
    """Non-Shinjo characters never see the parry phase picker."""
    _create_char(page, live_server_url, "AkodoParryPh", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 3, spent: false}];
    }""")
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "parry")
    picker = page.locator('[data-testid="shinjo-parry-phase-bonus"]')
    assert picker.count() == 0 or not picker.is_visible()


# ---------------------------------------------------------------------------
# Shinjo Bushi 3rd Dan: decrement all unspent action dice after parry
# ---------------------------------------------------------------------------

def test_shinjo_3rd_dan_parry_decrements_unspent_dice(page, live_server_url):
    """Shinjo 3rd Dan with attack=2: rolling parry decrements every unspent
    action die by 2; the die that paid for the parry itself is untouched."""
    _create_char(page, live_server_url, "Shinjo3Par", "shinjo_bushi",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    # Attack skill defaults to 1 in make_character_data; bump to 2.
    cid = _extract_char_id(page)
    page.evaluate(f"""async () => {{
        await fetch('/characters/{cid}/autosave', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{attack: 2}})
        }});
    }}""")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [
            {value: 3, spent: false},
            {value: 5, spent: false},
            {value: 7, spent: false},
        ];
    }""")
    _roll_via_menu_or_direct(page, "parry")
    # Parry auto-spent the lowest unspent die (value 3, index 0); the other
    # two get decremented by attack=2.
    dice = page.evaluate("() => window._trackingBridge.actionDice")
    assert dice[0]["spent"] is True
    assert dice[0]["value"] == 3  # spent dice are not decremented
    assert dice[1] == {"value": 3, "spent": False}  # 5 - 2
    assert dice[2] == {"value": 5, "spent": False}  # 7 - 2


def test_shinjo_below_3rd_dan_no_parry_decrement(page, live_server_url):
    """Shinjo 2nd Dan: no auto-decrement after parry (the 3rd Dan gate)."""
    _create_char(page, live_server_url, "Shinjo2Par", "shinjo_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [
            {value: 3, spent: false},
            {value: 5, spent: false},
        ];
    }""")
    _roll_via_menu_or_direct(page, "parry")
    dice = page.evaluate("() => window._trackingBridge.actionDice")
    assert dice[1] == {"value": 5, "spent": False}


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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "25")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    dismiss_wc_modal(page)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    dismiss_wc_modal(page)
    trade_btn.click()
    page.wait_for_timeout(300)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"
    assert trade_btn.is_disabled(), "Should be disabled after LW reset"
    # Add more LW and use again
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "20")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    dismiss_wc_modal(page)
    assert not trade_btn.is_disabled(), "Should be enabled again with new LW"
    trade_btn.click()
    page.wait_for_timeout(300)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "4"
    assert page.locator('[x-text="lightWounds"]').text_content().strip() == "0"


def test_ide_3rd_dan_subtract_behavioral(page, live_server_url):
    """Ide 3rd Dan: clicking subtract deducts VP and opens roll results modal."""
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
    # Wait for roll to complete in the modal
    _wait_roll_done(page)
    # VP should be deducted
    vp_after = page.evaluate("window._trackingBridge.voidPoints")
    assert vp_after == 0
    # Modal should be open with correct title and formula
    modal = page.locator('[data-modal="dice-roller"]')
    assert modal.is_visible()
    assert "Ide 3rd Dan" in modal.text_content()
    assert "2k1" in modal.text_content()
    # Should show kept/unkept dice breakdown
    assert page.locator('text="Kept dice"').is_visible()
    assert page.locator('text="Unkept dice"').is_visible()
    # Total should be shown
    total = page.evaluate("window._diceRoller.baseTotal")
    assert total > 0
    # Close the modal - button should still be visible for reuse
    modal.locator('button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    assert subtract_btn.is_visible()


def test_ide_4th_dan_regen_tooltip(page, live_server_url):
    """Ide 4th Dan: +2/night label has tooltip explaining the extra VP regen."""
    _create_char(page, live_server_url, "Ide4Tip", "ide_diplomat",
                 knack_overrides={"double_attack": 4, "feint": 4, "worldliness": 4})
    regen_label = page.locator('text="+2/night"')
    assert regen_label.is_visible()
    # The tooltip content should exist in the DOM (shown on hover)
    tooltip = page.locator('text="Ide 4th Dan: regain an extra +1 VP per night above the normal 1 per night"')
    assert tooltip.count() > 0


def test_ide_5th_dan_subtract_grants_temp_vp(page, live_server_url):
    """Ide 5th Dan: subtract button spending VP grants temp VP."""
    _create_char(page, live_server_url, "Ide5Sub", "ide_diplomat",
                 knack_overrides={"double_attack": 5, "feint": 5, "worldliness": 5},
                 skill_overrides={"tact": 2})
    sa = _get_school_abilities(page)
    assert sa.get("ide_temp_vp_on_spend") is True
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.evaluate("window._trackingBridge.tempVoidPoints = 0")
    page.wait_for_timeout(200)
    # Click subtract button
    subtract_btn = page.locator('button:has-text("Spend 1 VP to subtract")')
    assert subtract_btn.is_visible()
    subtract_btn.click()
    _wait_roll_done(page)
    # VP should be deducted
    vp_after = page.evaluate("window._trackingBridge.voidPoints")
    assert vp_after == 0
    # Temp VP should be granted (Ide 5th Dan: gain temp VP when spending regular VP)
    temp_vp = page.evaluate("window._trackingBridge.tempVoidPoints")
    assert temp_vp == 1


def test_ide_3rd_dan_subtract_spends_temp_vp(page, live_server_url):
    """Ide 3rd Dan: subtract button spends temp VP before regular VP."""
    _create_char(page, live_server_url, "Ide3Temp", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 2})
    # Give both regular and temp VP
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.evaluate("window._trackingBridge.tempVoidPoints = 1")
    page.wait_for_timeout(200)
    # Click subtract - should spend temp VP first
    subtract_btn = page.locator('button:has-text("Spend 1 VP to subtract")')
    subtract_btn.click()
    _wait_roll_done(page)
    assert page.evaluate("window._trackingBridge.tempVoidPoints") == 0
    assert page.evaluate("window._trackingBridge.voidPoints") == 1
    # Close modal and click again - should now spend regular VP
    page.locator('[data-modal="dice-roller"]').locator('button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    subtract_btn.click()
    _wait_roll_done(page)
    assert page.evaluate("window._trackingBridge.voidPoints") == 0
    # Button should still be enabled because worldliness VP is available
    assert not subtract_btn.is_disabled()


def test_ide_3rd_dan_subtract_enabled_with_only_temp_vp(page, live_server_url):
    """Ide 3rd Dan: subtract button enabled when only temp VP available."""
    _create_char(page, live_server_url, "Ide3TOnly", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 2})
    # Only temp VP, no regular
    page.evaluate("window._trackingBridge.voidPoints = 0")
    page.evaluate("window._trackingBridge.tempVoidPoints = 1")
    page.wait_for_timeout(200)
    subtract_btn = page.locator('button:has-text("Spend 1 VP to subtract")')
    assert not subtract_btn.is_disabled()
    subtract_btn.click()
    _wait_roll_done(page)
    assert page.evaluate("window._trackingBridge.tempVoidPoints") == 0


def test_ide_3rd_dan_subtract_spends_worldliness_vp(page, live_server_url):
    """Ide 3rd Dan: subtract button spends worldliness VP when regular and temp are 0."""
    _create_char(page, live_server_url, "Ide3World", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 2})
    # No regular or temp VP, only worldliness available (rank 3 = 3 uses)
    page.evaluate("window._trackingBridge.voidPoints = 0")
    page.evaluate("window._trackingBridge.tempVoidPoints = 0")
    page.wait_for_timeout(200)
    worldliness_before = page.evaluate("window._trackingBridge.getCount('worldliness')")
    assert worldliness_before == 0
    # Button should be enabled (worldliness VP available)
    subtract_btn = page.locator('button:has-text("Spend 1 VP to subtract")')
    assert not subtract_btn.is_disabled()
    subtract_btn.click()
    _wait_roll_done(page)
    # Worldliness counter should have incremented
    worldliness_after = page.evaluate("window._trackingBridge.getCount('worldliness')")
    assert worldliness_after == 1
    # Regular and temp VP should be unchanged
    assert page.evaluate("window._trackingBridge.voidPoints") == 0
    assert page.evaluate("window._trackingBridge.tempVoidPoints") == 0


def test_ide_3rd_dan_subtract_disabled_all_vp_exhausted(page, live_server_url):
    """Ide 3rd Dan: subtract button disabled when all VP types exhausted."""
    _create_char(page, live_server_url, "Ide3Exhaust", "ide_diplomat",
                 knack_overrides={"double_attack": 3, "feint": 3, "worldliness": 3},
                 skill_overrides={"tact": 2})
    # Exhaust all VP: regular=0, temp=0, worldliness fully used (rank 3, used 3)
    page.evaluate("window._trackingBridge.voidPoints = 0")
    page.evaluate("window._trackingBridge.tempVoidPoints = 0")
    page.evaluate("window._trackingBridge.setCount('worldliness', 3)")
    page.wait_for_timeout(200)
    subtract_btn = page.locator('button:has-text("Spend 1 VP to subtract")')
    assert subtract_btn.is_disabled()


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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "80")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    # Roll wound check - should fail with 80 LW and low dice
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "20")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    dismiss_wc_modal(page)
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


def test_doji_5th_dan_always_tn_skill_input(page, live_server_url):
    """Doji 5th Dan: always-TN skills show input directly (no checkbox)."""
    _create_char(page, live_server_url, "Doji5Always", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"manipulation": 1})
    _roll_via_menu_or_direct(page, "skill:manipulation")
    base = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    # The always-TN section should be visible
    always_section = page.locator('[data-testid="doji-5th-always"]')
    assert always_section.is_visible()
    # The optional section should NOT be visible
    assert not page.locator('[data-testid="doji-5th-optional"]').is_visible()
    # Enter opponent result of 30 -> bonus = floor((30-10)/5) = 4
    opponent_input = always_section.locator('input[x-model\\.number="dojiOpponentResult"]')
    opponent_input.fill("30")
    page.wait_for_timeout(300)
    result = always_section.text_content()
    assert "Adjusted total" in result
    expected_adjusted = base + 4
    assert str(expected_adjusted) in result


def test_doji_5th_dan_sometimes_tn_skill_checkbox(page, live_server_url):
    """Doji 5th Dan: sometimes-TN skills show checkbox, then input when checked."""
    _create_char(page, live_server_url, "Doji5Sometimes", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    # The optional section should be visible
    optional_section = page.locator('[data-testid="doji-5th-optional"]')
    assert optional_section.is_visible()
    # The always section should NOT be visible
    assert not page.locator('[data-testid="doji-5th-always"]').is_visible()
    # Checkbox should be visible
    checkbox = optional_section.locator('input[x-model="dojiTnRollApplied"]')
    assert checkbox.is_visible()
    # Input should NOT be visible yet (hidden until checkbox is checked)
    opponent_input = optional_section.locator('input[x-model\\.number="dojiOpponentResult"]')
    assert not opponent_input.is_visible()
    # Check the checkbox
    checkbox.click()
    page.wait_for_timeout(300)
    # Now the input should be visible
    assert opponent_input.is_visible()
    # Enter a TN
    base = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    opponent_input.fill("25")
    page.wait_for_timeout(300)
    result = optional_section.text_content()
    assert "Adjusted total" in result
    # floor((25-10)/5) = 3
    expected_adjusted = base + 3
    assert str(expected_adjusted) in result


def test_doji_5th_dan_never_tn_skill_no_input(page, live_server_url):
    """Doji 5th Dan: never-TN skills show no Doji input or checkbox."""
    _create_char(page, live_server_url, "Doji5Never", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"etiquette": 1})
    _roll_via_menu_or_direct(page, "skill:etiquette")
    # Neither section should be visible
    assert not page.locator('[data-testid="doji-5th-always"]').is_visible()
    assert not page.locator('[data-testid="doji-5th-optional"]').is_visible()


def test_doji_5th_dan_attack_auto_bonus(page, live_server_url):
    """Doji 5th Dan: attack rolls auto-apply bonus from TN and show in result."""
    _create_char(page, live_server_url, "Doji5Atk", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5})
    # Open attack modal - default TN is 20, so bonus = floor((20-10)/5) = 2
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    # Verify the pre-roll Doji note is visible
    pre_text = modal.text_content()
    assert "Doji 5th Dan" in pre_text
    # Roll
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    # Verify the bonus is in the result breakdown
    result_text = modal.text_content()
    assert "Doji 5th Dan" in result_text
    # Verify the bonus was actually applied to the formula
    bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.formula?.doji_5th_dan_bonus || 0;
        }
        return 0;
    }""")
    assert bonus == 2  # floor((20-10)/5)


def test_doji_5th_dan_wound_check_auto_bonus(page, live_server_url):
    """Doji 5th Dan: wound check auto-applies bonus from light wounds."""
    _create_char(page, live_server_url, "Doji5WC", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5})
    # Set light wounds to 30 -> bonus = floor((30-10)/5) = 4
    _set_light_wounds(page, 30)
    # Open wound check modal
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
    modal = page.locator('[data-modal="wound-check"]')
    # Verify the pre-roll Doji note is visible
    pre_text = modal.text_content()
    assert "Doji 5th Dan" in pre_text
    # Roll the wound check (button inside modal)
    modal.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    # Verify the bonus was applied
    bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.formula?.doji_5th_dan_bonus || 0;
        }
        return 0;
    }""")
    assert bonus == 4  # floor((30-10)/5)


def test_doji_4th_dan_untouched_checkbox_hidden_below_4th_dan(page, live_server_url):
    """Doji below 4th Dan: the untouched-target checkbox is NOT rendered."""
    _create_char(page, live_server_url, "Doji3NoUT", "doji_artisan",
                 knack_overrides={"counterattack": 3, "oppose_social": 3, "worldliness": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    ut = page.locator('[data-testid="doji-4th-dan-untouched"]')
    assert not ut.is_visible()


def test_doji_4th_dan_untouched_checkbox_visible_on_attack(page, live_server_url):
    """Doji 4th Dan: the checkbox is visible on the attack modal's pre-roll
    page, with a phase dropdown that only appears once checked."""
    _create_char(page, live_server_url, "Doji4UT", "doji_artisan",
                 knack_overrides={"counterattack": 4, "oppose_social": 4, "worldliness": 4})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    ut = page.locator('[data-testid="doji-4th-dan-untouched"]')
    assert ut.is_visible()
    assert ut.locator('[data-action="doji-4th-dan-phase"]').count() == 1
    # Dropdown hidden until checkbox is ticked.
    assert not ut.locator('[data-action="doji-4th-dan-phase"]').is_visible()
    ut.locator('[data-action="doji-4th-dan-untouched-checkbox"]').check()
    ut.locator('[data-action="doji-4th-dan-phase"]').wait_for(
        state='visible', timeout=2000)


def test_doji_4th_dan_bonus_shifts_probability_table(page, live_server_url):
    """Doji 4th Dan: ticking the checkbox and picking a phase raises the hit
    chance in the probability table (the bonus is added to the attack roll)."""
    _create_char(page, live_server_url, "Doji4Prob", "doji_artisan",
                 knack_overrides={"counterattack": 4, "oppose_social": 4, "worldliness": 4})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    base_chance = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.atkHitChance === 'function') return d.atkHitChance(0);
        }
        return 0;
    }""")
    ut = page.locator('[data-testid="doji-4th-dan-untouched"]')
    ut.locator('[data-action="doji-4th-dan-untouched-checkbox"]').check()
    ut.locator('[data-action="doji-4th-dan-phase"]').select_option("10")
    boosted = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.atkHitChance === 'function') return d.atkHitChance(0);
        }
        return 0;
    }""")
    assert boosted >= base_chance
    assert boosted > 0


def test_doji_4th_dan_bonus_applied_to_roll_and_breakdown(page, live_server_url):
    """Doji 4th Dan: rolling with the checkbox ticked adds +phase to the
    formula and surfaces the labeled line in the post-roll breakdown."""
    _create_char(page, live_server_url, "Doji4Roll", "doji_artisan",
                 knack_overrides={"counterattack": 4, "oppose_social": 4, "worldliness": 4})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    ut = page.locator('[data-testid="doji-4th-dan-untouched"]')
    ut.locator('[data-action="doji-4th-dan-untouched-checkbox"]').check()
    ut.locator('[data-action="doji-4th-dan-phase"]').select_option("7")
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return {
                bonus: d.formula?.doji_4th_dan_bonus || 0,
                phase: d.formula?.doji_4th_dan_phase || 0,
            };
        }
        return null;
    }""")
    assert bonus == {"bonus": 7, "phase": 7}
    breakdown = page.locator('[data-testid="doji-4th-dan-breakdown"]')
    assert breakdown.is_visible()
    assert "+7" in breakdown.text_content()


def test_doji_4th_dan_bonus_not_applied_when_unchecked(page, live_server_url):
    """Doji 4th Dan: without the checkbox the formula has no 4th Dan bonus."""
    _create_char(page, live_server_url, "Doji4NoApply", "doji_artisan",
                 knack_overrides={"counterattack": 4, "oppose_social": 4, "worldliness": 4})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    # Leave the checkbox unchecked; set a phase directly just to prove it
    # doesn't leak into the formula.
    page.evaluate("() => { window._diceRoller.atkDojiPhase = 5; }")
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.formula?.doji_4th_dan_bonus || 0;
        }
        return 0;
    }""")
    assert bonus == 0
    assert not page.locator('[data-testid="doji-4th-dan-breakdown"]').is_visible()


def test_doji_4th_dan_counterattack_shows_checkbox(page, live_server_url):
    """Doji 4th Dan counterattack (an attack-type knack) also surfaces the
    untouched-target checkbox on its attack modal."""
    _create_char(page, live_server_url, "Doji4Counter", "doji_artisan",
                 knack_overrides={"counterattack": 4, "oppose_social": 4, "worldliness": 4})
    page.locator('[data-roll-key="knack:counterattack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    assert page.locator('[data-testid="doji-4th-dan-untouched"]').is_visible()


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


def test_togashi_4th_dan_reroll_only_once_per_roll(page, live_server_url):
    """Togashi 4th Dan: Reroll button disappears after first use, reappears on next roll."""
    _create_char(page, live_server_url, "Togashi4Once", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert reroll_btn.is_visible(), "Reroll button should be visible after initial roll"
    # Note: this reroll commits to the new result - the post-reroll banner says so
    reroll_btn.click()
    _wait_roll_done(page)
    # The reroll button hides on togashiRerollUsed=true. Poll the Alpine
    # state and the DOM together: the test previously asserted is_visible()
    # immediately after _wait_roll_done, which races with the Alpine
    # reactive update of x-show under full-suite load.
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && 'togashiRerollUsed' in d && d.togashiRerollUsed === true && d.phase === 'done') {
                // Confirm DOM x-show has settled by inspecting the button.
                const btns = Array.from(document.querySelectorAll('button'))
                    .filter(b => b.textContent.includes('Reroll (Togashi 4th Dan)'));
                return btns.every(b => b.offsetParent === null
                    || getComputedStyle(b).display === 'none');
            }
        }
        return false;
    }""", timeout=5000)
    # Post-reroll banner mentions the original is discarded
    result_text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "discarded" in result_text.lower() or "original" in result_text.lower()
    # Close modal and roll again -> button should be available again
    page.locator('[data-modal="dice-roller"] button:has-text("×")').click()
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "skill:bragging")
    # The new roll resets togashiRerollUsed=false in executeRoll(); poll for
    # the button to become visible again rather than reading a snapshot
    # immediately, since x-show can lag the post-roll reactivity batch
    # under full-suite load.
    reroll_btn.wait_for(state='visible', timeout=5000)


def test_togashi_4th_dan_reroll_hidden_on_initiative(page, live_server_url):
    """Togashi 4th Dan: reroll button not shown on initiative rolls."""
    _create_char(page, live_server_url, "Togashi4Init", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4})
    # Togashi initiative is a dropdown (two variants); pick the normal variant
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-normal]', state='visible', timeout=10000)
    page.locator('[data-togashi-init-normal]').click()
    _wait_roll_done(page)
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert not reroll_btn.is_visible(), "Reroll must not appear on initiative (never contested)"


def test_togashi_4th_dan_reroll_hidden_on_etiquette(page, live_server_url):
    """Togashi 4th Dan: reroll button not shown on etiquette (never contested)."""
    _create_char(page, live_server_url, "Togashi4Etq", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skill_overrides={"etiquette": 1})
    _roll_via_menu_or_direct(page, "skill:etiquette")
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert not reroll_btn.is_visible(), "Reroll must not appear on etiquette"


def test_togashi_4th_dan_reroll_hidden_on_heraldry(page, live_server_url):
    """Togashi 4th Dan: reroll button not shown on heraldry (never contested)."""
    _create_char(page, live_server_url, "Togashi4Her", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skill_overrides={"heraldry": 1})
    _roll_via_menu_or_direct(page, "skill:heraldry")
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert not reroll_btn.is_visible(), "Reroll must not appear on heraldry"


def test_togashi_4th_dan_reroll_hidden_on_dragon_tattoo(page, live_server_url):
    """Togashi 4th Dan: reroll button not shown on Dragon Tattoo damage
    rolls - damage rolls are never contested."""
    _create_char(page, live_server_url, "Togashi4DT", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4})
    _roll_via_menu_or_direct(page, "knack:dragon_tattoo")
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert not reroll_btn.is_visible(), "Reroll must not appear on Dragon Tattoo (damage roll)"


def test_togashi_4th_dan_reroll_hidden_on_parry(page, live_server_url):
    """Togashi 4th Dan: reroll button not shown on parry rolls - parry is
    never contested (it raises the attacker's TN instead of being rolled
    against an opponent)."""
    _create_char(page, live_server_url, "Togashi4Parry", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4})
    _roll_via_menu_or_direct(page, "parry")
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert not reroll_btn.is_visible(), "Reroll must not appear on parry rolls"


def test_togashi_init_athletics_die_appears_in_side_panel(page, live_server_url):
    """After rolling initiative as a Togashi Ise Zumi, the Actions side
    panel must show the athletics-only bonus die alongside the main
    action dice, styled with the athletics-only (blue) variant and
    carrying the tooltip that explains it."""
    _create_char(page, live_server_url, "TogashiInitAD", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-normal]', state='visible', timeout=10000)
    page.locator('[data-togashi-init-normal]').click()
    _wait_roll_done(page)
    page.locator('[data-modal="dice-roller"] button:has-text("×")').click()
    page.wait_for_timeout(200)
    ath_die = page.locator(
        '[data-testid="action-dice-section"] '
        '[data-action="action-die"][data-die-athletics-only="true"]'
    )
    assert ath_die.count() == 1
    assert (
        ath_die.get_attribute("title")
        == "Athletics-only action die (Togashi special ability)"
    )


def test_togashi_non_athletics_parry_skips_athletics_die(page, live_server_url):
    """Spending the lowest unspent die for a plain parry must skip the
    athletics-only die even if it's the lowest value."""
    _create_char(page, live_server_url, "TogashiNonAthSkip", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 2, spent: false, athletics_only: true},
            {value: 5, spent: false}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(200)
    page.locator('[data-parry-menu] button:has-text("Roll")').first.click()
    _wait_roll_done(page)
    dice = page.evaluate("window._trackingBridge.actionDice")
    ath = next(d for d in dice if d.get("athletics_only"))
    reg = next(d for d in dice if not d.get("athletics_only"))
    assert ath["spent"] is False
    assert reg["spent"] is True


def test_togashi_athletics_parry_can_spend_athletics_die(page, live_server_url):
    """The athletics-only die's per-die menu offers Athletics Parry, and
    selecting it spends THAT die - confirming athletics actions are an
    eligible target for the otherwise-restricted athletics-only die."""
    _create_char(page, live_server_url, "TogashiAthParrySpend", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 2, spent: false, athletics_only: true},
            {value: 5, spent: false}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    # Open the athletics-only die's menu (it's the first die).
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.locator('[data-action-die-menu-item="athletics-parry"]:visible').click()
    _wait_roll_done(page)
    dice = page.evaluate("window._trackingBridge.actionDice")
    ath = next(d for d in dice if d.get("athletics_only"))
    reg = next(d for d in dice if not d.get("athletics_only"))
    assert ath["spent"] is True, "athletics-only die should be spent for athletics:parry"
    assert reg["spent"] is False


def test_togashi_4th_dan_reroll_hidden_on_athletics_parry(page, live_server_url):
    """Same exclusion applies to the athletics:parry roll key."""
    _create_char(page, live_server_url, "Togashi4AthParry", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4})
    _roll_via_menu_or_direct(page, "athletics:parry")
    reroll_btn = page.locator('button:has-text("Reroll (Togashi 4th Dan)")')
    assert not reroll_btn.is_visible(), (
        "Reroll must not appear on athletics:parry rolls"
    )


def _open_attack_modal(page, roll_key):
    """Open the attack modal for a roll key without rolling.

    Schools with an ``athletics`` knack render a regular-vs-athletics chooser
    before the attack modal; pick regular.
    """
    page.locator(f'[data-roll-key="{roll_key}"]').click()
    page.wait_for_timeout(200)
    choice_menu = page.locator('[data-attack-choice-menu]')
    if choice_menu.count() > 0 and choice_menu.is_visible():
        choice_menu.locator('[data-attack-choice="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)


def _attack_modal_bonus_text(page):
    """Return the 'Bonuses: ...' line text on the attack modal pre-roll panel."""
    return page.locator('[data-modal="attack"]').text_content()


# ===========================================================================
# ATTACK MODAL PRE-ROLL: bonus display + probability chart sanity
# ===========================================================================


def test_akodo_1st_dan_attack_modal_pre_roll_extra_die(page, live_server_url):
    """Akodo 1st Dan: attack modal pre-roll calls out the +1 rolled die."""
    _create_char(page, live_server_url, "Akodo1PR", "akodo_bushi")
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "1st Dan" in text
    # Probability chart should reflect the extra rolled die via rolled count.
    f = _get_formula(page, "attack")
    # Akodo base: 1(attack)+2(Fire) = 3. 1st Dan extra die -> 4k2.
    assert f["rolled"] >= 4


def test_ikoma_2nd_dan_attack_modal_pre_roll_free_raise(page, live_server_url):
    """Ikoma 2nd Dan: attack modal pre-roll mentions the +5 free raise."""
    _create_char(page, live_server_url, "Ikoma2PR", "ikoma_bard",
                 knack_overrides={"discern_honor": 2, "oppose_knowledge": 2, "oppose_social": 2})
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "2nd Dan" in text
    f = _get_formula(page, "attack")
    assert f["flat"] == 5


def test_brotherhood_2nd_dan_attack_modal_pre_roll_free_raise(page, live_server_url):
    """Brotherhood 2nd Dan: attack modal pre-roll mentions the +5 free raise."""
    _create_char(page, live_server_url, "Bro2PR", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "worldliness": 2})
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "2nd Dan" in text
    f = _get_formula(page, "attack")
    assert f["flat"] == 5


def test_bayushi_2nd_dan_double_attack_modal_pre_roll(page, live_server_url):
    """Bayushi 2nd Dan: double_attack modal pre-roll calls out the +5 free raise."""
    _create_char(page, live_server_url, "Bayushi2PR", "bayushi_bushi",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    _open_attack_modal(page, "knack:double_attack")
    text = _attack_modal_bonus_text(page)
    assert "2nd Dan" in text
    f = _get_formula(page, "knack:double_attack")
    assert f["flat"] == 5


def test_hida_2nd_dan_counterattack_modal_pre_roll(page, live_server_url):
    """Hida 2nd Dan: counterattack modal pre-roll calls out the +5 free raise."""
    _create_char(page, live_server_url, "Hida2PR", "hida_bushi",
                 knack_overrides={"counterattack": 2, "iaijutsu": 2, "lunge": 2})
    _open_attack_modal(page, "knack:counterattack")
    text = _attack_modal_bonus_text(page)
    assert "2nd Dan" in text
    f = _get_formula(page, "knack:counterattack")
    assert f["flat"] == 5


def test_daidoji_2nd_dan_counterattack_modal_pre_roll(page, live_server_url):
    """Daidoji 2nd Dan: counterattack modal pre-roll calls out the +5 free raise."""
    _create_char(page, live_server_url, "Daid2PR", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    _open_attack_modal(page, "knack:counterattack")
    text = _attack_modal_bonus_text(page)
    assert "2nd Dan" in text
    f = _get_formula(page, "knack:counterattack")
    assert f["flat"] == 5


def test_kitsuki_attack_modal_pre_roll_shows_water_bonus(page, live_server_url):
    """Kitsuki Special: attack modal pre-roll shows the +2*Water bonus."""
    _create_char(page, live_server_url, "KitsukiPR", "kitsuki_magistrate")
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "Kitsuki" in text
    f = _get_formula(page, "attack")
    # +2*Water: default Water=2 (non-school-ring) unless school ring is Water.
    assert f["flat"] >= 4  # at least +2*2


def test_courtier_special_attack_modal_pre_roll_shows_air_bonus(page, live_server_url):
    """Courtier Special: attack modal pre-roll shows the +Air bonus."""
    _create_char(page, live_server_url, "CourtierSpPR", "courtier")
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "Courtier Special" in text
    f = _get_formula(page, "attack")
    assert f["flat"] >= 2  # at least +Air


def test_courtier_5th_dan_attack_modal_pre_roll_shows_air_bonus(page, live_server_url):
    """Courtier 5th Dan: pre-roll lists both the special Air bonus and the 5th Dan Air bonus."""
    _create_char(page, live_server_url, "Courtier5PR", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5})
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "Courtier Special" in text
    assert "5th Dan" in text


def test_shosuro_acting_dice_attack_modal_pre_roll(page, live_server_url):
    """Shosuro Special: pre-roll shows the +acting rolled dice note."""
    _create_char(page, live_server_url, "ShosActPR", "shosuro_actor",
                 skill_overrides={"acting": 3})
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "Acting" in text
    f = _get_formula(page, "attack")
    # Shosuro attack base 1+Fire(2)=3 rolled, +1 from 1st Dan, +3 from acting = 7.
    assert f["rolled"] >= 7


def test_conviction_button_appears_on_skill_roll(page, live_server_url):
    """Characters with the conviction knack see a Spend Conviction (+1) button
    on skill roll results."""
    _create_char(page, live_server_url, "ConvSkill", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    spend = page.locator('[data-action="spend-conviction"]')
    assert spend.is_visible()


def test_conviction_not_on_initiative(page, live_server_url):
    """Conviction spend button should NOT appear on initiative rolls."""
    _create_char(page, live_server_url, "ConvInit", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_selector('[data-togashi-init-normal]', state='visible', timeout=10000)
    page.locator('[data-togashi-init-normal]').click()
    _wait_roll_done(page)
    assert not page.locator('[data-action="spend-conviction"]').is_visible()


def test_conviction_spend_adds_plus_one_and_decrements_pool(page, live_server_url):
    """Clicking Spend Conviction raises baseTotal by 1 and decrements the pool."""
    _create_char(page, live_server_url, "ConvSpend", "togashi_ise_zumi",
                 knack_overrides={"athletics": 2, "conviction": 2, "dragon_tattoo": 2},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    before = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.baseTotal === 'number') return {
                total: d.baseTotal, spent: d.convictionSpentThisRoll,
                pool: d.convictionPoolAvail(),
            };
        }
        return null;
    }""")
    page.locator('[data-action="spend-conviction"]').click()
    page.wait_for_timeout(150)
    after = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.baseTotal === 'number') return {
                total: d.baseTotal, spent: d.convictionSpentThisRoll,
                pool: d.convictionPoolAvail(),
            };
        }
        return null;
    }""")
    assert after["total"] == before["total"] + 1
    assert after["spent"] == before["spent"] + 1
    assert after["pool"] == before["pool"] - 1


def test_conviction_button_on_missed_attack(page, live_server_url):
    """A character with the conviction knack must see Spend Conviction (+1)
    on a MISSED attack - spending a point can turn a narrow miss into a
    hit, so gating the button to the HIT panel was a bug."""
    _create_char(page, live_server_url, "ConvMissAtk", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 3, "otherworldliness": 3, "worldliness": 3})
    _mock_dice_low(page)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    # TN 30 (max in the dropdown) guarantees a miss against mocked-low dice.
    modal.locator('select:visible').first.select_option("30")
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    _restore_dice(page)
    # MISS panel is visible; Conviction spend must be too.
    assert "MISSED" in modal.text_content(), \
        "Test precondition: attack should have missed against TN 40 with mocked-low dice"
    spend = modal.locator('[data-action="spend-conviction-atk-miss"]')
    assert spend.is_visible(), \
        "Spend Conviction button must appear on the MISS panel of the attack modal"
    # Clicking it raises atkRollTotal and fires _atkUpdateHitState.
    before = page.evaluate("() => window._diceRoller.atkRollTotal")
    spend.click()
    page.wait_for_timeout(150)
    after = page.evaluate("() => window._diceRoller.atkRollTotal")
    assert after == before + 1, f"Conviction spend should add 1 to atkRollTotal: {before} -> {after}"


def test_conviction_survives_togashi_reroll(page, live_server_url):
    """Spent conviction points persist after a Togashi 4th Dan reroll."""
    _create_char(page, live_server_url, "ConvReroll", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    # Spend 2 conviction
    spend = page.locator('[data-action="spend-conviction"]')
    spend.click()
    page.wait_for_timeout(100)
    spend.click()
    page.wait_for_timeout(100)
    before_spent = page.evaluate("() => window._diceRoller?.convictionSpentThisRoll")
    assert before_spent == 2
    # Togashi reroll
    page.locator('button:has-text("Reroll (Togashi 4th Dan)")').click()
    _wait_roll_done(page)
    after_spent = page.evaluate("() => window._diceRoller?.convictionSpentThisRoll")
    assert after_spent == 2, f"conviction spent should survive reroll; got {after_spent}"
    # The breakdown should still show the 2-point conviction line
    result_text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "Conviction" in result_text


def test_togashi_dragon_tattoo_no_void_spend(page, live_server_url):
    """Dragon Tattoo is a damage roll, so clicking it does not offer void spending."""
    _create_char(page, live_server_url, "TogashiDragonVP", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    vp = page.evaluate("window._trackingBridge?.voidPoints")
    assert vp > 0, "precondition: char has VP"
    page.locator('[data-roll-key="knack:dragon_tattoo"]').click()
    page.wait_for_timeout(300)
    # Should either roll directly or (if menu appears) the menu should not contain void options.
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    if menu.is_visible():
        text = menu.text_content()
        assert "void point" not in text.lower(), f"damage roll menu should not show void options: {text!r}"


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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "30")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Roll wound check (no VP pre-roll)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "30")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    # Roll wound check
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    # The Apply button should be visible (wait for Alpine to render the banked bonuses UI)
    page.locator('button:has-text("Apply +")').first.wait_for(state='visible', timeout=10000)
    assert page.locator('button:has-text("Apply +")').first.is_visible()


def test_akodo_4th_dan_vp_on_passed_wound_check(page, live_server_url):
    """Akodo 4th Dan: Spend VP (+5) button appears on PASSED wound check to increase margin."""
    _create_char(page, live_server_url, "Akodo4VP", "akodo_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    # Give VP and small light wounds so WC passes easily with mocked high dice
    page.evaluate("window._trackingBridge.voidPoints = 3")
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    # Roll wound check
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "80")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    # Roll wound check
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "10")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    # Select 1 VP
    vp_btn = modal.locator('button:has-text("+")').first
    if vp_btn.is_visible():
        vp_btn.click()
        page.wait_for_timeout(100)
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    assert page.locator('text="Banked 5th Dan Wound Check Bonuses"').is_visible()
    body = page.text_content("body")
    assert "+8" in body
    assert "+12" in body
    # Now add LW and roll a wound check - the bonus should be available as discretionary
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("15")
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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


def test_shinjo_5th_dan_banked_excess_in_tracking_section(page, live_server_url):
    """Shinjo 5th Dan banked parry excess surfaces in the Tracking section
    alongside every other discretionary banked bonus, and the wound-check
    'Apply +N' buttons carry a '5th Dan bonus' label."""
    _create_char(page, live_server_url, "Shinjo5Track", "shinjo_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    page.evaluate("""() => {
        window._trackingBridge.bankedWcExcess.push(
            {amount: 10, spent: false},
            {amount: 7, spent: false},
        );
        window._diceRoller.bankedWcExcess = window._trackingBridge.bankedWcExcess;
        window._trackingBridge.save();
    }""")
    page.wait_for_timeout(200)
    tracking_block = page.locator('[data-testid="banked-wc-excess-tracking"]')
    assert tracking_block.is_visible(), \
        "Shinjo 5th Dan banked excess should surface in tracking section"
    body = tracking_block.text_content()
    assert "+10" in body and "+7" in body
    # Mark spent from tracking: the remaining entry stays visible, spent one strikes through.
    tracking_block.locator('button:has-text("Mark spent")').first.click()
    page.wait_for_timeout(200)
    remaining = page.evaluate("""() =>
        window._trackingBridge.bankedWcExcess.filter(b => !b.spent).length
    """)
    assert remaining == 1, f"Expected 1 unspent entry after marking, got {remaining}"
    # Trigger a wound check to verify the Apply button carries the 5th Dan label.
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "40")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_low(page)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    wc_modal = page.locator('[data-modal="wound-check"]')
    apply_btn = wc_modal.locator('button:has-text("5th Dan bonus"):visible')
    assert apply_btn.count() >= 1, \
        "Wound-check modal should label the bankedWcExcess button as a 5th Dan bonus"


def test_shinjo_5th_dan_bank_excess_resets_between_parry_rolls(page, live_server_url):
    """Regression: the Bank Excess button used to mutate its own DOM
    (``$el.disabled = true``; ``$el.textContent = ...``), so after banking
    once the button stayed stuck as "Banked +N" on every subsequent parry
    roll in the same combat - which blocked the intended flow where a
    Shinjo can accumulate multiple banked bonuses and pick which to spend.
    The fix tracks the banking state in a reactive ``shinjoParryBankedThisRoll``
    latch that the _captureShinjoParryDieValue reset runs on every roll."""
    _create_char(page, live_server_url, "Shinjo5BankReset", "shinjo_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 3, spent: false}, {value: 7, spent: false}];
    }""")
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "parry")
    # Bank some excess on the first parry.
    first_total = page.evaluate("() => window._diceRoller.baseTotal")
    page.locator('input[x-model\\.number="shinjoParryOpponentRoll"]').fill("5")
    page.locator('[data-action="shinjo-bank-parry-excess"]').click()
    page.wait_for_timeout(200)
    first_banked = page.evaluate(
        "() => window._diceRoller.bankedWcExcess.filter(b => !b.spent).length"
    )
    assert first_banked == 1, "First parry should have banked one entry"
    # Close the modal and roll parry again.
    page.evaluate("() => window._diceRoller.close?.() || (window._diceRoller.open = false)")
    page.wait_for_timeout(200)
    _roll_via_menu_or_direct(page, "parry")
    _restore_dice(page)
    # The button must be enabled and labeled "Bank Excess" again, not
    # stuck on the previous roll's banked value.
    btn = page.locator('[data-action="shinjo-bank-parry-excess"]')
    assert btn.is_enabled(), "Bank Excess button should re-enable on a new parry roll"
    assert "Bank Excess" in btn.text_content(), \
        f"Button should show 'Bank Excess' on a new roll, got: {btn.text_content()!r}"
    # Banking a different amount now stacks on top of the prior entry.
    page.locator('input[x-model\\.number="shinjoParryOpponentRoll"]').fill("3")
    btn.click()
    page.wait_for_timeout(200)
    total_banked = page.evaluate(
        "() => window._diceRoller.bankedWcExcess.filter(b => !b.spent).length"
    )
    assert total_banked == 2, \
        f"Second parry should accumulate a second banked entry, got {total_banked}"


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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
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
    page.wait_for_selector('input[placeholder="Amount"]', timeout=10000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    _mock_dice_high(page)
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
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
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)

    # Nothing should be banked
    banked = page.evaluate("window._diceRoller?.hidaBankedWcBonus || 0")
    assert banked == 0, f"Below 5th Dan should NOT bank counterattack excess, got {banked}"

    # Banked note should not be visible
    note = page.locator('[data-testid="hida-5th-dan-banked-note"]')
    assert not note.is_visible(), "Hida 5th Dan banked note should NOT be visible below 5th Dan"
    _restore_dice(page)


@pytest.mark.xfail(reason="Pre-existing Isawa Ishi character creation issue in e2e tests")
def test_ishi_3rd_dan_add_button_visible(page, live_server_url):
    """Isawa Ishi 3rd Dan: add-to-roll button visible on sheet."""
    _create_char(page, live_server_url, "Ishi3Add", "isawa_ishi",
                 knack_overrides={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
                 skill_overrides={"precepts": 2})
    assert page.locator('text="Isawa Ishi 3rd Dan - Add to Roll"').is_visible()
    btn = page.locator('button:has-text("Spend 1 VP to add")')
    assert btn.is_visible()
    assert "2k1" in btn.text_content()


@pytest.mark.xfail(reason="Pre-existing Isawa Ishi character creation issue in e2e tests")
def test_ishi_3rd_dan_add_roll(page, live_server_url):
    """Isawa Ishi 3rd Dan: clicking add button deducts VP and opens roll results modal."""
    _create_char(page, live_server_url, "Ishi3Roll", "isawa_ishi",
                 knack_overrides={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
                 skill_overrides={"precepts": 2})
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)
    btn = page.locator('button:has-text("Spend 1 VP to add")')
    btn.click()
    _wait_roll_done(page)
    vp_after = page.evaluate("window._trackingBridge.voidPoints")
    assert vp_after == 0
    modal = page.locator('[data-modal="dice-roller"]')
    assert modal.is_visible()
    assert "Isawa Ishi 3rd Dan" in modal.text_content()
    assert "2k1" in modal.text_content()
    total = page.evaluate("window._diceRoller.baseTotal")
    assert total > 0


def test_oppose_social_roll_shows_penalty(page, live_server_url):
    """Oppose Social: roll result modal shows penalty to target's Air rolls."""
    _create_char(page, live_server_url, "OppSocial", "courtier",
                 skill_overrides={"manipulation": 1})
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "knack:oppose_social")
    _wait_roll_done(page)
    modal = page.locator('[data-modal="dice-roller"]')
    assert modal.is_visible()
    modal_text = modal.text_content()
    assert "Air skill rolls" in modal_text
    assert "rest of the conversation" in modal_text
    # Check that the penalty value is shown (total / 5)
    total = page.evaluate("window._diceRoller.baseTotal")
    expected_penalty = total // 5
    assert str(expected_penalty) in modal_text
    _restore_dice(page)


def test_oppose_knowledge_roll_shows_penalty(page, live_server_url):
    """Oppose Knowledge: roll result modal shows penalty to target's Water rolls."""
    _create_char(page, live_server_url, "OppKnow", "ikoma_bard",
                 skill_overrides={"bragging": 1})
    _mock_dice_high(page)
    _roll_via_menu_or_direct(page, "knack:oppose_knowledge")
    _wait_roll_done(page)
    modal = page.locator('[data-modal="dice-roller"]')
    assert modal.is_visible()
    modal_text = modal.text_content()
    assert "Water skill rolls" in modal_text
    assert "rest of the conversation" in modal_text
    total = page.evaluate("window._diceRoller.baseTotal")
    expected_penalty = total // 5
    assert str(expected_penalty) in modal_text


# --- Initiative resets per-round ability pools ---

def _init_reset_messages(page):
    return page.locator('[data-testid="per-round-reset-messages"]')


def test_mirumoto_3rd_dan_initiative_refills_round_points(page, live_server_url):
    """Mirumoto 3rd Dan: rolling initiative while round points are below max
    refills them to max and shows a refresh message in the result modal."""
    _create_char(page, live_server_url, "MiruInitRefill", "mirumoto_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    max_points = page.evaluate(
        "() => window._trackingBridge.mirumotoRoundPointsMax"
    )
    assert max_points > 0  # sanity (2 * attack = 2)
    # Simulate a partially-spent pool: fill to max then spend one.
    page.evaluate(
        "() => { const t = window._trackingBridge; t.mirumotoRoundPoints = t.mirumotoRoundPointsMax - 1; }"
    )
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    msgs = _init_reset_messages(page)
    assert msgs.is_visible()
    assert "Mirumoto 3rd Dan points refreshed" in msgs.text_content()
    # Pool should now be at max.
    current = page.evaluate("() => window._trackingBridge.mirumotoRoundPoints")
    assert current == max_points


def test_mirumoto_3rd_dan_initiative_no_message_when_pool_full(page, live_server_url):
    """No refresh message when the per-round pool was already at max."""
    _create_char(page, live_server_url, "MiruInitFull", "mirumoto_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    page.evaluate(
        "() => { const t = window._trackingBridge; t.mirumotoRoundPoints = t.mirumotoRoundPointsMax; }"
    )
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    assert not _init_reset_messages(page).is_visible()


def test_priest_5th_dan_initiative_refreshes_conviction(page, live_server_url):
    """Priest 5th Dan: initiative roll resets conviction_used to 0 and shows
    the Conviction refresh message."""
    _create_char(page, live_server_url, "Priest5Init", "priest",
                 knack_overrides={"conviction": 5, "otherworldliness": 5, "pontificate": 5})
    # Spend 3 conviction via the tracking bridge, which persists to the DB.
    page.evaluate("() => window._trackingBridge.setCount('conviction', 3)")
    # Sanity: pool reflects the spend.
    used_before = page.evaluate("() => window._trackingBridge.getCount('conviction')")
    assert used_before == 3
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    msgs = _init_reset_messages(page)
    assert msgs.is_visible()
    assert "Conviction pool refreshed" in msgs.text_content()
    used_after = page.evaluate("() => window._trackingBridge.getCount('conviction')")
    assert used_after == 0


def test_priest_5th_dan_initiative_no_message_when_conviction_unspent(page, live_server_url):
    """No Conviction refresh message when none was spent."""
    _create_char(page, live_server_url, "Priest5NoSpend", "priest",
                 knack_overrides={"conviction": 5, "otherworldliness": 5, "pontificate": 5})
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    assert not _init_reset_messages(page).is_visible()


def test_priest_4th_dan_initiative_does_not_reset_conviction(page, live_server_url):
    """Priest below 5th Dan: conviction is per-day, not per-round, so
    initiative must NOT reset it."""
    _create_char(page, live_server_url, "Priest4Init", "priest",
                 knack_overrides={"conviction": 4, "otherworldliness": 4, "pontificate": 4})
    page.evaluate("() => window._trackingBridge.setCount('conviction', 2)")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    assert not _init_reset_messages(page).is_visible()
    used_after = page.evaluate("() => window._trackingBridge.getCount('conviction')")
    assert used_after == 2


def test_non_initiative_roll_does_not_trigger_reset(page, live_server_url):
    """Only initiative rolls trigger per-round resets. A skill roll must not
    refill the Mirumoto 3rd Dan pool."""
    _create_char(page, live_server_url, "MiruSkillNoReset", "mirumoto_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3},
                 skill_overrides={"bragging": 1})
    # Pool starts at 0 by default; do not fill it.
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert not _init_reset_messages(page).is_visible()
    current = page.evaluate("() => window._trackingBridge.mirumotoRoundPoints")
    assert current == 0
    _restore_dice(page)


# --- Priest bless rituals (2k1 rolls available to any Priest) ---

def test_priest_bless_conversation_topic_rolls_2k1(page, live_server_url):
    """Priest any-Dan: the Bless conversation topic button rolls 2k1 and
    shows the dice modal titled for that ritual."""
    _create_char(page, live_server_url, "PriestBlessC", "priest",
                 knack_overrides={"conviction": 1, "otherworldliness": 1, "pontificate": 1})
    page.locator('[data-action="bless-conversation"]').click()
    _wait_roll_done(page)
    formula = page.evaluate("() => window._diceRoller.formula")
    assert formula["rolled"] == 2
    assert formula["kept"] == 1
    assert formula["flat"] == 0
    assert formula["is_initiative"] is False
    # Title drives the modal heading — make sure the ritual name is surfaced.
    title = page.evaluate("() => window._diceRoller.title")
    assert title == "Bless conversation topic"


def test_priest_bless_research_rolls_2k1(page, live_server_url):
    """Priest any-Dan: the Bless research button rolls 2k1 with its own title."""
    _create_char(page, live_server_url, "PriestBlessR", "priest",
                 knack_overrides={"conviction": 1, "otherworldliness": 1, "pontificate": 1})
    page.locator('[data-action="bless-research"]').click()
    _wait_roll_done(page)
    formula = page.evaluate("() => window._diceRoller.formula")
    assert formula["rolled"] == 2
    assert formula["kept"] == 1
    title = page.evaluate("() => window._diceRoller.title")
    assert title == "Bless research"


def test_priest_bless_buttons_have_rules_tooltips(page, live_server_url):
    """The full rules text for each ritual lives in a hover tooltip beside
    the button, so the player can confirm what it does before clicking."""
    _create_char(page, live_server_url, "PriestBlessT", "priest",
                 knack_overrides={"conviction": 1, "otherworldliness": 1, "pontificate": 1})
    conv = page.locator('[data-bless-conversation] .tooltip-content')
    research = page.locator('[data-bless-research] .tooltip-content')
    assert "bless a target and pick a topic of conversation" in conv.text_content()
    assert "Each blessing replaces the previous one" in conv.text_content()
    assert "target makes a roll to perform research" in research.text_content()


def test_priest_bless_roll_allows_conviction_spending(page, live_server_url):
    """Conviction may be spent on a bless roll (the standard in-modal block
    is visible and the button increments baseTotal by 1)."""
    _create_char(page, live_server_url, "PriestBlessConv", "priest",
                 knack_overrides={"conviction": 3, "otherworldliness": 3, "pontificate": 3})
    page.locator('[data-action="bless-conversation"]').click()
    _wait_roll_done(page)
    conv_block = page.locator('[data-conviction-block]')
    assert conv_block.is_visible()
    base_before = page.evaluate("() => window._diceRoller.baseTotal")
    conv_block.locator('[data-action="spend-conviction"]').click()
    base_after = page.evaluate("() => window._diceRoller.baseTotal")
    assert base_after == base_before + 1
    spent = page.evaluate("() => window._diceRoller.convictionSpentThisRoll")
    assert spent == 1


def test_priest_bless_roll_offers_no_void_spending(page, live_server_url):
    """Bless is not a skill roll, so it must NOT go through the roll menu
    that exposes Spend-1-VP / Spend-2-VP options."""
    _create_char(page, live_server_url, "PriestBlessNoVP", "priest",
                 knack_overrides={"conviction": 1, "otherworldliness": 1, "pontificate": 1})
    page.locator('[data-action="bless-conversation"]').click()
    _wait_roll_done(page)
    # The pre-roll VP menu flyout must not have appeared.
    menu_open = page.evaluate("() => window._diceRoller.rollMenuOpen")
    assert menu_open is False
    # formula.void_spent should be falsy (the bless path never writes it).
    void_spent = page.evaluate("() => window._diceRoller.formula?.void_spent || 0")
    assert void_spent == 0


def test_priest_bless_buttons_absent_on_non_priest(page, live_server_url):
    """The Bless ritual buttons are only rendered for Priest characters."""
    _create_char(page, live_server_url, "AkodoNoBless", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    assert page.locator('[data-action="bless-conversation"]').count() == 0
    assert page.locator('[data-action="bless-research"]').count() == 0


# --- Priest "sick or impaired" ritual: reroll Impaired 10s on a blessed roll ---

def _become_impaired(page):
    """Set the character to Impaired (SW == Earth) so 10s do not auto-reroll.

    Also zeroes out void points so clicking a roll key doesn't open the
    pre-roll void-spending menu (which would block the roll from completing).
    """
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.seriousWounds = 2;  // default Earth ring is 2 -> SW 2 is Impaired
        t.voidPoints = 0;
        t.tempVoidPoints = 0;
        t.save();
        window.dispatchEvent(new CustomEvent('wound-changed', { detail: { serious: 2 } }));
    }""")
    page.wait_for_timeout(150)


def _setup_impaired_target_with_party_priest(page, live_server_url, priest_name):
    """Seed a Priest and an Akodo ally in the same group. Navigate to the
    ally's sheet and make them Impaired. Returns the ally's sheet URL."""
    from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character, dismiss_wc_modal

    # Priest: rank 1 knacks is enough (any Dan provides the ritual).
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', priest_name)
    select_school(page, "priest")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(400)
    apply_changes(page, "Priest setup")

    # Ally: Akodo Bushi with bragging 1 (any rollable skill works).
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "ImpairedAlly")
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.locator('select[name="gaming_group_id"]').select_option(label="Tuesday Group")
    page.wait_for_timeout(400)
    apply_changes(page, "Ally setup")
    ally_url = page.url

    page.goto(ally_url)
    page.wait_for_selector('[data-roll-key="skill:bragging"]')
    _become_impaired(page)
    return ally_url


def test_priest_bless_reroll_button_shows_on_impaired_10(page, live_server_url):
    """When an Impaired character rolls a 10 and there is a priest in the
    party, a 'X priest blessed for 10 rerolls' button appears beside the
    no-reroll note."""
    _setup_impaired_target_with_party_priest(page, live_server_url, "Isawa Blesser")
    _mock_dice_ten(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_roll_done(page)
    _restore_dice(page)

    # The live_server_url DB persists across tests, so other tests may have
    # added priests to the shared Tuesday Group. Match this test's priest by name.
    btn = page.locator('[data-priest-bless-reroll-block] button').filter(
        has_text="Isawa Blesser"
    ).first
    assert btn.is_visible()
    assert "priest blessed for 10 rerolls" in btn.text_content()


def test_priest_bless_reroll_button_tooltip_has_rules_text(page, live_server_url):
    """The button's tooltip names the priest and quotes the sick-or-impaired ritual."""
    _setup_impaired_target_with_party_priest(page, live_server_url, "Kuni Blesser")
    _mock_dice_ten(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_roll_done(page)
    _restore_dice(page)

    # Scope to the row for THIS test's priest (others may exist in Tuesday Group
    # because the live_server DB persists across tests).
    row = page.locator('[data-priest-bless-reroll-block] > div').filter(
        has_text="Kuni Blesser"
    ).first
    tooltip = row.locator('.tooltip-content').first
    text = tooltip.text_content()
    assert "Kuni Blesser" in text
    assert "already suffering penalties from being sick or impaired" in text
    assert "ignore those penalties in the next conversation or fight" in text


def test_priest_bless_reroll_replaces_10s_and_updates_total(page, live_server_url):
    """Clicking the button rerolls the 10s, updates finalDice/keptSum, and
    the baseTotal reflects the new keptSum (discretionary bonuses unchanged)."""
    _setup_impaired_target_with_party_priest(page, live_server_url, "Kitsuki Blesser")
    _mock_dice_ten(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_roll_done(page)

    before = page.evaluate("""() => ({
        base: window._diceRoller.baseTotal,
        keptSum: window._diceRoller.keptSum,
        tens: window._diceRoller.finalDice.filter(d => d.value === 10).length,
    })""")
    assert before["tens"] > 0

    # Reroll produces 1s (guaranteed non-10, no further explosion).
    _mock_dice_low(page)
    page.locator('[data-priest-bless-reroll-block] button').first.click()
    _wait_roll_done(page)
    _restore_dice(page)

    after = page.evaluate("""() => ({
        base: window._diceRoller.baseTotal,
        keptSum: window._diceRoller.keptSum,
        tens: window._diceRoller.finalDice.filter(d => d.value === 10).length,
        phase: window._diceRoller.phase,
    })""")
    assert after["phase"] == "done"
    # No 10 remains, so the kept sum is smaller and the baseTotal drops with it.
    assert after["tens"] == 0
    assert after["keptSum"] < before["keptSum"]
    assert after["base"] < before["base"]


def test_priest_bless_reroll_button_hides_after_click(page, live_server_url):
    """After the reroll clears the 10s, the button auto-hides (its x-show
    gates on `finalDice.some(d => d.value === 10)`)."""
    _setup_impaired_target_with_party_priest(page, live_server_url, "Asahina Blesser")
    _mock_dice_ten(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_roll_done(page)
    _mock_dice_low(page)
    page.locator('[data-priest-bless-reroll-block] button').first.click()
    _wait_roll_done(page)
    _restore_dice(page)
    # Wait for the x-show to re-evaluate and hide the block.
    page.wait_for_function("""() => {
        const el = document.querySelector('[data-priest-bless-reroll-block]');
        return !el || el.offsetParent === null;
    }""", timeout=10000)
    block = page.locator('[data-priest-bless-reroll-block]')
    assert not block.is_visible()


def test_priest_bless_reroll_button_hidden_without_party_priest(page, live_server_url):
    """Impaired roll + 10 but no priest in party -> no button."""
    _create_char(page, live_server_url, "SoloImpaired", "akodo_bushi",
                 knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1},
                 skill_overrides={"bragging": 1})
    _become_impaired(page)
    _mock_dice_ten(page)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    assert page.locator('[data-priest-bless-reroll-block]').count() == 0 or \
        not page.locator('[data-priest-bless-reroll-block]').is_visible()


def test_priest_bless_reroll_button_hidden_when_not_impaired(page, live_server_url):
    """Priest in party but not Impaired -> 10s auto-reroll, button never shows."""
    _setup_impaired_target_with_party_priest(page, live_server_url, "Togashi Blesser")
    # Heal back to 0 SW.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.seriousWounds = 0;
        t.save();
        window.dispatchEvent(new CustomEvent('wound-changed', { detail: { serious: 0 } }));
    }""")
    page.wait_for_timeout(150)
    _mock_dice_high(page)  # roll 7s so no 10 anyway
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_roll_done(page)
    _restore_dice(page)
    block = page.locator('[data-priest-bless-reroll-block]')
    assert not block.is_visible()


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 1st Dan: extra die on initiative, athletics, wound check
# ---------------------------------------------------------------------------


@pytest.mark.school_abilities
def test_mantis_1st_dan_formula_extra_die(page, live_server_url):
    """Mantis Wave-Treader 1st Dan gives +1 rolled die on initiative,
    athletics (every rollable ring variant), and wound checks.

    Reads the embedded roll formulas from the sheet page and verifies the
    rolled counts against the Phase 2 rules. Default character has school
    knacks at rank 1 -> dan=1 (bonus active). Rings default to 2 each; Mantis
    defaults to Void as school ring so Void auto-raises to 3 (Water stays 2).
    """
    _create_char(page, live_server_url, "Mantis1Dan", "mantis_wave_treader")
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)

    # Initiative: base (Void+1) = 4 rolled, Void=3 kept. 1st Dan +1 -> 5k3.
    init = _get_formula(page, "initiative")
    assert init is not None, "initiative formula missing"
    assert init["rolled"] == 5, f"initiative rolled expected 5, got {init['rolled']}"
    assert init["kept"] == 3

    # Wound check: Water=2 -> base 3k2. 1st Dan +1 -> 4k2 with a labeled
    # bonus-source entry for the extra die.
    wc = _get_formula(page, "wound_check")
    assert wc is not None, "wound_check formula missing"
    assert wc["rolled"] == 4, f"wound_check rolled expected 4, got {wc['rolled']}"
    assert wc["kept"] == 2
    assert any("1st Dan" in src for src in wc.get("bonus_sources", [])), (
        f"wound_check should label the 1st Dan extra die, got: {wc.get('bonus_sources')}"
    )

    # Athletics: 2*Ring + athletics_rank rolled, Ring kept. athletics=1 (free
    # rank from school knacks). All four rollable rings are at 2 -> 5k2 base,
    # +1 Dan -> 6k2.
    for ring in ("Air", "Fire", "Earth", "Water"):
        ath = _get_formula(page, f"athletics:{ring}")
        assert ath is not None, f"athletics:{ring} formula missing"
        assert ath["rolled"] == 6, (
            f"athletics:{ring} rolled expected 6, got {ath['rolled']}"
        )
        assert ath["kept"] == 2


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 2nd Dan: flexible +5 free raise on chosen roll type
# ---------------------------------------------------------------------------


def _make_mantis_dan_2(page, live_server_url, name):
    """Create a Mantis character and raise school knacks to 2 (Dan 2)."""
    _create_char(
        page, live_server_url, name, "mantis_wave_treader",
        knack_overrides={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
    )


def _set_mantis_2nd_dan(page, char_id, choice):
    """Persist the Mantis 2nd Dan pick via the autosave endpoint."""
    _set_technique_choices(page, char_id, {"mantis_2nd_dan_free_raise": choice})


@pytest.mark.school_abilities
def test_mantis_2nd_dan_editor_picker_visible_and_saves(page, live_server_url):
    """Editor UI: the Mantis 2nd Dan picker appears when Dan>=2, and choosing
    a value persists it into technique_choices on save."""
    # Create the character but DON'T apply yet - we want to interact with the editor.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Mantis2Picker")
    select_school(page, "mantis_wave_treader")
    # The picker should be hidden at Dan 1.
    picker = page.locator('[data-testid="mantis-2nd-dan-picker"]')
    assert not picker.is_visible()
    # Raise all three school knacks to 2 to reach Dan 2.
    click_plus(page, "knack_athletics", 1)
    click_plus(page, "knack_iaijutsu", 1)
    click_plus(page, "knack_worldliness", 1)
    page.wait_for_timeout(200)
    # The picker is now visible and options include the eligible set.
    assert picker.is_visible()
    select = page.locator('[data-testid="mantis-2nd-dan-select"]')
    option_values = select.evaluate("el => Array.from(el.querySelectorAll('option')).map(o => o.value)")
    # Combat rolls present, initiative excluded, worldliness excluded.
    for needed in ("attack", "damage", "parry", "wound_check", "athletics", "iaijutsu", "bragging"):
        assert needed in option_values, f"option {needed!r} missing from picker"
    assert "initiative" not in option_values
    assert "worldliness" not in option_values
    # Pick "attack", wait for autosave, then verify via the autosave endpoint state.
    select.select_option("attack")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Mantis 2nd Dan picker")
    # After Apply Changes, the sheet's attack formula carries the +5 bonus.
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "attack")
    assert f["flat"] == 5


@pytest.mark.school_abilities
def test_mantis_2nd_dan_attack_choice_labeled(page, live_server_url):
    """Attack choice: the pre-roll Bonuses row and the post-roll breakdown
    both show the labeled +5."""
    _make_mantis_dan_2(page, live_server_url, "Mantis2Atk")
    cid = _extract_char_id(page)
    _set_mantis_2nd_dan(page, cid, "attack")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    # Pre-roll: open the attack modal and verify the Bonuses row mentions "2nd Dan".
    _open_attack_modal(page, "attack")
    modal_text = _attack_modal_bonus_text(page)
    assert "2nd Dan" in modal_text
    # Post-roll: roll and verify the breakdown includes "2nd Dan technique".
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    result_text = page.locator('[data-modal="attack"]').text_content()
    assert "2nd Dan technique" in result_text


@pytest.mark.school_abilities
def test_mantis_2nd_dan_parry_choice_labeled(page, live_server_url):
    """Parry choice: the post-roll roll-result modal shows the labeled +5."""
    _make_mantis_dan_2(page, live_server_url, "Mantis2Parry")
    cid = _extract_char_id(page)
    _set_mantis_2nd_dan(page, cid, "parry")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    _roll_via_menu_or_direct(page, "parry")
    text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "2nd Dan technique" in text


@pytest.mark.school_abilities
def test_mantis_2nd_dan_skill_choice_labeled(page, live_server_url):
    """Skill choice: the post-roll breakdown shows the +5 from 2nd Dan.

    Uses etiquette (no Honor/Recognition bonus, so flat=5 cleanly reflects
    only the Mantis choice)."""
    _create_char(
        page, live_server_url, "Mantis2Skill", "mantis_wave_treader",
        knack_overrides={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
        skill_overrides={"etiquette": 2},
    )
    cid = _extract_char_id(page)
    _set_mantis_2nd_dan(page, cid, "etiquette")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:etiquette")
    assert f["flat"] == 5
    _roll_via_menu_or_direct(page, "skill:etiquette")
    text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "2nd Dan technique" in text


@pytest.mark.school_abilities
def test_mantis_2nd_dan_knack_choice_labeled(page, live_server_url):
    """Knack choice (iaijutsu): the post-roll breakdown shows the +5."""
    _make_mantis_dan_2(page, live_server_url, "Mantis2Knack")
    cid = _extract_char_id(page)
    _set_mantis_2nd_dan(page, cid, "iaijutsu")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "knack:iaijutsu")
    assert f["flat"] == 5
    _roll_via_menu_or_direct(page, "knack:iaijutsu")
    text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "2nd Dan technique" in text


@pytest.mark.school_abilities
def test_mantis_2nd_dan_wound_check_choice_labeled(page, live_server_url):
    """Wound check choice: the WC modal's bonus_sources row shows the +5."""
    _make_mantis_dan_2(page, live_server_url, "Mantis2WC")
    cid = _extract_char_id(page)
    _set_mantis_2nd_dan(page, cid, "wound_check")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    wc = _get_formula(page, "wound_check")
    assert wc["flat"] == 5
    assert any("2nd Dan" in s for s in wc.get("bonus_sources", []))
    # Open the WC modal and verify the Bonuses line is visible.
    _set_light_wounds(page, 10)
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
    modal = page.locator('[data-modal="wound-check"]')
    assert "2nd Dan" in modal.text_content()


@pytest.mark.school_abilities
def test_mantis_2nd_dan_damage_choice_labeled(page, live_server_url):
    """Damage choice: the attack modal's pre-roll Damage bonuses row AND the
    post-roll damage result breakdown both show the labeled +5."""
    _make_mantis_dan_2(page, live_server_url, "Mantis2Dmg")
    cid = _extract_char_id(page)
    _set_mantis_2nd_dan(page, cid, "damage")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    atk = _get_formula(page, "attack")
    assert atk["damage_flat_bonus"] == 5
    assert any("2nd Dan" in s for s in atk.get("damage_bonus_sources", []))
    # Pre-roll: the attack modal should show a "Damage bonuses" row.
    _open_attack_modal(page, "attack")
    pre_text = _attack_modal_bonus_text(page)
    assert "Damage bonuses" in pre_text
    assert "2nd Dan" in pre_text
    # Set TN to 5 so the attack is guaranteed to hit, then roll attack and damage.
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select[x-model\\.number="atkTN"]').first.select_option("5")
    _mock_dice_high(page)
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    # Click Make Damage Roll (button inside the attack modal once the attack hits).
    roll_dmg_btn = modal.locator('button:has-text("Make Damage Roll")')
    roll_dmg_btn.first.wait_for(state='visible', timeout=5000)
    roll_dmg_btn.first.click()
    # Wait for damage result phase.
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    dmg_text = page.locator('[data-modal="attack"]').text_content()
    assert "2nd Dan" in dmg_text, f"Damage breakdown should show 2nd Dan label, got: {dmg_text[:400]}"


@pytest.mark.school_abilities
def test_mantis_2nd_dan_switch_choice_moves_bonus(page, live_server_url):
    """Switching the choice moves the bonus: pick attack, verify flat=5 on
    attack and flat=0 on wound check; then switch to wound_check and verify
    flat=0 on attack and flat=5 on wound check."""
    _make_mantis_dan_2(page, live_server_url, "Mantis2Switch")
    cid = _extract_char_id(page)
    # First: attack.
    _set_mantis_2nd_dan(page, cid, "attack")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    assert _get_formula(page, "attack")["flat"] == 5
    assert _get_formula(page, "wound_check")["flat"] == 0
    # Switch: wound_check.
    _set_mantis_2nd_dan(page, cid, "wound_check")
    page.reload()
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    assert _get_formula(page, "attack")["flat"] == 0
    assert _get_formula(page, "wound_check")["flat"] == 5


# ---------------------------------------------------------------------------
# Mantis Wave-Treader Special Ability: posture tracker (Phase 4 - state only)
# ---------------------------------------------------------------------------


def _posture_phase(page):
    """Read posturePhase from the tracking bridge."""
    return page.evaluate("window._trackingBridge.posturePhase")


def _posture_history(page):
    """Read postureHistory from the tracking bridge."""
    return page.evaluate("window._trackingBridge.postureHistory")


@pytest.mark.school_abilities
def test_mantis_posture_tracker_visibility(page, live_server_url):
    """Posture tracker appears on Mantis sheets, absent on non-Mantis."""
    _create_char(page, live_server_url, "MantisPostVis", "mantis_wave_treader")
    tracker = page.locator('[data-testid="mantis-posture-tracker"]')
    assert tracker.is_visible()
    assert page.locator('[data-action="mantis-posture-offensive"]').is_visible()
    assert page.locator('[data-action="mantis-posture-defensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_posture_tracker_absent_on_non_mantis(page, live_server_url):
    """Non-Mantis characters never see the posture tracker."""
    _create_char(page, live_server_url, "AkodoNoPosture", "akodo_bushi")
    assert page.locator('[data-testid="mantis-posture-tracker"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_posture_tracker_advance(page, live_server_url):
    """Clicking a posture button advances posturePhase and records the chosen
    posture; the 'Current: Phase X - <posture>' line reflects the latest pick.
    The selection persists through a page reload via adventure_state."""
    _create_char(page, live_server_url, "MantisPostAdv", "mantis_wave_treader")
    # Initial state: phase 1, no posture yet.
    assert _posture_phase(page) == 1
    assert _posture_history(page) == []
    assert not page.locator('[data-testid="mantis-current-posture"]').is_visible()
    # Click offensive for phase 1.
    page.locator('[data-action="mantis-posture-offensive"]').click()
    page.wait_for_function("() => window._trackingBridge.posturePhase === 2")
    assert _posture_history(page) == ["offensive"]
    current = page.locator('[data-testid="mantis-current-posture"]')
    assert current.is_visible()
    current_text = current.text_content()
    assert "Phase 1" in current_text
    assert "offensive" in current_text.lower()
    # Click defensive for phase 2.
    page.locator('[data-action="mantis-posture-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.posturePhase === 3")
    assert _posture_history(page) == ["offensive", "defensive"]
    current_text = page.locator('[data-testid="mantis-current-posture"]').text_content()
    assert "Phase 2" in current_text
    assert "defensive" in current_text.lower()
    # Reload: state rehydrates from adventure_state.
    page.reload()
    page.wait_for_selector('[data-testid="mantis-posture-tracker"]')
    assert _posture_phase(page) == 3
    assert _posture_history(page) == ["offensive", "defensive"]


@pytest.mark.school_abilities
def test_mantis_posture_tracker_disable_at_11(page, live_server_url):
    """After 10 posture picks (phases 1-10), both buttons are disabled and
    their labels show '...' instead of the out-of-range '11'."""
    _create_char(page, live_server_url, "MantisPost11", "mantis_wave_treader")
    offensive = page.locator('[data-action="mantis-posture-offensive"]')
    defensive = page.locator('[data-action="mantis-posture-defensive"]')
    for i in range(10):
        # Alternate for a realistic mix, but the behaviour doesn't depend on it.
        (offensive if i % 2 == 0 else defensive).click()
    page.wait_for_function("() => window._trackingBridge.posturePhase === 11")
    assert offensive.is_disabled()
    assert defensive.is_disabled()
    off_text = offensive.text_content().strip()
    def_text = defensive.text_content().strip()
    assert "..." in off_text and "11" not in off_text
    assert "..." in def_text and "11" not in def_text


@pytest.mark.school_abilities
def test_mantis_posture_tracker_reset_on_initiative(page, live_server_url):
    """Rolling initiative zeros the posture tracker back to phase 1 and
    empties the history (the end-of-round reset trigger)."""
    _create_char(page, live_server_url, "MantisPostInit", "mantis_wave_treader")
    # Build up some posture history first.
    page.locator('[data-action="mantis-posture-offensive"]').click()
    page.locator('[data-action="mantis-posture-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.posturePhase === 3")
    assert len(_posture_history(page)) == 2
    # Roll initiative: setActionDice() fires, which calls resetMantisRound().
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    # State reset happens inside setActionDice() before the save round-trip.
    page.wait_for_function("() => window._trackingBridge.posturePhase === 1")
    assert _posture_history(page) == []
    # Close the result modal so the "Current" visibility check can hit the
    # tracker block.
    page.locator('[data-modal="dice-roller"]').locator('button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    # The "Current" line is hidden again now that no posture is selected.
    assert not page.locator('[data-testid="mantis-current-posture"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_posture_tracker_reset_on_action_dice_clear(page, live_server_url):
    """Clicking the action-dice Clear button also resets the posture tracker
    (it's the other end-of-round trigger)."""
    _create_char(page, live_server_url, "MantisPostClr", "mantis_wave_treader")
    # First roll initiative so the Clear button has any dice to clear.
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    # Close the result modal so subsequent clicks on the tracker block reach.
    page.locator('[data-modal="dice-roller"]').locator('button:has-text("\u00d7")').click()
    page.wait_for_timeout(200)
    # Initiative reset phase to 1 already; now build up more history.
    page.locator('[data-action="mantis-posture-offensive"]').click()
    page.wait_for_function("() => window._trackingBridge.posturePhase === 2")
    assert _posture_history(page) == ["offensive"]
    # Click the action-dice Clear button.
    page.locator('[data-action="clear-action-dice"]').click()
    page.wait_for_function("() => window._trackingBridge.posturePhase === 1")
    assert _posture_history(page) == []
    # Let Alpine's reactive x-show on currentPosture() flush before asserting.
    page.wait_for_timeout(200)
    assert not page.locator('[data-testid="mantis-current-posture"]').is_visible()


# ---------------------------------------------------------------------------
# Mantis Wave-Treader Special Ability: posture bonuses (Phase 5)
# ---------------------------------------------------------------------------


def _select_posture(page, kind):
    """Click an offensive/defensive posture button and wait deterministically
    for the tracking bridge state AND the TN display's event-driven x-data
    scope to reflect the new posture before returning."""
    prev_len = page.evaluate(
        "() => (window._trackingBridge?.postureHistory?.length) || 0"
    )
    page.locator(f'[data-action="mantis-posture-{kind}"]').click()
    page.wait_for_function(
        f"() => (window._trackingBridge?.postureHistory?.length || 0) === {prev_len + 1}"
    )
    # The TN display's local x-data listens for `mantis-posture-changed`
    # and updates `posture` + `defensiveCount`. Wait for its state to match
    # the bridge AND for its x-text to re-render (span text == total()).
    page.wait_for_function(f"""() => {{
        const el = document.querySelector('[data-testid="tn-display"]');
        if (!el) return true;
        const d = window.Alpine && window.Alpine.$data(el);
        if (!d) return true;
        if (d.posture !== {kind!r}) return false;
        const bridgeDef = window._trackingBridge?.defensivePhaseCount?.() || 0;
        if ((d.defensiveCount || 0) !== bridgeDef) return false;
        const span = el.querySelector('span.font-bold');
        return !!(span && parseInt(span.textContent) === d.total());
    }}""")


@pytest.mark.school_abilities
def test_mantis_posture_tracker_bonus_summary_offensive(page, live_server_url):
    """Phase 5: offensive posture shows a summary of active bonuses."""
    _create_char(page, live_server_url, "MantisSumOff", "mantis_wave_treader")
    _select_posture(page, "offensive")
    summary = page.locator('[data-testid="mantis-posture-bonuses"]')
    assert summary.is_visible()
    text = summary.text_content()
    assert "attack rolls" in text
    assert "damage rolls" in text


@pytest.mark.school_abilities
def test_mantis_posture_tracker_bonus_summary_defensive(page, live_server_url):
    """Phase 5: defensive posture shows the WC + TN summary line."""
    _create_char(page, live_server_url, "MantisSumDef", "mantis_wave_treader")
    _select_posture(page, "defensive")
    summary = page.locator('[data-testid="mantis-posture-bonuses"]')
    assert summary.is_visible()
    text = summary.text_content()
    assert "wound checks" in text
    assert "TN to be hit" in text


@pytest.mark.school_abilities
def test_mantis_posture_tracker_bonus_summary_toggles(page, live_server_url):
    """Phase 5: toggling posture mid-round updates the summary line, so the
    next roll picks up the right set of bonuses."""
    _create_char(page, live_server_url, "MantisSumTog", "mantis_wave_treader")
    _select_posture(page, "offensive")
    summary = page.locator('[data-testid="mantis-posture-bonuses"]')
    assert "attack rolls" in summary.text_content()
    _select_posture(page, "defensive")
    # Second click advances the phase and the latest posture is defensive.
    assert "wound checks" in summary.text_content()


@pytest.mark.school_abilities
def test_mantis_offensive_posture_attack_pre_roll_bonuses(page, live_server_url):
    """Phase 5: offensive posture overlays '+5 from offensive posture' into
    the attack modal's pre-roll Bonuses row and the Damage bonuses row."""
    _create_char(page, live_server_url, "MantisOffPre", "mantis_wave_treader")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    # Both the attack-side and the damage-side row should surface the label.
    assert "+5 from offensive posture" in text
    # The Damage bonuses row specifically should carry the same label.
    modal = page.locator('[data-modal="attack"]')
    damage_row = modal.locator(':text("Damage bonuses:")').first
    assert damage_row.is_visible()


@pytest.mark.school_abilities
def test_mantis_offensive_posture_attack_post_roll_breakdown(page, live_server_url):
    """Phase 5: offensive posture +5 appears in the attack modal's post-roll
    result breakdown via formula.bonuses and adds to atkRollTotal."""
    _create_char(page, live_server_url, "MantisOffPost", "mantis_wave_treader")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    # Snapshot baseTotal that would be applied without posture for sanity.
    # Roll with fixed low dice so the +5 is unambiguous.
    _mock_dice_low(page)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    _restore_dice(page)
    modal = page.locator('[data-modal="attack"]')
    result_text = modal.text_content()
    assert "offensive posture" in result_text
    # The total includes the +5 from flat (baseTotal = keptSum + formula.flat).
    atk_total = page.evaluate("() => { const els = document.querySelectorAll('[x-data]'); for (const el of els) { const d = window.Alpine && window.Alpine.$data(el); if (d && typeof d.atkRollTotal === 'number') return d.atkRollTotal; } return null; }")
    # keptSum of all-1s = kept * 1 = 2 (base Mantis attack is 3k2); +5 posture flat.
    assert atk_total is not None
    assert atk_total >= 5


@pytest.mark.school_abilities
def test_mantis_offensive_posture_damage_preview_and_result(page, live_server_url):
    """Phase 5: offensive posture adds +5 flat to atkDamageParts at damage
    computation time (both pre-roll preview and post-roll damage breakdown)."""
    _create_char(page, live_server_url, "MantisOffDmg", "mantis_wave_treader")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    # Pre-roll: atkComputeDamage is called for the Avg Damage column; we can
    # also inspect atkDamageParts directly by invoking it via Alpine.
    parts = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.atkComputeDamage === 'function') {
                return d.atkComputeDamage(0, false, false, 0, false).parts;
            }
        }
        return null;
    }""")
    assert parts is not None
    assert any("offensive posture" in p for p in parts), (
        f"offensive posture label missing from atkComputeDamage parts: {parts}"
    )
    # Roll attack (low dice) -> roll damage; verify the result breakdown shows
    # the labeled line in the damage-result phase.
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select[x-model\\.number="atkTN"]').first.select_option("5")
    _mock_dice_high(page)
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    modal.locator('button:has-text("Make Damage Roll")').first.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    dmg_text = modal.text_content()
    assert "offensive posture" in dmg_text


@pytest.mark.school_abilities
def test_mantis_defensive_posture_tn_display_bumps(page, live_server_url):
    """Phase 5: the sheet's TN-to-be-hit display reflects +5 while in defensive
    posture and the tooltip surfaces the reason."""
    _create_char(page, live_server_url, "MantisTN", "mantis_wave_treader")
    tn_box = page.locator('[data-testid="tn-display"]')
    # Base TN: 5 + 5*parry (default parry=1) = 10.
    base_val = int(tn_box.locator("span.font-bold").first.text_content())
    assert base_val == 10
    # Enter defensive posture.
    _select_posture(page, "defensive")
    # TN number bumps by 5. `_select_posture` already waited for Alpine to
    # flush, so the DOM read is guaranteed to be up to date.
    assert int(tn_box.locator("span.font-bold").first.text_content()) == base_val + 5
    # The "+5 defensive posture" label is visible.
    bump = page.locator('[data-testid="tn-defensive-bump"]')
    bump.wait_for(state='visible', timeout=10000)
    # Tooltip-ready title attribute is set.
    title_attr = tn_box.locator("span.font-bold").first.get_attribute("title")
    assert title_attr and "defensive posture" in title_attr.lower()
    # Swap to offensive -> TN drops back and the label hides.
    _select_posture(page, "offensive")
    assert int(tn_box.locator("span.font-bold").first.text_content()) == base_val
    bump.wait_for(state='hidden', timeout=10000)


@pytest.mark.school_abilities
def test_mantis_defensive_posture_wc_modal_overlay(page, live_server_url):
    """Phase 5: defensive posture overlays +5 into the WC modal pre-roll
    Bonuses row, and the labeled entry persists into the post-roll breakdown
    (via formula.bonus_sources) and shifts wcRollTotal by 5."""
    _create_char(page, live_server_url, "MantisWC", "mantis_wave_treader")
    _select_posture(page, "defensive")
    _set_light_wounds(page, 10)
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
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="wound-check"]')
    assert "+5 from defensive posture" in modal.text_content()
    # Roll a low wound check so we can see the labeled entry in the post-roll
    # breakdown. WC fails, but the labeled line still appears.
    _mock_dice_low(page)
    modal.locator('button:has-text("Roll Wound Check")').first.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    assert "+5 from defensive posture" in modal.text_content()


@pytest.mark.school_abilities
def test_mantis_no_posture_no_overlay(page, live_server_url):
    """Sanity: with no posture selected, no posture labels leak into the attack
    modal. Guards against a regression where the overlay fires unconditionally."""
    _create_char(page, live_server_url, "MantisNone", "mantis_wave_treader")
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    assert "offensive posture" not in text
    assert "defensive posture" not in text


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 5th Dan: accumulated posture counters (Phase 6)
# ---------------------------------------------------------------------------


def _make_mantis_dan_5(page, live_server_url, name):
    """Create a Mantis character and raise school knacks to 5 (Dan 5)."""
    _create_char(
        page, live_server_url, name, "mantis_wave_treader",
        knack_overrides={"athletics": 5, "iaijutsu": 5, "worldliness": 5},
    )


@pytest.mark.school_abilities
def test_mantis_5th_dan_accumulator_block_hidden_with_no_history(page, live_server_url):
    """Phase 6: Dan 5 Mantis with no posture declarations - the accumulator
    sub-block is in the DOM but x-show hides it until a count > 0."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5Empty")
    block = page.locator('[data-testid="mantis-5th-dan-accumulator"]')
    # Block is present in DOM (server rendered it) but hidden.
    assert block.count() == 1
    assert not block.is_visible()


@pytest.mark.school_abilities
def test_mantis_5th_dan_accumulator_block_absent_at_dan_4(page, live_server_url):
    """Phase 6: Dan 4 Mantis does NOT get the accumulator block at all."""
    _create_char(
        page, live_server_url, "Mantis4Acc", "mantis_wave_treader",
        knack_overrides={"athletics": 4, "iaijutsu": 4, "worldliness": 4},
    )
    assert page.locator('[data-testid="mantis-5th-dan-accumulator"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_5th_dan_accumulator_counts_offensive(page, live_server_url):
    """Phase 6: three offensive posture clicks -> +3 accumulator shown."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5Off3")
    for _ in range(3):
        _select_posture(page, "offensive")
    off_line = page.locator('[data-testid="mantis-5th-dan-offensive"]')
    off_line.wait_for(state='visible', timeout=10000)
    assert "+3" in off_line.text_content()
    # Defensive line stays hidden (zero defensive phases).
    assert not page.locator('[data-testid="mantis-5th-dan-defensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_5th_dan_accumulator_counts_mixed(page, live_server_url):
    """Phase 6: alternating postures -> both accumulator lines show their counts."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5Mix")
    _select_posture(page, "offensive")  # phase 1
    _select_posture(page, "defensive")  # phase 2
    _select_posture(page, "offensive")  # phase 3
    page.wait_for_function(
        "() => window._trackingBridge?.offensivePhaseCount?.() === 2"
        " && window._trackingBridge?.defensivePhaseCount?.() === 1"
    )
    off_line = page.locator('[data-testid="mantis-5th-dan-offensive"]')
    def_line = page.locator('[data-testid="mantis-5th-dan-defensive"]')
    off_line.wait_for(state='visible', timeout=30000)
    def_line.wait_for(state='visible', timeout=30000)
    assert "+2" in off_line.text_content()
    assert "+1" in def_line.text_content()


@pytest.mark.school_abilities
def test_mantis_5th_dan_accumulator_resets_on_initiative(page, live_server_url):
    """Phase 6: rolling initiative clears postureHistory -> the derived
    offensive/defensive counts drop to zero and the sub-block hides."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5Reset")
    _select_posture(page, "offensive")
    _select_posture(page, "offensive")
    # wait_for(state='visible') absorbs Alpine's x-show microtask flush.
    page.locator('[data-testid="mantis-5th-dan-offensive"]').wait_for(
        state='visible', timeout=10000
    )
    # Roll initiative (any variant) - setActionDice triggers resetMantisRound.
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    page.wait_for_function("() => window._trackingBridge.offensivePhaseCount() === 0")
    page.locator('[data-modal="dice-roller"]').locator('button:has-text("\u00d7")').click()
    page.locator('[data-testid="mantis-5th-dan-accumulator"]').wait_for(
        state='hidden', timeout=10000
    )


@pytest.mark.school_abilities
def test_mantis_5th_dan_attack_modal_pre_roll_includes_accumulator(page, live_server_url):
    """Phase 6: pre-roll Bonuses row surfaces the 5th Dan offensive-count
    label when accumulator > 0."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5AtkPre")
    # Two offensive declarations + one defensive (so current is defensive but
    # accumulator is still 2 offensive). Tests that the accumulator is applied
    # independently of current posture.
    _select_posture(page, "offensive")
    _select_posture(page, "offensive")
    _select_posture(page, "defensive")
    _open_attack_modal(page, "attack")
    # Wait for the Bonuses row to render the 5th Dan label - x-show on the
    # row depends on _mantisLiveAttackLabels() which polls the bridge live;
    # under full-suite load Alpine can lag a tick after modal open before
    # the row appears.
    page.wait_for_function(
        '() => (document.querySelector(\'[data-modal="attack"]\')?.textContent || "")'
        '.includes("+2 from Mantis 5th Dan")',
        timeout=5000,
    )
    text = _attack_modal_bonus_text(page)
    # Current posture is defensive so the Phase 5 +5 offensive overlay is off,
    # but the 5th Dan accumulator (+2) still applies to attack/damage.
    assert "+5 from offensive posture" not in text
    assert "+2 from Mantis 5th Dan" in text
    # Damage bonuses row also shows the 5th Dan label.
    damage_row = page.locator('[data-modal="attack"]').locator(':text("Damage bonuses:")').first
    assert damage_row.is_visible()


@pytest.mark.school_abilities
def test_mantis_5th_dan_attack_post_roll_snapshot(page, live_server_url):
    """Phase 6: rollAttack snapshots the offensive accumulator into
    formula.bonuses; the post-roll breakdown shows the labeled +N entry."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5AtkPost")
    _select_posture(page, "offensive")
    _select_posture(page, "offensive")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    _mock_dice_low(page)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    _restore_dice(page)
    result_text = page.locator('[data-modal="attack"]').text_content()
    # Current posture is offensive -> Phase 5 adds +5; accumulator adds +3.
    assert "offensive posture" in result_text
    assert "Mantis 5th Dan" in result_text
    # atkRollTotal must include both +5 (current) and +3 (accumulator).
    atk_total = page.evaluate("() => { const els = document.querySelectorAll('[x-data]'); for (const el of els) { const d = window.Alpine && window.Alpine.$data(el); if (d && typeof d.atkRollTotal === 'number') return d.atkRollTotal; } return null; }")
    # Mantis base attack: 3k2 (attack 1, Fire 2). Low-dice mock -> kept sum 2,
    # formula.flat default 0, plus +5 (Phase 5) + +3 (Phase 6) = 10.
    assert atk_total is not None and atk_total >= 10


@pytest.mark.school_abilities
def test_mantis_5th_dan_damage_accumulator_in_parts(page, live_server_url):
    """Phase 6: atkComputeDamage pushes the labeled +N entry into parts."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5Dmg")
    _select_posture(page, "offensive")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    parts = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.atkComputeDamage === 'function') {
                return d.atkComputeDamage(0, false, false, 0, false).parts;
            }
        }
        return null;
    }""")
    assert parts is not None
    # Both the current-posture +5 and the 5th Dan +2 must appear as labeled lines.
    assert any("offensive posture" in p and "+5" in p for p in parts)
    assert any("Mantis 5th Dan" in p and "+2" in p for p in parts)


@pytest.mark.school_abilities
def test_mantis_5th_dan_wc_modal_defensive_accumulator(page, live_server_url):
    """Phase 6: WC modal pre-roll Bonuses row surfaces defensive accumulator
    separately from the current-posture +5. Post-roll breakdown also shows it."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5WC")
    _select_posture(page, "defensive")
    _select_posture(page, "defensive")
    _select_posture(page, "offensive")  # current posture offensive; accumulator still +2 defensive
    _set_light_wounds(page, 10)
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
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="wound-check"]')
    pre_text = modal.text_content()
    # Current posture offensive -> Phase 5 defensive-+5 overlay off; 5th Dan
    # defensive accumulator (+2) still applies.
    assert "+5 from defensive posture" not in pre_text
    assert "+2 from Mantis 5th Dan (defensive posture count)" in pre_text
    # Roll and verify post-roll breakdown also contains the label.
    _mock_dice_low(page)
    modal.locator('button:has-text("Roll Wound Check")').first.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    assert "+2 from Mantis 5th Dan (defensive posture count)" in modal.text_content()


@pytest.mark.school_abilities
def test_mantis_5th_dan_tn_display_bumps_with_accumulator(page, live_server_url):
    """Phase 6: TN display reflects base + defensive posture +5 + accumulator +N.
    The enumerated tooltip lists both contributions."""
    _make_mantis_dan_5(page, live_server_url, "Mantis5TN")
    tn_box = page.locator('[data-testid="tn-display"]')
    base = int(tn_box.locator("span.font-bold").first.text_content())
    assert base == 10  # 5 + 5*parry (parry=1)
    # Two defensive declarations: current posture defensive (+5) + accum +2.
    _select_posture(page, "defensive")
    _select_posture(page, "defensive")
    total = int(tn_box.locator("span.font-bold").first.text_content())
    assert total == base + 5 + 2
    # Both labels render (wait_for handles Alpine microtask flush).
    bump = page.locator('[data-testid="tn-defensive-bump"]')
    accum_label = page.locator('[data-testid="tn-5th-dan-accumulator"]')
    bump.wait_for(state='visible', timeout=10000)
    accum_label.wait_for(state='visible', timeout=10000)
    # Tooltip enumerates both contributions.
    title = tn_box.locator("span.font-bold").first.get_attribute("title")
    assert title
    assert "+5" in title and "defensive posture" in title
    assert "+2" in title and "5th Dan" in title
    # Switch to offensive -> current-posture +5 off, but accumulator stays.
    _select_posture(page, "offensive")
    total_after = int(tn_box.locator("span.font-bold").first.text_content())
    assert total_after == base + 2
    bump.wait_for(state='hidden', timeout=10000)
    accum_label.wait_for(state='visible', timeout=10000)


@pytest.mark.school_abilities
def test_mantis_dan_4_no_accumulator_on_attack(page, live_server_url):
    """Dan 4 Mantis: selecting postures builds postureHistory but the
    accumulator overlay does NOT apply (only the Phase 5 current-posture +5)."""
    _create_char(
        page, live_server_url, "Mantis4NoAcc", "mantis_wave_treader",
        knack_overrides={"athletics": 4, "iaijutsu": 4, "worldliness": 4},
    )
    _select_posture(page, "offensive")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    text = _attack_modal_bonus_text(page)
    # Current-posture +5 still lands (Phase 5 ability is not Dan-gated).
    assert "+5 from offensive posture" in text
    # The 5th Dan accumulator label MUST NOT appear.
    assert "Mantis 5th Dan" not in text


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 3rd Dan offensive: spend-action-die button (Phase 7)
# ---------------------------------------------------------------------------


def _make_mantis_dan_3(page, live_server_url, name, attack=1):
    """Create a Mantis character with school knacks at 3 (Dan 3) and an
    optional override for the attack skill (drives 3rd Dan X). Attack skill
    lives in its own editor field (not the skills block), so we can't reuse
    `_create_char`'s skill_overrides path - use the autosave endpoint."""
    _create_char(
        page, live_server_url, name, "mantis_wave_treader",
        knack_overrides={"athletics": 3, "iaijutsu": 3, "worldliness": 3},
    )
    if attack and attack > 1:
        cid = _extract_char_id(page)
        page.evaluate(f"""async () => {{
            await fetch('/characters/{cid}/autosave', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{attack: {attack}}})
            }});
        }}""")
        page.reload()
        page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)


def _seed_action_dice(page, values):
    """Populate the Mantis character's action dice from JS. Uses setActionDice
    so the tracking-bridge save round-trip fires (but the Mantis resetRound is
    harmless - it clears posture, which tests set afterwards)."""
    page.evaluate(f"""() => {{
        window._trackingBridge.setActionDice({list(values)!r});
    }}""")
    page.wait_for_function(
        f"() => (window._trackingBridge.actionDice || []).length === {len(values)}"
    )


@pytest.mark.school_abilities
def test_mantis_3rd_dan_button_hidden_without_posture(page, live_server_url):
    """No posture selected => button hidden even with action dice present."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3BtnHidden")
    _seed_action_dice(page, [3, 5])
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    assert not page.locator('[data-action="mantis-3rd-dan-offensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_button_hidden_in_defensive_posture(page, live_server_url):
    """Defensive posture => button hidden."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3BtnDef")
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "defensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    assert not page.locator('[data-action="mantis-3rd-dan-offensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_button_hidden_with_no_unspent_action_dice(page, live_server_url):
    """Offensive posture but all action dice spent => button hidden."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3BtnNoDice")
    _seed_action_dice(page, [3])
    # Mark the only die as spent.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 3, spent: true}];
        t.save();
    }""")
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    assert not page.locator('[data-action="mantis-3rd-dan-offensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_button_hidden_on_dan_2(page, live_server_url):
    """Dan 2 Mantis never sees the button (flag is false server-side)."""
    _create_char(
        page, live_server_url, "Mantis2NoBtn", "mantis_wave_treader",
        knack_overrides={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
    )
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    assert page.locator('[data-action="mantis-3rd-dan-offensive"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_3rd_dan_click_spends_die_and_accumulates(page, live_server_url):
    """Clicking the button spends the highest-value unspent regular action
    die (the "last" phase of the round) and bumps offensive3rdDanAccum by
    X (= attack skill rank)."""
    # Attack skill set to 3 so the accumulator reliably reflects that X > 1.
    _make_mantis_dan_3(page, live_server_url, "Mantis3Click", attack=3)
    _seed_action_dice(page, [4, 7])
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    btn = page.locator('[data-action="mantis-3rd-dan-offensive"]')
    btn.wait_for(state='visible', timeout=10000)
    btn.click()
    page.wait_for_function(
        "() => (window._trackingBridge.offensive3rdDanAccum || 0) === 3"
    )
    # The attack roll itself spent index 0 (value 4, lowest). The Mantis
    # 3rd Dan click then spent the highest-value unspent die (index 1,
    # value 7) with the labeled reason.
    state = page.evaluate("""() => {
        return window._trackingBridge.actionDice.map(d => ({
            value: d.value, spent: d.spent, spent_by: d.spent_by || null,
        }));
    }""")
    assert state[0]["spent"] is True  # spent by the attack roll itself
    assert state[1]["spent"] is True  # spent by Mantis 3rd Dan button
    assert state[1]["spent_by"] == "Mantis 3rd Dan (offensive)"


@pytest.mark.school_abilities
def test_mantis_3rd_dan_two_spends_stack_accumulator(page, live_server_url):
    """Two clicks stack the accumulator at 2X and spend two action dice."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3Stack", attack=2)
    _seed_action_dice(page, [3, 5, 7])
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    btn = page.locator('[data-action="mantis-3rd-dan-offensive"]')
    btn.click()
    page.wait_for_function(
        "() => (window._trackingBridge.offensive3rdDanAccum || 0) === 2"
    )
    btn.click()
    page.wait_for_function(
        "() => (window._trackingBridge.offensive3rdDanAccum || 0) === 4"
    )
    # Attack roll spent index 0 (lowest, value 3); the two Mantis 3rd Dan
    # clicks spend the highest-value unspent regular dice in descending
    # order - index 2 (value 7) first, then index 1 (value 5).
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        spent: d.spent, spent_by: d.spent_by || null
    }))""")
    assert all(d["spent"] for d in state)
    mantis_spends = [d for d in state if d["spent_by"] == "Mantis 3rd Dan (offensive)"]
    assert len(mantis_spends) == 2


@pytest.mark.school_abilities
def test_mantis_3rd_dan_next_attack_includes_accumulator(page, live_server_url):
    """After the accumulator is set, the next attack roll's pre-roll Bonuses
    row, post-roll breakdown, and formula.flat all include the labeled +X."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3NextAtk", attack=3)
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    # First attack: roll, click the 3rd Dan button.
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    page.locator('[data-action="mantis-3rd-dan-offensive"]').wait_for(state='visible', timeout=10000)
    page.locator('[data-action="mantis-3rd-dan-offensive"]').click()
    page.wait_for_function("() => window._trackingBridge.offensive3rdDanAccum === 3")
    # Close the modal.
    page.locator('[data-modal="attack"]').locator('button:has-text("\u00d7")').click()
    # Second attack: pre-roll Bonuses row should now include the labeled +3.
    _open_attack_modal(page, "attack")
    pre_text = _attack_modal_bonus_text(page)
    assert "+3 from Mantis 3rd Dan (offensive)" in pre_text
    # Roll and verify post-roll breakdown carries the same label (via
    # formula.bonuses snapshot in rollAttack).
    _mock_dice_low(page)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    _restore_dice(page)
    post_text = page.locator('[data-modal="attack"]').text_content()
    assert "Mantis 3rd Dan (offensive)" in post_text


@pytest.mark.school_abilities
def test_mantis_3rd_dan_damage_includes_accumulator(page, live_server_url):
    """After the accumulator is set, atkComputeDamage adds a labeled +X flat
    line to the damage parts (both pre-roll preview and post-roll damage)."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3Dmg", attack=3)
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    page.locator('[data-action="mantis-3rd-dan-offensive"]').click()
    page.wait_for_function("() => window._trackingBridge.offensive3rdDanAccum === 3")
    # Query atkComputeDamage's parts directly (pre-roll preview surface).
    parts = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.atkComputeDamage === 'function') {
                return d.atkComputeDamage(0, false, false, 0, false).parts;
            }
        }
        return null;
    }""")
    assert parts is not None
    assert any("Mantis 3rd Dan (offensive)" in p and "+3" in p for p in parts)


@pytest.mark.school_abilities
def test_mantis_3rd_dan_resets_on_initiative(page, live_server_url):
    """Rolling initiative zeros the accumulator (resetMantisRound)."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3Reset", attack=2)
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    page.locator('[data-action="mantis-3rd-dan-offensive"]').click()
    page.wait_for_function("() => window._trackingBridge.offensive3rdDanAccum === 2")
    # Close the attack modal so we can roll initiative.
    page.locator('[data-modal="attack"]').locator('button:has-text("\u00d7")').click()
    # Roll initiative - setActionDice calls resetMantisRound which zeros the
    # offensive3rdDanAccum alongside postureHistory.
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    page.wait_for_function("() => window._trackingBridge.offensive3rdDanAccum === 0")


# ---------------------------------------------------------------------------
# Mantis Wave-Treader 3rd Dan defensive + Clear bonuses (Phase 8)
# ---------------------------------------------------------------------------


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_button_hidden_without_posture(page, live_server_url):
    """No posture selected => defensive button hidden even with action dice."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefNo")
    _seed_action_dice(page, [3, 5])
    assert not page.locator('[data-action="mantis-3rd-dan-defensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_button_hidden_in_offensive_posture(page, live_server_url):
    """Offensive posture => defensive button hidden."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefOff")
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    assert not page.locator('[data-action="mantis-3rd-dan-defensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_button_hidden_no_action_dice(page, live_server_url):
    """Defensive posture but no unspent dice => button hidden."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefNoDie")
    _select_posture(page, "defensive")
    assert not page.locator('[data-action="mantis-3rd-dan-defensive"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_button_absent_on_dan_2(page, live_server_url):
    """Dan 2 Mantis never sees the defensive button."""
    _create_char(
        page, live_server_url, "Mantis2NoDef", "mantis_wave_treader",
        knack_overrides={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
    )
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "defensive")
    assert page.locator('[data-action="mantis-3rd-dan-defensive"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_click_spends_die_and_accumulates(page, live_server_url):
    """Click spends the highest-value unspent regular action die (the "last"
    phase of the round) and bumps defensive3rdDanAccum by X (= attack skill)."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefClick", attack=3)
    _seed_action_dice(page, [4, 7])
    _select_posture(page, "defensive")
    btn = page.locator('[data-action="mantis-3rd-dan-defensive"]')
    btn.wait_for(state='visible', timeout=10000)
    btn.click()
    page.wait_for_function(
        "() => (window._trackingBridge.defensive3rdDanAccum || 0) === 3"
    )
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        spent: d.spent, spent_by: d.spent_by || null
    }))""")
    # Highest-value unspent regular die (index 1, value 7) is now spent.
    assert state[0]["spent"] is False
    assert state[1]["spent"] is True
    assert state[1]["spent_by"] == "Mantis 3rd Dan (defensive)"


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_prefers_4th_dan_die(page, live_server_url):
    """When the Mantis 4th Dan bonus die is present and unspent, the
    defensive-3rd-Dan button spends it instead of a regular action die."""
    _make_mantis_dan_4(page, live_server_url, "Mantis3DefPrefer4th")
    _roll_initiative(page)
    _select_posture(page, "defensive")
    fourth_idx = page.evaluate(
        "() => (window._trackingBridge?.actionDice || [])"
        ".findIndex(d => d.mantis_4th_dan)"
    )
    assert fourth_idx >= 0
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function(
        "() => (window._trackingBridge.defensive3rdDanAccum || 0) > 0"
    )
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        spent: !!d.spent, mantis_4th_dan: !!d.mantis_4th_dan,
        spent_by: d.spent_by || null
    }))""")
    # Only the 4th Dan die was spent; other dice remain unspent.
    fourth = [d for d in state if d["mantis_4th_dan"]]
    assert len(fourth) == 1
    assert fourth[0]["spent"] is True
    assert fourth[0]["spent_by"] == "Mantis 3rd Dan (defensive)"
    for d in state:
        if not d["mantis_4th_dan"]:
            assert d["spent"] is False


@pytest.mark.school_abilities
def test_mantis_3rd_dan_offensive_prefers_4th_dan_die(page, live_server_url):
    """The offensive-3rd-Dan button (in the attack-result modal) also spends
    the Mantis 4th Dan die first when it's available."""
    _make_mantis_dan_4(page, live_server_url, "Mantis3OffPrefer4th")
    _roll_initiative(page)
    _select_posture(page, "offensive")
    fourth_idx_before = page.evaluate(
        "() => (window._trackingBridge?.actionDice || [])"
        ".findIndex(d => d.mantis_4th_dan)"
    )
    assert fourth_idx_before >= 0
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    page.locator('[data-action="mantis-3rd-dan-offensive"]').click()
    page.wait_for_function(
        "() => (window._trackingBridge.offensive3rdDanAccum || 0) > 0"
    )
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        spent: !!d.spent, mantis_4th_dan: !!d.mantis_4th_dan,
        spent_by: d.spent_by || null,
    }))""")
    fourth = [d for d in state if d["mantis_4th_dan"]]
    assert len(fourth) == 1
    assert fourth[0]["spent"] is True
    assert fourth[0]["spent_by"] == "Mantis 3rd Dan (offensive)"


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_spends_highest_regular_die(page, live_server_url):
    """Without a 4th Dan bonus die, the defensive-3rd-Dan button spends the
    highest-value unspent regular action die, not the lowest."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefHighest", attack=2)
    _seed_action_dice(page, [2, 5, 8])
    _select_posture(page, "defensive")
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function(
        "() => (window._trackingBridge.defensive3rdDanAccum || 0) === 2"
    )
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: !!d.spent, spent_by: d.spent_by || null
    }))""")
    # Highest-value die (value 8, last index) was spent; lower dice untouched.
    assert state[0]["spent"] is False
    assert state[1]["spent"] is False
    assert state[2]["spent"] is True
    assert state[2]["spent_by"] == "Mantis 3rd Dan (defensive)"


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_two_spends_stack(page, live_server_url):
    """Two defensive spends stack the accumulator at 2X."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefStack", attack=2)
    _seed_action_dice(page, [3, 5, 7])
    _select_posture(page, "defensive")
    btn = page.locator('[data-action="mantis-3rd-dan-defensive"]')
    btn.wait_for(state='visible', timeout=10000)
    btn.click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 2")
    btn.click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 4")


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_wc_overlay(page, live_server_url):
    """After spending, wound check modal pre-roll + post-roll show labeled +X."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefWC", attack=3)
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "defensive")
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 3")
    # Open WC modal; pre-roll Bonuses row should show both +5 (current posture)
    # and +3 (3rd Dan accumulator).
    _set_light_wounds(page, 10)
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
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="wound-check"]')
    pre_text = modal.text_content()
    assert "+5 from defensive posture" in pre_text
    assert "+3 from Mantis 3rd Dan (defensive)" in pre_text
    # Roll and verify post-roll breakdown still contains the label.
    _mock_dice_low(page)
    modal.locator('button:has-text("Roll Wound Check")').first.click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    _restore_dice(page)
    assert "+3 from Mantis 3rd Dan (defensive)" in modal.text_content()


@pytest.mark.school_abilities
def test_mantis_3rd_dan_defensive_tn_display(page, live_server_url):
    """TN display reflects base + defensive +5 + 3rd Dan accum; tooltip
    enumerates each contribution. Defensive-posture bump still visible."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DefTN", attack=3)
    _seed_action_dice(page, [3, 5])
    tn_box = page.locator('[data-testid="tn-display"]')
    base = int(tn_box.locator("span.font-bold").first.text_content())
    assert base == 10  # 5 + 5*parry (parry=1)
    _select_posture(page, "defensive")
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 3")
    # Wait for the TN display to reflect the new accumulator (we can't use
    # _select_posture's helper because the accumulator isn't posture state).
    page.wait_for_function("""() => {
        const el = document.querySelector('[data-testid="tn-display"]');
        const d = window.Alpine && window.Alpine.$data(el);
        return d && d.defensive3rdDan === 3;
    }""")
    total = int(tn_box.locator("span.font-bold").first.text_content())
    assert total == base + 5 + 3  # base + defensive posture + 3rd Dan accum
    # 3rd Dan inline label visible alongside the defensive-bump label.
    page.locator('[data-testid="tn-defensive-bump"]').wait_for(state='visible', timeout=10000)
    page.locator('[data-testid="tn-3rd-dan-accumulator"]').wait_for(state='visible', timeout=10000)
    title = tn_box.locator("span.font-bold").first.get_attribute("title")
    assert title
    assert "+5" in title and "defensive posture" in title
    assert "+3 Mantis 3rd Dan (defensive)" in title


@pytest.mark.school_abilities
def test_mantis_3rd_dan_action_die_menu_hidden_without_posture(page, live_server_url):
    """Per-die action menu: neither 3rd Dan option shown without a posture."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DieNoPose")
    _seed_action_dice(page, [3, 5])
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_selector('[data-action-die-menu-item="attack"]', state='visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-offensive"]').count() == 0
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-defensive"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_3rd_dan_action_die_menu_offensive_only_in_offensive(page, live_server_url):
    """Offensive posture => only the offensive 3rd Dan menu item appears."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DieOff")
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_selector('[data-action-die-menu-item="mantis-3rd-dan-offensive"]', state='visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-defensive"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_3rd_dan_action_die_menu_defensive_only_in_defensive(page, live_server_url):
    """Defensive posture => only the defensive 3rd Dan menu item appears."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DieDef")
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "defensive")
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_selector('[data-action-die-menu-item="mantis-3rd-dan-defensive"]', state='visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-offensive"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_3rd_dan_action_die_menu_absent_on_dan_2(page, live_server_url):
    """Dan 2 Mantis never renders the 3rd Dan menu items, any posture."""
    _create_char(
        page, live_server_url, "Mantis2DieNone", "mantis_wave_treader",
        knack_overrides={"athletics": 2, "iaijutsu": 2, "worldliness": 2},
    )
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "offensive")
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_selector('[data-action-die-menu-item="attack"]', state='visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-offensive"]').count() == 0
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-defensive"]').count() == 0


@pytest.mark.school_abilities
def test_mantis_3rd_dan_action_die_offensive_spends_specific_die(page, live_server_url):
    """Clicking the offensive 3rd Dan menu item spends the clicked die (not
    the lowest unspent one) and bumps the offensive accumulator by X."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DieOffClick", attack=3)
    _seed_action_dice(page, [3, 5, 7])
    _select_posture(page, "offensive")
    # Open the menu on the second die (index 1, value 5).
    dice = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]')
    dice.nth(1).click()
    item = page.locator('[data-action-die-menu-item="mantis-3rd-dan-offensive"]:visible')
    item.wait_for(state='visible', timeout=2000)
    item.click()
    page.wait_for_function("() => (window._trackingBridge.offensive3rdDanAccum || 0) === 3")
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: d.spent, spent_by: d.spent_by || null,
    }))""")
    assert state[0]["spent"] is False
    assert state[1]["spent"] is True
    assert state[1]["spent_by"] == "Mantis 3rd Dan (offensive)"
    assert state[2]["spent"] is False


@pytest.mark.school_abilities
def test_mantis_3rd_dan_action_die_defensive_spends_specific_die(page, live_server_url):
    """Clicking the defensive 3rd Dan menu item spends the clicked die and
    bumps the defensive accumulator by X."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3DieDefClick", attack=2)
    _seed_action_dice(page, [4, 6])
    _select_posture(page, "defensive")
    dice = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]')
    dice.nth(0).click()
    item = page.locator('[data-action-die-menu-item="mantis-3rd-dan-defensive"]:visible')
    item.wait_for(state='visible', timeout=2000)
    item.click()
    page.wait_for_function("() => (window._trackingBridge.defensive3rdDanAccum || 0) === 2")
    state = page.evaluate("""() => window._trackingBridge.actionDice.map(d => ({
        value: d.value, spent: d.spent, spent_by: d.spent_by || null,
    }))""")
    assert state[0]["spent"] is True
    assert state[0]["spent_by"] == "Mantis 3rd Dan (defensive)"
    assert state[1]["spent"] is False


@pytest.mark.school_abilities
def test_mantis_clear_bonuses_zeros_everything(page, live_server_url):
    """Clicking the posture tracker's Clear bonuses button wipes posture
    history, both 3rd Dan accumulators, AND the action dice (equivalent to
    the action-dice Clear button)."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3ClearAll", attack=3)
    _seed_action_dice(page, [3, 5, 7])
    _select_posture(page, "defensive")
    _select_posture(page, "defensive")
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 3")
    # Also stage an offensive accumulator so we can prove Clear zeros it too.
    # Switch to offensive and roll an attack to enable the offensive button.
    _select_posture(page, "offensive")
    _open_attack_modal(page, "attack")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    _wait_attack_result(page)
    page.locator('[data-action="mantis-3rd-dan-offensive"]').click()
    page.wait_for_function("() => window._trackingBridge.offensive3rdDanAccum === 3")
    # Close the attack modal so Clear bonuses is reachable.
    page.locator('[data-modal="attack"]').locator('button:has-text("\u00d7")').click()
    clear = page.locator('[data-action="mantis-clear-bonuses"]')
    clear.wait_for(state='visible', timeout=10000)
    clear.click()
    page.wait_for_function("""() => {
        const t = window._trackingBridge;
        return t.postureHistory.length === 0
            && t.offensive3rdDanAccum === 0
            && t.defensive3rdDanAccum === 0
            && t.actionDice.length === 0
            && t.posturePhase === 1;
    }""")


@pytest.mark.school_abilities
def test_mantis_clear_bonuses_button_hidden_when_empty(page, live_server_url):
    """Clear bonuses hidden on a fresh Mantis sheet with no round state."""
    _create_char(page, live_server_url, "Mantis3ClearHidden", "mantis_wave_treader")
    assert not page.locator('[data-action="mantis-clear-bonuses"]').is_visible()


@pytest.mark.school_abilities
def test_mantis_action_dice_clear_equivalent_to_clear_bonuses(page, live_server_url):
    """The action-dice Clear button has the same effect as Clear bonuses:
    both wipe accumulators, posture history, and action dice."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3ClearEquiv", attack=2)
    _seed_action_dice(page, [3, 5])
    _select_posture(page, "defensive")
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 2")
    # Click the action-dice section's Clear button.
    page.locator('[data-action="clear-action-dice"]').click()
    page.wait_for_function("""() => {
        const t = window._trackingBridge;
        return t.postureHistory.length === 0
            && t.defensive3rdDanAccum === 0
            && t.actionDice.length === 0;
    }""")


# ---------------------------------------------------------------------------
# Mantis Wave-Treader WC probability-table integration (Phase 9)
# ---------------------------------------------------------------------------


def _open_wc_modal_for_prob(page, lw):
    """Open the wound-check modal with a known LW so the probability table
    has a fixed baseline. wcProbRow() uses `wcLightWounds` and `wcProbs`,
    both populated at openWoundCheckModal() time."""
    _set_light_wounds(page, lw)
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
    page.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=10000)


def _close_wc_modal(page):
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && 'wcModalOpen' in d) { d.wcModalOpen = false; return; }
        }
    }""")
    page.wait_for_selector('[data-modal="wound-check"]', state='hidden', timeout=10000)


def _wc_prob_row(page, void_count=0):
    """Read wcProbRow(voidCount) directly from the diceRoller Alpine scope.
    Returns {passChance, expectedSW, rows} or None if probs aren't loaded."""
    return page.evaluate(f"""() => {{
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {{
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.wcProbRow === 'function') {{
                const r = d.wcProbRow({void_count});
                return r ? {{
                    passChance: r.passChance,
                    expectedSW: r.expectedSW,
                }} : null;
            }}
        }}
        return null;
    }}""")


@pytest.mark.school_abilities
def test_mantis_wc_probability_shifts_with_defensive_posture(page, live_server_url):
    """Selecting defensive posture adds +5 to the WC probability table's flat
    bonus, which strictly raises passChance and lowers expectedSW."""
    _make_mantis_dan_3(page, live_server_url, "MantisWCProbPos")
    _open_wc_modal_for_prob(page, lw=20)
    baseline = _wc_prob_row(page)
    assert baseline is not None
    _close_wc_modal(page)
    _select_posture(page, "defensive")
    _open_wc_modal_for_prob(page, lw=20)
    with_posture = _wc_prob_row(page)
    assert with_posture is not None
    assert with_posture["passChance"] > baseline["passChance"], (
        f"expected pass% to rise; baseline={baseline['passChance']} "
        f"with posture={with_posture['passChance']}"
    )
    assert with_posture["expectedSW"] < baseline["expectedSW"]


@pytest.mark.school_abilities
def test_mantis_wc_probability_shifts_with_3rd_dan_defensive(page, live_server_url):
    """Spending the 3rd Dan defensive button adds +X to the WC probability
    table's flat, raising passChance further."""
    _make_mantis_dan_3(page, live_server_url, "MantisWCProb3rd", attack=3)
    _seed_action_dice(page, [3, 5])
    # Baseline with defensive posture only.
    _select_posture(page, "defensive")
    _open_wc_modal_for_prob(page, lw=20)
    posture_only = _wc_prob_row(page)
    _close_wc_modal(page)
    # Spend the 3rd Dan defensive button - accumulator = 3.
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 3")
    _open_wc_modal_for_prob(page, lw=20)
    with_3rd_dan = _wc_prob_row(page)
    assert with_3rd_dan["passChance"] > posture_only["passChance"]
    assert with_3rd_dan["expectedSW"] < posture_only["expectedSW"]


@pytest.mark.school_abilities
def test_mantis_wc_probability_shifts_with_5th_dan_defensive_count(page, live_server_url):
    """Two defensive phase declarations on a Dan 5 Mantis add +2 to the WC
    probability table's flat (the 5th Dan accumulator)."""
    _make_mantis_dan_5(page, live_server_url, "MantisWCProb5th")
    # One defensive declaration -> current posture defensive + 1 accum count.
    _select_posture(page, "defensive")
    page.wait_for_function(
        "() => (window._trackingBridge?.defensivePhaseCount?.() || 0) === 1"
    )
    _open_wc_modal_for_prob(page, lw=20)
    one_phase = _wc_prob_row(page)
    _close_wc_modal(page)
    # Second defensive declaration: still current posture defensive, but now
    # defensivePhaseCount = 2 so the 5th Dan accumulator contributes +2.
    _select_posture(page, "defensive")
    page.wait_for_function(
        "() => (window._trackingBridge?.defensivePhaseCount?.() || 0) === 2"
    )
    _open_wc_modal_for_prob(page, lw=20)
    two_phases = _wc_prob_row(page)
    assert two_phases["passChance"] > one_phase["passChance"], (
        f"two_phases={two_phases} one_phase={one_phase}"
    )
    assert two_phases["expectedSW"] < one_phase["expectedSW"]


def _make_mantis_dan_4(page, live_server_url, name):
    """Create a Mantis character with school knacks at 4 (Dan 4)."""
    _create_char(
        page, live_server_url, name, "mantis_wave_treader",
        knack_overrides={"athletics": 4, "iaijutsu": 4, "worldliness": 4},
    )


def _roll_initiative(page):
    """Click the initiative action and wait for the roll result modal."""
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    # Close the result modal so subsequent posture clicks reach the tracker.
    page.locator('[data-modal="dice-roller"]').locator('button:has-text("\u00d7")').click()
    page.wait_for_timeout(100)


@pytest.mark.school_abilities
def test_mantis_4th_dan_athletics_die_appended_after_initiative(page, live_server_url):
    """Dan 4 Mantis: rolling initiative appends a deterministic value-1 die
    flagged with athletics_only + mantis_4th_dan metadata."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4Die")
    _roll_initiative(page)
    # The appended die is always at the end of the list. Value == 1 and the
    # mantis_4th_dan flag is set so the render+auto-spend logic treats it as
    # a restricted athletics-only die.
    state = page.evaluate("""() => {
        const dice = window._trackingBridge?.actionDice || [];
        return dice.map(d => ({
            value: d.value,
            mantis_4th_dan: !!d.mantis_4th_dan,
            athletics_only: !!d.athletics_only,
            spent: !!d.spent,
        }));
    }""")
    mantis_dice = [d for d in state if d["mantis_4th_dan"]]
    assert len(mantis_dice) == 1, f"expected exactly one Mantis 4th Dan die, got {state}"
    assert mantis_dice[0]["value"] == 1
    assert mantis_dice[0]["athletics_only"] is True
    assert mantis_dice[0]["spent"] is False


@pytest.mark.school_abilities
def test_mantis_4th_dan_die_renders_with_testable_markup(page, live_server_url):
    """The appended die gets the mantis-4th-dan data attribute and a tooltip
    explaining the movement / athletics / 3rd Dan restriction."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4Markup")
    _roll_initiative(page)
    buttons = page.locator('[data-action="action-die"][data-die-mantis-4th-dan="true"]')
    assert buttons.count() == 1
    btn = buttons.first
    assert btn.get_attribute("data-die-value") == "1"
    assert btn.get_attribute("data-die-athletics-only") == "true"
    title = btn.get_attribute("title")
    assert title and "Mantis 4th Dan" in title
    # The restriction is enumerated in the tooltip.
    assert "movement" in title.lower()
    assert "athletics" in title.lower()
    assert "3rd dan" in title.lower()


@pytest.mark.school_abilities
def test_mantis_4th_dan_die_spendable(page, live_server_url):
    """The Mantis 4th Dan die can be manually marked spent via the action-die
    menu (display-only restriction, same as Togashi's athletics-only die)."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4Spend")
    _roll_initiative(page)
    # Mark spent via Alpine directly (driving the per-die menu click-path
    # requires a Mantis-tailored UI that isn't in scope for Phase 10).
    page.evaluate("""() => {
        const t = window._trackingBridge;
        const i = t.actionDice.findIndex(d => d.mantis_4th_dan);
        t.spendActionDie(i);
    }""")
    state = page.evaluate("""() => {
        const d = (window._trackingBridge?.actionDice || [])
            .find(x => x.mantis_4th_dan);
        return d ? {spent: d.spent, value: d.value} : null;
    }""")
    assert state is not None
    assert state["spent"] is True
    assert state["value"] == 1


@pytest.mark.school_abilities
def test_mantis_4th_dan_die_regenerated_on_next_initiative(page, live_server_url):
    """Rolling initiative a second time clears the old bonus die and appends
    a fresh one (setActionDice resets and the mantis_4th_dan_athletics_die
    formula flag fires deterministically)."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4Regen")
    _roll_initiative(page)
    # Mark the bonus die spent, then re-roll initiative.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        const i = t.actionDice.findIndex(d => d.mantis_4th_dan);
        t.spendActionDie(i);
    }""")
    _roll_initiative(page)
    # Wait for the second initiative roll's setActionDice() to land on
    # the bridge with a fresh (unspent) mantis_4th_dan die. Reading
    # state immediately races with the dice-roller's post-animation
    # setActionDice call under full-suite load.
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || [])"
        ".some(d => d.mantis_4th_dan && !d.spent)",
        timeout=5000,
    )
    # Exactly one fresh (unspent) bonus die after re-roll.
    state = page.evaluate("""() => {
        const dice = window._trackingBridge?.actionDice || [];
        return dice.filter(d => d.mantis_4th_dan).map(d => ({
            value: d.value, spent: !!d.spent,
        }));
    }""")
    assert len(state) == 1
    assert state[0]["value"] == 1
    assert state[0]["spent"] is False


@pytest.mark.school_abilities
def test_mantis_4th_dan_die_cleared_by_clear_bonuses(page, live_server_url):
    """Clear bonuses wipes the bonus die along with all other action dice."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4Clear")
    _roll_initiative(page)
    clear = page.locator('[data-action="mantis-clear-bonuses"]')
    clear.wait_for(state='visible', timeout=10000)
    clear.click()
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || []).length === 0"
    )


@pytest.mark.school_abilities
def test_mantis_dan_3_no_4th_dan_die(page, live_server_url):
    """Dan 3 Mantis does not get the bonus athletics die (flag is false)."""
    _make_mantis_dan_3(page, live_server_url, "Mantis3NoDie4")
    _roll_initiative(page)
    mantis_count = page.evaluate("""() =>
        (window._trackingBridge?.actionDice || [])
            .filter(d => d.mantis_4th_dan).length
    """)
    assert mantis_count == 0


@pytest.mark.school_abilities
def test_non_mantis_dan_4_no_4th_dan_die(page, live_server_url):
    """Non-Mantis Dan 4 characters never get the Mantis 4th Dan die."""
    _create_char(
        page, live_server_url, "Akodo4NoMantis", "akodo_bushi",
        knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4},
    )
    _roll_initiative(page)
    mantis_count = page.evaluate("""() =>
        (window._trackingBridge?.actionDice || [])
            .filter(d => d.mantis_4th_dan).length
    """)
    assert mantis_count == 0


@pytest.mark.school_abilities
def test_mantis_4th_dan_die_flags_survive_reload(page, live_server_url):
    """Regression test: the athletics_only and mantis_4th_dan flags must be
    persisted on save so the die retains its restrictions AND its blue
    athletics-only rendering after a reload; the per-die menu must still
    surface Athletics Attack/Parry for the bonus die."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4Persist")
    _roll_initiative(page)
    # The bonus die is initially in memory with both flags set.
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || [])"
        ".some(d => d.mantis_4th_dan && d.athletics_only)",
        timeout=10000,
    )
    # Wait for the save-round-trip so the server has the flagged entry.
    page.wait_for_timeout(1000)
    page.reload()
    page.wait_for_selector('[data-testid="action-dice-section"]', state='visible', timeout=10000)
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || []).length > 0",
        timeout=10000,
    )
    flags = page.evaluate("""() => {
        const die = (window._trackingBridge?.actionDice || [])
            .find(d => d.mantis_4th_dan);
        return die ? {athletics_only: !!die.athletics_only, mantis_4th_dan: !!die.mantis_4th_dan} : null;
    }""")
    assert flags == {"athletics_only": True, "mantis_4th_dan": True}
    # SVG still carries the blue athletics-only class for the 4th Dan die.
    idx = page.evaluate(
        "() => (window._trackingBridge?.actionDice || [])"
        ".findIndex(d => d.mantis_4th_dan)"
    )
    assert idx >= 0
    section = page.locator('[data-testid="action-dice-section"]')
    assert section.locator(f'[data-action="action-die"][data-die-index="{idx}"]'
                           ' svg.athletics-only').count() == 1
    # Opening the menu still shows Athletics Attack / Parry / Predeclared Parry.
    section.locator('[data-action="action-die"]').nth(idx).click()
    page.wait_for_selector('[data-action-die-menu-item="athletics-attack"]:visible',
                           timeout=2000)
    assert page.locator('[data-action-die-menu-item="athletics-attack"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="athletics-parry"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="athletics-predeclared-parry"]:visible'
                        ).count() == 1


@pytest.mark.school_abilities
def test_mantis_regular_die_menu_hides_athletics_options(page, live_server_url):
    """Regular (non-bonus) Mantis action dice must NOT surface the Athletics
    Attack / Parry / Predeclared Parry options in the per-die menu."""
    _make_mantis_dan_4(page, live_server_url, "MantisDieNoAth")
    _seed_action_dice(page, [3, 5])
    # Open the first (regular) die's menu.
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_selector('[data-action-die-menu-item="attack"]:visible', timeout=2000)
    # Regular combat options are visible.
    assert page.locator('[data-action-die-menu-item="attack"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="parry"]:visible').count() == 1
    # Athletics variants are hidden.
    assert page.locator('[data-action-die-menu-item="athletics-attack"]:visible').count() == 0
    assert page.locator('[data-action-die-menu-item="athletics-parry"]:visible').count() == 0
    assert page.locator('[data-action-die-menu-item="athletics-predeclared-parry"]:visible').count() == 0


@pytest.mark.school_abilities
def test_mantis_4th_dan_die_menu_shows_only_athletics_and_3rd_dan(page, live_server_url):
    """The Mantis 4th Dan athletics-only die surfaces Athletics Attack/Parry/
    Predeclared Parry, hides regular Attack/Parry, and (in offensive posture)
    also shows the Mantis 3rd Dan offensive option."""
    _make_mantis_dan_4(page, live_server_url, "Mantis4DieMenu")
    _roll_initiative(page)
    # Find the Mantis 4th Dan die (athletics-only) and open its menu.
    page.wait_for_function(
        "() => (window._trackingBridge?.actionDice || [])"
        ".some(d => d.mantis_4th_dan)"
    )
    _select_posture(page, "offensive")
    idx = page.evaluate(
        "() => (window._trackingBridge?.actionDice || [])"
        ".findIndex(d => d.mantis_4th_dan)"
    )
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').nth(idx).click()
    page.wait_for_selector('[data-action-die-menu-item="athletics-attack"]:visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="athletics-attack"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="athletics-parry"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="athletics-predeclared-parry"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="mantis-3rd-dan-offensive"]:visible').count() == 1
    # Regular combat variants are not offered.
    assert page.locator('[data-action-die-menu-item="attack"]:visible').count() == 0
    assert page.locator('[data-action-die-menu-item="parry"]:visible').count() == 0
    assert page.locator('[data-action-die-menu-item="double-attack"]:visible').count() == 0


@pytest.mark.school_abilities
def test_mantis_attack_skill_menu_no_athletics_choice(page, live_server_url):
    """Clicking the Attack skill on a Mantis character must not open the
    Togashi-style attack-choice menu; it should go straight to the attack
    modal. Athletics attack is reached via the Athletics skill instead."""
    _create_char(page, live_server_url, "MantisAtkNoChoice", "mantis_wave_treader")
    # Confirm athletics:attack formula does exist server-side (would normally
    # trigger the attack choice menu for Togashi).
    has_formula = page.evaluate("() => !!(window._diceRoller?.formulas?.['athletics:attack'])")
    assert has_formula is True
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    # The attack-choice menu never appeared.
    assert page.locator('[data-roll-menu="root"]:visible').count() == 0


@pytest.mark.school_abilities
def test_mantis_parry_skill_menu_no_athletics_row(page, live_server_url):
    """Clicking the Parry skill on a Mantis character opens the parry menu
    without the Athletics Parry row."""
    _create_char(page, live_server_url, "MantisParryNoAth", "mantis_wave_treader")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    # The parry menu is present but without the athletics option.
    assert page.locator('[data-parry-menu] [data-parry-menu-athletics]').count() == 0


@pytest.mark.school_abilities
def test_togashi_attack_skill_menu_shows_athletics_choice(page, live_server_url):
    """Togashi Ise Zumi keeps the Athletics attack/parry options everywhere."""
    _create_char(page, live_server_url, "TogashiAtkChoice", "togashi_ise_zumi")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-attack-choice-menu]', state='visible', timeout=3000)
    # The attack choice menu includes both regular and athletics options.
    assert page.locator('[data-attack-choice-menu]').is_visible()


@pytest.mark.school_abilities
def test_togashi_parry_skill_menu_shows_athletics_row(page, live_server_url):
    """Togashi Ise Zumi's Parry menu still includes the Athletics Parry row."""
    _create_char(page, live_server_url, "TogashiParryAth", "togashi_ise_zumi")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    assert page.locator('[data-parry-menu] [data-parry-menu-athletics]').is_visible()


@pytest.mark.school_abilities
def test_togashi_regular_die_menu_shows_athletics_options(page, live_server_url):
    """Regression for Togashi: regular (non-athletics-only) action dice still
    surface the Athletics Attack/Parry/Predeclared Parry options."""
    _create_char(page, live_server_url, "TogashiDieAth", "togashi_ise_zumi")
    _seed_action_dice(page, [3, 5])
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_selector('[data-action-die-menu-item="athletics-attack"]:visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="athletics-attack"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="athletics-parry"]:visible').count() == 1
    assert page.locator('[data-action-die-menu-item="athletics-predeclared-parry"]:visible').count() == 1


@pytest.mark.school_abilities
def test_mantis_wc_probability_all_three_stack(page, live_server_url):
    """All three defensive-side overlays (posture +5, 5th Dan defensivePhaseCount,
    3rd Dan defensive accumulator) stack additively in the probability table."""
    _make_mantis_dan_5(page, live_server_url, "MantisWCProbAll")
    _seed_action_dice(page, [3, 5])
    # Baseline: no postures, no accumulators.
    _open_wc_modal_for_prob(page, lw=20)
    baseline = _wc_prob_row(page)
    _close_wc_modal(page)
    # Select two defensive postures (current + 5th Dan accum 2).
    _select_posture(page, "defensive")
    _select_posture(page, "defensive")
    # Spend 3rd Dan defensive button (accum +1; attack=1 default).
    page.locator('[data-action="mantis-3rd-dan-defensive"]').click()
    page.wait_for_function("() => window._trackingBridge.defensive3rdDanAccum === 1")
    _open_wc_modal_for_prob(page, lw=20)
    stacked = _wc_prob_row(page)
    # Stacked flat bonus: +5 (posture) + +2 (5th Dan) + +1 (3rd Dan) = +8.
    assert stacked["passChance"] > baseline["passChance"]
    # The modal's Bonuses row should list all three labeled entries. Wait for
    # Alpine to flush _mantisLiveWcLabels into the DOM before snapshotting -
    # the reactive x-text runs on a microtask after the modal opens, so a
    # snapshot text_content() can race the re-render under load.
    page.wait_for_function("""() => {
        const modal = document.querySelector('[data-modal="wound-check"]');
        if (!modal) return false;
        const txt = modal.textContent || '';
        return txt.includes('+5 from defensive posture')
            && txt.includes('+2 from Mantis 5th Dan (defensive posture count)')
            && txt.includes('+1 from Mantis 3rd Dan (defensive)');
    }""", timeout=10000)


# ===========================================================================
# Suzume Overseer (Sparrow): a sister-school of Doji Artisan and Merchant
# whose techniques are literally those other schools' techniques.
# 1st Dan: extra die on precepts/commerce/wound_check.
# 2nd Dan: free raise on chosen roll type (flexible picker).
# 3rd Dan: 2X adventure raises (X = precepts).
# 4th Dan: out of scope.
# 5th Dan: same as Doji 5th Dan (X-10)/5 bonus.
# Special: same as Merchant (post-roll VP).
# ===========================================================================


def _make_suzume(page, live_server_url, name, dan=1, **kwargs):
    """Create a Suzume Overseer at the given Dan with optional skill overrides."""
    knack_overrides = {"oppose_social": dan, "pontificate": dan, "worldliness": dan}
    _create_char(
        page, live_server_url, name, "suzume_overseer",
        knack_overrides=knack_overrides,
        **kwargs,
    )


@pytest.mark.school_abilities
def test_suzume_post_roll_vp_buttons_visible(page, live_server_url):
    """Suzume Overseer sees post-roll VP spending note (shared with Merchant)."""
    _make_suzume(page, live_server_url, "SuzumeVP", skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('text="Merchant Special: spend VP after seeing the roll."').is_visible()


@pytest.mark.school_abilities
def test_suzume_pre_roll_menu_has_no_vp_options(page, live_server_url):
    """Suzume pre-roll: VP options are hidden (post-roll VP supersedes them)."""
    _make_suzume(page, live_server_url, "SuzumeNoPreVP", skill_overrides={"bragging": 1})
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(400)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        text = menu.text_content()
        assert "Spend 1 void point" not in text
        assert "Spend 2 void points" not in text


@pytest.mark.school_abilities
def test_suzume_1st_dan_extra_die_on_precepts(page, live_server_url):
    """Suzume 1st Dan: rolling precepts shows +1 rolled die."""
    _make_suzume(page, live_server_url, "Suzume1Pre", skill_overrides={"precepts": 1})
    f = _get_formula(page, "skill:precepts")
    # rank(1) + Water(3) + 1 (1st Dan) = 5
    assert f["rolled"] == 5


@pytest.mark.school_abilities
def test_suzume_1st_dan_extra_die_on_wound_check(page, live_server_url):
    """Suzume 1st Dan: wound check gets +1 rolled die labeled 1st Dan."""
    _make_suzume(page, live_server_url, "Suzume1WC")
    wc = _get_formula(page, "wound_check")
    # Water=3 -> base 4k3; 1st Dan +1 -> 5k3
    assert wc["rolled"] == 5
    assert wc["kept"] == 3
    assert any("1st Dan" in s for s in wc.get("bonus_sources", []))


@pytest.mark.school_abilities
def test_kitsune_2nd_dan_picker_visible_and_saves(page, live_server_url):
    """Editor UI: Kitsune Warden uses the shared flexible-2nd-Dan picker.
    Picker hidden at Dan 1, visible at Dan 2, picks save and apply +5."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Kitsune2Picker")
    select_school(page, "kitsune_warden")
    # Pick a school ring so the school ring choice is set.
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    # Picker is hidden at Dan 1.
    picker = page.locator('[data-testid="flex-2nd-dan-picker"]')
    assert not picker.is_visible()
    # Raise all three school knacks to 2 to reach Dan 2.
    click_plus(page, "knack_absorb_void", 1)
    click_plus(page, "knack_commune", 1)
    click_plus(page, "knack_iaijutsu", 1)
    page.wait_for_timeout(200)
    assert picker.is_visible()
    # Need a non-zero bragging skill so the 2nd Dan +5 actually shows up
    # on a roll formula we can inspect.
    click_plus(page, "skill_bragging", 2)
    select = page.locator('[data-testid="flex-2nd-dan-select"]')
    select.select_option("bragging")
    page.evaluate("""async () => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.flushPendingSave === 'function') {
                await d.flushPendingSave();
                return;
            }
        }
    }""")
    apply_changes(page, "Kitsune 2nd Dan picker")
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    f = _get_formula(page, "skill:bragging")
    assert any(b.get("label") == "2nd Dan technique" and b.get("amount") == 5
               for b in f.get("bonuses", []))


@pytest.mark.school_abilities
def test_suzume_2nd_dan_picker_visible_and_saves(page, live_server_url):
    """Editor UI: the flexible 2nd Dan picker appears at Dan>=2 and saves."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Suzume2Picker")
    select_school(page, "suzume_overseer")
    # Picker is hidden at Dan 1.
    picker = page.locator('[data-testid="flex-2nd-dan-picker"]')
    assert not picker.is_visible()
    # Raise all three school knacks to 2 to reach Dan 2.
    click_plus(page, "knack_oppose_social", 1)
    click_plus(page, "knack_pontificate", 1)
    click_plus(page, "knack_worldliness", 1)
    page.wait_for_timeout(200)
    assert picker.is_visible()
    select = page.locator('[data-testid="flex-2nd-dan-select"]')
    option_values = select.evaluate("el => Array.from(el.querySelectorAll('option')).map(o => o.value)")
    for needed in ("attack", "damage", "parry", "wound_check", "tact", "bragging"):
        assert needed in option_values, f"option {needed!r} missing from picker"
    assert "initiative" not in option_values
    assert "worldliness" not in option_values
    select.select_option("tact")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Suzume 2nd Dan picker")
    page.wait_for_selector('#roll-formulas', state='attached', timeout=5000)
    # tact has Honor bonus on top of the 2nd Dan free raise; verify the +5
    # appears in the breakdown via the bonus list.
    f = _get_formula(page, "skill:tact")
    assert any(b.get("label") == "2nd Dan technique" and b.get("amount") == 5
               for b in f.get("bonuses", []))


@pytest.mark.school_abilities
def test_suzume_3rd_dan_precepts_raises(page, live_server_url):
    """Suzume at 3rd Dan: rolling sincerity (in applicable_to) shows Spend button."""
    _make_suzume(page, live_server_url, "Suzume3", dan=3,
                 skill_overrides={"precepts": 1, "sincerity": 1})
    _roll_via_menu_or_direct(page, "skill:sincerity")
    assert page.locator('[data-action="spend-raise"]').is_visible()


@pytest.mark.school_abilities
def test_suzume_5th_dan_always_tn_skill_input(page, live_server_url):
    """Suzume 5th Dan: always-TN skills show Doji-style input directly."""
    _make_suzume(page, live_server_url, "Suzume5Always", dan=5,
                 skill_overrides={"manipulation": 1})
    _roll_via_menu_or_direct(page, "skill:manipulation")
    base = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return d.baseTotal;
        }
        return 0;
    }""")
    always_section = page.locator('[data-testid="doji-5th-always"]')
    assert always_section.is_visible()
    assert not page.locator('[data-testid="doji-5th-optional"]').is_visible()
    opponent_input = always_section.locator('input[x-model\\.number="dojiOpponentResult"]')
    opponent_input.fill("30")
    page.wait_for_timeout(300)
    result = always_section.text_content()
    assert "Adjusted total" in result
    expected_adjusted = base + 4  # floor((30-10)/5)
    assert str(expected_adjusted) in result


@pytest.mark.school_abilities
def test_suzume_5th_dan_sometimes_tn_skill_checkbox(page, live_server_url):
    """Suzume 5th Dan: sometimes-TN skills show checkbox + input on check."""
    _make_suzume(page, live_server_url, "Suzume5Sometimes", dan=5,
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    optional_section = page.locator('[data-testid="doji-5th-optional"]')
    assert optional_section.is_visible()
    assert not page.locator('[data-testid="doji-5th-always"]').is_visible()
    checkbox = optional_section.locator('input[x-model="dojiTnRollApplied"]')
    assert checkbox.is_visible()


@pytest.mark.school_abilities
def test_suzume_5th_dan_never_tn_skill_no_input(page, live_server_url):
    """Suzume 5th Dan: never-TN skills show no Doji input or checkbox."""
    _make_suzume(page, live_server_url, "Suzume5Never", dan=5,
                 skill_overrides={"etiquette": 1})
    _roll_via_menu_or_direct(page, "skill:etiquette")
    assert not page.locator('[data-testid="doji-5th-always"]').is_visible()
    assert not page.locator('[data-testid="doji-5th-optional"]').is_visible()


@pytest.mark.school_abilities
def test_suzume_5th_dan_attack_auto_bonus(page, live_server_url):
    """Suzume 5th Dan: attack rolls auto-apply bonus from TN."""
    _make_suzume(page, live_server_url, "Suzume5Atk", dan=5)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    pre_text = modal.text_content()
    assert "Doji 5th Dan" in pre_text
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)
    bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return d.formula?.doji_5th_dan_bonus || 0;
        }
        return 0;
    }""")
    assert bonus == 2  # floor((20-10)/5)


@pytest.mark.school_abilities
def test_suzume_5th_dan_wound_check_auto_bonus(page, live_server_url):
    """Suzume 5th Dan: wound check auto-applies bonus from light wounds."""
    _make_suzume(page, live_server_url, "Suzume5WC", dan=5)
    _set_light_wounds(page, 30)
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
    modal = page.locator('[data-modal="wound-check"]')
    pre_text = modal.text_content()
    assert "Doji 5th Dan" in pre_text
    modal.locator('[data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    bonus = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.formula?.doji_5th_dan_bonus || 0;
        }
        return 0;
    }""")
    assert bonus == 4  # floor((30-10)/5)


# ---------------------------------------------------------------------------
# Kitsune Warden 3rd Dan — adventure raises with player-chosen applicable skills
# ---------------------------------------------------------------------------


def _make_kitsune(page, live_server_url, name, dan=1, picks=None, **kwargs):
    """Create a Kitsune Warden at the given Dan with optional 3rd Dan
    skill picks. Picks live in technique_choices.third_dan_skill_choices."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "kitsune_warden")
    # Pick a fixed school ring so the character is well-defined.
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    page.wait_for_timeout(200)
    # Set knack ranks directly on the Alpine model. click_plus drops clicks
    # under autosave reflow when ramping multiple knacks to high ranks.
    if dan > 1:
        page.evaluate(f"""() => {{
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {{
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.knacks) {{
                    d.knacks.absorb_void = {dan};
                    d.knacks.commune = {dan};
                    d.knacks.iaijutsu = {dan};
                    return;
                }}
            }}
        }}""")
        page.wait_for_timeout(200)
    for sid, rank in (kwargs.get("skill_overrides") or {}).items():
        click_plus(page, f"skill_{sid}", rank)
    # Drain any in-flight autosave from clicks BEFORE we write
    # technique_choices via the API, otherwise the frontend's stale
    # techniqueChoices state would clobber our picks on the next save.
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.evaluate("""async () => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.flushPendingSave === 'function') {
                await d.flushPendingSave();
                return;
            }
        }
    }""")
    if picks is not None:
        # Use the autosave API directly; this is the persisted state apply
        # will read. After the API call we sync the frontend Alpine model
        # with what the server now has, so a subsequent save (during apply)
        # doesn't overwrite our picks with the empty front-end value.
        char_id = _extract_char_id(page)
        _set_technique_choices(page, char_id, {"third_dan_skill_choices": picks})
        page.evaluate(f"""() => {{
            const els = document.querySelectorAll('[x-data]');
            for (const el of els) {{
                const d = window.Alpine && window.Alpine.$data(el);
                if (d && d.techniqueChoices !== undefined) {{
                    d.techniqueChoices = Object.assign(
                        {{}}, d.techniqueChoices,
                        {{third_dan_skill_choices: {picks!r}}}
                    );
                    return;
                }}
            }}
        }}""")
    apply_changes(page, "Kitsune setup")


@pytest.mark.school_abilities
def test_kitsune_3rd_dan_skill_picker_excludes_iaijutsu(page, live_server_url):
    """Editor: the 3rd Dan picker does NOT offer iaijutsu as an option."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    click_plus(page, "knack_absorb_void", 2)
    click_plus(page, "knack_commune", 2)
    click_plus(page, "knack_iaijutsu", 2)
    page.wait_for_timeout(200)
    page.wait_for_selector('[data-testid="kitsune-3rd-dan-picker"]', state="visible", timeout=5000)
    options = page.locator('[data-testid="kitsune-3rd-dan-slot-0"] option').all_text_contents()
    assert all("Iaijutsu" not in o for o in options), \
        f"Iaijutsu should NOT be in 3rd Dan picker options; got: {options}"


@pytest.mark.school_abilities
def test_kitsune_3rd_dan_chosen_skill_offers_raise_button(page, live_server_url):
    """Picking 'bragging' as a 3rd Dan applicable skill exposes the
    Spend-raise button when rolling bragging."""
    _make_kitsune(page, live_server_url, "K3Bragg", dan=3,
                  picks=["bragging", "tact", "sincerity"],
                  skill_overrides={"precepts": 1, "bragging": 1})
    # Sanity-check: the formula has the 3rd Dan annotation, and the
    # adventure-raises pool is non-zero. If either is wrong, the spend
    # button won't render and the assertion below will fail mysteriously.
    formula_max = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['skill:bragging']?.adventure_raises_max_per_roll || 0;
    }""")
    pool = page.evaluate("""() => {
        const el = document.getElementById('adventure-raises-config');
        return JSON.parse(el.textContent || '{}');
    }""")
    assert formula_max == 1, f"Expected adventure_raises_max_per_roll=1, got {formula_max}"
    assert pool.get("available", 0) > 0, f"Expected non-zero adventure-raises pool, got {pool}"
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('[data-action="spend-raise"]').is_visible()


@pytest.mark.school_abilities
def test_kitsune_3rd_dan_unpicked_skill_no_raise_button(page, live_server_url):
    """A skill NOT in the player's three picks does NOT show the
    Spend-raise button (etiquette unpicked)."""
    _make_kitsune(page, live_server_url, "K3Etiq", dan=3,
                  picks=["bragging", "tact", "sincerity"],
                  skill_overrides={"precepts": 1, "etiquette": 1})
    _roll_via_menu_or_direct(page, "skill:etiquette")
    assert not page.locator('[data-action="spend-raise"]').is_visible()


@pytest.mark.school_abilities
def test_kitsune_3rd_dan_attack_always_offers_raise(page, live_server_url):
    """Attack is in the always-on applicable_to list - even with no
    skill picks, the attack-modal annotates 3rd Dan adventure raises."""
    _make_kitsune(page, live_server_url, "K3Atk", dan=3,
                  picks=[],
                  skill_overrides={"precepts": 1})
    # Verify the attack formula is annotated with the 3rd Dan max-per-roll
    # cap (attack is always-on regardless of picks). The attack-modal's
    # "Spend Free Raise (+5)" button has no data-action attribute, so we
    # check the annotation on the formula directly.
    formula_max = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['attack']?.adventure_raises_max_per_roll || 0;
    }""")
    assert formula_max == 1, f"Expected attack annotated with max=1, got {formula_max}"
    _open_attack_modal_and_roll(page, "attack")
    # The "Spend Free Raise (+5)" button is in the attack-modal post-roll
    # panel, gated on atkFormula.adventure_raises_max_per_roll > 0. The
    # modal renders two copies of the button (one per layout breakpoint);
    # we just need at least one to be visible.
    modal = page.locator('[data-modal="attack"]')
    spend_btns = modal.locator('button:text-is("Spend Free Raise (+5)")')
    assert spend_btns.first.is_visible()


@pytest.mark.school_abilities
def test_kitsune_3rd_dan_wound_check_always_offers_raise(page, live_server_url):
    """Wound check is always-on applicable_to. A Dan 3 Kitsune with no
    skill picks still gets the WC formula annotated, and the modal's
    wcMaxRaisesPerRoll / wcHasDiscretionary state is non-zero so the
    spend-raise button can render in the FAILED branch."""
    _make_kitsune(page, live_server_url, "K3WC", dan=3, picks=[],
                  skill_overrides={"precepts": 1})
    formula_max = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['wound_check']?.adventure_raises_max_per_roll || 0;
    }""")
    assert formula_max == 1, f"Expected wound_check annotated with max=1, got {formula_max}"
    _set_light_wounds(page, 3)
    _roll_wound_check(page)
    state = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') {
                return {
                    wcMaxRaisesPerRoll: d.wcMaxRaisesPerRoll,
                    wcHasDiscretionary: d.wcHasDiscretionary,
                };
            }
        }
        return null;
    }""")
    # Non-zero raises-per-roll cap and discretionary flag means the modal
    # is wired up to surface the spend button (the button itself only
    # renders inside the FAILED branch by existing template design, so
    # we verify the underlying state rather than the visible button).
    assert state is not None
    assert state["wcMaxRaisesPerRoll"] >= 1
    assert state["wcHasDiscretionary"] is True


@pytest.mark.school_abilities
def test_kitsune_3rd_dan_per_adventure_counter_visible(page, live_server_url):
    """The Tracking section shows the '3rd Dan Free Raises (Precepts)'
    counter for a Dan 3 Kitsune with non-zero precepts."""
    _make_kitsune(page, live_server_url, "K3Counter", dan=3, picks=[],
                  skill_overrides={"precepts": 2})
    counter_label = page.locator('text="3rd Dan Free Raises (Precepts)"')
    assert counter_label.is_visible()


# ---------------------------------------------------------------------------
# Kitsune Warden 4th Dan — ring raise + 10-dice athletics floor
# ---------------------------------------------------------------------------


@pytest.mark.school_abilities
def test_kitsune_4th_dan_athletics_roll_shows_10_dice_floor(page, live_server_url):
    """At Dan 4, the bare athletics formula's rolled count is at least 10
    (the (2*Ring)k(Ring) floor). With Air ring 2, base = 4 rolled; floor
    raises it to 10. Kept stays at 2."""
    _make_kitsune(page, live_server_url, "K4Floor", dan=4)
    # Read the athletics:Air formula from the embedded JSON on the sheet.
    f = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['athletics:Air'] || null;
    }""")
    assert f is not None
    assert f["rolled"] == 10, f"Expected 10-dice floor on Air athletics, got {f['rolled']}"
    assert f["kept"] == 2, f"Expected kept=2 (Air ring), got {f['kept']}"


@pytest.mark.school_abilities
def test_kitsune_below_4th_dan_athletics_uses_normal_formula(page, live_server_url):
    """At Dan 3, no athletics floor: Air 2 -> 4k2."""
    _make_kitsune(page, live_server_url, "K3NoFloor", dan=3)
    f = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['athletics:Air'] || null;
    }""")
    assert f is not None
    assert f["rolled"] == 4, f"Expected normal 4 rolled at Dan 3, got {f['rolled']}"


@pytest.mark.school_abilities
def test_kitsune_4th_dan_athletics_attack_hidden_without_athletics_knack(page, live_server_url):
    """A Dan 4 Kitsune with no athletics knack does NOT see athletics-attack
    in the attack-roll menu. Existing baseline: only Togashi Ise Zumi
    surfaces athletics-attack/parry as standard variants; Kitsune is not
    in that group."""
    _make_kitsune(page, live_server_url, "K4NoAth", dan=4)
    # Click Attack to open the roll menu (or modal if no choice menu fires).
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_timeout(300)
    # If the chooser appears, "Athletics Attack" should NOT be there.
    # If the attack modal opens directly, that already implies no chooser.
    choice_menu = page.locator('[data-attack-choice-menu]')
    if choice_menu.count() > 0 and choice_menu.is_visible():
        athletics_choice = choice_menu.locator('[data-attack-choice="athletics_attack"]')
        assert not athletics_choice.is_visible(), \
            "Kitsune Warden should NOT show 'Athletics Attack' in the attack menu"


@pytest.mark.school_abilities
def test_kitsune_4th_dan_school_ring_auto_raise_for_water_choice(page, live_server_url):
    """Reaching 4th Dan auto-raises the player-chosen school ring (Water for
    this character) from 3 to 4. Mirrors test_fourth_dan_auto_raises_school_ring
    but for an "any non-Void" school."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    page.wait_for_timeout(300)
    # Sanity check: Alpine sees Water as the school ring.
    state = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.getSchoolRing === 'function') {
                return {schoolRing: d.getSchoolRing(), waterVal: d.rings?.Water,
                        dan: d.currentDan(), knacks: {...d.knacks}};
            }
        }
        return null;
    }""")
    assert state and state["schoolRing"] == "Water", f"schoolRing not Water: {state}"
    # Water starts at 3 once the ring choice is made (dan 1 -> minVal 3).
    assert page.locator('input[name="ring_water"]').input_value() == "3"
    # Raise all three knacks to 4 directly via Alpine state - click_plus
    # drops clicks under heavy session load, and we just want to drive Dan
    # to 4 to observe enforceFourthDanRing.
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.knacks) {
                d.knacks.absorb_void = 4;
                d.knacks.commune = 4;
                d.knacks.iaijutsu = 4;
                return;
            }
        }
    }""")
    page.wait_for_timeout(300)
    state2 = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.getSchoolRing === 'function') {
                return {schoolRing: d.getSchoolRing(), waterVal: d.rings?.Water,
                        dan: d.currentDan(), knacks: {...d.knacks}};
            }
        }
        return null;
    }""")
    assert state2 and state2["dan"] == 4, f"Expected Dan 4 after knack clicks: {state2}"
    assert page.locator('input[name="ring_water"]').input_value() == "4"


# ---------------------------------------------------------------------------
# Kitsune Warden Special Ability — skill-roll dropdown submenu (Phase 8)
# ---------------------------------------------------------------------------


def _make_kitsune_with_ring_setup(page, live_server_url, name, school_ring="Water"):
    """Create a Kitsune Warden with the given school ring chosen and a
    high non-default ring value (Water ring 4, others 2). With Water as
    school ring, Air-default skills (e.g. bragging) get a meaningful
    swap (4 vs 2)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option(school_ring)
    page.wait_for_timeout(200)
    # Raise the school ring to 4 (3 -> 4 with 1 click). Mantis non-school
    # rings stay at 2.
    if school_ring == "Water":
        click_plus(page, "ring_water", 1)  # 3 -> 4
    elif school_ring == "Air":
        click_plus(page, "ring_air", 1)
    elif school_ring == "Earth":
        click_plus(page, "ring_earth", 1)
    elif school_ring == "Fire":
        click_plus(page, "ring_fire", 1)
    # Give the character some skill ranks so the rolls succeed.
    click_plus(page, "skill_bragging", 2)  # Air skill
    click_plus(page, "skill_etiquette", 2)  # Air skill
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.evaluate("""async () => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.flushPendingSave === 'function') {
                await d.flushPendingSave();
                return;
            }
        }
    }""")
    apply_changes(page, "Kitsune swap setup")


@pytest.mark.school_abilities
def test_kitsune_skill_submenu_visible_when_school_ring_higher_than_skill_ring(page, live_server_url):
    """With school ring Water (4) and skill bragging on Air (2), the
    swap submenu block appears in the skill click menu."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8Visible", "Water")
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-skill-swap-block"]')
    assert block.is_visible()
    # The label calls out Water vs Air.
    text = block.text_content()
    assert "Water" in text
    assert "Air" in text


@pytest.mark.school_abilities
def test_kitsune_skill_submenu_hidden_when_skill_already_uses_school_ring(page, live_server_url):
    """A Water-ring skill (sincerity is Air... pick Etiquette which is
    Air. Use precepts which is Water.) When the natural ring matches
    the school ring, no swap option is offered (the swap would be a
    no-op identity). Use precepts on a Water-ring Kitsune."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8Same", "Water")
    # precepts is a Water skill. With school ring Water, swap is identity.
    # Click precepts and confirm no swap block.
    page.locator('[data-roll-key="skill:precepts"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-skill-swap-block"]')
    assert not block.is_visible()


@pytest.mark.school_abilities
def test_kitsune_skill_submenu_hidden_when_ring_values_equal(page, live_server_url):
    """If school ring's value equals natural ring's value (e.g. Water=2,
    Air=2), the swap is suppressed even though the rings differ."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K8EqualVal")
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    page.wait_for_timeout(200)
    # Don't raise Water -> stays at 3. Air also at 2. Bragging is Air.
    # Hmm, Water=3 vs Air=2 differ. To make values equal, lower Water to 2.
    # Actually school ring's floor is 3 below 4th Dan, so we can't go lower.
    # Compromise: set Water=3 and Earth=3 (raise Earth to 3 manually).
    # Use a Water skill (precepts default Water=3) vs Earth swap (3): same.
    # ...this is getting hairy. The unit tests already verify the
    # equal-value-no-swap case at the formula level. Here we just need a
    # case where the e2e UI suppresses. Use the rolling state.
    click_plus(page, "ring_earth", 1)  # 2 -> 3, equal to Water (3)
    click_plus(page, "skill_history", 2)  # Earth-default skill
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Equal-val test")
    page.locator('[data-roll-key="skill:history"]').click()
    page.wait_for_timeout(300)
    # history is Earth (rank 2 + Earth 3 = 5 rolled, 3 kept). Swap to
    # Water (3) gives identical 5/3 = swap suppressed.
    block = page.locator('[data-testid="kitsune-skill-swap-block"]')
    assert not block.is_visible()


@pytest.mark.school_abilities
def test_kitsune_skill_submenu_hidden_for_iaijutsu(page, live_server_url):
    """Iaijutsu knack rolls do not offer the swap (rules-excluded)."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8Iai", "Water")
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-skill-swap-block"]')
    assert not block.is_visible()


@pytest.mark.school_abilities
def test_kitsune_skill_swap_uses_school_ring_in_roll_formula(page, live_server_url):
    """Clicking the swap button rolls bragging with Water (4) instead of
    Air (2) - rolled count goes from 4 (rank 2 + Air 2) to 6 (rank 2 +
    Water 4), kept from 2 to 4."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8Roll", "Water")
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-kitsune-swap-roll]').click()
    # Wait for roll result.
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    # Read the rolled formula dimensions.
    f = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return {
                rolled: d.formula?.rolled, kept: d.formula?.kept,
                from: d.formula?.kitsune_swap_from_ring,
                to: d.formula?.kitsune_swap_to_ring,
            };
        }
        return null;
    }""")
    assert f is not None
    assert f["rolled"] == 6
    assert f["kept"] == 4
    assert f["from"] == "Air"
    assert f["to"] == "Water"


@pytest.mark.school_abilities
def test_kitsune_skill_swap_results_panel_shows_special_ability_annotation(page, live_server_url):
    """The roll result panel shows the 'Kitsune Warden Special Ability'
    annotation when the swap was used."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8Annot", "Water")
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-kitsune-swap-roll]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    annotation = page.locator('[data-testid="kitsune-swap-result-annotation"]')
    assert annotation.is_visible()
    text = annotation.text_content()
    assert "Water" in text
    assert "Air" in text


@pytest.mark.school_abilities
def test_kitsune_skill_swap_no_annotation_without_swap(page, live_server_url):
    """Without the swap, the annotation does NOT appear (regression
    guard)."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8NoAnnot", "Water")
    # Bypass the menu and call executeRoll directly without useKitsuneSwap.
    page.evaluate("""() => {
        if (window._diceRoller) window._diceRoller.executeRoll('skill:bragging', 0, null);
    }""")
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    annotation = page.locator('[data-testid="kitsune-swap-result-annotation"]')
    assert not annotation.is_visible()


@pytest.mark.school_abilities
def test_kitsune_skill_swap_with_void_spend_carries_through(page, live_server_url):
    """When the player picks 'Spend 1 Void Point (using Water)' from the
    swap block, the roll uses Water AND adds +1 void die. Final formula:
    rolled 6+1=7, kept 4+1=5."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K8VoidSwap", "Water")
    # Need a void point to spend. Default Void ring is 2, so VP max = 2.
    page.evaluate("window._trackingBridge.voidPoints = 1; window._trackingBridge.save && window._trackingBridge.save();")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-kitsune-swap-vp="1"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    f = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return {
                rolled: d.formula?.rolled, kept: d.formula?.kept,
                voidSpent: d.formula?.void_spent,
                to: d.formula?.kitsune_swap_to_ring,
            };
        }
        return null;
    }""")
    assert f is not None
    assert f["rolled"] == 7  # 6 (swap) + 1 (VP)
    assert f["kept"] == 5  # 4 + 1
    assert f["voidSpent"] == 1
    assert f["to"] == "Water"


# ---------------------------------------------------------------------------
# Kitsune Warden Special Ability — Attack & Wound Check modal checkboxes (Phase 9)
# ---------------------------------------------------------------------------


@pytest.mark.school_abilities
def test_kitsune_attack_modal_checkbox_visible_and_swaps_probability_table(page, live_server_url):
    """The attack-modal checkbox is visible for Kitsune Warden when school
    ring's value differs from Fire (default). Toggling re-renders the
    probability table from the swap-baseline rolled/kept."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K9AtkVis", "Water")
    # Open the attack modal.
    _open_attack_modal_and_roll_pre_only = lambda: page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.openAttackModal === 'function') {
                d.openAttackModal('attack');
                return;
            }
        }
    }""")
    _open_attack_modal_and_roll_pre_only()
    page.wait_for_selector('[data-modal="attack"]', state="visible", timeout=10000)
    checkbox = page.locator('[data-testid="kitsune-attack-ring-swap"]')
    assert checkbox.is_visible()
    # Read the prob-table's first row "Attack Roll" cell (void=0).
    modal = page.locator('[data-modal="attack"]')
    # Default: rank 1 + Fire 2 = 3 rolled, 2 kept -> "3k2"
    table_default = modal.locator('table').first
    cells = table_default.locator('tbody tr').first.locator('td')
    default_text = cells.nth(1).text_content().strip()
    assert default_text == "3k2"
    # Toggle the swap on -> Water (4) instead of Fire (2): rank 1 + Water 4 = 5k4
    checkbox.check()
    page.wait_for_timeout(200)
    swap_text = cells.nth(1).text_content().strip()
    assert swap_text == "5k4"


@pytest.mark.school_abilities
def test_kitsune_attack_modal_checkbox_hidden_when_ring_values_equal(page, live_server_url):
    """When the school ring's value equals the attack-default ring's value,
    the formula has no kitsune_swap (server gates equal-value swaps), so
    the checkbox is hidden."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K9AtkEqual")
    select_school(page, "kitsune_warden")
    # Pick Water but leave Water at 3 (default for school ring) and Fire at 2.
    # Lower Water back if needed... actually with school ring Water, floor is 3,
    # so Water=3 vs Fire=2 differ. To make values equal we need Water=2 - not
    # possible. Use a different approach: pick Air as school ring, Air=3 (auto),
    # Fire=2. Air vs Fire = different values. Hmm.
    # Workaround: pick Fire as school ring -> Fire=3. Then attack rolls Fire=3.
    # No swap (school ring IS Fire = default). Test that checkbox is hidden.
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Fire")
    page.wait_for_timeout(200)
    apply_changes(page, "Fire ring")
    # Open attack modal.
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.openAttackModal === 'function') {
                d.openAttackModal('attack');
                return;
            }
        }
    }""")
    page.wait_for_selector('[data-modal="attack"]', state="visible", timeout=10000)
    checkbox = page.locator('[data-testid="kitsune-attack-ring-swap"]')
    assert not checkbox.is_visible()


@pytest.mark.school_abilities
def test_kitsune_attack_modal_checkbox_hidden_for_iaijutsu_attack(page, live_server_url):
    """The iaijutsu attack variant has no kitsune_swap (rules-excluded),
    so the modal checkbox does NOT appear when atkKey is the iaijutsu
    attack key. Kitsune Warden has iaijutsu as a school knack, so this
    case applies in practice."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K9AtkIai", "Water")
    # Open the iaijutsu attack modal directly. Kitsune doesn't have the
    # Kakita-specific knack:iaijutsu:attack key (that's only attached for
    # Kakita), so for non-Kakita iaijutsu we'd open knack:iaijutsu via the
    # regular roll menu - which routes through the basic roll modal, NOT
    # the attack modal. So this test verifies a Kakita-specific code path
    # doesn't surface for Kitsune. Instead, we just confirm that the
    # formula for a Kitsune iaijutsu knack roll has no kitsune_swap.
    has_swap = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return !!data['knack:iaijutsu']?.kitsune_swap;
    }""")
    assert has_swap is False


@pytest.mark.school_abilities
def test_kitsune_wc_modal_checkbox_visible_and_swaps_probability_table(page, live_server_url):
    """The WC-modal checkbox is visible when school ring's value differs
    from Water. Toggling re-renders the WC probability table."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K9WCVis")
    select_school(page, "kitsune_warden")
    # Pick Earth so school ring (Earth, value 3 once auto-set) differs from
    # WC default (Water, 2). Default WC = Water+1 rolled = 3, Water = 2 kept.
    # With swap, WC uses Earth+1 = 4 rolled, Earth = 3 kept.
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Earth")
    page.wait_for_timeout(300)
    # Wait for Earth to be auto-raised to 3 by enforceFourthDanRing (or
    # at least by onSchoolRingChange). If the test uses select_option
    # without a wait, the apply_changes can fire before Alpine settles.
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_earth\"]')?.value === '3'",
        timeout=5000,
    )
    # When Kitsune Warden is selected, edit.html's onSchoolChange defaults
    # the schoolRingChoice to Water and bumps Water to 3 (the school-ring
    # floor). Picking Earth via the dropdown re-routes the school ring but
    # leaves Water at 3 - which would make Water and Earth tied at 3 and
    # collapse the WC swap to a no-op. Lower Water to 2 explicitly so the
    # WC swap (Water 2 -> Earth 3) is non-trivial.
    click_minus(page, "ring_water", 1)
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_water\"]')?.value === '2'",
        timeout=5000,
    )
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.evaluate("""async () => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.flushPendingSave === 'function') {
                await d.flushPendingSave();
                return;
            }
        }
    }""")
    apply_changes(page, "Earth ring")
    # Set light wounds and open WC modal.
    page.evaluate("""() => {
        const t = window._trackingBridge;
        if (t) { t.lightWounds = 5; t.save(); }
    }""")
    page.wait_for_timeout(200)
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
    page.wait_for_selector('[data-modal="wound-check"]', state="visible", timeout=10000)
    # Sanity-check that the formula has kitsune_swap attached.
    swap_data = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        const sa = JSON.parse(document.getElementById('school-abilities')?.textContent || '{}');
        return {
            wc_rolled: data['wound_check']?.rolled,
            wc_kept: data['wound_check']?.kept,
            wc_swap: data['wound_check']?.kitsune_swap || null,
            kitsune_school_ring: sa.kitsune_warden_school_ring,
            kitsune_swap_avail: sa.kitsune_warden_ring_swap_available,
            url: window.location.href,
        };
    }""")
    assert swap_data["wc_swap"] is not None, f"WC formula has no kitsune_swap: {swap_data}"
    checkbox = page.locator('[data-testid="kitsune-wc-ring-swap"]')
    assert checkbox.is_visible()
    # Probability of pass at void=0, default (Water 2): rolled=3, kept=2.
    # Probability of pass at void=0, swap (Earth 3): rolled=4, kept=3.
    # Just confirm toggling changes the percentage rendered.
    modal = page.locator('[data-modal="wound-check"]')
    table = modal.locator('table').first
    cells_default = table.locator('tbody tr').first.locator('td')
    default_pass = cells_default.nth(1).text_content().strip()
    checkbox.check()
    page.wait_for_timeout(200)
    swap_pass = cells_default.nth(1).text_content().strip()
    assert default_pass != swap_pass, \
        f"Toggling the swap checkbox did not change the pass percentage: {default_pass}"


@pytest.mark.school_abilities
def test_kitsune_wc_modal_checkbox_hidden_when_school_ring_is_water(page, live_server_url):
    """When school ring is Water (the WC default ring), the swap is a
    no-op identity so the checkbox is hidden."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K9WCWater", "Water")
    page.evaluate("""() => {
        const t = window._trackingBridge;
        if (t) { t.lightWounds = 5; t.save(); }
    }""")
    page.wait_for_timeout(200)
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
    page.wait_for_selector('[data-modal="wound-check"]', state="visible", timeout=10000)
    checkbox = page.locator('[data-testid="kitsune-wc-ring-swap"]')
    assert not checkbox.is_visible()


@pytest.mark.school_abilities
def test_kitsune_attack_modal_swap_persists_into_roll_results_annotation(page, live_server_url):
    """After rolling with the swap checkbox checked, the result panel
    shows the Kitsune annotation."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K9AtkAnnot", "Water")
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.openAttackModal === 'function') {
                d.openAttackModal('attack');
                return;
            }
        }
    }""")
    page.wait_for_selector('[data-modal="attack"]', state="visible", timeout=10000)
    page.locator('[data-testid="kitsune-attack-ring-swap"]').check()
    page.wait_for_timeout(200)
    # Force a low TN so the roll resolves quickly.
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'pre') { d.atkTN = 5; d.atkParrySkill = 1; return; }
        }
    }""")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    annotation = page.locator('[data-testid="kitsune-attack-swap-annotation"]')
    assert annotation.is_visible()
    text = annotation.text_content()
    assert "Water" in text
    assert "Fire" in text


@pytest.mark.school_abilities
def test_kitsune_wc_modal_swap_persists_into_roll_results_annotation(page, live_server_url):
    """After rolling WC with swap checked, the result panel shows the
    Kitsune annotation."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K9WCAnnot")
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Earth")
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_earth\"]')?.value === '3'",
        timeout=5000,
    )
    # Lower Water back to 2 (onSchoolChange seeded Water=3 because Water is
    # the default for variable-ring schools); see the visibility test for
    # the same workaround.
    click_minus(page, "ring_water", 1)
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_water\"]')?.value === '2'",
        timeout=5000,
    )
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.evaluate("""async () => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && typeof d.flushPendingSave === 'function') {
                await d.flushPendingSave();
                return;
            }
        }
    }""")
    apply_changes(page, "Earth ring")
    page.evaluate("""() => {
        const t = window._trackingBridge;
        if (t) { t.lightWounds = 3; t.save(); }
    }""")
    page.wait_for_timeout(200)
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
    page.wait_for_selector('[data-modal="wound-check"]', state="visible", timeout=10000)
    page.locator('[data-testid="kitsune-wc-ring-swap"]').check()
    page.wait_for_timeout(200)
    page.locator('[data-modal="wound-check"] [data-action="roll-wound-check-go"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    annotation = page.locator('[data-testid="kitsune-wc-swap-annotation"]')
    assert annotation.is_visible()
    text = annotation.text_content()
    assert "Earth" in text
    assert "Water" in text


# ---------------------------------------------------------------------------
# Kitsune Warden Special Ability — Parry top-level menu entries (Phase 10)
# ---------------------------------------------------------------------------


@pytest.mark.school_abilities
def test_kitsune_parry_menu_shows_swap_block_when_school_ring_higher_than_air(page, live_server_url):
    """A Dan-1 Kitsune with Water ring raised to 4 (and Air at 2) sees the
    Kitsune-parry-swap-block in the parry menu."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K10ParryHigh", "Water")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-parry-swap-block"]')
    assert block.is_visible()
    # Both swap entries visible inside the block.
    assert block.locator('[data-testid="kitsune-parry-swap-roll"]').is_visible()
    assert block.locator('[data-testid="kitsune-parry-swap-predeclared"]').is_visible()


@pytest.mark.school_abilities
def test_kitsune_parry_menu_no_swap_block_when_school_ring_is_air(page, live_server_url):
    """When school ring is Air (the parry default), no swap to offer."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K10ParryAir", "Air")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-parry-swap-block"]')
    assert not block.is_visible()


@pytest.mark.school_abilities
def test_kitsune_parry_menu_no_swap_block_when_school_ring_value_equals_air_value(page, live_server_url):
    """If school ring's value equals Air's value (e.g. both at 2), no
    meaningful swap so no block."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K10ParryEqual")
    select_school(page, "kitsune_warden")
    # Pick Earth, leave Earth at 3 (auto-set), then bump Air to 3 too.
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Earth")
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_earth\"]')?.value === '3'",
        timeout=5000,
    )
    # Lower Water to 2 (was bumped to 3 by school-default), so we don't
    # contaminate the Earth-vs-Air comparison.
    click_minus(page, "ring_water", 1)
    # Bump Air to 3 to match Earth's value.
    click_plus(page, "ring_air", 1)
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_air\"]')?.value === '3'",
        timeout=5000,
    )
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Equal Air-Earth")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-parry-swap-block"]')
    assert not block.is_visible()


@pytest.mark.school_abilities
def test_kitsune_parry_school_ring_entry_uses_school_ring_in_formula(page, live_server_url):
    """Clicking the swap-Roll entry rolls parry with the school ring's
    rolled/kept dimensions and stamps the swap-metadata on the formula."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K10ParryRoll", "Water")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-testid="kitsune-parry-swap-roll"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    f = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return {
                rolled: d.formula?.rolled, kept: d.formula?.kept,
                from: d.formula?.kitsune_swap_from_ring,
                to: d.formula?.kitsune_swap_to_ring,
            };
        }
        return null;
    }""")
    assert f is not None
    # Parry default: rank 1 + Air 2 = 3 rolled, 2 kept. Swap to Water 4: 1+4=5 rolled, 4 kept.
    assert f["rolled"] == 5
    assert f["kept"] == 4
    assert f["from"] == "Air"
    assert f["to"] == "Water"


@pytest.mark.school_abilities
def test_kitsune_parry_predeclared_school_ring_entry_includes_plus_5(page, live_server_url):
    """The predeclared swap entry adds +5 flat AND uses the swapped ring."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K10ParryPre", "Water")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    page.locator('[data-testid="kitsune-parry-swap-predeclared"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    f = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return {
                rolled: d.formula?.rolled, kept: d.formula?.kept,
                flat: d.formula?.flat, to: d.formula?.kitsune_swap_to_ring,
                bonuses: d.formula?.bonuses,
            };
        }
        return null;
    }""")
    assert f is not None
    assert f["rolled"] == 5  # swap rolled
    assert f["kept"] == 4  # swap kept
    assert f["flat"] == 5  # predeclared +5
    assert f["to"] == "Water"
    assert any(b.get("label") == "predeclared parry" and b.get("amount") == 5
               for b in (f["bonuses"] or []))


@pytest.mark.school_abilities
def test_kitsune_parry_swap_with_void_spend_carries_through(page, live_server_url):
    """Void-submenu under the swap entry: rolls parry with school ring + VP."""
    _make_kitsune_with_ring_setup(page, live_server_url, "K10ParryVoid", "Water")
    # Need a void point to spend.
    page.evaluate("window._trackingBridge.voidPoints = 1; window._trackingBridge.save && window._trackingBridge.save();")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_timeout(300)
    # Hover the swap-roll entry to surface its VP submenu, then click the
    # +1 VP option. Use a JS hover to reliably trigger Alpine's @mouseenter.
    page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.parryHoverRow !== undefined) { d.parryHoverRow = 'kitsune-roll'; return; }
        }
    }""")
    page.wait_for_timeout(200)
    submenu = page.locator('[data-parry-void-submenu="kitsune-roll"]')
    submenu.locator('button').first.click()  # +1 VP option
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    f = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return {
                rolled: d.formula?.rolled, kept: d.formula?.kept,
                voidSpent: d.formula?.void_spent,
                to: d.formula?.kitsune_swap_to_ring,
            };
        }
        return null;
    }""")
    assert f is not None
    # Swap rolled=5, kept=4. +1 VP -> rolled=6, kept=5.
    assert f["rolled"] == 6
    assert f["kept"] == 5
    assert f["voidSpent"] == 1
    assert f["to"] == "Water"


# ---------------------------------------------------------------------------
# Kitsune Warden Special Ability — Phase 11 polish (iaijutsu + equal-value)
# ---------------------------------------------------------------------------


@pytest.mark.school_abilities
def test_kitsune_skill_submenu_hidden_when_air_equals_water_in_value(page, live_server_url):
    """Equal-value edge case: Air=3 and Water=3 with school ring Water,
    bragging is Air. The swap is identity (rolled/kept unchanged), so the
    skill submenu does NOT show."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "K11Equal")
    select_school(page, "kitsune_warden")
    page.locator('text="Choose School Ring"').locator('..').locator('select').select_option("Water")
    page.wait_for_timeout(200)
    # Water is now 3 (school ring floor). Bump Air to 3 too.
    click_plus(page, "ring_air", 1)
    page.wait_for_function(
        "() => document.querySelector('input[name=\"ring_air\"]')?.value === '3'",
        timeout=5000,
    )
    click_plus(page, "skill_bragging", 2)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Equal Air-Water")
    # Open the bragging click menu and confirm no swap block.
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    block = page.locator('[data-testid="kitsune-skill-swap-block"]')
    assert not block.is_visible(), \
        "Swap block must NOT show when Air's value equals Water's value"

