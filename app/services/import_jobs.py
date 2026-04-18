"""Async job registry for character-import requests.

``POST /import`` kicks off a pipeline run in a worker thread, stores a
job record in an in-memory dict, and redirects the user to a progress
page that polls ``GET /import/status/{id}`` until the pipeline is done.
The progress UI then redirects on success or shows the error banner.

Scope limitations this design accepts on purpose:

- **In-memory registry.** Jobs live in a dict keyed by UUID and are
  lost on process restart. The import flow tolerates that because jobs
  complete within ~30 seconds; a restart mid-import manifests as the
  progress page timing out, which the user can retry. If we ever scale
  past one Fly machine, this moves to a Redis or DB-backed registry.
- **Single-process.** Same reason. Fly currently runs one machine.
- **Bounded memory.** A completed job is kept around for a short window
  so the progress page can read the final state, then reaped. The
  reaper runs opportunistically on each ``submit_job`` call - no
  separate timer thread.

For tests, ``_RUNNER`` can be monkey-patched to a synchronous callable
so assertions see the terminal state without sleep loops.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from app.database import SessionLocal
from app.models import Character
from app.services.import_orchestrator import (
    CharacterReady,
    ImportOutcome,
    Rejected,
    orchestrate_import,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job record
# ---------------------------------------------------------------------------


STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"


@dataclass
class ImportJob:
    id: str
    user_id: str
    state: str = STATE_PENDING
    stage: str = "Queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Populated when the pipeline succeeds:
    character_id: Optional[int] = None

    # Populated when the pipeline is rejected or errors:
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_status: int = 400

    def touch(self, *, stage: Optional[str] = None, state: Optional[str] = None) -> None:
        if stage is not None:
            self.stage = stage
        if state is not None:
            self.state = state
        self.updated_at = datetime.now(timezone.utc)

    def is_terminal(self) -> bool:
        return self.state in (STATE_SUCCEEDED, STATE_FAILED)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_JOBS: Dict[str, ImportJob] = {}
_LOCK = threading.Lock()

# How long to keep terminal jobs so the progress page can read them.
# The reaper runs during submit_job, so we only need enough buffer for
# a user to get to the edit page after success.
_TERMINAL_TTL = timedelta(minutes=10)


def _reap_expired() -> None:
    cutoff = datetime.now(timezone.utc) - _TERMINAL_TTL
    with _LOCK:
        expired = [
            jid for jid, job in _JOBS.items()
            if job.is_terminal() and job.updated_at < cutoff
        ]
        for jid in expired:
            del _JOBS[jid]


def get_job(job_id: str) -> Optional[ImportJob]:
    with _LOCK:
        return _JOBS.get(job_id)


# ---------------------------------------------------------------------------
# Dispatcher (pluggable so tests can force synchronous execution)
# ---------------------------------------------------------------------------


def _threaded_dispatch(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


_RUNNER: Callable[[Callable[[], None]], None] = _threaded_dispatch


def set_runner(runner: Callable[[Callable[[], None]], None]) -> None:
    """Override the dispatcher - mainly for tests that want
    synchronous execution."""
    global _RUNNER
    _RUNNER = runner


def reset_runner() -> None:
    global _RUNNER
    _RUNNER = _threaded_dispatch


# ---------------------------------------------------------------------------
# Submit + execute
# ---------------------------------------------------------------------------


def submit_job(
    *,
    user_id: str,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    url: Optional[str] = None,
    source_descriptor: Optional[str] = None,
) -> str:
    """Register a new job, dispatch the worker, return the job id."""
    _reap_expired()
    job_id = str(uuid.uuid4())
    job = ImportJob(id=job_id, user_id=user_id)
    with _LOCK:
        _JOBS[job_id] = job

    def _run() -> None:
        _execute_job(
            job_id,
            file_bytes=file_bytes,
            filename=filename,
            url=url,
            source_descriptor=source_descriptor,
        )

    _RUNNER(_run)
    return job_id


def _execute_job(
    job_id: str,
    *,
    file_bytes: Optional[bytes],
    filename: Optional[str],
    url: Optional[str],
    source_descriptor: Optional[str],
) -> None:
    job = get_job(job_id)
    if job is None:  # pragma: no cover - job was reaped before we started
        return

    job.touch(state=STATE_RUNNING, stage="Reading the document")

    try:
        outcome: ImportOutcome = orchestrate_import(
            file_bytes=file_bytes,
            filename=filename,
            url=url,
            source_descriptor=source_descriptor,
        )
    except Exception as exc:  # pragma: no cover - unexpected; orchestrator catches expected errors
        logger.exception("unexpected orchestrator exception")
        _mark_failed(
            job, error_code="internal_error",
            error_message=f"Unexpected import error: {exc}",
            status=500,
        )
        return

    if isinstance(outcome, Rejected):
        _mark_failed(
            job,
            error_code=outcome.error_code,
            error_message=outcome.user_message,
            status=_status_for(outcome.error_code),
        )
        return

    assert isinstance(outcome, CharacterReady)
    job.touch(stage="Saving the draft")
    try:
        character_id = _persist_character(job.user_id, outcome)
    except Exception as exc:  # pragma: no cover - DB errors surface as 500
        logger.exception("draft persistence failed")
        _mark_failed(
            job, error_code="persist_error",
            error_message=f"Could not save the draft: {exc}",
            status=500,
        )
        return

    job.character_id = character_id
    job.touch(state=STATE_SUCCEEDED, stage="Done")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_STATUS_MAP = {
    "file_too_large": 413,
    "url_response_too_large": 413,
    "gemini_rate_limited": 503,
    "gemini_not_configured": 503,
    "gemini_transport_error": 502,
    "gemini_invalid_response": 502,
    "document_not_public": 400,
    "multi_character_document": 400,
    "not_a_character_sheet": 400,
}


def _status_for(error_code: str) -> int:
    return _STATUS_MAP.get(error_code, 400)


def _mark_failed(
    job: ImportJob, *, error_code: str, error_message: str, status: int,
) -> None:
    job.error_code = error_code
    job.error_message = error_message
    job.error_status = status
    job.touch(state=STATE_FAILED, stage="Failed")


def _persist_character(user_id: str, outcome: CharacterReady) -> int:
    """Create the Draft in a fresh session (the request's session was
    closed as soon as POST /import returned)."""
    session = SessionLocal()
    try:
        character = Character(
            owner_discord_id=user_id,
            **outcome.character_data,
        )
        character.sections = outcome.sections
        character.current_void_points = character.ring_void
        session.add(character)
        session.commit()
        session.refresh(character)
        return character.id
    finally:
        session.close()


__all__ = [
    "STATE_PENDING",
    "STATE_RUNNING",
    "STATE_SUCCEEDED",
    "STATE_FAILED",
    "ImportJob",
    "submit_job",
    "get_job",
    "set_runner",
    "reset_runner",
]
