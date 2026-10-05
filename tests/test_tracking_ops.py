"""Tracking operations (app/services/tracking_ops.py, POST /characters/{id}/track/op)
and the adventure_state schema (app/services/adventure_state.py)."""

import pytest

from app.models import Character
from app.services import tracking_ops as ops
from app.services.adventure_state import sanitize_adventure_state

PLAYER = {"X-Test-User": "test_user_1:player"}
OTHER = {"X-Test-User": "test_user_2:other"}


def _char(client, **kw):
    s = client._test_session_factory()
    data = dict(name="Tracker", owner_discord_id="test_user_1", is_published=True,
                school="akodo_bushi", school_ring_choice="Water", ring_water=3,
                knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
                current_void_points=1, ring_void=2)
    data.update(kw)
    c = Character(**data)
    s.add(c)
    s.commit()
    cid = c.id
    s.close()
    return cid


def _op(client, cid, op, headers=PLAYER, **args):
    return client.post(f"/characters/{cid}/track/op", json={"op": op, "args": args}, headers=headers)


def _get(client, cid):
    s = client._test_session_factory()
    c = s.get(Character, cid)
    s.expunge(c)
    s.close()
    return c


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

def test_an_op_answers_with_the_new_snapshot_and_moves_the_revision(client):
    cid = _char(client)
    before = _get(client, cid).tracking_rev
    resp = _op(client, cid, "light_wounds", mode="add", value=7)
    data = resp.json()
    assert resp.status_code == 200 and data["tracking"]["current_light_wounds"] == 7
    assert data["tracking"]["rev"] == before + 1 == _get(client, cid).tracking_rev


def test_ops_are_editor_only(client):
    cid = _char(client)
    assert _op(client, cid, "void", headers=OTHER, delta=1).status_code == 403
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anon:
        assert anon.post(f"/characters/{cid}/track/op", json={"op": "void"}).status_code == 401
    assert client.post("/characters/99999/track/op", json={"op": "void"}).status_code == 404


def test_a_refusal_carries_the_snapshot(client):
    cid = _char(client)
    resp = _op(client, cid, "no_such_op")
    assert resp.status_code == 400 and "unknown operation" in resp.json()["error"]
    assert resp.json()["tracking"]["current_void_points"] == 1
    assert client.post(f"/characters/{cid}/track/op", json=[1], headers=PLAYER).status_code == 400
    bad = client.post(f"/characters/{cid}/track/op", json={"op": "void", "args": [1]}, headers=PLAYER)
    assert bad.status_code == 400 and "args" in bad.json()["error"]


# ---------------------------------------------------------------------------
# Wounds and void
# ---------------------------------------------------------------------------

def test_light_wounds(client):
    cid = _char(client)
    _op(client, cid, "light_wounds", mode="add", value=5)
    _op(client, cid, "light_wounds", mode="add", value=3)
    assert _get(client, cid).current_light_wounds == 8
    _op(client, cid, "light_wounds", mode="set", value=2)
    assert _get(client, cid).current_light_wounds == 2
    for args in ({"mode": "add", "value": 0}, {"mode": "set", "value": -1},
                 {"mode": "halve", "value": 1}, {"mode": "add", "value": "x"}):
        assert _op(client, cid, "light_wounds", **args).status_code == 400


def test_serious_wounds_keep_the_night_rest_cadence(client):
    cid = _char(client)
    _op(client, cid, "serious_wounds", delta=1)
    c = _get(client, cid)
    assert c.current_serious_wounds == 1
    assert c.sw_healing_received_new_since_rest and c.sw_healing_became_injured_since_rest
    _op(client, cid, "serious_wounds", delta=-1)
    c = _get(client, cid)
    assert c.current_serious_wounds == 0 and not c.sw_healing_received_new_since_rest
    _op(client, cid, "serious_wounds", delta=-1)
    assert _get(client, cid).current_serious_wounds == 0
    assert _op(client, cid, "serious_wounds", delta=2).status_code == 400


def test_take_serious_clears_the_light_wounds(client):
    cid = _char(client, current_light_wounds=14)
    _op(client, cid, "take_serious", count=2)
    c = _get(client, cid)
    assert (c.current_serious_wounds, c.current_light_wounds) == (2, 0)
    assert _op(client, cid, "take_serious", count=0).status_code == 400


def test_void_is_capped_at_its_maximum(client):
    cid = _char(client, current_void_points=2)
    _op(client, cid, "void", delta=1)
    assert _get(client, cid).current_void_points == 2  # void max is the lowest ring (2)
    _op(client, cid, "void", delta=-1)
    _op(client, cid, "void", delta=-1)
    _op(client, cid, "void", delta=-1)
    assert _get(client, cid).current_void_points == 0


