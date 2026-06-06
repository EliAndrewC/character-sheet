"""Tests for ``scripts/migrate_hiruma_feint_to_counterattack.py``.

Covers the pure rewrite helpers and the end-to-end DB migration of a
single Hiruma Scout character + its full revision history, including the
school guard, idempotency, and the deliberate non-touching of
foreign_knacks and roll_history.
"""

import importlib.util
from pathlib import Path

import pytest

from app.models import Character, CharacterVersion, RollHistory

# Load the script as a module (scripts/ is not a package).
_spec = importlib.util.spec_from_file_location(
    "migrate_hiruma",
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "migrate_hiruma_feint_to_counterattack.py",
)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestRenameInKnacks:
    def test_swaps_key_preserving_rank_and_order(self):
        out, note = mig.rename_in_knacks(
            {"double_attack": 2, "feint": 3, "iaijutsu": 1}
        )
        assert out == {"double_attack": 2, "counterattack": 3, "iaijutsu": 1}
        # Order preserved: counterattack sits where feint was.
        assert list(out.keys()) == ["double_attack", "counterattack", "iaijutsu"]
        assert "rank 3" in note

    def test_none_and_missing_are_noops(self):
        assert mig.rename_in_knacks(None) == (None, "")
        assert mig.rename_in_knacks({}) == (None, "")
        assert mig.rename_in_knacks({"iaijutsu": 1}) == (None, "")

    def test_both_present_is_skipped(self):
        out, note = mig.rename_in_knacks({"feint": 2, "counterattack": 1})
        assert out is None
        assert note.startswith("SKIPPED")


class TestRenameInState:
    def test_rewrites_nested_knacks_without_mutating_input(self):
        state = {"knacks": {"feint": 2}, "skills": {"kenjutsu": 3}}
        out, note = mig.rename_in_state(state)
        assert out["knacks"] == {"counterattack": 2}
        assert out["skills"] == {"kenjutsu": 3}
        # Input untouched (fresh copy returned).
        assert state["knacks"] == {"feint": 2}

    def test_none_and_no_feint_are_noops(self):
        assert mig.rename_in_state(None) == (None, "")
        assert mig.rename_in_state({"knacks": {"iaijutsu": 1}}) == (None, "")


class TestRenameInSummary:
    def test_replaces_display_name_whole_word(self):
        out, _ = mig.rename_in_summary("Feint changed from 1 to 2")
        assert out == "Counterattack changed from 1 to 2"

    def test_lowercase_whole_word_replaced(self):
        out, _ = mig.rename_in_summary("added feint to the build")
        assert out == "added counterattack to the build"

    def test_does_not_touch_substrings(self):
        # "Feinted" is a different word - must not be partially rewritten.
        assert mig.rename_in_summary("Feinted away") == (None, "")

    def test_noop_when_absent(self):
        assert mig.rename_in_summary("Initial character creation") == (None, "")
        assert mig.rename_in_summary("") == (None, "")
        assert mig.rename_in_summary(None) == (None, "")


# ---------------------------------------------------------------------------
# End-to-end DB migration
# ---------------------------------------------------------------------------


def _seed_hiruma(db, char_id=10):
    """A Hiruma Scout with feint across knacks, published_state, and a
    three-version history whose summaries name 'Feint'."""
    pub = {
        "knacks": {"double_attack": 2, "feint": 3, "iaijutsu": 1},
        "skills": {"kenjutsu": 2},
        "school": "hiruma_scout",
    }
    char = Character(
        id=char_id,
        name="Hiruma Tanaka",
        school="hiruma_scout",
        school_ring_choice="Air",
        knacks={"double_attack": 2, "feint": 3, "iaijutsu": 1},
        foreign_knacks={"feint": 1},  # unrelated; must NOT be touched
        published_state=pub,
        is_published=True,
    )
    db.add(char)
    db.add_all([
        CharacterVersion(
            character_id=char_id, version_number=1,
            state={"knacks": {"double_attack": 1, "feint": 1, "iaijutsu": 1}},
            summary="Initial character creation",
        ),
        CharacterVersion(
            character_id=char_id, version_number=2,
            state={"knacks": {"double_attack": 2, "feint": 2, "iaijutsu": 1}},
            summary="Feint changed from 1 to 2",
        ),
        CharacterVersion(
            character_id=char_id, version_number=3,
            state={"knacks": {"double_attack": 2, "feint": 3, "iaijutsu": 1}},
            summary="Feint changed from 2 to 3; Became 3rd Dan",
        ),
    ])
    db.add(RollHistory(
        character_id=char_id, roll_key="knack:feint",
        actor_discord_id="abc", payload={"title": "Feint"},
    ))
    db.commit()
    return char


def test_dry_run_changes_nothing(db):
    _seed_hiruma(db)
    report = mig.migrate_character(db, 10, apply=False)
    assert any("DRY RUN" in line for line in report)
    # Reload from DB: still feint everywhere.
    char = db.query(Character).filter(Character.id == 10).first()
    assert char.knacks == {"double_attack": 2, "feint": 3, "iaijutsu": 1}
    assert char.published_state["knacks"]["feint"] == 3
    v2 = db.query(CharacterVersion).filter_by(
        character_id=10, version_number=2).first()
    assert v2.summary == "Feint changed from 1 to 2"
    assert v2.state["knacks"]["feint"] == 2


