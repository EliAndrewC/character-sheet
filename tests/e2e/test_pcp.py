"""E2E: Player Character Points (rules/10-player_character_points.md).

Covers the confirmation modal, the three in-roll uses (reroll, free raise,
reroll-10s-while-impaired), the separate void refresh, the XP-summary category
+ undo (both View Sheet and edit page), the spend gate, and the read-only
non-persistence contract.

Dice are random, so the dice-dependent gating (reroll-10s needs a literal 10)
and the permission/gate states are driven through Alpine via page.evaluate to
stay deterministic; the spend/undo persistence is exercised against the real
server endpoints.
"""

import pytest

from tests.e2e.helpers import (
    select_school, click_plus, apply_changes, start_new_character,
)

pytestmark = [pytest.mark.pcp]


def _create_roller(page, live_server_url, name="PCP Roller", advantages=()):
    """Published akodo character with Bragging 1 (a generic skill roll) and
    VP zeroed so rolls skip the void-spend menu."""
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    for adv in advantages:
        page.check(f'input[name="adv_{adv}"]')
    click_plus(page, "skill_bragging", 1)
    page.wait_for_selector('text="Saved"', timeout=5000)
    apply_changes(page, "Roller setup")
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(200)
    return page.url


def _roll_bragging(page):
    page.locator('[data-roll-key="skill:bragging"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const data = window.Alpine && window.Alpine.$data(el);
            if (data && data.phase === 'done') return true;
        }
        return false;
    }""", timeout=10000)


def _attack_to_result(page, tn=60):
    """Open the attack modal and roll to the result panel. A high TN forces a
    MISS regardless of the dice, which is the user's scenario and shows the
    PCP options either way."""
    page.locator('[data-roll-key="attack"]').click()
    page.wait_for_timeout(200)
    menu = page.locator('[data-attack-choice-menu]')
    if menu.count() > 0 and menu.is_visible():
        menu.locator('[data-attack-choice="attack"]').click()
    page.wait_for_selector('[data-modal="attack"]', state='visible', timeout=10000)
    page.evaluate(f"""(tn) => {{
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {{
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'pre') {{ d.atkTN = tn; d.atkParrySkill = 1; return; }}
        }}
    }}""", arg=tn)
    page.locator('[data-modal="attack"] [data-action="roll-attack"]').click()
    page.wait_for_function("""() => {
        const els = document.querySelectorAll('[x-data]');
        for (const el of els) {
            const d = window.Alpine && window.Alpine.$data(el);
            if (d && d.atkPhase === 'result') return true;
        }
        return false;
    }""", timeout=10000)


def _pcp_menu_item(page, action):
    """Open the open roll-modal's PCP kebab, then click the given option. PCP
    options live in a compact ⋮ dropdown in each modal header; scope to the
    kebab inside a [data-modal] so the separate Void-Points-row kebab (which
    also lives on the sheet) isn't matched too."""
    page.locator('[data-modal] [data-action="pcp-menu"]:visible').click()
    page.wait_for_timeout(150)
    page.locator(f'[data-action="{action}"]:visible').click()


def test_confirm_modal_opens_with_cost_and_breakdown(page, live_server_url):
    _create_roller(page, live_server_url, "PcpConfirm")
    _roll_bragging(page)
    _pcp_menu_item(page, "pcp-raise")
    modal = page.locator('[data-modal="pcp-confirm"]')
    modal.wait_for(state="visible", timeout=4000)
    text = modal.text_content()
    assert "1st" in text          # first PCP
    assert "1 XP" in text         # costs 1 XP
    assert "unspent XP" in text   # not in debt (fresh character)
    # Cancel closes it without spending.
    modal.locator('button:text("Cancel")').click()
    page.wait_for_timeout(150)
    assert not modal.is_visible()
    assert page.evaluate("window._trackingBridge.pcpCount") == 0


def test_free_raise_applies_and_persists(page, live_server_url):
    _create_roller(page, live_server_url, "PcpRaise")
    _roll_bragging(page)
    before = page.evaluate("window._diceRoller.baseTotal")
    _pcp_menu_item(page, "pcp-raise")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    # +5 applied, result line shown, spend persisted (pcp_count bumped).
    page.wait_for_function(
        "(b) => window._diceRoller.baseTotal === b + 5", arg=before, timeout=4000,
    )
    assert page.locator('[data-testid="pcp-raise-line"]').is_visible()
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=4000)
    # Free raise is once per roll: the button is gone now.
    assert page.evaluate("window._diceRoller.canSpendPcpRaise()") is False


