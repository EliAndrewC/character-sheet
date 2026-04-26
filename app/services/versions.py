"""Version management for the draft/publish character model.

Handles publishing drafts, computing diff summaries, and reverting
to previous versions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.game_data import (
    ADVANTAGES, CAMPAIGN_ADVANTAGES, CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES, SCHOOLS, SKILLS, SCHOOL_KNACKS,
)
from app.models import Character, CharacterVersion, award_deltas_for_diff
from app.services.rolls import compute_dan


def _label(key: str) -> str:
    """Turn a snake_case id into a display label."""
    return key.replace("_", " ").title()


def compute_diff_summary(old_state: Dict[str, Any], new_state: Dict[str, Any]) -> List[str]:
    """Compute a human-readable list of changes between two character states."""
    diffs: List[str] = []

    # Name
    old_name = old_state.get("name", "")
    new_name = new_state.get("name", "")
    if old_name != new_name:
        diffs.append(f"Name changed from \"{old_name}\" to \"{new_name}\"")

    # Player name
    old_pn = old_state.get("player_name", "")
    new_pn = new_state.get("player_name", "")
    if old_pn != new_pn:
        diffs.append(f"Player name changed to \"{new_pn}\"")

    # School
    old_school = old_state.get("school", "")
    new_school = new_state.get("school", "")
    if old_school != new_school:
        diffs.append(f"School changed to {_label(new_school)}")

    # Rings
    old_rings = old_state.get("rings", {})
    new_rings = new_state.get("rings", {})
    for ring_name in ["Air", "Fire", "Earth", "Water", "Void"]:
        old_val = old_rings.get(ring_name, 2)
        new_val = new_rings.get(ring_name, 2)
        if old_val != new_val:
            diffs.append(f"{ring_name} raised from {old_val} to {new_val}" if new_val > old_val
                         else f"{ring_name} lowered from {old_val} to {new_val}")

    # Attack / Parry
    for field in ("attack", "parry"):
        old_val = old_state.get(field, 1)
        new_val = new_state.get(field, 1)
        if old_val != new_val:
            diffs.append(f"{field.title()} changed from {old_val} to {new_val}")

    # Skills
    old_skills = old_state.get("skills", {})
    new_skills = new_state.get("skills", {})
    all_skill_ids = set(old_skills.keys()) | set(new_skills.keys())
    for sid in sorted(all_skill_ids):
        old_val = old_skills.get(sid, 0)
        new_val = new_skills.get(sid, 0)
        if old_val != new_val:
            skill_def = SKILLS.get(sid)
            name = skill_def.name if skill_def else _label(sid)
            if old_val == 0:
                diffs.append(f"{name} raised to {new_val}")
            elif new_val == 0:
                diffs.append(f"{name} removed")
            else:
                diffs.append(f"{name} changed from {old_val} to {new_val}")

    # Knacks
    old_knacks = old_state.get("knacks", {})
    new_knacks = new_state.get("knacks", {})
    old_dan = compute_dan(old_knacks) if old_knacks else 0
    new_dan = compute_dan(new_knacks) if new_knacks else 0

    all_knack_ids = set(old_knacks.keys()) | set(new_knacks.keys())
    for kid in sorted(all_knack_ids):
        old_val = old_knacks.get(kid, 0)
        new_val = new_knacks.get(kid, 0)
        if old_val != new_val:
            knack_def = SCHOOL_KNACKS.get(kid)
            name = knack_def.name if knack_def else _label(kid)
            diffs.append(f"{name} changed from {old_val} to {new_val}")

    if new_dan != old_dan and new_dan > old_dan:
        ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}.get(new_dan, f"{new_dan}th")
        diffs.append(f"Became {ordinal} Dan")

    # Honor / Rank / Recognition
    for field, label in [("honor", "Honor"), ("rank", "Rank"), ("recognition", "Recognition")]:
        old_val = old_state.get(field, 1.0)
        new_val = new_state.get(field, 1.0)
        if old_val != new_val:
            diffs.append(f"{label} changed from {old_val} to {new_val}")

    # Advantages
    old_advs = set(old_state.get("advantages", []))
    new_advs = set(new_state.get("advantages", []))
    for aid in sorted(new_advs - old_advs):
        adv = ADVANTAGES.get(aid)
        name = adv.name if adv else _label(aid)
        diffs.append(f"Added advantage: {name}")
    for aid in sorted(old_advs - new_advs):
        adv = ADVANTAGES.get(aid)
        name = adv.name if adv else _label(aid)
        diffs.append(f"Removed advantage: {name}")

    # Disadvantages
    old_dises = set(old_state.get("disadvantages", []))
    new_dises = set(new_state.get("disadvantages", []))
    for did in sorted(new_dises - old_dises):
        dis = DISADVANTAGES.get(did)
        name = dis.name if dis else _label(did)
        diffs.append(f"Added disadvantage: {name}")
    for did in sorted(old_dises - new_dises):
        dis = DISADVANTAGES.get(did)
        name = dis.name if dis else _label(did)
        diffs.append(f"Removed disadvantage: {name}")

    # Campaign advantages
    old_camp_advs = set(old_state.get("campaign_advantages", []))
    new_camp_advs = set(new_state.get("campaign_advantages", []))
    for aid in sorted(new_camp_advs - old_camp_advs):
        adv = CAMPAIGN_ADVANTAGES.get(aid)
        name = adv.name if adv else _label(aid)
        diffs.append(f"Added campaign advantage: {name}")
    for aid in sorted(old_camp_advs - new_camp_advs):
        adv = CAMPAIGN_ADVANTAGES.get(aid)
        name = adv.name if adv else _label(aid)
        diffs.append(f"Removed campaign advantage: {name}")

    # Campaign disadvantages
    old_camp_dises = set(old_state.get("campaign_disadvantages", []))
    new_camp_dises = set(new_state.get("campaign_disadvantages", []))
    for did in sorted(new_camp_dises - old_camp_dises):
        dis = CAMPAIGN_DISADVANTAGES.get(did)
        name = dis.name if dis else _label(did)
        diffs.append(f"Added campaign disadvantage: {name}")
    for did in sorted(old_camp_dises - new_camp_dises):
        dis = CAMPAIGN_DISADVANTAGES.get(did)
        name = dis.name if dis else _label(did)
        diffs.append(f"Removed campaign disadvantage: {name}")

    # Earned XP
    old_xp = old_state.get("earned_xp", 0)
    new_xp = new_state.get("earned_xp", 0)
    if old_xp != new_xp:
        diffs.append(f"Earned XP changed from {old_xp} to {new_xp}")

    return diffs


# ---------------------------------------------------------------------------
# Structured diff for the version-history drill-down
# ---------------------------------------------------------------------------

# Category buckets used for grouping in the UI partial. Order matters - the
# template renders categories in this order. Listed roughly head-to-toe on
# a character sheet.
DIFF_CATEGORIES = (
    "Basics",
    "Rings",
    "Combat",
    "Skills",
    "Knacks",
    "Advantages",
    "Disadvantages",
    "Status",
    "XP",
    "Awards",
    "Sections",
)

# Display ordering for the four core rings + Void.
_RING_ORDER = ("Air", "Fire", "Earth", "Water", "Void")

# Ordinal suffix for Dan-promotion lines.
_DAN_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}


def _ordinal(n: int) -> str:
    return _DAN_ORDINAL.get(n, f"{n}th")


def _entry(category: str, label: str, before: Any, after: Any, kind: str) -> Dict[str, Any]:
    """Construct a DiffEntry dict.

    ``kind`` is one of ``change``, ``add``, ``remove``, ``section_updated``.
    ``before`` / ``after`` are pre-formatted strings (or None for adds /
    removes / opaque updates) - the template renders them as-is.
    """
    return {
        "category": category,
        "label": label,
        "before": before,
        "after": after,
        "kind": kind,
    }


def _fmt_number(val: Any) -> str:
    """Render a value the way the user expects to see it on the sheet.

    Floats keep one decimal so 2.0 doesn't collapse to "2"; ints render
    bare. Strings pass through. Everything else falls back to ``str``.
    """
    if isinstance(val, bool):  # bool is a subclass of int - check first
        return "yes" if val else "no"
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)


def compute_version_diff(
    prev_state: Optional[Dict[str, Any]],
    new_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Compute a structured diff between two character state snapshots.

    Returns a flat list of DiffEntry dicts (see ``_entry``) in stable
    category order, suitable for ``{% for cat, items in entries|groupby('category') %}``
    in a Jinja partial. The publish-path summary uses
    ``compute_diff_summary`` instead - that function returns flat strings
    and is load-bearing for the auto-summary, so this lives alongside it
    rather than replacing it.

    Pass ``prev_state=None`` (or an empty dict) only for the very first
    version - the function returns ``[]`` rather than crashing, but
    callers should normally short-circuit on v1 themselves.
    """
    if not prev_state:
        return []

    entries: List[Dict[str, Any]] = []

    # ---- Basics ----------------------------------------------------------
    for field, label in (("name", "Name"), ("player_name", "Player name")):
        before = prev_state.get(field, "")
        after = new_state.get(field, "")
        if before != after:
            entries.append(_entry("Basics", label, before or "(empty)",
                                  after or "(empty)", "change"))

    # name_explanation is freeform prose; surface only the fact-of-change.
    if prev_state.get("name_explanation", "") != new_state.get("name_explanation", ""):
        entries.append(_entry("Basics", "Name explanation",
                              None, "updated", "section_updated"))

    old_school = prev_state.get("school", "")
    new_school = new_state.get("school", "")
    if old_school != new_school:
        before_label = SCHOOLS[old_school].name if old_school in SCHOOLS else (
            _label(old_school) if old_school else "none"
        )
        after_label = SCHOOLS[new_school].name if new_school in SCHOOLS else (
            _label(new_school) if new_school else "none"
        )
        entries.append(_entry("Basics", "School", before_label, after_label, "change"))
    else:
        # Only emit a school-ring-choice change when the school itself
        # didn't change - otherwise the school line already covers it.
        old_choice = prev_state.get("school_ring_choice", "")
        new_choice = new_state.get("school_ring_choice", "")
        if old_choice != new_choice:
            entries.append(_entry("Basics", "School ring",
                                  old_choice or "none", new_choice or "none", "change"))

    # ---- Rings -----------------------------------------------------------
    old_rings = prev_state.get("rings", {}) or {}
    new_rings = new_state.get("rings", {}) or {}
    for ring in _RING_ORDER:
        before = old_rings.get(ring, 2)
        after = new_rings.get(ring, 2)
        if before != after:
            entries.append(_entry("Rings", ring, before, after, "change"))

    # ---- Combat (attack, parry, technique_choices) -----------------------
    for field, label in (("attack", "Attack"), ("parry", "Parry")):
        before = prev_state.get(field, 1)
        after = new_state.get(field, 1)
        if before != after:
            entries.append(_entry("Combat", label, before, after, "change"))

    old_tech = prev_state.get("technique_choices", {}) or {}
    new_tech = new_state.get("technique_choices", {}) or {}
    # 1st Dan choices: order is presentational, treat as a set.
    old_first = set(old_tech.get("first_dan_choices") or [])
    new_first = set(new_tech.get("first_dan_choices") or [])
    if old_first != new_first:
        entries.append(_entry(
            "Combat", "1st Dan choices",
            ", ".join(sorted(_skill_name(s) for s in old_first)) or "none",
            ", ".join(sorted(_skill_name(s) for s in new_first)) or "none",
            "change",
        ))
    old_second = old_tech.get("second_dan_choice") or ""
    new_second = new_tech.get("second_dan_choice") or ""
    if old_second != new_second:
        entries.append(_entry(
            "Combat", "2nd Dan choice",
            _skill_name(old_second) if old_second else "none",
            _skill_name(new_second) if new_second else "none",
            "change",
        ))

    # ---- Skills ----------------------------------------------------------
    old_skills = prev_state.get("skills", {}) or {}
    new_skills = new_state.get("skills", {}) or {}
    for sid in sorted(set(old_skills) | set(new_skills)):
        before = old_skills.get(sid, 0)
        after = new_skills.get(sid, 0)
        if before == after:
            continue
        name = _skill_name(sid)
        if before == 0:
            entries.append(_entry("Skills", name, None, after, "add"))
        elif after == 0:
            entries.append(_entry("Skills", name, before, None, "remove"))
        else:
            entries.append(_entry("Skills", name, before, after, "change"))

    # ---- Knacks ----------------------------------------------------------
    old_knacks = prev_state.get("knacks", {}) or {}
    new_knacks = new_state.get("knacks", {}) or {}
    for kid in sorted(set(old_knacks) | set(new_knacks)):
        before = old_knacks.get(kid, 0)
        after = new_knacks.get(kid, 0)
        if before == after:
            continue
        knack = SCHOOL_KNACKS.get(kid)
        name = knack.name if knack else _label(kid)
        if before == 0:
            entries.append(_entry("Knacks", name, None, after, "add"))
        elif after == 0:
            entries.append(_entry("Knacks", name, before, None, "remove"))
        else:
            entries.append(_entry("Knacks", name, before, after, "change"))

    # Dan promotion (Dan = lowest school knack rank).
    old_dan = compute_dan(old_knacks) if old_knacks else 0
    new_dan = compute_dan(new_knacks) if new_knacks else 0
    if new_dan > old_dan:
        entries.append(_entry(
            "Knacks", "Dan", _ordinal(old_dan) if old_dan else "none",
            _ordinal(new_dan), "change",
        ))

    # ---- Advantages / Disadvantages --------------------------------------
    _diff_id_list(entries, prev_state, new_state, "advantages",
                  "Advantages", "advantage", ADVANTAGES)
    _diff_id_list(entries, prev_state, new_state, "campaign_advantages",
                  "Advantages", "campaign advantage", CAMPAIGN_ADVANTAGES)
    _diff_id_list(entries, prev_state, new_state, "disadvantages",
                  "Disadvantages", "disadvantage", DISADVANTAGES)
    _diff_id_list(entries, prev_state, new_state, "campaign_disadvantages",
                  "Disadvantages", "campaign disadvantage", CAMPAIGN_DISADVANTAGES)

    # advantage_details: surface only when the advantage still exists on
    # both sides AND the per-advantage detail dict actually changed. New
    # advantages already produce an "add" line above; their initial detail
    # text would be redundant noise.
    old_details = prev_state.get("advantage_details", {}) or {}
    new_details = new_state.get("advantage_details", {}) or {}
    persistent = (
        (set(prev_state.get("advantages") or []) | set(prev_state.get("campaign_advantages") or [])
         | set(prev_state.get("disadvantages") or []) | set(prev_state.get("campaign_disadvantages") or []))
        & (set(new_state.get("advantages") or []) | set(new_state.get("campaign_advantages") or [])
           | set(new_state.get("disadvantages") or []) | set(new_state.get("campaign_disadvantages") or []))
    )
    for aid in sorted(persistent):
        if old_details.get(aid) != new_details.get(aid):
            name = _adv_or_dis_name(aid)
            entries.append(_entry("Advantages", f"{name} details",
                                  None, "updated", "section_updated"))

    # ---- Status (honor, rank, recognition, locks) ------------------------
    for field, label, default in (
        ("honor", "Honor", 1.0),
        ("rank", "Rank", 7.5),
        ("recognition", "Recognition", 7.5),
    ):
        before = prev_state.get(field, default)
        after = new_state.get(field, default)
        if before != after:
            entries.append(_entry("Status", label, _fmt_number(before),
                                  _fmt_number(after), "change"))

    for field, label, default in (
        ("rank_locked", "Rank locked", False),
        ("recognition_halved", "Recognition halved", False),
    ):
        before = prev_state.get(field, default)
        after = new_state.get(field, default)
        if before != after:
            entries.append(_entry("Status", label, _fmt_number(before),
                                  _fmt_number(after), "change"))

    # ---- XP --------------------------------------------------------------
    for field, label, default in (
        ("starting_xp", "Starting XP", 150),
        ("earned_xp", "Earned XP", 0),
    ):
        before = prev_state.get(field, default)
        after = new_state.get(field, default)
        if before != after:
            entries.append(_entry("XP", label, before, after, "change"))

    # ---- Awards ----------------------------------------------------------
    # award_deltas_for_diff strips the freeform ``source`` text so a
    # source-only edit doesn't show up as a phantom diff. We separately
    # render the source on added awards because that text IS the human
    # label for the award.
    old_awards = prev_state.get("rank_recognition_awards", []) or []
    new_awards = new_state.get("rank_recognition_awards", []) or []
    old_award_keys = {a.get("id"): a for a in old_awards if a.get("id")}
    new_award_keys = {a.get("id"): a for a in new_awards if a.get("id")}
    old_norm = {a["id"]: a for a in award_deltas_for_diff(old_awards) if a.get("id")}
    new_norm = {a["id"]: a for a in award_deltas_for_diff(new_awards) if a.get("id")}
    for aid in new_norm:
        if aid not in old_norm:
            full = new_award_keys.get(aid, {})
            entries.append(_entry(
                "Awards", _award_label(full),
                None, _award_after_text(full), "add",
            ))
    for aid in old_norm:
        if aid not in new_norm:
            full = old_award_keys.get(aid, {})
            entries.append(_entry(
                "Awards", _award_label(full),
                _award_after_text(full), None, "remove",
            ))
    for aid, new_n in new_norm.items():
        if aid in old_norm and old_norm[aid] != new_n:
            full_old = old_award_keys.get(aid, {})
            full_new = new_award_keys.get(aid, {})
            entries.append(_entry(
                "Awards", _award_label(full_new or full_old),
                _award_after_text(full_old), _award_after_text(full_new),
                "change",
            ))

    # ---- Sections (notes + rich-text sections) ---------------------------
    if prev_state.get("notes", "") != new_state.get("notes", ""):
        entries.append(_entry("Sections", "Notes",
                              None, "updated", "section_updated"))

    old_sections = prev_state.get("sections", []) or []
    new_sections = new_state.get("sections", []) or []
    old_by_label = {s.get("label", ""): s for s in old_sections}
    new_by_label = {s.get("label", ""): s for s in new_sections}
    for label in sorted(set(new_by_label) - set(old_by_label)):
        entries.append(_entry("Sections", label or "(unnamed)",
                              None, "added", "add"))
    for label in sorted(set(old_by_label) - set(new_by_label)):
        entries.append(_entry("Sections", label or "(unnamed)",
                              "present", None, "remove"))
    for label in sorted(set(old_by_label) & set(new_by_label)):
        if old_by_label[label].get("html", "") != new_by_label[label].get("html", ""):
            entries.append(_entry("Sections", label or "(unnamed)",
                                  None, "section content updated", "section_updated"))

    return entries


