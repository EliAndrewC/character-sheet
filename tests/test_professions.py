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


def test_everything_but_ninja_is_available():
    # Part 2 brought Priest in beside Wave Man; part 3 brought Worker and
    # Merchant. Ninja abilities are unlocked separately.
    for pid in ("wave_man", "priest", "worker", "merchant"):
        assert PROFESSIONS[pid].is_available is True, pid
    assert PROFESSIONS["ninja"].is_available is False


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

from app.game_data import PROFESSION_CHARACTER_TYPE as PTYPE  # noqa: E402
from app.services.professions import (  # noqa: E402
    PROFESSION_SELECT_VALUE,
    ability_counts_for_display,
    sanitize_profession_abilities,
    select_value_for,
    split_school_or_profession,
)


def test_split_plain_school_value():
    assert split_school_or_profession("hida_bushi") == ("hida_bushi", "")


def test_split_profession_value():
    assert split_school_or_profession("profession:wave_man") == ("", PTYPE)


def test_split_empty_value():
    assert split_school_or_profession("") == ("", "")


def test_split_rejects_unknown_school():
    assert split_school_or_profession("not_a_school") == ("", "")


def test_select_value_cannot_collide_with_a_school_id():
    from app.game_data import SCHOOLS
    assert PROFESSION_SELECT_VALUE not in SCHOOLS


def test_sanitize_drops_unknown_ability_ids():
    out = sanitize_profession_abilities({"nope": 1, "wave_man_initiative_die": 1})
    assert out == {"wave_man_initiative_die": 1}


def test_sanitize_drops_abilities_from_an_unavailable_profession():
    out = sanitize_profession_abilities({"ninja_fire_to_attack": 1})
    assert out == {}


def test_sanitize_clamps_to_max_per_ability():
    # D4: at most two copies of any Wave Man ability.
    out = sanitize_profession_abilities({"wave_man_initiative_die": 9})
    assert out == {"wave_man_initiative_die": 2}


def test_sanitize_clamps_priest_rituals_to_one():
    out = sanitize_profession_abilities({"priest_commune": 2})
    assert out == {"priest_commune": 1}


def test_sanitize_drops_zero_and_negative_counts():
    out = sanitize_profession_abilities({"wave_man_initiative_die": 0, "wave_man_round_damage": -3}
    )
    assert out == {}


def test_sanitize_ignores_non_integer_counts():
    out = sanitize_profession_abilities({"wave_man_initiative_die": "two"})
    assert out == {}


def test_sanitize_accepts_a_wave_man_ability_on_its_own():
    assert sanitize_profession_abilities(
        {"wave_man_initiative_die": 1}) == {"wave_man_initiative_die": 1}


def test_sanitize_handles_none():
    assert sanitize_profession_abilities(None) == {}


def test_ability_counts_for_display_orders_by_ordinal():
    groups = ability_counts_for_display(
        {"wave_man_round_damage": 2}, include_untaken=True)
    rows = next(g for g in groups if g["profession_id"] == "wave_man")["rows"]
    assert [r["ordinal"] for r in rows] == list(range(1, 11))
    assert rows[3]["count"] == 2
    assert rows[0]["count"] == 0


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
                       json={"school": "profession"})
    assert resp.status_code == 200
    c = _reload(client, cid)
    assert c.profession == PTYPE
    assert c.school == ""
    assert c.school_ring_choice == ""
    assert c.knacks == {}
    assert c.technique_choices == {}


def test_autosave_switching_to_a_profession_keeps_foreign_knacks(client):
    # D8: a Wave Man still buys knacks from other schools.
    cid = _seed(client, foreign_knacks={"counterattack": 2})
    client.post(f"/characters/{cid}/autosave", json={"school": "profession"})
    assert _reload(client, cid).foreign_knacks == {"counterattack": 2}


def test_autosave_switching_back_to_a_school_clears_the_profession(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={},
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
                json={"school": "profession", "profession": "nonsense"})
    c = _reload(client, cid)
    assert c.profession == PTYPE
    assert c.school == ""


def test_autosave_stores_profession_abilities(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={})
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"wave_man_initiative_die": 2,
                                 "wave_man_round_damage": 1},
    })
    assert _reload(client, cid).profession_abilities == {
        "wave_man_initiative_die": 2, "wave_man_round_damage": 1,
    }


def test_autosave_clamps_ability_counts_from_a_crafted_payload(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={})
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"wave_man_initiative_die": 99, "bogus": 1},
    })
    assert _reload(client, cid).profession_abilities == {"wave_man_initiative_die": 2}


def test_a_school_character_gets_no_benefit_from_stored_abilities(client):
    # The sanitizer no longer needs the character's own profession to
    # validate an ability id, so a stored map can survive on a school
    # character; ability_count is the gate that matters, and it reads 0.
    from app.services.professions import ability_count
    cid = _seed(client)
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"wave_man_initiative_die": 1},
    })
    c = _reload(client, cid)
    assert c.profession == ""
    assert ability_count(c.to_dict(), "wave_man_initiative_die") == 0


def test_autosave_legacy_prefixed_value_still_makes_a_profession_character(client):
    # An editor tab open across the deploy still POSTs profession:<id>;
    # resolving that to "no profession" would wipe their abilities.
    cid = _seed(client)
    client.post(f"/characters/{cid}/autosave",
                json={"school": "profession:ninja"})
    c = _reload(client, cid)
    assert c.profession == PTYPE
    assert c.school == ""


def test_form_post_can_select_a_profession(client):
    cid = _seed(client)
    resp = client.post(f"/characters/{cid}", data={
        "name": "Ronin", "school": "profession",
        "school_ring_choice": "", "honor": "1.0", "rank": "1.0",
        "recognition": "1.0", "starting_xp": "150", "earned_xp": "0",
        "attack": "1", "parry": "1",
    }, follow_redirects=False)
    assert resp.status_code in (200, 302, 303)
    c = _reload(client, cid)
    assert c.profession == PTYPE
    assert c.school == ""


def test_snapshot_round_trip_preserves_profession(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={},
                profession_abilities={"wave_man_round_damage": 2})
    from app.services.versions import _snapshot_state
    state = _snapshot_state(_reload(client, cid))
    assert state["profession"] == PTYPE
    assert state["profession_abilities"] == {"wave_man_round_damage": 2}


