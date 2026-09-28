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


def test_a_raise_on_a_server_roll_is_applied_by_the_server(page, live_server_url):
    """Phase 3: the raise shows at once, and the server applies it - the
    pool count and the recorded total both move."""
    from tests.e2e.test_rolls import _create_3rd_dan_courtier
    _create_3rd_dan_courtier(page, live_server_url, "ServerRaise")
    acts = []
    page.on("response", lambda r: acts.append(r) if r.url.endswith("/act") else None)
    page.locator('[data-roll-key="skill:manipulation"]').click()
    _wait_for_roll_result(page)
    before = _roller_data(page)["total"]
    page.locator('[data-action="spend-raise"]').click()
    page.wait_for_function("() => window._trackingBridge.getCount('adventure_raises') === 1", timeout=5000)
    assert _roller_data(page)["total"] == before + 5
    assert acts and acts[-1].json()["total"] == before + 5
    # The spend is the server's, so it survives a reload.
    page.reload()
    page.wait_for_function("() => window._trackingBridge.getCount('adventure_raises') === 1", timeout=5000)


# ---------------------------------------------------------------------------
# Rerolls (Phase 4)
# ---------------------------------------------------------------------------

def _acts(page):
    seen = []
    page.on("response", lambda r: seen.append(r) if r.url.endswith("/act") else None)
    return seen


def _done_after(page, seen, n):
    page.wait_for_function("() => window._diceRoller.phase === 'done'", timeout=10000)
    page.wait_for_timeout(100)
    assert len(seen) >= n
    return seen[-1].json()


def test_lucky_rerolls_on_the_server_and_the_sheet_shows_its_dice(page, live_server_url):
    from tests.e2e.dice_control import force_dice, restore_dice
    from tests.e2e.test_pcp import _create_roller as _pcp_roller, _roll_bragging
    _pcp_roller(page, live_server_url, "ServerLucky", advantages=("lucky",))
    seen = _acts(page)
    force_dice(page, [2])
    _roll_bragging(page)
    force_dice(page, [9])
    page.locator('[data-action="use-lucky"]').click()
    body = _done_after(page, seen, 1)
    restore_dice(page)
    shown = _roller_data(page)
    assert shown["dice"] == sorted(d["value"] for d in body["dice"]) and set(shown["dice"]) == {9}
    assert shown["total"] == body["total"]
    assert body["payload"]["lucky"]["kept"] == "reroll"
    assert page.locator('[data-testid="lucky-pair-banner"]:visible').is_visible()
    # The server spent Lucky: it stays spent after a reload.
    page.reload()
    page.wait_for_function("() => window._trackingBridge.getToggle('lucky_used') === true", timeout=5000)


def test_a_refused_reroll_says_so_and_changes_nothing(page, live_server_url):
    from tests.e2e.test_pcp import _create_roller as _pcp_roller, _roll_bragging
    _pcp_roller(page, live_server_url, "RefusedLucky", advantages=("lucky",))
    _roll_bragging(page)
    before = _roller_data(page)
    page.route("**/act", lambda route: route.fulfill(
        status=400, content_type="application/json", body=json.dumps({"error": "Not today."})))
    page.locator('[data-action="use-lucky"]').click()
    page.locator('[data-testid="reroll-error"]').wait_for(state="visible", timeout=5000)
    assert "Not today." in page.locator('[data-testid="reroll-error"]').text_content()
    after = _roller_data(page)
    assert after["dice"] == before["dice"] and after["total"] == before["total"]
    assert page.locator('[data-action="use-lucky"]').is_visible()  # still available


