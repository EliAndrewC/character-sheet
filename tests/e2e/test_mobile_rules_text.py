"""E2E: mobile (touch) rules-text flow on the View Sheet page.

The sheet used to surface a "?" icon next to every tooltip-trigger on touch
devices. The icon was visually noisy and didn't reliably work for skills/
attack/parry (the data-roll-key click handler swallowed the toggle). We
replaced it with a "View rules text" row at the bottom of the roll menu;
desktop hover keeps its 2s tooltip and never sees the row.

These tests stub ``matchMedia('(hover: none)')`` to force the touch path
in a chromium build that otherwise reports hover: hover. That stub is
exactly what the production code branches on, so it's the right level of
emulation for testing the behavior toggle.
"""

import pytest
from tests.e2e.helpers import (
    apply_changes,
    click_plus,
    select_school,
    start_new_character,
)

pytestmark = [pytest.mark.responsive, pytest.mark.rolls]

PHONE = {"width": 375, "height": 667}

# Force the production "(hover: none)" branch on. We don't rely on
# Playwright's is_mobile/has_touch context options because they don't
# always flip the hover media-query in headless chromium.
TOUCH_STUB = """
    const _origMM = window.matchMedia.bind(window);
    window.matchMedia = (q) => {
        const r = _origMM(q);
        if (typeof q === 'string' && q.includes('hover: none')) {
            return { matches: true, media: q,
                     addListener: () => {}, removeListener: () => {},
                     addEventListener: () => {}, removeEventListener: () => {},
                     onchange: null, dispatchEvent: () => false };
        }
        return r;
    };
"""


def _create_character(page, live_server_url, name):
    """Create a small Akodo Bushi character with one ranked skill and one
    advantage so the sheet has the things the tests want to interact
    with: a skill row that has rules text, an advantage with a tooltip,
    and the standard Attack / Parry combat tiles."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_etiquette", 1)
    page.check('input[name="adv_charming"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Mobile rules-text setup")
    return page.url


def _open_sheet_with_touch_stub(page, sheet_url):
    """Apply the touch stub on the next navigation, set the phone
    viewport, and reload the sheet so openRollMenu sees hover: none."""
    page.add_init_script(TOUCH_STUB)
    page.set_viewport_size(PHONE)
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")


def test_skill_tap_opens_menu_with_view_rules_text(page, live_server_url):
    """Tapping a skill row on a touch device opens the roll menu with a
    'View rules text' row at the bottom; clicking that row opens the
    rules modal containing the skill's description."""
    sheet_url = _create_character(page, live_server_url, "MobileSkill")
    _open_sheet_with_touch_stub(page, sheet_url)

    page.locator('[data-roll-key="skill:etiquette"]').click()

    menu = page.locator('[data-roll-menu="root"]')
    menu.wait_for(state="visible")
    rules_btn = menu.locator('[data-action="view-rules-text"]')
    assert rules_btn.is_visible(), "View rules text row should appear in the skill menu on touch"

    rules_btn.click()
    modal = page.locator('[data-modal="rules-text"]')
    modal.wait_for(state="visible")
    body = modal.locator('[data-rules-modal-body]').text_content() or ""
    # The Etiquette skill description is the canonical content of the tooltip
    # we copied in. Substring match keeps the test resilient if the rules
    # text gets slightly reworded.
    assert "Etiquette" in body
    # Modal should show the upstream canonical rules text (not the old
    # one-line summary). This phrase is the opening of the rules block in
    # rules/02-skills.md and exercises the rules_text field.
    assert "Protocol is extremely important" in body, (
        f"Expected canonical etiquette rules text in modal, got: {body[:200]!r}"
    )
    # Close out so we don't pollute later assertions on the same page.
    modal.locator('[data-action="close-rules-modal"]').click()
    modal.wait_for(state="hidden")


