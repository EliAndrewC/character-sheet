"""E2E: archery attacks (archery-design/design.md) - the Archery row, the
attack modal's archery mode (TN from its parts, hold bonus, extra actions),
the damage table and the automatic serious wounds."""

import pytest
from playwright.sync_api import expect

from tests.e2e.dice_control import force_dice, restore_dice
from tests.e2e.helpers import create_and_apply, open_archery_attack

pytestmark = [pytest.mark.archery]


def _modal(page):
    return page.locator('[data-modal="attack"]')


def _set_dice(page, values):
    page.evaluate(f"""async () => {{
        const t = window._trackingBridge;
        t.setActionDice({values!r});
        await t.whenSaved();
    }}""")


def _open_archery_from_die(page, nth):
    page.locator('[data-testid="action-dice-section"] [data-action="action-die"]').nth(nth).click()
    page.locator('[data-action-die-menu-item="archery"]:visible').click()
    _modal(page).wait_for(state="visible", timeout=5000)
    _modal(page).locator('[data-testid="archery-inputs"]').wait_for(state="visible", timeout=5000)


def _roll(page):
    _modal(page).locator('[data-action="roll-attack"]').click()
    page.wait_for_function("() => window._diceRoller && window._diceRoller.atkPhase === 'result'",
                           timeout=10000)


def test_attack_row_offers_archery(page, live_server_url):
    """Every character's Attack row offers Archery Attack (there is no
    separate Archery row); it opens the attack modal in archery mode, whose
    TN follows its parts and whose table drops the melee damage columns."""
    create_and_apply(page, live_server_url, "ArcheryRow")
    assert page.locator('[data-roll-key="archery"]').count() == 0
    page.locator('[data-roll-key="attack"]').click()
    choice = page.locator('[data-attack-choice="archery"]')
    expect(choice).to_be_visible()
    # Akodo 1st Dan: +1k0 attack AND +1k0 double attack: 5k2 at attack 1.
    expect(choice.locator('[data-testid="archery-formula"]')).to_contain_text("5k2")
    choice.click()
    m = _modal(page)
    m.wait_for(state="visible", timeout=5000)
    tn = m.locator('[data-testid="archery-tn"]')
    expect(tn).to_contain_text("25")  # base 20 + 5 for 0-49 ft
    m.locator('[data-testid="archery-distance"]').select_option("3")
    expect(tn).to_contain_text("40")
    m.locator('[data-testid="archery-evasion"]').check()
    m.locator('[data-testid="archery-cover"]').fill("10")
    expect(tn).to_contain_text("55")
    m.locator('[data-testid="archery-unseen"]').check()
    expect(tn).to_contain_text("40")  # 5 + 20 + 5 + 10
    expect(m.locator('[data-testid="archery-base-tn"]')).to_be_disabled()
    expect(m.locator('th:text("Avg Damage")')).to_be_hidden()
    expect(m.locator('th:text("Hit %")')).to_be_visible()
    assert page.evaluate("window._diceRoller.atkTN") == 40


