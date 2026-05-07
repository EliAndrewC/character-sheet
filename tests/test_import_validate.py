"""Tests for app/services/import_validate.py."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.services.import_schema import ExtractedCharacter
from app.services.import_validate import (
    AmbiguityEntry,
    DroppedEntry,
    ValidationReport,
    validate_and_normalise,
)


def _canonical_payload() -> Dict[str, Any]:
    return {
        "name": "Kakita Tomoe",
        "player_name": "Eli",
        "school_name_as_written": "Kakita Duelist",
        "school_ring_choice": "Fire",
        "rings": {"air": 2, "fire": 4, "earth": 2, "water": 3, "void": 2},
        "attack": 3, "parry": 3,
        "skills": [{"name_as_written": "Etiquette", "rank": 3}],
        "knacks": [
            {"name_as_written": "Iaijutsu", "rank": 3},
            {"name_as_written": "Double Attack", "rank": 2},
            {"name_as_written": "Lunge", "rank": 2},
        ],
        "advantages": [
            {"name_as_written": "Virtue", "detail": "Courage"},
            {"name_as_written": "Charming"},
        ],
        "disadvantages": [{"name_as_written": "Proud"}],
        "honor": 3.0, "rank": 7.5, "recognition": 7.5,
        "starting_xp": 150,
    }


def _run(payload: Dict[str, Any]):
    return validate_and_normalise(ExtractedCharacter.model_validate(payload))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_canonical_payload_validates_cleanly() -> None:
    data, report = _run(_canonical_payload())
    assert data["school"] == "kakita_duelist"
    assert data["school_ring_choice"] == "Fire"
    assert data["ring_fire"] == 4
    assert data["skills"] == {"etiquette": 3}
    assert "iaijutsu" in data["knacks"]
    assert "virtue" in data["advantages"]
    assert "proud" in data["disadvantages"]
    assert report.dropped == []
    assert report.wrong_school_knacks is False


# ---------------------------------------------------------------------------
# School handling
# ---------------------------------------------------------------------------

def test_unmatched_school_is_blank_and_reported() -> None:
    payload = _canonical_payload()
    payload["school_name_as_written"] = "Void Monk of the Lost Isles"
    data, report = _run(payload)
    assert data["school"] == ""
    assert data["school_ring_choice"] == ""
    assert report.school_unmatched == "Void Monk of the Lost Isles"


def test_aliased_school_is_flagged_as_ambiguity() -> None:
    payload = _canonical_payload()
    payload["school_name_as_written"] = "Crane Duelist"
    data, report = _run(payload)
    assert data["school"] == "kakita_duelist"
    assert any(a.kind == "school" and a.confidence == "aliased"
               for a in report.ambiguities)


def test_missing_school_name_produces_no_unmatched_flag() -> None:
    payload = _canonical_payload()
    payload["school_name_as_written"] = None
    data, report = _run(payload)
    assert data["school"] == ""
    assert report.school_unmatched is None


def test_fixed_ring_school_autosets_ring_choice_even_if_llm_missed_it() -> None:
    """Kakita Duelist's ring is fixed Fire; we auto-set regardless of LLM."""
    payload = _canonical_payload()
    payload["school_ring_choice"] = None
    data, _report = _run(payload)
    assert data["school_ring_choice"] == "Fire"


def test_flex_ring_school_uses_llm_choice_when_valid() -> None:
    """Brotherhood of Shinsei Monk can choose any non-Void; we respect the
    LLM's pick when it's legal."""
    payload = _canonical_payload()
    payload["school_name_as_written"] = "Brotherhood of Shinsei Monk"
    payload["school_ring_choice"] = "Water"
    data, report = _run(payload)
    assert data["school"] == "brotherhood_of_shinsei_monk"
    assert data["school_ring_choice"] == "Water"
    assert report.school_ring_choice_invalid is False


def test_flex_ring_school_flags_invalid_ring_choice() -> None:
    payload = _canonical_payload()
    payload["school_name_as_written"] = "Brotherhood of Shinsei Monk"
    # Void is explicitly not allowed for this school.
    payload["school_ring_choice"] = "Void"
    data, report = _run(payload)
    assert data["school_ring_choice"] == ""
    assert report.school_ring_choice_invalid is True