def test_changing_ability_count_shows_in_the_diff_summary():
    from app.services.versions import compute_diff_summary
    old = {"profession": PTYPE, "profession_abilities": {"wave_man_round_damage": 1}}
    new = {"profession": PTYPE, "profession_abilities": {"wave_man_round_damage": 2}}
    assert compute_diff_summary(old, new) == ["Round damage up changed from x1 to x2"]


def test_taking_and_dropping_abilities_show_in_the_diff_summary():
    from app.services.versions import compute_diff_summary
    old = {"profession": "", "profession_abilities": {}}
    new = {"profession": PTYPE,
           "profession_abilities": {"wave_man_round_damage": 2,
                                    "wave_man_initiative_die": 1}}
    diffs = compute_diff_summary(old, new)
    assert "Profession selected" in diffs
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
    (435, 20),                       # Wave Man alone is exhausted here
    (585, 30),                       # Wave Man 20 + Priest 10 alone
    (150 + 67 * 15, 68), (10_000, 68),  # pooled ceiling across all four
])
def test_allowance_boundaries(total_xp, expected):
    assert profession_ability_allowance(total_xp) == expected


def test_allowance_guards_against_junk_xp():
    assert profession_ability_allowance(-50) == 0
    assert profession_ability_allowance(None) == 0


