"""Tests for page and API routes."""

import pytest

from app.models import Character
from tests.conftest import make_character_form, query_db


def _seed_character(client, **kwargs):
    """Insert a character directly into the test DB via the client's connection."""
    session = client._test_session_factory()
    defaults = dict(
        name="Test Samurai",
        school="akodo_bushi",
        school_ring_choice="Water",
        ring_water=3,
        knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        owner_discord_id="183026066498125825",
        is_published=True,
        published_state={"name": kwargs.get("name", "Test Samurai")},
    )
    defaults.update(kwargs)
    c = Character(**defaults)
    session.add(c)
    session.commit()
    return c.id


class TestIndexPage:
    def test_empty_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "No characters yet" in resp.text

    def test_index_lists_published_characters(self, client):
        _seed_character(client, name="Akodo Toturi", is_published=True)

        resp = client.get("/")
        assert resp.status_code == 200
        assert "Akodo Toturi" in resp.text

    def test_index_shows_draft_to_owner(self, client):
        _seed_character(client, name="My Draft", is_published=False,
                        owner_discord_id="183026066498125825")

        resp = client.get("/")
        assert "My Draft" in resp.text


class TestCreateCharacter:
    def test_create_redirects_to_edit(self, client):
        resp = client.post("/characters", follow_redirects=False)
        assert resp.status_code == 303
        assert "/edit" in resp.headers["location"]

    def test_create_makes_blank_character(self, client):
        client.post("/characters")
        char = query_db(client).first()
        assert char is not None
        assert char.name == "New Character"
        assert char.is_published is False
        assert char.owner_discord_id == "183026066498125825"

    def test_create_starts_with_full_void_points(self, client):
        """New characters start with full void points (min ring = 2)."""
        client.post("/characters")
        char = query_db(client).first()
        assert char.current_void_points == 2

    def test_autosave_updates_void_for_unpublished(self, client):
        """Autosave on unpublished character keeps VP at max when rings change."""
        client.post("/characters")
        char = query_db(client).first()
        cid = char.id
        # Raise Void ring to 3 - void max should become 2 (min of all rings)
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 2  # min ring is still 2
        # Raise all rings to 3
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 3, "Fire": 3, "Earth": 3, "Water": 3, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 3  # min ring is now 3

    def test_autosave_does_not_change_void_for_published(self, client):
        """Autosave on published character does NOT reset VP when rings change."""
        cid = _seed_character(client, current_void_points=1, is_published=True)
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 3, "Fire": 3, "Earth": 3, "Water": 3, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 1  # unchanged


class TestViewCharacter:
    def test_view_character(self, client):
        cid = _seed_character(
            client,
            name="View Test",
            school="bayushi_bushi",
            school_ring_choice="Fire",
            ring_fire=3,
            skills={"bragging": 2},
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )

        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "View Test" in resp.text

    def test_view_shows_xp(self, client):
        cid = _seed_character(client, name="XP Test", ring_fire=3)

        resp = client.get(f"/characters/{cid}")
        assert "Total Spent" in resp.text
        assert "Unspent" in resp.text

    def test_view_nonexistent_404(self, client):
        resp = client.get("/characters/999")
        assert resp.status_code == 404


class TestEditCharacter:
    def test_edit_page_loads(self, client):
        cid = _seed_character(client, name="Edit Test")

        resp = client.get(f"/characters/{cid}/edit")
        assert resp.status_code == 200

    def test_edit_nonexistent_404(self, client):
        resp = client.get("/characters/999/edit")
        assert resp.status_code == 404


class TestUpdateCharacter:
    def test_update_changes_fields(self, client):
        cid = _seed_character(client, name="Original")

        form = make_character_form(name="Updated", ring_air="4", honor="3.0")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303

        char = query_db(client).filter(Character.id == cid).first()
        assert char.name == "Updated"
        assert char.ring_air == 4
        assert char.honor == 3.0

    def test_update_nonexistent_404(self, client):
        form = make_character_form()
        resp = client.post("/characters/999", data=form)
        assert resp.status_code == 404


