"""Generated NPCs, encounters and the roster (app/services/npcs.py, app/routes/combat.py)."""

import asyncio
import pathlib
import random
import re

import httpx
import pytest

from app.main import app
from app.models import Character, Encounter, EncounterAction, EncounterNpc, GamingGroup
from app.services import npc_names, npcs
from app.services.xp import validate_character

GM = "183026066498125825"
PLAYER = {"X-Test-User": "test_user_1:player"}


def _session(client):
    return client._test_session_factory()


@pytest.fixture
def group(client):
    s = _session(client)
    g = GamingGroup(name="Tuesday")
    s.add(g)
    s.commit()
    gid = g.id
    s.close()
    return gid


@pytest.fixture(autouse=True)
def no_names(monkeypatch):
    """No gm-assistant in unit tests unless a test says otherwise."""
    monkeypatch.delenv("GM_ASSISTANT_URL", raising=False)
    monkeypatch.delenv("GM_ASSISTANT_NAMES_TOKEN", raising=False)


def _start(client, gid, **body):
    return client.post(f"/groups/{gid}/combat/start", json=body)


def _gen(client, gid, *rows):
    return client.post(f"/groups/{gid}/combat/generate", json={"rows": list(rows)})


def _wave_men(count=2, **extra):
    return {"npc_type": "wave_man", "count": count, "earned_xp": 50, **extra}


def _npc_ids(client, gid):
    s = _session(client)
    ids = [c.id for c in s.query(Character).filter(Character.npc_group_id == gid).order_by(Character.id)]
    s.close()
    return ids


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def test_generate_creates_hidden_published_npcs_in_the_fight(client, group):
    assert _start(client, group, name="Bandits").status_code == 200
    resp = _gen(client, group, _wave_men(3))
    assert resp.status_code == 200
    created = resp.json()["created"]
    assert [c["name"] for c in created] == ["Wave Man 1", "Wave Man 2", "Wave Man 3"]
    s = _session(client)
    for c in s.query(Character).filter(Character.npc_group_id == group):
        assert c.is_npc and c.is_hidden and c.is_published
        assert c.gaming_group_id is None
        assert c.owner_discord_id == GM
        assert c.profession == "profession"
        assert c.earned_xp >= 55  # base 50 + at least one d10 x 5
        assert c.npc_generation["npc_type"] == "wave_man"
        assert c.current_void_points > 0 and c.current_light_wounds == 0
        assert not [w for w in validate_character(c.to_dict()) if "Total XP" in w or "not set" in w]
    enc = s.query(Encounter).one()
    assert enc.name == "Bandits" and len(enc.npcs) == 3
    s.close()


def test_exact_xp_and_combat_override(client, group):
    _start(client, group)
    _gen(client, group, {"npc_type": "kakita_duelist", "count": 1, "earned_xp": 100,
                         "roll_extra": False, "combat_share": 85})
    s = _session(client)
    c = s.query(Character).filter(Character.npc_group_id == group).one()
    assert c.earned_xp == 100
    assert c.npc_generation["combat_share"] == 0.85
    s.close()


def test_gm_names_come_first_then_numbering_continues(client, group):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    resp = _gen(client, group, _wave_men(3, names=["Goro", " "]))
    assert [c["name"] for c in resp.json()["created"]] == ["Goro", "Wave Man 2", "Wave Man 3"]


def test_suggested_names_are_used(client, group, monkeypatch):
    calls = []

    async def fake(count, peasant, avoid=()):
        calls.append((count, peasant, list(avoid)))
        return ["Heizo", "Tamaki"][:count]
    monkeypatch.setattr("app.routes.combat.fetch_names", fake)
    _start(client, group)
    resp = _gen(client, group, _wave_men(3, names=["Goro"]),
                {"npc_type": "kakita_duelist", "count": 1, "earned_xp": 0})
    names = [c["name"] for c in resp.json()["created"]]
    assert names == ["Goro", "Heizo", "Tamaki", "Heizo"]
    assert calls[0] == (2, True, ["Goro"])          # Wave Men: peasant pool
    assert calls[1] == (1, False, ["Goro", "Heizo", "Tamaki"])  # samurai pool, batch avoided


