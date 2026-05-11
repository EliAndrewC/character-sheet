"""Normalise an ``ExtractedCharacter`` into character-model field values.

Inputs: whatever the LLM returned (``ExtractedCharacter``), plus the
catalog matchers from ``import_match``. Outputs: a plain dict of fields
ready to hand to a ``Character`` constructor, plus a
``ValidationReport`` collecting everything the caller needs to surface
in Import Notes.

Responsibilities (design doc §9, §10.2):

  * Resolve the school name to an ID and auto-set ``school_ring_choice``
    to the school's required ring (or the player-chosen one for schools
    with multiple options).
  * Clamp ring values to 1-6. Values > 6 are treated as "pool values"
    (ring x 2) and halved with a flag.
  * Clamp skills / knacks / attack / parry to the legal ranges.
  * Drop skills / knacks / advantages / disadvantages the LLM returned
    with names we cannot match. Each drop is recorded for Import Notes.
  * Split advantages into ``advantages`` / ``campaign_advantages`` based
    on which catalog matched (same for disadvantages).
  * Preserve per-advantage detail text in ``advantage_details``.
  * Cross-check school knacks: if the declared school has three knacks
    and the imported knacks include none of them, flag
    ``wrong_school_knacks``. We still keep whatever ranks the user
    provided - the correction is a user decision, not ours.
  * Cross-check ``school_ring_choice`` against the school's allowed
    rings; if the LLM's pick isn't valid, blank it out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.game_data import (
    COMBAT_SKILL_MAX,
    COMBAT_SKILL_START,
    HONOR_MAX,
    HONOR_START,
    RECOGNITION_MAX_FACTOR,
    RING_DEFAULT,
    RING_MAX_NORMAL,
    RING_MAX_SCHOOL,
    SCHOOL_RING_OPTIONS,
    SCHOOLS,
    SKILL_MAX,
    KNACK_MAX,
    RING_NAMES,
)
from app.services.import_match import (
    ADV_BUCKET,
    ALIASED,
    DIS_BUCKET,
    EXACT,
    FUZZY,
    match_advantage_or_disadvantage,
    match_knack,
    match_ring_name,
    match_school,
    match_skill,
    match_skill_or_combat,
)
from app.services.import_schema import (
    ExtractedAdvantage,
    ExtractedCharacter,
    ExtractedSkillOrKnack,
    ExtractedSpecialization,
)


# ---------------------------------------------------------------------------
# Report struct
# ---------------------------------------------------------------------------


@dataclass
class DroppedEntry:
    """A single unmatched item the caller should mention in Import Notes."""
    kind: str   # "skill" / "knack" / "advantage" / "disadvantage"
    name_as_written: str
    reason: str = "not a recognised entry"


@dataclass
class AmbiguityEntry:
    """A matched item that resolved non-exactly - worth flagging to the
    user so they can double-check the importer's pick."""
    kind: str   # "school" / "skill" / "knack" / "advantage" / "disadvantage"
    name_as_written: str
    resolved_id: str
    confidence: str  # "aliased" / "fuzzy"


@dataclass
class ValidationReport:
    dropped: List[DroppedEntry] = field(default_factory=list)
    ambiguities: List[AmbiguityEntry] = field(default_factory=list)

    # Ring-value signals
    ring_pool_halved: List[str] = field(default_factory=list)
    ring_clamped: List[Tuple[str, int, int]] = field(default_factory=list)

    # School cross-checks
    school_unmatched: Optional[str] = None
    school_ring_choice_invalid: bool = False
    wrong_school_knacks: bool = False

    # XP stated by source (passthrough for reconcile)
    source_stated_spent_xp: Optional[int] = None
    source_stated_earned_xp: Optional[int] = None
    source_stated_unspent_xp: Optional[int] = None

    # True when the LLM's per_field_confidence marked a field as low.
    # Used as a *supplementary* signal (design §10.2).
    llm_low_confidence_fields: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _normalise_ring(value: Optional[int], ring_name: str,
                    report: ValidationReport) -> int:
    """Return a legal ring value, recording pool-halving and clamping."""
    if value is None:
        return RING_DEFAULT
    v = int(value)
    # Pool detection: values strictly above the school max (6) are almost
    # certainly pool-not-rank. Halve and keep going.
    if v > RING_MAX_SCHOOL:
        halved = v // 2
        report.ring_pool_halved.append(ring_name)
        v = halved
    clamped = _clamp(v, 1, RING_MAX_SCHOOL)
    if clamped != v:
        report.ring_clamped.append((ring_name, v, clamped))
    return clamped


