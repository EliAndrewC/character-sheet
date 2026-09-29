"""The Priest 3rd Dan precepts pool on the server (server-rolls-design
Phase 10): rolled and cleared by operations, swapped into a roll by a session
action."""

import pytest

from app.models import Character, GamingGroup
from app.services import roll_sessions as rs
from app.services.tracking_ops import OpRefused, apply_op, precepts_pool_flags
from tests.test_roll_sessions import OTHER, PLAYER, _act, _char, _get, _roll, _school
from tests.test_roll_sessions import scripted  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield


def _priest(client, dan=3, **kw):
    kw.setdefault("skills", {"precepts": 3})
    return _school(client, "priest", dan=dan, **kw)


def _op(client, cid, op, headers=PLAYER, **args):
    return client.post(f"/characters/{cid}/track/op", json={"op": op, "args": args}, headers=headers)


def test_the_pool_is_rolled_on_the_server_and_cleared_by_an_operation(client, scripted):
    cid = _priest(client)
    data = _roll(client, cid, roll_key="precepts_pool", headers=scripted("4,9,2")).json()
    assert data["pool"] == [{"value": 9}, {"value": 4}, {"value": 2}] and data["mode"] == "live"
    assert _get(client, cid).precepts_pool == data["pool"]
    t = _op(client, cid, "precepts_pool_clear").json()["tracking"]
    assert t["precepts_pool"] == []
    low = _priest(client, dan=2)
    assert "no precepts pool" in _roll(client, low, roll_key="precepts_pool").json()["error"]


def test_a_non_editor_rolls_a_pool_that_is_not_kept(client):
    cid = _priest(client)
    data = _roll(client, cid, roll_key="precepts_pool", headers=OTHER).json()
    assert data["mode"] == "simulate" and len(data["pool"]) == 3
    assert not _get(client, cid).precepts_pool


def test_pool_flags_and_unknown_ops():
    assert precepts_pool_flags(Character(name="x", school="akodo_bushi", knacks={}))["priest_precepts_pool_size"] == 0
    with pytest.raises(OpRefused):
        apply_op(Character(name="x", school="akodo_bushi", knacks={}), "nope", {})


def test_a_priest_swaps_their_own_pool(client, scripted):
    cid = _priest(client, precepts_pool=[{"value": 9}, {"value": 1}], current_light_wounds=10)
    data = _roll(client, cid, roll_key="parry", headers=scripted("3")).json()
    sid = data["session_id"]
    up = _act(client, cid, sid, "precepts_swap", priest_id="self", pool_index=0, rolled_value=3).json()
    assert up["precepts"]["pool"][0] == {"value": 3} and up["total"] > data["total"]
    assert _get(client, cid).precepts_pool == [{"value": 3}, {"value": 1}]
    # Their own roll may even take a LOWER die (to refresh the pool).
    down = _act(client, cid, sid, "precepts_swap", priest_id="self", pool_index=1, rolled_value=3).json()
    assert down["precepts"]["pool"][1] == {"value": 3}


def test_refusals(client, scripted):
    cid = _priest(client, precepts_pool=[{"value": 5}])
    sid = _roll(client, cid, roll_key="parry", headers=scripted("5")).json()["session_id"]
    assert "not allowed" in _act(client, cid, sid, "precepts_swap", priest_id="self", pool_index=0,
                                 rolled_value=5).json()["error"]
    assert "no 8" in _act(client, cid, sid, "precepts_swap", priest_id="self", pool_index=0,
                          rolled_value=8).json()["error"]
    assert "no such die" in _act(client, cid, sid, "precepts_swap", priest_id="self", pool_index=4,
                                 rolled_value=5).json()["error"]
    assert "whole numbers" in _act(client, cid, sid, "precepts_swap", priest_id="self", pool_index="x",
                                   rolled_value=5).json()["error"]
    assert "no precepts pool" in _act(client, cid, sid, "precepts_swap", priest_id=999, pool_index=0,
                                      rolled_value=5).json()["error"]
    other = _roll(client, cid).json()["session_id"]
    assert "only for attack" in _act(client, cid, other, "precepts_swap", priest_id="self").json()["error"]


def test_an_ally_swaps_only_upward_and_the_priests_pool_changes(client, scripted):
    s = client._test_session_factory()
    g = GamingGroup(name="Pool Group")
    s.add(g)
    s.commit()
    gid = g.id
    s.close()
    priest = _priest(client, precepts_pool=[{"value": 9}, {"value": 1}], gaming_group_id=gid)
    ally = _school(client, "akodo_bushi", gaming_group_id=gid, current_light_wounds=20)
    data = _roll(client, ally, roll_key="wound_check", headers=scripted("4")).json()
    sid = data["session_id"]
    assert "not allowed" in _act(client, ally, sid, "precepts_swap", priest_id=priest, pool_index=1,
                                 rolled_value=4).json()["error"]
    up = _act(client, ally, sid, "precepts_swap", priest_id=priest, pool_index=0, rolled_value=4).json()
    assert up["wc"]["passed"] is not None and up["total"] == data["total"] + 5
    assert _get(client, priest).precepts_pool == [{"value": 4}, {"value": 1}]


def test_a_simulated_swap_changes_no_pool(client, scripted):
    cid = _priest(client, precepts_pool=[{"value": 9}])
    sid = _roll(client, cid, roll_key="parry", headers={**OTHER, "X-Test-Dice": "3"}).json()["session_id"]
    got = _act(client, cid, sid, "precepts_swap", headers=OTHER, priest_id="self", pool_index=0,
               rolled_value=3).json()
    assert got["precepts"]["pool"] == [{"value": 3}]
    assert _get(client, cid).precepts_pool == [{"value": 9}]


def test_attack_damage_takes_a_swap(client, scripted):
    cid = _priest(client, precepts_pool=[{"value": 9}])
    sid = _roll(client, cid, roll_key="attack", tn=5, headers=scripted("9")).json()["session_id"]
    dmg = _act(client, cid, sid, "damage", headers=scripted("2")).json()["damage"]
    got = _act(client, cid, dmg["session_id"], "precepts_swap", priest_id="self", pool_index=0,
               rolled_value=2)
    assert got.status_code == 200
