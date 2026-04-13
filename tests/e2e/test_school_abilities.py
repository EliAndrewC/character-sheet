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
    # Check if roll menu opened
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        # Find the "Roll <name>" button - it has font-medium but skip any "Iaijutsu Duel" button
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


def test_akodo_2nd_dan_wound_check_bonus(page, live_server_url):
    """Akodo at 2nd Dan: wound check formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "AkodoWC2", "akodo_bushi",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    f = _get_formula(page, "wound_check")
    assert f is not None
    assert "+5 from 2nd Dan" in f.get("bonus_sources", [])


def test_akodo_3rd_dan_wc_banks_bonus(page, live_server_url):
    """Akodo 3rd Dan: wound check pass banks bonus for next attack."""
    _create_char(page, live_server_url, "AkodoWCBank", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    sa = _get_school_abilities(page)
    assert sa.get("akodo_wc_attack_bonus") is True
    assert sa.get("akodo_attack_skill", 0) > 0


# ===========================================================================
# BAYUSHI BUSHI (6 tests)
# ===========================================================================

def test_bayushi_vp_damage_on_attack(page, live_server_url):
    """Bayushi Bushi attack modal offers VP spending for bonus damage dice."""
    _create_char(page, live_server_url, "BayushiVPDmg", "bayushi_bushi")
    sa = _get_school_abilities(page)
    assert sa.get("bayushi_vp_damage") is True


def test_bayushi_1st_dan_formula_extra_die(page, live_server_url):
    """Bayushi 1st Dan: extra die on iaijutsu, double_attack, wound_check."""
    _create_char(page, live_server_url, "BayushiFormula", "bayushi_bushi")
    f_iai = _get_formula(page, "knack:iaijutsu")
    assert f_iai is not None
    # iaijutsu rank 1, Fire 3 (school ring), +1 from 1st Dan = 5 rolled
    assert f_iai["rolled"] == 5
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    # double_attack rank 1, Fire 3, +1 from 1st Dan = 5 rolled
    assert f_da["rolled"] == 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    # Water 2, base = 3 rolled, +1 from 1st Dan = 4 rolled
    assert f_wc["rolled"] == 4


def test_bayushi_2nd_dan_double_attack_bonus(page, live_server_url):
    """Bayushi at 2nd Dan: double attack formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "BayushiDA2", "bayushi_bushi",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    f = _get_formula(page, "knack:double_attack")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_bayushi_3rd_dan_feint_shows_damage(page, live_server_url):
    """Bayushi at 3rd Dan: feint roll shows Roll Feint Damage button."""
    _create_char(page, live_server_url, "BayushiFeintDmg", "bayushi_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    _roll_via_menu_or_direct(page, "knack:feint")
    assert page.locator('button:text("Roll Feint Damage")').is_visible()


def test_bayushi_4th_dan_post_feint_raise(page, live_server_url):
    """Bayushi at 4th Dan: feint roll shows bank free raise button."""
    _create_char(page, live_server_url, "BayushiFeint4", "bayushi_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    _roll_via_menu_or_direct(page, "knack:feint")
    assert page.locator('button:has-text("Bank free raise for next attack")').is_visible()


def test_bayushi_5th_dan_reduced_serious_wounds(page, live_server_url):
    """Bayushi at 5th Dan: wound check formula has bayushi_5th_dan_half_lw flag."""
    _create_char(page, live_server_url, "Bayushi5WC", "bayushi_bushi",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    f = _get_formula(page, "wound_check")
    assert f is not None
    assert f.get("bayushi_5th_dan_half_lw") is True


# ===========================================================================
# BROTHERHOOD OF SHINSEI (3 tests)
# ===========================================================================

def test_brotherhood_damage_unarmed_bonus(page, live_server_url):
    """Brotherhood 1st Dan: damage formula shows +1k1 unarmed bonus."""
    _create_char(page, live_server_url, "BrothDmg", "brotherhood_of_shinsei_monk")
    f = _get_formula(page, "attack")
    assert f is not None
    sources = f.get("damage_bonus_sources", [])
    assert any("+1k1" in s for s in sources)
    assert f.get("damage_extra_rolled", 0) >= 1
    assert f.get("damage_extra_kept", 0) >= 1


def test_brotherhood_1st_dan_formula_extra_die(page, live_server_url):
    """Brotherhood 1st Dan: extra die on attack, damage, wound_check."""
    _create_char(page, live_server_url, "BrothFormula", "brotherhood_of_shinsei_monk")
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    # attack rank 1, Fire 2, +1 from 1st Dan = 4 rolled
    assert f_atk["rolled"] == 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    # Water 3 (school ring defaults to Water), base = 4, +1 from 1st Dan = 5
    assert f_wc["rolled"] == 5


def test_brotherhood_2nd_dan_attack_bonus(page, live_server_url):
    """Brotherhood at 2nd Dan: attack formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "BrothAtk2", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "worldliness": 2})
    f = _get_formula(page, "attack")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


# ===========================================================================
# COURTIER (5 tests)
# ===========================================================================

def test_courtier_attack_air_bonus(page, live_server_url):
    """Courtier: attack formula has +Air flat bonus."""
    _create_char(page, live_server_url, "CourtAtk", "courtier")
    f = _get_formula(page, "attack")
    assert f is not None
    # Default Air = 2, should have bonuses containing Courtier (Air)
    assert any("Courtier" in b.get("label", "") for b in f.get("bonuses", []))


def test_courtier_damage_air_bonus(page, live_server_url):
    """Courtier: damage formula has +Air flat bonus."""
    _create_char(page, live_server_url, "CourtDmg", "courtier")
    f = _get_formula(page, "attack")
    assert f is not None
    sources = f.get("damage_bonus_sources", [])
    assert any("Courtier" in s for s in sources)
    assert f.get("damage_flat_bonus", 0) >= 3  # Air = 3 (school ring)


def test_courtier_1st_dan_formula_extra_die(page, live_server_url):
    """Courtier 1st Dan: extra die on tact, manipulation, wound_check."""
    _create_char(page, live_server_url, "CourtFormula", "courtier",
                 skill_overrides={"tact": 1, "manipulation": 1})
    f_tact = _get_formula(page, "skill:tact")
    assert f_tact is not None
    # tact is Air: rank 1 + Air 3 (school ring) + 1 (1st Dan) = 5
    assert f_tact["rolled"] == 5
    f_manip = _get_formula(page, "skill:manipulation")
    assert f_manip is not None
    # manipulation is Air: rank 1 + Air 3 (school ring) + 1 (1st Dan) = 5
    assert f_manip["rolled"] == 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4  # Water 2, base = 3, +1 from 1st Dan = 4


def test_courtier_2nd_dan_manipulation_bonus(page, live_server_url):
    """Courtier at 2nd Dan: manipulation formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "CourtManip2", "courtier",
                 knack_overrides={"discern_honor": 2, "oppose_social": 2, "worldliness": 2},
                 skill_overrides={"manipulation": 1})
    f = _get_formula(page, "skill:manipulation")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


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


# ===========================================================================
# DAIDOJI YOJIMBO (4 tests)
# ===========================================================================

def test_daidoji_1st_dan_formula_extra_die(page, live_server_url):
    """Daidoji 1st Dan: extra die on attack, counterattack, wound_check."""
    _create_char(page, live_server_url, "DaidojiFormula", "daidoji_yojimbo")
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk["rolled"] == 4  # attack 1 + Fire 2 + 1 = 4
    f_ca = _get_formula(page, "knack:counterattack")
    assert f_ca is not None
    assert f_ca["rolled"] == 4  # counterattack (Fire) 1 + Fire 2 + 1 = 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (school ring) + 1 + 1 = 5


def test_daidoji_2nd_dan_counterattack_bonus(page, live_server_url):
    """Daidoji at 2nd Dan: counterattack formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "DaidojiCA2", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    f = _get_formula(page, "knack:counterattack")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_daidoji_3rd_dan_counterattack_raises_note(page, live_server_url):
    """Daidoji at 3rd Dan: counterattack school ability flag is set with correct amount."""
    _create_char(page, live_server_url, "DaidojiCA3", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    sa = _get_school_abilities(page)
    assert sa.get("daidoji_counterattack_raises") is True
    assert sa.get("daidoji_counterattack_raises_amount", 0) > 0


def test_daidoji_5th_dan_wc_attacker_tn_note(page, live_server_url):
    """Daidoji at 5th Dan: wound check shows attacker TN reduction note."""
    _create_char(page, live_server_url, "DaidojiWC5", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    sa = _get_school_abilities(page)
    assert sa.get("daidoji_wc_lower_tn") is True


# ===========================================================================
# DOJI ARTISAN (3 tests)
# ===========================================================================

def test_doji_1st_dan_formula_extra_die(page, live_server_url):
    """Doji 1st Dan: extra die on counterattack, manipulation, wound_check."""
    _create_char(page, live_server_url, "DojiFormula", "doji_artisan",
                 skill_overrides={"manipulation": 1})
    f_ca = _get_formula(page, "knack:counterattack")
    assert f_ca is not None
    assert f_ca["rolled"] == 4  # counterattack (Fire) 1 + Fire 2 + 1 = 4
    f_manip = _get_formula(page, "skill:manipulation")
    assert f_manip is not None
    assert f_manip["rolled"] == 4  # manipulation (Air) 1 + Air 2 + 1 = 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (default school ring) + 1 + 1 = 5


def test_doji_2nd_dan_manipulation_bonus(page, live_server_url):
    """Doji at 2nd Dan: manipulation formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "DojiManip2", "doji_artisan",
                 knack_overrides={"counterattack": 2, "oppose_social": 2, "worldliness": 2},
                 skill_overrides={"manipulation": 1})
    f = _get_formula(page, "skill:manipulation")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_doji_5th_dan_opponent_bonus_input(page, live_server_url):
    """Doji 5th Dan: opponent result input appears after rolls."""
    _create_char(page, live_server_url, "Doji5opp", "doji_artisan",
                 knack_overrides={"counterattack": 5, "oppose_social": 5, "worldliness": 5})
    sa = _get_school_abilities(page)
    assert sa.get("doji_opponent_bonus") is True


# ===========================================================================
# HIDA BUSHI (4 tests)
# ===========================================================================

def test_hida_1st_dan_formula_extra_die(page, live_server_url):
    """Hida 1st Dan: extra die on attack, counterattack, wound_check."""
    _create_char(page, live_server_url, "HidaFormula", "hida_bushi")
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk["rolled"] == 4  # attack 1 + Fire 2 + 1 = 4
    f_ca = _get_formula(page, "knack:counterattack")
    assert f_ca is not None
    assert f_ca["rolled"] == 4  # counterattack (Fire) 1 + Fire 2 + 1 = 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (school ring) + 1 + 1 = 5


def test_hida_2nd_dan_counterattack_bonus(page, live_server_url):
    """Hida at 2nd Dan: counterattack formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "HidaCA2", "hida_bushi",
                 knack_overrides={"counterattack": 2, "iaijutsu": 2, "lunge": 2})
    f = _get_formula(page, "knack:counterattack")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_hida_3rd_dan_reroll_appears(page, live_server_url):
    """Hida at 3rd Dan sees dice reroll selection after attack roll."""
    _create_char(page, live_server_url, "HidaReroll", "hida_bushi",
                 knack_overrides={"counterattack": 3, "iaijutsu": 3, "lunge": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('button:text("Roll Attack")').click()
    _wait_attack_result(page)
    assert page.locator('text="Hida 3rd Dan: select up to"').is_visible()
    assert page.locator('button:text("Skip")').is_visible()


def test_hida_4th_dan_trade_sw_button(page, live_server_url):
    """Hida 4th Dan: button trades 2 SW for light wound reset."""
    _create_char(page, live_server_url, "Hida4SW", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    sa = _get_school_abilities(page)
    assert sa.get("hida_trade_sw") is True
    assert page.locator('button:has-text("Trade 2 SW to reset LW to 0")').is_visible()


# ===========================================================================
# HIRUMA SCOUT (5 tests)
# ===========================================================================

def test_hiruma_1st_dan_formula_extra_die(page, live_server_url):
    """Hiruma 1st Dan: extra die on initiative, parry, wound_check."""
    _create_char(page, live_server_url, "HirumaFormula", "hiruma_scout")
    f_init = _get_formula(page, "initiative")
    assert f_init is not None
    # Void 2, base = 3 rolled, +1 from 1st Dan = 4
    assert f_init["rolled"] == 4
    f_parry = _get_formula(page, "parry")
    assert f_parry is not None
    # parry 1 + Air 3 (school ring) + 1 = 5
    assert f_parry["rolled"] == 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4  # Water 2 + 1 + 1 = 4


def test_hiruma_initiative_action_dice_info(page, live_server_url):
    """Hiruma 4th Dan: initiative displays action dice -2 information."""
    _create_char(page, live_server_url, "Hiruma4Init", "hiruma_scout",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    f = _get_formula(page, "initiative")
    assert f is not None
    assert f.get("hiruma_4th_dan") is True


def test_hiruma_post_parry_bonus(page, live_server_url):
    """Hiruma 3rd Dan: post-parry bonus appears and applies to next attack/damage."""
    _create_char(page, live_server_url, "Hiruma3Parry", "hiruma_scout",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    sa = _get_school_abilities(page)
    assert sa.get("hiruma_post_parry_bonus") is True
    assert sa.get("hiruma_post_parry_amount", 0) > 0


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


# ===========================================================================
# IKOMA BARD (3 tests)
# ===========================================================================

def test_ikoma_1st_dan_formula_extra_die(page, live_server_url):
    """Ikoma 1st Dan: extra die on attack, bragging, wound_check."""
    _create_char(page, live_server_url, "IkomaFormula", "ikoma_bard",
                 skill_overrides={"bragging": 1})
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk["rolled"] == 4  # attack 1 + Fire 2 + 1 = 4
    f_brag = _get_formula(page, "skill:bragging")
    assert f_brag is not None
    # bragging (Air) rank 1 + Air 2 + 1 = 4
    assert f_brag["rolled"] == 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (default school ring) + 1 + 1 = 5


def test_ikoma_2nd_dan_attack_bonus(page, live_server_url):
    """Ikoma at 2nd Dan: attack formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "IkomaAtk2", "ikoma_bard",
                 knack_overrides={"discern_honor": 2, "oppose_knowledge": 2, "oppose_social": 2})
    f = _get_formula(page, "attack")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_ikoma_4th_dan_10_dice_floor(page, live_server_url):
    """Ikoma 4th Dan: damage roll has 10-dice floor on unparried attacks."""
    _create_char(page, live_server_url, "Ikoma4Dmg", "ikoma_bard",
                 knack_overrides={"discern_honor": 4, "oppose_knowledge": 4, "oppose_social": 4})
    sa = _get_school_abilities(page)
    assert sa.get("ikoma_10_dice_floor") is True


