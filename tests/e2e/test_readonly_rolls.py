"""E2E: Read-only roll mode (Phase 1).

Phase 1 builds the infrastructure - the banner partial is wired into
every roll-result panel on the sheet, but no roll interactions are
un-gated yet. So the Phase 1 clicktest is a structural assertion:

- An admin editor sees no banner anywhere in the DOM.
- A logged-in non-editor AND an anonymous viewer both get the banner
  partial rendered multiple times (once per roll-result panel), hidden
  by its enclosing x-show until a roll triggers it.
- The anon variant carries the login link with return_to pointing back
  at the sheet.

Roll-interaction tests land in later phases (Phase 2+).
"""

import pytest

from tests.e2e.helpers import create_and_apply

pytestmark = [pytest.mark.readonly_rolls]


def _published_sheet_url(page, live_server_url):
    """Create a published character as the admin and return its sheet URL."""
    url = create_and_apply(
        page, live_server_url,
        name="Readonly Mode Test",
        school="akodo_bushi",
        summary="Initial character creation",
    )
    # create_and_apply lands on the sheet view already
    return url


def test_editor_sees_no_banner_anywhere(page, live_server_url):
    """The admin/owner never renders the banner - partial emits nothing."""
    sheet_url = _published_sheet_url(page, live_server_url)
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    banners = page.locator('[data-testid="readonly-roll-banner"]')
    assert banners.count() == 0


def test_anon_sees_banner_hidden_in_dom(page, page_anon, live_server_url):
    """Anonymous visitor: banner is in the DOM (multiple copies, one per
    roll-result panel) and every copy is hidden until a result modal
    opens."""
    sheet_url = _published_sheet_url(page, live_server_url)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")
    banners = page_anon.locator('[data-testid="readonly-roll-banner"]')
    assert banners.count() > 0, "expected at least one banner copy in the DOM"
    # Every copy is inside an x-show/x-cloak'd result panel, so none is
    # visible on page load.
    for i in range(banners.count()):
        assert not banners.nth(i).is_visible()


def test_anon_banner_carries_login_link(page, page_anon, live_server_url):
    """The anon banner includes a return_to-aware login link."""
    sheet_url = _published_sheet_url(page, live_server_url)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")
    banners = page_anon.locator('[data-testid="readonly-roll-banner"]')
    banner_html = banners.first.evaluate("el => el.innerHTML")
    path = sheet_url.split(live_server_url, 1)[1]
    assert f"/auth/login?return_to={path}" in banner_html
    assert "not logged in" in banner_html


def test_non_editor_sees_banner_hidden_in_dom(page, page_nonadmin, live_server_url):
    """Logged-in non-editor gets the banner too, with the no-edit copy."""
    sheet_url = _published_sheet_url(page, live_server_url)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    banners = page_nonadmin.locator('[data-testid="readonly-roll-banner"]')
    assert banners.count() > 0
    # Non-editor copy differs from anon copy: it explicitly says "don't have
    # edit access" and does not contain a login link inside the banner
    # itself. (The login URL still lives in the Alpine state object for
    # the anon case, so we scope the link check to the banner element.)
    banner_html = banners.first.evaluate("el => el.innerHTML")
    assert "don't have edit access" in banner_html
    assert "/auth/login" not in banner_html


# ---------------------------------------------------------------------------
# Phase 2: action dice
#
# The roll buttons themselves (Roll Initiative, per-die Mark as spent, etc.)
# were already click-reachable on the public sheet template, but several
# `{% if viewer_can_edit %}` gates hid the Clear button, the per-die menu,
# and (for characters with no per_adventure items) the whole right column.
# These tests assert the un-gated flow + that the Phase 1 save shim stops
# the /track POST, so nothing persists for a viewer.
# ---------------------------------------------------------------------------


def _disable_dice_animations(page):
    """Mirror conftest's `page` fixture: kill dice animations client-side.

    page_anon and page_nonadmin don't install this by default, which can
    make roll tests flaky. Call before navigating to the sheet."""
    page.add_init_script("""
        window.__testDisableAnimations = true;
        const _origInterval = setInterval(() => {
            if (window._diceRoller) {
                window._diceRoller.prefs.dice_animation_enabled = false;
                window._diceRoller.prefs.dice_sound_enabled = false;
                clearInterval(_origInterval);
            }
        }, 50);
        document.addEventListener('alpine:initialized', () => {
            if (window._diceRoller) {
                window._diceRoller.prefs.dice_animation_enabled = false;
                window._diceRoller.prefs.dice_sound_enabled = false;
            }
        });
    """)


def _roll_initiative_and_close_modal(p):
    """Click the Initiative row, wait for the roll to complete, close the
    dice modal so the action-dice panel is exposed underneath."""
    p.locator('[data-roll-key="initiative"]').click()
    p.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const data = window.Alpine && window.Alpine.$data(el);
            if (data && data.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)
    p.locator('[data-modal="dice-roller"] button:has-text("×")').click()
    p.wait_for_timeout(150)


