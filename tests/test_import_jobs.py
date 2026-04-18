"""Unit tests for app/services/import_jobs.py."""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import pytest

from app.services import import_jobs as jobs
from app.services import import_llm as llm
from app.services.import_reconcile import IMPORT_NOTES_LABEL


FIXTURES = Path(__file__).parent / "import_fixtures"
HAPPY = FIXTURES / "happy_path"


# ---------------------------------------------------------------------------
# Fixture: synchronous job runner so tests see terminal state immediately.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _sync_runner():
    """Replace the threaded dispatcher with an inline one for tests.

    This is autouse so every test in this file sees terminal state
    without sleeping. The shared _JOBS dict is cleared between tests.
    """
    jobs.set_runner(lambda fn: fn())
    with jobs._LOCK:
        jobs._JOBS.clear()
    yield
    jobs.reset_runner()
    with jobs._LOCK:
        jobs._JOBS.clear()


# ---------------------------------------------------------------------------
# Mock Gemini + fake key
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


def _response_200(payload: Dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={
        "candidates": [{
            "content": {"parts": [{"text": json.dumps(payload)}]},
            "finishReason": "STOP",
        }],
    })


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


USER_ID = "183026066498125825"


# ---------------------------------------------------------------------------
# submit_job + happy path
# ---------------------------------------------------------------------------


def test_submit_job_runs_pipeline_and_persists_draft(db, monkeypatch) -> None:
    """End-to-end: submit a job, verify a draft Character is written to
    the DB and the job transitions to SUCCEEDED."""
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))

    # Route the jobs module's SessionLocal to our test DB's bind so the
    # worker writes into the same in-memory SQLite we query below.
    bind = db.get_bind()
    import sqlalchemy.orm as _orm
    monkeypatch.setattr(
        jobs, "SessionLocal",
        _orm.sessionmaker(autocommit=False, autoflush=False, bind=bind),
    )

    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    job_id = jobs.submit_job(
        user_id=USER_ID, file_bytes=data, filename="happy.txt",
        source_descriptor="happy.txt",
    )
    job = jobs.get_job(job_id)
    assert job is not None
    assert job.state == jobs.STATE_SUCCEEDED
    assert job.stage == "Done"
    assert job.character_id is not None

    # Draft is in the DB with the right owner and import notes.
    from app.models import Character
    char = db.query(Character).filter_by(id=job.character_id).first()
    assert char is not None
    assert char.owner_discord_id == USER_ID
    assert char.is_published is False
    assert char.sections[0]["label"] == IMPORT_NOTES_LABEL


def test_submit_job_rejected_pipeline_marks_failed(monkeypatch) -> None:
    """When the orchestrator rejects (e.g. multi-character), the job
    transitions to FAILED with the matching error_code."""
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: _response_200(
        _canonical_llm_payload(multi_character_detected=True)
    ))
    job_id = jobs.submit_job(user_id=USER_ID,
                             file_bytes=b"some text",
                             filename="x.txt")
    job = jobs.get_job(job_id)
    assert job.state == jobs.STATE_FAILED
    assert job.error_code == "multi_character_document"
    assert job.error_status == 400
    assert "more than one character" in job.error_message


def test_submit_job_oversize_rejected_without_running_gemini(monkeypatch) -> None:
    _install_transport(monkeypatch, lambda req: pytest.fail(
        "Gemini must not be called for oversize files"
    ))
    big = b"x" * (2 * 1024 * 1024)
    job_id = jobs.submit_job(user_id=USER_ID, file_bytes=big,
                             filename="big.txt")
    job = jobs.get_job(job_id)
    assert job.state == jobs.STATE_FAILED
    assert job.error_code == "file_too_large"
    assert job.error_status == 413


def test_submit_job_gemini_rate_limit_rejected(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: httpx.Response(429, json={"error": {}}))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    job_id = jobs.submit_job(user_id=USER_ID, file_bytes=data,
                             filename="happy.txt")
    job = jobs.get_job(job_id)
    assert job.state == jobs.STATE_FAILED
    assert job.error_code == "gemini_rate_limited"
    assert job.error_status == 503


def test_get_job_returns_none_for_unknown_id() -> None:
    assert jobs.get_job("nope") is None


def test_is_terminal_helper() -> None:
    job = jobs.ImportJob(id="x", user_id="y", state=jobs.STATE_PENDING)
    assert job.is_terminal() is False
    job.state = jobs.STATE_SUCCEEDED
    assert job.is_terminal() is True
    job.state = jobs.STATE_FAILED
    assert job.is_terminal() is True


def test_touch_updates_state_and_stage_and_bumps_timestamp() -> None:
    job = jobs.ImportJob(id="x", user_id="y")
    before = job.updated_at
    job.touch(stage="Reading", state=jobs.STATE_RUNNING)
    assert job.stage == "Reading"
    assert job.state == jobs.STATE_RUNNING
    assert job.updated_at > before


def test_reap_expired_drops_old_terminal_jobs(monkeypatch) -> None:
    # Manually stuff an old finished job in.
    job = jobs.ImportJob(id="old", user_id="y", state=jobs.STATE_SUCCEEDED)
    job.updated_at = job.updated_at - timedelta(minutes=30)
    with jobs._LOCK:
        jobs._JOBS["old"] = job

    # Adding a new job triggers the reaper.
    _install_transport(monkeypatch, lambda req: pytest.fail(
        "no Gemini call needed"
    ))
    jobs.submit_job(user_id="other", file_bytes=b"\x7fELF\x02\x01\x01\x00" + b"\0" * 200,
                    filename="a.out")
    assert jobs.get_job("old") is None


def test_reap_keeps_recent_terminal_jobs(monkeypatch) -> None:
    """Only jobs older than the TTL get reaped; fresh ones stay."""
    job = jobs.ImportJob(id="fresh", user_id="y", state=jobs.STATE_SUCCEEDED)
    with jobs._LOCK:
        jobs._JOBS["fresh"] = job

    _install_transport(monkeypatch, lambda req: pytest.fail("no call"))
    jobs.submit_job(user_id="other",
                    file_bytes=b"\x7fELF\x02\x01\x01\x00" + b"\0" * 200,
                    filename="a.out")
    assert jobs.get_job("fresh") is not None


def test_threaded_runner_actually_spawns_a_thread(monkeypatch) -> None:
    """Default runner dispatches to a daemon thread. This test exercises
    the pragma-less real path to prove it wires up properly. We use a
    quick-reject payload so the thread finishes almost instantly."""
    jobs.reset_runner()
    _install_transport(monkeypatch, lambda req: pytest.fail("no call"))
    job_id = jobs.submit_job(user_id=USER_ID,
                             file_bytes=b"\x7fELF\x02\x01\x01\x00" + b"\0" * 200,
                             filename="a.out")

    # Poll briefly for terminal state; since the pipeline rejects on
    # unsupported format, this resolves inside ~100ms.
    import time
    for _ in range(50):
        j = jobs.get_job(job_id)
        if j and j.is_terminal():
            break
        time.sleep(0.01)
    assert j.state == jobs.STATE_FAILED
    assert j.error_code == "unsupported_format"