def _wave_man_data(**over):
    data = {
        "school": "", "profession": PTYPE, "profession_abilities": {},
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
    assert b["professions"]["name"] == "Profession"
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
    b = calculate_xp_breakdown(_wave_man_data(starting_xp=2000, earned_xp=0))
    assert b["professions"]["allowance"] == 68
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
    assert any("2 profession picks" in e and "allows 1" in e for e in errs)


def test_error_when_one_ability_is_taken_too_many_times():
    errs = validate_character(_wave_man_data(
        starting_xp=400,
        profession_abilities={"wave_man_initiative_die": 3},
    ))
    assert any("may not be taken more than 2 times" in e for e in errs)


def test_error_on_an_ability_from_an_unavailable_profession():
    errs = validate_character(_wave_man_data(
        profession_abilities={"ninja_fire_to_attack": 1},
    ))
    assert any("not yet available" in e for e in errs)


def test_error_on_an_unknown_ability_id():
    errs = validate_character(_wave_man_data(profession_abilities={"bogus": 1}))
    assert any("not an ability of any profession" in e for e in errs)


def test_error_when_school_and_profession_are_both_set():
    errs = validate_character(_wave_man_data(school="akodo_bushi"))
    assert any("both a school and a profession" in e for e in errs)


def test_error_on_an_unknown_character_type():
    errs = validate_character(_wave_man_data(profession="nope"))
    assert any("Unknown character type" in e for e in errs)


def test_error_when_a_priest_ritual_is_taken_twice():
    # P7: rituals are once-only, unlike every other profession's abilities.
    errs = validate_character(_wave_man_data(
        starting_xp=400, profession_abilities={"priest_commune": 2}))
    assert any("may only be taken once" in e for e in errs)


def test_error_when_a_profession_character_has_school_knacks():
    errs = validate_character(_wave_man_data(knacks={"iaijutsu": 2}))
    assert any("no school knacks" in e for e in errs)


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
    assert any("3 unclaimed profession picks" in e for e in errs)


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

def test_editor_offers_one_profession_option_in_the_school_dropdown(client):
    # P1: one character type, not one per profession.
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    assert 'value="profession"' in html
    assert '<optgroup label="No school">' in html
    assert 'value="profession:wave_man"' not in html


def test_editor_hides_the_ninja_abilities(client):
    # P6/R1: Ninja abilities are unlocked separately and never shown.
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    assert 'data-profession-group="ninja"' not in html
    assert "ninja_fire_to_attack" not in html


def test_editor_shows_all_four_available_professions(client):
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    for pid in ("wave_man", "worker", "merchant", "priest"):
        assert f'data-profession-group="{pid}"' in html, pid


def test_editor_marks_priest_rituals_as_once_only(client):
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    assert 'data-testid="profession-once-only-priest"' in html
    assert 'data-testid="profession-once-only-wave_man"' not in html


def test_editor_lists_professions_in_rules_order(client):
    # With everything but Ninja available, the available-first sort is a
    # no-op and the rules file's own order stands.
    cid = _seed(client)
    html = client.get(f"/characters/{cid}/edit").text
    order = [html.index(f'data-profession-group="{p}"')
             for p in ("wave_man", "worker", "merchant", "priest")]
    assert order == sorted(order)


def test_editor_renders_every_available_ability(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={})
    html = client.get(f"/characters/{cid}/edit").text
    assert 'data-testid="profession-abilities"' in html
    for pid in ("wave_man", "priest"):
        for aid in (a.id for a in PROFESSIONS[pid].abilities):
            assert aid in html, aid


def test_editor_seeds_the_profession_select_value(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={})
    html = client.get(f"/characters/{cid}/edit").text
    assert '"profession"' in html


def test_editor_seeds_the_allowance_from_the_server(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={},
                starting_xp=180, school_ring_choice="")
    html = client.get(f"/characters/{cid}/edit").text
    assert '"allowance": 3' in html or '"allowance":3' in html


def test_profession_info_partial_renders(client):
    html = client.get("/characters/api/profession-info").text
    assert 'data-testid="profession-info"' in html
    assert "09-professions.md#wave-man-abilities" in html
    assert "09-professions.md#priest-rituals" in html
    # Ninja is hidden entirely (P6).
    assert "#ninja-abilities" not in html


def test_xp_endpoint_reads_the_profession_dropdown_value(client):
    cid = _seed(client)
    resp = client.post(f"/characters/{cid}/xp", json={
        "school": "profession",
        "profession_abilities": {"wave_man_round_damage": 1},
        "starting_xp": 150, "earned_xp": 0,
    })
    body = resp.json()
    assert body["professions"]["name"] == "Profession"
    assert body["professions"]["used"] == 1
    assert body["professions"]["allowance"] == 1


# ---------------------------------------------------------------------------
# Phase 4 - view sheet and other render surfaces
# ---------------------------------------------------------------------------

def _seed_wave_man(client, **over):
    defaults = dict(
        school="", school_ring_choice="", profession=PTYPE, knacks={},
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


def test_sheet_lists_only_the_abilities_actually_taken(client):
    # P10: the View Sheet is not the editor's catalogue.
    cid = _seed_wave_man(client)
    html = client.get(f"/characters/{cid}").text
    assert 'data-ability="wave_man_initiative_die"' in html
    for a in PROFESSIONS["wave_man"].abilities:
        if a.id != "wave_man_initiative_die":
            assert f'data-ability="{a.id}"' not in html


def test_sheet_groups_a_mixed_build_by_profession(client):
    cid = _seed_wave_man(client, starting_xp=200, profession_abilities={
        "wave_man_round_damage": 2, "priest_commune": 1,
    })
    html = client.get(f"/characters/{cid}").text
    assert 'data-profession-group="wave_man"' in html
    assert 'data-profession-group="priest"' in html
    assert html.index('data-profession-group="wave_man"') < html.index(
        'data-profession-group="priest"')


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
    assert row["profession"] == PTYPE
    assert row["profession_abilities"] == {"wave_man_round_damage": 2}


def test_sheet_xp_summary_shows_picks_used_not_xp(client):
    cid = _seed_wave_man(client, starting_xp=180,
                         profession_abilities={"wave_man_round_damage": 2})
    html = client.get(f"/characters/{cid}").text
    assert 'data-xp-card="professions"' in html
    assert "Profession abilities" in html
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
    assert "Profession (no school)" in flat
    assert "Wave Man Abilities" in flat
    assert "Round damage up x2" in flat


# ---------------------------------------------------------------------------
# Phase 6 - the Discord bot's roller
# ---------------------------------------------------------------------------

import random  # noqa: E402


def _impaired_wave_man(**over):
    data = _wave_man_data(starting_xp=600, skills={"etiquette": 3}, **over)
    data["current_serious_wounds"] = 9
    data["rings"]["Earth"] = 2
    return data


def test_bot_gets_the_extra_wound_check_dice(client):
    from app.services.roll_engine import execute_roll
    plain = execute_roll(_wave_man_data(), "wound_check", rng=random.Random(1))
    boosted = execute_roll(
        _wave_man_data(starting_xp=400,
                       profession_abilities={"wave_man_wound_check_dice": 2}),
        "wound_check", rng=random.Random(1))
    assert len(boosted["kept"]) + len(boosted["dropped"]) == \
        len(plain["kept"]) + len(plain["dropped"]) + 4


def test_bot_applies_w5_so_the_same_roll_matches_the_sheet():
    # W5's die is selected automatically, so there is no interactive choice
    # for the bot to skip - and a roll that came out differently depending
    # on where it was made would be a bug.
    from app.services.roll_engine import execute_roll
    data = _impaired_wave_man(
        profession_abilities={"wave_man_impaired_reroll": 2})

    class _TenThenSeven(random.Random):
        def __init__(self):
            super().__init__()
            self.queue = [10, 10, 4, 3, 2, 7, 7, 7, 7, 7, 7]

        def randint(self, a, b):
            return self.queue.pop(0) if self.queue else 5

    payload = execute_roll(data, "skill:etiquette", rng=_TenThenSeven())
    chains = [c["parts"] for c in payload["kept"] + payload["dropped"]]
    exploded = [c for c in chains if len(c) > 1]
    assert len(exploded) == 2, chains


def test_bot_respects_the_copy_count_for_w5():
    from app.services.roll_engine import execute_roll
    data = _impaired_wave_man(
        profession_abilities={"wave_man_impaired_reroll": 1})

    class _AllTens(random.Random):
        def __init__(self):
            super().__init__()
            self.n = 0

        def randint(self, a, b):
            self.n += 1
            return 10 if self.n <= 3 else 4

    payload = execute_roll(data, "skill:etiquette", rng=_AllTens())
    chains = [c["parts"] for c in payload["kept"] + payload["dropped"]]
    assert len([c for c in chains if len(c) > 1]) == 1, chains


def test_bot_does_not_explode_tens_without_the_ability():
    from app.services.roll_engine import execute_roll
    data = _impaired_wave_man()

    class _AllTens(random.Random):
        def randint(self, a, b):
            return 10

    payload = execute_roll(data, "skill:etiquette", rng=_AllTens())
    chains = [c["parts"] for c in payload["kept"] + payload["dropped"]]
    assert all(len(c) == 1 for c in chains), chains


def test_roll_dice_freed_tens_mirrors_the_js_helper():
    from app.services.roll_engine import roll_dice

    class _Seq(random.Random):
        def __init__(self, vals):
            super().__init__()
            self.vals = list(vals)

        def randint(self, a, b):
            return self.vals.pop(0) if self.vals else 1

    # Two 10s and a 4; one freed die -> only the first 10 chains.
    out = roll_dice(3, 2, False, rng=_Seq([10, 10, 4, 7]), freed_tens=1)
    chains = sorted(([d["parts"] for d in out["kept"] + out["dropped"]]), key=len)
    assert chains[-1] == [10, 7]
    assert out["kept_sum"] == 27


def test_roll_dice_freed_tens_is_ignored_when_tens_already_reroll():
    from app.services.roll_engine import roll_dice

    class _Seq(random.Random):
        def __init__(self, vals):
            super().__init__()
            self.vals = list(vals)

        def randint(self, a, b):
            return self.vals.pop(0) if self.vals else 1

    out = roll_dice(1, 1, True, rng=_Seq([10, 3]), freed_tens=2)
    assert out["kept"][0]["parts"] == [10, 3]


# ---------------------------------------------------------------------------
# Edge and error paths
# ---------------------------------------------------------------------------

def test_ability_count_of_nothing_is_zero():
    from app.services.professions import ability_count
    assert ability_count(None, "wave_man_round_damage") == 0


def test_form_post_ignores_malformed_ability_json(client):
    # The form path carries the map as a JSON string; a crafted body that
    # isn't JSON must leave the character with no abilities, not a 500.
    cid = _seed(client)
    resp = client.post(f"/characters/{cid}", data={
        "name": "Ronin", "school": "profession",
        "profession_abilities": "{not json at all",
        "school_ring_choice": "", "honor": "1.0", "rank": "1.0",
        "recognition": "1.0", "starting_xp": "150", "earned_xp": "0",
        "attack": "1", "parry": "1",
    }, follow_redirects=False)
    assert resp.status_code in (200, 302, 303)
    c = _reload(client, cid)
    assert c.profession == PTYPE
    assert c.profession_abilities == {}


def test_form_post_accepts_ability_json(client):
    cid = _seed(client)
    client.post(f"/characters/{cid}", data={
        "name": "Ronin", "school": "profession",
        "profession_abilities": '{"wave_man_round_damage": 2}',
        "school_ring_choice": "", "honor": "1.0", "rank": "1.0",
        "recognition": "1.0", "starting_xp": "300", "earned_xp": "0",
        "attack": "1", "parry": "1",
    }, follow_redirects=False)
    assert _reload(client, cid).profession_abilities == {"wave_man_round_damage": 2}


def test_w5_skips_non_ten_dice_while_the_budget_lasts():
    from app.services.roll_engine import roll_dice

    class _Seq(random.Random):
        def __init__(self, vals):
            super().__init__()
            self.vals = list(vals)

        def randint(self, a, b):
            return self.vals.pop(0) if self.vals else 1

    # A 4 sits between the two 10s: the loop must step over it rather
    # than spending the budget on it.
    out = roll_dice(3, 3, False, rng=_Seq([4, 10, 10, 6, 2]), freed_tens=2)
    chains = sorted([d["parts"] for d in out["kept"]], key=len)
    assert chains[0] == [4]
    assert [10, 6] in chains and [10, 2] in chains


def test_google_sheet_export_says_no_school_when_there_is_neither(client):
    from app.services.sheets import _build_overview_rows
    from app.services.status import compute_effective_status
    cid = _seed(client, school="", profession="", knacks={},
                school_ring_choice="")
    character = client._test_session_factory().get(Character, cid)
    char_dict = character.to_dict()
    rows = _build_overview_rows(
        character, char_dict, None, {}, 0,
        compute_effective_status(char_dict), {},
    )
    assert "No school" in str(rows)


def test_diff_summary_falls_back_to_a_label_for_an_unknown_ability():
    from app.services.versions import compute_diff_summary
    old = {"profession": PTYPE, "profession_abilities": {}}
    new = {"profession": PTYPE, "profession_abilities": {"legacy_thing": 1}}
    assert "Legacy Thing taken" in compute_diff_summary(old, new)


def test_breakdown_next_at_xp_is_the_base_before_any_pick_is_earned():
    b = calculate_xp_breakdown(_wave_man_data(starting_xp=100, earned_xp=0))
    assert b["professions"]["allowance"] == 0
    assert b["professions"]["next_at_xp"] == 150


def test_error_when_abilities_are_set_without_a_profession():
    errs = validate_character(_wave_man_data(
        profession="", school="akodo_bushi", school_ring_choice="Water",
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        profession_abilities={"wave_man_round_damage": 1},
    ))
    assert any("no profession is selected" in e for e in errs)


def test_validation_treats_a_non_integer_count_as_zero():
    errs = validate_character(_wave_man_data(
        starting_xp=150,
        profession_abilities={"wave_man_round_damage": "two"},
    ))
    # Counts as 0 picks used, so the soft unclaimed warning fires and no
    # over-allowance error does.
    assert any("unclaimed" in e for e in errs)
    assert not any("only allows" in e for e in errs)


def test_diff_summary_skips_abilities_that_did_not_change():
    from app.services.versions import compute_diff_summary
    old = {"profession": PTYPE,
           "profession_abilities": {"wave_man_round_damage": 2,
                                    "wave_man_initiative_die": 1}}
    new = {"profession": PTYPE,
           "profession_abilities": {"wave_man_round_damage": 2,
                                    "wave_man_initiative_die": 2}}
    diffs = compute_diff_summary(old, new)
    assert diffs == ["Extra initiative die changed from x1 to x2"]


# ===========================================================================
# Part 2 - one Profession character type, abilities pooled across professions
# (profession-design/priest-and-pooling.md)
# ===========================================================================

from app.game_data import (  # noqa: E402
    PROFESSION_ABILITY_POOL,
    PROFESSION_CHARACTER_TYPE,
)


# ---------------------------------------------------------------------------
# Phase 1 - availability, the pool, and the character-type sentinel
# ---------------------------------------------------------------------------

def test_availability_is_three_state():
    # P6 needs three states, which a boolean cannot express. Worker and
    # Merchant were previews until part 3 turned them on; Ninja abilities
    # are unlocked separately and stay hidden.
    for pid in ("wave_man", "priest", "worker", "merchant"):
        assert PROFESSIONS[pid].availability == "available", pid
    assert PROFESSIONS["ninja"].availability == "hidden"


def test_available_and_visible_helpers():
    assert PROFESSIONS["wave_man"].is_available is True
    assert PROFESSIONS["worker"].is_available is True
    # Ninja is neither available nor visible.
    assert PROFESSIONS["ninja"].is_available is False
    assert PROFESSIONS["ninja"].is_visible is False


def test_the_pool_holds_every_available_ability_only():
    ids = [a.id for a in PROFESSION_ABILITY_POOL]
    # Wave Man 10 + Priest 10 + Worker 9 (one held back) + Merchant 10.
    assert len(ids) == 39
    assert "wave_man_miss_raise" in ids
    assert "priest_commune" in ids
    assert "worker_strength" in ids
    assert "merchant_law" in ids
    assert "worker_advanced_as_basic" not in ids
    assert not any(i.startswith("ninja_") for i in ids)


def test_the_pool_is_ordered_by_profession_then_ordinal():
    from app.game_data import PROFESSION_BY_ABILITY, PROFESSIONS as _P
    order = list(_P)
    got = [(PROFESSION_BY_ABILITY[a.id], a.ordinal) for a in PROFESSION_ABILITY_POOL]
    assert got == sorted(got, key=lambda x: (order.index(x[0]), x[1]))


def test_character_type_sentinel_is_not_a_school_or_profession_id():
    from app.game_data import SCHOOLS
    assert PROFESSION_CHARACTER_TYPE not in SCHOOLS
    assert PROFESSION_CHARACTER_TYPE not in PROFESSIONS


# ---------------------------------------------------------------------------
# Phase 1 - the dropdown value
# ---------------------------------------------------------------------------

def test_split_accepts_the_bare_profession_value():
    assert split_school_or_profession("profession") == ("", PROFESSION_CHARACTER_TYPE)


def test_split_still_accepts_the_legacy_prefixed_value():
    # A stale editor tab open across the deploy will send the old form;
    # resolving it to "no profession" would wipe the character's abilities.
    assert split_school_or_profession("profession:wave_man") == (
        "", PROFESSION_CHARACTER_TYPE)
    assert split_school_or_profession("profession:priest") == (
        "", PROFESSION_CHARACTER_TYPE)


def test_split_legacy_value_naming_an_unknown_profession_is_still_a_profession():
    # The type is what matters now, not which profession was named.
    assert split_school_or_profession("profession:nope") == (
        "", PROFESSION_CHARACTER_TYPE)


def test_select_value_for_a_profession_character():
    assert select_value_for("", PROFESSION_CHARACTER_TYPE) == "profession"
    assert select_value_for("hida_bushi", "") == "hida_bushi"
    assert select_value_for("", "") == ""


# ---------------------------------------------------------------------------
# Phase 1 - sanitizing pools across professions
# ---------------------------------------------------------------------------

def test_sanitize_accepts_abilities_from_any_available_profession():
    out = sanitize_profession_abilities({
        "wave_man_round_damage": 2, "priest_commune": 1,
    })
    assert out == {"wave_man_round_damage": 2, "priest_commune": 1}


def test_sanitize_applies_each_abilitys_own_per_ability_limit():
    # P7: a Wave Man ability caps at 2 and a Priest ritual at 1, in the
    # SAME character.
    out = sanitize_profession_abilities({
        "wave_man_round_damage": 5, "priest_commune": 5,
    })
    assert out == {"wave_man_round_damage": 2, "priest_commune": 1}


def test_sanitize_drops_hidden_profession_abilities():
    out = sanitize_profession_abilities({
        "ninja_fire_to_attack": 1, "wave_man_round_damage": 1,
    })
    assert out == {"wave_man_round_damage": 1}


def test_sanitize_still_drops_junk():
    assert sanitize_profession_abilities({"nope": 1}) == {}
    assert sanitize_profession_abilities({"wave_man_round_damage": 0}) == {}
    assert sanitize_profession_abilities({"wave_man_round_damage": "two"}) == {}
    assert sanitize_profession_abilities({"wave_man_round_damage": True}) == {}
    assert sanitize_profession_abilities(None) == {}
    assert sanitize_profession_abilities("nonsense") == {}


# ---------------------------------------------------------------------------
# Phase 1 - ability_count no longer keys on the character's profession
# ---------------------------------------------------------------------------

def _mixed(**over):
    data = {
        "profession": PROFESSION_CHARACTER_TYPE,
        "profession_abilities": {"wave_man_round_damage": 2, "priest_commune": 1},
    }
    data.update(over)
    return data


def test_ability_count_reads_across_professions():
    from app.services.professions import ability_count
    assert ability_count(_mixed(), "wave_man_round_damage") == 2
    assert ability_count(_mixed(), "priest_commune") == 1
    assert ability_count(_mixed(), "wave_man_miss_raise") == 0


def test_ability_count_is_zero_for_a_school_character():
    from app.services.professions import ability_count
    assert ability_count(_mixed(profession=""), "wave_man_round_damage") == 0


def test_ability_count_is_zero_for_an_unavailable_profession():
    from app.services.professions import ability_count
    data = _mixed(profession_abilities={"ninja_fire_to_attack": 2})
    assert ability_count(data, "ninja_fire_to_attack") == 0


# ---------------------------------------------------------------------------
# Phase 1 - grouped display rows
# ---------------------------------------------------------------------------

def test_display_groups_by_profession_and_hides_ninja():
    groups = ability_counts_for_display(
        {"wave_man_round_damage": 2}, include_untaken=True)
    ids = [g["profession_id"] for g in groups]
    assert ids == ["wave_man", "worker", "merchant", "priest"]
    assert all(len(g["rows"]) == 10 for g in groups)
    wave = next(g for g in groups if g["profession_id"] == "wave_man")
    assert next(r for r in wave["rows"] if r["id"] == "wave_man_round_damage")["count"] == 2


def test_display_carries_availability_and_the_rules_anchor():
    groups = ability_counts_for_display({}, include_untaken=True)
    by_id = {g["profession_id"]: g for g in groups}
    assert by_id["wave_man"]["availability"] == "available"
    assert by_id["worker"]["availability"] == "available"
    assert by_id["priest"]["rules_anchor"] == "#priest-rituals"
    # Priest rituals are once-only, and the editor has to say so.
    assert by_id["priest"]["rows"][0]["max"] == 1
    assert by_id["wave_man"]["rows"][0]["max"] == 2


def test_display_for_the_sheet_shows_only_what_was_taken():
    # P10: the View Sheet lists taken abilities only, grouped.
    groups = ability_counts_for_display(
        {"wave_man_round_damage": 2, "priest_commune": 1}, include_untaken=False)
    assert [g["profession_id"] for g in groups] == ["wave_man", "priest"]
    assert [r["id"] for r in groups[0]["rows"]] == ["wave_man_round_damage"]
    assert [r["id"] for r in groups[1]["rows"]] == ["priest_commune"]


def test_display_for_the_sheet_of_a_character_with_nothing_taken():
    assert ability_counts_for_display({}, include_untaken=False) == []


# ---------------------------------------------------------------------------
# Phase 1 - the legacy-profession-type data migration
# ---------------------------------------------------------------------------

def test_migration_collapses_a_legacy_profession_id_to_the_type(db):
    # Unlike the ALTER branches in _migrate_add_columns, this one is
    # reachable on a fresh DB, so it gets a real test rather than a pragma.
    from app.database import _migrate_legacy_profession_types
    old = Character(name="Old Wave Man", school="", profession="wave_man",
                    profession_abilities={"wave_man_round_damage": 2})
    db.add(old)
    db.commit()
    cid = old.id
    assert _migrate_legacy_profession_types(db) == 1
    # The migration closes the session it was handed (it owns its own
    # lifecycle in production); re-query rather than refreshing a detached
    # instance.
    migrated = db.query(Character).filter(Character.id == cid).one()
    assert migrated.profession == PTYPE
    # Abilities are untouched: ids are globally unique and carry their own
    # provenance, so nothing about them needed rewriting.
    assert migrated.profession_abilities == {"wave_man_round_damage": 2}


def test_migration_leaves_school_and_already_migrated_characters_alone(db):
    from app.database import _migrate_legacy_profession_types
    db.add(Character(name="Schooled", school="akodo_bushi", profession=""))
    db.add(Character(name="Already", school="", profession=PTYPE))
    db.commit()
    assert _migrate_legacy_profession_types(db) == 0


def test_migration_normalizes_junk_in_the_profession_column(db):
    # A crafted write could have left anything here; whatever it says, the
    # character is a profession character.
    from app.database import _migrate_legacy_profession_types
    c = Character(name="Junk", school="", profession="nonsense")
    db.add(c)
    db.commit()
    cid = c.id
    assert _migrate_legacy_profession_types(db) == 1
    assert db.query(Character).filter(Character.id == cid).one().profession == PTYPE


# ---------------------------------------------------------------------------
# Phase 5 - Priest rituals for profession characters
# ---------------------------------------------------------------------------

def _abilities_for(client, cid):
    """The school_abilities flag dict the sheet renders from."""
    html = client.get(f"/characters/{cid}").text
    import json as _json
    import re as _re
    m = _re.search(r'id="school-abilities"[^>]*>(.*?)</script>', html, _re.S)
    return _json.loads(m.group(1)) if m else {}


def _party_priests(client, cid):
    html = client.get(f"/characters/{cid}").text
    import json as _json
    import re as _re
    m = _re.search(r'id="party-priests"[^>]*>(.*?)</script>', html, _re.S)
    return _json.loads(m.group(1)) if m else []


def test_bless_topic_and_research_are_separate_flags(client):
    # P4: two abilities, so taking one grants only its button.
    cid = _seed_wave_man(client, starting_xp=200, profession_abilities={
        "priest_conversation_blessing": 1})
    flags = _abilities_for(client, cid)
    assert flags.get("priest_bless_topic") is True
    assert not flags.get("priest_bless_research")

    cid2 = _seed_wave_man(client, name="Researcher", starting_xp=200,
                          profession_abilities={"priest_research_blessing": 1})
    flags2 = _abilities_for(client, cid2)
    assert flags2.get("priest_bless_research") is True
    assert not flags2.get("priest_bless_topic")


def test_a_profession_character_without_the_rituals_gets_neither(client):
    cid = _seed_wave_man(client, profession_abilities={"wave_man_round_damage": 1})
    flags = _abilities_for(client, cid)
    assert not flags.get("priest_bless_topic")
    assert not flags.get("priest_bless_research")


def test_a_priest_school_character_still_gets_both(client):
    cid = _seed(client, school="priest", school_ring_choice="Water",
                ring_water=3,
                knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
                is_published=True, published_state={"name": "Priest"})
    flags = _abilities_for(client, cid)
    assert flags.get("priest_bless_topic") is True
    assert flags.get("priest_bless_research") is True


def _group_with(client, *characters):
    """Seed a gaming group holding the given (kwargs) characters."""
    from app.models import GamingGroup
    session = client._test_session_factory()
    group = GamingGroup(name=f"Group {id(characters)}")
    session.add(group)
    session.commit()
    ids = []
    for kwargs in characters:
        kwargs.setdefault("is_published", True)
        kwargs.setdefault("published_state", {"name": kwargs.get("name", "x")})
        ids.append(_seed(client, gaming_group_id=group.id, **kwargs))
    return ids


def test_a_profession_character_with_the_ritual_can_bless_an_ally(client):
    blesser, ally = _group_with(
        client,
        dict(name="Ritual Ronin", school="", profession=PTYPE, knacks={},
             starting_xp=200,
             profession_abilities={"priest_ignore_penalties": 1}),
        dict(name="Ally"),
    )
    names = [p["name"] for p in _party_priests(client, ally)]
    assert "Ritual Ronin" in names


def test_a_profession_character_without_the_ritual_cannot(client):
    blesser, ally = _group_with(
        client,
        dict(name="Plain Ronin", school="", profession=PTYPE, knacks={},
             profession_abilities={"wave_man_round_damage": 1}),
        dict(name="Ally2"),
    )
    assert _party_priests(client, ally) == []


def test_a_priest_school_ally_still_appears(client):
    priest, ally = _group_with(
        client,
        dict(name="School Priest", school="priest", school_ring_choice="Water",
             ring_water=3,
             knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1}),
        dict(name="Ally3"),
    )
    assert [p["name"] for p in _party_priests(client, ally)] == ["School Priest"]


def test_a_priest_school_character_can_bless_themselves(client):
    # P9: supersedes the old rule, which excluded self.
    (priest,) = _group_with(
        client,
        dict(name="Lone Priest", school="priest", school_ring_choice="Water",
             ring_water=3,
             knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1}),
    )
    entries = _party_priests(client, priest)
    assert len(entries) == 1
    assert entries[0]["priest_id"] == priest
    assert entries[0].get("is_self") is True


