"""Unit tests for the server-side roll engine (app/services/roll_engine.py).

The dice math is asserted against a seeded RNG so the results are exact,
and the display helpers are asserted against the same cases as the browser's
``tests/js/roll_math.test.js`` - the two implementations have to agree or a
slash-command card would disagree with the sheet.
"""

import random

import pytest

from app.services import roll_engine
from app.services.roll_engine import (
    alt_cap,
    alt_total,
    apply_total_cap,
    execute_roll,
    impaired_now,
    roll_dice,
    roll_one_die,
    visible_alternatives,
    _formula_text,
)
from tests.conftest import make_character_data


def _character(**overrides):
    data = make_character_data(**overrides)
    data.setdefault("rings", {"Air": 3, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2})
    return data


class _ScriptedRandom:
    """An rng whose ``randint`` walks a fixed list of faces."""

    def __init__(self, faces):
        self._faces = list(faces)

    def randint(self, a, b):
        return self._faces.pop(0)


# ---------------------------------------------------------------------------
# One die
# ---------------------------------------------------------------------------


def test_roll_one_die_no_explosion():
    die = roll_one_die(True, _ScriptedRandom([7]))
    assert die == {"parts": [7], "value": 7}


def test_roll_one_die_explodes_on_ten():
    die = roll_one_die(True, _ScriptedRandom([10, 10, 4]))
    assert die == {"parts": [10, 10, 4], "value": 24}


def test_roll_one_die_does_not_explode_when_reroll_is_off():
    """Impaired characters keep the 10 as a flat 10."""
    die = roll_one_die(False, _ScriptedRandom([10]))
    assert die == {"parts": [10], "value": 10}


def test_roll_one_die_chain_is_bounded():
    """A stuck rng must not hang the request."""
    die = roll_one_die(True, _ScriptedRandom([10] * 200))
    assert len(die["parts"]) == roll_engine.MAX_CHAIN


# ---------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------


def test_roll_dice_keeps_the_highest():
    got = roll_dice(4, 2, False, _ScriptedRandom([3, 9, 1, 6]))
    assert [d["value"] for d in got["kept"]] == [6, 9]
    assert [d["value"] for d in got["dropped"]] == [1, 3]
    assert got["kept_sum"] == 15


def test_roll_dice_keeping_everything_drops_nothing():
    got = roll_dice(3, 3, False, _ScriptedRandom([2, 5, 8]))
    assert got["dropped"] == []
    assert got["kept_sum"] == 15


def test_roll_dice_kept_is_clamped_to_the_pool():
    got = roll_dice(2, 5, False, _ScriptedRandom([4, 4]))
    assert len(got["kept"]) == 2 and got["dropped"] == []


def test_roll_dice_zero_dice():
    got = roll_dice(0, 2, False, _ScriptedRandom([]))
    assert got == {"kept": [], "dropped": [], "kept_sum": 0}


def test_roll_dice_pool_is_bounded():
    got = roll_dice(10_000, 1, False, _ScriptedRandom([5] * 10_000))
    assert len(got["kept"]) + len(got["dropped"]) == roll_engine.MAX_DICE


def test_roll_dice_defaults_to_a_real_rng():
    """No rng argument still produces a legal roll."""
    got = roll_dice(5, 3, True)
    assert len(got["kept"]) == 3 and len(got["dropped"]) == 2
    assert got["kept_sum"] == sum(d["value"] for d in got["kept"])
    assert all(1 <= p <= 10 for d in got["kept"] for p in d["parts"])


def test_roll_dice_explodes_end_to_end():
    got = roll_dice(2, 1, True, _ScriptedRandom([10, 3, 5]))
    assert [d["parts"] for d in got["kept"]] == [[10, 3]]
    assert got["kept_sum"] == 13


# ---------------------------------------------------------------------------
# Display helpers - must match roll_math.js
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("total,cap,expected", [
    (20, 0, 20),        # 0 means uncapped
    (20, None, 20),
    (20, "15", 20),     # non-numeric cap ignored
    (20, True, 20),     # a bool is not a cap
    (20, 15, 15),
    (10, 15, 10),
])
def test_apply_total_cap(total, cap, expected):
    assert apply_total_cap(total, cap) == expected


