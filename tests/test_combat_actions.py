"""Server-side NPC actions, the combat page's state, and its routes
(app/services/combat_actions.py, combat_view.py, app/routes/combat.py)."""

import random

import pytest

from app.models import Character, Encounter, EncounterAction, GamingGroup, RollHistory
from app.services import combat_actions as ca
from app.services import combat_view as cv
from app.services import npcs
from app.services.per_adventure import per_adventure_abilities, remaining

GM = "183026066498125825"
PLAYER = {"X-Test-User": "test_user_1:player"}


class ConstRng:
    """Every die shows ``value`` (never 10, so nothing explodes)."""

    def __init__(self, value=5):
        self.value = value

    def randint(self, a, b):
        return self.value


@pytest.fixture
def world(client):
    """A group with one visible PC, one hidden PC, an active fight and one Wave Man."""
    s = client._test_session_factory()
    g = GamingGroup(name="Tuesday")
    s.add(g)
    s.flush()
    pc = Character(name="Yudai", owner_discord_id="test_user_1", gaming_group_id=g.id,
                   school="akodo_bushi", school_ring_choice="Water", parry=3, ring_earth=2,
                   knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
    hidden = Character(name="Secret", owner_discord_id="test_user_1", gaming_group_id=g.id, is_hidden=True)
    s.add_all([pc, hidden])
    s.flush()
    enc = npcs.start_encounter(s, g.id, "Ambush")
    (npc,) = npcs.generate(s, g, enc, GM, [{"npc_type": "wave_man", "count": 1, "earned_xp": 50,
                                            "roll_extra": False, "combat_share": 0.74}])
    s.commit()
    yield {"s": s, "g": g, "pc": pc, "hidden": hidden, "enc": enc, "npc": npc}
    s.close()


def _dice(npc, values=(3, 7)):
    npc.action_dice = [{"value": v, "spent": False} for v in values]


# ---------------------------------------------------------------------------
# Service: helpers
# ---------------------------------------------------------------------------

def test_attack_options_put_the_plain_attack_first(world):
    s = world["s"]
    g, enc = world["g"], world["enc"]
    (kakita,) = npcs.generate(s, g, enc, GM, [{"npc_type": "kakita_duelist", "count": 1,
                                               "earned_xp": 100, "roll_extra": False}])
    keys = [o["key"] for o in ca.attack_options(kakita)]
    assert keys[0] == "attack" and "knack:double_attack" in keys
    assert ca.tn_to_be_hit(world["pc"]) == 20


@pytest.mark.parametrize("indices,message", [
    (["x"], "pick an action die"),
    ([5], "not available"),
    ([0, 0], "not available"),
    ([], "pick an action die"),
])
def test_spend_dice_refuses(world, indices, message):
    npc = world["npc"]
    _dice(npc)
    with pytest.raises(ca.ActionError, match=message):
        ca._spend_dice(npc, indices)


def test_spend_dice_refuses_a_spent_die(world):
    npc = world["npc"]
    npc.action_dice = [{"value": 3, "spent": True}]
    with pytest.raises(ca.ActionError):
        ca._spend_dice(npc, [0])


def test_void_refusals(world, monkeypatch):
    npc = world["npc"]
    with pytest.raises(ca.ActionError, match="cannot spend void"):
        ca._plan(npc, {"void_blocked": True}, 1, "Attack")
    with pytest.raises(ca.ActionError):
        ca._plan(npc, {}, 99, "Attack")
    monkeypatch.setattr(ca, "formulas", lambda c: {})
    with pytest.raises(ca.ActionError, match="no parry roll"):
        ca._roll(world["s"], npc, GM, "parry", 0, rng=None)


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------

def test_new_round_rolls_for_fighters_and_clears_the_downed(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    g = world["g"]
    (down,) = npcs.generate(s, g, enc, GM, [{"npc_type": "wave_man", "count": 1}])
    npcs.set_status(s, enc, down, "dead")
    down.action_dice = [{"value": 4, "spent": False}]
    rolled = ca.new_round(s, enc, GM, rng=ConstRng(4))
    assert enc.current_round == 1
    assert list(rolled) == [npc.id]
    assert npc.action_dice and all(d["spent"] is False for d in npc.action_dice)
    assert down.action_dice == []
    assert s.query(RollHistory).filter_by(character_id=npc.id, roll_key="initiative").count() == 1


# ---------------------------------------------------------------------------
# Attack and damage
# ---------------------------------------------------------------------------

def test_attack_needs_a_real_attack_and_a_tn(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    with pytest.raises(ca.ActionError, match="no knack:lunge attack"):
        ca.attack(s, enc, npc, GM, roll_key="knack:lunge", die=0, target=None, tn=10)
    with pytest.raises(ca.ActionError, match="target or give a TN"):
        ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=None, tn=None)


def test_a_hit_on_the_target_tn_then_failed_parry_damage(world):
    s, enc, npc, pc = world["s"], world["enc"], world["npc"], world["pc"]
    _dice(npc)
    out = ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=pc, tn=None, rng=ConstRng(9))
    assert out["tn"] == 20
    action = s.get(EncounterAction, out["action_id"])
    assert action.target_character_id == pc.id and action.round == 0
    assert npc.action_dice[0]["spent"] is True
    if not out["hit"]:  # pragma: no cover - a 9s attack from a 50-XP Wave Man beats 20
        pytest.skip("did not hit")
    dmg = ca.damage(s, enc, action, GM, parry="failed", rng=ConstRng(5))
    assert dmg["outcome"] == "hit" and dmg["damage"] > 0
    assert action.detail["parry"] == "failed" and action.detail["damage"] == dmg["damage"]
    assert any("from failed parry" in p for p in dmg["payload"]["extras"])  # parry skill 3 from the target
    with pytest.raises(ca.ActionError, match="already resolved"):
        ca.damage(s, enc, action, GM)


def test_a_miss_rolls_no_damage(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    out = ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=None, tn=999, rng=ConstRng(1))
    assert out["hit"] is False and out["extra_dice"] == 0
    action = s.get(EncounterAction, out["action_id"])
    assert action.detail["outcome"] == "missed"
    with pytest.raises(ca.ActionError, match="only a hit"):
        ca.damage(s, enc, action, GM)


def test_parried_and_bad_damage_requests(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    out = ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=None, tn=0, rng=ConstRng(5))
    action = s.get(EncounterAction, out["action_id"])
    with pytest.raises(ca.ActionError, match="none, failed or parried"):
        ca.damage(s, enc, action, GM, parry="maybe")
    with pytest.raises(ca.ActionError, match="unknown weapon"):
        ca.damage(s, enc, action, GM, weapon="bazooka")
    assert ca.damage(s, enc, action, GM, parry="parried") == {"outcome": "parried"}
    with pytest.raises(ca.ActionError, match="already resolved"):
        ca.damage(s, enc, action, GM)


def test_no_target_means_no_parry_reduction(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    out = ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=None, tn=0, rng=ConstRng(5))
    action = s.get(EncounterAction, out["action_id"])
    dmg = ca.damage(s, enc, action, GM, parry="failed", rng=ConstRng(5))
    assert "-0k0 from failed parry" in dmg["payload"]["extras"]


def _patch_attack(monkeypatch, **extra):
    real = ca.formulas

    def patched(c):
        f = real(c)
        f["attack"] = dict(f["attack"], **extra)
        return f
    monkeypatch.setattr(ca, "formulas", patched)


def test_double_attack_excess_is_over_the_unraised_tn(world, monkeypatch):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    _patch_attack(monkeypatch, attack_variant="double_attack")
    out = ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=None, tn=0, rng=ConstRng(9))
    detail = s.get(EncounterAction, out["action_id"]).detail
    assert detail["effective_tn"] == 20
    raw = detail["raw_total"]
    assert out["hit"] == (raw >= 20)
    if out["hit"]:
        assert out["extra_dice"] == raw // 5