def test_generate_service_with_a_provider_and_rng(client, group):
    s = _session(client)
    g = s.get(GamingGroup, group)
    enc = npcs.start_encounter(s, group)
    made = npcs.generate(
        s, g, enc, GM, [_wave_men(2, roll_extra=False)],
        rng=random.Random(1), name_provider=lambda n, peasant: ["Only"],
    )
    assert [m.name for m in made] == ["Only", "Wave Man 1"]
    assert all(m.earned_xp == 50 for m in made)
    s.close()


@pytest.mark.parametrize("row,message", [
    ({"npc_type": "shugenja"}, "unknown NPC type"),
    ({"npc_type": "wave_man", "count": 0}, "count"),
    ({"npc_type": "wave_man", "count": "x"}, "whole number"),
    ({"npc_type": "wave_man", "earned_xp": -1}, "earned XP"),
    ({"npc_type": "wave_man", "combat_target": "lots"}, "number"),
])
def test_generate_rejects_bad_rows_and_creates_nothing(client, group, row, message):
    _start(client, group)
    resp = _gen(client, group, _wave_men(1), row)
    assert resp.status_code == 400 and message in resp.json()["error"]
    assert _npc_ids(client, group) == []


def test_generate_caps_the_batch(client, group):
    _start(client, group)
    resp = _gen(client, group, _wave_men(20), _wave_men(20))
    assert resp.status_code == 400 and "at most" in resp.json()["error"]


def test_generate_needs_rows_and_a_fight(client, group):
    assert _gen(client, group, _wave_men(1)).status_code == 409
    _start(client, group)
    assert client.post(f"/groups/{group}/combat/generate", json={"rows": []}).status_code == 400
    assert client.post(f"/groups/{group}/combat/generate", content=b"nope").status_code == 400


def test_combat_target_as_fraction_or_percent(client, group):
    s = _session(client)
    g, enc = s.get(GamingGroup, group), npcs.start_encounter(s, group)
    rng = random.Random(3)
    made = npcs.generate(s, g, enc, GM, [
        {"npc_type": "wave_man", "count": 1, "combat_target": 0.6},
        {"npc_type": "wave_man", "count": 1, "combat_target": 60},
    ], rng=rng)
    low, high = 0.532, 0.91
    for m in made:
        assert low <= m.npc_generation["combat_share"] <= high
    s.close()


# ---------------------------------------------------------------------------
# Encounters
# ---------------------------------------------------------------------------

def test_one_fight_at_a_time(client, group):
    assert _start(client, group, name="First").status_code == 200
    resp = _start(client, group, name="Second")
    assert resp.status_code == 409 and resp.json()["error"] == "fight_in_progress"
    assert "First" in resp.json()["message"]
    assert _start(client, group, name="Second", replace=True).status_code == 200
    s = _session(client)
    statuses = {e.name: e.status for e in s.query(Encounter)}
    assert statuses == {"First": "ended", "Second": "active"}
    s.close()


def test_end_fight(client, group):
    assert client.post(f"/groups/{group}/combat/end").status_code == 404
    _start(client, group)
    _gen(client, group, _wave_men(1))
    assert client.post(f"/groups/{group}/combat/end").status_code == 200
    s = _session(client)
    enc = s.query(Encounter).one()
    assert enc.status == "ended" and enc.ended_at is not None
    assert s.query(Character).filter(Character.npc_group_id == group).count() == 1
    s.close()


def test_status_remove_rename(client, group):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    (npc_id,) = _npc_ids(client, group)
    base = f"/groups/{group}/combat/npcs/{npc_id}"
    assert client.post(f"{base}/status", json={"status": "dead"}).json() == {"status": "dead"}
    assert client.post(f"{base}/status", json={"status": "napping"}).status_code == 400
    assert client.post(f"{base}/rename", json={"name": "  Kenji  "}).json() == {"name": "Kenji"}
    assert client.post(f"{base}/rename", json={"name": ""}).status_code == 400
    assert client.post(f"{base}/remove").status_code == 200
    assert client.post(f"{base}/remove").status_code == 404
    assert client.post(f"{base}/status", json={"status": "dead"}).status_code == 404
    s = _session(client)
    assert s.get(Character, npc_id).name == "Kenji"
    s.close()


