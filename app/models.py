from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, String, event, func, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def award_deltas_for_diff(awards: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Strip the freeform ``source`` text from each award before diffing.

    The ``source`` is metadata that the player can edit without triggering a
    new version, so version comparisons must ignore it. Returns a normalized
    list of ``{id, type, rank_delta, recognition_delta}`` dicts in the
    original order. The ``type`` field distinguishes numeric rank/recognition
    awards from reputation awards and IS version-significant.
    """
    if not awards:
        return []
    return [
        {
            "id": a.get("id"),
            "type": a.get("type", "rank_recognition"),
            "rank_delta": a.get("rank_delta", 0),
            "recognition_delta": a.get("recognition_delta", 0),
        }
        for a in awards
    ]


def advantage_details_for_diff(
    details: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Strip the freeform ``text`` field from each per-advantage detail
    so a text-only edit (e.g. retyping the Good Reputation description)
    doesn't flip ``has_unpublished_changes`` or surface in revision
    history diffs. Structural choices on the same dict - ``skills`` for
    Fierce/Specialization - remain version-significant.

    The whole ``dark_secret`` entry is dropped: both the secret text and
    the GM-chosen knowing player are private metadata (see
    ``app/services/dark_secret.py``), never part of the versioned build.

    Entries that contain only a ``text`` value collapse to ``{}`` and are
    dropped entirely, so a player who first types a description and then
    blanks it back out doesn't leave behind a phantom empty key that
    would mismatch a fresh snapshot's missing-key default.
    """
    if not details:
        return {}
    stripped: Dict[str, Any] = {}
    for aid, raw in details.items():
        if aid == "dark_secret":
            continue
        if not isinstance(raw, dict):
            stripped[aid] = raw
            continue
        kept = {k: v for k, v in raw.items() if k != "text"}
        if kept:
            stripped[aid] = kept
    return stripped


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    discord_name: Mapped[str] = mapped_column(String, default="")
    display_name: Mapped[str] = mapped_column(String, default="")
    granted_account_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    # Per-user preferences as a free-form dict; e.g.
    #   {"dice_animation_enabled": bool, "dice_sound_enabled": bool}
    preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "discord_id": self.discord_id,
            "discord_name": self.discord_name,
            "display_name": self.display_name or self.discord_name,
            "granted_account_ids": self.granted_account_ids or [],
            "preferences": self.preferences or {},
        }


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    discord_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class GamingGroup(Base):
    """A real-world gaming group / session schedule (e.g. "Tuesday Group")."""

    __tablename__ = "gaming_groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name}


class CharacterVersion(Base):
    __tablename__ = "character_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # ``ForeignKey`` here is mostly documentation: SQLite ships with FK
    # enforcement off and we don't enable it, so the cascade is driven
    # at the ORM level via the ``versions`` relationship on Character.
    # Existing prod tables don't carry the constraint either (``create_all``
    # is a no-op on tables that already exist).
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(String, default="")
    author_discord_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