def test_anon_init_roll_does_not_change_action_dice_display(
    page, page_anon, live_server_url
):
    """A non-editor's initiative roll does NOT add action dice to the
    sheet's action-dice-section. Whatever the editor's persisted dice
    state was, that's what the section shows - the non-editor's roll
    can't make dice appear or disappear from the displayed sheet.

    This test covers the empty-baseline case: editor never rolled
    initiative, server has actionDice=[]. The non-editor rolls
    initiative, sees the modal animate, closes it; the action-dice
    section remains hidden because actionDice is still []."""
    sheet_url = _published_sheet_url(page, live_server_url)

    _disable_dice_animations(page_anon)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")

    assert page_anon.evaluate("window._trackingBridge.actionDice.length") == 0
    section = page_anon.locator('[data-testid="action-dice-section"]')
    assert not section.is_visible()

    _roll_initiative_and_close_modal(page_anon)

    # The roll modal played and closed, but the bridge actionDice and
    # the action-dice-section are unchanged.
    assert page_anon.evaluate("window._trackingBridge.actionDice.length") == 0
    assert not section.is_visible()


def test_anon_init_roll_preserves_editor_action_dice(
    page, page_anon, live_server_url
):
    """Covers the seeded-baseline case: an editor previously rolled
    initiative so the server has persisted action dice. A non-editor
    visiting the sheet sees those dice. If they roll initiative
    themselves, the dice the editor rolled stay exactly where they
    were - the non-editor's roll can't replace or clear them."""
    sheet_url = _published_sheet_url(page, live_server_url)

    # Editor rolls initiative so the server has a non-empty actionDice.
    _disable_dice_animations(page)
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    _roll_initiative_and_close_modal(page)
    seeded_dice = page.evaluate("window._trackingBridge.actionDice")
    assert len(seeded_dice) > 0

    # Non-editor sees those dice.
    _disable_dice_animations(page_anon)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")
    pre_roll_dice = page_anon.evaluate("window._trackingBridge.actionDice")
    assert len(pre_roll_dice) == len(seeded_dice)
    section = page_anon.locator('[data-testid="action-dice-section"]')
    assert section.is_visible()

    # Non-editor rolls initiative themselves. The modal opens and
    # animates, but the bridge's actionDice array does not change -
    # the editor's seeded dice remain visible on the sheet.
    _roll_initiative_and_close_modal(page_anon)

    post_roll_dice = page_anon.evaluate("window._trackingBridge.actionDice")
    # Same dice (same values, same length) as before the non-editor roll.
    assert len(post_roll_dice) == len(seeded_dice)
    for before, after in zip(seeded_dice, post_roll_dice):
        assert before["value"] == after["value"]
        assert bool(before.get("spent")) == bool(after.get("spent"))
    assert section.is_visible()


# ---------------------------------------------------------------------------
# Phase 3: void points (regular + temp)
# ---------------------------------------------------------------------------


def _published_with_vp(page, live_server_url, *, temp_vp=0):
    """Like _published_sheet_url but also seeds current_void_points=max and
    (optionally) current_temp_void_points via the admin's own save shim.
    Returns (sheet_url, starting_vp)."""
    url = _published_sheet_url(page, live_server_url)
    # Baseline voidPoints at voidMax (2 for the default character). If temp_vp
    # is set, persist that too. Uses the admin's save path so the numbers
    # are in the DB when the non-editor loads the sheet.
    page.evaluate(
        "async (tempVp) => {"
        "  const t = window._trackingBridge;"
        "  t.voidPoints = t.voidMax;"
        "  t.tempVoidPoints = tempVp;"
        "  await t.save();"
        "}",
        temp_vp,
    )
    page.wait_for_timeout(200)
    starting_vp = page.evaluate("window._trackingBridge.voidPoints")
    return url, starting_vp


def test_non_editor_spends_vp_on_attack_does_not_change_vp(
    page, page_nonadmin, live_server_url
):
    """Non-editor selects 2 VP on an attack roll. The roll executes
    with the +10 (5 per VP) reflected in the result, but the sheet's
    displayed voidPoints count stays anchored to the persisted value
    throughout. Banner is visible during the modal."""
    sheet_url, starting_vp = _published_with_vp(page, live_server_url)
    assert starting_vp >= 2, "default akodo_bushi should start with 2 VP"

    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.voidPoints") == starting_vp

    page_nonadmin.locator('[data-roll-key="attack"]').click()
    page_nonadmin.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page_nonadmin.locator('[data-modal="attack"]')
    banner = modal.locator('[data-testid="readonly-roll-banner"]')
    assert banner.first.is_visible()

    # Select 2 VP via the pre-roll +/- control.
    plus = modal.locator('button:text-is("+")').first
    plus.click()
    plus.click()
    page_nonadmin.wait_for_timeout(100)
    assert page_nonadmin.evaluate(
        "window.Alpine.$data(document.querySelector('[data-modal=\"attack\"]')).atkVoidSelected"
    ) == 2

    # Roll the attack. The attack-roll computation should reflect the
    # 2 VP spend (each adds +5 to the roll total).
    modal.locator('[data-action="roll-attack"]').click()
    page_nonadmin.wait_for_function("""() => {
        const el = document.querySelector('[data-modal="attack"]');
        const data = el && window.Alpine && window.Alpine.$data(el);
        return data && data.atkPhase === 'result';
    }""", timeout=10000)

    # The bridge's voidPoints did NOT decrement - non-editors get the
    # roll-effect simulation but never the cost.
    assert page_nonadmin.evaluate("window._trackingBridge.voidPoints") == starting_vp
    assert banner.first.is_visible()

    # Refresh confirms the persisted value also stayed put.
    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.voidPoints") == starting_vp