def test_arrow_hit_damage_table_and_serious_wounds(page, live_server_url):
    """A hit shows the damage table and the serious wounds (Akodo has double
    attack: 2); a failed parry takes one back; the damage roll is the table
    row the d10 picked."""
    create_and_apply(page, live_server_url, "ArcheryHit")
    open_archery_attack(page)
    m = _modal(page)
    m.wait_for(state="visible", timeout=5000)
    m.locator('[data-testid="archery-base-tn"]').fill("5")
    force_dice(page, [9])
    _roll(page)
    # 5 dice of 9 keep 18 against TN 10: 8 over, one shift.
    expect(m.locator('[data-testid="archery-hit"]')).to_contain_text("2 automatic serious wounds")
    bands = m.locator('[data-testid="archery-bands"]')
    expect(bands.locator('[data-testid="archery-band-2"]')).to_contain_text("20%")
    expect(bands.locator('[data-testid="archery-band-8"]')).to_contain_text("20%")
    m.locator('[data-testid="atk-failed-parry"]').check()
    expect(m.locator('[data-testid="archery-hit"]')).to_contain_text("1 automatic serious wound")
    # The base odds stand beside this hit's (one shift: 10% from 10k2 to 10k8).
    expect(bands.locator('[data-testid="archery-base-8"]')).to_have_text("10%")
    expect(bands.locator('[data-testid="archery-now-8"]')).to_have_text("20%")
    expect(bands.locator('[data-testid="archery-no-shift"]')).to_be_hidden()
    # First the table roll: a d10 of its own, the row it picks lit.
    force_dice(page, [10])
    m.locator('[data-action="roll-arrow-table"]').click()
    page.wait_for_function("() => window._diceRoller.atkPhase === 'arrow-result'", timeout=10000)
    table = m.locator('[data-testid="arrow-table-result"]')
    expect(table.locator('[data-testid="arrow-table-d10"]')).to_have_text("10")
    expect(table.locator('[data-testid="arrow-table-band-8"]')).to_have_attribute("data-lit", "1")
    expect(table.locator('[data-testid="arrow-table-band-2"]')).not_to_have_attribute("data-lit", "1")
    expect(table.locator('[data-testid="arrow-table-now-8"]')).to_have_text("20%")
    # Not Lucky: no Lucky button.
    expect(table.locator('[data-action="lucky-arrow-table"]')).to_be_hidden()
    # Then the damage the row names.
    expect(table.locator('[data-action="roll-arrow-damage"]')).to_contain_text("Make 10k8 Damage Roll")
    force_dice(page, [4])
    table.locator('[data-action="roll-arrow-damage"]').click()
    page.wait_for_function("() => window._diceRoller.atkPhase === 'damage-result'", timeout=10000)
    restore_dice(page)
    expect(m.locator('[data-testid="arrow-serious-wounds"]')).to_have_text("+ 1 serious wound")
    f = page.evaluate("window._diceRoller.formula")
    assert f["arrow_damage"] and f["rolled"] == 10 and f["kept"] == 8 and f["arrow_d10"] == 10
    expect(m).to_contain_text("10k8 arrow (table roll 10: 20% chance)")


def test_hold_bonus_extra_actions_and_reset(page, live_server_url):
    """Dice 1 and 2 spent on one arrow in phase 5 are +12 (the GM's example);
    a second arrow in the same phase has no hold bonus."""
    create_and_apply(page, live_server_url, "ArcheryHold")
    _set_dice(page, [1, 2, 4, 8])
    _open_archery_from_die(page, 0)
    m = _modal(page)
    m.locator('[data-action="archery-phase"]').select_option("5")
    expect(m.locator('[data-testid="archery-hold-display"]')).to_contain_text("+4")
    # Die 8 has not come up by phase 5; dice 2 and 4 have.
    expect(m.locator('[data-testid="archery-extra-3"]')).to_have_count(0)
    m.locator('[data-testid="archery-extra-1"]').check()
    force_dice(page, [5])
    _roll(page)
    restore_dice(page)
    bonuses = page.evaluate("window._diceRoller.formula.bonuses")
    labels = {b["label"]: b["amount"] for b in bonuses}
    assert labels["held 4 phases (die 1)"] == 4
    assert labels["1 extra action (dice 2)"] == 8
    dice = page.evaluate("window._trackingBridge.actionDice")
    assert [d["spent"] for d in dice] == [True, True, False, False]
    assert page.evaluate("window._trackingBridge.adventureState.archery_last_arrow_phase") == 5
    page.keyboard.press("Escape")
    page.evaluate("window._diceRoller.atkModalOpen = false")
    # The next arrow, die 4 in phase 5: counted from the last arrow, +0.
    _open_archery_from_die(page, 2)
    # Phases before the last arrow are not offered; it opens at phase 5.
    expect(m.locator('[data-action="archery-phase"] option')).to_have_count(6)
    expect(m.locator('[data-action="archery-phase"]')).to_have_value("5")
    expect(m.locator('[data-testid="archery-hold-display"]')).to_contain_text("+0")
    expect(m.locator('[data-testid="archery-hold-display"]')).to_contain_text("last arrow in phase 5")
    m.locator('[data-action="archery-phase"]').select_option("7")
    expect(m.locator('[data-testid="archery-hold-display"]')).to_contain_text("+2")
    m.locator('[data-testid="archery-moving"]').check()
    expect(m.locator('[data-testid="archery-hold-display"]')).to_contain_text("+0")