def test_routes_404_for_unknown_npcs_and_no_fight(client, group):
    for path in ("status", "remove"):
        assert client.post(f"/groups/{group}/combat/npcs/999/{path}", json={}).status_code == 404
    for path in ("rebuild", "rename"):
        assert client.post(f"/groups/{group}/combat/npcs/999/{path}", json={}).status_code == 404
    for path in ("bring-back", "delete"):
        assert client.post(f"/groups/{group}/combat/roster/999/{path}", json={}).status_code == 404
    assert client.post("/groups/999/combat/start", json={}).status_code == 404


def test_service_errors_for_an_npc_not_in_the_fight(client, group):
    s = _session(client)
    enc = npcs.start_encounter(s, group)
    stranger = Character(name="x", is_npc=True, npc_group_id=group)
    s.add(stranger)
    s.flush()
    with pytest.raises(LookupError):
        npcs.set_status(s, enc, stranger, "dead")
    with pytest.raises(LookupError):
        npcs.remove_from_encounter(s, enc, stranger)
    link = npcs.add_to_encounter(s, enc, stranger)
    assert npcs.add_to_encounter(s, enc, stranger) is link
    s.close()


def test_every_write_is_gm_only(client, group):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    (npc_id,) = _npc_ids(client, group)
    posts = [
        "start", "end", "generate", f"npcs/{npc_id}/status", f"npcs/{npc_id}/remove",
        f"npcs/{npc_id}/rebuild", f"npcs/{npc_id}/rename",
        f"roster/{npc_id}/bring-back", f"roster/{npc_id}/delete",
    ]
    for path in posts:
        assert client.post(f"/groups/{group}/combat/{path}", json={}, headers=PLAYER).status_code == 403, path
    for path in ("roster", "npc-types"):
        assert client.get(f"/groups/{group}/combat/{path}", headers=PLAYER).status_code == 403


# ---------------------------------------------------------------------------
# Overrides, roster, bring back
# ---------------------------------------------------------------------------

def test_rebuild_with_new_xp_and_share(client, group):
    _start(client, group)
    _gen(client, group, {"npc_type": "kakita_duelist", "count": 1, "earned_xp": 0, "roll_extra": False})
    (npc_id,) = _npc_ids(client, group)
    url = f"/groups/{group}/combat/npcs/{npc_id}/rebuild"
    resp = client.post(url, json={"earned_xp": 200, "combat_share": 0.6})
    assert resp.json() == {"earned_xp": 200, "combat_share": 0.6}
    assert client.post(url, json={"combat_share": 99}).json()["combat_share"] == 0.91  # clamped
    assert client.post(url, json={"earned_xp": "lots"}).status_code == 400
    assert client.post(url, json={"earned_xp": 5000}).status_code == 400
    s = _session(client)
    assert len(s.get(Character, npc_id).versions) == 3
    s.close()


def test_roster_and_bring_back_heals_and_adds_xp(client, group):
    _start(client, group, name="Ambush")
    _gen(client, group, _wave_men(1, roll_extra=False))
    (npc_id,) = _npc_ids(client, group)
    client.post(f"/groups/{group}/combat/npcs/{npc_id}/status", json={"status": "unconscious"})
    s = _session(client)
    npc = s.get(Character, npc_id)
    before = npc.to_dict()
    npc.current_serious_wounds = 5
    npc.current_void_points = 0
    s.commit()
    s.close()
    client.post(f"/groups/{group}/combat/end")

    roster = client.get(f"/groups/{group}/combat/roster").json()["npcs"]
    assert roster == [{"id": npc_id, "name": "Wave Man 1", "type": "Wave Man",
                       "earned_xp": 50, "status": "unconscious", "in_fight": False}]
    assert client.post(f"/groups/{group}/combat/roster/{npc_id}/bring-back", json={}).status_code == 409

    _start(client, group, name="Rematch")
    resp = client.post(f"/groups/{group}/combat/roster/{npc_id}/bring-back", json={"gained_xp": 60})
    assert resp.json() == {"id": npc_id, "earned_xp": 110}
    s = _session(client)
    npc = s.get(Character, npc_id)
    assert npc.current_serious_wounds == 0 and npc.current_void_points > 0
    for ring, rank in before["rings"].items():
        assert npc.rings[ring] >= rank
    s.close()
    roster = client.get(f"/groups/{group}/combat/roster").json()["npcs"]
    assert roster[0]["in_fight"] and roster[0]["status"] == "fighting"
    assert client.post(f"/groups/{group}/combat/roster/{npc_id}/bring-back",
                       json={"gained_xp": -5}).status_code == 400


