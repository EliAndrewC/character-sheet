"""E2E: rolls the SERVER makes for the sheet (server-rolls-design Phase 1)."""

import json

import pytest

from tests.e2e.test_rolls import _create_roller, _wait_for_roll_result

pytestmark = [pytest.mark.server_rolls]


def _roller_data(page):
    return page.evaluate("""() => {
        for (const el of document.querySelectorAll('[x-data]')) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.phase !== undefined && d.finalDice !== undefined) {
                return {phase: d.phase, dice: d.finalDice.map(x => x.value).sort((a, b) => a - b),
                        total: d.baseTotal, historyId: d._rollHistoryId};
            }
        }
        return null;
    }""")


def test_the_dice_shown_are_the_servers(page, live_server_url):
    _create_roller(page, live_server_url, "ServerDice")
    answers = []
    page.on("response", lambda r: answers.append(r) if r.url.endswith("/roll") else None)
    page.locator('[data-roll-key="skill:bragging"]').click()
    _wait_for_roll_result(page)
    assert answers, "the roll went to the server"
    body = answers[0].json()
    shown = _roller_data(page)
    assert shown["dice"] == sorted(d["value"] for d in body["dice"])
    assert shown["total"] == body["total"]
    # The server recorded the roll; the tab adopted that row.
    assert shown["historyId"] == body["history_id"] and body["history_id"]


def test_a_failed_roll_offers_retry_with_the_same_request(page, live_server_url):
    _create_roller(page, live_server_url, "RetryRoll")
    seen = []

    def handler(route):
        seen.append(json.loads(route.request.post_data))
        if len(seen) == 1:
            route.abort()
        else:
            route.continue_()
    page.route("**/roll", handler)
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.locator('[data-testid="roll-retry"]').wait_for(state="visible", timeout=5000)
    assert "Could not reach the server" in page.locator('[data-testid="roll-error"]').text_content()
    page.locator('[data-testid="roll-retry"]').click()
    _wait_for_roll_result(page)
    assert len(seen) == 2 and seen[0]["request_id"] == seen[1]["request_id"]
    assert len(seen[0]["request_id"]) == 32


def test_a_non_editor_rolls_on_the_server_without_changing_anything(page, page_nonadmin, live_server_url):
    _create_roller(page, live_server_url, "SimRoll")
    url = page.url
    page_nonadmin.goto(url)
    answers = []
    page_nonadmin.on("response", lambda r: answers.append(r) if r.url.endswith("/roll") else None)
    page_nonadmin.locator('[data-roll-key="skill:bragging"]').click()
    _wait_for_roll_result(page_nonadmin)
    body = answers[0].json()
    assert body["mode"] == "simulate" and body["history_id"] is None
