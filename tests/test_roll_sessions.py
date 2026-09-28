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
    ("athletics:Water", True), ("initiative", False), ("initiative:athletics", False),
    ("parry", False), ("athletics:parry", False), ("athletics:attack", False),
    ("knack:feint", False), ("knack:feint:athletics", False), ("attack", False),
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
    ({"roll_key": "initiative"}, "not rolled on the server"),
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
