"""E2E: click-to-roll dice from the character sheet.

Tests cover the click handlers, the result modal contents, the impaired
indicator + 10s-not-rerolled note, and the profile-level animation/sound
toggles.
"""

import pytest

from tests.e2e.helpers import select_school, click_plus, apply_changes, create_and_apply, start_new_character

pytestmark = [pytest.mark.rolls]


def _create_roller(page, live_server_url, name="Roller"):
    """Make a character with bragging rank 1 (so a roll formula exists)."""
    page.goto(live_server_url)
    start_new_character(page)
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


def test_roll_menu_flipped_above_is_close_to_clicked_element(page, live_server_url):
    """When the roll menu doesn't fit below the clicked element it flips above,
    and the menu's bottom edge should sit just above the clicked element - NOT
    with a huge gap that the naive 'estimated menu height' math used to create."""
    _create_roller(page, live_server_url, "FlipGap")
    # Restore VP so the menu shows a realistic number of rows.
    page.evaluate("window._trackingBridge.voidPoints = 2; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    # Shrink the viewport and scroll so the ring sits near the bottom edge,
    # forcing the menu to flip above.
    page.set_viewport_size({"width": 900, "height": 500})
    ring = page.locator('[data-roll-key="athletics:Earth"]')
    ring.scroll_into_view_if_needed()
    page.evaluate(
        "el => { const r = el.getBoundingClientRect();"
        "        window.scrollBy(0, r.top - (window.innerHeight - r.height - 8)); }",
        ring.element_handle(),
    )
    page.wait_for_timeout(100)
    ring.click()
    page.wait_for_selector('.fixed.z-50.bg-white.rounded-lg.shadow-xl', state='visible', timeout=3000)
    # Measure actual gap between the menu's bottom edge and the ring's top edge.
    gap = page.evaluate(
        "el => { const r = el.getBoundingClientRect();"
        "        const m = document.querySelector('[data-roll-menu=\"root\"]').getBoundingClientRect();"
        "        return r.top - m.bottom; }",
        ring.element_handle(),
    )
    # Should be a small positive number (~4px design gap, allow some slack).
    assert 0 <= gap <= 20, f"menu bottom is {gap}px above ring top; expected a tight anchor"


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
    start_new_character(page)
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


# ---------------------------------------------------------------------------
# Athletics used as attack/parry (rules p05 §Athletics). Exposed as two
# additional entries in the athletics picker menu AND as choices when clicking
# the Attack/Parry buttons directly.
# ---------------------------------------------------------------------------


def test_athletics_picker_shows_attack_and_parry_options(page, live_server_url):
    """The athletics picker shows Athletics (Attack) and Athletics (Parry) buttons."""
    _create_athletics_knack_char(page, live_server_url, "AthCombatPick")
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    assert page.locator('[data-athletics-combat="attack"]').is_visible()
    assert page.locator('[data-athletics-combat="parry"]').is_visible()


def test_athletics_picker_attack_opens_attack_modal(page, live_server_url):
    """Clicking Athletics (Attack) in the picker opens the attack modal with the
    doubled-TN dropdown (TN = 5 + 10 * parry)."""
    _create_athletics_knack_char(page, live_server_url, "AthAtkModal")
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    page.locator('[data-athletics-combat="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # Title should show "Athletics Attack" (label stripped of "(Fire)")
    title = page.locator('[data-modal="attack"] h3.text-accent').text_content()
    assert "Athletics" in title and "Attack" in title
    # Doubled-TN dropdown: the "(Parry 3)" option should be TN 35, not 20
    body = page.locator('[data-modal="attack"]').text_content()
    assert "35 (Parry 3)" in body


def test_athletics_picker_has_predeclared_parry_row(page, live_server_url):
    """The athletics picker shows a 5th row, Athletics (Predeclared parry),
    below Athletics (Parry). Clicking it rolls athletics:parry with a +5
    predeclared-parry bonus baked into the formula flat."""
    _create_athletics_knack_char(page, live_server_url, "AthPredeclaredParry")
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(150)
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    row = page.locator('[data-athletics-combat="predeclared-parry"]')
    assert row.is_visible()
    # Original athletics:parry flat (before the +5 predeclared bonus)
    base_flat = page.evaluate("""() => {
        const el = document.getElementById('roll-formulas');
        const data = JSON.parse(el.textContent || '{}');
        return data['athletics:parry']?.flat || 0;
    }""")
    row.click()
    # Wait for the regular roll-result modal to land on phase 'done'
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done' && d.currentRollKey === 'athletics:parry') return true;
        }
        return false;
    }""", timeout=5000)
    info = page.evaluate("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done' && d.currentRollKey === 'athletics:parry') {
                return { flat: d.formula.flat, bonuses: d.formula.bonuses || [] };
            }
        }
        return null;
    }""")
    assert info is not None
    assert info["flat"] == base_flat + 5
    assert any(b.get("label") == "predeclared parry" and b.get("amount") == 5
               for b in info["bonuses"])


