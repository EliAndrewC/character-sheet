"""Unit tests for the Roll History feature.

Covers:
- is_owning_player predicate
- should_record_roll matrix (every permission combination)
- POST/PATCH/GET/annotation/hide/unhide endpoints
"""

import pytest

from app.models import Character, RollHistory, User
from app.services.auth import is_owning_player
from app.services.rolls_history import (
    should_record_roll,
    coerce_payload,
    coerce_action_die_spent,
    coerce_tn,
    coerce_annotation,
    MAX_ANNOTATION_LEN,
    MAX_PAYLOAD_BYTES,
)
from tests.conftest import make_character_data, query_db


# Admin id matches conftest's ADMIN_DISCORD_IDS env: 183026066498125825
ADMIN_ID = "183026066498125825"
OWNER_ID = "owner_user_42"
EDITOR_ID = "editor_user_77"
RANDOM_ID = "random_visitor_99"


def _make_char(db, *, owner=OWNER_ID, editor_ids=None):
    c = Character(
        name="Roller",
        owner_discord_id=owner,
        editor_discord_ids=editor_ids or [],
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# is_owning_player
# ---------------------------------------------------------------------------


def test_is_owning_player_anonymous():
    assert is_owning_player(None, OWNER_ID) is False


def test_is_owning_player_no_owner():
    assert is_owning_player(OWNER_ID, None) is False


def test_is_owning_player_match():
    assert is_owning_player(OWNER_ID, OWNER_ID) is True


def test_is_owning_player_mismatch():
    assert is_owning_player("someone_else", OWNER_ID) is False


# ---------------------------------------------------------------------------
# should_record_roll: full permission matrix
# ---------------------------------------------------------------------------


def test_should_record_owner_non_admin(db):
    char = _make_char(db, owner=OWNER_ID)
    record, is_owner = should_record_roll(OWNER_ID, char, [], admin_ids=[ADMIN_ID])
    assert record is True and is_owner is True


def test_should_record_owner_who_is_also_admin(db):
    char = _make_char(db, owner=ADMIN_ID)
    record, is_owner = should_record_roll(ADMIN_ID, char, [], admin_ids=[ADMIN_ID])
    assert record is True and is_owner is True


def test_should_NOT_record_admin_not_owner_not_editor(db):
    char = _make_char(db, owner=OWNER_ID, editor_ids=[])
    record, is_owner = should_record_roll(ADMIN_ID, char, [], admin_ids=[ADMIN_ID])
    assert record is False and is_owner is False


def test_should_NOT_record_admin_in_editor_list(db):
    """Admin status wins over editor membership: still don't record."""
    char = _make_char(db, owner=OWNER_ID, editor_ids=[ADMIN_ID])
    record, is_owner = should_record_roll(ADMIN_ID, char, [], admin_ids=[ADMIN_ID])
    assert record is False and is_owner is False


def test_should_NOT_record_admin_in_owner_grants(db):
    """Admin status wins even when owner granted them account-level access."""
    char = _make_char(db, owner=OWNER_ID, editor_ids=[])
    record, is_owner = should_record_roll(
        ADMIN_ID, char, [ADMIN_ID], admin_ids=[ADMIN_ID]
    )
    assert record is False and is_owner is False


def test_should_record_non_admin_editor(db):
    char = _make_char(db, owner=OWNER_ID, editor_ids=[EDITOR_ID])
    record, is_owner = should_record_roll(
        EDITOR_ID, char, [], admin_ids=[ADMIN_ID]
    )
    assert record is True and is_owner is False


def test_should_record_non_admin_granted_account(db):
    char = _make_char(db, owner=OWNER_ID, editor_ids=[])
    record, is_owner = should_record_roll(
        EDITOR_ID, char, [EDITOR_ID], admin_ids=[ADMIN_ID]
    )
    assert record is True and is_owner is False


def test_should_NOT_record_anonymous(db):
    char = _make_char(db, owner=OWNER_ID)
    record, is_owner = should_record_roll(None, char, [], admin_ids=[ADMIN_ID])
    assert record is False and is_owner is False


def test_should_NOT_record_random_visitor(db):
    char = _make_char(db, owner=OWNER_ID, editor_ids=[])
    record, is_owner = should_record_roll(
        RANDOM_ID, char, [], admin_ids=[ADMIN_ID]
    )
    assert record is False and is_owner is False


# ---------------------------------------------------------------------------
# coerce_* helpers
# ---------------------------------------------------------------------------


def test_coerce_payload_drops_non_dict():
    assert coerce_payload(None) == {}
    assert coerce_payload([1, 2]) == {}
    assert coerce_payload("foo") == {}


def test_coerce_payload_passes_dict():
    p = {"title": "X", "total": 10}
    assert coerce_payload(p) == p


def test_coerce_payload_drops_oversized():
    huge = {"x": "a" * (MAX_PAYLOAD_BYTES + 1)}
    assert coerce_payload(huge) == {}


def test_coerce_payload_drops_non_serializable():
    """A dict containing a non-JSON-serializable value falls back to {}
    rather than 500-ing the route."""
    class Unserializable:
        pass
    assert coerce_payload({"x": Unserializable()}) == {}


def test_coerce_action_die_spent_none():
    assert coerce_action_die_spent(None) is None


def test_coerce_action_die_spent_dict():
    assert coerce_action_die_spent(
        {"value": 7, "source": "attack"}
    ) == {"value": 7, "source": "attack"}


def test_coerce_action_die_spent_clamps_value():
    assert coerce_action_die_spent({"value": 99}) == {"value": 10}
    assert coerce_action_die_spent({"value": -5}) == {"value": 0}


def test_coerce_action_die_spent_bad_input():
    assert coerce_action_die_spent("string") is None
    assert coerce_action_die_spent({"value": "abc"}) == {"value": 0}


def test_coerce_action_die_spent_empty_returns_none():
    assert coerce_action_die_spent({}) is None


def test_coerce_action_die_spent_caps_source():
    big = "x" * 500
    out = coerce_action_die_spent({"source": big})
    assert len(out["source"]) == 200


def test_coerce_action_die_spent_drops_empty_source():
    """Empty/non-string source field is silently dropped."""
    assert coerce_action_die_spent({"source": ""}) is None
    assert coerce_action_die_spent({"source": 42}) is None


def test_coerce_tn_none():
    assert coerce_tn(None) is None


def test_coerce_tn_int():
    assert coerce_tn(35) == 35


def test_coerce_tn_string_int():
    assert coerce_tn("40") == 40


def test_coerce_tn_negative_to_none():
    assert coerce_tn(-1) is None


def test_coerce_tn_bad_input():
    assert coerce_tn("abc") is None
    assert coerce_tn([]) is None


def test_coerce_annotation_basic():
    assert coerce_annotation("hello") == "hello"


def test_coerce_annotation_trims():
    assert coerce_annotation("  hello  ") == "hello"


def test_coerce_annotation_caps_length():
    big = "x" * (MAX_ANNOTATION_LEN + 100)
    assert len(coerce_annotation(big)) == MAX_ANNOTATION_LEN


def test_coerce_annotation_non_string():
    assert coerce_annotation(None) == ""
    assert coerce_annotation(42) == ""


# ---------------------------------------------------------------------------
# Endpoint tests: POST /rolls
# ---------------------------------------------------------------------------


def _create_via_post(client, *, name="Roller", owner=ADMIN_ID, editor_ids=None):
    """Insert a character directly via the test client's DB session.

    The default `owner` is the admin user (which is also the default
    test-client identity), so the typical "owner makes a roll" path
    just works without any cross-session DB shuffling.
    """
    session = client._test_session_factory()
    c = Character(
        name=name,
        school="akodo_bushi",
        school_ring_choice="Water",
        ring_water=3,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id=owner,
        editor_discord_ids=editor_ids or [],
        is_published=True,
        published_state={},
    )
    session.add(c)
    session.commit()
    char_id = c.id
    session.close()
    return query_db(client).filter_by(id=char_id).first()


def _basic_post_body(roll_key="skill:bragging", **overrides):
    body = {
        "roll_key": roll_key,
        "roll_label": "Bragging",
        "payload": {"title": "Bragging", "total": 25, "formula": "5k3"},
        "impaired_at_roll": False,
    }
    body.update(overrides)
    return body


def test_post_401_anonymous(client):
    char = _create_via_post(client)
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_post_404_missing_character(client):
    resp = client.post(
        "/characters/9999/rolls",
        json=_basic_post_body(),
    )
    assert resp.status_code == 404


def test_post_owner_records_as_owner_roll(client):
    # Default test client IS the admin, who created the char and is the owner.
    char = _create_via_post(client)
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"]
    row = query_db(client, RollHistory).filter_by(id=body["id"]).first()
    assert row.is_owner_roll is True
    assert row.actor_discord_id == ADMIN_ID
    assert row.payload["total"] == 25


def test_post_non_admin_editor_records_as_non_owner(client):
    """An editor (test_user_1, non-admin) records with is_owner_roll=False."""
    char = _create_via_post(client, name="EditorCase")
    # Reassign the owner to a different non-admin id, and put test_user_1 in
    # the editor list. test_user_1 is in the whitelist but not admin.
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.owner_discord_id = OWNER_ID
    c.editor_discord_ids = ["test_user_1"]
    sess.commit()
    sess.close()
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
        headers={"X-Test-User": "test_user_1:Test User 1"},
    )
    assert resp.status_code == 200
    row = query_db(client, RollHistory).filter_by(id=resp.json()["id"]).first()
    assert row.is_owner_roll is False
    assert row.actor_discord_id == "test_user_1"


