"""E2E: the Copy-as-image card names every bonus its total includes.

The card used to show the right total while leaving out Hiruma 3rd Dan's
post-parry bonus, Bayushi 4th Dan's banked raise and Kakita 2nd / 4th Dan,
so whoever it was pasted to had to add the dice up to believe it. The server
side of this (every flat is a labeled row) is pinned by
tests/test_roll_card_bonuses.py; these check the sheet carries those rows
onto the card, and that Kakita 5th Dan's damage has a Copy button at all.
"""

import pytest
from tests.e2e.helpers import open_melee_attack

from tests.e2e.dice_control import force_dice

from tests.e2e.test_iaijutsu_duel import _open_duel_modal
from tests.e2e.test_school_abilities import (
    _create_char, _make_kakita_dan_5, _mock_dice_high, _restore_dice, _wait_attack_result,
)

pytestmark = [pytest.mark.school_abilities]


def _card(page, builder):
    return page.evaluate(f"() => window._diceRoller.{builder}()")


def _adds_up(card):
    import re
    extras = sum(int(m.group(1)) for e in card.get("extras") or []
                 if (m := re.match(r"^([+-]\d+)\s", e)))
    listed = sum(b["amount"] for b in card["bonuses"])
    assert card["kept_sum"] + listed + extras == card["total"], card


def _attack(page):
    open_melee_attack(page)
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    modal = page.locator('[data-modal="attack"]')
    modal.locator('select:visible').first.select_option("5")
    modal.locator('[data-action="roll-attack"]').click()
    _wait_attack_result(page)


def test_card_lists_hiruma_3rd_dan_on_attack(page, live_server_url):
    _create_char(page, live_server_url, "HirumaCard", "hiruma_scout",
                 knack_overrides={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    page.evaluate("""async () => {
        const t = window._trackingBridge;
        window._diceRoller.hirumaBankedAttackBonus = 4;
        t.hirumaBankedAttackBonus = 4;
        t.saveBankedBonuses();
        await t.whenSaved();
    }""")
    _mock_dice_high(page)
    _attack(page)
    _restore_dice(page)
    card = _card(page, "_buildAttackImagePayload")
    assert {"label": "Hiruma 3rd Dan (after a parry)", "amount": 4} in card["bonuses"]
    _adds_up(card)
    # Listed once in the result panel too (it used to have its own line).
    assert page.locator('[data-modal="attack"]').text_content().count("Hiruma 3rd Dan (after a parry)") == 1


def test_card_lists_bayushi_4th_dan_raise_applied_after_the_roll(page, live_server_url):
    _create_char(page, live_server_url, "BayushiCard", "bayushi_bushi",
                 knack_overrides={"double_attack": 4, "feint": 4, "iaijutsu": 4})
    page.evaluate("""async () => {
        const t = window._trackingBridge;
        window._diceRoller.bayushiBankedFeintRaise = 5;
        t.bayushiBankedFeintRaise = 5;
        t.saveBankedBonuses();
        await t.whenSaved();
    }""")
    _mock_dice_high(page)
    _attack(page)
    _restore_dice(page)
    page.locator('[data-modal="attack"] [data-action="bayushi-raise-spend"]:visible').first.click()
    page.wait_for_function("""() => (window._diceRoller._serverPostRollBonuses || [])
        .some(b => b.label === 'Bayushi 4th Dan banked raise')""", timeout=5000)
    card = _card(page, "_buildAttackImagePayload")
    assert {"label": "Bayushi 4th Dan banked raise", "amount": 5} in card["bonuses"]
    _adds_up(card)


def test_kakita_5th_dan_cards_list_2nd_and_4th_dan_and_damage_has_copy(page, live_server_url):
    _make_kakita_dan_5(page, live_server_url, "KakitaCard")
    page.locator('[data-action="kakita-5th-dan-contest"]').click()
    page.wait_for_selector('[data-modal="kakita-5th-dan"]', state='visible', timeout=5000)
    force_dice(page, [10, 7, 3])  # a rerolled 10 must reach the cards as two dice
    page.locator('[data-action="kakita-5th-roll"]').click()
    page.wait_for_function("() => window._diceRoller?.k5Phase === 'result'", timeout=10000)
    contest = _card(page, "_buildKakita5thImagePayload")
    assert {"parts": [10, 7]} in contest["kept"] + contest["dropped"], contest
    assert {"label": "2nd Dan technique", "amount": 5} in contest["bonuses"]
    _adds_up(contest)
    assert page.locator('[data-testid="kakita-5th-formula-bonus"]').first.is_visible()
    contest_history = page.evaluate("() => window._diceRoller._rollHistoryId")

    total = page.evaluate("() => window._diceRoller.k5RollTotal")
    page.locator('[data-action="kakita-5th-opponent-roll"]').fill(str(total))
    page.locator('[data-action="kakita-5th-roll-damage"]').click()
    page.wait_for_function("() => window._diceRoller?.k5Phase === 'damage-result'", timeout=10000)
    _restore_dice(page)
    damage = _card(page, "_buildKakita5thDamageImagePayload")
    assert {"parts": [10, 7]} in damage["kept"] + damage["dropped"], damage
    assert "+5 from 4th Dan (iaijutsu)" in damage["extras"]
    _adds_up(damage)
    copy = page.locator('[data-modal="kakita-5th-dan"] [data-action="copy-roll-image"]:visible')
    copy.wait_for(state="visible", timeout=5000)
    page.wait_for_function("() => window._diceRoller.rollImageStatus === 'ready'", timeout=10000)
    # The damage is its own history row; later edits must not land on the contest's.
    assert page.evaluate("() => window._diceRoller._rollHistoryId") != contest_history


def test_duel_contested_card_lists_kakita_2nd_dan(page, live_server_url):
    _create_char(page, live_server_url, "KakitaDuelCard", "kakita_duelist",
                 knack_overrides={"double_attack": 2, "iaijutsu": 2, "lunge": 2})
    _open_duel_modal(page)
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    modal.locator('input[placeholder="e.g. 200"]').fill("200")
    modal.locator('button:text("Proceed to Contested Roll")').click()
    _mock_dice_high(page)
    modal.locator('button:text("Roll Contested Iaijutsu")').click()
    page.wait_for_function("() => window._diceRoller?.duelPhase === 'contested-result'", timeout=10000)
    _restore_dice(page)
    card = _card(page, "_buildDuelContestedImagePayload")
    assert {"label": "2nd Dan technique", "amount": 5} in card["bonuses"]
    _adds_up(card)
