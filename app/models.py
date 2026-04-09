from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def award_deltas_for_diff(awards: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Strip the freeform ``source`` text from each award before diffing.

    The ``source`` is metadata that the player can edit without triggering a
    new version, so version comparisons must ignore it. Returns a normalized
    list of ``{id, rank_delta, recognition_delta}`` dicts in the original
    order.
    """
    if not awards:
        return []
    return [
        {
            "id": a.get("id"),
            "rank_delta": a.get("rank_delta", 0),
            "recognition_delta": a.get("recognition_delta", 0),
        }
        for a in awards
    ]


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
    character_id: Mapped[int] = mapped_column(nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(nullable=False)
    state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(String, default="")
    author_discord_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    player_name: Mapped[str] = mapped_column(String, default="")
    owner_discord_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    editor_discord_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)

    # Draft/publish state
    is_published: Mapped[bool] = mapped_column(default=False)
    published_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=None)
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
    advantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    disadvantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    campaign_advantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    campaign_disadvantages: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    # Extra details for advantages/disadvantages that need text or skill selections
    # Format: {"advantage_id": {"text": "...", "skills": ["skill_id", ...], "player": "discord_id"}}
    advantage_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

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
    # Per-adventure state: {"lucky_used": false, "unlucky_used": false,
    #   "adventure_raises_used": 0, "conviction_used": 0, ...}
    adventure_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

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

    # Gaming group assignment. Real-world session metadata, NOT versioned.
    # Deliberately excluded from to_dict() so it never enters published_state
    # snapshots, version diffs, or the "modified" badge.
    gaming_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("gaming_groups.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
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
        # Skip metadata fields; compare only game-relevant content
        skip = {"id", "created_at", "updated_at", "owner_discord_id", "editor_discord_ids"}
        # Default values for keys that may be absent from older snapshots
        defaults = {"campaign_advantages": [], "campaign_disadvantages": [],
                    "advantage_details": {},
                    "attack": 1, "parry": 1, "rank_locked": False,
                    "current_light_wounds": 0, "current_serious_wounds": 0,
                    "current_void_points": 0, "notes": "", "sections": [],
                    "rank_recognition_awards": []}
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
            if cur_val != pub_val:
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
            "player_name": self.player_name,
            "owner_discord_id": self.owner_discord_id,
            "editor_discord_ids": self.editor_discord_ids or [],
            "school": self.school,
            "school_ring_choice": self.school_ring_choice,
            "rings": self.rings,
            "attack": self.attack,
            "parry": self.parry,
            "skills": self.skills or {},
            "knacks": self.knacks or {},
            "advantages": self.advantages or [],
            "disadvantages": self.disadvantages or [],
            "campaign_advantages": self.campaign_advantages or [],
            "campaign_disadvantages": self.campaign_disadvantages or [],
            "advantage_details": self.advantage_details or {},
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
            "notes": self.notes,
            "sections": self.sections or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        """Create a Character instance from form / import data.

        Accepts either a flat ``rings`` dict or individual ``ring_*``
        keys.  JSON collection fields fall back to empty containers.
        """
        rings = data.get("rings", {})

        return cls(
            name=data.get("name", ""),
            player_name=data.get("player_name", ""),
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
            advantages=data.get("advantages", []),
            disadvantages=data.get("disadvantages", []),
            campaign_advantages=data.get("campaign_advantages", []),
            campaign_disadvantages=data.get("campaign_disadvantages", []),
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
            notes=data.get("notes", ""),
        )
