"""Server-made rolls for the character sheet (app/services/roll_sessions.py,
POST /characters/{id}/roll; server-rolls-design Phase 1)."""

import random
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Character, RollHistory, RollSession, User
from app.services import roll_sessions as rs

GM = "183026066498125825"
PLAYER = {"X-Test-User": "test_user_1:player"}
OTHER = {"X-Test-User": "test_user_2:other"}


def _char(client, **kw):
    s = client._test_session_factory()
    data = dict(
        name="Roller", owner_discord_id="test_user_1", is_published=True, is_hidden=False,
        school="akodo_bushi", school_ring_choice="Water",
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        skills={"etiquette": 2}, current_void_points=2, ring_void=2,
    )
    data.update(kw)
    c = Character(**data)
    s.add(c)
    s.commit()
    cid = c.id
    s.close()
    return cid


def _get(client, cid):
    s = client._test_session_factory()
    c = s.get(Character, cid)
    s.expunge(c)
    s.close()
    return c


def _roll(client, cid, headers=PLAYER, **body):
    body.setdefault("roll_key", "skill:etiquette")
    return client.post(f"/characters/{cid}/roll", json=body, headers=headers)


@pytest.fixture(autouse=True)
def fresh_limits():
    rs._anon_hits.clear()
    yield
    rs._anon_hits.clear()


# ---------------------------------------------------------------------------
# Which rolls are made here (Phase 1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,expected", [
    ("skill:etiquette", True), ("knack:iaijutsu", True), ("ring:Fire", True),
    ("athletics:Water", True), ("initiative", True), ("initiative:athletics", True),
    ("initiative:other", False),
    ("parry", True), ("athletics:parry", True), ("athletics:attack", False),
    ("knack:feint", True), ("knack:feint:athletics", True), ("attack", False),
    ("wound_check", False), ("", False),
])
def test_server_rolled(key, expected):
    assert rs.server_rolled(key) is expected


def test_anonymous_limit_is_a_sliding_window():
    for i in range(rs.ANON_LIMIT):
        assert rs.anonymous_allowed("1.2.3.4", now=100.0 + i * 0.1)
    assert not rs.anonymous_allowed("1.2.3.4", now=107.0)
    assert rs.anonymous_allowed("5.6.7.8", now=107.0)
    assert rs.anonymous_allowed("1.2.3.4", now=100.0 + rs.ANON_WINDOW + 1)


# ---------------------------------------------------------------------------
# Live rolls
# ---------------------------------------------------------------------------

def test_owner_roll_spends_void_records_and_answers(client):
    cid = _char(client)
    resp = _roll(client, cid, void=1)
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "live"
    assert data["formula"]["void_spent"] == 1
    # every die the payload kept or dropped is in the roll-order list
    cells = sorted(sum(d["parts"]) for d in data["dice"])
    shown = sorted(sum(c["parts"]) for c in data["payload"]["kept"] + data["payload"]["dropped"])
    assert cells == shown
    assert data["tracking"]["current_void_points"] == 1
    c = _get(client, cid)
    assert c.current_void_points == 1 and data["tracking"]["rev"] == c.tracking_rev
    s = client._test_session_factory()
    row = s.get(RollHistory, data["history_id"])
    assert row.roll_key == "skill:etiquette" and row.is_owner_roll and row.actor_discord_id == "test_user_1"
    assert row.payload["skill_rank"] == 2 and row.payload["total"] == data["total"]
    session = s.get(RollSession, data["session_id"])
    assert session.mode == "live" and session.history_id == row.id and session.choices["void"] == 1
    s.close()


def test_admin_who_is_not_the_owner_rolls_live_but_is_not_recorded(client):
    cid = _char(client)
    data = _roll(client, cid, headers={}, void=1).json()  # the default client is the GM
    assert data["mode"] == "live" and data["history_id"] is None
    assert _get(client, cid).current_void_points == 1


def test_character_level_editor_rolls_live(client):
    cid = _char(client, editor_discord_ids=["test_user_2"])
    data = _roll(client, cid, headers=OTHER).json()
    assert data["mode"] == "live"
    s = client._test_session_factory()
    assert s.get(RollHistory, data["history_id"]).is_owner_roll is False
    s.close()


# ---------------------------------------------------------------------------
# Simulate mode (Read-only Roll Mode)
# ---------------------------------------------------------------------------

def test_non_editor_simulates_and_nothing_changes(client):
    cid = _char(client)
    before = _get(client, cid)
    data = _roll(client, cid, headers=OTHER, void=1).json()
    assert data["mode"] == "simulate" and data["history_id"] is None
    assert data["formula"]["void_spent"] == 1  # the roll still shows the spend
    after = _get(client, cid)
    assert after.current_void_points == 2 and after.tracking_rev == before.tracking_rev
    assert data["tracking"]["current_void_points"] == 2


def test_simulate_still_checks_the_real_pools(client):
    cid = _char(client, current_void_points=0)
    assert _roll(client, cid, headers=OTHER, void=1).status_code == 400


def test_anonymous_visitors_roll_and_are_rate_limited(client):
    cid = _char(client)
    # No X-Test-User header: an anonymous visitor (the fixture's database
    # override is app-wide, so this client shares its connection).
    with TestClient(app) as anon:
        first = _roll(anon, cid, headers={})
        assert first.status_code == 200 and first.json()["mode"] == "simulate"
        for _ in range(rs.ANON_LIMIT):
            last = _roll(anon, cid, headers={})
        assert last.status_code == 429


def test_hidden_character_is_not_found(client):
    cid = _char(client, is_hidden=True)
    assert _roll(client, cid, headers=OTHER).status_code == 404
    assert client.post("/characters/99999/roll", json={}).status_code == 404


# ---------------------------------------------------------------------------
# Refusals (nothing rolled, nothing changed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,message", [
    ({"roll_key": "athletics:attack"}, "not rolled on the server"),
    ({"predeclared": True}, "only a parry"),
    ({"roll_key": "initiative", "void": 1}, "without spending void"),
    ({"roll_key": "initiative:athletics"}, "has no initiative:athletics roll"),
    ({"roll_key": "skill:underworld_nonsense"}, "has no skill:underworld_nonsense roll"),
    ({"roll_key": "knack:lunge"}, "has no knack:lunge roll"),
    ({"void": 5}, "at most"),
    ({"void": "x"}, "whole number"),
    ({"void": -1}, "negative"),
    ({"kitsune_swap": True}, "Kitsune"),
    ({"otherworldliness": 1}, "otherworldliness"),
])
def test_refusals(client, body, message):
    cid = _char(client)
    resp = _roll(client, cid, **body)
    assert resp.status_code == 400 and message in resp.json()["error"]
    c = _get(client, cid)
    assert c.current_void_points == 2
    s = client._test_session_factory()
    assert s.query(RollHistory).count() == 0 and s.query(RollSession).count() == 0
    s.close()


def test_body_must_be_an_object(client):
    cid = _char(client)
    assert client.post(f"/characters/{cid}/roll", json=[1], headers=PLAYER).status_code == 400


def test_discordant_cannot_spend_void(client):
    cid = _char(client, disadvantages=["discordant"])
    resp = _roll(client, cid, void=1)
    assert resp.status_code == 400 and "cannot spend void" in resp.json()["error"]