def _skill_name(sid: str) -> str:
    skill = SKILLS.get(sid)
    return skill.name if skill else _label(sid)


def _adv_or_dis_name(aid: str) -> str:
    """Resolve an advantage- or disadvantage-style id to its display name.

    Used for the ``advantage_details`` "details updated" line, where the
    id might land in any of the four collections (advantages,
    disadvantages, or their campaign variants).
    """
    for table in (ADVANTAGES, CAMPAIGN_ADVANTAGES, DISADVANTAGES, CAMPAIGN_DISADVANTAGES):
        item = table.get(aid)
        if item:
            return item.name
    return _label(aid)


def _diff_id_list(
    entries: List[Dict[str, Any]],
    prev_state: Dict[str, Any],
    new_state: Dict[str, Any],
    state_key: str,
    category: str,
    label_word: str,
    name_table: Dict[str, Any],
) -> None:
    """Emit add/remove entries for an id-list field (advantages etc.)."""
    old_ids = set(prev_state.get(state_key) or [])
    new_ids = set(new_state.get(state_key) or [])
    for aid in sorted(new_ids - old_ids):
        item = name_table.get(aid)
        name = item.name if item else _label(aid)
        entries.append(_entry(category, f"Added {label_word}: {name}",
                              None, name, "add"))
    for aid in sorted(old_ids - new_ids):
        item = name_table.get(aid)
        name = item.name if item else _label(aid)
        entries.append(_entry(category, f"Removed {label_word}: {name}",
                              name, None, "remove"))


