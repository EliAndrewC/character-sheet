"""E2E: Advanced tracking — per-adventure counters, toggles, reset, boundary conditions."""

from tests.e2e.helpers import select_school, click_plus, apply_changes, start_new_character
import pytest

pytestmark = pytest.mark.tracking

def _create_character_with_lucky(page, live_server_url):
    """Create and apply a character with the Lucky advantage."""

    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Lucky Character")
    select_school(page, "akodo_bushi")
    page.check('input[name="adv_lucky"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Initial character creation")


def test_serious_wounds_increment_decrement(page, live_server_url):
    """Serious wounds + and - work correctly."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    sw_row = page.locator('text="Serious Wounds"').locator('..')
    plus = sw_row.locator('button', has_text="+")
    minus = sw_row.locator('button', has_text="-")

    plus.click()
    plus.click()
    page.wait_for_timeout(500)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "2"

    minus.click()
    page.wait_for_timeout(500)
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "1"


def test_serious_wounds_persist(page, live_server_url):
    """Serious wounds persist across reload."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    sw_row = page.locator('text="Serious Wounds"').locator('..')
    sw_row.locator('button', has_text="+").click()
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector('text="Serious Wounds"')
    assert page.locator('[x-text="seriousWounds"]').text_content().strip() == "1"


def test_void_points_persist(page, live_server_url):
    """Void points persist across reload."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    # VP starts at 2 (full). Decrement to 1, reload, verify persistence.
    vp_row = page.locator('text="Void Points"').locator('..')
    vp_row.locator('button', has_text="-").click()
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector('text="Void Points"')
    assert page.locator('[x-text="voidPoints"]').text_content().strip() == "1"


def test_void_points_max_enforced(page, live_server_url):
    """Void points + button disabled at max (lowest ring)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    vp_row = page.locator('text="Void Points"').locator('..')
    plus = vp_row.locator('button', has_text="+")
    # Default rings: Air=2, Fire=2, Earth=2, Water=3, Void=2 -> max = 2
    # VP starts at max, so + should already be disabled
    page.wait_for_timeout(300)
    assert plus.is_disabled()


def test_wound_minus_disabled_at_zero(page, live_server_url):
    """Wound - button disabled when at 0."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")

    light_minus = page.locator('[data-action="lw-minus"]')
    assert light_minus.is_disabled()
    serious_minus = page.locator('text="Serious Wounds"').locator('..').locator('button', has_text="-")
    assert serious_minus.is_disabled()


def test_lucky_toggle_works(page, live_server_url):
    """Lucky toggle shows 'unused' and can be marked as used."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    assert "unused" in section.text_content()
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)
    assert "used" in section.text_content()
    section.locator('button:text("Undo")').wait_for(state="visible", timeout=5000)
    assert section.locator('button:text("Undo")').is_visible()


def test_lucky_toggle_persists(page, live_server_url):
    """Lucky toggle state persists across reload."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)
    page.reload()
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Undo")').wait_for(state="visible", timeout=5000)
    assert section.locator('button:text("Undo")').is_visible()


def test_reset_per_adventure(page, live_server_url):
    """Reset button resets all per-adventure abilities."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')

    # Use the lucky toggle
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)

    # Reset - opens modal, then confirm
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    page.locator('[data-action="confirm-reset"]').click()
    page.wait_for_timeout(500)

    # Should be back to unused
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    assert "unused" in section.text_content()


def _create_togashi_3rd_dan(page, live_server_url, precepts=2):
    """Togashi Ise Zumi 3rd Dan with a per-day athletics raise pool of 4*precepts."""
    from tests.e2e.helpers import select_school, click_plus, apply_changes
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Togashi3D Tracker")
    select_school(page, "togashi_ise_zumi")
    # Boost school knacks to rank 3 (Dan 3)
    for knack in ("athletics", "conviction", "dragon_tattoo"):
        for _ in range(2):
            click_plus(page, f"knack_{knack}", 1)
    if precepts > 0:
        click_plus(page, "skill_precepts", precepts)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Togashi 3D setup")


def test_togashi_3rd_dan_daily_raises_tracker_row(page, live_server_url):
    """Togashi 3rd Dan sheet shows 'Daily Athletics Raises' tracker with 4*precepts pool."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=2)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    row = page.locator('text="Daily Athletics Raises"').locator('..')
    assert "8 / 8" in row.text_content()


def test_per_day_ability_has_its_own_reset_button_with_tooltip(page, live_server_url):
    """Conviction and Daily Athletics Raises each have a 'Reset' button labelled as per-day."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    # Conviction is also per-day
    conviction_btn = page.locator('[data-action="reset-ability-conviction"]')
    assert conviction_btn.count() == 1
    assert conviction_btn.get_attribute("title") == "This pool resets each day"
    # Togashi daily athletics raises
    raises_btn = page.locator('[data-action="reset-ability-togashi_daily_athletics_raises"]')
    assert raises_btn.count() == 1
    assert raises_btn.get_attribute("title") == "This pool resets each day"


