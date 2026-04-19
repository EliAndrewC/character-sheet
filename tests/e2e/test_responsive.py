"""E2E: Responsive design sanity checks.

These run at a phone-sized viewport (375x667) to catch layout issues that
only appear on narrow screens: horizontal overflow, hamburger nav toggle,
and label truncation producing zero-width elements.
"""

import pytest
from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character

pytestmark = pytest.mark.responsive

PHONE = {"width": 375, "height": 667}


# ---------------------------------------------------------------------------
# No horizontal overflow
# ---------------------------------------------------------------------------


def _assert_no_horizontal_overflow(page):
    overflow = page.evaluate(
        "() => document.body.scrollWidth - window.innerWidth"
    )
    if overflow > 0:
        culprit = page.evaluate("""() => {
            const vw = window.innerWidth;
            const bad = [];
            document.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.right > vw + 2) {
                    bad.push({
                        tag: el.tagName,
                        cls: el.className?.toString?.()?.substring(0, 80) || '',
                        text: el.textContent?.substring(0, 40) || '',
                        right: Math.round(r.right),
                        width: Math.round(r.width),
                    });
                }
            });
            return bad.slice(0, 5);
        }""")
        for c in culprit:
            print(f"  OVERFLOW: <{c['tag']}> right={c['right']}px w={c['width']}px cls={c['cls'][:60]} text={c['text'][:30]}")
    assert overflow <= 0, f"Page overflows by {overflow}px horizontally"


def _create_character_then_phone(page, live_server_url, name="Phone Test"):
    """Create a character at desktop width, then return the sheet URL."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    return page.url  # sheet URL


def test_sheet_no_horizontal_overflow(page, live_server_url):
    """The character sheet has no horizontal scrollbar at phone width."""
    sheet_url = _create_character_then_phone(page, live_server_url, "SheetOverflow")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")
    _assert_no_horizontal_overflow(page)


def test_edit_no_horizontal_overflow(page, live_server_url):
    """The editor page has no horizontal scrollbar at phone width."""
    sheet_url = _create_character_then_phone(page, live_server_url, "EditOverflow")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('input[name="name"]')
    _assert_no_horizontal_overflow(page)


def test_homepage_no_horizontal_overflow(page, live_server_url):
    """The homepage has no horizontal scrollbar at phone width."""
    page.set_viewport_size(PHONE)
    page.goto(live_server_url)
    _assert_no_horizontal_overflow(page)


def test_homepage_headshot_placeholder_fits_card_at_phone_width(page, live_server_url):
    """The headshot placeholder next to each character name must be the
    documented 60x80 px and must not push the card text off-screen on a
    375 px phone."""
    # Need at least one character for the list to render any card.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Placeholder Card")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    page.goto(live_server_url)
    page.set_viewport_size(PHONE)

    placeholder = page.locator('[data-testid="character-headshot-placeholder"]').first
    placeholder.wait_for()
    box = placeholder.bounding_box()
    assert box is not None
    # Documented 60x80 (3:4 portrait) - allow a couple of px for Tailwind
    # rounding, never a zero-width collapse.
    assert 58 <= box["width"] <= 62, f"headshot width {box['width']} px"
    assert 78 <= box["height"] <= 82, f"headshot height {box['height']} px"
    _assert_no_horizontal_overflow(page)


# ---------------------------------------------------------------------------
# Nav hamburger toggle
# ---------------------------------------------------------------------------


def test_hamburger_visible_on_phone(page, live_server_url):
    """At phone width the hamburger button appears and nav items are hidden."""
    page.set_viewport_size(PHONE)
    page.goto(live_server_url)
    hamburger = page.locator('nav button[aria-label="Toggle navigation"]')
    assert hamburger.is_visible()
    # The "New Character" button should be hidden until toggled
    new_char = page.locator('nav button:text("New Character")')
    assert not new_char.is_visible()


def test_hamburger_toggle_shows_nav(page, live_server_url):
    """Clicking the hamburger reveals nav items; clicking again hides them."""
    page.set_viewport_size(PHONE)
    page.goto(live_server_url)
    hamburger = page.locator('nav button[aria-label="Toggle navigation"]')
    hamburger.click()
    page.wait_for_timeout(200)
    assert page.locator('nav button:text("New Character")').is_visible()
    # Close
    hamburger.click()
    page.wait_for_timeout(200)
    assert not page.locator('nav button:text("New Character")').is_visible()


def test_nav_visible_without_hamburger_on_desktop(page, live_server_url):
    """At desktop width the nav items are always visible without a hamburger."""
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(live_server_url)
    hamburger = page.locator('nav button[aria-label="Toggle navigation"]')
    assert not hamburger.is_visible()
    assert page.locator('nav button:text("New Character")').is_visible()


# ---------------------------------------------------------------------------
# No zero-width truncated labels
# ---------------------------------------------------------------------------


def _check_no_zero_width_truncated(page):
    """Assert all .truncate elements have non-zero rendered width."""
    zero_width = page.evaluate("""() => {
        const els = document.querySelectorAll('.truncate');
        const bad = [];
        for (const el of els) {
            if (el.offsetWidth === 0 && el.offsetParent !== null) {
                bad.push(el.textContent.trim().substring(0, 30));
            }
        }
        return bad;
    }""")
    assert zero_width == [], f"Labels with zero width: {zero_width}"


def test_no_zero_width_labels_on_editor(page, live_server_url):
    """All truncated labels on the editor have non-zero rendered width at
    phone size."""
    sheet_url = _create_character_then_phone(page, live_server_url, "EditorLabels")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('input[name="name"]')
    _check_no_zero_width_truncated(page)


def test_no_zero_width_labels_on_sheet(page, live_server_url):
    """All truncated labels on the sheet have non-zero rendered width at
    phone size."""
    sheet_url = _create_character_then_phone(page, live_server_url, "SheetLabels")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")
    _check_no_zero_width_truncated(page)