def test_wave_man_miss_raise_lands_without_extra_dice(world, monkeypatch):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    _patch_attack(monkeypatch, wave_man_miss_raise=2, wave_man_round_damage=1, shosuro_5th_dan=True)
    probe = ca.formulas(npc)["attack"]
    raw = probe["kept"] * 5 + (probe.get("flat") or 0)
    out = ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=None, tn=raw + 3, rng=ConstRng(5))
    assert out["hit"] and out["total"] == raw + 5 and out["extra_dice"] == 0
    action = s.get(EncounterAction, out["action_id"])
    assert action.detail["wave_man_raises"] == 1
    dmg = ca.damage(s, enc, action, GM, rng=ConstRng(5))
    assert dmg["damage"] % 5 == 3  # all-5s damage is a multiple of 5, so W4 adds 3
    extras = dmg["payload"]["extras"]
    assert any("lowest 3 dice" in e for e in extras) and any("rounded to" in e for e in extras)


# ---------------------------------------------------------------------------
# Parry, other
# ---------------------------------------------------------------------------

def test_parry_success_interrupt_and_predeclared(world):
    s, enc, npc, pc = world["s"], world["enc"], world["npc"], world["pc"]
    _dice(npc, (2, 5, 9))
    with pytest.raises(ca.ActionError, match="one action die, or two"):
        ca.parry(s, enc, npc, GM, dice=[0, 1, 2], attack_total=10)
    out = ca.parry(s, enc, npc, GM, dice=[0, 1], attack_total=1, predeclared=True,
                   attacker=pc, rng=ConstRng(5))
    assert out["success"]
    action = s.get(EncounterAction, out["action_id"])
    assert action.kind == "parry" and action.detail["interrupt"] is True
    assert action.detail["dice"] == [2, 5] and action.target_character_id == pc.id
    assert s.get(RollHistory, action.roll_history_id).payload["total"] == out["total"]
    miss = ca.parry(s, enc, npc, GM, dice=[2], attack_total=999, rng=ConstRng(1))
    assert miss["success"] is False