def test_alt_cap_prefers_the_rows_own():
    assert alt_cap({"max_total": 15}, 40) == 15


def test_alt_cap_inherits_the_formulas():
    assert alt_cap({}, 40) == 40


def test_alt_cap_uncapped():
    assert alt_cap({}, None) == 0


def test_alt_total_applies_the_row_cap():
    assert alt_total(20, {"extra_flat": 10, "max_total": 15}, 0) == 15
    assert alt_total(20, {"extra_flat": 10}, 0) == 30


def test_visible_alternatives_drops_rows_a_cap_swallows():
    """A capped row that lands on the roll's own total says nothing."""
    alts = [{"label": "vs Wasp", "extra_flat": 10}]
    assert visible_alternatives(20, alts, 15) == []
    assert visible_alternatives(20, alts, 0) == alts


def test_visible_alternatives_handles_none():
    assert visible_alternatives(20, None, 0) == []


# ---------------------------------------------------------------------------
# Formula text
# ---------------------------------------------------------------------------


def test_formula_text_without_a_bonus():
    assert _formula_text({"rolled": 3, "kept": 2}) == "3k2"


def test_formula_text_with_a_bonus():
    assert _formula_text({"rolled": 3, "kept": 2, "flat": 5}) == "3k2 + 5"


def test_formula_text_appends_the_skill_rank():
    got = _formula_text({
        "rolled": 3, "kept": 2, "flat": 5,
        "skill_name": "etiquette", "skill_rank": 1,
    })
    assert got == "3k2 + 5 (etiquette skill: 1)"


def test_formula_text_hides_a_negative_flat():
    """Matches the sheet's own convention, so cards look identical."""
    assert _formula_text({"rolled": 2, "kept": 2, "flat": -10}) == "2k2"


# ---------------------------------------------------------------------------
# execute_roll
# ---------------------------------------------------------------------------


def test_execute_roll_builds_the_card_payload():
    data = _character(
        school="courtier", skills={"etiquette": 1},
        knacks={"discern_honor": 1, "oppose_social": 1, "worldliness": 1},
        advantages=["charming"],
    )
    # Charming gives a +5 free raise, so the formula is 3k2 + 5.
    payload = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([2, 8, 6]),
    )
    assert payload["title"] == "Etiquette (Air)"
    assert payload["formula"] == "3k2 + 5 (etiquette skill: 1)"
    assert payload["kept"] == [{"parts": [6]}, {"parts": [8]}]
    assert payload["dropped"] == [{"parts": [2]}]
    assert payload["kept_sum"] == 14
    assert payload["total"] == 19
    assert payload["bonuses"] == [{"label": "Charming", "amount": 5}]
    assert payload["extras"] == []


def test_execute_roll_unknown_key():
    assert execute_roll(_character(), "skill:not_a_skill") is None


def test_execute_roll_is_deterministic_under_a_seed():
    data = _character(skills={"etiquette": 2})
    first = execute_roll(data, "skill:etiquette", rng=random.Random(1))
    second = execute_roll(data, "skill:etiquette", rng=random.Random(1))
    assert first == second


def test_execute_roll_applies_a_total_cap():
    """Withdrawn caps open etiquette rolls at 15; the payload total is capped."""
    data = _character(skills={"etiquette": 4}, disadvantages=["withdrawn"])
    payload = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([9, 9, 9, 9, 9, 9, 9]),
    )
    assert payload["total"] <= 15


def test_execute_roll_suppresses_the_reroll_when_impaired():
    """A 10 stays a 10 for an Impaired character - no exploding chain."""
    data = _character(skills={"etiquette": 2}, current_serious_wounds=99)
    assert impaired_now(data) is True
    payload = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([10] * 10),
    )
    assert all(cell["parts"] == [10] for cell in payload["kept"])


def test_impaired_now_false_for_a_healthy_character():
    assert impaired_now(_character()) is False


# ---------------------------------------------------------------------------
# Alternative rows on the payload
# ---------------------------------------------------------------------------


def _alts(formula, base_total):
    return roll_engine._alternatives_for_payload(formula, base_total)


def test_alternatives_keep_a_labelled_delta():
    formula = {"alternatives": [{"label": "vs Wasp", "extra_flat": 10}]}
    assert _alts(formula, 20) == [{"label": "vs Wasp", "extra_flat": 10}]


