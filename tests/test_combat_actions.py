"""Server-side NPC actions, the combat page's state, and its routes
(app/services/combat_actions.py, combat_view.py, app/routes/combat.py)."""

import json
import re

import pytest

from app.models import Character, Encounter, GamingGroup, RollHistory
from app.services import combat_actions as ca
from app.services import combat_view as cv
from app.services import fight_log
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


def _act(world, kind="other", label="Taunts", **kw):
    """A fight action, as the sheet's roller logs one (fight_log)."""
    fight_log._log(world["s"], world["enc"], world["npc"], kind, label, **kw)


# ---------------------------------------------------------------------------
# Service: helpers
# ---------------------------------------------------------------------------

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

def test_tn_to_be_hit_is_public_once_the_npc_was_attacked(world):
    """Unknown to players until the NPC has taken damage or parried in this
    fight: either one means somebody attacked it."""
    s, g, npc = world["s"], world["g"], world["npc"]
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] is None
    _act(world, kind="attack", label="Attack", total=20)
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] is None  # its own attack says nothing
    _act(world, kind="parry", label="Parry", total=20)
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] == ca.tn_to_be_hit(npc)


def test_tn_to_be_hit_is_public_once_the_npc_has_wounds(world):
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    npc.current_light_wounds = 5
    s.flush()
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] == ca.tn_to_be_hit(npc)
    ca.set_tracking(s, enc, npc, light=0, serious=0)  # the GM undoing a mistake
    assert cv.public_state(s, g)["npcs"][0]["tn_to_be_hit"] is None


# ---------------------------------------------------------------------------
# Wounds
# ---------------------------------------------------------------------------

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
                    "actions_this_round", "spent_dice", "unknown_dice", "tn_to_be_hit", "impaired"}
_PUBLIC_ACTION_KEYS = {"kind", "label", "target", "total", "outcome", "damage"}


def _spend(npc, *indices, spent=True):
    dice = [dict(d) for d in npc.action_dice]
    for i in indices:
        dice[i]["spent"] = spent
    npc.action_dice = dice


def test_public_state_is_the_allow_list(world):
    s, g, enc = world["s"], world["g"], world["enc"]
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    _act(world, kind="attack", label="Attack", total=20)
    state = cv.public_state(s, g)
    assert set(state) == {"rev", "group", "encounter", "pcs", "npcs"}
    assert state["encounter"] == {"name": "Ambush", "round": 1}
    assert [p["name"] for p in state["pcs"]] == ["Yudai"]  # the hidden PC is not in the fight
    assert set(state["pcs"][0]) == {"id", "name", "light_wounds", "serious_wounds", "action_dice", "impaired"}
    (row,) = state["npcs"]
    assert set(row) == _PUBLIC_NPC_KEYS
    assert set(row["actions_this_round"][0]) == _PUBLIC_ACTION_KEYS
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    assert cv.public_state(s, g)["npcs"][0]["actions_this_round"] == []


def test_players_see_spent_dice_and_the_actions_they_know_of(world):
    """Spent dice are public, with their values; unspent ones never are.
    From round 2, "?" dice stand for the most actions the NPC has spent in
    an earlier round of this fight, and turn into spent dice as it acts."""
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    assert len(npc.action_dice) >= 2
    row = cv.public_state(s, g)["npcs"][0]
    assert (row["spent_dice"], row["unknown_dice"]) == ([], 0)  # round 1: nothing known yet
    _spend(npc, 0)
    _spend(npc, 0, spent=False)  # changed its mind...
    _spend(npc, 0)               # ...and spent it again: still one action
    _spend(npc, 1)
    s.flush()
    row = cv.public_state(s, g)["npcs"][0]
    assert row["spent_dice"] == [npc.action_dice[0]["value"], npc.action_dice[1]["value"]]
    assert row["unknown_dice"] == 0
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    row = cv.public_state(s, g)["npcs"][0]
    assert (row["spent_dice"], row["unknown_dice"]) == ([], 2)
    _spend(npc, 0)
    s.flush()
    row = cv.public_state(s, g)["npcs"][0]
    assert (row["spent_dice"], row["unknown_dice"]) == ([npc.action_dice[0]["value"]], 1)


def test_players_see_who_is_impaired(world):
    s, g, npc, pc = world["s"], world["g"], world["npc"], world["pc"]
    state = cv.public_state(s, g)
    assert state["npcs"][0]["impaired"] is False and state["pcs"][0]["impaired"] is False
    npc.current_serious_wounds = npc.ring_earth
    pc.current_serious_wounds = pc.ring_earth
    s.flush()
    state = cv.public_state(s, g)
    assert state["npcs"][0]["impaired"] is True and state["pcs"][0]["impaired"] is True