def test_flex_ring_school_leaves_ring_blank_when_llm_gave_none() -> None:
    """Multi-option school + null LLM choice: leave blank for the user."""
    payload = _canonical_payload()
    payload["school_name_as_written"] = "Brotherhood of Shinsei Monk"
    payload["school_ring_choice"] = None
    data, report = _run(payload)
    assert data["school_ring_choice"] == ""
    assert report.school_ring_choice_invalid is False


# ---------------------------------------------------------------------------
# Rings
# ---------------------------------------------------------------------------

def test_ring_pool_values_are_halved_and_reported() -> None:
    payload = _canonical_payload()
    # Player wrote Fire "pool" of 8 (really rank 4).
    payload["rings"]["fire"] = 8
    payload["rings"]["water"] = 6  # exactly 6 stays as is (it's a legal rank)
    data, report = _run(payload)
    assert data["ring_fire"] == 4
    assert "Fire" in report.ring_pool_halved
    # 6 doesn't trigger halving.
    assert data["ring_water"] == 6
    assert "Water" not in report.ring_pool_halved


def test_ring_value_out_of_range_is_clamped() -> None:
    payload = _canonical_payload()
    payload["rings"]["air"] = 99  # halved to 49 and then clamped to 6
    data, report = _run(payload)
    assert data["ring_air"] == 6
    assert any(r[0] == "Air" and r[2] == 6 for r in report.ring_clamped)


def test_ring_value_zero_is_clamped_to_one() -> None:
    payload = _canonical_payload()
    payload["rings"]["earth"] = 0
    data, report = _run(payload)
    assert data["ring_earth"] == 1
    assert any(r[0] == "Earth" and r[2] == 1 for r in report.ring_clamped)


def test_null_rings_default_to_two() -> None:
    payload = _canonical_payload()
    payload["rings"] = {"air": None, "fire": None, "earth": None,
                        "water": None, "void": None}
    data, _report = _run(payload)
    # Default (RING_DEFAULT) is 2 for non-school rings; school ring gets
    # bumped to 3 because school_ring_choice is set.
    assert data["ring_air"] == 2
    assert data["ring_fire"] == 3  # school ring bump
    assert data["ring_earth"] == 2


def test_school_ring_bump_raises_ring_from_default_to_three() -> None:
    """Even when the source omits the school ring value, the importer
    should start it at 3 so XP math reflects the school's free bump."""
    payload = _canonical_payload()
    payload["rings"]["fire"] = 2  # below the school default
    data, _report = _run(payload)
    assert data["ring_fire"] == 3


# ---------------------------------------------------------------------------
# Skills / Knacks
# ---------------------------------------------------------------------------

def test_unknown_skill_is_dropped_and_reported() -> None:
    payload = _canonical_payload()
    payload["skills"].append({"name_as_written": "Gourmet", "rank": 2})
    data, report = _run(payload)
    assert "gourmet" not in data["skills"]
    assert any(d.kind == "skill" and d.name_as_written == "Gourmet"
               for d in report.dropped)


def test_aliased_skill_recorded_as_ambiguity() -> None:
    """Lore aliases to history - should show up in ambiguities, not
    dropped, and resolve under the canonical id."""
    payload = _canonical_payload()
    payload["skills"].append({"name_as_written": "Lore", "rank": 2})
    data, report = _run(payload)
    assert data["skills"].get("history") == 2
    assert any(a.kind == "skill" and a.resolved_id == "history"
               for a in report.ambiguities)


def test_skill_ranks_are_clamped_to_max() -> None:
    payload = _canonical_payload()
    payload["skills"].append({"name_as_written": "Sincerity", "rank": 99})
    data, _report = _run(payload)
    assert data["skills"]["sincerity"] == 5


def test_duplicate_skill_keeps_higher_rank() -> None:
    payload = _canonical_payload()
    payload["skills"].extend([
        {"name_as_written": "Tact", "rank": 2},
        {"name_as_written": "Tact", "rank": 4},
    ])
    data, _report = _run(payload)
    assert data["skills"]["tact"] == 4


def test_school_knacks_are_granted_at_rank_one_when_missing() -> None:
    """Even if the LLM forgets, Kakita Duelist starts with Iaijutsu,
    Double Attack, Lunge all at rank 1."""
    payload = _canonical_payload()
    payload["knacks"] = []  # user wrote no knacks
    data, _report = _run(payload)
    for k in ("iaijutsu", "double_attack", "lunge"):
        assert data["knacks"][k] >= 1


