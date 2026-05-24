"""Unit tests for the Night's Rest feature.

Covers the pure-Python SW healing cadence math, the /track endpoint's
SW-transition tracking hook, the preview and apply endpoints, and the
state-update side effects of taking a Night's Rest.
"""

import pytest

from app.services.nights_rest import (
    compute_sw_heal_amount,
    compute_nights_rest_plan,
    apply_nights_rest,
)
from app.models import Character


# ---------------------------------------------------------------------------
# Pure-Python cadence math
# ---------------------------------------------------------------------------


def _heal(
    *,
    old_sw,
    quick=False,
    slow=False,
    received_new=False,
    became_injured=False,
    last_was_healing=False,
    accelerate=False,
):
    """Thin keyword-only wrapper so each test reads as a scenario sentence."""
    return compute_sw_heal_amount(
        old_sw=old_sw,
        has_quick_healer=quick,
        has_slow_healer=slow,
        received_new_since_rest=received_new,
        became_injured_since_rest=became_injured,
        last_rest_was_healing_night=last_was_healing,
        accelerate=accelerate,
    )


def test_no_sw_no_heal():
    assert _heal(old_sw=0) == 0


def test_no_sw_no_heal_even_with_quick_healer():
    """Quick Healer can't conjure SW out of nothing."""
    assert _heal(old_sw=0, quick=True, received_new=True, became_injured=True) == 0


def test_first_rest_after_injury_heals_1():
    assert _heal(old_sw=3, received_new=True, became_injured=True) == 1


def test_second_rest_no_new_wounds_heals_0():
    assert _heal(old_sw=2, last_was_healing=True) == 0


def test_third_rest_no_new_wounds_heals_1():
    assert _heal(old_sw=2, last_was_healing=False) == 1


def test_quick_healer_first_rest_heals_2():
    assert _heal(
        old_sw=3, quick=True, received_new=True, became_injured=True
    ) == 2


def test_quick_healer_does_not_trigger_when_no_new_injuries():
    """On nights with received_new=False, QH offers no bonus."""
    assert _heal(old_sw=3, quick=True, last_was_healing=False) == 1
    assert _heal(old_sw=3, quick=True, last_was_healing=True) == 0


def test_quick_healer_retriggers_on_new_injuries_mid_cadence():
    """QH at SW=3 (last was a heal night, so today would normally be off),
    then takes 2 more SW (sets received_new but NOT became_injured because
    they weren't at 0), next rest heals 2 (QH bonus does fire)."""
    assert _heal(
        old_sw=5,
        quick=True,
        received_new=True,
        became_injured=False,
        last_was_healing=True,
    ) == 2


def test_slow_healer_first_night_heals_0():
    """SH suppresses the first night's heal after becoming injured."""
    assert _heal(
        old_sw=3, slow=True, received_new=True, became_injured=True
    ) == 0


def test_slow_healer_does_not_resuppress_mid_cadence():
    """SH already injured (became_injured=F for this rest because the
    0->positive transition was previously consumed) takes more SW mid-
    cadence -- next rest heals normally (1)."""
    assert _heal(
        old_sw=5,
        slow=True,
        received_new=True,
        became_injured=False,
        last_was_healing=False,
    ) == 1


def test_slow_healer_second_night_heals_1():
    """After the suppressed first night the post-state is recv=F, inj=F,
    last=F, so the next rest heals 1."""
    assert _heal(old_sw=3, slow=True, last_was_healing=False) == 1


def test_accelerate_flips_heal_to_off():
    """SW=2 with no new injuries and last=off (heal=1 normally) ->
    accelerate flips it to 0."""
    assert _heal(old_sw=2, last_was_healing=False, accelerate=True) == 0


def test_accelerate_flips_off_to_heal():
    """SW=2 with no new injuries and last=heal (heal=0 normally) ->
    accelerate flips it to 1."""
    assert _heal(old_sw=2, last_was_healing=True, accelerate=True) == 1


