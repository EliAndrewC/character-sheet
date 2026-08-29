"""Profession data, allowance and validation tests.

See profession-design/design.md. Abilities are numbered W1-W10 in the
order they appear in rules/09-professions.md; that numbering is used in
test names throughout.
"""
import pytest

from app.game_data import (
    PROFESSION_ABILITY_BONUSES,
    PROFESSION_ABILITY_UNLOCK_BASE,
    PROFESSION_ABILITY_UNLOCK_STEP,
    PROFESSIONS,
)


# ---------------------------------------------------------------------------
# Phase 1 - static data
# ---------------------------------------------------------------------------

def test_all_five_professions_load():
    assert set(PROFESSIONS) == {"wave_man", "worker", "merchant", "priest", "ninja"}


@pytest.mark.parametrize("pid", ["wave_man", "worker", "merchant", "priest", "ninja"])
def test_every_profession_has_ten_abilities(pid):
    assert len(PROFESSIONS[pid].abilities) == 10


@pytest.mark.parametrize("pid", ["wave_man", "worker", "merchant", "priest", "ninja"])
def test_ordinals_are_one_through_ten_in_order(pid):
    assert [a.ordinal for a in PROFESSIONS[pid].abilities] == list(range(1, 11))


def test_ability_ids_are_unique_across_all_professions():
    seen = [a.id for p in PROFESSIONS.values() for a in p.abilities]
    assert len(seen) == len(set(seen))


def test_priest_rituals_may_be_taken_once_everything_else_twice():
    # D4: each ability up to twice, except Priest rituals which are once-only.
    assert PROFESSIONS["priest"].max_per_ability == 1
    for pid in ("wave_man", "worker", "merchant", "ninja"):
        assert PROFESSIONS[pid].max_per_ability == 2


def test_only_wave_man_is_selectable():
    # D17: the other four are data-only until each is implemented.
    assert PROFESSIONS["wave_man"].selectable is True
    for pid in ("worker", "merchant", "priest", "ninja"):
        assert PROFESSIONS[pid].selectable is False


def test_every_profession_has_a_rules_anchor():
    for p in PROFESSIONS.values():
        assert p.rules_anchor.startswith("#")


def test_bonuses_reference_real_ability_ids():
    known = {a.id for p in PROFESSIONS.values() for a in p.abilities}
    assert set(PROFESSION_ABILITY_BONUSES) <= known


def test_unlock_constants():
    # D2: first pick at 150 XP, one more every 15 XP.
    assert PROFESSION_ABILITY_UNLOCK_BASE == 150
    assert PROFESSION_ABILITY_UNLOCK_STEP == 15


def test_wave_man_ability_text_matches_the_rules():
    abilities = PROFESSIONS["wave_man"].abilities
    # W3's wording was revised upstream on 2026-08-29 to key on dice
    # rolled rather than on "4k2"; make sure we carry the new text.
    assert "rolls fewer than 4 damage dice" in abilities[2].text
    assert "4k2" not in abilities[2].text
    assert abilities[0].text.startswith("When you make an attack roll that would miss")
    assert abilities[9].text.startswith("Raise the TN of someone making a wound check")


def test_wave_man_reference_only_abilities():
    # D14/D16: W2, W8 and W10 are reference text; the rest carry math.
    by_ordinal = {a.ordinal: a for a in PROFESSIONS["wave_man"].abilities}
    assert [o for o, a in sorted(by_ordinal.items()) if a.reference_only] == [2, 8, 10]
    assert all(by_ordinal[o].implemented for o in (1, 3, 4, 5, 6, 7, 9))


def test_worker_and_merchant_carry_money_bonuses():
    assert any(a.money_bonus for a in PROFESSIONS["worker"].abilities)
    assert any(a.money_bonus for a in PROFESSIONS["merchant"].abilities)


def test_priest_rituals_carry_times():
    assert any(a.ritual_time for a in PROFESSIONS["priest"].abilities)


# ---------------------------------------------------------------------------
# Phase 1 - school / profession mutual exclusion and ability sanitizing
# ---------------------------------------------------------------------------

from app.services.professions import (  # noqa: E402
    PROFESSION_SELECT_PREFIX,
    ability_counts_for_display,
    sanitize_profession_abilities,
    split_school_or_profession,
)


def test_split_plain_school_value():
    assert split_school_or_profession("hida_bushi") == ("hida_bushi", "")


def test_split_profession_value():
    assert split_school_or_profession("profession:wave_man") == ("", "wave_man")