def test_wrong_school_knacks_flagged() -> None:
    """User imports Hida Bushi school but writes Courtier knacks."""
    payload = _canonical_payload()
    payload["school_name_as_written"] = "Hida Bushi"
    payload["knacks"] = [
        {"name_as_written": "Discern Honor", "rank": 3},
        {"name_as_written": "Oppose Social", "rank": 2},
        {"name_as_written": "Worldliness", "rank": 2},
    ]
    data, report = _run(payload)
    # The user's chosen knacks AND the school's free knacks both get
    # into the dict; the flag tells Import Notes to call this out.
    assert report.wrong_school_knacks is True
    assert "discern_honor" in data["knacks"]


def test_unknown_knack_dropped() -> None:
    payload = _canonical_payload()
    payload["knacks"].append({"name_as_written": "Sword Dance", "rank": 2})
    data, report = _run(payload)
    assert "sword_dance" not in data["knacks"]
    assert any(d.kind == "knack" for d in report.dropped)


# ---------------------------------------------------------------------------
# Advantages / disadvantages
# ---------------------------------------------------------------------------

def test_campaign_advantage_routed_to_campaign_list() -> None:
    payload = _canonical_payload()
    payload["advantages"].append({"name_as_written": "Highest Regard"})
    data, _report = _run(payload)
    assert "highest_regard" in data["campaign_advantages"]
    assert "highest_regard" not in data["advantages"]


def test_detail_text_preserved_in_advantage_details() -> None:
    payload = _canonical_payload()
    data, _report = _run(payload)
    assert data["advantage_details"]["virtue"]["text"] == "Courage"


def test_family_reckoning_with_detail_goes_to_advantages_list() -> None:
    """Bucket-based disambiguation: under Advantages -> righteous sting."""
    payload = _canonical_payload()
    payload["advantages"].append(
        {"name_as_written": "Family Reckoning", "detail": ""}
    )
    data, _report = _run(payload)
    assert "family_reckoning_righteous_sting" in data["campaign_advantages"]


def test_specialization_via_dedicated_field_with_resolved_skill() -> None:
    """The LLM emits Specializations on the dedicated ``specializations``
    field. Each entry has ``text`` and ``skill_as_written``; the validator
    resolves the skill to a skill id and builds data["specializations"]."""
    payload = _canonical_payload()
    payload["specializations"] = [
        {"text": "Court Etiquette", "skill_as_written": "Etiquette"},
        {"text": "Loyalty Speeches", "skill_as_written": "Bragging"},
    ]
    data, _report = _run(payload)
    assert data["specializations"] == [
        {"text": "Court Etiquette", "skills": ["etiquette"]},
        {"text": "Loyalty Speeches", "skills": ["bragging"]},
    ]
    # Specialization is NOT in the flat advantages list.
    assert "specialization" not in data["advantages"]


def test_specialization_via_legacy_advantages_field_diverted() -> None:
    """An older LLM shape (or document) might emit Specialization as an
    entry in the `advantages` list with the sub-domain in ``detail``. The
    validator must divert it into ``specializations`` rather than persist
    it as a standard advantage. Skill stays empty - the user picks it on
    the edit page."""
    payload = _canonical_payload()
    payload["advantages"].append(
        {"name_as_written": "Specialization", "detail": "Court Etiquette"}
    )
    data, _report = _run(payload)
    assert "specialization" not in data["advantages"]
    # Detail bubbled into spec text; skills empty for the user to fill in.
    assert {"text": "Court Etiquette", "skills": []} in data["specializations"]


def test_specialization_unknown_skill_lands_with_empty_skills_and_ambiguity() -> None:
    """If the LLM-supplied skill name doesn't resolve, keep the spec
    (text is still useful) with empty skills and report an ambiguity."""
    payload = _canonical_payload()
    payload["specializations"] = [
        {"text": "Whittling", "skill_as_written": "Lumberjacking"},
    ]
    data, report = _run(payload)
    assert {"text": "Whittling", "skills": []} in data["specializations"]


def test_no_specializations_field_yields_empty_list() -> None:
    payload = _canonical_payload()
    data, _report = _run(payload)
    assert data["specializations"] == []