# ---------------------------------------------------------------------------
# Phase 4: wound checks + wounds
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 5: per-adventure consumables
# ---------------------------------------------------------------------------


def _publish_with_advantage(page, live_server_url, adv_id, name="PerAdventureChar"):
    """Create + publish an akodo_bushi with a single base advantage
    enabled. Returns the sheet URL."""
    from tests.e2e.helpers import start_new_character, select_school, apply_changes
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.check(f'input[name="adv_{adv_id}"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial")
    return page.url


def test_non_editor_lucky_mark_used_button_hidden(
    page, page_nonadmin, live_server_url
):
    """The Lucky 'Mark as used' / 'Undo' toggle buttons in the
    per-adventure panel are pure bookkeeping - clicking them only
    flips local Alpine state because the save shim swallows the
    POST. So per Principle 6, they are not rendered for non-editors.
    The state label ('Lucky: unused') stays visible so viewers can
    still SEE whether it's been used."""
    sheet_url = _publish_with_advantage(
        page, live_server_url, "lucky", name="LuckyReader"
    )
    # Editor regression: button IS rendered for the owner.
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    assert page.locator(
        '[data-action="toggle-lucky_used-on"]'
    ).count() == 1

    # Non-editor: button is gone, state label still there.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.locator(
        '[data-action="toggle-lucky_used-on"]'
    ).count() == 0
    assert page_nonadmin.locator(
        '[data-action="toggle-lucky_used-off"]'
    ).count() == 0
    # Status label still rendered for read-only visibility of the
    # current state.
    assert page_nonadmin.locator(
        'text="Lucky (re-roll): unused"'
    ).count() == 1


def _publish_with_knacks(page, live_server_url, *, name, school, knack_overrides):
    """Create + publish a character with custom knack ranks. Returns
    the sheet URL. Mirrors test_school_abilities._create_char but
    finishes by returning the post-apply sheet URL."""
    from tests.e2e.helpers import (
        start_new_character, select_school, click_plus, apply_changes,
    )
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    for knack, rank in knack_overrides.items():
        for _ in range(rank - 1):
            click_plus(page, f"knack_{knack}", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial")
    return page.url


def test_non_editor_per_adventure_counter_buttons_hidden(
    page, page_nonadmin, live_server_url
):
    """Per-adventure counter abilities render +/- buttons (and a
    Reset button for per-day pools) that go through setCount/
    resetAbility -> save(). For non-editors those POSTs are swallowed,
    so the buttons are bookkeeping-only and Principle 6 says hide
    them. The 'X / Y' remaining count stays visible.

    Uses ``courtier`` school - its school_knacks include
    ``worldliness`` which becomes a counter-type per-adventure ability
    at the default rank-1 starting point, no XP-spending required."""
    sheet_url = _publish_with_knacks(
        page, live_server_url,
        name="WorldlinessNonEditor", school="courtier",
        knack_overrides={"worldliness": 1},
    )

    # Editor regression: the counter +/- buttons render for the owner.
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    section = page.locator(
        'h3:has-text("Per-Adventure Abilities")'
    ).locator('..')
    assert section.locator('button:has-text("+")').count() >= 1
    assert section.locator('button:has-text("-")').count() >= 1

    # Non-editor: count text still rendered, buttons gone.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    section_n = page_nonadmin.locator(
        'h3:has-text("Per-Adventure Abilities")'
    ).locator('..')
    # State display still there ("Worldliness: 1 / 1").
    assert section_n.locator('text=Worldliness').count() >= 1
    # No mutation buttons within the per-adventure section.
    assert section_n.locator('button:has-text("+")').count() == 0
    assert section_n.locator('button:has-text("-")').count() == 0
    assert section_n.locator(
        '[data-action^="reset-ability-"]'
    ).count() == 0