def test_temp_void(client):
    cid = _char(client)
    _op(client, cid, "temp_void", delta=1)
    _op(client, cid, "temp_void", delta=1)
    _op(client, cid, "temp_void", delta=-1)
    assert _get(client, cid).current_temp_void_points == 1


# ---------------------------------------------------------------------------
# Per-adventure abilities
# ---------------------------------------------------------------------------

def _bard(client, **kw):
    return _char(client, school="ikoma_bard", advantages=["lucky"],
                 knacks={"discern_honor": 3, "oppose_knowledge": 3, "oppose_social": 3},
                 skills={"bragging": 2}, **kw)


def test_counters_toggles_and_resets(client):
    cid = _bard(client)
    for _ in range(6):
        _op(client, cid, "counter", id="adventure_raises", delta=1)
    assert _get(client, cid).adventure_state["adventure_raises_used"] == 4  # the max
    _op(client, cid, "toggle", id="lucky_used", value=True)
    assert _get(client, cid).adventure_state["lucky_used"] is True
    _op(client, cid, "reset_ability", id="adventure_raises")
    _op(client, cid, "reset_ability", id="lucky_used")
    state = _get(client, cid).adventure_state
    assert state["adventure_raises_used"] == 0 and state["lucky_used"] is False
    assert _op(client, cid, "counter", id="conviction", delta=1).status_code == 400
    assert _op(client, cid, "toggle", id="adventure_raises", value=True).status_code == 400
    assert _op(client, cid, "reset_ability", id="nothing").status_code == 400


def test_reset_adventure_clears_everything_per_adventure(client):
    cid = _bard(client, action_dice=[{"value": 3, "spent": True}], precepts_pool=[5],
                adventure_state={"adventure_raises_used": 2, "lucky_used": True,
                                 "akodo_banked_bonuses": [5], "mantis_posture_phase": 3})
    _op(client, cid, "reset_adventure")
    c = _get(client, cid)
    assert c.adventure_state == {"adventure_raises_used": 0, "lucky_used": False}
    assert c.action_dice == [] and c.precepts_pool == []


def _kitsune(client, **kw):
    return _char(client, school="kitsune_warden", school_ring_choice="Water",
                 knacks={"absorb_void": 2, "commune": 1, "iaijutsu": 1}, **kw)


def test_absorb_void_and_its_undo(client):
    cid = _kitsune(client, current_void_points=0)
    _op(client, cid, "absorb_void", delta=1)
    c = _get(client, cid)
    assert c.current_void_points == 1 and c.adventure_state["absorb_void_used"] == 1
    _op(client, cid, "absorb_void", delta=-1)
    c = _get(client, cid)
    assert c.current_void_points == 0 and c.adventure_state["absorb_void_used"] == 0
    assert _op(client, cid, "absorb_void", delta=-1).status_code == 400
    _op(client, cid, "absorb_void", delta=1)
    _op(client, cid, "absorb_void", delta=1)
    resp = _op(client, cid, "absorb_void", delta=1)
    assert resp.status_code == 400 and "used up" in resp.json()["error"]


# ---------------------------------------------------------------------------
# School techniques
# ---------------------------------------------------------------------------

def _togashi(client, **kw):
    return _char(client, school="togashi_ise_zumi", school_ring_choice="Void", ring_void=3,
                 knacks={"athletics": 5, "conviction": 5, "dragon_tattoo": 5}, **kw)


def test_togashi_heal(client):
    cid = _togashi(client, current_serious_wounds=3, current_void_points=0, current_temp_void_points=1)
    _op(client, cid, "togashi_heal")
    c = _get(client, cid)
    assert (c.current_serious_wounds, c.current_temp_void_points) == (1, 0)
    assert _op(client, cid, "togashi_heal").status_code == 400  # only 1 serious wound left
    broke = _togashi(client, current_serious_wounds=3, current_void_points=0)
    assert _op(client, broke, "togashi_heal").status_code == 400
    assert _op(client, _char(client, current_serious_wounds=3), "togashi_heal").status_code == 400


def test_hida_trade(client):
    cid = _char(client, school="hida_bushi", knacks={"counterattack": 4, "double_attack": 4, "iaijutsu": 4},
                current_light_wounds=20, current_serious_wounds=1)
    _op(client, cid, "hida_trade")
    c = _get(client, cid)
    assert (c.current_serious_wounds, c.current_light_wounds) == (3, 0)
    assert _op(client, cid, "hida_trade").status_code == 400  # nothing left to clear
    assert _op(client, _char(client, current_light_wounds=5), "hida_trade").status_code == 400


# ---------------------------------------------------------------------------
# Action dice
# ---------------------------------------------------------------------------