def test_split_empty_value():
    assert split_school_or_profession("") == ("", "")


def test_split_rejects_unknown_profession():
    assert split_school_or_profession("profession:nope") == ("", "")


def test_split_rejects_unselectable_profession():
    # D17: only Wave Man is pickable today.
    assert split_school_or_profession("profession:ninja") == ("", "")


def test_split_rejects_unknown_school():
    assert split_school_or_profession("not_a_school") == ("", "")


def test_select_prefix_cannot_collide_with_a_school_id():
    from app.game_data import SCHOOLS
    assert not any(s.startswith(PROFESSION_SELECT_PREFIX) for s in SCHOOLS)


def test_sanitize_drops_unknown_ability_ids():
    out = sanitize_profession_abilities("wave_man", {"nope": 1, "wave_man_initiative_die": 1})
    assert out == {"wave_man_initiative_die": 1}


def test_sanitize_drops_abilities_from_another_profession():
    out = sanitize_profession_abilities("wave_man", {"ninja_fire_to_attack": 1})
    assert out == {}


def test_sanitize_clamps_to_max_per_ability():
    # D4: at most two copies of any Wave Man ability.
    out = sanitize_profession_abilities("wave_man", {"wave_man_initiative_die": 9})
    assert out == {"wave_man_initiative_die": 2}


def test_sanitize_clamps_priest_rituals_to_one():
    out = sanitize_profession_abilities("priest", {"priest_commune": 2})
    assert out == {"priest_commune": 1}


def test_sanitize_drops_zero_and_negative_counts():
    out = sanitize_profession_abilities(
        "wave_man", {"wave_man_initiative_die": 0, "wave_man_round_damage": -3}
    )
    assert out == {}


def test_sanitize_ignores_non_integer_counts():
    out = sanitize_profession_abilities("wave_man", {"wave_man_initiative_die": "two"})
    assert out == {}


def test_sanitize_with_no_profession_returns_empty():
    assert sanitize_profession_abilities("", {"wave_man_initiative_die": 1}) == {}


def test_sanitize_handles_none():
    assert sanitize_profession_abilities("wave_man", None) == {}


def test_ability_counts_for_display_orders_by_ordinal():
    rows = ability_counts_for_display("wave_man", {"wave_man_round_damage": 2})
    assert [r["ordinal"] for r in rows] == list(range(1, 11))
    assert rows[3]["count"] == 2
    assert rows[0]["count"] == 0


def test_ability_counts_for_display_empty_profession():
    assert ability_counts_for_display("", {}) == []


# ---------------------------------------------------------------------------
# Phase 1 - save path: school and profession are mutually exclusive
# ---------------------------------------------------------------------------

from app.models import Character  # noqa: E402

OWNER = "183026066498125825"


def _seed(client, **kwargs):
    session = client._test_session_factory()
    defaults = dict(
        name="Ronin", school="akodo_bushi", school_ring_choice="Water",
        ring_water=3, knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id=OWNER, is_published=False,
    )
    defaults.update(kwargs)
    c = Character(**defaults)
    session.add(c)
    session.commit()
    return c.id


def _reload(client, cid):
    return client._test_session_factory().get(Character, cid)


def test_autosave_switching_to_a_profession_clears_school_state(client):
    cid = _seed(client, technique_choices={"second_dan_choice": "parry"})
    resp = client.post(f"/characters/{cid}/autosave",
                       json={"school": "profession:wave_man"})
    assert resp.status_code == 200
    c = _reload(client, cid)
    assert c.profession == "wave_man"
    assert c.school == ""
    assert c.school_ring_choice == ""
    assert c.knacks == {}
    assert c.technique_choices == {}


def test_autosave_switching_to_a_profession_keeps_foreign_knacks(client):
    # D8: a Wave Man still buys knacks from other schools.
    cid = _seed(client, foreign_knacks={"counterattack": 2})
    client.post(f"/characters/{cid}/autosave", json={"school": "profession:wave_man"})
    assert _reload(client, cid).foreign_knacks == {"counterattack": 2}


def test_autosave_switching_back_to_a_school_clears_the_profession(client):
    cid = _seed(client, school="", profession="wave_man", knacks={},
                profession_abilities={"wave_man_initiative_die": 2})
    client.post(f"/characters/{cid}/autosave", json={"school": "hida_bushi"})
    c = _reload(client, cid)
    assert c.school == "hida_bushi"
    assert c.profession == ""
    assert c.profession_abilities == {}


