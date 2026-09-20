"""Server-side void spending: limits, the draw order, refusals, consequences.

The draw-order and dice-cap cases are NOT written here - they live in
``tests/shared/void_spend_cases.json`` and are run by this module and by
``tests/js/shared_cases.test.js`` alike, so the Python and JS copies of the
rule cannot drift apart unnoticed.
"""

import json
from pathlib import Path

import pytest

from app.models import Character
from app.services.roll_engine import apply_dice_cap
from app.services.void_spend import (
    VoidAllocation,
    VoidSpendPlan,
    VoidSpendRefused,
    allocate_void_spend,
    apply_void_spend,
    plan_void_spend,
    school_dan,
    spend_consequences,
    void_limits,
    void_pools,
)


SHARED = json.loads(
    (Path(__file__).parent / "shared" / "void_spend_cases.json").read_text()
)


def _char(**kwargs):
    kwargs.setdefault("name", "Spender")
    # A school WITHOUT Worldliness, so the only void is what is set here.
    kwargs.setdefault("school", "akodo_bushi")
    kwargs.setdefault("knacks", {"double_attack": 1, "feint": 1, "iaijutsu": 1})
    for ring in ("air", "fire", "earth", "water", "void"):
        kwargs.setdefault(f"ring_{ring}", 3)
    kwargs.setdefault("current_void_points", 3)
    kwargs.setdefault("current_temp_void_points", 0)
    kwargs.setdefault("current_light_wounds", 0)
    kwargs.setdefault("adventure_state", {})
    return Character(**kwargs)


# ---------------------------------------------------------------------------
# Shared tables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", SHARED["allocate"], ids=lambda c: c["name"])
def test_allocate_matches_the_shared_table(case):
    assert allocate_void_spend(*case["args"]) == case["want"]


@pytest.mark.parametrize("case", SHARED["dice_cap"], ids=lambda c: c["name"])
def test_dice_cap_matches_the_shared_table(case):
    got = apply_dice_cap(*case["args"])
    assert {
        "rolled": got["rolled"], "kept": got["kept"],
        "flat": got["flat"], "overflow": got["overflow_flat"],
    } == case["want"]


def test_allocate_treats_garbage_as_zero():
    assert allocate_void_spend("two", None, "x", 1)["allocated"] == 0


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def test_limits_are_the_lowest_ring():
    limits = void_limits(_char(ring_fire=2).to_dict())
    assert limits["void_max"] == 2
    assert limits["cap"] == 2


def test_shugenja_have_a_bigger_pool_and_a_tighter_cap():
    char = _char(
        school="shugenja", ring_water=4,
        knacks={"commune": 2, "pontificate": 2, "spellcasting": 3},
    )
    limits = void_limits(char.to_dict())
    assert limits["void_max"] == 4 + 2     # highest ring + school rank
    assert limits["cap"] == 3 - 1          # lowest ring - 1


def test_the_cap_never_goes_negative():
    char = _char(school="isawa_ishi", knacks={}, ring_air=0)
    assert void_limits(char.to_dict())["cap"] == 0


def test_worldliness_from_a_school_knack():
    char = _char(school="courtier", knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 3})
    assert void_limits(char.to_dict())["worldliness_max"] == 3


def test_worldliness_from_a_foreign_knack():
    char = _char(
        foreign_knacks={"worldliness": 2},
    )
    assert void_limits(char.to_dict())["worldliness_max"] == 2


def test_a_profession_character_has_no_school_to_read():
    data = _char(school="", knacks={}).to_dict()
    assert school_dan(data) == 0
    assert void_limits(data) == {"void_max": 3, "cap": 3, "worldliness_max": 0}


def test_limits_default_missing_rings():
    assert void_limits({})["cap"] == 2


def test_pools_count_worldliness_already_used():
    char = _char(
        school="courtier",
        knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 3},
        current_temp_void_points=1,
        adventure_state={"worldliness_used": 2},
    )
    pools = void_pools(char, void_limits(char.to_dict()))
    assert pools == {"temp": 1, "regular": 3, "worldliness": 1, "total": 5}


# ---------------------------------------------------------------------------
# Consequences
# ---------------------------------------------------------------------------


def test_most_schools_have_no_consequences():
    effects = spend_consequences(_char().to_dict())
    assert not any(effects.values())


@pytest.mark.parametrize("school,knacks,key,value", [
    ("ide_diplomat", {"double_attack": 5, "feint": 5, "worldliness": 5},
     "ide_temp_vp_on_spend", True),
    ("yogo_warden", {"double_attack": 3, "iaijutsu": 3, "feint": 3},
     "yogo_vp_heal_amount", 4),
    ("matsu_bushi", {"double_attack": 3, "iaijutsu": 3, "lunge": 3},
     "matsu_vp_wc_amount", 6),
])
def test_school_consequences(school, knacks, key, value):
    from app.game_data import SCHOOLS

    ranks = dict.fromkeys(SCHOOLS[school].school_knacks, max(knacks.values()))
    effects = spend_consequences(
        _char(school=school, knacks=ranks, attack=2).to_dict()
    )
    assert effects[key] == value


def test_consequences_wait_for_the_right_dan():
    from app.game_data import SCHOOLS

    ranks = dict.fromkeys(SCHOOLS["matsu_bushi"].school_knacks, 2)
    effects = spend_consequences(
        _char(school="matsu_bushi", knacks=ranks).to_dict()
    )
    assert effects["matsu_vp_wc_bonus"] is False
    assert effects["matsu_vp_wc_amount"] == 0


