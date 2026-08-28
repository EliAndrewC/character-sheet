"""Unit tests for the Discord roll bot.

Covers the signature gate on POST /discord/interactions, the PING/PONG
handshake Discord requires before it will save an interactions URL, the
character-resolution rules (pin, then owned-and-in-a-group), and the roll
command end to end - including that the row it writes is indistinguishable
from a sheet roll to GET /api/rolls.
"""

import json

import pytest
from nacl.signing import SigningKey

from app.models import Character, GamingGroup, RollHistory, User
from app.routes import discord as discord_route
from app.services import discord_api, discord_commands
from app.services.discord_commands import (
    CommandError,
    character_overrides,
    invoker_discord_id,
    resolve_character,
    roll_key_for_command,
    run_roll_command,
)
from tests.conftest import query_db


ADMIN_ID = "183026066498125825"   # matches conftest's ADMIN_DISCORD_IDS
PLAYER_ID = "player_discord_77"
APP_ID = "1490400739934212116"


@pytest.fixture()
def signing_key(monkeypatch):
    """A throwaway Discord application key pair for signing test requests."""
    key = SigningKey.generate()
    monkeypatch.setenv("DISCORD_APPLICATION_ID", APP_ID)
    monkeypatch.setenv(
        "DISCORD_PUBLIC_KEY", key.verify_key.encode().hex(),
    )
    return key


@pytest.fixture(autouse=True)
def _no_overrides(monkeypatch):
    """Tests opt in to a pin; none is configured by default."""
    monkeypatch.delenv(discord_commands.OVERRIDES_ENV_VAR, raising=False)


@pytest.fixture()
def _capture_discord_calls(monkeypatch):
    """Record follow-up edits instead of calling Discord."""
    sent = []

    def _fake(token, content, png=None, filename="l7r-roll.png"):
        sent.append({
            "token": token, "content": content,
            "png": png, "filename": filename,
        })
        return True

    monkeypatch.setattr(discord_api, "edit_original_response", _fake)
    return sent


def _post(client, key, body: dict, timestamp="1700000000", tamper=False):
    raw = json.dumps(body).encode()
    signature = key.sign(timestamp.encode() + raw).signature.hex()
    if tamper:
        signature = ("0" * 128)
    return client.post(
        "/discord/interactions",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": timestamp,
        },
    )


def _command(name="etiquette", discord_id=PLAYER_ID, in_guild=True):
    who = {"id": discord_id, "username": "someone"}
    body = {
        "type": 2,
        "id": "interaction_1",
        "token": "interaction_token_abc",
        "data": {"id": "cmd_1", "name": name, "type": 1},
    }
    body["member" if in_guild else "user"] = (
        {"user": who} if in_guild else who
    )
    return body


def _make_character(db, **kwargs):
    kwargs.setdefault("name", "Roll Tester")
    kwargs.setdefault("owner_discord_id", PLAYER_ID)
    kwargs.setdefault("school", "courtier")
    kwargs.setdefault("skills", {"etiquette": 1})
    kwargs.setdefault(
        "knacks", {"discern_honor": 1, "oppose_social": 1, "worldliness": 1},
    )
    char = Character(**kwargs)
    db.add(char)
    db.flush()
    return char


def _session(client):
    return client._test_session_factory()


# ---------------------------------------------------------------------------
# Signature gate + handshake
# ---------------------------------------------------------------------------


def test_ping_gets_a_pong(client, signing_key):
    r = _post(client, signing_key, {"type": 1})
    assert r.status_code == 200
    assert r.json() == {"type": 1}


def test_bad_signature_is_401(client, signing_key):
    r = _post(client, signing_key, {"type": 1}, tamper=True)
    assert r.status_code == 401


def test_signature_from_the_wrong_key_is_401(client, signing_key):
    r = _post(client, SigningKey.generate(), {"type": 1})
    assert r.status_code == 401