def test_post_admin_not_owner_returns_204(client):
    """Admin rolling on someone else's character is silently dropped."""
    char = _create_via_post(client, name="AdminTestRoll")
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.owner_discord_id = OWNER_ID  # not admin
    sess.commit()
    sess.close()
    # Default test client is admin
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
    )
    assert resp.status_code == 204
    assert query_db(client, RollHistory).count() == 0


def test_post_admin_not_owner_returns_204_even_in_editor_list(client):
    """Admin in editor list STILL doesn't record - admin status wins."""
    char = _create_via_post(client, name="AdminInEditorList")
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.owner_discord_id = OWNER_ID
    c.editor_discord_ids = [ADMIN_ID]
    sess.commit()
    sess.close()
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
    )
    assert resp.status_code == 204
    assert query_db(client, RollHistory).count() == 0


def test_post_non_editor_returns_204(client):
    """Random logged-in visitor with no edit access: silently dropped."""
    char = _create_via_post(client, name="NonEditorTry")
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.owner_discord_id = OWNER_ID
    sess.commit()
    sess.close()
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 204
    assert query_db(client, RollHistory).count() == 0


def test_post_tn_round_trips(client):
    char = _create_via_post(client)
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(roll_key="attack", tn=35),
    )
    assert resp.status_code == 200
    row = query_db(client, RollHistory).filter_by(id=resp.json()["id"]).first()
    assert row.tn == 35


