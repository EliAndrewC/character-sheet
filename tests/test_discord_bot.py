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
    run_command,
)
from tests.conftest import query_db


def run_roll_command(db, name, discord_id, **options):
    """Run ``/name`` with ``options``, shaped as Discord sends them."""
    data = {"name": name, "options": [
        {"name": k, "value": v} for k, v in options.items()
    ]}
    return run_command(db, data, discord_id)


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


# ===========================================================================
# The full command set: /roll, per-skill, three knacks, /initiative, void
# ===========================================================================


from app.game_data import COMBAT_SKILLS, SCHOOL_KNACKS, SCHOOLS, SKILLS  # noqa: E402
from app.services.discord_commands import (                              # noqa: E402
    KNACK_COMMANDS,
    autocomplete_skills,
    command_definitions,
    command_names,
    focused_option_value,
)


def _grouped(db, **kwargs):
    """A character the PLAYER owns and is playing (in a gaming group)."""
    group = GamingGroup(name=kwargs.pop("group_name", "Tuesday Group"))
    db.add(group)
    db.flush()
    for ring in ("air", "fire", "earth", "water", "void"):
        kwargs.setdefault(f"ring_{ring}", 3)
    kwargs.setdefault("current_void_points", 3)
    char = _make_character(db, gaming_group_id=group.id, **kwargs)
    db.commit()
    return char


def _akodo(db, **kwargs):
    """No Worldliness, so the only void is what the test sets."""
    kwargs.setdefault("school", "akodo_bushi")
    kwargs.setdefault("knacks", {"double_attack": 1, "feint": 1, "iaijutsu": 1})
    return _grouped(db, **kwargs)


def _no_dice(monkeypatch):
    """Make any attempt to roll fail the test: a refusal must not roll."""
    def boom(*a, **kw):
        raise AssertionError("dice were rolled for a command that was refused")

    monkeypatch.setattr(discord_commands, "execute_roll", boom)
    monkeypatch.setattr(discord_commands, "execute_initiative", boom)


# --- C1: the command set is derived, and guarded ---------------------------


def test_the_registered_set_is_exactly_skills_plus_three_knacks_plus_two():
    """C1.3. Moving attack into SKILLS, or adding a knack casually, must turn
    this red rather than quietly register a command."""
    assert set(command_names()) == (
        set(SKILLS) | {"oppose-social", "oppose-knowledge", "commune"}
        | {"roll", "initiative"}
    )
    assert len(command_names()) == len(set(command_names())) == 23
    assert set(KNACK_COMMANDS.values()) == {
        "oppose_social", "oppose_knowledge", "commune",
    }


def test_no_combat_skill_is_reachable_through_any_command():
    assert not set(COMBAT_SKILLS) & set(SKILLS)
    reachable = {roll_key_for_command(n) for n in command_names()}
    reachable |= {
        roll_key_for_command("roll", {"skill": ident})
        for ident in list(SKILLS) + list(COMBAT_SKILLS) + list(SCHOOL_KNACKS)
    }
    reachable.discard(None)
    allowed = (
        {f"skill:{s}" for s in SKILLS}
        | {f"knack:{k}" for k in KNACK_COMMANDS.values()} | {"initiative"}
    )
    assert reachable == allowed
    for combat in COMBAT_SKILLS:
        assert roll_key_for_command(combat) is None
        assert roll_key_for_command("roll", {"skill": combat}) is None
    assert roll_key_for_command("iaijutsu") is None


def test_command_names_satisfy_discords_rules():
    import re

    for definition in command_definitions():
        assert re.fullmatch(r"[a-z0-9_-]{1,32}", definition["name"])
        assert 1 <= len(definition["description"]) <= 100
        assert definition["type"] == 1


def test_every_roll_takes_void_and_initiative_does_not():
    by_name = {d["name"]: d for d in command_definitions()}
    for name, definition in by_name.items():
        option_names = [o["name"] for o in definition["options"]]
        if name == "initiative":
            # rules/03-combat.md: initiative is rolled "without spending
            # void points".
            assert option_names == []
        elif name == "roll":
            assert option_names == ["skill", "void"]
        else:
            assert option_names == ["void"]
    skill = by_name["roll"]["options"][0]
    assert skill["required"] is True and skill["autocomplete"] is True
    void = by_name["etiquette"]["options"][0]
    assert void["type"] == 4 and void["required"] is False and void["min_value"] == 0
    assert "on top of" in by_name["commune"]["options"][0]["description"]