def test_action_dice(client):
    cid = _char(client, action_dice=[{"value": 2, "spent": False}, {"value": 6, "spent": False}],
                adventure_state={"mantis_posture_phase": 2})
    _op(client, cid, "action_die", index=0, action="spend", label="Moved")
    assert _get(client, cid).action_dice[0] == {"value": 2, "spent": True, "spent_by": "Moved"}
    assert _op(client, cid, "action_die", index=0, action="spend").status_code == 400
    _op(client, cid, "action_die", index=0, action="annotate", label="Charged")
    assert _get(client, cid).action_dice[0]["spent_by"] == "Charged"
    _op(client, cid, "action_die", index=0, action="annotate")
    assert "spent_by" not in _get(client, cid).action_dice[0]
    _op(client, cid, "action_die", index=0, action="unspend")
    assert _get(client, cid).action_dice[0] == {"value": 2, "spent": False}
    _op(client, cid, "action_die", index=1, action="spend")
    assert _get(client, cid).action_dice[1]["spent"] is True
    assert _op(client, cid, "action_die", index=9, action="spend").status_code == 400
    assert _op(client, cid, "action_die", index=0, action="juggle").status_code == 400
    _op(client, cid, "clear_action_dice")
    c = _get(client, cid)
    assert c.action_dice == [] and "mantis_posture_phase" not in c.adventure_state


def test_apply_op_directly_refuses_unknown_ops():
    with pytest.raises(ops.OpRefused):
        ops.apply_op(Character(name="x"), "nope", {})


# ---------------------------------------------------------------------------
# The adventure_state schema
# ---------------------------------------------------------------------------

def test_schema_keeps_known_keys_in_shape():
    c = Character(name="k", school="ikoma_bard", advantages=["lucky"],
                  knacks={"discern_honor": 3, "oppose_knowledge": 3, "oppose_social": 3},
                  skills={"bragging": 2})
    got = sanitize_adventure_state(c, {
        "adventure_raises_used": "3", "lucky_used": 1, "kakita_5th_dan_used": 0,
        "akodo_banked_bonuses": [5, "x", 10.0], "banked_wc_excess": 7,
        "hiruma_banked_attack_bonus": -4, "ide_banked_tn_reduce": "bad",
        "mantis_posture_phase": 0, "mantis_posture_history": ["offensive", "sleepy"],
        "stray": True,
    })
    assert got == {
        "adventure_raises_used": 3, "lucky_used": True, "kakita_5th_dan_used": False,
        "akodo_banked_bonuses": [5, 10], "banked_wc_excess": [7],
        "hiruma_banked_attack_bonus": 0, "ide_banked_tn_reduce": 0,
        "mantis_posture_phase": 1, "mantis_posture_history": ["offensive"],
    }


def test_schema_rejects_a_non_dict():
    assert sanitize_adventure_state(Character(name="x"), ["nope"]) == {}
    assert sanitize_adventure_state(Character(name="x"), {"mantis_posture_history": "x"}) == {
        "mantis_posture_history": []}


# ---------------------------------------------------------------------------
# Mantis postures, Mantis 3rd Dan, the Kakita interrupt (Phase 7)
# ---------------------------------------------------------------------------

def _mantis(client, dan=3, **kw):
    return _char(client, school="mantis_wave_treader", school_ring_choice="Water", attack=2,
                 knacks={"athletics": dan, "iaijutsu": dan, "worldliness": dan}, **kw)


def test_mantis_postures_run_to_phase_ten(client):
    cid = _mantis(client)
    assert _op(client, cid, "mantis_posture", type="offensive").status_code == 200
    state = _op(client, cid, "mantis_posture", type="defensive").json()["tracking"]["adventure_state"]
    assert state["mantis_posture_history"] == ["offensive", "defensive"] and state["mantis_posture_phase"] == 3
    assert _op(client, cid, "mantis_posture", type="sideways").status_code == 400
    full = _mantis(client, adventure_state={"mantis_posture_phase": 11})
    assert "every phase" in _op(client, full, "mantis_posture", type="offensive").json()["error"]
    other = _char(client)
    assert _op(client, other, "mantis_posture", type="offensive").status_code == 400


