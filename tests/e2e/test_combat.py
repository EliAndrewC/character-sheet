"""E2E: the GM combat tracker, generated NPCs, and the public combat page
(combat-design/design.md)."""

import re
import uuid

import pytest

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
        "actions_this_round", "spent_dice", "unknown_dice", "tn_to_be_hit", "impaired",
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
    assert "150 earned XP, 85% combat" in card.text_content()
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
    pc_name = f'[data-testid="pc-card-{pc_id}"] span.font-semibold'
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
    assert page_anon.locator(f'[data-testid="npc-actions-{npc_id}"]').text_content().strip() == ""

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
    assert "50 earned XP" in build.text_content() and not build.is_visible()
    for gone in ("Took damage", "Roll initiative", "Adjust", "Rebuild", "Rename", "Leave fight"):
        assert gone not in card.inner_text(), gone
    page.locator(f'[data-testid="npc-menu-{npc_id}"]').click()
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
