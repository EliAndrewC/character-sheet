"""Unit tests for the GM-facing read-only JSON API (app/routes/gm_api.py).

Covers the token gate, ``since`` / ``limit`` / ``group`` parsing, the
ascending + pageable ordering contract, payload flattening, and the
companion ``/api/characters`` rank lookup. Also covers the one write-path
addition the feature needed: the create-time ``skill_rank`` stamp.
"""

from datetime import datetime, timedelta

import pytest

from app.models import Character, GamingGroup, RollHistory
from app.routes import gm_api
from app.services.roll_descriptions import label_for_roll
from app.services.rolls_history import skill_rank_for_roll


TOKEN = "s3cret-roll-query-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# Matches conftest's ADMIN_DISCORD_IDS / the client fixture's X-Test-User.
ADMIN_ID = "183026066498125825"
OWNER_ID = "owner_user_42"

BASE = datetime(2026, 8, 25, 2, 14, 9)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    """Configure the shared secret for every test in this module.

    The 503-when-unset test deletes it again; everything else needs it
    present or every request would 503 instead of exercising the route.
    """
    monkeypatch.setenv(gm_api.TOKEN_ENV_VAR, TOKEN)


def _make_char(db, name="Bayushi Sadakichi", **kwargs):
    kwargs.setdefault("owner_discord_id", OWNER_ID)
    char = Character(name=name, **kwargs)
    db.add(char)
    db.flush()
    return char


def _make_roll(db, char, *, offset=0, **kwargs):
    """Insert a roll row with explicit timestamps.

    ``server_default=func.now()`` would give every row in a test the same
    second, which cannot exercise the ordering / paging contract; the
    ``offset`` (in seconds) spreads them out deterministically.
    """
    stamp = BASE + timedelta(seconds=offset)
    kwargs.setdefault("roll_key", "skill:etiquette")
    kwargs.setdefault("actor_discord_id", OWNER_ID)
    kwargs.setdefault("is_owner_roll", True)
    kwargs.setdefault("payload", {"title": "Etiquette", "total": 38})
    row = RollHistory(
        character_id=char.id,
        created_at=stamp,
        updated_at=stamp,
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _session(client):
    return client._test_session_factory()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_rolls_requires_a_token_header(client):
    r = client.get("/api/rolls?since=2026-08-01T00:00:00Z")
    assert r.status_code == 401


def test_rolls_rejects_a_wrong_token(client):
    r = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z",
        headers={"Authorization": "Bearer nope"},
    )
    assert r.status_code == 401


def test_rolls_rejects_a_non_bearer_scheme(client):
    r = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z",
        headers={"Authorization": f"Token {TOKEN}"},
    )
    assert r.status_code == 401


def test_rolls_rejects_the_token_in_the_query_string(client):
    """The token is GM-equivalent; a query string leaks it into logs."""
    r = client.get(f"/api/rolls?since=2026-08-01T00:00:00Z&token={TOKEN}")
    assert r.status_code == 401


