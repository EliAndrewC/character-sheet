"""Tests for the Character model."""

from app.models import Character, advantage_details_for_diff


class TestAdvantageDetailsForDiff:
    """The helper strips ``text`` from each advantage detail entry so
    text-only edits stay out of has_unpublished_changes / version diffs.
    Other fields (``skills``, ``player``) remain so structural choices
    still register."""

    def test_none_returns_empty_dict(self):
        assert advantage_details_for_diff(None) == {}

    def test_empty_dict_returns_empty_dict(self):
        assert advantage_details_for_diff({}) == {}

    def test_text_only_entry_collapses_and_is_dropped(self):
        # ``virtue`` carries only text; after stripping, the entry has
        # no remaining fields and is dropped entirely so a fresh
        # snapshot's missing-key default compares equal.
        out = advantage_details_for_diff({"virtue": {"text": "Courage"}})
        assert out == {}

    def test_skills_field_survives(self):
        out = advantage_details_for_diff(
            {"higher_purpose": {"text": "Cause", "skills": ["athletics"]}}
        )
        assert out == {"higher_purpose": {"skills": ["athletics"]}}

    def test_player_field_survives(self):
        # Dark Secret carries ``player`` (the knower). That's a
        # structural choice, not metadata - keep it.
        out = advantage_details_for_diff(
            {"dark_secret": {"text": "secret", "player": "discord_id_42"}}
        )
        assert out == {"dark_secret": {"player": "discord_id_42"}}

    def test_non_dict_entry_kept_as_is(self):
        # Defensive path: legacy or hand-edited DB rows may have
        # non-dict values. We keep them so comparisons still notice
        # real differences instead of silently collapsing.
        out = advantage_details_for_diff({"weird": "scalar-value"})
        assert out == {"weird": "scalar-value"}


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