# ---------------------------------------------------------------------------
# Otherworldliness, Kitsune swap, activation cost
# ---------------------------------------------------------------------------

def _monk(client, **kw):
    return _char(client, school="brotherhood_of_shinsei_monk", school_ring_choice="Water",
                 knacks={"conviction": 2, "otherworldliness": 2, "worldliness": 2}, skills={}, **kw)


def test_otherworldliness_on_an_unskilled_roll_grants_the_reroll(client):
    cid = _monk(client)
    data = _roll(client, cid, roll_key="skill:etiquette", otherworldliness=2).json()
    f = data["formula"]
    assert f["ow_spent"] == 2 and f["reroll_tens"] is True and f["no_reroll_reason"] == ""
    assert _get(client, cid).adventure_state["otherworldliness_used"] == 2


def test_otherworldliness_while_impaired_keeps_the_suppression(client):
    cid = _monk(client, current_serious_wounds=5)
    f = _roll(client, cid, roll_key="skill:etiquette", otherworldliness=1).json()["formula"]
    assert f["no_reroll_reason"] == "impaired"


def test_otherworldliness_limits(client):
    cid = _monk(client, adventure_state={"otherworldliness_used": 4})
    resp = _roll(client, cid, roll_key="skill:etiquette", otherworldliness=1)
    assert resp.status_code == 400 and "left" in resp.json()["error"]
    cid2 = _monk(client)
    resp = _roll(client, cid2, roll_key="skill:etiquette", otherworldliness=6)
    assert resp.status_code == 400 and "at most" in resp.json()["error"]


def test_otherworldliness_dice_are_capped_without_void(client, monkeypatch):
    cid = _monk(client)
    real = rs.build_all_roll_formulas

    def big(*a, **k):
        f = real(*a, **k)
        f["skill:etiquette"] = dict(f["skill:etiquette"], rolled=9, kept=9, otherworldliness_capacity=5)
        return f
    monkeypatch.setattr(rs, "build_all_roll_formulas", big)
    f = _roll(client, cid, roll_key="skill:etiquette", otherworldliness=3).json()["formula"]
    # 12 rolled -> 10 rolled + 11 kept -> 10 kept, +2 for the one past 10
    assert (f["rolled"], f["kept"]) == (10, 10) and f["void_overflow_bonus"] == 2


def test_kitsune_swap(client):
    cid = _char(client, school="kitsune_warden", school_ring_choice="Water", ring_water=3,
                knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1}, skills={"bragging": 1})
    data = _roll(client, cid, roll_key="skill:bragging", kitsune_swap=True).json()
    assert data["formula"]["kitsune_swap_to_ring"] == "Water"


def test_commune_pays_its_activation_point(client):
    cid = _char(client, school="kitsune_warden", school_ring_choice="Water",
                knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1}, current_void_points=2)
    data = _roll(client, cid, roll_key="knack:commune").json()
    assert data["formula"]["void_activation_cost"] == 1
    assert _get(client, cid).current_void_points == 1
    broke = _char(client, school="kitsune_warden", school_ring_choice="Water",
                  knacks={"absorb_void": 1, "commune": 1, "iaijutsu": 1}, current_void_points=0)
    assert _roll(client, broke, roll_key="knack:commune").status_code == 400


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

def test_old_sessions_are_reaped(client, monkeypatch):
    cid = _char(client)
    first = _roll(client, cid).json()["session_id"]
    monkeypatch.setattr(rs, "_now", lambda: rs.datetime.now(rs.timezone.utc).replace(tzinfo=None)
                        + rs.SESSION_TTL + timedelta(hours=1))
    _roll(client, cid)
    s = client._test_session_factory()
    assert s.get(RollSession, first) is None and s.query(RollSession).count() == 1
    s.close()


def test_the_rng_is_injectable(client):
    cid = _char(client)
    s = client._test_session_factory()
    c = s.get(Character, cid)
    a = rs.start_roll(s, c, "skill:etiquette", {}, viewer="test_user_1", live=False,
                      record=False, is_owner_roll=False, rng=random.Random(3))
    b = rs.start_roll(s, c, "skill:etiquette", {}, viewer="test_user_1", live=False,
                      record=False, is_owner_roll=False, rng=random.Random(3))
    assert a["dice"] == b["dice"] and a["total"] == b["total"]
    s.close()


def test_the_sheet_treats_character_level_editors_as_editors(client):
    """server-rolls-design 5.6: the sheet's viewer_can_edit follows the same
    rule as the writes (a character-level editor is an editor)."""
    cid = _char(client, editor_discord_ids=["test_user_2"])
    page = client.get(f"/characters/{cid}", headers=OTHER)
    assert page.status_code == 200 and "read-only-roll-banner" not in page.text


def test_a_retried_request_gets_the_same_roll_and_pays_once(client):
    cid = _char(client)
    rid = "ab" * 16
    first = _roll(client, cid, void=1, request_id=rid).json()
    again = _roll(client, cid, void=1, request_id=rid).json()
    assert again["session_id"] == first["session_id"] == rid
    assert again["dice"] == first["dice"] and again["history_id"] == first["history_id"]
    assert _get(client, cid).current_void_points == 1
    s = client._test_session_factory()
    assert s.query(RollHistory).count() == 1
    s.close()


def test_request_id_is_validated_and_not_shared(client):
    cid = _char(client)
    other = _char(client, name="Other")
    assert _roll(client, cid, request_id="nope").status_code == 400
    rid = "cd" * 16
    _roll(client, cid, request_id=rid)
    resp = _roll(client, other, request_id=rid)
    assert resp.status_code == 400 and "already used" in resp.json()["error"]


# ---------------------------------------------------------------------------
# Bless, the 3rd Dan Xk1 roll, freeform
# ---------------------------------------------------------------------------

def test_a_priest_blesses_on_the_server(client):
    cid = _char(client, school="priest", school_ring_choice="Water",
                knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1})
    data = _roll(client, cid, roll_key="bless", ritual="research").json()
    assert data["formula"]["label"] == "Bless research" and len(data["dice"]) == 2
    s = client._test_session_factory()
    assert s.get(RollHistory, data["history_id"]).roll_key == "bless"
    s.close()


def test_bless_needs_the_ritual(client):
    cid = _char(client)
    resp = _roll(client, cid, roll_key="bless", ritual="topic")
    assert resp.status_code == 400 and "cannot perform" in resp.json()["error"]
    assert _roll(client, cid, roll_key="bless", ritual="dance").status_code == 400


def test_a_profession_character_blesses_only_what_they_learned(client):
    cid = _char(client, school="", profession="profession", knacks={},
                profession_abilities={"priest_conversation_blessing": 1})
    assert _roll(client, cid, roll_key="bless", ritual="topic").status_code == 200
    assert _roll(client, cid, roll_key="bless", ritual="research").status_code == 400


def test_the_ide_xk1_roll_spends_a_void_point_with_consequences(client):
    cid = _char(client, school="ide_diplomat", school_ring_choice="Water", ring_water=3,
                knacks={"double_attack": 5, "feint": 5, "worldliness": 5}, skills={"tact": 3},
                current_void_points=2, current_temp_void_points=0)
    data = _roll(client, cid, roll_key="spend_vp_xk1").json()
    assert len(data["dice"]) == 3 and data["formula"]["kept"] == 1
    c = _get(client, cid)
    assert c.current_void_points == 1
    assert c.current_temp_void_points == 1  # Ide 5th Dan: a temp point back for a regular one
    s = client._test_session_factory()
    assert s.get(RollHistory, data["history_id"]).roll_key == "spend_vp_xk1:ide_diplomat"
    s.close()


