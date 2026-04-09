"""Tests for the gaming groups feature: model, set-group endpoint, admin routes,
homepage clustering, and the version-bypass invariant."""

import pytest

from app.models import Character, CharacterVersion, GamingGroup, User
from tests.conftest import query_db


# ---------------------------------------------------------------------------
# GamingGroup model
# ---------------------------------------------------------------------------


class TestGamingGroupModel:
    def test_create_group(self, db):
        g = GamingGroup(name="Tuesday Group")
        db.add(g)
        db.commit()
        assert g.id is not None
        assert g.name == "Tuesday Group"

    def test_unique_name_constraint(self, db):
        db.add(GamingGroup(name="Tuesday Group"))
        db.commit()
        db.add(GamingGroup(name="Tuesday Group"))
        with pytest.raises(Exception):
            db.commit()
        db.rollback()

    def test_to_dict(self, db):
        g = GamingGroup(name="Wednesday Group")
        db.add(g)
        db.commit()
        d = g.to_dict()
        assert d == {"id": g.id, "name": "Wednesday Group"}


class TestCharacterToDict:
    def test_gaming_group_id_excluded_from_to_dict(self, db):
        """Critical: gaming_group_id must NEVER appear in to_dict() output,
        otherwise it would leak into published_state and create version diffs."""
        g = GamingGroup(name="Tuesday Group")
        db.add(g)
        db.commit()
        c = Character(name="Test", gaming_group_id=g.id)
        db.add(c)
        db.commit()
        d = c.to_dict()
        assert "gaming_group_id" not in d


# ---------------------------------------------------------------------------
# POST /characters/{id}/set-group
# ---------------------------------------------------------------------------


def _make_user(client, discord_id: str = "183026066498125825", display_name: str = "Test"):
    """Insert a User row directly via the test connection."""
    sess = client._test_session_factory()
    if sess.query(User).filter(User.discord_id == discord_id).first() is None:
        sess.add(User(discord_id=discord_id, discord_name=display_name, display_name=display_name))
        sess.commit()
    sess.close()


def _make_character(client, owner_discord_id: str = "183026066498125825") -> int:
    """Create a character via the test connection and return its id."""
    sess = client._test_session_factory()
    c = Character(name="Set-Group Subject", owner_discord_id=owner_discord_id)
    sess.add(c)
    sess.commit()
    char_id = c.id
    sess.close()
    return char_id


def _make_group(client, name: str = "Tuesday Group") -> int:
    sess = client._test_session_factory()
    g = GamingGroup(name=name)
    sess.add(g)
    sess.commit()
    gid = g.id
    sess.close()
    return gid


class TestSetGroupEndpoint:
    def test_set_group_success(self, client):
        _make_user(client)
        char_id = _make_character(client)
        gid = _make_group(client)
        resp = client.post(
            f"/characters/{char_id}/set-group",
            json={"gaming_group_id": gid},
        )
        assert resp.status_code == 200
        assert resp.json()["gaming_group_id"] == gid
        # Verify persisted
        sess = client._test_session_factory()
        c = sess.query(Character).filter(Character.id == char_id).first()
        assert c.gaming_group_id == gid
        sess.close()

    def test_set_group_unassign_with_null(self, client):
        _make_user(client)
        char_id = _make_character(client)
        gid = _make_group(client)
        client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": gid})

        resp = client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": None})
        assert resp.status_code == 200
        assert resp.json()["gaming_group_id"] is None

    def test_set_group_unassign_with_empty_string(self, client):
        _make_user(client)
        char_id = _make_character(client)
        gid = _make_group(client)
        client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": gid})

        resp = client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": ""})
        assert resp.status_code == 200
        assert resp.json()["gaming_group_id"] is None

    def test_set_group_nonexistent_group(self, client):
        _make_user(client)
        char_id = _make_character(client)
        resp = client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": 99999})
        assert resp.status_code == 404

    def test_set_group_invalid_payload(self, client):
        _make_user(client)
        char_id = _make_character(client)
        resp = client.post(
            f"/characters/{char_id}/set-group", json={"gaming_group_id": "not-a-number"}
        )
        assert resp.status_code == 400

    def test_set_group_character_not_found(self, client):
        _make_user(client)
        resp = client.post("/characters/9999/set-group", json={"gaming_group_id": None})
        assert resp.status_code == 404

    def test_set_group_unauthenticated(self, client):
        char_id = _make_character(client)
        resp = client.post(
            f"/characters/{char_id}/set-group",
            json={"gaming_group_id": None},
            headers={"X-Test-User": ""},
        )
        # Empty X-Test-User header → no user
        assert resp.status_code in (401, 403)

    def test_set_group_forbidden_for_non_editor(self, client):
        # Owner is someone else; viewer is a non-admin, non-owner
        _make_user(client, discord_id="other_player", display_name="Other")
        char_id = _make_character(client, owner_discord_id="other_player")
        gid = _make_group(client)
        resp = client.post(
            f"/characters/{char_id}/set-group",
            json={"gaming_group_id": gid},
            headers={"X-Test-User": "test_user_1:NonOwner"},
        )
        assert resp.status_code == 403


