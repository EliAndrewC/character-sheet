"""L7R Character Builder — FastAPI application entry point."""

import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import init_db, SessionLocal
from app.models import Session as AuthSession, User
from app.routes import auth, characters, pages

app = FastAPI(title="L7R Character Builder")

# Templates
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)

# Static files
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


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
