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


def test_edit_basics_section_contains_its_controls(page, live_server_url):
    """The Basics section's white card must visually contain its controls
    at narrow phone widths (320-360 px). CSS grid items default to
    min-width: auto, so the longest <select> option (e.g. a player or
    gaming-group name) and the input + icon buttons row used to push
    the column track wider than the section, leaving the Player /
    Gaming Group dropdowns and the name-explanation icon button
    bleeding past the white card's right edge."""
    sheet_url = _create_character_then_phone(page, live_server_url, "BasicsBounds")
    edit_url = sheet_url + "/edit"
    for width in (320, 360, 375):
        page.set_viewport_size({"width": width, "height": 667})
        page.goto(edit_url)
        page.wait_for_selector('input[name="name"]')
        bleed = page.evaluate("""() => {
            const sec = [...document.querySelectorAll('section')]
                .find(s => s.querySelector('h2')?.textContent?.includes('Basics'));
            if (!sec) return [{tag: 'NONE', reason: 'no Basics section'}];
            const r = sec.getBoundingClientRect();
            const cs = getComputedStyle(sec);
            const innerRight = r.right - parseFloat(cs.paddingRight);
            const out = [];
            sec.querySelectorAll('input, select, button').forEach(el => {
                const er = el.getBoundingClientRect();
                if (er.width === 0) return;
                if (er.right > innerRight + 0.5) {
                    out.push({tag: el.tagName, right: Math.round(er.right), w: Math.round(er.width)});
                }
            });
            return out;
        }""")
        assert bleed == [], f"At width {width}px, Basics section controls overflow: {bleed}"


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


def _stub_alpine_route(ctx):
    """Make alpine.min.js return an empty body, so Alpine never initializes
    on the next navigation. The element classes / data-* attrs stay in the
    DOM exactly as the server sent them, which is what a real user sees in
    the brief window between HTML parse and Alpine boot."""
    ctx.route(
        "**/static/js/alpine.min.js",
        lambda route: route.fulfill(status=200, body="", content_type="application/javascript"),
    )


def test_nav_dropdown_hidden_on_mobile_before_alpine_init(browser, live_server_url):
    """The nav dropdown (New Character / username / Admin / Logout) must be
    hidden on mobile during the pre-Alpine FOUC window. Without the static
    `hidden` class on the dropdown, mobile users briefly see the menu flash
    open as the page is still loading."""
    ctx = browser.new_context(
        viewport={"width": 375, "height": 700},
        is_mobile=True,
        has_touch=True,
        extra_http_headers={"X-Test-User": "183026066498125825:eliandrewc"},
    )
    try:
        _stub_alpine_route(ctx)
        p = ctx.new_page()
        p.goto(live_server_url)
        p.wait_for_load_state("networkidle")
        # The "New Character" button lives inside the dropdown - if the
        # dropdown is still visible during FOUC it'll be visible too.
        nc = p.locator('nav button:text("New Character")')
        assert not nc.is_visible(), (
            "New Character button (inside the nav dropdown) is visible on "
            "mobile before Alpine init - the dropdown is FOUC-ing open."
        )
    finally:
        ctx.close()


def test_nav_dropdown_visible_on_desktop_before_alpine_init(browser, live_server_url):
    """The mobile-FOUC fix must NOT regress desktop: the nav stays visible
    even when Alpine has not yet initialized."""
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 720},
        extra_http_headers={"X-Test-User": "183026066498125825:eliandrewc"},
    )
    try:
        _stub_alpine_route(ctx)
        p = ctx.new_page()
        p.goto(live_server_url)
        p.wait_for_load_state("networkidle")
        nc = p.locator('nav button:text("New Character")')
        assert nc.is_visible(), (
            "New Character button must be visible on desktop pre-Alpine; "
            "the static `sm:flex` class should override the static `hidden`."
        )
    finally:
        ctx.close()


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


# ---------------------------------------------------------------------------
# Mobile rules-text expand toggles on the editor
#
# On phones the desktop hover tooltip turns into an awkward tap-to-toggle
# that fights the checkbox / +/- controls in the same row. The editor
# replaces it under <sm with a chevron button at the right of each row;
# tapping the chevron expands a rules-text panel below the row, leaving
# the form controls undisturbed.
# ---------------------------------------------------------------------------