def test_a_profession_character_with_the_ritual_can_bless_themselves(client):
    (ronin,) = _group_with(
        client,
        dict(name="Lone Ronin", school="", profession=PTYPE, knacks={},
             starting_xp=200,
             profession_abilities={"priest_ignore_penalties": 1}),
    )
    entries = _party_priests(client, ronin)
    assert [e["priest_id"] for e in entries] == [ronin]
    assert entries[0]["is_self"] is True


def test_self_blessing_needs_no_gaming_group(client):
    # The ritual is performed on yourself; there is no party to consult.
    cid = _seed_wave_man(client, starting_xp=200,
                         profession_abilities={"priest_ignore_penalties": 1})
    entries = _party_priests(client, cid)
    assert [e["is_self"] for e in entries] == [True]


def test_a_character_without_the_ritual_does_not_bless_themselves(client):
    cid = _seed_wave_man(client, profession_abilities={"wave_man_round_damage": 1})
    assert _party_priests(client, cid) == []


def test_self_and_ally_blessers_both_appear(client):
    ronin, priest = _group_with(
        client,
        dict(name="Both Ronin", school="", profession=PTYPE, knacks={},
             starting_xp=200,
             profession_abilities={"priest_ignore_penalties": 1}),
        dict(name="Other Priest", school="priest", school_ring_choice="Water",
             ring_water=3,
             knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1}),
    )
    entries = _party_priests(client, ronin)
    assert [e["name"] for e in entries] == ["Both Ronin", "Other Priest"]
    assert [e["is_self"] for e in entries] == [True, False]


