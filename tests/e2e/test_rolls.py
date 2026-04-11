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


def test_click_parry_opens_modal(page, live_server_url):
    _create_roller(page, live_server_url, "ClickParry")
    page.locator('[data-roll-key="parry"]').click()
    page.wait_for_selector('[data-modal="dice-roller"] h3.text-accent', state='visible', timeout=5000)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Parry" in title


def test_click_ring_opens_athletics_modal(page, live_server_url):
    _create_roller(page, live_server_url, "ClickRing")
    page.locator('[data-roll-key="athletics:Earth"]').click()
    page.wait_for_selector('[data-modal="dice-roller"] h3.text-accent', state='visible', timeout=5000)
    title = page.locator('[data-modal="dice-roller"] h3.text-accent').text_content()
    assert "Athletics" in title and "Earth" in title


def test_modal_shows_total_and_dice_after_animation(page, live_server_url):
    _create_roller(page, live_server_url, "ResultChar")
    # Disable animations via JS so the result panel appears immediately
    page.add_init_script(
        "localStorage.l7r_no_anim = '1';"
    )
    page.locator('[data-roll-key="skill:bragging"]').click()
    # Wait for the result Total to appear
    page.wait_for_selector('text="Total:"', state='visible', timeout=5000)
    body = page.locator('div.bg-ink\\/5').last.text_content()
    assert "Total:" in body


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
    page.locator('[data-roll-key="attack"]').click()
    # Attack now opens the attack modal - click "Roll Attack" to start the roll
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    page.locator('[data-modal="attack"] button:text("Roll Attack")').click()
    # Wait until the rolling phase has rendered the dice tray AND the dice
    # have stopped tumbling (otherwise the rotation transform skews
    # getBoundingClientRect and the measured angle is wrong).
    page.wait_for_function(
        "document.querySelectorAll('#dice-animation-atk svg.die').length > 0",
        timeout=5000,
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
    menu = page.locator('.fixed.z-50.bg-white.rounded-lg.shadow-xl')
    if menu.count() > 0 and menu.is_visible():
        # Click the first non-iaijutsu-strike button (the "Roll X" default)
        menu.locator('button.font-medium').first.click()
        page.wait_for_timeout(100)


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
