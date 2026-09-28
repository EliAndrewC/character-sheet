"""E2E: the GM combat tracker, generated NPCs, and the public combat page
(combat-design/design.md)."""

import re
import uuid

import pytest

from tests.e2e.helpers import create_and_apply

pytestmark = [pytest.mark.combat]


def _group_with_pc(page, live_server_url, pc_name):
    """A fresh group with one visible PC in it. Returns the group id."""
    gname = "Fight-" + uuid.uuid4().hex[:8]
    page.goto(f"{live_server_url}/admin/groups")
    page.fill('input[name="name"][placeholder*="Friday"]', gname)
    page.locator('form[action="/admin/groups/new"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    create_and_apply(page, live_server_url, name=pc_name, school="akodo_bushi")
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


def test_gm_generates_npcs_and_one_attacks_a_pc(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "TargetPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid, count=2)
    assert page.locator('[data-testid^="npc-card-"]').count() == 2
    assert "Wave Man 1" in page.locator('[data-testid="npc-section"]').text_content()
    assert "50 earned XP" in page.locator(f'[data-testid="npc-card-{npc_id}"]').text_content()

    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_selector(f'[data-testid="npc-die-{npc_id}-0"]')
    assert "Round 1" in page.locator('[data-testid="combat-round"]').text_content()

    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    page.locator('[data-testid="menu-attack-attack"]').click()
    pc = next(p for p in _state(page, live_server_url, gid)["pcs"] if p["name"] == "TargetPC")
    page.locator(f'[data-testid="target-{pc["id"]}"]').click()
    # The TN is pre-filled from the target and editable (D19).
    assert page.input_value('[data-testid="attack-tn"]') == str(pc["tn_to_be_hit"])
    page.fill('[data-testid="attack-tn"]', "1")  # make sure it hits
    page.locator('[data-testid="attack-roll-btn"]').click()
    page.wait_for_selector('[data-testid="attack-result"]')
    assert "hit" in page.locator('[data-testid="attack-result"]').text_content()
    page.locator('[data-testid="parry-failed"]').check()
    assert page.input_value('[data-testid="parry-skill"]') == str(pc["parry"])
    page.locator('[data-testid="damage-roll-btn"]').click()
    page.wait_for_selector('[data-testid="damage-result"]')
    assert re.search(r"\d+ damage", page.locator('[data-testid="damage-result"]').text_content())

    page.keyboard.press("Escape")
    die = page.locator(f'[data-testid="npc-die-{npc_id}-0"]')
    assert die.is_disabled()
    log = page.locator('[data-testid="action-log"]').text_content()
    assert "on TargetPC" in log and "damage" in log
    # The PC's wounds are the player's to enter (D19): the tracker wrote nothing.
    pc_after = next(p for p in _state(page, live_server_url, gid)["pcs"] if p["name"] == "TargetPC")
    assert (pc_after["light_wounds"], pc_after["serious_wounds"]) == (0, 0)


def test_npc_parries_and_spends_a_die_on_something_else(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "SwordPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_selector(f'[data-testid="npc-die-{npc_id}-0"]')
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    page.locator('[data-testid="menu-parry"]').click()
    page.fill('[data-testid="parry-attack-total"]', "5")
    page.locator('[data-testid="parry-predeclared"]').check()
    page.locator('[data-testid="parry-roll-btn"]').click()
    page.wait_for_selector('[data-testid="parry-result"]')
    assert "parried" in page.locator('[data-testid="parry-result"]').text_content()
    page.keyboard.press("Escape")
    dice = _state(page, live_server_url, gid)["npcs"][0]["action_dice"]
    if len(dice) > 1:
        page.locator(f'[data-testid="npc-die-{npc_id}-1"]').click()
        page.locator('[data-testid="menu-other"]').click()
        page.fill('[data-testid="other-label"]', "Moves to the bridge")
        page.locator('[data-testid="other-btn"]').click()
        page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
        assert "Moves to the bridge" in page.locator('[data-testid="action-log"]').text_content()


def test_npc_takes_damage_and_goes_down(page, live_server_url):
    gid = _group_with_pc(page, live_server_url, "HitterPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    page.locator(f'[data-testid="npc-took-damage-{npc_id}"]').click()
    page.fill('[data-testid="damage-amount"]', "12")
    page.locator('[data-testid="wound-check-btn"]').click()
    page.wait_for_selector('[data-testid="wound-check-result"]')
    result = page.locator('[data-testid="wound-check-result"]').text_content()
    assert "Wound check" in result
    if "passed" in result:
        page.locator('[data-testid="take-sw-btn"]').click()
    page.wait_for_function(
        f"document.querySelector('[data-testid=\"npc-sw-{npc_id}\"]').textContent !== '0'")
    if page.locator('[data-testid="combat-dialog"]').count():
        page.keyboard.press("Escape")

    # Adjusting serious wounds to 2 x Earth asks unconscious or dead (D9).
    page.locator(f'[data-testid="npc-adjust-{npc_id}"]').click()
    page.fill('[data-testid="adjust-sw"]', "20")
    page.locator('[data-testid="adjust-save-btn"]').click()
    page.wait_for_selector('[data-testid="down-prompt"]')
    page.locator('[data-testid="down-dead"]').click()
    page.wait_for_selector('[data-testid="down-prompt"]', state="detached")
    assert page.input_value(f'[data-testid="npc-status-{npc_id}"]') == "dead"


def test_public_view_shows_totals_but_not_how(page, page_anon, live_server_url):
    gid = _group_with_pc(page, live_server_url, "WatcherPC")
    npc_id = _start_fight_with_wave_men(page, live_server_url, gid)
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_selector(f'[data-testid="npc-die-{npc_id}-0"]')
    page.locator(f'[data-testid="npc-die-{npc_id}-0"]').click()
    page.locator('[data-testid="menu-other"]').click()
    page.fill('[data-testid="other-label"]', "Taunts")
    page.locator('[data-testid="other-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    page.locator('[data-testid="new-round-btn"]').click()
    page.wait_for_function("document.querySelector('[data-testid=\"combat-round\"]').textContent.includes('Round 2')")

    page_anon.goto(f"{live_server_url}/groups/{gid}/combat")
    card = page_anon.locator(f'[data-testid="npc-card-{npc_id}"]')
    assert "Wave Man 1" in card.text_content()
    assert "Last round: 1 action" in card.text_content()
    # GM-only markup sits in <template x-if="gm"> blocks that never render
    # here; nothing of it reaches the page's text or elements.
    shown = card.text_content()
    for secret in ("Void", "earned XP", "% combat", "Took damage", "Roll initiative"):
        assert secret not in shown, secret
    assert page_anon.locator('[data-testid^="npc-die-"]').count() == 0
    # The public poll carries no dice, void or stats.
    state = page_anon.request.get(f"{live_server_url}/groups/{gid}/combat/state").json()
    assert set(state["npcs"][0]) == {
        "id", "name", "light_wounds", "serious_wounds", "down",
        "actions_this_round", "actions_last_round",
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
    page.locator(f'[data-testid="npc-rebuild-{npc_id}"]').click()
    page.fill('[data-testid="rebuild-xp"]', "150")
    page.fill('[data-testid="rebuild-share"]', "85")
    page.locator('[data-testid="rebuild-save-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    card = page.locator(f'[data-testid="npc-card-{npc_id}"]')
    assert "150 earned XP, 85% combat" in card.text_content()
    page.locator(f'[data-testid="npc-rename-{npc_id}"]').click()
    page.fill('[data-testid="rename-input"]', "Big Goro")
    page.locator('[data-testid="rename-save-btn"]').click()
    page.wait_for_selector('[data-testid="combat-dialog"]', state="detached")
    assert page.locator(f'[data-testid="npc-name-{npc_id}"]').text_content() == "Big Goro"


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