def test_is_profession_character_handles_nothing():
    from app.services.professions import is_profession_character
    assert is_profession_character(None) is False
    assert is_profession_character({}) is False
    assert is_profession_character({"profession": PTYPE}) is True


def test_xp_summary_ignores_a_non_integer_count():
    # The sanitizer drops these on write; a stored row from an older
    # release could still carry one, and the summary must not blow up.
    summary = calculate_xp_breakdown(_wave_man_data(
        starting_xp=200,
        profession_abilities={"wave_man_round_damage": "two",
                              "priest_commune": 1},
    ))["professions"]
    assert summary["used"] == 1


# ===========================================================================
# Part 3 - Worker and Merchant abilities
# (profession-design/worker-and-merchant.md)
# ===========================================================================

# ---------------------------------------------------------------------------
# Phase 1 - the stored ability text must match the rules file verbatim
# ---------------------------------------------------------------------------

RULES_PROFESSIONS = "/host-l7r-repo/rules/09-professions.md"

_RULES_SECTION_TO_PROFESSION = {
    "Wave Man": "wave_man", "Worker": "worker", "Merchant": "merchant",
    "Priest": "priest", "Ninja": "ninja",
}


def _parse_rules_abilities():
    """Ability text straight out of rules/09-professions.md, by profession.

    Top-level list items only: the indented sub-items are money bonuses and
    ritual times, which are separate fields on ProfessionAbility.
    """
    import os
    import re
    if not os.path.exists(RULES_PROFESSIONS):
        pytest.skip("the l7r rules repo is not mounted at /host-l7r-repo")
    raw = open(RULES_PROFESSIONS).read()
    out = {}
    for m in re.finditer(r"^## (.+?) (?:Abilities|Rituals)\s*$", raw, re.M):
        start = m.end()
        nxt = raw.find("\n## ", start)
        body = raw[start: nxt if nxt != -1 else len(raw)]
        out[_RULES_SECTION_TO_PROFESSION[m.group(1).strip()]] = [
            line[2:].strip() for line in body.split("\n")
            if line.startswith("- ") and not line.startswith("  - ")
        ]
    return out


