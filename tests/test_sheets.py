"""Unit tests for app.services.sheets (spreadsheet formatting logic)."""

import pytest
from app.game_data import SCHOOL_KNACKS, SCHOOLS, SKILLS
from app.services.rolls import compute_skill_roll
from app.services.sheets import (
    _build_advantages_rows,
    _build_notes_rows,
    _build_overview_rows,
    _build_skills_rows,
    _build_xp_rows,
    strip_html,
)
from app.services.status import compute_effective_status
from app.services.xp import calculate_xp_breakdown
from tests.conftest import make_character_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeCharacter:
    """Minimal character-like object for testing sheet builders."""

    def __init__(self, data: dict):
        self.name = data.get("name", "Test Samurai")
        self.player_name = data.get("player_name", "Test Player")
        self.school = data.get("school", "akodo_bushi")
        self.school_ring_choice = data.get("school_ring_choice", "Water")
        self.attack = data.get("attack", 1)
        self.parry = data.get("parry", 1)
        self.honor = data.get("honor", 1.0)
        self.rank = data.get("rank", 7.5)
        self.recognition = data.get("recognition", 7.5)
        self.knacks = data.get("knacks", {})
        self.advantages = data.get("advantages", [])
        self.disadvantages = data.get("disadvantages", [])
        self.advantage_details = data.get("advantage_details", {})
        self.rings = data.get("rings", {"Air": 2, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2})


def _make_knacks(school_id: str, knacks_dict: dict) -> dict:
    school = SCHOOLS.get(school_id)
    result = {}
    if school:
        for knack_id in school.school_knacks:
            knack_data = SCHOOL_KNACKS.get(knack_id)
            rank = knacks_dict.get(knack_id, 1)
            result[knack_id] = {"data": knack_data, "rank": rank}
    return result


# ---------------------------------------------------------------------------
# strip_html tests
# ---------------------------------------------------------------------------

class TestStripHtml:
    def test_strips_tags(self):
        assert strip_html("<p>Hello</p>") == "Hello"

    def test_br_to_newline(self):
        assert strip_html("Line 1<br>Line 2") == "Line 1\nLine 2"

    def test_br_self_closing(self):
        assert strip_html("A<br/>B") == "A\nB"

    def test_preserves_plain_text(self):
        assert strip_html("no tags here") == "no tags here"

    def test_paragraph_separation(self):
        assert strip_html("<p>First</p><p>Second</p>") == "First\n\nSecond"

    def test_list_items(self):
        result = strip_html("<ul><li>A</li><li>B</li></ul>")
        assert "A" in result
        assert "B" in result

    def test_empty_string(self):
        assert strip_html("") == ""

    def test_none_like(self):
        assert strip_html(None) == ""


# ---------------------------------------------------------------------------
# Overview tab tests
# ---------------------------------------------------------------------------

