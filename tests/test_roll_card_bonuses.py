"""Every bonus a roll's total includes is LISTED on its card.

The exported dice card (and the roll-history row gm-assistant reads) shows
the kept dice, a BONUSES block and a DETAILS block. A reader adding them up
has to reach the total; when a technique bumped the formula's ``flat``
without naming itself in ``bonuses``, the card showed the right total and no
reason for it (Hiruma 3rd Dan, a ticked Specialization, Kakita 4th Dan's
damage raise, a wound check's 2nd Dan raise...).

Two invariants, checked broadly so a new technique cannot slip past:

* every formula the sheet rolls has ``flat == sum(bonuses)``;
* every payload the server writes adds up: kept dice + bonuses + the
  numeric DETAILS lines ("+10 from 5th Dan ...") == total.
"""

import re

import pytest

from app.game_data import (
    ADVANTAGES, CAMPAIGN_ADVANTAGES, CAMPAIGN_DISADVANTAGES, DISADVANTAGES, SCHOOLS, SKILLS,
)
from app.models import Character
from app.services import roll_sessions as rs
from app.services.attack_rolls import build_attack
from app.services.dice import build_all_roll_formulas
from tests.test_roll_sessions import _act, _roll, _school
from tests.test_roll_sessions import scripted  # noqa: F401

_NUMERIC = re.compile(r"^([+-]\d+)\s")


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield


def _listed(formula):
    return sum(b.get("amount") or 0 for b in formula.get("bonuses") or [])


def _assert_adds_up(payload):
    extras = sum(int(m.group(1)) for e in payload.get("extras") or [] if (m := _NUMERIC.match(e)))
    listed = sum(b["amount"] for b in payload.get("bonuses") or [])
    assert payload["kept_sum"] + listed + extras == payload["total"], payload


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------

def _data(school, dan, loaded):
    advs = list(ADVANTAGES) + list(CAMPAIGN_ADVANTAGES) if loaded else []
    dis = list(DISADVANTAGES) + list(CAMPAIGN_DISADVANTAGES) if loaded else []
    return dict(
        school=school, knacks={k: dan for k in SCHOOLS[school].school_knacks},
        rings={r: 3 for r in ("Air", "Fire", "Earth", "Water", "Void")}, attack=3, parry=3,
        skills={k: 3 for k in SKILLS}, advantages=advs, disadvantages=dis,
        campaign_advantages=advs, campaign_disadvantages=dis,
        technique_choices={"second_dan_choice": "wound_check",
                           "first_dan_choices": ["wound_check", "damage"]},
        specializations=[{"text": "x", "skills": ["attack", "bragging"]}],
    )


@pytest.mark.parametrize("school", sorted(SCHOOLS))
def test_every_formula_lists_its_whole_flat(school):
    for dan in range(1, 6):
        for loaded in (False, True):
            for key, f in build_all_roll_formulas(_data(school, dan, loaded)).items():
                if isinstance(f, dict):
                    assert (f.get("flat") or 0) == _listed(f), (school, dan, loaded, key, f.get("bonuses"))


def _c(**kw):
    data = dict(name="A", school="akodo_bushi", school_ring_choice="Water",
                knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1}, attack=2)
    data.update(kw)
    return Character(**data)


def test_every_attack_input_is_listed():
    """Each situational bonus ``build_attack`` adds, all at once."""
    c = _c(school="kakita_duelist", knacks={"double_attack": 3, "iaijutsu": 3, "lunge": 3},
           adventure_state={"hiruma_banked_attack_bonus": 6, "mantis_posture_history": ["offensive"]})
    base = {"flat": 7, "bonuses": [{"label": "2nd Dan", "amount": 7}], "attack_variant": "attack",
            "doji_5th_dan_always": True, "doji_4th_dan_untouched_target": True,
            "shinjo_phase_bonus_attack": True, "kakita_3rd_dan_defender_phase_bonus": True}
    f = build_attack(c, base, {"tn": 30, "extra_bonus": 4, "doji_phase": 3, "specs": [0],
                               "die_value": 2, "shinjo_phase": 6, "kakita_defender_phase": 5},
                     [{"text": "ambush"}])["formula"]
    labels = {b["label"]: b["amount"] for b in f["bonuses"]}
    assert labels["Hiruma 3rd Dan (after a parry)"] == 6
    assert labels["Specialization (ambush)"] == 10
    assert labels["Kakita 3rd Dan (die 2, defender phase 5, X = 2)"] == 6
    assert labels["Doji 5th Dan (TN 30)"] == 4
    assert f["flat"] == _listed(f)


def test_an_applied_specialization_is_not_also_an_alternative():
    alt = {"label": "if related to Specialization (ambush)", "extra_flat": 10}
    other = {"label": "if related to Specialization (katana)", "extra_flat": 10}
    specs = [{"text": "ambush"}, {"text": "katana"}]
    base = {"flat": 0, "bonuses": [], "alternatives": [alt, other]}
    picked = build_attack(_c(), base, {"tn": 20, "specs": [0]}, specs)["formula"]
    assert picked["alternatives"] == [other]
    unpicked = build_attack(_c(), base, {"tn": 20}, specs)["formula"]
    assert unpicked["alternatives"] == [alt, other]
    # An unnamed spec matches the row dice.py labels "your specialization".
    blank = {"label": "if related to Specialization (your specialization)", "extra_flat": 10}
    got = build_attack(_c(), {"flat": 0, "alternatives": [blank]}, {"tn": 20, "specs": [0]},
                       [{"text": ""}])["formula"]
    assert got["alternatives"] == []