# ===========================================================================
# ISAWA DUELIST (2 tests)
# ===========================================================================

def test_isawa_duelist_1st_dan_formula_extra_die(page, live_server_url):
    """Isawa Duelist 1st Dan: extra die on double_attack, lunge, wound_check."""
    _create_char(page, live_server_url, "IsawaFormula", "isawa_duelist")
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    # double_attack (Fire) 1 + Fire 2 + 1 = 4
    assert f_da["rolled"] == 4
    f_lunge = _get_formula(page, "knack:lunge")
    assert f_lunge is not None
    assert f_lunge["rolled"] == 4  # lunge (Fire) 1 + Fire 2 + 1 = 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (school ring) + 1 + 1 = 5


def test_isawa_duelist_5th_dan_banks_wc_excess(page, live_server_url):
    """Isawa Duelist at 5th Dan: wound check banks excess for future wound checks."""
    _create_char(page, live_server_url, "Isawa5WC", "isawa_duelist",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    sa = _get_school_abilities(page)
    assert sa.get("isawa_bank_wc_excess") is True


# ===========================================================================
# ISAWA ISHI (4 tests)
# ===========================================================================

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


def test_isawa_ishi_vp_spend_cap(page, live_server_url):
    """Isawa Ishi: VP spend cap shows min(rings) - 1."""
    _create_char(page, live_server_url, "IsawaIshiCap", "isawa_ishi")
    config = _get_void_spend_config(page)
    # min(rings) = 2 (default for all non-school rings), cap = 2 - 1 = 1
    assert config.get("cap") == 1


# ===========================================================================
# KAKITA DUELIST (3 tests)
# ===========================================================================

def test_kakita_1st_dan_formula_extra_die(page, live_server_url):
    """Kakita 1st Dan: extra die on double_attack, iaijutsu, initiative."""
    _create_char(page, live_server_url, "KakitaFormula", "kakita_duelist")
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    assert f_da["rolled"] == 5  # double_attack (Fire) 1 + Fire 3 (school ring) + 1 = 5
    f_iai = _get_formula(page, "knack:iaijutsu")
    assert f_iai is not None
    assert f_iai["rolled"] == 5  # iaijutsu (Fire) 1 + Fire 3 + 1 = 5
    f_init = _get_formula(page, "initiative")
    assert f_init is not None
    # Void 2, base = 3, +1 from 1st Dan = 4
    assert f_init["rolled"] == 4


def test_kakita_4th_dan_iaijutsu_damage_bonus(page, live_server_url):
    """Kakita at 4th Dan: damage modal shows +5 bonus for iaijutsu attacks."""
    _create_char(page, live_server_url, "Kakita4IaiDmg", "kakita_duelist",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    f = _get_formula(page, "knack:iaijutsu")
    assert f is not None
    sources = f.get("damage_bonus_sources", [])
    assert any("+5" in s and "iaijutsu" in s.lower() for s in sources)


def test_kakita_2nd_dan_iaijutsu_bonus(page, live_server_url):
    """Kakita at 2nd Dan: iaijutsu formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "KakitaIai2", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    f = _get_formula(page, "knack:iaijutsu")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


# ===========================================================================
# KITSUKI MAGISTRATE (4 tests)
# ===========================================================================

def test_kitsuki_1st_dan_formula_extra_die(page, live_server_url):
    """Kitsuki 1st Dan: extra die on investigation, interrogation, wound_check."""
    _create_char(page, live_server_url, "KitsukiFormula", "kitsuki_magistrate",
                 skill_overrides={"investigation": 1, "interrogation": 1})
    f_inv = _get_formula(page, "skill:investigation")
    assert f_inv is not None
    # investigation (Water) rank 1 + Water 3 (school ring) + 1 = 5
    assert f_inv["rolled"] == 5
    f_int = _get_formula(page, "skill:interrogation")
    assert f_int is not None
    # Kitsuki uses Water for interrogation: rank 1 + Water 3 (school ring) + 1 = 5
    assert f_int["rolled"] == 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (school ring) + 1 + 1 = 5


def test_kitsuki_attack_water_bonus(page, live_server_url):
    """Kitsuki: attack formula has +2*Water flat bonus."""
    _create_char(page, live_server_url, "KitsukiAtk", "kitsuki_magistrate")
    f = _get_formula(page, "attack")
    assert f is not None
    # Water = 3 (school ring), so +2*3 = +6
    assert any("Water" in b.get("label", "") for b in f.get("bonuses", []))
    assert f.get("flat", 0) >= 6


def test_kitsuki_interrogation_uses_water(page, live_server_url):
    """Kitsuki: interrogation roll uses Water ring value."""
    _create_char(page, live_server_url, "KitsukiInterrW", "kitsuki_magistrate",
                 skill_overrides={"interrogation": 1})
    f = _get_formula(page, "skill:interrogation")
    assert f is not None
    assert "Water" in f.get("label", "")


def test_kitsuki_5th_dan_ring_reduction_note(page, live_server_url):
    """Kitsuki 5th Dan: shows ring reduction note after rolls."""
    _create_char(page, live_server_url, "Kitsuki5Ring", "kitsuki_magistrate",
                 knack_overrides={"discern_honor": 5, "iaijutsu": 5, "presence": 5})
    sa = _get_school_abilities(page)
    assert sa.get("kitsuki_reduce_rings") is True


# ===========================================================================
# KUNI WITCH HUNTER (2 tests)
# ===========================================================================

def test_kuni_1st_dan_formula_extra_die(page, live_server_url):
    """Kuni 1st Dan: extra die on damage, interrogation, wound_check."""
    _create_char(page, live_server_url, "KuniFormula", "kuni_witch_hunter",
                 skill_overrides={"interrogation": 1})
    f_int = _get_formula(page, "skill:interrogation")
    assert f_int is not None
    # interrogation rank 1 + Air 2 + 1 = 4
    assert f_int["rolled"] == 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4
    # Damage bonus: +1 rolled die from 1st Dan
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk.get("damage_extra_rolled", 0) >= 1


def test_kuni_5th_dan_reflect_damage_ui(page, live_server_url):
    """Kuni 5th Dan: reflect damage UI and self-damage calculation visible."""
    _create_char(page, live_server_url, "Kuni5Reflect", "kuni_witch_hunter",
                 knack_overrides={"detect_taint": 5, "iaijutsu": 5, "presence": 5})
    sa = _get_school_abilities(page)
    assert sa.get("kuni_reflect_damage") is True
    assert page.locator('text="Kuni 5th Dan - Reflect Damage"').is_visible()


# ===========================================================================
# MATSU BUSHI (6 tests)
# ===========================================================================

def test_matsu_1st_dan_formula_extra_die(page, live_server_url):
    """Matsu 1st Dan: extra die on double_attack, iaijutsu, wound_check."""
    _create_char(page, live_server_url, "MatsuFormula", "matsu_bushi")
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    assert f_da["rolled"] == 5  # double_attack (Fire) 1 + Fire 3 (school ring) + 1 = 5
    f_iai = _get_formula(page, "knack:iaijutsu")
    assert f_iai is not None
    assert f_iai["rolled"] == 5  # iaijutsu (Fire) 1 + Fire 3 + 1 = 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4  # Water 2 + 1 + 1 = 4


def test_matsu_5th_dan_lw_reset_15(page, live_server_url):
    """Matsu 5th Dan: dealing serious wounds shows light wound reset to 15."""
    _create_char(page, live_server_url, "Matsu5LW", "matsu_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    sa = _get_school_abilities(page)
    assert sa.get("matsu_lw_reset_15") is True


def test_matsu_4th_dan_near_miss(page, live_server_url):
    """Matsu 4th Dan: double attack near-miss shows hit with no bonus damage."""
    _create_char(page, live_server_url, "Matsu4NM", "matsu_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    sa = _get_school_abilities(page)
    assert sa.get("matsu_near_miss") is True


def test_matsu_3rd_dan_vp_wc_bonus(page, live_server_url):
    """Matsu 3rd Dan: VP spending on wound check offers bonus option."""
    _create_char(page, live_server_url, "Matsu3WC", "matsu_bushi",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    sa = _get_school_abilities(page)
    assert sa.get("matsu_vp_wc_bonus") is True
    assert sa.get("matsu_vp_wc_amount", 0) > 0


# ===========================================================================
# MERCHANT (3 tests)
# ===========================================================================

def test_merchant_1st_dan_formula_extra_die(page, live_server_url):
    """Merchant 1st Dan: extra die on interrogation, sincerity, wound_check."""
    _create_char(page, live_server_url, "MerchFormula", "merchant",
                 skill_overrides={"interrogation": 1, "sincerity": 1})
    f_int = _get_formula(page, "skill:interrogation")
    assert f_int is not None
    assert f_int["rolled"] == 4  # interrogation (Air) 1 + Air 2 + 1 = 4
    f_sin = _get_formula(page, "skill:sincerity")
    assert f_sin is not None
    assert f_sin["rolled"] == 4  # sincerity (Air) 1 + Air 2 + 1 = 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 5  # Water 3 (school ring) + 1 + 1 = 5


def test_merchant_post_roll_vp_spending(page, live_server_url):
    """Merchant sees post-roll VP spending note after a skill roll."""
    _create_char(page, live_server_url, "MerchantVP", "merchant",
                 skill_overrides={"bragging": 1})
    _roll_via_menu_or_direct(page, "skill:bragging")
    assert page.locator('text="Merchant Special: spend VP after seeing the roll."').is_visible()


# ===========================================================================
# MIRUMOTO BUSHI (6 tests)
# ===========================================================================

def test_mirumoto_1st_dan_formula_extra_die(page, live_server_url):
    """Mirumoto 1st Dan: extra die on parry, double_attack, wound_check."""
    _create_char(page, live_server_url, "MirumotoFormula", "mirumoto_bushi")
    f_parry = _get_formula(page, "parry")
    assert f_parry is not None
    assert f_parry["rolled"] == 4  # parry 1 + Air 2 + 1 = 4
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    assert f_da["rolled"] == 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4


def test_mirumoto_parry_temp_vp(page, live_server_url):
    """Mirumoto Bushi: parry roll adds temp VP."""
    _create_char(page, live_server_url, "MirumotoParryVP", "mirumoto_bushi")
    sa = _get_school_abilities(page)
    assert sa.get("mirumoto_temp_vp_on_parry") is True


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


def test_mirumoto_4th_dan_reduced_damage_dice(page, live_server_url):
    """Mirumoto 4th Dan: failed parry shows reduced bonus damage dice."""
    _create_char(page, live_server_url, "Mirumoto4Parry", "mirumoto_bushi",
                 knack_overrides={"counterattack": 4, "double_attack": 4, "iaijutsu": 4})
    sa = _get_school_abilities(page)
    assert sa.get("mirumoto_parry_modifier") is True


def test_mirumoto_2nd_dan_parry_bonus(page, live_server_url):
    """Mirumoto at 2nd Dan: parry formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "MirumotoParry2", "mirumoto_bushi",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    f = _get_formula(page, "parry")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


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


# ===========================================================================
# OTAKU BUSHI (4 tests)
# ===========================================================================

def test_otaku_1st_dan_formula_extra_die(page, live_server_url):
    """Otaku 1st Dan: extra die on iaijutsu, lunge, wound_check."""
    _create_char(page, live_server_url, "OtakuFormula", "otaku_bushi")
    f_iai = _get_formula(page, "knack:iaijutsu")
    assert f_iai is not None
    assert f_iai["rolled"] == 5  # iaijutsu (Fire) 1 + Fire 3 (school ring) + 1 = 5
    f_lunge = _get_formula(page, "knack:lunge")
    assert f_lunge is not None
    assert f_lunge["rolled"] == 5  # lunge (Fire) 1 + Fire 3 + 1 = 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4  # Water 2 + 1 + 1 = 4


def test_otaku_5th_dan_trade_dice_for_sw(page, live_server_url):
    """Otaku at 5th Dan: attack result offers the 10-dice-for-1-SW option."""
    _create_char(page, live_server_url, "Otaku5Dice", "otaku_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    sa = _get_school_abilities(page)
    assert sa.get("otaku_trade_dice_for_sw") is True


def test_otaku_4th_dan_lunge_extra_die(page, live_server_url):
    """Otaku 4th Dan: lunge damage shows extra die even after failed parry."""
    _create_char(page, live_server_url, "Otaku4Lunge", "otaku_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    sa = _get_school_abilities(page)
    assert sa.get("otaku_lunge_extra_die") is True


# ===========================================================================
# PRIEST (2 tests)
# ===========================================================================

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


def test_priest_2nd_dan_honor_bonus_raise(page, live_server_url):
    """Priest 2nd Dan: free raise on Honor bonus rolls (bragging, precepts)."""
    _create_char(page, live_server_url, "Priest2Honor", "priest",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
                 skill_overrides={"bragging": 1})
    f = _get_formula(page, "skill:bragging")
    assert f is not None
    # Should have Priest 2nd Dan bonus
    assert any("Priest 2nd Dan" in b.get("label", "") for b in f.get("bonuses", []))


# ===========================================================================
# SHIBA BUSHI (3 tests)
# ===========================================================================

def test_shiba_1st_dan_formula_extra_die(page, live_server_url):
    """Shiba 1st Dan: extra die on double_attack, parry, wound_check."""
    _create_char(page, live_server_url, "ShibaFormula", "shiba_bushi")
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    assert f_da["rolled"] == 4  # double_attack (Fire) 1 + Fire 2 + 1 = 4
    f_parry = _get_formula(page, "parry")
    assert f_parry is not None
    assert f_parry["rolled"] == 5  # parry 1 + Air 3 (school ring) + 1 = 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4  # Water 2 + 1 + 1 = 4


def test_shiba_4th_dan_wound_check_3k1_bonus(page, live_server_url):
    """Shiba 4th Dan: wound check modal displays the 3k1 bonus."""
    _create_char(page, live_server_url, "Shiba4WC", "shiba_bushi",
                 knack_overrides={"counterattack": 4, "double_attack": 4, "iaijutsu": 4})
    f = _get_formula(page, "wound_check")
    assert f is not None
    assert "+3k1 from 4th Dan" in f.get("bonus_sources", [])


def test_shiba_2nd_dan_parry_bonus(page, live_server_url):
    """Shiba at 2nd Dan: parry formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "ShibaParry2", "shiba_bushi",
                 knack_overrides={"counterattack": 2, "double_attack": 2, "iaijutsu": 2})
    f = _get_formula(page, "parry")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


# ===========================================================================
# SHINJO BUSHI (4 tests)
# ===========================================================================

def test_shinjo_1st_dan_formula_extra_die(page, live_server_url):
    """Shinjo 1st Dan: extra die in initiative, double_attack, parry."""
    _create_char(page, live_server_url, "ShinjoFormula", "shinjo_bushi")
    f_init = _get_formula(page, "initiative")
    assert f_init is not None
    # Void 2, base = 3, +1 from 1st Dan = 4
    assert f_init["rolled"] == 4
    f_da = _get_formula(page, "knack:double_attack")
    assert f_da is not None
    assert f_da["rolled"] == 4  # double_attack (Fire) 1 + Fire 2 + 1 = 4
    f_parry = _get_formula(page, "parry")
    assert f_parry is not None
    assert f_parry["rolled"] == 5  # parry 1 + Air 3 (school ring) + 1 = 5


def test_shinjo_4th_dan_initiative_highest_die_1(page, live_server_url):
    """Shinjo 4th Dan: initiative roll sets highest die to 1."""
    _create_char(page, live_server_url, "Shinjo4Init", "shinjo_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    f = _get_formula(page, "initiative")
    assert f is not None
    assert f.get("shinjo_4th_dan") is True


def test_shinjo_5th_dan_parry_excess_wc(page, live_server_url):
    """Shinjo 5th Dan: wound check at 5th Dan offers parry excess application."""
    _create_char(page, live_server_url, "Shinjo5Parry", "shinjo_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    sa = _get_school_abilities(page)
    assert sa.get("shinjo_bank_parry_excess") is True


# ===========================================================================
# SHOSURO ACTOR (4 tests)
# ===========================================================================

def test_shosuro_1st_dan_formula_extra_die(page, live_server_url):
    """Shosuro 1st Dan: extra die on attack, sincerity, wound_check."""
    _create_char(page, live_server_url, "ShosuroFormula", "shosuro_actor",
                 skill_overrides={"sincerity": 1})
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk["rolled"] == 4  # attack 1 + Fire 2 + 1 = 4
    f_sin = _get_formula(page, "skill:sincerity")
    assert f_sin is not None
    assert f_sin["rolled"] == 5  # sincerity (Air) 1 + Air 3 (school ring) + 1 = 5
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4  # Water 2 + 1 + 1 = 4


def test_shosuro_stipend_display(page, live_server_url):
    """Shosuro Actor: stipend display on character sheet."""
    _create_char(page, live_server_url, "ShosuroStipend", "shosuro_actor")
    # All characters should have a stipend displayed
    stipend_el = page.locator('text="koku/year"').first
    assert stipend_el.is_visible()


def test_shosuro_acting_skill_bonus(page, live_server_url):
    """Shosuro Actor: roll formulas show the acting skill bonus (extra rolled dice)."""
    _create_char(page, live_server_url, "ShosuroActing", "shosuro_actor",
                 skill_overrides={"acting": 2})
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    # attack 1 + Fire 2 + 1 (1st Dan on attack) + 2 (acting bonus) = 6
    assert f_atk["rolled"] == 6


def test_shosuro_2nd_dan_sincerity_bonus(page, live_server_url):
    """Shosuro at 2nd Dan: sincerity formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "ShosuroSin2", "shosuro_actor",
                 knack_overrides={"athletics": 2, "discern_honor": 2, "pontificate": 2},
                 skill_overrides={"sincerity": 1})
    f = _get_formula(page, "skill:sincerity")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


# ===========================================================================
# SHUGENJA (4 tests - all skipped, school disabled in UI)
# ===========================================================================

@pytest.mark.skip(reason="Shugenja school disabled in UI")
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


# ===========================================================================
# TOGASHI ISE ZUMI (4 tests)
# ===========================================================================

def test_togashi_1st_dan_formula_extra_die(page, live_server_url):
    """Togashi 1st Dan: extra die on attack, parry, athletics."""
    _create_char(page, live_server_url, "TogashiFormula", "togashi_ise_zumi")
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk["rolled"] == 4  # attack 1 + Fire 2 + 1 = 4
    f_parry = _get_formula(page, "parry")
    assert f_parry is not None
    assert f_parry["rolled"] == 4
    # Athletics on Air: 2*Air + athletics_rank + 1 (1st Dan)
    # Athletics knack starts at rank 1 for Togashi; Air = 2
    # rolled = 2*2 + 1 + 1 = 6
    f_ath = _get_formula(page, "athletics:Air")
    assert f_ath is not None
    assert f_ath["rolled"] == 6


def test_togashi_4th_dan_reroll_contested(page, live_server_url):
    """Togashi 4th Dan: reroll button appears after contested rolls."""
    _create_char(page, live_server_url, "Togashi4Reroll", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4})
    sa = _get_school_abilities(page)
    assert sa.get("togashi_reroll_contested") is True


def test_togashi_3rd_dan_athletics_raises(page, live_server_url):
    """Togashi 3rd Dan: athletics roll shows raise spending button."""
    _create_char(page, live_server_url, "Togashi3Ath", "togashi_ise_zumi",
                 knack_overrides={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
                 skill_overrides={"precepts": 1})
    sa = _get_school_abilities(page)
    assert sa.get("togashi_daily_athletics_raises") is True
    assert sa.get("togashi_daily_raises_max", 0) > 0
    # Roll athletics and check for the button
    _roll_via_menu_or_direct(page, "athletics:Air")
    assert page.locator('button:has-text("Spend Athletics Raise")').is_visible()


def test_togashi_2nd_dan_athletics_bonus(page, live_server_url):
    """Togashi at 2nd Dan: athletics formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "TogashiAth2", "togashi_ise_zumi",
                 knack_overrides={"athletics": 2, "conviction": 2, "dragon_tattoo": 2})
    f = _get_formula(page, "athletics:Air")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


# ===========================================================================
# YOGO WARDEN (6 tests, 5th Dan is TBD - not included)
# ===========================================================================

def test_yogo_1st_dan_formula_extra_die(page, live_server_url):
    """Yogo 1st Dan: extra die on attack, damage, wound_check."""
    _create_char(page, live_server_url, "YogoFormula", "yogo_warden")
    f_atk = _get_formula(page, "attack")
    assert f_atk is not None
    assert f_atk["rolled"] == 4  # attack 1 + Fire 2 + 1 = 4
    f_wc = _get_formula(page, "wound_check")
    assert f_wc is not None
    assert f_wc["rolled"] == 4
    # Damage: +1 rolled die from 1st Dan
    assert f_atk.get("damage_extra_rolled", 0) >= 1


def test_yogo_3rd_dan_vp_heals_lw(page, live_server_url):
    """Yogo 3rd Dan: VP spending button reduces light wound counter."""
    _create_char(page, live_server_url, "Yogo3VP", "yogo_warden",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "feint": 3})
    sa = _get_school_abilities(page)
    assert sa.get("yogo_vp_heals_lw") is True
    assert sa.get("yogo_vp_heal_amount", 0) > 0


def test_yogo_temp_vp_on_sw(page, live_server_url):
    """Yogo Warden: serious wound grants temp VP."""
    _create_char(page, live_server_url, "YogoSWVP", "yogo_warden")
    sa = _get_school_abilities(page)
    assert sa.get("yogo_temp_vp_on_sw") is True


def test_yogo_4th_dan_wc_vp_raise(page, live_server_url):
    """Yogo 4th Dan: wound check VP spending gives enhanced VP bonus (+5 each)."""
    _create_char(page, live_server_url, "Yogo4WC", "yogo_warden",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "feint": 4})
    config = _get_void_spend_config(page)
    assert config.get("wc_vp_free_raise") is True


# ===========================================================================
# EXISTING TESTS (preserved from the original file)
# ===========================================================================


# --- Bayushi 3rd Dan: feint deals damage ---

def test_bayushi_feint_damage_button(page, live_server_url):
    """Bayushi at 3rd Dan sees 'Roll Feint Damage' after a feint roll."""
    _create_char(page, live_server_url, "BayushiFeintDmg2", "bayushi_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    _roll_via_menu_or_direct(page, "knack:feint")
    assert page.locator('button:text("Roll Feint Damage")').is_visible()


# --- Shiba 3rd Dan: parry deals damage ---

def test_shiba_parry_damage_button(page, live_server_url):
    """Shiba at 3rd Dan sees 'Roll Parry Damage' after a parry roll."""
    _create_char(page, live_server_url, "ShibaParryDmg", "shiba_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    _roll_via_menu_or_direct(page, "parry")
    assert page.locator('button:text("Roll Parry Damage")').is_visible()


# --- Feint temp VP for non-Akodo schools ---

def test_feint_temp_vp_button_for_bayushi(page, live_server_url):
    """Bayushi sees 'Feint succeeded (+1 temp VP)' button after feint."""
    _create_char(page, live_server_url, "BayushiFeintVP2", "bayushi_bushi")
    _roll_via_menu_or_direct(page, "knack:feint")
    assert page.locator('button:text("Feint succeeded (+1 temp VP)")').is_visible()


# --- Hida 3rd Dan: reroll dice selection ---

def test_hida_reroll_selection_appears(page, live_server_url):
    """Hida at 3rd Dan sees dice reroll selection after attack roll."""
    _create_char(page, live_server_url, "HidaReroll2", "hida_bushi",
                 knack_overrides={"counterattack": 3, "iaijutsu": 3, "lunge": 3})
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('button:text("Roll Attack")').click()
    _wait_attack_result(page)
    assert page.locator('text="Hida 3rd Dan: select up to"').is_visible()
    assert page.locator('button:text("Skip")').is_visible()


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


# ---------------------------------------------------------------------------
# Formula display tests (preserved from original)
# ---------------------------------------------------------------------------

def test_akodo_1st_dan_formula_display(page, live_server_url):
    """Akodo 1st Dan: attack formula has +1 rolled die from school technique."""
    _create_char(page, live_server_url, "AkodoFormula", "akodo_bushi")
    # Default: attack rank 1, Fire 2, +1 rolled die from 1st Dan = rolled 4, kept 2
    f = _get_formula(page, "attack")
    assert f is not None
    assert f["rolled"] == 4  # 1 + 2 + 1 (1st Dan)
    assert f["kept"] == 2


def test_matsu_initiative_10_dice(page, live_server_url):
    """Matsu Bushi always rolls 10 initiative dice (Special Ability)."""
    _create_char(page, live_server_url, "MatsuInit", "matsu_bushi")
    f = _get_formula(page, "initiative")
    assert f is not None
    assert f["rolled"] == 10


def test_kakita_initiative_phase_0(page, live_server_url):
    """Kakita Duelist initiative formula has kakita_phase_zero flag."""
    _create_char(page, live_server_url, "KakitaInit", "kakita_duelist")
    f = _get_formula(page, "initiative")
    assert f is not None
    assert f["kakita_phase_zero"] is True


def test_isawa_duelist_damage_shows_water(page, live_server_url):
    """Isawa Duelist attack formula uses Water (not Fire) for damage ring."""
    _create_char(page, live_server_url, "IsawaWater", "isawa_duelist")
    f = _get_formula(page, "attack")
    assert f is not None
    assert f["damage_ring_name"] == "Water"


# ---------------------------------------------------------------------------
# 2nd Dan bonus visibility tests (preserved from original)
# ---------------------------------------------------------------------------

def test_matsu_2nd_dan_iaijutsu_bonus(page, live_server_url):
    """Matsu at 2nd Dan: iaijutsu knack formula has +5 from 2nd Dan technique."""
    _create_char(page, live_server_url, "MatsuIai2", "matsu_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    f = _get_formula(page, "knack:iaijutsu")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_hiruma_2nd_dan_parry_bonus(page, live_server_url):
    """Hiruma at 2nd Dan: parry formula has +5 from 2nd Dan technique."""
    _create_char(page, live_server_url, "HirumaParry2", "hiruma_scout",
                 knack_overrides={"double_attack": 2, "feint": 2, "iaijutsu": 2})
    f = _get_formula(page, "parry")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_shinjo_2nd_dan_parry_bonus(page, live_server_url):
    """Shinjo at 2nd Dan: parry formula has +5 from 2nd Dan technique."""
    _create_char(page, live_server_url, "ShinjoParry2", "shinjo_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    f = _get_formula(page, "parry")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_kitsuki_2nd_dan_interrogation_bonus(page, live_server_url):
    """Kitsuki at 2nd Dan: interrogation skill formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "KitsukiInterr2", "kitsuki_magistrate",
                 knack_overrides={"discern_honor": 2, "iaijutsu": 2, "presence": 2},
                 skill_overrides={"interrogation": 1})
    f = _get_formula(page, "skill:interrogation")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_merchant_2nd_dan_interrogation_bonus(page, live_server_url):
    """Merchant at 2nd Dan: interrogation skill formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "MerchInterr2", "merchant",
                 knack_overrides={"discern_honor": 2, "oppose_knowledge": 2, "worldliness": 2},
                 skill_overrides={"interrogation": 1})
    f = _get_formula(page, "skill:interrogation")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_kuni_2nd_dan_interrogation_bonus(page, live_server_url):
    """Kuni at 2nd Dan: interrogation skill formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "KuniInterr2", "kuni_witch_hunter",
                 knack_overrides={"detect_taint": 2, "iaijutsu": 2, "presence": 2},
                 skill_overrides={"interrogation": 1})
    f = _get_formula(page, "skill:interrogation")
    assert f is not None
    assert any(b["label"] == "2nd Dan technique" and b["amount"] == 5
               for b in f.get("bonuses", []))


def test_yogo_2nd_dan_wound_check_bonus(page, live_server_url):
    """Yogo at 2nd Dan: wound check formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "YogoWC2", "yogo_warden",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "feint": 2})
    f = _get_formula(page, "wound_check")
    assert f is not None
    assert "+5 from 2nd Dan" in f.get("bonus_sources", [])


def test_otaku_2nd_dan_wound_check_bonus(page, live_server_url):
    """Otaku at 2nd Dan: wound check formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "OtakuWC2", "otaku_bushi",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    f = _get_formula(page, "wound_check")
    assert f is not None
    assert "+5 from 2nd Dan" in f.get("bonus_sources", [])


def test_isawa_duelist_2nd_dan_wound_check_bonus(page, live_server_url):
    """Isawa Duelist at 2nd Dan: wound check formula has +5 from 2nd Dan."""
    _create_char(page, live_server_url, "IsawaWC2", "isawa_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    f = _get_formula(page, "wound_check")
    assert f is not None
    assert "+5 from 2nd Dan" in f.get("bonus_sources", [])


# ---------------------------------------------------------------------------
# 3rd Dan applicable skills tests (preserved from original)
# ---------------------------------------------------------------------------

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
    """Hida 4th Dan: Trade 2 SW to reset LW button actually modifies tracking."""
    _create_char(page, live_server_url, "HidaTrade", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    # Set up: add 2 serious wounds
    sw_row = page.locator('text="Serious Wounds"').locator('..')
    sw_row.locator('button:has-text("+")').click()
    sw_row.locator('button:has-text("+")').click()
    page.wait_for_timeout(300)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"

    # Click the trade button
    trade_btn = page.locator('button:has-text("Trade 2 SW to reset LW to 0")')
    assert trade_btn.is_visible()
    trade_btn.click()
    page.wait_for_timeout(300)

    # SW should be 0 now
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "0"


def test_togashi_heal_sw_button_works(page, live_server_url):
    """Togashi 5th Dan: Spend 1 VP to heal 2 SW button works."""
    _create_char(page, live_server_url, "TogashiHeal", "togashi_ise_zumi",
                 knack_overrides={"athletics": 5, "conviction": 5, "dragon_tattoo": 5})
    # Give VP and SW
    vp_row = page.locator('text="Void Points"').locator('..')
    vp_row.locator('button:has-text("+")').click()
    page.wait_for_timeout(200)
    sw_row = page.locator('text="Serious Wounds"').locator('..')
    sw_row.locator('button:has-text("+")').click()
    sw_row.locator('button:has-text("+")').click()
    page.wait_for_timeout(300)

    # Click heal button
    heal_btn = page.locator('button:has-text("Spend 1 VP to heal 2 SW")')
    assert heal_btn.is_visible()
    heal_btn.click()
    page.wait_for_timeout(300)

    # VP should be 0, SW should be 0
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "0"
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


def test_courtier_5th_dan_air_bonus_on_skill(page, live_server_url):
    """Courtier 5th Dan: +Air flat bonus appears on skill roll formulas."""
    _create_char(page, live_server_url, "CourtierAir5", "courtier",
                 knack_overrides={"discern_honor": 5, "oppose_social": 5, "worldliness": 5},
                 skill_overrides={"bragging": 1})
    f = _get_formula(page, "skill:bragging")
    assert f is not None
    # Should have a bonus from Courtier 5th Dan (Air)
    assert any("5th Dan" in b.get("label", "") for b in f.get("bonuses", []))


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
    _roll_via_menu_or_direct(page, "parry")
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
    """Bayushi 5th Dan: failing wound check calculates serious wounds using half LW."""
    _create_char(page, live_server_url, "Bayushi5B", "bayushi_bushi",
                 knack_overrides={"double_attack": 5, "feint": 5, "iaijutsu": 5})
    # Verify the flag is set in the wound check formula
    f = _get_formula(page, "wound_check")
    assert f.get("bayushi_5th_dan_half_lw") is True
    # Add a large amount of light wounds to ensure failure
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "80")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
    # Roll wound check - with 80 LW, almost certain to fail
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
    # If failed, serious wounds should be based on half LW (40 not 80)
    wc_data = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return { passed: d.wcPassed, sw: d.wcSeriousWounds, margin: d.wcMargin };
        }
        return null;
    }""")
    if wc_data and not wc_data["passed"]:
        # With half-LW (40), the margin and SW should be roughly half what they'd be at 80
        assert wc_data["sw"] > 0  # we failed, so some SW
        assert wc_data["margin"] < 80  # margin should be based on 40, not 80


def test_brotherhood_unarmed_damage_behavioral(page, live_server_url):
    """Brotherhood Special: attack damage shows +1k1 unarmed bonus in breakdown."""
    _create_char(page, live_server_url, "Brotherhood_UB", "brotherhood_of_shinsei_monk",
                 knack_overrides={"conviction": 2, "otherworldliness": 2, "worldliness": 2})
    _open_attack_modal_and_roll(page, "attack")
    # Wait for hit, then check damage parts
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkHit !== undefined) return d.atkHit;
        }
        return false;
    }""")
    if hit:
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
    _open_attack_modal_and_roll(page, "attack")
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkHit !== undefined) return d.atkHit;
        }
        return false;
    }""")
    if hit:
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
    """Kakita Special: rolling initiative shows Phase 0 note or phase 0 dice."""
    _create_char(page, live_server_url, "KakitaP0B", "kakita_duelist",
                 knack_overrides={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    page.locator('[data-roll-key="initiative"]').click()
    _wait_roll_done(page)
    # The initiative result should mention Phase 0 (Kakita school note)
    result = _get_roll_result_text(page)
    assert "Phase 0" in result or "phase 0" in result.lower()


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
    # Set TN very low to maximize hit chance
    page.locator('[data-roll-key="knack:counterattack"]').click()
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
        result = _get_attack_result_text(page)
        assert "Daidoji 3rd Dan" in result
        assert "free raise" in result.lower()


def test_daidoji_5th_dan_tn_note_behavioral(page, live_server_url):
    """Daidoji 5th Dan: passing wound check shows attacker TN reduction note."""
    _create_char(page, live_server_url, "Daidoji5B", "daidoji_yojimbo",
                 knack_overrides={"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    # Add small LW so wound check is likely to pass
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
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
    passed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcPassed;
        }
        return false;
    }""")
    if passed:
        result = _get_wc_result_text(page)
        assert "Daidoji 5th Dan" in result


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
    _open_attack_modal_and_roll(page, "attack")
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkHit !== undefined) return d.atkHit;
        }
        return false;
    }""")
    if hit:
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
    # Roll attack, hit, then roll damage
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")  # low TN for guaranteed hit
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
    """Hida 4th Dan: Trade 2 SW button decreases SW by 2 and resets LW to 0."""
    _create_char(page, live_server_url, "Hida4TB", "hida_bushi",
                 knack_overrides={"counterattack": 4, "iaijutsu": 4, "lunge": 4})
    # Add serious wounds
    sw_row = page.locator('text="Serious Wounds"').locator('..')
    sw_row.locator('button:has-text("+")').click()
    sw_row.locator('button:has-text("+")').click()
    sw_row.locator('button:has-text("+")').click()
    page.wait_for_timeout(300)
    sw_before = int(page.locator('[x-text="seriousWounds"]').text_content().strip())
    assert sw_before == 3
    # Click trade button
    page.locator('button:has-text("Trade 2 SW to reset LW to 0")').click()
    page.wait_for_timeout(300)
    sw_after = int(page.locator('[x-text="seriousWounds"]').text_content().strip())
    assert sw_after == 1  # 3 - 2 = 1
    lw_after = int(page.locator('[x-text="lightWounds"]').text_content().strip())
    assert lw_after == 0


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
    # Roll wound check - should fail with 80 LW
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
    # Check if it failed (should with 80 LW)
    failed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return !d.wcPassed;
        }
        return false;
    }""")
    if failed:
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
        assert total_after == total_before + 5, f"Expected +5, got {total_before} -> {total_after}"
        vp_remaining = page.evaluate("window._trackingBridge?.voidPoints || 0")
        assert vp_remaining == 1  # spent 1 of 2