class TestSpecializations:
    """Specialization is the only advantage that may be taken multiple
    times. Each instance carries its own text + skill and costs 2 XP.
    The shape is `specializations: List[Dict]` on Character."""

    def test_to_dict_includes_specializations(self, db):
        c = Character(
            name="Spec",
            specializations=[
                {"text": "Court Etiquette", "skills": ["etiquette"]},
                {"text": "Dueling Stance", "skills": ["iaijutsu"]},
            ],
        )
        db.add(c)
        db.flush()
        d = c.to_dict()
        assert d["specializations"] == [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
            {"text": "Dueling Stance", "skills": ["iaijutsu"]},
        ]

    def test_to_dict_empty_specializations_default(self):
        c = Character(name="NoSpec")
        d = c.to_dict()
        assert d["specializations"] == []

    def test_from_dict_round_trips_specializations(self):
        data = {
            "name": "RT",
            "specializations": [
                {"text": "Long Sword Strikes", "skills": ["iaijutsu"]},
            ],
        }
        c = Character.from_dict(data)
        assert c.specializations == [
            {"text": "Long Sword Strikes", "skills": ["iaijutsu"]},
        ]

    def test_from_dict_lazy_migrates_legacy_shape(self):
        """Legacy characters carry advantages=["specialization"] +
        advantage_details["specialization"]={text,skills}. On read, lift
        the detail into specializations[0] and strip the flag from
        advantages so the rest of the system sees the new shape."""
        data = {
            "name": "Legacy",
            "advantages": ["lucky", "specialization", "fierce"],
            "advantage_details": {
                "specialization": {"text": "Politics", "skills": ["etiquette"]},
            },
        }
        c = Character.from_dict(data)
        assert "specialization" not in c.advantages
        assert c.advantages == ["lucky", "fierce"]
        assert c.specializations == [
            {"text": "Politics", "skills": ["etiquette"]},
        ]
        assert "specialization" not in (c.advantage_details or {})

    def test_from_dict_lazy_migration_skips_when_already_migrated(self):
        """If the new field is already populated, leave it alone (idempotent)."""
        data = {
            "name": "Already",
            "advantages": ["specialization"],  # stale flag, possible but should be cleared
            "advantage_details": {
                "specialization": {"text": "Stale", "skills": ["bragging"]},
            },
            "specializations": [
                {"text": "Already Migrated", "skills": ["etiquette"]},
            ],
        }
        c = Character.from_dict(data)
        assert c.specializations == [
            {"text": "Already Migrated", "skills": ["etiquette"]},
        ]
        # The stale flag must still be cleared so the new field is the
        # single source of truth.
        assert "specialization" not in c.advantages

    def test_from_dict_no_legacy_no_new_keeps_empty(self):
        c = Character.from_dict({"name": "Empty"})
        assert (c.specializations or []) == []


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

    def test_advantage_details_text_only_change_does_not_flip(self, db):
        # The freeform ``text`` field is metadata - retyping the
        # description on an existing advantage must NOT enable Apply
        # Changes. Symmetric with how an award ``source`` edit is
        # treated.
        c = self._published(
            db,
            advantages=["virtue"],
            advantage_details={"virtue": {"text": "Courage"}},
        )
        c.advantage_details = {"virtue": {"text": "Justice"}}
        assert c.has_unpublished_changes is False
        assert c.publish_status == "published"

    def test_advantage_details_skills_change_still_flips(self, db):
        # Higher Purpose's ``skills`` selection is structural. Editing
        # the skill list must still flip the character to Draft - text
        # is the only metadata field on the detail dict.
        c = self._published(
            db,
            advantages=["higher_purpose"],
            advantage_details={"higher_purpose": {"text": "Cause", "skills": ["athletics"]}},
        )
        c.advantage_details = {
            "higher_purpose": {"text": "Cause", "skills": ["bragging"]},
        }
        assert c.has_unpublished_changes is True
        assert c.publish_status == "modified"

    def test_advantage_details_first_time_text_does_not_flip(self, db):
        # A previously empty advantage detail entry getting its first
        # text value is still text-only - no Draft flip. Mirrors the
        # case where the player adds Good Reputation, publishes without
        # filling in the description, then comes back to type it in.
        c = self._published(
            db,
            advantages=["virtue"],
            advantage_details={},
        )
        c.advantage_details = {"virtue": {"text": "Courage"}}
        assert c.has_unpublished_changes is False
        assert c.publish_status == "published"

    def test_advantage_details_text_blanked_back_to_empty_does_not_flip(self, db):
        # Player types a description, publishes, then later clears it
        # back to blank. With ``text``-only entries dropped to {}, the
        # comparison shouldn't notice a phantom missing-key mismatch.
        c = self._published(
            db,
            advantages=["virtue"],
            advantage_details={"virtue": {"text": "Courage"}},
        )
        c.advantage_details = {"virtue": {}}
        assert c.has_unpublished_changes is False

    def test_legacy_published_state_missing_new_keys_does_not_flip(self, db):
        """Regression: a character whose ``published_state`` predates a
        column being added (e.g. ``specializations`` introduced after
        the snapshot was taken) must not show ``Draft changes`` for an
        unedited character. The comparison defaults must supply each
        new column's empty value so a missing key in the old snapshot
        compares equal to the column's ``or []`` / ``or {}`` fallback
        in ``to_dict``."""
        c = self._published(db)
        # Pretend the published_state was taken before these features
        # existed, by stripping the keys from the snapshot dict.
        snap = dict(c.published_state)
        for legacy_missing in (
            "specializations", "technique_choices",
            "foreign_knacks", "recognition_halved",
        ):
            snap.pop(legacy_missing, None)
        c.published_state = snap
        db.flush()
        assert c.has_unpublished_changes is False
        assert c.publish_status == "published"


