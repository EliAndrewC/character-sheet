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

class TestForeignKnackRows:
    """The Character Sheet tab has a 'Foreign School Knacks' section that
    renders only when the character has foreign knacks. Coverage for the
    foreign-knack iteration in _build_overview_rows."""

    def test_foreign_knacks_section_appears(self):
        data = make_character_data()
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        ath_data = SCHOOL_KNACKS.get("athletics")
        foreign = {"athletics": {"data": ath_data, "rank": 2}}
        rows = _build_overview_rows(
            char, data, school, knacks, 1, effective, {},
            char_foreign_knacks=foreign,
        )
        # Find the "Foreign School Knack" header row.
        header_idx = None
        for i, row in enumerate(rows):
            if row and row[0].get("userEnteredValue", {}).get("stringValue") == "Foreign School Knack":
                header_idx = i
                break
        assert header_idx is not None
        # Next row is the Athletics entry: name, ring, rank.
        athletics_row = rows[header_idx + 1]
        assert athletics_row[0]["userEnteredValue"]["stringValue"] == ath_data.name
        assert athletics_row[2]["userEnteredValue"]["numberValue"] == 2

    def test_foreign_knack_with_missing_data_is_skipped(self):
        """If a foreign knack entry has data=None (e.g. an obsolete id),
        the row is skipped without 500ing the spreadsheet build."""
        data = make_character_data()
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        foreign = {"obsolete_id": {"data": None, "rank": 2}}
        rows = _build_overview_rows(
            char, data, school, knacks, 1, effective, {},
            char_foreign_knacks=foreign,
        )
        # Header still appears (the section is gated on the dict having
        # any entries), but no body row for the obsolete id.
        assert not any(
            row and row[0].get("userEnteredValue", {}).get("stringValue") == "obsolete_id"
            for row in rows
        )


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


# ---------------------------------------------------------------------------
# Status modifier rows (rank/recognition/honor modifiers surfaced in overview)
# ---------------------------------------------------------------------------

class TestOverviewStatusModifiers:
    """When the effective status has modifiers (rank/recognition/honor), they
    render as indented sub-rows under the main status lines."""

    def test_rank_modifier_rendered(self):
        data = make_character_data(disadvantages=["bad_reputation"])
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        rows = _build_overview_rows(char, data, school, knacks, 1, effective, {})
        found = False
        for row in rows:
            if len(row) >= 2:
                label = row[0].get("userEnteredValue", {}).get("stringValue", "")
                val = row[1].get("userEnteredValue", {}).get("stringValue", "")
                if "Rank modifier" in label and "Bad Reputation" in val:
                    found = True
                    break
        assert found


# ---------------------------------------------------------------------------
# Unknown advantage/disadvantage IDs are silently skipped
# ---------------------------------------------------------------------------

class TestAdvantageRowsUnknownIds:
    def test_unknown_advantage_id_skipped(self):
        """An advantage ID not in ADVANTAGES nor CAMPAIGN_ADVANTAGES is ignored."""
        data = make_character_data(advantages=["lucky", "mystery_adv_that_was_removed"])
        rows = _build_advantages_rows(data, {})
        # Lucky appears
        assert any(
            row and row[0].get("userEnteredValue", {}).get("stringValue") == "Lucky"
            for row in rows
        )
        # Mystery ID does not appear in any form
        for row in rows:
            for cell in row:
                val = cell.get("userEnteredValue", {}).get("stringValue", "")
                assert "mystery_adv" not in val.lower()

    def test_unknown_disadvantage_id_skipped(self):
        data = make_character_data(disadvantages=["proud", "mystery_dis_that_was_removed"])
        rows = _build_advantages_rows(data, {})
        assert any(
            row and row[0].get("userEnteredValue", {}).get("stringValue") == "Proud"
            for row in rows
        )
        for row in rows:
            for cell in row:
                val = cell.get("userEnteredValue", {}).get("stringValue", "")
                assert "mystery_dis" not in val.lower()

    def test_campaign_disadvantage_gets_campaign_suffix(self):
        data = make_character_data(campaign_disadvantages=["peasantborn"])
        rows = _build_advantages_rows(data, {})
        found = False
        for row in rows:
            val = row[0].get("userEnteredValue", {}).get("stringValue", "") if row else ""
            if "Peasantborn" in val and "(campaign)" in val:
                found = True
                break
        assert found


