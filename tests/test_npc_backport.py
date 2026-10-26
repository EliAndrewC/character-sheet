"""Writing a built NPC's stats back to Obsidian Portal (app/services/npc_backport.py, issue #4)."""

import asyncio
import json
import pathlib
from types import SimpleNamespace

import httpx
import pytest

from app.models import Character, GamingGroup
from app.services import npc_backport

FIXTURES = json.loads((pathlib.Path(__file__).parent / "fixtures" / "npc_numbers_responses.json").read_text())


def _npc(**extra):
    fields = dict(
        id=41, name="Bayushi no Daika Koharu",
        ring_air=4, ring_earth=3, ring_fire=2, ring_water=3, ring_void=3, attack=2, parry=3,
        skills={"sincerity": 1, "tact": 2, "heraldry": 0}, knacks={"double_attack": 1},
        foreign_knacks=None, profession_abilities={"wave_man_1": 2},
    )
    fields.update(extra)
    return SimpleNamespace(**fields)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GM_ASSISTANT_URL", "https://gm.example/")
    monkeypatch.setenv("GM_ASSISTANT_NAMES_TOKEN", "tok")


@pytest.fixture(autouse=True)
def unconfigured(monkeypatch):
    monkeypatch.delenv("GM_ASSISTANT_URL", raising=False)
    monkeypatch.delenv("GM_ASSISTANT_NAMES_TOKEN", raising=False)


def _answer(monkeypatch, handler):
    """Route every gm-assistant call to ``handler``; returns the requests seen."""
    seen = []
    real = httpx.AsyncClient

    def record(request):
        seen.append(request)
        return handler(request)
    monkeypatch.setattr(npc_backport.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(record), **kw))
    return seen


def test_stats_are_rings_attack_parry_and_every_rank_of_one_or_more():
    assert npc_backport.npc_stats(_npc()) == {
        "Air": 4, "Earth": 3, "Fire": 2, "Water": 3, "Void": 3, "attack": 2, "parry": 3,
        "sincerity": 1, "tact": 2, "double_attack": 1,
    }
    assert npc_backport.npc_stats(_npc(foreign_knacks={"lunge": 2}))["lunge"] == 2


def test_the_request_carries_the_token_name_stats_and_sheet_id(configured, monkeypatch):
    seen = _answer(monkeypatch, lambda r: httpx.Response(200, json=FIXTURES["written"]))
    out = asyncio.run(npc_backport.backport(_npc()))
    (request,) = seen
    assert str(request.url) == "https://gm.example/api/npc-numbers"
    assert request.method == "POST" and request.headers["authorization"] == "Bearer tok"
    assert json.loads(request.content) == {
        "name": "Bayushi no Daika Koharu", "sheet_id": 41,
        "stats": npc_backport.npc_stats(_npc()),
    }
    assert out == {"name": "Bayushi no Daika Koharu", "status": "written",
                   "message": FIXTURES["written"]["message"]}


@pytest.mark.parametrize("status", ["written", "unchanged", "no_record", "ambiguous", "failed"])
def test_every_status_passes_its_message_through(configured, monkeypatch, status):
    _answer(monkeypatch, lambda r: httpx.Response(200, json=FIXTURES[status]))
    out = asyncio.run(npc_backport.backport(_npc()))
    assert out["status"] == status and out["message"] == FIXTURES[status]["message"]


def test_not_configured_is_off_and_sends_nothing(monkeypatch):
    seen = _answer(monkeypatch, lambda r: httpx.Response(200, json=FIXTURES["written"]))
    out = asyncio.run(npc_backport.backport(_npc()))
    assert out["status"] == "off" and "not configured" in out["message"] and seen == []