def test_specialization_with_aliased_skill_name_records_ambiguity() -> None:
    """If the LLM-supplied skill name is aliased / fuzzy-matched (not an
    exact match), the validator still resolves it but logs an ambiguity
    so the Import Notes section can flag it."""
    payload = _canonical_payload()
    payload["specializations"] = [
        {"text": "Bow Strings", "skill_as_written": "Etiqette"},  # typo
    ]
    data, report = _run(payload)
    # The fuzzy match still resolves, but with an ambiguity entry.
    assert data["specializations"] == [
        {"text": "Bow Strings", "skills": ["etiquette"]},
    ]
    assert any(
        a.kind == "specialization" and a.resolved_id == "etiquette"
        for a in report.ambiguities
    )


def test_unknown_advantage_dropped() -> None:
    payload = _canonical_payload()
    payload["advantages"].append({"name_as_written": "Administrator"})
    data, report = _run(payload)
    assert "administrator" not in data["advantages"]
    assert "administrator" not in data["campaign_advantages"]
    assert any(d.kind == "advantage" for d in report.dropped)


def test_aliased_advantage_recorded_as_ambiguity() -> None:
    """Add a misspelled advantage so we exercise fuzzy matching on the
    advantage catalog."""
    payload = _canonical_payload()
    payload["advantages"].append({"name_as_written": "Charmng"})  # typo
    data, report = _run(payload)
    assert "charming" in data["advantages"]
    assert any(a.kind == "advantage" for a in report.ambiguities)


def test_duplicate_advantage_deduplicated() -> None:
    payload = _canonical_payload()
    payload["advantages"].extend([
        {"name_as_written": "Charming"},
        {"name_as_written": "Charming"},
    ])
    data, _report = _run(payload)
    assert data["advantages"].count("charming") == 1


# ---------------------------------------------------------------------------
# Technique choices
# ---------------------------------------------------------------------------

def test_technique_choices_resolved_to_skill_ids() -> None:
    payload = _canonical_payload()
    payload["first_dan_choices"] = ["Etiquette", "Sincerity"]
    payload["second_dan_choice"] = "Etiquette"
    data, _report = _run(payload)
    assert data["technique_choices"]["first_dan_choices"] == ["etiquette", "sincerity"]
    assert data["technique_choices"]["second_dan_choice"] == "etiquette"


def test_technique_choice_with_unknown_skill_dropped() -> None:
    payload = _canonical_payload()
    payload["first_dan_choices"] = ["Etiquette", "Underwater Basketry"]
    payload["second_dan_choice"] = "Also Fake"
    data, report = _run(payload)
    assert data["technique_choices"]["first_dan_choices"] == ["etiquette"]
    assert "second_dan_choice" not in data["technique_choices"]
    assert any(d.kind == "technique_choice" for d in report.dropped)


def test_technique_choice_aliased_skill_is_ambiguity() -> None:
    payload = _canonical_payload()
    payload["first_dan_choices"] = ["Lore"]  # aliased -> history
    data, report = _run(payload)
    assert data["technique_choices"]["first_dan_choices"] == ["history"]
    assert any(a.kind == "technique_choice" for a in report.ambiguities)


def test_kitsune_warden_third_dan_skill_choices_resolved() -> None:
    """Kitsune Warden 3rd Dan: source-stated skill names resolve to
    SKILL ids and persist into technique_choices.third_dan_skill_choices."""
    payload = _canonical_payload()
    payload["third_dan_skill_choices"] = ["Bragging", "Sincerity", "Tact"]
    data, _report = _run(payload)
    assert data["technique_choices"]["third_dan_skill_choices"] == [
        "bragging", "sincerity", "tact",
    ]


def test_kitsune_warden_third_dan_drops_iaijutsu_with_warning() -> None:
    """Iaijutsu in third_dan_skill_choices is dropped (rules-excluded)
    and surfaces a DroppedEntry with that reason in the import report."""
    payload = _canonical_payload()
    payload["third_dan_skill_choices"] = ["Bragging", "Iaijutsu", "Tact"]
    data, report = _run(payload)
    # iaijutsu dropped; the other two persist.
    assert data["technique_choices"]["third_dan_skill_choices"] == [
        "bragging", "tact",
    ]
    assert any(
        d.kind == "technique_choice" and d.name_as_written == "Iaijutsu"
        and "iaijutsu" in (d.reason or "").lower()
        for d in report.dropped
    )


def test_kitsune_warden_third_dan_unknown_skill_dropped() -> None:
    """Unknown skill names in third_dan_skill_choices are dropped."""
    payload = _canonical_payload()
    payload["third_dan_skill_choices"] = ["Bragging", "Underwater Basketry"]
    data, report = _run(payload)
    assert data["technique_choices"]["third_dan_skill_choices"] == ["bragging"]
    assert any(
        d.kind == "technique_choice" and d.name_as_written == "Underwater Basketry"
        for d in report.dropped
    )