def test_per_day_reset_button_renders_left_of_counter(page, live_server_url):
    """The Reset button on a per-day counter is rendered to the LEFT of the
    +/- counter widget, not the right - it should appear before the
    decrement (-) button in DOM order, and its left edge should be left of
    the decrement button's left edge."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    # Use the conviction row for the layout assertion. Anchor on the
    # data-action button (uniquely scoped to this row) instead of a text
    # locator - "Conviction" also appears in the XP breakdown panel and
    # school knacks panel, which would resolve to multiple matches.
    reset_btn = page.locator('[data-action="reset-ability-conviction"]')
    counter_group = reset_btn.locator('..')
    row = counter_group.locator('..')
    minus = counter_group.locator('button', has_text="-").first
    plus = counter_group.locator('button', has_text="+").first
    reset_box = reset_btn.bounding_box()
    minus_box = minus.bounding_box()
    plus_box = plus.bounding_box()
    assert reset_box and minus_box and plus_box
    # The reset button must sit to the left of BOTH +/- buttons.
    assert reset_box["x"] < minus_box["x"], (
        f"Reset button at x={reset_box['x']} should be left of "
        f"decrement button at x={minus_box['x']}"
    )
    assert reset_box["x"] < plus_box["x"]
    # Sanity: row context still contains the counter
    assert "Conviction" in row.text_content()


def test_per_day_reset_button_disabled_until_spent(page, live_server_url):
    """The per-day reset button is disabled when nothing has been spent."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    btn = page.locator('[data-action="reset-ability-togashi_daily_athletics_raises"]')
    assert btn.is_disabled()


def test_per_day_reset_button_restores_pool(page, live_server_url):
    """Clicking the per-day reset button on a counter restores its full pool."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    # Spend 2 raises by manipulating the tracking bridge directly
    page.evaluate("window._trackingBridge.setCount('togashi_daily_athletics_raises', 2)")
    page.wait_for_timeout(300)
    row = page.locator('text="Daily Athletics Raises"').locator('..')
    assert "2 / 4" in row.text_content()
    # Click the dedicated Reset button
    page.locator('[data-action="reset-ability-togashi_daily_athletics_raises"]').click()
    page.wait_for_timeout(300)
    assert "4 / 4" in row.text_content()


def test_per_day_reset_leaves_other_counters_alone(page, live_server_url):
    """Resetting one per-day ability does not touch other per-adventure counters."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    # Spend 1 raise and 1 conviction
    page.evaluate("window._trackingBridge.setCount('togashi_daily_athletics_raises', 1)")
    page.evaluate("window._trackingBridge.setCount('conviction', 1)")
    page.wait_for_timeout(300)
    # Reset only athletics raises
    page.locator('[data-action="reset-ability-togashi_daily_athletics_raises"]').click()
    page.wait_for_timeout(300)
    conviction_used = page.evaluate("window._trackingBridge.getCount('conviction')")
    raises_used = page.evaluate("window._trackingBridge.getCount('togashi_daily_athletics_raises')")
    assert conviction_used == 1
    assert raises_used == 0


def test_per_adventure_reset_also_clears_per_day_pools(page, live_server_url):
    """The global per-adventure reset still clears conviction and daily athletics raises."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    page.evaluate("window._trackingBridge.setCount('togashi_daily_athletics_raises', 2)")
    page.evaluate("window._trackingBridge.setCount('conviction', 1)")
    page.wait_for_timeout(300)
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    page.locator('[data-action="confirm-reset"]').click()
    page.wait_for_timeout(400)
    assert page.evaluate("window._trackingBridge.getCount('togashi_daily_athletics_raises')") == 0
    assert page.evaluate("window._trackingBridge.getCount('conviction')") == 0


def test_per_adventure_reset_also_clears_action_dice(page, live_server_url):
    """Action dice from a prior combat round are stale state; the global
    per-adventure reset wipes them along with the per-adventure counters."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    # Seed action dice directly via the tracking bridge and consume one
    # counter so the Reset button becomes enabled.
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 4, spent: false},
            {value: 7, spent: true, spent_by: 'Attack'}
        ];
        window._trackingBridge.setCount('conviction', 1);
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    assert page.evaluate("window._trackingBridge.actionDice.length") == 2
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    # Summary mentions the action dice being cleared.
    body = page.text_content('body')
    assert "2 action dice" in body
    page.locator('[data-action="confirm-reset"]').click()
    page.wait_for_timeout(400)
    assert page.evaluate("window._trackingBridge.actionDice.length") == 0
    assert page.evaluate("window._trackingBridge.getCount('conviction')") == 0


