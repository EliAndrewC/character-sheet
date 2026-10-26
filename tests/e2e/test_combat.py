"""E2E: the GM combat tracker, generated NPCs, and the public combat page
(combat-design/design.md)."""

import re
import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.dice_control import force_dice, restore_dice
from tests.e2e.helpers import create_and_apply

pytestmark = [pytest.mark.combat]


def _group_with_pc(page, live_server_url, pc_name, *more_pcs):
    """A fresh group with visible PCs in it. Returns the group id."""
    gname = "Fight-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    for name in (pc_name,) + more_pcs:
        create_and_apply(page, live_server_url, name=name, school="akodo_bushi")
        page.goto(page.url + "/edit")
        page.wait_for_selector('select[name="gaming_group_id"]')
        page.locator('select[name="gaming_group_id"]').select_option(label=gname)
        page.wait_for_timeout(400)
    page.goto(live_server_url)
    page.locator('[data-testid="group-link"]', has_text=gname).first.click()
    page.wait_for_url(re.compile(r".*/groups/\d+$"))
    return int(page.url.rstrip("/").split("/")[-1])


def _start_fight_with_wave_men(page, live_server_url, group_id, count=1, name="Road ambush"):
    page.goto(f"{live_server_url}/groups/{group_id}/combat")
    page.fill('[data-testid="fight-name"]', name)
    page.locator('[data-testid="start-fight-btn"]').click()
    page.wait_for_selector('[data-testid="builder"]')
    page.locator('[data-testid="row-type-0"]').select_option("wave_man")
    page.fill('[data-testid="row-count-0"]', str(count))
    page.fill('[data-testid="row-xp-0"]', "50")
    page.locator('[data-testid="row-roll-0"]').uncheck()
    page.locator('[data-testid="generate-btn"]').click()
    page.wait_for_selector('[data-testid^="npc-card-"]')
    return page.locator('[data-testid^="npc-card-"]').first.get_attribute("data-testid").split("-")[-1]


def _state(page, live_server_url, group_id):
    return page.request.get(f"{live_server_url}/groups/{group_id}/combat/state").json()


def test_group_page_links_to_combat_for_everyone(page, page_nonadmin, live_server_url):
    gid = _group_with_pc(page, live_server_url, "LinkPC")
    page_nonadmin.goto(f"{live_server_url}/groups/{gid}")
    page_nonadmin.locator('[data-testid="group-combat-link"]').click()
    page_nonadmin.wait_for_url(f"**/groups/{gid}/combat")
    assert page_nonadmin.locator('[data-testid="combat-title"]').text_content() == "No fight in progress"
    assert page_nonadmin.locator('[data-testid="start-fight"]').count() == 0
    assert "LinkPC" in page_nonadmin.locator('[data-testid="pc-section"]').text_content()


def test_pc_names_link_to_their_sheets_in_a_new_tab(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "SheetLinkPC")
    pc_id = page.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()["pcs"][0]["id"]
    for viewer in (page, page_anon):
        viewer.goto(f"{live_server_url}/groups/{gid}/combat")
        link = viewer.locator(f'[data-testid="pc-name-{pc_id}"]')
        assert link.text_content() == "SheetLinkPC"
        assert link.get_attribute("href") == f"/characters/{pc_id}"
        assert link.get_attribute("target") == "_blank"
    with page.context.expect_page() as new_tab:
        page.locator(f'[data-testid="pc-name-{pc_id}"]').click()
    sheet = new_tab.value
    sheet.wait_for_load_state()
    assert sheet.url.endswith(f"/characters/{pc_id}")
    assert "SheetLinkPC" in sheet.content()
    sheet.close()


def _roller(page):
    """The NPC roll overlay: the sheet's own menu and modals, in an iframe."""
    page.wait_for_selector('[data-testid="npc-roller-frame"]')
    frame = page.frame_locator('[data-testid="npc-roller-frame"]')
    frame.locator('[data-testid="npc-roller"]').wait_for(state="attached")
    return frame


def _roller_gone(page):
    page.wait_for_selector('[data-testid="npc-roller-frame"]', state="detached", timeout=10000)


def _menu(page, npc_id, item):
    """Pick ``item`` (a testid prefix like "npc-adjust") from the NPC's kebab menu."""
    page.locator(f'[data-testid="npc-menu-{npc_id}"]').click()
    page.locator(f'[data-testid="{item}-{npc_id}"]').click()


def _round(page, npc_id):
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_selector(f'[data-testid="npc-die-{npc_id}-0"]')