def test_missing_signature_headers_are_401(client, signing_key):
    r = client.post("/discord/interactions", content=b'{"type":1}')
    assert r.status_code == 401


def test_a_changed_body_invalidates_the_signature(client, signing_key):
    """The signature covers timestamp + body, so a replayed body fails."""
    raw = json.dumps({"type": 1}).encode()
    signature = signing_key.sign(b"1700000000" + raw).signature.hex()
    r = client.post(
        "/discord/interactions",
        content=json.dumps({"type": 2}).encode(),
        headers={
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": "1700000000",
        },
    )
    assert r.status_code == 401


def test_503_when_the_application_is_not_configured(client, monkeypatch):
    monkeypatch.delenv("DISCORD_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    r = client.post("/discord/interactions", content=b'{"type":1}')
    assert r.status_code == 503


def test_verify_signature_rejects_malformed_hex(monkeypatch):
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", "not-hex")
    assert discord_api.verify_signature("aa", "1", b"{}") is False


def test_verify_signature_without_a_public_key(monkeypatch):
    monkeypatch.delenv("DISCORD_PUBLIC_KEY", raising=False)
    assert discord_api.verify_signature("aa", "1", b"{}") is False


def test_invalid_json_body_is_400(client, signing_key):
    raw = b"not json"
    signature = signing_key.sign(b"1700000000" + raw).signature.hex()
    r = client.post(
        "/discord/interactions", content=raw,
        headers={
            "X-Signature-Ed25519": signature,
            "X-Signature-Timestamp": "1700000000",
        },
    )
    assert r.status_code == 400


def test_non_object_json_is_400(client, signing_key):
    r = _post(client, signing_key, ["not", "an", "object"])
    assert r.status_code == 400


def test_unsupported_interaction_type_answers_privately(client, signing_key):
    r = _post(client, signing_key, {"type": 99})
    body = r.json()
    assert body["type"] == 4
    assert body["data"]["flags"] == discord_route.FLAG_EPHEMERAL


# ---------------------------------------------------------------------------
# Who invoked it
# ---------------------------------------------------------------------------


def test_invoker_from_a_guild_member():
    assert invoker_discord_id({"member": {"user": {"id": "42"}}}) == "42"


def test_invoker_from_a_direct_message():
    assert invoker_discord_id({"user": {"id": "42"}}) == "42"


def test_invoker_missing():
    assert invoker_discord_id({}) is None
    assert invoker_discord_id({"member": {}}) is None


def test_unidentifiable_invoker_answers_privately(client, signing_key):
    body = _command()
    body.pop("member")
    r = _post(client, signing_key, body)
    assert r.json()["data"]["flags"] == discord_route.FLAG_EPHEMERAL


# ---------------------------------------------------------------------------
# Command name -> roll key
# ---------------------------------------------------------------------------


def test_roll_key_for_a_known_skill():
    assert roll_key_for_command("etiquette") == "skill:etiquette"


def test_roll_key_is_case_insensitive():
    assert roll_key_for_command("  Etiquette ") == "skill:etiquette"


def test_roll_key_for_an_unknown_command():
    assert roll_key_for_command("summon-a-dragon") is None
    assert roll_key_for_command("") is None


def test_unknown_command_answers_privately(client, signing_key):
    db = _session(client)
    _make_character(db, gaming_group_id=None)
    db.commit()
    r = _post(client, signing_key, _command(name="nonsense"))
    assert "do not know how to roll" in r.json()["data"]["content"]


# ---------------------------------------------------------------------------
# Character resolution
# ---------------------------------------------------------------------------


def test_overrides_parsing(monkeypatch):
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, " 111:22 , 333:44 ",
    )
    assert character_overrides() == {"111": 22, "333": 44}


@pytest.mark.parametrize(
    "raw", ["", "garbage", "111:", ":22", "111:abc", "111"],
)
def test_overrides_skip_malformed_entries(monkeypatch, raw):
    monkeypatch.setenv(discord_commands.OVERRIDES_ENV_VAR, raw)
    assert character_overrides() == {}