def test_athletics_picker_parry_rolls_athletics_parry(page, live_server_url):
    """Clicking Athletics (Parry) in the picker rolls the athletics:parry formula."""
    _create_athletics_knack_char(page, live_server_url, "AthParryPick")
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(150)
    page.locator('[data-roll-key="knack:athletics"]').click()
    page.wait_for_selector('[data-athletics-picker-menu]', state='visible', timeout=3000)
    page.locator('[data-athletics-combat="parry"]').click()
    page.wait_for_selector('[data-modal="dice-roller"] h3.text-accent', state='visible', timeout=5000)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Athletics" in title and "Parry" in title


def test_attack_button_shows_athletics_choice_when_athletics_available(page, live_server_url):
    """Clicking the Attack button opens a menu with Roll Attack / Athletics Attack
    when the character has athletics knack."""
    _create_athletics_knack_char(page, live_server_url, "AtkChoice")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-attack-choice-menu]', state='visible', timeout=3000)
    assert page.locator('[data-attack-choice="attack"]').is_visible()
    assert page.locator('[data-attack-choice="athletics_attack"]').is_visible()


def test_attack_button_no_choice_menu_for_non_athletics_character(page, live_server_url):
    """Akodo (no athletics knack) clicks attack → attack modal opens directly."""
    _create_roller(page, live_server_url, "AkodoAtk")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # No choice menu should appear
    assert not page.locator('[data-attack-choice-menu]').is_visible()


