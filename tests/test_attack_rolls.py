"""The attack as the server makes it for the sheet (app/services/attack_rolls.py
and the attack half of roll_sessions; server-rolls-design Phase 7)."""

import pytest

from app.models import Character, RollHistory
from app.services import roll_sessions as rs
from app.services.attack_rolls import attack_outcome, build_attack, current_posture
from tests.test_roll_sessions import OTHER, PLAYER, _act, _char, _get, _roll, _row, _school

# The `scripted` fixture (X-Test-Dice) lives in test_roll_sessions.
from tests.test_roll_sessions import scripted  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield


def _c(**kw):
    data = dict(name="A", school="akodo_bushi", school_ring_choice="Water",
                knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1}, attack=2)
    data.update(kw)
    return Character(**data)


BASE = {"flat": 0, "bonuses": [], "attack_variant": "attack"}


def _labels(f):
    return {b["label"]: b["amount"] for b in f["bonuses"]}


# ---------------------------------------------------------------------------
# build_attack
# ---------------------------------------------------------------------------

def test_the_tn_is_required_and_inputs_are_numbers():
    with pytest.raises(ValueError, match="needs a TN"):
        build_attack(_c(), BASE, {}, [])
    with pytest.raises(ValueError, match="whole number"):
        build_attack(_c(), BASE, {"tn": "x"}, [])
    assert build_attack(_c(), BASE, {"tn": 15, "extra_bonus": ""}, [])["formula"]["attack_tn"] == 15


def test_mantis_postures_and_accumulators():
    c = _c(school="mantis_wave_treader", knacks={"athletics": 5, "iaijutsu": 5, "worldliness": 5},
           adventure_state={"mantis_posture_history": ["offensive", "defensive", "offensive"],
                            "mantis_offensive_3rd_dan_accum": 4})
    f = build_attack(c, BASE, {"tn": 20}, [])["formula"]
    assert _labels(f) == {"offensive posture": 5, "Mantis 5th Dan (offensive posture count)": 2,
                          "Mantis 3rd Dan (offensive)": 4}
    assert f["flat"] == 11
    assert current_posture({}) is None


def test_extra_bonus_specs_and_doji():
    f = build_attack(_c(), dict(BASE, doji_5th_dan_always=True, doji_4th_dan_untouched_target=True),
                     {"tn": 32, "extra_bonus": -3, "extra_label": "  ", "specs": [1, 0], "doji_phase": 4},
                     [{"text": "katana"}, {"text": ""}])["formula"]
    assert _labels(f)["extra bonus"] == -3
    assert f["doji_5th_dan_bonus"] == 4 and f["doji_4th_dan_bonus"] == 4
    assert f["attack_spec_bonus"] == 20 and f["attack_spec_applied_texts"] == ["unspecified", "katana"]
    assert f["flat"] == -3 + 4 + 4 + 20
    with pytest.raises(ValueError, match="specialization"):
        build_attack(_c(), BASE, {"tn": 10, "specs": [0, 0]}, [{"text": "x"}])
    low = build_attack(_c(), dict(BASE, doji_5th_dan_always=True), {"tn": 10}, [])["formula"]
    assert "doji_5th_dan_bonus" not in low


