from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    discord_name: Mapped[str] = mapped_column(String, default="")
    display_name: Mapped[str] = mapped_column(String, default="")
    granted_account_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "discord_id": self.discord_id,
            "discord_name": self.discord_name,
            "display_name": self.display_name or self.discord_name,
            "granted_account_ids": self.granted_account_ids or [],
        }


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    discord_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CharacterVersion(Base):
    __tablename__ = "character_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(nullable=False)
    state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(String, default="")
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

    # Honor / Rank / Recognition
    honor: Mapped[float] = mapped_column(Float, default=1.0)
    rank: Mapped[float] = mapped_column(Float, default=1.0)
    rank_locked: Mapped[bool] = mapped_column(default=False)
    recognition: Mapped[float] = mapped_column(Float, default=1.0)
    recognition_halved: Mapped[bool] = mapped_column(default=False)

    # XP tracking
    starting_xp: Mapped[int] = mapped_column(default=150)
    earned_xp: Mapped[int] = mapped_column(default=0)

    # Combat tracking (mutable session state)
    current_light_wounds: Mapped[int] = mapped_column(default=0)
    current_serious_wounds: Mapped[int] = mapped_column(default=0)
    current_void_points: Mapped[int] = mapped_column(default=0)

    # Metadata
    notes: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
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
            "honor": self.honor,
            "rank": self.rank,
            "rank_locked": self.rank_locked,
            "recognition": self.recognition,
            "recognition_halved": self.recognition_halved,
            "starting_xp": self.starting_xp,
            "earned_xp": self.earned_xp,
            "current_light_wounds": self.current_light_wounds,
            "current_serious_wounds": self.current_serious_wounds,
            "current_void_points": self.current_void_points,
            "notes": self.notes,
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
            honor=data.get("honor", 1.0),
            rank=data.get("rank", 1.0),
            rank_locked=data.get("rank_locked", False),
            recognition=data.get("recognition", 1.0),
            recognition_halved=data.get("recognition_halved", False),
            starting_xp=data.get("starting_xp", 150),
            earned_xp=data.get("earned_xp", 0),
            current_light_wounds=data.get("current_light_wounds", 0),
            current_serious_wounds=data.get("current_serious_wounds", 0),
            current_void_points=data.get("current_void_points", 0),
            notes=data.get("notes", ""),
        )