def test_reroll_does_not_stack_with_lucky(page, live_server_url):
    _create_roller(page, live_server_url, "PcpLucky", advantages=["lucky"])
    _roll_bragging(page)
    # Both rerolls available at first.
    assert page.evaluate("window._diceRoller.canUseLucky()") is True
    assert page.evaluate("window._diceRoller.canUsePcpReroll()") is True
    # Use Lucky -> the PCP reroll option disappears (no double reroll).
    # The Lucky button markup is included in every roll-flow panel, so scope
    # to the one visible in the open generic result modal.
    page.locator('button:has-text("Use Lucky to reroll"):visible').click()
    page.wait_for_timeout(400)
    assert page.evaluate("window._diceRoller.canUsePcpReroll()") is False
    page.locator('[data-modal] [data-action="pcp-menu"]:visible').click()
    page.wait_for_timeout(150)
    assert not page.locator('[data-action="pcp-reroll"]').is_visible()


def test_pcp_reroll_persists_and_blocks_further_reroll(page, live_server_url):
    _create_roller(page, live_server_url, "PcpReroll")
    _roll_bragging(page)
    _pcp_menu_item(page, "pcp-reroll")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=5000)
    # Reroll is once per roll; the keep-better pair banner is shown, labelled PCP.
    page.wait_for_function(
        "() => window._diceRoller.canUsePcpReroll() === false", timeout=4000,
    )
    # The pair banner is included in every roll-flow panel; scope to the
    # visible one in the open generic result modal.
    banner = page.locator('[data-testid="lucky-pair-banner"]:visible')
    banner.wait_for(state="visible", timeout=4000)
    assert "Player Character Point reroll" in banner.text_content()


def test_reroll_tens_gating(page, live_server_url):
    """Only offered when impaired, on a 10s-rerollable roll, with a 10 rolled."""
    _create_roller(page, live_server_url, "PcpTens")
    _roll_bragging(page)
    # Set up: impaired (SW >= Earth ring 2), a normal skill roll, a 10 present.
    def can(serious, values, key="skill:bragging", is_init=False, unskilled=False):
        return page.evaluate(
            """(a) => {
                const d = window._diceRoller;
                window._trackingBridge.seriousWounds = a.serious;
                d.formula = {kept: 1, rolled: 1, is_initiative: a.is_init, is_unskilled: a.unskilled};
                d.currentRollKey = a.key;
                d.finalDice = a.values.map(v => ({value: v}));
                d.pcpTensRerolledThisRoll = false;
                return d.canPcpRerollTens();
            }""",
            arg={"serious": serious, "values": values, "key": key,
                 "is_init": is_init, "unskilled": unskilled},
        )
    assert can(2, [10, 4]) is True            # impaired + a 10 + rerollable
    assert can(2, [7, 4]) is False            # no 10 rolled
    assert can(0, [10, 4]) is False           # not impaired
    assert can(2, [10], key="knack:iaijutsu:strike") is False  # strike excluded
    assert can(2, [10], is_init=True) is False                 # initiative excluded
    assert can(2, [10], unskilled=True) is False               # unskilled excluded


def test_reroll_tens_explodes_only_the_tens(page, live_server_url):
    """Reroll-10s is NOT a full reroll: it keeps every die and only explodes
    the 10s (adding the reroll). The canonical example: 7k4 [10,10,10,6,5,3,2]
    (=36) with each 10 rerolling to 6 -> 16,16,16 kept with the 6 -> 54."""
    _create_roller(page, live_server_url, "PcpTensExec")
    _roll_bragging(page)
    # Force a deterministic impaired 7k4 with three 10s, and make every reroll
    # a 6 (Math.random 0.5 -> face 6, so no further explosion).
    page.evaluate("""() => {
        const d = window._diceRoller;
        window._trackingBridge.seriousWounds = 5;  // impaired
        d.formula = { rolled: 7, kept: 4, flat: 0, is_initiative: false, is_unskilled: false };
        d.currentRollKey = 'skill:bragging';
        d.finalDice = [10,10,10,6,5,3,2].map(v => ({ value: v, parts: [v], kept: false }));
        d.keptSum = 36; d.baseTotal = 36;
        d.pcpTensRerolledThisRoll = false;
        d.phase = 'done'; d.open = true;
        window.__origRandom = Math.random; Math.random = () => 0.5;
    }""")
    _pcp_menu_item(page, "pcp-reroll-tens")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._diceRoller.pcpTensRerolledThisRoll === true", timeout=5000)
    state = page.evaluate("""() => {
        if (window.__origRandom) Math.random = window.__origRandom;
        const d = window._diceRoller;
        return {
            keptSum: d.keptSum,
            vals: d.finalDice.map(x => x.value).slice().sort((a,b)=>a-b),
            // the exploded dice show their chain via parts
            explodedParts: d.finalDice.filter(x => x.parts && x.parts.length > 1).map(x => x.parts),
        };
    }""")
    assert state["keptSum"] == 54                  # 16 + 16 + 16 + 6
    assert state["vals"] == [2, 3, 5, 6, 16, 16, 16]  # non-10 dice untouched
    assert state["explodedParts"] == [[10, 6], [10, 6], [10, 6]]  # 10 + reroll