def test_apply_rewrites_character_and_all_versions(db):
    _seed_hiruma(db)
    report = mig.migrate_character(db, 10, apply=True)
    assert any("APPLIED" in line for line in report)

    char = db.query(Character).filter(Character.id == 10).first()
    # Live knacks: rank preserved, feint gone.
    assert char.knacks == {
        "double_attack": 2, "counterattack": 3, "iaijutsu": 1,
    }
    assert "feint" not in char.knacks
    # published_state snapshot rewritten too.
    assert char.published_state["knacks"] == {
        "double_attack": 2, "counterattack": 3, "iaijutsu": 1,
    }

    versions = (
        db.query(CharacterVersion)
        .filter_by(character_id=10)
        .order_by(CharacterVersion.version_number)
        .all()
    )
    # Rank progression preserved as counterattack 1 -> 2 -> 3.
    assert [v.state["knacks"]["counterattack"] for v in versions] == [1, 2, 3]
    assert all("feint" not in v.state["knacks"] for v in versions)
    # Summaries rewritten; the non-feint summary is left alone.
    assert versions[0].summary == "Initial character creation"
    assert versions[1].summary == "Counterattack changed from 1 to 2"
    assert versions[2].summary == "Counterattack changed from 2 to 3; Became 3rd Dan"


def test_foreign_knacks_and_roll_history_untouched(db):
    _seed_hiruma(db)
    report = mig.migrate_character(db, 10, apply=True)
    char = db.query(Character).filter(Character.id == 10).first()
    # A feint bought from another school is unrelated - left as-is.
    assert char.foreign_knacks == {"feint": 1}
    # Roll history is reported but not modified.
    assert any("roll_history" in line for line in report)
    rolls = db.query(RollHistory).filter_by(character_id=10).all()
    assert len(rolls) == 1
    assert rolls[0].roll_key == "knack:feint"


def test_idempotent_second_run_is_noop(db):
    _seed_hiruma(db)
    mig.migrate_character(db, 10, apply=True)
    report = mig.migrate_character(db, 10, apply=True)
    assert any("nothing to do" in line for line in report)


def test_school_guard_aborts_on_non_hiruma(db):
    # A Shosuro Courtier legitimately has feint as a school knack.
    char = Character(
        id=20, name="Shosuro Spy", school="shosuro_courtier",
        knacks={"double_attack": 1, "feint": 2, "iaijutsu": 1},
    )
    db.add(char)
    db.commit()
    report = mig.migrate_character(db, 20, apply=True)
    assert any("ABORT" in line for line in report)
    # Untouched.
    char = db.query(Character).filter(Character.id == 20).first()
    assert char.knacks["feint"] == 2

    # --force overrides the guard.
    report = mig.migrate_character(db, 20, apply=True, force=True)
    assert any("APPLIED" in line for line in report)
    char = db.query(Character).filter(Character.id == 20).first()
    assert char.knacks == {"double_attack": 1, "counterattack": 2, "iaijutsu": 1}


def test_parametrized_counterattack_to_lunge(db):
    # The same machinery renames any knack id, e.g. a later Hiruma change
    # from counterattack -> lunge.
    char = Character(
        id=40, name="Hiruma Later", school="hiruma_scout",
        knacks={"double_attack": 4, "counterattack": 4, "iaijutsu": 4},
        published_state={"knacks": {"double_attack": 4, "counterattack": 4, "iaijutsu": 4}},
    )
    db.add(char)
    db.add(CharacterVersion(
        character_id=40, version_number=1,
        state={"knacks": {"counterattack": 4, "double_attack": 4, "iaijutsu": 4}},
        summary="Counterattack changed from 3 to 4",
    ))
    db.commit()
    report = mig.migrate_character(
        db, 40, apply=True,
        old_knack="counterattack", new_knack="lunge",
        old_name="Counterattack", new_name="Lunge",
    )
    assert any("APPLIED" in line for line in report)
    char = db.query(Character).filter(Character.id == 40).first()
    assert char.knacks == {"double_attack": 4, "lunge": 4, "iaijutsu": 4}
    assert char.published_state["knacks"]["lunge"] == 4
    v1 = db.query(CharacterVersion).filter_by(character_id=40, version_number=1).first()
    assert v1.state["knacks"]["lunge"] == 4
    assert "counterattack" not in v1.state["knacks"]
    assert v1.summary == "Lunge changed from 3 to 4"


def test_missing_character_reports_error(db):
    report = mig.migrate_character(db, 999, apply=True)
    assert any("no character with id=999" in line for line in report)


def test_both_knacks_present_is_skipped_not_clobbered(db):
    # A row that somehow holds both is left for a human.
    char = Character(
        id=30, name="Weird", school="hiruma_scout",
        knacks={"feint": 2, "counterattack": 1, "iaijutsu": 1},
    )
    db.add(char)
    db.commit()
    report = mig.migrate_character(db, 30, apply=True)
    assert any("SKIPPED" in line for line in report)
    char = db.query(Character).filter(Character.id == 30).first()
    # Nothing clobbered.
    assert char.knacks == {"feint": 2, "counterattack": 1, "iaijutsu": 1}