def test_mantis_3rd_dan_spends_the_right_die(client):
    dice = [{"value": 2, "spent": False}, {"value": 8, "spent": False},
            {"value": 1, "spent": False, "athletics_only": True, "mantis_4th_dan": True}]
    cid = _mantis(client, dan=4, action_dice=dice)
    t = _op(client, cid, "mantis_3rd_dan", side="offensive").json()["tracking"]
    assert t["action_dice"][2]["spent"] and t["adventure_state"]["mantis_offensive_3rd_dan_accum"] == 2
    t = _op(client, cid, "mantis_3rd_dan", side="defensive").json()["tracking"]
    assert t["action_dice"][1]["spent_by"] == "Mantis 3rd Dan (defensive)"
    t = _op(client, cid, "mantis_3rd_dan", side="offensive", index=0).json()["tracking"]
    assert t["action_dice"][0]["spent"] and t["adventure_state"]["mantis_offensive_3rd_dan_accum"] == 4
    assert "no action die" in _op(client, cid, "mantis_3rd_dan", side="offensive").json()["error"]
    assert "cannot be spent" in _op(client, cid, "mantis_3rd_dan", side="offensive", index=0).json()["error"]
    assert _op(client, cid, "mantis_3rd_dan", side="up").status_code == 400
    low = _mantis(client, dan=2, action_dice=dice)
    assert "no Mantis" in _op(client, low, "mantis_3rd_dan", side="offensive").json()["error"]


def test_kakita_interrupt_spends_the_two_highest(client):
    dice = [{"value": 3, "spent": False}, {"value": 9, "spent": False}, {"value": 6, "spent": False},
            {"value": 10, "spent": False, "athletics_only": True}]
    cid = _char(client, school="kakita_duelist", knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
                action_dice=dice)
    t = _op(client, cid, "kakita_interrupt").json()["tracking"]
    assert [d["spent"] for d in t["action_dice"]] == [False, True, True, False]
    assert "two unspent" in _op(client, cid, "kakita_interrupt").json()["error"]
    other = _char(client)
    assert _op(client, other, "kakita_interrupt").status_code == 400


def test_akodo_5th_dan_reflect_spends_void(client):
    cid = _char(client, knacks={"double_attack": 5, "feint": 5, "iaijutsu": 5},
                current_void_points=2, current_temp_void_points=1)
    t = _op(client, cid, "akodo_reflect", count=2).json()["tracking"]
    assert (t["current_temp_void_points"], t["current_void_points"]) == (0, 1)
    assert "at least 1" in _op(client, cid, "akodo_reflect", count=0).json()["error"]
    assert "reflect" in _op(client, cid, "akodo_reflect", count=5).json()["error"]
    low = _char(client)
    assert "cannot reflect" in _op(client, low, "akodo_reflect", count=1).json()["error"]


def test_bank_hand_edits(client):
    cid = _char(client, adventure_state={"akodo_banked_bonuses": [4, 6], "hiruma_banked_attack_bonus": 8})
    t = _op(client, cid, "bank", key="akodo_banked_bonuses", spend=6).json()["tracking"]
    assert t["adventure_state"]["akodo_banked_bonuses"] == [4]
    assert "no banked +9" in _op(client, cid, "bank", key="akodo_banked_bonuses", spend=9).json()["error"]
    t = _op(client, cid, "bank", key="hiruma_banked_attack_bonus", spend=5).json()["tracking"]
    assert t["adventure_state"]["hiruma_banked_attack_bonus"] == 3
    t = _op(client, cid, "bank", key="hiruma_banked_attack_bonus", clear=True).json()["tracking"]
    assert "hiruma_banked_attack_bonus" not in t["adventure_state"]
    assert "no such bank" in _op(client, cid, "bank", key="lucky_used", clear=True).json()["error"]


def test_an_action_die_can_be_set_to_what_was_rolled_at_the_table(client):
    """A player who rolls physical dice sets each die to match; the dice
    stay in order and a spent die keeps its spent state."""
    cid = _char(client, action_dice=[{"value": 2, "spent": False}, {"value": 5, "spent": True, "spent_by": "Parry"},
                                     {"value": 8, "spent": False}])
    r = _op(client, cid, "action_die", index=2, action="set_value", value=1)
    assert r.status_code == 200
    assert _get(client, cid).action_dice == [{"value": 1, "spent": False}, {"value": 2, "spent": False},
                                             {"value": 5, "spent": True, "spent_by": "Parry"}]
    _op(client, cid, "action_die", index=2, action="set_value", value=10)
    assert [d["value"] for d in _get(client, cid).action_dice] == [1, 2, 10]
    assert _get(client, cid).action_dice[2]["spent"] is True


@pytest.mark.parametrize("value", [0, 11, "x", None, True])
def test_an_action_die_value_must_be_one_to_ten(client, value):
    cid = _char(client, action_dice=[{"value": 2, "spent": False}])
    r = _op(client, cid, "action_die", index=0, action="set_value", value=value)
    assert r.status_code == 400 and "1 to 10" in r.json()["error"]
    assert _get(client, cid).action_dice == [{"value": 2, "spent": False}]


def test_only_an_editor_sets_a_die(client):
    cid = _char(client, action_dice=[{"value": 2, "spent": False}])
    assert _op(client, cid, "action_die", headers=OTHER, index=0, action="set_value", value=9).status_code == 403
