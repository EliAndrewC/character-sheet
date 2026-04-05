"""Discord OAuth2 authentication routes."""

import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session as AuthSession, User
from app.services.auth import is_whitelisted

router = APIRouter(prefix="/auth")

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"


def _get_redirect_uri(request: Request) -> str:
    """Build the OAuth redirect URI from the current request."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}/auth/callback"


@router.get("/login")
def login(request: Request):
    """Redirect to Discord OAuth2 authorization page."""
    client_id = os.environ.get("DISCORD_CLIENT_ID", "")
    if not client_id:
        return HTMLResponse("Discord OAuth not configured.", status_code=500)

    state = secrets.token_urlsafe(32)
    # Store state in a temporary cookie for CSRF protection
    params = {
        "client_id": client_id,
        "redirect_uri": _get_redirect_uri(request),
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    response = RedirectResponse(f"{DISCORD_AUTHORIZE_URL}?{urlencode(params)}")
    response.set_cookie("oauth_state", state, httponly=True, max_age=300, samesite="lax")
    return response


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", db: DBSession = Depends(get_db)):
    """Handle Discord OAuth2 callback."""
    # Verify state
    saved_state = request.cookies.get("oauth_state", "")
    if not state or state != saved_state:
        return HTMLResponse("Invalid OAuth state.", status_code=400)

    client_id = os.environ.get("DISCORD_CLIENT_ID", "")
    client_secret = os.environ.get("DISCORD_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return HTMLResponse("Discord OAuth not configured.", status_code=500)

    # Exchange code for token
    async with httpx.AsyncClient() as http:
        token_resp = await http.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _get_redirect_uri(request),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            return HTMLResponse(f"Failed to get token from Discord.", status_code=400)

        token_data = token_resp.json()
        access_token = token_data.get("access_token", "")

        # Get user info
        user_resp = await http.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            return HTMLResponse("Failed to get user info from Discord.", status_code=400)

        user_data = user_resp.json()

    discord_id = user_data.get("id", "")
    discord_name = user_data.get("username", "")

    # Check whitelist
    if not is_whitelisted(discord_id):
        return HTMLResponse(
            "Your Discord account is not authorized to use this application. "
            "Contact the GM to request access.",
            status_code=403,
        )

    # Upsert user
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if user:
        user.discord_name = discord_name
    else:
        user = User(
            discord_id=discord_id,
            discord_name=discord_name,
            display_name=discord_name,
        )
        db.add(user)
    db.commit()

    # Create session
    session_id = secrets.token_urlsafe(32)
    auth_session = AuthSession(session_id=session_id, discord_id=discord_id)
    db.add(auth_session)
    db.commit()

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "session_id", session_id,
        httponly=True, max_age=60 * 60 * 24 * 30,  # 30 days
        samesite="lax", secure=True,
    )
    response.delete_cookie("oauth_state")
    return response


@router.get("/logout")
def logout(request: Request, db: DBSession = Depends(get_db)):
    """Clear the session cookie and delete the server-side session."""
    session_id = request.cookies.get("session_id")
    if session_id:
        db.query(AuthSession).filter(AuthSession.session_id == session_id).delete()
        db.commit()

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_id")
    return response