def test_kitsune_warden_third_dan_empty_omits_key() -> None:
    """When no third_dan_skill_choices are extracted, the key is NOT
    written to technique_choices (existing semantics for first_dan_choices
    and second_dan_choice)."""
    payload = _canonical_payload()
    # Default empty list - third_dan_skill_choices is the schema default.
    data, _report = _run(payload)
    assert "third_dan_skill_choices" not in data.get("technique_choices", {})


def test_kitsune_warden_third_dan_aliased_skill_creates_ambiguity() -> None:
    """An aliased/fuzzy match in third_dan_skill_choices resolves but is
    flagged in report.ambiguities."""
    payload = _canonical_payload()
    payload["third_dan_skill_choices"] = ["Lore"]  # alias -> history
    data, report = _run(payload)
    assert data["technique_choices"]["third_dan_skill_choices"] == ["history"]
    assert any(a.kind == "technique_choice" for a in report.ambiguities)


def test_technique_choice_second_dan_aliased_match_recorded() -> None:
    """Aliased resolution of second_dan_choice also lands in ambiguities."""
    payload = _canonical_payload()
    payload["second_dan_choice"] = "Lore"  # alias for history
    data, report = _run(payload)
    assert data["technique_choices"]["second_dan_choice"] == "history"
    assert any(a.kind == "technique_choice" and a.resolved_id == "history"
               for a in report.ambiguities)


def test_technique_choice_first_dan_dedupes() -> None:
    payload = _canonical_payload()
    payload["first_dan_choices"] = ["Etiquette", "etiquette"]
    data, _report = _run(payload)
    assert data["technique_choices"]["first_dan_choices"] == ["etiquette"]


# ---------------------------------------------------------------------------
# Honor / Rank / Recognition
# ---------------------------------------------------------------------------

def test_honor_clamped_to_five() -> None:
    payload = _canonical_payload()
    payload["honor"] = 99.0
    data, _report = _run(payload)
    assert data["honor"] == 5.0


def test_honor_clamped_above_zero() -> None:
    payload = _canonical_payload()
    payload["honor"] = -2.0
    data, _report = _run(payload)
    assert data["honor"] == 0.5


def test_recognition_cap_follows_rank() -> None:
    """Recognition max is 1.5 * rank."""
    payload = _canonical_payload()
    payload["rank"] = 6.0
    payload["recognition"] = 99
    data, _report = _run(payload)
    assert data["recognition"] == pytest.approx(9.0)


def test_missing_honor_defaults() -> None:
    payload = _canonical_payload()
    payload["honor"] = None
    data, _report = _run(payload)
    assert data["honor"] == 1.0


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------

def test_combat_skills_clamped_to_max() -> None:
    payload = _canonical_payload()
    payload["attack"] = 99
    payload["parry"] = -5
    data, _report = _run(payload)
    assert data["attack"] == 5
    assert data["parry"] == 1


# ---------------------------------------------------------------------------
# LLM low-confidence passthrough
# ---------------------------------------------------------------------------

def test_llm_low_confidence_fields_propagated() -> None:
    payload = _canonical_payload()
    payload["per_field_confidence"] = {"school": "low", "name": "high"}
    _data, report = _run(payload)
    assert "school" in report.llm_low_confidence_fields
    assert "name" not in report.llm_low_confidence_fields


# ---------------------------------------------------------------------------
# Identity string hygiene
# ---------------------------------------------------------------------------

def test_name_and_player_stripped_and_truncated() -> None:
    payload = _canonical_payload()
    payload["name"] = "  Kakita Tomoe  "
    payload["player_name"] = "x" * 200
    data, _report = _run(payload)
    assert data["name"] == "Kakita Tomoe"
    assert len(data["player_name"]) == 120


# ---------------------------------------------------------------------------
# Starting XP clamp
# ---------------------------------------------------------------------------

def test_starting_xp_clamped_and_default() -> None:
    payload = _canonical_payload()
    payload["starting_xp"] = None
    data, _report = _run(payload)
    assert data["starting_xp"] == 150

    payload["starting_xp"] = 99999999
    data, _report = _run(payload)
    assert data["starting_xp"] == 10000
