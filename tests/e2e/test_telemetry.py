"""Clicktests for client diagnostics (static/js/telemetry.js).

The pure decisions are pinned in ``tests/js/telemetry.test.js`` and the
server half in ``tests/test_telemetry.py``; these cover the browser wiring:
that reports actually leave the page, that a tab killed with a REAL renderer
crash is reported by the next page, and that the new-version banner appears.

The live server's build id is ``e2e-build`` (see conftest); a newer deploy is
simulated by answering the keepalive ping with a different ``X-App-Build``.
"""

import json

import pytest

pytestmark = pytest.mark.telemetry

# Mon 2026-08-24 20:00 New York - inside the keepalive session window.
_IN_WINDOW = "new Date(Date.UTC(2026, 7, 25, 0, 0))"


def _ready(p, url):
    p.goto(url)
    p.wait_for_function("() => window.L7RTelemetry && window.L7RTelemetry.context().tab")


def _is_report(kind):
    def match(req):
        if not req.url.endswith("/client-log") or req.method != "POST":
            return False
        try:
            return json.loads(req.post_data or "{}").get("kind") == kind
        except ValueError:
            return False
    return match


def test_page_carries_its_build_and_registers_its_tab(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    assert page.get_attribute("html", "data-build") == "e2e-build"
    ctx = page.evaluate("window.L7RTelemetry.context()")
    assert ctx["build"] == "e2e-build"
    assert ctx["page"] == "/"
    entry = page.evaluate(f"JSON.parse(localStorage.getItem('l7r.tab.{ctx['tab']}'))")
    assert entry["tab"] == ctx["tab"]
    assert entry["page"] == "/"


def test_uncaught_error_is_reported(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    with page.expect_request(_is_report("error")) as req:
        page.evaluate("setTimeout(() => { throw new Error('e2e boom') }, 0)")
    body = json.loads(req.value.post_data)
    assert "e2e boom" in body["message"]
    assert body["build"] == "e2e-build"
    assert body["page"] == "/"
    assert "stack" in body


def test_unhandled_rejection_is_reported(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    with page.expect_request(_is_report("rejection")) as req:
        page.evaluate("Promise.reject(new Error('e2e rejected')); null")
    assert json.loads(req.value.post_data)["message"] == "e2e rejected"


def test_alpine_expression_error_carries_the_expression(page, live_server_url):
    """Alpine re-throws expression errors with the expression attached; that
    is what points at the offending template line."""
    _ready(page, f"{live_server_url}/")
    page.wait_for_function("() => window.Alpine !== undefined")
    with page.expect_request(_is_report("error")) as req:
        page.evaluate(
            "document.body.insertAdjacentHTML('beforeend',"
            " '<div x-data x-text=\"e2eMissing.property\"></div>')"
        )
    assert json.loads(req.value.post_data)["expression"] == "e2eMissing.property"


def test_repeated_errors_are_reported_once(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    hits = []
    page.on("request", lambda r: hits.append(r) if _is_report("error")(r) else None)
    page.evaluate(
        "for (let i = 0; i < 4; i++) setTimeout(() => { throw new Error('same') }, 0)"
    )
    page.wait_for_timeout(500)
    assert len(hits) == 1


def _crash_renderer(browser, page, url):
    """Kill ``page``'s renderer for real (CDP ``Page.crash``).

    Sent through the browser-level ``Target.sendMessageToTarget`` because a
    page session's ``send("Page.crash")`` waits for a reply the dead renderer
    can never give, and hangs the test."""
    crashed = []
    page.on("crash", lambda _: crashed.append(True))
    bs = browser.new_browser_cdp_session()
    target = next(
        t["targetId"] for t in bs.send("Target.getTargets")["targetInfos"]
        if t["type"] == "page" and t["url"] == url
    )
    session = bs.send("Target.attachToTarget", {"targetId": target, "flatten": False})
    bs.send("Target.sendMessageToTarget", {
        "sessionId": session["sessionId"],
        "message": json.dumps({"id": 1, "method": "Page.crash"}),
    })
    for _ in range(50):
        if crashed:
            return
        bs.send("Target.getTargets")  # a round trip, to let the event arrive
    raise AssertionError("renderer did not crash")


def test_a_crashed_tab_is_reported_by_the_next_page(page, live_server_url, browser):
    """A real renderer crash: the crashed page never runs pagehide, so its
    localStorage entry survives, nobody answers for it on the tab channel,
    and the next page reports it."""
    _ready(page, f"{live_server_url}/terms")
    dead_tab = page.evaluate("window.L7RTelemetry.context().tab")
    _crash_renderer(browser, page, f"{live_server_url}/terms")

    survivor = page.context.new_page()
    with survivor.expect_request(_is_report("unclean_exit"), timeout=10_000) as req:
        survivor.goto(f"{live_server_url}/")
    body = json.loads(req.value.post_data)
    assert body["tab"] == dead_tab
    assert body["page"] == "/terms"
    assert body["build"] == "e2e-build"
    assert body["vis"] == "visible"
    assert body["ago"] >= 0
    # Reported once: the entry is gone now.
    assert survivor.evaluate(f"localStorage.getItem('l7r.tab.{dead_tab}')") is None


def test_open_and_closed_tabs_are_not_reported(page, live_server_url):
    """A tab still open answers for itself, and a page that navigated away
    removed its own entry; neither may be reported."""
    _ready(page, f"{live_server_url}/terms")
    first_tab = page.evaluate("window.L7RTelemetry.context().tab")
    _ready(page, f"{live_server_url}/privacy")  # navigation = clean close of /terms
    live_tab = page.evaluate("window.L7RTelemetry.context().tab")
    assert page.evaluate(f"localStorage.getItem('l7r.tab.{first_tab}')") is None

    other = page.context.new_page()
    hits = []
    other.on("request", lambda r: hits.append(r) if _is_report("unclean_exit")(r) else None)
    _ready(other, f"{live_server_url}/")
    other.wait_for_timeout(3500)  # reap delay + probe window, with margin
    assert hits == []
    assert other.evaluate(f"localStorage.getItem('l7r.tab.{live_tab}')") is not None


def test_keepalive_ping_carries_the_memory_sample(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    tab = page.evaluate("window.L7RTelemetry.context().tab")
    with page.expect_request(lambda r: "/keepalive?" in r.url) as req:
        page.evaluate(
            f"window.L7RKeepAlive.tick({_IN_WINDOW}, window.fetch.bind(window),"
            " undefined, window.L7RKeepAlive.telemetryExtras())"
        )
    url = req.value.url
    assert f"tab={tab}" in url
    assert "build=e2e-build" in url
    assert "up=" in url
    assert "heap=" in url  # Chromium exposes performance.memory


def _redeploy(page, build="e2e-newer"):
    """Answer every keepalive ping as a server running a newer build."""
    page.route(
        "**/keepalive**",
        lambda route: route.fulfill(status=200, body="ok", headers={"X-App-Build": build}),
    )


def _ping(page):
    page.evaluate(
        f"window.L7RKeepAlive.tick({_IN_WINDOW}, window.fetch.bind(window),"
        " undefined, window.L7RKeepAlive.telemetryExtras())"
    )


def test_no_banner_while_the_build_matches(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    with page.expect_response(lambda r: "/keepalive" in r.url):
        _ping(page)
    page.wait_for_timeout(200)
    assert page.locator("#update-banner").is_hidden()


def test_new_build_shows_the_banner_and_later_dismisses_it(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    _redeploy(page)
    _ping(page)
    banner = page.locator("#update-banner")
    banner.wait_for(state="visible")
    assert "new version" in banner.inner_text()
    banner.locator("[data-update-dismiss]").click()
    assert banner.is_hidden()
    # "Later" holds for this page: the next ping does not bring it back.
    with page.expect_response(lambda r: "/keepalive" in r.url):
        _ping(page)
    page.wait_for_timeout(200)
    assert banner.is_hidden()


def test_reload_button_reloads_the_page(page, live_server_url):
    _ready(page, f"{live_server_url}/")
    old_tab = page.evaluate("window.L7RTelemetry.context().tab")
    _redeploy(page)
    _ping(page)
    page.locator("#update-banner").wait_for(state="visible")
    with page.expect_navigation():
        page.locator("[data-update-reload]").click()
    page.wait_for_function("() => window.L7RTelemetry && window.L7RTelemetry.context().tab")
    assert page.evaluate("window.L7RTelemetry.context().tab") != old_tab
    assert page.locator("#update-banner").is_hidden()


def test_banner_fits_a_phone_screen(page, live_server_url):
    page.set_viewport_size({"width": 375, "height": 740})
    _ready(page, f"{live_server_url}/")
    _redeploy(page)
    _ping(page)
    banner = page.locator("#update-banner")
    banner.wait_for(state="visible")
    box = banner.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    assert page.locator("[data-update-reload]").is_visible()
    assert page.locator("[data-update-dismiss]").is_visible()
