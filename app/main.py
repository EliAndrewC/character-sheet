"""L7R Character Builder — FastAPI application entry point."""

import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import init_db, SessionLocal
from app.models import Session as AuthSession, User
from app.routes import auth, characters, pages
from app.services.auth import is_admin

app = FastAPI(title="L7R Character Builder")

# Templates
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)
# Make is_admin available to all templates so the admin nav link can be gated
# without every route having to pass it in the context.
templates.env.globals["is_admin"] = is_admin

# Static files
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# Cache-busting helper for static assets. Returns the file's mtime as an
# integer string so that any change to the asset (post-redeploy) gets a fresh
# URL. Cached per process for O(1) lookup after the first call.
_static_versions: dict[str, str] = {}


def static_v(path: str) -> str:
    if path in _static_versions:
        return _static_versions[path]
    full = os.path.join(_static_dir, path)
    try:
        v = str(int(os.path.getmtime(full)))
    except OSError:
        v = "0"
    _static_versions[path] = v
    return v


templates.env.globals["static_v"] = static_v


# ---------------------------------------------------------------------------
# Auth middleware: sets request.state.user from session cookie or test bypass
# ---------------------------------------------------------------------------

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = None

        # Test bypass: X-Test-User header in test mode
        if os.environ.get("TEST_AUTH_BYPASS") == "true":
            test_header = request.headers.get("X-Test-User")
            if test_header and ":" in test_header:
                discord_id, discord_name = test_header.split(":", 1)
                request.state.user = {
                    "discord_id": discord_id,
                    "discord_name": discord_name,
                    "display_name": discord_name,
                }
                return await call_next(request)

        # Normal: check session cookie
        session_id = request.cookies.get("session_id")
        if session_id:
            db = SessionLocal()
            try:
                auth_session = (
                    db.query(AuthSession)
                    .filter(AuthSession.session_id == session_id)
                    .first()
                )
                if auth_session:
                    user = (
                        db.query(User)
                        .filter(User.discord_id == auth_session.discord_id)
                        .first()
                    )
                    if user:
                        request.state.user = user.to_dict()
            finally:
                db.close()

        return await call_next(request)


app.add_middleware(AuthMiddleware)

# Routes
app.include_router(pages.router)
app.include_router(characters.router)
app.include_router(auth.router)


@app.on_event("startup")
def on_startup():
    init_db()
    _seed_campaign_players()


def _seed_campaign_players():
    """Pre-create User records for all campaign players so they appear in
    dropdowns even before they log in via Discord."""
    from app.game_data import CAMPAIGN_PLAYERS

    db = SessionLocal()
    try:
        for discord_id, display_name in CAMPAIGN_PLAYERS.items():
            existing = db.query(User).filter(User.discord_id == discord_id).first()
            if not existing:
                db.add(User(
                    discord_id=discord_id,
                    discord_name=display_name,
                    display_name=display_name,
                ))
        db.commit()
    finally:
        db.close()