def test_edit_advantage_chevron_expands_rules_text_on_phone(page, live_server_url):
    """Tapping the chevron on the Charming advantage row at phone width
    expands the rules text panel; tapping again collapses it. The SVG
    rotates 180 degrees while expanded."""
    sheet_url = _create_character_then_phone(page, live_server_url, "AdvChev")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('input[name="adv_charming"]')

    chevron = page.locator('[data-testid="adv-chevron-charming"]')
    panel = page.locator('[data-testid="adv-rules-charming"]')
    svg = chevron.locator('svg')

    assert chevron.is_visible(), "chevron should be visible at phone width"
    assert not panel.is_visible(), "rules panel should be collapsed initially"
    assert "rotate-180" not in (svg.get_attribute("class") or "")

    chevron.click()
    panel.wait_for(state="visible", timeout=2000)
    panel_text = (panel.text_content() or "").strip()
    assert "free raise on etiquette" in panel_text.lower(), (
        f"expected Charming rules text, got {panel_text!r}"
    )
    assert "rotate-180" in (svg.get_attribute("class") or "")

    chevron.click()
    panel.wait_for(state="hidden", timeout=2000)
    assert "rotate-180" not in (svg.get_attribute("class") or "")


def test_edit_advantage_chevron_does_not_toggle_checkbox(page, live_server_url):
    """Clicking the chevron must not flip the underlying checkbox.
    The label still toggles the checkbox on its own click - that's fine -
    but the chevron lives outside the label and must not bubble into it."""
    sheet_url = _create_character_then_phone(page, live_server_url, "AdvChevCB")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('input[name="adv_charming"]')

    cb = page.locator('input[name="adv_charming"]')
    chevron = page.locator('[data-testid="adv-chevron-charming"]')
    initial = cb.is_checked()

    for _ in range(3):
        chevron.click()
        page.wait_for_timeout(50)
        assert cb.is_checked() == initial, (
            "Chevron click flipped the checkbox; it must only toggle the rules panel"
        )


def test_edit_disadvantage_chevron_expands_rules_text_on_phone(page, live_server_url):
    """Same chevron pattern works for disadvantage rows."""
    sheet_url = _create_character_then_phone(page, live_server_url, "DisChev")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('input[name="dis_vain"]')

    chevron = page.locator('[data-testid="dis-chevron-vain"]')
    panel = page.locator('[data-testid="dis-rules-vain"]')

    assert chevron.is_visible()
    assert not panel.is_visible()
    chevron.click()
    panel.wait_for(state="visible", timeout=2000)
    assert (panel.text_content() or "").strip() != ""


def test_edit_campaign_advantage_chevron_expands_rules_text_on_phone(page, live_server_url):
    """Same chevron pattern works for the Wasp Campaign advantages
    section. We don't need a parallel test for campaign disadvantages -
    the markup in that section is identical to campaign advantages."""
    sheet_url = _create_character_then_phone(page, live_server_url, "CampChev")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_load_state("networkidle")

    chevron = page.locator('[data-testid^="camp-adv-chevron-"]').first
    aid = (chevron.get_attribute("data-testid") or "").removeprefix("camp-adv-chevron-")
    panel = page.locator(f'[data-testid="camp-adv-rules-{aid}"]')

    chevron.scroll_into_view_if_needed()
    assert chevron.is_visible()
    assert not panel.is_visible()
    chevron.click()
    panel.wait_for(state="visible", timeout=2000)
    assert (panel.text_content() or "").strip() != ""