def test_known_actions_are_the_most_spent_in_any_earlier_round(world):
    s, g, enc, npc = world["s"], world["g"], world["enc"], world["npc"]
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    _spend(npc, 0, 1)
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    _spend(npc, 0)
    # A mid-round initiative reroll keeps this round's count out of "known".
    ca.roll_initiative(s, enc, npc, GM, rng=ConstRng(3))
    assert cv.public_state(s, g)["npcs"][0]["unknown_dice"] == 2
    _spend(npc, 0, 1)
    ca.new_round(s, enc, GM, rng=ConstRng(3))
    assert cv.public_state(s, g)["npcs"][0]["unknown_dice"] == 2


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
    _act(world, kind="attack", label="Attack", total=20, target=world["pc"].id)
    state = cv.gm_state(s, g)
    assert state["gm"] is True and state["encounter"]["id"] == enc.id
    row = state["npcs"][0]
    for key in ("void", "void_max", "tn_to_be_hit", "action_dice", "status",
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
    s, g, enc = world["s"], world["g"], world["enc"]
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
    npc_id = world["npc"].id
    assert client.post(_url(world, "/new-round")).json()["round"] == 1
    assert client.post(_url(world, f"/npcs/{npc_id}/initiative")).status_code == 200
    assert client.post(_url(world, f"/npcs/{npc_id}/tracking"), json={"light": 2}).json() == {"down_prompt": False}
    # The old quick-action routes are gone: the sheet's roller makes those rolls.
    for gone in ("attack", "parry", "other", "take-damage", "take-serious-wound"):
        assert client.post(_url(world, f"/npcs/{npc_id}/{gone}"), json={}).status_code in (404, 405)


def test_action_route_errors(client, world):
    npc_id = world["npc"].id
    base = f"/npcs/{npc_id}"
    assert client.post(_url(world, f"{base}/tracking"), json={"void": -1}).status_code == 400
    assert client.post(_url(world, "/npcs/99999/initiative"), json={}).status_code == 404
    assert client.post(_url(world, "/new-round"), json={}, headers=PLAYER).status_code == 403
    assert client.post(_url(world, f"{base}/initiative"), json={}, headers=PLAYER).status_code == 403
    assert client.post("/groups/999/combat/new-round").status_code == 404
    client.post(_url(world, "/end"))
    assert client.post(_url(world, "/new-round")).status_code == 409
    assert client.post(_url(world, f"{base}/initiative"), json={}).status_code == 409


@pytest.mark.parametrize("path", ["initiative", "tracking", "status", "remove", "rebuild", "rename"])
def test_action_routes_404_for_an_npc_not_in_the_fight(client, world, path):
    assert client.post(_url(world, f"/npcs/99999/{path}"), json={}).status_code == 404


def test_public_view_hides_spent_pc_dice(world):
    s, g, pc = world["s"], world["g"], world["pc"]
    pc.action_dice = [{"value": 2, "spent": True}, {"value": 6, "spent": False}]
    s.flush()
    (row,) = cv.public_state(s, g)["pcs"]
    assert row["action_dice"] == [{"value": 6}]


# ---------------------------------------------------------------------------
# The NPC roll overlay (the sheet's own die menu and roll modals)
# ---------------------------------------------------------------------------

def test_npc_roller_overlay_serves_the_sheets_roller(client, world):
    s, npc, pc = world["s"], world["npc"], world["pc"]
    _dice(npc, (3, 7))
    s.commit()
    page = client.get(_url(world, f"/npcs/{npc.id}/roller?die=1&x=100&y=50"))
    assert page.status_code == 200
    html = page.text
    assert 'x-data="diceRoller()"' in html and 'id="roll-formulas"' in html
    assert 'data-action-die-menu-item="attack"' in html and 'data-testid="npc-roller"' in html
    assert "<nav" not in html and "<footer" not in html
    targets = re.search(r'id="combat-targets">(.*?)</script>', html, re.S).group(1)
    assert json.loads(targets) == [{"id": pc.id, "name": "Yudai", "parry": 3, "tn": ca.tn_to_be_hit(pc)}]
    assert "lwPlusModal = true" not in html
    wounds = client.get(_url(world, f"/npcs/{npc.id}/roller?wounds=1")).text
    assert "Light Wounds" in wounds and "lwPlusModal = true" in wounds


def test_npc_roller_overlay_is_the_gms_and_only_for_npcs_in_the_fight(client, world):
    s, npc, pc = world["s"], world["npc"], world["pc"]
    assert client.get(_url(world, f"/npcs/{npc.id}/roller"), headers=PLAYER).status_code == 403
    assert client.get(_url(world, f"/npcs/{pc.id}/roller")).status_code == 404
    assert client.get(f"/groups/999/combat/npcs/{npc.id}/roller").status_code == 404
    npcs.end_encounter(s, world["enc"])
    s.commit()
    assert client.get(_url(world, f"/npcs/{npc.id}/roller")).status_code == 404