def test_non_editor_banked_bonus_mark_spent_button_hidden(
    page, page_nonadmin, live_server_url
):
    """School-specific banked-bonus UIs (Akodo 3rd Dan attack bonus,
    Bayushi/Hiruma/Hida/Isawa-Shinjo/Matsu equivalents) all render a
    Mark-spent / Clear button gated by the same Jinja
    viewer_can_edit gate. Pick the Akodo path as representative -
    Akodo Bushi at 3rd Dan grants akodo_wc_attack_bonus; the inner
    'Mark spent' button must not appear in the source for a
    non-editor.

    The block itself is x-show'd until akodoBankedBonuses is
    non-empty, so the visibility check is on the rendered HTML
    (server-side gate), not on element visibility."""
    sheet_url = _publish_with_knacks(
        page, live_server_url,
        name="AkodoThirdDanReader", school="akodo_bushi",
        knack_overrides={
            "double_attack": 3, "feint": 3, "iaijutsu": 3,
        },
    )

    # Editor regression: the Akodo banked-bonus block renders the
    # 'Mark spent' button source even though the parent is x-show
    # hidden until a bonus banks.
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    assert "Mark spent" in page.content(), (
        "editor on 3rd Dan akodo should see the banked-bonus button "
        "in the rendered HTML"
    )

    # Non-editor on the same character: the wrap removes the button
    # entirely from the rendered HTML.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert "Mark spent" not in page_nonadmin.content(), (
        "non-editor must not receive the banked-bonus 'Mark spent' "
        "button in the page source"
    )


def test_non_editor_mantis_posture_section_hidden_with_no_history(
    page, page_nonadmin, live_server_url
):
    """Mantis Wave-Treader's Posture tracker section is empty wedge
    for a non-editor when no posture has been declared yet (buttons
    are gated, current line is x-show'd off, accumulator likewise).
    Suppress the entire section in that case so the sheet doesn't
    show a 'Posture' header floating above whitespace. Editors still
    see it so they can pick a posture."""
    sheet_url = _publish_with_knacks(
        page, live_server_url,
        name="MantisNoHist", school="mantis_wave_treader",
        knack_overrides={},
    )
    # Editor regression: tracker rendered.
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    assert page.locator(
        '[data-testid="mantis-posture-tracker"]'
    ).count() == 1

    # Non-editor: no posture data on the server, so section is
    # absent from the DOM entirely.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.locator(
        '[data-testid="mantis-posture-tracker"]'
    ).count() == 0


def test_non_editor_mantis_posture_section_shown_with_history(
    page, page_nonadmin, live_server_url
):
    """Once a posture has been recorded server-side (editor clicked
    a posture button, persisted via /track), the section renders
    for non-editors so they can read the live state. The buttons
    stay hidden but the current posture line, bonuses, and
    accumulator are visible."""
    sheet_url = _publish_with_knacks(
        page, live_server_url,
        name="MantisWithHist", school="mantis_wave_treader",
        knack_overrides={},
    )
    # Editor picks an offensive posture so server adventure_state
    # gets non-empty mantis_posture_history.
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    page.locator('[data-action="mantis-posture-offensive"]').click()
    page.wait_for_function(
        "() => window._trackingBridge.posturePhase === 2"
    )

    # Non-editor reload: section is back, current posture visible,
    # buttons still hidden.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.locator(
        '[data-testid="mantis-posture-tracker"]'
    ).count() == 1
    current = page_nonadmin.locator(
        '[data-testid="mantis-current-posture"]'
    )
    assert current.is_visible()
    text = current.text_content()
    assert "Phase 1" in text
    assert "offensive" in text.lower()
    # Buttons remain editor-only even when the section is shown.
    assert page_nonadmin.locator(
        '[data-action="mantis-posture-offensive"]'
    ).count() == 0
    assert page_nonadmin.locator(
        '[data-action="mantis-posture-defensive"]'
    ).count() == 0


# Note: per-adventure counter abilities (adventure_raises, conviction,
# otherworldliness, worldliness, togashi_daily_athletics_raises) and
# the toggle path (lucky_used, unlucky_used) all sit inside the same
# templated per_adventure loop in sheet.html; the visibility gate
# wraps the buttons in the loop body, so the Lucky-toggle and
# courtier-counter tests above cover both paths structurally. The
# Akodo banked-bonus test covers the school-specific banked-bonus
# pattern; Bayushi / Hiruma / Hida / Isawa-Shinjo / Matsu use the
# identical Jinja gate, so they are transitively covered without
# requiring a dedicated high-Dan character per school.


def test_reset_per_adventure_button_hidden_for_non_editor(
    page, page_nonadmin, live_server_url
):
    """The bulk Reset Per-Adventure Abilities button stays editor-only
    per Principle 6: it isn't a roll and shimming it would no-op.
    The per-ability Reset buttons on per-day counters are hidden by
    the same gate (covered by the per-adventure-counter test above)."""
    sheet_url = _publish_with_advantage(
        page, live_server_url, "lucky", name="ResetHideCheck"
    )
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.locator(
        '[data-action="open-reset-modal"]'
    ).count() == 0


# ---------------------------------------------------------------------------
# Phase 7: gaming-group interactions (cross-character)
# ---------------------------------------------------------------------------


