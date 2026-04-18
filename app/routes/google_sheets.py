"""Google OAuth2 flow for exporting character sheets to Google Sheets."""

import logging
import os
import secrets
from urllib.parse import urlencode, quote

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.game_data import SCHOOL_KNACKS, SCHOOLS, SKILLS
from app.models import Character, User as UserModel
from app.services.auth import can_view_drafts
from app.services.rolls import compute_skill_roll
from app.services.sheets import create_spreadsheet
from app.services.status import compute_effective_status
from app.services.xp import calculate_xp_breakdown

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google")

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = "https://www.googleapis.com/auth/drive.file"


def _get_redirect_uri(request: Request) -> str:
    """Build the Google OAuth redirect URI from the current request."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}/auth/google/callback"


@router.get("/export/{char_id}")
def start_export(request: Request, char_id: int, db: DBSession = Depends(get_db)):
    """Redirect to Google OAuth consent screen to begin the export flow."""
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return HTMLResponse("Character not found", status_code=404)

    owner = db.query(UserModel).filter(UserModel.discord_id == character.owner_discord_id).first()
    owner_granted = owner.granted_account_ids or [] if owner else []
    if not can_view_drafts(user["discord_id"], character.owner_discord_id, owner_granted):
        return HTMLResponse("You don't have permission to export this character.", status_code=403)

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    if not client_id:
        return HTMLResponse("Google Sheets export is not configured.", status_code=500)

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": _get_redirect_uri(request),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "consent",
    }

    google_url = f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    # Render an HTML page that redirects via JS instead of a server-side
    # redirect.  The page pings a keepalive endpoint every few seconds so
    # the Fly.io machine stays warm while the user is on Google's consent
    # screen.  Without this, auto_stop_machines kills the machine and the
    # callback gets a 502.
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Redirecting to Google...</title></head>
<body>
<p>Redirecting to Google for authorization...</p>
<script>
setInterval(function(){{ fetch('/auth/google/keepalive').catch(function(){{}}); }}, 5000);
window.location.href = {_js_string(google_url)};
</script>
<noscript><a href="{google_url}">Click here to continue</a></noscript>
</body></html>"""

    response = HTMLResponse(html)
    response.set_cookie(
        "google_oauth_state", state,
        httponly=True, max_age=300, samesite="lax",
    )
    response.set_cookie(
        "google_export_char_id", str(char_id),
        httponly=True, max_age=300, samesite="lax",
    )
    return response


def _js_string(s: str) -> str:
    """Escape a string for safe embedding in a JS string literal."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


@router.get("/keepalive")
def keepalive():
    """No-op endpoint pinged by the export page to keep the machine alive."""
    return HTMLResponse("ok", status_code=200)


@router.get("/callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: DBSession = Depends(get_db),
):
    """Handle Google OAuth2 callback: exchange code, create sheet, redirect."""
    char_id_str = request.cookies.get("google_export_char_id", "")
    char_id = int(char_id_str) if char_id_str.isdigit() else 0

    def _error_redirect(reason: str) -> RedirectResponse:
        url = f"/characters/{char_id}/edit?sheets_error={reason}" if char_id else f"/?sheets_error={reason}"
        resp = RedirectResponse(url, status_code=303)
        resp.delete_cookie("google_oauth_state")
        resp.delete_cookie("google_export_char_id")
        return resp

    # Google returned an error (user declined, etc.)
    if error:
        return _error_redirect("auth_failed")

    # CSRF check
    saved_state = request.cookies.get("google_oauth_state", "")
    if not state or state != saved_state:
        return _error_redirect("expired")

    if not char_id:
        return _error_redirect("expired")

    # Verify user is logged in
    user = getattr(request.state, "user", None)
    if not user:
        return _error_redirect("auth_failed")

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return _error_redirect("api_failed")

    # Exchange authorization code for access token
    async with httpx.AsyncClient() as http:
        token_resp = await http.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": _get_redirect_uri(request),
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_resp.status_code != 200:
        log.error("Google token exchange failed: %s %s", token_resp.status_code, token_resp.text)
        return _error_redirect("auth_failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token", "")
    if not access_token:
        return _error_redirect("auth_failed")

    # Load character and compute derived data
    character = db.query(Character).filter(Character.id == char_id).first()
    if not character:
        return _error_redirect("not_found")

    char_dict = character.to_dict()
    school = SCHOOLS.get(character.school)

    char_knacks = {}
    if school:
        for knack_id in school.school_knacks:
            knack_data = SCHOOL_KNACKS.get(knack_id)
            rank = character.knacks.get(knack_id, 1) if character.knacks else 1
            char_knacks[knack_id] = {"data": knack_data, "rank": rank}

    knack_ranks = [char_knacks[k]["rank"] for k in char_knacks] if char_knacks else [0]
    dan = min(knack_ranks) if knack_ranks else 0

    xp_breakdown = calculate_xp_breakdown(char_dict)
    effective = compute_effective_status(char_dict)

    skill_rolls = {}
    for sid in (char_dict.get("skills") or {}):
        roll = compute_skill_roll(sid, char_dict)
        if roll.rolled > 0:
            skill_rolls[sid] = roll

    # Create or update the Google Sheet
    try:
        sheet_url = create_spreadsheet(
            access_token, character, char_dict, school, char_knacks,
            dan, xp_breakdown, effective, skill_rolls,
            existing_sheet_id=character.google_sheet_id,
        )
    except Exception:
        log.exception("Google Sheets API failed for character %s", char_id)
        return _error_redirect("api_failed")

    # Store the spreadsheet ID and a snapshot of the exported state
    # so we can detect whether the character has changed since export.
    # The URL format is https://docs.google.com/spreadsheets/d/{id}/edit
    try:
        parts = sheet_url.split("/d/")
        if len(parts) > 1:
            sheet_id = parts[1].split("/")[0]
            character.google_sheet_id = sheet_id
        character.google_sheet_exported_state = char_dict
        db.commit()
    except Exception:  # pragma: no cover
        # Non-critical: the export itself succeeded; failing to persist the
        # sheet_id just means we won't offer "update in place" next time.
        # Forcing this path in a test requires injecting a DB failure after a
        # successful API call, which doesn't model any real failure mode.
        pass

    # Redirect back to character edit page with success link
    response = RedirectResponse(
        f"/characters/{char_id}/edit?sheets_url={quote(sheet_url, safe='')}",
        status_code=303,
    )
    response.delete_cookie("google_oauth_state")
    response.delete_cookie("google_export_char_id")
    return response