def test_the_xk1_roll_needs_the_technique_and_a_point(client):
    assert _roll(client, _char(client), roll_key="spend_vp_xk1").status_code == 400
    broke = _char(client, school="isawa_ishi", school_ring_choice="Void", ring_void=3,
                  knacks={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
                  skills={"precepts": 2}, current_void_points=0)
    assert _roll(client, broke, roll_key="spend_vp_xk1").status_code == 400
    no_x = _char(client, school="isawa_ishi", school_ring_choice="Void", ring_void=3,
                 knacks={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3})
    assert _roll(client, no_x, roll_key="spend_vp_xk1").status_code == 400


def test_freeform(client):
    cid = _char(client)
    data = _roll(client, cid, roll_key="freeform", rolled=4, kept=9, reroll_tens=False).json()
    assert (data["formula"]["rolled"], data["formula"]["kept"]) == (4, 4)
    assert data["formula"]["reroll_tens"] is False
    assert all(len(d["parts"]) == 1 for d in data["dice"])
    for bad in ({"rolled": 0, "kept": 1}, {"rolled": 31, "kept": 1}, {"rolled": "x", "kept": 1}):
        assert _roll(client, cid, roll_key="freeform", **bad).status_code == 400


def test_special_rolls_take_no_void(client):
    cid = _char(client)
    resp = _roll(client, cid, roll_key="freeform", rolled=2, kept=1, void=1)
    assert resp.status_code == 400 and "no void" in resp.json()["error"]


def test_xk1_is_only_ide_and_isawa_ishi():
    from app.services.special_rolls import xk1_ability
    akodo = {"school": "akodo_bushi", "knacks": {"double_attack": 3, "feint": 3, "iaijutsu": 3}}
    assert xk1_ability(akodo) is None
    ishi = {"school": "isawa_ishi", "knacks": {"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
            "skills": {"precepts": 4}}
    assert xk1_ability(ishi) == {"x": 4, "title": "Isawa Ishi 3rd Dan", "verb": "add"}


def test_the_test_dice_header_scripts_the_roll_only_under_test_auth(client, monkeypatch):
    cid = _char(client)
    monkeypatch.setenv("TEST_AUTH_BYPASS", "true")
    data = client.post(f"/characters/{cid}/roll", json={"roll_key": "skill:etiquette"},
                       headers={**PLAYER, "X-Test-Dice": "3,4"}).json()
    assert [d["value"] for d in data["dice"]] == [3, 4, 3, 4][:len(data["dice"])]
    monkeypatch.setenv("TEST_AUTH_BYPASS", "false")
    data = client.post(f"/characters/{cid}/roll", json={"roll_key": "freeform", "rolled": 30, "kept": 1},
                       headers={**PLAYER, "X-Test-Dice": "3"}).json()
    assert {d["value"] for d in data["dice"]} != {3}  # ignored outside the test server


def test_scripted_rng_parsing():
    assert rs.scripted_rng_from_header("x,1") is None
    assert rs.scripted_rng_from_header(" , ") is None
    rng = rs.scripted_rng_from_header("12,0")
    assert (rng.randint(1, 10), rng.randint(1, 10)) == (10, 1)  # clamped


# ---------------------------------------------------------------------------
# Post-roll actions (Phase 3)
# ---------------------------------------------------------------------------

def _act(client, cid, sid, action, headers=PLAYER, **args):
    return client.post(f"/characters/{cid}/roll/{sid}/act",
                       json={"action": action, "args": args}, headers=headers)


def _ikoma(client, **kw):
    # 3rd Dan Ikoma Bard: bragging raises, 2 per roll, 4 per adventure
    return _char(client, school="ikoma_bard", school_ring_choice="Water", ring_water=3,
                 knacks={"discern_honor": 3, "oppose_knowledge": 3, "oppose_social": 3},
                 skills={"bragging": 2}, **kw)


def test_raises_add_five_respect_the_caps_and_undo(client):
    cid = _ikoma(client)
    data = _roll(client, cid, roll_key="skill:bragging").json()
    base, sid = data["total"], data["session_id"]
    r1 = _act(client, cid, sid, "raise").json()
    assert r1["total"] == base + 5
    assert r1["tracking"]["adventure_state"]["adventure_raises_used"] == 1
    assert _act(client, cid, sid, "raise").json()["total"] == base + 10
    over = _act(client, cid, sid, "raise")
    assert over.status_code == 400 and "no more" in over.json()["error"]
    back = _act(client, cid, sid, "undo_raise").json()
    assert back["total"] == base + 5 and back["tracking"]["adventure_state"]["adventure_raises_used"] == 1
    s = client._test_session_factory()
    row = s.get(RollHistory, data["history_id"])
    assert row.payload["total"] == base + 5
    assert {"label": "3rd Dan free raise", "amount": 5, "post_roll": True} in row.payload["bonuses"]
    s.close()
    _act(client, cid, sid, "undo_raise")
    assert _act(client, cid, sid, "undo_raise").status_code == 400


def test_raises_need_the_pool(client):
    cid = _ikoma(client, adventure_state={"adventure_raises_used": 4})
    sid = _roll(client, cid, roll_key="skill:bragging").json()["session_id"]
    resp = _act(client, cid, sid, "raise")
    assert resp.status_code == 400 and "left" in resp.json()["error"]


def test_simulated_spends_count_against_the_pool_but_never_persist(client):
    cid = _ikoma(client, adventure_state={"adventure_raises_used": 3})
    sid = _roll(client, cid, roll_key="skill:bragging", headers=OTHER).json()["session_id"]
    assert _act(client, cid, sid, "raise", headers=OTHER).status_code == 200
    assert _act(client, cid, sid, "raise", headers=OTHER).status_code == 400  # 1 was left
    assert _get(client, cid).adventure_state["adventure_raises_used"] == 3


def test_conviction(client):
    cid = _char(client, school="brotherhood_of_shinsei_monk", school_ring_choice="Water", ring_water=3,
                knacks={"conviction": 2, "otherworldliness": 1, "worldliness": 1}, skills={"etiquette": 1})
    data = _roll(client, cid).json()
    sid = data["session_id"]
    assert _act(client, cid, sid, "conviction").json()["total"] == data["total"] + 1
    _act(client, cid, sid, "conviction")
    assert _act(client, cid, sid, "conviction").status_code == 400  # rank 2 per roll
    assert _get(client, cid).adventure_state["conviction_used"] == 2


def test_togashi_raises_only_on_athletics(client):
    cid = _char(client, school="togashi_ise_zumi", school_ring_choice="Void", ring_void=3,
                knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3}, skills={"precepts": 1, "etiquette": 1})
    sid = _roll(client, cid, roll_key="athletics:Fire").json()["session_id"]
    assert _act(client, cid, sid, "togashi_raise").status_code == 200
    assert _act(client, cid, sid, "togashi_raise").status_code == 400  # precepts 1 per roll
    assert _act(client, cid, sid, "undo_togashi_raise").status_code == 200
    other = _roll(client, cid).json()["session_id"]
    assert _act(client, cid, other, "togashi_raise").status_code == 400


def test_courtier_5th_toggles(client, monkeypatch):
    cid = _char(client)
    real = rs.build_all_roll_formulas

    def with_courtier(*a, **k):
        f = real(*a, **k)
        f["skill:etiquette"] = dict(f["skill:etiquette"], courtier_5th_dan_optional=7)
        return f
    monkeypatch.setattr(rs, "build_all_roll_formulas", with_courtier)
    data = _roll(client, cid).json()
    sid = data["session_id"]
    assert _act(client, cid, sid, "courtier_5th", on=True).json()["total"] == data["total"] + 7
    assert _act(client, cid, sid, "courtier_5th", on=True).json()["total"] == data["total"] + 7
    assert _act(client, cid, sid, "courtier_5th", on=False).json()["total"] == data["total"]
    monkeypatch.setattr(rs, "build_all_roll_formulas", real)
    plain = _roll(client, cid).json()["session_id"]
    resp = _act(client, cid, plain, "courtier_5th", on=True)
    assert resp.status_code == 400 and "Courtier" in resp.json()["error"]


def test_act_errors(client):
    cid = _char(client)
    sid = _roll(client, cid).json()["session_id"]
    assert _act(client, cid, sid, "juggle").status_code == 400
    assert _act(client, cid, "nope", "raise").status_code == 404
    assert _act(client, cid, sid, "raise", headers=OTHER).status_code == 404  # not their roll
    assert client.post(f"/characters/{cid}/roll/{sid}/act", json=[1], headers=PLAYER).status_code == 400
    assert _act(client, cid, sid, "raise").status_code == 400  # no raises on this roll


def test_a_raise_the_formula_allows_still_needs_a_pool(client, monkeypatch):
    cid = _char(client)
    real = rs.build_all_roll_formulas

    def raises(*a, **k):
        f = real(*a, **k)
        f["skill:etiquette"] = dict(f["skill:etiquette"], adventure_raises_max_per_roll=2)
        return f
    monkeypatch.setattr(rs, "build_all_roll_formulas", raises)
    sid = _roll(client, cid).json()["session_id"]
    resp = _act(client, cid, sid, "raise")
    assert resp.status_code == 400 and "left" in resp.json()["error"]


# ---------------------------------------------------------------------------
# Rerolls (Phase 4)
# ---------------------------------------------------------------------------

@pytest.fixture
def scripted(monkeypatch):
    """Dice named by the X-Test-Dice header (the clicktest seam)."""
    monkeypatch.setenv("TEST_AUTH_BYPASS", "true")

    def headers(values, base=PLAYER):
        return {**base, "X-Test-Dice": values}
    return headers


def _values(answer):
    return sorted(d["value"] for d in answer["dice"])


def _row(client, history_id):
    s = client._test_session_factory()
    payload = s.get(RollHistory, history_id).payload
    s.close()
    return payload


def _published(client, **kw):
    cid = _char(client, **kw)
    s = client._test_session_factory()
    c = s.get(Character, cid)
    c.published_state = c.to_dict()
    s.commit()
    s.close()
    return cid


def test_lucky_rerolls_keeps_the_higher_and_is_spent(client, scripted):
    cid = _char(client, advantages=["lucky"])
    first = _roll(client, cid, headers=scripted("2")).json()
    up = _act(client, cid, first["session_id"], "lucky_reroll", headers=scripted("9")).json()
    assert set(_values(up)) == {9} and up["total"] > first["total"]
    pair = up["payload"]["lucky"]
    assert pair["kept"] == "reroll" and pair["source"] == "lucky"
    assert pair["original"]["total"] == first["total"] and pair["reroll"]["total"] == up["total"]
    assert "Lucky reroll used" in up["payload"]["extras"]
    assert up["tracking"]["adventure_state"]["lucky_used"] is True
    row = _row(client, first["history_id"])
    assert row["total"] == up["total"] and row["lucky"]["kept"] == "reroll"
    # One reroll per roll, and Lucky once per adventure.
    again = _act(client, cid, first["session_id"], "lucky_reroll", headers=scripted("9"))
    assert again.status_code == 400 and "already been rerolled" in again.json()["error"]
    other = _roll(client, cid).json()["session_id"]
    assert "already been used" in _act(client, cid, other, "lucky_reroll").json()["error"]


def test_a_lower_reroll_leaves_the_original_standing(client, scripted):
    cid = _char(client, advantages=["lucky"])
    first = _roll(client, cid, headers=scripted("9")).json()
    down = _act(client, cid, first["session_id"], "lucky_reroll", headers=scripted("1")).json()
    assert set(_values(down)) == {9} and down["total"] == first["total"]
    assert down["payload"]["lucky"]["kept"] == "original"
    assert down["payload"]["lucky"]["reroll"]["total"] < first["total"]
    assert "Lucky reroll used" in down["payload"]["extras"]


def test_a_reroll_keeps_the_bonuses_already_taken(client, scripted):
    cid = _ikoma(client, advantages=["lucky"])
    first = _roll(client, cid, roll_key="skill:bragging", headers=scripted("2")).json()
    sid = first["session_id"]
    _act(client, cid, sid, "raise")
    up = _act(client, cid, sid, "lucky_reroll", headers=scripted("9")).json()
    kept_sum = up["payload"]["kept_sum"]
    assert up["total"] == first["total"] - first["payload"]["kept_sum"] + kept_sum + 5
    assert {"label": "3rd Dan free raise", "amount": 5, "post_roll": True} in up["payload"]["bonuses"]
    assert up["payload"]["lucky"]["original"]["total"] == first["total"] + 5


def test_lucky_needs_the_advantage_and_simulates_without_spending(client, scripted):
    plain = _char(client)
    sid = _roll(client, plain).json()["session_id"]
    assert "not Lucky" in _act(client, plain, sid, "lucky_reroll").json()["error"]
    cid = _char(client, advantages=["lucky"])
    sid = _roll(client, cid, headers=OTHER).json()["session_id"]
    assert _act(client, cid, sid, "lucky_reroll", headers=OTHER).status_code == 200
    assert not (_get(client, cid).adventure_state or {}).get("lucky_used")


def test_pcp_reroll_spends_a_point_and_shares_the_lock(client, scripted):
    cid = _published(client, advantages=["lucky"])
    first = _roll(client, cid, headers=scripted("2")).json()
    sid = first["session_id"]
    paid = _act(client, cid, sid, "pcp_reroll", headers=scripted("9")).json()
    assert paid["pcp"]["pcp_count"] == 1 and paid["pcp"]["use"] == "reroll"
    assert paid["payload"]["lucky"]["source"] == "pcp"
    assert "Player Character Point reroll used" in paid["payload"]["extras"]
    assert _get(client, cid).pcp_count == 1
    assert _act(client, cid, sid, "lucky_reroll").status_code == 400  # the shared lock


def test_pcp_needs_a_clean_published_character_and_simulation_is_free(client, scripted):
    draft = _char(client, is_published=False)
    sid = _roll(client, draft).json()["session_id"]
    resp = _act(client, draft, sid, "pcp_reroll")
    assert resp.status_code == 400 and "pending changes" in resp.json()["error"]
    assert _act(client, draft, sid, "pcp_reroll").status_code == 400  # nothing was locked
    assert not _get(client, draft).pcp_count
    cid = _char(client)
    sim = _roll(client, cid, headers=OTHER).json()["session_id"]
    answer = _act(client, cid, sim, "pcp_reroll", headers=OTHER).json()
    assert "pcp" not in answer and not _get(client, cid).pcp_count


def test_pcp_free_raise_once_per_roll(client):
    cid = _published(client)
    first = _roll(client, cid).json()
    sid = first["session_id"]
    raised = _act(client, cid, sid, "pcp_free_raise").json()
    assert raised["total"] == first["total"] + 5 and raised["pcp"]["use"] == "free_raise"
    assert {"label": "Player Character Point free raise", "amount": 5, "post_roll": True} \
        in raised["payload"]["bonuses"]
    assert _act(client, cid, sid, "pcp_free_raise").status_code == 400


def _impaired(client, **kw):
    kw.setdefault("current_serious_wounds", 2)  # Earth 2
    return _published(client, **kw)


def test_pcp_rerolls_an_impaired_rolls_tens(client, scripted):
    cid = _impaired(client)
    first = _roll(client, cid, headers=scripted("10,3")).json()
    assert first["formula"]["no_reroll_reason"] == "impaired"
    tens = sum(1 for d in first["dice"] if d["value"] == 10)
    done = _act(client, cid, first["session_id"], "pcp_reroll_tens", headers=scripted("4")).json()
    assert sum(1 for d in done["dice"] if d["parts"] == [10, 4]) == tens
    assert done["pcp"]["use"] == "reroll_tens"
    assert "Rerolled 10s while impaired by spending a Player Character Point" in done["payload"]["extras"]
    again = _act(client, cid, first["session_id"], "pcp_reroll_tens")
    assert again.status_code == 400 and "already" in again.json()["error"]


def test_only_an_impaired_rolls_standing_tens_reroll(client, scripted):
    healthy = _published(client)
    sid = _roll(client, healthy, headers=scripted("10")).json()["session_id"]
    assert "Impaired" in _act(client, healthy, sid, "pcp_reroll_tens").json()["error"]
    hurt = _impaired(client)
    sid = _roll(client, hurt, headers=scripted("3")).json()["session_id"]
    assert "no 10" in _act(client, hurt, sid, "pcp_reroll_tens").json()["error"]


def test_the_priest_ritual_rerolls_the_tens_for_self_and_party(client, scripted):
    from app.models import GamingGroup
    s = client._test_session_factory()
    g = GamingGroup(name="Ritual Group")
    s.add(g)
    s.commit()
    gid = g.id
    s.close()
    priest = _char(client, name="Brother", school="priest", school_ring_choice="Water",
                   knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1}, gaming_group_id=gid)
    ally = _impaired(client, gaming_group_id=gid)
    first = _roll(client, ally, headers=scripted("10,3")).json()
    sid = first["session_id"]
    assert "cannot perform" in _act(client, ally, sid, "priest_ritual", priest_id=ally).json()["error"]
    assert "character id" in _act(client, ally, sid, "priest_ritual", priest_id="x").json()["error"]
    done = _act(client, ally, sid, "priest_ritual", priest_id=priest, headers=scripted("6")).json()
    assert 10 not in _values(done) and done["payload"]["kept_sum"] >= first["payload"]["kept_sum"] - 20
    assert "Impaired 10s rerolled (Brother performed the ritual)" in done["payload"]["extras"]
    # A priest may bless themselves.
    own = _roll(client, priest, headers=scripted("10"), **{}).json()
    s = client._test_session_factory()
    c = s.get(Character, priest)
    c.current_serious_wounds = 2
    s.commit()
    s.close()
    own = _roll(client, priest, headers=scripted("10")).json()
    assert _act(client, priest, own["session_id"], "priest_ritual", priest_id=priest).status_code == 200


