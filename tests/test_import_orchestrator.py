"""Unit tests for app/services/import_orchestrator.py.

All Gemini calls are stubbed via httpx.MockTransport. No real HTTP or
LLM traffic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import pytest

from app.services import import_llm as llm
from app.services.import_orchestrator import (
    CharacterReady,
    Rejected,
    orchestrate_import,
)


FIXTURES = Path(__file__).parent / "import_fixtures"
HAPPY = FIXTURES / "happy_path"
EDGES = FIXTURES / "edge_cases"


def _install_transport(
    monkeypatch, handler: Callable[[httpx.Request], httpx.Response]
) -> List[httpx.Request]:
    captured: List[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return handler(req)

    transport = httpx.MockTransport(wrapper)
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)
    return captured


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
        "name": "Kakita Tomoe",
        "player_name": "Eli",
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
        "first_dan_choices": [],
        "second_dan_choice": None,
        "honor": 3.0, "rank": 7.5, "recognition": 7.5,
        "starting_xp": 150,
        "source_stated_spent_xp": None,
        "source_stated_earned_xp": None,
        "source_stated_unspent_xp": None,
        "freeform_sections": [],
        "multi_character_detected": False,
        "not_a_character_sheet": False,
        "ambiguities": [],
        "per_field_confidence": {},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_file_happy_path_returns_character_ready(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()

    outcome = orchestrate_import(file_bytes=data,
                                 filename="happy_plaintext.txt")
    assert isinstance(outcome, CharacterReady)
    assert outcome.character_data["name"] == "Kakita Tomoe"
    assert outcome.character_data["school"] == "kakita_duelist"
    # Import Notes section always first.
    assert outcome.sections[0]["label"].startswith("Import Notes")
    # Model used defaults to primary flash when not sparse.
    assert "flash" in outcome.model_used
    assert outcome.fallback_used is False


def test_url_happy_path_returns_character_ready(monkeypatch) -> None:
    """Happy URL fetch through the orchestrator. The URL module's SSRF
    defense is tested in its own suite; here we just verify the chain."""
    _fake_key(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    from app.services import import_url as url_mod
    monkeypatch.setattr(url_mod, "_RESOLVER", lambda host: ["8.8.8.8"])

    def handler(req: httpx.Request) -> httpx.Response:
        # Distinguish LLM vs source-URL traffic by host.
        if "generativelanguage.googleapis.com" in str(req.url):
            return _response_200(_canonical_llm_payload())
        return httpx.Response(200,
                              headers={"content-type": "text/plain"},
                              content=body)

    _install_transport(monkeypatch, handler)

    outcome = orchestrate_import(url="https://example.com/char.txt")
    assert isinstance(outcome, CharacterReady)
    assert outcome.character_data["name"] == "Kakita Tomoe"


# ---------------------------------------------------------------------------
# Rejection flag paths
# ---------------------------------------------------------------------------

def test_multi_character_flag_causes_rejection(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: _response_200(
        _canonical_llm_payload(multi_character_detected=True)
    ))
    data = (EDGES / "multi_character.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="multi_character.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "multi_character_document"
    assert "split" in outcome.user_message
    assert "per-character" in outcome.user_message


def test_not_a_character_sheet_flag_causes_rejection(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: _response_200(
        _canonical_llm_payload(
            not_a_character_sheet=True,
            name=None, school_name_as_written=None,
            rings={"air": None, "fire": None, "earth": None,
                   "water": None, "void": None},
        )
    ))
    data = (EDGES / "not_a_character_sheet.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="not_a_character_sheet.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "not_a_character_sheet"
    assert "doesn't look like" in outcome.user_message


# ---------------------------------------------------------------------------
# Ingest-layer rejections surface with the right error_code
# ---------------------------------------------------------------------------

def test_oversize_file_rejected_without_touching_llm(monkeypatch) -> None:
    _fake_key(monkeypatch)
    # If the LLM were called, this would fail the test.
    _install_transport(monkeypatch, lambda req: pytest.fail(
        "LLM must not be called for oversize file"
    ))
    big = b"x" * (2 * 1024 * 1024)  # 2 MB, over the 1 MB cap
    outcome = orchestrate_import(file_bytes=big, filename="big.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "file_too_large"


def test_unsupported_format_rejected(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: pytest.fail(
        "LLM must not be called for unsupported format"
    ))
    outcome = orchestrate_import(
        file_bytes=b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 200,
        filename="a.out",
    )
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "unsupported_format"


def test_missing_source_rejected() -> None:
    outcome = orchestrate_import()
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "no_source"


def test_url_ssrf_rejected_without_touching_llm(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: pytest.fail(
        "LLM must not be called when URL is SSRF-blocked"
    ))
    outcome = orchestrate_import(url="http://127.0.0.1/char.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "url_blocked_ssrf"


def test_private_google_doc_rejected(monkeypatch) -> None:
    _fake_key(monkeypatch)
    from app.services import import_url as url_mod
    monkeypatch.setattr(url_mod, "_RESOLVER",
                        lambda host: ["142.250.0.1"])

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={
            "location": "https://accounts.google.com/ServiceLogin",
        })

    _install_transport(monkeypatch, handler)
    doc_url = ("https://docs.google.com/document/d/"
               "1AbCdEfGh_ijklmnopqrSTUVWXYZ0123456/edit")
    outcome = orchestrate_import(url=doc_url)
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "document_not_public"


# ---------------------------------------------------------------------------
# LLM-layer rejections
# ---------------------------------------------------------------------------

def test_gemini_missing_key_rejected(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="happy_plaintext.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "gemini_not_configured"


def test_gemini_rate_limit_rejected(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: httpx.Response(429, json={"error": {}}))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="happy_plaintext.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "gemini_rate_limited"


def test_gemini_transport_error_rejected(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: httpx.Response(500, json={"error": {}}))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="happy_plaintext.txt")
    assert isinstance(outcome, Rejected)
    assert outcome.error_code == "gemini_transport_error"


def test_gemini_invalid_response_rejected(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch, lambda req: httpx.Response(200, json={
        "candidates": [{
            "content": {"parts": [{"text": "not JSON at all"}]},
            "finishReason": "STOP",
        }],
    }))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="happy_plaintext.txt")
    assert isinstance(outcome, Rejected)
    # The orchestrator sees this after flash-to-pro fallback fails too.
    assert outcome.error_code in (
        "gemini_invalid_response", "gemini_transport_error"
    )


# ---------------------------------------------------------------------------
# Warnings passthrough
# ---------------------------------------------------------------------------

def test_extraction_warnings_make_it_into_import_notes(monkeypatch) -> None:
    _fake_key(monkeypatch)
    # Serve sparse first (flash), then full (pro) so fallback fires.
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _response_200(_canonical_llm_payload(
                name=None, school_name_as_written=None,
                rings={"air": None, "fire": None, "earth": None,
                       "water": None, "void": None},
            ))
        return _response_200(_canonical_llm_payload())

    _install_transport(monkeypatch, handler)
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="happy_plaintext.txt")
    assert isinstance(outcome, CharacterReady)
    assert outcome.fallback_used is True
    # The extraction-warnings section appears in the Import Notes HTML.
    notes_html = outcome.sections[0]["html"]
    assert "pro" in notes_html.lower() or "fallback" in notes_html.lower()


# ---------------------------------------------------------------------------
# Source descriptor defaults
# ---------------------------------------------------------------------------

def test_source_descriptor_defaults_to_filename(monkeypatch) -> None:
    _fake_key(monkeypatch)
    _install_transport(monkeypatch,
                       lambda req: _response_200(_canonical_llm_payload()))
    data = (HAPPY / "happy_plaintext.txt").read_bytes()
    outcome = orchestrate_import(file_bytes=data,
                                 filename="my-character.txt")
    notes_html = outcome.sections[0]["html"]
    assert "my-character.txt" in notes_html
