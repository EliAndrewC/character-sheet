"""Unit tests for the extended (activity-based) Fly keep-alive opt-in.

The pinger's timing logic is JavaScript and lives in
``tests/js/keepalive.test.js``; the browser wiring is in
``tests/e2e/test_keepalive.py``. What is tested here is the server half:
who gets opted in, and that the flag reaches the page.
"""

import pytest

from app.main import extended_keepalive_enabled
from app.services.auth import get_extended_keepalive_ids


ENV_VAR = "EXTENDED_KEEPALIVE_DISCORD_IDS"
# The discord id the client fixture's X-Test-User header authenticates as.
VIEWER_ID = "183026066498125825"


class _Request:
    """The bare minimum ``extended_keepalive_enabled`` reads off a request."""

    def __init__(self, user):
        self.state = type("S", (), {"user": user})()


@pytest.fixture(autouse=True)
def _no_opt_in_by_default(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# The id list
# ---------------------------------------------------------------------------


def test_ids_are_empty_when_unset():
    assert get_extended_keepalive_ids() == []


def test_ids_are_parsed_and_stripped(monkeypatch):
    monkeypatch.setenv(ENV_VAR, " 111 , 222,, 333 ")
    assert get_extended_keepalive_ids() == ["111", "222", "333"]


def test_ids_are_independent_of_the_admin_list(monkeypatch):
    """Being a GM does not, on its own, let your tab keep the machine warm."""
    monkeypatch.setenv("ADMIN_DISCORD_IDS", VIEWER_ID)
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert extended_keepalive_enabled(_Request({"discord_id": VIEWER_ID})) is False


# ---------------------------------------------------------------------------
# The per-request predicate
# ---------------------------------------------------------------------------


def test_enabled_for_a_listed_viewer(monkeypatch):
    monkeypatch.setenv(ENV_VAR, f"other_person,{VIEWER_ID}")
    assert extended_keepalive_enabled(_Request({"discord_id": VIEWER_ID})) is True


def test_disabled_for_an_unlisted_viewer(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "someone_else")
    assert extended_keepalive_enabled(_Request({"discord_id": VIEWER_ID})) is False


def test_disabled_for_an_anonymous_visitor(monkeypatch):
    monkeypatch.setenv(ENV_VAR, VIEWER_ID)
    assert extended_keepalive_enabled(_Request(None)) is False


def test_disabled_when_the_env_var_is_unset():
    assert extended_keepalive_enabled(_Request({"discord_id": VIEWER_ID})) is False


def test_disabled_for_a_user_with_no_discord_id(monkeypatch):
    monkeypatch.setenv(ENV_VAR, VIEWER_ID)
    assert extended_keepalive_enabled(_Request({})) is False


def test_tolerates_a_non_dict_user(monkeypatch):
    """Defensive: request.state.user is a dict everywhere, but a template
    global must not be the thing that 500s a page if that ever changes."""
    monkeypatch.setenv(ENV_VAR, VIEWER_ID)
    assert extended_keepalive_enabled(_Request("not-a-dict")) is False


# ---------------------------------------------------------------------------
# The flag on the rendered page
# ---------------------------------------------------------------------------


def test_flag_is_rendered_for_a_listed_viewer(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, VIEWER_ID)
    html = client.get("/").text
    assert 'data-extended-keepalive="1"' in html


def test_flag_is_absent_for_an_unlisted_viewer(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "someone_else")
    assert "data-extended-keepalive" not in client.get("/").text


def test_flag_is_absent_when_nobody_is_opted_in(client):
    assert "data-extended-keepalive" not in client.get("/").text


def test_flag_is_absent_for_a_logged_out_visitor(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, VIEWER_ID)
    html = client.get("/terms", headers={"X-Test-User": ""}).text
    assert "data-extended-keepalive" not in html


def test_the_flag_does_not_disturb_the_dark_mode_class(client, monkeypatch):
    """Both page-level flags live on <html>; neither should eat the other."""
    monkeypatch.setenv(ENV_VAR, VIEWER_ID)
    html = client.get("/", cookies={"dark_mode": "1"}).text
    assert '<html lang="en" class="dark" data-extended-keepalive="1">' in html