def _merchant(client, dan=1, **kw):
    kw.setdefault("current_void_points", 2)
    return _char(client, school="merchant", school_ring_choice="Water", ring_water=3,
                 knacks={"discern_honor": dan, "oppose_knowledge": dan, "worldliness": dan},
                 skills={"etiquette": 2, "commerce": 2}, **kw)


def test_the_business_reroll_costs_a_void_point(client, scripted):
    cid = _char(client, school="", profession="profession", knacks={}, current_void_points=1,
                profession_abilities={"merchant_void_reroll": 1}, advantages=["lucky"])
    first = _roll(client, cid, headers=scripted("2")).json()
    sid = first["session_id"]
    done = _act(client, cid, sid, "merchant_reroll", headers=scripted("9")).json()
    assert done["payload"]["lucky"]["source"] == "merchant"
    assert done["tracking"]["current_void_points"] == 0
    assert _act(client, cid, sid, "lucky_reroll").status_code == 400  # the shared lock
    broke = _roll(client, cid).json()["session_id"]
    resp = _act(client, cid, broke, "merchant_reroll")
    assert resp.status_code == 400 and _get(client, cid).current_void_points == 0
    plain = _char(client)
    sid = _roll(client, plain).json()["session_id"]
    assert "business" in _act(client, plain, sid, "merchant_reroll").json()["error"]