def test_accelerate_with_quick_healer_flips_2_to_0():
    """QH first night would heal 2; accelerate flips the underlying base
    to 0, taking the QH bonus with it. (Per user decision.)"""
    assert _heal(
        old_sw=3,
        quick=True,
        received_new=True,
        became_injured=True,
        accelerate=True,
    ) == 0


def test_quick_and_slow_healer_mutually_exclusive():
    """Defensive: the helper rejects characters with both - they're in
    EXCLUSIVE_PAIRS and should never coexist."""
    with pytest.raises(AssertionError):
        _heal(
            old_sw=3,
            quick=True,
            slow=True,
            received_new=True,
            became_injured=True,
        )


def test_heal_capped_at_old_sw():
    """A QH with only 1 SW heals 1, not 2."""
    assert _heal(
        old_sw=1, quick=True, received_new=True, became_injured=True
    ) == 1


# ---------------------------------------------------------------------------
# apply_nights_rest: state-update side effects
# ---------------------------------------------------------------------------


def _make_char(db, **overrides):
    """Build a minimal Character with default ring 2 everywhere."""
    defaults = dict(
        name="Test", school="akodo_bushi", school_ring_choice="Water",
        ring_air=2, ring_fire=2, ring_earth=2, ring_water=3, ring_void=2,
        attack=1, parry=1,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        advantages=[], disadvantages=[],
        current_light_wounds=0, current_serious_wounds=0,
        current_void_points=2,
        adventure_state={},
        action_dice=[], precepts_pool=[],
    )
    defaults.update(overrides)
    char = Character(**defaults)
    db.add(char)
    db.commit()
    return char