def test_knack_commands_are_hyphenated_but_their_keys_are_not():
    assert roll_key_for_command("oppose-social") == "knack:oppose_social"
    assert roll_key_for_command("oppose-knowledge") == "knack:oppose_knowledge"
    assert roll_key_for_command("commune") == "knack:commune"
    assert roll_key_for_command("oppose_social") is None
    assert roll_key_for_command("initiative") == "initiative"


# --- C2: /roll autocompletion ----------------------------------------------


def test_autocomplete_with_nothing_typed_lists_every_skill():
    choices = autocomplete_skills("")
    assert len(choices) == len(SKILLS) <= 25
    assert {c["value"] for c in choices} == set(SKILLS)
    assert [c["name"] for c in choices] == sorted(c["name"] for c in choices)
    assert autocomplete_skills(None) == choices


def test_autocomplete_is_case_insensitive_prefix_first_then_substring():
    names = [c["name"] for c in autocomplete_skills("IN")]
    prefix = [n for n in names if n.lower().startswith("in")]
    assert prefix and names[:len(prefix)] == prefix
    assert all("in" in n.lower() for n in names)
    assert len(names) > len(prefix)            # e.g. "Sincerity" by substring
    assert autocomplete_skills("sinc") == [
        {"name": "Sincerity", "value": "sincerity"},
    ]


def test_autocomplete_offers_skills_only_never_knacks_or_combat():
    assert autocomplete_skills("commune") == []
    assert autocomplete_skills("oppose") == []
    assert autocomplete_skills("attack") == []


def test_autocomplete_never_errors():
    class Hostile:
        def __str__(self):
            raise RuntimeError("no")

    assert autocomplete_skills(Hostile()) == autocomplete_skills("")


def test_focused_option_value():
    data = {"options": [
        {"name": "void", "value": 1},
        {"name": "skill", "value": "eti", "focused": True},
    ]}
    assert focused_option_value(data) == "eti"
    assert focused_option_value({}) == ""
    assert focused_option_value({"options": ["junk"]}) == ""


def test_autocomplete_interaction_answers_with_type_8(client, signing_key):
    body = _command(name="roll")
    body["type"] = 4
    body["data"]["options"] = [{"name": "skill", "value": "eti", "focused": True}]
    r = _post(client, signing_key, body)
    assert r.status_code == 200
    assert r.json() == {
        "type": 8,
        "data": {"choices": [{"name": "Etiquette", "value": "etiquette"}]},
    }


def test_autocomplete_needs_no_character_and_no_identity(client, signing_key):
    body = _command(name="roll")
    body["type"] = 4
    del body["member"]
    assert len(_post(client, signing_key, body).json()["data"]["choices"]) == len(SKILLS)


def test_roll_accepts_the_id_or_the_display_name(client):
    db = _session(client)
    _akodo(db, skills={"sincerity": 2})
    by_id, _ = run_roll_command(db, "roll", PLAYER_ID, skill="sincerity")
    by_name, _ = run_roll_command(db, "roll", PLAYER_ID, skill=" Sincerity ")
    assert by_id.endswith("Sincerity@2") and by_name.endswith("Sincerity@2")


def test_a_hand_typed_unknown_skill_is_refused_privately(
    client, signing_key, _capture_discord_calls,
):
    db = _session(client)
    _akodo(db)
    body = _command(name="roll")
    body["data"]["options"] = [{"name": "skill", "value": "basket weaving"}]
    r = _post(client, signing_key, body).json()
    assert r["type"] == 4 and r["data"]["flags"] == 64
    assert "basket weaving" in r["data"]["content"]
    assert _capture_discord_calls == []
    assert query_db(client, RollHistory).count() == 0


def test_roll_with_no_skill_at_all(client):
    db = _session(client)
    _akodo(db)
    with pytest.raises(CommandError):
        run_roll_command(db, "roll", PLAYER_ID)


# --- C3 / R1: void on a command ---------------------------------------------


def test_a_void_spend_comes_off_the_persisted_character(client):
    db = _session(client)
    char = _akodo(db, skills={"sincerity": 3}, current_temp_void_points=1)
    content, payload = run_roll_command(db, "sincerity", PLAYER_ID, void=2)

    assert content == f"**Roll Tester**: **{payload['total']}** Sincerity@3 (2 void)"
    assert "Rolled +2k2 from 2 spent void points" in payload["extras"]
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_temp_void_points == 0      # temporary first
    assert fresh.current_void_points == 2
    assert fresh.tracking_rev == 1                  # any open tab is now stale