def test_other_action_logs_its_label(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    _dice(npc)
    out = ca.other(s, enc, npc, die=0, label="  ")
    assert s.get(EncounterAction, out["action_id"]).label == "Action"


def test_tn_to_be_hit_is_public_once_the_npc_was_attacked(world):
    """Unknown to players until the NPC has taken damage or parried in this
    fight: either one means somebody attacked it."""
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] is None
    _dice(npc, (2, 5, 9))
    ca.parry(s, enc, npc, GM, dice=[0], attack_total=10, rng=ConstRng(5))
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] == ca.tn_to_be_hit(npc)


def test_tn_to_be_hit_is_public_once_the_npc_has_wounds(world):
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    ca.take_damage(s, enc, npc, GM, amount=5, rng=ConstRng(9))
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] == ca.tn_to_be_hit(npc)
    ca.set_tracking(s, enc, npc, light=0, serious=0)  # the GM undoing a mistake
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] is None


# ---------------------------------------------------------------------------
# Wounds
# ---------------------------------------------------------------------------

def test_take_damage_failed_check(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    with pytest.raises(ca.ActionError, match="positive"):
        ca.take_damage(s, enc, npc, GM, amount=0)
    out = ca.take_damage(s, enc, npc, GM, amount=200, rng=ConstRng(1))
    assert not out["passed"] and out["serious_wounds_taken"] >= 1
    assert npc.current_light_wounds == 0 and npc.current_serious_wounds == out["serious_wounds_taken"]
    assert out["down_prompt"] is True  # a huge failure passes 2 x Earth


def test_take_damage_passed_then_take_a_serious_wound(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    out = ca.take_damage(s, enc, npc, GM, amount=1, rng=ConstRng(5))
    assert out["passed"] and out["choice_needed"] and npc.current_light_wounds == 1
    assert ca.take_serious_wound(s, enc, npc) == {"down_prompt": False}
    assert (npc.current_light_wounds, npc.current_serious_wounds) == (0, 1)


def test_set_tracking(world):
    s, enc, npc = world["s"], world["enc"], world["npc"]
    with pytest.raises(ca.ActionError):
        ca.set_tracking(s, enc, npc, light=-1)
    assert ca.set_tracking(s, enc, npc, light=4, serious=1, void=0) == {"down_prompt": False}
    assert (npc.current_light_wounds, npc.current_serious_wounds, npc.current_void_points) == (4, 1, 0)
    assert ca.set_tracking(s, enc, npc)["down_prompt"] is False
    npcs.set_status(s, enc, npc, "unconscious")
    assert ca.set_tracking(s, enc, npc, serious=20)["down_prompt"] is False  # already down


def test_down_prompt_needs_the_npc_in_the_fight(world):
    npc = world["npc"]
    npc.current_serious_wounds = 99
    assert ca._down_prompt(Encounter(), npc) is False


# ---------------------------------------------------------------------------
# State payloads
# ---------------------------------------------------------------------------

_PUBLIC_NPC_KEYS = {"id", "name", "light_wounds", "serious_wounds", "down",
                    "actions_this_round", "actions_last_round", "tn_to_be_hit"}
_PUBLIC_ACTION_KEYS = {"kind", "label", "target", "total", "outcome", "damage"}


def test_public_state_is_the_allow_list(world):
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    ca.other(s, enc, npc, die=0, label="Taunts")
    state = cv.public_state(s, g)
    assert set(state) == {"rev", "group", "encounter", "pcs", "npcs"}
    assert state["encounter"] == {"name": "Ambush", "round": 1}
    assert [p["name"] for p in state["pcs"]] == ["Yudai"]  # the hidden PC is not in the fight
    assert set(state["pcs"][0]) == {"id", "name", "light_wounds", "serious_wounds", "action_dice"}
    (row,) = state["npcs"]
    assert set(row) == _PUBLIC_NPC_KEYS
    assert row["actions_last_round"] is None  # no full round yet
    assert set(row["actions_this_round"][0]) == _PUBLIC_ACTION_KEYS
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    row = cv.public_state(s, g)["npcs"][0]
    assert row["actions_last_round"] == 1 and row["actions_this_round"] == []


def test_public_state_without_a_fight(client):
    s = client._test_session_factory()
    g = GamingGroup(name="Quiet")
    s.add(g)
    s.flush()
    state = cv.public_state(s, g)
    assert state["encounter"] is None and state["npcs"] == [] and state["rev"] == "none"
    assert cv.gm_state(s, g)["encounter"] is None
    s.close()


def test_gm_state_has_everything(world):
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    _dice(npc)
    ca.attack(s, enc, npc, GM, roll_key="attack", die=0, target=world["pc"], tn=None, rng=ConstRng(5))
    state = cv.gm_state(s, g)
    assert state["gm"] is True and state["encounter"]["id"] == enc.id
    row = state["npcs"][0]
    for key in ("void", "void_max", "tn_to_be_hit", "action_dice", "attacks", "status",
                "combat_share", "bonuses", "sheet_url", "max_serious_wounds"):
        assert key in row
    (action,) = state["actions"]
    assert action["target"] == "Yudai" and action["npc"] == npc.name
    before = state["rev"]
    npc.current_light_wounds = 7
    s.flush()
    assert cv.gm_state(s, g)["rev"] != before


def test_bonuses_read_counters_and_toggles():
    c = Character(name="x", school="kitsune_warden",
                  knacks={"absorb_void": 3, "commune": 3, "iaijutsu": 3},
                  skills={"precepts": 2}, advantages=["lucky"],
                  adventure_state={"adventure_raises_used": 1, "lucky_used": True})
    got = {b["id"]: b for b in (remaining(c, a) for a in per_adventure_abilities(c))}
    assert got["adventure_raises"] == {"id": "adventure_raises", "name": got["adventure_raises"]["name"],
                                       "left": 3, "max": 4}
    assert got["lucky_used"]["used"] is True
    assert got["absorb_void"]["left"] == 3


def test_combat_rolls_cover_the_fight_window(world):
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    s.add(RollHistory(character_id=world["pc"].id, roll_key="attack", actor_discord_id="test_user_1",
                      payload={"title": "Attack", "total": 30, "kept": [{"parts": [10, 4]}], "dropped": []}))
    s.flush()
    rows = cv.combat_rolls(s, g, enc)
    assert [r["is_npc"] for r in rows] == [True, False]
    assert rows[1]["kept"] == [14] and rows[1]["total"] == 30
    npcs.end_encounter(s, enc)
    assert len(cv.combat_rolls(s, g, enc)) == 2
    empty = GamingGroup(name="Empty")
    s.add(empty)
    s.flush()
    lonely = npcs.start_encounter(s, empty.id)
    assert cv.combat_rolls(s, empty, lonely) == []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _url(world, path):
    return f"/groups/{world['g'].id}/combat{path}"


def test_page_and_state_for_gm_and_public(client, world):
    gm_page = client.get(_url(world, ""))
    assert gm_page.status_code == 200 and "Add opponents" in gm_page.text
    public = client.get(_url(world, ""), headers=PLAYER)
    assert public.status_code == 200 and 'data-testid="builder"' in public.text
    assert '"earned_xp"' not in public.text  # the embedded state is the public one
    assert '"earned_xp"' in gm_page.text
    assert client.get(_url(world, "/state")).json()["gm"] is True
    assert "gm" not in client.get(_url(world, "/state"), headers=PLAYER).json()
    assert client.get("/groups/999/combat").status_code == 404
    assert client.get("/groups/999/combat/state").status_code == 404


def test_the_gm_can_open_this_one_tab_as_the_player_view(client, world):
    """?view=player renders exactly what a player gets, for the GM too, so a
    screen-shared tab shows nothing the players may not see; the GM's other
    tabs are untouched."""
    shared = client.get(_url(world, "?view=player"))
    assert shared.status_code == 200
    assert '"earned_xp"' not in shared.text and 'data-testid="builder"' in shared.text
    assert 'data-testid="leave-player-view"' in shared.text
    state = client.get(_url(world, "/state?view=player")).json()
    assert state == client.get(_url(world, "/state"), headers=PLAYER).json()
    gm = client.get(_url(world, ""))
    assert 'data-testid="open-player-view"' in gm.text and '"earned_xp"' in gm.text
    # A player asking for it gets what they always get, without the way back.
    player = client.get(_url(world, "?view=player"), headers=PLAYER)
    assert 'data-testid="leave-player-view"' not in player.text
    assert 'data-testid="open-player-view"' not in player.text


def test_combat_rolls_page(client, world):
    assert client.get(_url(world, "/rolls"), headers=PLAYER).status_code == 403
    assert client.get("/groups/999/combat/rolls").status_code == 404
    client.post(_url(world, "/new-round"))
    page = client.get(_url(world, "/rolls"))
    assert page.status_code == 200 and 'data-testid="roll-row"' in page.text
    assert client.get(_url(world, f"/rolls?encounter={world['enc'].id}")).status_code == 200
    s = client._test_session_factory()
    lonely = GamingGroup(name="No fights")
    s.add(lonely)
    s.commit()
    assert "No fights yet" in client.get(f"/groups/{lonely.id}/combat/rolls").text
    s.close()


def test_action_routes_end_to_end(client, world):
    npc_id, pc_id = world["npc"].id, world["pc"].id
    assert client.post(_url(world, "/new-round")).json()["round"] == 1
    assert client.post(_url(world, f"/npcs/{npc_id}/initiative")).status_code == 200
    atk = client.post(_url(world, f"/npcs/{npc_id}/attack"),
                      json={"roll_key": "attack", "die": 0, "target_id": pc_id, "tn": 0})
    assert atk.status_code == 200 and atk.json()["hit"] is True
    dmg = client.post(_url(world, f"/actions/{atk.json()['action_id']}/damage"),
                      json={"parry": "failed", "parry_skill": 2, "weapon": "knife"})
    assert dmg.status_code == 200 and dmg.json()["damage"] > 0
    assert client.post(_url(world, f"/actions/{atk.json()['action_id']}/damage"), json={}).status_code == 400
    par = client.post(_url(world, f"/npcs/{npc_id}/parry"),
                      json={"die": 1, "attack_total": 1, "attacker_id": pc_id})
    assert par.status_code in (200, 400)  # 400 only if the NPC rolled a single die
    wc = client.post(_url(world, f"/npcs/{npc_id}/take-damage"), json={"amount": 3})
    assert wc.status_code == 200
    assert client.post(_url(world, f"/npcs/{npc_id}/take-serious-wound")).status_code == 200
    assert client.post(_url(world, f"/npcs/{npc_id}/tracking"), json={"light": 2}).json() == {"down_prompt": False}


def test_action_route_errors(client, world):
    npc_id = world["npc"].id
    base = f"/npcs/{npc_id}"
    assert client.post(_url(world, f"{base}/attack"), json={"target_id": 99999}).status_code == 404
    assert client.post(_url(world, f"{base}/attack"), json={"target_id": world["hidden"].id}).status_code == 404
    assert client.post(_url(world, f"{base}/attack"), json={"die": 0, "tn": 5}).status_code == 400  # no dice yet
    assert client.post(_url(world, f"{base}/attack"), json={"die": "x", "tn": 5}).status_code == 400
    assert client.post(_url(world, f"{base}/parry"), json={"dice": [0]}).status_code == 400
    assert client.post(_url(world, f"{base}/parry"), json={"dice": [0], "attack_total": 5}).status_code == 400
    assert client.post(_url(world, f"{base}/other"), json={"die": 0}).status_code == 400
    assert client.post(_url(world, f"{base}/take-damage"), json={"amount": 0}).status_code == 400
    assert client.post(_url(world, f"{base}/tracking"), json={"void": -1}).status_code == 400
    assert client.post(_url(world, "/actions/99999/damage"), json={}).status_code == 404
    assert client.post(_url(world, "/npcs/99999/other"), json={}).status_code == 404
    for path in ("/new-round", f"{base}/other"):
        assert client.post(_url(world, path), json={}, headers=PLAYER).status_code == 403
    assert client.post("/groups/999/combat/new-round").status_code == 404
    assert client.post(_url(world, "/actions/1/damage"), headers=PLAYER).status_code == 403
    client.post(_url(world, "/end"))
    assert client.post(_url(world, "/new-round")).status_code == 409
    assert client.post(_url(world, f"{base}/other"), json={}).status_code == 409


def test_other_route(client, world):
    client.post(_url(world, "/new-round"))
    out = client.post(_url(world, f"/npcs/{world['npc'].id}/other"), json={"die": 0, "label": "Moves"})
    assert out.status_code == 200


@pytest.mark.parametrize("path", ["initiative", "attack", "parry", "take-damage",
                                  "take-serious-wound", "tracking"])
def test_action_routes_404_for_an_npc_not_in_the_fight(client, world, path):
    assert client.post(_url(world, f"/npcs/99999/{path}"), json={}).status_code == 404


def test_attack_target_must_be_a_number(client, world):
    resp = client.post(_url(world, f"/npcs/{world['npc'].id}/attack"), json={"target_id": "abc"})
    assert resp.status_code == 404


def test_public_view_hides_spent_pc_dice(world):
    s, g, pc = world["s"], world["g"], world["pc"]
    pc.action_dice = [{"value": 2, "spent": True}, {"value": 6, "spent": False}]
    s.flush()
    (row,) = cv.public_state(s, g)["pcs"]
    assert row["action_dice"] == [{"value": 6}]
