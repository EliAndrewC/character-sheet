"""Routes for the character-import feature.

Four endpoints:

  ``GET  /import``                 - render the upload form
  ``POST /import``                 - kick off an import job, redirect to progress
  ``GET  /import/progress/{id}``   - render the polling page
  ``GET  /import/status/{id}``     - JSON status for the polling JS

The route layer is deliberately thin: input validation, rate limit,
kill-switch, and dispatch to ``import_jobs``. All the pipeline work
happens inside the worker thread so the POST returns immediately.

The module is named ``import_char`` rather than ``import`` to avoid
shadowing Python's ``import`` keyword in import statements.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.import_ingest import IMPORT_MAX_UPLOAD_MB
from app.services.import_jobs import (
    STATE_FAILED,
    STATE_SUCCEEDED,
    get_job,
    submit_job,
)
from app.services.import_rate_limit import (
    check_rate_limit,
    import_enabled,
)


router = APIRouter()


def _templates():
    from app.main import templates
    return templates


_KILL_SWITCH_MESSAGE = (
    "Character import is temporarily unavailable. Please try again later."
)


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------


def _render_import_form(
    request: Request,
    *,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
    status_code: int = 200,
) -> HTMLResponse:
    return _templates().TemplateResponse(
        request=request,
        name="character/import.html",
        context={
            "request": request,
            "error_message": error_message,
            "error_code": error_code,
            "max_upload_mb": IMPORT_MAX_UPLOAD_MB,
        },
        status_code=status_code,
    )


@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    if not import_enabled():
        return _render_import_form(
            request, error_message=_KILL_SWITCH_MESSAGE, status_code=503,
        )
    return _render_import_form(request)


# ---------------------------------------------------------------------------
# POST: submit an import job
# ---------------------------------------------------------------------------


@router.post("/import")
async def import_submit(
    request: Request,
    db: Session = Depends(get_db),
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    if not import_enabled():
        return _render_import_form(
            request, error_message=_KILL_SWITCH_MESSAGE, status_code=503,
        )

    # Rate limit before reading any bytes off the wire.
    rate_error = check_rate_limit(db, user["discord_id"])
    if rate_error is not None:
        return _render_import_form(
            request, error_message=rate_error, status_code=429,
        )

    # Figure out the source.
    file_bytes: Optional[bytes] = None
    filename: Optional[str] = None
    url_clean = (url or "").strip() or None
    has_file = file is not None and file.filename
    if has_file:
        file_bytes = await file.read()
        filename = file.filename

    if not has_file and not url_clean:
        return _render_import_form(
            request,
            error_message=(
                "Please upload a file or paste a URL before submitting."
            ),
            status_code=400,
        )
    if has_file and url_clean:
        return _render_import_form(
            request,
            error_message=(
                "Please provide either a file OR a URL, not both."
            ),
            status_code=400,
        )

    job_id = submit_job(
        user_id=user["discord_id"],
        file_bytes=file_bytes,
        filename=filename,
        url=url_clean,
        source_descriptor=filename or url_clean,
    )
    return RedirectResponse(
        f"/import/progress/{job_id}", status_code=303,
    )


# ---------------------------------------------------------------------------
# Progress page (polling UI)
# ---------------------------------------------------------------------------


@router.get("/import/progress/{job_id}", response_class=HTMLResponse)
def import_progress(request: Request, job_id: str):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    job = get_job(job_id)
    # Unknown job IDs reuse the "not your job" message so we don't leak
    # which IDs exist.
    if job is None or job.user_id != user["discord_id"]:
        return _render_import_form(
            request,
            error_message=(
                "That import job is no longer available. Start a new "
                "import below."
            ),
            status_code=404,
        )

    return _templates().TemplateResponse(
        request=request,
        name="character/import_progress.html",
        context={
            "request": request,
            "job_id": job.id,
        },
    )


# ---------------------------------------------------------------------------
# Status JSON (polled by the progress page)
# ---------------------------------------------------------------------------


@router.get("/import/status/{job_id}")
def import_status(request: Request, job_id: str) -> JSONResponse:
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse({"error": "not_authenticated"}, status_code=401)

    job = get_job(job_id)
    if job is None or job.user_id != user["discord_id"]:
        return JSONResponse({"error": "not_found"}, status_code=404)

    payload = {
        "id": job.id,
        "state": job.state,
        "stage": job.stage,
    }
    if job.state == STATE_SUCCEEDED:
        payload["redirect_url"] = f"/characters/{job.character_id}/edit"
    elif job.state == STATE_FAILED:
        payload["error_code"] = job.error_code
        payload["error_message"] = job.error_message
        payload["error_status"] = job.error_status
    return JSONResponse(payload)


__all__ = ["router"]