def test_rolls_503_when_the_token_is_not_configured(client, monkeypatch):
    monkeypatch.delenv(gm_api.TOKEN_ENV_VAR, raising=False)
    r = client.get("/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH)
    assert r.status_code == 503
    assert gm_api.TOKEN_ENV_VAR in r.json()["error"]


def test_rolls_503_when_the_token_is_blank(client, monkeypatch):
    """A whitespace-only secret is a misconfiguration, not an empty password."""
    monkeypatch.setenv(gm_api.TOKEN_ENV_VAR, "   ")
    r = client.get("/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH)
    assert r.status_code == 503


def test_characters_requires_a_token(client):
    assert client.get("/api/characters").status_code == 401


def test_characters_503_when_the_token_is_not_configured(client, monkeypatch):
    monkeypatch.delenv(gm_api.TOKEN_ENV_VAR, raising=False)
    assert client.get("/api/characters", headers=AUTH).status_code == 503


def test_auth_failure_beats_parameter_validation(client):
    """A bad token must not learn which params the endpoint takes."""
    r = client.get("/api/rolls", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def test_since_is_required(client):
    r = client.get("/api/rolls", headers=AUTH)
    assert r.status_code == 400
    assert "since" in r.json()["error"]


def test_since_rejects_a_naive_timestamp(client):
    r = client.get("/api/rolls?since=2026-08-01T00:00:00", headers=AUTH)
    assert r.status_code == 400
    assert "timezone" in r.json()["error"]


def test_since_rejects_garbage(client):
    r = client.get("/api/rolls?since=last+tuesday", headers=AUTH)
    assert r.status_code == 400


def test_since_accepts_a_numeric_offset(client):
    r = client.get("/api/rolls?since=2026-08-01T00:00:00-04:00", headers=AUTH)
    assert r.status_code == 200


def test_limit_must_be_an_integer(client):
    r = client.get("/api/rolls?since=2026-08-01T00:00:00Z&limit=many", headers=AUTH)
    assert r.status_code == 400


def test_limit_must_be_positive(client):
    r = client.get("/api/rolls?since=2026-08-01T00:00:00Z&limit=0", headers=AUTH)
    assert r.status_code == 400


def test_group_must_be_an_integer(client):
    r = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z&group=tuesday", headers=AUTH,
    )
    assert r.status_code == 400


def test_parse_limit_defaults_and_clamps():
    assert gm_api._parse_limit(None) == (gm_api.DEFAULT_LIMIT, None)
    assert gm_api._parse_limit("") == (gm_api.DEFAULT_LIMIT, None)
    assert gm_api._parse_limit("5") == (5, None)
    assert gm_api._parse_limit("99999") == (gm_api.MAX_LIMIT, None)


def test_parse_group_blank_is_no_filter():
    assert gm_api._parse_group(None) == (None, None)
    assert gm_api._parse_group("  ") == (None, None)
    assert gm_api._parse_group("2") == (2, None)


def test_parse_since_lowercase_z():
    dt, err = gm_api._parse_since("2026-08-01t00:00:00z")
    assert err is None
    assert dt == datetime(2026, 8, 1, 0, 0, 0)


def test_parse_since_converts_offset_to_naive_utc():
    dt, err = gm_api._parse_since("2026-08-01T00:00:00-04:00")
    assert err is None
    assert dt == datetime(2026, 8, 1, 4, 0, 0)


# ---------------------------------------------------------------------------
# GET /api/rolls - ordering, paging, filtering
# ---------------------------------------------------------------------------


def test_rolls_empty_response(client):
    r = client.get("/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"rolls": [], "more": False}


def test_rolls_ascending_by_updated_at(client):
    db = _session(client)
    char = _make_char(db)
    for offset in (30, 10, 20):
        _make_roll(db, char, offset=offset)
    db.commit()

    body = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()
    stamps = [row["updated_at"] for row in body["rolls"]]
    assert stamps == sorted(stamps)
    assert body["more"] is False


def test_rolls_since_bound_is_inclusive_on_updated_at(client):
    db = _session(client)
    char = _make_char(db)
    _make_roll(db, char, offset=0)
    _make_roll(db, char, offset=60)
    db.commit()

    body = client.get(
        f"/api/rolls?since={BASE.isoformat()}Z", headers=AUTH,
    ).json()
    assert len(body["rolls"]) == 2

    body = client.get(
        f"/api/rolls?since={(BASE + timedelta(seconds=1)).isoformat()}Z",
        headers=AUTH,
    ).json()
    assert len(body["rolls"]) == 1


def test_rolls_filters_on_updated_at_not_created_at(client):
    """A row created before ``since`` but edited after it must come back."""
    db = _session(client)
    char = _make_char(db)
    row = RollHistory(
        character_id=char.id,
        roll_key="skill:etiquette",
        actor_discord_id=OWNER_ID,
        payload={"title": "Etiquette"},
        created_at=BASE,
        updated_at=BASE + timedelta(hours=1),
    )
    db.add(row)
    db.commit()

    body = client.get(
        f"/api/rolls?since={(BASE + timedelta(minutes=30)).isoformat()}Z",
        headers=AUTH,
    ).json()
    assert [r["id"] for r in body["rolls"]] == [row.id]


def test_rolls_limit_and_more_flag(client):
    db = _session(client)
    char = _make_char(db)
    for offset in range(5):
        _make_roll(db, char, offset=offset)
    db.commit()

    body = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z&limit=2", headers=AUTH,
    ).json()
    assert len(body["rolls"]) == 2
    assert body["more"] is True

    body = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z&limit=5", headers=AUTH,
    ).json()
    assert len(body["rolls"]) == 5
    assert body["more"] is False


def test_rolls_paging_by_last_updated_at(client):
    """Walk the whole feed the way the REPL is meant to."""
    db = _session(client)
    char = _make_char(db)
    for offset in range(5):
        _make_roll(db, char, offset=offset * 10)
    db.commit()

    seen = []
    since = "2026-08-01T00:00:00Z"
    for _ in range(5):
        body = client.get(
            f"/api/rolls?since={since}&limit=2", headers=AUTH,
        ).json()
        for row in body["rolls"]:
            if row["id"] not in seen:
                seen.append(row["id"])
        if not body["more"]:
            break
        since = body["rolls"][-1]["updated_at"]
    assert len(seen) == 5
    assert seen == sorted(seen)


def test_rolls_group_filter(client):
    db = _session(client)
    tuesday = GamingGroup(name="Tuesday Group")
    monday = GamingGroup(name="Monday Group")
    db.add_all([tuesday, monday])
    db.flush()
    tues_char = _make_char(db, name="Tues PC", gaming_group_id=tuesday.id)
    mon_char = _make_char(db, name="Mon PC", gaming_group_id=monday.id)
    _make_roll(db, tues_char, offset=0)
    _make_roll(db, mon_char, offset=1)
    db.commit()

    body = client.get(
        f"/api/rolls?since=2026-08-01T00:00:00Z&group={tuesday.id}",
        headers=AUTH,
    ).json()
    assert [r["character_name"] for r in body["rolls"]] == ["Tues PC"]
    assert body["rolls"][0]["gaming_group_name"] == "Tuesday Group"
    assert body["rolls"][0]["gaming_group_id"] == tuesday.id


def test_rolls_include_characters_with_no_group(client):
    db = _session(client)
    char = _make_char(db, name="Ronin")
    _make_roll(db, char)
    db.commit()

    row = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert row["gaming_group_id"] is None
    assert row["gaming_group_name"] is None


def test_rolls_include_hidden_rolls(client):
    db = _session(client)
    char = _make_char(db)
    _make_roll(db, char, offset=0, is_hidden=True)
    db.commit()

    row = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert row["is_hidden"] is True


def test_rolls_include_hidden_and_unpublished_characters(client):
    """GM NPCs and drafts are rolls that happened; do not filter them out."""
    db = _session(client)
    npc = _make_char(
        db, name="Kakita Toshimoko", owner_discord_id=ADMIN_ID,
        is_hidden=True, is_published=False,
    )
    _make_roll(db, npc, actor_discord_id=ADMIN_ID)
    db.commit()

    body = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()
    assert [r["character_name"] for r in body["rolls"]] == ["Kakita Toshimoko"]


# ---------------------------------------------------------------------------
# GET /api/rolls - serialization
# ---------------------------------------------------------------------------


def test_roll_serialization_shape(client):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    char = _make_char(db, gaming_group_id=group.id)
    payload = {
        "title": "Etiquette",
        "formula": "7k3 + 5 (etiquette skill: 3)",
        "total": 38,
        "skill_rank": 3,
        "kept": [{"parts": [10, 7]}, {"parts": [9]}, {"parts": [6]}],
        "dropped": [{"parts": [5]}, {"value": 4}, 3],
        "bonuses": [{"label": "from Charming", "amount": 5}],
        "alternatives": [
            {
                "label": "open sincerity",
                "extra_flat": 0,
                "max_total": 15,
                "max_total_source": "Withdrawn",
            },
        ],
        "rolled_by": "Test User 1",
    }
    row = _make_roll(
        db, char, payload=payload, tn=25, impaired_at_roll=True,
        annotation="vs the magistrate",
        action_die_spent={"value": 4, "source": "initiative"},
    )
    db.commit()

    got = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]

    assert got["id"] == row.id
    assert got["created_at"].endswith("Z")
    assert got["updated_at"].endswith("Z")
    assert got["character_id"] == char.id
    assert got["character_name"] == "Bayushi Sadakichi"
    assert got["gaming_group_id"] == group.id
    assert got["gaming_group_name"] == "Tuesday Group"
    assert got["owner_discord_id"] == OWNER_ID
    assert got["actor_discord_id"] == OWNER_ID
    assert got["is_owner_roll"] is True
    assert got["roll_key"] == "skill:etiquette"
    assert got["label"] == "Etiquette"
    assert got["skill_rank"] == 3
    assert got["formula"] == "7k3 + 5 (etiquette skill: 3)"
    assert got["total"] == 38
    # A 10 that exploded into a 7 collapses to a single 17.
    assert got["kept"] == [17, 9, 6]
    assert got["dropped"] == [5, 4, 3]
    assert got["bonuses"] == [{"label": "from Charming", "value": 5}]
    assert got["alternatives"] == payload["alternatives"]
    assert got["tn"] == 25
    assert got["impaired_at_roll"] is True
    assert got["action_die_spent"] == {"value": 4, "source": "initiative"}
    assert got["is_hidden"] is False
    assert got["annotation"] == "vs the magistrate"
    assert got["rolled_by"] == "Test User 1"