def test_unseen_target_cannot_parry(page, live_server_url):
    create_and_apply(page, live_server_url, "ArcheryUnseen")
    open_archery_attack(page)
    m = _modal(page)
    m.wait_for(state="visible", timeout=5000)
    m.locator('[data-testid="archery-unseen"]').check()
    force_dice(page, [9])
    _roll(page)
    restore_dice(page)
    expect(m.locator('[data-testid="archery-unseen-note"]')).to_be_visible()
    expect(m.locator('[data-testid="atk-failed-parry"]')).to_be_hidden()


def test_npc_archer_from_the_combat_page(page, live_server_url):
    """The GM's NPC shoots a PC through the combat page's roll overlay (the
    sheet's own modal): the target's TN seeds the arrow's base TN, and the
    fight log records the hit, its damage and its serious wounds."""
    from tests.e2e.test_combat import _group_with_pc, _start_fight_with_wave_men, _round, _roller, \
        _roller_gone, _state
    gid = _group_with_pc(page, live_server_url, "ArrowTarget")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    _round(page, npc_id)
    force_dice(page, [9])
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    frame = _roller(page)
    frame.locator('[data-action-die-menu-item="archery"]:visible').click()
    pc = next(p for p in _state(page, live_server_url, gid)["pcs"] if p["name"] == "ArrowTarget")
    frame.locator('[data-testid="atk-target"]').select_option(str(pc["id"]))
    expect(frame.locator('[data-testid="archery-base-tn"]')).to_have_value("10")  # 5 + 5 x parry 1
    frame.locator('[data-action="roll-attack"]').click()
    frame.locator('[data-action="roll-arrow-table"]').click()
    frame.locator('[data-action="roll-arrow-damage"]').click()
    frame.locator('[data-testid="arrow-serious-wounds"]').wait_for()
    frame.locator('button:visible', has_text="Close").last.click()
    restore_dice(page)
    _roller_gone(page)
    state = _state(page, live_server_url, gid)
    (attack,) = [a for a in state["actions"] if a["kind"] == "attack"]
    assert attack["target"] == "ArrowTarget" and attack["detail"]["outcome"] == "hit"
    assert attack["detail"]["serious_wounds"] >= 1
    assert "serious wound" in page.locator('[data-testid="action-log"]').text_content()


def test_a_non_editor_arrow_changes_nothing(page, page_nonadmin, live_server_url):
    """A viewer who cannot edit the character test-drives an arrow: it rolls
    and resolves, and the owner's action dice and last-arrow phase stay put."""
    url = create_and_apply(page, live_server_url, "ArcheryViewer")
    _set_dice(page, [1, 2])
    page_nonadmin.goto(url)
    open_archery_attack(page_nonadmin)
    m = _modal(page_nonadmin)
    m.wait_for(state="visible", timeout=5000)
    m.locator('[data-testid="archery-base-tn"]').fill("5")
    m.locator('[data-action="archery-phase"]').select_option("5")
    m.locator('[data-testid="archery-extra-1"]').check()
    force_dice(page_nonadmin, [9])
    _roll(page_nonadmin)
    expect(m.locator('[data-testid="archery-hit"]')).to_be_visible()
    assert page_nonadmin.evaluate("window._diceRoller._serverSessionMode") == "simulate"
    # The test-drive gets the bonuses its preview showed: +4 held, +8 extra.
    labels = {b["label"]: b["amount"] for b in page_nonadmin.evaluate("window._diceRoller.formula.bonuses")}
    assert labels["held 4 phases (die 1)"] == 4 and labels["1 extra action (dice 2)"] == 8
    page.reload()
    dice = page.evaluate("window._trackingBridge.actionDice")
    assert [d["spent"] for d in dice] == [False, False]
    assert not page.evaluate("window._trackingBridge.adventureState.archery_last_arrow_phase")


