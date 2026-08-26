"""Clicktests for the Fly keep-alive pinger (static/js/keepalive.js).

The real timer fires once a minute, so instead of waiting we drive the
exported ``tick`` directly in the browser and watch the network for the
resulting ``GET /keepalive``.
"""

import pytest

pytestmark = pytest.mark.keepalive

# Mon 2026-08-24 20:00 America/New_York (EDT, UTC-4) - inside the window.
_IN_WINDOW_MS = "Date.UTC(2026, 7, 25, 0, 0)"
# Wed 2026-08-26 20:00 New York - outside the window.
_OUT_WINDOW_MS = "Date.UTC(2026, 7, 27, 0, 0)"


def test_keepalive_script_loads_and_exposes_api(page, live_server_url):
    page.goto(f"{live_server_url}/")
    page.wait_for_function("() => window.L7RKeepAlive !== undefined")
    assert page.evaluate("window.L7RKeepAlive.INTERVAL_MS") == 60000
    assert page.evaluate("window.L7RKeepAlive.URL") == "/keepalive"


def test_keepalive_tick_pings_server_inside_window(page, live_server_url):
    page.goto(f"{live_server_url}/")
    page.wait_for_function("() => window.L7RKeepAlive !== undefined")
    with page.expect_response(lambda r: r.url.endswith("/keepalive")) as resp_info:
        sent = page.evaluate(
            f"window.L7RKeepAlive.tick(new Date({_IN_WINDOW_MS}), window.fetch.bind(window))"
        )
    assert sent is True
    resp = resp_info.value
    assert resp.status == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_keepalive_tick_is_silent_outside_window(page, live_server_url):
    page.goto(f"{live_server_url}/")
    page.wait_for_function("() => window.L7RKeepAlive !== undefined")
    hits = []
    page.on("request", lambda r: hits.append(r.url) if r.url.endswith("/keepalive") else None)
    sent = page.evaluate(
        f"window.L7RKeepAlive.tick(new Date({_OUT_WINDOW_MS}), window.fetch.bind(window))"
    )
    page.wait_for_timeout(300)
    assert sent is False
    assert hits == []


def test_keepalive_works_for_anonymous_visitor(page_anon, live_server_url):
    """Logged-out pages include the script and the endpoint needs no auth."""
    page_anon.goto(f"{live_server_url}/terms")
    page_anon.wait_for_function("() => window.L7RKeepAlive !== undefined")
    with page_anon.expect_response(lambda r: r.url.endswith("/keepalive")) as resp_info:
        page_anon.evaluate(
            f"window.L7RKeepAlive.tick(new Date({_IN_WINDOW_MS}), window.fetch.bind(window))"
        )
    assert resp_info.value.status == 200