def test_a_simulated_business_reroll_checks_the_pool_net_of_the_roll(client):
    cid = _char(client, school="", profession="profession", knacks={}, current_void_points=1,
                profession_abilities={"merchant_void_reroll": 1})
    sid = _roll(client, cid, headers=OTHER, void=1).json()["session_id"]  # the only point
    assert _act(client, cid, sid, "merchant_reroll", headers=OTHER).status_code == 400
    sid = _roll(client, cid, headers=OTHER).json()["session_id"]
    assert _act(client, cid, sid, "merchant_reroll", headers=OTHER).status_code == 200
    assert _get(client, cid).current_void_points == 1


def test_merchant_5th_dan_rerolls_chosen_dice(client, scripted):
    cid = _merchant(client, dan=5)
    first = _roll(client, cid, roll_key="skill:commerce", headers=scripted("1,2,9")).json()
    sid = first["session_id"]
    assert "sum to at least 5" in _act(client, cid, sid, "merchant_5th", values=[1, 2]).json()["error"]
    assert "no 7" in _act(client, cid, sid, "merchant_5th", values=[7]).json()["error"]
    assert "at least one" in _act(client, cid, sid, "merchant_5th", values=[]).json()["error"]
    done = _act(client, cid, sid, "merchant_5th", values=[1], headers=scripted("8")).json()
    assert done["formula"]["merchant_5th_dan_used"] is True
    delta = done["formula"]["merchant_5th_dan_bonus"]
    assert done["total"] == first["total"] + delta
    assert f"{delta:+d} from Merchant 5th Dan reroll" in done["payload"]["extras"]
    assert "already" in _act(client, cid, sid, "merchant_5th", values=[2]).json()["error"]
    low = _merchant(client, dan=4)
    sid = _roll(client, low).json()["session_id"]
    assert "5th Dan" in _act(client, low, sid, "merchant_5th", values=[1]).json()["error"]


