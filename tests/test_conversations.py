"""Unit tests for the GM's open conversation and ``/discern-honor``.

``/api/conversation`` is the one WRITE surface of the GM API and has its own
secret; ``/discern-honor`` is a lookup into what it stored. The spec is
``discord-design/discern-honor-requirements.md`` - the properties gm-assistant
relies on (D5) are each pinned here by name.
"""

import json
from datetime import datetime, timedelta

import pytest
from nacl.signing import SigningKey

from app.models import (
    Character,
    Conversation,
    ConversationDiscernHonor,
    ConversationNpc,
    GamingGroup,
    RollHistory,
)
from app.routes import gm_api
from app.services import conversations, discord_api, discord_commands
from app.services.conversations import (
    CONVERSATION_TTL,
    discern_honor_reply,
    has_discern_honor,
    utcnow,
)


READ_TOKEN = "the-read-token"
WRITE_TOKEN = "the-write-token"
READ = {"Authorization": f"Bearer {READ_TOKEN}"}
WRITE = {"Authorization": f"Bearer {WRITE_TOKEN}"}

PLAYER_ID = "player_discord_77"
OTHER_ID = "player_discord_78"


@pytest.fixture(autouse=True)
def _tokens(monkeypatch):
    monkeypatch.setenv(gm_api.TOKEN_ENV_VAR, READ_TOKEN)
    monkeypatch.setenv(gm_api.WRITE_TOKEN_ENV_VAR, WRITE_TOKEN)
    monkeypatch.delenv(discord_commands.OVERRIDES_ENV_VAR, raising=False)


def _session(client):
    return client._test_session_factory()


@pytest.fixture()
def world(client):
    """A group with two PCs who have the knack and one who does not."""
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    other_group = GamingGroup(name="Monday Group")
    db.add_all([group, other_group])
    db.flush()
    asker = Character(
        name="Doji Asker", owner_discord_id=PLAYER_ID, school="courtier",
        knacks={"discern_honor": 2}, gaming_group_id=group.id,
    )
    second = Character(
        name="Kitsuki Second", owner_discord_id=OTHER_ID,
        foreign_knacks={"discern_honor": 1}, gaming_group_id=group.id,
    )
    without = Character(
        name="Hida Without", owner_discord_id="player_discord_79",
        knacks={"iaijutsu": 1}, gaming_group_id=group.id,
    )
    db.add_all([asker, second, without])
    db.commit()
    ids = {
        "group": group.id, "other_group": other_group.id,
        "asker": asker.id, "second": second.id, "without": without.id,
    }
    db.close()
    return ids


def _now_iso(delta=timedelta(0)):
    return (utcnow() + delta).isoformat() + "Z"


def _body(world, **overrides):
    body = {
        "conversation_id": "c-20260921-7f3a",
        "group": world["group"],
        "npc_ref": "opaque-ref",
        "opened_at": _now_iso(),
        "discern_honor": [
            {"character_id": world["asker"], "told": 4.5},
            {"character_id": world["second"], "told": 3.0},
        ],
    }
    body.update(overrides)
    return body


def _put(client, body, headers=WRITE):
    return client.put("/api/conversation", json=body, headers=headers)


def _get(client, group, headers=WRITE):
    return client.get(f"/api/conversation?group={group}", headers=headers)


def _entries(client, world):
    got = _get(client, world["group"]).json()["conversation"]
    return {e["character_id"]: e for e in got["discern_honor"]}


def _ask(client, character_id, now=None):
    db = _session(client)
    try:
        character = db.query(Character).filter(Character.id == character_id).one()
        reply = discern_honor_reply(db, character, now=now)
        db.commit()
        return reply
    finally:
        db.close()


# ---------------------------------------------------------------------------
# D1.1 - auth
# ---------------------------------------------------------------------------


def test_write_routes_503_when_the_write_token_is_unset(client, world, monkeypatch):
    """The read token being configured must not stand in for it."""
    monkeypatch.delenv(gm_api.WRITE_TOKEN_ENV_VAR)
    assert _put(client, _body(world), headers=READ).status_code == 503
    assert _put(client, _body(world)).status_code == 503
    r = client.delete("/api/conversation/c-1", headers=WRITE)
    assert r.status_code == 503


def test_write_routes_401_when_presented_with_the_read_token(client, world):
    assert _put(client, _body(world), headers=READ).status_code == 401
    assert _put(client, _body(world)).status_code == 200
    r = client.delete("/api/conversation/c-20260921-7f3a", headers=READ)
    assert r.status_code == 401
    assert _get(client, world["group"]).json()["conversation"] is not None


@pytest.mark.parametrize("headers", [
    {}, {"Authorization": WRITE_TOKEN}, {"Authorization": "Bearer nope"},
    {"Authorization": "Basic " + WRITE_TOKEN},
])
def test_write_routes_401_without_a_valid_bearer(client, world, headers):
    assert _put(client, _body(world), headers=headers).status_code == 401