def _safe_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - pydantic catches this
        return default


def _safe_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - pydantic catches this
        return default


# ---------------------------------------------------------------------------
# Per-field normalisers
# ---------------------------------------------------------------------------


def _normalise_school(
    extracted: ExtractedCharacter, report: ValidationReport,
) -> Tuple[str, str]:
    """Return ``(school_id, school_ring_choice)``.

    When the school is matched and has only one legal ring, we auto-set
    the ring choice (the user's chosen ring is not really "a choice" for
    fixed-ring schools but the model still needs it set so XP math is
    right). For multi-option schools we use whatever the LLM returned
    (validated).
    """
    school_id = ""
    ring_choice = ""

    school_name = extracted.school_name_as_written or ""
    if not school_name:
        report.school_unmatched = None  # stays None; simply absent
        return school_id, ring_choice

    matched_id, confidence = match_school(school_name)
    if matched_id is None:
        report.school_unmatched = school_name
        return school_id, ring_choice

    school_id = matched_id
    if confidence in (ALIASED, FUZZY):
        report.ambiguities.append(AmbiguityEntry(
            kind="school",
            name_as_written=school_name,
            resolved_id=matched_id,
            confidence=confidence,
        ))

    # Resolve school_ring_choice.
    options = SCHOOL_RING_OPTIONS.get(school_id, [])
    if len(options) == 1:
        ring_choice = options[0]
    elif len(options) > 1:
        # The LLM's school_ring_choice, if any, must land in the option list.
        llm_choice = extracted.school_ring_choice
        if llm_choice in options:
            ring_choice = llm_choice
        elif llm_choice:
            # They gave a ring, but it's not legal for this school.
            report.school_ring_choice_invalid = True
        # If none given, stays blank and the user picks on edit.

    return school_id, ring_choice


def _normalise_skills_or_knacks(
    items: List[ExtractedSkillOrKnack],
    kind: str,
    max_rank: int,
    matcher,
    report: ValidationReport,
) -> Dict[str, int]:
    """Generic skill/knack resolver."""
    out: Dict[str, int] = {}
    for entry in items:
        matched_id, confidence = matcher(entry.name_as_written)
        if matched_id is None:
            report.dropped.append(DroppedEntry(
                kind=kind,
                name_as_written=entry.name_as_written,
            ))
            continue
        if confidence in (ALIASED, FUZZY):
            report.ambiguities.append(AmbiguityEntry(
                kind=kind,
                name_as_written=entry.name_as_written,
                resolved_id=matched_id,
                confidence=confidence,
            ))
        rank = _clamp(_safe_int(entry.rank, 0), 0, max_rank)
        # If the same skill appears twice (LLM hiccup), keep the higher.
        out[matched_id] = max(out.get(matched_id, 0), rank)
    return out


def _grant_free_school_knacks(
    knacks: Dict[str, int],
    school_id: str,
    report: ValidationReport,
) -> Dict[str, int]:
    """Schools grant their three knacks at rank 1 for free. Ensure any of
    the school's canonical knacks appear at rank >= 1 in the output."""
    school = SCHOOLS.get(school_id)
    if school is None:  # pragma: no cover - caller gates on school_id truthy
        return knacks
    school_knack_ids = set(school.school_knacks)
    # Track whether the user's knacks intersect the school's knacks.
    imported_ids = set(knacks.keys())
    if imported_ids and not (imported_ids & school_knack_ids):
        report.wrong_school_knacks = True
    # Ensure all school knacks are represented at rank >= 1 so XP math
    # stays aligned with what the game engine expects.
    for kid in school_knack_ids:
        knacks[kid] = max(knacks.get(kid, 0), 1)
    return knacks