def test_resolve_uses_the_pin_even_without_a_group(client, monkeypatch):
    """The GM's case: pinned to a character that is in no gaming group."""
    db = _session(client)
    char = _make_character(
        db, name="Roll Tester", owner_discord_id=ADMIN_ID, gaming_group_id=None,
    )
    db.commit()
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"{ADMIN_ID}:{char.id}",
    )
    assert resolve_character(db, ADMIN_ID).id == char.id


def test_resolve_pin_beats_an_owned_grouped_character(client, monkeypatch):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    pinned = _make_character(db, name="Pinned", gaming_group_id=None)
    _make_character(db, name="In A Group", gaming_group_id=group.id)
    db.commit()
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"{PLAYER_ID}:{pinned.id}",
    )
    assert resolve_character(db, PLAYER_ID).name == "Pinned"


def test_resolve_pin_to_a_missing_character_explains_itself(client, monkeypatch):
    db = _session(client)
    monkeypatch.setenv(discord_commands.OVERRIDES_ENV_VAR, f"{PLAYER_ID}:9999")
    with pytest.raises(CommandError, match="pinned to character 9999"):
        resolve_character(db, PLAYER_ID)


def test_resolve_picks_the_owned_character_in_a_group(client):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(db, name="Ungrouped", gaming_group_id=None)
    _make_character(db, name="Grouped", gaming_group_id=group.id)
    db.commit()
    assert resolve_character(db, PLAYER_ID).name == "Grouped"


def test_resolve_ignores_other_peoples_characters(client):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(
        db, name="Someone Else", owner_discord_id="other", gaming_group_id=group.id,
    )
    db.commit()
    with pytest.raises(CommandError, match="could not find a character"):
        resolve_character(db, PLAYER_ID)


def test_resolve_with_no_characters_at_all(client):
    db = _session(client)
    with pytest.raises(CommandError, match="could not find a character"):
        resolve_character(db, PLAYER_ID)


def test_resolve_breaks_ties_on_most_recently_updated(client):
    from datetime import datetime

    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    older = _make_character(db, name="Older", gaming_group_id=group.id)
    newer = _make_character(db, name="Newer", gaming_group_id=group.id)
    older.updated_at = datetime(2026, 1, 1)
    newer.updated_at = datetime(2026, 6, 1)
    db.commit()
    assert resolve_character(db, PLAYER_ID).name == "Newer"


def test_no_character_answers_privately(client, signing_key):
    r = _post(client, signing_key, _command())
    body = r.json()
    assert body["type"] == 4
    assert body["data"]["flags"] == discord_route.FLAG_EPHEMERAL
    assert "could not find a character" in body["data"]["content"]


# ---------------------------------------------------------------------------
# Rolling
# ---------------------------------------------------------------------------


def test_run_roll_command_returns_content_and_payload(client):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(db, gaming_group_id=group.id, advantages=["charming"])
    db.commit()

    content, payload = run_roll_command(db, "etiquette", PLAYER_ID)
    assert payload["title"] == "Etiquette (Air)"
    assert payload["formula"].startswith("3k2 + 5 (etiquette skill: 1)")
    assert content == (
        f"**Roll Tester**: **{payload['total']}** Etiquette@1"
    )


def test_run_roll_command_records_the_roll(client):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    char = _make_character(db, gaming_group_id=group.id)
    db.commit()

    run_roll_command(db, "etiquette", PLAYER_ID)

    row = query_db(client, RollHistory).one()
    assert row.character_id == char.id
    assert row.roll_key == "skill:etiquette"
    assert row.actor_discord_id == PLAYER_ID
    assert row.is_owner_roll is True
    assert row.payload["skill_rank"] == 1
    assert row.impaired_at_roll is False


