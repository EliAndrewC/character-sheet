"""Where browsers report trouble. See ``app/services/telemetry.py``.

Both endpoints are public (a logged-out page can crash too), touch no
database, and answer ``204`` with nothing to read. What they write goes to
the app log only, bounded by a process-wide throttle and a body-size cap.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, Response

from app.services.telemetry import (
    CLIENT_KINDS,
    MAX_CLIENT_BODY,
    MAX_REPORTS_BODY,
    Throttle,
    client_ip,
    crash_reports,
    describe_user,
    format_client_report,
    format_crash_report,
    sanitize_client_report,
)

router = APIRouter()
log = logging.getLogger("app.client")

# A bad night is a handful of reports; 60 a minute is a runaway, not a crash.
throttle = Throttle(limit=60, window=60.0)


async def _read_json(request: Request, cap: int):
    """The body parsed as JSON, or a ``Response`` explaining why not."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > cap:
        return Response(status_code=413)
    body = await request.body()
    if len(body) > cap:
        return Response(status_code=413)
    try:
        return json.loads(body)
    except ValueError:
        return Response(status_code=400)


def _throttled() -> Response | None:
    if throttle.allow():
        return None
    # Say so once per burst, not once per dropped report.
    if throttle.dropped == 1 or throttle.dropped % 100 == 0:
        log.warning("client reports throttled (%d dropped so far)", throttle.dropped)
    return Response(status_code=429)


@router.post("/client-log")
async def client_log(request: Request):
    """A report from ``static/js/telemetry.js``: an uncaught error or
    rejection, a tab that ended without closing, or the all-clear for one.
    Sent with ``sendBeacon``, which carries the session cookie, so the line
    names the user even though nobody is waiting on the answer."""
    data = await _read_json(request, MAX_CLIENT_BODY)
    if isinstance(data, Response):
        return data
    report = sanitize_client_report(data)
    if report is None:
        return Response(status_code=400)
    blocked = _throttled()
    if blocked:
        return blocked
    line = format_client_report(
        report,
        describe_user(getattr(request.state, "user", None)),
        client_ip(request.headers, request.client.host if request.client else None),
    )
    log.log(logging.getLevelName(CLIENT_KINDS[report["kind"]]), "%s", line)
    return Response(status_code=204)


@router.post("/client-reports")
async def client_reports(request: Request):
    """Chrome's Reporting API endpoint, named by the ``Reporting-Endpoints``
    header on every page (``app/access_log.py``). Only crash reports are
    kept. Chrome queues these in the browser process, so one arrives even
    when the crashed tab is never reopened - the case our own script can't
    see."""
    data = await _read_json(request, MAX_REPORTS_BODY)
    if isinstance(data, Response):
        return data
    reports = crash_reports(data)
    if reports:
        ip = client_ip(request.headers, request.client.host if request.client else None)
        for report in reports:
            if _throttled():
                break
            log.warning("%s", format_crash_report(report, ip))
    return Response(status_code=204)