def test_a_token_in_the_query_string_is_not_accepted(client, world):
    r = client.put(
        f"/api/conversation?token={WRITE_TOKEN}", json=_body(world),
    )
    assert r.status_code == 401


def test_get_accepts_either_token(client, world, monkeypatch):
    _put(client, _body(world))
    assert _get(client, world["group"], READ).status_code == 200
    assert _get(client, world["group"], WRITE).status_code == 200
    assert _get(client, world["group"], {}).status_code == 401
    # Either one alone is enough to read; neither is a 503.
    monkeypatch.delenv(gm_api.WRITE_TOKEN_ENV_VAR)
    assert _get(client, world["group"], READ).status_code == 200
    assert _get(client, world["group"], WRITE).status_code == 401
    monkeypatch.delenv(gm_api.TOKEN_ENV_VAR)
    assert _get(client, world["group"], READ).status_code == 503


def test_the_read_routes_do_not_accept_the_write_token(client):
    """Separate secrets in BOTH directions."""
    r = client.get("/api/characters", headers=WRITE)
    assert r.status_code == 401


def test_a_non_ascii_token_is_a_401_not_a_crash(client, world):
    request = client.build_request(
        "PUT", "/api/conversation", json=_body(world),
        headers=[(b"authorization", "Bearer café".encode("latin-1"))],
    )
    assert client.send(request).status_code == 401


# ---------------------------------------------------------------------------
# D1.2 / D1.4 - shape
# ---------------------------------------------------------------------------


def test_put_then_get_round_trips_the_conversation(client, world):
    opened = "2026-09-21T19:10:00-04:00"
    # Relative to now so the fixed instant above cannot expire the test.
    body = _body(world, opened_at=_now_iso())
    r = _put(client, body)
    assert r.status_code == 200
    got = _get(client, world["group"]).json()["conversation"]
    assert got == r.json()["conversation"]
    assert got["conversation_id"] == "c-20260921-7f3a"
    assert got["group"] == world["group"]
    assert got["npc_ref"] == "opaque-ref"
    assert got["opened_at"] == body["opened_at"]
    assert got["discern_honor"] == [
        {"character_id": world["asker"], "told": 4.5, "asked_at": None},
        {"character_id": world["second"], "told": 3.0, "asked_at": None},
    ]
    # An offset is converted to UTC, not dropped.
    far = _put(client, _body(world, opened_at=opened)).json()["conversation"]
    assert far["opened_at"] == "2026-09-21T23:10:00Z"
    assert far["expires_at"] == "2026-09-22T11:10:00Z"


def test_told_comes_back_exactly_as_sent(client, world):
    """3.0 stays a float, 3 stays an int: nothing touches the number."""
    _put(client, _body(world, discern_honor=[
        {"character_id": world["asker"], "told": 3.0},
        {"character_id": world["second"], "told": 3},
    ]))
    raw = _get(client, world["group"]).text
    told = [e["told"] for e in json.loads(raw)["conversation"]["discern_honor"]]
    assert told == [3.0, 3]
    assert [type(t) for t in told] == [float, int]


def test_get_is_null_when_nothing_is_open(client, world):
    r = _get(client, world["group"])
    assert r.status_code == 200
    assert r.json() == {"conversation": None}


@pytest.mark.parametrize("query", ["", "?group=", "?group=tuesday"])
def test_get_needs_an_integer_group(client, world, query):
    r = client.get("/api/conversation" + query, headers=WRITE)
    assert r.status_code == 400


def test_npc_ref_and_entries_are_optional(client, world):
    body = _body(world)
    del body["npc_ref"], body["discern_honor"]
    got = _put(client, body).json()["conversation"]
    assert got["npc_ref"] == "" and got["discern_honor"] == []
    got = _put(client, _body(world, npc_ref=None)).json()["conversation"]
    assert got["npc_ref"] == ""


@pytest.mark.parametrize("change,status", [
    ({"conversation_id": ""}, 400),
    ({"conversation_id": "   "}, 400),
    ({"conversation_id": 7}, 400),
    ({"conversation_id": "x" * 129}, 400),
    ({"group": "1"}, 400),
    ({"group": True}, 400),
    ({"group": 99999}, 404),
    ({"npc_ref": 5}, 400),
    ({"opened_at": None}, 400),
    ({"opened_at": "yesterday"}, 400),
    ({"opened_at": "2026-09-21T23:10:00"}, 400),      # naive
    ({"discern_honor": {"character_id": 1}}, 400),
    ({"discern_honor": ["nope"]}, 400),
    ({"discern_honor": [{"character_id": "1", "told": 4.5}]}, 400),
    ({"discern_honor": [{"character_id": 99999, "told": 4.5}]}, 400),
])
def test_put_refuses_a_malformed_body(client, world, change, status):
    r = _put(client, _body(world, **change))
    assert r.status_code == status
    assert r.json()["error"]


