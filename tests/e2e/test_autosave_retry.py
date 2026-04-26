"""E2E: autosave failure handling.

The editor's autosave used to swallow failures - on any non-2xx the
``saveStatus`` flipped to "Save failed" and the ``_dirty`` bit was lost,
so the next autosave never re-attempted the same payload. A deploy or
transient network blip mid-edit could strand changes silently.

These tests pin the new behavior:

  * 5xx / network error -> "Save failed - retrying", periodic retry via
    a timer (window.__testSaveRetryMs lets the tests run that timer at
    a few hundred ms instead of the production 30 seconds).
  * 4xx -> terminal status "Save failed (NNN)", no retry (a real bug
    won't go away by hammering the server with the same payload).
  * Either failure mode arms the beforeunload warning so closing the
    tab with stranded changes asks for confirmation.
"""

import pytest
from tests.e2e.helpers import (
    select_school, start_new_character,
)

pytestmark = [pytest.mark.autosave]

# Compress the production 30s retry interval so the test doesn't sit on
# its hands. Set BEFORE navigation via add_init_script so it's in place
# when the editor's Alpine init() reads it. 600ms is short enough to
# keep the test snappy but long enough that Playwright's wait_for_selector
# polling reliably catches the transient "Save failed - retrying" state
# before the retry succeeds and flips it to "Saved".
SHORT_RETRY_INIT = "window.__testSaveRetryMs = 600;"


def _open_editor(page, live_server_url, name):
    """Land on the editor for a brand-new character with the touch /
    test-retry overrides applied. The character must be saved at least
    once via the standard flow before this returns; otherwise the
    /autosave POST tries to save against a missing row and 404s for
    reasons unrelated to the retry logic."""
    page.add_init_script(SHORT_RETRY_INIT)
    page.goto(live_server_url)
    start_new_character(page)
    page.wait_for_selector('input[name="name"]')
    page.fill('input[name="name"]', name)
    select_school(page, "akodo_bushi")
    page.wait_for_selector('text="Saved"', timeout=5000)


def _trigger_dirty(page, new_name):
    """Force a markDirty() by editing the name field, which the
    characterForm $watch tree picks up via the input's @input handler."""
    page.fill('input[name="name"]', new_name)


def test_5xx_failure_retries_until_save_succeeds(page, live_server_url):
    """A 5xx response should set "Save failed - retrying" and the retry
    timer should fire a fresh autosave that succeeds once the server
    recovers. We simulate the server going down for exactly one request
    (the deploy-window pattern)."""
    _open_editor(page, live_server_url, "RetryRecover")

    # Fail the next autosave with 503, let everything after pass through.
    state = {"calls": 0}

    def handler(route):
        state["calls"] += 1
        if state["calls"] == 1:
            route.fulfill(status=503, body="boom")
        else:
            route.continue_()

    page.route("**/autosave", handler)

    _trigger_dirty(page, "RetryRecover Mk II")

    # First attempt fails -> retrying status appears.
    page.wait_for_selector('text="Save failed - retrying"', timeout=5000)

    # Periodic retry (200ms) re-runs doSave, which builds a fresh body
    # from the live form state and POSTs again - now allowed through.
    page.wait_for_selector('text="Saved"', timeout=5000)
    assert state["calls"] >= 2, f"expected retry to fire a second autosave, only saw {state['calls']}"


def test_4xx_failure_is_terminal_no_retry(page, live_server_url):
    """A 4xx error means the server actively rejected this payload -
    retrying won't help. Status carries the code so the user knows
    something real is wrong, and no further /autosave fires after the
    retry interval has elapsed."""
    _open_editor(page, live_server_url, "Terminal4xx")

    state = {"calls": 0}

    def handler(route):
        state["calls"] += 1
        route.fulfill(status=400, body="bad")

    page.route("**/autosave", handler)

    _trigger_dirty(page, "Terminal4xx Mk II")

    page.wait_for_selector('text="Save failed (400)"', timeout=5000)
    calls_at_failure = state["calls"]

    # Wait noticeably longer than the test retry interval (200ms) - if
    # the timer fired we'd see additional /autosave requests.
    page.wait_for_timeout(800)
    assert state["calls"] == calls_at_failure, (
        f"expected NO retries after 4xx, but call count went "
        f"{calls_at_failure} -> {state['calls']}"
    )
    # And the status stays terminal.
    assert page.locator('text="Save failed (400)"').is_visible()


def test_beforeunload_warns_when_save_failed(page, live_server_url):
    """After a failed save the editor arms a beforeunload listener so a
    tab close (or back-button) asks for confirmation rather than silently
    eating the buffered edits. We check the listener is wired up by
    dispatching the event ourselves and inspecting the returnValue,
    which is what browsers use to decide whether to show the dialog."""
    _open_editor(page, live_server_url, "BeforeUnload")

    page.route("**/autosave", lambda route: route.fulfill(status=503))
    _trigger_dirty(page, "BeforeUnload Mk II")
    page.wait_for_selector('text="Save failed - retrying"', timeout=5000)

    # Synthetic beforeunload: dispatch a cancelable event and inspect
    # whether the page's listener marked it for warning. The browser
    # uses returnValue (any non-empty value) to decide whether to show
    # the dialog; preventDefault() is the modern equivalent.
    armed = page.evaluate("""() => {
        const ev = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(ev);
        return ev.defaultPrevented || ev.returnValue !== undefined && ev.returnValue !== '';
    }""")
    # `defaultPrevented` is the reliable signal in Chromium; `returnValue
    # !== ''` would be true in our handler but the event only carries
    # the value if the runtime exposes BeforeUnloadEvent.returnValue,
    # which Playwright's synthetic Event does not. Either being truthy
    # is enough.
    assert armed is True or armed == "" is False, (
        "beforeunload listener did not flag the event as preventing default"
    )
    # Sanity: the same dispatch on a clean page returns False. Easiest
    # way to verify the negative is to clear dirty + status and try
    # again from the same page session.
    page.evaluate("""() => {
        const root = document.querySelector('[x-data="characterForm()"]');
        const data = window.Alpine.$data(root);
        data._dirty = false;
        data.saveStatus = '';
    }""")
    not_armed = page.evaluate("""() => {
        const ev = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(ev);
        return ev.defaultPrevented;
    }""")
    assert not_armed is False, "beforeunload should not warn on a clean editor"