def test_alternatives_drop_an_unlabelled_row():
    formula = {"alternatives": [{"label": "  ", "extra_flat": 10}]}
    assert _alts(formula, 20) == []


def test_alternatives_drop_a_non_integer_delta():
    formula = {"alternatives": [{"label": "vs Wasp", "extra_flat": "lots"}]}
    assert _alts(formula, 20) == []


def test_alternatives_drop_a_pointless_zero_row():
    formula = {"alternatives": [{"label": "vs Wasp", "extra_flat": 0}]}
    assert _alts(formula, 20) == []


def test_alternatives_keep_a_zero_row_that_carries_a_cap():
    """Withdrawn's open-sincerity row: the ceiling IS the information."""
    formula = {
        "alternatives": [{
            "label": "open sincerity", "extra_flat": 0,
            "max_total": 15, "max_total_source": "Withdrawn",
        }],
    }
    assert _alts(formula, 20) == [{
        "label": "open sincerity", "extra_flat": 0,
        "max_total": 15, "max_total_source": "Withdrawn",
    }]


def test_alternatives_drop_a_row_the_formula_cap_flattens():
    """The row would show 15, and so does the roll itself - so say nothing."""
    formula = {
        "max_total": 15,
        "max_total_source": "Withdrawn",
        "alternatives": [{"label": "open etiquette", "extra_flat": 10}],
    }
    assert _alts(formula, 20) == []


def test_alternatives_inherit_the_formula_cap_and_its_source():
    """A row with no cap of its own still lands under the formula's."""
    formula = {
        "max_total": 30,
        "max_total_source": "Withdrawn",
        "alternatives": [{"label": "vs Wasp", "extra_flat": 20}],
    }
    assert _alts(formula, 20) == [{
        "label": "vs Wasp", "extra_flat": 20,
        "max_total": 30, "max_total_source": "Withdrawn",
    }]


def test_alternatives_keep_a_cap_with_no_named_source():
    formula = {
        "alternatives": [{"label": "capped", "extra_flat": 0, "max_total": 15}],
    }
    assert _alts(formula, 20) == [
        {"label": "capped", "extra_flat": 0, "max_total": 15},
    ]


def test_execute_roll_carries_specialization_alternatives(monkeypatch):
    """End to end: a Specialization surfaces as an alternative-total row."""
    data = _character(
        skills={"etiquette": 2},
        specializations=[{"text": "Court Gossip", "skills": ["etiquette"]}],
    )
    payload = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([4, 5, 6, 7, 8]),
    )
    labels = [a["label"] for a in payload["alternatives"]]
    assert any("Court Gossip" in label for label in labels), labels


def test_alternatives_drop_a_zero_row_that_opts_out_of_the_formula_cap():
    """Uncapped and adding nothing: the row survives the visibility filter
    (its value differs from the roll's capped total) but still says
    nothing about itself, so the payload drops it."""
    formula = {
        "max_total": 15,
        "alternatives": [
            {"label": "not capped, no delta", "extra_flat": 0, "max_total": 0},
        ],
    }
    assert _alts(formula, 20) == []


# ---------------------------------------------------------------------------
# The "10s not rerolled" note on the card
# ---------------------------------------------------------------------------


def test_no_reroll_note_explains_an_impaired_ten():
    formula = {"reroll_tens": False, "no_reroll_reason": "impaired"}
    cells = [{"parts": [10]}, {"parts": [4]}]
    assert roll_engine._no_reroll_note(formula, cells) == (
        "10s not rerolled due to being Impaired"
    )


def test_no_reroll_note_is_silent_without_a_ten():
    """Nothing was suppressed that the reader can see, so say nothing."""
    formula = {"reroll_tens": False, "no_reroll_reason": "impaired"}
    assert roll_engine._no_reroll_note(formula, [{"parts": [9]}]) == ""


def test_no_reroll_note_ignores_a_ten_that_did_reroll():
    """A 10 that exploded is a multi-part chain, not a stranded 10."""
    formula = {"reroll_tens": True, "no_reroll_reason": ""}
    assert roll_engine._no_reroll_note(formula, [{"parts": [10, 7]}]) == ""