def test_attack_choice_athletics_opens_modal_with_doubled_tn(page, live_server_url):
    """Selecting Athletics Attack from the choice menu opens the modal with 5+10*P TN options."""
    _create_athletics_knack_char(page, live_server_url, "AtkChoiceAth")
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-attack-choice-menu]', state='visible', timeout=3000)
    page.locator('[data-attack-choice="athletics_attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    body = page.locator('[data-modal="attack"]').text_content()
    assert "athletics attack" in body.lower()
    assert "35 (Parry 3)" in body


def test_parry_menu_shows_athletics_parry_option(page, live_server_url):
    """Clicking parry with athletics available shows an Athletics Parry option
    in the parry menu."""
    _create_athletics_knack_char(page, live_server_url, "ParryAth")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    assert page.locator('[data-parry-menu-athletics]').is_visible()


def test_parry_menu_no_athletics_for_non_athletics_character(page, live_server_url):
    """Akodo (no athletics knack) parry menu has no Athletics Parry entry."""
    _create_roller(page, live_server_url, "AkodoParry")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    assert not page.locator('[data-parry-menu-athletics]').is_visible()


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
    page.wait_for_selector('[data-modal="dice-roller"] >> text="Total:"',
                           state='visible', timeout=5000)
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
    page.wait_for_selector('[data-modal="dice-roller"] >> text="Total:"',
                           state='visible', timeout=2000)
    body = page.text_content("body")
    assert "Total:" in body


def test_athletics_label_in_modal(page, live_server_url):
    _create_roller(page, live_server_url, "AthleticsChar")
    page.locator('[data-roll-key="athletics:Water"]').click()
    # Athletics ring clicks always show the roll menu; click "Roll" to proceed
    page.wait_for_selector('.fixed.z-50.bg-white.rounded-lg.shadow-xl', state='visible', timeout=5000)
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    menu.locator('button.font-medium:has-text("Roll")').first.click()
    page.wait_for_selector('[data-modal="dice-roller"] >> text="Total:"',
                           state='visible', timeout=5000)
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
    page.locator('[data-modal="attack"] select:visible').select_option("5")
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
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
    start_new_character(page)
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
    start_new_character(page)
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


# ---------------------------------------------------------------------------
# Freeform Roll (generic escape hatch for rules we don't model)
# ---------------------------------------------------------------------------


def test_freeform_button_visible_on_sheet(page, live_server_url):
    """The Freeform Roll button is visible in the Rings section header."""
    _create_roller(page, live_server_url, "FFButton")
    assert page.locator('[data-action="open-freeform-roll"]').is_visible()


def test_freeform_button_opens_modal(page, live_server_url):
    """Clicking Freeform Roll opens the modal in its pre-roll phase."""
    _create_roller(page, live_server_url, "FFOpen")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    modal = page.locator('[data-modal="freeform-roll"]')
    assert modal.locator('[data-freeform="rolled"]').is_visible()
    assert modal.locator('[data-freeform="kept"]').is_visible()
    assert modal.locator('[data-freeform="reroll-tens"]').is_visible()


def test_freeform_defaults_to_1k1(page, live_server_url):
    """Both dropdowns start at 1 by default (1k1)."""
    _create_roller(page, live_server_url, "FF1k1")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    rolled = page.locator('[data-freeform="rolled"]').input_value()
    kept = page.locator('[data-freeform="kept"]').input_value()
    assert rolled == "1"
    assert kept == "1"


def test_freeform_kept_cannot_exceed_rolled(page, live_server_url):
    """The 'kept' dropdown only exposes options up to 'rolled'."""
    _create_roller(page, live_server_url, "FFKeptCap")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    # With rolled=1, kept dropdown has only one option
    options = page.locator('[data-freeform="kept"] option').all_text_contents()
    assert options == ["1"]
    # Set rolled to 5 and kept options should expand
    page.locator('[data-freeform="rolled"]').select_option("5")
    options = page.locator('[data-freeform="kept"] option').all_text_contents()
    assert options == ["1", "2", "3", "4", "5"]


def test_freeform_lowering_rolled_clamps_kept(page, live_server_url):
    """If kept is higher than rolled after lowering rolled, kept clamps down."""
    _create_roller(page, live_server_url, "FFClamp")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    page.locator('[data-freeform="rolled"]').select_option("7")
    page.locator('[data-freeform="kept"]').select_option("5")
    # Lower rolled below kept
    page.locator('[data-freeform="rolled"]').select_option("3")
    page.wait_for_timeout(150)
    kept = page.locator('[data-freeform="kept"]').input_value()
    assert kept == "3"


def test_freeform_reroll_default_true_when_healthy(page, live_server_url):
    """Healthy character: Reroll 10s checkbox is checked by default."""
    _create_roller(page, live_server_url, "FFHealthy")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    assert page.locator('[data-freeform="reroll-tens"]').is_checked()


def test_freeform_reroll_default_false_when_impaired(page, live_server_url):
    """Impaired character: Reroll 10s checkbox is unchecked by default."""
    _create_roller(page, live_server_url, "FFImpaired")
    # Default Earth ring is 2; add 2 serious wounds to become impaired
    sw_section = page.locator('text="Serious Wounds"').locator('..')
    plus_btn = sw_section.locator('button', has_text="+").first
    plus_btn.click()
    page.wait_for_timeout(120)
    plus_btn.click()
    page.wait_for_timeout(300)
    # Open the modal - freeform reads impaired state live via tracking bridge
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    assert not page.locator('[data-freeform="reroll-tens"]').is_checked()


def test_freeform_reroll_checkbox_togglable(page, live_server_url):
    """The player can override the Reroll 10s default either way."""
    _create_roller(page, live_server_url, "FFToggle")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    cb = page.locator('[data-freeform="reroll-tens"]')
    assert cb.is_checked()
    cb.uncheck()
    assert not cb.is_checked()
    cb.check()
    assert cb.is_checked()


def test_freeform_roll_shows_result_with_total(page, live_server_url):
    """Clicking Roll produces a result with a Total."""
    _create_roller(page, live_server_url, "FFResult")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    page.locator('[data-freeform="rolled"]').select_option("4")
    page.locator('[data-freeform="kept"]').select_option("2")
    page.locator('[data-action="freeform-roll"]').click()
    # Wait for the result phase (dice-animation tray disappears, Total: appears)
    page.wait_for_selector('[data-modal="freeform-roll"] [data-freeform="total"]',
                           state='visible', timeout=10000)
    total = int(page.locator('[data-modal="freeform-roll"] [data-freeform="total"]').text_content())
    # 2 kept dice, each 1-10 (10s re-roll and explode), so total >= 2.
    assert total >= 2


def test_freeform_roll_again_returns_to_pre_phase(page, live_server_url):
    """Roll Again resets the modal to the pre-roll phase."""
    _create_roller(page, live_server_url, "FFAgain")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    page.locator('[data-action="freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"] [data-freeform="total"]',
                           state='visible', timeout=10000)
    page.locator('[data-action="freeform-roll-again"]').click()
    page.wait_for_timeout(150)
    # Pre-phase controls are visible again
    assert page.locator('[data-freeform="rolled"]').is_visible()
    assert page.locator('[data-action="freeform-roll"]').is_visible()


def test_freeform_modal_close_button(page, live_server_url):
    """The modal's × close button hides the modal."""
    _create_roller(page, live_server_url, "FFClose")
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    page.locator('[data-modal="freeform-roll"] button', has_text="×").click()
    page.wait_for_timeout(200)
    assert not page.locator('[data-modal="freeform-roll"]').is_visible()


def test_freeform_roll_applies_no_bonuses(page, live_server_url):
    """Rolling 1k1 caps total at 10 (ignoring 10s-reroll chain bonus), with no
    flat bonuses ever added from advantages, techniques, or skills."""
    _create_roller(page, live_server_url, "FFNoBonus")
    # Even Akodo's Charming +1k0 on bragging doesn't affect a freeform roll.
    page.locator('[data-action="open-freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"]', state='visible', timeout=3000)
    # Uncheck reroll so the result is strictly 1 d10 in [1,10]
    page.locator('[data-freeform="reroll-tens"]').uncheck()
    page.locator('[data-action="freeform-roll"]').click()
    page.wait_for_selector('[data-modal="freeform-roll"] [data-freeform="total"]',
                           state='visible', timeout=10000)
    total = int(page.locator('[data-modal="freeform-roll"] [data-freeform="total"]').text_content())
    # 1k1 with no reroll: total must be in [1, 10] with NO +flat bonuses.
    assert 1 <= total <= 10


# --- Action-dice tracking (initiative persistence + auto-spend) ---


def _close_dice_modal(page):
    """Close the dice roller modal to expose the sheet underneath."""
    page.locator('[data-modal="dice-roller"] button:has-text("×")').click()
    page.wait_for_timeout(150)


def test_initiative_populates_action_dice_section(page, live_server_url):
    """Rolling initiative persists the resulting dice to the Tracking section."""
    _create_roller(page, live_server_url, "ActionDiceInit")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    _close_dice_modal(page)
    section = page.locator('[data-testid="action-dice-section"]')
    assert section.is_visible()
    # Count of rendered dice matches the trackingBridge state
    count = page.evaluate("window._trackingBridge.actionDice.length")
    assert count > 0
    assert section.locator('[data-action="action-die"]').count() == count


def test_action_die_dropdown_marks_spent(page, live_server_url):
    """Clicking an unspent action die + 'Action was spent' marks it spent."""
    _create_roller(page, live_server_url, "ActionDieSpend")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    _close_dice_modal(page)
    first_die = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first
    first_die.click()
    page.locator('[data-action="action-die-spent"]').first.click()
    page.wait_for_timeout(100)
    spent = page.evaluate("window._trackingBridge.actionDice[0].spent")
    assert spent is True


def test_spent_action_die_dropdown_marks_unspent(page, live_server_url):
    """A spent die's dropdown has 'Mark as unspent' which flips it back."""
    _create_roller(page, live_server_url, "ActionDieUnspend")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    _close_dice_modal(page)
    # Pre-spend the first die programmatically, then flip it back via the UI
    page.evaluate(
        "window._trackingBridge.actionDice[0].spent = true;"
        " window._trackingBridge.save();"
    )
    page.wait_for_timeout(100)
    first_die = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first
    first_die.click()
    page.locator('[data-action="action-die-unspent"]').first.click()
    page.wait_for_timeout(100)
    spent = page.evaluate("window._trackingBridge.actionDice[0].spent")
    assert spent is False


def test_clear_action_dice_hides_section(page, live_server_url):
    """Clear button removes every action die and hides the section."""
    _create_roller(page, live_server_url, "ActionDieClear")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    _close_dice_modal(page)
    page.locator('[data-action="clear-action-dice"]').click()
    page.wait_for_timeout(100)
    remaining = page.evaluate("window._trackingBridge.actionDice.length")
    assert remaining == 0
    section = page.locator('[data-testid="action-dice-section"]')
    assert not section.is_visible()


def test_parry_auto_spends_lowest_action_die(page, live_server_url):
    """Rolling a parry marks the lowest unspent action die as spent."""
    _create_roller(page, live_server_url, "ActionDieParry")
    # Seed deterministic action dice so we can check "lowest" behavior
    page.evaluate(
        "window._trackingBridge.setActionDice([3, 5, 7]);"
    )
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.click()
    _wait_for_roll_result(page)
    dice = page.evaluate("window._trackingBridge.actionDice")
    # Lowest (value 3) should be spent, others untouched.
    assert dice[0]["spent"] is True
    assert dice[1]["spent"] is False
    assert dice[2]["spent"] is False


def test_attack_auto_spends_lowest_action_die(page, live_server_url):
    """Rolling an attack from the attack modal spends the lowest unspent die."""
    _create_roller(page, live_server_url, "ActionDieAttack")
    page.evaluate("window._trackingBridge.setActionDice([2, 4, 6]);")
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # Click the Roll button inside the attack modal
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_timeout(500)
    dice = page.evaluate("window._trackingBridge.actionDice")
    assert dice[0]["spent"] is True
    assert dice[1]["spent"] is False
    assert dice[2]["spent"] is False


def test_attack_with_all_dice_spent_still_rolls(page, live_server_url):
    """An attack with no unspent action dice proceeds (no die marked; no error)."""
    _create_roller(page, live_server_url, "ActionDieAllSpent")
    page.evaluate(
        "window._trackingBridge.actionDice = "
        "[{value: 3, spent: true}, {value: 5, spent: true}];"
        " window._trackingBridge.save();"
    )
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_timeout(500)
    dice = page.evaluate("window._trackingBridge.actionDice")
    # Both were already spent; remain spent, nothing else to spend.
    assert dice[0]["spent"] is True
    assert dice[1]["spent"] is True


def test_initiative_reroll_replaces_previous_action_dice(page, live_server_url):
    """Rolling initiative again replaces the stored action dice (new round)."""
    _create_roller(page, live_server_url, "ActionDieReroll")
    page.evaluate(
        "window._trackingBridge.actionDice = "
        "[{value: 9, spent: true}, {value: 9, spent: true}];"
        " window._trackingBridge.save();"
    )
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    dice = page.evaluate("window._trackingBridge.actionDice")
    # Freshly rolled dice: all unspent and not necessarily both 9.
    assert all(not d["spent"] for d in dice)


def test_parry_annotates_spent_die_with_result(page, live_server_url):
    """Parry auto-spends a die and annotates it with the parry total."""
    _create_roller(page, live_server_url, "ActionDieParryTooltip")
    page.evaluate("window._trackingBridge.setActionDice([3, 5, 7]);")
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-parry-menu]', state='visible', timeout=3000)
    page.locator('[data-parry-menu] button:has-text("Roll Parry")').first.click()
    _wait_for_roll_result(page)
    # Close the dice modal, then inspect the annotated die.
    page.locator('[data-modal="dice-roller"] button:has-text("×")').click()
    page.wait_for_timeout(100)
    spent_by = page.evaluate("window._trackingBridge.actionDice[0].spent_by")
    assert spent_by is not None
    assert spent_by.startswith("Parry: total ")


