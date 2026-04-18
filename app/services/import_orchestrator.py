"""The one function the /import route calls.

``orchestrate_import`` glues together every stage of the pipeline:

  1. Ingest file bytes or URL content (``import_ingest``, ``import_url``).
  2. LLM extraction with flash-to-pro fallback (``import_llm``).
  3. Check the rejection flags the LLM set (multi-character, not a
     character sheet) - these short-circuit before we validate.
  4. Validate + normalise + reconcile (``import_reconcile``).

Output is a typed ``ImportOutcome`` the route maps to either a "Draft
ready" redirect or an error banner on the /import page. All expected
failure modes surface as a ``Rejected`` with an ``error_code`` matching
what the Phase 2 fixture expected JSON files call for; unexpected
exceptions propagate and become a 500.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.services.import_ingest import (
    FileTooLargeError,
    ImportIngestError,
    ParseError,
    UnsupportedFormatError,
    DocumentUnreadableError,
    ingest_bytes,
)
from app.services.import_llm import (
    ExtractionOutcome,
    GeminiConfigError,
    GeminiError,
    GeminiInvalidResponseError,
    GeminiRateLimitError,
    GeminiTransportError,
    extract_with_fallback,
)
from app.services.import_reconcile import run_post_llm_pipeline
from app.services.import_schema import ExtractedCharacter
from app.services.import_url import (
    GoogleDocNotPublicError,
    ImportUrlError,
    UrlBlockedError,
    UrlFetchError,
    UrlRedirectChainTooLongError,
    UrlResponseTooLargeError,
    UrlSchemeError,
    ingest_url,
)


# ---------------------------------------------------------------------------
# Outcome types
# ---------------------------------------------------------------------------


@dataclass
class CharacterReady:
    """Success: ready to construct a Character and redirect."""
    character_data: Dict[str, Any]
    sections: List[Dict[str, str]]
    model_used: str
    fallback_used: bool
    # Informational messages surfaced in Import Notes / telemetry.
    warnings: List[str] = field(default_factory=list)


@dataclass
class Rejected:
    """Every path that does not produce a character.

    ``error_code`` matches the Phase 2 fixture ``expected.json`` values
    so future integration tests can assert directly against it.
    """
    error_code: str
    user_message: str


ImportOutcome = Union[CharacterReady, Rejected]


# ---------------------------------------------------------------------------
# Rejection helpers
# ---------------------------------------------------------------------------

_MULTI_CHARACTER_MESSAGE = (
    "This document appears to describe more than one character. Please "
    "split it into per-character documents and import them one at a time."
)

_NOT_A_SHEET_MESSAGE = (
    "This document doesn't look like an L7R character sheet. Check that "
    "you uploaded the right file - we could not find any character data "
    "in it."
)


def _reject_from_flags(extracted: ExtractedCharacter) -> Optional[Rejected]:
    if extracted.multi_character_detected:
        return Rejected(
            error_code="multi_character_document",
            user_message=_MULTI_CHARACTER_MESSAGE,
        )
    if extracted.not_a_character_sheet:
        return Rejected(
            error_code="not_a_character_sheet",
            user_message=_NOT_A_SHEET_MESSAGE,
        )
    return None


# ---------------------------------------------------------------------------
# Ingest step (file bytes OR URL)
# ---------------------------------------------------------------------------


def _ingest(
    file_bytes: Optional[bytes],
    filename: Optional[str],
    url: Optional[str],
) -> Union["IngestOk", Rejected]:
    if file_bytes is not None:
        try:
            ingest_result = ingest_bytes(file_bytes, filename=filename)
        except ImportIngestError as exc:
            return _ingest_error_to_rejected(exc)
        return IngestOk(ingest_result=ingest_result)

    if url:
        try:
            ingest_result = ingest_url(url)
        except (ImportUrlError, ImportIngestError) as exc:
            return _ingest_error_to_rejected(exc)
        return IngestOk(ingest_result=ingest_result)

    return Rejected(
        error_code="no_source",
        user_message="Please provide either a file to upload or a URL.",
    )


@dataclass
class IngestOk:
    ingest_result: Any  # IngestResult; avoid import cycle for typing


def _ingest_error_to_rejected(exc: Exception) -> Rejected:
    # Every typed error already carries a user_message and error_code.
    # Wrap an unexpected exception (theoretically unreachable) as a
    # generic ingest error - defensive only.
    error_code = getattr(exc, "error_code", "ingest_error")
    user_message = getattr(exc, "user_message", None) or str(exc)
    return Rejected(error_code=error_code, user_message=user_message)


# ---------------------------------------------------------------------------
# LLM step
# ---------------------------------------------------------------------------


def _call_llm(text: str, pdf_bytes: Optional[bytes]) -> Union[ExtractionOutcome, Rejected]:
    try:
        return extract_with_fallback(
            text, pdf_bytes_for_multimodal=pdf_bytes,
        )
    except GeminiConfigError as exc:
        return Rejected(error_code=exc.error_code,
                        user_message=exc.user_message)
    except GeminiRateLimitError as exc:
        return Rejected(error_code=exc.error_code,
                        user_message=exc.user_message)
    except (GeminiTransportError, GeminiInvalidResponseError) as exc:
        return Rejected(error_code=exc.error_code,
                        user_message=exc.user_message)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def orchestrate_import(
    *,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    url: Optional[str] = None,
    source_descriptor: Optional[str] = None,
) -> ImportOutcome:
    """Run the full import pipeline.

    Exactly one of ``file_bytes`` or ``url`` should be provided; the
    route layer is responsible for parsing the request and calling with
    the appropriate argument.

    ``source_descriptor`` is what shows up in Import Notes as "Source:";
    the route layer should set it to the original filename or URL so the
    user can see where their character came from even if we don't store
    the document.
    """
    # 1. Ingest --------------------------------------------------------
    ingest_step = _ingest(file_bytes, filename, url)
    if isinstance(ingest_step, Rejected):
        return ingest_step
    ingest_result = ingest_step.ingest_result

    # Default source descriptor to whatever we know.
    if source_descriptor is None:
        source_descriptor = filename or url or ""

    # 2. LLM ----------------------------------------------------------
    pdf_bytes = (
        ingest_result.pdf_bytes_for_multimodal
        if ingest_result.needs_multimodal_fallback
        else None
    )
    llm_step = _call_llm(ingest_result.text, pdf_bytes)
    if isinstance(llm_step, Rejected):
        return llm_step
    extraction: ExtractionOutcome = llm_step

    # 3. Classify -----------------------------------------------------
    reject = _reject_from_flags(extraction.character)
    if reject is not None:
        return reject

    # 4. Validate / reconcile ----------------------------------------
    warnings: List[str] = []
    warnings.extend(ingest_result.warnings or [])
    warnings.extend(extraction.warnings or [])

    pipeline_result = run_post_llm_pipeline(
        extraction.character,
        source_descriptor=source_descriptor,
        model_used=extraction.model_used,
        fallback_used=extraction.fallback_used,
        extra_warnings=warnings,
    )

    return CharacterReady(
        character_data=pipeline_result["character_data"],
        sections=pipeline_result["sections"],
        model_used=extraction.model_used,
        fallback_used=extraction.fallback_used,
        warnings=warnings,
    )


__all__ = [
    "orchestrate_import",
    "ImportOutcome",
    "CharacterReady",
    "Rejected",
]
