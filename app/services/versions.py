"""Version management for the draft/publish character model.

Handles publishing drafts, computing diff summaries, and reverting
to previous versions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.game_data import (
    ADVANTAGES, CAMPAIGN_ADVANTAGES, CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES, SKILLS, SCHOOL_KNACKS,
)
from app.models import Character, CharacterVersion
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

    db.flush()
    return version


def _restore_character_from_state(character: Character, state: Dict[str, Any]):
    """Update a character's draft fields from a state dict."""
    character.name = state.get("name", character.name)
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