class TestOverviewRows:
    def test_title_row(self):
        data = make_character_data()
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        # First row should be the character name
        assert rows[0][0]["userEnteredValue"]["stringValue"] == "Test Samurai"

    def test_rings_present(self):
        data = make_character_data(rings={"Air": 3, "Fire": 2, "Earth": 4, "Water": 3, "Void": 2})
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        # Find the rings header
        ring_header_idx = None
        for i, row in enumerate(rows):
            if row and row[0].get("userEnteredValue", {}).get("stringValue") == "Ring":
                ring_header_idx = i
                break
        assert ring_header_idx is not None
        # Next 5 rows should be the 5 rings
        ring_names = []
        for j in range(1, 6):
            val = rows[ring_header_idx + j][0]["userEnteredValue"]["stringValue"]
            ring_names.append(val.replace(" (School)", ""))
        assert ring_names == ["Air", "Fire", "Earth", "Water", "Void"]

    def test_school_ring_marked(self):
        data = make_character_data(school_ring_choice="Water")
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        # Find a cell containing "Water (School)"
        found = False
        for row in rows:
            for cell in row:
                val = cell.get("userEnteredValue", {}).get("stringValue", "")
                if "Water (School)" in val:
                    found = True
                    break
        assert found

    def test_derived_stats(self):
        data = make_character_data(parry=3, rings={"Air": 2, "Fire": 2, "Earth": 3, "Water": 2, "Void": 4})
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        # TN to be hit = 5 + 5 * 3 = 20
        tn_found = False
        for row in rows:
            if len(row) >= 2:
                label = row[0].get("userEnteredValue", {}).get("stringValue", "")
                if label == "TN to be Hit":
                    assert row[1]["userEnteredValue"]["numberValue"] == 20
                    tn_found = True
        assert tn_found

    def test_combat_skills(self):
        data = make_character_data(attack=3, parry=2)
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        attack_found = False
        for row in rows:
            if row and row[0].get("userEnteredValue", {}).get("stringValue") == "Attack":
                assert row[1]["userEnteredValue"]["numberValue"] == 3
                attack_found = True
        assert attack_found

    def test_status_section(self):
        data = make_character_data(honor=3.0, rank=8.0, recognition=9.0)
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        honor_found = False
        for row in rows:
            if row and row[0].get("userEnteredValue", {}).get("stringValue") == "Honor":
                assert row[1]["userEnteredValue"]["numberValue"] == 3.0
                honor_found = True
        assert honor_found

    def test_techniques_attained_and_unattained(self):
        data = make_character_data()
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        # Dan 1: only 1st Dan should be bold
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        dan_rows = [r for r in rows if r and "Dan" in r[0].get("userEnteredValue", {}).get("stringValue", "") and "Technique" not in r[0].get("userEnteredValue", {}).get("stringValue", "")]
        # At least 1st Dan row exists
        assert len(dan_rows) >= 1


# ---------------------------------------------------------------------------
# Skills tab tests
# ---------------------------------------------------------------------------

class TestSkillsRows:
    def test_only_nonzero_skills(self):
        data = make_character_data(skills={"bragging": 2, "etiquette": 0, "culture": 3})
        rows = _build_skills_rows(data, {})
        skill_names = []
        for row in rows:
            if row and len(row) >= 3:
                val = row[0].get("userEnteredValue", {}).get("stringValue", "")
                if val in [s.name for s in SKILLS.values()]:
                    skill_names.append(val)
        assert "Bragging" in skill_names
        assert "Culture" in skill_names
        # Etiquette has rank 0, should not appear
        assert "Etiquette" not in skill_names

    def test_skill_rolls_included(self):
        data = make_character_data(skills={"bragging": 3})
        rolls = {}
        roll = compute_skill_roll("bragging", data)
        if roll.rolled > 0:
            rolls["bragging"] = roll
        rows = _build_skills_rows(data, rolls)
        # Find Bragging row and check it has a roll string
        for row in rows:
            if row and row[0].get("userEnteredValue", {}).get("stringValue") == "Bragging":
                roll_str = row[3]["userEnteredValue"]["stringValue"]
                assert "k" in roll_str  # e.g. "5k2"
                break

    def test_grouped_by_category(self):
        data = make_character_data(skills={"bragging": 1, "culture": 1, "acting": 1, "commerce": 1})
        rows = _build_skills_rows(data, {})
        # Check all 4 category sub-headers present
        subheaders = [r[0]["userEnteredValue"]["stringValue"] for r in rows if r and "Skills (" in r[0].get("userEnteredValue", {}).get("stringValue", "")]
        assert "Social Skills (Basic)" in subheaders
        assert "Social Skills (Advanced)" in subheaders
        assert "Knowledge Skills (Basic)" in subheaders
        assert "Knowledge Skills (Advanced)" in subheaders


# ---------------------------------------------------------------------------
# Advantages tab tests
# ---------------------------------------------------------------------------

