"""Archery attacks (rules/03-combat.md "Archery Rules"; archery-design/design.md).

The formula: an arrow is an attack, and the school bonuses of every other
attack type stack onto it. The roll session: the TN from its parts, the hold
and extra-action bonuses, the damage table and the automatic serious wounds.
"""

import pytest

from app.services.dice import (
    build_all_roll_formulas,
    build_archery_formula,
    is_combat_roll,
    _discordant_blocks_void,
)
from tests.conftest import make_character_data


def _bonus(formula, label):
    return [b["amount"] for b in formula["bonuses"] if b["label"] == label]


# ---------------------------------------------------------------------------
# The formula
# ---------------------------------------------------------------------------


class TestArcheryFormula:
    def test_rules_example_kakita_4th_dan(self):
        """The rules' own example: a 4th Dan Kakita gets +2k0 + 5 on the arrow
        (1st Dan's iaijutsu and double attack dice, 2nd Dan's iaijutsu raise)
        and +5 damage (4th Dan, normally iaijutsu only). The iaijutsu rank is
        a separate rule and adds on top."""
        char = make_character_data(
            school="kakita_duelist", attack=2, rings={"Air": 2, "Fire": 3, "Earth": 2, "Water": 2, "Void": 2},
            knacks={"double_attack": 4, "iaijutsu": 4, "lunge": 4},
        )
        f = build_all_roll_formulas(char)
        plain, arrow = f["attack"], f["archery"]
        assert arrow["rolled"] - plain["rolled"] == 2
        assert arrow["kept"] == plain["kept"] == 3
        assert _bonus(arrow, "2nd Dan technique (iaijutsu)") == [5]
        assert _bonus(arrow, "Iaijutsu (4)") == [4]
        assert arrow["flat"] - plain["flat"] == 9
        assert arrow["damage_flat_bonus"] == 5
        assert "+5 from 4th Dan (iaijutsu)" in arrow["damage_bonus_sources"]
        assert plain["damage_flat_bonus"] == 0
        assert "+1 rolled die from 1st Dan (double attack)" in arrow["bonus_sources"]
        assert "+1 rolled die from 1st Dan (iaijutsu)" in arrow["bonus_sources"]

    def test_kakita_below_4th_dan_no_damage_bonus(self):
        char = make_character_data(school="kakita_duelist", knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3})
        assert build_all_roll_formulas(char)["archery"]["damage_flat_bonus"] == 0

    def test_attack_and_double_attack_dice_stack(self):
        # Akodo 1st Dan: +1k0 attack AND +1k0 double attack.
        char = make_character_data(school="akodo_bushi", attack=2,
                                   knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        f = build_all_roll_formulas(char)
        # attack 2 + Fire 2 = 4, +1 attack, +1 double attack.
        assert f["archery"]["rolled"] == 6
        assert f["attack"]["rolled"] == 5
        assert f["archery"]["label"] == "Archery (Fire)"

    def test_counterattack_raise_stacks(self):
        # Hida 2nd Dan: +5 on counterattack.
        char = make_character_data(school="hida_bushi", knacks={"counterattack": 2, "iaijutsu": 2, "lunge": 2})
        assert _bonus(build_all_roll_formulas(char)["archery"], "2nd Dan technique (counterattack)") == [5]

    def test_lunge_bonuses_left_out(self):
        # Otaku 1st Dan: +1k0 iaijutsu and lunge. Only the iaijutsu die stacks.
        char = make_character_data(school="otaku_bushi", knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1})
        f = build_all_roll_formulas(char)
        assert f["archery"]["rolled"] - f["attack"]["rolled"] == 1
        assert not any("lunge" in s for s in f["archery"]["bonus_sources"])

    def test_flexible_first_dan_pick_on_iaijutsu(self):
        char = make_character_data(
            school="kitsune_warden", knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1},
            technique_choices={"first_dan_choices": ["iaijutsu", "parry", "damage"]},
        )
        f = build_all_roll_formulas(char)
        assert f["archery"]["rolled"] - f["attack"]["rolled"] == 1
        # The damage pick is a rolled damage die: on an arrow, 5 excess.
        assert f["archery"]["archery_damage_excess"] == 5

    def test_no_iaijutsu_no_flat(self):
        char = make_character_data(school="hida_bushi", knacks={"counterattack": 1, "lunge": 1})
        arrow = build_all_roll_formulas(char)["archery"]
        assert arrow["archery_iaijutsu_bonus"] == 0
        assert not any(b["label"].startswith("Iaijutsu") for b in arrow["bonuses"])

    def test_foreign_iaijutsu_counts(self):
        char = make_character_data(school="hida_bushi", knacks={"counterattack": 1, "lunge": 1},
                                   foreign_knacks={"iaijutsu": 2})
        arrow = build_all_roll_formulas(char)["archery"]
        assert arrow["archery_iaijutsu_bonus"] == 2
        assert _bonus(arrow, "Iaijutsu (2)") == [2]

    def test_double_attack_serious_wound(self):
        with_da = make_character_data(school="akodo_bushi", knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        without = make_character_data(school="hida_bushi", knacks={"counterattack": 1, "iaijutsu": 1, "lunge": 1})
        assert build_all_roll_formulas(with_da)["archery"]["archery_double_attack_sw"] == 1
        assert build_all_roll_formulas(without)["archery"]["archery_double_attack_sw"] == 0

    def test_is_an_attack_type_and_a_combat_roll(self):
        arrow = build_all_roll_formulas(make_character_data())["archery"]
        assert arrow["is_attack_type"] is True
        assert arrow["attack_variant"] == "archery"
        assert arrow["is_combat_roll"] is True
        assert is_combat_roll("archery")
        assert _discordant_blocks_void("archery")

    def test_discordant_blocks_void(self):
        char = make_character_data(disadvantages=["discordant"])
        assert build_all_roll_formulas(char)["archery"]["void_blocked"] is True

    def test_damage_dice_become_excess(self):
        # Yogo 1st Dan: +1 rolled damage die -> 5 excess, never a die.
        char = make_character_data(school="yogo_warden", knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        arrow = build_all_roll_formulas(char)["archery"]
        assert arrow["damage_extra_rolled"] == 1
        assert arrow["archery_damage_excess"] == 5

    def test_third_dan_raises_reach_the_arrow(self):
        # Doji 3rd Dan: culture free raises usable on counterattack only.
        char = make_character_data(
            school="doji_artisan", skills={"culture": 2},
            knacks={"counterattack": 3, "oppose_social": 3, "worldliness": 3},
        )
        f = build_all_roll_formulas(char)
        assert f["archery"]["adventure_raises_max_per_roll"] == 2
        assert not f["attack"].get("adventure_raises_max_per_roll")

    def test_third_dan_on_attack_reaches_the_arrow(self):
        char = make_character_data(school="kitsuki_magistrate", skills={"investigation": 3},
                                   knacks={"discern_honor": 3, "iaijutsu": 3, "presence": 3})
        assert build_all_roll_formulas(char)["archery"]["adventure_raises_max_per_roll"] == 3

    def test_no_attack_skill_no_arrow(self):
        assert build_archery_formula(make_character_data(attack=0)) is None

    def test_dice_past_ten_become_kept(self):
        char = make_character_data(school="akodo_bushi", attack=5,
                                   rings={"Air": 2, "Fire": 5, "Earth": 2, "Water": 3, "Void": 2},
                                   knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        arrow = build_archery_formula(char)
        # 5 + 5 + 2 = 12 rolled -> 10k7.
        assert (arrow.rolled, arrow.kept) == (10, 7)


# ---------------------------------------------------------------------------
# The roll session (the server makes the arrow)
# ---------------------------------------------------------------------------

from app.models import RollHistory  # noqa: E402
from app.services import roll_sessions as rs  # noqa: E402
from app.services.attack_rolls import build_attack  # noqa: E402
from tests.test_roll_sessions import OTHER, PLAYER, _act, _char, _get, _row, _school  # noqa: E402,F401
from tests.test_roll_sessions import scripted  # noqa: E402,F401


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield


DICE = [{"value": 1, "spent": True}, {"value": 2, "spent": False}, {"value": 4, "spent": False},
        {"value": 8, "spent": False}, {"value": 3, "spent": False, "athletics_only": True}]


def _arrow(client, cid, headers=PLAYER, **archery):
    archery.setdefault("base_tn", 5)
    return client.post(f"/characters/{cid}/roll", json={"roll_key": "archery", "archery": archery},
                       headers=headers)


class _Char:
    def __init__(self, dice=(), state=None):
        self.action_dice = [dict(d) for d in dice]
        self.adventure_state = state or {}

    def to_dict(self):
        return {"school": "akodo_bushi", "knacks": {}, "attack": 1}


def _build(archery, dice=DICE, state=None):
    return build_attack(_Char(dice, state), {"flat": 0, "bonuses": [], "attack_variant": "archery"},
                        {"archery": archery}, [])["formula"]


class TestArcheryInputs:
    def test_tn_from_its_parts(self):
        f = _build({"base_tn": 20, "distance": 3, "evasion": True, "cover": 10})
        assert f["attack_tn"] == 55
        assert [p["label"] for p in f["archery_tn_parts"]] == ["base TN", "200-399 ft", "evasion", "cover"]
        assert _build({"unseen": True, "distance": 0})["attack_tn"] == 10
        assert _build({"unseen": True})["archery_unseen"] is True

    def test_bad_inputs(self):
        for bad, msg in [({}, "target's TN"), ({"base_tn": "x"}, "whole number"),
                         ({"base_tn": 5, "extra_dice": [2]}, "current phase"),
                         ({"base_tn": 5, "phase": 5, "die_index": 9}, "no such action die"),
                         ({"base_tn": 5, "phase": 5, "die_index": 4}, "athletics"),
                         ({"base_tn": 5, "phase": 5, "die_index": 0, "extra_dice": [0]}, "only once"),
                         ({"base_tn": 5, "phase": 5, "extra_dice": [0]}, "already spent"),
                         ({"base_tn": 5, "phase": 5, "extra_dice": [3]}, "has not come up"),
                         ({"base_tn": 5, "extra_dice": "2"}, "must be a list"),
                         ({"base_tn": 5, "phase": 5, "die_index": True}, "no such action die")]:
            with pytest.raises(ValueError, match=msg):
                _build(bad)
        with pytest.raises(ValueError, match="an object"):
            build_attack(_Char(), {"flat": 0, "bonuses": [], "attack_variant": "archery"},
                         {"archery": [1]}, [])

    def test_rules_example_two_dice_in_phase_five(self):
        """GM, Q1: dice 1 and 2 on one arrow in phase 5 = +4 + (5 + 3) = +12."""
        f = _build({"base_tn": 5, "phase": 5, "die_index": 0, "extra_dice": [1]})
        assert f["flat"] == 12
        labels = {b["label"]: b["amount"] for b in f["bonuses"]}
        assert labels == {"held 4 phases (die 1)": 4, "1 extra action (dice 2)": 8}
        assert f["archery_spend"] == {"dice": [1], "phase": 5}

    def test_hold_counts_from_the_last_arrow(self):
        f = _build({"base_tn": 5, "phase": 5, "die_index": 1}, state={"archery_last_arrow_phase": 5})
        assert f["flat"] == 0
        f = _build({"base_tn": 5, "phase": 8, "die_index": 1, "extra_dice": [2]},
                   state={"archery_last_arrow_phase": 5})
        assert f["flat"] == 3 + 5 + 3

    def test_moving_drops_the_hold(self):
        f = _build({"base_tn": 5, "phase": 6, "die_index": 0, "extra_dice": [1, 2], "moving": True})
        assert f["flat"] == 10
        assert f["archery_moving"] is True

    def test_no_dice_no_bonus(self):
        f = _build({"base_tn": 15}, dice=[])
        assert f["flat"] == 0 and f["archery_spend"] == {"dice": [], "phase": 0}


class TestArcherySession:
    def test_live_arrow_spends_extras_and_remembers_the_phase(self, client, scripted):
        cid = _school(client, "akodo_bushi", action_dice=[dict(d) for d in DICE[:4]])
        data = _arrow(client, cid, base_tn=10, distance=1, phase=5, die_index=0, extra_dice=[1],
                      headers=scripted("9")).json()
        assert data["attack"]["tn"] == 20
        assert data["formula"]["attack_variant"] == "archery"
        c = _get(client, cid)
        assert c.action_dice[1]["spent"] and c.action_dice[1]["spent_by"] == "Archery (extra action)"
        assert not c.action_dice[2]["spent"]
        assert c.adventure_state["archery_last_arrow_phase"] == 5
        s = client._test_session_factory()
        assert s.get(RollHistory, data["history_id"]).roll_key == "archery"
        assert s.get(RollHistory, data["history_id"]).payload["skill_rank"] == 2
        s.close()

    def test_simulated_arrow_changes_nothing(self, client, scripted):
        cid = _school(client, "akodo_bushi", action_dice=[dict(d) for d in DICE[:4]])
        data = _arrow(client, cid, phase=5, die_index=0, extra_dice=[1],
                      headers=scripted("9", base=OTHER)).json()
        assert data["mode"] == "simulate"
        c = _get(client, cid)
        assert not c.action_dice[1]["spent"]
        assert "archery_last_arrow_phase" not in (c.adventure_state or {})

    def test_bad_input_is_refused(self, client):
        cid = _school(client, "akodo_bushi")
        r = client.post(f"/characters/{cid}/roll", json={"roll_key": "archery", "archery": {}},
                        headers=PLAYER)
        assert r.status_code == 400 and "TN" in r.json()["error"]

    def test_initiative_clears_the_last_arrow_phase(self):
        from app.services.tracking import PER_ROUND_STATE_KEYS
        assert "archery_last_arrow_phase" in PER_ROUND_STATE_KEYS

    def test_arrow_damage_band_and_serious_wounds(self, client, scripted):
        # Akodo holds double attack: 2 automatic serious wounds.
        cid = _school(client, "akodo_bushi", ring_fire=3)
        sid = _arrow(client, cid, base_tn=5, headers=scripted("9")).json()["session_id"]
        # The first scripted die is the table roll: 7 against the shifted odds.
        dmg = _act(client, cid, sid, "damage", headers=scripted("7,5")).json()["damage"]
        f = dmg["formula"]
        assert f["arrow_damage"] and f["rolled"] == 10 and f["arrow_d10"] == 7
        assert f["arrow_serious_wounds"] == 2
        assert dmg["payload"]["serious_wounds"] == 2
        assert dmg["payload"]["title"] == "Arrow Damage"
        s = client._test_session_factory()
        assert s.get(RollHistory, dmg["history_id"]).roll_key == "archery:damage"
        s.close()
        assert "already" in _act(client, cid, sid, "damage").json()["error"]

    def test_the_bands_follow_the_excess(self, client, scripted):
        # Attack 2 + Fire 2 = 5k2 with Akodo's 1st Dan dice (6k2 on an arrow):
        # every die a 4 keeps 8, so 8 - 5 = 3 over: no shift. A table roll of
        # 1 is 10k2.
        cid = _school(client, "akodo_bushi")
        sid = _arrow(client, cid, base_tn=0, headers=scripted("4")).json()["session_id"]
        dmg = _act(client, cid, sid, "damage", headers=scripted("1,5")).json()["damage"]
        assert dmg["formula"]["arrow_band_odds"] == [3, 3, 3, 1]
        assert dmg["formula"]["kept"] == 2
        assert "10k2 arrow (table roll 1: 30% chance)" in dmg["payload"]["extras"]

    def test_raises_past_forty_five(self, client, scripted):
        cid = _school(client, "akodo_bushi", attack=5, ring_fire=5)
        # 10k7 of 9s + the 1st Dan flats + 30 extra, against TN 10 (unseen,
        # close): far past 45 over, so 10k8 is certain and the rest are raises.
        data = client.post(f"/characters/{cid}/roll", json={
            "roll_key": "archery", "extra_bonus": 30, "archery": {"unseen": True}},
            headers=scripted("9")).json()
        excess = data["attack"]["excess"]
        assert excess >= 60
        raises = excess // 5 - 9
        dmg = _act(client, cid, data["session_id"], "damage", headers=scripted("1,5")).json()["damage"]
        assert dmg["formula"]["arrow_band_odds"] == [0, 0, 0, 10]
        assert dmg["formula"]["kept"] == 8
        assert f"+{5 * raises} from {raises} free raises (beat the TN by more than 45)" in dmg["payload"]["extras"]

    def test_failed_parry_takes_back_one_serious_wound(self, client, scripted):
        cid = _school(client, "kitsuki_magistrate")  # no double attack: 1 serious wound
        sid = _arrow(client, cid, headers=scripted("9")).json()["session_id"]
        dmg = _act(client, cid, sid, "damage", failed_parry=True, headers=scripted("5")).json()["damage"]
        assert dmg["payload"]["serious_wounds"] == 0
        assert any("failed parry" in e for e in dmg["payload"]["extras"])
        cid2 = _school(client, "akodo_bushi")
        sid2 = _arrow(client, cid2, headers=scripted("9")).json()["session_id"]
        dmg2 = _act(client, cid2, sid2, "damage", failed_parry=True, headers=scripted("5")).json()["damage"]
        assert dmg2["payload"]["serious_wounds"] == 1

    def test_no_dice_trade_on_an_arrow(self, client, scripted):
        cid = _school(client, "otaku_bushi", dan=5)
        sid = _arrow(client, cid, headers=scripted("9")).json()["session_id"]
        assert "no damage dice" in _act(client, cid, sid, "damage", trade=True).json()["error"]

    def test_ability_damage_dice_shift_the_bands(self, client, scripted):
        # Bayushi: +1k1 damage per void point on the attack = 10 excess each.
        cid = _school(client, "bayushi_bushi", current_void_points=2)
        sid = client.post(f"/characters/{cid}/roll",
                          json={"roll_key": "archery", "void": 1, "archery": {"base_tn": 0}},
                          headers=scripted("4")).json()
        dmg = _act(client, cid, sid["session_id"], "damage", headers=scripted("1,5")).json()["damage"]
        assert "+10 excess from abilities" in dmg["payload"]["extras"]

    def test_flat_damage_bonuses_and_mantis(self, client, scripted):
        cid = _school(client, "kakita_duelist", dan=4)
        sid = _arrow(client, cid, headers=scripted("9")).json()["session_id"]
        dmg = _act(client, cid, sid, "damage", headers=scripted("5")).json()["damage"]
        assert "+5 from 4th Dan (iaijutsu)" in dmg["payload"]["extras"]
        mantis = _school(client, "mantis_wave_treader", dan=5,
                         adventure_state={"mantis_posture_history": ["offensive"]})
        msid = _arrow(client, mantis, headers=scripted("9")).json()["session_id"]
        mdmg = _act(client, mantis, msid, "damage", headers=scripted("5")).json()["damage"]
        assert any("offensive posture" in e for e in mdmg["payload"]["extras"])
        hiruma = _school(client, "hiruma_scout", adventure_state={"hiruma_banked_attack_bonus": 4})
        hsid = _arrow(client, hiruma, headers=scripted("9")).json()["session_id"]
        hdmg = _act(client, hiruma, hsid, "damage", headers=scripted("5")).json()["damage"]
        assert "+4 from Hiruma 3rd Dan (after a parry)" in hdmg["payload"]["extras"]

    def test_hida_rerolls_two_x(self, client, scripted):
        cid = _school(client, "hida_bushi", dan=3, attack=2)
        sid = _arrow(client, cid, headers=scripted("3")).json()["session_id"]
        r = _act(client, cid, sid, "hida_reroll", values=[3, 3, 3, 3], headers=scripted("5"))
        assert r.status_code == 200, r.json()
        r5 = _act(client, cid, _arrow(client, cid, headers=scripted("3")).json()["session_id"],
                  "hida_reroll", values=[3, 3, 3, 3, 3])
        assert "at most 4" in r5.json()["error"]

    def test_a_patch_keeps_the_arrow_fields(self, client, scripted):
        cid = _school(client, "akodo_bushi")
        sid = _arrow(client, cid, headers=scripted("9")).json()["session_id"]
        dmg = _act(client, cid, sid, "damage", headers=scripted("7,5")).json()["damage"]
        r = client.patch(f"/characters/{cid}/rolls/{dmg['history_id']}", headers=PLAYER,
                         json={"payload": {"title": "Arrow Damage", "total": 99, "serious_wounds": 0}})
        assert r.status_code == 200
        row = _row(client, dmg["history_id"])
        assert row["total"] == 99
        assert row["serious_wounds"] == 2 and row["arrow_d10"] == 7
        # A plain attack's damage row has none of them to carry.
        plain = client.post(f"/characters/{cid}/roll", json={"roll_key": "attack", "tn": 5},
                            headers=scripted("9")).json()
        pd = _act(client, cid, plain["session_id"], "damage", headers=scripted("5")).json()["damage"]
        client.patch(f"/characters/{cid}/rolls/{pd['history_id']}", headers=PLAYER,
                     json={"payload": {"title": "Damage", "total": 3}})
        assert "serious_wounds" not in _row(client, pd["history_id"])


def test_statistics_cover_the_arrow():
    from app.services.roll_stats import averages, notes
    data = make_character_data()
    f = build_all_roll_formulas(data)
    assert "archery" in averages(data, f)
    assert any(n.startswith("Archery:") for n in notes(data, f["archery"]))
    assert not any(n.startswith("Archery:") for n in notes(data, f["attack"]))


def test_attack_actions_reach_the_arrow(client, scripted):
    """The post-roll attack actions accept an archery session."""
    cid = _school(client, "mirumoto_bushi", dan=3, adventure_state={"mirumoto_round_points": 2})
    sid = _arrow(client, cid, headers=scripted("5")).json()["session_id"]
    assert _act(client, cid, sid, "mirumoto_point").status_code == 200
    akodo = _school(client, "akodo_bushi", dan=4, current_void_points=1, advantages=["lucky"])
    asid = _arrow(client, akodo, headers=scripted("5")).json()["session_id"]
    assert _act(client, akodo, asid, "akodo_vp").status_code == 200
    assert _act(client, akodo, asid, "lucky_reroll", headers=scripted("9")).status_code == 200
    isawa = _school(client, "isawa_duelist", dan=3)
    data = _arrow(client, isawa, headers=scripted("5")).json()
    assert any(b["label"].startswith("Isawa") for b in data["payload"]["bonuses"])


def test_descriptions_and_no_kitsune_swap():
    from app.services.roll_descriptions import describe_roll
    assert describe_roll("archery")["title"] == "Archery"
    assert describe_roll("archery:damage")["title"] == "Damage (Archery)"
    assert "10k8" in describe_roll("archery:damage")["body"]
    # The Kitsune ring swap is not offered on an arrow (design "Later"):
    # applying it would drop every stacked die.
    char = make_character_data(school="kitsune_warden", school_ring_choice="Water",
                               rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
                               knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1})
    f = build_all_roll_formulas(char)
    assert "kitsune_swap" in f["attack"]
    assert "kitsune_swap" not in f["archery"]


def test_shinjo_and_archery_hold_both_apply():
    """GM, Q2: Shinjo's +2 per phase held stacks with the arrow's +1."""
    from app.models import Character
    c = Character(name="S", school="shinjo_bushi", knacks={"double_attack": 1, "iaijutsu": 1, "lunge": 1},
                  attack=1, action_dice=[{"value": 1, "spent": True}], adventure_state={})
    f = build_attack(c, {"flat": 0, "bonuses": [], "attack_variant": "archery", "shinjo_phase_bonus_attack": True},
                     {"die_value": 1, "shinjo_phase": 5, "archery": {"base_tn": 5, "phase": 5, "die_index": 0}},
                     [])["formula"]
    labels = {b["label"]: b["amount"] for b in f["bonuses"]}
    assert labels["held 4 phases (die 1)"] == 4
    assert f["shinjo_phase_bonus"] == 8
    assert f["flat"] == 12


def test_gm_api_reports_an_arrows_serious_wounds(client, scripted, monkeypatch):
    from app.routes import gm_api
    monkeypatch.setenv(gm_api.TOKEN_ENV_VAR, "t0ken")
    cid = _school(client, "akodo_bushi")
    sid = _arrow(client, cid, headers=scripted("9")).json()["session_id"]
    dmg = _act(client, cid, sid, "damage", headers=scripted("5")).json()["damage"]
    rows = client.get("/api/rolls?since=2000-01-01T00:00:00Z",
                      headers={"Authorization": "Bearer t0ken"}).json()["rolls"]
    by_key = {r["roll_key"]: r for r in rows}
    assert by_key["archery:damage"]["serious_wounds"] == dmg["payload"]["serious_wounds"] == 2
    assert "serious_wounds" not in by_key["archery"]
    assert by_key["archery"]["skill_rank"] == 2