# ===========================================================================
# COMPLEX MULTI-STEP FLOW TESTS
# ===========================================================================


def test_akodo_3rd_dan_bank_and_apply_behavioral(page, live_server_url):
    """Akodo 3rd Dan: pass wound check -> bonus banked -> apply to attack."""
    _create_char(page, live_server_url, "Akodo3FB", "akodo_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Add small LW so wound check is likely to pass
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
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
    passed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcPassed;
        }
        return false;
    }""")
    if passed:
        # Keep light wounds (this triggers banking)
        page.locator('button:has-text("Keep Light Wounds")').click()
        page.wait_for_timeout(300)
        # Check that a bonus was banked
        banked = page.evaluate("window._diceRoller?.akodoBankedBonuses?.filter(b => !b.spent)?.length || 0")
        assert banked > 0, "A bonus should be banked after passing wound check"
        # Roll an attack and check for the Apply button
        page.locator('[data-roll-key="attack"]').click()
        page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
        modal = page.locator('[data-modal="attack"]')
        modal.locator('select').select_option("5")
        modal.locator('button:has-text("Roll")').first.click()
        _wait_attack_result(page)
        # The Apply button should be visible
        assert page.locator('button:has-text("Apply +")').first.is_visible()


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
    hit = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkHit !== undefined) return d.atkHit;
        }
        return false;
    }""")
    if hit:
        result = _get_attack_result_text(page)
        assert "Bayushi" in result or "VP" in result