def test_autosave_rejects_a_payload_sending_both(client):
    # A crafted POST naming both must not leave the character with both.
    cid = _seed(client)
    client.post(f"/characters/{cid}/autosave",
                json={"school": "profession:wave_man", "profession": "wave_man"})
    c = _reload(client, cid)
    assert c.profession == "wave_man"
    assert c.school == ""


def test_autosave_stores_profession_abilities(client):
    cid = _seed(client, school="", profession="wave_man", knacks={})
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"wave_man_initiative_die": 2,
                                 "wave_man_round_damage": 1},
    })
    assert _reload(client, cid).profession_abilities == {
        "wave_man_initiative_die": 2, "wave_man_round_damage": 1,
    }


def test_autosave_clamps_ability_counts_from_a_crafted_payload(client):
    cid = _seed(client, school="", profession="wave_man", knacks={})
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"wave_man_initiative_die": 99, "bogus": 1},
    })
    assert _reload(client, cid).profession_abilities == {"wave_man_initiative_die": 2}


def test_autosave_ignores_abilities_when_there_is_no_profession(client):
    cid = _seed(client)
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"wave_man_initiative_die": 1},
    })
    assert _reload(client, cid).profession_abilities == {}


def test_autosave_unselectable_profession_is_refused(client):
    # D17: Ninja is data-only for now.
    cid = _seed(client)
    client.post(f"/characters/{cid}/autosave", json={"school": "profession:ninja"})
    c = _reload(client, cid)
    assert c.profession == ""
    assert c.school == ""


def test_form_post_can_select_a_profession(client):
    cid = _seed(client)
    resp = client.post(f"/characters/{cid}", data={
        "name": "Ronin", "school": "profession:wave_man",
        "school_ring_choice": "", "honor": "1.0", "rank": "1.0",
        "recognition": "1.0", "starting_xp": "150", "earned_xp": "0",
        "attack": "1", "parry": "1",
    }, follow_redirects=False)
    assert resp.status_code in (200, 302, 303)
    c = _reload(client, cid)
    assert c.profession == "wave_man"
    assert c.school == ""


def test_snapshot_round_trip_preserves_profession(client):
    cid = _seed(client, school="", profession="wave_man", knacks={},
                profession_abilities={"wave_man_round_damage": 2})
    from app.services.versions import _snapshot_state
    state = _snapshot_state(_reload(client, cid))
    assert state["profession"] == "wave_man"
    assert state["profession_abilities"] == {"wave_man_round_damage": 2}


def test_changing_ability_count_shows_in_the_diff_summary():
    from app.services.versions import compute_diff_summary
    old = {"profession": "wave_man", "profession_abilities": {"wave_man_round_damage": 1}}
    new = {"profession": "wave_man", "profession_abilities": {"wave_man_round_damage": 2}}
    assert compute_diff_summary(old, new) == ["Round damage up changed from x1 to x2"]


def test_taking_and_dropping_abilities_show_in_the_diff_summary():
    from app.services.versions import compute_diff_summary
    old = {"profession": "", "profession_abilities": {}}
    new = {"profession": "wave_man",
           "profession_abilities": {"wave_man_round_damage": 2,
                                    "wave_man_initiative_die": 1}}
    diffs = compute_diff_summary(old, new)
    assert "Profession changed to Wave Man" in diffs
    assert "Round damage up taken x2" in diffs
    assert "Extra initiative die taken" in diffs
    back = compute_diff_summary(new, old)
    assert "Profession removed" in back
    assert "Round damage up dropped" in back


# ---------------------------------------------------------------------------
# Phase 2 - allowance
# ---------------------------------------------------------------------------

from app.services.xp import (  # noqa: E402
    calculate_xp_breakdown,
    profession_ability_allowance,
    validate_character,
)


@pytest.mark.parametrize("total_xp,expected", [
    (0, 0), (100, 0), (149, 0),      # D2: nothing before 150 XP
    (150, 1), (151, 1), (164, 1),    # first pick at exactly 150
    (165, 2), (179, 2), (180, 3),    # then one every 15
    (285, 10), (420, 19),
    (435, 20), (1000, 20),           # D4 ceiling: 10 abilities x 2 copies
])
def test_allowance_boundaries(total_xp, expected):
    assert profession_ability_allowance(total_xp, "wave_man") == expected


def test_allowance_caps_lower_for_priest_rituals():
    # Rituals are once-only, so the ceiling is 10 picks, not 20.
    assert profession_ability_allowance(10_000, "priest") == 10


