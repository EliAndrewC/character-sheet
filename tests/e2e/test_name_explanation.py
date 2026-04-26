"""E2E: name explanation icon, edit modal, and sheet tooltip."""

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character

pytestmark = [pytest.mark.name_generator]


def _go_to_editor(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')


def _open_explanation_modal(page):
    page.locator('[data-action="open-explanation-modal"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="visible", timeout=3000)


# ---------------------------------------------------------------------------
# Icon + modal basics
# ---------------------------------------------------------------------------


def test_explanation_icon_visible(page, live_server_url):
    _go_to_editor(page, live_server_url)
    assert page.locator('[data-action="open-explanation-modal"]').is_visible()


def test_modal_opens_with_intro_text_and_empty_textarea(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    modal = page.locator('[data-modal="name-explanation"]')
    assert "Rokugani choose their adult names" in modal.inner_text()
    assert page.locator('[data-field="name-explanation-text"]').input_value() == ""


def test_modal_closes_on_cancel(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    page.locator('[data-action="cancel-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)


def test_modal_closes_on_escape(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    page.keyboard.press("Escape")
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)


def test_cancel_reverts_unsaved_edits(page, live_server_url):
    _go_to_editor(page, live_server_url)
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill("Typed but not saved.")
    page.locator('[data-action="cancel-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    # Reopen: textarea should be empty again (save never happened).
    _open_explanation_modal(page)
    assert page.locator('[data-field="name-explanation-text"]').input_value() == ""


# ---------------------------------------------------------------------------
# Save persists + icon highlights when explanation exists
# ---------------------------------------------------------------------------


def test_save_persists_and_reloads(page, live_server_url):
    """Save writes to the character (via autosave), survives a reload."""
    _go_to_editor(page, live_server_url)
    # Give the character a school + name so Apply Changes isn't blocked later.
    page.fill('input[name="name"]', "Isao")
    select_school(page, "akodo_bushi")
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill(
        "Chosen to honor a grandfather."
    )
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    # Let the debounced autosave flush.
    page.wait_for_timeout(2000)
    # Reload the editor to confirm the value came back from the server.
    page.reload()
    page.wait_for_selector('input[name="name"]')
    _open_explanation_modal(page)
    assert page.locator('[data-field="name-explanation-text"]').input_value() \
        == "Chosen to honor a grandfather."


def test_icon_highlights_when_explanation_exists(page, live_server_url):
    """The note icon switches to an accent style once the explanation has content."""
    _go_to_editor(page, live_server_url)
    btn = page.locator('[data-action="open-explanation-modal"]')
    # Before save: default muted style. border-ink/20 compiles to rgba ~ 20% opacity.
    initial_classes = btn.get_attribute("class") or ""
    assert "text-ink/70" in initial_classes
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill("A meaningful name.")
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    # After save: accent style.
    updated_classes = btn.get_attribute("class") or ""
    assert "text-accent" in updated_classes


# ---------------------------------------------------------------------------
# Sheet page tooltip
# ---------------------------------------------------------------------------


def test_sheet_shows_tooltip_icon_when_explanation_exists(page, live_server_url):
    """A character with a saved name explanation has a tooltip icon on the
    sheet; its contents are the explanation text."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Akodo Ginawa")
    select_school(page, "akodo_bushi")
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill(
        "Ginawa means 'honorable path'."
    )
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    apply_changes(page, "initial")
    # Apply redirects to the sheet. Verify tooltip marker is present and
    # carries the explanation as its inner text.
    page.wait_for_selector('[data-testid="name-explanation-tooltip"]', timeout=5000)
    tooltip = page.locator('[data-testid="name-explanation-tooltip"]')
    assert tooltip.is_visible()
    # tooltip-content is visibility:hidden until hover, so inner_text is
    # empty. Use text_content to read the hidden payload.
    assert "Ginawa means 'honorable path'." in (tooltip.text_content() or "")


def test_sheet_has_no_tooltip_icon_without_explanation(page, live_server_url):
    """No icon is rendered when the explanation is empty."""
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', "Akodo Ginawa")
    select_school(page, "akodo_bushi")
    apply_changes(page, "initial")
    # On the sheet, the marker element should not exist.
    assert page.locator('[data-testid="name-explanation-tooltip"]').count() == 0


def _make_character_with_explanation(page, live_server_url, name, explanation):
    _go_to_editor(page, live_server_url)
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    _open_explanation_modal(page)
    page.locator('[data-field="name-explanation-text"]').fill(explanation)
    page.locator('[data-action="save-explanation"]').click()
    page.wait_for_selector('[data-modal="name-explanation"]', state="hidden", timeout=3000)
    apply_changes(page, "set explanation")
    page.wait_for_selector('[data-testid="name-explanation-tooltip"]', timeout=5000)


def test_sheet_explanation_tooltip_click_toggles_on_desktop(page, live_server_url):
    """Clicking the icon on desktop opens (and re-clicking closes) the tooltip,
    without waiting for the 2000ms hover delay."""
    _make_character_with_explanation(
        page, live_server_url, "DesktopClick", "A name to remember."
    )
    trigger = page.locator('[data-testid="name-explanation-tooltip"]')
    tip = trigger.locator('.tooltip-content')
    # Initially hidden (CSS visibility:hidden).
    assert tip.evaluate("el => getComputedStyle(el).visibility") == "hidden"
    # Click opens immediately - no 2000ms wait.
    trigger.dispatch_event("click")
    page.wait_for_timeout(50)
    assert trigger.evaluate("el => el.classList.contains('tooltip-active')")
    assert tip.evaluate("el => getComputedStyle(el).visibility") == "visible"
    # Click again closes.
    trigger.dispatch_event("click")
    page.wait_for_timeout(50)
    assert not trigger.evaluate("el => el.classList.contains('tooltip-active')")


def test_sheet_explanation_tooltip_click_outside_closes(page, live_server_url):
    """Clicking outside the icon closes an open name-explanation tooltip."""
    _make_character_with_explanation(
        page, live_server_url, "ClickAway", "Some explanation."
    )
    trigger = page.locator('[data-testid="name-explanation-tooltip"]')
    trigger.dispatch_event("click")
    page.wait_for_timeout(50)
    assert trigger.evaluate("el => el.classList.contains('tooltip-active')")
    # Click somewhere else on the page.
    page.locator('body').dispatch_event("click")
    page.wait_for_timeout(50)
    assert not trigger.evaluate("el => el.classList.contains('tooltip-active')")


def test_sheet_explanation_tooltip_does_not_overflow_on_mobile(page, live_server_url):
    """At a phone-sized viewport, opening the explanation tooltip never makes
    the page horizontally scrollable - the tooltip is shifted left so its
    right edge fits within the viewport."""
    long_text = (
        "This name has a long explanation that would normally make a "
        "fixed-width tooltip overflow far past the right edge of a narrow "
        "phone viewport. Repeated. " * 4
    )
    _make_character_with_explanation(page, live_server_url, "MobileOverflow", long_text)
    page.set_viewport_size({"width": 380, "height": 800})
    page.wait_for_timeout(100)
    trigger = page.locator('[data-testid="name-explanation-tooltip"]')
    trigger.scroll_into_view_if_needed()
    trigger.dispatch_event("click")
    page.wait_for_timeout(100)
    # Tooltip is open.
    assert trigger.evaluate("el => el.classList.contains('tooltip-active')")
    tip = trigger.locator('.tooltip-content')
    assert tip.evaluate("el => getComputedStyle(el).visibility") == "visible"
    # Tooltip's bounding rect is fully within the layout viewport (with small
    # margin tolerance for sub-pixel rounding). Use clientWidth, not
    # window.innerWidth - on mobile, innerWidth grows to match the document's
    # post-overflow scrollWidth, which masks the very bug this test guards.
    rect = tip.bounding_box()
    vw = page.evaluate("document.documentElement.clientWidth")
    assert rect is not None
    assert rect["x"] >= -1, f"tooltip overflows left: x={rect['x']}"
    assert rect["x"] + rect["width"] <= vw + 1, (
        f"tooltip overflows right: x+w={rect['x'] + rect['width']}, vw={vw}"
    )
    # The page should not have horizontal scroll caused by the tooltip.
    page_scroll_w = page.evaluate("document.documentElement.scrollWidth")
    client_w = page.evaluate("document.documentElement.clientWidth")
    assert page_scroll_w <= client_w + 1, (
        f"page is horizontally scrollable: scrollWidth={page_scroll_w}, clientWidth={client_w}"
    )


def test_sheet_explanation_tooltip_does_not_overflow_in_mobile_emulation(
    browser, live_server_url, page
):
    """The same overflow check as above, but in a real mobile-emulation
    context (is_mobile=True, has_touch=True). On mobile, an absolutely-
    positioned tooltip that overflows the layout viewport pushes
    document.scrollWidth - and ``window.innerWidth`` - past the visual
    viewport. The clamp logic must not read innerWidth in that state, or
    it computes too small a shift and the tooltip stays clipped.

    Reproduces the live-site regression where the name-explanation
    tooltip drifted past the screen edge on a real phone even though
    desktop-mode clicktests were green."""
    long_text = (
        "This name has a long explanation that would normally make a "
        "fixed-width tooltip overflow far past the right edge of a narrow "
        "phone viewport. Repeated. " * 4
    )
    # Set up the character (and grab the sheet URL) in the default
    # desktop-style page fixture, which has the auth bypass header.
    _make_character_with_explanation(page, live_server_url, "MobileEmuOverflow", long_text)
    sheet_url = page.url

    mobile_ctx = browser.new_context(
        viewport={"width": 375, "height": 800},
        is_mobile=True,
        has_touch=True,
        extra_http_headers={"X-Test-User": "183026066498125825:eliandrewc"},
    )
    try:
        mp = mobile_ctx.new_page()
        mp.goto(sheet_url)
        mp.wait_for_load_state("networkidle")
        trigger = mp.locator('[data-testid="name-explanation-tooltip"]')
        trigger.tap()
        mp.wait_for_timeout(200)
        tip = trigger.locator('.tooltip-content')
        assert tip.evaluate("el => getComputedStyle(el).visibility") == "visible"
        rect = tip.bounding_box()
        vw = mp.evaluate("document.documentElement.clientWidth")
        assert rect is not None
        assert rect["x"] >= -1, f"tooltip overflows left: x={rect['x']}"
        assert rect["x"] + rect["width"] <= vw + 1, (
            f"tooltip overflows right: x+w={rect['x'] + rect['width']}, vw={vw}"
        )
    finally:
        mobile_ctx.close()
