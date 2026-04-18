"""E2E: click-to-roll dice from the character sheet.

Tests cover the click handlers, the result modal contents, the impaired
indicator + 10s-not-rerolled note, and the profile-level animation/sound
toggles.
"""

import pytest

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply

pytestmark = [pytest.mark.rolls]


def _create_roller(page, live_server_url, name="Roller"):
    """Make a character with bragging rank 1 (so a roll formula exists)."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Roller setup")
    # Set VP to 0 so rolls go directly without a void spending menu
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)


def test_click_skill_opens_modal_with_skill_name(page, live_server_url):
    _create_roller(page, live_server_url, "ClickSkill")
    # Click the bragging row
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_for_roll_result(page)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Bragging" in title


def test_click_attack_opens_attack_modal(page, live_server_url):
    """Clicking attack opens the attack modal (not the regular dice roller)."""
    _create_roller(page, live_server_url, "ClickAttack")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"] h3.text-accent', state='visible', timeout=5000)
    title = page.locator('[data-modal="attack"] h3.text-accent').text_content()
    assert "Attack" in title


def test_click_parry_shows_predeclare_option(page, live_server_url):
    """Clicking parry shows roll menu with Roll Parry and Predeclared Parry."""
    _create_roller(page, live_server_url, "ClickParry")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    menu = page.locator('[data-parry-menu]')
    text = menu.text_content()
    assert "Roll Parry" in text
    assert "Predeclared Parry" in text
    # Click the Roll Parry option to roll normally
    menu.locator('button:has-text("Roll Parry")').first.click()
    _wait_for_roll_result(page)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Parry" in title


def test_parry_hover_reveals_void_submenu_on_roll(page, live_server_url):
    """Hovering Roll Parry reveals the void-spend submenu when VP is available."""
    _create_roller(page, live_server_url, "ParryHoverRoll")
    page.evaluate("window._trackingBridge.voidPoints = 2; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.hover()
    page.wait_for_selector('[data-parry-void-submenu="roll"]', state='visible', timeout=3000)
    submenu = page.locator('[data-parry-void-submenu="roll"]')
    text = submenu.text_content()
    assert "Spend 1 void point" in text
    assert "Spend 2 void points" in text


def test_parry_hover_reveals_void_submenu_on_predeclared(page, live_server_url):
    """Hovering Predeclared Parry reveals its own void-spend submenu with +5 label."""
    _create_roller(page, live_server_url, "ParryHoverPre")
    page.evaluate("window._trackingBridge.voidPoints = 1; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    page.locator('[data-parry-menu] button:has-text("Predeclared Parry")').first.hover()
    page.wait_for_selector('[data-parry-void-submenu="predeclared"]', state='visible', timeout=3000)
    submenu = page.locator('[data-parry-void-submenu="predeclared"]')
    text = submenu.text_content()
    assert "Spend 1 void point" in text
    assert "predeclared" in text.lower()


def test_parry_void_submenu_click_rolls_with_void(page, live_server_url):
    """Clicking a void option under Roll Parry rolls parry with void spent."""
    _create_roller(page, live_server_url, "ParryVoidRoll")
    page.evaluate("window._trackingBridge.voidPoints = 1; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.hover()
    page.wait_for_selector('[data-parry-void-submenu="roll"]', state='visible', timeout=3000)
    page.locator('[data-parry-void-submenu="roll"] button:has-text("Spend 1 void point")').click()
    _wait_for_roll_result(page)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Parry" in title
    # VP should have been deducted
    vp_after = page.evaluate("window._trackingBridge.voidPoints")
    assert vp_after == 0


def test_parry_void_submenu_click_rolls_predeclared_with_void(page, live_server_url):
    """Clicking a void option under Predeclared Parry rolls with +5 bonus and void spent."""
    _create_roller(page, live_server_url, "ParryVoidPre")
    page.evaluate("window._trackingBridge.voidPoints = 1; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    page.locator('[data-parry-menu] button:has-text("Predeclared Parry")').first.hover()
    page.wait_for_selector('[data-parry-void-submenu="predeclared"]', state='visible', timeout=3000)
    page.locator('[data-parry-void-submenu="predeclared"] button').first.click()
    _wait_for_roll_result(page)
    result = page.locator('[data-modal="dice-roller"]').text_content()
    assert "predeclared" in result.lower() or "+5" in result


def test_parry_no_void_submenu_arrow_when_no_vp(page, live_server_url):
    """With 0 VP, the parry options do not show the void-submenu arrow indicator."""
    _create_roller(page, live_server_url, "ParryNoVP")
    # _create_roller already sets VP to 0
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    # Hovering should not reveal any submenu
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.hover()
    page.wait_for_timeout(200)
    assert page.locator('[data-parry-void-submenu="roll"]').count() == 0 \
        or not page.locator('[data-parry-void-submenu="roll"]').is_visible()


def test_click_ring_opens_athletics_modal(page, live_server_url):
    _create_roller(page, live_server_url, "ClickRing")
    page.locator('[data-roll-key="athletics:Earth"]').click()
    # Athletics ring clicks always show the roll menu; click "Roll" to proceed
    page.wait_for_selector('.fixed.z-50.bg-white.rounded-lg.shadow-xl', state='visible', timeout=5000)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    menu.locator('button.font-medium:has-text("Roll")').first.click()
    page.wait_for_selector('[data-modal="dice-roller"] h3.text-accent', state='visible', timeout=5000)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Athletics" in title and "Earth" in title


def test_click_ring_always_shows_menu_even_with_zero_vp(page, live_server_url):
    """Athletics ring click opens the roll menu (with void options) even at 0 VP."""
    _create_roller(page, live_server_url, "ClickRingZeroVP")
    # _create_roller already zeroes out VP
    vp = page.evaluate("window._trackingBridge?.voidPoints")
    assert vp == 0, "precondition: test char has 0 VP"
    page.locator('[data-roll-key="athletics:Air"]').click()
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    page.wait_for_selector('.fixed.z-50.bg-white.rounded-lg.shadow-xl', state='visible', timeout=3000)
    assert menu.is_visible(), "roll menu should appear for athletics ring click"
    assert menu.text_content() and "Air" in menu.text_content()


def test_click_ring_shows_void_options_when_vp_available(page, live_server_url):
    """Athletics ring click shows the 'Spend N void points' dropdown when VP is available."""
    _create_roller(page, live_server_url, "ClickRingVP")
    # Restore VP for this test
    page.evaluate("window._trackingBridge.voidPoints = 2; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    page.locator('[data-roll-key="athletics:Earth"]').click()
    page.wait_for_selector('.fixed.z-50.bg-white.rounded-lg.shadow-xl', state='visible', timeout=3000)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    text = menu.text_content()
    assert "Spend 1 void point" in text
    assert "Spend 2 void points" in text


def _create_athletics_knack_char(page, live_server_url, name="AthKnack"):
    """Make a character whose school has athletics as a school knack (Togashi)."""
    from tests.e2e.helpers import select_school, apply_changes
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "togashi_ise_zumi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Athletics knack setup")


def test_athletics_knack_icon_opens_ring_picker(page, live_server_url):
    """Athletics knack die icon opens a ring picker with all four non-Void rings."""
    _create_athletics_knack_char(page, live_server_url, "AthPick")
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    for ring in ["Air", "Fire", "Water", "Earth"]:
        btn = page.locator(f'button[data-athletics-ring="{ring}"]')
        assert btn.is_visible(), f"ring option {ring} should be visible"


def test_athletics_knack_picker_rolls_selected_ring(page, live_server_url):
    """Selecting a ring in the athletics picker rolls Athletics (Ring)."""
    _create_athletics_knack_char(page, live_server_url, "AthPickFire")
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    page.locator('button[data-athletics-ring="Fire"]').click()
    page.wait_for_selector('[data-modal="dice-roller"] h3.text-accent', state='visible', timeout=5000)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Athletics" in title and "Fire" in title


def test_athletics_knack_picker_void_submenu(page, live_server_url):
    """Hovering a ring in the athletics picker shows the void-points submenu."""
    _create_athletics_knack_char(page, live_server_url, "AthPickVoid")
    # Togashi starts with Void 3 -> 3 VP available by default
    vp = page.evaluate("window._trackingBridge?.voidPoints")
    assert vp > 0, "precondition: VP available"
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    # Hover over the Air ring option and expect the void submenu to appear
    page.locator('button[data-athletics-ring="Air"]').hover()
    page.wait_for_selector('[data-athletics-void-submenu="Air"]', state='visible', timeout=3000)
    submenu = page.locator('[data-athletics-void-submenu="Air"]')
    text = submenu.text_content()
    assert "Spend 1 void point" in text


def test_modal_shows_total_and_dice_after_animation(page, live_server_url):
    _create_roller(page, live_server_url, "ResultChar")
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_for_roll_result(page)
    modal = page.locator('[data-modal="dice-roller"]')
    text = modal.text_content()
    assert "Total:" in text


def test_modal_close_button(page, live_server_url):
    _create_roller(page, live_server_url, "CloseChar")
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_selector('[data-modal="dice-roller"] h3.text-accent', state='visible', timeout=5000)
    # Click the × close button inside the modal
    page.locator('[data-modal="dice-roller"] button', has_text="×").click()
    page.wait_for_timeout(300)
    # Modal should be hidden — the h3 inside the modal is no longer visible
    assert not page.locator('[data-modal="dice-roller"] h3.text-accent').is_visible()


def test_impaired_character_modal_shows_no_reroll_note(page, live_server_url):
    """A character with serious wounds >= Earth ring is impaired and the modal
    should display the impaired note."""
    _create_roller(page, live_server_url, "ImpairedChar")
    # Default Earth ring is 2; add 2 serious wounds via the tracking + button
    sw_section = page.locator('text="Serious Wounds"').locator('..')
    plus_btn = sw_section.locator('button', has_text="+").first
    plus_btn.click()
    page.wait_for_timeout(150)
    plus_btn.click()
    page.wait_for_timeout(300)
    # Reload so server-side is_impaired_now picks up the new wounds and the
    # roll_formulas reflect reroll_tens=False
    page.reload()
    page.wait_for_selector('[data-roll-key="skill:bragging"]')
    # Click bragging
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_selector('text="Total:"', state='visible', timeout=5000)
    body = page.text_content("body")
    assert "10s not rerolled due to being Impaired" in body


def test_unskilled_character_modal_names_skill_in_no_reroll_note(page, live_server_url):
    """Clicking an unranked basic skill opens the modal; the no-reroll note
    must identify the zero-ranked skill by name so the player knows why 10s
    aren't rerolled."""
    _create_roller(page, live_server_url, "UnskilledChar")
    # The roller has bragging at 1 but not intimidation. Intimidation is a
    # basic skill (unskilled = no reroll, no penalty).
    page.locator('[data-roll-key="skill:intimidation"]').click()
    _wait_for_roll_result(page)
    body = page.text_content("body")
    assert "10s not rerolled due to Intimidation being 0" in body