class TestDeleteCharacter:
    def test_delete_removes_character(self, client):
        cid = _seed_character(client, name="Delete Me")

        resp = client.post(f"/characters/{cid}/delete", follow_redirects=False)
        assert resp.status_code == 303
        assert query_db(client).count() == 0

    def test_delete_nonexistent_no_error(self, client):
        resp = client.post("/characters/999/delete", follow_redirects=False)
        assert resp.status_code == 303


class TestAutoSave:
    def test_autosave_updates_character(self, client):
        cid = _seed_character(client, name="Before Save")

        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "After Save", "rings": {"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        char = query_db(client).filter(Character.id == cid).first()
        assert char.name == "After Save"
        assert char.ring_air == 3

    def test_autosave_partial_update(self, client):
        cid = _seed_character(client, name="Original", honor=1.0)

        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"honor": 3.0},
        )
        assert resp.status_code == 200

        char = query_db(client).filter(Character.id == cid).first()
        assert char.honor == 3.0
        assert char.name == "Original"  # unchanged


    def test_autosave_owner_reassignment_by_admin(self, client):
        """Admin can reassign character ownership via autosave."""
        from app.models import User
        session = client._test_session_factory()
        # Create the admin user and another user
        session.add(User(discord_id="183026066498125825", discord_name="admin", display_name="Admin"))
        session.add(User(discord_id="999", discord_name="other", display_name="Other Player"))
        session.commit()

        cid = _seed_character(client, name="Reassign Me")

        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"owner_discord_id": "999"},
        )
        assert resp.status_code == 200

        char = query_db(client).filter(Character.id == cid).first()
        assert char.owner_discord_id == "999"
        assert char.player_name == "Other Player"


