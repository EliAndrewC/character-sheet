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


def test_precepts_pool_no_overflow_at_phone_width(page, live_server_url):
    """A 3rd Dan priest with a full 10-die precepts pool must not cause
    horizontal overflow at phone width. The pool dice icons should wrap
    within their flex container rather than forcing a scroll."""
    # Create the priest at desktop width first so the editor renders normally.
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "PhonePool")
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 2)
    click_plus(page, "skill_precepts", 5)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Phone Pool")
    sheet_url = page.url
    # Seed a full 10-die pool so the section renders its widest possible state.
    page.evaluate("""
        window._trackingBridge.preceptsPool = Array.from({length: 10}, () => ({value: 10}));
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.set_viewport_size(PHONE)
    page.goto(sheet_url)
    page.wait_for_selector('[data-testid="precepts-pool-section"]')
    page.wait_for_load_state("networkidle")
    _assert_no_horizontal_overflow(page)


def test_dan_badge_text_centered(page, live_server_url):
    """The Dan badge on the sheet has text-align: center so when the badge
    gets squeezed on a narrow viewport and the text wraps to a second line
    inside the oval, both lines stay horizontally centered rather than the
    second line collapsing to the left edge."""
    sheet_url = _create_character_then_phone(page, live_server_url, "DanCenter")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")
    # Find the Dan badge - the only span with rounded-full inside the school section.
    text_align = page.evaluate("""() => {
        const span = [...document.querySelectorAll('span.rounded-full')]
            .find(el => /\\d+(st|nd|rd|th) Dan/.test(el.textContent));
        return span ? getComputedStyle(span).textAlign : null;
    }""")
    assert text_align == "center", f"Dan badge text-align is {text_align!r}, expected 'center'"


def _create_character_with_modifier_loaded_skill(page, live_server_url):
    """Create a character whose bragging row has multiple roll modifiers
    (Fierce + raised Honor) so it earns the `skill-row--has-modifiers`
    class. Etiquette is added unmodified (no Charming, no honor bonus on
    that skill) so the test has a clean single-modifier-free row to
    compare against."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "RowLayout")
    select_school(page, "akodo_bushi")
    click_plus(page, "skill_bragging", 1)
    click_plus(page, "skill_etiquette", 1)
    page.check('input[name="adv_fierce"]')
    click_plus(page, "honor", 4)  # raise honor so the +Honor modifier kicks in
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Row Layout setup")
    return page.url


def test_skill_row_stacks_long_modifiers_on_phone(page, live_server_url):
    """A skill row with several roll modifiers (e.g. Bragging on a
    Fierce + high-honor Akodo) becomes too wide to fit one line on a
    phone. The grid layout flips that row to a 2-column layout where
    the parenthetical roll text spans a second row, while the name
    column keeps its width so other rows still line up."""
    sheet_url = _create_character_with_modifier_loaded_skill(page, live_server_url)
    page.set_viewport_size(PHONE)
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")

    bragging = page.locator('[data-roll-key="skill:bragging"]')
    bragging.scroll_into_view_if_needed()
    # Verify the renderer chose to flag this as a multi-modifier row.
    assert "skill-row--has-modifiers" in (bragging.get_attribute("class") or "")

    # Roll text should sit below the name (different y), not beside it.
    name_box = bragging.locator(".skill-row__name").bounding_box()
    roll_box = bragging.locator(".skill-row__roll").bounding_box()
    assert name_box and roll_box
    assert roll_box["y"] > name_box["y"] + 4, (
        f"Bragging roll ({roll_box}) should wrap below name ({name_box}) on phone"
    )

    # A simple no-modifier row should stay single-line at the same width.
    etiquette = page.locator('[data-roll-key="skill:etiquette"]')
    etiquette.scroll_into_view_if_needed()
    assert "skill-row--has-modifiers" not in (etiquette.get_attribute("class") or "")
    e_name_box = etiquette.locator(".skill-row__name").bounding_box()
    e_roll_box = etiquette.locator(".skill-row__roll").bounding_box()
    assert e_name_box and e_roll_box
    # Same row when single-line: tops within ~4px of each other.
    assert abs(e_roll_box["y"] - e_name_box["y"]) < 8, (
        f"Etiquette roll ({e_roll_box}) should sit on the same line as its name ({e_name_box})"
    )

    # Name column lines up across rows: same x and same width.
    assert name_box["x"] == e_name_box["x"]
    assert name_box["width"] == e_name_box["width"]


def test_skill_row_stays_three_column_on_desktop(page, live_server_url):
    """At desktop width every skill row sits on a single line in a
    three-column grid (name | pips | roll), regardless of how many roll
    modifiers it carries."""
    sheet_url = _create_character_with_modifier_loaded_skill(page, live_server_url)
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(sheet_url)
    page.wait_for_load_state("networkidle")

    for sid in ("bragging", "etiquette"):
        row = page.locator(f'[data-roll-key="skill:{sid}"]')
        row.scroll_into_view_if_needed()
        n = row.locator(".skill-row__name").bounding_box()
        r = row.locator(".skill-row__roll").bounding_box()
        assert n and r
        # Same row when desktop 3-column: tops within ~4px of each other.
        assert abs(r["y"] - n["y"]) < 8, (
            f"{sid} desktop layout should be one line (name {n}, roll {r})"
        )


def test_sheet_no_horizontal_overflow_across_widths(page, live_server_url):
    """View Sheet must not overflow horizontally at phone, tablet, or
    desktop widths. The Phase 6 art/school grid was the trigger for
    adding this test - it ensures the lg:grid doesn't blow past the
    viewport on narrow screens."""
    sheet_url = _create_character_then_phone(page, live_server_url, "SheetWidths")
    for viewport in (
        {"width": 375, "height": 667},     # phone
        {"width": 768, "height": 1024},    # tablet
        {"width": 1280, "height": 720},    # desktop
    ):
        page.set_viewport_size(viewport)
        page.goto(sheet_url)
        page.wait_for_load_state("networkidle")
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