def test_reset_button_enabled_with_only_action_dice(page, live_server_url):
    """If the only stale state is action dice (no counters spent, no
    toggles set), the global Reset button must still be clickable so the
    user can wipe the dice through the usual confirm modal."""
    _create_togashi_3rd_dan(page, live_server_url, precepts=1)
    page.wait_for_selector('text="Daily Athletics Raises"', timeout=10000)
    page.evaluate("""
        window._trackingBridge.actionDice = [{value: 3, spent: false}];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    btn = page.locator('[data-action="open-reset-modal"]')
    assert not btn.is_disabled()
    btn.click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    page.locator('[data-action="confirm-reset"]').click()
    page.wait_for_timeout(400)
    assert page.evaluate("window._trackingBridge.actionDice.length") == 0


def test_non_per_day_counter_has_no_reset_button(page, live_server_url):
    """Otherworldliness (not per_day) should not render a per-ability reset button."""
    # Brotherhood of Shinsei Monk has otherworldliness as a school knack
    from tests.e2e.helpers import select_school, click_plus, apply_changes
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Shinsei OW")
    select_school(page, "brotherhood_of_shinsei_monk")
    for knack in ("conviction", "otherworldliness", "worldliness"):
        for _ in range(2):
            click_plus(page, f"knack_{knack}", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Shinsei setup")
    page.wait_for_selector('text="Otherworldliness"', timeout=10000)
    assert page.locator('[data-action="reset-ability-otherworldliness"]').count() == 0
    assert page.locator('[data-action="reset-ability-worldliness"]').count() == 0
    # Conviction should still have one (per-day)
    assert page.locator('[data-action="reset-ability-conviction"]').count() == 1


def test_reset_modal_lists_abilities_to_restore(page, live_server_url):
    """The reset modal lists which specific abilities will be restored."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    # Use lucky
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(500)
    # Open reset modal
    page.locator('[data-action="open-reset-modal"]').click()
    page.wait_for_selector('[data-action="confirm-reset"]', state='visible', timeout=10000)
    # The modal should list "Regain Lucky (re-roll)"
    body = page.text_content("body")
    assert "Regain" in body
    assert "Lucky" in body
    # Close without resetting
    page.keyboard.press("Escape")


# ===========================================================================
# Night's Rest
# ===========================================================================


def _create_basic_akodo(page, live_server_url, *, name="Restful"):
    """Create + apply a minimal Akodo character so non-editor tests can see
    the published sheet, and the editor has a working tracking section.
    NB: a bare Akodo has no per-adventure abilities, so the Reset button is
    NOT rendered - but the Night's Rest button always is (for editors)."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Setup")
    page.wait_for_selector(
        '[data-action="open-nights-rest-modal"]', timeout=10000,
    )


def test_nights_rest_button_renders_next_to_reset(page, live_server_url):
    """When a per-adventure ability exists, both buttons render and the
    Night's Rest button sits to the right of the Reset button."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('[data-action="open-reset-modal"]', timeout=10000)
    reset_btn = page.locator('[data-action="open-reset-modal"]')
    nr_btn = page.locator('[data-action="open-nights-rest-modal"]')
    assert nr_btn.count() == 1
    assert nr_btn.is_visible()
    reset_box = reset_btn.bounding_box()
    nr_box = nr_btn.bounding_box()
    assert reset_box and nr_box
    assert nr_box["x"] > reset_box["x"]


def test_nights_rest_button_renders_without_per_adventure(page, live_server_url):
    """A vanilla character with no per-adventure abilities still gets the
    Night's Rest button - it always has something to do (LW/VP/SW/etc)."""
    _create_basic_akodo(page, live_server_url)
    assert page.locator('[data-action="open-reset-modal"]').count() == 0
    assert page.locator('[data-action="open-nights-rest-modal"]').is_visible()


def test_nights_rest_button_hidden_for_non_editor(
    page, page_nonadmin, live_server_url
):
    """A non-editor visiting a published sheet must not see the button."""
    _create_basic_akodo(page, live_server_url, name="Public NR")
    sheet_url = page.url
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector('text="Tracking"', timeout=10000)
    assert page_nonadmin.locator(
        '[data-action="open-nights-rest-modal"]'
    ).count() == 0


def test_nights_rest_nothing_modal_when_no_changes(page, live_server_url):
    """Fresh character: no LW, full VP, nothing to clear -> Nothing modal."""
    _create_basic_akodo(page, live_server_url)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector(
        '[data-action="close-nights-rest-nothing"]',
        state='visible', timeout=5000,
    )
    body = page.text_content("body")
    assert "nothing to restore" in body.lower()
    # Confirm modal should NOT be open
    assert not page.locator('[data-action="confirm-nights-rest"]').is_visible()


def test_nights_rest_confirm_modal_lists_effects(page, live_server_url):
    """Take some LW + spend a VP, modal lists both effects."""
    _create_basic_akodo(page, live_server_url)
    # Bring LW to 4 and VP to 1 via the tracking bridge
    page.evaluate("""
        window._trackingBridge.lightWounds = 4;
        window._trackingBridge.voidPoints = 1;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector(
        '[data-action="confirm-nights-rest"]',
        state='visible', timeout=5000,
    )
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Heal 4 light wounds" in body
    assert "Restore 1 void point" in body


def test_nights_rest_confirm_applies_heal_lw_and_vp(page, live_server_url):
    """Clicking Confirm zeroes LW and regenerates 1 VP for a non-Ishi."""
    _create_basic_akodo(page, live_server_url)
    page.evaluate("""
        window._trackingBridge.lightWounds = 5;
        window._trackingBridge.voidPoints = 0;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    page.locator('[data-action="confirm-nights-rest"]').click()
    # The frontend reloads on success; wait for tracking to remount.
    page.wait_for_selector('text="Tracking"', timeout=10000)
    page.wait_for_function(
        "window._trackingBridge && window._trackingBridge.lightWounds === 0",
        timeout=10000,
    )
    assert page.evaluate("window._trackingBridge.voidPoints") == 1


def test_nights_rest_cancel_leaves_state_unchanged(page, live_server_url):
    """Cancel button closes modal without persisting any changes."""
    _create_basic_akodo(page, live_server_url)
    page.evaluate("""
        window._trackingBridge.lightWounds = 3;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="cancel-nights-rest"]', timeout=5000)
    page.locator('[data-action="cancel-nights-rest"]').click()
    page.wait_for_timeout(300)
    assert page.evaluate("window._trackingBridge.lightWounds") == 3


def test_nights_rest_accelerate_visible_only_with_sw_remaining(
    page, live_server_url,
):
    """Accelerate checkbox only renders when SW will remain after heal."""
    _create_basic_akodo(page, live_server_url)
    # SW=3, fresh injury -> heals 1, leaves 2; checkbox should appear.
    page.evaluate("""
        window._trackingBridge.seriousWounds = 3;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    page.locator('[data-action="nights-rest-accelerate"]').wait_for(state="visible", timeout=5000)
    assert page.locator('[data-action="nights-rest-accelerate"]').is_visible()
    page.locator('[data-action="cancel-nights-rest"]').click()
    page.wait_for_timeout(200)
    # SW=1 -> heals 1, leaves 0; checkbox should NOT appear.
    page.evaluate("""
        window._trackingBridge.seriousWounds = 1;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    assert not page.locator('[data-action="nights-rest-accelerate"]').is_visible()


def test_nights_rest_accelerate_updates_heal_count_in_place(
    page, live_server_url,
):
    """Toggling the accelerate checkbox rewrites the displayed SW heal
    count from the alt_effects diff, without re-fetching."""
    _create_basic_akodo(page, live_server_url)
    page.evaluate("""
        window._trackingBridge.seriousWounds = 3;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body_before = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Heal 1 serious wound" in body_before
    page.locator('[data-action="nights-rest-accelerate"]').check()
    page.wait_for_timeout(150)
    body_after = page.text_content('[data-testid="nights-rest-effects"]')
    # Accelerate flips QH/normal first-night 1 -> 0 (the bonus follows the base).
    assert "Heal 0 serious wounds" in body_after


def test_nights_rest_isawa_ishi_lists_lowest_ring_vp(page, live_server_url):
    """Ishi VP regen = lowest ring; modal should reflect that amount."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Ishi NR")
    select_school(page, "isawa_ishi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Ishi setup")
    # Default rings on Isawa Ishi: lowest ring is 2 -> regen 2.
    # Spend VP all the way down so the modal definitely shows the bullet.
    page.evaluate("""
        window._trackingBridge.voidPoints = 0;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Restore 2 void points" in body


def test_nights_rest_refreshes_absorb_void_only_for_ishi(
    page, live_server_url,
):
    """Ishi: Absorb Void is per-day, so a use shows up as 'Refresh Absorb Void'.
    Kitsune Warden: Absorb Void is per-adventure and should NOT appear."""
    # Ishi case
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Ishi AV")
    select_school(page, "isawa_ishi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Ishi setup")
    page.wait_for_selector('text="Absorb Void"', timeout=10000)
    # Spend a VP and use Absorb Void to set absorb_void_used=1
    page.evaluate("""
        window._trackingBridge.voidPoints = 0;
        window._trackingBridge.setCount('absorb_void', 1);
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Absorb Void" in body
    page.locator('[data-action="cancel-nights-rest"]').click()


def test_nights_rest_does_NOT_refresh_absorb_void_for_kitsune(
    page, live_server_url,
):
    """Kitsune Warden gets Absorb Void as per-adventure, NOT per-day."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Kitsune AV")
    select_school(page, "kitsune_warden")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Kitsune setup")
    page.wait_for_selector('text="Absorb Void"', timeout=10000)
    page.evaluate("""
        window._trackingBridge.voidPoints = 0;
        window._trackingBridge.setCount('absorb_void', 1);
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    # There WILL be a confirm modal (VP regen needed) - but Absorb Void
    # must NOT appear in the bullet list.
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Absorb Void" not in body


def test_nights_rest_does_not_clear_lucky_toggle(page, live_server_url):
    """Lucky is per-adventure; Night's Rest must leave it 'used'."""
    _create_character_with_lucky(page, live_server_url)
    page.wait_for_selector('text="Lucky (re-roll)"')
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    section.locator('button:text("Mark as used")').click()
    page.wait_for_timeout(300)
    # Also bring LW > 0 so the rest actually does something visible.
    page.evaluate("""
        window._trackingBridge.lightWounds = 2;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    page.locator('[data-action="confirm-nights-rest"]').click()
    page.wait_for_selector('text="Tracking"', timeout=10000)
    page.wait_for_function(
        "window._trackingBridge && window._trackingBridge.lightWounds === 0",
        timeout=10000,
    )
    # Lucky should STILL be marked used.
    section = page.locator('text="Lucky (re-roll)"').locator('..')
    assert "used" in section.text_content()
    assert section.locator('button:text("Undo")').is_visible()


def test_nights_rest_clears_action_dice(page, live_server_url):
    """Leftover action dice are stale combat-in-progress state; cleared."""
    _create_basic_akodo(page, live_server_url)
    page.evaluate("""
        window._trackingBridge.actionDice = [
            {value: 4, spent: false},
            {value: 7, spent: false},
        ];
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(200)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "2 initiative dice" in body
    page.locator('[data-action="confirm-nights-rest"]').click()
    page.wait_for_selector('text="Tracking"', timeout=10000)
    page.wait_for_function(
        "window._trackingBridge && window._trackingBridge.actionDice.length === 0",
        timeout=10000,
    )


def test_nights_rest_quick_healer_heals_2_on_first_night(page, live_server_url):
    """Quick Healer + first night after injury = 2 SW healed."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "QH NR")
    select_school(page, "akodo_bushi")
    page.check('input[name="adv_quick_healer"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "QH setup")
    # Take 3 SW - this triggers /track to set received_new + became_injured
    page.evaluate("""
        window._trackingBridge.seriousWounds = 3;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(300)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Heal 2 serious wounds" in body
    page.locator('[data-action="confirm-nights-rest"]').click()
    page.wait_for_selector('text="Tracking"', timeout=10000)
    page.wait_for_function(
        "window._trackingBridge && window._trackingBridge.seriousWounds === 1",
        timeout=10000,
    )


def test_nights_rest_slow_healer_heals_0_on_first_night(page, live_server_url):
    """Slow Healer suppresses the first night's heal after becoming injured."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "SH NR")
    select_school(page, "akodo_bushi")
    page.check('input[name="dis_slow_healer"]')
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "SH setup")
    page.evaluate("""
        window._trackingBridge.seriousWounds = 3;
        window._trackingBridge.save();
    """)
    page.wait_for_timeout(300)
    page.locator('[data-action="open-nights-rest-modal"]').click()
    page.wait_for_selector('[data-action="confirm-nights-rest"]', timeout=5000)
    body = page.text_content('[data-testid="nights-rest-effects"]')
    assert "Heal 0 serious wounds" in body
    page.locator('[data-action="confirm-nights-rest"]').click()
    page.wait_for_selector('text="Tracking"', timeout=10000)
    # SW stays at 3 since SH suppressed
    page.wait_for_function(
        "window._trackingBridge && window._trackingBridge.seriousWounds === 3",
        timeout=10000,
    )
