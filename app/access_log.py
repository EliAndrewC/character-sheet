"""One access line per request, naming who made it.

Replaces uvicorn's own access log (muted in ``log_config``), which could
only say ``172.16.7.106 - "GET /characters/14"``: the address is Fly's proxy
for every visitor, so a whole game night's traffic looked like one person.
This line carries the real client address, the signed-in user, the status
and the time taken, with login secrets redacted:

    1.2.3.4 "GET /characters/14" 200 12ms user=3163...(marshall)

It is a pure ASGI middleware installed OUTSIDE ``AuthMiddleware``, so by the
time the response starts, ``AuthMiddleware`` has already put the user in
``scope["state"]``. It also stamps two headers on the way out:

  * ``X-App-Build`` on everything - an open tab compares it with the build
    it was rendered by (``static/js/telemetry.js``).
  * ``Reporting-Endpoints`` on pages - where Chrome sends a crash report
    for the page (``POST /client-reports``).

``ACCESS_LOG=off`` silences the line (the clicktest server sets it, as it
used to pass uvicorn ``--no-access-log``); the headers are sent regardless.
"""

from __future__ import annotations

import logging
import os
import time

from app.services.telemetry import build_id, client_ip, describe_user, redact_path

log = logging.getLogger("app.access")

REPORTING_ENDPOINTS = b'default="/client-reports"'


class _Headers:
    """Case-insensitive lookup over raw ASGI header pairs."""

    def __init__(self, raw):
        self._d = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw}

    def get(self, key, default=None):
        return self._d.get(key.lower(), default)


class AccessLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        status = {"code": 500}
        build = build_id().encode("latin-1", "replace")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-app-build", build))
                content_type = next(
                    (v for k, v in headers if k.lower() == b"content-type"), b""
                )
                if content_type.startswith(b"text/html"):
                    headers.append((b"reporting-endpoints", REPORTING_ENDPOINTS))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if os.environ.get("ACCESS_LOG", "").lower() != "off":
                self._log(scope, status["code"], started)

    @staticmethod
    def _log(scope, code, started):
        peer = scope.get("client")
        ip = client_ip(_Headers(scope.get("headers", [])), peer[0] if peer else None)
        path = redact_path(
            scope.get("path", ""), scope.get("query_string", b"").decode("latin-1")
        )
        user = describe_user((scope.get("state") or {}).get("user"))
        ms = int((time.monotonic() - started) * 1000)
        log.info('%s "%s %s" %d %dms user=%s',
                 ip, scope.get("method", "-"), path, code, ms, user)
