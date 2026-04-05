"""Tests for the draft/publish model and version history."""

import pytest
from app.models import Character, CharacterVersion
from app.services.versions import compute_diff_summary, publish_character, revert_character


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