class TestSetGroupBypassesVersioning:
    def test_set_group_does_not_create_version(self, client):
        _make_user(client)
        char_id = _make_character(client)
        gid = _make_group(client)
        # Sanity: no versions to start
        sess = client._test_session_factory()
        before = sess.query(CharacterVersion).filter(CharacterVersion.character_id == char_id).count()
        sess.close()
        assert before == 0

        client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": gid})

        sess = client._test_session_factory()
        after = sess.query(CharacterVersion).filter(CharacterVersion.character_id == char_id).count()
        sess.close()
        assert after == 0

    def test_set_group_does_not_modify_published_state(self, client):
        """Setting a group on a published character must NOT change
        published_state and must NOT trigger has_unpublished_changes."""
        _make_user(client)
        sess = client._test_session_factory()
        c = Character(
            name="Published",
            owner_discord_id="183026066498125825",
            is_published=True,
        )
        sess.add(c)
        sess.commit()
        # Build the published snapshot from to_dict so it matches the current draft
        c.published_state = c.to_dict()
        sess.commit()
        char_id = c.id
        snapshot_before = dict(c.published_state)
        # Sanity: the freshly published character has no unpublished changes
        assert c.has_unpublished_changes is False
        sess.close()

        gid = _make_group(client)
        client.post(f"/characters/{char_id}/set-group", json={"gaming_group_id": gid})

        sess = client._test_session_factory()
        refreshed = sess.query(Character).filter(Character.id == char_id).first()
        # published_state is byte-for-byte unchanged
        assert refreshed.published_state == snapshot_before
        # And no "modified" badge appears
        assert refreshed.has_unpublished_changes is False
        sess.close()


# ---------------------------------------------------------------------------
# Homepage clustering
# ---------------------------------------------------------------------------


class TestHomepageClustering:
    def test_index_clusters_by_group(self, client):
        _make_user(client)
        gid_t = _make_group(client, "Tuesday Group")
        gid_w = _make_group(client, "Wednesday Group")
        sess = client._test_session_factory()
        sess.add_all([
            Character(name="Tuesday One", owner_discord_id="183026066498125825", gaming_group_id=gid_t),
            Character(name="Tuesday Two", owner_discord_id="183026066498125825", gaming_group_id=gid_t),
            Character(name="Wednesday One", owner_discord_id="183026066498125825", gaming_group_id=gid_w),
            Character(name="Loner", owner_discord_id="183026066498125825"),
        ])
        sess.commit()
        sess.close()

        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.text
        # All three section headings appear
        assert "Tuesday Group" in body
        assert "Wednesday Group" in body
        assert "Not assigned to a group" in body
        # Tuesday characters appear under Tuesday section
        # (a coarse but reliable check: order Tuesday before Wednesday before Not assigned)
        assert body.find("Tuesday Group") < body.find("Wednesday Group")
        assert body.find("Wednesday Group") < body.find("Not assigned to a group")

    def test_index_omits_empty_groups(self, client):
        _make_user(client)
        _make_group(client, "Tuesday Group")
        gid_w = _make_group(client, "Wednesday Group")
        sess = client._test_session_factory()
        sess.add(Character(name="Solo", owner_discord_id="183026066498125825", gaming_group_id=gid_w))
        sess.commit()
        sess.close()

        resp = client.get("/")
        body = resp.text
        # Tuesday has no members → its heading must NOT appear
        assert "Tuesday Group" not in body
        assert "Wednesday Group" in body

    def test_index_omits_unassigned_when_empty(self, client):
        _make_user(client)
        gid = _make_group(client, "Tuesday Group")
        sess = client._test_session_factory()
        sess.add(Character(name="In Group", owner_discord_id="183026066498125825", gaming_group_id=gid))
        sess.commit()
        sess.close()

        resp = client.get("/")
        body = resp.text
        assert "Tuesday Group" in body
        assert "Not assigned to a group" not in body


