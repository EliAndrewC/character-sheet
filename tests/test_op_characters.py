"""Builder rows from Obsidian Portal characters (app/services/op_characters.py,
combat-design D46-D47): gm-assistant's raw facts, the GM's school
conventions, and the combat page's lookup route."""

import asyncio

import httpx
import pytest

from app.models import GamingGroup
from app.services import op_characters as op

PLAYER = {"X-Test-User": "test_user_1:player"}

FUMITAKE = {
    "name": "Tsuruchi Fumitake", "slug": "tsuruchi-fumitake",
    "school_line": "male Peasantborn", "tags": ["Wasp Clan", "Inspector"],
    "earned_xp": 140,
    "trait_lines": ["contemptuous", "Poor - even by Wasp standards", "Contrary", "Wealthy"],
    "stat_lines": ["- Air 4", "- sincerity 4", "- juggling 3"],
}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("GM_ASSISTANT_URL", "https://gm.example/")
    monkeypatch.setenv("GM_ASSISTANT_NAMES_TOKEN", "tok")


def _patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(op.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def _fetch(ref="Fumitake"):
    return asyncio.run(op.fetch_op_character(ref))


# ---------------------------------------------------------------------------
# School line and tags -> NPC type (D46)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("school_line,tags,expected", [
    ("male Peasantborn", [], "wave_man"),
    ("female peasant", [], "wave_man"),
    ("male Peasantborn Merchant", [], "wave_man"),          # any peasant
    ("male Mantis Bushi", [], "mantis_wave_treader"),       # the line predates the school
    ("female Mantis Wave-Treader", [], "mantis_wave_treader"),
    ("female Bayushi Bushi", [], "bayushi_bushi"),
    ("male hida bushi", [], "hida_bushi"),
    ("female Priest", ["monk"], "priest"),                  # a listed school wins
    (None, ["monk", "Seven Temples"], "brotherhood_of_shinsei_monk"),
    ("", ["Order of Bishamon"], "brotherhood_of_shinsei_monk"),
    ("male Monk", ["Order of Ebisu"], "brotherhood_of_shinsei_monk"),
    (None, ["peasant"], "wave_man"),
    ("male Seppun Bushi", [], None),
    ("male Akodo Bushi", ["Hantei Family"], None),
    ("male Kitsuki Magistrate", ["Imperial Magistrate"], "kitsuki_magistrate"),
    ("male Sailor", [], None),
    (None, ["Wasp Clan", 7], None),
])
def test_npc_type_for(school_line, tags, expected):
    npc_type, why = op.npc_type_for(school_line, tags)
    assert npc_type == expected
    assert why


def test_unmapped_reasons_name_the_problem():
    assert "Imperial" in op.npc_type_for("male Seppun Bushi", [])[1]
    assert '"male Sailor"' in op.npc_type_for("male Sailor", [])[1]
    assert "No school is listed" in op.npc_type_for(None, [])[1]


def test_a_line_naming_two_schools_is_left_to_the_gm(monkeypatch):
    monkeypatch.setattr(op.gen, "npc_type_options",
                        lambda: [("hida_bushi", "Hida Bushi"), ("hida", "Hida")])
    npc_type, why = op.npc_type_for("male Hida Bushi", [])
    assert npc_type is None and "more than one school" in why


# ---------------------------------------------------------------------------
# The builder row
# ---------------------------------------------------------------------------

def test_builder_row_reads_everything_and_shows_what_it_did_not_use():
    row = op.builder_row(FUMITAKE)
    assert row["name"] == "Tsuruchi Fumitake"
    assert row["npc_type"] == "wave_man" and "peasant" in row["type_note"]
    assert row["earned_xp"] == 140
    assert row["traits"]["disadvantages"] == ["contrary", "poor"]
    assert row["traits"]["advantages"] == ["wealthy"]
    assert sorted(row["trait_names"]) == ["Contrary", "Poor", "Wealthy"]
    assert row["recorded"] == {"Air": 4, "sincerity": 4}
    assert row["ignored"] == ["contemptuous", "- juggling 3"]


@pytest.mark.parametrize("earned", [None, True, "140", 1.5])
def test_builder_row_without_a_usable_xp(earned):
    assert op.builder_row({**FUMITAKE, "earned_xp": earned})["earned_xp"] is None


def test_builder_row_tolerates_missing_lists():
    row = op.builder_row({"name": "  Hideki  ", "school_line": None, "tags": "monk",
                          "trait_lines": None, "stat_lines": [3]})
    assert row["name"] == "Hideki" and row["npc_type"] is None
    assert row["recorded"] == {} and row["ignored"] == [] and row["trait_names"] == []


# ---------------------------------------------------------------------------
# The gm-assistant client
# ---------------------------------------------------------------------------

