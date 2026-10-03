"""The feint modal (TN + odds) and the server-decided feint outcome: temp
void points, the highest action die moved to the feint's phase, the
"parried" toggle, and the Bayushi 3rd Dan damage columns."""

import re

import pytest

from tests.e2e.helpers import save_tracking
from tests.e2e.test_school_abilities import _create_char, _roll_feint

pytestmark = [pytest.mark.rolls, pytest.mark.school_abilities]


def _dice_values(page):
    return [d["value"] for d in page.evaluate("window._trackingBridge.actionDice")]


def test_feint_modal_needs_a_tn_and_shows_the_odds(page, live_server_url):
    _create_char(page, live_server_url, "FeintOdds", "akodo_bushi")
    save_tracking(page, voidPoints=2)
    page.locator('[data-roll-key="knack:feint"]').click()
    page.wait_for_selector('[data-modal="feint"]', state='visible', timeout=3000)
    assert not page.locator('[data-modal="attack"]').is_visible()
    assert page.locator('[data-testid="feint-tn-prompt"]').is_visible()
    assert page.locator('[data-action="roll-feint-go"]').is_disabled()
    note = " ".join(page.locator('[data-testid="feint-success-note"]').text_content().split())
    assert "+4 temp void points" in note and "unsuccessful feint still gives +1" in note
    page.locator('[data-testid="feint-tn-input"]').fill("20")
    table = page.locator('[data-testid="feint-prob-table"]')
    table.wait_for(state="visible", timeout=3000)
    rows = table.locator('tbody tr')
    assert rows.count() >= 2
    chances = [int(rows.nth(i).locator('td').nth(2).text_content().strip().rstrip('%'))
               for i in range(rows.count())]
    # Void points only help.
    assert chances == sorted(chances) and chances[-1] > chances[0]
    # Akodo does no feint damage: no damage columns.
    assert "Damage" not in table.locator('thead').text_content()
    assert page.locator('[data-action="roll-feint-go"]').is_enabled()


def test_a_successful_feint_moves_the_highest_action_die(page, live_server_url):
    _create_char(page, live_server_url, "FeintMove", "akodo_bushi")
    page.evaluate("""async () => {
        const t = window._trackingBridge;
        t.actionDice = [{value: 3, spent: false}, {value: 5, spent: false}, {value: 8, spent: false}];
        await t.save(); await t.whenSaved();
    }""")
    dice = page.locator('[data-testid="action-dice-section"] [data-action="action-die"]')
    dice.nth(0).click()
    page.locator('[data-action-die-menu-item="feint"]:visible').click()
    page.wait_for_selector('[data-modal="feint"]', state='visible', timeout=3000)
    page.locator('[data-testid="feint-tn-input"]').fill("1")
    page.locator('[data-action="roll-feint-go"]').click()
    page.wait_for_selector('[data-testid="feint-moved-die"]', state='visible', timeout=10000)
    assert "from phase 8 to phase 3" in " ".join(
        page.locator('[data-testid="feint-moved-die"]').text_content().split())
    page.wait_for_function(
        "() => window._trackingBridge.actionDice.map(d => d.value).join() === '3,5,3'", timeout=5000)
    spent = page.evaluate("window._trackingBridge.actionDice[0]")
    assert spent["spent"] is True and "vs TN 1 - succeeded" in spent.get("spent_by", "")
    # Parried: the die goes back to phase 8 and the die's note says so.
    page.locator('[data-testid="feint-parried"]').check()
    page.wait_for_function(
        "() => window._trackingBridge.actionDice.map(d => d.value).join() === '3,5,8'", timeout=5000)
    assert not page.locator('[data-testid="feint-moved-die"]').is_visible()
    page.wait_for_function(
        "() => (window._trackingBridge.actionDice[0].spent_by || '').includes('parried')", timeout=5000)
    page.reload()
    page.wait_for_function(
        "() => window._trackingBridge.actionDice.map(d => d.value).join() === '3,5,8'", timeout=5000)


def test_bayushi_feint_odds_show_damage_and_a_miss_hides_it(page, live_server_url):
    _create_char(page, live_server_url, "FeintBayushi", "bayushi_bushi",
                 knack_overrides={"double_attack": 3, "feint": 3, "iaijutsu": 3})
    save_tracking(page, voidPoints=2, tempVoidPoints=0)
    page.locator('[data-roll-key="knack:feint"]').click()
    page.wait_for_selector('[data-modal="feint"]', state='visible', timeout=3000)
    page.locator('[data-testid="feint-tn-input"]').fill("25")
    table = page.locator('[data-testid="feint-prob-table"]')
    table.wait_for(state="visible", timeout=3000)
    assert "Avg Damage" in table.locator('thead').text_content()
    first = table.locator('tbody tr').nth(0).locator('td')
    second = table.locator('tbody tr').nth(1).locator('td')
    # Xk1 with no void; each void point adds 1k1 (Bayushi Special).
    x = int(re.match(r"(\d+)k1$", first.nth(3).text_content().strip()).group(1))
    assert second.nth(3).text_content().strip() == f"{x + 1}k2"
    assert float(second.nth(4).text_content()) > float(first.nth(4).text_content())
    page.locator('[data-modal="feint"] button:has-text("×")').click()
    # A missed feint: no temp void, no damage roll.
    _roll_feint(page, tn=999)
    assert "missed" in page.locator('[data-testid="feint-outcome-line"]').text_content()
    assert not page.locator('[data-testid="feint-temp-vp"]').is_visible()
    assert not page.locator('button:text("Roll Feint Damage")').is_visible()
    assert page.evaluate("window._trackingBridge.tempVoidPoints") == 0


@pytest.mark.readonly_rolls
def test_a_non_editor_feint_shows_the_outcome_but_changes_nothing(page, page_nonadmin, live_server_url):
    from tests.e2e.test_readonly_rolls import _publish_with_knacks
    sheet_url = _publish_with_knacks(
        page, live_server_url, name="FeintReader", school="akodo_bushi",
        knack_overrides={"double_attack": 1, "feint": 1, "iaijutsu": 1},
    )
    page.goto(sheet_url)
    page.wait_for_selector("h1")
    save_tracking(page, tempVoidPoints=0)
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector("h1")
    _roll_feint(page_nonadmin, tn=1)
    assert "Feint succeeded" in page_nonadmin.locator('[data-testid="feint-outcome-line"]').text_content()
    assert "+4" in page_nonadmin.locator('[data-testid="feint-temp-vp"]').text_content()
    page_nonadmin.locator('[data-testid="feint-parried"]').check()
    page_nonadmin.wait_for_function(
        "() => (window._diceRoller.feintState || {}).parried === true", timeout=5000)
    assert page_nonadmin.evaluate("window._trackingBridge.tempVoidPoints") == 0
    page.reload()
    page.wait_for_selector("h1")
    assert page.evaluate("window._trackingBridge.tempVoidPoints") == 0