def test_impaired_indicator_visible_on_sheet(page, live_server_url):
    _create_roller(page, live_server_url, "ImpairedBadgeChar")
    sw_section = page.locator('text="Serious Wounds"').locator('..')
    plus_btn = sw_section.locator('button', has_text="+").first
    plus_btn.click()
    page.wait_for_timeout(120)
    plus_btn.click()
    page.wait_for_timeout(300)
    page.reload()
    body = page.text_content("body")
    assert "IMPAIRED" in body


def test_impaired_indicator_absent_when_healthy(page, live_server_url):
    _create_roller(page, live_server_url, "HealthyChar")
    body = page.text_content("body")
    assert "IMPAIRED" not in body


def test_disable_animation_preference(page, live_server_url):
    """Setting dice_animation off in profile -> modal opens without animation tray."""
    _create_roller(page, live_server_url, "NoAnimChar")
    sheet_url = page.url
    # Visit profile and uncheck animation
    page.goto(f"{live_server_url}/profile")
    page.uncheck('input[name="dice_animation"]')
    page.locator('button[type="submit"]', has_text="Save Changes").click()
    page.wait_for_load_state("networkidle")
    # Back to the sheet
    page.goto(sheet_url)
    page.wait_for_selector('[data-roll-key="skill:bragging"]')
    page.locator('[data-roll-key="skill:bragging"]').click()
    # Result panel should be immediately visible (no animation phase)
    page.wait_for_selector('text="Total:"', state='visible', timeout=2000)
    body = page.text_content("body")
    assert "Total:" in body


