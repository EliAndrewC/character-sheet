"""Tests for the draft/publish model and version history."""

import pytest
from app.models import Character, CharacterVersion
from app.services.versions import (
    compute_diff_summary, compute_version_diff, publish_character, revert_character,
)


class TestCharacterVersionModel:
    def test_create_version(self, db):
        char = Character(name="Test", school="akodo_bushi", school_ring_choice="Water",
                         ring_water=3, owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()

        version = CharacterVersion(
            character_id=char.id,
            version_number=1,
            state=char.to_dict(),
            summary="Initial creation",
        )
        db.add(version)
        db.flush()

        assert version.id is not None
        assert version.version_number == 1
        assert version.state["name"] == "Test"
        assert version.summary == "Initial creation"

    def test_character_is_published_flag(self, db):
        char = Character(name="Draft", owner_discord_id="123")
        db.add(char)
        db.flush()
        assert char.is_published is False

    def test_character_published_state(self, db):
        char = Character(name="Test", owner_discord_id="123")
        db.add(char)
        db.flush()
        assert char.published_state is None


class TestDiffSummary:
    def test_ring_change(self):
        old = {"rings": {"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2}}
        new = {"rings": {"Air": 2, "Fire": 3, "Earth": 2, "Water": 3, "Void": 2}}
        diffs = compute_diff_summary(old, new)
        assert any("Fire" in d and "2" in d and "3" in d for d in diffs)

    def test_skill_raised(self):
        old = {"skills": {"bragging": 1}}
        new = {"skills": {"bragging": 2}}
        diffs = compute_diff_summary(old, new)
        assert any("Bragging" in d and "1" in d and "2" in d for d in diffs)

    def test_skill_added(self):
        old = {"skills": {}}
        new = {"skills": {"precepts": 3}}
        diffs = compute_diff_summary(old, new)
        assert any("Precepts" in d for d in diffs)

    def test_honor_change(self):
        old = {"honor": 1.0}
        new = {"honor": 2.5}
        diffs = compute_diff_summary(old, new)
        assert any("Honor" in d for d in diffs)

    def test_advantage_added(self):
        old = {"advantages": []}
        new = {"advantages": ["lucky"]}
        diffs = compute_diff_summary(old, new)
        assert any("Lucky" in d for d in diffs)

    def test_foreign_knack_added(self):
        old = {"foreign_knacks": {}}
        new = {"foreign_knacks": {"athletics": 2}}
        diffs = compute_diff_summary(old, new)
        assert any("Added foreign knack: Athletics" in d for d in diffs)

    def test_foreign_knack_removed(self):
        old = {"foreign_knacks": {"athletics": 2}}
        new = {"foreign_knacks": {}}
        diffs = compute_diff_summary(old, new)
        assert any("Removed foreign knack: Athletics" in d for d in diffs)

    def test_foreign_knack_rank_changed(self):
        old = {"foreign_knacks": {"athletics": 1}}
        new = {"foreign_knacks": {"athletics": 3}}
        diffs = compute_diff_summary(old, new)
        assert any(
            "Foreign knack Athletics" in d and "1" in d and "3" in d
            for d in diffs
        )

    def test_foreign_knack_unchanged_emits_nothing(self):
        old = {"foreign_knacks": {"athletics": 2}}
        new = {"foreign_knacks": {"athletics": 2}}
        diffs = compute_diff_summary(old, new)
        assert not any("foreign knack" in d.lower() for d in diffs)

    def test_foreign_knack_unknown_id_uses_label_fallback(self):
        """If a foreign-knack id has no SCHOOL_KNACKS entry (e.g. from
        an obsolete fixture), the label falls back to the prettified id."""
        old = {"foreign_knacks": {}}
        new = {"foreign_knacks": {"made_up_knack": 1}}
        diffs = compute_diff_summary(old, new)
        assert any("Made Up Knack" in d or "made_up_knack" in d for d in diffs)

    def test_disadvantage_removed(self):
        old = {"disadvantages": ["proud"]}
        new = {"disadvantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Proud" in d for d in diffs)

    def test_knack_raised_with_dan_change(self):
        old = {"knacks": {"feint": 2, "iaijutsu": 2, "double_attack": 2},
               "school": "akodo_bushi"}
        new = {"knacks": {"feint": 3, "iaijutsu": 3, "double_attack": 3},
               "school": "akodo_bushi"}
        diffs = compute_diff_summary(old, new)
        assert any("3rd Dan" in d for d in diffs)

    def test_attack_parry_change(self):
        old = {"attack": 1, "parry": 1}
        new = {"attack": 2, "parry": 1}
        diffs = compute_diff_summary(old, new)
        assert any("Attack" in d for d in diffs)

    def test_player_name_change(self):
        old = {"player_name": "Old"}
        new = {"player_name": "New"}
        diffs = compute_diff_summary(old, new)
        assert any("New" in d for d in diffs)

    def test_school_change(self):
        old = {"school": "akodo_bushi"}
        new = {"school": "bayushi_bushi"}
        diffs = compute_diff_summary(old, new)
        assert any("Bayushi" in d for d in diffs)

    def test_earned_xp_change(self):
        old = {"earned_xp": 0}
        new = {"earned_xp": 30}
        diffs = compute_diff_summary(old, new)
        assert any("Earned XP" in d for d in diffs)

    def test_skill_removed(self):
        old = {"skills": {"bragging": 2}}
        new = {"skills": {}}
        diffs = compute_diff_summary(old, new)
        assert any("Bragging" in d and "removed" in d.lower() for d in diffs)

    def test_no_changes(self):
        state = {"rings": {"Air": 2}, "skills": {}, "honor": 1.0}
        diffs = compute_diff_summary(state, state)
        assert diffs == []

    def test_name_change(self):
        old = {"name": "Old Name"}
        new = {"name": "New Name"}
        diffs = compute_diff_summary(old, new)
        assert any("name" in d.lower() for d in diffs)

    def test_advantage_removed(self):
        old = {"advantages": ["lucky"]}
        new = {"advantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Removed advantage" in d and "Lucky" in d for d in diffs)

    def test_specialization_added_summary(self):
        old = {"specializations": []}
        new = {"specializations": [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
        ]}
        diffs = compute_diff_summary(old, new)
        assert any(
            "Added specialization" in d and "Court Etiquette" in d
            and "Etiquette" in d
            for d in diffs
        )

    def test_specialization_removed_summary(self):
        old = {"specializations": [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
        ]}
        new = {"specializations": []}
        diffs = compute_diff_summary(old, new)
        assert any(
            "Removed specialization" in d and "Court Etiquette" in d
            for d in diffs
        )

    def test_specializations_unchanged_emit_no_lines(self):
        old = {"specializations": [
            {"text": "Court Etiquette", "skills": ["etiquette"]},
        ]}
        new = old
        diffs = compute_diff_summary(old, new)
        assert all("specialization" not in d.lower() for d in diffs)

    def test_specialization_with_no_skill_renders_text_only(self):
        """A spec with an empty / unresolved skill list still renders -
        falls back to the bare text without the parenthesised skill name."""
        old = {"specializations": []}
        new = {"specializations": [
            {"text": "Whittling", "skills": []},
        ]}
        diffs = compute_diff_summary(old, new)
        assert any(
            "Added specialization" in d and "Whittling" in d
            and "(" not in d  # no skill paren
            for d in diffs
        )

    def test_advantage_removed_unknown_id_falls_back_to_label(self):
        old = {"advantages": ["totally_made_up_adv"]}
        new = {"advantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Totally Made Up Adv" in d for d in diffs)

    def test_disadvantage_added(self):
        old = {"disadvantages": []}
        new = {"disadvantages": ["proud"]}
        diffs = compute_diff_summary(old, new)
        assert any("Added disadvantage" in d and "Proud" in d for d in diffs)

    def test_disadvantage_added_unknown_id_falls_back_to_label(self):
        old = {"disadvantages": []}
        new = {"disadvantages": ["made_up_dis"]}
        diffs = compute_diff_summary(old, new)
        assert any("Made Up Dis" in d for d in diffs)

    def test_campaign_advantage_added(self):
        old = {"campaign_advantages": []}
        new = {"campaign_advantages": ["highest_regard"]}
        diffs = compute_diff_summary(old, new)
        assert any("Added campaign advantage" in d and "Highest Regard" in d for d in diffs)

    def test_campaign_advantage_added_unknown_id_falls_back_to_label(self):
        old = {"campaign_advantages": []}
        new = {"campaign_advantages": ["mystery_boon"]}
        diffs = compute_diff_summary(old, new)
        assert any("Mystery Boon" in d for d in diffs)

    def test_campaign_advantage_removed(self):
        old = {"campaign_advantages": ["highest_regard"]}
        new = {"campaign_advantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Removed campaign advantage" in d and "Highest Regard" in d for d in diffs)

    def test_campaign_advantage_removed_unknown_id_falls_back_to_label(self):
        old = {"campaign_advantages": ["mystery_boon"]}
        new = {"campaign_advantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Removed campaign advantage" in d and "Mystery Boon" in d for d in diffs)

    def test_campaign_disadvantage_added(self):
        old = {"campaign_disadvantages": []}
        new = {"campaign_disadvantages": ["peasantborn"]}
        diffs = compute_diff_summary(old, new)
        assert any("Added campaign disadvantage" in d and "Peasantborn" in d for d in diffs)

    def test_campaign_disadvantage_added_unknown_id_falls_back_to_label(self):
        old = {"campaign_disadvantages": []}
        new = {"campaign_disadvantages": ["mystery_curse"]}
        diffs = compute_diff_summary(old, new)
        assert any("Mystery Curse" in d for d in diffs)

    def test_campaign_disadvantage_removed(self):
        old = {"campaign_disadvantages": ["peasantborn"]}
        new = {"campaign_disadvantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Removed campaign disadvantage" in d and "Peasantborn" in d for d in diffs)

    def test_campaign_disadvantage_removed_unknown_id_falls_back_to_label(self):
        old = {"campaign_disadvantages": ["mystery_curse"]}
        new = {"campaign_disadvantages": []}
        diffs = compute_diff_summary(old, new)
        assert any("Removed campaign disadvantage" in d and "Mystery Curse" in d for d in diffs)


class TestPublishCharacter:
    def test_first_publish(self, db):
        char = Character(name="Publish Test", school="akodo_bushi",
                         school_ring_choice="Water", ring_water=3,
                         owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()

        version = publish_character(char, db)

        assert char.is_published is True
        assert char.published_state is not None
        assert char.published_state["name"] == "Publish Test"
        assert version.version_number == 1
        assert version.summary  # should have some summary text

    def test_second_publish_increments_version(self, db):
        char = Character(name="V1", school="akodo_bushi",
                         school_ring_choice="Water", ring_water=3,
                         owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()

        v1 = publish_character(char, db)
        assert v1.version_number == 1

        char.name = "V2"
        char.ring_fire = 3
        db.flush()

        v2 = publish_character(char, db)
        assert v2.version_number == 2
        assert any("Fire" in d for d in v2.summary.split("; "))

    def test_published_state_matches_snapshot(self, db):
        char = Character(name="Snapshot", school="akodo_bushi",
                         school_ring_choice="Water", ring_water=3,
                         honor=2.0, owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()

        publish_character(char, db)

        # Modify draft
        char.honor = 3.0
        db.flush()

        # Published state should still show honor 2.0
        assert char.published_state["honor"] == 2.0


class TestRevertCharacter:
    def test_revert_creates_new_version(self, db):
        char = Character(name="V1 Name", school="akodo_bushi",
                         school_ring_choice="Water", ring_water=3,
                         owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()
        v1 = publish_character(char, db)

        char.name = "V2 Name"
        db.flush()
        v2 = publish_character(char, db)

        # Revert to v1
        v3 = revert_character(char, v1.id, db)

        assert v3.version_number == 3
        assert "revert" in v3.summary.lower()
        assert char.name == "V1 Name"
        assert char.published_state["name"] == "V1 Name"

    def test_revert_with_unknown_version_id_raises(self, db):
        char = Character(name="Target", school="akodo_bushi",
                         school_ring_choice="Water", ring_water=3,
                         owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()
        publish_character(char, db)

        with pytest.raises(ValueError, match="Version 99999 not found"):
            revert_character(char, 99999, db)

    def test_revert_restores_all_fields(self, db):
        char = Character(name="Original", school="akodo_bushi",
                         school_ring_choice="Water", ring_water=3,
                         ring_fire=2, honor=1.0, owner_discord_id="123",
                         knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1})
        db.add(char)
        db.flush()
        v1 = publish_character(char, db)

        char.ring_fire = 4
        char.honor = 3.0
        db.flush()
        publish_character(char, db)

        revert_character(char, v1.id, db)

        assert char.ring_fire == 2
        assert char.honor == 1.0


class TestDiscardDraftChanges:
    """``discard_draft_changes`` resets a character's draft to its
    ``published_state`` so any unapplied edits are undone. It does NOT
    create a new version (unlike publish/revert) - it's purely an undo."""

    def test_discard_restores_basic_fields_to_published_state(self, db):
        from app.services.versions import discard_draft_changes
        char = Character(
            name="Original", school="akodo_bushi", school_ring_choice="Water",
            ring_water=3, honor=1.0, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        db.add(char)
        db.flush()
        publish_character(char, db)

        # Edit the draft.
        char.name = "Drafted"
        char.honor = 4.5
        db.flush()
        assert char.has_unpublished_changes

        discard_draft_changes(char, db)
        db.flush()

        assert char.name == "Original"
        assert char.honor == 1.0
        assert not char.has_unpublished_changes

    def test_discard_restores_specializations(self, db):
        """Spec list is one of the newer fields - confirm restore covers it."""
        from app.services.versions import discard_draft_changes
        char = Character(
            name="Spec Discard", school="akodo_bushi", school_ring_choice="Water",
            ring_water=3, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            specializations=[{"text": "Court", "skills": ["etiquette"]}],
        )
        db.add(char)
        db.flush()
        publish_character(char, db)

        # Add another spec to the draft.
        char.specializations = char.specializations + [
            {"text": "Drafted", "skills": ["bragging"]},
        ]
        db.flush()

        discard_draft_changes(char, db)
        db.flush()

        assert char.specializations == [
            {"text": "Court", "skills": ["etiquette"]},
        ]

    def test_discard_does_not_create_a_new_version(self, db):
        from app.services.versions import discard_draft_changes
        from app.models import CharacterVersion
        char = Character(
            name="No New Version", school="akodo_bushi", school_ring_choice="Water",
            ring_water=3, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        db.add(char)
        db.flush()
        publish_character(char, db)
        version_count_before = (
            db.query(CharacterVersion)
            .filter(CharacterVersion.character_id == char.id).count()
        )

        char.name = "Drafted"
        db.flush()
        discard_draft_changes(char, db)
        db.flush()

        version_count_after = (
            db.query(CharacterVersion)
            .filter(CharacterVersion.character_id == char.id).count()
        )
        assert version_count_after == version_count_before

    def test_discard_does_not_touch_tracking_fields(self, db):
        """Adventure / wound / VP state is per-session, not per-version.
        Discard must NOT zero them out alongside the draft fields."""
        from app.services.versions import discard_draft_changes
        char = Character(
            name="Track", school="akodo_bushi", school_ring_choice="Water",
            ring_water=3, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        db.add(char)
        db.flush()
        publish_character(char, db)

        char.current_light_wounds = 7
        char.current_void_points = 1
        char.adventure_state = {"lucky_used": True}
        char.name = "Drafted"
        db.flush()

        discard_draft_changes(char, db)
        db.flush()

        # Tracking state preserved.
        assert char.current_light_wounds == 7
        assert char.current_void_points == 1
        assert char.adventure_state == {"lucky_used": True}
        # Draft change reverted.
        assert char.name != "Drafted"

    def test_discard_with_no_published_state_is_a_noop(self, db):
        """Defensive: a never-published draft has nothing to revert to.
        The function should not raise; it should leave the row untouched."""
        from app.services.versions import discard_draft_changes
        char = Character(
            name="Never Published", school="akodo_bushi", school_ring_choice="Water",
            owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
        )
        db.add(char)
        db.flush()
        # No publish - no published_state.
        discard_draft_changes(char, db)
        db.flush()
        assert char.name == "Never Published"


class TestPreceptsPoolDanDrop:
    """Priest 3rd Dan's precepts pool is a live column on Character; it must
    not outlive a rank change that drops the priest below 3rd Dan. Both
    publish_character and revert_character call _wipe_precepts_pool_if_dan_drop
    so the pool clears whenever a committed state puts the priest at dan < 3."""

    def _seed_priest_with_pool(self, db, *, knack_rank=3, pool=None):
        pool = pool if pool is not None else [{"value": 7}, {"value": 4}]
        char = Character(
            name="Priest Pool",
            school="priest",
            school_ring_choice="Water",
            ring_water=3,
            owner_discord_id="123",
            knacks={"conviction": knack_rank, "otherworldliness": knack_rank,
                    "pontificate": knack_rank},
            skills={"precepts": 2},
            precepts_pool=pool,
        )
        db.add(char)
        db.flush()
        return char

    def test_publish_keeps_pool_when_dan_stays_at_3_or_higher(self, db):
        char = self._seed_priest_with_pool(db, knack_rank=3)
        publish_character(char, db)
        assert char.precepts_pool == [{"value": 7}, {"value": 4}]

    def test_publish_wipes_pool_when_dan_drops_below_3(self, db):
        char = self._seed_priest_with_pool(db, knack_rank=3)
        publish_character(char, db)
        # Drop one knack to rank 2, which pulls Dan down to 2.
        char.knacks = {"conviction": 2, "otherworldliness": 3, "pontificate": 3}
        publish_character(char, db)
        assert char.precepts_pool == []

    def test_publish_wipes_pool_for_non_priest_that_stores_one(self, db):
        """Defensive: the helper is a no-op for non-priests, so a non-priest
        character that somehow ended up with a pool keeps it (the only way
        to store one was to be a priest before; this case shouldn't happen
        in practice)."""
        char = Character(
            name="Not A Priest", school="akodo_bushi",
            school_ring_choice="Water", ring_water=3, owner_discord_id="123",
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            precepts_pool=[{"value": 5}],
        )
        db.add(char); db.flush()
        publish_character(char, db)
        # Non-priest: the helper leaves the value alone.
        assert char.precepts_pool == [{"value": 5}]

    def test_revert_wipes_pool_when_reverted_state_is_below_3rd_dan(self, db):
        """Reverting to an earlier version where the priest was at dan < 3
        clears any currently-held pool."""
        char = self._seed_priest_with_pool(db, knack_rank=2, pool=[])
        v1 = publish_character(char, db)  # at dan 2 with empty pool
        char.knacks = {"conviction": 3, "otherworldliness": 3, "pontificate": 3}
        char.precepts_pool = [{"value": 9}, {"value": 6}]
        publish_character(char, db)  # now at dan 3 with pool
        assert char.precepts_pool == [{"value": 9}, {"value": 6}]
        # Revert back to v1 (dan 2). Pool must clear.
        revert_character(char, v1.id, db)
        assert char.precepts_pool == []


class TestComputeVersionDiff:
    """The structured diff used by the version-history drill-down UI.

    These tests pin the per-category emit rules; the partial template
    uses ``{% for cat, items in entries|groupby('category') %}`` so the
    list shape (flat list of category-tagged dicts) is part of the
    contract.
    """

    @staticmethod
    def _by_category(entries, category):
        return [e for e in entries if e["category"] == category]

    def test_empty_when_states_equal(self):
        state = {"name": "Akodo", "rings": {"Air": 3}, "skills": {"bragging": 2}}
        assert compute_version_diff(state, state) == []

    def test_empty_when_prev_state_is_empty(self):
        # First version of a character: caller short-circuits, but the
        # function shouldn't crash.
        assert compute_version_diff({}, {"name": "x"}) == []
        assert compute_version_diff(None, {"name": "x"}) == []

    def test_basics_name_change(self):
        entries = compute_version_diff({"name": "Old"}, {"name": "New"})
        basics = self._by_category(entries, "Basics")
        assert any(e["label"] == "Name" and e["before"] == "Old" and e["after"] == "New"
                   for e in basics)

    def test_basics_player_name_change_renders_empty_when_unset(self):
        entries = compute_version_diff({"player_name": ""}, {"player_name": "Alice"})
        basics = self._by_category(entries, "Basics")
        match = next(e for e in basics if e["label"] == "Player name")
        assert match["before"] == "(empty)" and match["after"] == "Alice"

    def test_name_explanation_surfaces_as_section_updated(self):
        entries = compute_version_diff(
            {"name_explanation": "old reason"},
            {"name_explanation": "new reason"},
        )
        match = next(e for e in entries if e["label"] == "Name explanation")
        assert match["kind"] == "section_updated"
        assert match["after"] == "updated"
        # Crucially, the actual prose isn't dumped into the diff.
        assert "old reason" not in str(match) and "new reason" not in str(match)

    def test_school_change_renders_display_names(self):
        entries = compute_version_diff(
            {"school": ""}, {"school": "akodo_bushi"},
        )
        match = next(e for e in entries if e["label"] == "School")
        assert match["before"] == "none"
        assert match["after"] == "Akodo Bushi"

    def test_school_ring_choice_suppressed_when_school_changes(self):
        # School change implies a different ring choice; the school line
        # already covers that, so a separate ring-choice line would be
        # duplicate noise.
        entries = compute_version_diff(
            {"school": "akodo_bushi", "school_ring_choice": "Earth"},
            {"school": "kakita_duelist", "school_ring_choice": "Air"},
        )
        labels = {e["label"] for e in entries}
        assert "School" in labels
        assert "School ring" not in labels

    def test_school_ring_choice_emitted_when_school_unchanged(self):
        entries = compute_version_diff(
            {"school": "shiba_bushi", "school_ring_choice": "Air"},
            {"school": "shiba_bushi", "school_ring_choice": "Fire"},
        )
        match = next(e for e in entries if e["label"] == "School ring")
        assert match["before"] == "Air" and match["after"] == "Fire"

    def test_rings_up_and_down(self):
        entries = compute_version_diff(
            {"rings": {"Air": 2, "Fire": 4}},
            {"rings": {"Air": 4, "Fire": 3}},
        )
        rings = self._by_category(entries, "Rings")
        air = next(e for e in rings if e["label"] == "Air")
        fire = next(e for e in rings if e["label"] == "Fire")
        assert air["before"] == 2 and air["after"] == 4
        assert fire["before"] == 4 and fire["after"] == 3

    def test_attack_parry_change(self):
        entries = compute_version_diff(
            {"attack": 2, "parry": 1}, {"attack": 3, "parry": 1},
        )
        combat = self._by_category(entries, "Combat")
        assert any(e["label"] == "Attack" and e["before"] == 2 and e["after"] == 3
                   for e in combat)

    def test_first_dan_choices_are_set_semantics(self):
        # Reordering the same skills emits no diff line.
        entries = compute_version_diff(
            {"technique_choices": {"first_dan_choices": ["bragging", "etiquette"]}},
            {"technique_choices": {"first_dan_choices": ["etiquette", "bragging"]}},
        )
        assert not any(e["label"] == "1st Dan choices" for e in entries)

    def test_first_dan_choices_emit_on_set_change(self):
        entries = compute_version_diff(
            {"technique_choices": {"first_dan_choices": ["bragging"]}},
            {"technique_choices": {"first_dan_choices": ["bragging", "etiquette"]}},
        )
        match = next(e for e in entries if e["label"] == "1st Dan choices")
        assert match["before"] == "Bragging" and match["after"] == "Bragging, Etiquette"

    def test_second_dan_choice_change(self):
        entries = compute_version_diff(
            {"technique_choices": {"second_dan_choice": "bragging"}},
            {"technique_choices": {"second_dan_choice": "etiquette"}},
        )
        match = next(e for e in entries if e["label"] == "2nd Dan choice")
        assert match["before"] == "Bragging" and match["after"] == "Etiquette"

    def test_skills_add_remove_change(self):
        entries = compute_version_diff(
            {"skills": {"bragging": 2, "etiquette": 1}},
            {"skills": {"bragging": 3, "tact": 1}},
        )
        skills = self._by_category(entries, "Skills")
        names = {e["label"]: e for e in skills}
        assert names["Bragging"]["kind"] == "change"
        assert names["Bragging"]["before"] == 2 and names["Bragging"]["after"] == 3
        assert names["Etiquette"]["kind"] == "remove"
        assert names["Tact"]["kind"] == "add" and names["Tact"]["after"] == 1

    def test_knack_unchanged_skipped(self):
        # When two knacks are present and one is unchanged, the loop
        # ``continue`` for the unchanged one and only emits the changed.
        prev = {"knacks": {"double_attack": 1, "feint": 1}}
        new = {"knacks": {"double_attack": 1, "feint": 2}}
        knacks = self._by_category(compute_version_diff(prev, new), "Knacks")
        labels = [e["label"] for e in knacks if e["label"] != "Dan"]
        assert labels == ["Feint"]

    def test_knack_removed(self):
        prev = {"knacks": {"double_attack": 2, "feint": 1, "iaijutsu": 1}}
        new = {"knacks": {"double_attack": 0, "feint": 1, "iaijutsu": 1}}
        match = next(e for e in compute_version_diff(prev, new)
                     if e["category"] == "Knacks" and e["label"] != "Dan")
        assert match["kind"] == "remove"

    def test_unknown_knack_id_falls_back_to_label_case(self):
        entries = compute_version_diff(
            {"knacks": {}}, {"knacks": {"made_up_knack": 1}},
        )
        match = next(e for e in entries if e["category"] == "Knacks")
        assert match["label"] == "Made Up Knack"

    def test_unknown_advantage_details_id_falls_back_to_label(self):
        # An advantage id that exists in neither ADVANTAGES nor any of
        # the campaign tables should still produce a sensible label
        # rather than crashing.
        entries = compute_version_diff(
            {"advantages": ["mystery_id"], "advantage_details": {"mystery_id": {"text": "a"}}},
            {"advantages": ["mystery_id"], "advantage_details": {"mystery_id": {"text": "b"}}},
        )
        match = next(e for e in entries if "details" in e["label"])
        assert match["label"].startswith("Mystery Id")

    def test_award_with_recognition_only_renders_only_that_part(self):
        prev = {"rank_recognition_awards": []}
        new = {"rank_recognition_awards": [{
            "id": "y", "rank_delta": 0, "recognition_delta": 1.0,
            "source": "Famous deed",
        }]}
        match = next(e for e in compute_version_diff(prev, new)
                     if e["category"] == "Awards")
        # Only recognition was changed, so the rank delta line must not appear.
        assert "rank" not in (match["after"] or "")
        assert "+1.0 recognition" in (match["after"] or "")

    def test_award_without_source_renders_id_fallback_label(self):
        prev = {"rank_recognition_awards": []}
        new = {"rank_recognition_awards": [{
            "id": "abcdef1234", "rank_delta": 0.5, "recognition_delta": 0,
            "source": "",
        }]}
        match = next(e for e in compute_version_diff(prev, new)
                     if e["category"] == "Awards")
        assert match["label"] == "Award abcdef12"

    def test_award_with_no_deltas_falls_back_to_type_string(self):
        # A reputation-style award (no numeric rank/rec deltas) still
        # needs SOMETHING in the after-text. Tests the type fallback.
        prev = {"rank_recognition_awards": []}
        new = {"rank_recognition_awards": [{
            "id": "rep1", "type": "reputation",
            "rank_delta": 0, "recognition_delta": 0,
            "source": "Bandit lord vendetta",
        }]}
        match = next(e for e in compute_version_diff(prev, new)
                     if e["category"] == "Awards")
        assert match["after"] == "reputation"

    def test_knacks_promotion_dan(self):
        # Bumping the lowest school knack from 1 to 2 promotes Akodo to 2nd Dan.
        old = {"knacks": {"double_attack": 1, "feint": 1, "iaijutsu": 1}}
        new = {"knacks": {"double_attack": 2, "feint": 2, "iaijutsu": 2}}
        entries = compute_version_diff(old, new)
        knacks = self._by_category(entries, "Knacks")
        dan_line = next(e for e in knacks if e["label"] == "Dan")
        assert dan_line["before"] == "1st" and dan_line["after"] == "2nd"

    def test_advantages_added_and_removed(self):
        entries = compute_version_diff(
            {"advantages": ["fierce"]},
            {"advantages": ["charming"]},
        )
        advs = self._by_category(entries, "Advantages")
        kinds = {e["kind"] for e in advs}
        assert kinds == {"add", "remove"}
        labels = {e["label"] for e in advs}
        assert any("Charming" in l for l in labels)
        assert any("Fierce" in l for l in labels)

    def test_advantages_reordered_returns_empty(self):
        entries = compute_version_diff(
            {"advantages": ["fierce", "charming"]},
            {"advantages": ["charming", "fierce"]},
        )
        assert entries == []

    def test_specialization_added_emits_advantages_entry(self):
        entries = compute_version_diff(
            {"specializations": []},
            {"specializations": [
                {"text": "Court Etiquette", "skills": ["etiquette"]},
            ]},
        )
        advs = self._by_category(entries, "Advantages")
        match = next(e for e in advs if "Added specialization" in e["label"])
        assert match["kind"] == "add"
        assert "Court Etiquette" in match["label"]
        assert "Etiquette" in match["label"]

    def test_specialization_removed_emits_advantages_entry(self):
        entries = compute_version_diff(
            {"specializations": [
                {"text": "Old", "skills": ["bragging"]},
            ]},
            {"specializations": []},
        )
        advs = self._by_category(entries, "Advantages")
        assert any(
            e["kind"] == "remove" and "Old" in e["label"] for e in advs
        )

    def test_specialization_text_change_renders_as_remove_plus_add(self):
        entries = compute_version_diff(
            {"specializations": [
                {"text": "Court Politics", "skills": ["etiquette"]},
            ]},
            {"specializations": [
                {"text": "Court Etiquette", "skills": ["etiquette"]},
            ]},
        )
        advs = self._by_category(entries, "Advantages")
        kinds = {e["kind"] for e in advs}
        assert kinds == {"add", "remove"}
        labels = " ".join(e["label"] for e in advs)
        assert "Court Politics" in labels
        assert "Court Etiquette" in labels

    def test_specialization_unchanged_returns_no_advantages_entry(self):
        same = [{"text": "Court Etiquette", "skills": ["etiquette"]}]
        entries = compute_version_diff(
            {"specializations": same}, {"specializations": list(same)},
        )
        advs = self._by_category(entries, "Advantages")
        assert advs == []

    def test_specialization_with_no_skill_renders_text_only_in_structured_diff(self):
        entries = compute_version_diff(
            {"specializations": []},
            {"specializations": [{"text": "Whittling", "skills": []}]},
        )
        advs = self._by_category(entries, "Advantages")
        match = next(e for e in advs if "Whittling" in e["label"])
        # No skill paren in the label since no skill is resolved.
        assert "(" not in match["label"]

    def test_campaign_advantage_added(self):
        entries = compute_version_diff(
            {"campaign_advantages": []},
            {"campaign_advantages": ["wasp_friend"]},
        )
        match = next(e for e in entries if "campaign advantage" in e["label"].lower())
        assert match["category"] == "Advantages"
        assert match["kind"] == "add"

    def test_advantage_details_updated_on_persistent_advantage(self):
        entries = compute_version_diff(
            {"advantages": ["higher_purpose"],
             "advantage_details": {"higher_purpose": {"text": "old"}}},
            {"advantages": ["higher_purpose"],
             "advantage_details": {"higher_purpose": {"text": "new"}}},
        )
        match = next(e for e in entries if e["label"].startswith("Higher Purpose"))
        assert match["kind"] == "section_updated"

    def test_advantage_details_not_emitted_for_newly_added_advantage(self):
        # The "add" line covers the introduction; a second "details
        # updated" line would be redundant. The function rule is to only
        # emit details when the advantage exists on BOTH sides.
        entries = compute_version_diff(
            {"advantages": [], "advantage_details": {}},
            {"advantages": ["higher_purpose"],
             "advantage_details": {"higher_purpose": {"text": "x"}}},
        )
        labels = [e["label"] for e in entries]
        assert any(l.startswith("Added advantage") for l in labels)
        assert not any("details" in l for l in labels)

    def test_disadvantage_removed(self):
        entries = compute_version_diff(
            {"disadvantages": ["bad_reputation"]},
            {"disadvantages": []},
        )
        match = next(e for e in entries if "disadvantage" in e["label"].lower())
        assert match["category"] == "Disadvantages"
        assert match["kind"] == "remove"

    def test_status_int_honor_renders_as_string(self):
        # Older or imported snapshots may store honor as int (2) rather
        # than float (2.0). The formatter falls back to str() and
        # produces a sensible "2" rather than crashing.
        entries = compute_version_diff(
            {"honor": 2}, {"honor": 3},
        )
        match = next(e for e in entries if e["label"] == "Honor")
        assert match["before"] == "2" and match["after"] == "3"

    def test_status_floats_format_with_one_decimal(self):
        entries = compute_version_diff(
            {"honor": 2.0}, {"honor": 3.5},
        )
        match = next(e for e in entries if e["label"] == "Honor")
        assert match["before"] == "2.0" and match["after"] == "3.5"

    def test_rank_locked_toggle(self):
        entries = compute_version_diff(
            {"rank_locked": True}, {"rank_locked": False},
        )
        match = next(e for e in entries if e["label"] == "Rank locked")
        assert match["before"] == "yes" and match["after"] == "no"

    def test_xp_change(self):
        entries = compute_version_diff(
            {"starting_xp": 150, "earned_xp": 50},
            {"starting_xp": 150, "earned_xp": 75},
        )
        xp = self._by_category(entries, "XP")
        labels = {e["label"]: e for e in xp}
        assert "Earned XP" in labels and labels["Earned XP"]["before"] == 50

    def test_award_added_includes_source_text(self):
        entries = compute_version_diff(
            {"rank_recognition_awards": []},
            {"rank_recognition_awards": [{
                "id": "abc-123-def",
                "rank_delta": 0.5,
                "recognition_delta": 0,
                "source": "Defeated bandit lord",
            }]},
        )
        match = next(e for e in entries if e["category"] == "Awards")
        # Source text is the human label.
        assert match["label"] == "Defeated bandit lord"
        assert match["kind"] == "add"
        assert "+0.5 rank" in (match["after"] or "")

    def test_award_source_only_edit_emits_nothing(self):
        # Editing the freeform source text does NOT trigger a version
        # diff entry - mirrors award_deltas_for_diff behavior.
        prev = {"rank_recognition_awards": [{
            "id": "x", "rank_delta": 0.5, "recognition_delta": 0,
            "source": "old reason",
        }]}
        new = {"rank_recognition_awards": [{
            "id": "x", "rank_delta": 0.5, "recognition_delta": 0,
            "source": "new reason",
        }]}
        assert compute_version_diff(prev, new) == []

    def test_award_delta_change_emits_change_entry(self):
        prev = {"rank_recognition_awards": [{
            "id": "x", "rank_delta": 0.5, "recognition_delta": 0, "source": "s",
        }]}
        new = {"rank_recognition_awards": [{
            "id": "x", "rank_delta": 1.0, "recognition_delta": 0, "source": "s",
        }]}
        match = next(e for e in compute_version_diff(prev, new)
                     if e["category"] == "Awards")
        assert match["kind"] == "change"

    def test_award_removed(self):
        prev = {"rank_recognition_awards": [{
            "id": "x", "rank_delta": 0.5, "recognition_delta": 0, "source": "Old award",
        }]}
        new = {"rank_recognition_awards": []}
        match = next(e for e in compute_version_diff(prev, new)
                     if e["category"] == "Awards")
        assert match["kind"] == "remove"
        assert match["label"] == "Old award"

    def test_notes_change_renders_as_content_updated(self):
        entries = compute_version_diff(
            {"notes": "old"}, {"notes": "new"},
        )
        match = next(e for e in entries if e["label"] == "Notes")
        assert match["category"] == "Sections"
        assert match["kind"] == "section_updated"
        # No raw text in the diff.
        assert "old" not in str(match) and "new" not in str(match)

    def test_section_added(self):
        entries = compute_version_diff(
            {"sections": []},
            {"sections": [{"label": "Backstory", "html": "<p>x</p>"}]},
        )
        match = next(e for e in entries if e["label"] == "Backstory")
        assert match["category"] == "Sections" and match["kind"] == "add"

    def test_section_removed(self):
        entries = compute_version_diff(
            {"sections": [{"label": "Allies", "html": "<p>x</p>"}]},
            {"sections": []},
        )
        match = next(e for e in entries if e["label"] == "Allies")
        assert match["kind"] == "remove"

    def test_section_html_only_change(self):
        entries = compute_version_diff(
            {"sections": [{"label": "Backstory", "html": "<p>old</p>"}]},
            {"sections": [{"label": "Backstory", "html": "<p>new</p>"}]},
        )
        match = next(e for e in entries if e["label"] == "Backstory")
        assert match["kind"] == "section_updated"
        # Body text isn't dumped.
        assert "old" not in str(match) and "new" not in str(match)

    def test_session_state_filtered_out(self):
        # Mutable per-session fields must never appear in a version diff.
        prev = {"current_light_wounds": 0, "current_void_points": 3,
                "action_dice": [], "precepts_pool": [],
                "adventure_state": {}}
        new = {"current_light_wounds": 5, "current_void_points": 0,
               "action_dice": [{"value": 7, "spent": False}],
               "precepts_pool": [{"value": 9}],
               "adventure_state": {"lucky_used": True}}
        assert compute_version_diff(prev, new) == []

    def test_metadata_fields_filtered_out(self):
        prev = {"id": 1, "created_at": "old", "updated_at": "old",
                "owner_discord_id": "a", "google_sheet_id": "x"}
        new = {"id": 1, "created_at": "old", "updated_at": "new",
               "owner_discord_id": "b", "google_sheet_id": "y"}
        assert compute_version_diff(prev, new) == []

    def test_missing_prev_field_treats_new_entries_as_added(self):
        # An older snapshot lacks the ``sections`` key entirely. Every
        # entry in the new sections list should appear as an "add".
        entries = compute_version_diff(
            {"name": "x"},
            {"name": "x", "sections": [
                {"label": "Backstory", "html": "<p>...</p>"},
                {"label": "Allies", "html": "<p>...</p>"},
            ]},
        )
        secs = [e for e in entries if e["category"] == "Sections"]
        assert {e["label"] for e in secs} == {"Backstory", "Allies"}
        assert all(e["kind"] == "add" for e in secs)

    def test_unknown_skill_id_falls_back_to_label_case(self):
        # An imported character may carry skill ids the codebase doesn't
        # know about (typo, removed skill). The function shouldn't crash;
        # it falls back to a Title-Case label.
        entries = compute_version_diff(
            {"skills": {"made_up_skill": 1}},
            {"skills": {"made_up_skill": 2}},
        )
        match = next(e for e in entries if e["category"] == "Skills")
        assert match["label"] == "Made Up Skill"

    def test_categories_are_in_stable_order(self):
        # The template renders categories via Jinja groupby, which is
        # insertion-order. Ensure entries land in the canonical order
        # regardless of the order the input fields happen to be in.
        from app.services.versions import DIFF_CATEGORIES
        prev = {
            "earned_xp": 0,
            "rings": {"Air": 2}, "skills": {}, "advantages": [],
            "honor": 1.0, "name": "x", "attack": 1,
            "knacks": {}, "disadvantages": [], "sections": [],
        }
        new = {
            "earned_xp": 5,                        # XP
            "rings": {"Air": 3},                   # Rings
            "skills": {"bragging": 1},             # Skills
            "advantages": ["fierce"],              # Advantages
            "honor": 2.0,                          # Status
            "name": "y",                           # Basics
            "attack": 2,                           # Combat
            "knacks": {"double_attack": 1},        # Knacks
            "disadvantages": ["bad_reputation"],   # Disadvantages
            "sections": [{"label": "Notes",
                          "html": "<p>x</p>"}],    # Sections
        }
        entries = compute_version_diff(prev, new)
        seen = []
        for e in entries:
            if not seen or seen[-1] != e["category"]:
                seen.append(e["category"])
        # `seen` must be a subsequence of DIFF_CATEGORIES.
        idx = -1
        for cat in seen:
            new_idx = DIFF_CATEGORIES.index(cat)
            assert new_idx > idx, f"{cat} out of order in {seen}"
            idx = new_idx
