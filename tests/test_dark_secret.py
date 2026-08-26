"""Dark Secret privacy: helpers, the metadata endpoint, page stripping,
and the version system's hands-off treatment of the secret.

See ``app/services/dark_secret.py`` for the rules under test.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Character, CharacterVersion, GamingGroup, User
from app.services.dark_secret import (
    DARK_SECRET_ID,
    can_set_dark_secret_knower,
    can_view_dark_secret,
    dark_secret_view,
    details_for_viewer,
    knower_choices,
    knower_display_name,
    merge_dark_secret,
    strip_dark_secret,
)
from app.services.versions import _snapshot_state
from app.services.xp import validate_character
from tests.conftest import make_character_data, query_db

ADMIN = "183026066498125825"
OWNER = "owner_777"
EDITOR = "editor_555"
OTHER = "other_999"

OWNER_HEADERS = {"X-Test-User": f"{OWNER}:Owner Player"}
EDITOR_HEADERS = {"X-Test-User": f"{EDITOR}:Granted Editor"}
OTHER_HEADERS = {"X-Test-User": f"{OTHER}:Some Other Player"}

SECRET = "I poisoned the brother of the daimyo"


def _seed(client, **kwargs):
    """A published, visible, non-admin-owned character with Dark Secret
    taken, an editor grant for EDITOR, and a secret already stored."""
    session = client._test_session_factory()
    for did, name in ((OWNER, "Owner Player"), (EDITOR, "Granted Editor"),
                      (OTHER, "Some Other Player"), (ADMIN, "GM")):
        if not session.query(User).filter(User.discord_id == did).first():
            session.add(User(discord_id=did, discord_name=name, display_name=name))
    session.commit()
    defaults = dict(
        name="Secretive Samurai",
        school="akodo_bushi",
        school_ring_choice="Water",
        ring_water=3,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id=OWNER,
        editor_discord_ids=[EDITOR],
        disadvantages=["dark_secret"],
        advantage_details={
            DARK_SECRET_ID: {"text": SECRET, "player": ""},
        },
        is_published=True,
        is_hidden=False,
        published_state={"name": "Secretive Samurai"},
    )
    defaults.update(kwargs)
    c = Character(**defaults)
    session.add(c)
    session.commit()
    return c.id


def _seed_knower(client, name="Confidant", **kwargs):
    session = client._test_session_factory()
    defaults = dict(name=name, school="akodo_bushi", owner_discord_id=OTHER,
                    is_published=True, is_hidden=False)
    defaults.update(kwargs)
    c = Character(**defaults)
    session.add(c)
    session.commit()
    return c.id


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_can_view_owner_and_admin_only(self):
        assert can_view_dark_secret(OWNER, OWNER, admin_ids=[ADMIN])
        assert can_view_dark_secret(ADMIN, OWNER, admin_ids=[ADMIN])
        assert not can_view_dark_secret(EDITOR, OWNER, admin_ids=[ADMIN])
        assert not can_view_dark_secret(None, OWNER, admin_ids=[ADMIN])

    def test_can_view_reads_admin_env_by_default(self):
        # conftest sets ADMIN_DISCORD_IDS to the admin id.
        assert can_view_dark_secret(ADMIN, OWNER)
        assert not can_view_dark_secret(OTHER, OWNER)

    def test_can_set_knower_admin_only(self):
        assert can_set_dark_secret_knower(ADMIN)
        assert not can_set_dark_secret_knower(OWNER)
        assert not can_set_dark_secret_knower(None)
        assert can_set_dark_secret_knower("x", admin_ids=["x"])

    def test_strip_removes_only_dark_secret(self):
        assert strip_dark_secret(None) == {}
        out = strip_dark_secret({DARK_SECRET_ID: {"text": "s"}, "virtue": {"text": "v"}})
        assert out == {"virtue": {"text": "v"}}

    def test_merge_discards_incoming_and_keeps_persisted(self):
        incoming = {DARK_SECRET_ID: {"text": "attacker wrote this"}, "virtue": {"text": "v"}}
        persisted = {DARK_SECRET_ID: {"text": "real"}, "driven": {"text": "old"}}
        assert merge_dark_secret(incoming, persisted) == {
            "virtue": {"text": "v"}, DARK_SECRET_ID: {"text": "real"},
        }
        # No persisted secret -> incoming one is simply dropped.
        assert merge_dark_secret(incoming, {}) == {"virtue": {"text": "v"}}
        # Non-dict incoming payloads are treated as empty.
        assert merge_dark_secret("junk", persisted) == {DARK_SECRET_ID: {"text": "real"}}

    def test_details_for_viewer(self):
        d = {DARK_SECRET_ID: {"text": "s"}, "virtue": {"text": "v"}}
        assert details_for_viewer(d, OWNER, OWNER, admin_ids=[]) == d
        assert details_for_viewer(d, EDITOR, OWNER, admin_ids=[]) == {"virtue": {"text": "v"}}

    def test_knower_display_name(self, client):
        _seed(client)
        db = client._test_session_factory()
        assert knower_display_name(None, db) == ""
        assert knower_display_name({}, db) == ""
        assert knower_display_name({"player": "nobody_here"}, db) == ""
        assert knower_display_name({"player": OTHER}, db) == "Some Other Player"

    def test_knower_choices_excludes_owner_and_sorts(self, client):
        cid = _seed(client)
        db = client._test_session_factory()
        db.add(User(discord_id="zz", discord_name="zz-handle", display_name=""))
        db.commit()
        me = db.query(Character).filter(Character.id == cid).first()
        choices = knower_choices(me, db)
        ids = [c["discord_id"] for c in choices]
        assert OWNER not in ids
        names = [c["name"] for c in choices]
        assert names == sorted(names, key=str.casefold)
        assert {"discord_id": "zz", "name": "zz-handle"} in choices

    def test_dark_secret_view_blank_for_non_viewer(self, client):
        cid = _seed(client)
        db = client._test_session_factory()
        me = db.query(Character).filter(Character.id == cid).first()
        assert dark_secret_view(me, db, EDITOR) == {
            "can_view": False, "can_set_knower": False, "text": "",
            "knower_player_id": "", "knower_name": "",
        }
        owner_view = dark_secret_view(me, db, OWNER)
        assert owner_view["can_view"] and not owner_view["can_set_knower"]
        assert owner_view["text"] == SECRET
        assert dark_secret_view(me, db, ADMIN)["can_set_knower"] is True


# ---------------------------------------------------------------------------
# validate_character warnings
# ---------------------------------------------------------------------------

class TestValidationWarnings:
    def test_both_missing(self):
        data = make_character_data(disadvantages=["dark_secret"], advantage_details={})
        errs = validate_character(data)
        assert any("no description has been written" in e for e in errs)
        assert any("GM has not yet chosen" in e for e in errs)
        # The generic "requires a description" wording is NOT used for it.
        assert not any("Dark Secret requires" in e for e in errs)

    def test_text_and_knower_set(self):
        data = make_character_data(
            disadvantages=["dark_secret"],
            advantage_details={DARK_SECRET_ID: {"text": "s", "player": "abc"}},
        )
        assert not any("Dark Secret" in e for e in validate_character(data))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class TestGetDarkSecret:
    def test_owner_reads(self, client):
        cid = _seed(client)
        resp = client.get(f"/characters/{cid}/dark-secret", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["text"] == SECRET
        assert resp.json()["can_set_knower"] is False

    def test_admin_reads(self, client):
        cid = _seed(client)
        resp = client.get(f"/characters/{cid}/dark-secret")
        assert resp.status_code == 200
        assert resp.json()["text"] == SECRET
        assert resp.json()["can_set_knower"] is True

    def test_editor_forbidden(self, client):
        cid = _seed(client)
        resp = client.get(f"/characters/{cid}/dark-secret", headers=EDITOR_HEADERS)
        assert resp.status_code == 403
        assert SECRET not in resp.text

    def test_anonymous_401(self, client):
        cid = _seed(client)
        client.headers.pop("X-Test-User", None)
        assert client.get(f"/characters/{cid}/dark-secret").status_code == 401

    def test_unknown_404(self, client):
        assert client.get("/characters/999999/dark-secret").status_code == 404


class TestSetDarkSecret:
    def test_owner_sets_text(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"text": "  new secret  "}, headers=OWNER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["text"] == "new secret"
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details[DARK_SECRET_ID]["text"] == "new secret"

    def test_owner_clears_text_with_null(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"text": None}, headers=OWNER_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["text"] == ""

    def test_text_must_be_string(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"text": 42}, headers=OWNER_HEADERS)
        assert resp.status_code == 400

    def test_body_must_be_object(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json=["nope"], headers=OWNER_HEADERS)
        assert resp.status_code == 400

    def test_editor_forbidden(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"text": "hijack"}, headers=EDITOR_HEADERS)
        assert resp.status_code == 403
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details[DARK_SECRET_ID]["text"] == SECRET

    def test_anonymous_401_and_unknown_404(self, client):
        cid = _seed(client)
        assert client.post("/characters/999999/dark-secret", json={"text": "x"}).status_code == 404
        client.headers.pop("X-Test-User", None)
        assert client.post(f"/characters/{cid}/dark-secret", json={"text": "x"}).status_code == 401

    def test_owner_cannot_set_knower(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"player": OTHER}, headers=OWNER_HEADERS)
        assert resp.status_code == 403
        char = query_db(client).filter(Character.id == cid).first()
        assert not char.advantage_details[DARK_SECRET_ID].get("player")

    def test_admin_sets_knower(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret", json={"player": OTHER})
        assert resp.status_code == 200
        assert resp.json()["knower_player_id"] == OTHER
        assert resp.json()["knower_name"] == "Some Other Player"
        # Text untouched when only the knower is sent.
        assert resp.json()["text"] == SECRET
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details[DARK_SECRET_ID]["player"] == OTHER

    def test_admin_clears_knower(self, client):
        cid = _seed(client, advantage_details={
            DARK_SECRET_ID: {"text": SECRET, "player": OTHER},
        })
        for empty in (None, ""):
            resp = client.post(f"/characters/{cid}/dark-secret", json={"player": empty})
            assert resp.status_code == 200
            assert resp.json()["knower_player_id"] == ""
            assert resp.json()["knower_name"] == ""

    def test_admin_knower_validation(self, client):
        cid = _seed(client)
        r = client.post(f"/characters/{cid}/dark-secret", json={"player": 123})
        assert r.status_code == 400
        r = client.post(f"/characters/{cid}/dark-secret", json={"player": OWNER})
        assert r.status_code == 400
        r = client.post(f"/characters/{cid}/dark-secret", json={"player": "no_such_user"})
        assert r.status_code == 404

    def test_admin_sets_text_and_knower_together(self, client):
        cid = _seed(client)
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"text": "gm edit", "player": OTHER})
        assert resp.status_code == 200
        assert resp.json()["text"] == "gm edit"
        assert resp.json()["knower_player_id"] == OTHER

    def test_first_write_on_character_without_entry(self, client):
        cid = _seed(client, advantage_details={})
        resp = client.post(f"/characters/{cid}/dark-secret",
                           json={"text": "fresh"}, headers=OWNER_HEADERS)
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details == {DARK_SECRET_ID: {"text": "fresh"}}


class TestAutosaveIgnoresDarkSecret:
    def test_editor_autosave_cannot_read_or_clobber(self, client):
        cid = _seed(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"advantage_details": {"virtue": {"text": "Courage"}}},
            headers=EDITOR_HEADERS,
        )
        assert resp.status_code == 200
        assert SECRET not in resp.text
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details == {
            "virtue": {"text": "Courage"},
            DARK_SECRET_ID: {"text": SECRET, "player": ""},
        }

    def test_owner_autosave_with_dark_secret_key_is_ignored(self, client):
        cid = _seed(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"advantage_details": {DARK_SECRET_ID: {"text": "via autosave"}}},
            headers=OWNER_HEADERS,
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details[DARK_SECRET_ID]["text"] == SECRET


# ---------------------------------------------------------------------------
# Version system: metadata, never snapshotted, never reverted
# ---------------------------------------------------------------------------

class TestVersioning:
    def test_snapshot_strips_dark_secret(self, client):
        cid = _seed(client, advantage_details={
            DARK_SECRET_ID: {"text": SECRET}, "virtue": {"text": "v"},
        })
        char = query_db(client).filter(Character.id == cid).first()
        state = _snapshot_state(char)
        assert state["advantage_details"] == {"virtue": {"text": "v"}}

    def test_edit_does_not_flip_draft_and_publish_omits_secret(self, client):
        cid = _seed(client, is_published=False, published_state=None)
        resp = client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert not char.has_unpublished_changes
        assert DARK_SECRET_ID not in char.published_state["advantage_details"]
        version = query_db(client, CharacterVersion).filter(
            CharacterVersion.character_id == cid).first()
        assert SECRET not in str(version.state)

        client.post(f"/characters/{cid}/dark-secret",
                    json={"text": "changed", "player": OTHER})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details[DARK_SECRET_ID]["text"] == "changed"
        assert not char.has_unpublished_changes
        assert char.publish_status == "published"
        # And the draft diff has nothing to say about it.
        diff = client.get(f"/characters/{cid}/draft-diff").json()
        assert diff["lines"] == []

    def test_discard_and_revert_preserve_current_secret(self, client):
        cid = _seed(client, is_published=False, published_state=None)
        client.post(f"/characters/{cid}/publish", json={"summary": "v1"})
        client.post(f"/characters/{cid}/autosave", json={"honor": 2.0})
        client.post(f"/characters/{cid}/publish", json={"summary": "v2"})
        client.post(f"/characters/{cid}/dark-secret",
                    json={"text": "latest", "player": OTHER})

        # Discard: dirty the draft, then discard - the secret survives.
        client.post(f"/characters/{cid}/autosave", json={"honor": 3.0})
        assert client.post(f"/characters/{cid}/discard").status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.honor == 2.0
        assert char.advantage_details[DARK_SECRET_ID] == {
            "text": "latest", "player": OTHER,
        }

        # Revert to v1: same story.
        v1 = query_db(client, CharacterVersion).filter(
            CharacterVersion.character_id == cid,
            CharacterVersion.version_number == 1,
        ).first()
        assert client.post(f"/characters/{cid}/revert/{v1.id}").status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.honor == 1.0
        assert char.advantage_details[DARK_SECRET_ID]["text"] == "latest"

    def test_google_sheet_stale_ignores_dark_secret(self, client):
        cid = _seed(client, google_sheet_id="abc")
        char = query_db(client).filter(Character.id == cid).first()
        exported = char.to_dict()
        exported["advantage_details"] = strip_dark_secret(exported["advantage_details"])
        char.google_sheet_exported_state = exported
        assert char.google_sheet_is_stale is False
        # A real details change still counts.
        exported2 = dict(exported)
        exported2["advantage_details"] = {"virtue": {"text": "Courage"}}
        char.google_sheet_exported_state = exported2
        assert char.google_sheet_is_stale is True


# ---------------------------------------------------------------------------
# Pages never leak the secret to the wrong viewer
# ---------------------------------------------------------------------------

class TestViewSheet:
    def test_owner_sees_secret_and_knower(self, client):
        cid = _seed(client, advantage_details={
            DARK_SECRET_ID: {"text": SECRET, "player": OTHER},
        })
        resp = client.get(f"/characters/{cid}", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        assert SECRET in resp.text
        assert "known by Some Other Player" in resp.text

    def test_owner_sees_unchosen_knower_note(self, client):
        cid = _seed(client)
        resp = client.get(f"/characters/{cid}", headers=OWNER_HEADERS)
        assert "the GM has not yet chosen who knows" in resp.text

    def test_admin_sees_secret(self, client):
        cid = _seed(client)
        assert SECRET in client.get(f"/characters/{cid}").text

    @pytest.mark.parametrize("headers", [EDITOR_HEADERS, OTHER_HEADERS, None])
    def test_everyone_else_sees_only_padlock(self, client, headers):
        cid = _seed(client, advantage_details={
            DARK_SECRET_ID: {"text": SECRET, "player": OTHER},
        })
        if headers is None:
            client.headers.pop("X-Test-User", None)
            resp = client.get(f"/characters/{cid}")
        else:
            resp = client.get(f"/characters/{cid}", headers=headers)
        assert resp.status_code == 200
        assert "Dark Secret" in resp.text
        assert SECRET not in resp.text
        assert "known by" not in resp.text
        assert "private" in resp.text


class TestEditPage:
    def test_editor_page_has_no_secret(self, client):
        cid = _seed(client, advantage_details={
            DARK_SECRET_ID: {"text": SECRET, "player": OTHER},
        })
        resp = client.get(f"/characters/{cid}/edit", headers=EDITOR_HEADERS)
        assert resp.status_code == 200
        assert SECRET not in resp.text
        assert '"knower_player_id": ""' in resp.text
        assert '"can_view": false' in resp.text

    def test_owner_page_embeds_secret_but_no_knower_choices(self, client):
        cid = _seed(client)
        resp = client.get(f"/characters/{cid}/edit", headers=OWNER_HEADERS)
        assert SECRET in resp.text
        assert '"can_set_knower": false' in resp.text
        # Knower dropdown options are admin-only markup.
        assert f'<option value="{OTHER}">' not in resp.text

    def test_admin_page_has_knower_choices(self, client):
        cid = _seed(client)
        resp = client.get(f"/characters/{cid}/edit")
        assert '"can_set_knower": true' in resp.text
        assert f'<option value="{OTHER}">Some Other Player</option>' in resp.text
        assert f'<option value="{OWNER}">' not in resp.text


class TestGroupSummary:
    def _seed_group(self, client, viewer_is_owner_of_other=False):
        db = client._test_session_factory()
        g = GamingGroup(name="Tuesday")
        db.add(g)
        db.commit()
        _seed_knower(client, name="Kakita Confidant", gaming_group_id=g.id)
        cid = _seed(client, gaming_group_id=g.id, advantage_details={
            DARK_SECRET_ID: {"text": SECRET, "player": OTHER},
        })
        return g.id, cid

    def test_admin_sees_secret_in_chip(self, client):
        gid, _ = self._seed_group(client)
        resp = client.get(f"/groups/{gid}")
        assert resp.status_code == 200
        assert SECRET in resp.text
        assert "known by Some Other Player" in resp.text

    def test_owner_sees_own_secret(self, client):
        gid, _ = self._seed_group(client)
        resp = client.get(f"/groups/{gid}", headers=OWNER_HEADERS)
        assert SECRET in resp.text

    def test_other_player_sees_plain_chip(self, client):
        gid, _ = self._seed_group(client)
        # OTHER is the chosen knowing player, and still can't read the text.
        resp = client.get(f"/groups/{gid}", headers=OTHER_HEADERS)
        assert resp.status_code == 200
        assert 'data-dis-id="dark_secret"' in resp.text
        assert SECRET not in resp.text
        assert "known by" not in resp.text


class TestGoogleSheetsExport:
    def _run_callback(self, client, cid, headers):
        state = "test-state"
        client.cookies.set("google_oauth_state", state)
        client.cookies.set("google_export_char_id", str(cid))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "fake-token"}
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        with patch("app.routes.google_sheets.create_spreadsheet") as mock_create, \
                patch("app.routes.google_sheets.httpx.AsyncClient", return_value=mock_http), \
                patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "s"}):
            mock_create.return_value = "https://docs.google.com/spreadsheets/d/abc123/edit"
            resp = client.get("/auth/google/callback?code=c&state=test-state",
                              follow_redirects=False, headers=headers)
            assert resp.status_code == 303
            return mock_create.call_args.args[2]  # char_dict

    def test_editor_export_strips_secret(self, client):
        cid = _seed(client)
        char_dict = self._run_callback(client, cid, EDITOR_HEADERS)
        assert DARK_SECRET_ID not in char_dict["advantage_details"]

    def test_owner_export_keeps_secret(self, client):
        cid = _seed(client)
        char_dict = self._run_callback(client, cid, OWNER_HEADERS)
        assert char_dict["advantage_details"][DARK_SECRET_ID]["text"] == SECRET
