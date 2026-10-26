"""Night's Rest records (``RestEvent``): the sheet's button and the GM's Rest
page both record one, the Roll History lists them among the rolls, and the
Rest page shows the last ``REST_RECENT_DAYS`` days of them."""

import json
import re
from datetime import datetime, timedelta, timezone

from app.models import Character, GamingGroup, RestEvent, RollHistory
from app.routes.pages import REST_RECENT_DAYS

GM = "183026066498125825"
PLAYER = "test_user_1"
PLAYER_HDR = {"X-Test-User": f"{PLAYER}:Player One"}
NONADMIN = {"X-Test-User": "test_user_2:NotGm"}


def _session(client):
    return client._test_session_factory()


def _seed(client, **kw):
    s = _session(client)
    defaults = dict(
        name="Rester", school="akodo_bushi", school_ring_choice="Water",
        ring_water=3, knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id=PLAYER, is_published=True,
        published_state={"name": kw.get("name", "Rester")},
        current_light_wounds=0, current_serious_wounds=0, current_void_points=2,
    )
    defaults.update(kw)
    c = Character(**defaults)
    s.add(c)
    s.commit()
    return c.id


def _group(client, name="Rest Group"):
    s = _session(client)
    g = GamingGroup(name=name)
    s.add(g)
    s.commit()
    return g.id


def _rests(client, char_id):
    return (_session(client).query(RestEvent)
            .filter(RestEvent.character_id == char_id)
            .order_by(RestEvent.id).all())


def _page_json(text, script_id):
    m = re.search(r'id="%s">(.*?)</script>' % script_id, text, re.S)
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# The sheet's button records a rest
# ---------------------------------------------------------------------------


def test_owner_rest_is_recorded_with_before_and_after(client):
    cid = _seed(client, current_light_wounds=4, current_serious_wounds=2,
                current_void_points=0, sw_healing_received_new_since_rest=True,
                sw_healing_became_injured_since_rest=True)
    resp = client.post(f"/characters/{cid}/nights-rest", json={},
                       headers=PLAYER_HDR)
    assert resp.status_code == 200
    [rest] = _rests(client, cid)
    assert rest.actor_discord_id == PLAYER
    assert rest.is_owner_action is True
    assert rest.accelerate is False
    assert rest.summary["lw_before"] == 4
    assert rest.summary["sw_before"] == 2
    assert rest.summary["sw_healed"] == 1
    assert rest.summary["sw_remaining"] == 1
    assert rest.summary["vp_before"] == 0
    assert rest.summary["vp_after"] == 1


def test_a_rest_that_restores_nothing_is_still_recorded(client):
    """The point is counting nights, not only the ones that healed."""
    cid = _seed(client)
    client.post(f"/characters/{cid}/nights-rest", json={}, headers=PLAYER_HDR)
    client.post(f"/characters/{cid}/nights-rest", json={}, headers=PLAYER_HDR)
    assert len(_rests(client, cid)) == 2


def test_gm_rest_from_the_sheet_is_recorded_even_though_gm_rolls_are_not(client):
    cid = _seed(client)
    client.post(f"/characters/{cid}/nights-rest",
                json={"accelerate_cadence": True})
    [rest] = _rests(client, cid)
    assert rest.actor_discord_id == GM
    assert rest.is_owner_action is False
    assert rest.accelerate is True


def test_refused_rest_records_nothing(client):
    cid = _seed(client)
    resp = client.post(f"/characters/{cid}/nights-rest", json={},
                       headers=NONADMIN)
    assert resp.status_code == 403
    assert _rests(client, cid) == []


def test_a_rest_never_becomes_a_roll_history_row(client):
    """/api/rolls, the dice card and the statistics read roll_history."""
    cid = _seed(client)
    client.post(f"/characters/{cid}/nights-rest", json={}, headers=PLAYER_HDR)
    assert _session(client).query(RollHistory).filter(
        RollHistory.character_id == cid).count() == 0


# ---------------------------------------------------------------------------
# Roll History lists them
# ---------------------------------------------------------------------------


def test_roll_history_page_lists_rests_between_rolls_by_time(client):
    cid = _seed(client)
    s = _session(client)
    t0 = datetime(2026, 10, 19, 23, 0, 0)
    s.add(RollHistory(character_id=cid, roll_key="skill:etiquette",
                      actor_discord_id=PLAYER, is_owner_roll=True,
                      payload={"title": "Etiquette", "total": 20},
                      created_at=t0))
    s.add(RollHistory(character_id=cid, roll_key="skill:etiquette",
                      actor_discord_id=PLAYER, is_owner_roll=True,
                      payload={"title": "Etiquette", "total": 25},
                      created_at=t0 + timedelta(hours=2)))
    s.add(RestEvent(character_id=cid, actor_discord_id=GM,
                    is_owner_action=False, summary={"sw_healed": 1},
                    created_at=t0 + timedelta(hours=1)))
    s.commit()
    resp = client.get(f"/characters/{cid}/roll-history", headers=PLAYER_HDR)
    assert resp.status_code == 200
    items = _page_json(resp.text, "rolls-data")
    assert [i["kind"] for i in items] == ["roll", "rest", "roll"]
    rest = items[1]
    assert rest["key"].startswith("rest-")
    assert rest["summary"] == {"sw_healed": 1}
    assert rest["is_owner_roll"] is False
    assert rest["actor_name"]  # resolved like a roll's actor
    assert rest["created_at"].endswith("Z")
    assert len({i["key"] for i in items}) == 3