def _normalise_advantages(
    items: List[ExtractedAdvantage],
    bucket: str,
    report: ValidationReport,
) -> Tuple[List[str], List[str], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (base_ids, campaign_ids, details_dict, diverted_specs).

    Specialization is the only advantage that can be taken multiple times.
    A legacy LLM payload (or older document) may emit one or more
    ``Specialization`` entries on the regular advantages list - divert
    those into the dedicated ``specializations`` shape rather than
    persist them as a flat advantage. Skill stays empty since the
    detail text doesn't carry a skill name; the user picks on edit.
    """
    base_out: List[str] = []
    campaign_out: List[str] = []
    details: Dict[str, Dict[str, Any]] = {}
    diverted_specs: List[Dict[str, Any]] = []

    for entry in items:
        matched_id, catalog, confidence = match_advantage_or_disadvantage(
            entry.name_as_written, bucket=bucket,
        )
        kind = "advantage" if bucket == ADV_BUCKET else "disadvantage"
        if matched_id is None:
            report.dropped.append(DroppedEntry(
                kind=kind,
                name_as_written=entry.name_as_written,
            ))
            continue
        # Specialization on the legacy advantages path: divert each
        # occurrence into its own spec row keyed by the detail text.
        if matched_id == "specialization" and bucket == ADV_BUCKET:
            text = (entry.detail or "").strip()
            diverted_specs.append({"text": text, "skills": []})
            continue
        if confidence in (ALIASED, FUZZY):
            report.ambiguities.append(AmbiguityEntry(
                kind=kind,
                name_as_written=entry.name_as_written,
                resolved_id=matched_id,
                confidence=confidence,
            ))
        if catalog == "campaign":
            if matched_id not in campaign_out:
                campaign_out.append(matched_id)
        else:
            if matched_id not in base_out:
                base_out.append(matched_id)
        if entry.detail:
            details[matched_id] = {"text": entry.detail}

    return base_out, campaign_out, details, diverted_specs


def _normalise_specializations(
    items: List["ExtractedSpecialization"],
    diverted_from_advantages: List[Dict[str, Any]],
    report: ValidationReport,
) -> List[Dict[str, Any]]:
    """Resolve each Specialization's ``skill_as_written`` to a SKILL id.

    Specs with an unresolvable skill name keep their text but get
    ``skills: []`` so the user can fix the skill on the edit page.
    Diverted legacy specs (no skill name available) are appended too.
    """
    out: List[Dict[str, Any]] = []
    for spec in items:
        text = (spec.text or "").strip()
        skill_name = (spec.skill_as_written or "").strip()
        skills: List[str] = []
        if skill_name:
            skill_id, confidence = match_skill_or_combat(skill_name)
            if skill_id is not None:
                skills = [skill_id]
                if confidence in (ALIASED, FUZZY):
                    report.ambiguities.append(AmbiguityEntry(
                        kind="specialization",
                        name_as_written=skill_name,
                        resolved_id=skill_id,
                        confidence=confidence,
                    ))
        if text or skills:
            out.append({"text": text, "skills": skills})
    out.extend(diverted_from_advantages)
    return out


def _normalise_technique_choices(
    extracted: ExtractedCharacter, report: ValidationReport,
) -> Dict[str, Any]:
    """Resolve technique-choice skill *names* to skill IDs.

    Only kept for schools with flexible techniques. Invalid choices are
    silently dropped (the user can fix on edit); the legit ones stay.
    """
    choices: Dict[str, Any] = {}

    resolved_first: List[str] = []
    for raw_name in extracted.first_dan_choices or []:
        skill_id, confidence = match_skill(raw_name)
        if skill_id is None:
            report.dropped.append(DroppedEntry(
                kind="technique_choice",
                name_as_written=raw_name,
                reason="unknown skill name",
            ))
            continue
        if confidence in (ALIASED, FUZZY):
            report.ambiguities.append(AmbiguityEntry(
                kind="technique_choice",
                name_as_written=raw_name,
                resolved_id=skill_id,
                confidence=confidence,
            ))
        if skill_id not in resolved_first:
            resolved_first.append(skill_id)
    if resolved_first:
        choices["first_dan_choices"] = resolved_first

    if extracted.second_dan_choice:
        skill_id, confidence = match_skill(extracted.second_dan_choice)
        if skill_id is not None:
            choices["second_dan_choice"] = skill_id
            if confidence in (ALIASED, FUZZY):
                report.ambiguities.append(AmbiguityEntry(
                    kind="technique_choice",
                    name_as_written=extracted.second_dan_choice,
                    resolved_id=skill_id,
                    confidence=confidence,
                ))
        else:
            report.dropped.append(DroppedEntry(
                kind="technique_choice",
                name_as_written=extracted.second_dan_choice,
                reason="unknown skill name",
            ))

    # Kitsune Warden 3rd Dan: resolve the three player-chosen skills.
    # Iaijutsu is dropped explicitly (rules-excluded) - and iaijutsu lives
    # in SCHOOL_KNACKS not SKILLS, so we check for the iaijutsu knack alias
    # first and report the rules-specific reason. Unknown names (not a
    # skill, not a knack) are dropped with the generic "unknown" reason.
    resolved_third: List[str] = []
    for raw_name in extracted.third_dan_skill_choices or []:
        knack_id, _kc = match_knack(raw_name)
        if knack_id == "iaijutsu":
            report.dropped.append(DroppedEntry(
                kind="technique_choice",
                name_as_written=raw_name,
                reason="iaijutsu is not eligible for Kitsune Warden 3rd Dan",
            ))
            continue
        skill_id, confidence = match_skill(raw_name)
        if skill_id is None:
            report.dropped.append(DroppedEntry(
                kind="technique_choice",
                name_as_written=raw_name,
                reason="unknown skill name",
            ))
            continue
        if confidence in (ALIASED, FUZZY):
            report.ambiguities.append(AmbiguityEntry(
                kind="technique_choice",
                name_as_written=raw_name,
                resolved_id=skill_id,
                confidence=confidence,
            ))
        if skill_id not in resolved_third:
            resolved_third.append(skill_id)
    if resolved_third:
        choices["third_dan_skill_choices"] = resolved_third

    return choices


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def validate_and_normalise(
    extracted: ExtractedCharacter,
) -> Tuple[Dict[str, Any], ValidationReport]:
    """Top-level entry point for Phase 5's validation step.

    Returns ``(character_data, report)`` where ``character_data`` is a
    dict that can be passed as keyword arguments to ``Character(...)``
    (plus ``sections`` separately, which Phase 5's reconcile step
    assembles). ``report`` is consumed by the reconciliation step when
    building the Import Notes section.
    """
    report = ValidationReport(
        source_stated_spent_xp=extracted.source_stated_spent_xp,
        source_stated_earned_xp=extracted.source_stated_earned_xp,
        source_stated_unspent_xp=extracted.source_stated_unspent_xp,
    )

    # LLM-reported confidence is a secondary signal; we forward it
    # verbatim so reconcile can surface low-confidence fields to the user.
    for field_name, conf in (extracted.per_field_confidence or {}).items():
        if isinstance(conf, str) and conf.lower() == "low":
            report.llm_low_confidence_fields.append(field_name)

    # --- Identity ------------------------------------------------------
    data: Dict[str, Any] = {
        "name": (extracted.name or "").strip()[:120],
        "player_name": (extracted.player_name or "").strip()[:120],
    }

    # --- School --------------------------------------------------------
    school_id, school_ring_choice = _normalise_school(extracted, report)
    data["school"] = school_id
    data["school_ring_choice"] = school_ring_choice

    # --- Rings ---------------------------------------------------------
    r = extracted.rings
    data["ring_air"]   = _normalise_ring(r.air,   "Air",   report)
    data["ring_fire"]  = _normalise_ring(r.fire,  "Fire",  report)
    data["ring_earth"] = _normalise_ring(r.earth, "Earth", report)
    data["ring_water"] = _normalise_ring(r.water, "Water", report)
    data["ring_void"]  = _normalise_ring(r.void,  "Void",  report)

    # --- Combat --------------------------------------------------------
    data["attack"] = _clamp(
        _safe_int(extracted.attack, COMBAT_SKILL_START),
        COMBAT_SKILL_START, COMBAT_SKILL_MAX,
    )
    data["parry"] = _clamp(
        _safe_int(extracted.parry, COMBAT_SKILL_START),
        COMBAT_SKILL_START, COMBAT_SKILL_MAX,
    )

    # --- Skills / Knacks ----------------------------------------------
    data["skills"] = _normalise_skills_or_knacks(
        extracted.skills, "skill", SKILL_MAX, match_skill, report,
    )
    knacks = _normalise_skills_or_knacks(
        extracted.knacks, "knack", KNACK_MAX, match_knack, report,
    )
    if school_id:
        knacks = _grant_free_school_knacks(knacks, school_id, report)
    data["knacks"] = knacks

    # --- Advantages / Disadvantages -----------------------------------
    advs, c_advs, adv_details, diverted_specs = _normalise_advantages(
        extracted.advantages, ADV_BUCKET, report,
    )
    disads, c_disads, disad_details, _ = _normalise_advantages(
        extracted.disadvantages, DIS_BUCKET, report,
    )
    data["advantages"] = advs
    data["campaign_advantages"] = c_advs
    data["disadvantages"] = disads
    data["campaign_disadvantages"] = c_disads
    merged_details = {**adv_details, **disad_details}
    data["advantage_details"] = merged_details

    # --- Specializations (taken multiple times) -----------------------
    data["specializations"] = _normalise_specializations(
        extracted.specializations, diverted_specs, report,
    )

    # --- Technique choices --------------------------------------------
    data["technique_choices"] = _normalise_technique_choices(extracted, report)

    # --- Honor / Rank / Recognition -----------------------------------
    data["honor"] = _clamp_float(
        _safe_float(extracted.honor, HONOR_START),
        0.5, HONOR_MAX,
    )
    # Rank comes in ~0.5 increments; we clamp to a generous range so we
    # don't surprise the user - the edit page will let them adjust.
    data["rank"] = _clamp_float(
        _safe_float(extracted.rank, 7.5), 1.0, 10.0,
    )
    data["rank_locked"] = True
    rec = _safe_float(extracted.recognition, data["rank"])
    rec_cap = data["rank"] * RECOGNITION_MAX_FACTOR
    data["recognition"] = _clamp_float(rec, 1.0, rec_cap)
    data["recognition_halved"] = False

    # --- XP -----------------------------------------------------------
    data["starting_xp"] = _clamp(
        _safe_int(extracted.starting_xp, 150), 0, 10_000,
    )
    # earned_xp is computed in the reconcile step from the actual stats.
    data["earned_xp"] = 0

    # --- Ring / combat default bump ------------------------------------
    # If the school ring is set, bump that ring's value to at least the
    # "school default" so the starting character isn't under-powered
    # because the LLM missed a label. This matches what the UI does when
    # a user picks a school.
    if school_id and school_ring_choice in RING_NAMES:
        key = f"ring_{school_ring_choice.lower()}"
        if data[key] < 3:
            data[key] = 3

    return data, report


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


__all__ = [
    "DroppedEntry",
    "AmbiguityEntry",
    "ValidationReport",
    "validate_and_normalise",
]