# ---------------------------------------------------------------------------
# Admin manage groups CRUD
# ---------------------------------------------------------------------------


class TestAdminGroupsCRUD:
    def test_admin_groups_page_renders_for_admin(self, client):
        _make_user(client)
        _make_group(client, "Tuesday Group")
        resp = client.get("/admin/groups")
        assert resp.status_code == 200
        assert "Tuesday Group" in resp.text
        assert "Manage Gaming Groups" in resp.text

    def test_admin_groups_page_forbidden_for_non_admin(self, client):
        resp = client.get("/admin/groups", headers={"X-Test-User": "test_user_1:NonAdmin"})
        assert resp.status_code == 403

    def test_admin_create_group(self, client):
        _make_user(client)
        resp = client.post("/admin/groups/new", data={"name": "Friday Group"}, follow_redirects=False)
        assert resp.status_code == 303
        sess = client._test_session_factory()
        assert sess.query(GamingGroup).filter(GamingGroup.name == "Friday Group").first() is not None
        sess.close()

    def test_admin_create_group_empty_name_ignored(self, client):
        _make_user(client)
        resp = client.post("/admin/groups/new", data={"name": "  "}, follow_redirects=False)
        assert resp.status_code == 303
        sess = client._test_session_factory()
        assert sess.query(GamingGroup).count() == 0
        sess.close()

    def test_admin_create_group_duplicate_name_ignored(self, client):
        _make_user(client)
        _make_group(client, "Tuesday Group")
        resp = client.post("/admin/groups/new", data={"name": "Tuesday Group"}, follow_redirects=False)
        assert resp.status_code == 303
        sess = client._test_session_factory()
        assert sess.query(GamingGroup).filter(GamingGroup.name == "Tuesday Group").count() == 1
        sess.close()

    def test_admin_create_group_forbidden_for_non_admin(self, client):
        resp = client.post(
            "/admin/groups/new",
            data={"name": "Sneaky"},
            headers={"X-Test-User": "test_user_1:NonAdmin"},
            follow_redirects=False,
        )
        assert resp.status_code == 403
        sess = client._test_session_factory()
        assert sess.query(GamingGroup).count() == 0
        sess.close()

    def test_admin_rename_group(self, client):
        _make_user(client)
        gid = _make_group(client, "Tuesday Group")
        resp = client.post(
            f"/admin/groups/{gid}/rename",
            data={"name": "Tuesday Night"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        sess = client._test_session_factory()
        g = sess.query(GamingGroup).filter(GamingGroup.id == gid).first()
        assert g.name == "Tuesday Night"
        sess.close()

    def test_admin_rename_to_existing_name_blocked(self, client):
        _make_user(client)
        gid_t = _make_group(client, "Tuesday Group")
        _make_group(client, "Wednesday Group")
        resp = client.post(
            f"/admin/groups/{gid_t}/rename",
            data={"name": "Wednesday Group"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        sess = client._test_session_factory()
        g = sess.query(GamingGroup).filter(GamingGroup.id == gid_t).first()
        assert g.name == "Tuesday Group"  # unchanged
        sess.close()

    def test_admin_rename_forbidden_for_non_admin(self, client):
        gid = _make_group(client, "Tuesday Group")
        resp = client.post(
            f"/admin/groups/{gid}/rename",
            data={"name": "Hax"},
            headers={"X-Test-User": "test_user_1:NonAdmin"},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_admin_delete_group_unassigns_members(self, client):
        _make_user(client)
        gid = _make_group(client, "Tuesday Group")
        sess = client._test_session_factory()
        c = Character(name="Member", owner_discord_id="183026066498125825", gaming_group_id=gid)
        sess.add(c)
        sess.commit()
        char_id = c.id
        sess.close()

        resp = client.post(f"/admin/groups/{gid}/delete", follow_redirects=False)
        assert resp.status_code == 303
        sess = client._test_session_factory()
        # Group is gone
        assert sess.query(GamingGroup).filter(GamingGroup.id == gid).first() is None
        # Character still exists, now unassigned
        c = sess.query(Character).filter(Character.id == char_id).first()
        assert c is not None
        assert c.gaming_group_id is None
        sess.close()

    def test_admin_delete_forbidden_for_non_admin(self, client):
        gid = _make_group(client, "Tuesday Group")
        resp = client.post(
            f"/admin/groups/{gid}/delete",
            headers={"X-Test-User": "test_user_1:NonAdmin"},
            follow_redirects=False,
        )
        assert resp.status_code == 403