def test_gm_generates_npcs_and_one_attacks_a_pc(page, live_server_url):
    """A die opens the SHEET's die menu and attack modal (with its odds and
    the fight's PCs as targets); the roll, its damage and the spent die land
    in the fight log, and nothing is written to the PC."""
    gid = _group_with_pc(page, live_server_url, "TargetPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid, count=2)
    assert page.locator('[data-testid^="npc-card-"]').count() == 2
    assert "Wave Man 1" in page.locator('[data-testid="npc-section"]').text_content()
    assert "50 earned XP" in page.locator(f'[data-testid="npc-card-{npc_id}"]').text_content()
    _round(page, npc_id)
    assert "Round 1" in page.locator('[data-testid="combat-round"]').text_content()
    # The sheet's die icon.
    assert page.locator(f'[data-testid="npc-die-{npc_id}-0"] svg.die.action-die').count() == 1

    force_dice(page, [9])
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    frame = _roller(page)
    frame.locator('[data-action-die-menu-item="attack"]').click()
    pc = next(p for p in _state(page, live_server_url, gid)["pcs"] if p["name"] == "TargetPC")
    frame.locator('[data-testid="atk-target"]').select_option(str(pc["id"]))
    frame.locator('[data-action="roll-attack"]').click()
    frame.locator('[data-action="roll-damage"]').wait_for()
    frame.locator('[data-action="roll-damage"]').click()
    frame.get_by_role("button", name="Close").last.wait_for()
    frame.locator('button:visible', has_text="Close").last.click()
    restore_dice(page)
    _roller_gone(page)

    state = _state(page, live_server_url, gid)
    npc = next(n for n in state["npcs"] if n["id"] == int(npc_id))
    assert npc["action_dice"][0]["spent"] is True
    (attack,) = [a for a in state["actions"] if a["kind"] == "attack"]
    assert attack["target"] == "TargetPC" and attack["detail"]["outcome"] == "hit"
    assert attack["detail"]["damage"] > 0
    log = page.locator('[data-testid="action-log"]').text_content()
    assert "on TargetPC" in log and "damage" in log
    # The PC's wounds are the player's to enter (D19): the tracker wrote nothing.
    pc_after = next(p for p in state["pcs"] if p["name"] == "TargetPC")
    assert (pc_after["light_wounds"], pc_after["serious_wounds"]) == (0, 0)


def test_npc_parries_and_marks_a_die_spent(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "SwordPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    _round(page, npc_id)
    force_dice(page, [9])
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    frame = _roller(page)
    frame.locator('[data-action-die-menu-item="parry"]').click()
    frame.locator('input[x-model\\.number="parryTN"]').fill("5")
    frame.locator('[data-action="roll-parry-go"]').click()
    frame.locator('button:visible', has_text="Close").last.wait_for()
    frame.locator('button:visible', has_text="Close").last.click()
    restore_dice(page)
    _roller_gone(page)
    state = _state(page, live_server_url, gid)
    (parry,) = [a for a in state["actions"] if a["kind"] == "parry"]
    assert parry["detail"]["outcome"] == "parried"

    if len(state["npcs"][0]["action_dice"]) > 1:
        page.locator(f'[data-testid="npc-die-{npc_id}-1"]').click()
        _roller(page).locator('[data-action="action-die-spent"]').click()
        _roller_gone(page)
        page.wait_for_selector(f'[data-testid="npc-die-{npc_id}-1"][data-die-spent="true"]')


def test_a_die_menu_closed_without_choosing_removes_the_overlay(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "IdlePC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    _round(page, npc_id)
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    _roller(page).locator('[data-action-die-menu-item="attack"]').wait_for()
    page.mouse.click(5, 5)  # outside the menu: the sheet's click-outside closes it
    _roller_gone(page)
    assert _state(page, live_server_url, gid)["actions"] == []


def test_npc_takes_damage_and_goes_down(page, live_server_url):
    """"Took damage" opens the sheet's light-wounds modal and its wound check."""
    gid = _group_with_pc(page, live_server_url, "HitterPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    force_dice(page, [1])  # a failed check
    page.locator(f'[data-testid="npc-lw-btn-{npc_id}"]').click()
    frame = _roller(page)
    frame.locator('input[x-model="lwAddAmount"]').fill("40")
    frame.locator('button:visible', has_text="Add").first.click()
    frame.locator('[data-action="roll-wound-check-go"]').click()
    frame.locator('button:visible', has_text="Close").last.wait_for()
    frame.locator('button:visible', has_text="Close").last.click()
    restore_dice(page)
    _roller_gone(page)
    page.wait_for_function(
        f"document.querySelector('[data-testid=\"npc-sw-{npc_id}\"]').textContent !== '0'")
    if page.locator('[data-testid="down-prompt"]').count():
        page.locator('[data-testid="down-dead"]').click()
        page.wait_for_selector('[data-testid="down-prompt"]', state="detached")
    else:
        # Adjusting serious wounds to 2 x Earth asks unconscious or dead (D9).
        _menu(page, npc_id, "npc-adjust")
        page.fill('[data-testid="adjust-sw"]', "20")
        page.locator('[data-testid="adjust-save-btn"]').click()
        page.wait_for_selector('[data-testid="down-prompt"]')
        page.locator('[data-testid="down-dead"]').click()
        page.wait_for_selector('[data-testid="down-prompt"]', state="detached")
    assert page.locator(f'[data-testid="npc-status-label-{npc_id}"]').text_content() == "Dead"


def test_public_view_shows_totals_but_not_how(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "WatcherPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_selector(f'[data-testid="npc-die-{npc_id}-0"]')
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    _roller(page).locator('[data-action="action-die-spent"]').click()
    _roller_gone(page)
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_function("document.querySelector('[data-testid=\"combat-round\"]').textContent.includes('Round 2')")

    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    card = page_anon.locator(f'[data-testid="npc-card-{npc_id}"]')
    assert "Wave Man 1" in card.text_content()
    # One action known from round 1, not taken yet this round: one "?" die.
    assert page_anon.locator(f'[data-testid="npc-unknown-die-{npc_id}"]').count() == 1
    # GM-only markup sits in <template x-if="gm"> blocks that never render
    # here; nothing of it reaches the page's text or elements.
    shown = card.text_content()
    for secret in ("Void", "earned XP", "% combat", "Took damage", "Roll initiative"):
        assert secret not in shown, secret
    assert page_anon.locator('[data-testid^="npc-die-"]').count() == 0
    # The public poll carries no unspent dice, void or stats.
    state = page_anon.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()
    assert set(state["npcs"][0]) == {
        "id", "name", "light_wounds", "serious_wounds", "down",
        "spent_dice", "unknown_dice", "tn_to_be_hit", "impaired",
    }


def test_players_cannot_open_an_npc_sheet_and_home_never_lists_npcs(page, page_nonadmin, live_server_url):
    gid = _group_with_pc(page, live_server_url, "CuriousPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    resp = page_nonadmin.goto(f"{live_server_url}/characters/{npc_id}")
    assert resp.status == 404
    page.goto(live_server_url)
    assert "Wave Man 1" not in page.content()
    page.goto(f"{live_server_url}/characters/{npc_id}")
    assert "Wave Man 1" in page.content()


def test_roster_brings_an_npc_back_to_the_next_fight(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "RosterPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    page.once("dialog", lambda d: d.accept())
    page.locator('[data-testid="end-fight-btn"]').click()
    page.wait_for_selector('[data-testid="start-fight"]')
    page.fill('[data-testid="fight-name"]', "Rematch")
    page.locator('[data-testid="start-fight-btn"]').click()
    page.wait_for_selector('[data-testid="builder"]')
    page.locator('[data-testid="roster-load-btn"]').click()
    page.wait_for_selector(f'[data-testid="roster-row-{npc_id}"]')
    page.fill(f'[data-testid="roster-gained-{npc_id}"]', "30")
    page.locator(f'[data-testid="roster-back-{npc_id}"]').click()
    page.wait_for_selector(f'[data-testid="npc-card-{npc_id}"]')
    assert "80 earned XP" in page.locator(f'[data-testid="npc-card-{npc_id}"]').text_content()


def test_rebuild_and_rename_an_npc(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "RebuildPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    _menu(page, npc_id, "npc-rebuild")
    page.fill('[data-testid="rebuild-xp"]', "150")
    page.fill('[data-testid="rebuild-share"]', "85")
    page.locator('[data-testid="rebuild-save-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    card = page.locator(f'[data-testid="npc-card-{npc_id}"]')
    # The card redraws after the rebuild, so wait for it rather than read it once.
    expect(card).to_contain_text("150 earned XP (300 total), 85% combat")
    _menu(page, npc_id, "npc-rename")
    page.fill('[data-testid="rename-input"]', "Big Goro")
    page.locator('[data-testid="rename-save-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    assert page.locator(f'[data-testid="npc-name-{npc_id}"] > span').first.text_content() == "Big Goro"


def test_combat_rolls_view_filters_npc_rolls(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "RollsPC")
    _start_fight_with_wave_men(page, live_server_url, gid)
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_selector('[data-testid^="npc-die-"]')
    page.locator('[data-testid="combat-rolls-link"]').click()
    page.wait_for_url("**/combat/rolls")
    rows = page.locator('[data-testid="roll-row"]')
    assert rows.count() >= 1
    npc_row = page.locator('[data-testid="roll-row"][data-kind="npc"]').first
    assert "Initiative" in npc_row.text_content()
    page.locator('[data-testid="rolls-filter-pc"]').click()
    npc_row.wait_for(state="hidden")
    page.locator('[data-testid="rolls-filter-npc"]').click()
    npc_row.wait_for(state="visible")


def test_combat_page_has_no_js_errors_and_fits_a_phone(page, live_server_url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    gid = _group_with_pc(page, live_server_url, "PhonePC")
    _start_fight_with_wave_men(page, live_server_url, gid)
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    page.wait_for_selector('[data-testid^="npc-card-"]')
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert not overflow
    assert errors == []


def test_gm_opens_a_player_view_tab_that_follows_the_fight(page, live_server_url):
    """The GM's "Player view" opens this page in a new tab as players see it
    (for screen sharing); it keeps updating from the GM's own tab, even while
    hidden, and the GM's tab keeps the full tracker."""
    gid = _group_with_pc(page, live_server_url, "SharePC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    with page.context.expect_page() as new_tab:
        page.locator('[data-testid="open-player-view"]').click()
    shared = new_tab.value
    shared.wait_for_selector(f'[data-testid="npc-card-{npc_id}"]')
    assert "view=player" in shared.url
    assert shared.locator('[data-testid="new-round-btn"]').count() == 0
    assert shared.locator('[data-testid="open-player-view"]').count() == 0
    assert "earned XP" not in shared.locator(f'[data-testid="npc-card-{npc_id}"]').text_content()
    assert shared.locator('[data-testid="leave-player-view"]').is_visible()

    # The GM acts in the original tab; the shared tab follows by itself.
    page.bring_to_front()
    page.locator('[data-testid="new-round-btn"]').click()
    shared.wait_for_function(
        "document.querySelector('[data-testid=\"combat-round\"]').textContent.includes('Round 1')",
        timeout=15000)
    assert page.locator('[data-testid="new-round-btn"]').is_visible()
    assert page.locator(f'[data-testid^="npc-die-{npc_id}-"]').count() > 0


def test_players_see_an_npcs_tn_only_after_it_was_attacked(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "TnPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    page_anon.wait_for_selector(f'[data-testid="npc-card-{npc_id}"]')
    assert page_anon.locator(f'[data-testid="npc-public-tn-{npc_id}"]').count() == 0

    page.locator(f'[data-testid="npc-lw-btn-{npc_id}"]').click()
    frame = _roller(page)
    frame.locator('input[x-model="lwAddAmount"]').fill("3")
    frame.locator('button:visible', has_text="Add").first.click()
    force_dice(page, [9])  # a passed check: the sheet asks keep or take
    frame.locator('[data-action="roll-wound-check-go"]').click()
    frame.locator('button:visible', has_text="Keep Light Wounds").click()
    restore_dice(page)
    _roller_gone(page)
    page.wait_for_function(f"document.querySelector('[data-testid=\"npc-lw-{npc_id}\"]')?.textContent !== '0' || document.querySelector('[data-testid=\"npc-sw-{npc_id}\"]')?.textContent !== '0'")
    tn = _state(page, live_server_url, gid)["npcs"][0]["tn_to_be_hit"]
    shown = page_anon.locator(f'[data-testid="npc-public-tn-{npc_id}"]')
    shown.wait_for(timeout=15000)
    assert f"TN {tn}" in shown.text_content()


def _same_line(page, a, b):
    ba, bb = page.locator(a).bounding_box(), page.locator(b).bounding_box()
    return abs((ba["y"] + ba["height"] / 2) - (bb["y"] + bb["height"] / 2)) < 8


def test_player_view_puts_wounds_on_the_name_line(page, page_anon, live_server_url):
    """Players' cards show "LW n · SW n" (and TN once known) right of the
    name, wrapping below on a narrow screen; the GM's cards are unchanged."""
    gid = _group_with_pc(page, live_server_url, "LinePC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    pc_id = _state(page, live_server_url, gid)["pcs"][0]["id"]
    page_anon.set_viewport_size({"width": 1200, "height": 800})
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    page_anon.wait_for_selector(f'[data-testid="npc-public-stats-{npc_id}"]')
    assert _same_line(page_anon, f'[data-testid="npc-name-{npc_id}"]', f'[data-testid="npc-public-stats-{npc_id}"]')
    pc_name = f'[data-testid="pc-name-{pc_id}"]'
    assert _same_line(page_anon, pc_name, f'[data-testid="pc-public-stats-{pc_id}"]')
    text = " ".join(page_anon.locator(f'[data-testid="pc-public-stats-{pc_id}"]').inner_text().split())
    assert text == "LW 0 · SW 0"
    page_anon.set_viewport_size({"width": 360, "height": 800})
    assert page_anon.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    # The GM's own card keeps its separate stats row.
    assert page.locator(f'[data-testid="npc-public-stats-{npc_id}"]').count() == 0
    assert page.locator(f'[data-testid="npc-void-{npc_id}"]').is_visible()


def test_players_see_spent_dice_once_however_often_the_gm_changes_their_mind(page, page_anon, live_server_url):
    """Spend, unspend, spend: players see ONE spent die with its value and no
    extra actions; next round the action they know of is a "?" die until
    the NPC spends a die again."""
    gid = _group_with_pc(page, live_server_url, "DicePC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    _round(page, npc_id)
    for item in ("action-die-spent", "action-die-unspent", "action-die-spent"):
        page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
        _roller(page).locator(f'[data-action="{item}"]').click()
        _roller_gone(page)
    value = _state(page, live_server_url, gid)["npcs"][0]["action_dice"][0]["value"]

    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    spent = page_anon.locator(f'[data-testid="npc-spent-die-{npc_id}"]')
    spent.first.wait_for()
    assert spent.count() == 1 and spent.first.text_content().strip() == str(value)
    assert page_anon.locator(f'[data-testid="npc-unknown-die-{npc_id}"]').count() == 0
    assert page_anon.locator(f'[data-testid="npc-actions-{npc_id}"]').count() == 0  # rolls are never public

    _round(page, npc_id)
    page_anon.locator(f'[data-testid="npc-unknown-die-{npc_id}"]').first.wait_for(timeout=15000)
    assert page_anon.locator(f'[data-testid="npc-unknown-die-{npc_id}"]').text_content().strip() == "?"
    assert page_anon.locator(f'[data-testid="npc-spent-die-{npc_id}"]').count() == 0
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    _roller(page).locator('[data-action="action-die-spent"]').click()
    _roller_gone(page)
    page_anon.locator(f'[data-testid="npc-spent-die-{npc_id}"]').first.wait_for(timeout=15000)
    assert page_anon.locator(f'[data-testid="npc-unknown-die-{npc_id}"]').count() == 0


def test_gm_card_keeps_npc_controls_in_a_kebab_menu(page, page_anon, live_server_url):
    """The GM card: build as a tooltip on the name, every control in the
    kebab menu (status reads Fighting / Down / Dead), LW opens the wound
    modal. Impaired shows as an orange SW count, for players too."""
    gid = _group_with_pc(page, live_server_url, "KebabPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    card = page.locator(f'[data-testid="npc-card-{npc_id}"]')
    build = page.locator(f'[data-testid="npc-build-{npc_id}"]')
    assert "50 earned XP (200 total)" in build.text_content() and "% non-combat" in build.text_content()
    assert not build.is_visible()
    # Hovering shows it after the site's tooltip delay. The name's truncate
    # used to sit on the trigger itself and clip the tooltip to nothing.
    page.locator(f'[data-testid="npc-name-{npc_id}"]').hover()
    page.wait_for_function(f"""() => {{
        const r = document.querySelector('[data-testid="npc-build-{npc_id}"]').getBoundingClientRect();
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return getComputedStyle(hit).visibility === 'visible' && hit.closest('[data-testid="npc-build-{npc_id}"]');
    }}""", timeout=5000)
    page.mouse.move(0, 0)
    for gone in ("Took damage", "Roll initiative", "Adjust", "Rebuild", "Rename", "Leave fight"):
        assert gone not in card.inner_text(), gone
    page.locator(f'[data-testid="npc-menu-{npc_id}"]').click()
    # Alpine shows the menu on its next tick; reading the text at once raced it.
    page.locator(f'[data-testid="npc-sheet-{npc_id}"]').wait_for(state="visible")
    menu_text = card.inner_text()
    for item in ("Roll initiative", "Adjust", "Rebuild", "Rename", "Sheet", "Leave fight", "Fighting", "Down", "Dead"):
        assert item in menu_text, item
    assert "Unconscious" not in menu_text
    page.locator(f'[data-testid="npc-status-{npc_id}-unconscious"]').click()
    page.wait_for_selector(f'[data-testid="npc-status-label-{npc_id}"]')
    assert page.locator(f'[data-testid="npc-status-label-{npc_id}"]').text_content() == "Down"
    page.locator(f'[data-testid="npc-menu-{npc_id}"]').click()
    page.locator(f'[data-testid="npc-status-{npc_id}-fighting"]').click()
    page.wait_for_selector(f'[data-testid="npc-status-label-{npc_id}"]', state="detached")

    # Impaired: serious wounds at Earth turns SW orange, with a tooltip.
    earth = _state(page, live_server_url, gid)["npcs"][0]["earth"]
    _menu(page, npc_id, "npc-adjust")
    page.fill('[data-testid="adjust-sw"]', str(earth))
    page.locator('[data-testid="adjust-save-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    page.wait_for_selector(f'[data-testid="npc-card-{npc_id}"] [data-impaired="true"]')
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    public_sw = page_anon.locator(f'[data-testid="npc-card-{npc_id}"] [data-impaired="true"]')
    public_sw.wait_for()
    assert "Impaired" in public_sw.text_content()
    assert "text-orange-600" in public_sw.get_attribute("class")

    # LW is the "took damage" control.
    page.locator(f'[data-testid="npc-lw-btn-{npc_id}"]').click()
    _roller(page).locator('input[x-model="lwAddAmount"]').wait_for()


def _drag(page, grip, target, below=True):
    """Drag by ``grip`` to just below (or above) ``target``, the way a hand does."""
    g = page.locator(grip).bounding_box()
    t = page.locator(target).bounding_box()
    page.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
    page.mouse.down()
    y = t["y"] + t["height"] + 5 if below else t["y"] - 5
    page.mouse.move(t["x"] + t["width"] / 2, y, steps=8)
    page.mouse.up()


def _names(page, side):
    return page.locator(f'[data-order-side="{side}"] [data-order-id]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-order-id'))")


def test_gm_drags_each_side_into_the_order_they_stand_in(page, page_anon, live_server_url):
    """Each column reorders within itself, persists for the fight, and the
    player view follows; an NPC dragged over the PC column stays an NPC."""
    gid = _group_with_pc(page, live_server_url, "AlphaPC", "BetaPC")
    _start_fight_with_wave_men(page, live_server_url, gid, count=2)
    pcs, npcs = _names(page, "pcs"), _names(page, "npcs")
    assert len(pcs) == 2 and len(npcs) == 2

    _drag(page, f'[data-testid="pc-grip-{pcs[0]}"]', f'[data-testid="pc-card-{pcs[1]}"]')
    page.wait_for_function(f"document.querySelector('[data-order-side=\"pcs\"] [data-order-id]').getAttribute('data-order-id') === '{pcs[1]}'")
    _drag(page, f'[data-testid="npc-grip-{npcs[1]}"]', f'[data-testid="npc-card-{npcs[0]}"]', below=False)
    page.wait_for_function(f"document.querySelector('[data-order-side=\"npcs\"] [data-order-id]').getAttribute('data-order-id') === '{npcs[1]}'")
    page.wait_for_timeout(300)

    page.reload()  # it persists
    assert _names(page, "pcs") == [pcs[1], pcs[0]] and _names(page, "npcs") == [npcs[1], npcs[0]]
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    page_anon.wait_for_selector('[data-order-side="npcs"] [data-order-id]')
    assert _names(page_anon, "pcs") == [pcs[1], pcs[0]] and _names(page_anon, "npcs") == [npcs[1], npcs[0]]
    assert page_anon.locator('[data-testid^="pc-grip-"], [data-testid^="npc-grip-"]').count() == 0

    # Dragging an NPC across into the PC column changes neither column.
    _drag(page, f'[data-testid="npc-grip-{npcs[1]}"]', f'[data-testid="pc-card-{pcs[0]}"]')
    page.wait_for_timeout(500)
    page.reload()
    assert _names(page, "pcs") == [pcs[1], pcs[0]]
    assert sorted(_names(page, "npcs")) == sorted(npcs)


def test_gm_draws_striking_lines_players_see_them_and_the_gm_can_hide_them(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "ReachA", "ReachB")
    _start_fight_with_wave_men(page, live_server_url, gid, count=2)
    page.set_viewport_size({"width": 1280, "height": 900})
    pcs, npcs = [int(i) for i in _names(page, "pcs")], [int(i) for i in _names(page, "npcs")]
    arena = page.locator('[data-testid="combat-arena"]')
    assert "lg:grid-cols-2" in arena.get_attribute("class")  # no strip until there is a line

    # From an NPC's kebab: Can strike > a PC.
    page.locator(f'[data-testid="npc-menu-{npcs[0]}"]').click()
    page.locator(f'[data-testid="npc-can-strike-{npcs[0]}"]').hover()
    page.locator(f'[data-testid="npc-card-{npcs[0]}"] [data-testid="reach-{pcs[0]}-{npcs[0]}"]').check()
    page.wait_for_selector(f'[data-testid="reach-line-{pcs[0]}-{npcs[0]}"]', state="attached")
    page.keyboard.press("Escape")
    page.mouse.click(5, 5)
    # From a PC's kebab: Can strike > an NPC.
    page.locator(f'[data-testid="pc-menu-{pcs[1]}"]').click()
    page.locator(f'[data-testid="pc-can-strike-{pcs[1]}"]').hover()
    page.locator(f'[data-testid="pc-card-{pcs[1]}"] [data-testid="reach-{pcs[1]}-{npcs[0]}"]').check()
    page.wait_for_selector(f'[data-testid="reach-line-{pcs[1]}-{npcs[0]}"]', state="attached")
    page.mouse.click(5, 5)
    assert "lg:grid-cols-2" not in arena.get_attribute("class")

    page_anon.set_viewport_size({"width": 1280, "height": 900})
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    page_anon.wait_for_selector(f'[data-testid="reach-line-{pcs[0]}-{npcs[0]}"]', state="attached")
    assert page_anon.locator('[data-testid^="reach-line-"]').count() == 2
    assert page_anon.locator('[data-testid^="reach-hit-"]').count() == 0  # players cannot remove one

    # The GM clicks a line: it highlights and offers to remove it.
    page.locator(f'[data-testid="reach-hit-{pcs[0]}-{npcs[0]}"]').click()
    page.wait_for_selector('[data-testid="reach-line-menu"]')
    assert "ReachA" in page.locator('[data-testid="reach-line-menu"]').text_content()
    page.locator('[data-testid="reach-line-remove"]').click()
    page.wait_for_selector(f'[data-testid="reach-line-{pcs[0]}-{npcs[0]}"]', state="detached")
    page_anon.wait_for_selector(f'[data-testid="reach-line-{pcs[0]}-{npcs[0]}"]', state="detached", timeout=15000)

    # A phone stacks the columns: the pairing is written on the card instead.
    page_anon.set_viewport_size({"width": 390, "height": 800})
    page_anon.wait_for_selector(f'[data-testid="pc-reach-{pcs[1]}"]')
    assert "Can strike: Wave Man" in page_anon.locator(f'[data-testid="pc-reach-{pcs[1]}"]').text_content()
    assert page_anon.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    # The GM's switch hides them everywhere.
    page.locator('[data-testid="show-reach"]').uncheck()
    page.wait_for_selector('[data-testid^="reach-line-"]', state="detached")
    page_anon.wait_for_selector(f'[data-testid="pc-reach-{pcs[1]}"]', state="hidden", timeout=15000)
    state = page_anon.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()
    assert state["reach"] == []


def test_an_npc_going_down_loses_its_striking_lines(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "DownLineA")
    _start_fight_with_wave_men(page, live_server_url, gid, count=2)
    page.set_viewport_size({"width": 1280, "height": 900})
    pc, npcs = int(_names(page, "pcs")[0]), [int(i) for i in _names(page, "npcs")]
    for npc in npcs:
        r = page.request.post(f"{live_server_url}/groups/{gid}/combat/reach",
                              data={"pc_id": pc, "npc_id": npc, "on": True})
        assert r.ok
    page.reload()
    page.wait_for_selector(f'[data-testid="reach-line-{pc}-{npcs[0]}"]', state="attached")
    page_anon.set_viewport_size({"width": 1280, "height": 900})
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    page_anon.wait_for_selector(f'[data-testid="reach-line-{pc}-{npcs[0]}"]', state="attached")

    # Wounds to the dying threshold, then "Down" in the prompt.
    _menu(page, npcs[0], "npc-adjust")
    page.fill('[data-testid="adjust-sw"]', "20")
    page.locator('[data-testid="adjust-save-btn"]').click()
    page.wait_for_selector('[data-testid="down-prompt"]')
    page.locator('[data-testid="down-unconscious"]').click()
    page.wait_for_selector(f'[data-testid="reach-line-{pc}-{npcs[0]}"]', state="detached")
    assert page.locator(f'[data-testid="reach-line-{pc}-{npcs[1]}"]').count() == 1  # the other NPC's stays
    page_anon.wait_for_selector(f'[data-testid="reach-line-{pc}-{npcs[0]}"]', state="detached", timeout=15000)
    assert page_anon.locator(f'[data-testid="reach-line-{pc}-{npcs[1]}"]').count() == 1


def test_a_player_rolls_initiative_and_sets_a_die_on_their_own_pc(page, page_nonadmin, live_server_url):
    """From the combat page a player uses their own PC's action dice with the
    sheet's own initiative roll and die menu - "Set value" included, to match
    physical dice - and gets no controls for anyone else's PC."""
    gid = _group_with_pc(page, live_server_url, "GmOwnedPC")
    _start_fight_with_wave_men(page, live_server_url, gid)
    gname = page.locator('[data-testid="group-nav-link"]').text_content().strip()
    create_and_apply(page_nonadmin, live_server_url, name="PlayerOwnedPC", school="akodo_bushi")
    page_nonadmin.goto(page_nonadmin.url + "/edit")
    page_nonadmin.wait_for_selector('select[name="gaming_group_id"]')
    page_nonadmin.locator('select[name="gaming_group_id"]').select_option(label=gname)
    page_nonadmin.wait_for_timeout(400)

    page_nonadmin.goto(f"{live_server_url}/groups/{gid}/combat")
    state = page_nonadmin.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()
    mine = next(p for p in state["pcs"] if p["name"] == "PlayerOwnedPC")
    theirs = next(p for p in state["pcs"] if p["name"] == "GmOwnedPC")
    assert mine.get("mine") is True and "mine" not in theirs
    assert page_nonadmin.locator(f'[data-testid="pc-init-{theirs["id"]}"]').count() == 0

    page_nonadmin.locator(f'[data-testid="pc-init-{mine["id"]}"]').click()
    frame = _roller(page_nonadmin)
    frame.locator('[data-modal="dice-roller"] button:has-text("×")').click(timeout=15000)
    _roller_gone(page_nonadmin)
    page_nonadmin.wait_for_selector(f'[data-testid="pc-die-{mine["id"]}-0"]')

    page_nonadmin.locator(f'[data-testid="pc-die-{mine["id"]}-0"]').click()
    _roller(page_nonadmin).locator('[data-action="action-die-set-value"]').select_option("10")
    _roller_gone(page_nonadmin)
    dice = page_nonadmin.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()
    dice = next(p for p in dice["pcs"] if p["id"] == mine["id"])["action_dice"]
    assert dice[-1]["value"] == 10
    assert page_nonadmin.request.get(
        f"{live_server_url}/groups/{gid}/combat/roller/{theirs['id']}").status == 403


def test_gm_sees_the_obsidian_portal_backport_outcome(page, live_server_url):
    # The clicktest server has no gm-assistant, so every build answers "off":
    # shown quietly, after generating and after a rename, and dismissable.
    gid = _group_with_pc(page, live_server_url, "BackportPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid, count=2)
    panel = page.locator('[data-testid="backport"]')
    expect(panel).to_be_visible()
    lines = panel.locator('[data-testid="backport-line"]')
    expect(lines).to_have_count(2)
    expect(lines.first).to_have_attribute("data-status", "off")
    expect(lines.first).to_contain_text("Obsidian Portal not updated")
    assert "text-ink/50" in lines.first.get_attribute("class")
    page.locator('[data-testid="backport-dismiss"]').click()
    expect(panel).to_be_hidden()
    _menu(page, npc_id, "npc-rename")
    page.fill('[data-testid="rename-input"]', "Tsuruchi Goro")
    page.locator('[data-testid="rename-save-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    expect(lines).to_have_count(1)
    expect(lines.first).to_contain_text("Tsuruchi Goro: Obsidian Portal not updated")
    # A gm-assistant answer that needs the GM's eye is not quiet.
    page.evaluate("""() => {
        const root = document.querySelector('[data-testid="backport"]').closest('[x-data]');
        Alpine.$data(root).backport = [{name: "A", status: "ambiguous", message: "A: several records"},
                                        {name: "B", status: "written", message: "B: added Air 4"}];
    }""")
    expect(lines).to_have_count(2)
    assert "text-accent" in lines.nth(0).get_attribute("class")
    assert "text-ink" in lines.nth(1).get_attribute("class")


def test_backport_panel_is_gm_only(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "BackportAnonPC")
    _start_fight_with_wave_men(page, live_server_url, gid)
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    page_anon.wait_for_selector('[data-testid^="npc-card-"], [data-testid^="public-npc"]', timeout=10000)
    assert page_anon.locator('[data-testid="backport"]').count() == 0 or \
        not page_anon.locator('[data-testid="backport"]').is_visible()


# ---------------------------------------------------------------------------
# A PC's attack target and weapon (combat_targets)
# ---------------------------------------------------------------------------

def _pc_in_fight(page, live_server_url, wave_men=2):
    """A group with one PC (the GM's own) in a fight with ``wave_men`` Wave
    Men, the PC within striking distance of the first only."""
    gid = _group_with_pc(page, live_server_url, "Striker")
    _start_fight_with_wave_men(page, live_server_url, gid, count=wave_men)
    state = _state(page, live_server_url, gid)
    pc, npcs = state["pcs"][0], state["npcs"]
    page.request.post(f"{live_server_url}/groups/{gid}/combat/reach",
                      data={"pc_id": pc["id"], "npc_id": npcs[0]["id"], "on": True})
    return gid, pc, npcs


def test_a_pcs_attack_starts_by_choosing_a_target_whose_tn_it_locks(page, page_anon, live_server_url):
    from tests.e2e.helpers import open_melee_attack

    gid, pc, npcs = _pc_in_fight(page, live_server_url)
    near, far = npcs
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    open_melee_attack(page)
    step = page.locator('[data-testid="atk-fight-step"]')
    expect(step).to_be_visible()
    picker = page.locator('[data-testid="atk-fight-target"]')
    options = picker.locator("option").all_text_contents()
    # Melee: only who the PC can reach, and no TN nobody has learned yet.
    assert options == ["- Choose a target -", f"{near['name']} (TN not yet known)"]
    expect(page.locator('[data-testid="atk-fight-out-of-reach"]')).to_contain_text(far["name"])
    picker.select_option(str(near["id"]))
    expect(page.locator('[data-testid="atk-fight-reveal-note"]')).to_contain_text("may not take the attack back")
    page.locator('[data-testid="atk-fight-confirm"]').click()

    expect(page.locator('[data-testid="atk-locked-target"]')).to_contain_text(near["name"])
    expect(page.locator('[data-testid="atk-locked-tn"]')).to_have_text(str(near["tn_to_be_hit"]))
    # Choosing it revealed the TN to everyone, on the combat page too.
    public = page_anon.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()
    assert next(n for n in public["npcs"] if n["id"] == near["id"])["tn_to_be_hit"] == near["tn_to_be_hit"]
    assert next(n for n in public["npcs"] if n["id"] == far["id"])["tn_to_be_hit"] is None

    force_dice(page, [9, 9, 9, 9, 9])
    page.locator('[data-action="roll-attack"]').click()
    expect(page.locator('[data-modal="attack"]')).to_contain_text(f"vs TN {near['tn_to_be_hit']}")
    restore_dice(page)

    # A known TN is listed from then on; "Change target" goes back to the list.
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    open_melee_attack(page)
    expect(page.locator('[data-testid="atk-fight-target"] option').nth(1)).to_have_text(
        f"{near['name']} (TN {near['tn_to_be_hit']})")
    page.locator('[data-testid="atk-fight-target"]').select_option(str(near["id"]))
    expect(page.locator('[data-testid="atk-fight-reveal-note"]')).to_be_hidden()
    page.locator('[data-testid="atk-fight-confirm"]').click()
    page.locator('[data-testid="atk-change-target"]').click()
    expect(step).to_be_visible()
    # "Not one of these" is the ordinary TN picker.
    page.locator('[data-testid="atk-fight-skip"]').click()
    expect(page.locator('[data-testid="atk-locked-target"]')).to_be_hidden()
    expect(page.locator('[data-testid="atk-choose-target"]')).to_be_visible()


def test_an_arrow_may_target_anyone_in_the_fight(page, live_server_url):
    from tests.e2e.helpers import open_archery_attack

    gid, pc, npcs = _pc_in_fight(page, live_server_url)
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    open_archery_attack(page)
    picker = page.locator('[data-testid="atk-fight-target"]')
    expect(picker.locator("option")).to_have_count(3)  # the placeholder and both Wave Men
    expect(page.locator('[data-testid="atk-fight-out-of-reach"]')).to_be_hidden()
    picker.select_option(str(npcs[1]["id"]))
    page.locator('[data-testid="atk-fight-confirm"]').click()
    base = page.locator('[data-testid="archery-base-tn"]')
    expect(base).to_be_disabled()
    expect(base).to_have_value(str(npcs[1]["tn_to_be_hit"]))


def test_the_gm_sets_a_pcs_weapon_for_the_fight(page, live_server_url):
    from tests.e2e.helpers import open_melee_attack

    gid, pc, npcs = _pc_in_fight(page, live_server_url, wave_men=1)
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    page.locator(f'[data-testid="pc-menu-{pc["id"]}"]').click()
    page.fill(f'[data-testid="pc-weapon-rolled-{pc["id"]}"]', "5")
    page.fill(f'[data-testid="pc-weapon-kept-{pc["id"]}"]', "3")
    page.locator(f'[data-testid="pc-weapon-set-{pc["id"]}"]').click()
    expect(page.locator(f'[data-testid="pc-weapon-{pc["id"]}"]')).to_have_text("Weapon 5k3")

    page.goto(f"{live_server_url}/characters/{pc['id']}")
    open_melee_attack(page)
    page.locator('[data-testid="atk-fight-target"]').select_option(str(npcs[0]["id"]))
    page.locator('[data-testid="atk-fight-confirm"]').click()
    rolled, kept = page.locator('[data-testid="atk-weapon-rolled"]'), page.locator('[data-testid="atk-weapon-kept"]')
    expect(rolled).to_be_disabled()
    expect(rolled).to_have_value("5")
    expect(kept).to_have_value("3")
    expect(page.locator('[data-testid="atk-weapon-locked"]')).to_be_visible()

    # Cleared, the modal's own inputs are back.
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    page.locator(f'[data-testid="pc-menu-{pc["id"]}"]').click()
    page.locator(f'[data-testid="pc-weapon-clear-{pc["id"]}"]').click()
    expect(page.locator(f'[data-testid="pc-weapon-{pc["id"]}"]')).to_be_hidden()
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    open_melee_attack(page)
    page.locator('[data-testid="atk-fight-skip"]').click()
    expect(page.locator('[data-testid="atk-weapon-rolled"]')).to_be_enabled()


def test_the_gm_puts_a_pc_in_a_duel_and_their_duel_and_stance_rolls_know_the_opponent(
        page, page_anon, live_server_url):
    from tests.e2e.test_iaijutsu_duel import _open_duel_modal, _wait_dice_done

    gid, pc, (npc,) = _pc_in_fight(page, live_server_url, wave_men=1)
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    page.locator(f'[data-testid="pc-menu-{pc["id"]}"]').click()
    page.locator(f'[data-testid="pc-duel-{pc["id"]}"]').select_option(str(npc["id"]))
    expect(page.locator(f'[data-testid="pc-dueling-{pc["id"]}"]')).to_have_text(
        f"In an iaijutsu duel with {npc['name']}")
    expect(page.locator(f'[data-testid="npc-dueling-{npc["id"]}"]')).to_have_text(
        "In an iaijutsu duel with Striker")
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    expect(page_anon.locator(f'[data-testid="pc-dueling-{pc["id"]}"]')).to_be_visible()

    # The duel modal: no XP to enter, the NPC's TN instead.
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    _open_duel_modal(page)
    duel_tn = npc["total_xp"] // 10
    expect(page.locator('[data-testid="duel-fight-opponent-tn"]')).to_have_text(str(duel_tn))
    modal = page.locator('[data-modal="iaijutsu-duel"]')
    expect(modal.locator('button:has-text("Proceed to Contested Roll")')).to_be_enabled()
    modal.locator('button:has-text("×")').click()

    # Evaluate Stance: what this roll tells about that opponent.
    force_dice(page, [1, 1, 1, 1, 1, 1])
    page.locator('[data-roll-key="knack:iaijutsu"]').click()
    page.locator('[data-action="evaluate-stance"]').click()
    _wait_dice_done(page)
    restore_dice(page)
    known = page.locator('[data-testid="evaluate-stance-known"]')
    expect(known).to_be_visible()
    expect(page.locator('[data-testid="evaluate-stance-known-fire"]')).to_contain_text(f"{npc['name']}'s Fire Ring: at least", use_inner_text=True)
    expect(page.locator('[data-testid="evaluate-stance-known-tn"]')).to_contain_text("at least", use_inner_text=True)
    expect(page.locator('[data-testid="evaluate-stance-known-tn"]')).not_to_contain_text("exactly", use_inner_text=True)
    expect(page.locator('[data-testid="evaluate-stance-fire"]')).to_be_hidden()

    # Ending the duel puts the XP input back.
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    page.locator(f'[data-testid="pc-menu-{pc["id"]}"]').click()
    page.locator(f'[data-testid="pc-duel-{pc["id"]}"]').select_option("")
    expect(page.locator(f'[data-testid="pc-dueling-{pc["id"]}"]')).to_be_hidden()


@pytest.mark.parametrize("side", ["pc", "npc"])
def test_a_can_strike_flyout_stays_open_while_the_pointer_crosses_to_it(page, live_server_url, side):
    """The flyout sits beside the kebab menu; moving the pointer slowly from
    "Can strike" into it must never pass over a strip that belongs to
    neither (that strip used to close the flyout)."""
    gid, pc, (npc,) = _pc_in_fight(page, live_server_url, wave_men=1)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    me, other = (pc, npc) if side == "pc" else (npc, pc)
    page.locator(f'[data-testid="{side}-menu-{me["id"]}"]').click()
    item = page.locator(f'[data-testid="{side}-can-strike-{me["id"]}"]')
    item.hover()
    flyout = page.locator(f'[data-testid="{side}-can-strike-flyout-{me["id"]}"]')
    expect(flyout).to_be_visible()
    pair = (me["id"], other["id"]) if side == "pc" else (other["id"], me["id"])
    box = page.locator(f'[data-testid="{side}-card-{me["id"]}"] [data-testid="reach-{pair[0]}-{pair[1]}"]')
    start, end = item.bounding_box(), box.bounding_box()
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    # Slowly, one small step at a time, to the checkbox.
    page.mouse.move(end["x"] + end["width"] / 2, end["y"] + end["height"] / 2, steps=60)
    expect(flyout).to_be_visible()
    box.check()
    expect(box).to_be_checked()


# ---------------------------------------------------------------------------
# The fight's phase
# ---------------------------------------------------------------------------

def _school_pc_in_fight(page, live_server_url, name, school, knacks=None, skills=None):
    """A fresh group whose one PC is ``name`` of ``school`` (knack ranks
    ``knacks``), in a fight with one Wave Man it can strike."""
    from tests.e2e.test_school_abilities import _create_char

    gname = "Fight-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    _create_char(page, live_server_url, name, school, knack_overrides=knacks, skill_overrides=skills)
    sheet = page.url
    page.goto(sheet + "/edit")
    page.wait_for_selector('select[name="gaming_group_id"]')
    page.locator('select[name="gaming_group_id"]').select_option(label=gname)
    page.wait_for_timeout(400)
    page.goto(live_server_url)
    page.locator('[data-testid="group-link"]', has_text=gname).first.click()
    page.wait_for_url(re.compile(r".*/groups/\d+$"))
    gid = int(page.url.rstrip("/").split("/")[-1])
    _start_fight_with_wave_men(page, live_server_url, gid, count=1)
    state = _state(page, live_server_url, gid)
    pc, npc = state["pcs"][0], state["npcs"][0]
    page.request.post(f"{live_server_url}/groups/{gid}/combat/reach",
                      data={"pc_id": pc["id"], "npc_id": npc["id"], "on": True})
    return gid, pc, npc


def _set_dice(page, live_server_url, char_id, dice):
    """Save action dice on a character (the sheet bridge's test-setup save)."""
    import json as _json

    page.goto(f"{live_server_url}/characters/{char_id}")
    page.wait_for_function("() => window._trackingBridge")
    page.evaluate(f"""async () => {{
        const t = window._trackingBridge;
        t.actionDice = {_json.dumps(dice)};
        await t.save();
        await t.whenSaved();
    }}""")


def _phase(page, live_server_url, gid, delta):
    page.request.post(f"{live_server_url}/groups/{gid}/combat/phase", data={"delta": delta})


def test_the_gm_moves_the_phase_and_players_see_it(page, page_anon, live_server_url):
    gid, pc, npcs = _pc_in_fight(page, live_server_url, wave_men=1)
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    phase = page.locator('[data-testid="combat-phase"]')
    expect(phase).to_have_text("Phase 0")
    expect(page.locator('[data-testid="phase-back"]')).to_be_disabled()
    page.locator('[data-testid="phase-next"]').click()
    page.locator('[data-testid="phase-next"]').click()
    expect(phase).to_have_text("Phase 2")
    page.locator('[data-testid="phase-back"]').click()
    expect(phase).to_have_text("Phase 1")
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    expect(page_anon.locator('[data-testid="combat-phase"]')).to_have_text("Phase 1")
    assert page_anon.locator('[data-testid="phase-next"]').count() == 0
    page.locator('[data-testid="new-round-btn"]').click()
    expect(phase).to_have_text("Phase 0")


def test_a_kakita_attacks_in_the_fights_phase_knowing_the_targets_next_action(page, live_server_url):
    from tests.e2e.helpers import open_melee_attack

    gid, pc, npc = _school_pc_in_fight(page, live_server_url, "PhaseKakita", "kakita_duelist",
                                       knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    _set_dice(page, live_server_url, npc["id"], [{"value": 8, "spent": False}])
    _set_dice(page, live_server_url, pc["id"], [{"value": 2, "spent": False}])
    for _ in range(5):
        _phase(page, live_server_url, gid, 1)

    page.goto(f"{live_server_url}/characters/{pc['id']}")
    open_melee_attack(page)
    page.locator('[data-testid="atk-fight-target"]').select_option(str(npc["id"]))
    page.locator('[data-testid="atk-fight-confirm"]').click()
    kakita = page.locator('[data-testid="kakita-3rd-dan-bonus"]')
    expect(kakita).to_contain_text("Kakita 3rd Dan: phase")
    expect(page.locator('[data-testid="kakita-3rd-dan-attacker-phase"]')).to_have_text("5")
    expect(page.locator('[data-testid="kakita-3rd-dan-known-phase"]')).to_have_text("8")
    expect(page.locator('[data-action="kakita-3rd-dan-defender-phase"]')).to_be_hidden()
    expect(page.locator('[data-testid="kakita-3rd-dan-bonus-display"]')).to_contain_text("+3")  # X = attack 1

    force_dice(page, [9, 9, 9, 9, 9])
    page.locator('[data-action="roll-attack"]').click()
    expect(page.locator('[data-testid="kakita-3rd-dan-breakdown"]')).to_contain_text("phase 5, defender phase 8")
    restore_dice(page)


def test_a_mantis_waits_for_the_gms_phase_and_the_combat_page_shows_the_posture(page, page_anon, live_server_url):
    gid, pc, npc = _school_pc_in_fight(page, live_server_url, "PhaseMantis", "mantis_wave_treader")
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    page.locator('[data-action="mantis-posture-offensive"]').click()
    expect(page.get_by_text("your posture for phase 1 can be chosen once the GM reaches it")).to_be_visible()
    expect(page.locator('[data-action="mantis-posture-offensive"]')).to_contain_text("for Phase 1")

    _phase(page, live_server_url, gid, 1)
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    line = page_anon.locator(f'[data-testid="pc-phase-posture-{pc["id"]}"]')
    expect(line).to_contain_text("not yet chosen")
    page.reload()
    page.locator('[data-action="mantis-posture-offensive"]').click()
    expect(page.locator('[data-action="mantis-posture-offensive"]')).to_contain_text("for Phase 2")
    expect(line).to_contain_text("Posture this phase: offensive", timeout=10000)  # the page polls


def test_a_priest_blesses_the_current_phase_on_the_combat_page(page, page_anon, live_server_url):
    gid, pc, npc = _school_pc_in_fight(page, live_server_url, "PhasePriest", "priest")
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    line = page.locator(f'[data-testid="pc-phase-blessing-{pc["id"]}"]')
    expect(line).to_contain_text("not yet chosen")
    page.locator(f'[data-testid="pc-blessing-{pc["id"]}"]').select_option("wound_check")
    expect(line).to_contain_text("Blessing this phase: wound checks")
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    anon_line = page_anon.locator(f'[data-testid="pc-phase-blessing-{pc["id"]}"]')
    expect(anon_line).to_contain_text("wound checks")
    assert page_anon.locator(f'[data-testid="pc-blessing-{pc["id"]}"]').count() == 0
    page.locator('[data-testid="phase-next"]').click()
    expect(line).to_contain_text("not yet chosen")


def _raises_left(page):
    return page.evaluate("() => window._trackingBridge.getCount('adventure_raises')")


def test_a_kitsune_warden_blesses_a_phase_and_performs_rituals_for_free_raises(page, page_anon, live_server_url):
    gid, pc, npc = _school_pc_in_fight(page, live_server_url, "PhaseKitsune", "kitsune_warden",
                                       knacks={"absorb_void": 3, "commune": 3, "iaijutsu": 3},
                                       skills={"precepts": 2})
    # Optional: no "not yet chosen" line on the card.
    page.goto(f"{live_server_url}/groups/{gid}/combat")
    line = page.locator(f'[data-testid="pc-phase-blessing-{pc["id"]}"]')
    expect(line).to_be_hidden()
    page.locator(f'[data-testid="pc-menu-{pc["id"]}"]').click()
    page.locator(f'[data-testid="pc-optional-blessing-{pc["id"]}"]').select_option("damage")
    expect(line).to_contain_text("Blessing this phase: damage")
    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    expect(page_anon.locator(f'[data-testid="pc-phase-blessing-{pc["id"]}"]')).to_contain_text("damage")

    # The sheet: one raise spent already; the rituals say what they cost.
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    page.wait_for_function("() => window._trackingBridge")
    used = page.evaluate("() => window._trackingBridge.getCount('adventure_raises')")
    expect(page.locator('[data-testid="kitsune-ritual-cost"]')).to_contain_text("one 3rd Dan free raise")
    page.locator('[data-action="bless-conversation"]').click()
    page.wait_for_function("() => window._diceRoller && window._diceRoller.phase === 'done'")
    assert page.evaluate("() => window._trackingBridge.getCount('adventure_raises')") == used + 1
    page.locator('[data-modal="dice-roller"] button:has-text("×")').click()

    # Bless this combat phase from the sheet: the fight's phase, a changed pick.
    _phase(page, live_server_url, gid, 1)
    page.locator('[data-action="sheet-phase-blessing-kind"]').select_option("wound_check")
    page.locator('[data-action="sheet-phase-blessing"]').click()
    expect(page.locator('[data-testid="sheet-phase-blessing-note"]')).to_have_text("Phase 1 blessed: wound checks.")
    assert page.evaluate("() => window._trackingBridge.getCount('adventure_raises')") == used + 2
    expect(page_anon.locator(f'[data-testid="pc-phase-blessing-{pc["id"]}"]')).to_contain_text(
        "wound checks", timeout=10000)


def test_a_shinjos_parry_in_a_fight_is_spent_at_the_fights_phase(page, live_server_url):
    gid, pc, npc = _school_pc_in_fight(page, live_server_url, "PhaseShinjo", "shinjo_bushi")
    _set_dice(page, live_server_url, pc["id"], [{"value": 2, "spent": False}])
    for _ in range(6):
        _phase(page, live_server_url, gid, 1)
    page.goto(f"{live_server_url}/characters/{pc['id']}")
    page.wait_for_function("() => window._trackingBridge")
    from tests.e2e.test_school_abilities import _roll_via_menu_or_direct

    _roll_via_menu_or_direct(page, "parry")
    expect(page.locator('[data-testid="shinjo-parry-fight-phase"]')).to_have_text("6")
    expect(page.locator('[data-testid="shinjo-parry-phase-bonus-display"]')).to_contain_text("+8")
    expect(page.locator('[data-action="shinjo-parry-phase"]')).to_be_hidden()
