"""Generated NPCs, encounters and the per-group NPC roster.

combat-design/design.md 4.3. An NPC is a real ``Character`` (so every rule
applies) with ``is_npc`` set, owned by the GM, hidden, and never a party
member: its ``gaming_group_id`` stays NULL so every group / party query
excludes it by construction, and ``npc_group_id`` names the group whose
roster holds it. Players never see one: ``npc_guard`` 404s every
``/characters/{char_id}...`` request for an NPC unless the viewer is an admin.

An encounter is one fight; at most one per group is active (D33). Ending it
archives its NPCs into the roster, from where the GM can bring one back -
healed and rested (D17), optionally having gained XP (D8).
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, Encounter, EncounterAction, EncounterNpc, GamingGroup
from app.services import npc_generator as gen
from app.services.auth import is_admin
from app.services.versions import publish_character
from app.services.void_spend import void_limits

NPC_STATUSES = ("fighting", "unconscious", "dead")

# Fields build_npc() produces that are written straight onto the character.
_BUILD_FIELDS = (
    "school", "school_ring_choice", "profession", "profession_abilities",
    "attack", "parry", "skills", "knacks", "foreign_knacks",
    "technique_choices", "starting_xp", "earned_xp",
    *gen.TRAIT_FIELDS,
)

MAX_NPCS_PER_REQUEST = 30


class EncounterConflict(Exception):
    """Starting a fight while another is active, without saying to end it."""


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def viewer_id(request: Request) -> Optional[str]:
    user = getattr(request.state, "user", None) or {}
    return user.get("discord_id")


def npc_guard(request: Request, db: Session = Depends(get_db)) -> None:
    """Router dependency: an NPC does not exist for anyone but an admin.

    Sits on every router with ``/characters/{char_id}`` routes (pages,
    characters, rolls, art, google_sheets), so no sheet, editor, JSON
    endpoint or roll history of an NPC can reach a player - including a
    player the GM has granted account-level access for their own
    characters. ``tests/test_npcs.py`` fails if a ``{char_id}`` route is
    registered on a router without it.
    """
    raw = request.path_params.get("char_id")
    viewer = viewer_id(request)
    if raw is None or (viewer and is_admin(viewer)):
        return
    try:
        char_id = int(raw)
    except (TypeError, ValueError):
        return  # FastAPI's own validation answers malformed ids
    row = db.query(Character.is_npc).filter(Character.id == char_id).first()
    if row and row[0]:
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Building NPC characters
# ---------------------------------------------------------------------------

def apply_build(character: Character, build: Dict[str, Any]) -> None:
    """Write an ``npc_generator.build_npc`` result onto a character."""
    for field in _BUILD_FIELDS:
        setattr(character, field, build[field])
    rings = build["rings"]
    character.ring_air = rings["Air"]
    character.ring_fire = rings["Fire"]
    character.ring_earth = rings["Earth"]
    character.ring_water = rings["Water"]
    character.ring_void = rings["Void"]
    character.npc_generation = build["generation"]


def rest(character: Character) -> None:
    """Healed and rested (D17): no wounds, full void, no action dice, and
    fresh per-adventure state."""
    character.current_light_wounds = 0
    character.current_serious_wounds = 0
    character.current_temp_void_points = 0
    character.current_void_points = void_limits(character.to_dict())["void_max"]
    character.action_dice = []
    character.adventure_state = {}
    character.precepts_pool = []


def create_npc(
    db: Session, group_id: int, owner_discord_id: str, build: Dict[str, Any], name: str,
) -> Character:
    character = Character(
        name=name,
        player_name="NPC",
        owner_discord_id=owner_discord_id,
        is_hidden=True,
        is_npc=True,
        npc_group_id=group_id,
    )
    apply_build(character, build)
    rest(character)
    db.add(character)
    db.flush()
    publish_character(character, db, summary=_build_summary(build), author_discord_id=owner_discord_id)
    return character


def _build_summary(build: Dict[str, Any]) -> str:
    g = build["generation"]
    return (
        f"Generated NPC: {gen.npc_type_label(g['npc_type'])}, {g['earned_xp']} earned XP, "
        f"{round(100 * g['combat_share'])}% combat (simulator {g['simulator']})"
    )


def rebuild_npc(
    db: Session, npc: Character, *, earned_xp: Optional[int] = None,
    combat_share: Optional[float] = None, author_discord_id: Optional[str] = None,
) -> Character:
    """Re-generate an NPC with a new earned XP and / or combat share.

    Used for the GM's per-NPC overrides after generation and for a returning
    NPC who gained XP. The re-generated build never comes back below the old
    one (``never_below``). Wounds and void are left alone; bringing an NPC
    back rests it separately.
    """
    g = dict(npc.npc_generation or {})
    npc_type = g.get("npc_type") or _infer_type(npc)
    share = gen.clamp_combat_share(combat_share if combat_share is not None
                                   else g.get("combat_share", gen.default_combat_share()))
    earned = earned_xp if earned_xp is not None else npc.earned_xp or 0
    build = gen.build_npc(npc_type, earned, share, traits=g.get("traits"), recorded=g.get("recorded"))
    if earned >= (npc.earned_xp or 0) and combat_share is None:
        build = gen.never_below(npc.to_dict(), build)
    apply_build(npc, build)
    db.flush()
    publish_character(npc, db, summary=_build_summary(build), author_discord_id=author_discord_id)
    return npc


def _infer_type(npc: Character) -> str:
    return gen.WAVE_MAN if npc.profession else npc.school


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

NameProvider = Callable[[int, bool], List[str]]


def fallback_names(db: Session, group_id: int, label: str, count: int) -> List[str]:
    """"Wave Man 4", "Wave Man 5", ... continuing past any already in the roster."""
    pattern = re.compile(rf"^{re.escape(label)} (\d+)$")
    taken = [
        int(m.group(1))
        for (name,) in db.query(Character.name).filter(Character.npc_group_id == group_id)
        if (m := pattern.match(name or ""))
    ]
    start = max(taken, default=0) + 1
    return [f"{label} {start + i}" for i in range(count)]


# ---------------------------------------------------------------------------
# Encounters
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def active_encounter(db: Session, group_id: int) -> Optional[Encounter]:
    return (
        db.query(Encounter)
        .filter(Encounter.gaming_group_id == group_id, Encounter.status == "active")
        .order_by(Encounter.id.desc())
        .first()
    )


def touch(encounter: Encounter) -> None:
    """Something a viewer of the combat page should see has changed."""
    encounter.rev = (encounter.rev or 0) + 1


def start_encounter(db: Session, group_id: int, name: str = "", *, replace: bool = False) -> Encounter:
    """Start the group's fight. One at a time (D33): with a fight already
    running this refuses unless ``replace``, which ends that one first."""
    current = active_encounter(db, group_id)
    if current is not None:
        if not replace:
            raise EncounterConflict(current.name or "the current fight")
        end_encounter(db, current)
    encounter = Encounter(gaming_group_id=group_id, name=name.strip() or "Fight", status="active")
    db.add(encounter)
    db.flush()
    return encounter


def end_encounter(db: Session, encounter: Encounter) -> None:
    """End the fight; its NPCs stay in the group's roster (D8)."""
    encounter.status = "ended"
    encounter.ended_at = _now()
    touch(encounter)
    db.flush()