def _publish_with_group(page, name, school, group_label="Tuesday Group", knacks=None, skills=None):
    """Create + apply a character via the admin page, then set the
    gaming group via the edit page's dropdown. Returns the sheet URL."""
    from tests.e2e.helpers import (
        start_new_character, select_school, click_plus, apply_changes,
    )
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, school)
    for k, rank in (knacks or {}).items():
        click_plus(page, f"knack_{k}", rank - 1)
    for s, rank in (skills or {}).items():
        click_plus(page, f"skill_{s}", rank)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, f"Setup {name}")
    sheet_url = page.url
    page.goto(sheet_url + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label=group_label)
    page.wait_for_timeout(500)
    return sheet_url


def test_non_editor_ally_conviction_no_persist(
    page, page_nonadmin, live_server_url
):
    """Phase 7: a non-editor viewer of an ally character spends the
    party priest's 5th Dan conviction on an attack. Local Alpine state
    reflects the spend; the save shim short-circuits the
    /ally-conviction POST; after a refresh the priest's conviction_used
    is still 0.

    Setup: a Dan 5 priest + an akodo_bushi ally, both in Tuesday Group.
    The non-editor (test_user_1) owns neither character. The banner in
    the attack modal makes the read-only state obvious."""
    page.goto(live_server_url)
    priest_url = _publish_with_group(
        page, name="Phase7 Priest", school="priest",
        knacks={"conviction": 5, "otherworldliness": 5, "pontificate": 5},
    )
    page.goto(live_server_url)
    ally_url = _publish_with_group(
        page, name="Phase7 Ally", school="akodo_bushi",
    )
    # Set VP to 0 on the ally so the roll doesn't open a void-spend menu.
    page.goto(ally_url)
    page.evaluate(
        "async () => { const t = window._trackingBridge;"
        "  t.voidPoints = 0; await t.save(); }"
    )
    page.wait_for_timeout(200)

    # Non-editor loads the ally's sheet and exercises the attack flow.
    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(ally_url)
    page_nonadmin.wait_for_selector("h1")

    # The priest-conviction-allies JSON must surface the priest for the
    # ally-conviction UI to appear in roll modals. Under a heavy full
    # suite the live-server DB may carry stale Dan-5 priests in the
    # same group from earlier tests, so find our priest by name
    # rather than taking index 0.
    allies_json = page_nonadmin.evaluate(
        "() => JSON.parse(document.getElementById('priest-conviction-allies').textContent)"
    )
    ours = [a for a in allies_json if a["name"] == "Phase7 Priest"]
    assert ours, f"expected 'Phase7 Priest' in priest-conviction-allies, got {allies_json}"
    priest_id = ours[0]["priest_id"]

    # Open the attack modal, force TN=5 so the hit block renders
    # reliably (the priest-ally spend UI lives inside the HIT branch),
    # and roll.
    page_nonadmin.locator('[data-roll-key="attack"]').click()
    page_nonadmin.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)
    modal = page_nonadmin.locator('[data-modal="attack"]')
    # Banner visible inside attack modal.
    assert modal.locator('[data-testid="readonly-roll-banner"]').first.is_visible()
    page_nonadmin.evaluate(
        "() => {"
        "  const el = document.querySelector('[data-modal=\"attack\"]');"
        "  window.Alpine.$data(el).atkTN = 5;"
        "}"
    )
    modal.locator('[data-action="roll-attack"]').click()
    page_nonadmin.wait_for_function("""() => {
        const el = document.querySelector('[data-modal="attack"]');
        const data = el && window.Alpine && window.Alpine.$data(el);
        return data && data.atkPhase === 'result';
    }""", timeout=10000)
    assert page_nonadmin.evaluate(
        "() => window.Alpine.$data(document.querySelector('[data-modal=\"attack\"]')).atkHit"
    ), "attack should hit with TN=5"

    # Click "Spend Conviction (+1)" for the priest ally.
    spend_btn = modal.locator(f'[data-action="spend-priest-ally-atk-{priest_id}"]')
    assert spend_btn.is_visible()
    spend_btn.click()
    page_nonadmin.wait_for_timeout(300)

    # Local state: this-roll spent counter is 1, ally pool "used" bumps.
    spent = page_nonadmin.evaluate(
        f"() => window._diceRoller.priestAllySpent({priest_id})"
    )
    assert spent == 1

    # Refresh server state via admin: priest.conviction_used stayed 0.
    page.goto(priest_url)
    page.wait_for_selector("h1")
    page.wait_for_function(
        "() => window._trackingBridge",
        timeout=10000,
    )
    priest_conviction_used = page.evaluate(
        "() => window._trackingBridge.getCount('conviction')"
    )
    assert priest_conviction_used == 0


# ---------------------------------------------------------------------------
# Phase 6: priest precepts pool (own priest)
# ---------------------------------------------------------------------------