def test_fetch_sends_the_ref_and_token(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json=FUMITAKE)
    _patch_http(monkeypatch, handler)
    assert _fetch("https://x.obsidianportal.com/characters/tsuruchi-fumitake") == FUMITAKE
    assert seen["auth"] == "Bearer tok"
    assert seen["url"].startswith("https://gm.example/api/op-character?ref=https")


def test_fetch_when_not_configured(monkeypatch):
    monkeypatch.delenv("GM_ASSISTANT_NAMES_TOKEN")
    with pytest.raises(op.OpLookupError, match="lookups are off"):
        _fetch()


def test_an_ambiguous_name_carries_the_candidates(monkeypatch):
    _patch_http(monkeypatch, lambda r: httpx.Response(
        409, json={"error": "Bayushi matches several", "candidates": ["A", 3, "B"]}))
    with pytest.raises(op.OpLookupError) as exc:
        _fetch("Bayushi")
    assert str(exc.value) == "Bayushi matches several" and exc.value.candidates == ["A", "B"]


@pytest.mark.parametrize("status", [400, 404])
def test_gm_assistants_refusal_is_passed_on(monkeypatch, status):
    _patch_http(monkeypatch, lambda r: httpx.Response(
        status, json={"error": "no Obsidian Portal record for Nobody", "candidates": "x"}))
    with pytest.raises(op.OpLookupError) as exc:
        _fetch("Nobody")
    assert "Nobody" in str(exc.value) and exc.value.candidates == []


@pytest.mark.parametrize("response", [
    httpx.Response(500, json={"error": "boom"}),
    httpx.Response(200, content=b"not json"),
    httpx.Response(200, json=["Fumitake"]),
    httpx.Response(200, json={"slug": "no-name"}),
])
def test_anything_else_is_a_plain_failure(monkeypatch, response):
    _patch_http(monkeypatch, lambda r: response)
    with pytest.raises(op.OpLookupError, match="answered"):
        _fetch()


def test_gm_assistant_asleep(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("asleep")
    _patch_http(monkeypatch, handler)
    with pytest.raises(op.OpLookupError, match="did not answer"):
        _fetch()


# ---------------------------------------------------------------------------
# GET /groups/{id}/combat/op-character
# ---------------------------------------------------------------------------

@pytest.fixture
def gid(client):
    s = client._test_session_factory()
    g = GamingGroup(name="Tuesday")
    s.add(g)
    s.commit()
    out = g.id
    s.close()
    return out


def _lookup(client, gid, ref, headers=None):
    return client.get(f"/groups/{gid}/combat/op-character", params={"ref": ref}, headers=headers or {})


def test_the_route_answers_a_builder_row(client, gid, monkeypatch):
    _patch_http(monkeypatch, lambda r: httpx.Response(200, json=FUMITAKE))
    r = _lookup(client, gid, " Fumitake ")
    assert r.status_code == 200
    assert r.json()["row"]["npc_type"] == "wave_man"


def test_the_route_is_the_gms_and_needs_a_ref(client, gid):
    assert _lookup(client, gid, "Fumitake", PLAYER).status_code == 403
    assert _lookup(client, 99999, "Fumitake").status_code == 404
    r = _lookup(client, gid, "   ")
    assert r.status_code == 400 and "Paste" in r.json()["error"]


def test_the_route_passes_on_a_refusal_with_candidates(client, gid, monkeypatch):
    _patch_http(monkeypatch, lambda r: httpx.Response(
        409, json={"error": "several", "candidates": ["A", "B"]}))
    r = _lookup(client, gid, "Bayushi")
    assert r.status_code == 400
    assert r.json() == {"error": "several", "candidates": ["A", "B"]}


def test_a_looked_up_row_generates_with_its_name_traits_and_numbers(client, gid, monkeypatch):
    """The row the page posts after a lookup is one generate already takes."""
    import app.routes.combat as combat_routes
    monkeypatch.setattr(combat_routes, "fetch_names", lambda *a, **k: asyncio.sleep(0, []))
    monkeypatch.setattr(combat_routes, "backport_all", lambda created: asyncio.sleep(0, []))
    _patch_http(monkeypatch, lambda r: httpx.Response(200, json=FUMITAKE))
    row = _lookup(client, gid, "Fumitake").json()["row"]
    assert client.post(f"/groups/{gid}/combat/start", json={}).status_code == 200
    r = client.post(f"/groups/{gid}/combat/generate", json={"rows": [{
        "npc_type": row["npc_type"], "count": 1, "earned_xp": row["earned_xp"],
        "roll_extra": False, "names": [row["name"]],
        "traits": row["traits"], "recorded": row["recorded"],
    }]})
    assert r.status_code == 200, r.text
    assert [c["name"] for c in r.json()["created"]] == ["Tsuruchi Fumitake"]
