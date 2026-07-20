"""E2E test fixtures — starts a live server for Playwright to hit."""

import os
import socket
import subprocess
import sys
import time

import pytest


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url():
    """Start a uvicorn server on a random port with a temp database.

    Yields the base URL (e.g. "http://localhost:54321").
    The server and database are torn down after the test session.
    """
    port = _find_free_port()
    db_path = f"/tmp/l7r_test_{port}.db"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_path
    env["TEST_AUTH_BYPASS"] = "true"
    env["DISCORD_WHITELIST_IDS"] = "183026066498125825,test_user_1,test_user_2"
    env["ADMIN_DISCORD_IDS"] = "183026066498125825"
    # Keep the Gemini API offline for clicktests; the stub returns canned
    # responses based on markers in the uploaded document. See
    # app/services/import_llm.py::_stub_response_for.
    env["IMPORT_USE_TEST_STUB"] = "1"
    # Don't leak a real Gemini key into the subprocess - the stub short-
    # circuits before the key check, but belt-and-braces.
    env.pop("GEMINI_API_KEY", None)
    # Import is fail-closed by default in production (an unset env var
    # keeps the feature disabled). The clicktest suite exercises the
    # import flow, so opt in explicitly for the live server.
    env["IMPORT_ENABLED"] = "true"
    # Character art (Phase 7/8): enable the feature + Imagen stub so
    # the wizard works end-to-end without hitting Google.
    env["ART_GEN_ENABLED"] = "true"
    env["ART_GEN_USE_TEST_STUB"] = "1"
    # Disk-backed storage stub for S3. The storage layer switches to
    # a local tmpdir and the ``/test-art-stub/{key}`` route serves the
    # bytes back so the browser can display them. The bucket name is
    # just a placeholder to satisfy the "storage configured" check.
    env["ART_STORAGE_USE_TEST_STUB"] = "1"
    art_stub_dir = f"/tmp/l7r_art_stub_{port}"
    env["ART_STORAGE_STUB_DIR"] = art_stub_dir
    env["S3_BACKUP_BUCKET"] = "stub-bucket"
    env["S3_BACKUP_REGION"] = "us-east-1"

    # Server output goes to a FILE, not a pipe. A pipe is a fixed ~64KB
    # kernel buffer, and nothing drains it during the session - once it
    # fills, the server blocks forever inside its logging write and every
    # subsequent test dies with "Page.goto: Timeout 30000ms exceeded".
    # That is what --no-access-log below was papering over: it silenced the
    # loudest writer instead of fixing the pipe. stderr still filled on long
    # runs (~1300 tests), killing the back half of the suite. A file has no
    # such limit, and keeps the output readable for the startup-failure path.
    log_path = f"/tmp/l7r_test_server_{port}.log"
    server_log = open(log_path, "w+b")

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            # Access logs are pure noise for the clicktests; keep them off so
            # the log file stays small and greppable.
            "--no-access-log",
        ],
        cwd="/character-sheet",
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )

    def _read_server_log():
        server_log.flush()
        with open(log_path, "rb") as fh:
            return fh.read().decode(errors="replace")

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError(
            f"Server failed to start on port {port}.\n"
            f"server output:\n{_read_server_log()}"
        )

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # A wedged server ignores SIGTERM; don't let teardown error out and
        # mask the real failure. (This fired as a session ERROR on the run
        # where the stderr pipe filled.)
        proc.kill()
        proc.wait(timeout=5)
    server_log.close()
    if os.path.exists(log_path):
        os.remove(log_path)
    if os.path.exists(db_path):
        os.remove(db_path)
    # Clean up art storage stub tmpdir
    import shutil
    if os.path.isdir(art_stub_dir):
        shutil.rmtree(art_stub_dir, ignore_errors=True)


# Disable dice animations in tests to eliminate timing flakiness. Installed
# on EVERY page fixture below - `page_nonadmin` and `page_anon` drive the
# read-only roll walkthrough (a viewer can roll on someone else's sheet), so
# they need this just as much as the editor `page` does.
#
# This is flake protection, not a speedup: dice.js hands the caller its final
# dice via onDiceReady BEFORE the ~3.2s animation starts, so Playwright's
# `phase === 'done'` waits never block on it. What the animation does do is
# burn a timer + DOM churn per roll, which under full-suite CPU load can
# starve the Alpine tick a test is waiting on.
_DISABLE_ANIMS_SCRIPT = """
    window.__testDisableAnimations = true;
    // Disable dice animation/sound on BOTH roll components: the main
    // diceRoller (_diceRoller.prefs) and the separate freeform roller
    // (_freeformRoller.ffPrefs). Without the latter, freeform rolls
    // animate for ~3.2s and flake under full-suite CPU load.
    const _disableAnims = () => {
        if (window._diceRoller) {
            window._diceRoller.prefs.dice_animation_enabled = false;
            window._diceRoller.prefs.dice_sound_enabled = false;
        }
        if (window._freeformRoller) {
            window._freeformRoller.ffPrefs.dice_animation_enabled = false;
            window._freeformRoller.ffPrefs.dice_sound_enabled = false;
        }
    };
    // After Alpine initializes, override the prefs. Keep polling until
    // both components exist (they init independently). Pages that never
    // instantiate both keep polling harmlessly until the context closes.
    const _origInterval = setInterval(() => {
        _disableAnims();
        if (window._diceRoller && window._freeformRoller) clearInterval(_origInterval);
    }, 50);
    // Also disable for any future page loads
    document.addEventListener('alpine:initialized', _disableAnims);
"""


@pytest.fixture()
def page(live_server_url, browser):
    """Yield a Playwright page with the auth bypass header set (admin user)."""
    ctx = browser.new_context(
        extra_http_headers={"X-Test-User": "183026066498125825:eliandrewc"}
    )
    p = ctx.new_page()
    p.add_init_script(_DISABLE_ANIMS_SCRIPT)
    yield p
    ctx.close()


@pytest.fixture()
def page_nonadmin(live_server_url, browser):
    """Yield a Playwright page as a non-admin test user."""
    ctx = browser.new_context(
        extra_http_headers={"X-Test-User": "test_user_1:Test User 1"}
    )
    p = ctx.new_page()
    p.add_init_script(_DISABLE_ANIMS_SCRIPT)
    yield p
    ctx.close()


@pytest.fixture()
def page_anon(live_server_url, browser):
    """Yield a Playwright page with no auth (anonymous visitor)."""
    ctx = browser.new_context()
    p = ctx.new_page()
    p.add_init_script(_DISABLE_ANIMS_SCRIPT)
    yield p
    ctx.close()