def test_togashi_4th_dan_reroll_is_one_server_roll(page, live_server_url):
    from tests.e2e.dice_control import force_dice, restore_dice
    from tests.e2e.test_school_abilities import _create_char, _roll_via_menu_or_direct
    _create_char(page, live_server_url, "ServerTogashi", "togashi_ise_zumi",
                 knack_overrides={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skill_overrides={"bragging": 1})
    seen = _acts(page)
    force_dice(page, [9])
    _roll_via_menu_or_direct(page, "skill:bragging")
    first = _roller_data(page)
    force_dice(page, [1])
    page.locator('[data-action="togashi-4th-reroll"]').click()
    body = _done_after(page, seen, 1)
    restore_dice(page)
    shown = _roller_data(page)
    assert set(shown["dice"]) == {1} and shown["total"] == body["total"] < first["total"]
    assert shown["historyId"] == first["historyId"]  # still the one recorded roll
    banner = page.locator('text=Togashi 4th Dan rerolled')
    assert banner.is_visible() and str(first["total"]) in banner.text_content()


# ---------------------------------------------------------------------------
# Initiative (Phase 5)
# ---------------------------------------------------------------------------

def test_initiative_is_rolled_by_the_server_and_starts_the_round(page, live_server_url):
    from tests.e2e.dice_control import force_dice, restore_dice
    _create_roller(page, live_server_url, "ServerInit")
    answers = []
    page.on("response", lambda r: answers.append(r) if r.url.endswith("/roll") else None)
    force_dice(page, [3])
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_function("() => window._diceRoller.phase === 'done'", timeout=10000)
    restore_dice(page)
    body = answers[0].json()
    assert body["formula"]["is_initiative"] and body["action_dice"]
    values = [d["value"] for d in body["action_dice"]]
    assert page.evaluate("() => window._diceRoller.actionDice.map(d => d.value)") == values
    assert page.evaluate("() => window._trackingBridge.actionDice.map(d => d.value)") == values
    page.reload()
    page.wait_for_function(
        f"() => JSON.stringify(window._trackingBridge.actionDice.map(d => d.value)) === '{json.dumps(values, separators=(',', ':'))}'",
        timeout=5000)


def test_lucky_on_initiative_replaces_the_action_dice(page, live_server_url):
    from tests.e2e.dice_control import force_dice, restore_dice
    from tests.e2e.test_pcp import _create_roller as _pcp_roller
    _pcp_roller(page, live_server_url, "ServerInitLucky", advantages=("lucky",))
    seen = _acts(page)
    force_dice(page, [2])
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_function("() => window._diceRoller.phase === 'done'", timeout=10000)
    first = page.evaluate("() => window._diceRoller.actionDice.map(d => d.value)")
    force_dice(page, [8])
    page.locator('[data-action="use-lucky"]').click()
    body = _done_after(page, seen, 1)
    restore_dice(page)
    rerolled = [d["value"] for d in body["action_dice"]]
    assert set(rerolled) == {8} and set(first) == {2}
    assert page.evaluate("() => window._trackingBridge.actionDice.map(d => d.value)") == rerolled
    assert page.evaluate("() => window._diceRoller.luckyPrevActionDice") == first


# ---------------------------------------------------------------------------
# Parry and feint (Phase 6)
# ---------------------------------------------------------------------------

def _rolls(page):
    seen = []
    page.on("request", lambda r: seen.append(r) if r.url.endswith("/roll") and r.method == "POST" else None)
    return seen


def test_a_predeclared_parry_is_rolled_by_the_server(page, live_server_url):
    from tests.e2e.test_rolls import _open_parry_modal
    _create_roller(page, live_server_url, "ServerParry")
    sent = _rolls(page)
    _open_parry_modal(page)
    page.locator('[data-testid="parry-predeclared"]').check()
    page.locator('[data-action="roll-parry-go"]').click()
    _wait_for_roll_result(page)
    body = json.loads(sent[-1].post_data)
    assert body["roll_key"] == "parry" and body["predeclared"] is True
    bonuses = page.evaluate("() => window._diceRoller.formula.bonuses.map(b => b.label)")
    assert "predeclared parry" in bonuses


def test_mirumoto_parry_hooks_and_points_are_the_servers(page, live_server_url):
    from tests.e2e.test_rolls import _open_parry_modal
    from tests.e2e.test_school_abilities import _create_char
    _create_char(page, live_server_url, "ServerMirumoto", "mirumoto_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    page.evaluate("async () => { const t = window._trackingBridge; t.voidPoints = 0; t.tempVoidPoints = 0;"
                  " await t.save(); await t.whenSaved(); }")
    page.locator('[data-roll-key="initiative"]').click()
    page.wait_for_function("() => window._diceRoller.phase === 'done'", timeout=10000)
    page.wait_for_function("() => window._trackingBridge.mirumotoRoundPoints === 2", timeout=5000)
    page.locator('[data-modal="dice-roller"] button:has-text("Close")').first.click()
    _open_parry_modal(page)
    page.locator('[data-action="roll-parry-go"]').click()
    _wait_for_roll_result(page)
    # The server's Mirumoto hook: one temp void point for the parry.
    page.wait_for_function("() => window._trackingBridge.tempVoidPoints === 1", timeout=5000)
    before = _roller_data(page)["total"]
    page.locator('[data-action="mirumoto-point-spend"]').click()
    page.wait_for_function("() => window._trackingBridge.mirumotoRoundPoints === 1", timeout=5000)
    assert _roller_data(page)["total"] == before + 2
    page.reload()
    page.wait_for_function("() => window._trackingBridge.mirumotoRoundPoints === 1"
                           " && window._trackingBridge.tempVoidPoints === 1", timeout=5000)


def test_akodo_feint_void_points_are_granted_by_the_server(page, live_server_url):
    from tests.e2e.test_school_abilities import _create_char, _roll_via_menu_or_direct
    _create_char(page, live_server_url, "ServerAkodoFeint", "akodo_bushi")
    page.evaluate("async () => { const t = window._trackingBridge; t.voidPoints = 0; t.tempVoidPoints = 0;"
                  " await t.save(); await t.whenSaved(); }")
    _roll_via_menu_or_direct(page, "knack:feint")
    page.locator('[data-action="akodo-feint-succeeded"]').click()
    page.wait_for_function("() => window._trackingBridge.tempVoidPoints === 4", timeout=5000)
    assert not page.locator('[data-action="akodo-feint-failed"]').is_visible()
    page.reload()
    page.wait_for_function("() => window._trackingBridge.tempVoidPoints === 4", timeout=5000)


def test_shiba_parry_damage_is_rolled_by_the_server(page, live_server_url):
    from tests.e2e.dice_control import force_dice, restore_dice
    from tests.e2e.test_rolls import _open_parry_modal
    from tests.e2e.test_school_abilities import _create_char
    _create_char(page, live_server_url, "ServerShiba", "shiba_bushi",
                 knack_overrides={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    seen = _acts(page)
    _open_parry_modal(page)
    page.locator('[data-action="roll-parry-go"]').click()
    _wait_for_roll_result(page)
    force_dice(page, [7])
    page.locator('[data-action="shiba-parry-damage"]').click()
    page.wait_for_function("() => window._diceRoller.phase === 'sub-damage-result'", timeout=10000)
    restore_dice(page)
    body = seen[-1].json()["sub_damage"]
    assert body["total"] == 7 and page.evaluate("() => window._diceRoller.subDamageTotal") == 7