def test_post_action_die_spent_round_trips(client):
    char = _create_via_post(client)
    resp = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(
            roll_key="attack",
            action_die_spent={"value": 7, "source": "Attack"},
        ),
    )
    assert resp.status_code == 200
    row = query_db(client, RollHistory).filter_by(id=resp.json()["id"]).first()
    assert row.action_die_spent == {"value": 7, "source": "Attack"}


# ---------------------------------------------------------------------------
# PATCH /rolls/{id} (payload update)
# ---------------------------------------------------------------------------


def test_patch_updates_payload(client):
    char = _create_via_post(client)
    r = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
    )
    rid = r.json()["id"]
    resp = client.patch(
        f"/characters/{char.id}/rolls/{rid}",
        json={"payload": {"title": "Bragging", "total": 30}},
    )
    assert resp.status_code == 200
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.payload["total"] == 30


def test_patch_does_not_touch_annotation_or_hidden(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    # Annotate + hide first
    client.patch(
        f"/characters/{char.id}/rolls/{rid}/annotation",
        json={"annotation": "great roll"},
    )
    client.post(f"/characters/{char.id}/rolls/{rid}/hide")
    # PATCH payload only
    client.patch(
        f"/characters/{char.id}/rolls/{rid}",
        json={"payload": {"total": 30}},
    )
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.annotation == "great roll"
    assert row.is_hidden is True


def test_patch_403_for_different_actor(client):
    """Only the user who originally rolled can PATCH the payload (so a
    non-owner editor can't accidentally rewrite an owner's roll)."""
    char = _create_via_post(client, name="DifferentActor")
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.owner_discord_id = OWNER_ID
    c.editor_discord_ids = ["test_user_1", "test_user_2"]
    sess.commit()
    sess.close()
    # test_user_1 makes the roll
    r = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(),
        headers={"X-Test-User": "test_user_1:Test User 1"},
    )
    rid = r.json()["id"]
    # test_user_2 tries to PATCH it
    resp = client.patch(
        f"/characters/{char.id}/rolls/{rid}",
        json={"payload": {"total": 99}},
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 403


def test_patch_404_unknown_roll(client):
    char = _create_via_post(client)
    resp = client.patch(
        f"/characters/{char.id}/rolls/99999",
        json={"payload": {"total": 1}},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /rolls (list)
# ---------------------------------------------------------------------------


def test_get_list_401_anonymous(client):
    char = _create_via_post(client)
    resp = client.get(
        f"/characters/{char.id}/rolls",
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_get_list_404_missing(client):
    resp = client.get("/characters/9999/rolls")
    assert resp.status_code == 404


def test_get_list_403_for_non_editor(client):
    char = _create_via_post(client, name="GetList403")
    sess = client._test_session_factory()
    c = sess.query(Character).filter_by(id=char.id).first()
    c.owner_discord_id = OWNER_ID
    sess.commit()
    sess.close()
    resp = client.get(
        f"/characters/{char.id}/rolls",
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 403


def test_get_list_returns_newest_first(client):
    char = _create_via_post(client)
    r1 = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body(roll_label="First"))
    r2 = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body(roll_label="Second"))
    rows = client.get(f"/characters/{char.id}/rolls").json()["rolls"]
    assert len(rows) == 2
    assert rows[0]["id"] == r2.json()["id"]
    assert rows[1]["id"] == r1.json()["id"]


def test_get_list_default_omits_hidden(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    client.post(f"/characters/{char.id}/rolls/{rid}/hide")
    rows = client.get(f"/characters/{char.id}/rolls").json()["rolls"]
    assert rows == []


def test_get_list_include_hidden(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    client.post(f"/characters/{char.id}/rolls/{rid}/hide")
    rows = client.get(
        f"/characters/{char.id}/rolls?include_hidden=1"
    ).json()["rolls"]
    assert len(rows) == 1
    assert rows[0]["is_hidden"] is True


def test_get_list_row_shape(client):
    char = _create_via_post(client)
    r = client.post(
        f"/characters/{char.id}/rolls",
        json=_basic_post_body(roll_key="attack", tn=35),
    )
    row = client.get(f"/characters/{char.id}/rolls").json()["rolls"][0]
    for key in (
        "id", "roll_key", "roll_label", "payload", "impaired_at_roll",
        "tn", "is_hidden", "annotation", "actor_discord_id",
        "is_owner_roll", "created_at",
    ):
        assert key in row, f"missing {key}"
    assert row["tn"] == 35


# ---------------------------------------------------------------------------
# Annotation PATCH
# ---------------------------------------------------------------------------


def test_annotation_patch_persists(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    client.patch(
        f"/characters/{char.id}/rolls/{rid}/annotation",
        json={"annotation": "nice"},
    )
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.annotation == "nice"


def test_annotation_patch_trims_whitespace(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    client.patch(
        f"/characters/{char.id}/rolls/{rid}/annotation",
        json={"annotation": "  spaced  "},
    )
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.annotation == "spaced"


def test_annotation_patch_caps_length(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    big = "x" * (MAX_ANNOTATION_LEN + 200)
    client.patch(
        f"/characters/{char.id}/rolls/{rid}/annotation",
        json={"annotation": big},
    )
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert len(row.annotation) == MAX_ANNOTATION_LEN


def test_annotation_patch_403_for_non_editor(client):
    """test_user_1 owns the character + makes a roll; test_user_2 has no
    edit access and cannot annotate."""
    char = _create_via_post(client, name="AnnoNonEditor", owner="test_user_1")
    r = client.post(
        f"/characters/{char.id}/rolls", json=_basic_post_body(),
        headers={"X-Test-User": "test_user_1:Test User 1"},
    )
    rid = r.json()["id"]
    resp = client.patch(
        f"/characters/{char.id}/rolls/{rid}/annotation",
        json={"annotation": "noooo"},
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Hide / unhide
# ---------------------------------------------------------------------------


def test_hide_and_unhide_roundtrip(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    client.post(f"/characters/{char.id}/rolls/{rid}/hide")
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.is_hidden is True
    client.post(f"/characters/{char.id}/rolls/{rid}/unhide")
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.is_hidden is False


def test_hide_idempotent(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    client.post(f"/characters/{char.id}/rolls/{rid}/hide")
    resp = client.post(f"/characters/{char.id}/rolls/{rid}/hide")
    assert resp.status_code == 200
    assert resp.json()["is_hidden"] is True


def test_hide_403_for_non_editor(client):
    """test_user_1 owns + rolls; test_user_2 has no edit access and 403s."""
    char = _create_via_post(client, name="HideNonEditor", owner="test_user_1")
    r = client.post(
        f"/characters/{char.id}/rolls", json=_basic_post_body(),
        headers={"X-Test-User": "test_user_1:Test User 1"},
    )
    rid = r.json()["id"]
    resp = client.post(
        f"/characters/{char.id}/rolls/{rid}/hide",
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 403


def test_unhide_404_unknown_roll(client):
    char = _create_via_post(client)
    resp = client.post(f"/characters/{char.id}/rolls/9999/unhide")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Hidden-character + auth boundary coverage
# ---------------------------------------------------------------------------


def _make_hidden_char(client, owner="test_user_1"):
    """Hidden + unpublished character so the can_view_drafts gate kicks in."""
    session = client._test_session_factory()
    c = Character(
        name="Hidden",
        school="akodo_bushi",
        school_ring_choice="Water",
        ring_water=3,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id=owner,
        editor_discord_ids=[],
        is_published=False,
        is_hidden=True,
    )
    session.add(c)
    session.commit()
    cid = c.id
    session.close()
    return cid


def test_post_404_hidden_char_for_non_editor(client):
    cid = _make_hidden_char(client)
    resp = client.post(
        f"/characters/{cid}/rolls",
        json=_basic_post_body(),
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 404


def test_patch_401_anonymous(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    resp = client.patch(
        f"/characters/{char.id}/rolls/{rid}",
        json={"payload": {"total": 1}},
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_patch_404_missing_char(client):
    resp = client.patch(
        "/characters/9999/rolls/1",
        json={"payload": {}},
    )
    assert resp.status_code == 404


def test_patch_404_hidden_char_non_editor(client):
    cid = _make_hidden_char(client)
    resp = client.patch(
        f"/characters/{cid}/rolls/1",
        json={"payload": {}},
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 404


def test_patch_updates_action_die_spent(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    resp = client.patch(
        f"/characters/{char.id}/rolls/{rid}",
        json={"action_die_spent": {"value": 9, "source": "Mantis"}},
    )
    assert resp.status_code == 200
    row = query_db(client, RollHistory).filter_by(id=rid).first()
    assert row.action_die_spent == {"value": 9, "source": "Mantis"}


def test_get_list_404_hidden_char_non_editor(client):
    cid = _make_hidden_char(client)
    resp = client.get(
        f"/characters/{cid}/rolls",
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 404


def test_annotation_patch_401_anonymous(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    resp = client.patch(
        f"/characters/{char.id}/rolls/{rid}/annotation",
        json={"annotation": "x"},
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_annotation_patch_404_missing_char(client):
    resp = client.patch(
        "/characters/9999/rolls/1/annotation",
        json={"annotation": "x"},
    )
    assert resp.status_code == 404


def test_annotation_patch_404_hidden_char_non_editor(client):
    cid = _make_hidden_char(client)
    resp = client.patch(
        f"/characters/{cid}/rolls/1/annotation",
        json={"annotation": "x"},
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 404


def test_annotation_patch_404_unknown_roll(client):
    char = _create_via_post(client)
    resp = client.patch(
        f"/characters/{char.id}/rolls/9999/annotation",
        json={"annotation": "x"},
    )
    assert resp.status_code == 404


def test_hide_401_anonymous(client):
    char = _create_via_post(client)
    r = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    rid = r.json()["id"]
    resp = client.post(
        f"/characters/{char.id}/rolls/{rid}/hide",
        headers={"X-Test-User": ""},
    )
    assert resp.status_code == 401


def test_hide_404_missing_char(client):
    resp = client.post("/characters/9999/rolls/1/hide")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /characters/{id}/roll-history (the page route)
# ---------------------------------------------------------------------------


def test_roll_history_page_401_anonymous_redirects(client):
    char = _create_via_post(client)
    resp = client.get(
        f"/characters/{char.id}/roll-history",
        headers={"X-Test-User": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/auth/login" in resp.headers.get("location", "")


def test_roll_history_page_404_missing_char(client):
    resp = client.get("/characters/9999/roll-history")
    assert resp.status_code == 404


def test_roll_history_page_404_hidden_char_non_editor(client):
    cid = _make_hidden_char(client)
    resp = client.get(
        f"/characters/{cid}/roll-history",
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 404


def test_roll_history_page_403_for_non_editor(client):
    char = _create_via_post(client, name="PageNonEditor", owner=OWNER_ID)
    resp = client.get(
        f"/characters/{char.id}/roll-history",
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 403


def test_roll_history_page_200_for_editor(client):
    char = _create_via_post(client)
    resp = client.get(f"/characters/{char.id}/roll-history")
    assert resp.status_code == 200
    assert "Roll History" in resp.text
    # The roll-type column header reads "Type of Roll" (not just "Roll", which
    # is ambiguous with the roll's result).
    assert "Type of Roll" in resp.text


def test_roll_history_page_embeds_rolls_json(client):
    char = _create_via_post(client)
    # Insert a roll directly via the API
    client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    resp = client.get(f"/characters/{char.id}/roll-history")
    assert resp.status_code == 200
    # The page embeds the rolls JSON inside the rolls-data script tag
    assert 'id="rolls-data"' in resp.text
    assert "skill:bragging" in resp.text  # roll_key shows up in the embedded JSON


# ---------------------------------------------------------------------------
# UTC timezone marker on created_at
# ---------------------------------------------------------------------------


def test_get_list_created_at_has_utc_marker(client):
    """Naive SQLite UTC timestamps must be serialized as UTC-marked ISO
    strings so JS Date() doesn't reinterpret them as local time."""
    char = _create_via_post(client)
    client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    row = client.get(f"/characters/{char.id}/rolls").json()["rolls"][0]
    created = row["created_at"]
    assert created is not None
    assert created.endswith("Z"), (
        f"created_at must end with Z to mark UTC; got {created!r}"
    )


def test_post_create_response_has_utc_marker(client):
    char = _create_via_post(client)
    resp = client.post(f"/characters/{char.id}/rolls", json=_basic_post_body())
    assert resp.status_code == 200
    created = resp.json()["created_at"]
    assert created is not None
    assert created.endswith("Z")


def test_iso_utc_helper_handles_aware_datetime():
    """If the row's datetime ever becomes tz-aware (Postgres future-proofing,
    etc.), the helper must NOT double-append a Z."""
    from datetime import datetime, timezone
    from app.routes.rolls import _iso_utc
    aware = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)
    out = _iso_utc(aware)
    assert out
    assert not out.endswith("ZZ")
    # The string already encodes +00:00 for aware UTC; no Z needed
    assert "+00:00" in out or out.endswith("Z")


def test_iso_utc_helper_handles_none():
    from app.routes.rolls import _iso_utc
    assert _iso_utc(None) is None


def test_hide_404_hidden_char_non_editor(client):
    cid = _make_hidden_char(client)
    resp = client.post(
        f"/characters/{cid}/rolls/1/hide",
        headers={"X-Test-User": "test_user_2:Test User 2"},
    )
    assert resp.status_code == 404
