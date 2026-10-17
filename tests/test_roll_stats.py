"""Roll statistics (probability-design/design.md): the distributions behind
the sheet's average badges and the statistics modal."""

import pytest

from app.data import prob, shosuro_lowest_3_avg
from app.models import Character, User
from app.services import roll_stats as rs
from app.services.dice import build_all_roll_formulas
from tests.conftest import make_character_data


def _mean(start, pmf):
    return sum((start + i) * p for i, p in enumerate(pmf))


def _formula(**kw):
    f = {"label": "Test (Fire)", "rolled": 5, "kept": 3, "flat": 0, "bonuses": [],
         "reroll_tens": True}
    f.update(kw)
    return f


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reroll", [True, False])
@pytest.mark.parametrize("rk", [(1, 1), (5, 3), (10, 10)])
def test_ordinary_roll_is_the_probability_table(rk, reroll):
    start, pmf, ability = rs.dice_distribution(rk[0], rk[1], reroll)
    assert sum(pmf) == pytest.approx(1.0)
    assert _mean(start, pmf) == pytest.approx(prob[reroll][rk], abs=0.02)
    assert set(ability) == {0.0}
    # Every kept die shows at least 1; the table's rarest totals (all ones on
    # ten dice) never came up in its simulation.
    assert start >= rk[1]


def test_no_dice_is_a_certain_zero():
    assert rs.dice_distribution(0, 0, True) == (0, [1.0], [0.0])
    assert rs.dice_distribution(3, 0, True) == (0, [1.0], [0.0])


def test_dice_beyond_ten_are_clamped():
    assert rs.dice_distribution(12, 12, True)[0] == rs.dice_distribution(10, 10, True)[0]


@pytest.mark.parametrize("reroll", [True, False])
def test_shosuro_cells_agree_with_the_existing_average_table(reroll):
    start, pmf, ability = rs.dice_distribution(6, 3, reroll, "shosuro")
    assert sum(pmf) == pytest.approx(1.0)
    bonus = sum(p * a for p, a in zip(pmf, ability))
    assert bonus == pytest.approx(shosuro_lowest_3_avg[reroll][6], abs=0.1)
    assert _mean(start, pmf) - bonus == pytest.approx(prob[reroll][6, 3], abs=0.2)


def test_hida_reroll_raises_the_average_and_says_by_how_much():
    start, pmf, ability = rs.dice_distribution(6, 3, True, "hida", 2)
    gain = sum(p * a for p, a in zip(pmf, ability))
    assert gain > 1
    assert _mean(start, pmf) - gain == pytest.approx(prob[True][6, 3], abs=0.2)
    # More rerolled dice, more gain.
    start4, pmf4, ab4 = rs.dice_distribution(6, 3, True, "hida", 4)
    assert sum(p * a for p, a in zip(pmf4, ab4)) > gain


@pytest.mark.parametrize("reroll", [True, False])
def test_merchant_reroll_never_lowers_the_average(reroll):
    start, pmf, ability = rs.dice_distribution(5, 3, reroll, "merchant")
    assert sum(p * a for p, a in zip(pmf, ability)) > 0
    assert _mean(start, pmf) > prob[reroll][5, 3]


def test_keep_better_is_the_max_of_two_rolls():
    assert rs.keep_better([0.5, 0.5]) == pytest.approx([0.25, 0.75])
    start, pmf, _ = rs.dice_distribution(4, 2, True)
    better = rs.keep_better(pmf)
    assert sum(better) == pytest.approx(1.0)
    assert _mean(start, better) > _mean(start, pmf)


def test_quantile():
    assert rs._quantile(10, [0.5, 0.5], 0.5) == 10
    assert rs._quantile(10, [0.5, 0.5], 0.9) == 11
    assert rs._quantile(3, [1.0], 0.1) == 3


# ---------------------------------------------------------------------------
# Which ability shapes a roll
# ---------------------------------------------------------------------------


def _data(school, knacks, **kw):
    return make_character_data(school=school, knacks=knacks, **kw)


