"""HTTP-level tests for the /import, /import/progress/, /import/status/ routes.

Phase 7 made the POST async via an in-memory job registry. These tests
replace the job-runner with an inline synchronous dispatcher so each
POST fully resolves before the test checks status; without that, race
conditions would make the assertions flaky.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import pytest

from app.models import Character
from app.services import import_jobs
from app.services import import_llm as llm
from app.services.import_reconcile import IMPORT_NOTES_LABEL


FIXTURES = Path(__file__).parent / "import_fixtures"
HAPPY = FIXTURES / "happy_path"
EDGES = FIXTURES / "edge_cases"
USER_ID = "183026066498125825"


# ---------------------------------------------------------------------------
# Fixtures: sync runner + route the job's SessionLocal through the test DB.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _sync_runner():
    import_jobs.set_runner(lambda fn: fn())
    with import_jobs._LOCK:
        import_jobs._JOBS.clear()
    yield
    import_jobs.reset_runner()
    with import_jobs._LOCK:
        import_jobs._JOBS.clear()


@pytest.fixture(autouse=True)
def _route_jobs_through_test_db(client, monkeypatch):
    """Make the jobs module's SessionLocal resolve against the same
    in-memory engine our TestClient uses. Without this, a successful
    import writes to a DIFFERENT database than the one the test queries."""
    import sqlalchemy.orm as _orm
    session = client._test_session_factory()
    bind = session.get_bind()
    session.close()
    monkeypatch.setattr(
        import_jobs, "SessionLocal",
        _orm.sessionmaker(autocommit=False, autoflush=False, bind=bind),
    )


# ---------------------------------------------------------------------------
# Mock-Gemini helper
# ---------------------------------------------------------------------------

def _install_transport(
    monkeypatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)


def _fake_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-key")
    monkeypatch.setattr(llm, "IMPORT_LLM_RETRY_BACKOFF_SEC", 0.0)


def _canonical_llm_payload(**overrides) -> Dict[str, Any]:
    payload = {
        "name": "Kakita Tomoe", "player_name": "Eli",
        "school_name_as_written": "Kakita Duelist",
        "school_ring_choice": "Fire",
        "rings": {"air": 2, "fire": 4, "earth": 2, "water": 3, "void": 2},
        "attack": 3, "parry": 3,
        "skills": [{"name_as_written": "Etiquette", "rank": 3}],
        "knacks": [
            {"name_as_written": "Iaijutsu", "rank": 3},
            {"name_as_written": "Double Attack", "rank": 2},
            {"name_as_written": "Lunge", "rank": 2},
        ],
        "advantages": [{"name_as_written": "Charming"}],
        "disadvantages": [{"name_as_written": "Proud"}],
        "first_dan_choices": [], "second_dan_choice": None,
        "honor": 3.0, "rank": 7.5, "recognition": 7.5,
        "starting_xp": 150,
        "source_stated_spent_xp": None,
        "source_stated_earned_xp": None,
        "source_stated_unspent_xp": None,
        "freeform_sections": [],
        "multi_character_detected": False,
        "not_a_character_sheet": False,
        "ambiguities": [], "per_field_confidence": {},
    }
    payload.update(overrides)
    return payload


def _response_200(payload: Dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{
            "content": {"parts": [{"text": json.dumps(payload)}]},
            "finishReason": "STOP",
        }],
    })


def _submit(client, *, file_bytes=None, filename=None, url=None,
            follow_redirects=False):
    kwargs = {"follow_redirects": follow_redirects}
    if file_bytes is not None:
        kwargs["files"] = {"file": (filename or "doc.txt", file_bytes,
                                    "text/plain")}
    if url is not None:
        kwargs["data"] = {"url": url}
    return client.post("/import", **kwargs)


def _extract_job_id(resp) -> str:
    loc = resp.headers["location"]
    assert loc.startswith("/import/progress/"), loc
    return loc.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# GET /import
# ---------------------------------------------------------------------------

def test_get_import_unauthenticated_redirects_to_login(client) -> None:
    resp = client.get("/import", headers={"X-Test-User": ""},
                      follow_redirects=False)
    assert resp.status_code == 303
    assert "/auth/login" in resp.headers["location"]


def test_get_import_renders_form(client) -> None:
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "Import a Character" in resp.text
    # Tabs are present so the user can switch between file and URL.
    assert 'data-testid="import-tab-file"' in resp.text
    assert 'data-testid="import-tab-url"' in resp.text


def test_get_import_kill_switch_shows_503(client, monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_ENABLED", "false")
    resp = client.get("/import")
    assert resp.status_code == 503
    assert "temporarily unavailable" in resp.text


# ---------------------------------------------------------------------------
# POST /import: guardrails that render the form inline
# ---------------------------------------------------------------------------

def test_post_unauthenticated_redirects(client) -> None:
    resp = client.post("/import", headers={"X-Test-User": ""},
                       data={"url": "https://example.com/foo"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "/auth/login" in resp.headers["location"]


def test_post_kill_switch_shows_503(client, monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_ENABLED", "0")
    resp = client.post(
        "/import",
        files={"file": ("x.txt", b"abc", "text/plain")},
    )
    assert resp.status_code == 503


def test_post_no_source_returns_400(client) -> None:
    resp = client.post("/import", data={})
    assert resp.status_code == 400
    assert "upload a file or paste a URL" in resp.text


def test_post_both_file_and_url_returns_400(client) -> None:
    resp = client.post(
        "/import",
        data={"url": "https://example.com/char.txt"},
        files={"file": ("happy.txt", b"abc", "text/plain")},
    )
    assert resp.status_code == 400
    assert "file OR a URL" in resp.text


# ---------------------------------------------------------------------------
# POST /import: happy path (file)
# ---------------------------------------------------------------------------

def test_post_happy_file_redirects_to_progress_and_persists_draft(
    client, monkeypatch,
) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()

    resp = _submit(client, file_bytes=data, filename="happy_plaintext.txt")
    assert resp.status_code == 303
    job_id = _extract_job_id(resp)

    # Status endpoint reports success + the edit URL.
    resp = client.get(f"/import/status/{job_id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["state"] == "succeeded"
    assert payload["stage"] == "Done"
    assert payload["redirect_url"].startswith("/characters/")
    assert payload["redirect_url"].endswith("/edit")

    # Draft is in the DB.
    session = client._test_session_factory()
    chars = session.query(Character).all()
    assert len(chars) == 1
    character = chars[0]
    assert character.is_published is False
    assert character.owner_discord_id == USER_ID
    assert character.name == "Kakita Tomoe"
    assert character.sections[0]["label"] == IMPORT_NOTES_LABEL
    assert character.current_void_points == character.ring_void


def test_post_happy_url(client, monkeypatch) -> None:
    _fake_key(monkeypatch)
    from app.services import import_url as url_mod
    monkeypatch.setattr(url_mod, "_RESOLVER", lambda host: ["142.250.0.1"])
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        if "generativelanguage.googleapis.com" in str(req.url):
            return _response_200(_canonical_llm_payload())
        return httpx.Response(200,
                              headers={"content-type": "text/plain"},
                              content=body)

    _install_transport(monkeypatch, handler)
    doc_url = ("https://docs.google.com/document/d/"
               "1AbCdEfGh_ijklmnopqrSTUVWXYZ0123456/edit")
    resp = _submit(client, url=doc_url)
    assert resp.status_code == 303

    session = client._test_session_factory()
    assert session.query(Character).count() == 1


# ---------------------------------------------------------------------------
# POST /import: rejection paths populate job.error_* and status surfaces it
# ---------------------------------------------------------------------------

def test_post_multi_character_job_fails_with_error_code(
    client, monkeypatch,
) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: _response_200(
        _canonical_llm_payload(multi_character_detected=True)
    ))
    data = (EDGES / "multi_character.txt").read_bytes()
    resp = _submit(client, file_bytes=data, filename="multi.txt")
    assert resp.status_code == 303
    job_id = _extract_job_id(resp)

    status = client.get(f"/import/status/{job_id}").json()
    assert status["state"] == "failed"
    assert status["error_code"] == "multi_character_document"
    assert "more than one character" in status["error_message"]
    assert status["error_status"] == 400

    session = client._test_session_factory()
    assert session.query(Character).count() == 0


def test_post_private_google_doc_status_has_dedicated_error_code(
    client, monkeypatch,
) -> None:
    _fake_key(monkeypatch)
    from app.services import import_url as url_mod
    monkeypatch.setattr(url_mod, "_RESOLVER", lambda host: ["142.250.0.1"])
    _install_transport(monkeypatch, lambda req: httpx.Response(302, headers={
        "location": "https://accounts.google.com/ServiceLogin",
    }))
    doc_url = ("https://docs.google.com/document/d/"
               "1AbCdEfGh_ijklmnopqrSTUVWXYZ0123456/edit")
    resp = _submit(client, url=doc_url)
    job_id = _extract_job_id(resp)
    status = client.get(f"/import/status/{job_id}").json()
    assert status["error_code"] == "document_not_public"


def test_post_oversize_fails_before_extraction(client) -> None:
    big = b"x" * (2 * 1024 * 1024)
    resp = _submit(client, file_bytes=big, filename="big.txt")
    job_id = _extract_job_id(resp)
    status = client.get(f"/import/status/{job_id}").json()
    assert status["state"] == "failed"
    assert status["error_code"] == "file_too_large"
    assert status["error_status"] == 413


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------

def test_post_rate_limit_blocks_before_job_creation(
    client, monkeypatch,
) -> None:
    monkeypatch.setenv("IMPORT_RATE_LIMIT_PER_DAY", "2")
    session = client._test_session_factory()
    for i in range(2):
        session.add(Character(
            name=f"Imported {i}", owner_discord_id=USER_ID,
            school="kakita_duelist",
            sections=[{"label": IMPORT_NOTES_LABEL, "html": "<p>n</p>"}],
        ))
    session.commit()

    _install_transport(monkeypatch, lambda req: pytest.fail(
        "rate-limit check must fire before any extraction"
    ))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    resp = _submit(client, file_bytes=data, filename="happy.txt")
    assert resp.status_code == 429
    assert "last 24 hours" in resp.text


# ---------------------------------------------------------------------------
# Progress page
# ---------------------------------------------------------------------------

def test_progress_page_renders_for_owner(client, monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    resp = _submit(client, file_bytes=data, filename="happy.txt")
    job_id = _extract_job_id(resp)

    resp = client.get(f"/import/progress/{job_id}")
    assert resp.status_code == 200
    assert f'data-job-id="{job_id}"' in resp.text
    assert "Importing your character" in resp.text


def test_progress_page_rejects_other_users_jobs(client, monkeypatch) -> None:
    """A job belongs to its submitter; other users get the "no longer
    available" message (same as unknown IDs - no ID-existence leak)."""
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    resp = _submit(client, file_bytes=data, filename="happy.txt")
    job_id = _extract_job_id(resp)

    # Request the progress page as a different user.
    resp = client.get(f"/import/progress/{job_id}",
                      headers={"X-Test-User": "test_user_1:otherplayer"})
    assert resp.status_code == 404
    assert "no longer available" in resp.text


