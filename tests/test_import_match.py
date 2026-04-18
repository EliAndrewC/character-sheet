"""Tests for app/services/import_match.py (catalog matching)."""

from __future__ import annotations

import pytest

from app.services.import_match import (
    ADV_BUCKET,
    ALIASED,
    DIS_BUCKET,
    EXACT,
    FUZZY,
    match_advantage_or_disadvantage,
    match_knack,
    match_ring_name,
    match_school,
    match_skill,
)


# ---------------------------------------------------------------------------
# Schools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,expected_id", [
    ("Kakita Duelist", "kakita_duelist"),
    ("kakita duelist", "kakita_duelist"),
    ("  KAKITA   DUELIST  ", "kakita_duelist"),
    ("Hida Bushi", "hida_bushi"),
])
def test_schools_exact_match(query: str, expected_id: str) -> None:
    sid, conf = match_school(query)
    assert sid == expected_id
    assert conf == EXACT


@pytest.mark.parametrize("query,expected_id", [
    ("Crane Duelist", "kakita_duelist"),
    ("Crab Bushi", "hida_bushi"),
    ("Lion Bushi", "akodo_bushi"),
    ("Scorpion Actor", "shosuro_actor"),
    ("Tattooed Monk", "togashi_ise_zumi"),
    ("Ise Zumi", "togashi_ise_zumi"),
    ("Battle Maiden", "otaku_bushi"),
    ("Unicorn Diplomat", "ide_diplomat"),
    ("Shinsei Monk", "brotherhood_of_shinsei_monk"),
])
def test_schools_aliased_match(query: str, expected_id: str) -> None:
    sid, conf = match_school(query)
    assert sid == expected_id
    assert conf == ALIASED


def test_schools_id_echo_matches() -> None:
    """The LLM occasionally returns the raw ID string; we accept that."""
    sid, conf = match_school("kakita_duelist")
    assert sid == "kakita_duelist"
    assert conf == EXACT


def test_schools_fuzzy_match_tolerates_typos() -> None:
    sid, conf = match_school("Kakita Duelistt")  # extra letter
    assert sid == "kakita_duelist"
    assert conf == FUZZY


def test_schools_no_match_returns_none() -> None:
    sid, conf = match_school("Void Monk of the Lost Isles")
    assert sid is None
    assert conf is None


def test_schools_empty_string_returns_none() -> None:
    assert match_school("") == (None, None)
    assert match_school(None if False else "") == (None, None)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,expected_id", [
    ("Etiquette", "etiquette"),
    ("etiquette", "etiquette"),
    ("  Sincerity  ", "sincerity"),
])
def test_skills_exact_match(query: str, expected_id: str) -> None:
    sid, conf = match_skill(query)
    assert sid == expected_id
    assert conf == EXACT


def test_skills_alias_lore_to_history() -> None:
    sid, conf = match_skill("Lore")
    assert sid == "history"
    assert conf == ALIASED


def test_skills_unknown_dropped() -> None:
    sid, conf = match_skill("Gourmet")
    assert (sid, conf) == (None, None)


# ---------------------------------------------------------------------------
# Knacks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,expected_id", [
    ("Iaijutsu", "iaijutsu"),
    ("Double Attack", "double_attack"),
    ("Lunge", "lunge"),
])
def test_knacks_exact_match(query: str, expected_id: str) -> None:
    sid, conf = match_knack(query)
    assert sid == expected_id
    assert conf == EXACT


@pytest.mark.parametrize("query,expected_id", [
    ("iai", "iaijutsu"),
    ("Double Strike", "double_attack"),
    ("Counter Attack", "counterattack"),
])
def test_knacks_aliased_match(query: str, expected_id: str) -> None:
    sid, conf = match_knack(query)
    assert sid == expected_id
    assert conf == ALIASED


def test_knacks_unknown_returns_none() -> None:
    assert match_knack("Sword Dance") == (None, None)


# ---------------------------------------------------------------------------
# Ring names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["Fire", "fire", "FIRE", "  Fire  "])
def test_ring_name_variants_normalize_to_title_case(query: str) -> None:
    assert match_ring_name(query) == "Fire"


def test_ring_name_unknown_returns_none() -> None:
    assert match_ring_name("Void of the Ages") is None


def test_ring_name_empty_returns_none() -> None:
    assert match_ring_name("") is None


# ---------------------------------------------------------------------------
# Advantages / Disadvantages with bucket disambiguation
# ---------------------------------------------------------------------------

def test_advantage_base_catalog_exact_match() -> None:
    aid, catalog, conf = match_advantage_or_disadvantage(
        "Charming", bucket=ADV_BUCKET,
    )
    assert aid == "charming"
    assert catalog == "base"
    assert conf == EXACT


def test_advantage_campaign_catalog_match() -> None:
    aid, catalog, conf = match_advantage_or_disadvantage(
        "Highest Regard", bucket=ADV_BUCKET,
    )
    assert aid == "highest_regard"
    assert catalog == "campaign"
    assert conf == EXACT


def test_disadvantage_base_catalog_exact_match() -> None:
    did, catalog, conf = match_advantage_or_disadvantage(
        "Proud", bucket=DIS_BUCKET,
    )
    assert did == "proud"
    assert catalog == "base"
    assert conf == EXACT


def test_disadvantage_campaign_catalog_match() -> None:
    did, catalog, _conf = match_advantage_or_disadvantage(
        "Crane-indebted", bucket=DIS_BUCKET,
    )
    assert did == "crane_indebted"
    assert catalog == "campaign"


def test_family_reckoning_resolves_to_righteous_under_advantages() -> None:
    """Most important disambiguation: 'Family Reckoning' with no suffix
    under Advantages must resolve to Righteous Sting."""
    aid, catalog, conf = match_advantage_or_disadvantage(
        "Family Reckoning", bucket=ADV_BUCKET,
    )
    assert aid == "family_reckoning_righteous_sting"
    assert catalog == "campaign"
    assert conf == ALIASED


def test_family_reckoning_resolves_to_venomous_under_disadvantages() -> None:
    did, catalog, conf = match_advantage_or_disadvantage(
        "Family Reckoning", bucket=DIS_BUCKET,
    )
    assert did == "family_reckoning_venomous_sting"
    assert catalog == "campaign"
    assert conf == ALIASED


def test_family_reckoning_explicit_suffix_exact_match() -> None:
    """If the source wrote the full name, respect it. The bucket doesn't
    override an explicit choice."""
    aid, catalog, conf = match_advantage_or_disadvantage(
        "Family Reckoning: Righteous Sting", bucket=ADV_BUCKET,
    )
    assert aid == "family_reckoning_righteous_sting"
    assert catalog == "campaign"
    assert conf == EXACT


def test_unknown_advantage_returns_all_none() -> None:
    aid, catalog, conf = match_advantage_or_disadvantage(
        "Administrator", bucket=ADV_BUCKET,
    )
    assert aid is None
    assert catalog is None
    assert conf is None


def test_invalid_bucket_raises_value_error() -> None:
    with pytest.raises(ValueError):
        match_advantage_or_disadvantage("Charming", bucket="neither")
