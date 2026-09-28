"""E2E: two writers on one character's tracking state.

A sheet tab posts its whole tracking state on every change. Before the
tracking revision existed, a tab that had not seen a change made elsewhere
wrote its stale copy back over it - a void point spent in another tab (or
from a Discord roll command) silently came back. Now the stale save is
refused and the tab recovers on screen, without a reload.
"""

import re
import time

import pytest

from tests.e2e.helpers import apply_changes, select_school, start_new_character

pytestmark = pytest.mark.tracking

NOTICE = '[data-testid="tracking-stale-notice"]'


def _new_sheet(page, live_server_url):
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', "Two Tabs")
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Test")
    page.wait_for_selector('text="Void Points"')
    return int(re.search(r"/characters/(\d+)", page.url).group(1))


def _row_button(page, label, sign):
    return page.locator(f'text="{label}"').locator('..').locator(
        'button', has_text=sign)


def _shown(page, field):
    return page.locator(f'[x-text="{field}"]').first.text_content().strip()


def _spend_void_elsewhere(page):
    """A second tab on the same sheet spends a void point."""
    other = page.context.new_page()
    other.goto(page.url)
    other.wait_for_selector('text="Void Points"')
    with other.expect_response(lambda r: r.url.endswith("/track/op")) as saved:
        _row_button(other, "Void Points", "-").click()
    assert saved.value.status == 200
    other.close()


def _stale_blob_save(page):
    """A whole-state save built on this tab's (stale) copy - what the flows
    not yet moved to operations still send (server-rolls-design 4.2)."""
    with page.expect_response(lambda r: r.url.endswith("/track")) as resp:
        page.evaluate("() => { const t = window._trackingBridge; t.seriousWounds += 1; t.save(); }")
    return resp.value


def test_an_operation_from_a_tab_that_missed_a_change_still_lands(page, live_server_url):
    """Tracking buttons are operations now: a tab that has not seen another
    tab's change does not lose its click, and catches up in the same reply."""
    _new_sheet(page, live_server_url)
    _spend_void_elsewhere(page)
    assert _shown(page, "voidPoints") == "2"   # not reloaded yet
    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    with page.expect_response(lambda r: r.url.endswith("/track/op")) as op:
        _row_button(page, "Serious Wounds", "+").click()
    assert op.value.status == 200
    page.wait_for_function("() => window._trackingBridge.voidPoints === 1")
    assert _shown(page, "seriousWounds") == "1"
    assert not page.locator(NOTICE).is_visible()
    assert navigations == []


def test_stale_save_is_refused_and_the_tab_recovers_without_reload(
    page, live_server_url,
):
    _new_sheet(page, live_server_url)
    _spend_void_elsewhere(page)
    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    assert _stale_blob_save(page).status == 409
    page.wait_for_selector(NOTICE, state="visible")
    # Adopted the other tab's spend instead of refunding it ...
    assert _shown(page, "voidPoints") == "1"
    # ... and says plainly that its own change did not land.
    assert _shown(page, "seriousWounds") == "0"
    assert "not applied" in page.locator(NOTICE).text_content()
    assert navigations == [], "the tab must recover without reloading"


def test_after_recovering_the_tab_can_save_again(page, live_server_url):
    _new_sheet(page, live_server_url)
    _spend_void_elsewhere(page)
    _stale_blob_save(page)
    page.wait_for_selector(NOTICE, state="visible")
    with page.expect_response(lambda r: r.url.endswith("/track/op")) as saved:
        _row_button(page, "Serious Wounds", "+").click()
    assert saved.value.status == 200
    page.reload()
    page.wait_for_selector('text="Void Points"')
    assert _shown(page, "seriousWounds") == "1"
    assert _shown(page, "voidPoints") == "1"      # the other tab's spend survived


def test_stale_notice_can_be_dismissed(page, live_server_url):
    _new_sheet(page, live_server_url)
    _spend_void_elsewhere(page)
    _stale_blob_save(page)
    page.wait_for_selector(NOTICE, state="visible")
    page.locator(NOTICE).locator("button").click()
    page.wait_for_selector(NOTICE, state="hidden")


def test_rapid_clicks_all_persist(page, live_server_url):
    """Operations queue in order: a burst of clicks against a slow server
    all land (a save requested mid-flight used to be DROPPED)."""
    _new_sheet(page, live_server_url)
    def slow(route):
        time.sleep(0.3)
        route.continue_()

    page.route("**/track/op", slow)
    plus = _row_button(page, "Serious Wounds", "+")
    plus.click()
    plus.click()
    plus.click()
    page.wait_for_function("() => window._trackingBridge.seriousWounds === 3", timeout=10000)
    page.unroute("**/track/op")
    page.reload()
    page.wait_for_selector('text="Serious Wounds"')
    assert _shown(page, "seriousWounds") == "3"
    assert not page.locator(NOTICE).is_visible()


def test_stale_notice_fits_a_phone_screen(page, live_server_url):
    _new_sheet(page, live_server_url)
    page.set_viewport_size({"width": 375, "height": 700})
    _spend_void_elsewhere(page)
    _stale_blob_save(page)
    page.wait_for_selector(NOTICE, state="visible")
    box = page.locator(NOTICE).bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0
