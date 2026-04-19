"""Routes for character art uploads, cropping, and deletion.

The upload flow is:

  1. ``GET  /characters/{id}/art``            - landing page (file picker)
  2. ``POST /characters/{id}/art/upload``     - validate, stage, redirect
  3. ``GET  /characters/{id}/art/crop/{sid}`` - Cropper.js UI
  4. ``GET  /characters/{id}/art/staged/{sid}`` - serves the staged image
  5. ``POST /characters/{id}/art/crop/{sid}`` - save crop -> S3 -> DB
  6. ``POST /characters/{id}/art/delete``     - remove from DB + S3

Art is metadata, not stats - writes go straight to the published
Character row. Changing art never flips a character into Draft and
never touches an existing Draft's stats. Permission gate: anyone with
edit access on the character can change its art.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from PIL import Image

from app.database import get_db
from app.models import Character, User as UserModel
from app.services import art_image, art_jobs, art_prompt, art_storage
from app.services.art_face_detect import detect_face
from app.services.art_image import HEADSHOT_ASPECT_RATIO
from app.services.auth import can_edit_character, get_all_editors

log = logging.getLogger(__name__)

router = APIRouter()


def _templates():
    """Lazy templates accessor - avoids circular import with app.main."""
    from app.main import templates
    return templates


# ---------------------------------------------------------------------------
# Common: load character and enforce edit access.
# ---------------------------------------------------------------------------


def _load_character_for_edit(
    request: Request, db: Session, char_id: int,
) -> tuple[Optional[Character], Optional[Response]]:
    """Return ``(character, None)`` on success or ``(None, response)`` to short-circuit.

    Short-circuit cases: not logged in (redirect to login), character
    not found (404), or not allowed to edit (403). All art routes use
    this so the permission copy stays consistent.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return None, RedirectResponse("/auth/login", status_code=303)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return None, HTMLResponse("Character not found", status_code=404)

    owner = (
        db.query(UserModel)
        .filter(UserModel.discord_id == character.owner_discord_id)
        .first()
    )
    all_editors = get_all_editors(
        character.editor_discord_ids or [],
        owner.granted_account_ids or [] if owner else [],
    )
    if not can_edit_character(
        user["discord_id"], character.owner_discord_id, all_editors,
    ):
        return None, HTMLResponse(
            "You don't have permission to change this character's art.",
            status_code=403,
        )
    return character, None


def _bucket_and_region() -> tuple[Optional[str], str]:
    """Read S3 config the same way ``backup.py`` does."""
    bucket = os.environ.get("S3_BACKUP_BUCKET")
    region = os.environ.get("S3_BACKUP_REGION", "us-east-1")
    return bucket, region


# ---------------------------------------------------------------------------
# GET /characters/{id}/art - landing page
# ---------------------------------------------------------------------------


@router.get("/characters/{char_id}/art", response_class=HTMLResponse)
def art_landing(
    request: Request, char_id: int, db: Session = Depends(get_db),
):
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    headshot_url = None
    if character.headshot_s3_key:
        bucket, region = _bucket_and_region()
        if bucket:
            headshot_url = art_storage.public_url(
                character.headshot_s3_key, bucket=bucket, region=region,
            )

    return _templates().TemplateResponse(
        request=request,
        name="character/art.html",
        context={
            "character": character,
            "headshot_url": headshot_url,
            "max_upload_mb": art_image.MAX_UPLOAD_BYTES // (1024 * 1024),
        },
    )


# ---------------------------------------------------------------------------
# POST /characters/{id}/art/upload - validate + stage, redirect to crop
# ---------------------------------------------------------------------------


def _render_landing_with_error(
    request: Request,
    character: Character,
    *,
    error_message: str,
    status_code: int,
) -> HTMLResponse:
    headshot_url = None
    if character.headshot_s3_key:
        bucket, region = _bucket_and_region()
        if bucket:
            headshot_url = art_storage.public_url(
                character.headshot_s3_key, bucket=bucket, region=region,
            )
    return _templates().TemplateResponse(
        request=request,
        name="character/art.html",
        context={
            "character": character,
            "headshot_url": headshot_url,
            "error_message": error_message,
            "max_upload_mb": art_image.MAX_UPLOAD_BYTES // (1024 * 1024),
        },
        status_code=status_code,
    )


