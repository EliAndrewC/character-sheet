"""Async job registry for character-art generation (Phase 8).

Mirrors ``import_jobs.py``: the submit route dispatches a worker
thread that calls Imagen, validates the returned bytes, and fills
them into the same ``StagedArt`` slot the Phase 7 prompt-review flow
created. The review page polls ``/art/generate/status/{staging_id}``
for progress.

Jobs are keyed by the staging_id (the existing Phase 4/7 identifier)
so the frontend doesn't juggle a second id: one id carries the prompt
through generation and on to the crop step.

For tests, ``_RUNNER`` can be monkey-patched to a synchronous callable.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from app.services import art_generate, art_image, art_jobs, art_rate_limit


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"


@dataclass
class ArtGenJob:
    staging_id: str
    user_id: str
    char_id: int
    state: str = STATE_PENDING
    stage: str = "Queued"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def touch(
        self, *, stage: Optional[str] = None, state: Optional[str] = None,
    ) -> None:
        if stage is not None:
            self.stage = stage
        if state is not None:
            self.state = state
        self.updated_at = datetime.now(timezone.utc)

    def is_terminal(self) -> bool:
        return self.state in (STATE_SUCCEEDED, STATE_FAILED)


# ---------------------------------------------------------------------------
# Registry (keyed by staging_id, not a separate job_id)
# ---------------------------------------------------------------------------


_JOBS: Dict[str, ArtGenJob] = {}
_LOCK = threading.Lock()

_TERMINAL_TTL = timedelta(minutes=10)


def _reap_expired() -> None:
    cutoff = datetime.now(timezone.utc) - _TERMINAL_TTL
    with _LOCK:
        expired = [
            sid for sid, j in _JOBS.items()
            if j.is_terminal() and j.updated_at < cutoff
        ]
        for sid in expired:
            del _JOBS[sid]


def get_job(staging_id: str) -> Optional[ArtGenJob]:
    with _LOCK:
        return _JOBS.get(staging_id)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _threaded_dispatch(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


_RUNNER: Callable[[Callable[[], None]], None] = _threaded_dispatch


def set_runner(runner: Callable[[Callable[[], None]], None]) -> None:
    """Override the dispatcher - mainly for tests that want synchronous execution."""
    global _RUNNER
    _RUNNER = runner


def reset_runner() -> None:
    global _RUNNER
    _RUNNER = _threaded_dispatch


# ---------------------------------------------------------------------------
# Submit + execute
# ---------------------------------------------------------------------------


def submit_job(
    *, user_id: str, char_id: int, staging_id: str, prompt: str,
) -> ArtGenJob:
    """Register a new job keyed by ``staging_id`` and dispatch the worker."""
    _reap_expired()
    job = ArtGenJob(staging_id=staging_id, user_id=user_id, char_id=char_id)
    with _LOCK:
        _JOBS[staging_id] = job

    def _run() -> None:
        _execute_job(staging_id=staging_id, prompt=prompt)

    _RUNNER(_run)
    return job


def _execute_job(*, staging_id: str, prompt: str) -> None:
    job = get_job(staging_id)
    if job is None:  # pragma: no cover - we just created it
        return
    job.touch(state=STATE_RUNNING, stage="Calling Imagen")

    # Guard: the staging slot may have been reaped if the user abandoned
    # the flow for 15+ minutes between steps.
    staged = art_jobs.get_staged(staging_id)
    if staged is None:
        _mark_failed(
            job,
            error_code="staging_expired",
            error_message=(
                "Your session expired before the image finished "
                "generating. Please start over."
            ),
        )
        return

    try:
        raw_bytes = art_generate.generate_image(prompt)
    except art_generate.ImageGenerationError as exc:
        _mark_failed(
            job,
            error_code=exc.error_code,
            error_message=exc.user_message,
        )
        return
    except Exception as exc:  # pragma: no cover - unexpected wrapper failures
        log.exception("Unexpected art generation failure")
        _mark_failed(
            job,
            error_code="gen_error",
            error_message=f"Unexpected error: {exc}",
        )
        return

    # Validate the bytes through the same pipeline uploads use. If
    # Imagen returned something malformed (wrong format, weird dims),
    # we reject it rather than staging nonsense the crop step would
    # choke on.
    try:
        validated = art_image.validate_upload(raw_bytes)
    except art_image.ArtImageError as exc:
        _mark_failed(
            job,
            error_code=exc.error_code,
            error_message=exc.user_message,
        )
        return

    # Re-encode to PNG bytes so the crop page serves them the same way
    # the upload flow does (the Phase 4 staging shim saves PNG).
    import io
    buf = io.BytesIO()
    validated.img.save(buf, format="PNG")
    art_jobs.update_staged_bytes(
        staging_id,
        full_bytes=buf.getvalue(),
        width=validated.width,
        height=validated.height,
    )

    # Record the successful generation against the user's rate-limit
    # counter. Only count completed work so failures don't punish the
    # user's budget.
    art_rate_limit.record_generation(job.user_id)

    job.touch(state=STATE_SUCCEEDED, stage="Done")


def _mark_failed(
    job: ArtGenJob, *, error_code: str, error_message: str,
) -> None:
    job.error_code = error_code
    job.error_message = error_message
    job.touch(state=STATE_FAILED, stage="Failed")


__all__ = [
    "STATE_FAILED",
    "STATE_PENDING",
    "STATE_RUNNING",
    "STATE_SUCCEEDED",
    "ArtGenJob",
    "get_job",
    "reset_runner",
    "set_runner",
    "submit_job",
]