def test_progress_page_unknown_id_shows_404(client) -> None:
    resp = client.get("/import/progress/does-not-exist")
    assert resp.status_code == 404
    assert "no longer available" in resp.text


def test_progress_page_unauthenticated_redirects(client) -> None:
    resp = client.get("/import/progress/whatever",
                      headers={"X-Test-User": ""},
                      follow_redirects=False)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Status endpoint auth
# ---------------------------------------------------------------------------

def test_status_endpoint_unknown_returns_404(client) -> None:
    resp = client.get("/import/status/nope")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_status_endpoint_unauthenticated_returns_401(client) -> None:
    resp = client.get("/import/status/anything",
                      headers={"X-Test-User": ""})
    assert resp.status_code == 401
    assert resp.json()["error"] == "not_authenticated"


def test_status_endpoint_rejects_other_users_job(
    client, monkeypatch,
) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    resp = _submit(client, file_bytes=data, filename="happy.txt")
    job_id = _extract_job_id(resp)

    resp = client.get(f"/import/status/{job_id}",
                      headers={"X-Test-User": "test_user_1:otherplayer"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Nav dropdown structural check (responsive sanity)
# ---------------------------------------------------------------------------

def test_nav_dropdown_offers_create_and_import(client) -> None:
    """The nav bar's New Character control is a dropdown with both the
    "Create" (POST /characters) and "Import" (/import) entry points."""
    resp = client.get("/")
    body = resp.text
    assert 'data-testid="new-character-menu"' in body
    assert 'data-testid="new-character-option-create"' in body
    assert 'data-testid="new-character-option-import"' in body
    assert 'href="/import"' in body


# ---------------------------------------------------------------------------
# Edit-page Import Notes banner (applies only to Drafts from the importer)
# ---------------------------------------------------------------------------

def test_edit_page_shows_import_banner_for_imported_drafts(client) -> None:
    """After a successful import we land on the edit page as a Draft
    with the Import Notes section - the banner must surface."""
    session = client._test_session_factory()
    c = Character(
        name="Imported Char", owner_discord_id=USER_ID,
        school="kakita_duelist",
        is_published=False,
        sections=[{"label": IMPORT_NOTES_LABEL, "html": "<p>notes</p>"}],
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    resp = client.get(f"/characters/{c.id}/edit")
    assert resp.status_code == 200
    assert 'data-testid="import-notes-banner"' in resp.text
    assert "imported from an external document" in resp.text


def test_edit_page_no_import_banner_for_non_imported_characters(client) -> None:
    session = client._test_session_factory()
    c = Character(
        name="Hand-built", owner_discord_id=USER_ID,
        school="kakita_duelist",
        is_published=False,
        sections=[{"label": "Backstory", "html": "<p>a tale</p>"}],
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    resp = client.get(f"/characters/{c.id}/edit")
    assert 'data-testid="import-notes-banner"' not in resp.text


def test_edit_page_no_import_banner_once_published(client) -> None:
    """Once the user applies changes the banner stops being useful; it
    was a review prompt, and the character is past review."""
    session = client._test_session_factory()
    c = Character(
        name="Published Import", owner_discord_id=USER_ID,
        school="kakita_duelist",
        is_published=True, published_state={"name": "Published Import"},
        sections=[{"label": IMPORT_NOTES_LABEL, "html": "<p>notes</p>"}],
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    resp = client.get(f"/characters/{c.id}/edit")
    assert 'data-testid="import-notes-banner"' not in resp.text
