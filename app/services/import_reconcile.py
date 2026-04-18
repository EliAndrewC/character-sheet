"""Recompute XP and build the Import Notes section.

Inputs: the normalised character_data dict from ``import_validate`` plus
the ``ValidationReport`` it produced, optionally a source descriptor
(filename or URL) and the Gemini model that was used. Outputs: the same
``character_data`` with ``earned_xp`` set correctly, plus a sections
list whose first entry is the "Import Notes - please review" block of
sanitized HTML.

The XP math reuses ``app.services.xp.calculate_xp_breakdown`` so there
is exactly one place where XP rules live. We never trust the source's
XP numbers for the character itself - we only compare them for the
reconciliation paragraph in Import Notes (design §9.1 "Fields the
importer never populates" + §10.1).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.game_data import (
    ADVANTAGES,
    CAMPAIGN_ADVANTAGES,
    CAMPAIGN_DISADVANTAGES,
    DISADVANTAGES,
    RING_NAMES,
    SCHOOL_KNACKS,
    SCHOOLS,
    SKILLS,
)
from app.services.import_validate import (
    AmbiguityEntry,
    DroppedEntry,
    ValidationReport,
)
from app.services.sanitize import sanitize_html
from app.services.xp import calculate_xp_breakdown


IMPORT_NOTES_LABEL = "Import Notes - please review"


# ---------------------------------------------------------------------------
# XP math
# ---------------------------------------------------------------------------


@dataclass
class XpReconciliation:
    computed_spent: int
    source_stated_spent: Optional[int]
    source_stated_earned: Optional[int]
    source_stated_unspent: Optional[int]
    discrepancy: Optional[int]  # None when source stated nothing

    def has_discrepancy(self) -> bool:
        return self.discrepancy is not None and self.discrepancy != 0


def _character_data_for_xp(character_data: Dict[str, Any]) -> Dict[str, Any]:
    """Shape ``character_data`` into the dict layout that
    ``calculate_xp_breakdown`` expects (``rings`` sub-object rather than
    the flat ``ring_*`` columns used by the SQLAlchemy model)."""
    rings = {
        "Air": character_data.get("ring_air", 2),
        "Fire": character_data.get("ring_fire", 2),
        "Earth": character_data.get("ring_earth", 2),
        "Water": character_data.get("ring_water", 2),
        "Void": character_data.get("ring_void", 2),
    }
    data = dict(character_data)
    data["rings"] = rings
    data.setdefault("rank_recognition_awards", [])
    return data


def _total_from_breakdown(breakdown: Dict[str, Any]) -> int:
    total = 0
    for v in breakdown.values():
        if isinstance(v, dict) and "total" in v:
            total += v["total"]
    return total


def reconcile_xp(
    character_data: Dict[str, Any],
    report: ValidationReport,
) -> XpReconciliation:
    """Recompute XP from the imported stats; set ``earned_xp`` on
    ``character_data`` so the resulting character is always internally
    consistent; return a reconciliation struct for Import Notes."""
    shaped = _character_data_for_xp(character_data)
    breakdown = calculate_xp_breakdown(shaped)
    computed_spent = _total_from_breakdown(breakdown)

    starting_xp = int(character_data.get("starting_xp", 150))
    # earned_xp must cover any spending beyond the starting budget.
    # Unspent starting XP stays implicit (the UI shows "unspent"
    # separately).
    character_data["earned_xp"] = max(0, computed_spent - starting_xp)

    stated_spent = report.source_stated_spent_xp
    discrepancy = None
    if stated_spent is not None:
        discrepancy = computed_spent - stated_spent

    return XpReconciliation(
        computed_spent=computed_spent,
        source_stated_spent=stated_spent,
        source_stated_earned=report.source_stated_earned_xp,
        source_stated_unspent=report.source_stated_unspent_xp,
        discrepancy=discrepancy,
    )


# ---------------------------------------------------------------------------
# Import Notes HTML builder
# ---------------------------------------------------------------------------


def _display_school(school_id: str) -> str:
    if not school_id:
        return ""
    school = SCHOOLS.get(school_id)
    return school.name if school else school_id


def _display_skill(skill_id: str) -> str:
    skill = SKILLS.get(skill_id)
    return skill.name if skill else skill_id


def _display_knack(knack_id: str) -> str:
    k = SCHOOL_KNACKS.get(knack_id)
    return k.name if k else knack_id


def _display_advantage(adv_id: str) -> str:
    for catalog in (ADVANTAGES, DISADVANTAGES, CAMPAIGN_ADVANTAGES,
                    CAMPAIGN_DISADVANTAGES):
        if adv_id in catalog:
            return catalog[adv_id].name
    return adv_id  # pragma: no cover - unknown IDs get filtered before this


def _h(text: str) -> str:
    """Shorthand for ``html.escape``."""
    return html.escape(text, quote=False)


def _fmt_ambiguity(amb: AmbiguityEntry) -> str:
    kind_label = amb.kind.replace("_", " ").capitalize()
    resolved_display: str
    if amb.kind == "school":
        resolved_display = _display_school(amb.resolved_id)
    elif amb.kind == "skill":
        resolved_display = _display_skill(amb.resolved_id)
    elif amb.kind == "knack":
        resolved_display = _display_knack(amb.resolved_id)
    elif amb.kind in ("advantage", "disadvantage"):
        resolved_display = _display_advantage(amb.resolved_id)
    else:  # pragma: no cover - defensive; we only produce the kinds above
        resolved_display = amb.resolved_id
    detail = (
        f"{kind_label} <em>{_h(amb.name_as_written)}</em> was "
        f"{_h(amb.confidence)}-matched to <strong>"
        f"{_h(resolved_display)}</strong>."
    )
    return f"<li>{detail}</li>"


def _fmt_dropped(dropped: DroppedEntry) -> str:
    kind_label = dropped.kind.replace("_", " ").capitalize()
    return (
        f"<li>{kind_label} <em>{_h(dropped.name_as_written)}</em>: "
        f"{_h(dropped.reason)}. Dropped.</li>"
    )


def build_import_notes_html(
    character_data: Dict[str, Any],
    report: ValidationReport,
    xp: XpReconciliation,
    *,
    source_descriptor: Optional[str] = None,
    model_used: Optional[str] = None,
    fallback_used: bool = False,
    extra_warnings: Optional[List[str]] = None,
) -> str:
    """Return sanitized HTML for the Import Notes section."""
    parts: List[str] = []

    # --- Header --------------------------------------------------------
    parts.append(
        "<p><strong>This character was imported from an external "
        "document.</strong> Please review the items below before applying "
        "changes; the importer flags anything that was inferred, "
        "ambiguous, or dropped.</p>"
    )

    # --- Import summary -----------------------------------------------
    summary: List[str] = []
    if source_descriptor:
        summary.append(f"<li>Source: <code>{_h(source_descriptor)}</code></li>")
    summary.append(
        "<li>Imported at: " + _h(_utc_now_iso()) + " (UTC)</li>"
    )
    if model_used:
        label = f"Gemini {model_used}"
        if fallback_used:
            label += " (fallback - primary produced a sparse result)"
        summary.append(f"<li>Model: {_h(label)}</li>")
    if summary:
        parts.append("<h3>Import summary</h3>")
        parts.append("<ul>" + "".join(summary) + "</ul>")

    # --- What you should double-check ---------------------------------
    checks: List[str] = []
    if report.school_unmatched:
        checks.append(
            "<li><strong>School:</strong> we could not match "
            f"<em>{_h(report.school_unmatched)}</em> to any L7R school. "
            "Please pick a school on the edit page.</li>"
        )
    if report.school_ring_choice_invalid:
        checks.append(
            "<li><strong>School ring:</strong> the source named a ring "
            "that isn't valid for the chosen school. Left blank - pick "
            "on the edit page.</li>"
        )
    if report.wrong_school_knacks:
        school_name = _display_school(character_data.get("school", ""))
        checks.append(
            "<li><strong>Knacks:</strong> your listed knacks don't match "
            f"the {_h(school_name)} school's knacks. The source's knacks "
            "were imported anyway - verify the school or the knacks.</li>"
        )
    if report.ring_pool_halved:
        rings = ", ".join(_h(r) for r in report.ring_pool_halved)
        checks.append(
            f"<li><strong>Rings:</strong> {rings} looked like pool values "
            "(greater than 6) and were halved to ring ranks.</li>"
        )
    if report.ring_clamped:
        for ring, raw, clamped in report.ring_clamped:
            checks.append(
                f"<li><strong>Ring {_h(ring)}:</strong> value {raw} was "
                f"outside the 1-6 range and was clamped to {clamped}.</li>"
            )
    for amb in report.ambiguities:
        checks.append(_fmt_ambiguity(amb))
    for field_name in report.llm_low_confidence_fields:
        checks.append(
            f"<li>Field <code>{_h(field_name)}</code>: the model was not "
            "confident about this value - double-check.</li>"
        )
    if checks:
        parts.append("<h3>What you should double-check</h3>")
        parts.append("<ul>" + "".join(checks) + "</ul>")

    # --- What we could not import -------------------------------------
    if report.dropped:
        parts.append("<h3>What we could not import</h3>")
        parts.append("<ul>" + "".join(_fmt_dropped(d) for d in report.dropped) + "</ul>")

    # --- XP reconciliation --------------------------------------------
    parts.append("<h3>XP reconciliation</h3>")
    parts.append(_xp_block(xp))

    # --- Extra warnings (from Phase 4: transport warnings, truncation) ---
    if extra_warnings:
        parts.append("<h3>Extraction notes</h3>")
        parts.append("<ul>" + "".join(
            f"<li>{_h(w)}</li>" for w in extra_warnings
        ) + "</ul>")

    return sanitize_html("\n".join(parts))


def _xp_block(xp: XpReconciliation) -> str:
    lines: List[str] = []
    if xp.source_stated_spent is not None or xp.source_stated_unspent is not None:
        stated_bits: List[str] = []
        if xp.source_stated_spent is not None:
            stated_bits.append(f"{xp.source_stated_spent} XP spent")
        if xp.source_stated_unspent is not None:
            stated_bits.append(f"{xp.source_stated_unspent} XP unspent")
        if xp.source_stated_earned is not None:
            stated_bits.append(f"{xp.source_stated_earned} XP earned")
        lines.append(f"<li>Source stated: {', '.join(stated_bits)}.</li>")
    lines.append(
        f"<li>We recomputed: <strong>{xp.computed_spent} XP</strong> "
        "spent on the imported stats.</li>"
    )
    if xp.has_discrepancy():
        direction = "more than" if xp.discrepancy > 0 else "less than"
        lines.append(
            f"<li><strong>Difference:</strong> our total is "
            f"{abs(xp.discrepancy)} XP {direction} the source's stated "
            "spent total. Common causes: a typo in the source, a "
            "forgotten skill rank, or rule mismatch. Review the imported "
            "stats against your original sheet.</li>"
        )
    elif xp.source_stated_spent is not None:
        lines.append(
            "<li>Our total matches the source; no XP discrepancy.</li>"
        )
    return "<ul>" + "".join(lines) + "</ul>"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def build_sections(
    character_data: Dict[str, Any],
    extracted_sections: List[Dict[str, str]],
    report: ValidationReport,
    xp: XpReconciliation,
    *,
    source_descriptor: Optional[str] = None,
    model_used: Optional[str] = None,
    fallback_used: bool = False,
    extra_warnings: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Return the full sections list with Import Notes first.

    ``extracted_sections`` is whatever the LLM returned as
    ``freeform_sections``.
    """
    import_notes_html = build_import_notes_html(
        character_data,
        report,
        xp,
        source_descriptor=source_descriptor,
        model_used=model_used,
        fallback_used=fallback_used,
        extra_warnings=extra_warnings,
    )

    sections: List[Dict[str, str]] = [
        {"label": IMPORT_NOTES_LABEL, "html": import_notes_html}
    ]
    for s in extracted_sections:
        label = (s.get("label") or "Untitled").strip()[:120]
        content = s.get("content") or ""
        # Freeform content comes from untrusted LLM output which in turn
        # came from an untrusted document. Wrap in a <p> and sanitize.
        sections.append({
            "label": label,
            "html": sanitize_html(f"<p>{_h(content)}</p>"),
        })
    return sections