def test_a_void_roll_is_recorded_exactly_as_it_was_posted(client, monkeypatch):
    """R1.4 / R5.1: same payload in roll_history, reachable via /api/rolls."""
    monkeypatch.setenv("ROLL_QUERY_TOKEN", "gm-token")
    db = _session(client)
    _akodo(db, skills={"sincerity": 3})
    _, payload = run_roll_command(db, "sincerity", PLAYER_ID, void=1)

    row = query_db(client, RollHistory).one()
    assert row.payload == payload
    assert row.roll_key == "skill:sincerity"
    got = client.get(
        "/api/rolls?since=2000-01-01T00:00:00Z",
        headers={"Authorization": "Bearer gm-token"},
    ).json()["rolls"][0]
    assert got["total"] == payload["total"]
    assert got["skill_rank"] == 3
    assert len(got["kept"]) == len(payload["kept"])


def test_a_plain_roll_is_unchanged_and_spends_nothing(client):
    db = _session(client)
    char = _akodo(db, skills={"sincerity": 3})
    content, payload = run_roll_command(db, "sincerity", PLAYER_ID)
    assert content == f"**Roll Tester**: **{payload['total']}** Sincerity@3"
    assert "(" not in content
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 3 and fresh.tracking_rev == 0
    assert run_roll_command(db, "sincerity", PLAYER_ID, void=0)[0].endswith("@3")


@pytest.mark.parametrize("void,held,needle", [
    (3, 2, "has 2 void points, not 3"),                 # cannot afford it
    (4, 9, "at most 3 void points on a single roll"),   # over the per-roll cap
])
def test_a_refused_spend_names_the_number_and_leaves_no_trace(
    client, monkeypatch, void, held, needle,
):
    db = _session(client)
    char = _akodo(db, current_void_points=held)
    _no_dice(monkeypatch)
    with pytest.raises(CommandError) as exc:
        run_roll_command(db, "etiquette", PLAYER_ID, void=void)
    assert needle in str(exc.value)
    assert "Nothing was rolled" in str(exc.value)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == held
    assert fresh.tracking_rev == 0
    assert query_db(client, RollHistory).count() == 0


def test_a_refusal_is_ephemeral_and_posts_nothing(
    client, signing_key, _capture_discord_calls,
):
    db = _session(client)
    _akodo(db, current_void_points=0)
    body = _command()
    body["data"]["options"] = [{"name": "void", "value": 1}]
    r = _post(client, signing_key, body).json()
    assert r["type"] == 4 and r["data"]["flags"] == 64
    assert "has 0 void points" in r["data"]["content"]
    assert _capture_discord_calls == []


@pytest.mark.parametrize("bad", [-1, "lots", 1.5e400])
def test_a_nonsense_void_count_is_refused(client, monkeypatch, bad):
    db = _session(client)
    _akodo(db)
    _no_dice(monkeypatch)
    with pytest.raises(CommandError):
        run_roll_command(db, "etiquette", PLAYER_ID, void=bad)


def test_a_boolean_void_is_ignored_rather_than_read_as_one(client):
    db = _session(client)
    char = _akodo(db)
    run_roll_command(db, "etiquette", PLAYER_ID, void=True)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 3


def test_discordant_characters_cannot_spend_void_on_a_skill(client, monkeypatch):
    db = _session(client)
    char = _akodo(db, disadvantages=["discordant"])
    _no_dice(monkeypatch)
    with pytest.raises(CommandError) as exc:
        run_roll_command(db, "etiquette", PLAYER_ID, void=1)
    assert "Discordant" in str(exc.value)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 3


def test_school_consequences_fire_on_a_command_spend(client):
    db = _session(client)
    char = _grouped(
        db, school="matsu_bushi", attack=2,
        knacks=dict.fromkeys(SCHOOLS["matsu_bushi"].school_knacks, 3),
    )
    run_roll_command(db, "etiquette", PLAYER_ID, void=2)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.adventure_state["matsu_banked_wc_bonuses"] == [6, 6]