@pytest.mark.parametrize("reason,expected", [
    ("impaired", "10s not rerolled due to being Impaired"),
    ("iaijutsu_strike", "10s not rerolled for the strike in an iaijutsu duel"),
    ("unskilled", "10s not rerolled due to Intimidation being 0"),
    ("something_new", ""),
])
def test_no_reroll_note_wording_per_reason(reason, expected):
    formula = {
        "reroll_tens": False, "no_reroll_reason": reason,
        "unskilled_skill_name": "Intimidation",
    }
    assert roll_engine._no_reroll_note(formula, [{"parts": [10]}]) == expected


def test_no_reroll_note_unskilled_without_a_name():
    formula = {"reroll_tens": False, "no_reroll_reason": "unskilled"}
    assert roll_engine._no_reroll_note(formula, [{"parts": [10]}]) == (
        "10s not rerolled due to that skill being 0"
    )


def test_execute_roll_puts_the_note_on_an_impaired_card():
    data = _character(skills={"etiquette": 2}, current_serious_wounds=99)
    payload = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([10, 3, 4, 5, 6]),
    )
    assert payload["extras"] == ["10s not rerolled due to being Impaired"]
    # The stranded 10 is on the card, unexploded, next to the explanation.
    assert {"parts": [10]} in payload["kept"] + payload["dropped"]


def test_execute_roll_leaves_extras_empty_for_a_healthy_roll():
    data = _character(skills={"etiquette": 2})
    payload = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([10, 2, 3, 4, 5, 6]),
    )
    assert payload["extras"] == []


# ---------------------------------------------------------------------------
# Void spends on a roll
# ---------------------------------------------------------------------------


def test_a_void_point_is_plus_one_k_one():
    data = _character(skills={"etiquette": 2})
    plain = execute_roll(data, "skill:etiquette", rng=_ScriptedRandom([1] * 20))
    spent = execute_roll(
        data, "skill:etiquette", rng=_ScriptedRandom([1] * 20), void_spent=2,
    )
    assert len(spent["kept"]) == len(plain["kept"]) + 2
    assert (
        len(spent["kept"]) + len(spent["dropped"])
        == len(plain["kept"]) + len(plain["dropped"]) + 2
    )
    assert spent["extras"] == ["Rolled +2k2 from 2 spent void points"]
    # The subtitle shows the pool that was actually rolled, as the sheet does.
    assert spent["formula"].startswith(f"{len(spent['kept']) + len(spent['dropped'])}k")


def test_one_void_point_is_singular_on_the_card():
    payload = execute_roll(
        _character(skills={"etiquette": 1}), "skill:etiquette",
        rng=_ScriptedRandom([1] * 20), void_spent=1,
    )
    assert payload["extras"] == ["Rolled +1k1 from 1 spent void point"]


def test_void_dice_past_ten_k_ten_become_flat():
    formula = {"label": "Big", "rolled": 9, "kept": 9, "flat": 1, "reroll_tens": False}
    payload = execute_roll(
        {}, "x", rng=_ScriptedRandom([2] * 20), void_spent=3, formula=formula,
    )
    # 12k12 -> 10k10 with kept overflow: rolled 12 -> kept 14 -> +8.
    assert payload["formula"] == "10k10 + 9"
    assert payload["total"] == 20 + 9
    assert "+8 from rolling above 10k10 (+2 per extra die above 10)" in payload["extras"]


def test_a_passed_in_formula_is_not_mutated():
    formula = {"label": "F", "rolled": 3, "kept": 2, "flat": 0, "reroll_tens": False}
    execute_roll({}, "x", rng=_ScriptedRandom([2] * 9), void_spent=1, formula=formula)
    assert (formula["rolled"], formula["kept"]) == (3, 2)


def test_an_activation_cost_is_named_on_the_card():
    formula = {
        "label": "Commune (Water)", "rolled": 4, "kept": 2, "flat": 0,
        "reroll_tens": False, "requires_void_point": True,
    }
    payload = execute_roll(
        {}, "knack:commune", rng=_ScriptedRandom([3] * 9), void_spent=1,
        formula=formula,
    )
    assert payload["extras"] == [
        "1 void point spent to activate Commune (Water)",
        "Rolled +1k1 from 1 spent void point",
    ]