# ---------------------------------------------------------------------------
# XP rows — note items are skipped inside subsections
# ---------------------------------------------------------------------------

class TestXpRowsSubsectionNote:
    """Lines in a subsection marked with ``"note": True`` are informational
    hints for the UI and must be omitted from the spreadsheet."""

    def test_subsection_note_row_is_skipped(self):
        data = make_character_data()
        # Hand-crafted breakdown: a subsection containing a note row and a
        # regular row. The note row should not appear in the output.
        xp_breakdown = {
            "rings": {"label": "Rings", "total": 0, "rows": []},
            "school_knacks": {"label": "School Knacks", "total": 0, "rows": []},
            "skills": {
                "label": "Skills", "total": 5,
                "subsections": [
                    {"label": "Basic Skills", "rows": [
                        {"xp": 5, "label": "Bragging", "from_val": 0, "to_val": 1},
                        {"xp": 0, "label": "This is a note", "note": True},
                    ]},
                    {"label": "Advanced Skills", "rows": []},
                ],
            },
            "combat_skills": {"label": "Attack / Parry", "total": 0, "rows": []},
            "advantages": {"label": "Advantages", "total": 0, "rows": []},
            "honor_rank_recognition": {
                "label": "Honor / Rank / Recognition", "total": 0, "rows": [],
            },
            "disadvantages": {"label": "Disadvantages", "total": 0, "rows": []},
            "grand_total": 5,
        }
        rows = _build_xp_rows(xp_breakdown, data)
        note_found = False
        bragging_found = False
        for row in rows:
            for cell in row:
                val = cell.get("userEnteredValue", {}).get("stringValue", "")
                if "This is a note" in val:
                    note_found = True
                if val == "Bragging":
                    bragging_found = True
        assert bragging_found
        assert not note_found


# ---------------------------------------------------------------------------
# Low-level request builders for the Sheets batchUpdate API
# ---------------------------------------------------------------------------

class TestSheetsApiRequestBuilders:
    def test_sheet_properties(self):
        from app.services.sheets import _sheet_properties
        out = _sheet_properties("My Tab", 3)
        assert out["properties"]["sheetId"] == 3
        assert out["properties"]["title"] == "My Tab"
        assert out["properties"]["gridProperties"]["frozenRowCount"] == 1

    def test_col_width_requests(self):
        from app.services.sheets import _col_width_requests
        reqs = _col_width_requests(5, [100, 200, 300])
        assert len(reqs) == 3
        assert reqs[0]["updateDimensionProperties"]["range"]["sheetId"] == 5
        assert reqs[0]["updateDimensionProperties"]["properties"]["pixelSize"] == 100
        assert reqs[1]["updateDimensionProperties"]["range"]["startIndex"] == 1
        assert reqs[2]["updateDimensionProperties"]["properties"]["pixelSize"] == 300

    def test_col_width_requests_empty(self):
        from app.services.sheets import _col_width_requests
        assert _col_width_requests(5, []) == []

    def test_rows_to_update_cells(self):
        from app.services.sheets import _rows_to_update_cells, _str_cell
        rows = [[_str_cell("A"), _str_cell("B")], [], [_str_cell("C")]]
        req = _rows_to_update_cells(2, rows)
        assert req["updateCells"]["start"]["sheetId"] == 2
        assert len(req["updateCells"]["rows"]) == 3
        # Empty row gets a single blank cell (Sheets API requires at least one value)
        assert len(req["updateCells"]["rows"][1]["values"]) == 1

    def test_merge_title_request(self):
        from app.services.sheets import _merge_title_request
        req = _merge_title_request(sheet_id=7, num_cols=4)
        rng = req["mergeCells"]["range"]
        assert rng["sheetId"] == 7
        assert rng["endColumnIndex"] == 4
        assert req["mergeCells"]["mergeType"] == "MERGE_ALL"

    def test_clear_sheet_request(self):
        from app.services.sheets import _clear_sheet_request
        req = _clear_sheet_request(4)
        assert req["updateCells"]["range"]["sheetId"] == 4
        assert "userEnteredValue" in req["updateCells"]["fields"]

    def test_unmerge_all_request(self):
        from app.services.sheets import _unmerge_all_request
        req = _unmerge_all_request(9)
        assert req["unmergeCells"]["range"]["sheetId"] == 9


