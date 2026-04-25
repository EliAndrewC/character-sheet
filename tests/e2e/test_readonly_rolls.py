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


def test_anon_rolls_initiative_no_persist(page, page_anon, live_server_url):
    """Anon rolls initiative: action dice appear locally, action-dice-section
    becomes visible, banner visible inside it, refresh clears everything."""
    sheet_url = _published_sheet_url(page, live_server_url)

    _disable_dice_animations(page_anon)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")

    # Before rolling: no action dice, action-dice-section hidden.
    assert page_anon.evaluate("window._trackingBridge.actionDice.length") == 0
    section = page_anon.locator('[data-testid="action-dice-section"]')
    assert not section.is_visible()

    _roll_initiative_and_close_modal(page_anon)

    # After rolling: dice present in Alpine state, section visible, and
    # its internal read-only banner is now visible too.
    assert page_anon.evaluate("window._trackingBridge.actionDice.length") > 0
    assert section.is_visible()
    section_banner = section.locator('[data-testid="readonly-roll-banner"]')
    assert section_banner.count() == 1
    assert section_banner.first.is_visible()

    # Refresh: server never received anything, so the reloaded sheet has
    # no action dice.
    page_anon.reload()
    page_anon.wait_for_selector("h1")
    assert page_anon.evaluate("window._trackingBridge.actionDice.length") == 0
    assert not page_anon.locator('[data-testid="action-dice-section"]').is_visible()


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


def test_non_editor_spends_vp_on_attack_no_persist(
    page, page_nonadmin, live_server_url
):
    """Non-editor spends 2 VP on an attack roll: VP decrements locally,
    banner is visible during the result, refresh restores the original VP.

    Plan calls this 'spend 2 VP on a skill roll'. Uses the attack modal
    because it has an explicit VP +/- selector that makes the spend
    easy to drive from Playwright."""
    sheet_url, starting_vp = _published_with_vp(page, live_server_url)
    assert starting_vp >= 2, "default akodo_bushi should start with 2 VP"

    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.voidPoints") == starting_vp

    # Open the attack modal.
    page_nonadmin.locator('[data-roll-key="attack"]').click()
    page_nonadmin.wait_for_selector('[data-modal="attack"]', state='visible', timeout=5000)

    # Banner must be visible inside the attack modal (Phase 2 placement).
    modal = page_nonadmin.locator('[data-modal="attack"]')
    banner = modal.locator('[data-testid="readonly-roll-banner"]')
    assert banner.count() == 1
    assert banner.first.is_visible()

    # Select 2 VP via the pre-roll +/- control.
    plus = modal.locator('button:text-is("+")').first
    plus.click()
    plus.click()
    page_nonadmin.wait_for_timeout(100)
    assert page_nonadmin.evaluate("window.Alpine.$data(document.querySelector('[data-modal=\"attack\"]')).atkVoidSelected") == 2

    # Roll the attack.
    modal.locator('[data-action="roll-attack"]').click()
    page_nonadmin.wait_for_function("""() => {
        const el = document.querySelector('[data-modal="attack"]');
        const data = el && window.Alpine && window.Alpine.$data(el);
        return data && data.atkPhase === 'result';
    }""", timeout=10000)

    # Locally, voidPoints decremented by 2.
    assert page_nonadmin.evaluate("window._trackingBridge.voidPoints") == starting_vp - 2
    # Banner still visible on the result.
    assert banner.first.is_visible()

    # Refresh: nothing persisted. VP back to starting value.
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


def test_non_editor_lucky_toggle_no_persist(
    page, page_nonadmin, live_server_url
):
    """Non-editor flips the Lucky 'Mark as used' toggle in the
    per-adventure panel. Local adventure_state.lucky_used becomes true;
    refresh has no effect server-side. Covers setToggle → save() which
    is the shim shared by all per-adventure toggle abilities (Lucky,
    Unlucky, Mantis 2nd Dan free-raise flag, etc.)."""
    sheet_url = _publish_with_advantage(
        page, live_server_url, "lucky", name="LuckyReader"
    )
    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate(
        "window._trackingBridge.getToggle('lucky_used')"
    ) is False

    btn = page_nonadmin.locator('[data-action="toggle-lucky_used-on"]')
    assert btn.is_visible()
    btn.click()
    page_nonadmin.wait_for_timeout(150)
    assert page_nonadmin.evaluate(
        "window._trackingBridge.getToggle('lucky_used')"
    ) is True

    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate(
        "window._trackingBridge.getToggle('lucky_used')"
    ) is False


# Note: per-adventure counter abilities (adventure_raises, conviction,
# otherworldliness, worldliness, togashi_daily_athletics_raises) all
# route through setCount -> save(). The toggle path (lucky_used,
# unlucky_used) routes through setToggle -> save(). Both hit the Phase
# 1 save shim identically, so the Lucky toggle test above is
# representative coverage for every per-adventure setToggle/setCount
# consumable.
#
# School-specific banked-bonus UIs (akodo_banked_bonuses,
# bayushi_banked_feint_raise, hiruma_banked_attack_bonus, etc.) render
# only when the character has the relevant school_ability (typically
# 3rd Dan+). They route through saveBankedBonuses() -> save() - the
# same shim - so they are transitively covered by the Lucky test
# without each requiring a dedicated high-rank character setup.


