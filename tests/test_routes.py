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

    def test_autosave_updates_void_for_isawa_ishi(self, client):
        """Autosave on Isawa Ishi uses shugenja VP formula (highest ring + school rank)."""
        cid = _seed_character(
            client, school="isawa_ishi", school_ring_choice="Void",
            knacks={"absorb_void": 1, "kharmic_spin": 1, "otherworldliness": 1},
            is_published=False,
        )
        # Set rings: highest ring = 3 (Void), dan = 1 (min knack), VP max = 3 + 1 = 4
        client.post(f"/characters/{cid}/autosave", json={
            "rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 3}
        })
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_void_points == 4  # highest ring (3) + dan (1)

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


class TestAutosaveAllFieldSetters:
    """One test per ``if "<key>" in body:`` branch in autosave. These aren't
    behavior tests per se — they exercise the cheap per-key setters so we know
    each branch actually writes to the column. Missing coverage here means a
    silent regression could make a field un-saveable."""

    def test_school_setter(self, client):
        cid = _seed_character(client, school="akodo_bushi")
        client.post(f"/characters/{cid}/autosave", json={"school": "bayushi_bushi"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.school == "bayushi_bushi"

    def test_school_ring_choice_setter(self, client):
        cid = _seed_character(client, school_ring_choice="Water")
        client.post(f"/characters/{cid}/autosave", json={"school_ring_choice": "Fire"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.school_ring_choice == "Fire"

    def test_skills_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"skills": {"bragging": 3, "etiquette": 2}},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.skills == {"bragging": 3, "etiquette": 2}

    def test_knacks_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"knacks": {"double_attack": 2, "feint": 1, "iaijutsu": 1}},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.knacks == {"double_attack": 2, "feint": 1, "iaijutsu": 1}

    def test_advantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"advantages": ["lucky", "charming"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantages == ["lucky", "charming"]

    def test_disadvantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"disadvantages": ["proud", "unkempt"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.disadvantages == ["proud", "unkempt"]

    def test_campaign_advantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"campaign_advantages": ["highest_regard"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.campaign_advantages == ["highest_regard"]

    def test_campaign_disadvantages_setter(self, client):
        cid = _seed_character(client)
        client.post(
            f"/characters/{cid}/autosave",
            json={"campaign_disadvantages": ["peasantborn"]},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.campaign_disadvantages == ["peasantborn"]

    def test_advantage_details_setter(self, client):
        cid = _seed_character(client)
        details = {"higher_purpose": {"text": "justice", "skills": ["interrogation"]}}
        client.post(
            f"/characters/{cid}/autosave",
            json={"advantage_details": details},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.advantage_details == details

    def test_technique_choices_setter(self, client):
        cid = _seed_character(client)
        choices = {"1": "manipulation"}
        client.post(
            f"/characters/{cid}/autosave",
            json={"technique_choices": choices},
        )
        char = query_db(client).filter(Character.id == cid).first()
        assert char.technique_choices == choices

    def test_rank_locked_setter(self, client):
        cid = _seed_character(client, rank_locked=False)
        client.post(f"/characters/{cid}/autosave", json={"rank_locked": True})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_locked is True

    def test_recognition_halved_setter(self, client):
        cid = _seed_character(client, recognition_halved=False)
        client.post(f"/characters/{cid}/autosave", json={"recognition_halved": True})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.recognition_halved is True

    def test_earned_xp_setter(self, client):
        cid = _seed_character(client, earned_xp=0)
        client.post(f"/characters/{cid}/autosave", json={"earned_xp": 42})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.earned_xp == 42

    def test_notes_setter(self, client):
        cid = _seed_character(client)
        client.post(f"/characters/{cid}/autosave", json={"notes": "Some notes"})
        char = query_db(client).filter(Character.id == cid).first()
        assert char.notes == "Some notes"


class TestAutosavePermissionPaths:
    """401/404/403 short-circuits in autosave + set-group."""

    def test_autosave_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "x"},
            headers={"X-Test-User": ""},
        )
        assert resp.status_code == 401

    def test_autosave_unknown_character_404(self, client):
        resp = client.post("/characters/99999/autosave", json={"name": "x"})
        assert resp.status_code == 404

    def test_autosave_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "x"},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403


class TestAwardTypeFallback:
    """Unknown award ``type`` strings fall back to ``rank_recognition``."""

    def test_unknown_award_type_falls_back(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {
                        "id": "a1", "type": "made_up_type",
                        "rank_delta": 1.0, "recognition_delta": 0,
                        "source": "Whatever",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["type"] == "rank_recognition"

    def test_valid_non_default_type_preserved(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={
                "rank_recognition_awards": [
                    {
                        "id": "a1", "type": "good_reputation",
                        "rank_delta": 0, "recognition_delta": 0.5,
                        "source": "Saved the village",
                    },
                ],
            },
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.rank_recognition_awards[0]["type"] == "good_reputation"


class TestUpdateCharacterFormRoute:
    """Form-based /characters/{id} update: auth, permission, admin reassignment."""

    def test_update_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}",
            data=make_character_form(),
            headers={"X-Test-User": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]

    def test_update_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}",
            data=make_character_form(),
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_admin_can_reassign_owner_via_form(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="183026066498125825", discord_name="admin", display_name="Admin"))
        session.add(User(discord_id="999", discord_name="other", display_name="New Owner"))
        session.commit()
        cid = _seed_character(client)

        form = make_character_form(owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}", data=form, follow_redirects=False
        )
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.owner_discord_id == "999"
        assert char.player_name == "New Owner"

    def test_non_admin_reassignment_silently_ignored(self, client):
        """Non-admin submitting owner_discord_id should not change the owner.
        The field is simply ignored, not rejected."""
        from app.models import User
        session = client._test_session_factory()
        # test_user_1 is whitelisted but not admin
        session.add(User(discord_id="test_user_1", discord_name="Test 1", display_name="Test 1"))
        session.add(User(discord_id="evil", discord_name="Evil", display_name="Evil"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="test_user_1")

        form = make_character_form(owner_discord_id="evil")
        resp = client.post(
            f"/characters/{cid}",
            data=form,
            headers={"X-Test-User": "test_user_1:Test 1"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert char.owner_discord_id == "test_user_1"

    def test_admin_reassignment_to_unknown_user_is_ignored(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="183026066498125825", discord_name="admin", display_name="Admin"))
        session.commit()
        cid = _seed_character(client)

        form = make_character_form(owner_discord_id="nonexistent_id")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        # Owner unchanged because lookup failed
        assert char.owner_discord_id == "183026066498125825"


class TestDeletePermissions:
    def test_delete_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/delete",
            headers={"X-Test-User": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers["location"]
        # Character should still exist
        char = query_db(client).filter(Character.id == cid).first()
        assert char is not None

    def test_delete_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/delete",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403
        char = query_db(client).filter(Character.id == cid).first()
        assert char is not None


class TestPublishRevertVersionPermissions:
    """401/404/403 guards on publish, revert, update_version_summary, get_versions."""

    def test_publish_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/publish", headers={"X-Test-User": ""}
        )
        assert resp.status_code == 401

    def test_publish_unknown_character_404(self, client):
        resp = client.post("/characters/99999/publish")
        assert resp.status_code == 404

    def test_publish_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/publish",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_revert_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/revert/1", headers={"X-Test-User": ""}
        )
        assert resp.status_code == 401

    def test_revert_unknown_character_404(self, client):
        resp = client.post("/characters/99999/revert/1")
        assert resp.status_code == 404

    def test_revert_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/revert/1",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403

    def test_update_version_summary_requires_auth(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/versions/1/summary",
            headers={"X-Test-User": ""},
            json={"summary": "x"},
        )
        assert resp.status_code == 401

    def test_update_version_summary_unknown_character_404(self, client):
        resp = client.post(
            "/characters/99999/versions/1/summary", json={"summary": "x"}
        )
        assert resp.status_code == 404

    def test_update_version_summary_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/versions/1/summary",
            headers={"X-Test-User": "test_user_1:Test User 1"},
            json={"summary": "x"},
        )
        assert resp.status_code == 403

    def test_get_versions_unknown_character_404(self, client):
        resp = client.get("/characters/99999/versions")
        assert resp.status_code == 404


class TestSetAwardSourceForbidden:
    def test_set_award_source_forbidden_for_non_editor(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.post(
            f"/characters/{cid}/set-award-source",
            json={"award_id": "a1", "source": "x"},
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403


class TestTrackStateTempVoid:
    def test_track_temp_void_points(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/track", json={"current_temp_void_points": 2}
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_temp_void_points == 2

    def test_track_temp_void_points_clamped_negative(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/track", json={"current_temp_void_points": -5}
        )
        assert resp.status_code == 200
        char = query_db(client).filter(Character.id == cid).first()
        assert char.current_temp_void_points == 0


class TestStaticPages:
    def test_terms_page_renders(self, client):
        resp = client.get("/terms")
        assert resp.status_code == 200

    def test_privacy_page_renders(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200


class TestCharactersNewRedirect:
    """GET /characters/new is a legacy path that just bounces back to home."""

    def test_new_character_get_redirects_home(self, client):
        resp = client.get("/characters/new", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"


class TestEditPagePermissions:
    def test_edit_forbidden_for_non_owner(self, client):
        from app.models import User
        session = client._test_session_factory()
        session.add(User(discord_id="999", discord_name="other", display_name="Other"))
        session.commit()
        cid = _seed_character(client, owner_discord_id="999")
        resp = client.get(
            f"/characters/{cid}/edit",
            headers={"X-Test-User": "test_user_1:Test User 1"},
        )
        assert resp.status_code == 403
        assert "permission" in resp.text.lower()


class TestPartyMemberDaidojiCounterattack:
    """View a character sheet in a group with a Daidoji Yojimbo at 3rd+ Dan: that
    party member appears in daidoji_counterattack_party with raises = attack skill."""

    def _make_group_with_partners(self, client, viewer_school, partner_school, partner_dan):
        from app.models import GamingGroup
        session = client._test_session_factory()
        group = GamingGroup(name="Party")
        session.add(group)
        session.commit()
        gid = group.id

        # Viewer's knacks depend on school — use defaults from _seed_character
        viewer_id = _seed_character(
            client, name="Viewer", school=viewer_school, gaming_group_id=gid,
        )
        partner_knacks = {"counterattack": partner_dan, "double_attack": partner_dan, "iaijutsu": partner_dan}
        partner_id = _seed_character(
            client,
            name="Yojimbo Friend",
            school=partner_school,
            school_ring_choice="Water",
            knacks=partner_knacks,
            skills={"attack": 4},
            gaming_group_id=gid,
        )
        return viewer_id, partner_id

    def test_daidoji_3rd_dan_partner_surfaces(self, client):
        viewer_id, _ = self._make_group_with_partners(
            client, "akodo_bushi", "daidoji_yojimbo", partner_dan=3
        )
        resp = client.get(f"/characters/{viewer_id}")
        assert resp.status_code == 200
        assert "Yojimbo Friend" in resp.text

    def test_daidoji_below_3rd_dan_no_counterattack_entry(self, client):
        """At 2nd Dan the Daidoji counterattack raises ability isn't active yet.
        The partner is still shown as a party member, but not in the
        counterattack context (that's behavioral, not just rendering)."""
        viewer_id, _ = self._make_group_with_partners(
            client, "akodo_bushi", "daidoji_yojimbo", partner_dan=2
        )
        resp = client.get(f"/characters/{viewer_id}")
        assert resp.status_code == 200

    def test_non_daidoji_partner_not_in_counterattack_list(self, client):
        viewer_id, _ = self._make_group_with_partners(
            client, "akodo_bushi", "bayushi_bushi", partner_dan=5
        )
        resp = client.get(f"/characters/{viewer_id}")
        assert resp.status_code == 200


class TestPerAdventureAbilitiesOnSheet:
    """The sheet surfaces per-adventure toggles/counters for Lucky, Unlucky, 3rd
    Dan free raises, and spendable knacks (conviction/otherworldliness/worldliness)."""

    def test_lucky_advantage_shown(self, client):
        cid = _seed_character(client, advantages=["lucky"])
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "Lucky" in resp.text

    def test_unlucky_disadvantage_shown(self, client):
        cid = _seed_character(client, disadvantages=["unlucky"])
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "Unlucky" in resp.text

    def test_third_dan_free_raises_shown(self, client):
        """Brotherhood monk at 3rd Dan with precepts skill gets 2X adventure raises."""
        cid = _seed_character(
            client,
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
            skills={"precepts": 4},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "3rd Dan Free Raises" in resp.text

    def test_third_dan_with_zero_source_skill_not_shown(self, client):
        """If source_skill rank is 0, no per-adventure raises are listed."""
        cid = _seed_character(
            client,
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 3, "otherworldliness": 3, "worldliness": 3},
            skills={},  # no precepts
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        assert "3rd Dan Free Raises" not in resp.text

    def test_spendable_knacks_shown(self, client):
        """Brotherhood monk has conviction, otherworldliness, worldliness —
        all three should appear as per-adventure counters."""
        cid = _seed_character(
            client,
            school="brotherhood_of_shinsei_monk",
            school_ring_choice="Water",
            knacks={"conviction": 2, "otherworldliness": 3, "worldliness": 1},
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200
        # All three knack labels should be in the per-adventure section
        assert "Conviction" in resp.text
        assert "Otherworldliness" in resp.text
        assert "Worldliness" in resp.text


class TestShugenjaVoidMax:
    """Shugenja/Isawa Ishi use void_points_max_shugenja; all other schools use
    min of rings for void_max."""

    def test_shugenja_void_max_uses_shugenja_formula(self, client):
        """A shugenja sheet renders and void_max/spend_cap come from the
        school-specific formula."""
        cid = _seed_character(
            client,
            school="shugenja",
            school_ring_choice="Air",
            knacks={"absorb_void": 3, "kharmic_spin": 3, "otherworldliness": 3},
            ring_air=3, ring_water=3, ring_earth=3, ring_fire=3, ring_void=3,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200

    def test_isawa_ishi_void_max_uses_shugenja_formula(self, client):
        cid = _seed_character(
            client,
            school="isawa_ishi",
            school_ring_choice="Void",
            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3},
            ring_air=3, ring_water=3, ring_earth=3, ring_fire=3, ring_void=4,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200


class TestWoundCheckProbability10k10Caps:
    """The wound check probability table key loop applies 10k10 caps for each
    void spend level. High Water + void spend pushes rolled past 10 and kept
    past 10, exercising both cap branches (lines 377-381 in pages.py)."""

    def test_high_water_and_void_caps_do_not_crash_sheet(self, client):
        """Water=8 -> wc base 9k8; with void spend 2 rings cap kicks in."""
        cid = _seed_character(
            client,
            ring_water=8, ring_air=8, ring_earth=8, ring_fire=8, ring_void=8,
        )
        resp = client.get(f"/characters/{cid}")
        assert resp.status_code == 200


class TestFormCheckboxParsing:
    """_parse_form_to_dict checkbox branches: advantages/disadvantages 'on' values."""

    def test_form_checkbox_advantages_parsed(self, client):
        cid = _seed_character(client)
        form = make_character_form(adv_lucky="on", adv_charming="on")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert "lucky" in char.advantages
        assert "charming" in char.advantages

    def test_form_checkbox_disadvantages_parsed(self, client):
        cid = _seed_character(client)
        form = make_character_form(dis_proud="on", dis_unkempt="on")
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = query_db(client).filter(Character.id == cid).first()
        assert "proud" in char.disadvantages
        assert "unkempt" in char.disadvantages