# ---------------------------------------------------------------------------
# Pipeline: the one public entry point that Phase 6 will call.
# ---------------------------------------------------------------------------


def run_post_llm_pipeline(
    extracted,
    *,
    source_descriptor: Optional[str] = None,
    model_used: Optional[str] = None,
    fallback_used: bool = False,
    extra_warnings: Optional[List[str]] = None,
):
    """Chain validate -> reconcile -> sections.

    Returns a dict ``{"character_data": {...}, "sections": [...],
    "report": ValidationReport, "xp": XpReconciliation}`` so the
    orchestrator (Phase 6) can both persist the character AND surface
    structured data for the response page / telemetry.
    """
    # Imported inside to avoid an otherwise-circular import (import_match
    # already pulled in import_schema; having import_validate do the same
    # top-level would cycle through this module).
    from app.services.import_validate import validate_and_normalise

    character_data, report = validate_and_normalise(extracted)
    xp = reconcile_xp(character_data, report)

    # Freeform sections from the LLM are list-of-dicts; pydantic turns
    # them into ExtractedSection models. Convert back to plain dicts.
    extracted_sections = [
        {"label": s.label, "content": s.content}
        for s in (extracted.freeform_sections or [])
    ]

    sections = build_sections(
        character_data,
        extracted_sections,
        report,
        xp,
        source_descriptor=source_descriptor,
        model_used=model_used,
        fallback_used=fallback_used,
        extra_warnings=extra_warnings,
    )

    return {
        "character_data": character_data,
        "sections": sections,
        "report": report,
        "xp": xp,
    }


__all__ = [
    "IMPORT_NOTES_LABEL",
    "XpReconciliation",
    "reconcile_xp",
    "build_import_notes_html",
    "build_sections",
    "run_post_llm_pipeline",
]