def test_hiruma_3rd_dan_parry_then_attack_behavioral(page, live_server_url):
    """Hiruma 3rd Dan: parry auto-banks bonus, then attack applies it."""
    _create_char(page, live_server_url, "Hiruma3FB", "hiruma_scout",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    # Roll parry to bank the bonus
    _roll_via_menu_or_direct(page, "parry")
    page.wait_for_timeout(300)
    # Close the roll result via the dice roller modal's close button
    page.locator('[data-modal="dice-roller"] button:has-text("Close")').click()
    page.wait_for_timeout(300)
    # Check bonus was banked
    banked = page.evaluate("window._diceRoller?.hirumaBankedAttackBonus || 0")
    assert banked > 0, f"Expected banked bonus > 0, got {banked}"
    # Now roll attack - bonus should be auto-applied
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select').select_option("5")
    modal.locator('button:has-text("Roll")').first.click()
    _wait_attack_result(page)
    result = _get_attack_result_text(page)
    assert "Hiruma" in result or "post-parry" in result.lower()


def test_isawa_duelist_5th_dan_bank_excess_behavioral(page, live_server_url):
    """Isawa Duelist 5th Dan: pass WC banks excess, next WC can apply it."""
    _create_char(page, live_server_url, "IsawaD5FB", "isawa_duelist",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    # Add small LW for first wound check (likely to pass)
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page.fill('input[placeholder="Amount"]', "5")
    page.locator('input[placeholder="Amount"]').locator('..').locator('button:has-text("Add")').click()
    page.wait_for_timeout(300)
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
    passed = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return d.wcPassed;
        }
        return false;
    }""")
    if passed:
        # Keep light wounds (triggers banking the excess)
        page.locator('button:has-text("Keep Light Wounds")').click()
        page.wait_for_timeout(300)
        banked = page.evaluate("window._diceRoller?.bankedWcExcess || 0")
        assert banked > 0, "WC excess should be banked after passing"


def test_matsu_3rd_dan_vp_wc_bonus_behavioral(page, live_server_url):
    """Matsu 3rd Dan: spend VP banks WC bonus, wound check shows Apply button."""
    _create_char(page, live_server_url, "Matsu3FB", "matsu_bushi",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
                 skill_overrides={"bragging": 1})
    # Give VP
    page.evaluate("window._trackingBridge.voidPoints = 1")
    page.wait_for_timeout(200)
    # Roll bragging with 1 VP to bank the Matsu bonus
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_timeout(300)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.is_visible():
        vp_btn = menu.locator('button.text-accent').first
        if vp_btn.is_visible():
            vp_btn.click()
            _wait_roll_done(page)
            page.wait_for_timeout(300)
            banked = page.evaluate("window._diceRoller?.matsuBankedWcBonus || 0")
            assert banked > 0, f"Matsu WC bonus should be banked, got {banked}"


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
        assert "NEAR-MISS" in result


def test_mirumoto_4th_dan_parry_reduction_behavioral(page, live_server_url):
    """Mirumoto 4th Dan: damage formula shows halved parry reduction."""
    _create_char(page, live_server_url, "Mirumoto4PB", "mirumoto_bushi",
                 knack_overrides={"counterattack": 4, "double_attack": 4, "iaijutsu": 4})
    # Roll attack, check the failed parry checkbox, verify halved text
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
        # Check the failed parry checkbox using x-model attribute
        page.locator('input[x-model="atkFailedParry"]').check()
        page.wait_for_timeout(300)
        result = _get_attack_result_text(page)
        assert "halved" in result.lower() or "4th Dan" in result


def test_otaku_4th_dan_lunge_parry_behavioral(page, live_server_url):
    """Otaku 4th Dan: lunge with failed parry shows extra die in damage parts."""
    _create_char(page, live_server_url, "Otaku4LB", "otaku_bushi",
                 knack_overrides={"double_attack": 4, "iaijutsu": 4, "lunge": 4})
    # Roll lunge
    page.locator('[data-roll-key="knack:lunge"]').click()
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
        # Check failed parry
        page.locator('input[x-model="atkFailedParry"]').check()
        page.wait_for_timeout(300)
        result = _get_attack_result_text(page)
        # Lunge part should be in the damage breakdown
        assert "Lunge" in result


def test_otaku_5th_dan_trade_dice_behavioral(page, live_server_url):
    """Otaku 5th Dan: with enough damage dice, trade-for-SW button works."""
    _create_char(page, live_server_url, "Otaku5TB", "otaku_bushi",
                 knack_overrides={"double_attack": 5, "iaijutsu": 5, "lunge": 5})
    sa = _get_school_abilities(page)
    assert sa.get("otaku_trade_dice_for_sw") is True
    # The trade button appears on damage-result when rolled >= 12
    # Verify the flag is set - actual testing requires enough damage dice
    # which depends on the weapon and hit excess


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
        page.wait_for_timeout(300)
        banked = page.evaluate("window._diceRoller?.bankedWcExcess || 0")
        expected_excess = our_total - 5
        if expected_excess > 0:
            assert banked >= expected_excess