def _normalize(text):
    import re
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize("pid", ["wave_man", "worker", "merchant", "priest", "ninja"])
def test_stored_ability_text_matches_the_rules_file(pid):
    """The rules are the source of truth; this catches upstream rewording.

    It has already happened twice - the Wave Man's third ability was
    reworded during the first build, and five Worker/Merchant abilities
    before the third - so a test is cheaper than noticing by eye.
    """
    upstream = _parse_rules_abilities()[pid]
    stored = PROFESSIONS[pid].abilities
    assert len(upstream) == len(stored)
    for want, ability in zip(upstream, stored):
        assert _normalize(ability.text) == _normalize(want), ability.id


def test_the_rules_file_parse_finds_all_five_professions():
    # A parse that silently found nothing would make the test above vacuous.
    parsed = _parse_rules_abilities()
    assert set(parsed) == set(PROFESSIONS)
    assert all(len(v) == 10 for v in parsed.values())


# ---------------------------------------------------------------------------
# Phase 1 - per-ability availability
# ---------------------------------------------------------------------------

def test_worker_and_merchant_are_now_available():
    for pid in ("wave_man", "priest", "worker", "merchant"):
        assert PROFESSIONS[pid].is_available is True, pid
    assert PROFESSIONS["ninja"].is_available is False


