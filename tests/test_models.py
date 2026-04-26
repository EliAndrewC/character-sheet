"""Tests for the Character model."""

from app.models import Character


class TestCharacterRings:
    def test_rings_property(self):
        c = Character(
            name="Test", ring_air=3, ring_fire=2, ring_earth=4, ring_water=3, ring_void=2
        )
        assert c.rings == {
            "Air": 3, "Fire": 2, "Earth": 4, "Water": 3, "Void": 2
        }

    def test_default_rings_from_db(self, db):
        """Column defaults only apply when flushed to the DB."""
        c = Character(name="Test")
        db.add(c)
        db.flush()
        assert c.rings == {
            "Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2
        }


class TestCharacterToDict:
    def test_includes_rings_dict(self, db):
        c = Character(name="Test", school="akodo_bushi", school_ring_choice="Water")
        db.add(c)
        db.flush()
        d = c.to_dict()
        assert d["rings"] == {"Air": 2, "Fire": 2, "Earth": 2, "Water": 2, "Void": 2}

    def test_includes_core_fields(self):
        c = Character(
            name="Akodo Toturi",
            player_name="Eli",
            school="akodo_bushi",
            school_ring_choice="Water",
            honor=2.0,
            rank=1.5,
        )
        d = c.to_dict()
        assert d["name"] == "Akodo Toturi"
        assert d["player_name"] == "Eli"
        assert d["school"] == "akodo_bushi"
        assert d["school_ring_choice"] == "Water"
        assert d["honor"] == 2.0
        assert d["rank"] == 1.5

    def test_empty_collections_default(self):
        c = Character(name="Test")
        d = c.to_dict()
        assert d["skills"] == {}
        assert d["knacks"] == {}
        assert d["advantages"] == []
        assert d["disadvantages"] == []


class TestCharacterFromDict:
    def test_from_dict_with_rings(self):
        data = {
            "name": "Bayushi Kachiko",
            "school": "bayushi_bushi",
            "school_ring_choice": "Fire",
            "rings": {"Air": 3, "Fire": 3, "Earth": 2, "Water": 2, "Void": 2},
        }
        c = Character.from_dict(data)
        assert c.name == "Bayushi Kachiko"
        assert c.ring_air == 3
        assert c.ring_fire == 3
        assert c.ring_earth == 2

    def test_from_dict_defaults(self):
        c = Character.from_dict({"name": "Minimal"})
        assert c.ring_air == 2
        assert c.honor == 1.0
        assert c.starting_xp == 150
        assert c.skills == {}
        assert c.advantages == []

    def test_from_dict_with_collections(self):
        data = {
            "name": "Test",
            "skills": {"bragging": 2, "precepts": 3},
            "knacks": {"feint": 2},
            "advantages": ["lucky"],
            "disadvantages": ["proud"],
        }
        c = Character.from_dict(data)
        assert c.skills == {"bragging": 2, "precepts": 3}
        assert c.knacks == {"feint": 2}
        assert c.advantages == ["lucky"]
        assert c.disadvantages == ["proud"]

    def test_roundtrip(self):
        data = {
            "name": "Roundtrip",
            "player_name": "Tester",
            "school": "akodo_bushi",
            "school_ring_choice": "Water",
            "rings": {"Air": 3, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2},
            "skills": {"precepts": 3},
            "knacks": {"double_attack": 1, "feint": 2, "iaijutsu": 1},
            "advantages": ["fierce"],
            "disadvantages": ["proud"],
            "honor": 2.5,
            "rank": 1.0,
            "recognition": 1.0,
            "recognition_halved": False,
            "starting_xp": 150,
            "earned_xp": 20,
            "notes": "Some notes",
        }
        c = Character.from_dict(data)
        d = c.to_dict()
        assert d["name"] == "Roundtrip"
        assert d["rings"] == {"Air": 3, "Fire": 2, "Earth": 2, "Water": 4, "Void": 2}
        assert d["skills"] == {"precepts": 3}
        assert d["knacks"] == {"double_attack": 1, "feint": 2, "iaijutsu": 1}
        assert d["advantages"] == ["fierce"]
        assert d["disadvantages"] == ["proud"]
        assert d["honor"] == 2.5
        assert d["earned_xp"] == 20
        assert d["notes"] == "Some notes"


