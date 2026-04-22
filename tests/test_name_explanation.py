"""Tests for the name_explanation field: model serialization, edit routes,
and version restore.
"""

from app.models import Character
from app.services.versions import _restore_character_from_state


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


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TestModel:
    def test_default_is_empty_string(self, db):
        c = Character(name="Test")
        db.add(c)
        db.flush()
        assert c.name_explanation == ""

    def test_to_dict_includes_explanation(self):
        c = Character(name="Test", name_explanation="A name of quiet water.")
        assert c.to_dict()["name_explanation"] == "A name of quiet water."

    def test_to_dict_emits_empty_string_when_missing(self):
        c = Character(name="Test")
        # Column default only applies on flush; before flush it's None.
        assert c.to_dict()["name_explanation"] == ""

    def test_from_dict_reads_explanation(self):
        c = Character.from_dict({"name": "Test", "name_explanation": "Meaningful."})
        assert c.name_explanation == "Meaningful."

    def test_from_dict_defaults_to_empty(self):
        c = Character.from_dict({"name": "Test"})
        assert c.name_explanation == ""


# ---------------------------------------------------------------------------
# Autosave JSON endpoint
# ---------------------------------------------------------------------------


class TestAutosave:
    def test_autosave_sets_explanation(self, client):
        cid = _seed_character(client)
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name_explanation": "Born under a winter moon."},
        )
        assert resp.status_code == 200
        char = client._test_session_factory().query(Character).filter(Character.id == cid).first()
        assert char.name_explanation == "Born under a winter moon."

    def test_autosave_clears_explanation_with_empty_string(self, client):
        cid = _seed_character(client, name_explanation="Old text.")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name_explanation": ""},
        )
        assert resp.status_code == 200
        char = client._test_session_factory().query(Character).filter(Character.id == cid).first()
        assert char.name_explanation == ""

    def test_autosave_coerces_null_to_empty(self, client):
        cid = _seed_character(client, name_explanation="Old text.")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name_explanation": None},
        )
        assert resp.status_code == 200
        char = client._test_session_factory().query(Character).filter(Character.id == cid).first()
        assert char.name_explanation == ""

    def test_autosave_leaves_explanation_alone_when_absent(self, client):
        cid = _seed_character(client, name_explanation="Original prose.")
        resp = client.post(
            f"/characters/{cid}/autosave",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        char = client._test_session_factory().query(Character).filter(Character.id == cid).first()
        assert char.name_explanation == "Original prose."


# ---------------------------------------------------------------------------
# Form POST (legacy update route)
# ---------------------------------------------------------------------------


class TestFormUpdate:
    def test_form_post_persists_explanation(self, client):
        # Go through the real create+edit flow so permissions and the form
        # parser are exercised, not just the model.
        resp = client.post("/characters", data={}, follow_redirects=False)
        assert resp.status_code == 303
        cid = int(resp.headers["location"].rstrip("/").split("/")[-2])
        form = {
            "name": "Akodo Ginawa",
            "name_explanation": "Chosen for the Akodo ancestor who loved peace.",
            "school": "akodo_bushi",
            "school_ring_choice": "Water",
            "honor": "1.0", "rank": "1.0", "recognition": "1.0",
            "starting_xp": "150", "earned_xp": "0",
            "attack": "1", "parry": "1",
            "ring_air": "2", "ring_fire": "2", "ring_earth": "2",
            "ring_water": "3", "ring_void": "2",
        }
        resp = client.post(f"/characters/{cid}", data=form, follow_redirects=False)
        assert resp.status_code == 303
        char = client._test_session_factory().query(Character).filter(Character.id == cid).first()
        assert char.name_explanation == "Chosen for the Akodo ancestor who loved peace."


# ---------------------------------------------------------------------------
# Version restore
# ---------------------------------------------------------------------------


class TestVersionRestore:
    def test_restore_sets_explanation_from_state(self):
        c = Character(name="Test", name_explanation="Current draft note.")
        _restore_character_from_state(c, {"name": "Test", "name_explanation": "Older note."})
        assert c.name_explanation == "Older note."

    def test_restore_clears_explanation_when_state_has_none(self):
        c = Character(name="Test", name_explanation="Current draft note.")
        _restore_character_from_state(c, {"name": "Test"})
        assert c.name_explanation == ""


# ---------------------------------------------------------------------------
# Draft diff: editing name_explanation triggers a "modified" draft
# ---------------------------------------------------------------------------


class TestDraftDiff:
    def test_has_unpublished_changes_when_explanation_differs(self, db):
        c = Character(name="Test", is_published=True, name_explanation="New text.")
        db.add(c)
        db.flush()
        # Seed published_state from a snapshot with DIFFERENT explanation.
        snapshot = c.to_dict()
        snapshot["name_explanation"] = "Old text."
        c.published_state = snapshot
        assert c.has_unpublished_changes is True

    def test_no_changes_when_explanation_matches(self, db):
        c = Character(name="Test", is_published=True, name_explanation="Same text.")
        db.add(c)
        db.flush()
        c.published_state = c.to_dict()
        assert c.has_unpublished_changes is False