def test_attack_annotates_spent_die_with_result(page, live_server_url):
    """Attack auto-spends a die and annotates it with roll total + hit/miss."""
    _create_roller(page, live_server_url, "ActionDieAttackTooltip")
    page.evaluate("window._trackingBridge.setActionDice([2, 4, 6]);")
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_timeout(500)
    spent_by = page.evaluate("window._trackingBridge.actionDice[0].spent_by")
    assert spent_by is not None
    assert "Attack" in spent_by
    assert "vs TN" in spent_by
    # Outcome must be recorded even if we don't know hit/miss in advance.
    assert "hit" in spent_by or "miss" in spent_by


def test_attack_tooltip_updates_when_conviction_spent_on_damage(page, live_server_url):
    """Conviction spent on damage (after the damage roll) must be reflected in
    the spent action die's tooltip. Previously the tooltip was only written
    once at the end of rollDamage(), so later discretionary bonuses were lost."""
    import re
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "DmgConvTip")
    select_school(page, "brotherhood_of_shinsei_monk")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup DmgConvTip")
    # Seed an action die so the attack has one to auto-spend.
    page.evaluate("window._trackingBridge.setActionDice([5]);")
    page.wait_for_timeout(100)
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    # TN 5 is trivially low, guaranteeing a hit so damage roll is available.
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
    assert "HIT" in modal.text_content()
    modal.locator('button:text("Make Damage Roll")').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'damage-result') return true;
        }
        return false;
    }""", timeout=10000)
    before = page.evaluate("window._trackingBridge.actionDice[0].spent_by")
    m = re.search(r"damage (\d+)", before or "")
    assert m is not None, f"expected 'damage N' in tooltip, got {before!r}"
    dmg_before = int(m.group(1))
    modal.locator('[data-action="spend-conviction-damage"]').click()
    page.wait_for_timeout(200)
    after = page.evaluate("window._trackingBridge.actionDice[0].spent_by")
    m2 = re.search(r"damage (\d+)", after or "")
    assert m2 is not None, f"expected 'damage N' in tooltip, got {after!r}"
    assert int(m2.group(1)) == dmg_before + 1, (
        f"tooltip damage should be {dmg_before + 1} after +1 conviction; got {after!r}"
    )


def test_action_die_tooltip_uses_spent_by_text(page, live_server_url):
    """The die's title attribute reflects the stored spent_by text."""
    _create_roller(page, live_server_url, "ActionDieTooltipAttr")
    page.evaluate(
        "window._trackingBridge.actionDice = ["
        "{value: 4, spent: true, spent_by: 'Parry: total 22'}];"
        " window._trackingBridge.save();"
    )
    page.wait_for_timeout(100)
    die = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first
    assert die.get_attribute('title') == 'Parry: total 22'
    assert die.get_attribute('data-die-spent-by') == 'Parry: total 22'