class TestRankRecognitionAwards:
    """GM-awarded Rank/Recognition bonuses: persistence, validation, and the
    metadata-only source endpoint that bypasses the version system."""

    def test_autosave_persists_awards_list(self, client):
        cid = _seed_character(client, rank=7.5, recognition=7.5)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 8.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {
                        "id": "a1",
                        "rank_delta": 1.0,
                        "recognition_delta": 0.5,
                        "source": "Defended village",
                        "created_at": "2026-04-09T00:00:00",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank == 8.5
        assert char.recognition == 8.0
        assert len(char.rank_recognition_awards) == 1
        assert char.rank_recognition_awards[0]["source"] == "Defended village"
        assert char.rank_recognition_awards[0]["rank_delta"] == 1.0

    def test_autosave_rejects_negative_recognition_delta(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 0, "recognition_delta": -1.0, "source": "x"},
                ],
            },
        )
        assert resp.status_code == 400
        assert "Recognition delta cannot be negative" in resp.json()["error"]

    def test_autosave_rejects_empty_source(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0, "source": ""},
                ],
            },
        )
        assert resp.status_code == 400
        assert "source" in resp.json()["error"].lower()

    def test_autosave_rejects_non_list_awards(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rank_recognition_awards": "not a list"},
        )
        assert resp.status_code == 400

    def test_autosave_rejects_non_dict_award_entry(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"rank_recognition_awards": ["not a dict"]},
        )
        assert resp.status_code == 400

    def test_autosave_rejects_non_numeric_delta(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": "abc", "recognition_delta": 0, "source": "x"},
                ],
            },
        )
        assert resp.status_code == 400

    def test_set_award_source_updates_only_source(self, client):
        cid = _seed_character(client)
        # Seed with one award via autosave
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0, "source": "old"},
                ],
            },
        )
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "new source"},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["source"] == "new source"
        # Deltas untouched
        assert char.rank_recognition_awards[0]["rank_delta"] == 1.0

    def test_set_award_source_unknown_award_404(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "missing", "source": "x"},
        )
        assert resp.status_code == 404

    def test_set_award_source_requires_award_id(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"source": "x"},
        )
        assert resp.status_code == 400

    def test_set_award_source_requires_source(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": ""},
        )
        assert resp.status_code == 400

    def test_source_change_does_not_trigger_unpublished(self, client):
        """Editing only an award's source must not flip the character to
        'modified' state — that's the whole point of the metadata endpoint."""
        cid = _seed_character(client)
        # Add an award and publish so we have a baseline
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 8.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0.5,
                     "source": "Original reason", "created_at": "2026-04-09T00:00:00"},
                ],
            },
        )
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes is False

        # Edit only the source via the metadata endpoint
        client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "Reworded reason"},
        )

        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["source"] == "Reworded reason"
        assert char.has_unpublished_changes is False, (
            "Editing only the award source must NOT trigger a draft"
        )

    def test_delta_change_does_trigger_unpublished(self, client):
        """In contrast, changing an award's delta IS a versionable change."""
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 8.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0.5,
                     "source": "Reason", "created_at": "2026-04-09T00:00:00"},
                ],
            },
        )
        client.post(f"/characters/{cid}/publish", json={"summary": "Initial"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes is False

        # Edit the rank delta via the regular autosave path
        client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank": 9.5,
                "recognition": 8.0,
                "rank_recognition_awards": [
                    {"id": "a1", "rank_delta": 2.0, "recognition_delta": 0.5,
                     "source": "Reason", "created_at": "2026-04-09T00:00:00"},
                ],
            },
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.has_unpublished_changes is True

    def test_set_award_source_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "x"},
            headers={"X-Test-User": ""},
        )
        assert resp.status_code == 401

    def test_set_award_source_404_for_unknown_character(self, client):
        resp = client.post(
            "/characters/9999/set-award-source",
            json={"award_id": "a1", "source": "x"},
        )
        assert resp.status_code == 404

    def test_award_delta_only_diff_marks_unpublished(self, client):
        """Direct unit-level check that the awards-only diff branch fires.

        The published snapshot has one award with rank_delta=1.0; we mutate
        the live awards JSON to rank_delta=2.0 *without* touching the
        character's rank field. The diff comparison must spot this via the
        rank_recognition_awards branch and return True.
        """
        from app.models import award_deltas_for_diff
        cid = _seed_character(client)
        char = query_db(client).filter(Character.id == cid).first()
        # Publish a baseline that already has one award.
        char.rank_recognition_awards = [
            {"id": "a1", "rank_delta": 1.0, "recognition_delta": 0.5,
             "source": "Reason", "created_at": "2026-04-09T00:00:00"},
        ]
        char.is_published = True
        char.published_state = char.to_dict()
        client._test_session_factory().merge(char)
        # Now mutate the awards delta but keep everything else identical.
        char.rank_recognition_awards = [
            {"id": "a1", "rank_delta": 2.0, "recognition_delta": 0.5,
             "source": "Reason", "created_at": "2026-04-09T00:00:00"},
        ]
        assert char.has_unpublished_changes is True
        # And the helper itself reports the same deltas after stripping source
        assert award_deltas_for_diff(char.rank_recognition_awards) != \
            award_deltas_for_diff(char.published_state["rank_recognition_awards"])