@pytest.mark.parametrize("told", [None, "4.5", True, [4.5]])
def test_put_refuses_a_told_that_is_not_a_number(client, world, told):
    r = _put(client, _body(world, discern_honor=[
        {"character_id": world["asker"], "told": told},
    ]))
    assert r.status_code == 400


def test_put_refuses_a_non_finite_told(client, world):
    raw = json.dumps(_body(world, discern_honor=[
        {"character_id": world["asker"], "told": float("nan")},
    ]))
    assert "NaN" in raw
    r = client.put(
        "/api/conversation", content=raw,
        headers={**WRITE, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_put_refuses_the_same_character_twice(client, world):
    r = _put(client, _body(world, discern_honor=[
        {"character_id": world["asker"], "told": 4.5},
        {"character_id": world["asker"], "told": 1.0},
    ]))
    assert r.status_code == 400


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"text"'])
def test_put_refuses_a_body_that_is_not_a_json_object(client, world, raw):
    r = client.put(
        "/api/conversation", content=raw,
        headers={**WRITE, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_a_refused_put_leaves_the_open_conversation_alone(client, world):
    _put(client, _body(world))
    _ask(client, world["asker"])
    before = _get(client, world["group"]).json()
    r = _put(client, _body(world, conversation_id="c-new", discern_honor=[
        {"character_id": 99999, "told": 1.0},
    ]))
    assert r.status_code == 400
    assert _get(client, world["group"]).json() == before


# ---------------------------------------------------------------------------
# D1.3 - the same id preserves, a new id replaces
# ---------------------------------------------------------------------------


def test_put_of_the_open_id_preserves_told_and_asked_at(client, world):
    _put(client, _body(world, discern_honor=[
        {"character_id": world["asker"], "told": 4.5},
    ]))
    _ask(client, world["asker"])
    first = _entries(client, world)[world["asker"]]
    assert first["asked_at"] is not None

    # A retry, or a resume after a crash, that recomputed different numbers.
    r = _put(client, _body(world, discern_honor=[
        {"character_id": world["asker"], "told": 1.0},
        {"character_id": world["second"], "told": 3.0},
    ]))
    assert r.status_code == 200
    entries = _entries(client, world)
    assert entries[world["asker"]] == first               # told AND asked_at
    assert entries[world["second"]] == {
        "character_id": world["second"], "told": 3.0, "asked_at": None,
    }
    assert "4.5" in _ask(client, world["asker"])


def test_put_of_the_open_id_never_drops_an_entry(client, world):
    _put(client, _body(world))
    _put(client, _body(world, discern_honor=[]))
    assert set(_entries(client, world)) == {world["asker"], world["second"]}


def test_put_of_a_new_id_replaces_the_groups_conversation(client, world):
    _put(client, _body(world))
    _ask(client, world["asker"])
    r = _put(client, _body(world, conversation_id="c-next", discern_honor=[
        {"character_id": world["asker"], "told": 2.5},
    ]))
    assert r.status_code == 200
    got = _get(client, world["group"]).json()["conversation"]
    assert got["conversation_id"] == "c-next"
    assert got["discern_honor"] == [
        {"character_id": world["asker"], "told": 2.5, "asked_at": None},
    ]
    db = _session(client)
    assert db.query(Conversation).count() == 1
    assert db.query(ConversationDiscernHonor).count() == 1
    db.close()


def test_one_conversation_per_group_not_one_overall(client, world):
    _put(client, _body(world))
    _put(client, _body(
        world, conversation_id="c-monday", group=world["other_group"],
        discern_honor=[],
    ))
    assert _get(client, world["group"]).json()["conversation"][
        "conversation_id"] == "c-20260921-7f3a"
    assert _get(client, world["other_group"]).json()["conversation"][
        "conversation_id"] == "c-monday"


def test_an_id_open_for_another_group_is_a_409(client, world):
    _put(client, _body(world))
    r = _put(client, _body(world, group=world["other_group"]))
    assert r.status_code == 409
    assert _get(client, world["other_group"]).json() == {"conversation": None}


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_closes_the_conversation(client, world):
    _put(client, _body(world))
    r = client.delete("/api/conversation/c-20260921-7f3a", headers=WRITE)
    assert r.status_code == 200
    assert r.json() == {"closed": "c-20260921-7f3a"}
    assert _get(client, world["group"]).json() == {"conversation": None}
    assert _ask(client, world["asker"]).startswith("No conversation is open")
    db = _session(client)
    assert db.query(ConversationDiscernHonor).count() == 0
    db.close()


def test_delete_of_an_unknown_id_is_404(client, world):
    r = client.delete("/api/conversation/never-opened", headers=WRITE)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# D3 - the replies
# ---------------------------------------------------------------------------


def test_reply_without_the_knack_comes_first(client, world):
    """Checked before the conversation, open or not."""
    assert "does not have the Discern Honor knack" in _ask(client, world["without"])
    _put(client, _body(world, discern_honor=[
        {"character_id": world["without"], "told": 4.5},
    ]))
    reply = _ask(client, world["without"])
    assert "does not have the Discern Honor knack" in reply
    assert "4.5" not in reply
    assert _entries(client, world)[world["without"]]["asked_at"] is None


def test_reply_when_no_conversation_is_open(client, world):
    assert _ask(client, world["asker"]) == (
        "No conversation is open right now - ask the GM."
    )


def test_reply_when_the_conversation_has_no_entry_for_them(client, world):
    _put(client, _body(world, discern_honor=[
        {"character_id": world["second"], "told": 3.0},
    ]))
    assert _ask(client, world["asker"]) == (
        "The GM will have to tell you this one - ask the GM."
    )
    assert _entries(client, world)[world["second"]]["asked_at"] is None


def test_reply_with_an_entry_is_the_told_value(client, world):
    _put(client, _body(world))
    assert _ask(client, world["asker"]) == (
        "Doji Asker's current read of this character's Honor is **4.5**."
    )
    # A foreign knack counts, and a whole number keeps its decimal place.
    assert _ask(client, world["second"]) == (
        "Kitsuki Second's current read of this character's Honor is **3.0**."
    )


def test_the_reply_never_shows_npc_ref_or_hints_at_accuracy(client, world):
    _put(client, _body(world, npc_ref="Otsuki-the-alias"))
    reply = _ask(client, world["asker"]).lower()
    assert "otsuki" not in reply
    for word in ("accura", "exact", "final", "roughly", "about", "approx",
                 "first", "again", "already", "conversations"):
        assert word not in reply


def test_a_character_in_no_group_has_no_open_conversation(client, world):
    db = _session(client)
    db.query(Character).filter(Character.id == world["asker"]).update(
        {"gaming_group_id": None})
    db.commit()
    db.close()
    _put(client, _body(world))
    assert _ask(client, world["asker"]).startswith("No conversation is open")


@pytest.mark.parametrize("knacks,foreign,expected", [
    ({"discern_honor": 1}, None, True),
    (None, {"discern_honor": 3}, True),
    ({"discern_honor": 0}, {}, False),
    ({"discern_honor": None}, None, False),
    ({"discern_honor": "two"}, None, False),
    ({}, {}, False),
    (None, None, False),
])
def test_has_discern_honor(knacks, foreign, expected):
    character = Character(name="x", knacks=knacks, foreign_knacks=foreign)
    assert has_discern_honor(character) is expected


# ---------------------------------------------------------------------------
# D3.5 - asking again
# ---------------------------------------------------------------------------


def test_asking_n_times_is_byte_identical_and_keeps_the_first_asked_at(client, world):
    _put(client, _body(world))
    first_time = utcnow().replace(microsecond=0)
    replies = [_ask(client, world["asker"], now=first_time)]
    stamped = _entries(client, world)[world["asker"]]["asked_at"]
    assert stamped == first_time.isoformat() + "Z"
    for minutes in range(1, 6):
        replies.append(_ask(
            client, world["asker"], now=first_time + timedelta(minutes=minutes),
        ))
    assert len({r.encode() for r in replies}) == 1
    assert _entries(client, world)[world["asker"]]["asked_at"] == stamped
    assert _entries(client, world)[world["second"]]["asked_at"] is None


# ---------------------------------------------------------------------------
# D4 - expiry
# ---------------------------------------------------------------------------


def test_an_expired_conversation_is_not_served_and_not_returned(client, world):
    _put(client, _body(
        world, opened_at=_now_iso(-CONVERSATION_TTL - timedelta(minutes=1)),
    ))
    assert _get(client, world["group"]).json() == {"conversation": None}
    assert _ask(client, world["asker"]).startswith("No conversation is open")
    db = _session(client)
    assert db.query(ConversationDiscernHonor).filter(
        ConversationDiscernHonor.asked_at.isnot(None)).count() == 0
    db.close()


def test_a_conversation_just_inside_the_window_is_still_open(client, world):
    _put(client, _body(
        world, opened_at=_now_iso(-CONVERSATION_TTL + timedelta(minutes=1)),
    ))
    assert _get(client, world["group"]).json()["conversation"] is not None
    assert "4.5" in _ask(client, world["asker"])


def test_expiry_is_measured_from_opened_at(client, world):
    _put(client, _body(world))
    late = utcnow() + CONVERSATION_TTL + timedelta(minutes=1)
    assert _ask(client, world["asker"], now=late).startswith("No conversation")
    db = _session(client)
    assert conversations.open_conversation(db, world["group"], late) is None
    assert conversations.open_conversation(db, world["group"]) is not None
    assert conversations.open_conversation(db, None) is None
    db.close()


def test_a_new_conversation_can_replace_an_expired_one(client, world):
    _put(client, _body(world, opened_at=_now_iso(-timedelta(days=2))))
    r = _put(client, _body(world, conversation_id="c-today"))
    assert r.status_code == 200
    assert _get(client, world["group"]).json()["conversation"][
        "conversation_id"] == "c-today"


# ---------------------------------------------------------------------------
# The command, through POST /discord/interactions
# ---------------------------------------------------------------------------


@pytest.fixture()
def signing_key(monkeypatch):
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "1490400739934212116")
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    return key


@pytest.fixture()
def discord_calls(monkeypatch):
    """Any follow-up to Discord would be a channel post. There must be none."""
    sent = []
    monkeypatch.setattr(
        discord_api, "edit_original_response",
        lambda *args, **kwargs: sent.append(args) or True,
    )
    return sent


def _interact(client, key, discord_id, options=None, kind=2):
    data = {"id": "cmd_1", "name": "discern-honor", "type": 1}
    if options is not None:
        data["options"] = options
    raw = json.dumps({
        "type": kind, "id": "interaction_1", "token": "interaction_token_abc",
        "data": data,
        "member": {"user": {"id": discord_id, "username": "someone"}},
    }).encode()
    timestamp = "1700000000"
    return client.post("/discord/interactions", content=raw, headers={
        "Content-Type": "application/json",
        "X-Signature-Ed25519": key.sign(timestamp.encode() + raw).signature.hex(),
        "X-Signature-Timestamp": timestamp,
    })


def _assert_private(response, discord_calls, client):
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == 4                       # an immediate message...
    assert body["data"]["flags"] == 1 << 6         # ...only the invoker sees
    assert discord_calls == []                     # no card, no channel post
    db = _session(client)
    assert db.query(RollHistory).count() == 0
    db.close()
    return body["data"]["content"]


def test_every_reply_path_is_ephemeral_and_writes_no_roll(
    client, world, signing_key, discord_calls,
):
    def ask(discord_id):
        return _assert_private(
            _interact(client, signing_key, discord_id), discord_calls, client,
        )

    assert "could not find a character" in ask("nobody_at_all")
    assert "does not have the Discern Honor knack" in ask("player_discord_79")
    assert "No conversation is open" in ask(PLAYER_ID)
    _put(client, _body(world, discern_honor=[
        {"character_id": world["second"], "told": 3.0},
    ]))
    assert "The GM will have to tell you" in ask(PLAYER_ID)
    assert "**3.0**" in ask(OTHER_ID)


def test_the_command_twice_is_identical_and_stamps_once(
    client, world, signing_key, discord_calls,
):
    _put(client, _body(world))
    first = _interact(client, signing_key, PLAYER_ID)
    stamped = _entries(client, world)[world["asker"]]["asked_at"]
    assert stamped is not None
    second = _interact(client, signing_key, PLAYER_ID)
    assert first.content == second.content
    assert "**4.5**" in _assert_private(second, discord_calls, client)
    assert _entries(client, world)[world["asker"]]["asked_at"] == stamped
    assert _entries(client, world)[world["second"]]["asked_at"] is None


def test_the_command_resolves_a_pinned_character(
    client, world, signing_key, discord_calls, monkeypatch,
):
    """Same resolution as the roll commands: the GM's pin wins."""
    gm = "183026066498125825"
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"{gm}:{world['second']}",
    )
    _put(client, _body(world))
    content = _assert_private(
        _interact(client, signing_key, gm), discord_calls, client,
    )
    assert content.startswith("Kitsuki Second's") and "**3.0**" in content


def test_the_command_needs_edit_access(
    client, world, signing_key, discord_calls, monkeypatch,
):
    """A pin to somebody else's character, for a non-admin, reads nothing."""
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"stranger_1:{world['asker']}",
    )
    _put(client, _body(world))
    content = _assert_private(
        _interact(client, signing_key, "stranger_1"), discord_calls, client,
    )
    assert "do not have edit access" in content
    assert "4.5" not in content
    assert _entries(client, world)[world["asker"]]["asked_at"] is None


def test_discern_honor_is_not_a_roll_command():
    assert discord_commands.roll_key_for_command("discern-honor") is None
    assert discord_commands.run_private_command(None, {"name": "etiquette"}, "x") is None
    assert discord_commands.run_private_command(None, None, "x") is None
    definition = next(
        c for c in discord_commands.command_definitions()
        if c["name"] == "discern-honor"
    )
    (npc,) = definition["options"]
    assert npc["name"] == "npc" and npc["type"] == 3
    assert npc["required"] is False and npc["autocomplete"] is True


def test_the_rules_text_typo_is_fixed():
    from app.game_data import SCHOOL_KNACKS

    text = SCHOOL_KNACKS["discern_honor"].rules_text
    assert "0.5 * (1k1 - 5)" in text and "1k1 - 0.5" not in text


# ---------------------------------------------------------------------------
# Several NPCs in one conversation (character-sheet#6)
# ---------------------------------------------------------------------------


def _npc(ref, name, entries, present=True):
    return {
        "npc_ref": ref, "name": name, "present": present,
        "discern_honor": [{"character_id": c, "told": t} for c, t in entries],
    }


def _multi(world, npcs, conversation_id="c-multi"):
    return {
        "conversation_id": conversation_id, "group": world["group"],
        "opened_at": _now_iso(), "npcs": npcs,
    }


def _two(world, **kw):
    return _multi(world, [
        _npc("ref-hideki", "Hideki", [(world["asker"], 4.1)]),
        _npc("ref-souma", "Souma", [(world["asker"], 2.5), (world["second"], 3.0)]),
    ], **kw)


def _ask_npc(client, character_id, npc):
    db = _session(client)
    try:
        character = db.query(Character).filter(Character.id == character_id).one()
        reply = discern_honor_reply(db, character, npc)
        db.commit()
        return reply
    finally:
        db.close()


def _npcs(client, world):
    return _get(client, world["group"]).json()["conversation"]["npcs"]


def test_multi_npc_put_round_trips_and_keeps_the_old_fields_for_the_primary(client, world):
    r = _put(client, _two(world))
    assert r.status_code == 200
    got = _get(client, world["group"]).json()["conversation"]
    assert got == r.json()["conversation"]
    assert got["npcs"] == [
        {"npc_ref": "ref-hideki", "name": "Hideki", "present": True, "discern_honor": [
            {"character_id": world["asker"], "told": 4.1, "asked_at": None},
        ]},
        {"npc_ref": "ref-souma", "name": "Souma", "present": True, "discern_honor": [
            {"character_id": world["asker"], "told": 2.5, "asked_at": None},
            {"character_id": world["second"], "told": 3.0, "asked_at": None},
        ]},
    ]
    # The deployed REPL reads the one-NPC shape: the primary NPC's.
    assert got["npc_ref"] == "ref-hideki"
    assert got["discern_honor"] == got["npcs"][0]["discern_honor"]


def test_the_old_shape_is_a_one_npc_list_without_a_name(client, world):
    got = _put(client, _body(world)).json()["conversation"]
    assert [(n["npc_ref"], n["name"], n["present"]) for n in got["npcs"]] == [
        ("opaque-ref", "", True),
    ]
    assert got["npcs"][0]["discern_honor"] == got["discern_honor"]


def test_a_conversation_with_no_npcs_serializes_empty(client, world):
    got = _put(client, _multi(world, [])).json()["conversation"]
    assert got["npcs"] == [] and got["npc_ref"] == "" and got["discern_honor"] == []


def test_present_defaults_to_true(client, world):
    npc = _npc("ref-hideki", "Hideki", [])
    del npc["present"]
    assert _put(client, _multi(world, [npc])).json()["conversation"]["npcs"][0]["present"] is True


@pytest.mark.parametrize("npcs", [
    {"npc_ref": "x"},
    ["nope"],
    [{"name": "Hideki"}],
    [{"npc_ref": "", "name": "Hideki"}],
    [{"npc_ref": "x" * 129, "name": "Hideki"}],
    [{"npc_ref": 5, "name": "Hideki"}],
    [{"npc_ref": "a"}],
    [{"npc_ref": "a", "name": "   "}],
    [{"npc_ref": "a", "name": "x" * 81}],
    [{"npc_ref": "a", "name": "Hideki", "present": "yes"}],
    [{"npc_ref": "a", "name": "Hideki"}, {"npc_ref": "a", "name": "Souma"}],
    [{"npc_ref": "a", "name": "Hideki", "discern_honor": [{"character_id": 99999, "told": 1}]}],
    [{"npc_ref": "a", "name": "Hideki"}, {"npc_ref": "b", "name": "hideki"}],
])
def test_put_refuses_malformed_npcs(client, world, npcs):
    r = _put(client, _multi(world, npcs))
    assert r.status_code == 400
    assert r.json()["error"]


def test_put_refuses_npcs_mixed_with_the_old_fields(client, world):
    for extra in ({"npc_ref": "x"}, {"discern_honor": []}):
        r = _put(client, {**_two(world), **extra})
        assert r.status_code == 400 and "not both" in r.json()["error"]


def test_a_departed_npc_may_share_a_name_with_a_present_one(client, world):
    r = _put(client, _multi(world, [
        _npc("a", "Souma", [], present=False), _npc("b", "souma", []),
    ]))
    assert r.status_code == 200


def test_a_reput_cannot_make_two_present_npcs_share_a_name(client, world):
    _put(client, _two(world))
    r = _put(client, _multi(world, [_npc("ref-new", "SOUMA", [])]))
    assert r.status_code == 400 and "SOUMA" in r.json()["error"]
    assert [n["name"] for n in _npcs(client, world)] == ["Hideki", "Souma"]
    # Once the first Souma leaves, the name is free.
    gone = _npc("ref-souma", "Souma", [], present=False)
    r = _put(client, _multi(world, [gone, _npc("ref-new", "SOUMA", [])]))
    assert r.status_code == 200


def test_reput_of_the_open_id_merges_npcs_by_ref(client, world):
    _put(client, _two(world))
    _ask_npc(client, world["asker"], "Souma")
    stamped = _npcs(client, world)[1]["discern_honor"][0]["asked_at"]
    assert stamped is not None
    # Reordered, Souma renamed and departed with a changed told value,
    # Hideki left out, a newcomer added, and the second PC added to Hideki.
    r = _put(client, _multi(world, [
        _npc("ref-new", "Kaede", [(world["asker"], 1.0)]),
        _npc("ref-souma", "Tsuruchi Souma", [(world["asker"], 9.9)], present=False),
        _npc("ref-hideki", "Hideki", [(world["asker"], 9.9), (world["second"], 2.0)]),
    ]))
    assert r.status_code == 200
    npcs = _npcs(client, world)
    assert [(n["npc_ref"], n["name"], n["present"]) for n in npcs] == [
        ("ref-hideki", "Hideki", True),
        ("ref-souma", "Tsuruchi Souma", False),
        ("ref-new", "Kaede", True),
    ]
    assert [(e["character_id"], e["told"]) for e in npcs[0]["discern_honor"]] == [
        (world["asker"], 4.1), (world["second"], 2.0),
    ]
    assert npcs[1]["discern_honor"][0] == {
        "character_id": world["asker"], "told": 2.5, "asked_at": stamped,
    }
    # Left out of a re-PUT: kept as it was.
    _put(client, _multi(world, [_npc("ref-new", "Kaede", [])]))
    assert [n["npc_ref"] for n in _npcs(client, world)] == ["ref-hideki", "ref-souma", "ref-new"]
    # A departed NPC can come back.
    _put(client, _multi(world, [_npc("ref-souma", "Souma", [], present=True)]))
    assert _npcs(client, world)[1]["present"] is True


def test_a_new_id_replaces_every_npc_and_delete_removes_them(client, world):
    _put(client, _two(world))
    _put(client, _two(world, conversation_id="c-next"))
    db = _session(client)
    assert db.query(ConversationNpc).count() == 2
    assert db.query(ConversationDiscernHonor).count() == 3
    db.close()
    assert client.delete("/api/conversation/c-next", headers=WRITE).status_code == 200
    db = _session(client)
    assert db.query(ConversationNpc).count() == 0
    assert db.query(ConversationDiscernHonor).count() == 0
    db.close()


def test_without_npc_every_present_npc_is_answered_and_stamped(client, world):
    _put(client, _multi(world, [
        _npc("ref-hideki", "Hideki", [(world["asker"], 4.1)]),
        _npc("ref-souma", "Souma", [(world["second"], 3.0)]),
        _npc("ref-gone", "Kaede", [(world["asker"], 7.0)], present=False),
    ]))
    first = _ask_npc(client, world["asker"], None)
    assert first == (
        "Doji Asker's current read of their Honor:\n"
        "- Hideki: **4.1**\n"
        "- Souma: the GM will have to tell you this one"
    )
    assert _ask_npc(client, world["asker"], "") == first
    npcs = _npcs(client, world)
    assert npcs[0]["discern_honor"][0]["asked_at"] is not None
    assert npcs[1]["discern_honor"][0]["asked_at"] is None     # the second PC's
    assert npcs[2]["discern_honor"][0]["asked_at"] is None     # departed: not asked
    assert "ref-" not in first and "Kaede" not in first


def test_one_present_npc_reads_as_it_always_did(client, world):
    _put(client, _multi(world, [
        _npc("ref-hideki", "Hideki", [(world["asker"], 4.1)]),
        _npc("ref-gone", "Kaede", [(world["asker"], 7.0)], present=False),
    ]))
    assert _ask_npc(client, world["asker"], None) == (
        "Doji Asker's current read of this character's Honor is **4.1**."
    )
    assert _ask_npc(client, world["second"], None) == (
        "The GM will have to tell you this one - ask the GM."
    )


def test_when_everyone_has_left(client, world):
    _put(client, _multi(world, [_npc("a", "Hideki", [(world["asker"], 4.1)], present=False)]))
    assert _ask_npc(client, world["asker"], None) == (
        "No one in this conversation is still here - ask the GM."
    )
    assert _ask_npc(client, world["asker"], "Hideki") == (
        "No one called Hideki is in this conversation. Present: nobody."
    )


def test_naming_an_npc_answers_for_that_one(client, world):
    _put(client, _two(world))
    assert _ask_npc(client, world["asker"], "  souma ") == (
        "Doji Asker's current read of Souma's Honor is **2.5**."
    )
    npcs = _npcs(client, world)
    assert npcs[0]["discern_honor"][0]["asked_at"] is None
    assert npcs[1]["discern_honor"][0]["asked_at"] is not None
    assert _ask_npc(client, world["second"], "Hideki") == (
        "The GM will have to tell you this one - ask the GM."
    )
    assert _ask_npc(client, world["asker"], "Kaede") == (
        "No one called Kaede is in this conversation. Present: Hideki, Souma."
    )
    assert _ask_npc(client, world["asker"], "x" * 200).startswith(
        f"No one called {'x' * 80} is"
    )


def test_a_departed_npc_cannot_be_named_but_keeps_its_asks(client, world):
    _put(client, _two(world))
    _ask_npc(client, world["asker"], "Hideki")
    _put(client, _multi(world, [_npc("ref-hideki", "Hideki", [], present=False)]))
    assert _ask_npc(client, world["asker"], "Hideki") == (
        "No one called Hideki is in this conversation. Present: Souma."
    )
    assert _npcs(client, world)[0]["discern_honor"][0]["asked_at"] is not None


def test_an_old_shape_npc_beside_named_ones_is_this_character(client, world):
    """Only a mix of the two shapes on one id makes a nameless NPC appear
    beside named ones; it still reads sensibly and is never offered."""
    _put(client, _multi(world, [_npc("ref-hideki", "Hideki", [(world["asker"], 4.1)])]))
    _put(client, {
        "conversation_id": "c-multi", "group": world["group"], "opened_at": _now_iso(),
        "npc_ref": "", "discern_honor": [{"character_id": world["asker"], "told": 2.0}],
    })
    assert _ask_npc(client, world["asker"], None).endswith("- this character: **2.0**")
    assert "Present: Hideki." in _ask_npc(client, world["asker"], "Kaede")
    db = _session(client)
    asker = db.query(Character).filter(Character.id == world["asker"]).one()
    assert conversations.present_npc_names(db, asker) == ["Hideki"]
    db.close()


def test_the_command_takes_the_npc_option(client, world, signing_key, discord_calls):
    _put(client, _two(world))
    content = _assert_private(_interact(
        client, signing_key, PLAYER_ID,
        options=[{"name": "npc", "type": 3, "value": "Hideki"}],
    ), discord_calls, client)
    assert content == "Doji Asker's current read of Hideki's Honor is **4.1**."
    content = _assert_private(
        _interact(client, signing_key, PLAYER_ID), discord_calls, client,
    )
    assert "- Hideki: **4.1**" in content and "- Souma: **2.5**" in content


def _complete(client, key, discord_id, typed):
    r = _interact(client, key, discord_id, kind=4, options=[
        {"name": "npc", "type": 3, "value": typed, "focused": True},
    ])
    assert r.status_code == 200 and r.json()["type"] == 8
    return [c["value"] for c in r.json()["data"]["choices"]]


def test_npc_autocomplete_offers_the_present_npcs_of_the_askers_group(
    client, world, signing_key,
):
    assert _complete(client, signing_key, PLAYER_ID, "") == []      # nothing open
    _put(client, _multi(world, [
        _npc("a", "Hideki", []), _npc("b", "Souma", []),
        _npc("c", "Kaede", [], present=False), _npc("d", "Tsuruchi Shiro", []),
    ]))
    assert _complete(client, signing_key, PLAYER_ID, "") == ["Hideki", "Souma", "Tsuruchi Shiro"]
    assert _complete(client, signing_key, PLAYER_ID, "s") == ["Souma", "Tsuruchi Shiro"]
    assert _complete(client, signing_key, PLAYER_ID, "SHI") == ["Tsuruchi Shiro"]
    assert _complete(client, signing_key, PLAYER_ID, "kae") == []     # departed
    # No character, or one in another group, is offered nothing.
    assert _complete(client, signing_key, "nobody_at_all", "") == []
    db = _session(client)
    db.query(Character).filter(Character.id == world["second"]).one().gaming_group_id = (
        world["other_group"]
    )
    db.commit()
    db.close()
    assert _complete(client, signing_key, OTHER_ID, "") == []


def test_npc_autocomplete_needs_edit_access(client, world, signing_key, monkeypatch):
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"stranger_1:{world['asker']}",
    )
    _put(client, _two(world))
    assert _complete(client, signing_key, "stranger_1", "") == []


def test_roll_autocomplete_is_unchanged(client, signing_key):
    raw = json.dumps({
        "type": 4, "id": "i", "token": "t",
        "data": {"id": "c", "name": "roll", "type": 1, "options": [
            {"name": "skill", "type": 3, "value": "etiq", "focused": True},
        ]},
        "member": {"user": {"id": PLAYER_ID, "username": "someone"}},
    }).encode()
    r = client.post("/discord/interactions", content=raw, headers={
        "Content-Type": "application/json",
        "X-Signature-Ed25519": signing_key.sign(b"1700000000" + raw).signature.hex(),
        "X-Signature-Timestamp": "1700000000",
    })
    assert [c["value"] for c in r.json()["data"]["choices"]] == ["etiquette"]