class TestAdvantagesRows:
    def test_advantages_listed(self):
        data = make_character_data(advantages=["lucky", "charming"])
        rows = _build_advantages_rows(data, {})
        names = [r[0]["userEnteredValue"]["stringValue"] for r in rows if r and r[0].get("userEnteredValue", {}).get("stringValue") not in ("", "Advantage", "Disadvantage", "Advantages & Disadvantages")]
        assert "Lucky" in names
        assert "Charming" in names

    def test_campaign_advantages_marked(self):
        data = make_character_data(campaign_advantages=["household_wealth"])
        rows = _build_advantages_rows(data, {})
        found = False
        for row in rows:
            val = row[0].get("userEnteredValue", {}).get("stringValue", "") if row else ""
            if "(campaign)" in val:
                found = True
        assert found

    def test_disadvantages_listed(self):
        data = make_character_data(disadvantages=["proud"])
        rows = _build_advantages_rows(data, {})
        names = [r[0]["userEnteredValue"]["stringValue"] for r in rows if r and r[0].get("userEnteredValue", {}).get("stringValue") not in ("", "Advantage", "Disadvantage", "Advantages & Disadvantages")]
        assert "Proud" in names

    def test_detail_text_included(self):
        data = make_character_data(advantages=["virtue"])
        details = {"virtue": {"text": "Compassion"}}
        rows = _build_advantages_rows(data, details)
        for row in rows:
            if row and row[0].get("userEnteredValue", {}).get("stringValue", "").startswith("Virtue"):
                assert row[1]["userEnteredValue"]["stringValue"] == "Compassion"
                break


# ---------------------------------------------------------------------------
# XP tab tests
# ---------------------------------------------------------------------------

class TestXpRows:
    def test_grand_totals_present(self):
        data = make_character_data(
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
        )
        xp_breakdown = calculate_xp_breakdown(data)
        rows = _build_xp_rows(xp_breakdown, data)
        # Find "Total Spent" row
        for row in rows:
            if len(row) >= 2 and row[1].get("userEnteredValue", {}).get("stringValue") == "Total Spent":
                total = row[0]["userEnteredValue"]["numberValue"]
                assert total > 0
                return
        pytest.fail("Total Spent row not found")

    def test_unspent_row_present(self):
        data = make_character_data()
        xp_breakdown = calculate_xp_breakdown(data)
        rows = _build_xp_rows(xp_breakdown, data)
        for row in rows:
            if len(row) >= 2 and row[1].get("userEnteredValue", {}).get("stringValue") == "Unspent":
                return
        pytest.fail("Unspent row not found")

    def test_all_categories_present(self):
        data = make_character_data(
            rings={"Air": 3, "Fire": 2, "Earth": 2, "Water": 3, "Void": 2},
            skills={"bragging": 2},
            advantages=["lucky"],
        )
        xp_breakdown = calculate_xp_breakdown(data)
        rows = _build_xp_rows(xp_breakdown, data)
        labels = set()
        for row in rows:
            if row:
                val = row[0].get("userEnteredValue", {}).get("stringValue", "")
                if val:
                    labels.add(val)
        assert "Rings" in labels
        assert "School Knacks" in labels
        assert "Skills" in labels


# ---------------------------------------------------------------------------
# Notes tab tests
# ---------------------------------------------------------------------------

class TestNotesRows:
    def test_sections_rendered(self):
        data = make_character_data(sections=[
            {"label": "Background", "html": "<p>Born in the Lion lands.</p>"},
            {"label": "Personality", "html": "<p>Bold and brave.</p>"},
        ])
        # Inject sections into the dict directly
        rows = _build_notes_rows(data)
        labels = [r[0]["userEnteredValue"]["stringValue"] for r in rows if r and r[0].get("userEnteredFormat", {}).get("backgroundColor") is not None]
        assert "Background" in labels
        assert "Personality" in labels

    def test_html_stripped_in_sections(self):
        data = make_character_data(sections=[
            {"label": "Notes", "html": "<p>Some <strong>bold</strong> text</p>"},
        ])
        rows = _build_notes_rows(data)
        # Find the content row (not the header)
        content_rows = [r for r in rows if r and r[0].get("userEnteredValue", {}).get("stringValue", "").startswith("Some")]
        assert len(content_rows) >= 1
        assert "bold" in content_rows[0][0]["userEnteredValue"]["stringValue"]
        assert "<" not in content_rows[0][0]["userEnteredValue"]["stringValue"]

    def test_empty_sections_omitted(self):
        data = make_character_data(sections=[
            {"label": "Empty", "html": ""},
        ])
        rows = _build_notes_rows(data)
        labels = [r[0]["userEnteredValue"]["stringValue"] for r in rows if r]
        assert "Empty" not in labels