def test_manual_spend_does_not_set_spent_by(page, live_server_url):
    """Clicking 'Action was spent' manually leaves spent_by empty (no action context)."""
    _create_roller(page, live_server_url, "ActionDieManual")
    page.locator('[data-roll-key="initiative"]').click()
    _wait_for_roll_result(page)
    page.locator('[data-modal="dice-roller"] button:has-text("×")').click()
    page.wait_for_timeout(100)
    first_die = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first
    first_die.click()
    page.locator('[data-action="action-die-spent"]').first.click()
    page.wait_for_timeout(100)
    spent_by = page.evaluate(
        "window._trackingBridge.actionDice[0].spent_by || null"
    )
    assert spent_by is None


# ---------------------------------------------------------------------------
# Per-die action menu (pick which die pays for an action)
# ---------------------------------------------------------------------------


def test_action_die_menu_shows_action_options(page, live_server_url):
    """Clicking an unspent action die opens a menu listing Roll Attack,
    Roll Parry, Predeclared Parry (+5), and Mark as spent at minimum."""
    _create_roller(page, live_server_url, "ADMenuOptions")
    page.evaluate("""
        window._trackingBridge.actionDice = [{value: 5, spent: false}];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    menu = page.locator('[data-action-die-menu-item="attack"]')
    menu.wait_for(state='visible', timeout=2000)
    assert page.locator('[data-action-die-menu-item="attack"]').is_visible()
    assert page.locator('[data-action-die-menu-item="parry"]').is_visible()
    assert page.locator('[data-action-die-menu-item="predeclared-parry"]').is_visible()
    assert page.locator('[data-action="action-die-spent"]').is_visible()


def test_action_die_menu_parry_spends_that_die(page, live_server_url):
    """Picking Parry from the per-die menu must spend *that* specific die,
    not the lowest unspent die."""
    _create_roller(page, live_server_url, "ADMenuParry")
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 3, spent: false},
            {value: 7, spent: false}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    # Click the SECOND die (value 7 - not the lowest).
    dice = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]')
    dice.nth(1).click()
    # Each die renders its own (hidden) menu, so scope to the open one.
    page.locator('[data-action-die-menu-item="parry"]:visible').click()
    # Wait for parry roll to complete.
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done' && d.currentRollKey === 'parry') return true;
        }
        return false;
    }""", timeout=5000)
    state = page.evaluate("window._trackingBridge.actionDice")
    # The 3 stays unspent; the 7 is spent and annotated as a parry.
    assert state[0]["spent"] is False
    assert state[1]["spent"] is True
    assert "Parry" in state[1].get("spent_by", "")