SHOSURO5 = _data("shosuro_actor", {"athletics": 5, "discern_honor": 5, "pontificate": 5})
MERCHANT5 = _data("merchant", {"discern_honor": 5, "oppose_knowledge": 5, "worldliness": 5})
HIDA3 = _data("hida_bushi", {"counterattack": 3, "double_attack": 3, "iaijutsu": 3}, attack=3)


def test_ability_shosuro_and_merchant_shape_every_roll():
    assert rs._ability(SHOSURO5, _formula()) == ("shosuro", 0)
    assert rs._ability(MERCHANT5, _formula()) == ("merchant", 0)
    below = _data("shosuro_actor", {"athletics": 4, "discern_honor": 5, "pontificate": 5})
    assert rs._ability(below, _formula()) == (None, 0)


def test_ability_hida_counts_x_2x_and_halves_when_impaired():
    attack = _formula(is_attack_type=True, attack_variant="attack")
    counter = _formula(is_attack_type=True, attack_variant="counterattack")
    assert rs._ability(HIDA3, attack) == ("hida", 3)
    assert rs._ability(HIDA3, counter) == ("hida", 6)
    impaired = dict(HIDA3, current_serious_wounds=2)
    assert rs._ability(impaired, attack) == ("hida", 2)
    assert rs._ability(HIDA3, _formula()) == (None, 0)  # not an attack
    assert rs._ability(HIDA3, dict(attack, reroll_tens=False)) == (None, 0)
    assert rs._ability(dict(HIDA3, attack=0), attack) == (None, 0)
    # Past the table's counts: the next count up, or all ten dice.
    assert rs._ability(dict(HIDA3, attack=7), attack) == ("hida", 8)
    assert rs._ability(dict(HIDA3, attack=7), counter) == ("hida", 10)
    assert rs.level(dict(HIDA3, attack=7), counter, 0)["mean"] > 0


# ---------------------------------------------------------------------------
# One void level
# ---------------------------------------------------------------------------


def test_level_breakdown_sums_to_the_average():
    f = _formula(flat=7, bonuses=[{"label": "2nd Dan", "amount": 5},
                                   {"label": "Honor", "amount": 2}])
    view = rs.level(make_character_data(), f, 0)
    assert view["dice_label"] == "5k3"
    assert sum(p["value"] for p in view["parts"]) == pytest.approx(view["mean"], abs=0.15)
    assert [p["label"] for p in view["parts"]] == ["Dice", "2nd Dan", "Honor"]
    assert view["ability_label"] is None
    assert view["p10"] <= view["median"] <= view["p90"]


def test_level_bins_are_five_wide_and_sum_to_one():
    view = rs.level(make_character_data(), _formula(flat=3), 0)
    bins = view["bins"]
    assert all(b["lo"] % 5 == 0 and b["hi"] == b["lo"] + 4 for b in bins)
    assert sum(b["p"] for b in bins) == pytest.approx(1.0, abs=1e-3)
    assert bins[0]["at_least"] == pytest.approx(1.0)
    assert bins[0]["open_low"] and bins[-1]["open_high"]
    filled = next(b for b in bins if b["p"] > 0.1)
    assert filled["lo"] - 3 <= filled["dice"] <= filled["hi"] - 3 + 0.01


def test_level_with_void_adds_dice_and_mirumoto_bonus():
    mirumoto = _data("mirumoto_bushi", {"counterattack": 5, "double_attack": 5, "iaijutsu": 5})
    f = _formula(is_combat_roll=True)
    view = rs.level(mirumoto, f, 2)
    assert view["dice_label"] == "7k5"
    assert {"label": "5th Dan (+10 per void point)", "value": 20} in view["parts"]


def test_level_void_past_ten_k_ten_becomes_flat():
    # 13k12: three rolled dice past 10 become kept (15), five kept past 10 are +2 each.
    view = rs.level(make_character_data(), _formula(rolled=10, kept=9), 3)
    assert view["dice_label"] == "10k10"
    assert {"label": "extra dice above 10k10", "value": 10} in view["parts"]


def test_level_cap_folds_the_tail_into_the_cap():
    view = rs.level(make_character_data(), _formula(max_total=15), 0)
    assert view["bins"][-1]["lo"] == 15 and view["bins"][-1]["open_high"] is False
    assert view["median"] <= 15 and view["p90"] <= 15
    assert view["parts"][-1]["label"] == "Capped at 15"
    assert view["parts"][-1]["value"] < 0