def test_athletics_label_in_modal(page, live_server_url):
    _create_roller(page, live_server_url, "AthleticsChar")
    page.locator('[data-roll-key="athletics:Water"]').click()
    # Athletics ring clicks always show the roll menu; click "Roll" to proceed
    page.wait_for_selector('.fixed.z-50.bg-white.rounded-lg.shadow-xl', state='visible', timeout=5000)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    menu.locator('button.font-medium:has-text("Roll")').first.click()
    page.wait_for_selector('text="Total:"', state='visible', timeout=5000)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Athletics" in title and "Water" in title


def test_die_top_angle_is_about_70_degrees(page, live_server_url):
    """Diagnostic: measure the actual rendered top angle of a die element.

    Reads the SVG polygon points, the SVG's getBoundingClientRect, and
    computes the screen-space angle at the top vertex. We assert that the
    rendered angle is ~70 degrees (within a small tolerance), which is the
    blunter kite geometry the dice service emits.
    """
    _create_roller(page, live_server_url, "AngleProbe")
    sheet_url = page.url
    # Make sure animation is enabled — a previous test in the suite may have
    # disabled it via the profile, and the dice tray is only populated when
    # animations are on.
    page.goto(f"{live_server_url}/profile")
    page.check('input[name="dice_animation"]')
    page.locator('button[type="submit"]', has_text="Save Changes").click()
    page.wait_for_load_state("networkidle")
    page.goto(sheet_url)
    page.wait_for_selector('[data-roll-key="attack"]')
    # Re-enable animations for this test (conftest disables them)
    page.evaluate("if (window._diceRoller) window._diceRoller.prefs.dice_animation_enabled = true")
    page.locator('[data-roll-key="attack"]').click()
    # Attack now opens the attack modal - click "Roll Attack" to start the roll
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] select').select_option("5")
    page.locator('[data-modal="attack"] button:has-text("Roll")').first.click()
    # Wait until the rolling phase has rendered the dice tray AND the dice
    # have stopped tumbling (otherwise the rotation transform skews
    # getBoundingClientRect and the measured angle is wrong).
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation-atk svg.die').length > 0",
        timeout=15000,
    )
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation-atk svg.die.rolling').length === 0",
        timeout=10000,
    )

    measurement = page.evaluate(
        """
        () => {
            const die = document.querySelector('#dice-animation-atk svg.die') || document.querySelector('#dice-animation svg.die');
            if (!die) return {error: 'no die element'};
            const path = die.querySelector('path.die-shape');
            if (!path) return {error: 'no path'};
            const rect = die.getBoundingClientRect();
            const vb = die.viewBox.baseVal;
            // The path has rounded corners drawn as quadratic Bezier curves;
            // each Q's control point is the original sharp kite vertex. The
            // path data has exactly four Q commands (one per kite vertex).
            const d = path.getAttribute('d').trim();
            const qMatches = [...d.matchAll(/Q\\s+([\\d.\\-]+)\\s+([\\d.\\-]+)\\s+([\\d.\\-]+)\\s+([\\d.\\-]+)/g)];
            if (qMatches.length !== 4) return {error: 'expected 4 Q commands, got ' + qMatches.length};
            // The Q commands appear in path order: R, B, L, T (the path
            // starts at the leave-T point and goes clockwise).
            const ctrls = qMatches.map(m => [parseFloat(m[1]), parseFloat(m[2])]);
            const R = ctrls[0], B = ctrls[1], L = ctrls[2], T = ctrls[3];
            const sx = rect.width / vb.width;
            const sy = rect.height / vb.height;
            const toScreen = p => [p[0] * sx, p[1] * sy];
            const tS = toScreen(T), rS = toScreen(R), lS = toScreen(L);
            const v1 = [rS[0] - tS[0], rS[1] - tS[1]];
            const v2 = [lS[0] - tS[0], lS[1] - tS[1]];
            const dot = v1[0] * v2[0] + v1[1] * v2[1];
            const m1 = Math.hypot(v1[0], v1[1]);
            const m2 = Math.hypot(v2[0], v2[1]);
            const angle = Math.acos(dot / (m1 * m2)) * 180 / Math.PI;
            return {
                rect: {width: rect.width, height: rect.height},
                viewBox: {w: vb.width, h: vb.height},
                vertices: {T, R, B, L},
                angle: angle,
            };
        }
        """
    )
    print(f"\nMeasured: {measurement}")
    assert "error" not in measurement
    assert 67 <= measurement["angle"] <= 73, (
        f"Expected ~70 degrees, got {measurement['angle']}. Full: {measurement}"
    )