def test_nothing_is_spent_if_recording_fails(client, monkeypatch):
    """R1.3: all-or-nothing. The spend and the row are one transaction."""
    db = _session(client)
    char = _akodo(db)

    def boom(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(discord_commands, "_record", boom)
    with pytest.raises(RuntimeError):
        run_roll_command(db, "etiquette", PLAYER_ID, void=2)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 3
    assert query_db(client, RollHistory).count() == 0


def test_a_gm_on_a_pinned_character_spends_void_but_leaves_no_row(
    client, monkeypatch,
):
    """C5.3: the no-history rule is about the record, not about the dice."""
    db = _session(client)
    char = _akodo(db)
    monkeypatch.setenv(discord_commands.OVERRIDES_ENV_VAR, f"{ADMIN_ID}:{char.id}")
    content, _ = run_roll_command(db, "etiquette", ADMIN_ID, void=1)
    assert content.endswith("(1 void)")
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 2
    assert query_db(client, RollHistory).count() == 0


def test_a_command_cannot_write_to_a_character_the_invoker_cannot_edit(
    client, monkeypatch,
):
    """C5.2. Resolution only returns owned or pinned characters today; this
    is what stops a later change to it from becoming a write hole."""
    db = _session(client)
    char = _akodo(db)
    monkeypatch.setenv(discord_commands.OVERRIDES_ENV_VAR, f"stranger_5:{char.id}")
    _no_dice(monkeypatch)
    with pytest.raises(CommandError) as exc:
        run_roll_command(db, "etiquette", "stranger_5", void=1)
    assert "edit access" in str(exc.value)
    with pytest.raises(CommandError):
        run_roll_command(db, "initiative", "stranger_5")
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 3 and fresh.action_dice in ([], None)


def test_resolution_never_returns_someone_elses_character(client):
    db = _session(client)
    _akodo(db, owner_discord_id="somebody_else", editor_discord_ids=[PLAYER_ID])
    with pytest.raises(CommandError):
        resolve_character(db, PLAYER_ID)


# --- R3: knacks --------------------------------------------------------------


def _kitsune(db, **kwargs):
    kwargs.setdefault("school", "kitsune_warden")
    kwargs.setdefault("school_ring_choice", "Water")
    kwargs.setdefault(
        "knacks", dict.fromkeys(SCHOOLS["kitsune_warden"].school_knacks, 2))
    return _grouped(db, **kwargs)


def test_oppose_social_rolls_and_records_like_a_skill(client):
    db = _session(client)
    _grouped(db, knacks={"discern_honor": 1, "oppose_social": 3, "worldliness": 1})
    content, payload = run_roll_command(db, "oppose-social", PLAYER_ID)
    assert content == f"**Roll Tester**: **{payload['total']}** {payload['title']}"
    assert payload["title"].startswith("Oppose Social")
    row = query_db(client, RollHistory).one()
    assert row.roll_key == "knack:oppose_social"
    assert row.payload["skill_rank"] == 3


def test_a_knack_the_character_does_not_have(client, monkeypatch):
    db = _session(client)
    _akodo(db)
    _no_dice(monkeypatch)
    for command, name in (("commune", "Commune"),
                          ("oppose-knowledge", "Oppose Knowledge")):
        with pytest.raises(CommandError) as exc:
            run_roll_command(db, command, PLAYER_ID)
        assert str(exc.value) == f"Roll Tester does not have the {name} knack."


def test_commune_charges_its_activation_point(client):
    db = _session(client)
    char = _kitsune(db, current_void_points=2)
    content, payload = run_roll_command(db, "commune", PLAYER_ID)
    assert content == (
        f"**Roll Tester**: **{payload['total']}** Commune (Water) "
        "(1 void to activate)"
    )
    assert payload["extras"][0] == "1 void point spent to activate Commune (Water)"
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 1


def test_commune_is_refused_outright_when_the_point_cannot_be_paid(
    client, monkeypatch,
):
    db = _session(client)
    _kitsune(db, current_void_points=0)
    _no_dice(monkeypatch)
    with pytest.raises(CommandError) as exc:
        run_roll_command(db, "commune", PLAYER_ID)
    assert "costs 1 void point to make" in str(exc.value)
    assert "has 0" in str(exc.value)
    assert query_db(client, RollHistory).count() == 0


def test_commune_checks_an_optional_spend_against_what_remains(
    client, monkeypatch,
):
    """C3.4: cap 3, holding 2 -> exactly 1 can go into the roll."""
    db = _session(client)
    char = _kitsune(db, current_void_points=2)
    real = discord_commands.execute_roll
    _no_dice(monkeypatch)
    with pytest.raises(CommandError) as exc:
        run_roll_command(db, "commune", PLAYER_ID, void=2)
    assert "only 1 can go into the roll, not 2" in str(exc.value)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 2

    monkeypatch.setattr(discord_commands, "execute_roll", real)
    content, payload = run_roll_command(db, "commune", PLAYER_ID, void=1)
    assert content.endswith("Commune (Water) (1 void to activate, 1 void)")
    assert payload["extras"][:2] == [
        "1 void point spent to activate Commune (Water)",
        "Rolled +1k1 from 1 spent void point",
    ]
    db.expire_all()
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 0


# --- C4 / R2: /initiative ----------------------------------------------------


def test_initiative_starts_the_round_on_the_persisted_character(client):
    db = _session(client)
    char = _akodo(
        db,
        action_dice=[{"value": 9, "spent": True, "spent_by": "Attack"}],
        precepts_pool=[{"value": 8}],
        adventure_state={"kakita_5th_dan_used": True, "lucky_used": True,
                         "mantis_posture_phase": 3},
    )
    content, payload = run_roll_command(db, "initiative", PLAYER_ID)

    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    values = [d["value"] for d in fresh.action_dice]
    assert len(values) == 3 and values == sorted(values)   # Void 3
    assert all(d["spent"] is False for d in fresh.action_dice)
    assert fresh.adventure_state == {"lucky_used": True}
    assert fresh.precepts_pool == [{"value": 8}]
    assert fresh.current_void_points == 3
    assert fresh.tracking_rev == 1

    dice = ", ".join(str(v) for v in values)
    assert content == f"**Roll Tester** rolls initiative - action dice: {dice}"
    assert payload["show_total"] is False
    assert [c["parts"][0] for c in payload["kept"]] == values
    row = query_db(client, RollHistory).one()
    assert row.roll_key == "initiative" and row.payload == payload


def test_the_initiative_line_has_no_number_directly_before_a_word(client):
    """C6.2: gm-assistant parses "<number> <Skill>" out of roll lines."""
    import re

    db = _session(client)
    _akodo(db)
    content, _ = run_roll_command(db, "initiative", PLAYER_ID)
    assert not re.search(r"\d\s+[A-Za-z]", content.replace("**", ""))


def test_initiative_ignores_a_void_option(client):
    db = _session(client)
    char = _akodo(db)
    run_roll_command(db, "initiative", PLAYER_ID, void=2)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    assert fresh.current_void_points == 3


def test_the_sheet_then_shows_those_dice(client, monkeypatch):
    """R2.3: nothing about them is recognizable as having come from outside."""
    db = _session(client)
    char = _akodo(db, owner_discord_id=ADMIN_ID, is_published=True)
    run_roll_command(db, "initiative", ADMIN_ID)
    fresh = query_db(client, Character).filter(Character.id == char.id).one()
    html = client.get(f"/characters/{char.id}").text
    assert json.dumps(fresh.action_dice, sort_keys=True) in html
    assert set(fresh.action_dice[0]) == {"value", "spent"}


def test_initiative_posts_its_card_without_a_total(
    client, signing_key, _capture_discord_calls,
):
    db = _session(client)
    _akodo(db)
    assert _post(client, signing_key, _command(name="initiative")).json() == {"type": 5}
    sent = _capture_discord_calls[0]
    assert "rolls initiative - action dice:" in sent["content"]
    assert sent["png"][:8] == b"\x89PNG\r\n\x1a\n"


# --- R6.1: current state over the read-only API ------------------------------


def test_api_characters_carries_current_state(client, monkeypatch):
    monkeypatch.setenv("ROLL_QUERY_TOKEN", "gm-token")
    db = _session(client)
    char = _akodo(db, current_temp_void_points=1, current_light_wounds=7)
    run_roll_command(db, "initiative", PLAYER_ID)
    run_roll_command(db, "etiquette", PLAYER_ID, void=2)

    rows = client.get(
        "/api/characters", headers={"Authorization": "Bearer gm-token"},
    ).json()["characters"]
    current = next(r for r in rows if r["id"] == char.id)["current"]
    assert current["void_points"] == 2
    assert current["temp_void_points"] == 0
    assert current["worldliness_void_remaining"] == 0
    assert current["void_max"] == 3 and current["void_spend_cap"] == 3
    assert current["light_wounds"] == 7 and current["serious_wounds"] == 0
    assert len(current["action_dice"]) == 3
    assert current["tracking_rev"] == 2


# --- C7: registration ---------------------------------------------------------


def _load_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parent.parent / "scripts" / "register_discord_commands.py"
    spec = importlib.util.spec_from_file_location("register_discord_commands", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_registers_the_full_set_by_default():
    script = _load_script()
    assert script.select_commands("") == command_definitions()
    subset = script.select_commands("Roll, etiquette")
    assert [c["name"] for c in subset] == ["roll", "etiquette"]
    with pytest.raises(SystemExit):
        script.select_commands("attack")


def test_put_global_commands(monkeypatch, signing_key):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot-token")
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"name": "roll"}]

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def put(self, url, **kwargs):
            captured.update({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr(discord_api.httpx, "Client", lambda *a, **kw: _Client())
    assert discord_api.put_global_commands([{"name": "roll"}]) == [{"name": "roll"}]
    assert captured["url"].endswith(f"/applications/{APP_ID}/commands")
    assert "guilds" not in captured["url"]