def test_a_timeout_is_a_reported_failure(configured, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("asleep", request=request)
    _answer(monkeypatch, handler)
    out = asyncio.run(npc_backport.backport(_npc()))
    assert out == {"name": "Bayushi no Daika Koharu", "status": "failed",
                   "message": "Bayushi no Daika Koharu: Obsidian Portal not updated (gm-assistant did not answer)"}


@pytest.mark.parametrize("response,detail", [
    (httpx.Response(400, json=FIXTURES["bad_request"]), FIXTURES["bad_request"]["error"]),
    (httpx.Response(401, json={"error": "bad token"}), "bad token"),
    (httpx.Response(503, text="not configured"), "gm-assistant answered 503"),
    (httpx.Response(502, json=["not", "a", "dict"]), "gm-assistant answered 502"),
])
def test_a_non_200_is_a_reported_failure(configured, monkeypatch, response, detail):
    _answer(monkeypatch, lambda r: response)
    out = asyncio.run(npc_backport.backport(_npc()))
    assert out["status"] == "failed"
    assert out["message"] == f"Bayushi no Daika Koharu: Obsidian Portal not updated ({detail})"


@pytest.mark.parametrize("body", [
    b"not json", b"[]", json.dumps({"status": "exploded", "message": "?"}).encode(),
    json.dumps({"status": "written", "message": "  "}).encode(),
    json.dumps({"status": "written"}).encode(),
])
def test_a_malformed_answer_is_a_reported_failure(configured, monkeypatch, body):
    _answer(monkeypatch, lambda r: httpx.Response(200, content=body))
    out = asyncio.run(npc_backport.backport(_npc()))
    assert out["status"] == "failed" and "malformed" in out["message"]


def test_backport_all_keeps_the_order(configured, monkeypatch):
    def handler(request):
        name = json.loads(request.content)["name"]
        return httpx.Response(200, json={"status": "no_record", "message": f"{name}: no record"})
    _answer(monkeypatch, handler)
    out = asyncio.run(npc_backport.backport_all([_npc(name="A"), _npc(name="B"), _npc(name="C")]))
    assert [o["message"] for o in out] == ["A: no record", "B: no record", "C: no record"]
    assert asyncio.run(npc_backport.backport_all([])) == []


# ---------------------------------------------------------------------------
# The combat routes call it after every build
# ---------------------------------------------------------------------------

@pytest.fixture
def group(client):
    s = client._test_session_factory()
    g = GamingGroup(name="Tuesday")
    s.add(g)
    s.commit()
    gid = g.id
    s.close()
    client.post(f"/groups/{gid}/combat/start", json={})
    return gid


def _names_and_stats(seen):
    return [(json.loads(r.content)["name"], json.loads(r.content)["stats"]) for r in seen]


def _saved(client, npc_id):
    s = client._test_session_factory()
    c = s.get(Character, npc_id)
    stats = npc_backport.npc_stats(c)
    s.close()
    return stats


def test_generate_backports_every_created_npc_after_saving_it(client, group, configured, monkeypatch):
    def handler(request):
        name = json.loads(request.content)["name"]
        return httpx.Response(200, json={"status": "no_record", "message": f"{name}: no record"})
    seen = _answer(monkeypatch, handler)
    monkeypatch.setattr("app.routes.combat.fetch_names", lambda *a, **k: asyncio.sleep(0, []))
    resp = client.post(f"/groups/{group}/combat/generate", json={"rows": [
        {"npc_type": "wave_man", "count": 2, "earned_xp": 50, "names": ["Goro", "Heizo"]}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["backport"] == [
        {"name": "Goro", "status": "no_record", "message": "Goro: no record"},
        {"name": "Heizo", "status": "no_record", "message": "Heizo: no record"},
    ]
    ids = [c["id"] for c in body["created"]]
    assert _names_and_stats(seen) == [("Goro", _saved(client, ids[0])), ("Heizo", _saved(client, ids[1]))]


def test_a_failing_gm_assistant_never_undoes_the_npc(client, group, configured, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down", request=request)
    _answer(monkeypatch, handler)
    resp = client.post(f"/groups/{group}/combat/generate", json={"rows": [
        {"npc_type": "wave_man", "count": 1, "earned_xp": 50, "names": ["Goro"]}]})
    assert resp.status_code == 200 and resp.json()["backport"][0]["status"] == "failed"
    s = client._test_session_factory()
    assert s.get(Character, resp.json()["created"][0]["id"]).name == "Goro"
    s.close()


def _one_npc(client, group):
    resp = client.post(f"/groups/{group}/combat/generate", json={"rows": [
        {"npc_type": "akodo_bushi", "count": 1, "earned_xp": 50, "names": ["Goro"]}]})
    return resp.json()["created"][0]["id"]


def test_rebuild_backports_the_final_stats(client, group, configured, monkeypatch):
    npc_id = _one_npc(client, group)
    seen = _answer(monkeypatch, lambda r: httpx.Response(200, json=FIXTURES["unchanged"]))
    resp = client.post(f"/groups/{group}/combat/npcs/{npc_id}/rebuild", json={"earned_xp": 120})
    assert resp.json()["backport"][0]["status"] == "unchanged"
    assert _names_and_stats(seen) == [("Goro", _saved(client, npc_id))]


def test_rename_backports_only_a_new_name(client, group, configured, monkeypatch):
    npc_id = _one_npc(client, group)
    seen = _answer(monkeypatch, lambda r: httpx.Response(200, json=FIXTURES["unchanged"]))
    url = f"/groups/{group}/combat/npcs/{npc_id}/rename"
    assert client.post(url, json={"name": "Goro"}).json()["backport"] == []
    assert seen == []
    assert client.post(url, json={"name": "Tsuruchi Kyoma"}).json()["backport"][0]["status"] == "unchanged"
    assert [n for n, _ in _names_and_stats(seen)] == ["Tsuruchi Kyoma"]


def test_bring_back_backports_only_with_gained_xp(client, group, configured, monkeypatch):
    npc_id = _one_npc(client, group)
    client.post(f"/groups/{group}/combat/end")
    client.post(f"/groups/{group}/combat/start", json={})
    seen = _answer(monkeypatch, lambda r: httpx.Response(200, json=FIXTURES["written"]))
    url = f"/groups/{group}/combat/roster/{npc_id}/bring-back"
    assert client.post(url, json={}).json()["backport"] == []
    assert seen == []
    client.post(f"/groups/{group}/combat/npcs/{npc_id}/remove")
    assert client.post(url, json={"gained_xp": 40}).json()["backport"][0]["status"] == "written"
    assert _names_and_stats(seen) == [("Goro", _saved(client, npc_id))]
