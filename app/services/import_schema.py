"""Structured-output schema for the Gemini character-extraction call.

The LLM returns "as-written" strings (e.g. ``"Crane Duelist"``) rather than
catalog IDs (e.g. ``"kakita_duelist"``). Fuzzy matching against the real
catalogs in ``app/game_data.py`` happens in Phase 5 (``import_match.py``).
This separation keeps the LLM's job simple - it does not need our full
game data in its context - and means catalog drift never requires prompt
changes.

Two things live in this module:

1. ``ExtractedCharacter`` - a Pydantic model the LLM client validates
   against after parsing Gemini's JSON response.

2. ``GEMINI_RESPONSE_SCHEMA`` - a hand-written OpenAPI-style schema dict
   passed to Gemini's ``generationConfig.responseSchema`` so the model
   is physically constrained to emit only fields we accept (design §5.1).

Gemini's responseSchema is based on OpenAPI 3.0, NOT JSON Schema Draft
2020. We therefore cannot use ``pydantic.model_json_schema()`` directly;
the dialects disagree on ``nullable`` vs. ``"type": ["string", "null"]``,
``anyOf``/``oneOf``, etc. Keeping the schema hand-written is less clever
but keeps us compatible with the actual API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Pydantic model used for server-side validation
# ---------------------------------------------------------------------------


class ExtractedSkillOrKnack(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name_as_written: str
    rank: int


class ExtractedAdvantage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name_as_written: str
    detail: str = ""


class ExtractedSpecialization(BaseModel):
    """One Specialization. May appear multiple times on the same character.
    ``skill_as_written`` is the human-readable skill name from the document
    that the validator resolves to a SKILL id. ``text`` is the sub-domain
    descriptor (e.g. ``"Court Etiquette"``) - free-form, GM-discussed."""
    model_config = ConfigDict(extra="ignore")
    text: str = ""
    skill_as_written: str = ""


class ExtractedRings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    air: Optional[int] = None
    fire: Optional[int] = None
    earth: Optional[int] = None
    water: Optional[int] = None
    void: Optional[int] = None


class ExtractedSection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str
    content: str


class ExtractedAmbiguity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    note: str


class ExtractedCharacter(BaseModel):
    """What the LLM produces after a successful extraction call."""

    model_config = ConfigDict(extra="ignore")

    # --- Identity ------------------------------------------------------
    name: Optional[str] = None
    player_name: Optional[str] = None

    # --- School --------------------------------------------------------
    school_name_as_written: Optional[str] = None
    # One of "Air", "Fire", "Earth", "Water", "Void" when the source or the
    # school requires a choice; None otherwise.
    school_ring_choice: Optional[str] = None

    # --- Rings ---------------------------------------------------------
    rings: ExtractedRings = Field(default_factory=ExtractedRings)

    # --- Combat --------------------------------------------------------
    attack: Optional[int] = None
    parry: Optional[int] = None

    # --- Skills / Knacks ----------------------------------------------
    skills: List[ExtractedSkillOrKnack] = Field(default_factory=list)
    knacks: List[ExtractedSkillOrKnack] = Field(default_factory=list)

    # --- Advantages / Disadvantages -----------------------------------
    advantages: List[ExtractedAdvantage] = Field(default_factory=list)
    disadvantages: List[ExtractedAdvantage] = Field(default_factory=list)

    # --- Specializations ----------------------------------------------
    # Specialization is the only advantage that may be taken multiple
    # times. The LLM emits one entry per instance with the sub-domain
    # text plus the human-readable skill name. The validator resolves
    # each skill name to a SKILL id before persisting.
    specializations: List[ExtractedSpecialization] = Field(default_factory=list)

    # --- Technique choices --------------------------------------------
    # Only for schools with player-choosable 1st / 2nd Dan techniques
    # (isawa_ishi, ide_diplomat, priest, shugenja, kitsune_warden,
    # suzume_overseer - see game_data).
    first_dan_choices: List[str] = Field(default_factory=list)
    second_dan_choice: Optional[str] = None
    # Kitsune Warden 3rd Dan: three player-chosen skills the adventure
    # raises pool can also be applied to (in addition to the always-on
    # attack and wound check). Skill names as written; iaijutsu is dropped
    # by the resolver.
    third_dan_skill_choices: List[str] = Field(default_factory=list)

    # --- Honor / Rank / Recognition -----------------------------------
    honor: Optional[float] = None
    rank: Optional[float] = None
    recognition: Optional[float] = None

    # --- XP -----------------------------------------------------------
    # Starting XP defaults to 150 in our app; the LLM sets this only when
    # the source states something different.
    starting_xp: Optional[int] = None
    # The remaining XP fields are for reconciliation only; we never write
    # them to the character directly. See design doc §9.1.
    source_stated_spent_xp: Optional[int] = None
    source_stated_earned_xp: Optional[int] = None
    source_stated_unspent_xp: Optional[int] = None

    # --- Freeform sections --------------------------------------------
    freeform_sections: List[ExtractedSection] = Field(default_factory=list)

    # --- Rejection signals --------------------------------------------
    # The LLM is instructed to set these when it detects the document is
    # either a roster of characters or not a character sheet at all. The
    # orchestrator (Phase 6) uses these to reject rather than import.
    multi_character_detected: bool = False
    not_a_character_sheet: bool = False

    # --- Self-report metadata -----------------------------------------
    # Used as a *supplementary* confidence signal (design §10.2). The
    # real confidence comes from structural and catalog checks later.
    ambiguities: List[ExtractedAmbiguity] = Field(default_factory=list)
    per_field_confidence: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Gemini responseSchema (OpenAPI 3.0 dialect)
# ---------------------------------------------------------------------------
#
# Gemini requires a schema dict rather than a Pydantic model. We keep the
# shape tight - most fields are nullable rather than required - because the
# LLM sometimes omits perfectly-legal nulls when we mark everything required.

_RING_VALUE = {"type": "INTEGER", "nullable": True,
               "description": "Ring rank 1 to 6, or null if absent."}

_SKILL_OR_KNACK_ENTRY = {
    "type": "OBJECT",
    "properties": {
        "name_as_written": {
            "type": "STRING",
            "description": "Name exactly as it appears in the source document. "
                           "Do not translate to a canonical form."
        },
        "rank": {"type": "INTEGER"},
    },
    "required": ["name_as_written", "rank"],
}

_ADVANTAGE_ENTRY = {
    "type": "OBJECT",
    "properties": {
        "name_as_written": {
            "type": "STRING",
            "description": "Name exactly as it appears in the source document."
        },
        "detail": {
            "type": "STRING",
            "description": "Free-text detail if the advantage carries one "
                           "(e.g. Virtue: Courage -> detail is 'Courage'). "
                           "Empty string if none."
        },
    },
    "required": ["name_as_written"],
}

_SECTION_ENTRY = {
    "type": "OBJECT",
    "properties": {
        "label": {"type": "STRING"},
        "content": {"type": "STRING"},
    },
    "required": ["label", "content"],
}

_AMBIGUITY_ENTRY = {
    "type": "OBJECT",
    "properties": {
        "field": {"type": "STRING"},
        "note": {"type": "STRING"},
    },
    "required": ["field", "note"],
}


GEMINI_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        # Identity
        "name": {"type": "STRING", "nullable": True},
        "player_name": {"type": "STRING", "nullable": True},

        # School
        "school_name_as_written": {"type": "STRING", "nullable": True},
        "school_ring_choice": {
            "type": "STRING",
            "nullable": True,
            "enum": ["Air", "Fire", "Earth", "Water", "Void"],
            "description": "Set only for schools with a chosen school ring.",
        },

        # Rings
        "rings": {
            "type": "OBJECT",
            "properties": {
                "air":   _RING_VALUE,
                "fire":  _RING_VALUE,
                "earth": _RING_VALUE,
                "water": _RING_VALUE,
                "void":  _RING_VALUE,
            },
        },

        # Combat
        "attack": {"type": "INTEGER", "nullable": True},
        "parry":  {"type": "INTEGER", "nullable": True},

        # Skills / Knacks
        "skills": {"type": "ARRAY", "items": _SKILL_OR_KNACK_ENTRY},
        "knacks": {"type": "ARRAY", "items": _SKILL_OR_KNACK_ENTRY},

        # Advantages / Disadvantages
        "advantages":    {"type": "ARRAY", "items": _ADVANTAGE_ENTRY},
        "disadvantages": {"type": "ARRAY", "items": _ADVANTAGE_ENTRY},

        # Technique choices
        "first_dan_choices": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Skill names (as written) chosen for 1st Dan. "
                           "Empty list if not applicable.",
        },
        "second_dan_choice": {"type": "STRING", "nullable": True},
        "third_dan_skill_choices": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Kitsune Warden 3rd Dan: skill names (as "
                           "written) chosen as the three additional "
                           "applicable_to entries. Iaijutsu is excluded "
                           "and will be dropped by the resolver.",
        },

        # Honor / Rank / Recognition
        "honor":       {"type": "NUMBER", "nullable": True},
        "rank":        {"type": "NUMBER", "nullable": True},
        "recognition": {"type": "NUMBER", "nullable": True},

        # XP
        "starting_xp":              {"type": "INTEGER", "nullable": True},
        "source_stated_spent_xp":   {"type": "INTEGER", "nullable": True},
        "source_stated_earned_xp":  {"type": "INTEGER", "nullable": True},
        "source_stated_unspent_xp": {"type": "INTEGER", "nullable": True},

        # Freeform sections
        "freeform_sections": {"type": "ARRAY", "items": _SECTION_ENTRY},

        # Rejection flags
        "multi_character_detected": {"type": "BOOLEAN"},
        "not_a_character_sheet":    {"type": "BOOLEAN"},

        # Self-report
        "ambiguities": {"type": "ARRAY", "items": _AMBIGUITY_ENTRY},
        "per_field_confidence": {
            "type": "OBJECT",
            "description": "Keys are field names; values are one of "
                           "'high' / 'medium' / 'low'.",
        },
    },
    "required": [
        "rings",
        "skills",
        "knacks",
        "advantages",
        "disadvantages",
        "freeform_sections",
        "first_dan_choices",
        "ambiguities",
        "multi_character_detected",
        "not_a_character_sheet",
    ],
}


# ---------------------------------------------------------------------------
# Heuristic for "this extraction is too sparse; try the fallback model"
# ---------------------------------------------------------------------------


def looks_too_sparse(extracted: ExtractedCharacter) -> bool:
    """Return True when the extraction result is probably a bad read
    (most identifying fields empty) and the orchestrator should escalate
    to the fallback model.

    Defined as: name AND school are both missing, OR every ring is null.
    These signals together almost always mean the LLM could not locate
    any usable data in the document - classic flash-fumble we try to
    recover from with pro (design §10.3 layer 2).
    """
    if extracted.not_a_character_sheet:
        # The model itself is confident this is not a sheet; no retry.
        return False
    identity_missing = (
        not extracted.name and not extracted.school_name_as_written
    )
    rings = extracted.rings
    rings_all_null = all(
        getattr(rings, r) is None for r in ("air", "fire", "earth", "water", "void")
    )
    return identity_missing or rings_all_null


__all__ = [
    "ExtractedCharacter",
    "ExtractedRings",
    "ExtractedSkillOrKnack",
    "ExtractedAdvantage",
    "ExtractedSpecialization",
    "ExtractedSection",
    "ExtractedAmbiguity",
    "GEMINI_RESPONSE_SCHEMA",
    "looks_too_sparse",
]