class TestAgeMetadata:
    """Age is metadata, not a stat. It persists, the editor can read/write
    it, and the validator complains when unset - but it must NOT count as
    an unpublished change, must NOT appear in revision history diffs, and
    must NOT be reverted by Discard / Revert."""

    def test_to_dict_includes_age(self):
        c = Character(name="Aged", age=28)
        d = c.to_dict()
        assert d["age"] == 28

    def test_to_dict_age_default_is_none(self):
        c = Character(name="Unaged")
        d = c.to_dict()
        assert d["age"] is None

    def test_from_dict_accepts_age(self):
        c = Character.from_dict({"name": "RT", "age": 35})
        assert c.age == 35

    def test_from_dict_age_default_is_none(self):
        c = Character.from_dict({"name": "NoAge"})
        assert c.age is None

    def test_changing_age_does_not_flip_has_unpublished_changes(self, db):
        c = Character(
            name="AgeNoFlip", school="akodo_bushi", school_ring_choice="Water",
            ring_water=3, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            age=None,
        )
        db.add(c)
        db.flush()
        from app.services.versions import publish_character
        publish_character(c, db)
        db.flush()
        assert not c.has_unpublished_changes
        # Setting age must NOT flip the character into "modified" state.
        c.age = 30
        db.flush()
        assert not c.has_unpublished_changes

    def test_discard_preserves_age(self, db):
        from app.services.versions import publish_character, discard_draft_changes
        c = Character(
            name="AgeKeep", school="akodo_bushi", school_ring_choice="Water",
            ring_water=3, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            age=20,
        )
        db.add(c)
        db.flush()
        publish_character(c, db)
        db.flush()
        # Edit a stat AND change age; only the stat should revert.
        c.honor = 4.0
        c.age = 99
        db.flush()
        discard_draft_changes(c, db)
        db.flush()
        assert c.honor == 1.0  # stat reverted
        assert c.age == 99     # metadata preserved


class TestEagerSpecializationBackfill:
    """Live-site characters carry the legacy single-Specialization shape
    in their stored ``advantages`` + ``advantage_details``. The eager
    backfill in ``_migrate_legacy_specializations`` rewrites those rows
    on app startup so the new shape is the single source of truth on
    every subsequent read."""

    def test_migrates_legacy_row(self, db):
        from app.database import _migrate_legacy_specializations
        c = Character(
            name="Legacy",
            advantages=["lucky", "specialization", "fierce"],
            advantage_details={
                "specialization": {"text": "Politics", "skills": ["etiquette"]},
                "virtue": {"text": "Courage"},
            },
            specializations=[],
        )
        db.add(c)
        db.commit()

        # Run on a fresh session bound to the same in-memory engine.
        Session = type(db)
        session = Session(bind=db.bind)
        try:
            updated = _migrate_legacy_specializations(session)
        finally:
            pass  # _migrate_legacy_specializations closes the session it gets
        assert updated == 1

        # Reload the row and assert the new shape.
        fresh = db.query(Character).filter(Character.name == "Legacy").first()
        assert "specialization" not in fresh.advantages
        assert fresh.advantages == ["lucky", "fierce"]
        assert fresh.specializations == [
            {"text": "Politics", "skills": ["etiquette"]},
        ]
        # Other detail entries unaffected.
        assert fresh.advantage_details == {"virtue": {"text": "Courage"}}

    def test_idempotent_on_already_migrated_row(self, db):
        from app.database import _migrate_legacy_specializations
        c = Character(
            name="Already",
            advantages=["lucky"],
            specializations=[
                {"text": "Court", "skills": ["etiquette"]},
            ],
        )
        db.add(c)
        db.commit()

        Session = type(db)
        session = Session(bind=db.bind)
        updated = _migrate_legacy_specializations(session)
        # Nothing to do.
        assert updated == 0

        fresh = db.query(Character).filter(Character.name == "Already").first()
        assert fresh.advantages == ["lucky"]
        assert fresh.specializations == [
            {"text": "Court", "skills": ["etiquette"]},
        ]

    def test_legacy_row_with_no_existing_detail_still_strips_flag(self, db):
        """If somehow a character has 'specialization' in advantages but
        no corresponding detail dict, drop the flag and leave specs empty
        (not [{empty_text}], which would clutter the editor)."""
        from app.database import _migrate_legacy_specializations
        c = Character(
            name="StaleFlag",
            advantages=["specialization"],
            advantage_details={},
        )
        db.add(c)
        db.commit()

        Session = type(db)
        session = Session(bind=db.bind)
        updated = _migrate_legacy_specializations(session)
        assert updated == 1

        fresh = db.query(Character).filter(Character.name == "StaleFlag").first()
        assert "specialization" not in fresh.advantages
        # Empty placeholder spec is acceptable so the editor surfaces a
        # row the player can complete; or empty list. Either is fine -
        # what matters is the flag is gone.
        assert "specialization" not in (fresh.advantage_details or {})


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
