"""app/services/combat_math.py: the server twin of the sheet's attack math."""

import json
import pathlib
import re

import pytest

from app.services import combat_math as cm

_CASES = json.loads(
    (pathlib.Path(__file__).parent / "shared" / "combat_math_cases.json").read_text()
)


def _snake(value):
    if isinstance(value, dict):
        return {re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), k): v for k, v in value.items()}
    return value


@pytest.mark.parametrize(
    "section,case",
    [(s, c) for s, cases in _CASES.items() if not s.startswith("_") for c in cases],
    ids=lambda v: v if isinstance(v, str) else v["name"],
)
def test_shared_cases(section, case):
    assert getattr(cm, section)(*case["args"]) == _snake(case["want"])


def _formula(**kw):
    base = {"attack_variant": "attack", "damage_ring_val": 3, "damage_ring_name": "Fire",
            "damage_extra_rolled": 0, "damage_extra_kept": 0, "damage_flat_bonus": 0}
    base.update(kw)
    return base


def test_plain_katana_hit():
    pool = cm.damage_pool(_formula(), extra_dice=2)
    assert (pool["rolled"], pool["kept"], pool["flat"]) == (9, 2, 0)
    assert pool["parts"] == ["4k2 katana", "+3k0 from Fire", "+2k0 extra from attack roll"]
    assert pool["add_lowest_three"] is False


def test_weapons_and_school_extras_and_flat():
    pool = cm.damage_pool(_formula(damage_extra_rolled=1, damage_extra_kept=1, damage_flat_bonus=5),
                          weapon="knife")
    assert (pool["rolled"], pool["kept"], pool["flat"]) == (6, 3, 5)
    assert "+1k1 from school" in pool["parts"] and "+5 flat" in pool["parts"]
    assert cm.damage_pool(_formula(), weapon="nonsense")["rolled"] == 7  # falls back to katana


def test_lunge_and_double_attack_failed_parry():
    assert cm.damage_pool(_formula(attack_variant="lunge"))["rolled"] == 8
    da = cm.damage_pool(_formula(attack_variant="double_attack"), extra_dice=3,
                        failed_parry=True, parry_skill=2)
    # 3 excess + 2 double attack - 2 parry = 3 extra
    assert da["rolled"] == 4 + 3 + 3
    assert "+2k0 from Double Attack (failed parry)" in da["parts"]


@pytest.mark.parametrize("flags,expected_rolled,part", [
    ({}, 7 + 0, "-3k0 from failed parry"),
    ({"mirumoto_parry_modifier": True}, 7 + 2, "-1k0 from failed parry (halved by 4th Dan)"),
    ({"brotherhood_parry_no_reduce": True}, 7 + 3, "parry does not reduce dice (4th Dan)"),
])
def test_failed_parry_modes(flags, expected_rolled, part):
    pool = cm.damage_pool(_formula(), extra_dice=3, failed_parry=True, parry_skill=3, flags=flags)
    assert pool["rolled"] == expected_rolled and part in pool["parts"]


def test_otaku_lunge_keeps_its_die_through_a_parry():
    pool = cm.damage_pool(_formula(attack_variant="lunge"), failed_parry=True, parry_skill=5,
                          flags={"otaku_lunge_extra_die": True})
    assert pool["rolled"] == 7 + 1


def test_wave_man_weapon_and_recovered_dice():
    f = _formula(wave_man_weapon_dice=1, wave_man_failed_parry_dice=1)
    pool = cm.damage_pool(f, weapon="knife", extra_dice=4, failed_parry=True, parry_skill=3)
    # knife 2 -> 3, +3 Fire, extra 4 - 3 + 2 recovered = 3
    assert pool["rolled"] == 3 + 3 + 3
    assert "+2k0 recovered from Wave Man" in pool["parts"]
    assert "+1k0 weapon dice from Wave Man" in pool["parts"]


def test_bayushi_void_adds_kept_dice():
    pool = cm.damage_pool(_formula(void_spent=2), flags={"bayushi_vp_damage": True})
    assert (pool["rolled"], pool["kept"]) == (9, 4)


def test_ikoma_floor_only_when_unparried():
    assert cm.damage_pool(_formula(), flags={"ikoma_10_dice_floor": True})["rolled"] == 10
    parried = cm.damage_pool(_formula(), failed_parry=True, flags={"ikoma_10_dice_floor": True})
    assert parried["rolled"] == 7


def test_ten_k_ten_cap_and_shosuro():
    pool = cm.damage_pool(_formula(damage_extra_kept=9, shosuro_5th_dan=True), extra_dice=6)
    assert (pool["rolled"], pool["kept"]) == (10, 10)
    assert pool["flat"] == 2 * (2 + 9 + 3 - 10)
    assert any("10k10" in p for p in pool["parts"])
    assert pool["add_lowest_three"] is True


@pytest.mark.parametrize("school,knacks,flag", [
    ("otaku_bushi", {"double_attack": 4, "iaijutsu": 4, "lunge": 4}, "otaku_lunge_extra_die"),
    ("brotherhood_of_shinsei_monk", {"conviction": 4, "otherworldliness": 4, "worldliness": 4}, "brotherhood_parry_no_reduce"),
    ("mirumoto_bushi", {"counterattack": 4, "double_attack": 4, "iaijutsu": 4}, "mirumoto_parry_modifier"),
    ("bayushi_bushi", {"double_attack": 1, "feint": 1, "iaijutsu": 1}, "bayushi_vp_damage"),
    ("ikoma_bard", {"discern_honor": 4, "oppose_knowledge": 4, "oppose_social": 4}, "ikoma_10_dice_floor"),
])
def test_damage_flags(school, knacks, flag):
    flags = cm.damage_flags({"school": school, "knacks": knacks})
    assert [k for k, v in flags.items() if v] == [flag]
    low = {k: 3 for k in knacks}
    if flag != "bayushi_vp_damage":
        assert not any(cm.damage_flags({"school": school, "knacks": low}).values())