class TestPublishStatus:
    def test_unpublished_character(self):
        c = Character(name="Test", is_published=False)
        assert c.has_unpublished_changes is False
        assert c.publish_status == "unpublished"

    def test_published_no_changes(self, db):
        c = Character(name="Test", school="akodo_bushi", is_published=True)
        db.add(c)
        db.flush()
        c.published_state = c.to_dict()
        assert c.has_unpublished_changes is False
        assert c.publish_status == "published"

    def test_published_with_changes(self, db):
        c = Character(name="Test", school="akodo_bushi", honor=1.0, is_published=True)
        db.add(c)
        db.flush()
        c.published_state = c.to_dict()
        c.honor = 3.0
        assert c.has_unpublished_changes is True
        assert c.publish_status == "modified"

    def test_published_state_none(self):
        c = Character(name="Test", is_published=True, published_state=None)
        assert c.has_unpublished_changes is False
        assert c.publish_status == "published"

    # ----------------------------------------------------------------------
    # Mutable session state must not flip a published character to
    # "modified". /track writes wounds, void, action dice, etc. to the
    # row but never updates published_state - and these aren't really
    # stat-level changes worth versioning.
    # ----------------------------------------------------------------------

    def _published(self, db, **kwargs):
        kwargs.setdefault("school", "akodo_bushi")
        c = Character(name="Sessioned", is_published=True, **kwargs)
        db.add(c)
        db.flush()
        c.published_state = c.to_dict()
        # Sanity: clean state right after publish.
        assert c.has_unpublished_changes is False
        return c

    def test_taking_light_wounds_does_not_flip_to_modified(self, db):
        c = self._published(db)
        c.current_light_wounds = 7
        assert c.has_unpublished_changes is False
        assert c.publish_status == "published"

    def test_taking_serious_wounds_does_not_flip_to_modified(self, db):
        c = self._published(db)
        c.current_serious_wounds = 2
        assert c.has_unpublished_changes is False

    def test_spending_void_does_not_flip_to_modified(self, db):
        c = self._published(db, ring_void=4)
        c.current_void_points = 2
        c.current_temp_void_points = 1
        assert c.has_unpublished_changes is False

    def test_rolling_action_dice_does_not_flip_to_modified(self, db):
        c = self._published(db)
        c.action_dice = [{"value": 7, "spent": False}, {"value": 3, "spent": True}]
        assert c.has_unpublished_changes is False

    def test_priest_precepts_pool_change_does_not_flip_to_modified(self, db):
        c = self._published(db, school="priest",
                            knacks={"conviction": 3, "otherworldliness": 3, "pontificate": 3})
        c.precepts_pool = [{"value": 9}, {"value": 6}, {"value": 4}]
        assert c.has_unpublished_changes is False

    def test_google_sheet_id_change_does_not_flip_to_modified(self, db):
        # Exporting to Google Sheets stamps google_sheet_id. That's pure
        # export metadata, not a stat change.
        c = self._published(db)
        c.google_sheet_id = "1AbCdEf-spreadsheet-id"
        assert c.has_unpublished_changes is False

    def test_real_stat_change_still_flips_to_modified(self, db):
        # Regression guard: with the expanded skip set we still need to
        # detect actual gameplay changes. A skill bump must still trip
        # has_unpublished_changes.
        c = self._published(db)
        c.skills = {"bragging": 2}
        assert c.has_unpublished_changes is True
        assert c.publish_status == "modified"


class TestCharacterDB:
    def test_create_and_query(self, db):
        c = Character(name="DB Test", school="akodo_bushi", school_ring_choice="Water")
        db.add(c)
        db.commit()

        result = db.query(Character).filter(Character.name == "DB Test").first()
        assert result is not None
        assert result.school == "akodo_bushi"
        assert result.ring_air == 2

    def test_json_fields_persist(self, db):
        c = Character(
            name="JSON Test",
            skills={"bragging": 2},
            advantages=["lucky"],
        )
        db.add(c)
        db.commit()

        result = db.query(Character).filter(Character.name == "JSON Test").first()
        assert result.skills == {"bragging": 2}
        assert result.advantages == ["lucky"]

    def test_update_fields(self, db):
        c = Character(name="Update Test", honor=1.0)
        db.add(c)
        db.commit()

        c.honor = 3.0
        c.skills = {"precepts": 2}
        db.commit()

        result = db.query(Character).filter(Character.name == "Update Test").first()
        assert result.honor == 3.0
        assert result.skills == {"precepts": 2}

    def test_delete(self, db):
        c = Character(name="Delete Me")
        db.add(c)
        db.commit()
        char_id = c.id

        db.delete(c)
        db.commit()

        assert db.query(Character).filter(Character.id == char_id).first() is None
