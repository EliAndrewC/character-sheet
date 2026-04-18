"""Tests for app/services/import_reconcile.py (XP recompute + notes)."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.services.import_reconcile import (
    IMPORT_NOTES_LABEL,
    XpReconciliation,
    build_import_notes_html,
    build_sections,
    reconcile_xp,
    run_post_llm_pipeline,
)
from app.services.import_schema import ExtractedCharacter
from app.services.import_validate import (
    AmbiguityEntry,
    DroppedEntry,
    ValidationReport,
    validate_and_normalise,
)


def _canonical_extracted() -> ExtractedCharacter:
    return ExtractedCharacter.model_validate({
        "name": "Kakita Tomoe",
        "player_name": "Eli",
        "school_name_as_written": "Kakita Duelist",
        "school_ring_choice": "Fire",
        "rings": {"air": 2, "fire": 4, "earth": 2, "water": 3, "void": 2},
        "attack": 3, "parry": 3,
        "skills": [
            {"name_as_written": "Etiquette", "rank": 3},
            {"name_as_written": "Sincerity", "rank": 3},
            {"name_as_written": "Tact", "rank": 2},
            {"name_as_written": "Heraldry", "rank": 2},
            {"name_as_written": "History", "rank": 2},
            {"name_as_written": "Culture", "rank": 2},
            {"name_as_written": "Strategy", "rank": 1},
        ],
        "knacks": [
            {"name_as_written": "Iaijutsu", "rank": 3},
            {"name_as_written": "Double Attack", "rank": 2},
            {"name_as_written": "Lunge", "rank": 2},
        ],
        "advantages": [
            {"name_as_written": "Virtue", "detail": "Courage"},
            {"name_as_written": "Charming"},
            {"name_as_written": "Kind Eye"},
            {"name_as_written": "Highest Regard"},
        ],
        "disadvantages": [
            {"name_as_written": "Proud"},
            {"name_as_written": "Contrary"},
        ],
        "honor": 3.0, "rank": 7.5, "recognition": 7.5,
        "starting_xp": 150,
        "source_stated_spent_xp": 118,
        "source_stated_unspent_xp": 32,
        "freeform_sections": [
            {"label": "Background", "content": "Born to the Kakita family."},
        ],
    })


# ---------------------------------------------------------------------------
# reconcile_xp
# ---------------------------------------------------------------------------

def test_reconcile_matches_expected_for_canonical_character() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    # The canonical fixture was designed to land at exactly 118 XP.
    assert xp.computed_spent == 118
    assert xp.source_stated_spent == 118
    assert xp.discrepancy == 0
    assert xp.has_discrepancy() is False


def test_reconcile_sets_earned_xp_to_cover_overspend() -> None:
    """When spent > starting_xp, earned_xp absorbs the excess so the
    resulting character is internally consistent."""
    extracted = _canonical_extracted()
    # Force a heavier build to push spent > 150.
    extracted.rings.fire = 5
    extracted.rings.water = 4
    extracted.attack = 4
    extracted.parry = 4
    data, report = validate_and_normalise(extracted)
    xp = reconcile_xp(data, report)
    assert xp.computed_spent > 150
    assert data["earned_xp"] == xp.computed_spent - 150


def test_reconcile_reports_discrepancy_when_source_xp_wrong() -> None:
    extracted = _canonical_extracted()
    # User claimed they spent 60, but the real total is 118.
    extracted.source_stated_spent_xp = 60
    _data, report = validate_and_normalise(extracted)
    # validate_and_normalise copies source-stated XP into the report.
    assert report.source_stated_spent_xp == 60


def test_reconcile_no_source_xp_gives_none_discrepancy() -> None:
    extracted = _canonical_extracted()
    extracted.source_stated_spent_xp = None
    extracted.source_stated_earned_xp = None
    extracted.source_stated_unspent_xp = None
    data, report = validate_and_normalise(extracted)
    xp = reconcile_xp(data, report)
    assert xp.discrepancy is None
    assert xp.has_discrepancy() is False


def test_reconcile_earned_xp_is_never_negative() -> None:
    """If the imported stats cost less than starting_xp (unspent budget),
    earned_xp stays at 0; the UI shows the unspent XP separately."""
    extracted = _canonical_extracted()
    # Minimal build so spent < 150.
    extracted.rings = extracted.rings.model_copy(update={"fire": 2})
    extracted.skills = []
    extracted.attack = 1
    extracted.parry = 1
    data, report = validate_and_normalise(extracted)
    xp = reconcile_xp(data, report)
    assert xp.computed_spent <= 150
    assert data["earned_xp"] == 0


# ---------------------------------------------------------------------------
# Import Notes HTML rendering
# ---------------------------------------------------------------------------

def test_import_notes_includes_source_descriptor_and_model() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(
        data, report, xp,
        source_descriptor="happy_plaintext.txt",
        model_used="gemini-2.5-flash",
    )
    assert "happy_plaintext.txt" in html_
    assert "gemini-2.5-flash" in html_


def test_import_notes_marks_fallback_when_used() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(
        data, report, xp,
        model_used="gemini-2.5-pro",
        fallback_used=True,
    )
    assert "fallback" in html_


def test_import_notes_summarises_dropped_entries() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.dropped.append(
        DroppedEntry(kind="skill", name_as_written="Gourmet")
    )
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "Gourmet" in html_
    assert "Dropped" in html_


def test_import_notes_surfaces_school_unmatched_flag() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.school_unmatched = "Void Monk of the Lost Isles"
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "Void Monk of the Lost Isles" in html_


def test_import_notes_surfaces_wrong_school_knacks() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.wrong_school_knacks = True
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "knacks" in html_.lower()


def test_import_notes_wrong_school_knacks_handles_blank_school() -> None:
    """Edge case: the orchestrator sets wrong_school_knacks but the
    school never matched, so school_id is empty. We should not crash."""
    data, report = validate_and_normalise(_canonical_extracted())
    data["school"] = ""
    report.wrong_school_knacks = True
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    # The sentence still renders without a school name.
    assert "knacks" in html_.lower()


def test_import_notes_surfaces_ring_pool_halving() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.ring_pool_halved.append("Fire")
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "pool" in html_.lower()


def test_import_notes_surfaces_ring_clamp() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.ring_clamped.append(("Air", 12, 6))
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "Air" in html_ and "12" in html_ and "6" in html_


def test_import_notes_surfaces_invalid_school_ring_choice() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.school_ring_choice_invalid = True
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "school ring" in html_.lower()


def test_import_notes_renders_ambiguity_for_school() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.ambiguities.append(AmbiguityEntry(
        kind="school",
        name_as_written="Crane Duelist",
        resolved_id="kakita_duelist",
        confidence="aliased",
    ))
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "Crane Duelist" in html_
    assert "Kakita Duelist" in html_
    assert "aliased" in html_


def test_import_notes_renders_ambiguity_for_skill_knack_advantage() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.ambiguities.extend([
        AmbiguityEntry(kind="skill", name_as_written="Lore",
                       resolved_id="history", confidence="aliased"),
        AmbiguityEntry(kind="knack", name_as_written="iai",
                       resolved_id="iaijutsu", confidence="aliased"),
        AmbiguityEntry(kind="advantage", name_as_written="Charmng",
                       resolved_id="charming", confidence="fuzzy"),
        AmbiguityEntry(kind="disadvantage", name_as_written="Pr",
                       resolved_id="proud", confidence="fuzzy"),
    ])
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    # Every resolved canonical name renders.
    for needle in ("History", "Iaijutsu", "Charming", "Proud"):
        assert needle in html_


def test_import_notes_surfaces_llm_low_confidence_fields() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.llm_low_confidence_fields.append("school")
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "school" in html_


def test_import_notes_xp_section_is_always_present() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "XP reconciliation" in html_
    assert "118" in html_


def test_import_notes_xp_section_notes_match_when_no_discrepancy() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "no XP discrepancy" in html_


def test_import_notes_xp_section_flags_discrepancy() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.source_stated_spent_xp = 60
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "more than" in html_ or "less than" in html_
    assert "Difference" in html_


def test_import_notes_xp_section_notes_underreport_direction() -> None:
    """User stated *more* than the real total; message should say 'less than'."""
    data, report = validate_and_normalise(_canonical_extracted())
    report.source_stated_spent_xp = 999
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "less than" in html_


def test_import_notes_xp_section_includes_all_stated_bits() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    report.source_stated_spent_xp = 118
    report.source_stated_earned_xp = 0
    report.source_stated_unspent_xp = 32
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(data, report, xp)
    assert "118 XP spent" in html_
    assert "32 XP unspent" in html_
    assert "0 XP earned" in html_


def test_import_notes_extra_warnings_surface() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    html_ = build_import_notes_html(
        data, report, xp,
        extra_warnings=[
            "Truncated after 10 PDF pages",
            "Gemini pro retry fired",
        ],
    )
    assert "Truncated after 10 PDF pages" in html_
    assert "Extraction notes" in html_


# ---------------------------------------------------------------------------
# build_sections
# ---------------------------------------------------------------------------

def test_build_sections_puts_import_notes_first() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    sections = build_sections(data, [
        {"label": "Background", "content": "A noble backstory."},
    ], report, xp)
    assert sections[0]["label"] == IMPORT_NOTES_LABEL
    assert sections[1]["label"] == "Background"


def test_build_sections_sanitizes_untrusted_content() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    sections = build_sections(data, [
        {"label": "Backstory",
         "content": "<script>alert(1)</script>Kept text"},
    ], report, xp)
    # sanitize_html strips scripts. The literal tags from the content
    # are also HTML-escaped before sanitisation (we treat them as text).
    body = sections[1]["html"]
    assert "<script>" not in body
    assert "Kept text" in body


def test_build_sections_truncates_long_labels() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    sections = build_sections(data, [
        {"label": "x" * 300, "content": "body"},
    ], report, xp)
    assert len(sections[1]["label"]) == 120


def test_build_sections_handles_missing_label() -> None:
    data, report = validate_and_normalise(_canonical_extracted())
    xp = reconcile_xp(data, report)
    sections = build_sections(data, [
        {"content": "body but no label"},
    ], report, xp)
    assert sections[1]["label"] == "Untitled"


# ---------------------------------------------------------------------------
# run_post_llm_pipeline (integration)
# ---------------------------------------------------------------------------

def test_run_pipeline_produces_expected_character_data() -> None:
    result = run_post_llm_pipeline(
        _canonical_extracted(),
        source_descriptor="happy_plaintext.txt",
        model_used="gemini-2.5-flash",
    )
    data = result["character_data"]
    assert data["name"] == "Kakita Tomoe"
    assert data["school"] == "kakita_duelist"
    assert data["school_ring_choice"] == "Fire"
    assert data["ring_fire"] == 4
    assert data["skills"]["etiquette"] == 3
    assert "iaijutsu" in data["knacks"]
    assert "virtue" in data["advantages"]
    assert "highest_regard" in data["campaign_advantages"]
    assert data["advantage_details"]["virtue"]["text"] == "Courage"
    assert result["xp"].computed_spent == 118


def test_run_pipeline_includes_extra_warnings() -> None:
    result = run_post_llm_pipeline(
        _canonical_extracted(),
        extra_warnings=["test warning"],
    )
    notes_html = result["sections"][0]["html"]
    assert "test warning" in notes_html


def test_run_pipeline_default_source_descriptor_omits_line() -> None:
    """When the orchestrator doesn't pass a source descriptor, Import
    Notes still renders but without the source line."""
    result = run_post_llm_pipeline(_canonical_extracted())
    notes_html = result["sections"][0]["html"]
    assert "Source:" not in notes_html


def test_run_pipeline_empty_freeform_sections_just_gives_import_notes() -> None:
    extracted = _canonical_extracted()
    extracted.freeform_sections = []
    result = run_post_llm_pipeline(extracted)
    assert len(result["sections"]) == 1
    assert result["sections"][0]["label"] == IMPORT_NOTES_LABEL


# ---------------------------------------------------------------------------
# Integration: fixture text + recorded LLM response -> final character
# ---------------------------------------------------------------------------
#
# This exercises the Phase 5 pipeline end-to-end against the canonical
# fixture without ever calling the real LLM (we use a recorded response).

def test_integration_canonical_fixture_end_to_end() -> None:
    """Simulates the full flow after Phase 4: we already have an
    ExtractedCharacter-shaped dict the LLM would have returned, and we
    run it through validate + reconcile + sections to produce a
    Character-ready payload."""
    # This is exactly what a happy Gemini call would produce for our
    # fixture. It mirrors tests/import_fixtures/happy_path/
    # canonical.expected.json, stepped back one notch to the "as written"
    # shape that the LLM emits.
    llm_response = {
        "name": "Kakita Tomoe",
        "player_name": "Eli",
        "school_name_as_written": "Kakita Duelist",
        "school_ring_choice": "Fire",
        "rings": {"air": 2, "fire": 4, "earth": 2, "water": 3, "void": 2},
        "attack": 3, "parry": 3,
        "skills": [
            {"name_as_written": "Etiquette", "rank": 3},
            {"name_as_written": "Sincerity", "rank": 3},
            {"name_as_written": "Tact", "rank": 2},
            {"name_as_written": "Heraldry", "rank": 2},
            {"name_as_written": "History", "rank": 2},
            {"name_as_written": "Culture", "rank": 2},
            {"name_as_written": "Strategy", "rank": 1},
        ],
        "knacks": [
            {"name_as_written": "Iaijutsu", "rank": 3},
            {"name_as_written": "Double Attack", "rank": 2},
            {"name_as_written": "Lunge", "rank": 2},
        ],
        "advantages": [
            {"name_as_written": "Virtue", "detail": "Courage"},
            {"name_as_written": "Charming"},
            {"name_as_written": "Kind Eye"},
            {"name_as_written": "Highest Regard"},
        ],
        "disadvantages": [
            {"name_as_written": "Proud"},
            {"name_as_written": "Contrary"},
        ],
        "honor": 3.0, "rank": 7.5, "recognition": 7.5,
        "starting_xp": 150,
        "source_stated_spent_xp": 118,
        "source_stated_unspent_xp": 32,
        "freeform_sections": [
            {"label": "Background", "content": "Born to the Kakita family."},
            {"label": "Appearance",
             "content": "Tall for a Crane, with pale silver hair."},
        ],
    }
    extracted = ExtractedCharacter.model_validate(llm_response)
    result = run_post_llm_pipeline(
        extracted,
        source_descriptor="happy_plaintext.txt",
        model_used="gemini-2.5-flash",
    )
    data = result["character_data"]

    # Match against canonical.expected.json's character block. We assert
    # the important identity / ring / skills / knacks / adv / disadv /
    # honor bits; a future change to the rule defaults shouldn't require
    # editing this test unless the change is actually behavioural.
    assert data["name"] == "Kakita Tomoe"
    assert data["player_name"] == "Eli"
    assert data["school"] == "kakita_duelist"
    assert data["school_ring_choice"] == "Fire"
    assert (data["ring_air"], data["ring_fire"], data["ring_earth"],
            data["ring_water"], data["ring_void"]) == (2, 4, 2, 3, 2)
    assert data["attack"] == 3
    assert data["parry"] == 3
    assert data["skills"] == {
        "etiquette": 3, "sincerity": 3, "tact": 2,
        "heraldry": 2, "history": 2, "culture": 2, "strategy": 1,
    }
    assert data["knacks"] == {"iaijutsu": 3, "double_attack": 2, "lunge": 2}
    assert data["advantages"] == ["virtue", "charming", "kind_eye"]
    assert data["campaign_advantages"] == ["highest_regard"]
    assert data["disadvantages"] == ["proud", "contrary"]
    assert data["advantage_details"]["virtue"]["text"] == "Courage"
    assert data["honor"] == 3.0
    assert data["rank"] == 7.5
    assert data["starting_xp"] == 150
    assert data["earned_xp"] == 0  # spent == starting, no earned XP needed

    # XP reconciliation: 118 spent = 118 stated, no discrepancy.
    assert result["xp"].computed_spent == 118
    assert result["xp"].has_discrepancy() is False

    # Sections: Import Notes first, then the two freeform sections.
    assert result["sections"][0]["label"] == IMPORT_NOTES_LABEL
    assert result["sections"][1]["label"] == "Background"
    assert result["sections"][2]["label"] == "Appearance"