def test_roll_label_matches_label_for_roll(client):
    """The API label is the same derivation the readonly modal shows."""
    db = _session(client)
    char = _make_char(db)
    payload = {"title": "Iaijutsu (Kakita)"}
    _make_roll(db, char, roll_key="knack:iaijutsu", payload=payload)
    db.commit()

    got = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["label"] == label_for_roll("knack:iaijutsu", payload) == "Iaijutsu (Kakita)"


def test_roll_serialization_tolerates_an_empty_payload(client):
    db = _session(client)
    char = _make_char(db)
    _make_roll(db, char, roll_key="wound_check", payload={})
    db.commit()

    got = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["skill_rank"] is None
    assert got["formula"] == ""
    assert got["total"] is None
    assert got["kept"] == [] and got["dropped"] == []
    assert got["bonuses"] == [] and got["alternatives"] == []
    assert "rolled_by" not in got
    # No payload title -> falls back to the explainer title for the key.
    assert got["label"] == label_for_roll("wound_check", {})


def test_roll_serialization_tolerates_a_malformed_payload(client):
    db = _session(client)
    char = _make_char(db)
    _make_roll(db, char, payload={
        "title": "Etiquette",
        "kept": "not a list",
        "dropped": [None, {"parts": ["x"]}, {"no_parts_no_value": 1}],
        "bonuses": ["nope", {"label": "bad", "amount": "x"}, {"amount": 3}],
        "alternatives": ["nope", {"label": "ok", "extra_flat": 5}],
    })
    db.commit()

    got = client.get(
        "/api/rolls?since=2026-08-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["kept"] == []
    # None and the no-parts/no-value dict are skipped; ["x"] sums to 0.
    assert got["dropped"] == [0, 0]
    assert got["bonuses"] == [{"label": "", "value": 3}]
    assert got["alternatives"] == [{"label": "ok", "extra_flat": 5}]


def test_bonus_value_key_is_accepted():
    """``amount`` is the stored key, but a payload using ``value`` works."""
    assert gm_api._bonuses({"bonuses": [{"label": "x", "value": 2}]}) == [
        {"label": "x", "value": 2},
    ]


def test_die_values_rejects_booleans():
    assert gm_api._die_values([True, 4]) == [4]


# ---------------------------------------------------------------------------
# skill_rank: the write-path stamp
# ---------------------------------------------------------------------------


def test_skill_rank_for_roll_skill(db):
    char = Character(name="X", skills={"etiquette": 3})
    assert skill_rank_for_roll("skill:etiquette", char) == 3


def test_skill_rank_for_roll_unbought_skill_is_zero(db):
    char = Character(name="X", skills={})
    assert skill_rank_for_roll("skill:etiquette", char) == 0


def test_skill_rank_for_roll_unknown_skill_is_none(db):
    char = Character(name="X", skills={"etiquette": 3})
    assert skill_rank_for_roll("skill:not_a_skill", char) is None


def test_skill_rank_for_roll_knack(db):
    char = Character(name="X", knacks={"iaijutsu": 4})
    assert skill_rank_for_roll("knack:iaijutsu", char) == 4


def test_skill_rank_for_roll_foreign_knack(db):
    char = Character(name="X", knacks={}, foreign_knacks={"athletics": 2})
    assert skill_rank_for_roll("knack:athletics", char) == 2


def test_skill_rank_for_roll_pontificate_variant_key(db):
    """``knack:pontificate:as:etiquette`` still resolves the knack rank."""
    char = Character(name="X", knacks={"pontificate": 3})
    assert skill_rank_for_roll("knack:pontificate:as:etiquette", char) == 3


def test_skill_rank_for_roll_unknown_knack_is_none(db):
    char = Character(name="X", knacks={"iaijutsu": 4})
    assert skill_rank_for_roll("knack:not_a_knack", char) is None


@pytest.mark.parametrize(
    "key", ["attack", "double_attack", "counterattack", "lunge"],
)
def test_skill_rank_for_roll_attack_variants(db, key):
    char = Character(name="X", attack=4, parry=2)
    assert skill_rank_for_roll(key, char) == 4


def test_skill_rank_for_roll_parry(db):
    char = Character(name="X", attack=4, parry=2)
    assert skill_rank_for_roll("parry", char) == 2


@pytest.mark.parametrize(
    "key", ["", None, "wound_check", "initiative", "ring:Fire", "freeform"],
)
def test_skill_rank_for_roll_has_no_rank(db, key):
    char = Character(name="X", skills={"etiquette": 3})
    assert skill_rank_for_roll(key, char) is None


def test_skill_rank_for_roll_null_columns(db):
    """Defensive: a row whose JSON columns are NULL must not blow up."""
    char = Character(
        name="X", skills=None, knacks=None, foreign_knacks=None,
        attack=None, parry=None,
    )
    assert skill_rank_for_roll("skill:etiquette", char) == 0
    assert skill_rank_for_roll("knack:iaijutsu", char) == 0
    assert skill_rank_for_roll("attack", char) == 0
    assert skill_rank_for_roll("parry", char) == 0


def test_create_roll_stamps_skill_rank(client):
    """POST /characters/{id}/rolls records the rank the character has now."""
    db = _session(client)
    char = _make_char(db, owner_discord_id=ADMIN_ID, skills={"etiquette": 3})
    db.commit()

    r = client.post(
        f"/characters/{char.id}/rolls",
        json={"roll_key": "skill:etiquette", "payload": {"title": "Etiquette"}},
    )
    assert r.status_code == 200

    got = client.get(
        "/api/rolls?since=2020-01-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["skill_rank"] == 3


def test_create_roll_omits_skill_rank_for_rankless_rolls(client):
    db = _session(client)
    char = _make_char(db, owner_discord_id=ADMIN_ID)
    db.commit()

    client.post(
        f"/characters/{char.id}/rolls",
        json={"roll_key": "wound_check", "payload": {"title": "Wound Check"}},
    )
    got = client.get(
        "/api/rolls?since=2020-01-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["skill_rank"] is None


def test_patch_roll_preserves_skill_rank(client):
    """A post-roll bonus toggle must not erase the create-time stamp."""
    db = _session(client)
    char = _make_char(db, owner_discord_id=ADMIN_ID, skills={"etiquette": 3})
    db.commit()

    created = client.post(
        f"/characters/{char.id}/rolls",
        json={"roll_key": "skill:etiquette", "payload": {"title": "Etiquette"}},
    ).json()
    r = client.patch(
        f"/characters/{char.id}/rolls/{created['id']}",
        json={"payload": {"title": "Etiquette", "total": 43}},
    )
    assert r.status_code == 200

    got = client.get(
        "/api/rolls?since=2020-01-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["skill_rank"] == 3
    assert got["total"] == 43


def test_patch_roll_keeps_a_client_supplied_rank(client):
    """The carry-forward must not clobber a rank already in the new payload."""
    db = _session(client)
    char = _make_char(db, owner_discord_id=ADMIN_ID, skills={"etiquette": 3})
    db.commit()

    created = client.post(
        f"/characters/{char.id}/rolls",
        json={"roll_key": "skill:etiquette", "payload": {"title": "Etiquette"}},
    ).json()
    client.patch(
        f"/characters/{char.id}/rolls/{created['id']}",
        json={"payload": {"title": "Etiquette", "skill_rank": 5}},
    )
    got = client.get(
        "/api/rolls?since=2020-01-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["skill_rank"] == 5


def test_patch_roll_with_no_prior_rank(client):
    """Rankless rolls take the carry-forward branch's else path cleanly."""
    db = _session(client)
    char = _make_char(db, owner_discord_id=ADMIN_ID)
    db.commit()

    created = client.post(
        f"/characters/{char.id}/rolls",
        json={"roll_key": "wound_check", "payload": {"title": "Wound Check"}},
    ).json()
    r = client.patch(
        f"/characters/{char.id}/rolls/{created['id']}",
        json={"payload": {"title": "Wound Check", "total": 20}},
    )
    assert r.status_code == 200
    got = client.get(
        "/api/rolls?since=2020-01-01T00:00:00Z", headers=AUTH,
    ).json()["rolls"][0]
    assert got["skill_rank"] is None
    assert got["total"] == 20


# ---------------------------------------------------------------------------
# GET /api/characters
# ---------------------------------------------------------------------------


def test_characters_empty(client):
    body = client.get("/api/characters", headers=AUTH).json()
    assert body == {"characters": [], "gaming_groups": []}


def test_characters_full_shape(client):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_char(
        db,
        gaming_group_id=group.id,
        editor_discord_ids=["editor_1"],
        skills={"etiquette": 3, "investigation": 2, "commerce": 0},
        knacks={"discern_honor": 2},
        foreign_knacks={"athletics": 1},
        attack=4,
        parry=3,
    )
    db.commit()

    body = client.get("/api/characters", headers=AUTH).json()
    assert body["gaming_groups"] == [{"id": group.id, "name": "Tuesday Group"}]
    got = body["characters"][0]
    assert got["name"] == "Bayushi Sadakichi"
    assert got["owner_discord_id"] == OWNER_ID
    assert got["editor_discord_ids"] == ["editor_1"]
    assert got["gaming_group_id"] == group.id
    assert got["gaming_group_name"] == "Tuesday Group"
    assert got["skills"] == {
        "etiquette": 3, "investigation": 2, "commerce": 0,
        "attack": 4, "parry": 3,
    }
    # School knacks and knacks bought from another school merge into one map.
    assert got["knacks"] == {"discern_honor": 2, "athletics": 1}


def test_characters_without_a_group(client):
    db = _session(client)
    _make_char(db, name="Ronin")
    db.commit()

    got = client.get("/api/characters", headers=AUTH).json()["characters"][0]
    assert got["gaming_group_id"] is None
    assert got["gaming_group_name"] is None


def test_characters_includes_hidden_drafts(client):
    db = _session(client)
    _make_char(db, name="Secret NPC", is_hidden=True, is_published=False)
    db.commit()

    body = client.get("/api/characters", headers=AUTH).json()
    assert [c["name"] for c in body["characters"]] == ["Secret NPC"]


def test_characters_null_json_columns(client):
    db = _session(client)
    char = Character(name="Bare", owner_discord_id=None)
    char.skills = None
    char.knacks = None
    char.foreign_knacks = None
    char.editor_discord_ids = None
    db.add(char)
    db.commit()

    got = client.get("/api/characters", headers=AUTH).json()["characters"][0]
    assert got["owner_discord_id"] is None
    assert got["editor_discord_ids"] == []
    assert got["knacks"] == {}
    assert got["skills"] == {"attack": 1, "parry": 1}