def test_delete_removes_the_npc_and_its_links(client, group):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    (npc_id,) = _npc_ids(client, group)
    s = _session(client)
    s.add(EncounterAction(encounter_id=s.query(Encounter).one().id, character_id=npc_id, kind="attack"))
    s.commit()
    s.close()
    assert client.post(f"/groups/{group}/combat/roster/{npc_id}/delete").status_code == 200
    s = _session(client)
    assert s.get(Character, npc_id) is None
    assert s.query(EncounterNpc).count() == 0 and s.query(EncounterAction).count() == 0
    s.close()


def test_rebuild_infers_type_for_an_npc_without_generation_record(client, group):
    s = _session(client)
    npc = Character(name="Old", is_npc=True, npc_group_id=group, school="akodo_bushi",
                    school_ring_choice="Water", owner_discord_id=GM)
    s.add(npc)
    s.flush()
    npcs.rebuild_npc(s, npc, earned_xp=40)
    assert npc.npc_generation["npc_type"] == "akodo_bushi"
    assert npcs._infer_type(Character(profession="profession")) == "wave_man"
    s.close()


def test_npc_type_options(client, group):
    data = client.get(f"/groups/{group}/combat/npc-types").json()
    assert {"id": "wave_man", "label": "Wave Man"} in data["types"]
    assert data["combat_share"] == {"default": pytest.approx(0.741), "min": 0.532, "max": 0.91}


# ---------------------------------------------------------------------------
# Players never see an NPC
# ---------------------------------------------------------------------------

def test_npc_sheet_and_endpoints_404_for_players(client, group):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    (npc_id,) = _npc_ids(client, group)
    assert client.get(f"/characters/{npc_id}").status_code == 200  # the GM
    for path in ("", "/edit", "/rolls", "/versions"):
        assert client.get(f"/characters/{npc_id}{path}", headers=PLAYER).status_code == 404, path


def test_guard_ignores_malformed_ids_and_non_npcs(client):
    s = _session(client)
    pc = Character(name="PC", owner_discord_id="test_user_1")
    s.add(pc)
    s.commit()
    pc_id = pc.id
    s.close()
    assert client.get(f"/characters/{pc_id}", headers=PLAYER).status_code == 200
    assert client.get("/characters/abc", headers=PLAYER).status_code in (404, 422)


def test_every_char_id_route_is_guarded():
    """A route taking {char_id} must sit behind npc_guard, or an NPC's data
    could reach a player through it."""
    from fastapi.routing import APIRoute

    unguarded = []
    for route in app.routes:
        if isinstance(route, APIRoute) and "{char_id}" in route.path:
            deps = {d.call for d in route.dependant.dependencies}
            if npcs.npc_guard not in deps:
                unguarded.append(route.path)
    assert unguarded == []


def test_google_export_callback_refuses_an_npc_to_a_player(client, group, monkeypatch):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    (npc_id,) = _npc_ids(client, group)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "y")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": "t"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()
    monkeypatch.setattr("app.routes.google_sheets.httpx.AsyncClient", lambda *a, **k: FakeClient())
    client.cookies.set("google_oauth_state", "s")
    client.cookies.set("google_export_char_id", str(npc_id))
    resp = client.get("/auth/google/callback?state=s&code=c", headers=PLAYER, follow_redirects=False)
    assert "not_found" in resp.headers["location"]


