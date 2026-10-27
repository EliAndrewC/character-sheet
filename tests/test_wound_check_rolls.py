"""The wound check as the server makes it for the sheet
(app/services/wound_checks.py and the wound-check half of roll_sessions;
server-rolls-design Phase 8)."""

import pytest

from app.models import Character, GamingGroup
from app.services import roll_sessions as rs
from app.services.wound_checks import akodo_banked_bonus, build_wound_check, daidoji_counterattack
from tests.test_roll_sessions import OTHER, _act, _char, _get, _roll, _row, _school
from tests.test_roll_sessions import scripted  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield


def _wc(client, cid, headers=None, **body):
    body.setdefault("roll_key", "wound_check")
    return _roll(client, cid, **({"headers": headers} if headers else {}), **body)


def test_build_wound_check_bonuses():
    c = Character(name="M", school="mantis_wave_treader", school_ring_choice="Water", attack=2,
                  knacks={"athletics": 5, "iaijutsu": 5, "worldliness": 5},
                  adventure_state={"mantis_posture_history": ["defensive", "offensive", "defensive"],
                                   "mantis_defensive_3rd_dan_accum": 2, "hida_banked_wc_bonus": 3})
    built = build_wound_check(c, {"flat": 0, "bonuses": [], "doji_5th_dan_wc": True}, 27, strike=False,
                              daidoji={"raises": 2, "bonus": 10})
    labels = {b["label"]: b["amount"] for b in built["formula"]["bonuses"]}
    assert labels == {"defensive posture": 5, "Mantis 5th Dan (defensive posture count)": 2,
                      "Mantis 3rd Dan (defensive)": 2, "Hida 5th Dan counterattack excess": 3,
                      "Doji 5th Dan": 3, "Daidoji counterattack (2 free raises)": 10}
    assert built["consumes"] == ["hida_banked_wc_bonus"]
    strike = build_wound_check(Character(name="x", school="akodo_bushi", knacks={}), {"flat": 0}, 5,
                               strike=True, daidoji=None)["formula"]
    assert strike["reroll_tens"] is False and strike["no_reroll_reason"] == "iaijutsu_strike"
    low = build_wound_check(Character(name="x", school="akodo_bushi", knacks={}),
                            {"flat": 0, "doji_5th_dan_wc": True}, 12, strike=False, daidoji=None)["formula"]
    assert "doji_5th_dan_bonus" not in low


def test_akodo_banked_bonus():
    assert akodo_banked_bonus(12, 3) == 6
    assert akodo_banked_bonus(0, 3) == 0 and akodo_banked_bonus(12, 0) == 0


def test_daidoji_counterattack_self_and_party(client):
    own = Character(name="D", school="daidoji_yojimbo", attack=3,
                    knacks={"counterattack": 3, "double_attack": 3, "iaijutsu": 3})
    assert daidoji_counterattack(own, []) == {"label": "Hit was counterattacked", "raises": 3, "bonus": 15}
    plain = Character(name="P", school="akodo_bushi", knacks={})
    assert daidoji_counterattack(plain, [plain]) is None
    assert daidoji_counterattack(plain, [own])["label"] == "D counterattacked this hit"


def test_a_live_wound_check_uses_the_characters_wounds(client, scripted):
    cid = _school(client, "akodo_bushi", current_light_wounds=15, adventure_state={"hida_banked_wc_bonus": 0})
    data = _wc(client, cid, light_wounds=99, headers=scripted("9")).json()
    assert data["wc"]["light_wounds"] == 15 and data["wc"]["passed"]
    none = _school(client, "akodo_bushi")
    assert "no light wounds" in _wc(client, none).json()["error"]


def test_a_simulated_wound_check_takes_the_scenario_amount(client, scripted):
    cid = _school(client, "akodo_bushi")
    data = _wc(client, cid, headers={**OTHER, "X-Test-Dice": "1"}, light_wounds=40).json()
    assert data["wc"]["light_wounds"] == 40 and not data["wc"]["passed"]
    res = _act(client, cid, data["session_id"], "wc_resolve", headers=OTHER, choice="fail").json()
    assert res["resolved"] == "fail" and not _get(client, cid).current_serious_wounds


