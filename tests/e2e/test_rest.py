"""E2E: Night's Rest records - the Roll History line for each rest, the
sheet's "Rest anyway", and the GM's Rest page (rest everyone / one)."""

import uuid

import pytest

from tests.e2e.helpers import create_and_apply, save_tracking

pytestmark = [pytest.mark.tracking, pytest.mark.groups]


def _rest_from_sheet(page, anyway=False):
    page.locator('[data-action="open-nights-rest-modal"]').click()
    btn = ('[data-action="confirm-nights-rest-anyway"]' if anyway
           else '[data-action="confirm-nights-rest"]')
    page.wait_for_selector(btn, state="visible", timeout=5000)
    with page.expect_navigation():
        page.locator(btn).click()
    page.wait_for_selector('[data-action="open-nights-rest-modal"]', timeout=10000)


def test_each_rest_is_a_roll_history_line(page, live_server_url):
    """A rest that heals and one that restores nothing ("Rest anyway") both
    show in the Roll History, with what changed in the tooltip."""
    sheet = create_and_apply(page, live_server_url, name="RestLog")
    page.goto(sheet)
    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    save_tracking(page, lightWounds=4)
    _rest_from_sheet(page)
    _rest_from_sheet(page, anyway=True)

    page.locator('[data-action="roll-history"]').click()
    page.wait_for_selector('[data-testid="roll-history-page"]')
    rows = page.locator('[data-rest-id]')
    assert rows.count() == 2
    assert page.locator('[data-testid="rh-counts"]').text_content().strip() \
        == "2 Night's Rests recorded"
    assert "no serious wounds healed" in rows.first.text_content()
    # No Hide button or note on a rest row; clicking it opens nothing.
    assert rows.first.locator('[data-action="hide-roll"]').count() == 0
    assert rows.first.locator('[data-action="annotation-input"]').count() == 0
    rows.nth(1).locator('[data-testid="rest-label"]').hover()
    explainer = rows.nth(1).locator('[data-testid="rest-explainer"]')
    assert "Heal 4 light wounds" in explainer.text_content()
    rows.first.locator('[data-testid="rest-label"]').hover()
    assert "Nothing needed restoring." in rows.first.locator(
        '[data-testid="rest-explainer"]').text_content()
    rows.first.locator('[data-testid="rest-result"]').click()
    page.wait_for_timeout(300)
    assert page.locator('[data-testid="readonly-roll-modal"]:visible').count() == 0


def _make_rest_group(page, live_server_url, names):
    gname = "Rest-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    sheets = {}
    for nm in names:
        sheets[nm] = create_and_apply(page, live_server_url, name=nm, school="akodo_bushi")
        page.goto(sheets[nm] + "/edit")
        page.wait_for_selector('select[name="gaming_group_id"]')
        page.locator('select[name="gaming_group_id"]').select_option(label=gname)
        page.wait_for_timeout(400)  # let setGroup() round-trip
    page.goto(live_server_url)
    page.locator('[data-testid="group-link"]', has_text=gname).first.click()
    page.wait_for_url("**/groups/**")
    page.locator('[data-testid="group-rest-link"]').click()
    page.wait_for_url("**/groups/**/rest")
    return sheets


def _card(page, name):
    return page.locator('[data-group-rest-card]', has_text=name)


