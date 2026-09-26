"""Diagnostics: the access line, the build header, and the two endpoints
browsers report trouble to. See ``app/services/telemetry.py``.

The browser half (error capture, dead-tab detection, the update banner) is
pure-tested in ``tests/js/telemetry.test.js`` and clicktested in
``tests/e2e/test_telemetry.py``.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import telemetry as telemetry_routes
from app.services import telemetry as T

VIEWER = "183026066498125825"


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.delenv("APP_BUILD_ID", raising=False)
    monkeypatch.delenv("FLY_IMAGE_REF", raising=False)
    monkeypatch.delenv("ACCESS_LOG", raising=False)
    # A fresh throttle per test, so one test's reports can't starve the next.
    monkeypatch.setattr(telemetry_routes, "throttle", T.Throttle(limit=60, window=60.0))


def _lines(caplog, logger):
    return [r.getMessage() for r in caplog.records if r.name == logger]


# ---------------------------------------------------------------------------
# build_id
# ---------------------------------------------------------------------------


class TestBuildId:
    def test_dev_when_nothing_is_set(self):
        assert T.build_id() == "dev"

    def test_fly_image_tag(self, monkeypatch):
        monkeypatch.setenv(
            "FLY_IMAGE_REF", "registry.fly.io/l7r-character-sheet:deployment-01K5ABC"
        )
        assert T.build_id() == "deployment-01K5ABC"

    def test_fly_image_ref_without_a_tag_is_used_whole(self, monkeypatch):
        monkeypatch.setenv("FLY_IMAGE_REF", "registry.fly.io/app:")
        assert T.build_id() == "registry.fly.io/app:"
        monkeypatch.setenv("FLY_IMAGE_REF", "sha256abc")
        assert T.build_id() == "sha256abc"

    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("FLY_IMAGE_REF", "registry.fly.io/app:deployment-1")
        monkeypatch.setenv("APP_BUILD_ID", " e2e-build ")
        assert T.build_id() == "e2e-build"


# ---------------------------------------------------------------------------
# Access-line helpers
# ---------------------------------------------------------------------------


class TestRedactPath:
    @pytest.mark.parametrize("path, query, expected", [
        ("/characters/14", "", "/characters/14"),
        ("/keepalive", "tab=a&heap=80", "/keepalive?tab=a&heap=80"),
        ("/auth/magic-login/1f0e-uuid", "", "/auth/magic-login/[redacted]"),
        ("/auth/test-login/1f0e-uuid", "", "/auth/test-login/[redacted]"),
        ("/auth/callback", "code=abc&state=xyz", "/auth/callback?[redacted]"),
        ("/auth/google/callback", "code=abc", "/auth/google/callback?[redacted]"),
        ("/auth/callback", "", "/auth/callback"),
    ])
    def test_redaction(self, path, query, expected):
        assert T.redact_path(path, query) == expected


class TestDescribeUser:
    def test_anonymous(self):
        assert T.describe_user(None) == "-"
        assert T.describe_user({}) == "-"
        assert T.describe_user("nope") == "-"

    def test_id_and_display_name(self):
        assert T.describe_user(
            {"discord_id": "316", "display_name": "Marshall", "discord_name": "m"}
        ) == "316(Marshall)"

    def test_falls_back_to_discord_name_then_id_alone(self):
        assert T.describe_user({"discord_id": "316", "discord_name": "m z"}) == "316(m_z)"
        assert T.describe_user({"discord_id": "316"}) == "316"

    def test_nothing_can_break_the_line(self):
        out = T.describe_user({"discord_id": "31 6\n", "display_name": 'x" user=admin\n'})
        assert " " not in out and "\n" not in out and '"' not in out


class _H(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class TestClientIp:
    def test_fly_header_wins(self):
        assert T.client_ip(_H({"fly-client-ip": "203.0.113.9"}), "172.16.7.106") == "203.0.113.9"
        assert T.client_ip(_H({"fly-client-ip": "2001:db8::1"}), "x") == "2001:db8::1"

    def test_malformed_header_is_ignored(self):
        assert T.client_ip(_H({"fly-client-ip": "evil user=admin"}), "10.0.0.1") == "10.0.0.1"

    def test_no_header_no_peer(self):
        assert T.client_ip(_H(), None) == "-"


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


def test_throttle_limits_within_the_window_and_recovers():
    now = [0.0]
    t = T.Throttle(limit=2, window=10.0, clock=lambda: now[0])
    assert t.allow() and t.allow()
    assert t.allow() is False
    assert t.dropped == 1
    now[0] = 10.0
    assert t.allow() is True


# ---------------------------------------------------------------------------
# The access-log middleware
# ---------------------------------------------------------------------------


class TestAccessLog:
    def test_line_names_user_real_ip_status_and_time(self, client, caplog):
        caplog.set_level(logging.INFO, logger="app.access")
        client.get("/terms", headers={"Fly-Client-IP": "203.0.113.9"})
        [line] = [l for l in _lines(caplog, "app.access") if "/terms" in l]
        assert line.startswith('203.0.113.9 "GET /terms" 200 ')
        assert line.endswith(f"ms user={VIEWER}(testplayer)")

    def test_anonymous_request(self, caplog):
        caplog.set_level(logging.INFO, logger="app.access")
        with TestClient(app) as anon:
            anon.get("/keepalive?tab=abc&heap=88")
        [line] = _lines(caplog, "app.access")
        assert '"GET /keepalive?tab=abc&heap=88" 200' in line
        assert line.endswith("user=-")

    def test_magic_login_secret_never_reaches_the_log(self, caplog):
        caplog.set_level(logging.INFO, logger="app.access")
        with TestClient(app, follow_redirects=False) as anon:
            anon.get("/auth/magic-login/00000000-secret-uuid")
        text = "\n".join(_lines(caplog, "app.access"))
        assert "secret-uuid" not in text
        assert "/auth/magic-login/[redacted]" in text

    def test_can_be_switched_off(self, client, caplog, monkeypatch):
        monkeypatch.setenv("ACCESS_LOG", "off")
        caplog.set_level(logging.INFO, logger="app.access")
        resp = client.get("/keepalive")
        assert _lines(caplog, "app.access") == []
        # The headers do not depend on the log.
        assert resp.headers["x-app-build"] == "dev"

    def test_a_crashing_route_is_still_logged_as_500(self, caplog):
        from fastapi import FastAPI
        from app.access_log import AccessLogMiddleware

        inner = FastAPI()

        @inner.get("/boom")
        def boom():
            raise RuntimeError("kaboom")

        inner.add_middleware(AccessLogMiddleware)
        caplog.set_level(logging.INFO, logger="app.access")
        with TestClient(inner, raise_server_exceptions=False) as c:
            assert c.get("/boom").status_code == 500
        [line] = _lines(caplog, "app.access")
        assert '"GET /boom" 500' in line

    def test_non_http_scopes_pass_straight_through(self):
        import asyncio
        from app.access_log import AccessLogMiddleware

        seen = []

        async def inner(scope, receive, send):
            seen.append(scope["type"])

        asyncio.run(AccessLogMiddleware(inner)({"type": "lifespan"}, None, None))
        assert seen == ["lifespan"]

    def test_missing_peer_address(self, caplog):
        import asyncio
        from app.access_log import AccessLogMiddleware

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})

        async def send(message):
            pass

        caplog.set_level(logging.INFO, logger="app.access")
        asyncio.run(AccessLogMiddleware(inner)(
            {"type": "http", "method": "GET", "path": "/x", "headers": []}, None, send,
        ))
        [line] = _lines(caplog, "app.access")
        assert line.startswith('- "GET /x" 204')


class TestHeaders:
    def test_every_response_names_the_build(self, client, monkeypatch):
        monkeypatch.setenv("APP_BUILD_ID", "b42")
        assert client.get("/keepalive").headers["x-app-build"] == "b42"
        assert client.get("/terms").headers["x-app-build"] == "b42"

    def test_pages_name_the_reporting_endpoint(self, client):
        page = client.get("/terms")
        assert page.headers["reporting-endpoints"] == 'default="/client-reports"'
        # Not on non-HTML responses: only a document can have crash reports.
        assert "reporting-endpoints" not in client.get("/keepalive").headers

    def test_page_is_stamped_with_its_build(self, client, monkeypatch):
        monkeypatch.setenv("APP_BUILD_ID", "b42")
        html = client.get("/terms").text
        assert 'data-build="b42"' in html
        assert "/static/js/telemetry.js?v=" in html
        assert 'id="update-banner" hidden' in html


# ---------------------------------------------------------------------------
# POST /client-log
# ---------------------------------------------------------------------------


class TestSanitizeClientReport:
    def test_rejects_non_reports(self):
        assert T.sanitize_client_report([]) is None
        assert T.sanitize_client_report({"kind": "nope"}) is None
        assert T.sanitize_client_report({}) is None

    def test_keeps_known_fields_typed_and_truncated(self):
        out = T.sanitize_client_report({
            "kind": "error", "message": "m" * 900, "line": 12.7, "col": "3",
            "up": True, "heap": float("nan"), "ago": float("inf"), "evil": "x",
            "tab": 5, "stack": "s" * 5000,
        })
        assert out == {"kind": "error", "message": "m" * 500, "line": 12, "stack": "s" * 2000}


class TestClientLog:
    def test_error_report_is_logged_with_the_user(self, client, caplog):
        caplog.set_level(logging.INFO, logger="app.client")
        resp = client.post("/client-log", content=json.dumps({
            "kind": "error", "tab": "t1", "build": "b1", "page": "/characters/14",
            "message": "TypeError: x is undefined\nuser=admin", "line": 3,
        }), headers={"Fly-Client-IP": "203.0.113.9"})
        assert resp.status_code == 204
        [rec] = [r for r in caplog.records if r.name == "app.client"]
        assert rec.levelno == logging.WARNING
        line = rec.getMessage()
        assert line.startswith(
            f'client-error user={VIEWER}(testplayer) ip=203.0.113.9 tab=t1 build=b1'
            ' page="/characters/14" '
        )
        # Free text is JSON-escaped: a newline cannot start a forged line.
        assert "\n" not in line
        assert json.loads(line.split(" ", 6)[6]) == {
            "line": 3, "message": "TypeError: x is undefined\nuser=admin",
        }

    def test_resumed_is_info_and_minimal_lines_have_no_tail(self, client, caplog):
        caplog.set_level(logging.INFO, logger="app.client")
        client.post("/client-log", content='{"kind": "resumed"}')
        [rec] = [r for r in caplog.records if r.name == "app.client"]
        assert rec.levelno == logging.INFO
        assert rec.getMessage().endswith('tab=- build=- page="-"')

    @pytest.mark.parametrize("body, status", [
        ("{nope", 400),
        ('{"kind": "unknown"}', 400),
        ('["error"]', 400),
    ])
    def test_bad_bodies(self, client, body, status, caplog):
        caplog.set_level(logging.INFO, logger="app.client")
        assert client.post("/client-log", content=body).status_code == status
        assert _lines(caplog, "app.client") == []

    def test_oversized_bodies(self, client):
        big = json.dumps({"kind": "error", "message": "x" * (T.MAX_CLIENT_BODY + 1)})
        assert client.post("/client-log", content=big).status_code == 413

    def test_oversized_declared_length(self):
        import asyncio

        from starlette.requests import Request

        scope = {
            "type": "http", "method": "POST", "path": "/client-log",
            "headers": [(b"content-length", str(T.MAX_CLIENT_BODY + 1).encode())],
        }

        async def receive():  # pragma: no cover - never read: refused on the header
            raise AssertionError("body read despite the declared length")

        resp = asyncio.run(telemetry_routes._read_json(Request(scope, receive), T.MAX_CLIENT_BODY))
        assert resp.status_code == 413

    def test_oversized_body_without_a_declared_length(self):
        """Chunked uploads carry no Content-Length; the cap still holds."""
        import asyncio

        from starlette.requests import Request

        scope = {"type": "http", "method": "POST", "path": "/client-log", "headers": []}
        chunks = [b"x" * T.MAX_CLIENT_BODY, b"x"]

        async def receive():
            chunk = chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}

        resp = asyncio.run(telemetry_routes._read_json(Request(scope, receive), T.MAX_CLIENT_BODY))
        assert resp.status_code == 413

    def test_anonymous_reports_are_accepted(self, caplog):
        caplog.set_level(logging.INFO, logger="app.client")
        with TestClient(app) as anon:
            assert anon.post("/client-log", content='{"kind": "error"}').status_code == 204
        assert " user=- " in _lines(caplog, "app.client")[0]

    def test_throttled(self, client, caplog, monkeypatch):
        monkeypatch.setattr(telemetry_routes, "throttle", T.Throttle(limit=1, window=60.0))
        caplog.set_level(logging.INFO, logger="app.client")
        assert client.post("/client-log", content='{"kind": "error"}').status_code == 204
        assert client.post("/client-log", content='{"kind": "error"}').status_code == 429
        assert client.post("/client-log", content='{"kind": "error"}').status_code == 429
        lines = _lines(caplog, "app.client")
        # One report, and ONE line saying reports are being dropped.
        assert len(lines) == 2
        assert lines[1] == "client reports throttled (1 dropped so far)"


# ---------------------------------------------------------------------------
# POST /client-reports (Chrome's Reporting API)
# ---------------------------------------------------------------------------

_CRASH = {
    "type": "crash",
    "age": 1200,
    "url": "https://l7r-character-sheet.fly.dev/characters/14",
    "user_agent": "Mozilla/5.0 Chrome/140",
    "body": {"reason": "oom", "is_top_level": True, "page_visibility": "visible"},
}


class TestCrashReports:
    def test_extracts_only_crashes(self):
        out = T.crash_reports([
            _CRASH,
            {"type": "deprecation", "body": {"id": "Unload"}},
            "junk",
            {"type": "crash", "body": "not a dict"},
        ])
        assert out[0] == {
            "url": _CRASH["url"], "age_ms": 1200, "user_agent": _CRASH["user_agent"],
            "reason": "oom", "stack": None, "is_top_level": True, "visibility": "visible",
        }
        assert out[1]["reason"] is None and out[1]["is_top_level"] is None
        assert len(out) == 2

    def test_non_list_is_nothing(self):
        assert T.crash_reports({"type": "crash"}) == []

    def test_endpoint_logs_a_crash(self, client, caplog):
        caplog.set_level(logging.INFO, logger="app.client")
        resp = client.post(
            "/client-reports", content=json.dumps([_CRASH]),
            headers={"Content-Type": "application/reports+json", "Fly-Client-IP": "203.0.113.9"},
        )
        assert resp.status_code == 204
        [rec] = [r for r in caplog.records if r.name == "app.client"]
        assert rec.levelno == logging.WARNING
        msg = rec.getMessage()
        assert msg.startswith("browser-crash ip=203.0.113.9 {")
        fields = json.loads(msg.split(" ", 2)[2])
        assert fields["reason"] == "oom" and "stack" not in fields

    def test_endpoint_ignores_other_report_types(self, client, caplog):
        caplog.set_level(logging.INFO, logger="app.client")
        body = json.dumps([{"type": "deprecation", "body": {}}])
        assert client.post("/client-reports", content=body).status_code == 204
        assert _lines(caplog, "app.client") == []

    def test_endpoint_rejects_bad_json(self, client):
        assert client.post("/client-reports", content="{").status_code == 400

    def test_endpoint_is_throttled_too(self, client, caplog, monkeypatch):
        monkeypatch.setattr(telemetry_routes, "throttle", T.Throttle(limit=1, window=60.0))
        caplog.set_level(logging.INFO, logger="app.client")
        client.post("/client-reports", content=json.dumps([_CRASH, _CRASH, _CRASH]))
        lines = _lines(caplog, "app.client")
        assert len([l for l in lines if l.startswith("browser-crash")]) == 1