# ---------------------------------------------------------------------------
# The GM's Rest page
# ---------------------------------------------------------------------------


def test_rest_page_requires_admin(client):
    gid = _group(client)
    assert client.get(f"/groups/{gid}/rest", headers=NONADMIN).status_code == 403


def test_rest_page_404_when_group_missing(client):
    assert client.get("/groups/99999/rest").status_code == 404


def test_rest_page_empty_group(client):
    gid = _group(client)
    _seed(client, gaming_group_id=gid, is_hidden=True, name="Hidden")
    resp = client.get(f"/groups/{gid}/rest")
    assert resp.status_code == 200
    assert "No visible characters" in resp.text
    assert "Hidden" not in resp.text


def test_rest_page_shows_recent_rests_and_what_a_rest_would_restore(client):
    gid = _group(client)
    rested = _seed(client, gaming_group_id=gid, name="Rested")
    tired = _seed(client, gaming_group_id=gid, name="Tired",
                  current_light_wounds=3)
    s = _session(client)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    s.add(RestEvent(character_id=rested, actor_discord_id=PLAYER,
                    is_owner_action=True, summary={"sw_healed": 1},
                    created_at=now - timedelta(days=1)))
    # Too old to count as recent.
    s.add(RestEvent(character_id=tired, actor_discord_id=PLAYER,
                    is_owner_action=True, summary={},
                    created_at=now - timedelta(days=REST_RECENT_DAYS, hours=1)))
    s.commit()
    resp = client.get(f"/groups/{gid}/rest")
    assert resp.status_code == 200
    m = re.search(r"x-data='groupRest\(\d+, (.*?)\)'", resp.text, re.S)
    cards = {c["name"]: c for c in json.loads(m.group(1))}
    assert [r["sw_healed"] for r in cards["Rested"]["rests"]] == [1]
    assert cards["Rested"]["rests"][0]["by_owner"] is True
    assert cards["Rested"]["would_restore"] == []
    assert cards["Tired"]["rests"] == []
    assert cards["Tired"]["would_restore"] == ["Heal 3 light wounds"]


def test_group_summary_links_the_rest_page_for_the_gm_only(client):
    gid = _group(client)
    _seed(client, gaming_group_id=gid)
    assert f'href="/groups/{gid}/rest"' in client.get(f"/groups/{gid}").text
    resp = client.get(f"/groups/{gid}", headers=NONADMIN)
    assert f'href="/groups/{gid}/rest"' not in resp.text


# ---- apply ----


def test_apply_anonymous_401(client):
    gid = _group(client)
    resp = client.post(f"/groups/{gid}/rest/apply", json={},
                       headers={"X-Test-User": ""})
    assert resp.status_code == 401


def test_apply_non_admin_403(client):
    gid = _group(client)
    cid = _seed(client, gaming_group_id=gid)
    resp = client.post(f"/groups/{gid}/rest/apply", json={}, headers=NONADMIN)
    assert resp.status_code == 403
    assert _rests(client, cid) == []


def test_apply_group_missing_404(client):
    assert client.post("/groups/99999/rest/apply", json={}).status_code == 404


def test_apply_invalid_json_400(client):
    gid = _group(client)
    resp = client.post(f"/groups/{gid}/rest/apply", content=b"{nope",
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_apply_non_dict_400(client):
    gid = _group(client)
    assert client.post(f"/groups/{gid}/rest/apply", json=[1]).status_code == 400


def test_apply_bad_char_id_400(client):
    gid = _group(client)
    for bad in ("3", True, 1.5):
        resp = client.post(f"/groups/{gid}/rest/apply", json={"char_id": bad})
        assert resp.status_code == 400


def test_apply_char_not_in_group_404(client):
    gid = _group(client)
    other = _seed(client)  # no group
    hidden = _seed(client, gaming_group_id=gid, is_hidden=True)
    for cid in (other, hidden):
        resp = client.post(f"/groups/{gid}/rest/apply", json={"char_id": cid})
        assert resp.status_code == 404
        assert _rests(client, cid) == []


def test_apply_to_everyone_rests_every_visible_character(client):
    gid = _group(client)
    a = _seed(client, gaming_group_id=gid, name="A", current_light_wounds=5)
    b = _seed(client, gaming_group_id=gid, name="B")
    hidden = _seed(client, gaming_group_id=gid, name="H", is_hidden=True)
    resp = client.post(f"/groups/{gid}/rest/apply", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["rested"]) == sorted([a, b])
    for cid in (a, b):
        [rest] = _rests(client, cid)
        assert rest.actor_discord_id == GM
        assert rest.is_owner_action is False
    assert _rests(client, hidden) == []
    cards = {c["id"]: c for c in body["cards"]}
    assert len(cards[a]["rests"]) == 1
    assert cards[a]["would_restore"] == []
    c = _session(client).query(Character).filter(Character.id == a).first()
    assert c.current_light_wounds == 0


def test_apply_to_one_rests_only_that_one(client):
    gid = _group(client)
    a = _seed(client, gaming_group_id=gid, name="A")
    b = _seed(client, gaming_group_id=gid, name="B")
    resp = client.post(f"/groups/{gid}/rest/apply", json={"char_id": b})
    assert resp.status_code == 200
    assert resp.json()["rested"] == [b]
    assert _rests(client, a) == []
    assert len(_rests(client, b)) == 1
    # Every card comes back, so the page can redraw the whole list.
    assert {c["id"] for c in resp.json()["cards"]} == {a, b}