def test_slash_command_rolls_are_visible_to_the_gm_api(client, monkeypatch):
    """A slash-command row reads back exactly like a sheet row."""
    monkeypatch.setenv("ROLL_QUERY_TOKEN", "gm-token")
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(db, gaming_group_id=group.id)
    db.commit()

    content, _ = run_roll_command(db, "etiquette", PLAYER_ID)

    got = client.get(
        "/api/rolls?since=2000-01-01T00:00:00Z",
        headers={"Authorization": "Bearer gm-token"},
    ).json()["rolls"][0]
    assert got["roll_key"] == "skill:etiquette"
    assert got["label"] == "Etiquette (Air)"
    assert got["skill_rank"] == 1
    assert got["gaming_group_name"] == "Tuesday Group"
    assert str(got["total"]) in content


def test_admin_rolling_a_character_they_do_not_own_is_not_recorded(
    client, monkeypatch,
):
    """The sheet's blanket admin exclusion applies to slash commands too."""
    db = _session(client)
    char = _make_character(db, owner_discord_id=PLAYER_ID, gaming_group_id=None)
    db.commit()
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"{ADMIN_ID}:{char.id}",
    )

    content, payload = run_roll_command(db, "etiquette", ADMIN_ID)
    assert payload["total"] > 0
    assert content.startswith("**Roll Tester**")
    assert query_db(client, RollHistory).count() == 0


def test_owner_grants_still_record_as_a_non_owner_roll(client, monkeypatch):
    db = _session(client)
    owner = User(discord_id=PLAYER_ID, granted_account_ids=["friend_9"])
    db.add(owner)
    char = _make_character(db, gaming_group_id=None)
    db.commit()
    monkeypatch.setenv(
        discord_commands.OVERRIDES_ENV_VAR, f"friend_9:{char.id}",
    )

    run_roll_command(db, "etiquette", "friend_9")
    row = query_db(client, RollHistory).one()
    assert row.is_owner_roll is False
    assert row.actor_discord_id == "friend_9"


def test_party_effects_reach_a_slash_command_roll(client):
    """A 2nd Dan Priest ally grants the party a free raise on precepts."""
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(
        db, name="Priestly", owner_discord_id="priest_owner",
        school="priest", gaming_group_id=group.id,
        knacks={"conviction": 2, "otherworldliness": 2, "pontificate": 2},
    )
    _make_character(
        db, name="Roll Tester", gaming_group_id=group.id,
        school="priest",
        knacks={"conviction": 1, "otherworldliness": 1, "pontificate": 1},
        skills={"precepts": 2},
    )
    db.commit()

    _, payload = run_roll_command(db, "precepts", PLAYER_ID)
    labels = [b["label"] for b in payload["bonuses"]]
    assert any("Priest" in label for label in labels), labels


# ---------------------------------------------------------------------------
# The full interaction round trip
# ---------------------------------------------------------------------------


def test_command_defers_then_posts_the_card(
    client, signing_key, _capture_discord_calls,
):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(db, gaming_group_id=group.id)
    db.commit()

    r = _post(client, signing_key, _command())
    assert r.status_code == 200
    assert r.json() == {"type": 5}

    # TestClient runs background tasks before returning.
    assert len(_capture_discord_calls) == 1
    sent = _capture_discord_calls[0]
    assert sent["token"] == "interaction_token_abc"
    assert sent["content"].startswith("**Roll Tester**: **")
    assert sent["filename"] == "l7r-roll.png"
    assert sent["png"][:8] == b"\x89PNG\r\n\x1a\n"

    assert query_db(client, RollHistory).count() == 1


def test_command_works_in_a_direct_message(
    client, signing_key, _capture_discord_calls,
):
    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    _make_character(db, gaming_group_id=group.id)
    db.commit()

    r = _post(client, signing_key, _command(in_guild=False))
    assert r.json() == {"type": 5}
    assert len(_capture_discord_calls) == 1