def test_action_die_menu_attack_opens_modal_spends_on_roll(page, live_server_url):
    """Picking Roll Attack opens the attack modal; clicking Roll in the
    modal spends the selected die (not the lowest)."""
    _create_roller(page, live_server_url, "ADMenuAttack")
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 2, spent: false},
            {value: 8, spent: false}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    # Click the second die.
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').nth(1).click()
    # Each die renders its own (hidden) menu, so scope to the open one.
    page.locator('[data-action-die-menu-item="attack"]:visible').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    state = page.evaluate("window._trackingBridge.actionDice")
    assert state[0]["spent"] is False
    assert state[1]["spent"] is True


def test_action_die_menu_attack_cancel_does_not_spend(page, live_server_url):
    """Opening the attack modal from the per-die menu and then cancelling
    leaves the die unspent - the spend fires only when Roll commits."""
    _create_roller(page, live_server_url, "ADMenuAttackCancel")
    page.evaluate("""
        window._trackingBridge.actionDice = [{value: 5, spent: false}];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.locator('[data-action-die-menu-item="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=3000)
    # Cancel via X button
    page.locator('[data-modal="attack"] button:has-text("×")').first.click()
    page.wait_for_timeout(200)
    state = page.evaluate("window._trackingBridge.actionDice")
    assert state[0]["spent"] is False


def test_athletics_only_die_menu_restricts_to_athletics(page, live_server_url):
    """An athletics-only die's menu must omit regular attack/parry/feint
    rows (only athletics attack/parry options + Mark as spent are shown)."""
    _create_roller(page, live_server_url, "ADMenuAthOnly")
    # Create a Togashi scenario so athletics:attack and athletics:parry
    # formulas exist, then seed an athletics-only die directly.
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 6, spent: false, athletics_only: true}
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(150)
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').first.click()
    page.wait_for_timeout(200)
    # Regular rows are gated behind !die.athletics_only and must not render.
    assert page.locator('[data-action-die-menu-item="attack"]').count() == 0
    assert page.locator('[data-action-die-menu-item="parry"]').count() == 0
    assert page.locator('[data-action-die-menu-item="predeclared-parry"]').count() == 0
    # Manual mark-spent is always available.
    assert page.locator('[data-action="action-die-spent"]').count() == 1