def _create_priest_3rd_dan(page, live_server_url, name="PriestNonEditor", precepts=2):
    """Build a priest character with Dan=3 (all three school knacks at
    rank 3) and a precepts skill rank. Returns the sheet URL."""
    from tests.e2e.helpers import (
        start_new_character, select_school, click_plus, apply_changes,
    )
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "priest")
    for knack in ("conviction", "otherworldliness", "pontificate"):
        click_plus(page, f"knack_{knack}", 2)  # rank 1 -> 3
    click_plus(page, "skill_precepts", precepts)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Priest setup")
    return page.url


def test_non_editor_generates_priest_pool_no_persist(
    page, page_nonadmin, live_server_url
):
    """Non-editor priest-viewer clicks Generate dice pool: pool populates
    locally (Alpine state), but the /track POST is shimmed so refresh
    restores an empty pool. Representative for the Phase 6 un-gating.

    The in-modal pool-die swap UI (precepts_pool_block macro) was never
    Jinja-gated; its self-swap path calls t.save() which is the same
    shim, so it is transitively covered."""
    sheet_url = _create_priest_3rd_dan(
        page, live_server_url, name="PoolGenReader", precepts=2
    )
    # Admin's pool starts empty (we didn't roll it). Confirm.
    assert page.evaluate("window._trackingBridge.preceptsPool.length") == 0

    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    page_nonadmin.wait_for_function(
        "() => window._trackingBridge && Array.isArray(window._trackingBridge.preceptsPool)",
        timeout=10000,
    )
    assert page_nonadmin.evaluate("window._trackingBridge.preceptsPool.length") == 0

    # Generate dice pool button is un-gated and visible.
    gen = page_nonadmin.locator('[data-action="roll-precepts-pool"]')
    assert gen.is_visible()
    gen.click()
    # Pool populates to precepts-skill-many dice. The roll animation
    # pipeline runs locally and t.save() is shimmed for non-editors.
    page_nonadmin.wait_for_function(
        "() => window._trackingBridge.preceptsPool.length === 2",
        timeout=15000,
    )
    # Dice render.
    assert page_nonadmin.locator('[data-testid="precepts-pool-die"]').count() == 2

    # Refresh: nothing persisted, pool is empty again.
    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    page_nonadmin.wait_for_function(
        "() => window._trackingBridge && Array.isArray(window._trackingBridge.preceptsPool)",
        timeout=10000,
    )
    assert page_nonadmin.evaluate("window._trackingBridge.preceptsPool.length") == 0


def _seed_light_wounds(page, live_server_url, light_wounds):
    """Admin path: create a published character, add light_wounds via the
    LW plus modal's 'Set total' input, dismiss the auto-opened WC modal,
    and return the sheet URL."""
    url = _published_sheet_url(page, live_server_url)
    page.goto(url + "/edit")
    page.wait_for_selector('h1')
    # Edit page and sheet share the same trackingData. Drive the LW plus
    # modal from the view sheet so the state persists exactly like a
    # human user would set it.
    page.goto(url)
    page.wait_for_selector('h1')
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="New total"]', timeout=3000)
    page.locator('input[placeholder="New total"]').fill(str(light_wounds))
    page.locator('button:text-is("Set")').last.click()
    page.wait_for_timeout(300)
    # The Set action auto-opens the WC modal. Close it so the non-editor
    # loads a clean sheet.
    wc_modal = page.locator('[data-modal="wound-check"]')
    if wc_modal.count() > 0 and wc_modal.is_visible():
        wc_modal.locator('button', has_text="×").first.click()
        page.wait_for_timeout(150)
    return url


def test_non_editor_rolls_wc_does_not_change_displayed_counts(
    page, page_nonadmin, live_server_url
):
    """Non-editor with LW>0 walks through a WC roll all the way to
    Take Serious. None of the displayed counters move - the sheet
    stays anchored to the persisted server values throughout the
    walk-through. The banner is visible during the modal."""
    sheet_url = _seed_light_wounds(page, live_server_url, light_wounds=1)
    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 1
    assert page_nonadmin.evaluate("window._trackingBridge.seriousWounds") == 0

    # Open the WC modal via the always-visible WC button.
    page_nonadmin.locator('[data-action="roll-wound-check"]').click()
    page_nonadmin.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=5000)
    modal = page_nonadmin.locator('[data-modal="wound-check"]')
    banner = modal.locator('[data-testid="readonly-roll-banner"]')
    assert banner.first.is_visible()

    # Roll. With LW=1 pass probability is essentially 1.
    page_nonadmin.locator('[data-action="roll-wound-check-go"]').click()
    page_nonadmin.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)
    assert "PASSED" in modal.text_content()

    # Click Take 1 Serious. For an editor this would mutate
    # lightWounds and seriousWounds locally; for a non-editor it
    # must close the modal without touching either.
    modal.locator('button:text("Take 1 Serious Wound")').click()
    page_nonadmin.wait_for_timeout(300)
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 1
    assert page_nonadmin.evaluate("window._trackingBridge.seriousWounds") == 0

    # Refresh: nothing persisted (defense in depth).
    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 1
    assert page_nonadmin.evaluate("window._trackingBridge.seriousWounds") == 0