def test_card_render_failure_still_posts_the_total(
    client, monkeypatch, _capture_discord_calls,
):
    """A broken renderer must not leave the invoker on "thinking..."."""
    import app.services.dice_card as dice_card

    def _boom(payload):
        raise RuntimeError("cairo exploded")

    monkeypatch.setattr(dice_card, "render_png", _boom)
    discord_route.deliver_card("tok", "**X**: **20** Etiquette@1", {"title": "x"})

    sent = _capture_discord_calls[0]
    assert sent["png"] is None
    assert sent["content"] == "**X**: **20** Etiquette@1"


# ---------------------------------------------------------------------------
# Outbound helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """An httpx.Client stand-in that replays a scripted list of results.

    Each entry is either a ``_FakeResponse`` or an exception to raise. The
    last entry repeats once the script runs out, so a test that wants "404
    forever" only has to say it once.
    """

    def __init__(self, script, captured):
        # The list is SHARED across instances on purpose: edit_original_response
        # opens a new client per attempt, so a per-instance copy would replay
        # the first scripted result forever and no retry could ever succeed.
        self._script = script
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def patch(self, url, **kwargs):
        self._captured.append({"url": url, **kwargs})
        result = (
            self._script.pop(0) if len(self._script) > 1 else self._script[0]
        )
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture()
def discord_http(monkeypatch):
    """Script discord_api's outbound PATCHes and capture what was sent."""
    captured = []

    def _install(*script):
        remaining = list(script)
        monkeypatch.setattr(
            discord_api.httpx, "Client",
            lambda *a, **kw: _FakeClient(remaining, captured),
        )
        return captured

    return _install


@pytest.fixture(autouse=True)
def _no_retry_sleeps(monkeypatch):
    """Keep the retry backoff's shape but not its wall-clock cost."""
    monkeypatch.setattr(
        discord_api, "FOLLOWUP_RETRY_DELAYS",
        tuple(0 for _ in discord_api.FOLLOWUP_RETRY_DELAYS),
    )


def test_edit_original_response_sends_multipart(discord_http, signing_key):
    """The PNG goes as files[0] with the JSON body in payload_json."""
    captured = discord_http(_FakeResponse())
    assert discord_api.edit_original_response("tok", "hi", b"PNGDATA") is True

    assert len(captured) == 1
    sent = captured[0]
    assert sent["url"].endswith(f"/webhooks/{APP_ID}/tok/messages/@original")
    body = json.loads(sent["data"]["payload_json"])
    assert body["content"] == "hi"
    assert body["attachments"] == [{"id": 0, "filename": "l7r-roll.png"}]
    assert sent["files"]["files[0]"][1] == b"PNGDATA"


def test_edit_original_response_without_a_file_sends_json(
    discord_http, signing_key,
):
    captured = discord_http(_FakeResponse())
    assert discord_api.edit_original_response("tok", "hi") is True
    assert captured[0]["json"] == {"content": "hi"}


def test_edit_original_response_retries_the_deferral_race(
    discord_http, signing_key,
):
    """The 404 a fresh deferral reliably returns must not strand the invoker.

    Discord has not finished creating the placeholder message when the
    follow-up leaves, so the first attempt gets "Unknown Webhook" even
    though the token is valid.
    """
    captured = discord_http(
        _FakeResponse(404, '{"message": "Unknown Webhook", "code": 10015}'),
        _FakeResponse(404, '{"message": "Unknown Webhook", "code": 10015}'),
        _FakeResponse(200),
    )
    assert discord_api.edit_original_response("tok", "hi", b"PNG") is True
    assert len(captured) == 3


def test_edit_original_response_gives_up_eventually(discord_http, signing_key):
    captured = discord_http(_FakeResponse(404, "Unknown Webhook"))
    assert discord_api.edit_original_response("tok", "hi") is False
    assert len(captured) == 1 + len(discord_api.FOLLOWUP_RETRY_DELAYS)


