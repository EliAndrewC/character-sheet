"""The iaijutsu duel and Kakita 5th Dan as the server makes them
(app/services/duels.py and the duel half of roll_sessions; Phase 9)."""

import pytest

from app.models import RollHistory
from app.services import roll_sessions as rs
from app.services.duels import kakita_5th_damage_pool, restart_bonus
from tests.test_roll_sessions import OTHER, _act, _get, _roll, _row, _school
from tests.test_roll_sessions import scripted  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield


def test_restart_bonus_validation():
    assert restart_bonus({"restart_bonus": 10}) == 10 and restart_bonus({}) == 0
    assert restart_bonus({"restart_bonus": 500}) == 100
    for bad in ("x", -5, 7):
        with pytest.raises(ValueError):
            restart_bonus({"restart_bonus": bad})


def test_the_contested_roll_takes_void_and_the_restart_bonus(client, scripted):
    cid = _school(client, "kakita_duelist", current_void_points=2, ring_void=2)
    data = _roll(client, cid, roll_key="iaijutsu:contested", void=1, restart_bonus=5,
                 headers=scripted("5")).json()
    assert {"label": "duel restart", "amount": 5} in data["payload"]["bonuses"]
    assert data["tracking"]["current_void_points"] == 1 and data["duel"]["total"] == data["total"]
    assert _row(client, data["history_id"])["title"] == "Iaijutsu Contested"
    assert "multiple of 5" in _roll(client, cid, roll_key="iaijutsu:contested", restart_bonus=3).json()["error"]
    s = client._test_session_factory()
    assert s.get(RollHistory, data["history_id"]).roll_key == "iaijutsu:contested"
    s.close()


def test_the_strike_is_judged_and_its_damage_rolled(client, scripted):
    cid = _school(client, "kakita_duelist", ring_fire=3)
    assert "no void" in _roll(client, cid, roll_key="iaijutsu:strike", void=1).json()["error"]
    assert "whole number" in _roll(client, cid, roll_key="iaijutsu:strike", opponent_tn="x").json()["error"]
    strike = _roll(client, cid, roll_key="iaijutsu:strike", opponent_tn=10, headers=scripted("10")).json()
    assert strike["formula"]["reroll_tens"] is False and strike["duel"]["hit"]
    sid = strike["session_id"]
    up = _act(client, cid, sid, "conviction")
    assert up.status_code in (200, 400)
    dmg = _act(client, cid, sid, "duel_damage", weapon_rolled=4, weapon_kept=2).json()["damage"]
    assert dmg["history_id"] and dmg["formula"]["is_damage_roll"]
    assert "already" in _act(client, cid, sid, "duel_damage").json()["error"]
    assert "whole numbers" in _act(client, cid, _roll(client, cid, roll_key="iaijutsu:strike",
                                                        opponent_tn=0).json()["session_id"],
                                   "duel_damage", weapon_rolled="x").json()["error"]
    miss = _roll(client, cid, roll_key="iaijutsu:strike", opponent_tn=500).json()["session_id"]
    assert "only a strike that hit" in _act(client, cid, miss, "duel_damage").json()["error"]
    other = _roll(client, cid).json()["session_id"]
    assert "only for a strike" in _act(client, cid, other, "duel_damage").json()["error"]


def _kakita5(client, **kw):
    return _school(client, "kakita_duelist", dan=5, attack=2, **kw)


def test_kakita_5th_dan_contest_is_latched_once_per_round(client, scripted):
    cid = _kakita5(client)
    data = _roll(client, cid, roll_key="kakita_5th_dan", opponent_has_iaijutsu=False, defender_phase=4,
                 opponent_skill_rank=3, headers=scripted("5")).json()
    labels = {b["label"]: b["amount"] for b in data["payload"]["bonuses"]}
    assert labels["opponent has no iaijutsu"] == 5 and labels["Kakita 3rd Dan (phase 0)"] == 8
    assert labels["contested skill"] == 10
    assert _get(client, cid).adventure_state["kakita_5th_dan_used"] is True
    assert "already been used" in _roll(client, cid, roll_key="kakita_5th_dan").json()["error"]
    assert "no void" in _roll(client, cid, roll_key="kakita_5th_dan", void=1).json()["error"]
    assert "whole number" in _roll(client, _kakita5(client), roll_key="kakita_5th_dan",
                                   defender_phase="x").json()["error"]
    sid = data["session_id"]
    dmg = _act(client, cid, sid, "kakita_5th_damage", opponent_roll=data["total"] - 10,
               headers=scripted("6")).json()["damage"]
    assert dmg["history_id"] and "+2k0 from the contest" in dmg["payload"]["extras"]
    assert "already" in _act(client, cid, sid, "kakita_5th_damage").json()["error"]
    other = _roll(client, cid).json()["session_id"]
    assert "only for the Kakita" in _act(client, cid, other, "kakita_5th_damage").json()["error"]
    low = _school(client, "kakita_duelist", dan=4)
    assert "no Kakita 5th Dan" in _roll(client, low, roll_key="kakita_5th_dan").json()["error"]


def test_kakita_5th_dan_in_simulation_and_a_lost_contest(client, scripted):
    cid = _kakita5(client)
    data = _roll(client, cid, roll_key="kakita_5th_dan", headers=OTHER).json()
    assert not (_get(client, cid).adventure_state or {}).get("kakita_5th_dan_used")
    lost = _act(client, cid, data["session_id"], "kakita_5th_damage", headers=OTHER,
                opponent_roll=data["total"] + 200, weapon_rolled=0, weapon_kept=0).json()["damage"]
    assert lost["dice"] == [] and lost["history_id"] is None
    assert "whole numbers" in _act(client, cid, _roll(client, cid, roll_key="kakita_5th_dan",
                                                        headers=OTHER).json()["session_id"],
                                   "kakita_5th_damage", headers=OTHER, opponent_roll="x").json()["error"]


def test_kakita_5th_damage_pool():
    assert kakita_5th_damage_pool({"damage_ring_val": 3}, (4, 2), 12)["rolled"] == 9
    assert kakita_5th_damage_pool({"damage_ring_val": 3}, (4, 2), -12)["adjust"] == -2