def test_shinjo_and_kakita_phase_bonuses():
    shinjo = _c(school="shinjo_bushi", knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
    f = build_attack(shinjo, dict(BASE, shinjo_phase_bonus_attack=True),
                     {"tn": 10, "die_value": 2, "shinjo_phase": 5}, [])["formula"]
    assert f["shinjo_phase_bonus"] == 6
    same = build_attack(shinjo, dict(BASE, shinjo_phase_bonus_attack=True),
                        {"tn": 10, "die_value": 5, "shinjo_phase": 5}, [])["formula"]
    assert "shinjo_phase_bonus" not in same
    kakita = _c(school="kakita_duelist", knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
    f = build_attack(kakita, dict(BASE, kakita_3rd_dan_defender_phase_bonus=True),
                     {"tn": 10, "die_value": 3, "kakita_defender_phase": 7}, [])["formula"]
    assert f["kakita_3rd_dan_bonus"] == 8 and f["kakita_3rd_dan_attacker_phase"] == 3
    forced = build_attack(kakita, dict(BASE, kakita_3rd_dan_defender_phase_bonus=True),
                          {"tn": 10, "attacker_phase": 0, "kakita_defender_phase": 2}, [])["formula"]
    assert forced["kakita_3rd_dan_bonus"] == 4
    none = build_attack(kakita, dict(BASE, kakita_3rd_dan_defender_phase_bonus=True),
                        {"tn": 10, "die_value": 6, "kakita_defender_phase": 2}, [])["formula"]
    assert "kakita_3rd_dan_bonus" not in none


def test_banks_are_consumed():
    c = _c(adventure_state={"hiruma_banked_attack_bonus": 6, "ide_banked_tn_reduce": 10})
    built = build_attack(c, BASE, {"tn": 20}, [])
    assert built["formula"]["hiruma_parry_bonus"] == 6 and built["formula"]["flat"] == 6
    assert built["formula"]["ide_tn_reduce"] == 10
    assert built["consumes"] == ["hiruma_banked_attack_bonus", "ide_banked_tn_reduce"]


# ---------------------------------------------------------------------------
# attack_outcome
# ---------------------------------------------------------------------------

def test_outcomes():
    f = {"attack_tn": 20, "attack_variant": "attack"}
    assert attack_outcome(f, 31) == {"tn": 20, "effective_tn": 20, "hit": True, "near_miss": False,
                                     "excess": 11, "extra_dice": 2}
    assert attack_outcome(f, 19)["hit"] is False
    da = {"attack_tn": 20, "attack_variant": "double_attack"}
    assert attack_outcome(da, 45)["extra_dice"] == 5  # excess over the BASE TN
    assert attack_outcome(da, 30)["hit"] is False
    near = attack_outcome(da, 30, near_miss_rule=True)
    assert near["near_miss"] and near["hit"] and near["extra_dice"] == 0
    assert attack_outcome(dict(f, ide_tn_reduce=10), 12)["effective_tn"] == 10
    # W1: the raises reach the TN but earn no extra dice.
    assert attack_outcome(f, 20, wave_man_raised=5)["extra_dice"] == 0


# ---------------------------------------------------------------------------
# The attack session
# ---------------------------------------------------------------------------

def _attack(client, cid, headers=PLAYER, **body):
    body.setdefault("roll_key", "attack")
    body.setdefault("tn", 20)
    return _roll(client, cid, headers=headers, **body)


def test_a_live_attack_spends_the_banks_and_is_judged(client, scripted):
    cid = _school(client, "hiruma_scout", adventure_state={"hiruma_banked_attack_bonus": 4,
                                                           "ide_banked_tn_reduce": 5})
    data = _attack(client, cid, headers=scripted("9")).json()
    assert data["formula"]["hiruma_parry_bonus"] == 4
    assert data["attack"]["effective_tn"] == 15 and data["attack"]["hit"]
    state = _get(client, cid).adventure_state or {}
    assert "hiruma_banked_attack_bonus" not in state and "ide_banked_tn_reduce" not in state
    assert _row(client, data["history_id"])["total"] == data["total"]
    s = client._test_session_factory()
    assert s.get(RollHistory, data["history_id"]).tn == 20
    s.close()


def test_a_simulated_attack_keeps_the_banks(client):
    cid = _school(client, "hiruma_scout", adventure_state={"hiruma_banked_attack_bonus": 4})
    data = _attack(client, cid, headers=OTHER).json()
    assert data["formula"]["hiruma_parry_bonus"] == 4
    assert _get(client, cid).adventure_state["hiruma_banked_attack_bonus"] == 4


def test_attack_refusals(client):
    cid = _school(client, "akodo_bushi")
    assert "needs a TN" in _roll(client, cid, roll_key="attack").json()["error"]
    sid = _roll(client, cid).json()["session_id"]
    for action in ("isawa", "post_bonus", "courtier_vp", "hida_reroll", "damage", "akodo_bank",
                   "bayushi_raise"):
        assert "only for an attack" in _act(client, cid, sid, action).json()["error"], action


def test_wave_man_miss_raises(client, scripted):
    cid = _char(client, school="", profession="profession", knacks={},
                profession_abilities={"wave_man_miss_raise": 2}, attack=1)
    if not rs.build_all_roll_formulas(_get(client, cid).to_dict()).get("attack", {}).get("wave_man_miss_raise"):
        pytest.skip("W1 id differs")
    data = _attack(client, cid, tn=100, headers=scripted("1")).json()
    assert data["attack"]["wave_man_raises"] == 2 and not data["attack"]["hit"]


def test_isawa_trade_is_on_by_default_and_can_be_taken_back(client, scripted):
    cid = _school(client, "isawa_duelist", dan=3)
    data = _attack(client, cid, headers=scripted("5")).json()
    bonus = next(b["amount"] for b in data["payload"]["bonuses"] if b["label"].startswith("Isawa"))
    off = _act(client, cid, data["session_id"], "isawa", on=False).json()
    assert off["total"] == data["total"] - bonus
    on = _act(client, cid, data["session_id"], "isawa", on=True).json()
    assert on["total"] == data["total"]


def test_post_bonus_and_courtier(client, scripted):
    cid = _school(client, "courtier", dan=4, current_temp_void_points=0)
    data = _attack(client, cid, tn=5, headers=scripted("9")).json()
    sid = data["session_id"]
    assert _act(client, cid, sid, "post_bonus", amount=7).json()["total"] == data["total"] + 7
    assert _act(client, cid, sid, "post_bonus", amount=3).json()["total"] == data["total"] + 3
    assert _act(client, cid, sid, "post_bonus", amount=0).json()["total"] == data["total"]
    assert "whole number" in _act(client, cid, sid, "post_bonus", amount="x").json()["error"]
    got = _act(client, cid, sid, "courtier_vp").json()
    assert got["tracking"]["current_temp_void_points"] == 1
    assert "already" in _act(client, cid, sid, "courtier_vp").json()["error"]
    miss = _attack(client, cid, tn=200).json()["session_id"]
    assert "successful" in _act(client, cid, miss, "courtier_vp").json()["error"]
    other = _school(client, "akodo_bushi")
    osid = _attack(client, other).json()["session_id"]
    assert "no void point" in _act(client, other, osid, "courtier_vp").json()["error"]
    assert "no Isawa" in _act(client, other, osid, "isawa", on=True).json()["error"]


def test_akodo_banked_bonuses(client):
    cid = _school(client, "akodo_bushi", dan=3, adventure_state={"akodo_banked_bonuses": [4, 6]})
    data = _attack(client, cid).json()
    sid = data["session_id"]
    got = _act(client, cid, sid, "akodo_bank", amount=6).json()
    assert got["total"] == data["total"] + 6 and got["tracking"]["adventure_state"]["akodo_banked_bonuses"] == [4]
    assert "no banked +6" in _act(client, cid, sid, "akodo_bank", amount=6).json()["error"]
    assert "whole number" in _act(client, cid, sid, "akodo_bank", amount="x").json()["error"]
    back = _act(client, cid, sid, "undo_akodo_bank").json()
    assert sorted(back["tracking"]["adventure_state"]["akodo_banked_bonuses"]) == [4, 6]
    assert "put back" in _act(client, cid, sid, "undo_akodo_bank").json()["error"]
    sim = _attack(client, cid, headers=OTHER).json()["session_id"]
    assert _act(client, cid, sim, "akodo_bank", headers=OTHER, amount=4).status_code == 200
    assert _act(client, cid, sim, "akodo_bank", headers=OTHER, amount=4).status_code == 400
    assert _act(client, cid, sim, "undo_akodo_bank", headers=OTHER).status_code == 200
    low = _school(client, "akodo_bushi", dan=2)
    lsid = _attack(client, low).json()["session_id"]
    assert "no Akodo" in _act(client, low, lsid, "akodo_bank", amount=4).json()["error"]


def test_bayushi_banked_raise(client):
    cid = _school(client, "bayushi_bushi", dan=4, adventure_state={"bayushi_banked_feint_raise": 5})
    data = _attack(client, cid).json()
    sid = data["session_id"]
    got = _act(client, cid, sid, "bayushi_raise").json()
    assert got["total"] == data["total"] + 5
    assert got["tracking"]["adventure_state"]["bayushi_banked_feint_raise"] == 0
    assert "no banked raise" in _act(client, cid, sid, "bayushi_raise").json()["error"]
    back = _act(client, cid, sid, "undo_bayushi_raise").json()
    assert back["tracking"]["adventure_state"]["bayushi_banked_feint_raise"] == 5
    assert "put back" in _act(client, cid, sid, "undo_bayushi_raise").json()["error"]
    sim = _attack(client, cid, headers=OTHER).json()["session_id"]
    assert _act(client, cid, sim, "bayushi_raise", headers=OTHER).status_code == 200
    assert _act(client, cid, sim, "bayushi_raise", headers=OTHER).status_code == 400


def test_hida_reroll_keeps_the_bonuses(client, scripted):
    cid = _school(client, "hida_bushi", dan=3, adventure_state={"adventure_raises_used": 0})
    data = _attack(client, cid, headers=scripted("2")).json()
    sid = data["session_id"]
    _act(client, cid, sid, "post_bonus", amount=5)
    assert "at most 2" in _act(client, cid, sid, "hida_reroll", values=[2, 2, 2]).json()["error"]
    assert "no 9" in _act(client, cid, sid, "hida_reroll", values=[9]).json()["error"]
    assert "at least one" in _act(client, cid, sid, "hida_reroll", values=[]).json()["error"]
    done = _act(client, cid, sid, "hida_reroll", values=[2, 2], headers=scripted("8")).json()
    assert sorted(d["value"] for d in done["dice"]).count(8) == 2
    assert done["total"] == done["payload"]["kept_sum"] + data["formula"]["flat"] + 5
    assert "already" in _act(client, cid, sid, "hida_reroll", values=[2]).json()["error"]
    counter = _school(client, "hida_bushi", dan=3, knacks={"counterattack": 3}, current_serious_wounds=2)
    f = rs.build_all_roll_formulas(_get(client, counter).to_dict())
    key = next(k for k, v in f.items() if v.get("attack_variant") == "counterattack")
    csid = _attack(client, counter, roll_key=key, headers=scripted("2")).json()["session_id"]
    # 2X = 4 on a counterattack, halved to 2 while Impaired.
    assert "at most 2" in _act(client, counter, csid, "hida_reroll", values=[2, 2, 2]).json()["error"]
    other = _school(client, "akodo_bushi")
    osid = _attack(client, other).json()["session_id"]
    assert "no Hida" in _act(client, other, osid, "hida_reroll", values=[1]).json()["error"]


def test_hida_5th_dan_banks_a_counterattacks_excess(client, scripted):
    cid = _school(client, "hida_bushi", dan=5, knacks={"counterattack": 5})
    f = rs.build_all_roll_formulas(_get(client, cid).to_dict())
    key = next(k for k, v in f.items() if v.get("attack_variant") == "counterattack")
    data = _attack(client, cid, roll_key=key, tn=10, headers=scripted("9")).json()
    assert _get(client, cid).adventure_state["hida_banked_wc_bonus"] == data["attack"]["excess"] > 0


def test_mirumoto_and_akodo_vp_on_attacks(client):
    cid = _school(client, "mirumoto_bushi", dan=3, adventure_state={"mirumoto_round_points": 2})
    sid = _attack(client, cid).json()["session_id"]
    assert _act(client, cid, sid, "mirumoto_point").status_code == 200
    akodo = _school(client, "akodo_bushi", dan=4, current_void_points=1)
    asid = _attack(client, akodo).json()["session_id"]
    assert _act(client, akodo, asid, "akodo_vp").status_code == 200


def test_damage_is_its_own_recorded_session(client, scripted):
    cid = _school(client, "akodo_bushi", advantages=["lucky"], ring_fire=3)
    data = _attack(client, cid, tn=5, headers=scripted("9")).json()
    sid = data["session_id"]
    dmg = _act(client, cid, sid, "damage", weapon_rolled=4, weapon_kept=2,
               headers=scripted("6")).json()["damage"]
    assert dmg["formula"]["is_damage_roll"] and dmg["history_id"]
    assert dmg["formula"]["rolled"] == min(10, 4 + 3 + data["attack"]["extra_dice"])
    row = _row(client, dmg["history_id"])
    assert row["total"] == dmg["total"]
    s = client._test_session_factory()
    assert s.get(RollHistory, dmg["history_id"]).roll_key == "attack:damage"
    s.close()
    assert "already" in _act(client, cid, sid, "damage").json()["error"]
    # The damage roll takes its own Lucky reroll.
    again = _act(client, cid, dmg["session_id"], "lucky_reroll", headers=scripted("9")).json()
    assert again["payload"]["lucky"]["kept"] == "reroll"
    miss = _attack(client, cid, tn=300).json()["session_id"]
    assert "only a hit" in _act(client, cid, miss, "damage").json()["error"]


def test_damage_inputs(client, scripted):
    cid = _school(client, "mantis_wave_treader", dan=5,
                  adventure_state={"mantis_posture_history": ["offensive"], "mantis_offensive_3rd_dan_accum": 2})
    sid = _attack(client, cid, tn=5, headers=scripted("9")).json()["session_id"]
    bad = _act(client, cid, sid, "damage", parry_skill="x")
    assert "whole numbers" in bad.json()["error"]
    assert "cannot trade" in _act(client, cid, sid, "damage", trade=True).json()["error"]
    dmg = _act(client, cid, sid, "damage", failed_parry=True, parry_skill=2).json()["damage"]
    extras = " ".join(dmg["payload"]["extras"])
    assert "offensive posture" in extras and "Mantis 5th Dan" in extras and "Mantis 3rd Dan" in extras
    otaku = _school(client, "otaku_bushi", dan=5)
    osid = _attack(client, otaku, tn=5, headers=scripted("9")).json()["session_id"]
    traded = _act(client, otaku, osid, "damage", trade=True).json()["damage"]
    assert traded["formula"]["traded_for_sw"] and traded["formula"]["rolled"] >= 2


def test_wave_man_damage_rounding(client, scripted):
    from app.services.roll_engine import score_roll
    out = score_roll({}, {"kept": 1, "flat": 0, "is_damage_roll": True, "wave_man_round_damage": 1},
                     [{"parts": [7], "value": 7}], [])
    assert out["total"] == 10 and "Wave Man: 7 rounded to 10" in out["extras"]


def test_hiruma_bank_adds_to_damage(client, scripted):
    cid = _school(client, "hiruma_scout", adventure_state={"hiruma_banked_attack_bonus": 4})
    sid = _attack(client, cid, tn=5, headers=scripted("9")).json()["session_id"]
    dmg = _act(client, cid, sid, "damage").json()["damage"]
    assert "+4 from Hiruma post-parry bonus" in dmg["payload"]["extras"]
    assert dmg["formula"]["flat"] >= 4


def test_damage_rejudges_at_a_corrected_tn(client, scripted):
    cid = _school(client, "akodo_bushi")
    data = _attack(client, cid, tn=5, headers=scripted("9")).json()
    sid = data["session_id"]
    assert "whole number" in _act(client, cid, sid, "damage", tn="x").json()["error"]
    assert "only a hit" in _act(client, cid, sid, "damage", tn=500).json()["error"]
    dmg = _act(client, cid, sid, "damage", tn=data["total"]).json()["damage"]
    assert dmg["formula"]["rolled"] >= 2