def link_for(encounter: Encounter, character_id: int) -> Optional[EncounterNpc]:
    return next((link for link in encounter.npcs if link.character_id == character_id), None)


def add_to_encounter(db: Session, encounter: Encounter, npc: Character) -> EncounterNpc:
    existing = link_for(encounter, npc.id)
    if existing is not None:
        return existing
    link = EncounterNpc(encounter_id=encounter.id, character_id=npc.id, status="fighting")
    encounter.npcs.append(link)
    touch(encounter)
    db.flush()
    return link


ORDER_SIDES = ("pcs", "npcs")


def in_standing_order(encounter: Optional[Encounter], side: str, items: Sequence[Any],
                      id_of: Callable[[Any], int] = lambda c: c.id) -> List[Any]:
    """``items`` in the order the GM dragged this side into; anyone not in
    it (joined since) keeps the default order, after the rest."""
    saved = ((encounter.standing_order or {}).get(side) or []) if encounter else []
    rank = {cid: i for i, cid in enumerate(saved)}
    return sorted(items, key=lambda c: rank.get(id_of(c), len(saved)))


def set_standing_order(db: Session, encounter: Encounter, side: str, ids: Any,
                       members: Sequence[int]) -> None:
    """Save one side's order. ``ids`` must be exactly that side's ``members``,
    each once - a PC never lands among the NPCs or the reverse."""
    if side not in ORDER_SIDES:
        raise ValueError("side must be pcs or npcs")
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ValueError("ids must be a list of character ids")
    if len(ids) != len(set(ids)) or set(ids) != set(members):
        raise ValueError("the order must name everyone on that side, once")
    encounter.standing_order = {**(encounter.standing_order or {}), side: ids}
    touch(encounter)
    db.flush()