#: Free-form metadata fields. Edits to these do NOT flip the character
#: into "unpublished changes" state, do NOT appear in revision-history
#: diffs / Discard-Changes preview, and are NOT reverted by Discard /
#: Revert. They live on the row but sit outside the version system.
#:
#: ``sections`` (rich-text Notes/Backstory/Allies blocks) and the legacy
#: single-textarea ``notes`` field are freeform prose with no mechanical
#: effect on the character, so they follow the same contract as name/age -
#: the player can rewrite their backstory at any time without it counting
#: as a build change.
METADATA_FIELDS = frozenset({
    "name",
    "name_explanation",
    "player_name",
    "age",
    "lineage",
    "sections",
    "notes",
})


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Free-form text explaining the meaning of the character's name, and
    # the in-character reason they chose it at their adult-name ceremony.
    # Displayed as a tooltip on the character sheet.
    name_explanation: Mapped[str] = mapped_column(String, default="")
    player_name: Mapped[str] = mapped_column(String, default="")
    # Optional metadata. Surfaces in the editor and on the View Sheet,
    # but is intentionally NOT a stat: changes don't flip the character
    # into "unpublished changes" state, don't appear in revision-history
    # diffs, and Discard / Revert don't touch it.
    age: Mapped[Optional[int]] = mapped_column(default=None, nullable=True)
    # Wasp lineage: "Tsuruchi", "Kyoma", "Ami", or a free-form string the
    # player typed via the "Other" dropdown option. Same metadata
    # contract as ``age``. Validator flags it as unset when blank.
    lineage: Mapped[str] = mapped_column(String, default="")
    owner_discord_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    editor_discord_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)

    # Draft/publish state
    is_published: Mapped[bool] = mapped_column(default=False)
    published_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=None)
    # Visibility gate for in-progress drafts. When True, only editors (owner,
    # admins, account-grantees) can see the character anywhere. Set to True
    # when a character is created via POST /characters; cleared one-way by
    # the first Apply Changes or by the explicit "Make Draft Visible" button.
    is_hidden: Mapped[bool] = mapped_column(default=False)
    school: Mapped[str] = mapped_column(String, default="")
    school_ring_choice: Mapped[str] = mapped_column(String, default="")
    # Profession taken INSTEAD of a school (see profession-design/design.md).
    # Mutually exclusive with `school`: setting one clears the other. A
    # profession character has no School Ring, no school knacks and no Dan,
    # but may still buy foreign school knacks.
    profession: Mapped[str] = mapped_column(String, default="")
    # Profession abilities as an id -> count map, NOT a list of ids: an
    # ability may be taken more than once (twice for every profession
    # except Priest, whose rituals are once-only) and a second copy applies
    # the effect a second time. Same shape as `knacks` / `skills`.
    profession_abilities: Mapped[Optional[Dict[str, int]]] = mapped_column(
        JSON, default=dict
    )

    # Rings stored as individual columns for easy querying
    ring_air: Mapped[int] = mapped_column(default=2)
    ring_fire: Mapped[int] = mapped_column(default=2)
    ring_earth: Mapped[int] = mapped_column(default=2)
    ring_water: Mapped[int] = mapped_column(default=2)
    ring_void: Mapped[int] = mapped_column(default=2)

    # Combat skills
    attack: Mapped[int] = mapped_column(default=1)
    parry: Mapped[int] = mapped_column(default=1)

    # Variable collections as JSON
    skills: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, default=dict)
    knacks: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, default=dict)
    # Non-supernatural school knacks purchased from OTHER schools. The 0->1
    # raise costs a flat 10 XP premium; rank 2..5 cost the normal 2 * new_rank.
    # Stored separately from `knacks` so that compute_dan() and the
    # "school knacks must match the school" validator stay correct.
    foreign_knacks: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, default=dict)
    advantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    disadvantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    campaign_advantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    campaign_disadvantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    # Extra details for advantages/disadvantages that need text or skill selections
    # Format: {"advantage_id": {"text": "...", "skills": ["skill_id", ...], "player": "discord_id"}}
    advantage_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        # active_history: the build revision compares old and new with the
        # dark secret left out, so it needs the old value even when expired.
        JSON, default=dict, active_history=True
    )
    # Specializations are the only advantage that can be taken multiple times,
    # so they live in their own list (rather than a duplicate-allowed entry in
    # `advantages`). Each entry: {"text": "<sub-domain>", "skills": ["<skill_id>"]}.
    # Costs 2 XP per entry; gives a +10 conditional alternative on the named skill.
    specializations: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, default=list)

    # Player-chosen technique selections (for schools with flexible 1st/2nd Dan)
    # Format: {"first_dan_choices": ["skill_id", ...], "second_dan_choice": "skill_id"}
    technique_choices: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

    # Honor / Rank / Recognition
    honor: Mapped[float] = mapped_column(Float, default=1.0)
    rank: Mapped[float] = mapped_column(Float, default=7.5)
    rank_locked: Mapped[bool] = mapped_column(default=True)
    recognition: Mapped[float] = mapped_column(Float, default=7.5)
    recognition_halved: Mapped[bool] = mapped_column(default=False)

    # GM-awarded Rank / Recognition bonuses earned during play. Each entry:
    #   {"id": str, "rank_delta": float, "recognition_delta": float,
    #    "source": str, "created_at": str (ISO timestamp)}
    # The deltas are versioned (changing them triggers a draft + must be
    # Applied), but the freeform ``source`` text is metadata and may be edited
    # without creating a new version — see ``award_deltas_for_diff``.
    rank_recognition_awards: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, default=list
    )

    # XP tracking
    starting_xp: Mapped[int] = mapped_column(default=150)
    earned_xp: Mapped[int] = mapped_column(default=0)
    # Player Character Points: the number of times this character has spent a
    # PCP. Versioned build state (each spend immediately publishes a new
    # version; undoing a spend is a discardable draft change). The escalating
    # XP cost of N spends is the Nth triangular number, N*(N+1)//2 - see
    # services/xp.pcp_total_cost. See rules/10-player_character_points.md.
    pcp_count: Mapped[int] = mapped_column(default=0)

    # Combat tracking (mutable session state). ``active_history`` on every
    # column in TRACKING_COLUMNS makes SQLAlchemy load the old value when a
    # new one is assigned, so ``_bump_revisions`` can tell a real change
    # from a whole-state save that re-sent what was already there.
    current_light_wounds: Mapped[int] = mapped_column(default=0, active_history=True)
    current_serious_wounds: Mapped[int] = mapped_column(default=0, active_history=True)
    current_void_points: Mapped[int] = mapped_column(default=0, active_history=True)
    current_temp_void_points: Mapped[int] = mapped_column(default=0, active_history=True)
    # Night's Rest healing-cadence flags. Updated by the /track endpoint
    # whenever SW changes, and by the Night's Rest endpoint. Excluded from
    # the version diff (live session state, not part of the character build).
    # received_new_since_rest fires the Quick Healer bonus on the next rest;
    # became_injured_since_rest fires the Slow Healer suppression but ONLY on
    # the 0->positive transition (not subsequent SW increases mid-cadence);
    # last_rest_was_healing_night drives the 1/0/1/0 alternating cadence.
    # All three are cleared when SW returns to 0.
    sw_healing_received_new_since_rest: Mapped[bool] = mapped_column(default=False)
    sw_healing_became_injured_since_rest: Mapped[bool] = mapped_column(default=False)
    sw_healing_last_rest_was_healing_night: Mapped[bool] = mapped_column(default=False)
    # Per-adventure state: {"lucky_used": false, "unlucky_used": false,
    #   "adventure_raises_used": 0, "conviction_used": 0, ...}
    adventure_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=dict, active_history=True
    )
    # Current combat round action dice. Populated when the player rolls
    # initiative and cleared by the Clear button. Each entry is
    # {"value": int (0-10), "spent": bool}.
    action_dice: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, default=list, active_history=True
    )
    # Priest 3rd Dan precepts dice pool. Persists across combat rounds (so
    # it is NOT cleared by action-dice Clear or by rolling initiative) but
    # IS cleared by the per-adventure reset. Each entry is {"value": int (1-10)}.
    precepts_pool: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, default=list, active_history=True
    )
    # Money ledger: user-added income / expense entries the player keeps
    # for tracking koku across the campaign. The initial Spring equinox
    # disbursal (25% of stipend, ceiling) is NOT stored here - it's
    # computed dynamically from ``effective.stipend`` at render time so
    # it always reflects the current stipend. Each entry is
    # ``{"id": str, "kind": "income"|"expense", "label": str,
    # "amount": int}``. Lives outside the version system - editing the
    # ledger never flips the character into Draft state.
    money_ledger: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, default=list)
    # Optimistic-concurrency token for the live tracking state above (see
    # ``TRACKING_COLUMNS``). Bumped automatically whenever any of those
    # columns changes, by ``_bump_revisions`` below - never by hand - so a
    # writer that loaded the sheet at revision N and saves after someone else
    # moved it to N+1 is refused instead of silently overwriting them.
    tracking_rev: Mapped[int] = mapped_column(default=0)
    # The same, for the BUILD (see ``BUILD_COLUMNS``): the editor holds a copy
    # of the whole build and autosaves all of it. Deliberately a SEPARATE
    # counter - a wound taken on the sheet cannot conflict with an editor
    # tab, so it must not make one stale, and vice versa.
    build_rev: Mapped[int] = mapped_column(default=0)

    # Metadata
    notes: Mapped[str] = mapped_column(String, default="")
    # Rich-text "sections": user-labelled blocks of sanitized HTML.
    # Replaces the legacy single Notes textarea. Each entry is
    # ``{"label": str, "html": str}`` with HTML pre-sanitised on the server.
    sections: Mapped[Optional[List[Dict[str, str]]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Google Sheets export: stores the spreadsheet ID of the most recent export
    # so future exports can update in place instead of creating a new sheet.
    # google_sheet_exported_state stores a to_dict() snapshot at export time
    # so we can detect whether the character has changed since the last export.
    google_sheet_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    google_sheet_exported_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=None
    )

    # Gaming group assignment. Real-world session metadata, NOT versioned.
    # Deliberately excluded from to_dict() so it never enters published_state
    # snapshots, version diffs, or the "modified" badge.
    gaming_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("gaming_groups.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Character art. Metadata only - NOT versioned. Deliberately excluded
    # from to_dict() so changing art never flips the character into Draft
    # status. Writes go directly to this row via the dedicated art endpoints.
    art_s3_key: Mapped[Optional[str]] = mapped_column(String, default=None)
    headshot_s3_key: Mapped[Optional[str]] = mapped_column(String, default=None)
    art_updated_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    art_source: Mapped[Optional[str]] = mapped_column(String, default=None)
    art_prompt: Mapped[Optional[str]] = mapped_column(String, default=None)

    # Drives ORM cascade on delete: db.delete(character) takes the
    # CharacterVersion rows with it. Without this, deleting a character
    # leaves orphan revisions behind, and SQLite reuses the freed id
    # on the next insert so the new character starts life with the
    # deleted one's revision history hanging off it.
    versions: Mapped[List["CharacterVersion"]] = relationship(
        "CharacterVersion",
        cascade="all, delete-orphan",
        passive_deletes=False,
    )

    # Roll history: one row per dice roll made on this character's sheet.
    # Cascade-on-delete so deleting the character removes its rolls too
    # (mirrors the CharacterVersion relationship). See RollHistory below.
    roll_history: Mapped[List["RollHistory"]] = relationship(
        "RollHistory",
        cascade="all, delete-orphan",
        passive_deletes=False,
    )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def rings(self) -> Dict[str, int]:
        """Return ring values keyed by display name."""
        return {
            "Air": self.ring_air,
            "Fire": self.ring_fire,
            "Earth": self.ring_earth,
            "Water": self.ring_water,
            "Void": self.ring_void,
        }

    @property
    def has_unpublished_changes(self) -> bool:
        """True when the current draft differs from the published snapshot."""
        if not self.is_published or self.published_state is None:
            return False
        current = self.to_dict()
        # Skip metadata fields; compare only game-relevant content. Session
        # state (wounds, void, action dice, precepts pool) is mutated by
        # /track every time the player takes damage, rolls dice, or spends
        # void; it must not flip the character to "modified". Same for
        # google_sheet_id, which is stamped by the Sheets export and is
        # pure metadata.
        skip = {"id", "created_at", "updated_at", "owner_discord_id",
                "editor_discord_ids",
                "current_light_wounds", "current_serious_wounds",
                "current_void_points", "current_temp_void_points",
                "action_dice", "precepts_pool", "money_ledger",
                "sw_healing_received_new_since_rest",
                "sw_healing_became_injured_since_rest",
                "sw_healing_last_rest_was_healing_night",
                "google_sheet_id"} | METADATA_FIELDS
        # Default values for keys that may be absent from older
        # snapshots. Without an entry here, ``published_state.get(key,
        # None)`` returns None for keys that didn't exist when the
        # character was last published, ``cur_val`` is the new column's
        # "empty" value (``[]`` / ``{}`` / ``False``), and the
        # mismatch silently flips the character into "Draft changes"
        # state with no real edit. Every list/dict/bool field that
        # ``to_dict`` returns through an ``or`` fallback needs a
        # default of the same shape here.
        # ``test_snapshot_missing_any_empty_valued_key_does_not_flip``
        # fails if a key is missing here. ``profession`` /
        # ``profession_abilities`` were once missing, and every character
        # published before professions shipped showed "Draft changes".
        defaults = {"campaign_advantages": [], "campaign_disadvantages": [],
                    "advantage_details": {},
                    "school_ring_choice": "", "skills": {}, "knacks": {},
                    "advantages": [], "disadvantages": [], "earned_xp": 0,
                    "profession": "", "profession_abilities": {},
                    "attack": 1, "parry": 1, "rank_locked": False,
                    "current_light_wounds": 0, "current_serious_wounds": 0,
                    "current_void_points": 0, "current_temp_void_points": 0,
                    "action_dice": [], "precepts_pool": [], "money_ledger": [],
                    "sw_healing_received_new_since_rest": False,
                    "sw_healing_became_injured_since_rest": False,
                    "sw_healing_last_rest_was_healing_night": False,
                    "notes": "", "sections": [],
                    "rank_recognition_awards": [],
                    "specializations": [], "technique_choices": {},
                    "foreign_knacks": {}, "recognition_halved": False,
                    "pcp_count": 0}
        for key in current:
            if key in skip:
                continue
            cur_val = current[key]
            pub_val = self.published_state.get(key, defaults.get(key))
            # Awards: the freeform ``source`` text is metadata, so an
            # edit-source-only change must NOT trigger a draft. Compare
            # only the deltas + ids.
            if key == "rank_recognition_awards":
                if award_deltas_for_diff(cur_val) != award_deltas_for_diff(pub_val):
                    return True
                continue
            # Advantage detail ``text`` is metadata for the same reason
            # an award ``source`` is - it's a freeform description, not
            # a stat. Strip it before comparing so retyping the Good
            # Reputation text doesn't flip the character to Draft.
            if key == "advantage_details":
                if (
                    advantage_details_for_diff(cur_val)
                    != advantage_details_for_diff(pub_val)
                ):
                    return True
                continue
            if cur_val != pub_val:
                return True
        return False

    @property
    def google_sheet_is_stale(self) -> bool:
        """True when the character has changed since the last Google Sheets export."""
        if not self.google_sheet_id or self.google_sheet_exported_state is None:
            return True
        current = self.to_dict()
        exported = self.google_sheet_exported_state
        skip = {"id", "created_at", "updated_at", "owner_discord_id",
                "editor_discord_ids", "google_sheet_id"}
        for key in current:
            if key in skip:
                continue
            if key == "advantage_details":
                # The dark secret is private metadata that the export
                # may have omitted (non-owner exporter) or that the
                # owner may have retyped since - neither makes the
                # exported sheet stale.
                from app.services.dark_secret import strip_dark_secret
                if strip_dark_secret(current[key]) != strip_dark_secret(exported.get(key)):
                    return True
                continue
            if current[key] != exported.get(key):
                return True
        return False

    @property
    def publish_status(self) -> str:
        """Return 'unpublished', 'published', or 'modified'."""
        if not self.is_published:
            return "unpublished"
        if self.has_unpublished_changes:
            return "modified"
        return "published"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict matching the shape expected by the XP engine.

        The returned dict is suitable for ``calculate_total_xp`` in
        ``xp.py`` — flat ring values, JSON collections, and scalar
        tracking fields.
        """
        return {
            "id": self.id,
            "name": self.name,
            "name_explanation": self.name_explanation or "",
            "player_name": self.player_name,
            "age": self.age,
            "lineage": self.lineage or "",
            "owner_discord_id": self.owner_discord_id,
            "editor_discord_ids": self.editor_discord_ids or [],
            "school": self.school,
            "school_ring_choice": self.school_ring_choice,
            "profession": self.profession or "",
            "profession_abilities": self.profession_abilities or {},
            "rings": self.rings,
            "attack": self.attack,
            "parry": self.parry,
            "skills": self.skills or {},
            "knacks": self.knacks or {},
            "foreign_knacks": self.foreign_knacks or {},
            "advantages": self.advantages or [],
            "disadvantages": self.disadvantages or [],
            "campaign_advantages": self.campaign_advantages or [],
            "campaign_disadvantages": self.campaign_disadvantages or [],
            "advantage_details": self.advantage_details or {},
            "specializations": self.specializations or [],
            "technique_choices": self.technique_choices or {},
            "honor": self.honor,
            "rank": self.rank,
            "rank_locked": self.rank_locked,
            "recognition": self.recognition,
            "recognition_halved": self.recognition_halved,
            "rank_recognition_awards": self.rank_recognition_awards or [],
            "starting_xp": self.starting_xp,
            "earned_xp": self.earned_xp,
            "pcp_count": self.pcp_count or 0,
            "current_light_wounds": self.current_light_wounds,
            "current_serious_wounds": self.current_serious_wounds,
            "current_void_points": self.current_void_points,
            "current_temp_void_points": self.current_temp_void_points,
            "action_dice": self.action_dice or [],
            "precepts_pool": self.precepts_pool or [],
            "money_ledger": self.money_ledger or [],
            "notes": self.notes,
            "sections": self.sections or [],
            "google_sheet_id": self.google_sheet_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        """Create a Character instance from form / import data.

        Accepts either a flat ``rings`` dict or individual ``ring_*``
        keys.  JSON collection fields fall back to empty containers.

        Performs the legacy-shape lift for Specialization: pre-multi-spec
        characters carried ``advantages=[..., "specialization", ...]`` and
        ``advantage_details["specialization"] = {text, skills}``. Lift the
        detail into ``specializations[0]`` and strip the flag so the rest
        of the system sees only the new shape.
        """
        rings = data.get("rings", {})

        # --- Lazy migration: legacy single-Specialization → list shape ---
        advantages = list(data.get("advantages", []) or [])
        advantage_details = dict(data.get("advantage_details", {}) or {})
        specializations = list(data.get("specializations", []) or [])
        if "specialization" in advantages:
            if not specializations:
                legacy = advantage_details.get("specialization")
                if legacy:
                    specializations = [{
                        "text": legacy.get("text", ""),
                        "skills": list(legacy.get("skills") or []),
                    }]
            advantages = [a for a in advantages if a != "specialization"]
            advantage_details.pop("specialization", None)

        return cls(
            name=data.get("name", ""),
            name_explanation=data.get("name_explanation", ""),
            player_name=data.get("player_name", ""),
            age=data.get("age"),
            lineage=(data.get("lineage") or ""),
            school=data.get("school", ""),
            school_ring_choice=data.get("school_ring_choice", ""),
            ring_air=rings.get("Air", data.get("ring_air", 2)),
            ring_fire=rings.get("Fire", data.get("ring_fire", 2)),
            ring_earth=rings.get("Earth", data.get("ring_earth", 2)),
            ring_water=rings.get("Water", data.get("ring_water", 2)),
            ring_void=rings.get("Void", data.get("ring_void", 2)),
            attack=data.get("attack", 1),
            parry=data.get("parry", 1),
            skills=data.get("skills", {}),
            knacks=data.get("knacks", {}),
            foreign_knacks=data.get("foreign_knacks", {}),
            advantages=advantages,
            disadvantages=data.get("disadvantages", []),
            campaign_advantages=data.get("campaign_advantages", []),
            campaign_disadvantages=data.get("campaign_disadvantages", []),
            advantage_details=advantage_details,
            specializations=specializations,
            honor=data.get("honor", 1.0),
            rank=data.get("rank", 1.0),
            rank_locked=data.get("rank_locked", False),
            recognition=data.get("recognition", 1.0),
            recognition_halved=data.get("recognition_halved", False),
            rank_recognition_awards=data.get("rank_recognition_awards", []),
            starting_xp=data.get("starting_xp", 150),
            earned_xp=data.get("earned_xp", 0),
            pcp_count=data.get("pcp_count", 0),
            current_light_wounds=data.get("current_light_wounds", 0),
            current_serious_wounds=data.get("current_serious_wounds", 0),
            current_void_points=data.get("current_void_points", 0),
            current_temp_void_points=data.get("current_temp_void_points", 0),
            notes=data.get("notes", ""),
            technique_choices=data.get("technique_choices", {}),
        )


#: The live session state a sheet tab holds a whole copy of and writes back.
#: A change to ANY of these moves ``Character.tracking_rev``.
TRACKING_COLUMNS = (
    "current_light_wounds",
    "current_serious_wounds",
    "current_void_points",
    "current_temp_void_points",
    "adventure_state",
    "action_dice",
    "precepts_pool",
)
# ``money_ledger`` is deliberately NOT here. No tab ever posts the ledger
# whole: its routes add / edit / delete ONE entry by id, server-side, so two
# writers compose instead of overwriting each other. Putting it under the
# revision would only make every koku entry turn the player's next wound or
# void save into a false "changed somewhere else".


#: The character BUILD: everything an editor tab holds a copy of and
#: autosaves whole. A change to any of these moves ``Character.build_rev``.
#: ``tests/test_build_rev.py`` fails if POST /autosave starts writing a
#: column that is not listed here.
BUILD_COLUMNS = (
    "name", "name_explanation", "player_name", "age", "lineage",
    "owner_discord_id",
    "school", "school_ring_choice", "profession", "profession_abilities",
    "ring_air", "ring_fire", "ring_earth", "ring_water", "ring_void",
    "attack", "parry", "skills", "knacks", "foreign_knacks",
    "advantages", "disadvantages", "campaign_advantages",
    "campaign_disadvantages", "advantage_details", "specializations",
    "technique_choices",
    "honor", "rank", "rank_locked", "recognition", "recognition_halved",
    "rank_recognition_awards",
    "starting_xp", "earned_xp", "pcp_count",
    "notes", "sections",
)


def _without_dark_secret(details: Any) -> Any:
    """``advantage_details`` as far as the build revision is concerned.

    The dark secret is written only through POST /dark-secret, and autosave
    always carries the persisted entry forward (``merge_dark_secret``), so a
    stale autosave cannot lose it. Leaving it out here means the GM setting a
    secret does not throw a "changed elsewhere" prompt at the player's open
    editor - over a field that editor cannot even see.
    """
    if not isinstance(details, dict):
        return details
    return {k: v for k, v in details.items() if k != "dark_secret"}


def _changed(state, name: str) -> bool:
    """Whether column ``name`` is being written with a DIFFERENT value.

    ``history.deleted`` is empty when the old value was never loaded (an
    expired attribute); that counts as changed, which is the safe direction.
    Tracking columns set ``active_history`` so they always have it; build
    columns are only ever written on a freshly loaded row.
    """
    history = state.attrs[name].history
    if not history.added:
        return False
    added, deleted = list(history.added), list(history.deleted)
    if name == "advantage_details":
        added = [_without_dark_secret(v) for v in added]
        deleted = [_without_dark_secret(v) for v in deleted]
    return added != deleted


@event.listens_for(Character, "before_update")
def _bump_revisions(mapper, connection, character) -> None:
    """Move ``tracking_rev`` / ``build_rev`` when their columns are written.

    Hooked at the ORM layer rather than called from each route ON PURPOSE:
    the writers are many (POST /track, Night's Rest, the PCP void refresh,
    a party member spending a priest's conviction, the Discord roll
    commands; autosave, discard, revert, a PCP spend, the award-source
    endpoint, whatever comes next) and a bump somebody has to remember is a
    bump somebody forgets. Here, a new writer participates by existing.
    Only fires when a value actually changed, so a save that re-sends what
    was already there does not make every other open tab stale.
    """
    state = inspect(character)
    if any(_changed(state, name) for name in TRACKING_COLUMNS):
        character.tracking_rev = (character.tracking_rev or 0) + 1
    if any(_changed(state, name) for name in BUILD_COLUMNS):
        character.build_rev = (character.build_rev or 0) + 1


class RollHistory(Base):
    """One row per dice roll made on a character's sheet.

    Created when a roll's result modal first opens (POST /characters/{id}/rolls),
    updated in place as the player toggles post-roll discretionary bonuses
    (PATCH /characters/{id}/rolls/{roll_id}). Recording is owner-only with the
    GM/admin blanket exclusion described in app/services/rolls_history.py;
    viewing and editing (annotation, hide/unhide) is open to any editor.

    Schema note: a brand-new table is created on first startup by
    Base.metadata.create_all in init_db(). The _migrate_add_columns helper
    only handles new columns on EXISTING tables; new tables need no entry there.
    """

    __tablename__ = "roll_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True,
    )
    # Canonical roll key from build_all_roll_formulas (e.g. "skill:bragging",
    # "knack:iaijutsu", "attack", "parry", "wound_check", "initiative",
    # "initiative:athletics", "ring:Fire") or a synthesized key for the
    # special rollers ("bless", "freeform", "spend_vp_xk1").
    roll_key: Mapped[str] = mapped_column(String, nullable=False)
    # NOTE: the display label is NOT stored. It is derived at read time from
    # payload.title (see app/services/roll_descriptions.label_for_roll), which
    # every roll records. The old roll_label column was dropped (database.py
    # migration) to avoid duplicating the label in two places.
    # Discord id of whoever clicked the roll button. The server gates
    # recording, so this will always be either the owner or a non-admin
    # editor of the character.
    actor_discord_id: Mapped[str] = mapped_column(String, nullable=False)
    # True iff actor_discord_id was the character's owner at record time.
    # Stored (not computed) so a later owner change doesn't reclassify history.
    is_owner_roll: Mapped[bool] = mapped_column(default=False)
    impaired_at_roll: Mapped[bool] = mapped_column(default=False)
    # Known TN at roll time. NULL when the roll has no auto-derivable TN
    # (skill rolls, initiative, contested rolls before the opposing roll
    # lands, parry rolls).
    tn: Mapped[Optional[int]] = mapped_column(default=None, nullable=True)
    # Full roll-results modal payload. Superset of _buildRollImagePayload()'s
    # output: title, formula, kept, dropped, bonuses, alternatives, total,
    # footer, show_total, action_dice. The dice-card renderer reads from
    # this shape directly so the readonly modal needs no transformation.
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    # Which action die was spent for this roll, if any. None when the roll
    # didn't consume one (e.g. initiative itself).
    action_die_spent: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=None, nullable=True,
    )
    # Player-toggleable hide flag, plus a freeform annotation. Both are
    # writeable by any editor regardless of who originally rolled.
    is_hidden: Mapped[bool] = mapped_column(default=False)
    annotation: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        # Newest-first within a character is the canonical list query.
        Index("ix_roll_history_char_created", "character_id", "created_at"),
    )


class Conversation(Base):
    """The conversation the GM currently has open with one gaming group.

    Written only by the GM's ``gm-assistant`` REPL through ``/api/conversation``
    and read by the ``/discern-honor`` slash command (see
    ``app/services/conversations.py``). At most one row per gaming group:
    opening a conversation under a new id replaces the group's previous one.

    ``npc_ref`` is an opaque string the REPL uses to recognize its own
    conversation after a crash. It is not a name, and it is never shown to a
    player. Timestamps are naive UTC, like every other datetime here.

    Schema note: a brand-new table, so ``create_all`` makes it on first
    startup and ``_migrate_add_columns`` needs no entry.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    gaming_group_id: Mapped[int] = mapped_column(
        ForeignKey("gaming_groups.id"), nullable=False, unique=True,
    )
    npc_ref: Mapped[str] = mapped_column(String, default="")
    opened_at: Mapped[datetime] = mapped_column(nullable=False)

    entries: Mapped[List["ConversationDiscernHonor"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="ConversationDiscernHonor.id",
    )


class ConversationDiscernHonor(Base):
    """What one character is told when they use Discern Honor in a conversation.

    ``told`` is the number the GM's tooling computed and the ONLY Honor-related
    value this app ever holds - never a true Honor. Nothing does arithmetic
    on it, and it is kept as its JSON literal in a TEXT column so it comes
    back exactly as it was sent: a column declared JSON has NUMERIC affinity
    in SQLite, which quietly turns a bare ``3.0`` into ``3``. ``asked_at`` is set by the first ``/discern-honor`` and never moves
    again, which is how the REPL learns which characters actually asked.
    """

    __tablename__ = "conversation_discern_honor"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), nullable=False,
    )
    told_json: Mapped[str] = mapped_column("told", String, nullable=False)
    asked_at: Mapped[Optional[datetime]] = mapped_column(default=None, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="entries")

    @property
    def told(self) -> Any:
        return json.loads(self.told_json)

    @told.setter
    def told(self, value: Any) -> None:
        self.told_json = json.dumps(value)