def _award_label(award: Dict[str, Any]) -> str:
    """Short header for an award entry. Falls back to the id snippet so a
    malformed award without a source still renders something."""
    src = (award.get("source") or "").strip()
    if src:
        return src
    aid = award.get("id") or ""
    return f"Award {aid[:8]}" if aid else "Award"


def _award_after_text(award: Dict[str, Any]) -> str:
    """Compact summary of an award's deltas, e.g. ``+0.5 rank, +1.0 recognition``."""
    parts: List[str] = []
    rd = award.get("rank_delta", 0) or 0
    re = award.get("recognition_delta", 0) or 0
    if rd:
        parts.append(f"{rd:+.1f} rank")
    if re:
        parts.append(f"{re:+.1f} recognition")
    if not parts:
        return award.get("type", "award")
    return ", ".join(parts)


def publish_character(
    character: Character,
    db: Session,
    summary: str = "",
    author_discord_id: str | None = None,
) -> CharacterVersion:
    """Apply the current draft as a new version.

    Snapshots the character's current state, uses the provided summary
    (or auto-generates one from the diff), and creates a version record.
    """
    current_state = character.to_dict()
    old_state = character.published_state or {}

    # Use provided summary, or auto-generate from diff
    if not summary:
        if old_state:
            diff_lines = compute_diff_summary(old_state, current_state)
            summary = "; ".join(diff_lines) if diff_lines else "No changes"
        else:
            summary = "Initial character creation"

    # Determine version number
    latest = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.character_id == character.id)
        .order_by(CharacterVersion.version_number.desc())
        .first()
    )
    version_number = (latest.version_number + 1) if latest else 1

    # Create version record
    version = CharacterVersion(
        character_id=character.id,
        version_number=version_number,
        state=current_state,
        summary=summary,
        author_discord_id=author_discord_id,
    )
    db.add(version)

    # Update character's published state
    character.is_published = True
    character.published_state = current_state
    # Apply Changes implicitly reveals a hidden draft. Once cleared, hidden
    # cannot return - revealing is permanent.
    character.is_hidden = False

    # Priest 3rd Dan precepts pool only exists while the priest is at 3rd Dan
    # or higher. If this publish drops them below 3rd Dan, wipe any stored
    # pool so it doesn't silently resurrect if they later rank up again.
    _wipe_precepts_pool_if_dan_drop(character)

    db.flush()
    return version