def test_gm_rest_page_rests_one_then_everyone(page, live_server_url):
    sheets = _make_rest_group(page, live_server_url, ["RestOne", "RestTwo"])
    # Spend a void point on RestTwo so its card says what a rest would do.
    page.goto(sheets["RestTwo"])
    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    save_tracking(page, lightWounds=3)
    page.go_back()
    page.reload()
    page.wait_for_selector('[data-group-rest-card]')

    assert _card(page, "RestOne").locator('[data-testid="no-recent-rest"]').is_visible()
    assert "Heal 3 light wounds" in _card(page, "RestTwo").locator(
        '[data-testid="would-restore"]').text_content()

    page.once("dialog", lambda d: d.accept())
    two = _card(page, "RestTwo")
    two.locator('[data-testid="row-rest-btn"]').click()
    two.locator('[data-testid="row-rest-ok"]').wait_for(state="visible")
    assert two.locator('[data-testid="recent-rest"]').count() == 1
    assert "Nothing to restore" in two.locator('[data-testid="would-restore"]').text_content()
    assert _card(page, "RestOne").locator('[data-testid="recent-rest"]').count() == 0

    dialogs = []
    page.once("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.locator('[data-testid="mass-rest-btn"]').click()
    page.wait_for_selector('[data-testid="mass-rest-ok"]', state="visible")
    assert "all 2 characters" in dialogs[0]
    assert _card(page, "RestOne").locator('[data-testid="recent-rest"]').count() == 1
    assert _card(page, "RestTwo").locator('[data-testid="recent-rest"]').count() == 2

    # Rests applied from this page are in the character's Roll History.
    # (In this harness the GM created the PC, so it is an owner's rest and
    # carries no "[by ...]" badge; the unit tests cover the GM-not-owner flag.)
    page.goto(sheets["RestTwo"] + "/roll-history")
    page.wait_for_selector('[data-testid="roll-history-page"]')
    assert page.locator('[data-rest-id]').count() == 2


def test_rest_page_and_group_nav_fit_a_phone(page, live_server_url):
    """No horizontal overflow at 375px on the Rest page, with "Rest
    everyone" visible, nor on the Group Summary whose nav gained a link."""
    _make_rest_group(page, live_server_url, ["RestPhoneWithAFairlyLongName"])
    rest_url = page.url
    page.set_viewport_size({"width": 375, "height": 700})
    page.goto(rest_url)
    page.wait_for_selector('[data-group-rest-card]')
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert page.locator('[data-testid="mass-rest-btn"]').is_visible()
    page.goto(rest_url.rsplit("/rest", 1)[0])
    page.wait_for_load_state("networkidle")
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def _modal_picker(page):
    return page.locator('[data-testid="rest-date-picker"]:visible')


def test_sheet_rest_takes_an_in_game_night_and_next_night_follows_it(page, live_server_url):
    """Pick the 14th day of the 3rd month, rest; the next rest's dialog names
    it as the previous rest, and "Next night" picks the 15th."""
    sheet = create_and_apply(page, live_server_url, name="RestNight")
    page.goto(sheet)
    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    save_tracking(page, lightWounds=2)

    page.locator('[data-action="open-nights-rest-modal"]').click()
    picker = _modal_picker(page)
    picker.wait_for(state="visible", timeout=5000)
    assert "No Night's Rest recorded yet." in picker.locator(
        '[data-testid="rest-previous"]').text_content()
    assert picker.locator('[data-action="rest-next-night"]').is_disabled()
    assert picker.locator('[data-testid="rest-day"]').is_disabled()
    month = picker.locator('[data-testid="rest-month"]')
    assert 'Yayoi ("new life")' in month.locator('option[value="3"]').text_content()
    month.select_option("3")
    day = picker.locator('[data-testid="rest-day"]')
    assert day.locator('option[value="1"]').text_content() == '1 - Seimei ("clear and bright")'
    assert day.locator('option[value="2"]').text_content() == "2"
    day.select_option("14")
    with page.expect_navigation():
        page.locator('[data-action="confirm-nights-rest"]').click()

    # Nothing to restore now, so the second rest goes through "Rest anyway".
    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    page.locator('[data-action="open-nights-rest-modal"]').click()
    picker = _modal_picker(page)
    picker.wait_for(state="visible", timeout=5000)
    assert "Previous rest: 14th day of the 3rd month (Yayoi)" in picker.locator(
        '[data-testid="rest-previous"]').text_content()
    nxt = picker.locator('[data-action="rest-next-night"]')
    assert "15th day of the 3rd month" in nxt.text_content()
    nxt.click()
    assert picker.locator('[data-testid="rest-month"]').input_value() == "3"
    assert picker.locator('[data-testid="rest-day"]').input_value() == "15"
    with page.expect_navigation():
        page.locator('[data-action="confirm-nights-rest-anyway"]').click()

    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    page.locator('[data-action="roll-history"]').click()
    page.wait_for_selector('[data-testid="roll-history-page"]')
    nights = page.locator('[data-testid="rest-game-date"]')
    assert [nights.nth(i).text_content() for i in range(nights.count())] == [
        "15th day of the 3rd month (Yayoi)", "14th day of the 3rd month (Yayoi)"]


def test_sheet_rest_refuses_a_month_without_a_day(page, live_server_url):
    sheet = create_and_apply(page, live_server_url, name="RestHalfNight")
    page.goto(sheet)
    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    page.locator('[data-action="open-nights-rest-modal"]').click()
    picker = _modal_picker(page)
    picker.wait_for(state="visible", timeout=5000)
    picker.locator('[data-testid="rest-month"]').select_option("3")
    page.locator('[data-action="confirm-nights-rest-anyway"]').click()
    err = picker.locator('[data-testid="rest-date-error"]')
    err.wait_for(state="visible")
    assert "both a month and a day" in err.text_content()
    # Still open, nothing recorded.
    assert page.locator('[data-action="confirm-nights-rest-anyway"]').is_visible()


def test_gm_rest_page_dates_the_rest_and_offers_the_next_night(page, live_server_url):
    _make_rest_group(page, live_server_url, ["NightOne", "NightTwo"])
    picker = page.locator('[data-testid="rest-date-picker"]')
    assert "No Night's Rest recorded yet." in picker.locator(
        '[data-testid="rest-previous"]').text_content()
    picker.locator('[data-testid="rest-month"]').select_option("12")
    picker.locator('[data-testid="rest-day"]').select_option("30")

    dialogs = []
    page.once("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.locator('[data-testid="mass-rest-btn"]').click()
    page.wait_for_selector('[data-testid="mass-rest-ok"]', state="visible")
    assert "on the 30th day of the 12th month" in dialogs[0]
    for name in ("NightOne", "NightTwo"):
        assert "30th day of the 12th month (Shiwasu)" in _card(page, name).locator(
            '[data-testid="recent-rest-night"]').text_content()

    # The group's latest rest is now dated; "Next night" wraps to the new year
    # and dates a single card's rest too.
    assert "Latest rest in this group: 30th day of the 12th month" in picker.locator(
        '[data-testid="rest-previous"]').text_content()
    picker.locator('[data-action="rest-next-night"]').click()
    assert picker.locator('[data-testid="rest-month"]').input_value() == "1"
    assert picker.locator('[data-testid="rest-day"]').input_value() == "1"
    page.once("dialog", lambda d: d.accept())
    one = _card(page, "NightOne")
    one.locator('[data-testid="row-rest-btn"]').click()
    one.locator('[data-testid="row-rest-ok"]').wait_for(state="visible")
    assert "1st day of the 1st month (Mutsuki)" in one.locator(
        '[data-testid="recent-rest-night"]').first.text_content()


def test_rest_date_picker_fits_a_phone(page, live_server_url):
    """The day labels are long (the 3rd of the 3rd month is a sentence); the
    picker must not widen the sheet's dialog past a 375px screen."""
    sheet = create_and_apply(page, live_server_url, name="RestPhonePicker")
    page.set_viewport_size({"width": 375, "height": 700})
    page.goto(sheet)
    page.wait_for_selector('[data-action="open-nights-rest-modal"]')
    page.locator('[data-action="open-nights-rest-modal"]').click()
    picker = _modal_picker(page)
    picker.wait_for(state="visible", timeout=5000)
    picker.locator('[data-testid="rest-month"]').select_option("3")
    picker.locator('[data-testid="rest-day"]').select_option("3")
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    box = picker.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375