def test_non_editor_lw_plus_does_not_change_displayed_lw(
    page, page_nonadmin, live_server_url
):
    """Non-editor on a 0-LW character clicks LW + and enters '43'.
    The LW + modal opens, accepts the input, and dispatches the WC
    modal which then runs against TN=43. Throughout, the sheet's
    displayed lightWounds stays anchored at 0."""
    sheet_url = _published_sheet_url(page, live_server_url)
    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 0

    page_nonadmin.locator('[data-action="lw-plus"]').click()
    page_nonadmin.wait_for_selector('input[placeholder="Amount"]', timeout=3000)
    page_nonadmin.locator('input[placeholder="Amount"]').fill("43")
    page_nonadmin.locator('input[placeholder="Amount"]').locator('..').locator(
        'button', has_text="Add"
    ).click()
    # Sheet's displayed counter must not have moved.
    page_nonadmin.wait_for_timeout(150)
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 0

    # The WC modal opens with the entered amount as the TN to beat.
    page_nonadmin.wait_for_selector(
        '[data-modal="wound-check"]', state='visible', timeout=5000,
    )
    modal = page_nonadmin.locator('[data-modal="wound-check"]')
    assert page_nonadmin.evaluate(
        "window._diceRoller.wcLightWounds"
    ) == 43

    # Banner is visible in the WC modal.
    assert modal.locator(
        '[data-testid="readonly-roll-banner"]'
    ).first.is_visible()


def test_non_editor_lw_minus_button_disabled(
    page, page_nonadmin, live_server_url
):
    """The LW - button stays in the DOM (so the layout doesn't shift
    when toggling viewer / editor) but is disabled for non-editors,
    even when LW > 0. Editors still see it enabled."""
    sheet_url = _seed_light_wounds(page, live_server_url, light_wounds=2)

    # Editor: button enabled (because LW > 0).
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    assert page.locator(
        '[data-action="lw-minus"]'
    ).is_enabled()

    # Non-editor: button rendered but disabled regardless of LW count.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    minus = page_nonadmin.locator('[data-action="lw-minus"]')
    assert minus.count() == 1
    assert minus.is_visible()
    assert not minus.is_enabled()


def test_non_editor_mirumoto_parry_does_not_grant_temp_vp(
    page, page_nonadmin, live_server_url
):
    """Mirumoto Bushi auto-grants 1 temp VP after every parry roll.
    For an editor that adds 1 to tempVoidPoints; for a non-editor
    we do the parry walk-through but skip the auto-grant - their
    temp VP count stays at the persisted value."""
    sheet_url = _publish_with_knacks(
        page, live_server_url,
        name="MirumotoNonEditor", school="mirumoto_bushi",
        knack_overrides={},
    )
    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    starting_temp = page_nonadmin.evaluate(
        "window._trackingBridge.tempVoidPoints"
    )

    # Parry uses a small menu - click "Roll Parry" inside it.
    page_nonadmin.locator('[data-roll-key="parry"]').click()
    page_nonadmin.wait_for_selector(
        '[data-parry-menu]', state='visible', timeout=5000,
    )
    page_nonadmin.locator(
        '[data-parry-menu] button:has-text("Roll Parry")'
    ).first.click()
    page_nonadmin.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)

    # Mirumoto's auto-grant must NOT have fired for the non-editor.
    assert page_nonadmin.evaluate(
        "window._trackingBridge.tempVoidPoints"
    ) == starting_temp