def test_a_capped_roll_says_so_on_the_card():
    """Same closing bullet the sheet adds when Withdrawn bites."""
    data = _character(skills={"etiquette": 4}, disadvantages=["withdrawn"])
    payload = execute_roll(data, "skill:etiquette", rng=_ScriptedRandom([9] * 20))
    assert payload["total"] == 15
    assert payload["extras"][-1].startswith("Capped at 15 by Withdrawn (rolled ")


def test_a_cap_with_no_named_source():
    formula = {
        "label": "F", "rolled": 2, "kept": 2, "flat": 0,
        "reroll_tens": False, "max_total": 5,
    }
    payload = execute_roll({}, "x", rng=_ScriptedRandom([9, 9]), formula=formula)
    assert payload["extras"] == ["Capped at 5 by a disadvantage (rolled 18)"]


def test_shosuro_5th_dan_adds_the_lowest_three_dice():
    """A front-end-only rule until the slash commands needed it: the sheet
    added these dice, the server's roller did not."""
    data = _character(
        school="shosuro_actor",
        knacks={"athletics": 5, "discern_honor": 5, "pontificate": 5},
    )
    formula = {"label": "F", "rolled": 5, "kept": 2, "flat": 0, "reroll_tens": False}
    payload = execute_roll(
        data, "x", rng=_ScriptedRandom([9, 1, 8, 2, 3]), formula=formula,
    )
    assert payload["kept_sum"] == 17
    assert payload["total"] == 17 + (1 + 2 + 3)
    assert payload["extras"] == ["+6 from 5th Dan (lowest 3 dice added to result)"]


def test_shosuro_below_5th_dan_adds_nothing():
    data = _character(
        school="shosuro_actor",
        knacks={"athletics": 4, "discern_honor": 5, "pontificate": 5},
    )
    formula = {"label": "F", "rolled": 3, "kept": 1, "flat": 0, "reroll_tens": False}
    payload = execute_roll(data, "x", rng=_ScriptedRandom([9, 1, 8]), formula=formula)
    assert payload["total"] == 9
    assert payload["extras"] == []


# ---------------------------------------------------------------------------
# Initiative
# ---------------------------------------------------------------------------


import json as _json                                    # noqa: E402
from pathlib import Path as _Path                       # noqa: E402

from app.services.roll_engine import (                  # noqa: E402
    execute_initiative,
    initiative_action_values,
    initiative_sort_value,
)

_INITIATIVE_CASES = _json.loads(
    (_Path(__file__).parent / "shared" / "initiative_cases.json").read_text()
)


@pytest.mark.parametrize(
    "case", _INITIATIVE_CASES["sort_value"], ids=lambda c: c["name"])
def test_initiative_sort_value_matches_the_shared_table(case):
    assert initiative_sort_value(*case["args"]) == case["want"]


@pytest.mark.parametrize(
    "case", _INITIATIVE_CASES["action_values"], ids=lambda c: c["name"])
def test_initiative_action_values_match_the_shared_table(case):
    kept = list(case["kept"])
    assert initiative_action_values(kept, case["flags"]) == case["want"]
    assert kept == case["kept"]


def _school(school, rank, **overrides):
    from app.game_data import SCHOOLS

    return _character(
        school=school,
        knacks=dict.fromkeys(SCHOOLS[school].school_knacks, rank), **overrides,
    )


def test_initiative_keeps_the_lowest_dice_and_never_rerolls_tens():
    data = _character()                     # Void 2: roll 3, keep the lowest 2
    result = execute_initiative(data, rng=_ScriptedRandom([10, 3, 7]))
    assert result["action_dice"] == [{"value": 3}, {"value": 7}]
    payload = result["payload"]
    assert payload["title"] == "Initiative"
    assert payload["formula"] == "3k2"
    assert payload["kept"] == [{"parts": [3]}, {"parts": [7]}]
    assert payload["dropped"] == [{"parts": [10]}]     # a flat 10, not a chain
    assert payload["show_total"] is False
    assert payload["footer"] == "Action dice"
    assert payload["total"] == 0 and payload["bonuses"] == []


def test_kakita_keeps_a_ten_because_it_is_phase_zero():
    data = _school("kakita_duelist", 1)
    rolled = execute_initiative(data, rng=_ScriptedRandom([1] * 12))
    count = len(rolled["action_dice"]) + len(rolled["payload"]["dropped"])
    faces = [10] + [5] * (count - 1)
    result = execute_initiative(data, rng=_ScriptedRandom(faces))
    assert result["action_dice"][0] == {"value": 0}
    assert {"parts": [10]} not in result["payload"]["dropped"]