# ---------------------------------------------------------------------------
# Payloads, as the server writes them
# ---------------------------------------------------------------------------

def test_a_hiruma_attack_and_its_damage_add_up(client, scripted):
    cid = _school(client, "hiruma_scout", dan=3, adventure_state={"hiruma_banked_attack_bonus": 6})
    data = _roll(client, cid, roll_key="attack", tn=5, headers=scripted("9")).json()
    assert {"label": "Hiruma 3rd Dan (after a parry)", "amount": 6} in data["payload"]["bonuses"]
    _assert_adds_up(data["payload"])
    dmg = _act(client, cid, data["session_id"], "damage").json()["damage"]
    assert "+6 from Hiruma 3rd Dan (after a parry)" in dmg["payload"]["extras"]
    _assert_adds_up(dmg["payload"])


def test_post_roll_spends_are_listed(client, scripted):
    """Bayushi 4th Dan's banked raise and the GM's extra bonus, after the roll."""
    cid = _school(client, "bayushi_bushi", dan=4, adventure_state={"bayushi_banked_feint_raise": 5})
    data = _roll(client, cid, roll_key="attack", tn=20, headers=scripted("4")).json()
    got = _act(client, cid, data["session_id"], "bayushi_raise").json()
    assert {"label": "Bayushi 4th Dan banked raise", "amount": 5, "post_roll": True} in got["payload"]["bonuses"]
    _assert_adds_up(got["payload"])


def test_a_specialized_attack_adds_up(client, scripted):
    cid = _school(client, "akodo_bushi", specializations=[{"text": "ambush", "skills": ["attack"]}])
    data = _roll(client, cid, roll_key="attack", tn=20, specs=[0], headers=scripted("4")).json()
    assert {"label": "Specialization (ambush)", "amount": 10} in data["payload"]["bonuses"]
    assert data["payload"]["alternatives"] == []
    _assert_adds_up(data["payload"])


def test_kakita_duel_rolls_add_up(client, scripted):
    cid = _school(client, "kakita_duelist", dan=4, ring_fire=3)
    contested = _roll(client, cid, roll_key="iaijutsu:contested", headers=scripted("5")).json()
    assert any(b["amount"] == 5 for b in contested["payload"]["bonuses"])  # 2nd Dan
    _assert_adds_up(contested["payload"])
    strike = _roll(client, cid, roll_key="iaijutsu:strike", opponent_tn=5, headers=scripted("9")).json()
    _assert_adds_up(strike["payload"])
    dmg = _act(client, cid, strike["session_id"], "duel_damage").json()["damage"]
    assert "+5 from 4th Dan (iaijutsu)" in dmg["payload"]["extras"]
    assert "+3k0 from Fire" in dmg["payload"]["extras"]
    _assert_adds_up(dmg["payload"])


def test_kakita_5th_dan_contest_and_damage_add_up(client, scripted):
    cid = _school(client, "kakita_duelist", dan=5, attack=2)
    data = _roll(client, cid, roll_key="kakita_5th_dan", opponent_has_iaijutsu=False, defender_phase=4,
                 opponent_skill_rank=3, headers=scripted("5")).json()
    labels = {b["label"] for b in data["payload"]["bonuses"]}
    assert "5th Dan (opponent has no iaijutsu)" in labels and "contested-roll skill gap" in labels
    _assert_adds_up(data["payload"])
    dmg = _act(client, cid, data["session_id"], "kakita_5th_damage", opponent_roll=data["total"] - 10,
               headers=scripted("6")).json()["damage"]
    assert "+5 from 4th Dan (iaijutsu)" in dmg["payload"]["extras"]
    _assert_adds_up(dmg["payload"])


def test_a_wound_check_lists_its_second_dan_raise(client, scripted):
    cid = _school(client, "akodo_bushi", dan=2, current_light_wounds=10)
    data = _roll(client, cid, roll_key="wound_check", light_wounds=10, headers=scripted("5")).json()
    assert {"label": "2nd Dan", "amount": 5} in data["payload"]["bonuses"]
    _assert_adds_up(data["payload"])


def test_duel_damage_parts_name_school_dice_flat_and_overflow():
    from app.services.duels import duel_damage_pool
    f = {"damage_ring_val": 4, "damage_ring_name": "Fire", "damage_extra_rolled": 1,
         "damage_extra_kept": 1, "damage_flat_bonus": 7,
         "damage_bonus_sources": ["+1k1 from 1st Dan (unarmed)", "+5 from 4th Dan (iaijutsu)"]}
    pool = duel_damage_pool(f, (4, 2), 6)
    assert pool["parts"] == ["4k2 weapon", "+4k0 from Fire", "+1k1 from school",
                             "+6k0 from the strike's excess", "+5 from 4th Dan (iaijutsu)", "+2 flat"]
    big = duel_damage_pool(f, (10, 10), 0)
    assert big["parts"][-1] == f"+{big['overflow_flat']} from rolling above 10k10"