def test_attack_tap_opens_menu_with_roll_and_view_rules(page, live_server_url):
    """Tapping the Attack tile on a touch device opens a menu with a
    'Roll Attack' row (which opens the existing attack modal) plus the
    'View rules text' row. Desktop still jumps straight into the attack
    modal on click, so this is a touch-only behavior."""
    sheet_url = _create_character(page, live_server_url, "MobileAttack")
    _open_sheet_with_touch_stub(page, sheet_url)

    page.locator('[data-roll-key="attack"]').click()
    menu = page.locator('[data-roll-menu="root"]')
    menu.wait_for(state="visible")

    # Two rows: the mobile-attack Roll button and the rules-text row.
    roll_btn = menu.locator('[data-mobile-attack-roll]')
    rules_btn = menu.locator('[data-action="view-rules-text"]')
    assert roll_btn.is_visible()
    assert rules_btn.is_visible()

    # "Roll Attack" should open the attack modal that desktop sees.
    roll_btn.click()
    attack_modal = page.locator('[data-modal="attack"]')
    attack_modal.wait_for(state="visible", timeout=3000)
    # Close the attack modal.
    attack_modal.locator('button', has_text="×").first.click()

    # Tap attack again, this time use the rules-text route.
    page.locator('[data-roll-key="attack"]').click()
    page.locator('[data-action="view-rules-text"]').click()
    rules_modal = page.locator('[data-modal="rules-text"]')
    rules_modal.wait_for(state="visible")
    body = rules_modal.locator('[data-rules-modal-body]').text_content() or ""
    assert "Attack" in body and "TN" in body  # canonical attack tooltip phrasing


def test_parry_menu_includes_view_rules_text_on_touch(page, live_server_url):
    """Parry already opens a menu on every device. On touch the new
    'View rules text' row should be appended to that existing menu."""
    sheet_url = _create_character(page, live_server_url, "MobileParry")
    _open_sheet_with_touch_stub(page, sheet_url)

    page.locator('[data-roll-key="parry"]').click()
    menu = page.locator('[data-roll-menu="root"]')
    menu.wait_for(state="visible")

    # Pre-existing parry rows are still there.
    assert menu.locator('[data-parry-menu]').is_visible()
    # And the new rules-text row was appended.
    rules_btn = menu.locator('[data-action="view-rules-text"]')
    assert rules_btn.is_visible()


def _charming_advantage_row(page):
    """Locate the Charming *advantage* tooltip-trigger.

    Charming also appears as a bonus source on the Etiquette skill row,
    and that skill row is itself a tooltip-trigger with data-roll-key.
    Filter out roll-key triggers so we don't accidentally grab the
    skill row instead of the advantage."""
    return page.locator('div.tooltip-trigger:not([data-roll-key])').filter(
        has=page.locator('span.cursor-help', has_text="Charming")
    ).first


def test_advantage_tap_shows_inline_tooltip(page, live_server_url):
    """Advantages have no roll/menu, so the tap-to-toggle from base.html
    still applies: tapping an advantage toggles its inline tooltip.

    We dispatch a synthetic click rather than using Playwright's mouse
    click - chromium's mouse simulation leaves the cursor hovering over
    the element, which fires the 2000ms desktop hover rule and confuses
    the assertion. A bare ``click()`` event mirrors what a real tap
    delivers on a touch device (no lingering hover)."""
    sheet_url = _create_character(page, live_server_url, "MobileAdv")
    _open_sheet_with_touch_stub(page, sheet_url)

    adv = _charming_advantage_row(page)
    adv.scroll_into_view_if_needed()
    tt = adv.locator('.tooltip-content').first
    assert tt.evaluate("el => getComputedStyle(el).visibility") == "hidden"
    # The JS class-toggle and the CSS-driven visibility flip should both
    # land in the same microtask as the click event.
    adv.dispatch_event("click")
    assert adv.evaluate("el => el.classList.contains('tooltip-active')")
    assert tt.evaluate("el => getComputedStyle(el).visibility") == "visible"


def test_no_question_mark_after_pseudo_element(page, live_server_url):
    """The ``?`` indicator that previously appeared next to every
    tooltip-trigger on touch is gone. We assert by reading the
    computed ``::after`` content of an advantage row, which used to be
    the canonical quoted-string '"?"'."""
    sheet_url = _create_character(page, live_server_url, "MobileNoQ")
    _open_sheet_with_touch_stub(page, sheet_url)

    adv = _charming_advantage_row(page)
    adv.scroll_into_view_if_needed()
    after_content = adv.evaluate(
        "el => getComputedStyle(el, '::after').content"
    )
    # CSS reports unset content as "none". Either is fine; what matters
    # is that the literal "?" character is no longer there.
    assert "?" not in after_content, f"::after still emits a ? indicator: {after_content!r}"