def test_hiruma_4th_dan_lowers_the_action_dice():
    data = _school("hiruma_scout", 4)
    result = execute_initiative(data, rng=_ScriptedRandom([2] * 12))
    assert {d["value"] for d in result["action_dice"]} == {1}


def test_shinjo_4th_dan_sets_the_highest_die_to_one():
    data = _school("shinjo_bushi", 4)
    result = execute_initiative(data, rng=_ScriptedRandom([6] * 12))
    values = [d["value"] for d in result["action_dice"]]
    assert values[0] == 1 and set(values[1:]) == {6}


def test_togashi_default_variant_rolls_one_extra_athletics_die():
    data = _school("togashi_ise_zumi", 1)
    result = execute_initiative(data, rng=_ScriptedRandom([4] * 12 + [9]))
    assert result["action_dice"][-1]["athletics_only"] is True
    assert all("athletics_only" not in d for d in result["action_dice"][:-1])
    # The extra die is on the card too: the KEPT row is the final action dice.
    assert len(result["payload"]["kept"]) == len(result["action_dice"])


def test_mantis_4th_dan_gets_a_value_one_die_that_is_never_rolled():
    data = _school("mantis_wave_treader", 4)
    base = execute_initiative(_school("mantis_wave_treader", 3),
                              rng=_ScriptedRandom([8] * 12))
    result = execute_initiative(data, rng=_ScriptedRandom([8] * 12))
    assert result["action_dice"][-1] == {
        "value": 1, "athletics_only": True, "mantis_4th_dan": True,
    }
    assert len(result["action_dice"]) == len(base["action_dice"]) + 1


def test_initiative_uses_a_real_rng_by_default():
    result = execute_initiative(_character())
    assert all(1 <= d["value"] <= 10 for d in result["action_dice"])


# ---------------------------------------------------------------------------
# Mirumoto 5th Dan: +10 per void point, on combat rolls only
# ---------------------------------------------------------------------------


def _mirumoto(rank=5):
    return _school("mirumoto_bushi", rank, skills={"sincerity": 2})


def test_mirumoto_5th_dan_void_adds_ten_on_a_combat_roll():
    data = _mirumoto()
    plain = execute_roll(data, "parry", rng=_ScriptedRandom([1] * 20), void_spent=0)
    spent = execute_roll(data, "parry", rng=_ScriptedRandom([1] * 20), void_spent=2)
    assert spent["total"] == plain["total"] + 2 + 20      # two more 1s kept, +10 each
    assert "+20 from 5th Dan (+10 per VP on combat rolls)" in spent["extras"]
    # Same bullet order as the sheet: the void dice, then the 5th Dan line.
    assert spent["extras"].index("Rolled +2k2 from 2 spent void points") < \
        spent["extras"].index("+20 from 5th Dan (+10 per VP on combat rolls)")


def test_mirumoto_5th_dan_void_adds_nothing_on_a_skill_roll():
    """The bug: the sheet's generic roller added +10 to a Sincerity roll."""
    data = _mirumoto()
    plain = execute_roll(data, "skill:sincerity", rng=_ScriptedRandom([1] * 20))
    spent = execute_roll(
        data, "skill:sincerity", rng=_ScriptedRandom([1] * 20), void_spent=1,
    )
    assert spent["total"] == plain["total"] + 1
    assert spent["extras"] == ["Rolled +1k1 from 1 spent void point"]


def test_mirumoto_4th_dan_gets_no_bonus_even_on_a_combat_roll():
    data = _mirumoto(rank=4)
    spent = execute_roll(data, "parry", rng=_ScriptedRandom([1] * 20), void_spent=1)
    assert not any("5th Dan" in e for e in spent["extras"])


def test_the_sheet_and_the_server_read_the_bonus_from_one_place():
    from app.services.void_spend import combat_vp_flat_bonus

    assert combat_vp_flat_bonus(_mirumoto()) == 10
    assert combat_vp_flat_bonus(_mirumoto(rank=4)) == 0
    assert combat_vp_flat_bonus(_character()) == 0
