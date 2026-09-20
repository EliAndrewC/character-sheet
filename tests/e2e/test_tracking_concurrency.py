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
    """A second tab on the same sheet spends a void point and saves."""
    other = page.context.new_page()
    other.goto(page.url)
    other.wait_for_selector('text="Void Points"')
    with other.expect_response(lambda r: r.url.endswith("/track")) as saved:
        _row_button(other, "Void Points", "-").click()
    assert saved.value.status == 200
    other.close()


def test_stale_save_is_refused_and_the_tab_recovers_without_reload(
    page, live_server_url,
):
    _new_sheet(page, live_server_url)
    assert _shown(page, "voidPoints") == "2"
    assert not page.locator(NOTICE).is_visible()

    _spend_void_elsewhere(page)
    # This tab has not reloaded: it still believes void is 2.
    assert _shown(page, "voidPoints") == "2"

    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    with page.expect_response(lambda r: r.url.endswith("/track")) as refused:
        _row_button(page, "Serious Wounds", "+").click()
    assert refused.value.status == 409

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
    with page.expect_response(lambda r: r.url.endswith("/track")):
        _row_button(page, "Serious Wounds", "+").click()
    page.wait_for_selector(NOTICE, state="visible")

    with page.expect_response(lambda r: r.url.endswith("/track")) as saved:
        _row_button(page, "Serious Wounds", "+").click()
    assert saved.value.status == 200

    page.reload()
    page.wait_for_selector('text="Void Points"')
    assert _shown(page, "seriousWounds") == "1"
    assert _shown(page, "voidPoints") == "1"      # the other tab's spend survived


def test_stale_notice_can_be_dismissed(page, live_server_url):
    _new_sheet(page, live_server_url)
    _spend_void_elsewhere(page)
    _row_button(page, "Serious Wounds", "+").click()
    page.wait_for_selector(NOTICE, state="visible")
    page.locator(NOTICE).locator("button").click()
    page.wait_for_selector(NOTICE, state="hidden")


def test_rapid_clicks_all_persist(page, live_server_url):
    """A save requested while another was in flight used to be DROPPED, so
    the last click of a burst never reached the server."""
    _new_sheet(page, live_server_url)
    # Hold every /track response back briefly so the clicks genuinely overlap
    # an in-flight save, as they do against a cold Fly machine.
    def slow(route):
        time.sleep(0.3)
        route.continue_()

    page.route("**/track", slow)
    plus = _row_button(page, "Serious Wounds", "+")
    plus.click()
    plus.click()
    plus.click()
    assert _shown(page, "seriousWounds") == "3"
    page.wait_for_timeout(2000)
    page.unroute("**/track")

    page.reload()
    page.wait_for_selector('text="Serious Wounds"')
    assert _shown(page, "seriousWounds") == "3"
    assert not page.locator(NOTICE).is_visible()


def test_stale_notice_fits_a_phone_screen(page, live_server_url):
    _new_sheet(page, live_server_url)
    page.set_viewport_size({"width": 375, "height": 700})
    _spend_void_elsewhere(page)
    _row_button(page, "Serious Wounds", "+").click()
    page.wait_for_selector(NOTICE, state="visible")
    box = page.locator(NOTICE).bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0