def test_merchant_spends_void_after_the_roll(client, scripted):
    cid = _merchant(client)
    first = _roll(client, cid, headers=scripted("5")).json()
    sid = first["session_id"]
    more = _act(client, cid, sid, "merchant_vp", headers=scripted("7")).json()
    assert len(more["dice"]) == len(first["dice"]) + 1
    assert more["formula"]["rolled"] == first["formula"]["rolled"] + 1
    assert more["formula"]["merchant_vp_spent"] == 1 and more["tracking"]["current_void_points"] == 1
    assert more["total"] == first["total"] + 7
    assert "1 void point spent after the roll (Merchant)" in more["payload"]["extras"]
    assert f"{more['formula']['rolled']}k" in more["payload"]["formula"]
    plain = _char(client)
    sid = _roll(client, plain).json()["session_id"]
    assert "after the roll" in _act(client, plain, sid, "merchant_vp").json()["error"]


def test_merchant_void_after_the_roll_obeys_the_cap_and_10k10(client, scripted, monkeypatch):
    cid = _merchant(client, current_void_points=5)
    sid = _roll(client, cid, void=2).json()["session_id"]  # cap is Void 2
    resp = _act(client, cid, sid, "merchant_vp")
    assert resp.status_code == 400 and "at most 2" in resp.json()["error"]
    sid = _roll(client, cid, roll_key="freeform", rolled=10, kept=10).json()["session_id"]
    capped = _act(client, cid, sid, "merchant_vp").json()
    # 11k11 is 10k12 is 10k10 + 4, as for any void point past 10k10.
    assert len(capped["dice"]) == 10 and capped["formula"]["flat"] == 4


def _togashi(client, **kw):
    return _char(client, school="togashi_ise_zumi", school_ring_choice="Void", ring_void=3,
                 knacks={"athletics": 4, "conviction": 4, "dragon_tattoo": 4},
                 skills={"precepts": 2, "etiquette": 1, "sincerity": 2}, **kw)


def test_togashi_4th_dan_takes_the_new_result_and_keeps_the_raises(client, scripted):
    cid = _togashi(client)
    first = _roll(client, cid, roll_key="athletics:Fire", headers=scripted("9")).json()
    sid = first["session_id"]
    _act(client, cid, sid, "togashi_raise")
    down = _act(client, cid, sid, "togashi_4th", headers=scripted("1")).json()
    assert set(_values(down)) == {1} and down["total"] == down["payload"]["kept_sum"] \
        + first["total"] - first["payload"]["kept_sum"] + 5
    assert down["payload"]["togashi_original_total"] == first["total"] + 5
    assert "Togashi reroll used" in down["payload"]["extras"]
    assert _act(client, cid, sid, "togashi_4th").status_code == 400  # once
    s = client._test_session_factory()
    assert s.query(RollHistory).filter(RollHistory.character_id == cid).count() == 1
    s.close()


def test_togashi_4th_dan_only_on_contested_rolls(client):
    cid = _togashi(client, advantages=["lucky"])
    sid = _roll(client, cid, roll_key="skill:etiquette").json()["session_id"]
    assert "cannot take" in _act(client, cid, sid, "togashi_4th").json()["error"]
    sid = _roll(client, cid, roll_key="skill:sincerity").json()["session_id"]
    _act(client, cid, sid, "lucky_reroll")
    assert _act(client, cid, sid, "togashi_4th").status_code == 400
    low = _char(client, school="togashi_ise_zumi", school_ring_choice="Void",
                knacks={"athletics": 3, "conviction": 3, "dragon_tattoo": 3})
    sid = _roll(client, low, roll_key="ring:Fire").json()["session_id"]
    assert "4th Dan" in _act(client, low, sid, "togashi_4th").json()["error"]


def test_anonymous_rerolls_are_rate_limited(client, monkeypatch):
    cid = _char(client, advantages=["lucky"])
    with TestClient(app) as anon:
        data = _roll(anon, cid, headers={}).json()
        url = f"/characters/{cid}/roll/{data['session_id']}/act"
        assert anon.post(url, json={"action": "lucky_reroll", "args": {}}).status_code == 200
        monkeypatch.setattr(rs, "anonymous_allowed", lambda *a, **k: False)
        resp = anon.post(url, json={"action": "lucky_reroll", "args": {}})
        assert resp.status_code == 429
        resp = anon.post(url, json={"action": "raise", "args": {}})
        assert resp.status_code == 400  # not a reroll: no limit, just no raises


# ---------------------------------------------------------------------------
# Initiative (Phase 5)
# ---------------------------------------------------------------------------

def test_initiative_starts_the_round_and_records(client, scripted):
    cid = _char(client, adventure_state={"kakita_5th_dan_used": True, "mantis_posture_phase": 2},
                action_dice=[{"value": 9, "spent": True}])
    data = _roll(client, cid, roll_key="initiative", headers=scripted("7,3,5")).json()
    assert data["formula"]["is_initiative"] and data["total"] == 0
    values = [d["value"] for d in data["action_dice"]]
    assert values == sorted(values) and len(values) == data["formula"]["kept"]
    c = _get(client, cid)
    assert [d["value"] for d in c.action_dice] == values and not any(d["spent"] for d in c.action_dice)
    assert "kakita_5th_dan_used" not in c.adventure_state and "mantis_posture_phase" not in c.adventure_state
    row = _row(client, data["history_id"])
    assert row["show_total"] is False and [k["parts"][0] for k in row["kept"]] == values
    assert data["tracking"]["action_dice"] == c.action_dice


def test_simulated_initiative_changes_nothing(client):
    cid = _char(client, action_dice=[{"value": 9, "spent": True}])
    data = _roll(client, cid, roll_key="initiative", headers=OTHER).json()
    assert data["mode"] == "simulate" and data["action_dice"] and data["history_id"] is None
    assert _get(client, cid).action_dice == [{"value": 9, "spent": True}]


def test_priest_5th_dan_gets_conviction_back(client):
    cid = _char(client, school="priest", school_ring_choice="Water",
                knacks={"conviction": 5, "otherworldliness": 5, "pontificate": 5},
                adventure_state={"conviction_used": 3})
    data = _roll(client, cid, roll_key="initiative").json()
    assert "Conviction pool refreshed for the new combat round" in data["notes"]
    assert _get(client, cid).adventure_state["conviction_used"] == 0


def test_togashi_initiative_variants(client, scripted):
    cid = _togashi(client)
    normal = _roll(client, cid, roll_key="initiative", headers=scripted("4")).json()
    extra = [d for d in normal["action_dice"] if d.get("athletics_only")]
    assert len(extra) == 1 and extra[0]["value"] == 4
    ath = _roll(client, cid, roll_key="initiative:athletics").json()
    assert ath["action_dice"] and all(d["athletics_only"] for d in ath["action_dice"])


def test_lucky_on_initiative_takes_the_reroll_and_restarts_the_round(client, scripted):
    cid = _char(client, advantages=["lucky"])
    first = _roll(client, cid, roll_key="initiative", headers=scripted("2")).json()
    sid = first["session_id"]
    s = client._test_session_factory()
    c = s.get(Character, cid)
    c.action_dice = [dict(d, spent=True) for d in c.action_dice]
    s.commit()
    s.close()
    worse = _act(client, cid, sid, "lucky_reroll", headers=scripted("9")).json()
    assert [d["value"] for d in worse["action_dice"]] == [9] * len(first["action_dice"])
    pair = worse["payload"]["lucky"]
    assert pair["kept"] == "reroll" and pair["original"]["show_total"] is False
    assert [d["value"] for d in pair["original"]["action_dice"]] == [2] * len(first["action_dice"])
    c = _get(client, cid)
    assert [d["value"] for d in c.action_dice] == [9] * len(first["action_dice"])
    assert not any(d["spent"] for d in c.action_dice)
    assert _row(client, first["history_id"])["lucky"]["kept"] == "reroll"


