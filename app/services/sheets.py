"""Google Sheets export: build and format a character sheet spreadsheet."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx

from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES,
    SCHOOL_KNACKS,
    SCHOOLS,
    SKILLS,
)

# ---------------------------------------------------------------------------
# Colour palette (RGB floats 0-1) matching the web app's theme
# ---------------------------------------------------------------------------
_ACCENT = {"red": 0.545, "green": 0.0, "blue": 0.0}  # #8b0000
_WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
_PARCHMENT = {"red": 0.96, "green": 0.94, "blue": 0.91}  # #f5f0e8
_LIGHT_GRAY = {"red": 0.976, "green": 0.976, "blue": 0.976}  # #f9f9f9
_INK = {"red": 0.15, "green": 0.13, "blue": 0.11}
_MUTED = {"red": 0.5, "green": 0.48, "blue": 0.45}

# ---------------------------------------------------------------------------
# Cell / row helper builders
# ---------------------------------------------------------------------------

def _str_cell(text: str, **fmt) -> dict:
    cell: dict = {"userEnteredValue": {"stringValue": str(text)}}
    if fmt:
        cell["userEnteredFormat"] = fmt
    return cell


def _num_cell(value, **fmt) -> dict:
    cell: dict = {"userEnteredValue": {"numberValue": float(value)}}
    if fmt:
        cell["userEnteredFormat"] = fmt
    return cell


def _blank_cell(**fmt) -> dict:
    cell: dict = {"userEnteredValue": {"stringValue": ""}}
    if fmt:
        cell["userEnteredFormat"] = fmt
    return cell


def _bold(**extra) -> dict:
    fmt: dict = {"textFormat": {"bold": True}}
    fmt.update(extra)
    return fmt


def _header_fmt() -> dict:
    return {
        "backgroundColor": _ACCENT,
        "textFormat": {"bold": True, "foregroundColor": _WHITE, "fontSize": 10},
        "horizontalAlignment": "CENTER",
    }


def _subheader_fmt() -> dict:
    return {
        "backgroundColor": _PARCHMENT,
        "textFormat": {"bold": True, "fontSize": 10},
    }


def _title_fmt() -> dict:
    return {
        "textFormat": {"bold": True, "fontSize": 16, "foregroundColor": _INK},
    }


def _row_bg(row_index: int) -> dict:
    """Alternating row background: white for even, light gray for odd."""
    if row_index % 2 == 1:
        return {"backgroundColor": _LIGHT_GRAY}
    return {}


def _right_align() -> dict:
    return {"horizontalAlignment": "RIGHT"}


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

def strip_html(html: str) -> str:
    """Convert sanitized HTML to plain text for spreadsheet cells."""
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>\s*<li[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    return text


# ---------------------------------------------------------------------------
# Tab builders - each returns a list of row-dicts (list of cell-dicts)
# ---------------------------------------------------------------------------

def _build_overview_rows(
    character,
    char_dict: dict,
    school,
    char_knacks: dict,
    dan: int,
    effective: Any,
    skill_rolls: dict,
    char_foreign_knacks: Optional[dict] = None,
) -> List[List[dict]]:
    """Build rows for the main 'Character Sheet' tab."""
    rows: List[List[dict]] = []
    ring_map = char_dict.get("rings", {})

    # Title
    rows.append([_str_cell(character.name, **_title_fmt())])

    # Identity
    school_name = school.name if school else "No school"
    dan_suffix = {1: "st", 2: "nd", 3: "rd"}.get(dan, "th")
    rows.append([
        _str_cell("Player", **_bold()),
        _str_cell(character.player_name or ""),
        _str_cell("School", **_bold()),
        _str_cell(school_name),
    ])
    rows.append([
        _str_cell("Dan", **_bold()),
        _str_cell(f"{dan}{dan_suffix}"),
        _str_cell("School Ring", **_bold()),
        _str_cell(character.school_ring_choice or ""),
    ])

    # Blank separator
    rows.append([])

    # Special Ability
    if school and school.special_ability:
        rows.append([_str_cell("Special Ability", **_subheader_fmt())])
        rows.append([_str_cell(school.special_ability)])
        rows.append([])

    # --- Rings ---
    rows.append([
        _str_cell("Ring", **_header_fmt()),
        _str_cell("Value", **_header_fmt()),
    ])
    for i, ring_name in enumerate(["Air", "Fire", "Earth", "Water", "Void"]):
        label = ring_name
        if ring_name == character.school_ring_choice:
            label += " (School)"
        bg = _row_bg(i)
        rows.append([_str_cell(label, **bg), _num_cell(ring_map.get(ring_name, 2), **bg)])

    rows.append([])

    # --- Derived Stats ---
    rows.append([_str_cell("Derived Stats", **_subheader_fmt())])
    tn_to_hit = 5 + 5 * character.parry
    init_rolled = ring_map.get("Void", 2) + 1
    init_kept = ring_map.get("Void", 2)
    wc_rolled = ring_map.get("Water", 2) + 1
    wc_kept = ring_map.get("Water", 2)
    rows.append([
        _str_cell("TN to be Hit", **_bold()), _num_cell(tn_to_hit),
    ])
    rows.append([
        _str_cell("Initiative", **_bold()), _str_cell(f"{init_rolled}k{init_kept}"),
    ])
    rows.append([
        _str_cell("Wound Check", **_bold()), _str_cell(f"{wc_rolled}k{wc_kept}"),
    ])
    rows.append([
        _str_cell("Impaired at", **_bold()),
        _str_cell(f"{ring_map.get('Earth', 2)} serious wounds"),
    ])
    rows.append([
        _str_cell("Dying at", **_bold()),
        _str_cell(f"{ring_map.get('Earth', 2) * 2} serious wounds"),
    ])

    rows.append([])

    # --- Combat Skills ---
    rows.append([
        _str_cell("Combat Skill", **_header_fmt()),
        _str_cell("Rank", **_header_fmt()),
        _str_cell("Roll", **_header_fmt()),
    ])
    fire = ring_map.get("Fire", 2)
    air = ring_map.get("Air", 2)
    rows.append([
        _str_cell("Attack"), _num_cell(character.attack),
        _str_cell(f"{character.attack + fire}k{fire}"),
    ])
    rows.append([
        _str_cell("Parry"), _num_cell(character.parry),
        _str_cell(f"{character.parry + air}k{air}"),
    ])

    rows.append([])

    # --- School Knacks ---
    rows.append([
        _str_cell("Knack", **_header_fmt()),
        _str_cell("Ring", **_header_fmt()),
        _str_cell("Rank", **_header_fmt()),
    ])
    for i, (kid, info) in enumerate(char_knacks.items()):
        if info.get("data"):
            bg = _row_bg(i)
            rows.append([
                _str_cell(info["data"].name, **bg),
                _str_cell(info["data"].ring or "", **bg),
                _num_cell(info["rank"], **bg),
            ])

    # --- Foreign School Knacks (only if any) ---
    if char_foreign_knacks:
        rows.append([])
        rows.append([
            _str_cell("Foreign School Knack", **_header_fmt()),
            _str_cell("Ring", **_header_fmt()),
            _str_cell("Rank", **_header_fmt()),
        ])
        for i, (kid, info) in enumerate(char_foreign_knacks.items()):
            if info.get("data"):
                bg = _row_bg(i)
                rows.append([
                    _str_cell(info["data"].name, **bg),
                    _str_cell(info["data"].ring or "", **bg),
                    _num_cell(info["rank"], **bg),
                ])

    rows.append([])

    # --- Status ---
    rows.append([
        _str_cell("Status", **_header_fmt()),
        _str_cell("Value", **_header_fmt()),
    ])
    rows.append([_str_cell("Honor"), _num_cell(character.honor)])
    rows.append([_str_cell("Rank"), _num_cell(character.rank)])
    rows.append([_str_cell("Recognition"), _num_cell(character.recognition)])
    rows.append([
        _str_cell("Stipend"),
        _str_cell(f"{effective.stipend} koku/year"),
    ])

    # Status modifiers
    for mod_type, mods in [
        ("Rank", effective.rank_modifiers),
        ("Recognition", effective.recognition_modifiers),
        ("Honor", effective.honor_modifiers),
    ]:
        if mods:
            for m in mods:
                rows.append([
                    _str_cell(f"  {mod_type} modifier", **{"textFormat": {"foregroundColor": _MUTED}}),
                    _str_cell(f"{m['value']:+.1f} ({m['source']})", **{"textFormat": {"foregroundColor": _MUTED}}),
                ])

    rows.append([])

    # --- Techniques ---
    if school and school.techniques:
        rows.append([
            _str_cell("Dan", **_header_fmt()),
            _str_cell("Technique", **_header_fmt()),
        ])
        for d, desc in school.techniques.items():
            attained = d <= dan
            fmt: dict = {}
            if attained:
                fmt = _bold()
            else:
                fmt = {"textFormat": {"foregroundColor": _MUTED}}
            dan_suffix_t = {1: "st", 2: "nd", 3: "rd"}.get(d, "th")
            rows.append([
                _str_cell(f"{d}{dan_suffix_t} Dan", **fmt),
                _str_cell(desc, **fmt),
            ])

    return rows


def _build_skills_rows(
    char_dict: dict,
    skill_rolls: dict,
) -> List[List[dict]]:
    """Build rows for the 'Skills' tab."""
    rows: List[List[dict]] = []
    char_skills = char_dict.get("skills") or {}

    rows.append([_str_cell("Skills", **_title_fmt())])
    rows.append([])

    categories = [
        ("Social Skills (Basic)", "social", False),
        ("Social Skills (Advanced)", "social", True),
        ("Knowledge Skills (Basic)", "knowledge", False),
        ("Knowledge Skills (Advanced)", "knowledge", True),
    ]

    for section_label, cat, advanced in categories:
        rows.append([
            _str_cell(section_label, **_subheader_fmt()),
            _blank_cell(**_subheader_fmt()),
            _blank_cell(**_subheader_fmt()),
            _blank_cell(**_subheader_fmt()),
        ])
        rows.append([
            _str_cell("Skill", **_header_fmt()),
            _str_cell("Ring", **_header_fmt()),
            _str_cell("Rank", **_header_fmt()),
            _str_cell("Roll", **_header_fmt()),
        ])
        data_row_idx = 0
        for sid, skill in SKILLS.items():
            if skill.category != cat or skill.is_advanced != advanced:
                continue
            rank = char_skills.get(sid, 0)
            if rank == 0:
                continue
            bg = _row_bg(data_row_idx)
            roll_str = ""
            if sid in skill_rolls:
                roll = skill_rolls[sid]
                roll_str = roll.display
                if len(roll.tooltip_lines) > 1:
                    roll_str += f" ({roll.parenthetical})"
            rows.append([
                _str_cell(skill.name, **bg),
                _str_cell(skill.ring.value, **bg),
                _num_cell(rank, **bg),
                _str_cell(roll_str, **bg),
            ])
            data_row_idx += 1
        rows.append([])

    return rows


def _build_advantages_rows(
    char_dict: dict,
    advantage_details: dict,
) -> List[List[dict]]:
    """Build rows for the 'Advantages & Disadvantages' tab."""
    rows: List[List[dict]] = []

    rows.append([_str_cell("Advantages & Disadvantages", **_title_fmt())])
    rows.append([])

    all_advs = (char_dict.get("advantages") or []) + (char_dict.get("campaign_advantages") or [])
    all_disadvs = (char_dict.get("disadvantages") or []) + (char_dict.get("campaign_disadvantages") or [])
    campaign_advs = set(char_dict.get("campaign_advantages") or [])
    campaign_disadvs = set(char_dict.get("campaign_disadvantages") or [])
    specs = char_dict.get("specializations") or []

    # Advantages section (incl. one row per Specialization since each
    # instance is its own line item with distinct text/skill).
    if all_advs or specs:
        rows.append([
            _str_cell("Advantage", **_header_fmt()),
            _str_cell("Details", **_header_fmt()),
        ])
        i = 0
        for aid in all_advs:
            adv = ADVANTAGES.get(aid) or CAMPAIGN_ADVANTAGES.get(aid)
            if not adv:
                continue
            bg = _row_bg(i)
            name = adv.name
            if aid in campaign_advs:
                name += " (campaign)"
            detail = advantage_details.get(aid, {})
            detail_text = detail.get("text", "") if isinstance(detail, dict) else ""
            rows.append([_str_cell(name, **bg), _str_cell(detail_text, **bg)])
            i += 1
        for spec in specs:
            bg = _row_bg(i)
            text = (spec.get("text") or "").strip()
            skill_id = (spec.get("skills") or [None])[0]
            sk = SKILLS.get(skill_id) if skill_id else None
            detail_text = f"{text} ({sk.name})" if (text and sk) else text or (sk.name if sk else "")
            rows.append([
                _str_cell("Specialization", **bg),
                _str_cell(detail_text, **bg),
            ])
            i += 1
        rows.append([])

    # Disadvantages section
    if all_disadvs:
        rows.append([
            _str_cell("Disadvantage", **_header_fmt()),
            _str_cell("Details", **_header_fmt()),
        ])
        for i, did in enumerate(all_disadvs):
            dis = DISADVANTAGES.get(did) or CAMPAIGN_DISADVANTAGES.get(did)
            if not dis:
                continue
            bg = _row_bg(i)
            name = dis.name
            if did in campaign_disadvs:
                name += " (campaign)"
            detail = advantage_details.get(did, {})
            detail_text = detail.get("text", "") if isinstance(detail, dict) else ""
            rows.append([_str_cell(name, **bg), _str_cell(detail_text, **bg)])

    return rows


def _build_xp_rows(
    xp_breakdown: dict,
    char_dict: dict,
) -> List[List[dict]]:
    """Build rows for the 'XP Breakdown' tab."""
    rows: List[List[dict]] = []

    rows.append([_str_cell("XP Breakdown", **_title_fmt())])
    rows.append([])

    section_keys = [
        "rings", "school_knacks", "skills", "combat_skills",
        "advantages", "honor_rank_recognition", "foreign_knacks",
        "disadvantages",
    ]

    for key in section_keys:
        section = xp_breakdown.get(key)
        if section is None:
            # Older callers may pass a breakdown that predates this section.
            continue
        # Foreign knacks: skip the section entirely when the character has
        # none, mirroring the View Sheet's conditional rendering.
        if key == "foreign_knacks" and not section.get("rows"):
            continue
        rows.append([
            _str_cell(section["label"], **_subheader_fmt()),
            _blank_cell(**_subheader_fmt()),
            _blank_cell(**_subheader_fmt()),
        ])
        rows.append([
            _str_cell("XP", **_header_fmt()),
            _str_cell("Item", **_header_fmt()),
            _str_cell("Change", **_header_fmt()),
        ])

        if "subsections" in section:
            for sub in section["subsections"]:
                if sub["rows"]:
                    rows.append([
                        _blank_cell(),
                        _str_cell(sub["label"], **_bold()),
                        _blank_cell(),
                    ])
                    for i, item in enumerate(sub["rows"]):
                        if item.get("note"):
                            continue
                        bg = _row_bg(i)
                        change = ""
                        if "from_val" in item:
                            change = f"{item['from_val']} -> {item['to_val']}"
                        rows.append([
                            _num_cell(item["xp"], **{**bg, **_right_align()}),
                            _str_cell(item["label"], **bg),
                            _str_cell(change, **bg),
                        ])
        else:
            for i, item in enumerate(section.get("rows", [])):
                if item.get("note"):
                    continue
                bg = _row_bg(i)
                change = ""
                if "from_val" in item:
                    change = f"{item['from_val']} -> {item['to_val']}"
                rows.append([
                    _num_cell(item["xp"], **{**bg, **_right_align()}),
                    _str_cell(item["label"], **bg),
                    _str_cell(change, **bg),
                ])

        # Category total
        rows.append([
            _num_cell(section["total"], **_bold(**_right_align())),
            _str_cell(f"Total {section['label']}", **_bold()),
            _blank_cell(),
        ])
        rows.append([])

    # Grand totals
    dis_xp = abs(xp_breakdown["disadvantages"]["total"])
    gross_spent = xp_breakdown["grand_total"] + dis_xp
    budget = char_dict.get("starting_xp", 150) + char_dict.get("earned_xp", 0) + dis_xp
    remaining = budget - gross_spent

    rows.append([
        _str_cell("Summary", **_subheader_fmt()),
        _blank_cell(**_subheader_fmt()),
        _blank_cell(**_subheader_fmt()),
    ])
    rows.append([
        _num_cell(gross_spent, **_bold(**_right_align())),
        _str_cell("Total Spent", **_bold()),
        _blank_cell(),
    ])
    rows.append([
        _num_cell(budget, **_bold(**_right_align())),
        _str_cell("Total Budget", **_bold()),
        _str_cell(f"({char_dict.get('starting_xp', 150)} starting + {char_dict.get('earned_xp', 0)} earned + {dis_xp} disadvantages)"),
    ])
    rows.append([
        _num_cell(remaining, **_bold(**_right_align())),
        _str_cell("Unspent", **_bold()),
        _blank_cell(),
    ])

    return rows


def _build_notes_rows(
    char_dict: dict,
) -> List[List[dict]]:
    """Build rows for the 'Notes' tab."""
    rows: List[List[dict]] = []

    rows.append([_str_cell("Notes", **_title_fmt())])
    rows.append([])

    sections = char_dict.get("sections") or []
    for sec in sections:
        label = sec.get("label", "Section")
        html = sec.get("html", "")
        text = strip_html(html)
        if not text:
            continue
        rows.append([_str_cell(label, **_subheader_fmt())])
        # Split into lines so each gets its own row for readability
        for line in text.split("\n"):
            rows.append([_str_cell(line)])
        rows.append([])

    return rows


# ---------------------------------------------------------------------------
# Spreadsheet assembly
# ---------------------------------------------------------------------------

# Column widths per tab (pixels)
_TAB_COLUMNS = {
    "Character Sheet": [200, 180, 150, 350],
    "Skills": [180, 100, 60, 200],
    "Advantages & Disadvantages": [200, 400],
    "XP Breakdown": [60, 250, 150],
    "Notes": [700],
}


def _sheet_properties(title: str, sheet_id: int) -> dict:
    return {
        "properties": {
            "sheetId": sheet_id,
            "title": title,
            "gridProperties": {"frozenRowCount": 1},
        }
    }


def _col_width_requests(sheet_id: int, widths: List[int]) -> List[dict]:
    """Build UpdateDimensionProperties requests for column widths."""
    reqs = []
    for i, w in enumerate(widths):
        reqs.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1,
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })
    return reqs


def _rows_to_update_cells(sheet_id: int, rows: List[List[dict]]) -> dict:
    """Build an UpdateCells request from a list of row data."""
    api_rows = []
    for row in rows:
        api_rows.append({"values": row if row else [_blank_cell()]})
    return {
        "updateCells": {
            "rows": api_rows,
            "fields": "userEnteredValue,userEnteredFormat",
            "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
        }
    }


def _merge_title_request(sheet_id: int, num_cols: int) -> dict:
    """Merge the title row across all columns."""
    return {
        "mergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols,
            },
            "mergeType": "MERGE_ALL",
        }
    }


SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


def _clear_sheet_request(sheet_id: int) -> dict:
    """Build an UpdateCells request that clears all content and formatting."""
    return {
        "updateCells": {
            "range": {"sheetId": sheet_id},
            "fields": "userEnteredValue,userEnteredFormat",
        }
    }


def _unmerge_all_request(sheet_id: int) -> dict:
    """Unmerge all cells on a sheet so we can re-merge the title row cleanly."""
    return {
        "unmergeCells": {
            "range": {"sheetId": sheet_id},
        }
    }


def create_spreadsheet(
    access_token: str,
    character,
    char_dict: dict,
    school,
    char_knacks: dict,
    dan: int,
    xp_breakdown: dict,
    effective,
    skill_rolls: dict,
    existing_sheet_id: Optional[str] = None,
    char_foreign_knacks: Optional[dict] = None,
) -> str:
    """Create or update a formatted Google Sheet and return its URL.

    If ``existing_sheet_id`` is provided, attempts to update that spreadsheet
    in place (clear all tabs, repopulate). Falls back to creating a new sheet
    if the existing one is inaccessible (deleted, permissions revoked, etc.).

    Uses direct HTTP calls to the Sheets API instead of the heavy
    google-api-python-client library (which OOMs on 256MB machines).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    title = f"{character.name} - L7R Character Sheet"

    # Define tab names and IDs
    tabs = [
        ("Character Sheet", 0),
        ("Skills", 1),
        ("Advantages & Disadvantages", 2),
        ("XP Breakdown", 3),
        ("Notes", 4),
    ]

    # Build row data for each tab
    overview_rows = _build_overview_rows(
        character, char_dict, school, char_knacks, dan, effective, skill_rolls,
        char_foreign_knacks=char_foreign_knacks,
    )
    skills_rows = _build_skills_rows(char_dict, skill_rolls)
    adv_rows = _build_advantages_rows(char_dict, character.advantage_details or {})
    xp_rows = _build_xp_rows(xp_breakdown, char_dict)
    notes_rows = _build_notes_rows(char_dict)

    tab_rows = [overview_rows, skills_rows, adv_rows, xp_rows, notes_rows]

    with httpx.Client(timeout=30) as http:
        spreadsheet_id = None
        spreadsheet_url = None

        # Try to update the existing spreadsheet
        if existing_sheet_id:
            resp = http.get(f"{SHEETS_API}/{existing_sheet_id}", headers=headers)
            if resp.status_code == 200:
                spreadsheet_id = existing_sheet_id
                spreadsheet_url = resp.json().get("spreadsheetUrl")

        # Create a new spreadsheet if we don't have one to update
        if not spreadsheet_id:
            spreadsheet_body = {
                "properties": {"title": title},
                "sheets": [_sheet_properties(name, sid) for name, sid in tabs],
            }
            resp = http.post(SHEETS_API, headers=headers, json=spreadsheet_body)
            resp.raise_for_status()
            spreadsheet = resp.json()
            spreadsheet_id = spreadsheet["spreadsheetId"]
            spreadsheet_url = spreadsheet["spreadsheetUrl"]

        # Build all batchUpdate requests
        requests: List[dict] = []

        # If updating an existing sheet, clear all tabs first
        if existing_sheet_id and existing_sheet_id == spreadsheet_id:
            # Update the title
            requests.append({
                "updateSpreadsheetProperties": {
                    "properties": {"title": title},
                    "fields": "title",
                }
            })
            for _tab_name, sheet_id in tabs:
                requests.append(_unmerge_all_request(sheet_id))
                requests.append(_clear_sheet_request(sheet_id))

        for (tab_name, sheet_id), rows in zip(tabs, tab_rows):
            if rows:
                requests.append(_rows_to_update_cells(sheet_id, rows))
            col_widths = _TAB_COLUMNS.get(tab_name, [200])
            requests.extend(_col_width_requests(sheet_id, col_widths))
            num_cols = len(col_widths)
            requests.append(_merge_title_request(sheet_id, num_cols))

        # Execute all formatting in one batch call
        if requests:
            resp = http.post(
                f"{SHEETS_API}/{spreadsheet_id}:batchUpdate",
                headers=headers,
                json={"requests": requests},
            )
            resp.raise_for_status()

    return spreadsheet_url