# ---------------------------------------------------------------------------
# create_spreadsheet — full flow with mocked httpx client
# ---------------------------------------------------------------------------

class _FakeHttpResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _FakeHttpClient:
    """httpx.Client replacement: programs sequenced get/post responses."""

    def __init__(self, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    # The test sets these class-level slots before each call.
    get_response = None
    post_responses: list = []  # sequential: first call returns [0], then [1], ...

    def get(self, url, headers=None):
        return _FakeHttpClient.get_response

    def post(self, url, headers=None, json=None):
        _FakeHttpClient.last_post_json = json
        _FakeHttpClient.last_post_url = url
        if _FakeHttpClient.post_responses:
            return _FakeHttpClient.post_responses.pop(0)
        return _FakeHttpResponse(200)


class TestCreateSpreadsheet:
    def _fixtures(self):
        from app.services.status import compute_effective_status
        from app.services.xp import calculate_xp_breakdown
        data = make_character_data()
        char = _FakeCharacter(data)
        school = SCHOOLS.get("akodo_bushi")
        knacks = _make_knacks("akodo_bushi", data["knacks"])
        effective = compute_effective_status(data)
        xp = calculate_xp_breakdown(data)
        return data, char, school, knacks, effective, xp

    def test_creates_new_spreadsheet(self, monkeypatch):
        """No existing_sheet_id → POST to create, then batchUpdate."""
        from app.services import sheets as sheets_mod
        data, char, school, knacks, effective, xp = self._fixtures()

        _FakeHttpClient.get_response = None
        _FakeHttpClient.post_responses = [
            _FakeHttpResponse(200, {
                "spreadsheetId": "new-id",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new-id/edit",
            }),
            _FakeHttpResponse(200, {}),  # batchUpdate
        ]
        monkeypatch.setattr(sheets_mod.httpx, "Client", _FakeHttpClient)

        url = sheets_mod.create_spreadsheet(
            "tok", char, data, school, knacks, 1, xp, effective, {},
            existing_sheet_id=None,
        )
        assert url == "https://docs.google.com/spreadsheets/d/new-id/edit"

    def test_updates_existing_spreadsheet(self, monkeypatch):
        """existing_sheet_id fetches OK → reuses that sheet, no create POST."""
        from app.services import sheets as sheets_mod
        data, char, school, knacks, effective, xp = self._fixtures()

        _FakeHttpClient.get_response = _FakeHttpResponse(200, {
            "spreadsheetId": "old-id",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/old-id/edit",
        })
        _FakeHttpClient.post_responses = [_FakeHttpResponse(200, {})]  # batchUpdate
        monkeypatch.setattr(sheets_mod.httpx, "Client", _FakeHttpClient)

        url = sheets_mod.create_spreadsheet(
            "tok", char, data, school, knacks, 1, xp, effective, {},
            existing_sheet_id="old-id",
        )
        assert url == "https://docs.google.com/spreadsheets/d/old-id/edit"
        # batchUpdate should have included a title update + clears
        batch = _FakeHttpClient.last_post_json
        req_types = {next(iter(r)) for r in batch["requests"]}
        assert "updateSpreadsheetProperties" in req_types
        assert "unmergeCells" in req_types

    def test_falls_back_to_create_when_existing_sheet_gone(self, monkeypatch):
        """If the provided existing_sheet_id returns 404, create a fresh sheet."""
        from app.services import sheets as sheets_mod
        data, char, school, knacks, effective, xp = self._fixtures()

        _FakeHttpClient.get_response = _FakeHttpResponse(404, {})
        _FakeHttpClient.post_responses = [
            _FakeHttpResponse(200, {
                "spreadsheetId": "fresh-id",
                "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/fresh-id/edit",
            }),
            _FakeHttpResponse(200, {}),  # batchUpdate
        ]
        monkeypatch.setattr(sheets_mod.httpx, "Client", _FakeHttpClient)

        url = sheets_mod.create_spreadsheet(
            "tok", char, data, school, knacks, 1, xp, effective, {},
            existing_sheet_id="dead-id",
        )
        assert "fresh-id" in url