def test_apply_heal_to_zero_clears_all_flags(db):
    char = _make_char(
        db,
        current_serious_wounds=1,
        sw_healing_received_new_since_rest=True,
        sw_healing_became_injured_since_rest=True,
        sw_healing_last_rest_was_healing_night=False,
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_serious_wounds == 0
    assert char.sw_healing_received_new_since_rest is False
    assert char.sw_healing_became_injured_since_rest is False
    assert char.sw_healing_last_rest_was_healing_night is False


def test_apply_partial_heal_sets_last_was_healing_true(db):
    char = _make_char(
        db,
        current_serious_wounds=3,
        sw_healing_received_new_since_rest=True,
        sw_healing_became_injured_since_rest=True,
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_serious_wounds == 2
    assert char.sw_healing_last_rest_was_healing_night is True
    assert char.sw_healing_received_new_since_rest is False
    assert char.sw_healing_became_injured_since_rest is False


def test_apply_off_night_sets_last_was_healing_false(db):
    char = _make_char(
        db,
        current_serious_wounds=2,
        sw_healing_last_rest_was_healing_night=True,
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_serious_wounds == 2
    assert char.sw_healing_last_rest_was_healing_night is False


def test_apply_lw_reset_to_zero(db):
    char = _make_char(db, current_light_wounds=7)
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_light_wounds == 0


def test_apply_vp_regen_normal_school_adds_1(db):
    char = _make_char(db, current_void_points=0)
    # void_max for default rings (2,2,2,3,2) = 2
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_void_points == 1


def test_apply_vp_regen_capped_at_max(db):
    char = _make_char(db, current_void_points=2)  # already at max
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_void_points == 2


def test_apply_vp_regen_isawa_ishi_uses_lowest_ring(db):
    char = _make_char(
        db,
        school="isawa_ishi",
        school_ring_choice="Void",
        ring_air=3, ring_fire=4, ring_earth=2, ring_water=5, ring_void=3,
        knacks={"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1},
        current_void_points=0,
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    # lowest ring is Earth=2 -> regen 2
    assert char.current_void_points == 2


def test_apply_vp_regen_isawa_ishi_capped_at_max(db):
    char = _make_char(
        db,
        school="isawa_ishi",
        school_ring_choice="Void",
        ring_air=3, ring_fire=4, ring_earth=2, ring_water=5, ring_void=3,
        knacks={"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1},
        current_void_points=4,  # very near max
    )
    # max = highest_ring(5) + school_rank(min knack rank, 1) = 6; regen 2 caps at 6
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_void_points == 6


def test_apply_conviction_pool_refreshed(db):
    char = _make_char(
        db,
        adventure_state={"conviction_used": 2},
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1, "conviction": 2},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get("conviction_used", 0) == 0


def test_apply_absorb_void_refreshed_only_for_isawa_ishi(db):
    """Ishi has Absorb Void as per-day; Night's Rest must refresh it."""
    char = _make_char(
        db,
        school="isawa_ishi",
        school_ring_choice="Void",
        knacks={"absorb_void": 2, "kharmic_spin": 1, "otherworldliness": 1},
        adventure_state={"absorb_void_used": 2},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get("absorb_void_used", 0) == 0


def test_apply_absorb_void_NOT_refreshed_for_non_ishi(db):
    """Kitsune Warden: Absorb Void is per-adventure, not per-day. The
    counter must survive a Night's Rest."""
    char = _make_char(
        db,
        school="kitsune_warden",
        school_ring_choice="Water",
        knacks={"absorb_void": 2, "wilderness": 1, "kitsune_arts": 1},
        adventure_state={"absorb_void_used": 2},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get("absorb_void_used") == 2


def test_apply_togashi_daily_athletics_raises_refreshed(db):
    char = _make_char(
        db,
        school="togashi_ise_zumi",
        school_ring_choice="Earth",
        knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3},
        skills={"precepts": 2},
        adventure_state={"togashi_daily_athletics_raises_used": 5},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get(
        "togashi_daily_athletics_raises_used", 0
    ) == 0


def test_apply_lucky_toggle_NOT_cleared(db):
    """Lucky is per-adventure; Night's Rest does NOT clear it."""
    char = _make_char(
        db,
        advantages=["lucky"],
        adventure_state={"lucky_used": True},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get("lucky_used") is True


def test_apply_adventure_raises_not_cleared(db):
    """3rd Dan free raises are per-adventure (NOT per-day) for non-Togashi."""
    char = _make_char(
        db,
        adventure_state={"adventure_raises_used": 3},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get("adventure_raises_used") == 3


def test_apply_worldliness_not_cleared(db):
    char = _make_char(
        db,
        adventure_state={"worldliness_used": 2},
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1, "worldliness": 3},
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.adventure_state.get("worldliness_used") == 2


def test_apply_action_dice_cleared(db):
    char = _make_char(
        db,
        action_dice=[{"value": 4, "spent": False}, {"value": 7, "spent": True}],
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.action_dice == []


def test_apply_precepts_pool_cleared(db):
    char = _make_char(
        db,
        school="priest",
        school_ring_choice="Air",
        knacks={"precepts": 3, "calligraphy": 1, "sutras": 1},
        precepts_pool=[{"value": 7}, {"value": 3}],
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.precepts_pool == []


def test_apply_mantis_posture_state_cleared(db):
    char = _make_char(
        db,
        adventure_state={
            "mantis_posture_phase": 3,
            "mantis_posture_history": ["offensive", "defensive"],
            "mantis_offensive_3rd_dan_accum": 5,
            "mantis_defensive_3rd_dan_accum": 2,
            "kakita_5th_dan_used": True,
        },
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert "mantis_posture_phase" not in char.adventure_state
    assert "mantis_posture_history" not in char.adventure_state
    assert "mantis_offensive_3rd_dan_accum" not in char.adventure_state
    assert "mantis_defensive_3rd_dan_accum" not in char.adventure_state
    assert "kakita_5th_dan_used" not in char.adventure_state


def test_apply_banked_combat_bonuses_cleared(db):
    char = _make_char(
        db,
        adventure_state={
            "akodo_banked_bonuses": [5, 10],
            "hiruma_banked_attack_bonus": 5,
            "bayushi_banked_feint_raise": 1,
            "matsu_banked_wc_bonuses": [10],
            "matsu_banked_wc_bonus": 5,
            "banked_wc_excess": [3],
            "ide_banked_tn_reduce": 2,
            "hida_banked_wc_bonus": 5,
        },
    )
    apply_nights_rest(char, accelerate=False)
    db.commit()
    for k in (
        "akodo_banked_bonuses", "hiruma_banked_attack_bonus",
        "bayushi_banked_feint_raise", "matsu_banked_wc_bonuses",
        "matsu_banked_wc_bonus", "banked_wc_excess",
        "ide_banked_tn_reduce", "hida_banked_wc_bonus",
    ):
        assert k not in char.adventure_state, f"{k} should have been cleared"


def test_apply_temp_void_points_cleared(db):
    """current_temp_void_points are per-combat-round; clear on Night's Rest."""
    char = _make_char(db, current_temp_void_points=2)
    apply_nights_rest(char, accelerate=False)
    db.commit()
    assert char.current_temp_void_points == 0


# ---------------------------------------------------------------------------
# compute_nights_rest_plan: preview shape
# ---------------------------------------------------------------------------


def test_plan_would_change_false_when_nothing_to_do(db):
    char = _make_char(db)  # full VP, no LW, no SW, no pools spent
    plan = compute_nights_rest_plan(char, accelerate=False)
    assert plan["would_change"] is False
    assert plan["effects"] == []
    assert plan["sw_remaining_after"] == 0


def test_plan_lists_lw_heal_when_lw_positive(db):
    char = _make_char(db, current_light_wounds=4)
    plan = compute_nights_rest_plan(char, accelerate=False)
    assert plan["would_change"] is True
    keys = [e["key"] for e in plan["effects"]]
    assert "heal_lw" in keys
    lw_effect = next(e for e in plan["effects"] if e["key"] == "heal_lw")
    assert lw_effect["amount"] == 4
    assert "4" in lw_effect["label"]


def test_plan_pluralizes_lw_heal(db):
    char = _make_char(db, current_light_wounds=1)
    plan = compute_nights_rest_plan(char, accelerate=False)
    lw_effect = next(e for e in plan["effects"] if e["key"] == "heal_lw")
    assert "1 light wound" in lw_effect["label"]


def test_plan_lists_vp_regen_when_below_max(db):
    char = _make_char(db, current_void_points=0)
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "restore_vp" in keys
    vp_effect = next(e for e in plan["effects"] if e["key"] == "restore_vp")
    assert vp_effect["amount"] == 1


def test_plan_isawa_ishi_lists_lowest_ring_vp_amount(db):
    char = _make_char(
        db,
        school="isawa_ishi",
        school_ring_choice="Void",
        ring_air=3, ring_fire=4, ring_earth=2, ring_water=5, ring_void=3,
        knacks={"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1},
        current_void_points=0,
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    vp_effect = next(e for e in plan["effects"] if e["key"] == "restore_vp")
    assert vp_effect["amount"] == 2  # lowest ring (Earth)


def test_plan_includes_sw_remaining_after(db):
    char = _make_char(
        db,
        current_serious_wounds=3,
        sw_healing_received_new_since_rest=True,
        sw_healing_became_injured_since_rest=True,
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    assert plan["sw_remaining_after"] == 2  # heal 1 from 3


def test_plan_includes_alt_effects_only_when_sw_remains(db):
    """When the default heal would still leave SW>0, the plan must include
    alt_effects so the modal's accelerate checkbox can re-render."""
    char = _make_char(
        db,
        current_serious_wounds=3,
        sw_healing_received_new_since_rest=True,
        sw_healing_became_injured_since_rest=True,
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    assert plan["alt_effects"]
    # The alt SW heal should differ from the default (1 -> 0)
    alt_sw = next(e for e in plan["alt_effects"] if e["key"] == "heal_sw")
    assert alt_sw["amount"] == 0


def test_plan_no_alt_effects_when_sw_heals_to_zero(db):
    """SW=1 heals to 0; no remaining SW so no accelerate option."""
    char = _make_char(
        db,
        current_serious_wounds=1,
        sw_healing_received_new_since_rest=True,
        sw_healing_became_injured_since_rest=True,
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    assert plan["sw_remaining_after"] == 0
    assert plan["alt_effects"] == []


def test_plan_always_shows_sw_line_when_sw_positive_even_if_heal_zero(db):
    """User decision #1: when SW>0 we always display the SW status line
    so the accelerate toggle has something to flip."""
    char = _make_char(
        db,
        current_serious_wounds=2,
        sw_healing_last_rest_was_healing_night=True,  # off night today
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    sw_effects = [e for e in plan["effects"] if e["key"] == "heal_sw"]
    assert len(sw_effects) == 1
    assert sw_effects[0]["amount"] == 0
    # And would_change should be True because the SW line is shown
    assert plan["would_change"] is True


def test_plan_omits_sw_line_when_no_sw(db):
    char = _make_char(db, current_light_wounds=2)  # only LW
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "heal_sw" not in keys


def test_plan_lists_combat_in_progress_clears(db):
    char = _make_char(
        db,
        action_dice=[{"value": 5, "spent": False}, {"value": 7, "spent": False}],
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "clear_action_dice" in keys


def test_plan_singular_action_die_label(db):
    char = _make_char(db, action_dice=[{"value": 5, "spent": False}])
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(e for e in plan["effects"] if e["key"] == "clear_action_dice")
    assert "1 initiative die" in bullet["label"]


def test_plan_lists_precepts_pool_clear(db):
    char = _make_char(
        db,
        school="priest", school_ring_choice="Air",
        knacks={"precepts": 3, "calligraphy": 1, "sutras": 1},
        precepts_pool=[{"value": 7}, {"value": 3}],
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(e for e in plan["effects"] if e["key"] == "clear_precepts_pool")
    assert "2 dice" in bullet["label"]


def test_plan_singular_precepts_pool_label(db):
    char = _make_char(
        db,
        school="priest", school_ring_choice="Air",
        knacks={"precepts": 3, "calligraphy": 1, "sutras": 1},
        precepts_pool=[{"value": 5}],
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(e for e in plan["effects"] if e["key"] == "clear_precepts_pool")
    assert "1 die" in bullet["label"]


def test_plan_lists_mantis_posture_clear(db):
    char = _make_char(
        db,
        adventure_state={
            "mantis_posture_history": ["offensive"],
            "mantis_posture_phase": 2,
        },
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "clear_mantis_posture" in keys


def test_plan_lists_banked_bonuses_single(db):
    """A single banked bonus reads 'Clear 1 banked combat bonus' (singular)."""
    char = _make_char(
        db,
        adventure_state={"hiruma_banked_attack_bonus": 5},
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(
        e for e in plan["effects"] if e["key"] == "clear_banked_bonuses"
    )
    assert "1 banked combat bonus" in bullet["label"]
    assert "bonuses" not in bullet["label"]


def test_plan_lists_banked_bonuses_multiple_pluralized(db):
    """Akodo banked-bonuses list contributes len(list) to the count."""
    char = _make_char(
        db,
        adventure_state={
            "akodo_banked_bonuses": [5, 10, 5],
            "hiruma_banked_attack_bonus": 5,
        },
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(
        e for e in plan["effects"] if e["key"] == "clear_banked_bonuses"
    )
    assert "4 banked combat bonuses" in bullet["label"]


def test_plan_lists_temp_void_clear(db):
    char = _make_char(db, current_temp_void_points=3)
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(e for e in plan["effects"] if e["key"] == "clear_temp_void")
    assert "3 temporary void points" in bullet["label"]


def test_plan_singular_temp_void_label(db):
    char = _make_char(db, current_temp_void_points=1)
    plan = compute_nights_rest_plan(char, accelerate=False)
    bullet = next(e for e in plan["effects"] if e["key"] == "clear_temp_void")
    assert "1 temporary void point" in bullet["label"]
    assert "points" not in bullet["label"]


def test_plan_lists_kakita_5th_dan_flag_clear(db):
    char = _make_char(
        db,
        school="kakita_bushi", school_ring_choice="Air",
        knacks={"iaijutsu": 5, "double_attack": 5, "feint": 5},
        adventure_state={"kakita_5th_dan_used": True},
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "clear_kakita_5th_dan_used" in keys


def test_plan_lists_conviction_refresh(db):
    char = _make_char(
        db,
        adventure_state={"conviction_used": 2},
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1, "conviction": 3},
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "refresh_conviction" in keys


def test_plan_does_NOT_list_lucky_refresh(db):
    """Lucky is per-adventure; Night's Rest must not offer to refresh it."""
    char = _make_char(
        db,
        advantages=["lucky"],
        adventure_state={"lucky_used": True},
    )
    plan = compute_nights_rest_plan(char, accelerate=False)
    keys = [e["key"] for e in plan["effects"]]
    assert "refresh_lucky" not in keys
    assert all("ucky" not in e["label"] for e in plan["effects"])


# ---------------------------------------------------------------------------
# /track endpoint SW-transition hook
# ---------------------------------------------------------------------------


def _create_via_post(client, **overrides):
    """Create a character through the POST endpoint and return its row."""
    from tests.conftest import make_character_data, query_db
    data = make_character_data(**overrides)
    resp = client.post("/characters", json=data)
    assert resp.status_code in (200, 201, 303), resp.text
    return query_db(client).first()


def _track(client, char_id, **fields):
    return client.post(f"/characters/{char_id}/track", json=fields)


def test_track_sets_received_new_when_sw_increases(client):
    char = _create_via_post(client)
    resp = _track(client, char.id, current_serious_wounds=1)
    assert resp.status_code == 200
    from tests.conftest import query_db
    c = query_db(client).filter_by(id=char.id).first()
    assert c.sw_healing_received_new_since_rest is True
    assert c.sw_healing_became_injured_since_rest is True


def test_track_sets_became_injured_on_zero_to_positive_only(client):
    char = _create_via_post(client)
    _track(client, char.id, current_serious_wounds=2)
    # Simulate a Night's Rest having cleared the post-rest flags, then take
    # more SW. Have to commit through the same connection the route uses.
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.sw_healing_received_new_since_rest = False
    c.sw_healing_became_injured_since_rest = False
    c.sw_healing_last_rest_was_healing_night = True
    sess.commit()
    sess.close()
    # Increase SW from 2 to 4
    _track(client, char.id, current_serious_wounds=4)
    from tests.conftest import query_db
    c2 = query_db(client).filter_by(id=char.id).first()
    assert c2.sw_healing_received_new_since_rest is True
    # Must NOT re-set became_injured because we weren't at 0
    assert c2.sw_healing_became_injured_since_rest is False


def test_track_clears_all_healing_flags_on_sw_to_zero(client):
    char = _create_via_post(client)
    _track(client, char.id, current_serious_wounds=2)
    _track(client, char.id, current_serious_wounds=0)
    from tests.conftest import query_db
    c = query_db(client).filter_by(id=char.id).first()
    assert c.sw_healing_received_new_since_rest is False
    assert c.sw_healing_became_injured_since_rest is False
    assert c.sw_healing_last_rest_was_healing_night is False


def test_track_no_flag_changes_on_sw_unchanged(client):
    char = _create_via_post(client)
    _track(client, char.id, current_serious_wounds=2)
    # Same value again - shouldn't toggle anything
    _track(client, char.id, current_serious_wounds=2)
    from tests.conftest import query_db
    c = query_db(client).filter_by(id=char.id).first()
    assert c.sw_healing_received_new_since_rest is True
    assert c.sw_healing_became_injured_since_rest is True


def test_track_no_flag_changes_on_sw_decrease_short_of_zero(client):
    """Manual SW decrement (e.g. player corrected a miscount) does not
    advance the cadence. Flags are unchanged."""
    char = _create_via_post(client)
    _track(client, char.id, current_serious_wounds=3)
    _track(client, char.id, current_serious_wounds=2)
    from tests.conftest import query_db
    c = query_db(client).filter_by(id=char.id).first()
    assert c.sw_healing_received_new_since_rest is True
    assert c.sw_healing_became_injured_since_rest is True


# ---------------------------------------------------------------------------
# Endpoint integration: preview + apply
# ---------------------------------------------------------------------------


def test_preview_401_when_not_logged_in(client):
    char = _create_via_post(client)
    resp = client.get(
        f"/characters/{char.id}/nights-rest/preview",
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_preview_404_when_character_missing(client):
    resp = client.get("/characters/9999/nights-rest/preview")
    assert resp.status_code == 404


def test_preview_403_for_non_editor(client):
    char = _create_via_post(client)
    resp = client.get(
        f"/characters/{char.id}/nights-rest/preview",
        headers={"X-Test-User": "test_user_2:other"},
    )
    assert resp.status_code == 403


def test_preview_returns_would_change_false_when_nothing_to_do(client):
    char = _create_via_post(client)
    resp = client.get(f"/characters/{char.id}/nights-rest/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["would_change"] is False


def test_preview_returns_effects_for_lw(client):
    char = _create_via_post(client)
    _track(client, char.id, current_light_wounds=3)
    resp = client.get(f"/characters/{char.id}/nights-rest/preview")
    body = resp.json()
    assert body["would_change"] is True
    keys = [e["key"] for e in body["effects"]]
    assert "heal_lw" in keys


def test_post_401_when_not_logged_in(client):
    char = _create_via_post(client)
    resp = client.post(
        f"/characters/{char.id}/nights-rest",
        json={"accelerate_cadence": False},
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_post_404_when_character_missing(client):
    resp = client.post(
        "/characters/9999/nights-rest",
        json={"accelerate_cadence": False},
    )
    assert resp.status_code == 404


def test_post_403_for_non_editor(client):
    char = _create_via_post(client)
    resp = client.post(
        f"/characters/{char.id}/nights-rest",
        json={"accelerate_cadence": False},
        headers={"X-Test-User": "test_user_2:other"},
    )
    assert resp.status_code == 403


def test_post_applies_all_effects_atomically(client):
    char = _create_via_post(client)
    _track(client, char.id, current_light_wounds=5, current_void_points=0)
    resp = client.post(
        f"/characters/{char.id}/nights-rest",
        json={"accelerate_cadence": False},
    )
    assert resp.status_code == 200
    from tests.conftest import query_db
    c = query_db(client).filter_by(id=char.id).first()
    assert c.current_light_wounds == 0
    # Non-Ishi regens 1 VP per night, so 0 -> 1 (not all the way to max=2).
    assert c.current_void_points == 1


def test_post_with_accelerate_inverts_cadence(client):
    char = _create_via_post(client)
    # Set up SW=2 with last_was_healing=True (so today is off-night, heal=0)
    _track(client, char.id, current_serious_wounds=2)
    from tests.conftest import query_db
    # Manually flip flags via the DB
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.sw_healing_received_new_since_rest = False
    c.sw_healing_became_injured_since_rest = False
    c.sw_healing_last_rest_was_healing_night = True
    sess.commit()
    sess.close()
    # Without accelerate: heal=0
    # With accelerate: heal=1
    resp = client.post(
        f"/characters/{char.id}/nights-rest",
        json={"accelerate_cadence": True},
    )
    assert resp.status_code == 200
    c2 = query_db(client).filter_by(id=char.id).first()
    assert c2.current_serious_wounds == 1