# ---------------------------------------------------------------------------
# Planning: refusals name the number
# ---------------------------------------------------------------------------


def test_plan_with_nothing_to_spend():
    plan = plan_void_spend(_char())
    assert plan.combined.total == 0


def test_plan_draws_temporary_first():
    plan = plan_void_spend(_char(current_temp_void_points=1), 2)
    assert plan.optional == VoidAllocation(1, 1, 0)
    assert plan.activation.total == 0


def test_plan_refuses_more_than_the_character_has():
    with pytest.raises(VoidSpendRefused) as exc:
        plan_void_spend(_char(current_void_points=1), 2)
    assert "has 1 void point," in str(exc.value)
    assert "not 2" in str(exc.value)


def test_plan_refuses_more_than_the_per_roll_cap():
    char = _char(current_void_points=3, current_temp_void_points=4)
    with pytest.raises(VoidSpendRefused) as exc:
        plan_void_spend(char, 4)
    assert "at most 3 void points" in str(exc.value)


def test_activation_is_paid_first_and_the_rest_checked_against_what_remains():
    """Cap 3, holding 2: exactly 1 may go into a Commune roll."""
    char = _char(current_void_points=2)
    plan = plan_void_spend(char, 1, activation_cost=1)
    assert plan.activation.total == 1
    assert plan.optional.total == 1
    with pytest.raises(VoidSpendRefused) as exc:
        plan_void_spend(char, 2, activation_cost=1, roll_label="Commune")
    assert "only 1 can go into the roll, not 2" in str(exc.value)


def test_activation_does_not_lower_the_cap():
    """The activation point is a cost, not part of the +1k1 spend: a
    character with plenty of void may still put their full cap on top."""
    char = _char(current_void_points=3, current_temp_void_points=1)
    plan = plan_void_spend(char, 3, activation_cost=1)
    assert plan.combined.total == 4


def test_activation_that_cannot_be_paid_is_refused():
    with pytest.raises(VoidSpendRefused) as exc:
        plan_void_spend(
            _char(current_void_points=0), 0, activation_cost=1,
            roll_label="Commune (Water)",
        )
    assert "Commune (Water) costs 1 void point" in str(exc.value)
    assert "has 0" in str(exc.value)


def test_planning_mutates_nothing():
    char = _char(current_void_points=2)
    plan_void_spend(char, 2)
    assert char.current_void_points == 2


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def test_apply_deducts_from_each_pool():
    char = _char(
        school="courtier",
        knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 2},
        current_void_points=1, current_temp_void_points=1,
    )
    apply_void_spend(char, plan_void_spend(char, 3))
    assert char.current_temp_void_points == 0
    assert char.current_void_points == 0
    assert char.adventure_state == {"worldliness_used": 1}


def test_apply_of_an_empty_plan_touches_nothing():
    char = _char(adventure_state={"lucky_used": True})
    apply_void_spend(char, VoidSpendPlan(VoidAllocation(), VoidAllocation()))
    assert char.current_void_points == 3
    assert char.adventure_state == {"lucky_used": True}


def _school_char(school, rank, **kwargs):
    from app.game_data import SCHOOLS

    return _char(
        school=school,
        knacks=dict.fromkeys(SCHOOLS[school].school_knacks, rank), **kwargs,
    )


def test_ide_5th_dan_gains_temp_void_for_non_temporary_points_only():
    char = _school_char(
        "ide_diplomat", 5, current_void_points=2, current_temp_void_points=1,
    )
    apply_void_spend(char, plan_void_spend(char, 3))
    # 1 temp + 2 regular spent; the 2 regular come back as temporary.
    assert char.current_void_points == 0
    assert char.current_temp_void_points == 2


def test_yogo_warden_3rd_dan_heals_light_wounds_never_below_zero():
    char = _school_char(
        "yogo_warden", 3, attack=3, current_light_wounds=10,
    )
    apply_void_spend(char, plan_void_spend(char, 1))
    assert char.current_light_wounds == 4
    apply_void_spend(char, plan_void_spend(char, 1))
    assert char.current_light_wounds == 0


def test_matsu_3rd_dan_banks_one_bonus_per_point():
    char = _school_char(
        "matsu_bushi", 3, attack=2,
        adventure_state={"matsu_banked_wc_bonuses": [6], "lucky_used": True},
    )
    apply_void_spend(char, plan_void_spend(char, 2))
    assert char.adventure_state == {
        "matsu_banked_wc_bonuses": [6, 6, 6], "lucky_used": True,
    }


def test_matsu_bank_starts_from_nothing_or_the_legacy_number():
    char = _school_char(
        "matsu_bushi", 3, attack=1, adventure_state={"matsu_banked_wc_bonuses": 9},
    )
    apply_void_spend(char, plan_void_spend(char, 1))
    assert char.adventure_state["matsu_banked_wc_bonuses"] == [3]


def test_the_sheet_renders_the_same_limits_the_server_enforces(client):
    """R1.1: the page and the server cannot disagree about a cap."""
    import re

    session = client._test_session_factory()
    char = _char(
        owner_discord_id="183026066498125825", is_published=True, ring_air=2,
    )
    session.add(char)
    session.commit()
    html = client.get(f"/characters/{char.id}").text
    limits = void_limits(char.to_dict())
    blob = re.search(r'id="void-spend-config"[^>]*>([^<]+)<', html)
    assert blob, "the sheet no longer embeds void-spend-config"
    config = json.loads(blob.group(1))
    assert config["cap"] == limits["cap"] == 2
    assert config["worldliness_max"] == limits["worldliness_max"]