class TestTrackState:
    def test_track_wounds(self, client):
        cid = _seed_character(client, name="Track Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": 3, "current_serious_wounds": 1},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_light_wounds == 3
        assert char.current_serious_wounds == 1

    def test_track_void_points(self, client):
        cid = _seed_character(client, name="Void Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_void_points": 2},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 2

    def test_track_adventure_state(self, client):
        cid = _seed_character(client, name="Adventure Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"adventure_state": {"lucky_used": True, "adventure_raises_used": 3}},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.adventure_state["lucky_used"] is True
        assert char.adventure_state["adventure_raises_used"] == 3

    def test_track_nonexistent_404(self, client):
        resp = client.post("/characters/999/track", json={"current_light_wounds": 1})
        assert resp.status_code == 404

    def test_track_clamps_negative(self, client):
        cid = _seed_character(client, name="Clamp Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": -5},
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_light_wounds == 0

    def test_track_requires_auth(self, client):
        cid = _seed_character(client, name="Track Auth Test")
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": 1},
            headers={"X-Test-User": ""},
        )
        assert resp.status_code == 401

    def test_track_forbidden_for_non_editor(self, client):
        from app.models import User
        # Seed a character owned by a different user
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, name="Track Permission", owner_discord_id="999")
        # Use a different non-admin test user
        resp = client.post(
            f"/characters/{cid}/track",
            json={"current_light_wounds": 1},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403


class TestPublish:
    def test_publish_creates_version(self, client):
        cid = _seed_character(client, name="Publish Me", is_published=False)

        resp = client.post(f"/characters/{cid}/publish")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert data["version_number"] == 1

        char = query_db(client).filter(Character.id == cid).first()
        assert char.is_published is True
        assert char.published_state is not None

    def test_publish_with_custom_summary(self, client):
        cid = _seed_character(client, name="Custom Summary", is_published=False)
        resp = client.post(
            f"/characters/{cid}/publish",
            json={"summary": "Spending XP from the latest adventure"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "Spending XP from the latest adventure"

    def test_publish_records_author(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="Author Test", is_published=False)
        client.post(f"/characters/{cid}/publish", json={"summary": "test"})
        session = client._test_session_factory()
        v = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid
        ).first()
        assert v.author_discord_id == "183026066498125825"


class TestUpdateVersionSummary:
    def test_update_summary(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="Edit Summary")
        client.post(f"/characters/{cid}/publish", json={"summary": "original"})
        session = client._test_session_factory()
        v = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid
        ).first()

        resp = client.post(
            f"/characters/{cid}/versions/{v.id}/summary",
            json={"summary": "updated summary"},
        )
        assert resp.status_code == 200
        session.refresh(v)
        assert v.summary == "updated summary"

    def test_update_nonexistent_version_404(self, client):
        cid = _seed_character(client, name="No Version")
        resp = client.post(
            f"/characters/{cid}/versions/999/summary",
            json={"summary": "nope"},
        )
        assert resp.status_code == 404


class TestRevert:
    def test_revert_to_previous_version(self, client):
        from app.models import CharacterVersion
        cid = _seed_character(client, name="V1")

        # Publish v1
        client.post(f"/characters/{cid}/publish")

        # Modify and publish v2
        client.post(f"/characters/{cid}/autosave", json={"name": "V2"})
        client.post(f"/characters/{cid}/publish")

        # Get v1's id
        session = client._test_session_factory()
        v1 = session.query(CharacterVersion).filter(
            CharacterVersion.character_id == cid,
            CharacterVersion.version_number == 1,
        ).first()

        # Revert to v1
        resp = client.post(f"/characters/{cid}/revert/{v1.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reverted"
        assert data["version_number"] == 3

        char = query_db(client).filter(Character.id == cid).first()
        assert char.name == "V1"


class TestVersionHistory:
    def test_get_versions(self, client):
        cid = _seed_character(client, name="Version Test")
        client.post(f"/characters/{cid}/publish")

        resp = client.get(f"/characters/{cid}/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version_number"] == 1


class TestSchoolInfoPartial:
    def test_valid_school(self, client):
        resp = client.get("/characters/api/school-info/akodo_bushi")
        assert resp.status_code == 200
        assert "Water" in resp.text
        assert "Special Ability" in resp.text

    def test_invalid_school_empty(self, client):
        resp = client.get("/characters/api/school-info/nonexistent")
        assert resp.status_code == 200
        assert resp.text == ""


class TestXPCalcPartial:
    def test_xp_calc_returns_breakdown(self, client):
        form = make_character_form(ring_fire="3", skill_precepts="3")
        resp = client.post("/characters/api/xp-calc", data=form)
        assert resp.status_code == 200
        assert "Unspent" in resp.text
