"""Per-adventure (and per-day) abilities: the counters and toggles a
character spends down between rests - 3rd Dan free raises, Lucky, the knack
pools, Togashi's daily athletics raises.

Shared by the sheet's tracking section (``pages.view_character``) and the
GM's combat tracker, which shows what each combatant has left (design 4.5).
How much of each has been used lives in ``Character.adventure_state``: a
counter under ``<id>_used``, a toggle under ``<id>`` (the sheet's
``getCount`` / ``getToggle`` in ``_tracking_js.html``).
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.game_data import SCHOOL_KNACKS, SCHOOL_TECHNIQUE_BONUSES, SCHOOLS, SKILLS


def per_adventure_abilities(character: Any) -> List[Dict[str, Any]]:
    school = SCHOOLS.get(character.school or "")
    char_knacks: Dict[str, Dict[str, Any]] = {}
    if school:
        for knack_id in school.school_knacks:
            rank = character.knacks.get(knack_id, 1) if character.knacks else 1
            char_knacks[knack_id] = {"data": SCHOOL_KNACKS.get(knack_id), "rank": rank}
    char_foreign_knacks: Dict[str, Dict[str, Any]] = {}
    for knack_id, rank in (character.foreign_knacks or {}).items():
        knack_data = SCHOOL_KNACKS.get(knack_id)
        if knack_data is not None:
            char_foreign_knacks[knack_id] = {"data": knack_data, "rank": rank}
    knack_ranks = [k["rank"] for k in char_knacks.values()] or [0]
    dan = min(knack_ranks)

    per_adventure = []
    advantages = character.advantages or []
    disadvantages = character.disadvantages or []

    # 3rd Dan free raises
    tech_bonuses = SCHOOL_TECHNIQUE_BONUSES.get(character.school, {})
    if dan >= 3 and tech_bonuses.get("third_dan"):
        t3 = tech_bonuses["third_dan"]
        source_skill = t3["source_skill"]
        source_rank = (character.skills or {}).get(source_skill, 0)
        if source_rank > 0:
            skill_name = SKILLS[source_skill].name if source_skill in SKILLS else source_skill
            per_adventure.append({
                "id": "adventure_raises",
                "name": f"3rd Dan Free Raises ({skill_name})",
                "type": "counter",
                "max": 2 * source_rank,
            })

    # Lucky / Unlucky
    if "lucky" in advantages:
        per_adventure.append({"id": "lucky_used", "name": "Lucky (re-roll)", "type": "toggle"})
    if "unlucky" in disadvantages:
        per_adventure.append({"id": "unlucky_used", "name": "Unlucky (GM penalty)", "type": "toggle"})

    # Spendable knacks: conviction, otherworldliness, worldliness, absorb_void.
    # Conviction and otherworldliness both give 2X points per day (X = rank);
    # worldliness and absorb_void pools are X. Conviction is marked per_day so
    # the tracker shows a dedicated "reset" button. Foreign-knack copies grant
    # the same pool (e.g. "if you take Worldliness, you get the Worldliness
    # pool") - absorb_void is supernatural so it can't be a foreign knack.
    # Absorb Void is per-adventure by default (Kitsune Warden uses it that
    # way); the Isawa Ishi special ability overrides it to per-day so the
    # pool resets with a full night's rest alongside the school's VP regen.
    for knack_id in ("conviction", "otherworldliness", "worldliness", "absorb_void"):
        info = char_knacks.get(knack_id) or char_foreign_knacks.get(knack_id)
        if info:
            knack_rank = info["rank"]
            knack_name = info["data"].name
            pool_max = knack_rank * 2 if knack_id in ("otherworldliness", "conviction") else knack_rank
            entry = {
                "id": knack_id,
                "name": knack_name,
                "type": "counter",
                "max": pool_max,
            }
            if knack_id == "conviction":
                entry["per_day"] = True
            if knack_id == "absorb_void" and character.school == "isawa_ishi":
                entry["per_day"] = True
            per_adventure.append(entry)

    # Togashi 3rd Dan: daily pool of 4X athletics free raises (X = precepts).
    # Per-day pool, so gets a dedicated reset button in addition to the
    # per-adventure reset.
    if character.school == "togashi_ise_zumi" and dan >= 3:
        precepts_rank = (character.skills or {}).get("precepts", 0)
        if precepts_rank > 0:
            per_adventure.append({
                "id": "togashi_daily_athletics_raises",
                "name": "Daily Athletics Raises",
                "type": "counter",
                "max": 4 * precepts_rank,
                "per_day": True,
            })
    return per_adventure


def remaining(character: Any, ability: Dict[str, Any]) -> Dict[str, Any]:
    """``{"id", "name", "left", "max"}`` for a counter, or ``{"id", "name",
    "used"}`` for a toggle, read from the character's adventure state."""
    state = character.adventure_state or {}
    if ability["type"] == "toggle":
        return {"id": ability["id"], "name": ability["name"], "used": bool(state.get(ability["id"]))}
    used = int(state.get(ability["id"] + "_used", 0) or 0)
    return {"id": ability["id"], "name": ability["name"],
            "left": max(0, ability["max"] - used), "max": ability["max"]}
