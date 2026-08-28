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


# ---------------------------------------------------------------------------
# The activity window (EXTENDED_KEEPALIVE_DISCORD_IDS). The e2e server opts
# the ``page`` fixture's user in and nobody else.
# ---------------------------------------------------------------------------

# Wed 2026-08-26 12:00 New York - nowhere near a game night, so any ping here
# can only be coming from the activity window.
_OFF_NIGHT_MS = "Date.UTC(2026, 7, 26, 16, 0)"


def test_extended_flag_is_rendered_for_an_opted_in_viewer(page, live_server_url):
    page.goto(f"{live_server_url}/")
    assert page.get_attribute("html", "data-extended-keepalive") == "1"
    page.wait_for_function("() => window.L7RKeepAlive !== undefined")
    assert page.evaluate("window.L7RKeepAlive.currentOptions().extended") is True


def test_extended_flag_is_absent_for_everyone_else(page_nonadmin, live_server_url):
    page_nonadmin.goto(f"{live_server_url}/")
    assert page_nonadmin.get_attribute("html", "data-extended-keepalive") is None
    page_nonadmin.wait_for_function("() => window.L7RKeepAlive !== undefined")
    assert page_nonadmin.evaluate(
        "window.L7RKeepAlive.currentOptions().extended"
    ) is False


def test_loading_a_page_starts_the_activity_window(page, live_server_url):
    """A page load counts as an interaction, so the hour starts on arrival."""
    page.goto(f"{live_server_url}/")
    page.wait_for_function("() => window.L7RKeepAlive.currentOptions().lastInteraction")
    with page.expect_response(lambda r: r.url.endswith("/keepalive")):
        sent = page.evaluate(
            "window.L7RKeepAlive.tick(new Date(),"
            " window.fetch.bind(window), window.L7RKeepAlive.currentOptions())"
        )
    assert sent is True


def test_an_hour_after_the_last_interaction_the_pings_stop(page, live_server_url):
    """A forgotten tab goes quiet rather than pinging forever."""
    page.goto(f"{live_server_url}/")
    page.wait_for_function("() => window.L7RKeepAlive !== undefined")
    hits = []
    page.on("request", lambda r: hits.append(r.url) if r.url.endswith("/keepalive") else None)
    # Ask the question as of an hour and a minute after the page load.
    sent = page.evaluate(
        "() => {"
        "  const K = window.L7RKeepAlive;"
        "  const later = new Date(K.currentOptions().lastInteraction + 61 * 60 * 1000);"
        "  return K.tick(later, window.fetch.bind(window), K.currentOptions());"
        "}"
    )
    page.wait_for_timeout(300)
    assert sent is False
    assert hits == []


def test_clicking_restarts_the_activity_window(page, live_server_url):
    """The listener is what makes 'interact and it kicks off again' true."""
    page.goto(f"{live_server_url}/")
    page.wait_for_function("() => window.L7RKeepAlive.currentOptions().lastInteraction")
    # Backdate the last interaction to well outside the hour.
    page.evaluate(
        "window.L7RKeepAlive.noteInteraction(new Date(Date.now() - 2 * 60 * 60 * 1000))"
    )
    assert page.evaluate(
        f"window.L7RKeepAlive.tick(new Date({_OFF_NIGHT_MS}),"
        " window.fetch.bind(window), window.L7RKeepAlive.currentOptions())"
    ) is False

    stale = page.evaluate("window.L7RKeepAlive.currentOptions().lastInteraction")
    page.click("body")
    page.wait_for_function(
        f"() => window.L7RKeepAlive.currentOptions().lastInteraction > {stale}"
    )
    with page.expect_response(lambda r: r.url.endswith("/keepalive")):
        assert page.evaluate(
            "window.L7RKeepAlive.tick(new Date(),"
            " window.fetch.bind(window), window.L7RKeepAlive.currentOptions())"
        ) is True


def test_off_night_is_still_silent_for_an_ordinary_viewer(
    page_nonadmin, live_server_url,
):
    """Without the opt-in, nothing changes: off-night tabs stay quiet."""
    page_nonadmin.goto(f"{live_server_url}/")
    page_nonadmin.wait_for_function("() => window.L7RKeepAlive !== undefined")
    hits = []
    page_nonadmin.on(
        "request",
        lambda r: hits.append(r.url) if r.url.endswith("/keepalive") else None,
    )
    sent = page_nonadmin.evaluate(
        f"window.L7RKeepAlive.tick(new Date({_OFF_NIGHT_MS}),"
        " window.fetch.bind(window), window.L7RKeepAlive.currentOptions())"
    )
    page_nonadmin.wait_for_timeout(300)
    assert sent is False
    assert hits == []