def test_the_campaign_specific_worker_ability_is_not_selectable():
    # R2: Wk5, advanced-skills-as-basic, is campaign-specific.
    by_id = {a.id: a for a in PROFESSIONS["worker"].abilities}
    assert by_id["worker_advanced_as_basic"].available is False
    assert all(a.available for a in PROFESSIONS["worker"].abilities
               if a.id != "worker_advanced_as_basic")


def test_every_other_profession_ability_is_available():
    for pid in ("wave_man", "priest", "merchant"):
        assert all(a.available for a in PROFESSIONS[pid].abilities), pid


def test_ability_availability_needs_both_the_profession_and_the_ability():
    from app.services.professions import ability_is_available
    assert ability_is_available("worker_strength") is True
    assert ability_is_available("worker_advanced_as_basic") is False   # ability
    assert ability_is_available("ninja_fire_to_attack") is False        # profession
    assert ability_is_available("nope") is False


def test_the_unselectable_ability_is_out_of_the_pool():
    ids = [a.id for a in PROFESSION_ABILITY_POOL]
    assert "worker_advanced_as_basic" not in ids
    assert "worker_strength" in ids
    assert "merchant_open_commerce" in ids


def test_the_pooled_ceiling_counts_only_takeable_abilities():
    from app.services.xp import profession_ability_allowance, profession_ability_pool_size
    # Wave Man 10x2 + Priest 10x1 + Worker 9x2 + Merchant 10x2 = 68.
    assert profession_ability_pool_size() == 68
    assert profession_ability_allowance(10_000) == 68
    # 68 picks needs 150 + 67*15 XP.
    assert profession_ability_allowance(150 + 67 * 15) == 68
    assert profession_ability_allowance(150 + 66 * 15) == 67


def test_sanitize_drops_the_unselectable_ability():
    out = sanitize_profession_abilities({
        "worker_advanced_as_basic": 1, "worker_strength": 2,
    })
    assert out == {"worker_strength": 2}


def test_ability_count_is_zero_for_the_unselectable_ability():
    from app.services.professions import ability_count
    data = {"profession": PTYPE,
            "profession_abilities": {"worker_advanced_as_basic": 2}}
    assert ability_count(data, "worker_advanced_as_basic") == 0


def test_validation_names_the_unselectable_ability(client):
    errs = validate_character(_wave_man_data(
        starting_xp=200,
        profession_abilities={"worker_advanced_as_basic": 1}))
    assert any("not yet available" in e or "not available" in e for e in errs)
    assert not any("not an ability of any profession" in e for e in errs)


def test_the_editor_still_shows_the_unselectable_ability(client):
    # R2 is "greyed out", not "hidden": a player should see it exists.
    cid = _seed(client, school="", profession=PTYPE, knacks={})
    html = client.get(f"/characters/{cid}/edit").text
    assert "worker_advanced_as_basic" in html
    assert 'data-profession-group="worker"' in html


def test_worker_and_merchant_abilities_are_takeable_end_to_end(client):
    cid = _seed(client, school="", profession=PTYPE, knacks={}, starting_xp=400)
    client.post(f"/characters/{cid}/autosave", json={
        "profession_abilities": {"worker_strength": 2, "merchant_law": 1},
    })
    assert _reload(client, cid).profession_abilities == {
        "worker_strength": 2, "merchant_law": 1}


# ---------------------------------------------------------------------------
# Phase 2 - conditional free raises as "Alternative totals" rows
# ---------------------------------------------------------------------------

def _prof(abilities, **over):
    data = _wave_man_data(starting_xp=1000, **over)
    data["profession_abilities"] = abilities
    return data


