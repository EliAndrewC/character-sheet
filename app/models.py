from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, String, func
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
    Fierce/Specialization, ``player`` for Dark Secret - remain
    version-significant.

    Entries that contain only a ``text`` value collapse to ``{}`` and are
    dropped entirely, so a player who first types a description and then
    blanks it back out doesn't leave behind a phantom empty key that
    would mismatch a fresh snapshot's missing-key default.
    """
    if not details:
        return {}
    stripped: Dict[str, Any] = {}
    for aid, raw in details.items():
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
    advantage_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
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

    # Combat tracking (mutable session state)
    current_light_wounds: Mapped[int] = mapped_column(default=0)
    current_serious_wounds: Mapped[int] = mapped_column(default=0)
    current_void_points: Mapped[int] = mapped_column(default=0)
    current_temp_void_points: Mapped[int] = mapped_column(default=0)
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
    adventure_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    # Current combat round action dice. Populated when the player rolls
    # initiative and cleared by the Clear button. Each entry is
    # {"value": int (0-10), "spent": bool}.
    action_dice: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, default=list)
    # Priest 3rd Dan precepts dice pool. Persists across combat rounds (so
    # it is NOT cleared by action-dice Clear or by rolling initiative) but
    # IS cleared by the per-adventure reset. Each entry is {"value": int (1-10)}.
    precepts_pool: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, default=list)
    # Money ledger: user-added income / expense entries the player keeps
    # for tracking koku across the campaign. The initial Spring equinox
    # disbursal (25% of stipend, ceiling) is NOT stored here - it's
    # computed dynamically from ``effective.stipend`` at render time so
    # it always reflects the current stipend. Each entry is
    # ``{"id": str, "kind": "income"|"expense", "label": str,
    # "amount": int}``. Lives outside the version system - editing the
    # ledger never flips the character into Draft state.
    money_ledger: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, default=list)

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
        defaults = {"campaign_advantages": [], "campaign_disadvantages": [],
                    "advantage_details": {},
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
                    "foreign_knacks": {}, "recognition_halved": False}
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
            current_light_wounds=data.get("current_light_wounds", 0),
            current_serious_wounds=data.get("current_serious_wounds", 0),
            current_void_points=data.get("current_void_points", 0),
            current_temp_void_points=data.get("current_temp_void_points", 0),
            notes=data.get("notes", ""),
            technique_choices=data.get("technique_choices", {}),
        )


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
    # Display label snapshotted at roll time so the list page doesn't have
    # to redo the formula lookup or know about every roll-key suffix.
    roll_label: Mapped[str] = mapped_column(String, default="")
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