def test_a_simulated_initiative_reroll_leaves_the_round_alone(client):
    cid = _char(client, advantages=["lucky"], action_dice=[{"value": 9, "spent": True}])
    sid = _roll(client, cid, roll_key="initiative", headers=OTHER).json()["session_id"]
    assert _act(client, cid, sid, "lucky_reroll", headers=OTHER).json()["action_dice"]
    assert _get(client, cid).action_dice == [{"value": 9, "spent": True}]


def test_initiative_refuses_bonuses_and_partial_rerolls(client):
    cid = _merchant(client, dan=5, current_serious_wounds=2)
    sid = _roll(client, cid, roll_key="initiative").json()["session_id"]
    for action, args in (("raise", {}), ("conviction", {}), ("pcp_free_raise", {}),
                         ("pcp_reroll_tens", {}), ("merchant_5th", {"values": [1]}),
                         ("merchant_vp", {}), ("priest_ritual", {"priest_id": cid})):
        resp = _act(client, cid, sid, action, **args)
        assert resp.status_code == 400, action
        assert "initiative" in resp.json()["error"], action
    biz = _char(client, school="", profession="profession", knacks={},
                profession_abilities={"merchant_void_reroll": 1})
    sid = _roll(client, biz, roll_key="initiative").json()["session_id"]
    assert "initiative" in _act(client, biz, sid, "merchant_reroll").json()["error"]


# ---------------------------------------------------------------------------
# Parry and feint (Phase 6)
# ---------------------------------------------------------------------------

def _school(client, school, dan=1, ring="Water", **kw):
    from app.game_data import SCHOOLS
    knacks = dict({k: dan for k in SCHOOLS[school].school_knacks}, **kw.pop("knacks", {}))
    kw.setdefault("skills", {})
    kw.setdefault("attack", 2)
    return _char(client, school=school, school_ring_choice=ring, knacks=knacks, **kw)


def test_a_predeclared_parry_adds_five(client, scripted):
    cid = _school(client, "akodo_bushi")
    plain = _roll(client, cid, roll_key="parry", headers=scripted("5")).json()
    pre = _roll(client, cid, roll_key="parry", predeclared=True, headers=scripted("5")).json()
    assert pre["total"] == plain["total"] + 5
    assert {"label": "predeclared parry", "amount": 5} in pre["payload"]["bonuses"]


def test_mirumoto_parry_hooks_and_round_points(client):
    cid = _school(client, "mirumoto_bushi", dan=3, current_temp_void_points=0)
    init = _roll(client, cid, roll_key="initiative").json()
    assert "Mirumoto 3rd Dan points refreshed for the new combat round" in init["notes"]
    assert _get(client, cid).adventure_state["mirumoto_round_points"] == 4  # 2 x attack 2
    data = _roll(client, cid, roll_key="parry").json()
    assert "Gained 1 temp void point from the parry (Mirumoto)" in data["notes"]
    assert data["tracking"]["current_temp_void_points"] == 1
    sid = data["session_id"]
    up = _act(client, cid, sid, "mirumoto_point").json()
    assert up["total"] == data["total"] + 2
    assert up["tracking"]["adventure_state"]["mirumoto_round_points"] == 3
    back = _act(client, cid, sid, "undo_mirumoto_point").json()
    assert back["total"] == data["total"] and back["tracking"]["adventure_state"]["mirumoto_round_points"] == 4
    assert "undo" in _act(client, cid, sid, "undo_mirumoto_point").json()["error"]
    # An athletics parry gets neither the temp point nor the round points.
    ath = _roll(client, cid, roll_key="athletics:parry")
    if ath.status_code == 200:
        assert not ath.json()["notes"]
        assert _act(client, cid, ath.json()["session_id"], "mirumoto_point").status_code == 400


def test_mirumoto_points_run_out_and_simulate_counts_its_own(client):
    cid = _school(client, "mirumoto_bushi", dan=3, adventure_state={"mirumoto_round_points": 1})
    sid = _roll(client, cid, roll_key="parry", headers=OTHER).json()["session_id"]
    assert _act(client, cid, sid, "mirumoto_point", headers=OTHER).status_code == 200
    assert "left" in _act(client, cid, sid, "mirumoto_point", headers=OTHER).json()["error"]
    assert _get(client, cid).adventure_state["mirumoto_round_points"] == 1
    other = _school(client, "akodo_bushi")
    sid = _roll(client, other, roll_key="parry").json()["session_id"]
    assert _act(client, other, sid, "mirumoto_point").status_code == 400


def test_shinjo_3rd_dan_parry_lowers_the_unspent_dice(client):
    cid = _school(client, "shinjo_bushi", dan=3,
                  action_dice=[{"value": 5, "spent": True}, {"value": 7, "spent": False}])
    data = _roll(client, cid, roll_key="parry").json()
    assert "Unspent action dice lowered by 2 (Shinjo 3rd Dan)" in data["notes"]
    assert _get(client, cid).action_dice == [{"value": 5, "spent": True}, {"value": 5, "spent": False}]


def test_shinjo_phase_bonus_and_5th_dan_bank(client, scripted):
    cid = _school(client, "shinjo_bushi", dan=5)
    data = _roll(client, cid, roll_key="parry", headers=scripted("5")).json()
    sid = data["session_id"]
    held = _act(client, cid, sid, "shinjo_phase", phase=6, die_value=2).json()
    assert held["total"] == data["total"] + 8
    assert _act(client, cid, sid, "shinjo_phase", phase=1, die_value=2).json()["total"] == data["total"]
    assert "whole numbers" in _act(client, cid, sid, "shinjo_phase", phase="x").json()["error"]
    bank = _act(client, cid, sid, "shinjo_bank", opponent=data["total"] - 3).json()
    assert bank["banked"] == 3
    assert bank["tracking"]["adventure_state"]["banked_wc_excess"] == [3]
    assert "already" in _act(client, cid, sid, "shinjo_bank", opponent=0).json()["error"]
    none = _roll(client, cid, roll_key="parry").json()["session_id"]
    assert _act(client, cid, none, "shinjo_bank", opponent=999).json()["banked"] == 0
    assert "whole number" in _act(client, cid, _roll(client, cid, roll_key="parry").json()["session_id"],
                                  "shinjo_bank", opponent="x").json()["error"]
    other = _school(client, "akodo_bushi")
    osid = _roll(client, other, roll_key="parry").json()["session_id"]
    assert _act(client, other, osid, "shinjo_bank").status_code == 400
    assert _act(client, other, osid, "shinjo_phase", phase=3).status_code == 400


def test_hiruma_parry_banks_for_the_next_attack(client):
    cid = _school(client, "hiruma_scout", dan=3)
    _roll(client, cid, roll_key="parry")
    _roll(client, cid, roll_key="parry")
    assert _get(client, cid).adventure_state["hiruma_banked_attack_bonus"] == 8


