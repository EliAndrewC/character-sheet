"""L7R Character Builder — FastAPI application entry point."""

import logging
import os
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import init_db, SessionLocal
from app.models import Session as AuthSession, User
from app.routes import art, auth, characters, google_sheets, import_char, pages
from app.services.auth import is_admin
from app.services.import_rate_limit import import_enabled

log = logging.getLogger(__name__)

app = FastAPI(title="L7R Character Builder")

# Templates
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)
# Make is_admin available to all templates so the admin nav link can be gated
# without every route having to pass it in the context.
templates.env.globals["is_admin"] = is_admin
# Read at request time so toggling the kill switch doesn't require a
# template reload - matches how the /import route itself reads it.
templates.env.globals["import_enabled"] = import_enabled


def get_backup_error():
    """Return backup error string for admin banner, or None."""
    return backup_status.get("last_error")


templates.env.globals["get_backup_error"] = get_backup_error

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


# Character art URL helper. Returns the public S3 URL for a character's
# headshot (or None if the character has no art or S3 isn't configured).
# The art bucket objects are public-read so no signing is needed; we
# append ``art_updated_at`` as a cache-buster so replacing a character's
# art invalidates any in-flight CDN / browser cache entries.
def _art_url_for_key(char, key_attr: str) -> str | None:
    key = getattr(char, key_attr, None)
    if not key:
        return None
    bucket = os.environ.get("S3_BACKUP_BUCKET")
    if not bucket:
        return None
    region = os.environ.get("S3_BACKUP_REGION", "us-east-1")
    from app.services.art_storage import public_url
    url = public_url(key, bucket=bucket, region=region)
    updated = getattr(char, "art_updated_at", None)
    if updated is not None:
        # ``public_url`` now returns a presigned URL with its own query
        # string, so the cache-bust has to be appended with ``&`` rather
        # than ``?``. In stub mode (disk-backed test server) there is no
        # existing query string, so fall back to ``?``.
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}v={int(updated.timestamp())}"
    return url


def headshot_url(char) -> str | None:
    return _art_url_for_key(char, "headshot_s3_key")


def full_art_url(char) -> str | None:
    return _art_url_for_key(char, "art_s3_key")


templates.env.globals["headshot_url"] = headshot_url
templates.env.globals["full_art_url"] = full_art_url

# Kill-switch check for the "Generate with AI" dropdown entry on the
# edit page. Read at request time so toggling the env var doesn't need
# a restart (mirrors how ``import_enabled`` is wired above).
from app.services.art_rate_limit import art_gen_enabled as _art_gen_enabled
templates.env.globals["art_gen_enabled"] = _art_gen_enabled


# Per-school rules-link substitutions for the "Special Ability" text. When a
# school's ability quotes a rules section that lives in the upstream L7R
# repo, we wrap the named phrase in an anchor tag so players can jump to it.
_SPECIAL_ABILITY_LINKS: dict[str, tuple[str, str]] = {
    "priest": (
        "all 10 rituals",
        "https://github.com/EliAndrewC/l7r/blob/master/rules/09-professions.md#priest-rituals",
    ),
}


def school_special_ability_html(school) -> Markup:
    """Render a school's special ability as HTML, linkifying any phrase that
    points at a rules section (currently just the Priest's "all 10 rituals")."""
    text = school.special_ability or ""
    link = _SPECIAL_ABILITY_LINKS.get(school.id) if school else None
    if link:
        phrase, url = link
        before, sep, after = text.partition(phrase)
        if sep:
            return Markup(
                f'{escape(before)}'
                f'<a href="{escape(url)}" target="_blank" rel="noopener" '
                f'class="text-accent hover:underline">{escape(sep)}</a>'
                f'{escape(after)}'
            )
    return Markup(escape(text))


templates.env.globals["school_special_ability_html"] = school_special_ability_html


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
app.include_router(google_sheets.router)
app.include_router(import_char.router)
app.include_router(art.router)


# Global backup status (read by routes for admin banner)
backup_status = {"last_success": None, "last_error": None, "in_progress": False}


@app.on_event("startup")
def on_startup():
    init_db()
    _seed_campaign_players()
    threading.Thread(target=_check_and_backup, daemon=True).start()


def _check_and_backup():
    """Background thread: check if backup is needed, run if so.

    Waits 30 seconds after startup before importing boto3 to avoid
    memory pressure during the critical startup window when Fly.io
    health checks are running.
    """
    import time
    time.sleep(30)

    from app.services.backup import get_last_backup_time, run_backup, should_backup

    try:
        bucket = os.environ.get("S3_BACKUP_BUCKET")
        if not bucket:
            return  # No backup configured, skip silently

        region = os.environ.get("S3_BACKUP_REGION", "us-east-1")
        db_path = os.environ.get("DATABASE_URL", "l7r.db")

        last = get_last_backup_time(bucket, region)
        now = datetime.now(timezone.utc)
        if not should_backup(last, now):
            backup_status["last_success"] = last
            log.info("Backup not needed (last: %s)", last)
            return

        backup_status["in_progress"] = True
        result = run_backup(db_path, bucket, region)
        backup_status["in_progress"] = False

        if result["success"]:
            backup_status["last_success"] = now
            backup_status["last_error"] = None
            log.info("Backup completed: %s", result["key"])
            # Sweep orphaned character-art S3 objects after the DB
            # snapshot lands. Only runs on a successful backup so a
            # credentials failure shows up as "backup failed" in the
            # admin banner rather than being overwritten by a
            # downstream symptom.
            _sweep_art_orphans(bucket, region)
        else:
            backup_status["last_error"] = result["error"]
            log.error("Backup failed: %s", result["error"])
    except Exception as e:
        backup_status["in_progress"] = False
        backup_status["last_error"] = str(e)
        log.error("Backup check failed: %s", e)


def _sweep_art_orphans(bucket: str, region: str):
    """Run the art-orphan cleanup sweep; record errors on backup_status."""
    try:
        from app.services.art_backup import cleanup_orphans
        db = SessionLocal()
        try:
            cleanup_orphans(db, bucket=bucket, region=region)
        finally:
            db.close()
    except Exception as e:
        backup_status["last_error"] = f"Art orphan cleanup failed: {e}"
        log.error("Art orphan cleanup failed: %s", e)


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