def test_no_shift_and_lucky_reroll_of_the_table(page, live_server_url):
    """A hit by less than 5 shows the base odds alone, saying nothing
    shifted; a Lucky character may reroll the table roll (the higher d10
    stands), and the damage follows the rerolled row."""
    create_and_apply(page, live_server_url, "ArcheryLucky", advantages=["lucky"])
    open_archery_attack(page)
    m = _modal(page)
    m.wait_for(state="visible", timeout=5000)
    # 5k2 of 3s keeps 6 against base 0 + 5 for distance: 1 over, no shift.
    m.locator('[data-testid="archery-base-tn"]').fill("0")
    force_dice(page, [3])
    _roll(page)
    bands = m.locator('[data-testid="archery-bands"]')
    expect(bands.locator('[data-testid="archery-no-shift"]')).to_be_visible()
    expect(bands.locator('[data-testid="archery-now-2"]')).to_be_hidden()
    expect(bands.locator('[data-testid="archery-base-8"]')).to_have_text("10%")
    force_dice(page, [2])
    m.locator('[data-action="roll-arrow-table"]').click()
    page.wait_for_function("() => window._diceRoller.atkPhase === 'arrow-result'", timeout=10000)
    table = m.locator('[data-testid="arrow-table-result"]')
    expect(table.locator('[data-testid="arrow-table-band-2"]')).to_have_attribute("data-lit", "1")
    force_dice(page, [10])
    table.locator('[data-action="lucky-arrow-table"]').click()
    expect(table.locator('[data-testid="arrow-table-d10"]')).to_have_text("10")
    expect(table.locator('[data-testid="arrow-table-band-8"]')).to_have_attribute("data-lit", "1")
    expect(table.locator('[data-testid="arrow-table-rerolled"]')).to_contain_text("Lucky")
    expect(table.locator('[data-action="lucky-arrow-table"]')).to_be_hidden()
    assert page.evaluate("window._trackingBridge.getToggle('lucky_used')")
    force_dice(page, [4])
    table.locator('[data-action="roll-arrow-damage"]').click()
    page.wait_for_function("() => window._diceRoller.atkPhase === 'damage-result'", timeout=10000)
    restore_dice(page)
    expect(m).to_contain_text("table roll rerolled with Lucky: 2, then 10; the 10 stands")
    assert page.evaluate("window._diceRoller.formula.kept") == 8


def test_pcp_reroll_of_the_table(page, live_server_url):
    """The table roll's PCP reroll sits in the modal's PCP menu (a reroll
    only: no free raise or 10s reroll is offered there)."""
    create_and_apply(page, live_server_url, "ArcheryPcp")
    open_archery_attack(page)
    m = _modal(page)
    m.wait_for(state="visible", timeout=5000)
    m.locator('[data-testid="archery-base-tn"]').fill("0")
    force_dice(page, [3])
    _roll(page)
    force_dice(page, [1])
    m.locator('[data-action="roll-arrow-table"]').click()
    page.wait_for_function("() => window._diceRoller.atkPhase === 'arrow-result'", timeout=10000)
    m.locator('[data-action="pcp-menu"]:visible').click()
    expect(page.locator('[data-action="pcp-raise-attack"]:visible')).to_have_count(0)
    force_dice(page, [9])
    page.locator('[data-action="pcp-reroll-arrow-table"]:visible').click()
    page.locator('[data-action="pcp-confirm-accept"]').click()
    table = m.locator('[data-testid="arrow-table-result"]')
    expect(table.locator('[data-testid="arrow-table-d10"]')).to_have_text("9")
    expect(table.locator('[data-testid="arrow-table-band-6"]')).to_have_attribute("data-lit", "1")
    expect(table.locator('[data-testid="arrow-table-rerolled"]')).to_contain_text("Player Character Point")
    restore_dice(page)
    assert page.evaluate("window._trackingBridge.pcpCount") == 1