def test_feint_hooks(client):
    ide = _school(client, "ide_diplomat", current_temp_void_points=0)
    data = _roll(client, ide, roll_key="knack:feint").json()
    assert data["tracking"]["current_temp_void_points"] == 1
    sid = data["session_id"]
    assert _act(client, ide, sid, "ide_bank").json()["tracking"]["adventure_state"]["ide_banked_tn_reduce"] == 10
    assert "already" in _act(client, ide, sid, "ide_bank").json()["error"]
    bay = _school(client, "bayushi_bushi", dan=4)
    _roll(client, bay, roll_key="knack:feint")
    assert _get(client, bay).adventure_state["bayushi_banked_feint_raise"] == 5
    akodo = _school(client, "akodo_bushi", current_temp_void_points=0)
    sid = _roll(client, akodo, roll_key="knack:feint").json()["session_id"]
    assert _act(client, akodo, sid, "akodo_feint", succeeded=True).json()["gained"] == 4
    assert _act(client, akodo, sid, "akodo_feint", succeeded=False).status_code == 400
    assert _get(client, akodo).current_temp_void_points == 4
    sid = _roll(client, akodo, roll_key="knack:feint").json()["session_id"]
    assert _act(client, akodo, sid, "akodo_feint").json()["gained"] == 1
    assert _act(client, ide, sid if False else _roll(client, ide, roll_key="knack:feint").json()["session_id"],
                "akodo_feint").status_code == 400
    psid = _roll(client, ide, roll_key="parry").json()["session_id"]
    assert _act(client, ide, psid, "ide_bank").status_code == 400


def test_simulated_feint_hooks_change_nothing(client):
    cid = _school(client, "akodo_bushi", current_temp_void_points=0)
    data = _roll(client, cid, roll_key="knack:feint", headers=OTHER).json()
    assert data["notes"] == []
    assert _act(client, cid, data["session_id"], "akodo_feint", headers=OTHER, succeeded=True).json()["gained"] == 4
    ide = _school(client, "ide_diplomat")
    sid = _roll(client, ide, roll_key="knack:feint", headers=OTHER).json()["session_id"]
    _act(client, ide, sid, "ide_bank", headers=OTHER)
    assert _get(client, cid).current_temp_void_points == 0
    assert not (_get(client, ide).adventure_state or {}).get("ide_banked_tn_reduce")


def test_akodo_4th_dan_void_raise_draws_and_refunds(client):
    cid = _school(client, "akodo_bushi", dan=4, current_void_points=1, current_temp_void_points=1)
    data = _roll(client, cid, roll_key="parry").json()
    sid = data["session_id"]
    one = _act(client, cid, sid, "akodo_vp").json()
    assert one["total"] == data["total"] + 5 and one["tracking"]["current_temp_void_points"] == 0
    two = _act(client, cid, sid, "akodo_vp").json()
    assert two["tracking"]["current_void_points"] == 0 and two["total"] == data["total"] + 10
    assert "void" in _act(client, cid, sid, "akodo_vp").json()["error"]
    back = _act(client, cid, sid, "undo_akodo_vp").json()
    assert back["tracking"]["current_void_points"] == 1
    back = _act(client, cid, sid, "undo_akodo_vp").json()
    assert back["tracking"]["current_temp_void_points"] == 1 and back["total"] == data["total"]
    assert "undo" in _act(client, cid, sid, "undo_akodo_vp").json()["error"]
    plain = _roll(client, cid).json()["session_id"]
    assert _act(client, cid, plain, "akodo_vp").status_code == 400


def test_akodo_4th_dan_raise_from_worldliness_and_in_simulation(client):
    cid = _school(client, "akodo_bushi", dan=4, current_void_points=0, current_temp_void_points=0,
                  foreign_knacks={"worldliness": 1})
    sid = _roll(client, cid, roll_key="parry").json()["session_id"]
    got = _act(client, cid, sid, "akodo_vp").json()
    assert got["tracking"]["adventure_state"]["worldliness_used"] == 1
    back = _act(client, cid, sid, "undo_akodo_vp").json()
    assert back["tracking"]["adventure_state"]["worldliness_used"] == 0
    sim = _school(client, "akodo_bushi", dan=4, current_void_points=1)
    sid = _roll(client, sim, roll_key="parry", headers=OTHER).json()["session_id"]
    assert _act(client, sim, sid, "akodo_vp", headers=OTHER).status_code == 200
    assert _act(client, sim, sid, "akodo_vp", headers=OTHER).status_code == 400
    assert _act(client, sim, sid, "undo_akodo_vp", headers=OTHER).status_code == 200
    assert _get(client, sim).current_void_points == 1


def test_shiba_and_bayushi_damage_rolls_are_recorded(client, scripted):
    shiba = _school(client, "shiba_bushi", dan=3)
    sid = _roll(client, shiba, roll_key="parry").json()["session_id"]
    dmg = _act(client, shiba, sid, "sub_damage", headers=scripted("6")).json()["sub_damage"]
    assert dmg["label"] == "Shiba 3rd Dan parry damage (4k1)" and dmg["total"] == 6
    row = _row(client, dmg["history_id"])
    assert row["total"] == 6 and row["title"].startswith("Shiba")
    assert "already" in _act(client, shiba, sid, "sub_damage").json()["error"]
    bay = _school(client, "bayushi_bushi", dan=3, current_void_points=2, ring_void=2)
    sid = _roll(client, bay, roll_key="knack:feint", void=1).json()["session_id"]
    dmg = _act(client, bay, sid, "sub_damage").json()["sub_damage"]
    assert dmg["label"] == "Bayushi 3rd Dan feint damage (3k2)" and dmg["kept"] == 2
    plain = _school(client, "akodo_bushi")
    sid = _roll(client, plain, roll_key="parry").json()["session_id"]
    assert "no damage" in _act(client, plain, sid, "sub_damage").json()["error"]
    sim = _roll(client, shiba, roll_key="parry", headers=OTHER).json()["session_id"]
    assert _act(client, shiba, sim, "sub_damage", headers=OTHER).json()["sub_damage"]["history_id"] is None


def test_mirumoto_points_op_and_reset(client):
    from app.services.tracking_ops import OpRefused, apply_op
    cid = _school(client, "mirumoto_bushi", dan=3)
    s = client._test_session_factory()
    c = s.get(Character, cid)
    apply_op(c, "mirumoto_points", {"reset": True})
    assert c.adventure_state["mirumoto_round_points"] == 4
    apply_op(c, "mirumoto_points", {"delta": -1})
    apply_op(c, "mirumoto_points", {"delta": 1})
    apply_op(c, "mirumoto_points", {"delta": 1})
    assert c.adventure_state["mirumoto_round_points"] == 4
    apply_op(c, "reset_adventure", {})
    assert "mirumoto_round_points" not in c.adventure_state
    other = s.get(Character, _school(client, "akodo_bushi"))
    with pytest.raises(OpRefused):
        apply_op(other, "mirumoto_points", {"delta": 1})
    s.close()


def test_the_schema_bounds_mirumoto_points():
    from app.services.adventure_state import sanitize_adventure_state
    c = Character(name="M", school="mirumoto_bushi", school_ring_choice="Void",
                  knacks={"counterattack": 3, "double_attack": 3, "iaijutsu": 3}, attack=2)
    assert sanitize_adventure_state(c, {"mirumoto_round_points": 99}) == {"mirumoto_round_points": 4}