# Every non-by-id Character query in app/, classified. NPCs have a NULL
# gaming_group_id, so group/party queries exclude them by construction; a new
# listing site must be added here after deciding how it treats NPCs.
_LISTING_SITES = {
    "app/database.py": "migrations touch every row",
    "app/services/discord_commands.py": "owned AND gaming_group_id NOT NULL",
    "app/services/import_rate_limit.py": "the user's own imports",
    "app/services/party.py": "same gaming group",
    "app/services/npcs.py": "the NPC roster itself",
    "app/routes/gm_api.py": "every character, NPCs flagged is_npc",
    "app/routes/pages.py": "index filters is_npc; the rest are by gaming_group_id",
}


def test_every_character_listing_site_is_classified():
    root = pathlib.Path(__file__).resolve().parent.parent
    found = set()
    for path in (root / "app").rglob("*.py"):
        text = path.read_text()
        for m in re.finditer(r"query\(Character\)((?:\s*\n?\s*\.[a-z_]+\([^()]*(?:\([^()]*\)[^()]*)*\))*)", text):
            if "Character.id ==" not in m.group(1):
                found.add(str(path.relative_to(root)))
    assert found <= set(_LISTING_SITES), found - set(_LISTING_SITES)


def test_home_page_never_lists_npcs(client, group):
    _start(client, group)
    _gen(client, group, _wave_men(1))
    assert "Wave Man 1" not in client.get("/").text


def test_gm_api_flags_npcs(client, group, monkeypatch):
    monkeypatch.setenv("ROLL_QUERY_TOKEN", "t")
    _start(client, group)
    _gen(client, group, _wave_men(1))
    rows = client.get("/api/characters", headers={"Authorization": "Bearer t"}).json()["characters"]
    npc = next(r for r in rows if r["name"] == "Wave Man 1")
    assert npc["is_npc"] is True and npc["npc_group_id"] == group and npc["gaming_group_id"] is None


def test_npcs_skip_pc_only_warnings():
    data = {"is_npc": True, "profession": "profession", "starting_xp": 150, "earned_xp": 300,
            "profession_abilities": {}, "rings": {}, "skills": {}, "knacks": {}}
    warnings = validate_character(data)
    assert not any("not set" in w or "unclaimed" in w for w in warnings)
    data["is_npc"] = False
    assert any("Age is not set" in w for w in validate_character(data))


# ---------------------------------------------------------------------------
# gm-assistant names client
# ---------------------------------------------------------------------------

def _names_env(monkeypatch):
    monkeypatch.setenv("GM_ASSISTANT_URL", "https://gm.example/")
    monkeypatch.setenv("GM_ASSISTANT_NAMES_TOKEN", "tok")


def _patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(npc_names.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_names_not_configured_or_nothing_needed():
    assert asyncio.run(npc_names.fetch_names(3, True)) == []


def test_names_are_fetched_with_the_token(monkeypatch):
    _names_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"names": ["Heizo", " ", 7, "Tamaki", "Extra"]})
    _patch_http(monkeypatch, handler)
    assert asyncio.run(npc_names.fetch_names(3, True, avoid=["Goro"])) == ["Heizo", "Tamaki", "Extra"]
    assert seen["auth"] == "Bearer tok"
    assert seen["url"].startswith("https://gm.example/api/names?")
    assert "peasant=true" in seen["url"] and "avoid=Goro" in seen["url"] and "count=3" in seen["url"]
    assert asyncio.run(npc_names.fetch_names(0, True)) == []


@pytest.mark.parametrize("response", [
    httpx.Response(503),
    httpx.Response(200, content=b"not json"),
    httpx.Response(200, json={"names": "Heizo"}),
    httpx.Response(200, json=["Heizo"]),
])
def test_names_failures_yield_nothing(monkeypatch, response):
    _names_env(monkeypatch)
    _patch_http(monkeypatch, lambda request: response)
    assert asyncio.run(npc_names.fetch_names(2, False)) == []


def test_names_unreachable_yields_nothing(monkeypatch):
    _names_env(monkeypatch)

    def handler(request):
        raise httpx.ConnectError("asleep")
    _patch_http(monkeypatch, handler)
    assert asyncio.run(npc_names.fetch_names(2, False)) == []