def test_edit_original_response_backs_off_between_attempts(
    discord_http, signing_key, monkeypatch,
):
    """Retries wait, so a slow deferral gets a real chance to land."""
    slept = []
    monkeypatch.setattr(discord_api, "FOLLOWUP_RETRY_DELAYS", (0.25, 0.5))
    monkeypatch.setattr(discord_api.time, "sleep", slept.append)

    discord_http(_FakeResponse(404, "Unknown Webhook"), _FakeResponse(200))
    assert discord_api.edit_original_response("tok", "hi") is True
    assert slept == [0.25]


def test_edit_original_response_does_not_retry_our_own_bugs(
    discord_http, signing_key,
):
    """A 403 will not improve on the second attempt."""
    captured = discord_http(_FakeResponse(403, "Missing Access"))
    assert discord_api.edit_original_response("tok", "hi") is False
    assert len(captured) == 1


def test_edit_original_response_retries_a_transport_error(
    discord_http, signing_key,
):
    import httpx

    captured = discord_http(
        httpx.ConnectError("no route to host"), _FakeResponse(200),
    )
    assert discord_api.edit_original_response("tok", "hi") is True
    assert len(captured) == 2


def test_edit_original_response_survives_a_transport_error(
    discord_http, signing_key,
):
    import httpx

    discord_http(httpx.ConnectError("no route to host"))
    assert discord_api.edit_original_response("tok", "hi") is False


def test_put_guild_commands(monkeypatch, signing_key):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot-token")
    captured = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "etiquette"}]

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def put(self, url, **kwargs):
            captured.update({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr(discord_api.httpx, "Client", lambda *a, **kw: _Client())
    got = discord_api.put_guild_commands("guild_1", [{"name": "etiquette"}])
    assert got == [{"name": "etiquette"}]
    assert captured["url"].endswith(f"/applications/{APP_ID}/guilds/guild_1/commands")
    assert captured["headers"]["Authorization"] == "Bot bot-token"


def test_set_interactions_endpoint_url(monkeypatch, signing_key):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot-token")
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"interactions_endpoint_url": "https://example.test/x"}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def patch(self, url, **kwargs):
            captured.update({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr(discord_api.httpx, "Client", lambda *a, **kw: _Client())
    got = discord_api.set_interactions_endpoint_url("https://example.test/x")
    assert got["interactions_endpoint_url"] == "https://example.test/x"
    assert captured["json"] == {
        "interactions_endpoint_url": "https://example.test/x",
    }


def test_bot_token_and_configured(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "  bot-token  ")
    assert discord_api.bot_token() == "bot-token"
    monkeypatch.delenv("DISCORD_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    assert discord_api.configured() is False


def test_party_member_dan_for_an_unknown_school(client):
    """A character with no school has no school knacks, so no Dan."""
    from app.services.party import party_member_dan

    db = _session(client)
    char = _make_character(db, school="", knacks={})
    assert party_member_dan(char) == 0


def test_hidden_party_members_are_invisible_to_other_players(client):
    """A hidden draft must not leak its party effects onto someone's roll."""
    from app.services.party import visible_party_members

    db = _session(client)
    group = GamingGroup(name="Tuesday Group")
    db.add(group)
    db.flush()
    mine = _make_character(db, name="Mine", gaming_group_id=group.id)
    _make_character(
        db, name="Secret Draft", owner_discord_id="someone_else",
        gaming_group_id=group.id, is_hidden=True,
    )
    _make_character(
        db, name="Published Ally", owner_discord_id="someone_else",
        gaming_group_id=group.id, is_hidden=False,
    )
    db.commit()

    seen = visible_party_members(db, mine, PLAYER_ID)
    assert [p.name for p in seen] == ["Published Ally"]
    # An admin sees drafts anywhere, so the GM's rolls include them.
    assert sorted(p.name for p in visible_party_members(db, mine, ADMIN_ID)) == [
        "Published Ally", "Secret Draft",
    ]


def test_no_party_lookup_without_a_gaming_group(client):
    from app.services.party import visible_party_members

    db = _session(client)
    solo = _make_character(db, gaming_group_id=None)
    db.commit()
    assert visible_party_members(db, solo, PLAYER_ID) == []