def test_allowance_is_zero_without_a_profession():
    assert profession_ability_allowance(500, "") == 0
    assert profession_ability_allowance(500, "not_a_profession") == 0


def test_allowance_guards_against_junk_xp():
    assert profession_ability_allowance(-50, "wave_man") == 0
    assert profession_ability_allowance(None, "wave_man") == 0


def _wave_man_data(**over):
    data = {
        "school": "", "profession": "wave_man", "profession_abilities": {},
        "school_ring_choice": "", "knacks": {}, "foreign_knacks": {},
        "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2},
        "skills": {}, "attack": 1, "parry": 1,
        "advantages": [], "disadvantages": [],
        "starting_xp": 150, "earned_xp": 0,
        "age": 25, "lineage": "Ronin", "honor": 1.0,
        # The campaign's Rank/Recognition floor, not the rules default.
        "rank": 7.5, "recognition": 7.5,
    }
    data.update(over)
    return data


def test_abilities_cost_no_xp():
    # D2: free. Taking abilities must not move spent or remaining.
    bare = calculate_xp_breakdown(_wave_man_data())
    loaded = calculate_xp_breakdown(_wave_man_data(
        profession_abilities={"wave_man_initiative_die": 2,
                              "wave_man_round_damage": 2},
    ))
    assert bare["grand_total"] == loaded["grand_total"]


def test_xp_breakdown_reports_the_profession_row():
    b = calculate_xp_breakdown(_wave_man_data(
        starting_xp=180,
        profession_abilities={"wave_man_initiative_die": 2},
    ))
    assert b["professions"]["name"] == "Wave Man"
    assert b["professions"]["used"] == 2
    assert b["professions"]["allowance"] == 3
    assert b["professions"]["total"] == 0
    assert b["professions"]["next_at_xp"] == 195