def test_void_refresh_spends_pcp_and_regains_point(page, live_server_url):
    _create_roller(page, live_server_url, "PcpVoid")
    # The void-refresh kebab is absent while void points are full...
    assert not page.locator('[data-action="pcp-void-refresh"]').is_visible()
    # Drop a void point so a refresh has somewhere to go (max is 2).
    page.evaluate("window._trackingBridge.voidPoints = 0; window._trackingBridge.save()")
    page.wait_for_timeout(150)
    # ...and appears (in the Void Points row kebab) once one is spent. No roll
    # modal is open here, so the only visible kebab is the void-row one.
    page.locator('[data-action="pcp-menu"]:visible').click()
    page.wait_for_timeout(150)
    page.locator('[data-action="pcp-void-refresh"]:visible').click()
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    assert "void point" in page.locator('[data-modal="pcp-confirm"]').text_content()
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._trackingBridge.voidPoints === 1", timeout=5000)
    assert page.evaluate("window._trackingBridge.pcpCount") == 1


def test_gate_blocks_spend_when_modified(page, live_server_url):
    _create_roller(page, live_server_url, "PcpGate")
    _roll_bragging(page)
    # Simulate a pending draft edit: the sheet is no longer published-clean.
    page.evaluate("window._trackingBridge.pcpPublishedClean = false")
    _pcp_menu_item(page, "pcp-raise")
    modal = page.locator('[data-modal="pcp-confirm"]')
    modal.wait_for(state="visible")
    assert page.locator('[data-testid="pcp-confirm-blocked"]').is_visible()
    assert page.locator('[data-action="pcp-confirm-accept"]').is_disabled()


def test_xp_summary_category_and_undo_on_view_sheet(page, live_server_url):
    _create_roller(page, live_server_url, "PcpSummary")
    _roll_bragging(page)
    _pcp_menu_item(page, "pcp-raise")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=5000)
    page.evaluate("window._diceRoller.close()")
    page.wait_for_timeout(150)
    # The XP Summary now shows the PCP category card (updated live).
    card = page.locator('[data-xp-card="pcp"]')
    card.wait_for(state="visible", timeout=4000)
    card.click()  # expand
    # Undo it -> the cost drops permanently (card collapses to zero) and the
    # tracking bridge stays in sync so a later spend isn't over-charged.
    page.locator('[data-action="pcp-undo"]').click()
    card.wait_for(state="hidden", timeout=4000)
    page.wait_for_function("() => window._trackingBridge.pcpCount === 0", timeout=4000)
    # Reload: the reduction persisted server-side (not a discardable draft).
    page.reload()
    page.wait_for_selector('h1')
    assert page.locator('[data-xp-card="pcp"]').count() == 1
    assert not page.locator('[data-xp-card="pcp"]').is_visible()


def test_edit_page_shows_pcp_undo_line(page, live_server_url):
    sheet_url = _create_roller(page, live_server_url, "PcpEdit")
    _roll_bragging(page)
    _pcp_menu_item(page, "pcp-raise")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=5000)
    # The edit page surfaces the spend + an Undo control.
    page.goto(sheet_url + "/edit")
    line = page.locator('[data-testid="pcp-editor-line"]')
    line.wait_for(state="visible", timeout=5000)
    assert "1" in line.text_content()
    line.locator('[data-action="pcp-undo"]').click()
    # pcpCount drops to 0 on the form; the line hides.
    line.wait_for(state="hidden", timeout=4000)