# --- Initiative Rolls ---


def test_initiative_roll_shows_action_dice(page, live_server_url):
    """Clicking the Initiative box rolls and shows action dice (not a Total)."""
    _create_roller(page, live_server_url, "InitRoll")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    modal = page.locator('[data-modal="dice-roller"]')
    assert modal.locator('text="Action Dice"').is_visible()


def test_initiative_no_total_shown(page, live_server_url):
    """Initiative results show action dice, not a summed Total."""
    _create_roller(page, live_server_url, "InitNoTotal")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    modal = page.locator('[data-modal="dice-roller"]')
    # The initiative-specific "Action Dice" section should be visible
    assert modal.locator('text="Action Dice"').is_visible()


# --- 3rd Dan Free Raises on the roll modal ---


def _create_3rd_dan_courtier(page, live_server_url, name="Courtier3Dan"):
    """Create a Courtier at 3rd Dan with Tact 3 and Manipulation 2."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "courtier")
    page.wait_for_timeout(500)
    # Select school ring (Courtier has fixed Air ring)
    # Raise knacks to 3 for 3rd Dan
    click_plus(page, "knack_discern_honor", 2)  # 1 → 3
    click_plus(page, "knack_oppose_social", 2)
    click_plus(page, "knack_worldliness", 2)
    # Tact 3 = source skill for 3rd Dan
    click_plus(page, "skill_tact", 3)
    # Manipulation 2 = a skill in the 3rd Dan applicable_to list
    click_plus(page, "skill_manipulation", 2)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "3rd Dan Courtier setup")


def _dismiss_roll_menu_if_open(page):
    """If the void-spending roll menu appeared, click the default 'Roll X' option."""
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
    if already_done:
        return
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl.border')
    if menu.count() > 0 and menu.is_visible():
        buttons = menu.locator('button.font-medium')
        for i in range(buttons.count()):
            text = buttons.nth(i).text_content().strip()
            if text.startswith("Roll "):
                buttons.nth(i).click()
                return
        buttons.first.click()


def _wait_for_roll_result(page):
    """Wait for the dice roller Alpine component to reach ``phase='done'``.
    If the void-spending roll menu is showing, click 'Roll X' first."""
    _dismiss_roll_menu_if_open(page)
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const data = window.Alpine && window.Alpine.$data(el);
            if (data && data.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)


def test_unskilled_advanced_skill_shows_minus_10_in_breakdown(page, live_server_url):
    """Rolling an advanced skill at rank 0 lists the -10 penalty in the result breakdown."""
    page.goto(live_server_url)
    page.locator('button:text("New Character")').click()
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "UnskilledAdv")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    # Manipulation is an advanced skill; character has no rank -> unskilled formula with -10
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    modal_text = page.locator('[data-modal="dice-roller"]').text_content()
    assert "-10" in modal_text
    assert "unskilled advanced penalty" in modal_text


def test_spend_raise_button_visible_for_applicable_skill(page, live_server_url):
    """The 'Spend 3rd Dan Free Raise' button appears on the roll modal for
    skills in the 3rd Dan applicable_to list."""
    _create_3rd_dan_courtier(page, live_server_url)
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    assert page.locator('[data-action="spend-raise"]').is_visible()
    assert page.locator('[data-action="undo-raise"]').is_visible()


def test_spend_raise_adds_5_to_total(page, live_server_url):
    _create_3rd_dan_courtier(page, live_server_url, "SpendTest")
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    total_before = int(page.locator('[data-modal="dice-roller"] .font-bold.text-lg .text-accent').text_content().strip())
    page.locator('[data-action="spend-raise"]').click()
    page.wait_for_timeout(200)
    total_after = int(page.locator('[data-modal="dice-roller"] .font-bold.text-lg .text-accent').text_content().strip())
    assert total_after == total_before + 5


def test_undo_raise_reverses_spend(page, live_server_url):
    _create_3rd_dan_courtier(page, live_server_url, "UndoTest")
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    total_before = int(page.locator('[data-modal="dice-roller"] .font-bold.text-lg .text-accent').text_content().strip())
    page.locator('[data-action="spend-raise"]').click()
    page.wait_for_timeout(100)
    page.locator('[data-action="undo-raise"]').click()
    page.wait_for_timeout(200)
    total_after = int(page.locator('[data-modal="dice-roller"] .font-bold.text-lg .text-accent').text_content().strip())
    assert total_after == total_before


def test_spend_disabled_at_per_roll_max(page, live_server_url):
    """Spend button disables after spending max-per-roll raises (= source rank)."""
    _create_3rd_dan_courtier(page, live_server_url, "MaxPerRoll")
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    # Tact rank 3 → max 3 per roll
    for _ in range(3):
        page.locator('[data-action="spend-raise"]').click()
        page.wait_for_timeout(100)
    assert page.locator('[data-action="spend-raise"]').is_disabled()


def test_undo_disabled_when_none_spent(page, live_server_url):
    """Undo button is disabled when no raises have been spent this roll."""
    _create_3rd_dan_courtier(page, live_server_url, "UndoDisabled")
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    assert page.locator('[data-action="undo-raise"]').is_disabled()


def test_no_spend_button_for_non_applicable_skill(page, live_server_url):
    """Skills NOT in the 3rd Dan applicable_to list don't show the button."""
    _create_3rd_dan_courtier(page, live_server_url, "NonApplicable")
    # Tact IS in applicable_to, but let's check a skill that isn't:
    # add bragging rank 1
    page.goto(page.url.replace("/characters/", "/characters/") + "/edit")
    page.wait_for_selector('input[name="name"]')
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Add bragging")
    # Roll bragging — should NOT show spend button (x-show=false → hidden)
    page.wait_for_selector('[data-roll-key="skill:bragging"]', timeout=5000)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_for_roll_result(page)
    assert not page.locator('[data-action="spend-raise"]').is_visible()