@router.post("/characters/{char_id}/art/upload")
async def art_upload(
    request: Request,
    char_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    raw = await file.read()
    if not raw:
        return _render_landing_with_error(
            request, character,
            error_message="No file was uploaded. Please pick an image.",
            status_code=400,
        )

    try:
        validated = art_image.validate_upload(raw)
    except art_image.ImageTooLargeError as exc:
        return _render_landing_with_error(
            request, character, error_message=exc.user_message, status_code=413,
        )
    except art_image.ArtImageError as exc:
        return _render_landing_with_error(
            request, character, error_message=exc.user_message, status_code=422,
        )

    # Persist the RGB-normalised image back to bytes. Keeping PNG here
    # means the crop page doesn't accidentally double-encode lossy
    # JPEG/WebP; the final WebP re-encode happens in build_headshot /
    # encode_for_storage.
    buf = io.BytesIO()
    validated.img.save(buf, format="PNG")
    staging_id = art_jobs.stage_art(
        user_id=request.state.user["discord_id"],
        char_id=char_id,
        full_bytes=buf.getvalue(),
        width=validated.width,
        height=validated.height,
        source="upload",
    )
    return RedirectResponse(
        f"/characters/{char_id}/art/crop/{staging_id}",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# GET /characters/{id}/art/crop/{sid} - cropper UI
# ---------------------------------------------------------------------------


@router.get("/characters/{char_id}/art/crop/{staging_id}",
            response_class=HTMLResponse)
def art_crop_page(
    request: Request,
    char_id: int,
    staging_id: str,
    db: Session = Depends(get_db),
):
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    staged = art_jobs.get_staged(staging_id)
    if (
        staged is None
        or staged.char_id != char_id
        or staged.user_id != request.state.user["discord_id"]
    ):
        return HTMLResponse(
            "That upload is no longer available. Please try again.",
            status_code=404,
        )

    # Seed the initial crop box from the face detector.
    pil_img = Image.open(io.BytesIO(staged.full_bytes)).convert("RGB")
    default_bbox = detect_face(pil_img, aspect_ratio=HEADSHOT_ASPECT_RATIO)

    return _templates().TemplateResponse(
        request=request,
        name="character/art_crop.html",
        context={
            "character": character,
            "staging_id": staging_id,
            "image_url": f"/characters/{char_id}/art/staged/{staging_id}",
            "image_width": staged.width,
            "image_height": staged.height,
            "default_bbox": list(default_bbox),
            "aspect_ratio": HEADSHOT_ASPECT_RATIO,
        },
    )


# ---------------------------------------------------------------------------
# GET /characters/{id}/art/staged/{sid} - serve the staged image bytes
# ---------------------------------------------------------------------------


@router.get("/characters/{char_id}/art/staged/{staging_id}")
def art_staged_image(
    request: Request,
    char_id: int,
    staging_id: str,
    db: Session = Depends(get_db),
):
    """Serve the staged image bytes so Cropper.js can render them.

    Same permission gate as the crop page. The bytes never hit S3 until
    the user clicks Save.
    """
    _character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    staged = art_jobs.get_staged(staging_id)
    if (
        staged is None
        or staged.char_id != char_id
        or staged.user_id != request.state.user["discord_id"]
    ):
        return Response(status_code=404)
    return Response(
        content=staged.full_bytes,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


# ---------------------------------------------------------------------------
# POST /characters/{id}/art/crop/{sid} - commit the crop
# ---------------------------------------------------------------------------


@router.post("/characters/{char_id}/art/crop/{staging_id}")
def art_crop_save(
    request: Request,
    char_id: int,
    staging_id: str,
    x: int = Form(...),
    y: int = Form(...),
    w: int = Form(...),
    h: int = Form(...),
    db: Session = Depends(get_db),
):
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    staged = art_jobs.get_staged(staging_id)
    if (
        staged is None
        or staged.char_id != char_id
        or staged.user_id != request.state.user["discord_id"]
    ):
        return RedirectResponse(
            f"/characters/{char_id}/art?art_error=expired",
            status_code=303,
        )

    bucket, region = _bucket_and_region()
    if not bucket:
        return RedirectResponse(
            f"/characters/{char_id}/art?art_error=storage_not_configured",
            status_code=303,
        )

    pil_img = Image.open(io.BytesIO(staged.full_bytes)).convert("RGB")

    # Build headshot (WebP) and encode the full art (WebP, downscaled
    # to FULL_ART_MAX_EDGE).
    headshot_bytes = art_image.build_headshot(pil_img, (x, y, w, h))
    full_bytes = art_image.encode_for_storage(pil_img, "full")

    # Upload to S3. Any failure here bubbles up to the caller - we
    # redirect to the landing page with an error marker rather than
    # 500ing the browser.
    try:
        full_key, head_key = art_storage.upload_art(
            char_id, full_bytes, headshot_bytes,
            bucket=bucket, region=region,
        )
    except Exception:
        log.exception("Art upload to S3 failed for character %s", char_id)
        return RedirectResponse(
            f"/characters/{char_id}/art?art_error=upload_failed",
            status_code=303,
        )

    # Clean up the previous art from S3 before overwriting the keys on
    # the Character row. Failures here are non-fatal - the orphan-cleanup
    # sweep in Phase 9 is the safety net.
    old_keys = [character.art_s3_key, character.headshot_s3_key]
    try:
        art_storage.delete_art(bucket, region, *old_keys)
    except Exception:
        log.exception("Old art cleanup failed for character %s", char_id)

    # Update the PUBLISHED Character row. Never flips is_published,
    # never touches an existing Draft's stats.
    character.art_s3_key = full_key
    character.headshot_s3_key = head_key
    character.art_updated_at = datetime.now(timezone.utc)
    character.art_source = staged.source
    character.art_prompt = staged.prompt
    db.commit()

    art_jobs.clear_staged(staging_id)

    return RedirectResponse(
        f"/characters/{char_id}/edit?art_saved=1",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# POST /characters/{id}/art/delete
# ---------------------------------------------------------------------------


@router.post("/characters/{char_id}/art/delete")
def art_delete(
    request: Request,
    char_id: int,
    db: Session = Depends(get_db),
):
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    if not character.art_s3_key and not character.headshot_s3_key:
        # Nothing to delete - just bounce back to the landing page.
        return RedirectResponse(
            f"/characters/{char_id}/art",
            status_code=303,
        )

    bucket, region = _bucket_and_region()
    if bucket:
        try:
            art_storage.delete_art(
                bucket, region,
                character.art_s3_key, character.headshot_s3_key,
            )
        except Exception:
            log.exception("Art delete from S3 failed for character %s", char_id)
            # Keep going - clear the columns so the UI reflects the
            # intended state. Orphan cleanup will sweep the S3 leftovers.

    character.art_s3_key = None
    character.headshot_s3_key = None
    character.art_updated_at = datetime.now(timezone.utc)
    character.art_source = None
    character.art_prompt = None
    db.commit()

    return RedirectResponse(
        f"/characters/{char_id}/edit?art_deleted=1",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Phase 7: Mad-libs prompt builder UI
#
# The wizard has three visible steps (gender -> options -> review) and
# five routes. Step 3 (assemble) is POST-only; it builds the final
# prompt, drops it in a staging slot, and redirects to the review GET.
# Phase 8 wires the submit route to kick off a real Gemini call; for
# now it's a stub that returns a 501 so the clicktests for steps 1-3
# can exercise the flow without hitting the network.
# ---------------------------------------------------------------------------


@router.get("/characters/{char_id}/art/generate", response_class=HTMLResponse)
def art_generate_gender(
    request: Request, char_id: int, db: Session = Depends(get_db),
):
    """Step 1: gender selection."""
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err
    return _templates().TemplateResponse(
        request=request,
        name="character/art_generate_gender.html",
        context={"character": character},
    )


@router.get(
    "/characters/{char_id}/art/generate/options",
    response_class=HTMLResponse,
)
def art_generate_options(
    request: Request,
    char_id: int,
    gender: str = "",
    db: Session = Depends(get_db),
):
    """Step 2: mad-libs form. Gender is carried forward via query string
    from step 1 so a refresh on this page doesn't lose the selection."""
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err
    if gender not in ("male", "female"):
        # Nudge the user back to step 1 rather than rendering a form
        # that can't produce a valid prompt.
        return RedirectResponse(
            f"/characters/{char_id}/art/generate", status_code=303,
        )
    return _templates().TemplateResponse(
        request=request,
        name="character/art_generate_options.html",
        context={
            "character": character,
            "gender": gender,
            "clan_colors": art_prompt.CLAN_COLORS,
            "default_clan": art_prompt.DEFAULT_CLAN,
            "default_age": art_prompt.DEFAULT_AGE,
            "age_min": art_prompt.AGE_MIN,
            "age_max": art_prompt.AGE_MAX,
            "armor_options": art_prompt.ARMOR_OPTIONS,
        },
    )


@router.post("/characters/{char_id}/art/generate/assemble")
def art_generate_assemble(
    request: Request,
    char_id: int,
    gender: str = Form(...),
    clan: str = Form(...),
    age: int = Form(...),
    holding: str = Form(""),
    expression: str = Form(""),
    armor: str = Form(""),
    armor_modifier: str = Form(""),
    db: Session = Depends(get_db),
):
    """Step 2 -> step 3. Builds the prompt, stages it, redirects."""
    _character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    try:
        prompt = art_prompt.assemble_prompt(
            gender=gender, clan=clan, age=age,
            holding=holding, expression=expression,
            armor=armor, armor_modifier=armor_modifier,
        )
    except ValueError:
        # Any out-of-range input bounces back to step 1. We don't try
        # to carry partial state forward - it's rare enough that a
        # clean reset is less confusing than a half-filled form.
        return RedirectResponse(
            f"/characters/{char_id}/art/generate", status_code=303,
        )

    staging_id = art_jobs.stage_art(
        user_id=request.state.user["discord_id"],
        char_id=char_id,
        source="generated",
        prompt=prompt,
    )
    return RedirectResponse(
        f"/characters/{char_id}/art/generate/review/{staging_id}",
        status_code=303,
    )


@router.get(
    "/characters/{char_id}/art/generate/review/{staging_id}",
    response_class=HTMLResponse,
)
def art_generate_review(
    request: Request,
    char_id: int,
    staging_id: str,
    db: Session = Depends(get_db),
):
    """Step 3: show the assembled prompt in an editable textarea."""
    character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    staged = art_jobs.get_staged(staging_id)
    if (
        staged is None
        or staged.char_id != char_id
        or staged.user_id != request.state.user["discord_id"]
        or staged.source != "generated"
        or not staged.prompt
    ):
        return HTMLResponse(
            "That prompt is no longer available. Please start over.",
            status_code=404,
        )
    return _templates().TemplateResponse(
        request=request,
        name="character/art_generate_review.html",
        context={
            "character": character,
            "staging_id": staging_id,
            "prompt_text": staged.prompt,
        },
    )


@router.post(
    "/characters/{char_id}/art/generate/submit/{staging_id}"
)
def art_generate_submit(
    request: Request,
    char_id: int,
    staging_id: str,
    prompt: str = Form(...),
    db: Session = Depends(get_db),
):
    """Step 3 -> Phase 8 kickoff. Stub until Phase 8 wires in Gemini.

    The user may have edited the prompt in the textarea, so we overwrite
    the staged prompt before handing off.
    """
    _character, err = _load_character_for_edit(request, db, char_id)
    if err is not None:
        return err

    staged = art_jobs.get_staged(staging_id)
    if (
        staged is None
        or staged.char_id != char_id
        or staged.user_id != request.state.user["discord_id"]
        or staged.source != "generated"
    ):
        return HTMLResponse(
            "That prompt is no longer available. Please start over.",
            status_code=404,
        )
    # Save the (possibly edited) prompt before Phase 8 reads it.
    staged.prompt = prompt
    # Phase 8 will replace this with a real redirect to the generation
    # progress page. Keep the 501 so any accidental production hit is
    # loud rather than silent.
    return HTMLResponse(
        "Art generation is not yet implemented. This wires up in Phase 8.",
        status_code=501,
    )


__all__ = ["router"]