def test_strike_and_daidoji_refusals(client):
    cid = _school(client, "akodo_bushi", current_light_wounds=10, current_void_points=2)
    assert "no void" in _wc(client, cid, strike=True, void=1).json()["error"]
    assert "no Daidoji" in _wc(client, cid, daidoji=True).json()["error"]
    data = _wc(client, cid, strike=True).json()
    assert data["formula"]["no_reroll_reason"] == "iaijutsu_strike"
    assert "only Conviction" in _act(client, cid, data["session_id"], "raise").json()["error"]
    assert "only Conviction" in _act(client, cid, data["session_id"], "wc_vp").json()["error"]
    d = _school(client, "daidoji_yojimbo", dan=3, current_light_wounds=10)
    assert _wc(client, d, daidoji=True).json()["formula"]["daidoji_counterattack_bonus"] == 10


def test_failure_and_yogo_temp_void(client, scripted):
    cid = _school(client, "yogo_warden", current_light_wounds=45, current_temp_void_points=0)
    data = _wc(client, cid, headers=scripted("1")).json()
    sid = data["session_id"]
    wounds = data["wc"]["serious_wounds"]
    assert wounds >= 1
    assert "not a failure" not in _act(client, cid, sid, "wc_resolve", choice="keep").json()["error"]
    assert "choice must" in _act(client, cid, sid, "wc_resolve", choice="maybe").json()["error"]
    done = _act(client, cid, sid, "wc_resolve", choice="fail").json()
    c = _get(client, cid)
    assert c.current_serious_wounds == wounds and c.current_light_wounds == 0
    assert c.current_temp_void_points == wounds
    assert "already resolved" in _act(client, cid, sid, "wc_resolve", choice="fail").json()["error"]
    assert done["resolved"] == "fail"