def test_non_editor_akodo_wc_vp_raise_does_not_change_vp(
    page, page_nonadmin, live_server_url
):
    """Akodo bushi's 4th Dan 'spend VP for free raise after seeing
    the wound check' is a post-roll VP spend in the WC modal. For a
    non-editor: the +5 still applies to wcRollTotal so the result
    reflects the spend, but bridge voidPoints stays at the
    persisted value."""
    # 4th Dan akodo so the post-roll VP free-raise is granted; seed
    # VP via the admin's save shim and LW via the LW + modal so the
    # WC modal has something to roll against.
    sheet_url = _publish_with_knacks(
        page, live_server_url,
        name="Akodo4thDanReader", school="akodo_bushi",
        knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4},
    )
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    page.evaluate(
        "async () => {"
        "  const t = window._trackingBridge;"
        "  t.voidPoints = t.voidMax;"
        "  await t.save();"
        "}"
    )
    page.wait_for_timeout(150)
    starting_vp = page.evaluate("window._trackingBridge.voidPoints")
    assert starting_vp >= 1, "expected non-zero VP after seeding"
    page.locator('[data-action="lw-plus"]').click()
    page.wait_for_selector('input[placeholder="New total"]', timeout=3000)
    page.locator('input[placeholder="New total"]').fill("20")
    page.locator('button:text-is("Set")').last.click()
    page.wait_for_timeout(300)
    wc_modal = page.locator('[data-modal="wound-check"]')
    if wc_modal.count() > 0 and wc_modal.is_visible():
        wc_modal.locator('button', has_text="×").first.click()
        page.wait_for_timeout(150)

    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate(
        "window._trackingBridge.voidPoints"
    ) == starting_vp

    # Roll the wound check.
    page_nonadmin.locator('[data-action="roll-wound-check"]').click()
    page_nonadmin.wait_for_selector(
        '[data-modal="wound-check"]', state='visible', timeout=5000,
    )
    page_nonadmin.locator('[data-action="roll-wound-check-go"]').click()
    page_nonadmin.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.wcPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)

    pre_spend_total = page_nonadmin.evaluate(
        "window._diceRoller.wcRollTotal"
    )

    # Click "Spend VP (+5)" in the post-roll discretionary panel.
    spend_btn = page_nonadmin.locator(
        '[data-modal="wound-check"] button:has-text("Spend VP (+5)")'
    ).first
    spend_btn.click()
    page_nonadmin.wait_for_timeout(150)

    # The roll total reflects the +5 (modal-local effect preserved).
    assert page_nonadmin.evaluate(
        "window._diceRoller.wcRollTotal"
    ) == pre_spend_total + 5

    # But the bridge's voidPoints did not move.
    assert page_nonadmin.evaluate(
        "window._trackingBridge.voidPoints"
    ) == starting_vp


def test_non_editor_sw_vp_temp_vp_buttons_hidden(
    page, page_nonadmin, live_server_url
):
    """Serious Wounds, Void Points, and Temp Void +/- buttons are
    bookkeeping for non-editors - clicking them would only flip
    local Alpine state since the save shim swallows the POST. Hide
    them. The label and current count still render so the viewer
    can read the state."""
    sheet_url, _ = _published_with_vp(page, live_server_url, temp_vp=3)

    # Match the leaf row (label + counter), not its ancestor section.
    row_selector = 'div.flex.items-center.justify-between.gap-4'

    # Editor regression: all six counter buttons render.
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    sw_row = page.locator(row_selector).filter(has_text="Serious Wounds").first
    assert sw_row.locator('button:text-is("-")').count() == 1
    assert sw_row.locator('button:text-is("+")').count() == 1
    vp_row = page.locator(row_selector).filter(has_text="Void Points").first
    assert vp_row.locator('button:text-is("-")').count() == 1
    assert vp_row.locator('button:text-is("+")').count() == 1
    tempvp_row = page.locator('[data-testid="temp-void-row"]')
    assert tempvp_row.locator('[data-action="temp-vp-minus"]').count() == 1
    assert tempvp_row.locator('[data-action="temp-vp-plus"]').count() == 1

    # Non-editor: every counter button gone, state labels still
    # rendered.
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    sw_row_n = page_nonadmin.locator(row_selector).filter(
        has_text="Serious Wounds"
    ).first
    assert sw_row_n.locator('button:text-is("-")').count() == 0
    assert sw_row_n.locator('button:text-is("+")').count() == 0
    vp_row_n = page_nonadmin.locator(row_selector).filter(
        has_text="Void Points"
    ).first
    assert vp_row_n.locator('button:text-is("-")').count() == 0
    assert vp_row_n.locator('button:text-is("+")').count() == 0
    tempvp_row_n = page_nonadmin.locator('[data-testid="temp-void-row"]')
    assert tempvp_row_n.locator('[data-action="temp-vp-minus"]').count() == 0
    assert tempvp_row_n.locator('[data-action="temp-vp-plus"]').count() == 0
    # Counts still visible.
    assert page_nonadmin.evaluate(
        "window._trackingBridge.tempVoidPoints"
    ) == 3


def test_anon_cannot_clear_seeded_action_dice(
    page, page_anon, live_server_url
):
    """Belt-and-braces companion to the init-roll preservation test:
    even the explicit Clear button on the action-dice section must
    not remove an editor's seeded dice when clicked by a non-editor."""
    sheet_url = _published_sheet_url(page, live_server_url)

    # Editor rolls initiative to seed action dice on the server.
    _disable_dice_animations(page)
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    _roll_initiative_and_close_modal(page)
    seeded_count = len(page.evaluate("window._trackingBridge.actionDice"))
    assert seeded_count > 0

    _disable_dice_animations(page_anon)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")
    section = page_anon.locator('[data-testid="action-dice-section"]')
    assert section.is_visible()

    # Non-editor clicks the Clear button.
    page_anon.locator('[data-action="clear-action-dice"]').click()
    page_anon.wait_for_timeout(150)

    # Bridge still has the editor's dice; section still visible.
    assert page_anon.evaluate(
        "window._trackingBridge.actionDice.length"
    ) == seeded_count
    assert section.is_visible()