def test_reset_per_adventure_button_hidden_for_non_editor(
    page, page_nonadmin, live_server_url
):
    """The bulk Reset Per-Adventure Abilities button stays editor-only
    per Principle 6: it isn't a roll and shimming it would no-op. The
    per-ability Reset buttons (per_day counters) DO render for
    non-editors - those are useful for local bookkeeping."""
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


def test_non_editor_rolls_wc_takes_serious_no_persist(
    page, page_nonadmin, live_server_url
):
    """Non-editor with LW>0 opens the WC modal, rolls, picks Take 1
    Serious. LW→0, SW→1 locally. Banner visible inside WC modal.
    Refresh restores original LW and SW=0."""
    sheet_url = _seed_light_wounds(page, live_server_url, light_wounds=1)
    # Baseline server state (as seen by non-editor).
    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 1
    assert page_nonadmin.evaluate("window._trackingBridge.seriousWounds") == 0

    # Open the WC modal via the un-gated WC button.
    wc_btn = page_nonadmin.locator('[data-action="roll-wound-check"]')
    assert wc_btn.is_visible()
    wc_btn.click()
    page_nonadmin.wait_for_selector('[data-modal="wound-check"]', state='visible', timeout=5000)

    # Banner visible inside the WC modal (Phase 2 placement).
    modal = page_nonadmin.locator('[data-modal="wound-check"]')
    banner = modal.locator('[data-testid="readonly-roll-banner"]')
    assert banner.count() == 1
    assert banner.first.is_visible()

    # Trigger the roll. With LW=1 the pass probability is virtually 1.
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

    # Take 1 Serious Wound. Drives lwTakeSeriousAndReset via Alpine,
    # which calls this.save() — shimmed for non-editors.
    modal.locator('button:text("Take 1 Serious Wound")').click()
    page_nonadmin.wait_for_timeout(300)
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 0
    assert page_nonadmin.evaluate("window._trackingBridge.seriousWounds") == 1

    # Refresh: nothing persisted, original LW and SW.
    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.lightWounds") == 1
    assert page_nonadmin.evaluate("window._trackingBridge.seriousWounds") == 0


def test_non_editor_spends_temp_vp_no_persist(
    page, page_nonadmin, live_server_url
):
    """Non-editor decrements temp VP via the tracking panel's - button,
    refresh restores the seeded value.

    The tracking-panel +/- buttons were the specific Jinja gate un-gated
    in Phase 3. akodo_bushi (the default school used by
    _published_sheet_url) already has has_temp_void=True because it
    carries the feint knack; seed current_temp_void_points via the
    admin's save, then have the non-editor drive the - button."""
    sheet_url, _ = _published_with_vp(page, live_server_url, temp_vp=3)
    assert page.evaluate("window._trackingBridge.tempVoidPoints") == 3

    _disable_dice_animations(page_nonadmin)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.tempVoidPoints") == 3

    minus_btn = page_nonadmin.locator('[data-action="temp-vp-minus"]')
    minus_btn.click()
    minus_btn.click()
    page_nonadmin.wait_for_timeout(100)
    assert page_nonadmin.evaluate("window._trackingBridge.tempVoidPoints") == 1

    # Refresh: tempVoidPoints back to the seeded 3.
    page_nonadmin.reload()
    page_nonadmin.wait_for_selector("h1")
    assert page_nonadmin.evaluate("window._trackingBridge.tempVoidPoints") == 3


def test_anon_spends_action_die_no_persist(page, page_anon, live_server_url):
    """Anon rolls initiative → opens per-die menu → marks first die spent.
    Locally the die flips to spent; after refresh it is not spent (server
    state never heard about it)."""
    sheet_url = _published_sheet_url(page, live_server_url)

    _disable_dice_animations(page_anon)
    page_anon.goto(sheet_url)
    page_anon.wait_for_selector("h1")

    _roll_initiative_and_close_modal(page_anon)

    # Click the first die to open its per-die menu, then click "Mark as spent".
    first_die = page_anon.locator(
        '[data-testid="action-dice-section"] [data-action="action-die"]'
    ).first
    first_die.click()
    page_anon.locator('[data-action="action-die-spent"]').first.click()
    page_anon.wait_for_timeout(100)

    # Local Alpine state flipped.
    assert page_anon.evaluate("window._trackingBridge.actionDice[0].spent") is True

    # Refresh: nothing persisted, so there are no dice at all.
    page_anon.reload()
    page_anon.wait_for_selector("h1")
    assert page_anon.evaluate("window._trackingBridge.actionDice.length") == 0