def test_a_pass_keeps_or_takes_one_serious(client, scripted):
    isawa = _school(client, "isawa_duelist", dan=5, current_light_wounds=10)
    data = _wc(client, isawa, headers=scripted("9")).json()
    assert "is not a failure" in _act(client, isawa, data["session_id"], "wc_resolve", choice="fail").json()["error"]
    _act(client, isawa, data["session_id"], "wc_resolve", choice="keep")
    assert _get(client, isawa).adventure_state["banked_wc_excess"] == [data["wc"]["margin"]]
    akodo = _school(client, "akodo_bushi", dan=3, current_light_wounds=10)
    data = _wc(client, akodo, headers=scripted("9")).json()
    _act(client, akodo, data["session_id"], "wc_resolve", choice="keep")
    assert _get(client, akodo).adventure_state["akodo_banked_bonuses"] == [(data["wc"]["margin"] // 5) * 2]
    yogo = _school(client, "yogo_warden", current_light_wounds=10, current_temp_void_points=0)
    data = _wc(client, yogo, headers=scripted("9")).json()
    _act(client, yogo, data["session_id"], "wc_resolve", choice="take_sw")
    c = _get(client, yogo)
    assert (c.current_serious_wounds, c.current_light_wounds, c.current_temp_void_points) == (1, 0, 1)
    plain = _school(client, "akodo_bushi", current_light_wounds=10)
    data = _wc(client, plain, headers=scripted("9")).json()
    _act(client, plain, data["session_id"], "wc_resolve", choice="keep")
    assert not (_get(client, plain).adventure_state or {}).get("banked_wc_excess")


def test_4th_dan_void_raise_on_wound_checks(client, scripted):
    cid = _school(client, "yogo_warden", dan=4, current_light_wounds=40, current_void_points=1,
                  current_temp_void_points=0)
    data = _wc(client, cid, headers=scripted("1")).json()
    sid = data["session_id"]
    up = _act(client, cid, sid, "wc_vp").json()
    assert up["total"] == data["total"] + 5 and up["tracking"]["current_void_points"] == 0
    assert "void" in _act(client, cid, sid, "wc_vp").json()["error"]
    back = _act(client, cid, sid, "undo_wc_vp").json()
    assert back["tracking"]["current_void_points"] == 1
    assert "undo" in _act(client, cid, sid, "undo_wc_vp").json()["error"]
    # Yogo 3rd Dan: that point also took 2 x attack (4) off the light wounds
    # being checked, and taking it back puts them back.
    assert up["wc"]["light_wounds"] == 36 and up["wc"]["yogo_lw_healed"] == 4
    assert up["tracking"]["current_light_wounds"] == 36
    assert back["wc"]["light_wounds"] == 40 and "yogo_lw_healed" not in back["wc"]
    assert back["tracking"]["current_light_wounds"] == 40
    plain = _school(client, "akodo_bushi", current_light_wounds=10)
    psid = _wc(client, plain).json()["session_id"]
    assert "no 4th Dan" in _act(client, plain, psid, "wc_vp").json()["error"]
    other = _roll(client, plain).json()["session_id"]
    for action in ("wc_vp", "matsu_bank", "wc_excess", "wc_resolve"):
        assert "only for a wound check" in _act(client, plain, other, action).json()["error"], action


def test_banks_on_wound_checks(client, scripted):
    cid = _school(client, "matsu_bushi", current_light_wounds=30,
                  adventure_state={"matsu_banked_wc_bonuses": [6], "banked_wc_excess": [4, 4]})
    data = _wc(client, cid, headers=scripted("1")).json()
    sid = data["session_id"]
    got = _act(client, cid, sid, "matsu_bank", amount=6).json()
    assert got["total"] == data["total"] + 6 and got["tracking"]["adventure_state"]["matsu_banked_wc_bonuses"] == []
    assert "no Matsu banked bonus of +6" in _act(client, cid, sid, "matsu_bank", amount=6).json()["error"]
    assert "whole number" in _act(client, cid, sid, "wc_excess", amount="x").json()["error"]
    ex = _act(client, cid, sid, "wc_excess", amount=4).json()
    assert ex["tracking"]["adventure_state"]["banked_wc_excess"] == [4]
    back = _act(client, cid, sid, "undo_matsu_bank").json()
    assert back["tracking"]["adventure_state"]["matsu_banked_wc_bonuses"] == [6]
    assert "put back" in _act(client, cid, sid, "undo_matsu_bank").json()["error"]
    sim = _wc(client, cid, headers=OTHER, light_wounds=30).json()["session_id"]
    assert _act(client, cid, sim, "wc_excess", headers=OTHER, amount=4).status_code == 200
    assert _act(client, cid, sim, "undo_wc_excess", headers=OTHER).status_code == 200
    assert _get(client, cid).adventure_state["banked_wc_excess"] == [4]


def test_the_hida_bank_is_spent_and_lucky_rejudges(client, scripted):
    cid = _school(client, "hida_bushi", current_light_wounds=12, advantages=["lucky"],
                  adventure_state={"hida_banked_wc_bonus": 5})
    data = _wc(client, cid, headers=scripted("1")).json()
    assert data["formula"]["hida_counterattack_bonus"] == 5
    assert "hida_banked_wc_bonus" not in (_get(client, cid).adventure_state or {})
    up = _act(client, cid, data["session_id"], "lucky_reroll", headers=scripted("9")).json()
    assert up["wc"]["passed"] and _row(client, data["history_id"])["total"] == up["total"]


def test_build_wound_check_extra_bonus():
    c = Character(name="x", school="akodo_bushi", knacks={})
    f = build_wound_check(c, {"flat": 2, "bonuses": [{"label": "2nd Dan", "amount": 2}]}, 20,
                          strike=False, daidoji=None, extra=("armor", 7))["formula"]
    assert f["flat"] == 9
    assert f["bonuses"] == [{"label": "2nd Dan", "amount": 2},
                            {"label": "armor", "amount": 7, "situational": True}]


def test_a_wound_check_takes_the_modals_extra_bonus(client, scripted):
    cid = _school(client, "akodo_bushi", current_light_wounds=30)
    plain = _wc(client, cid, headers=scripted("9")).json()
    data = _wc(client, cid, extra_bonus=12, extra_label="  shelter  ", headers=scripted("9")).json()
    assert data["total"] == plain["total"] + 12
    assert {"label": "shelter", "amount": 12, "situational": True} in data["formula"]["bonuses"]
    assert data["wc"]["passed"] == (data["total"] >= 30)
    assert {"label": "shelter", "amount": 12} in [
        {"label": b["label"], "amount": b["amount"]} for b in _row(client, data["history_id"])["bonuses"]]
    # No label falls back to "extra bonus"; an iaijutsu strike's check takes it too.
    strike = _wc(client, cid, strike=True, extra_bonus=-4, headers=scripted("9")).json()
    assert {"label": "extra bonus", "amount": -4, "situational": True} in strike["formula"]["bonuses"]
    assert "whole number" in _wc(client, cid, extra_bonus="lots").json()["error"]


@pytest.mark.parametrize("dan, flat", [(3, 5), (4, 10)])
def test_yogo_pre_roll_void_lowers_light_wounds_before_the_check(client, scripted, dan, flat):
    """Tsuruchi Hidemasa: 47 light wounds, attack 4, spends 1 void point -
    rolls against 39, with the 2nd Dan raise (and at 4th Dan, one more)."""
    cid = _school(client, "yogo_warden", dan=dan, attack=4, current_light_wounds=47,
                  current_void_points=2, current_temp_void_points=0)
    data = _wc(client, cid, void=1, headers=scripted("5")).json()
    assert data["formula"]["flat"] == flat
    assert data["wc"]["light_wounds"] == 39
    assert (data["wc"]["yogo_lw_before"], data["wc"]["yogo_lw_healed"]) == (47, 8)
    assert data["tracking"]["current_light_wounds"] == 39
    labels = [b["label"] for b in data["payload"]["bonuses"]]
    assert ("Yogo 4th Dan (1 void point spent)" in labels) == (dan >= 4)


def test_yogo_heal_stops_at_zero_and_applies_to_a_simulated_scenario(client, scripted):
    cid = _school(client, "yogo_warden", dan=4, attack=4, current_light_wounds=10,
                  current_void_points=3, current_temp_void_points=0)
    data = _wc(client, cid, void=2, headers=scripted("5")).json()
    assert data["wc"]["light_wounds"] == 0 and data["wc"]["yogo_lw_healed"] == 10
    assert data["wc"]["passed"]
    assert "Yogo 4th Dan (2 void points spent)" in [b["label"] for b in data["payload"]["bonuses"]]
    # A test-drive (Read-only Roll Mode) heals the scenario amount, not the character.
    sim = _school(client, "yogo_warden", dan=3, attack=4, current_void_points=2)
    data = _wc(client, sim, headers={**OTHER, "X-Test-Dice": "5"}, light_wounds=47, void=1).json()
    assert data["wc"]["light_wounds"] == 39
    assert _get(client, sim).current_void_points == 2


def test_a_yogo_post_roll_point_heals_no_more_than_is_left(client, scripted):
    cid = _school(client, "yogo_warden", dan=4, attack=4, current_light_wounds=11,
                  current_void_points=2, current_temp_void_points=0)
    data = _wc(client, cid, void=1, headers=scripted("1")).json()
    assert data["wc"]["light_wounds"] == 3
    up = _act(client, cid, data["session_id"], "wc_vp").json()
    assert up["wc"]["light_wounds"] == 0 and up["wc"]["yogo_lw_healed"] == 11
    assert up["tracking"]["current_light_wounds"] == 0
    back = _act(client, cid, data["session_id"], "undo_wc_vp").json()
    assert back["wc"]["light_wounds"] == 3 and back["tracking"]["current_light_wounds"] == 3
    # Simulated: the session heals, the character does not.
    sim = _school(client, "yogo_warden", dan=4, attack=4, current_void_points=1)
    s = _wc(client, sim, headers={**OTHER, "X-Test-Dice": "1"}, light_wounds=20).json()
    up = _act(client, sim, s["session_id"], "wc_vp", headers=OTHER).json()
    assert up["wc"]["light_wounds"] == 12 and not _get(client, sim).current_light_wounds


def test_a_strike_wound_check_takes_player_character_points(client, scripted):
    """GM 2026-10-27: nothing bars a PCP on an iaijutsu strike's wound check
    - a free raise and a reroll both land; reroll-10s stays refused (the
    strike never rerolls 10s, rules/10)."""
    cid = _school(client, "akodo_bushi", current_light_wounds=40)
    data = _wc(client, cid, strike=True, light_wounds=40, headers=scripted("1")).json()
    sid, base = data["session_id"], data["total"]
    raised = _act(client, cid, sid, "pcp_free_raise").json()
    assert raised["pcp"]["use"] == "free_raise" and raised["total"] == base + 5
    rerolled = _act(client, cid, sid, "pcp_reroll", headers=scripted("9")).json()
    assert rerolled["pcp"]["use"] == "reroll" and rerolled["total"] > base + 5
    assert _act(client, cid, sid, "pcp_reroll_tens").status_code == 400
    assert _get(client, cid).pcp_count == 2


def test_the_strike_itself_takes_player_character_points(client, scripted):
    cid = _school(client, "kakita_duelist", ring_fire=3)
    strike = _roll(client, cid, roll_key="iaijutsu:strike", opponent_tn=20, headers=scripted("5")).json()
    assert strike["duel"]["excess"] == -5
    raised = _act(client, cid, strike["session_id"], "pcp_free_raise").json()
    assert raised["duel"] == {"hit": True, "excess": 0}
    rerolled = _act(client, cid, strike["session_id"], "pcp_reroll", headers=scripted("9")).json()
    assert rerolled["pcp"]["use"] == "reroll" and rerolled["duel"]["excess"] > 0