def revert_character(
    character: Character,
    version_id: int,
    db: Session,
    summary: str = "",
    author_discord_id: str | None = None,
) -> CharacterVersion:
    """Revert a character to a previous version.

    Creates a new version that's a copy of the specified old version,
    updates the character's draft and published state to match.
    """
    old_version = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.id == version_id,
                CharacterVersion.character_id == character.id)
        .first()
    )
    if old_version is None:
        raise ValueError(f"Version {version_id} not found for character {character.id}")

    old_state = old_version.state

    # Restore draft fields from the old state
    _restore_character_from_state(character, old_state)

    # Create new version
    latest = (
        db.query(CharacterVersion)
        .filter(CharacterVersion.character_id == character.id)
        .order_by(CharacterVersion.version_number.desc())
        .first()
    )
    new_version_number = (latest.version_number + 1) if latest else 1

    if not summary:
        summary = f"Reverted to version {old_version.version_number}"

    version = CharacterVersion(
        character_id=character.id,
        version_number=new_version_number,
        state=old_state,
        summary=summary,
        author_discord_id=author_discord_id,
    )
    db.add(version)

    character.published_state = old_state
    character.is_published = True

    # A revert may reset the priest's knack ranks such that their Dan falls
    # below 3; in that case the precepts pool (a 3rd Dan ability) cannot exist.
    _wipe_precepts_pool_if_dan_drop(character)

    db.flush()
    return version


