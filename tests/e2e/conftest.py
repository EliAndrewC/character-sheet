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

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        cwd="/workspace",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

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
        stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"Server failed to start on port {port}.\n"
            f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield base_url

    proc.terminate()
    proc.wait(timeout=5)
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture()
def page(live_server_url, browser):
    """Yield a Playwright page with the auth bypass header set (admin user)."""
    ctx = browser.new_context(
        extra_http_headers={"X-Test-User": "183026066498125825:eliandrewc"}
    )
    p = ctx.new_page()
    yield p
    ctx.close()


@pytest.fixture()
def page_nonadmin(live_server_url, browser):
    """Yield a Playwright page as a non-admin test user."""
    ctx = browser.new_context(
        extra_http_headers={"X-Test-User": "test_user_1:Test User 1"}
    )
    p = ctx.new_page()
    yield p
    ctx.close()


@pytest.fixture()
def page_anon(live_server_url, browser):
    """Yield a Playwright page with no auth (anonymous visitor)."""
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    ctx.close()