def test_xp_breakdown_profession_row_absent_for_a_school_character():
    b = calculate_xp_breakdown(_wave_man_data(
        school="akodo_bushi", profession="", profession_abilities={},
        school_ring_choice="Water",
        rings={"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
    ))
    assert b["professions"] is None


def test_breakdown_next_at_xp_is_none_at_the_ceiling():
    b = calculate_xp_breakdown(_wave_man_data(starting_xp=435, earned_xp=100))
    assert b["professions"]["allowance"] == 20
    assert b["professions"]["next_at_xp"] is None


# ---------------------------------------------------------------------------
# Phase 2 - validation
# ---------------------------------------------------------------------------

def test_valid_wave_man_has_no_errors():
    # 150 XP grants exactly one pick; claim it so the soft "unclaimed"
    # warning doesn't fire.
    assert validate_character(_wave_man_data(
        profession_abilities={"wave_man_initiative_die": 1},
    )) == []


def test_error_when_picks_exceed_the_allowance():
    errs = validate_character(_wave_man_data(
        starting_xp=150,  # allowance 1
        profession_abilities={"wave_man_initiative_die": 2},
    ))
    assert any("2 Wave Man picks" in e and "allows 1" in e for e in errs)


def test_error_when_one_ability_is_taken_too_many_times():
    errs = validate_character(_wave_man_data(
        starting_xp=400,
        profession_abilities={"wave_man_initiative_die": 3},
    ))
    assert any("more than 2" in e for e in errs)


def test_error_on_an_ability_from_another_profession():
    errs = validate_character(_wave_man_data(
        profession_abilities={"ninja_fire_to_attack": 1},
    ))
    assert any("not a Wave Man ability" in e for e in errs)


def test_error_on_an_unknown_ability_id():
    errs = validate_character(_wave_man_data(profession_abilities={"bogus": 1}))
    assert any("not a Wave Man ability" in e for e in errs)


def test_error_when_school_and_profession_are_both_set():
    errs = validate_character(_wave_man_data(school="akodo_bushi"))
    assert any("both a school and a profession" in e for e in errs)


def test_error_on_an_unknown_profession():
    errs = validate_character(_wave_man_data(profession="nope"))
    assert any("Unknown profession" in e for e in errs)


def test_error_on_a_profession_that_is_not_selectable_yet():
    errs = validate_character(_wave_man_data(
        profession="ninja", profession_abilities={},
    ))
    assert any("not yet available" in e for e in errs)


def test_error_when_a_profession_character_has_school_knacks():
    errs = validate_character(_wave_man_data(knacks={"iaijutsu": 2}))
    assert any("school knacks" in e for e in errs)


def test_error_when_a_profession_character_has_a_school_ring():
    errs = validate_character(_wave_man_data(school_ring_choice="Water"))
    assert any("School Ring" in e for e in errs)


def test_foreign_knacks_are_fine_for_a_profession_character():
    # D8: expressly allowed - no knack complaint, unlike school knacks.
    errs = validate_character(_wave_man_data(
        foreign_knacks={"counterattack": 2}, starting_xp=200,
        profession_abilities={"wave_man_initiative_die": 2,
                              "wave_man_round_damage": 2},
    ))
    assert not any("knack" in e for e in errs)
    assert errs == []


def test_warning_for_unclaimed_picks():
    errs = validate_character(_wave_man_data(starting_xp=180))
    assert any("3 unclaimed Wave Man picks" in e for e in errs)


def test_no_unclaimed_warning_when_all_picks_are_used():
    errs = validate_character(_wave_man_data(
        starting_xp=180, profession_abilities={
            "wave_man_initiative_die": 2, "wave_man_round_damage": 1},
    ))
    assert not any("unclaimed" in e for e in errs)


def test_profession_character_rings_cap_at_five_and_floor_at_two():
    # D7: no School Ring, so every ring behaves like a non-school ring.
    for ring in ("Air", "Fire", "Earth", "Water", "Void"):
        good = _wave_man_data(starting_xp=400)
        good["rings"][ring] = 5
        assert not any("exceeds maximum" in e for e in validate_character(good))
        bad = _wave_man_data(starting_xp=400)
        bad["rings"][ring] = 6
        assert any("exceeds maximum" in e for e in validate_character(bad))


def test_profession_character_is_dan_zero_end_to_end():
    from app.services.dice import build_all_roll_formulas
    from app.services.rolls import compute_dan
    data = _wave_man_data()
    assert compute_dan(data.get("knacks", {}) or {}) == 0
    formulas = build_all_roll_formulas(data)
    assert formulas  # renders without a school, at Dan 0


def test_merged_knacks_for_an_all_foreign_knack_character():
    from app.services.dice import merged_knacks
    data = _wave_man_data(foreign_knacks={"counterattack": 3})
    assert merged_knacks(data).get("counterattack") == 3


def test_editor_xp_view_carries_the_allowance():
    from app.services.xp import editor_xp_view
    view = editor_xp_view(_wave_man_data(
        starting_xp=195, profession_abilities={"wave_man_round_damage": 2}))
    assert view["professions"]["allowance"] == 4
    assert view["professions"]["used"] == 2
    assert view["professions"]["next_at_xp"] == 210


def test_editor_xp_view_has_no_profession_row_for_a_school_character():
    from app.services.xp import editor_xp_view
    view = editor_xp_view(_wave_man_data(profession="", school="akodo_bushi"))
    assert view["professions"] is None


# ---------------------------------------------------------------------------
# Phase 5 - W6 (initiative) and W7 (wound checks), the formula-layer abilities
# ---------------------------------------------------------------------------

from app.services.dice import (  # noqa: E402
    build_initiative_formula,
    build_wound_check_formula,
)


@pytest.mark.parametrize("copies,extra", [(0, 0), (1, 1), (2, 2)])
def test_w6_extra_unkept_initiative_die_per_copy(copies, extra):
    base = build_initiative_formula(_wave_man_data())
    data = _wave_man_data(starting_xp=400)
    if copies:
        data["profession_abilities"] = {"wave_man_initiative_die": copies}
    got = build_initiative_formula(data)
    assert got["rolled"] == base["rolled"] + extra
    # The extra dice are ROLLED, never kept.
    assert got["kept"] == base["kept"]


def test_w6_names_its_source_on_the_sheet():
    data = _wave_man_data(starting_xp=400,
                          profession_abilities={"wave_man_initiative_die": 2})
    f = build_initiative_formula(data)
    assert any("Wave Man" in s for s in (f.get("bonus_sources") or []))


def test_w6_does_nothing_for_a_school_character():
    school = _wave_man_data(
        profession="", school="akodo_bushi",
        profession_abilities={"wave_man_initiative_die": 2})
    assert (build_initiative_formula(school)["rolled"]
            == build_initiative_formula(_wave_man_data())["rolled"])


@pytest.mark.parametrize("copies,extra", [(0, 0), (1, 2), (2, 4)])
def test_w7_two_extra_unkept_wound_check_dice_per_copy(copies, extra):
    base = build_wound_check_formula(_wave_man_data())
    data = _wave_man_data(starting_xp=400)
    if copies:
        data["profession_abilities"] = {"wave_man_wound_check_dice": copies}
    got = build_wound_check_formula(data)
    assert got["rolled"] == base["rolled"] + extra
    assert got["kept"] == base["kept"]


def test_w7_names_its_source_on_the_sheet():
    data = _wave_man_data(starting_xp=400,
                          profession_abilities={"wave_man_wound_check_dice": 1})
    f = build_wound_check_formula(data)
    assert any("Wave Man" in s for s in (f.get("bonus_sources") or []))


def test_w7_respects_the_ten_dice_cap():
    # A high-Water Wave Man with two copies adds 4 rolled dice; the 10k10
    # cap still applies (excess rolled dice convert per apply_dice_caps).
    data = _wave_man_data(starting_xp=400,
                          profession_abilities={"wave_man_wound_check_dice": 2})
    data["rings"]["Water"] = 5
    f = build_wound_check_formula(data)
    assert f["rolled"] <= 10
    assert f["kept"] <= 10


# ---------------------------------------------------------------------------
# Phase 5 - the annotation pass in build_all_roll_formulas
# ---------------------------------------------------------------------------

from app.services.dice import build_all_roll_formulas, is_wave_man_attack_key  # noqa: E402


def _wave_man_fighter(**over):
    """A Wave Man who bought every attack knack as a foreign knack (D8)."""
    data = _wave_man_data(starting_xp=600, **over)
    data.setdefault("foreign_knacks", {})
    data["foreign_knacks"] = {
        "counterattack": 2, "double_attack": 2, "lunge": 2, "iaijutsu": 2,
    }
    return data


def test_w1_reaches_every_attack_type_including_iaijutsu():
    # D9: unlike ATTACK_TYPE_KEYS, the Wave Man's attack scope includes
    # the iaijutsu strike.
    data = _wave_man_fighter(profession_abilities={"wave_man_miss_raise": 2})
    out = build_all_roll_formulas(data)
    for key in ("attack", "knack:counterattack", "knack:double_attack",
                "knack:lunge", "knack:iaijutsu"):
        assert key in out, key
        assert out[key].get("wave_man_miss_raise") == 2, key


def test_w1_does_not_touch_non_attack_rolls():
    data = _wave_man_fighter(profession_abilities={"wave_man_miss_raise": 2})
    out = build_all_roll_formulas(data)
    assert not out["parry"].get("wave_man_miss_raise")
    assert not out["skill:etiquette"].get("wave_man_miss_raise")
    assert not out["wound_check"].get("wave_man_miss_raise")


def test_is_wave_man_attack_key_covers_iaijutsu_but_not_initiative():
    assert is_wave_man_attack_key("knack:iaijutsu", {})
    assert is_wave_man_attack_key("attack", {"is_attack_type": True})
    assert not is_wave_man_attack_key("initiative:athletics", {})
    assert not is_wave_man_attack_key("parry", {})


def test_reference_only_abilities_are_annotated_on_attacks():
    # W2 and W10 carry no math, but the result panel needs to know how
    # many copies to name in its reminder line.
    data = _wave_man_fighter(profession_abilities={
        "wave_man_parry_tn": 2, "wave_man_wound_check_tn": 1})
    out = build_all_roll_formulas(data)
    assert out["attack"]["wave_man_parry_tn"] == 2
    assert out["attack"]["wave_man_wound_check_tn"] == 1


def test_damage_abilities_are_annotated_on_attacks():
    data = _wave_man_fighter(profession_abilities={
        "wave_man_weapon_dice": 2, "wave_man_round_damage": 1,
        "wave_man_failed_parry_dice": 2})
    out = build_all_roll_formulas(data)
    assert out["attack"]["wave_man_weapon_dice"] == 2
    assert out["attack"]["wave_man_round_damage"] == 1
    assert out["attack"]["wave_man_failed_parry_dice"] == 2


def test_w5_frees_dice_only_where_impaired_suppressed_the_reroll():
    # D12: wherever 10s could ever reroll. Initiative and the iaijutsu
    # strike never reroll for anyone, so they carry a different
    # no_reroll_reason and are untouched.
    data = _wave_man_fighter(profession_abilities={"wave_man_impaired_reroll": 2},
                             skills={"etiquette": 3})
    data["current_serious_wounds"] = 9   # impaired: SW >= Earth
    data["rings"]["Earth"] = 2
    out = build_all_roll_formulas(data)
    assert out["skill:etiquette"].get("wave_man_freed_dice") == 2
    assert out["attack"].get("wave_man_freed_dice") == 2
    assert not out["initiative"].get("wave_man_freed_dice")


def test_w5_is_absent_when_not_impaired():
    data = _wave_man_fighter(profession_abilities={"wave_man_impaired_reroll": 2})
    out = build_all_roll_formulas(data)
    assert not out["skill:etiquette"].get("wave_man_freed_dice")


def test_w5_does_not_clear_the_impaired_suppression():
    # The ability frees specific dice; it does not turn reroll_tens back
    # on the way the Hida 3rd Dan technique does.
    data = _wave_man_fighter(profession_abilities={"wave_man_impaired_reroll": 2},
                             skills={"etiquette": 3})
    data["current_serious_wounds"] = 9
    data["rings"]["Earth"] = 2
    out = build_all_roll_formulas(data)
    assert out["skill:etiquette"]["reroll_tens"] is False
    assert out["skill:etiquette"]["no_reroll_reason"] == "impaired"


def test_a_school_character_gets_no_wave_man_annotations():
    data = _wave_man_data(
        profession="", school="akodo_bushi", school_ring_choice="Water",
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        profession_abilities={"wave_man_miss_raise": 2})
    data["rings"]["Water"] = 3
    out = build_all_roll_formulas(data)
    assert not out["attack"].get("wave_man_miss_raise")


def test_w5_does_not_resurrect_a_reroll_suppressed_for_another_reason():
    # An unskilled roll never rerolls 10s regardless of Impaired, so W5
    # must not reach it - the annotation keys on the reason, not the flag.
    data = _wave_man_fighter(profession_abilities={"wave_man_impaired_reroll": 2})
    data["current_serious_wounds"] = 9
    data["rings"]["Earth"] = 2
    out = build_all_roll_formulas(data)
    assert out["skill:etiquette"]["no_reroll_reason"] == "unskilled"
    assert not out["skill:etiquette"].get("wave_man_freed_dice")


# ---------------------------------------------------------------------------
# Phase 3 - editor rendering
# ---------------------------------------------------------------------------

def test_editor_offers_wave_man_in_the_school_dropdown(client):
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    assert 'value="profession:wave_man"' in html
    assert "Professions (no school)" in html


def test_editor_greys_out_the_unimplemented_professions(client):
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    for pid in ("worker", "merchant", "priest", "ninja"):
        assert f'value="profession:{pid}"' in html
    assert html.count("(not yet implemented)") >= 4


def test_editor_renders_all_ten_abilities_for_a_wave_man(client):
    cid = _seed(client, school="", profession="wave_man", knacks={})
    html = client.get(f"/characters/{cid}/edit").text
    assert 'data-testid="profession-abilities"' in html
    for aid in (a.id for a in PROFESSIONS["wave_man"].abilities):
        assert aid in html


def test_editor_seeds_the_profession_select_value(client):
    cid = _seed(client, school="", profession="wave_man", knacks={})
    html = client.get(f"/characters/{cid}/edit").text
    assert '"profession:wave_man"' in html


def test_editor_seeds_the_allowance_from_the_server(client):
    cid = _seed(client, school="", profession="wave_man", knacks={},
                starting_xp=180, school_ring_choice="")
    html = client.get(f"/characters/{cid}/edit").text
    assert '"allowance": 3' in html or '"allowance":3' in html


def test_profession_info_partial_renders(client):
    html = client.get("/characters/api/profession-info/wave_man").text
    assert 'data-testid="profession-info"' in html
    assert "Wave Man" in html
    assert "09-professions.md#wave-man-abilities" in html


def test_profession_info_partial_refuses_an_unselectable_profession(client):
    assert client.get("/characters/api/profession-info/ninja").text == ""


def test_profession_info_partial_refuses_an_unknown_profession(client):
    assert client.get("/characters/api/profession-info/nope").text == ""


def test_xp_endpoint_splits_the_prefixed_dropdown_value(client):
    cid = _seed(client)
    resp = client.post(f"/characters/{cid}/xp", json={
        "school": "profession:wave_man",
        "profession_abilities": {"wave_man_round_damage": 1},
        "starting_xp": 150, "earned_xp": 0,
    })
    body = resp.json()
    assert body["professions"]["name"] == "Wave Man"
    assert body["professions"]["used"] == 1
    assert body["professions"]["allowance"] == 1


# ---------------------------------------------------------------------------
# Phase 4 - view sheet and other render surfaces
# ---------------------------------------------------------------------------

def _seed_wave_man(client, **over):
    defaults = dict(
        school="", school_ring_choice="", profession="wave_man", knacks={},
        ring_water=2, is_published=True,
        published_state={"name": "Ronin"},
        profession_abilities={"wave_man_initiative_die": 1},
    )
    defaults.update(over)
    return _seed(client, **defaults)


def test_sheet_shows_the_profession_panel(client):
    cid = _seed_wave_man(client)
    html = client.get(f"/characters/{cid}").text
    assert "Wave Man" in html
    assert "No school selected yet" not in html
    assert "No School Ring or Dan" in html


def test_sheet_lists_every_ability_with_the_taken_ones_emphasised(client):
    cid = _seed_wave_man(client)
    html = client.get(f"/characters/{cid}").text
    for a in PROFESSIONS["wave_man"].abilities:
        assert f'data-ability="{a.id}"' in html


def test_sheet_marks_an_ability_taken_twice(client):
    cid = _seed_wave_man(client, starting_xp=200,
                         profession_abilities={"wave_man_round_damage": 2})
    html = client.get(f"/characters/{cid}").text
    assert 'data-testid="ability-x2-wave_man_round_damage"' in html


def test_sheet_flags_reference_only_abilities_the_character_took(client):
    cid = _seed_wave_man(client, profession_abilities={"wave_man_parry_tn": 1})
    html = client.get(f"/characters/{cid}").text
    assert 'data-testid="reference-only-wave_man_parry_tn"' in html
    assert "changes what your opponent rolls" in html


def test_sheet_does_not_flag_reference_only_abilities_not_taken(client):
    cid = _seed_wave_man(client, profession_abilities={"wave_man_round_damage": 1})
    html = client.get(f"/characters/{cid}").text
    assert 'data-testid="reference-only-wave_man_parry_tn"' not in html


def test_sheet_explains_w1s_auto_succeeding_parry_when_taken(client):
    cid = _seed_wave_man(client, profession_abilities={"wave_man_miss_raise": 1})
    html = client.get(f"/characters/{cid}").text
    assert 'data-testid="w1-parry-note"' in html
    # D-answer to Q4: the parry auto-succeeds but is STILL ROLLED.
    assert "still rolled" in html


def test_sheet_links_the_profession_rules(client):
    cid = _seed_wave_man(client)
    html = client.get(f"/characters/{cid}").text
    assert "09-professions.md#wave-man-abilities" in html


def test_sheet_for_a_school_character_is_unchanged(client):
    cid = _seed(client)
    html = client.get(f"/characters/{cid}").text
    assert "Profession" not in html or "Wave Man" not in html


def test_gm_api_reports_profession_and_abilities(client, monkeypatch):
    monkeypatch.setenv("ROLL_QUERY_TOKEN", "tok")
    cid = _seed_wave_man(client, profession_abilities={"wave_man_round_damage": 2},
                         starting_xp=200)
    resp = client.get("/api/characters", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    row = next(c for c in resp.json()["characters"] if c["id"] == cid)
    assert row["profession"] == "wave_man"
    assert row["profession_abilities"] == {"wave_man_round_damage": 2}


def test_sheet_xp_summary_shows_picks_used_not_xp(client):
    cid = _seed_wave_man(client, starting_xp=180,
                         profession_abilities={"wave_man_round_damage": 2})
    html = client.get(f"/characters/{cid}").text
    assert 'data-xp-card="professions"' in html
    assert "Wave Man abilities" in html
    assert "2 / 3" in html


def test_sheet_xp_summary_has_no_profession_card_for_a_school_character(client):
    cid = _seed(client)
    html = client.get(f"/characters/{cid}").text
    assert 'data-xp-card="professions"' not in html


def test_google_sheet_export_names_the_profession(client):
    from app.services.sheets import _build_overview_rows
    cid = _seed_wave_man(client, starting_xp=200,
                         profession_abilities={"wave_man_round_damage": 2})
    character = client._test_session_factory().get(Character, cid)
    from app.services.status import compute_effective_status
    char_dict = character.to_dict()
    rows = _build_overview_rows(
        character, char_dict, None, {}, 0,
        compute_effective_status(char_dict), {},
    )
    flat = str(rows)
    assert "Wave Man (profession)" in flat
    assert "Wave Man Abilities" in flat
    assert "Round damage up x2" in flat