def _alts(character_data, key):
    formulas = build_all_roll_formulas(character_data)
    return formulas[key].get("alternatives") or []


def _alt_labels(character_data, key):
    return [a["label"] for a in _alts(character_data, key)]


@pytest.mark.parametrize("ability,key,raises,fragment", [
    ("worker_etiquette_higher_class", "skill:etiquette", 3, "higher social class"),
    ("worker_commerce_purchases", "skill:commerce", 3, "making purchases"),
    ("worker_ethics_bragging", "skill:bragging", 4, "own ethics"),
    ("worker_ethics_bragging", "skill:precepts", 4, "own ethics"),
    ("worker_strength", "athletics:Water", 2, "feats of strength"),
    ("worker_endurance", "athletics:Earth", 2, "feats of endurance"),
    ("worker_authority_trouble", "skill:sincerity", 5, "authority figure"),
    ("worker_authority_trouble", "skill:tact", 5, "authority figure"),
    ("merchant_sincerity", "skill:sincerity", 2, "your business"),
    ("merchant_interrogation", "skill:interrogation", 2, "your business"),
    ("merchant_investigation", "skill:investigation", 4, "your business"),
    ("merchant_contested_commerce", "skill:commerce", 2, "contested"),
    ("merchant_culture_gifts", "skill:culture", 4, "gifts"),
    ("merchant_heraldry", "skill:heraldry", 5, "customers"),
    ("merchant_law", "skill:law", 3, "your business"),
])
def test_each_conditional_ability_adds_its_row(ability, key, raises, fragment):
    rows = [a for a in _alts(_prof({ability: 1}), key) if fragment in a["label"]]
    assert len(rows) == 1, _alt_labels(_prof({ability: 1}), key)
    assert rows[0]["extra_flat"] == raises * 5


@pytest.mark.parametrize("ability,key,raises,fragment", [
    ("worker_etiquette_higher_class", "skill:etiquette", 3, "higher social class"),
    ("worker_strength", "athletics:Water", 2, "feats of strength"),
    ("merchant_heraldry", "skill:heraldry", 5, "customers"),
])
def test_two_copies_double_the_free_raises(ability, key, raises, fragment):
    # R10: all bonuses double when an ability is taken twice.
    rows = [a for a in _alts(_prof({ability: 2}), key) if fragment in a["label"]]
    assert rows[0]["extra_flat"] == raises * 5 * 2


def test_no_rows_without_the_ability():
    assert _alts(_prof({}), "skill:etiquette") == []


def test_a_school_character_gets_no_profession_rows():
    data = _wave_man_data(profession="", school="akodo_bushi",
                          school_ring_choice="Water",
                          knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
                          profession_abilities={"merchant_law": 2})
    data["rings"]["Water"] = 3
    assert _alts(data, "skill:law") == []


def test_worker_strength_does_not_touch_the_other_rings():
    data = _prof({"worker_strength": 2})
    assert _alt_labels(data, "athletics:Water")
    for ring in ("Air", "Fire", "Earth"):
        assert not any("strength" in l for l in _alt_labels(data, f"athletics:{ring}"))


def test_endurance_and_strength_land_on_different_rings():
    data = _prof({"worker_strength": 1, "worker_endurance": 1})
    assert any("strength" in l for l in _alt_labels(data, "athletics:Water"))
    assert any("endurance" in l for l in _alt_labels(data, "athletics:Earth"))
    assert not any("endurance" in l for l in _alt_labels(data, "athletics:Water"))


def test_merchant_business_experience_emits_a_plain_and_a_contested_row():
    # M4: "3 free raises ... and an extra free raise if the roll is contested"
    # cannot be one row, because a row states a single number.
    rows = _alts(_prof({"merchant_bragging_precepts": 1}), "skill:bragging")
    amounts = sorted(r["extra_flat"] for r in rows)
    assert amounts == [15, 20]
    assert any("contested" in r["label"] for r in rows)


def test_the_contested_row_doubles_too():
    rows = _alts(_prof({"merchant_bragging_precepts": 2}), "skill:bragging")
    assert sorted(r["extra_flat"] for r in rows) == [30, 40]


def test_two_abilities_on_one_skill_stay_separate_rows():
    # Wk7 (ethics) and M4 (business experience) both touch bragging with
    # different conditions; merging them would claim a bonus that does not
    # exist for either condition alone.
    data = _prof({"worker_ethics_bragging": 1, "merchant_bragging_precepts": 1})
    rows = _alts(data, "skill:bragging")
    assert len(rows) == 3          # ethics, business, business-contested
    assert len({r["label"] for r in rows}) == 3


def test_the_authority_rows_are_open_roll_only():
    # Wk10 names OPEN sincerity and tact rolls.
    for key in ("skill:sincerity", "skill:tact"):
        rows = [a for a in _alts(_prof({"worker_authority_trouble": 1}), key)
                if "authority" in a["label"]]
        assert rows[0].get("open_roll") is True, key


def test_business_rows_are_not_open_roll_gated():
    rows = [a for a in _alts(_prof({"merchant_law": 1}), "skill:law")
            if "business" in a["label"]]
    assert not rows[0].get("open_roll")


def test_a_profession_row_does_not_disturb_withdrawns_cap():
    """Withdrawn caps OPEN sincerity at 15, and carries that cap on its own
    open-roll alternative row rather than on the base formula (a contested
    sincerity roll is uncapped). A profession free raise is a separate row
    with its own condition, so it must neither inherit the cap nor lift it.

    The two rows not combining is the existing modelling of conditional
    bonuses generally - Streetwise and Withdrawn behave the same way - not
    something these abilities introduce.
    """
    data = _prof({"merchant_sincerity": 2}, disadvantages=["withdrawn"])
    rows = _alts(data, "skill:sincerity")
    withdrawn = [r for r in rows if r.get("max_total")]
    business = [r for r in rows if "business" in r["label"]]
    assert len(withdrawn) == 1
    assert withdrawn[0]["max_total"] == 15
    assert withdrawn[0].get("open_roll") is True
    assert len(business) == 1
    assert not business[0].get("max_total")
    assert business[0]["extra_flat"] == 20


def test_the_bot_card_carries_the_new_alternatives():
    from app.services.roll_engine import execute_roll
    import random
    payload = execute_roll(_prof({"merchant_law": 1}), "skill:law",
                           rng=random.Random(7))
    assert any("business" in a["label"] for a in payload["alternatives"])