def test_readonly_viewer_effect_is_local_only(page_nonadmin, live_server_url, page):
    """A non-editor can walk through a PCP free raise (sees the effect) but
    nothing persists - the read-only roll contract (rules + CLAUDE.md)."""
    sheet_url = _create_roller(page, live_server_url, "PcpReadonly")
    page_nonadmin.goto(sheet_url)
    page_nonadmin.wait_for_selector('[data-roll-key="skill:bragging"]')
    page_nonadmin.evaluate("window._trackingBridge.voidPoints = 0")
    _roll_bragging(page_nonadmin)
    before = page_nonadmin.evaluate("window._diceRoller.baseTotal")
    _pcp_menu_item(page_nonadmin, "pcp-raise")
    modal = page_nonadmin.locator('[data-modal="pcp-confirm"]')
    modal.wait_for(state="visible")
    # Read-only note is shown.
    assert page_nonadmin.locator('[data-testid="pcp-confirm-readonly"]').is_visible()
    page_nonadmin.locator('[data-action="pcp-confirm-accept"]').click()
    # The +5 applies to the displayed roll...
    page_nonadmin.wait_for_function(
        "(b) => window._diceRoller.baseTotal === b + 5", arg=before, timeout=4000,
    )
    # ...but the persisted PCP count never moves for a non-editor.
    assert page_nonadmin.evaluate("window._trackingBridge.pcpCount") == 0


def test_attack_pcp_reroll(page, live_server_url):
    """The reported bug: a missed attack must offer PCP reroll. Verify it
    spends, persists, and shows the keep-better pair banner."""
    _create_roller(page, live_server_url, "PcpAtkReroll")
    _attack_to_result(page)
    _pcp_menu_item(page, "pcp-reroll-attack")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=5000)
    # One reroll per roll: the option is gone, and the pair banner shows (PCP).
    page.wait_for_function("() => window._diceRoller.canUsePcpReroll() === false", timeout=4000)
    banner = page.locator('[data-modal="attack"] [data-testid="lucky-pair-banner"]:visible')
    banner.wait_for(state="visible", timeout=4000)
    assert "Player Character Point reroll" in banner.text_content()


def test_attack_reroll_banner_does_not_leak_to_next_attack(page, live_server_url):
    """Regression: rerolling one attack must not leave its reroll pair banner
    showing on the next attack after closing/reopening the modal."""
    _create_roller(page, live_server_url, "PcpAtkLeak")
    _attack_to_result(page)
    _pcp_menu_item(page, "pcp-reroll-attack")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("() => window._diceRoller.luckyRollPair !== null", timeout=5000)
    # Close the attack modal and roll a fresh attack.
    page.evaluate("window._diceRoller.atkModalOpen = false")
    page.wait_for_timeout(150)
    _attack_to_result(page)
    # The previous roll's pair banner must be gone and the reroll available again.
    assert page.evaluate("window._diceRoller.luckyRollPair") is None
    assert page.evaluate("window._diceRoller.pcpRerollUsedThisRoll") is False
    assert not page.locator('[data-modal="attack"] [data-testid="lucky-pair-banner"]:visible').count()


def test_attack_pcp_free_raise(page, live_server_url):
    """A missed attack can spend a PCP for a +5 free raise; the attack total
    goes up by 5, the hit state recomputes, and the spend persists."""
    _create_roller(page, live_server_url, "PcpAtkRaise")
    _attack_to_result(page)
    before = page.evaluate("window._diceRoller.atkRollTotal")
    _pcp_menu_item(page, "pcp-raise-attack")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    page.locator('[data-action="pcp-confirm-accept"]').click()
    page.wait_for_function("(b) => window._diceRoller.atkRollTotal === b + 5",
                           arg=before, timeout=5000)
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=4000)
    # The +5 is listed in the attack result breakdown (the reported bug).
    assert page.locator('[data-testid="pcp-raise-line-attack"]').is_visible()
    # Free raise is once per roll.
    assert page.evaluate("window._diceRoller.canSpendPcpRaise()") is False


def test_accept_button_guards_against_double_spend(page, live_server_url):
    """Rapid double-clicks of "Spend Player Character Point" must not fire two
    spends / two rerolls - the accept handler is re-entrancy guarded and the
    modal closes immediately."""
    _create_roller(page, live_server_url, "PcpDouble")
    _roll_bragging(page)
    _pcp_menu_item(page, "pcp-reroll")
    page.locator('[data-modal="pcp-confirm"]').wait_for(state="visible")
    # Fire the accept handler twice in the same tick (simulates a fast double
    # click before the first spend's POST resolves).
    page.evaluate("window._diceRoller.acceptPcpConfirm(); window._diceRoller.acceptPcpConfirm();")
    page.wait_for_function("() => window._trackingBridge.pcpCount === 1", timeout=5000)
    # Give any erroneous second spend a chance to land, then confirm it didn't.
    page.wait_for_timeout(800)
    assert page.evaluate("window._trackingBridge.pcpCount") == 1
    assert page.evaluate("window._diceRoller.canUsePcpReroll()") is False