def test_edit_skill_row_mobile_layout(page, live_server_url):
    """At phone width, the skill row stacks name + controls into column 1,
    puts the roll display in column 2, and adds a chevron column 3.
    The XP-cost label is hidden on mobile."""
    sheet_url = _create_character_then_phone(page, live_server_url, "SkillMobile")
    page.set_viewport_size(PHONE)
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('[data-testid="skill-chevron-bragging"]')

    layout = page.evaluate("""() => {
        const row = document.querySelector('[data-testid="skill-chevron-bragging"]')
                            .closest('.editor-skill-row');
        const r = (sel) => {
            const el = row.querySelector(sel);
            if (!el) return null;
            const b = el.getBoundingClientRect();
            return {x: b.x, y: b.y, width: b.width, height: b.height};
        };
        const xp = row.querySelector('.editor-skill-row__xp');
        return {
            display: getComputedStyle(row).display,
            name: r('.editor-skill-row__name'),
            ctrls: r('.editor-skill-row__ctrls'),
            roll: r('.editor-skill-row__roll'),
            chev: r('.editor-skill-row__chevron'),
            xp_display: xp ? getComputedStyle(xp).display : null,
        };
    }""")

    assert layout["display"] == "grid", f"expected grid layout on phone, got {layout['display']}"
    # Name and controls share column 1: same x, different y (controls below name).
    assert layout["name"]["x"] == layout["ctrls"]["x"], (
        f"name x={layout['name']['x']} should equal ctrls x={layout['ctrls']['x']}"
    )
    assert layout["ctrls"]["y"] > layout["name"]["y"] + 4, (
        f"ctrls (y={layout['ctrls']['y']}) should sit below name (y={layout['name']['y']})"
    )
    # Roll display sits in column 2: x is to the right of name's right edge.
    name_right = layout["name"]["x"] + layout["name"]["width"]
    assert layout["roll"]["x"] >= name_right, (
        f"roll (x={layout['roll']['x']}) should start to the right of name (right={name_right})"
    )
    # Chevron in column 3: to the right of the roll's right edge.
    roll_right = layout["roll"]["x"] + layout["roll"]["width"]
    assert layout["chev"]["x"] >= roll_right - 1, (
        f"chevron (x={layout['chev']['x']}) should sit right of roll (right={roll_right})"
    )
    # XP-cost label hidden on mobile.
    assert layout["xp_display"] == "none", (
        f"XP-cost label should be display:none on phone, got {layout['xp_display']!r}"
    )


def test_edit_skill_row_desktop_layout_unchanged(page, live_server_url):
    """At desktop width the skill row keeps the original single-line flex
    layout: name, controls, XP label, roll display all on the same y line.
    The chevron is hidden via sm:hidden."""
    sheet_url = _create_character_then_phone(page, live_server_url, "SkillDesk")
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('.editor-skill-row')

    layout = page.evaluate("""() => {
        const row = document.querySelector('.editor-skill-row');
        const r = (sel) => {
            const el = row.querySelector(sel);
            if (!el) return null;
            const b = el.getBoundingClientRect();
            return {x: b.x, y: b.y, width: b.width};
        };
        const chev = row.querySelector('.editor-skill-row__chevron');
        const xp = row.querySelector('.editor-skill-row__xp');
        return {
            display: getComputedStyle(row).display,
            name: r('.editor-skill-row__name'),
            ctrls: r('.editor-skill-row__ctrls'),
            xp: r('.editor-skill-row__xp'),
            roll: r('.editor-skill-row__roll'),
            chev_display: chev ? getComputedStyle(chev).display : null,
            xp_display: xp ? getComputedStyle(xp).display : null,
        };
    }""")

    assert layout["display"] == "flex", f"expected flex on desktop, got {layout['display']}"
    assert layout["chev_display"] == "none", "chevron must be hidden on desktop"
    assert layout["xp_display"] != "none", "XP label must be visible on desktop"
    # All four visible elements line up on roughly the same y (within 8px).
    ys = [layout[k]["y"] for k in ("name", "ctrls", "xp", "roll")]
    spread = max(ys) - min(ys)
    assert spread < 8, (
        f"name/ctrls/xp/roll should sit on one line on desktop; y spread = {spread}"
    )


def test_edit_chevron_hidden_on_desktop(page, live_server_url):
    """All editor row chevrons collapse to display:none at sm and up.
    Tested across one advantage row and one skill row to cover both
    sm:hidden uses (utility class on advantage chevrons, named-area
    grid track on skill chevrons)."""
    sheet_url = _create_character_then_phone(page, live_server_url, "DeskChevHidden")
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('input[name="adv_charming"]')

    states = page.evaluate("""() => {
        const adv = document.querySelector('[data-testid="adv-chevron-charming"]');
        const skill = document.querySelector('[data-testid="skill-chevron-bragging"]');
        return {
            adv_display: adv ? getComputedStyle(adv).display : null,
            skill_display: skill ? getComputedStyle(skill).display : null,
        };
    }""")
    assert states["adv_display"] == "none", (
        f"advantage chevron should be hidden on desktop, got {states['adv_display']!r}"
    )
    assert states["skill_display"] == "none", (
        f"skill chevron should be hidden on desktop, got {states['skill_display']!r}"
    )