def set_reach(db: Session, encounter: Encounter, pc_id: Any, npc_id: Any, on: bool,
              pcs: Sequence[int], npc_ids: Sequence[int]) -> None:
    """Mark (or clear) that a PC and an NPC in this fight can strike each
    other. Undirected, one PC and one NPC, each pair once."""
    if not (isinstance(pc_id, int) and pc_id in pcs and isinstance(npc_id, int) and npc_id in npc_ids):
        raise ValueError("a line joins a PC and an NPC in this fight")
    pair = [pc_id, npc_id]
    pairs = list(encounter.reach or [])
    if on and pair not in pairs:
        pairs.append(pair)
    elif not on:
        pairs = [p for p in pairs if p != pair]
    encounter.reach = pairs
    touch(encounter)
    db.flush()


def current_reach(encounter: Optional[Encounter], pcs: Sequence[int], npc_ids: Sequence[int]) -> List[List[int]]:
    """The pairs whose PC and NPC are both still in the fight."""
    if encounter is None:
        return []
    return [p for p in (encounter.reach or []) if p[0] in pcs and p[1] in npc_ids]


def set_status(db: Session, encounter: Encounter, npc: Character, status: str) -> EncounterNpc:
    if status not in NPC_STATUSES:
        raise ValueError(f"unknown status {status!r}")
    link = link_for(encounter, npc.id)
    if link is None:
        raise LookupError("that NPC is not in this fight")
    link.status = status
    touch(encounter)
    db.flush()
    return link


def remove_from_encounter(db: Session, encounter: Encounter, npc: Character) -> None:
    link = link_for(encounter, npc.id)
    if link is None:
        raise LookupError("that NPC is not in this fight")
    encounter.npcs.remove(link)
    touch(encounter)
    db.flush()


def generate(
    db: Session,
    group: GamingGroup,
    encounter: Encounter,
    owner_discord_id: str,
    rows: Sequence[Dict[str, Any]],
    *,
    rng: Optional[random.Random] = None,
    name_provider: Optional[NameProvider] = None,
) -> List[Character]:
    """Generate NPCs from builder rows and add them to the fight.

    Each row: ``npc_type``, ``count``, ``earned_xp`` (the base, or the exact
    value), ``roll_extra`` (D5/D13), ``combat_target`` (D6) and optional
    ``combat_share`` (a per-NPC override that replaces the draw) and
    ``names`` (the GM's own, used in order before any suggestions).
    Validates every row before creating anything.
    """
    rng = rng or random.SystemRandom()
    plans = [row if row.get("_planned") else _plan_row(row) for row in rows]
    if sum(p["count"] for p in plans) > MAX_NPCS_PER_REQUEST:
        raise ValueError(f"at most {MAX_NPCS_PER_REQUEST} NPCs at a time")
    created: List[Character] = []
    for plan in plans:
        names = list(plan["names"])
        missing = plan["count"] - len(names)
        if missing > 0 and name_provider is not None:
            names += [n for n in name_provider(missing, gen.is_peasant_type(plan["npc_type"])) if n][:missing]
        missing = plan["count"] - len(names)
        if missing > 0:
            names += fallback_names(db, group.id, gen.npc_type_label(plan["npc_type"]), missing)
        for i in range(plan["count"]):
            earned = plan["earned_xp"]
            if plan["roll_extra"]:
                earned += gen.roll_extra_xp(rng)[0]
            share = plan["combat_share"]
            if share is None:
                share = gen.draw_combat_share(plan["combat_target"], rng)
            build = gen.build_npc(plan["npc_type"], earned, share, traits=plan["traits"],
                                  recorded=plan["recorded"])
            npc = create_npc(db, group.id, owner_discord_id, build, names[i])
            add_to_encounter(db, encounter, npc)
            created.append(npc)
    return created


