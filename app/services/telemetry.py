"""Diagnostics: who made a request, which build a tab is running, and the
reports browsers send back when something goes wrong on their side.

Written after a player's tab crashed mid-session (2026-09-21) and the logs
could not say whose tab it was or whether we were to blame: every request
arrived from the same Fly proxy address and no line named a user. Four
pieces, all landing in the ordinary app log on the persistent volume (see
``log_config.py``) - no third-party service, no S3:

  1. ``app.access_log.AccessLogMiddleware`` writes one access line per
     request naming the user and the real client address (``describe_user``,
     ``client_ip``), with secrets in login URLs redacted (``redact_path``).
  2. ``POST /client-log`` receives JavaScript errors and "that tab ended
     without closing" reports from ``static/js/telemetry.js``
     (``sanitize_client_report``).
  3. ``POST /client-reports`` receives Chrome's own crash reports (the
     Reporting API; ``crash_reports``), which can arrive even when no page
     of ours ever runs again.
  4. ``build_id()`` stamps every response with ``X-App-Build`` and every
     page with ``data-build``, so an open tab can tell it is out of date.

Everything a browser sends is untrusted: unknown keys are dropped, strings
are truncated, and the free-text fields are written out as JSON so a
message cannot forge a log line.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque

# ---------------------------------------------------------------------------
# Build id
# ---------------------------------------------------------------------------


def build_id() -> str:
    """An identifier that changes when a new version is deployed.

    ``APP_BUILD_ID`` wins when set (tests, and an escape hatch). Otherwise
    Fly's ``FLY_IMAGE_REF`` (``registry.fly.io/<app>:deployment-01K...``),
    whose tag is new for every ``fly deploy`` but NOT for ``fly secrets
    set``, which restarts the machine on the same image - a secrets change
    must not tell every open tab to reload. Locally neither is set and the
    id is ``dev``, so a dev server never asks anyone to reload."""
    explicit = os.environ.get("APP_BUILD_ID", "").strip()
    if explicit:
        return explicit
    ref = os.environ.get("FLY_IMAGE_REF", "").strip()
    if ref:
        return ref.rsplit(":", 1)[-1] or ref
    return "dev"


# ---------------------------------------------------------------------------
# Access-line helpers
# ---------------------------------------------------------------------------

# Paths whose last segment IS a credential. A magic-login UUID signs the
# holder in (as an admin, for an admin's id), so it must never reach a log.
_SECRET_SEGMENT = re.compile(r"^(/auth/(?:magic-login|test-login)/)[^/?]+")
# OAuth callbacks carry a one-time code and the CSRF state in the query.
_SECRET_QUERY_PATHS = ("/auth/callback", "/auth/google/callback")


def redact_path(path: str, query: str = "") -> str:
    """``path`` plus ``?query``, with credentials replaced by ``[redacted]``."""
    path = _SECRET_SEGMENT.sub(r"\1[redacted]", path)
    if query and path in _SECRET_QUERY_PATHS:
        query = "[redacted]"
    return f"{path}?{query}" if query else path


_UNSAFE = re.compile(r"[^\w.@-]+")


def describe_user(user) -> str:
    """``<discord_id>(<name>)`` for a signed-in viewer, ``-`` otherwise.

    The id is what joins against the database; the name is there so a
    person reading the log does not have to look it up. Whitespace and
    anything else that could break the line apart is squashed."""
    if not isinstance(user, dict) or not user.get("discord_id"):
        return "-"
    uid = _UNSAFE.sub("_", str(user["discord_id"]))[:40]
    name = user.get("display_name") or user.get("discord_name") or ""
    name = _UNSAFE.sub("_", str(name)).strip("_")[:40]
    return f"{uid}({name})" if name else uid


def client_ip(headers, fallback: str | None) -> str:
    """The visitor's address. Behind Fly every connection comes from the
    proxy, so the peer address is useless; Fly puts the real one in
    ``Fly-Client-IP``. The header is only trusted as far as it is
    well-formed - it goes in a log line, not an access decision."""
    raw = (headers.get("fly-client-ip") or "").strip()
    if raw and re.fullmatch(r"[0-9A-Fa-f:.]{2,45}", raw):
        return raw
    return fallback or "-"


# ---------------------------------------------------------------------------
# Throttle: the report endpoints are public, so bound what they can write.
# ---------------------------------------------------------------------------


class Throttle:
    """At most ``limit`` events per ``window`` seconds, process-wide.

    The browser side already caps itself per page load; this is the backstop
    against a script (or a runaway loop) filling the volume. Deliberately
    global rather than per-client: the whole campaign produces a handful of
    reports on a bad night, so any limit a real night could hit is far above
    anything that matters."""

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()
        self.dropped = 0

    def allow(self) -> bool:
        now = self._clock()
        with self._lock:
            while self._hits and now - self._hits[0] >= self.window:
                self._hits.popleft()
            if len(self._hits) >= self.limit:
                self.dropped += 1
                return False
            self._hits.append(now)
            return True


# ---------------------------------------------------------------------------
# Reports from our own script (POST /client-log)
# ---------------------------------------------------------------------------

# kind -> log level name. "resumed" is the all-clear for an earlier
# "unclean_exit": a tab the browser had frozen came back after another tab
# gave it up for dead.
CLIENT_KINDS = {
    "error": "WARNING",
    "rejection": "WARNING",
    "unclean_exit": "WARNING",
    "discarded": "WARNING",
    "resumed": "INFO",
}

# field -> (type, max length for strings)
_CLIENT_FIELDS = {
    "tab": (str, 16),
    "build": (str, 64),
    "page": (str, 300),
    "message": (str, 500),
    "source": (str, 300),
    "line": (int, None),
    "col": (int, None),
    "stack": (str, 2000),
    "expression": (str, 300),
    "up": (int, None),          # seconds the page had been open
    "heap": (int, None),        # MB of JS heap at the last sample (Chrome only)
    "heap_start": (int, None),  # MB at the first sample
    "heap_max": (int, None),    # largest sample
    "ago": (int, None),         # seconds since the dead tab was last seen
    "vis": (str, 12),           # visibility at the last heartbeat
}

MAX_CLIENT_BODY = 16 * 1024


def _coerce(value, kind, limit):
    if kind is int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return int(value)
    if not isinstance(value, str):
        return None
    return value[:limit]


def sanitize_client_report(data) -> dict | None:
    """Keep only the known fields of a ``/client-log`` body, typed and
    truncated. ``None`` when it is not a report at all (not an object, or
    an unknown ``kind``)."""
    if not isinstance(data, dict) or data.get("kind") not in CLIENT_KINDS:
        return None
    out = {"kind": data["kind"]}
    for key, (kind, limit) in _CLIENT_FIELDS.items():
        if key in data:
            value = _coerce(data[key], kind, limit)
            if value is not None:
                out[key] = value
    return out


def format_client_report(report: dict, user_desc: str, ip: str) -> str:
    """One log line. The routing fields come first so the line greps well;
    everything else, free text included, rides in a JSON tail."""
    head = (
        f"client-{report['kind']} user={user_desc} ip={ip}"
        f" tab={report.get('tab', '-')} build={report.get('build', '-')}"
        f" page={json.dumps(report.get('page', '-'))}"
    )
    rest = {
        k: v for k, v in report.items() if k not in ("kind", "tab", "build", "page")
    }
    return f"{head} {json.dumps(rest, sort_keys=True)}" if rest else head


# ---------------------------------------------------------------------------
# Chrome's Reporting API (POST /client-reports)
# ---------------------------------------------------------------------------

MAX_REPORTS_BODY = 64 * 1024


def crash_reports(data) -> list[dict]:
    """The ``crash`` entries of a Reporting API batch, flattened.

    The batch is a JSON array of ``{type, age, url, user_agent, body}``.
    Chrome sends it WITHOUT cookies, so there is no user to name; the url
    (which character) and the time are what tie it to a person. The same
    endpoint also receives deprecation and intervention reports, which are
    dropped here - they are about the browser's API surface, not about
    whether a tab died."""
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict) or item.get("type") != "crash":
            continue
        body = item.get("body") if isinstance(item.get("body"), dict) else {}
        out.append({
            "url": _coerce(item.get("url"), str, 300),
            "age_ms": _coerce(item.get("age"), int, None),
            "user_agent": _coerce(item.get("user_agent"), str, 300),
            # "oom" and "unresponsive" are the two Chrome currently sends;
            # absent means the crash had some other cause.
            "reason": _coerce(body.get("reason"), str, 40),
            "stack": _coerce(body.get("stack"), str, 2000),
            "is_top_level": body.get("is_top_level") if isinstance(
                body.get("is_top_level"), bool) else None,
            "visibility": _coerce(body.get("page_visibility"), str, 12),
        })
    return out


def format_crash_report(report: dict, ip: str) -> str:
    fields = {k: v for k, v in report.items() if v is not None}
    return f"browser-crash ip={ip} {json.dumps(fields, sort_keys=True)}"