def test_level_shape_changer_reports_its_part_per_bar():
    view = rs.level(SHOSURO5, _formula(), 0)
    assert view["ability_label"] == "5th Dan (lowest three dice)"
    assert view["parts"][1]["label"] == "5th Dan (lowest three dice)"
    assert all("ability" in b for b in view["bins"] if b["p"] > 0)


def test_level_keep_better_raises_the_average():
    plain = rs.level(make_character_data(), _formula(), 1)
    better = rs.level(make_character_data(), _formula(), 1, better=True)
    assert better["mean"] > plain["mean"]


def test_void_max_and_the_reason_when_there_is_none():
    data = make_character_data()  # lowest ring 2
    assert rs.void_max(data, _formula()) == 2
    assert rs.void_reason(data, _formula()) == ""
    assert rs.void_max(data, _formula(requires_void_point=True)) == 1
    assert rs.void_max(data, _formula(void_blocked=True)) == 0
    assert rs.void_reason(data, _formula(void_blocked=True)).startswith("Discordant")
    assert rs.void_max(data, _formula(no_reroll_reason="iaijutsu_strike")) == 0
    assert "iaijutsu strike" in rs.void_reason(data, _formula(no_reroll_reason="iaijutsu_strike"))
    # A shugenja's cap is the lowest ring - 1: 1 here, all of it the activation.
    ishi = _data("isawa_ishi", {"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1})
    assert rs.void_max(ishi, _formula(requires_void_point=True)) == 0
    assert "activates" in rs.void_reason(ishi, _formula(requires_void_point=True))
    low = dict(ishi, rings={"Air": 1, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2})
    assert rs.void_reason(low, _formula()) == "Your per-roll void limit is 0."


def test_void_max_ignores_the_points_held_right_now():
    """The modal is about what the character CAN do (GM, 2026-10-17)."""
    broke = make_character_data(current_void_points=0, current_temp_void_points=0)
    assert rs.void_max(broke, _formula()) == 2


# ---------------------------------------------------------------------------
# Notes and assumptions
# ---------------------------------------------------------------------------


def test_notes_list_every_post_roll_bonus():
    f = _formula(adventure_raises_max_per_roll=2, courtier_5th_dan_optional=3,
                 doji_5th_dan_optional=True,
                 alternatives=[{"label": "relating to your business", "extra_flat": 5},
                               {"label": "capped", "extra_flat": 0}])
    data = make_character_data(foreign_knacks={"conviction": 2})
    assert rs.notes(data, f) == [
        "3rd Dan free raises after the roll: +5 each, up to 2 on this roll.",
        "Courtier 5th Dan: +3 when it applies.",
        "Doji 5th Dan: +1 for every 5 the TN exceeds 10.",
        "+5 relating to your business.",
        "Conviction: up to +2 after the roll.",
    ]
    assert rs.notes(make_character_data(), _formula()) == []


def test_assumptions():
    attack = _formula(is_attack_type=True, attack_variant="attack")
    assert "up to 3 of them" in rs.assumptions(HIDA3, attack)[0]
    merchant = rs.assumptions(MERCHANT5, _formula())
    assert "5 x (dice - 1)" in merchant[0] and "after seeing the roll" in merchant[1]
    assert rs.assumptions(SHOSURO5, _formula()) == []
    freed = rs.assumptions(make_character_data(),
                           _formula(wave_man_freed_dice=1, reroll_tens=False))
    assert "Wave Man" in freed[0]


# ---------------------------------------------------------------------------
# A whole character
# ---------------------------------------------------------------------------


def test_roll_stats_and_averages_for_a_real_character():
    data = make_character_data(skills={"etiquette": 2})
    formulas = build_all_roll_formulas(data)
    stats = rs.roll_stats(data, formulas, "attack")
    assert stats["key"] == "attack" and stats["void_max"] == 2
    assert [lv["void"] for lv in stats["levels"]] == [0, 1, 2]
    assert stats["levels"][1]["better"]["mean"] > stats["levels"][1]["normal"]["mean"]
    assert rs.roll_stats(data, formulas, "initiative") is None
    assert rs.roll_stats(data, formulas, "nonsense") is None

    avgs = rs.averages(data, formulas)
    assert "initiative" not in avgs and "skill:etiquette" in avgs
    assert avgs["attack"]["mean"] == stats["levels"][0]["normal"]["mean"]


ISHI3 = _data("isawa_ishi", {"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
              skills={"precepts": 4})


def test_isawa_ishi_3rd_dan_xk1_roll_has_statistics():
    formulas = build_all_roll_formulas(ISHI3)
    avgs = rs.averages(ISHI3, formulas)
    assert avgs[rs.XK1_KEY]["label"] == "Isawa Ishi 3rd Dan"
    stats = rs.roll_stats(ISHI3, formulas, rs.XK1_KEY)
    assert stats["void_max"] == 0 and "price" in stats["void_reason"]
    assert stats["levels"][0]["normal"]["dice_label"] == "4k1"
    assert stats["levels"][0]["normal"]["mean"] == pytest.approx(prob[True][4, 1], abs=0.1)
    ide = _data("ide_diplomat", {"double_attack": 3, "feint": 3, "worldliness": 3}, skills={"tact": 2})
    assert rs.averages(ide, build_all_roll_formulas(ide))[rs.XK1_KEY]["label"] == "Ide 3rd Dan"
    # No precepts, no roll; below 3rd Dan, no roll.
    assert rs.XK1_KEY not in rs.averages(dict(ISHI3, skills={}), formulas)
    assert rs.XK1_KEY not in rs.averages(make_character_data(), build_all_roll_formulas(make_character_data()))


# ---------------------------------------------------------------------------
# Routes and the setting
# ---------------------------------------------------------------------------


def _char(client, **kw):
    s = client._test_session_factory()
    data = dict(name="Stats", owner_discord_id="183026066498125825", is_published=True,
                is_hidden=False, school="akodo_bushi", school_ring_choice="Water",
                knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1}, skills={"etiquette": 2})
    data.update(kw)
    c = Character(**data)
    s.add(c)
    s.commit()
    cid = c.id
    s.close()
    return cid


def test_roll_stats_routes(client):
    cid = _char(client)
    r = client.get(f"/characters/{cid}/roll-stats?key=skill:etiquette")
    assert r.status_code == 200 and r.json()["levels"][0]["normal"]["mean"] > 0
    r = client.get(f"/characters/{cid}/roll-stats/averages")
    assert r.status_code == 200 and "attack" in r.json()["averages"]
    assert client.get(f"/characters/{cid}/roll-stats?key=initiative").status_code == 404
    assert client.get(f"/characters/{cid}/roll-stats").status_code == 404
    assert client.get("/characters/99999/roll-stats?key=attack").status_code == 404
    assert client.get("/characters/99999/roll-stats/averages").status_code == 404


def test_hidden_character_stats_are_for_its_editors_only(client):
    cid = _char(client, owner_discord_id="owner-1", is_hidden=True)
    s = client._test_session_factory()
    s.add(User(discord_id="owner-1", discord_name="o", display_name="o"))
    s.commit()
    s.close()
    stranger = {"X-Test-User": "stranger-9:Stranger"}
    assert client.get(f"/characters/{cid}/roll-stats?key=attack", headers=stranger).status_code == 404
    assert client.get(f"/characters/{cid}/roll-stats/averages", headers=stranger).status_code == 404
    owner = {"X-Test-User": "owner-1:Owner"}
    assert client.get(f"/characters/{cid}/roll-stats?key=attack", headers=owner).status_code == 200


def test_hidden_character_with_no_owner_row_is_still_hidden(client):
    cid = _char(client, owner_discord_id="ghost", is_hidden=True)
    stranger = {"X-Test-User": "stranger-9:Stranger"}
    assert client.get(f"/characters/{cid}/roll-stats/averages", headers=stranger).status_code == 404


def _gm_user(client):
    s = client._test_session_factory()
    s.add(User(discord_id="183026066498125825", discord_name="gm", display_name="GM"))
    s.commit()
    s.close()


def _prefs(client):
    s = client._test_session_factory()
    u = s.query(User).filter(User.discord_id == "183026066498125825").first()
    prefs = dict(u.preferences or {})
    s.close()
    return prefs


def test_the_setting_is_off_by_default_and_saved_from_the_profile(client):
    _gm_user(client)
    cid = _char(client)
    page = client.get(f"/characters/{cid}").text
    assert "data-roll-avg" not in page and "roll-stats-modal" not in page

    client.post("/profile", data={"display_name": "GM", "roll_stats": "on"})
    assert _prefs(client)["roll_stats_enabled"] is True
    page = client.get(f"/characters/{cid}").text
    assert 'data-roll-avg="skill:etiquette"' in page
    assert 'data-roll-avg="wound_check"' in page and 'data-roll-avg="ring:Fire"' in page
    # Averages are shown as whole numbers.
    import re
    shown = re.search(r'data-roll-avg="attack".*?>avg&nbsp;<span[^>]*>([^<]*)<', page, re.S).group(1)
    assert shown.isdigit()
    assert "roll-stats-modal" in page
    assert 'checked' in client.get("/profile").text.split('data-testid="roll-stats-pref"')[1][:200]

    client.post("/profile", data={"display_name": "GM"})
    assert _prefs(client)["roll_stats_enabled"] is False


# ---------------------------------------------------------------------------
# The generic /probabilities page
# ---------------------------------------------------------------------------


def test_generic_stats():
    g = rs.generic_stats(8, 3, True)
    assert g["label"] == "8k3" and g["reroll"] is True
    assert g["normal"]["mean"] == pytest.approx(prob[True][8, 3], abs=0.1)
    assert g["better"]["mean"] > g["normal"]["mean"]
    assert rs.generic_stats(8, 3, False)["normal"]["mean"] == pytest.approx(prob[False][8, 3], abs=0.1)
    for bad in [(0, 0), (3, 4), (11, 2), (2, 0)]:
        assert rs.generic_stats(*bad, True) is None


def test_chance_text():
    assert rs._chance_text(1.0, True) == "100%"
    assert rs._chance_text(0.996, True) == ">99%"
    assert rs._chance_text(0.5962, True) == "60%"
    assert rs._chance_text(0.0123, True) == "1%"
    assert rs._chance_text(0.003, True) == "0.3%"
    assert rs._chance_text(0.0004, True) == "<0.1%"
    # Rerolling 10s, nothing is impossible - only too rare for the table.
    assert rs._chance_text(0, True) == "<0.1%"
    assert rs._chance_text(0, False) == "0%"


def test_probability_tables():
    t = rs.probability_tables()
    assert t["tns"][0] == 5 and t["tns"][-1] == 100 and len(t["tns"]) == 20
    assert len(t["dice"]) == 55 and (3, 7) not in t["dice"]
    assert t["reroll"]["averages"]["1,1"] == round(prob[True][1, 1])
    # 1k1 reaches 10 one time in ten, with or without rerolling 10s.
    assert t["reroll"]["chances"]["1,1"][1]["text"] == "10%"
    assert t["no_reroll"]["chances"]["1,1"][2]["text"] == "0%"
    assert t["reroll"]["chances"]["1,1"][2]["text"] == "6%"


def test_probability_page_and_roll_route(client):
    page = client.get("/probabilities")
    assert page.status_code == 200
    assert 'data-dice="8k3"' in page.text and 'data-row="10k10"' in page.text
    assert 'data-dice="3k7"' not in page.text
    assert 'href="/profile#roll-statistics"' in page.text
    r = client.get("/probabilities/roll?rolled=8&kept=3&reroll=0")
    assert r.status_code == 200 and r.json()["reroll"] is False
    assert client.get("/probabilities/roll?rolled=3&kept=7").status_code == 400
    assert client.get("/probabilities/roll").status_code == 400


def test_probability_page_is_public(client):
    client.headers.pop("X-Test-User", None)
    assert client.get("/probabilities").status_code == 200
    assert client.get("/probabilities/roll?rolled=2&kept=2").status_code == 200