def _plan_row(row: Dict[str, Any]) -> Dict[str, Any]:
    npc_type = row.get("npc_type")
    if npc_type not in gen.npc_types():
        raise ValueError(f"unknown NPC type {npc_type!r}")
    count = _int(row.get("count", 1), "count")
    if not 1 <= count <= MAX_NPCS_PER_REQUEST:
        raise ValueError("count must be between 1 and 30")
    earned = _int(row.get("earned_xp", 0), "earned XP")
    if not 0 <= earned <= 2000:
        raise ValueError("earned XP must be between 0 and 2000")
    target = row.get("combat_target")
    target = gen.default_combat_share() if target in (None, "") else _share(target)
    override = row.get("combat_share")
    override = None if override in (None, "") else gen.clamp_combat_share(_share(override))
    names = [str(n).strip()[:80] for n in (row.get("names") or []) if str(n).strip()]
    traits = gen.normalize_traits(row.get("traits"))
    recorded = gen.normalize_recorded(row.get("recorded"))
    return {
        "_planned": True, "traits": traits, "recorded": recorded,
        "npc_type": npc_type, "count": count, "earned_xp": earned,
        "roll_extra": bool(row.get("roll_extra", True)),
        "combat_target": target, "combat_share": override, "names": names[:count],
    }


def _int(value: Any, what: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a whole number") from None


def _share(value: Any) -> float:
    """A combat share given as a fraction (0.74) or a percentage (74)."""
    try:
        share = float(value)
    except (TypeError, ValueError):
        raise ValueError("combat share must be a number") from None
    return share / 100 if share > 1 else share


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

def roster(db: Session, group_id: int) -> List[Character]:
    """Every NPC the group has fought, newest first."""
    return (
        db.query(Character)
        .filter(Character.is_npc.is_(True), Character.npc_group_id == group_id)
        .order_by(Character.id.desc())
        .all()
    )


def last_status(db: Session, npc: Character) -> str:
    """The NPC's status in the most recent fight it was in."""
    link = (
        db.query(EncounterNpc)
        .filter(EncounterNpc.character_id == npc.id)
        .order_by(EncounterNpc.id.desc())
        .first()
    )
    return link.status if link else "fighting"


def bring_back(
    db: Session, encounter: Encounter, npc: Character, *, gained_xp: int = 0,
    author_discord_id: Optional[str] = None,
) -> EncounterNpc:
    """A roster NPC joins this fight, healed and rested (D17), optionally
    having gained ``gained_xp`` earned XP since the last time (D8)."""
    if gained_xp < 0:
        raise ValueError("gained XP cannot be negative")
    if gained_xp:
        rebuild_npc(db, npc, earned_xp=(npc.earned_xp or 0) + gained_xp, author_discord_id=author_discord_id)
    rest(npc)
    return add_to_encounter(db, encounter, npc)


def delete_npc(db: Session, npc: Character) -> None:
    """Remove an NPC for good (explicit, from the roster)."""
    db.query(EncounterNpc).filter(EncounterNpc.character_id == npc.id).delete()
    db.query(EncounterAction).filter(EncounterAction.character_id == npc.id).delete()
    db.delete(npc)
    db.flush()