def _wipe_precepts_pool_if_dan_drop(character: Character) -> None:
    """Clear Character.precepts_pool if the character is a Priest whose
    current Dan is below 3. Called from publish_character and revert_character
    so stale pool data doesn't outlive the 3rd Dan technique that created it.
    """
    if character.school != "priest":
        return
    dan = compute_dan(character.knacks or {})
    if dan < 3:
        character.precepts_pool = []


def _restore_character_from_state(character: Character, state: Dict[str, Any]):
    """Update a character's draft fields from a state dict."""
    character.name = state.get("name", character.name)
    character.name_explanation = state.get("name_explanation", "")
    character.player_name = state.get("player_name", "")
    character.school = state.get("school", "")
    character.school_ring_choice = state.get("school_ring_choice", "")

    rings = state.get("rings", {})
    character.ring_air = rings.get("Air", 2)
    character.ring_fire = rings.get("Fire", 2)
    character.ring_earth = rings.get("Earth", 2)
    character.ring_water = rings.get("Water", 2)
    character.ring_void = rings.get("Void", 2)

    character.attack = state.get("attack", 1)
    character.parry = state.get("parry", 1)
    character.skills = state.get("skills", {})
    character.knacks = state.get("knacks", {})
    character.advantages = state.get("advantages", [])
    character.disadvantages = state.get("disadvantages", [])
    character.campaign_advantages = state.get("campaign_advantages", [])
    character.campaign_disadvantages = state.get("campaign_disadvantages", [])
    character.honor = state.get("honor", 1.0)
    character.rank = state.get("rank", 1.0)
    character.rank_locked = state.get("rank_locked", False)
    character.recognition = state.get("recognition", 1.0)
    character.recognition_halved = state.get("recognition_halved", False)
    character.earned_xp = state.get("earned_xp", 0)
    character.notes = state.get("notes", "")
