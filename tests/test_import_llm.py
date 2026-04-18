"""Tests for app/services/import_schema.py and app/services/import_llm.py.

All Gemini calls are stubbed via ``httpx.MockTransport``. Tests never hit
the real API, and never reference the real ``GEMINI_API_KEY``; every test
sets its own fake key through monkeypatch.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any, Callable, Dict, List

import httpx
import pytest
from pydantic import ValidationError

from app.services import import_llm as llm
from app.services import import_schema as schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-key")
    # Lower backoff so retry tests are instantaneous.
    monkeypatch.setattr(llm, "IMPORT_LLM_RETRY_BACKOFF_SEC", 0.0)


def _install_transport(
    monkeypatch, handler: Callable[[httpx.Request], httpx.Response]
) -> List[httpx.Request]:
    """Route every httpx call through ``handler`` and return the list of
    captured requests for inspection by the caller."""
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


def _response_200(payload_json: str) -> httpx.Response:
    body = {
        "candidates": [{
            "content": {"parts": [{"text": payload_json}]},
            "finishReason": "STOP",
        }],
    }
    return httpx.Response(200, json=body)


def _canonical_llm_payload() -> Dict[str, Any]:
    """The LLM-side equivalent of canonical.expected.json's character
    block, shaped to match GEMINI_RESPONSE_SCHEMA."""
    return {
        "name": "Kakita Tomoe",
        "player_name": "Eli",
        "school_name_as_written": "Kakita Duelist",
        "school_ring_choice": "Fire",
        "rings": {"air": 2, "fire": 4, "earth": 2, "water": 3, "void": 2},
        "attack": 3,
        "parry": 3,
        "skills": [
            {"name_as_written": "Etiquette", "rank": 3},
            {"name_as_written": "Sincerity", "rank": 3},
        ],
        "knacks": [
            {"name_as_written": "Iaijutsu", "rank": 3},
            {"name_as_written": "Double Attack", "rank": 2},
            {"name_as_written": "Lunge", "rank": 2},
        ],
        "advantages": [
            {"name_as_written": "Virtue", "detail": "Courage"},
            {"name_as_written": "Charming", "detail": ""},
        ],
        "disadvantages": [
            {"name_as_written": "Proud", "detail": ""},
        ],
        "first_dan_choices": [],
        "second_dan_choice": None,
        "honor": 3.0, "rank": 7.5, "recognition": 7.5,
        "starting_xp": 150,
        "source_stated_spent_xp": 118,
        "source_stated_earned_xp": 0,
        "source_stated_unspent_xp": 32,
        "freeform_sections": [
            {"label": "Background", "content": "Born to the Kakita family."},
        ],
        "multi_character_detected": False,
        "not_a_character_sheet": False,
        "ambiguities": [],
        "per_field_confidence": {"name": "high"},
    }


def _sparse_llm_payload() -> Dict[str, Any]:
    """Near-empty extraction: flash couldn't find anything useful."""
    return {
        "name": None,
        "player_name": None,
        "school_name_as_written": None,
        "school_ring_choice": None,
        "rings": {"air": None, "fire": None, "earth": None, "water": None, "void": None},
        "attack": None,
        "parry": None,
        "skills": [],
        "knacks": [],
        "advantages": [],
        "disadvantages": [],
        "first_dan_choices": [],
        "second_dan_choice": None,
        "honor": None,
        "rank": None,
        "recognition": None,
        "starting_xp": None,
        "source_stated_spent_xp": None,
        "source_stated_earned_xp": None,
        "source_stated_unspent_xp": None,
        "freeform_sections": [],
        "multi_character_detected": False,
        "not_a_character_sheet": False,
        "ambiguities": [],
        "per_field_confidence": {},
    }


# ---------------------------------------------------------------------------
# import_schema: Pydantic validation
# ---------------------------------------------------------------------------


def test_pydantic_accepts_canonical_payload() -> None:
    c = schema.ExtractedCharacter.model_validate(_canonical_llm_payload())
    assert c.name == "Kakita Tomoe"
    assert c.school_ring_choice == "Fire"
    assert c.rings.fire == 4
    assert c.skills[0].name_as_written == "Etiquette"
    assert c.advantages[0].detail == "Courage"
    assert c.multi_character_detected is False


def test_pydantic_ignores_extra_fields() -> None:
    """Gemini sometimes returns extra fields the schema doesn't declare;
    we must tolerate those silently rather than raising."""
    payload = _canonical_llm_payload()
    payload["unexpected_bonus_field"] = "ignored"
    schema.ExtractedCharacter.model_validate(payload)  # no raise


def test_pydantic_rejects_wrong_types_in_rings() -> None:
    payload = _canonical_llm_payload()
    payload["rings"]["fire"] = "four"  # should be int|None
    with pytest.raises(ValidationError):
        schema.ExtractedCharacter.model_validate(payload)


def test_pydantic_rejects_skill_with_missing_rank() -> None:
    payload = _canonical_llm_payload()
    payload["skills"].append({"name_as_written": "Bragging"})
    with pytest.raises(ValidationError):
        schema.ExtractedCharacter.model_validate(payload)


def test_defaults_allow_minimal_payload() -> None:
    """All list / object fields default to empty, so an LLM that returns
    only the identity fields still parses."""
    c = schema.ExtractedCharacter.model_validate({
        "name": "Kakita Tomoe",
    })
    assert c.skills == []
    assert c.advantages == []
    assert c.rings.fire is None


# ---------------------------------------------------------------------------
# looks_too_sparse heuristic
# ---------------------------------------------------------------------------


def test_looks_too_sparse_true_when_everything_empty() -> None:
    c = schema.ExtractedCharacter.model_validate(_sparse_llm_payload())
    assert schema.looks_too_sparse(c) is True


def test_looks_too_sparse_false_for_full_character() -> None:
    c = schema.ExtractedCharacter.model_validate(_canonical_llm_payload())
    assert schema.looks_too_sparse(c) is False


def test_looks_too_sparse_respects_not_a_character_sheet_flag() -> None:
    """If the LLM explicitly says 'this isn't a sheet', we do NOT retry -
    the rejection is the right outcome, not a sparse-result symptom."""
    payload = _sparse_llm_payload()
    payload["not_a_character_sheet"] = True
    c = schema.ExtractedCharacter.model_validate(payload)
    assert schema.looks_too_sparse(c) is False


def test_looks_too_sparse_triggers_on_missing_identity_even_with_rings() -> None:
    """An LLM result that somehow has rings but no name or school is
    still considered a flash-fumble worth retrying."""
    payload = _sparse_llm_payload()
    payload["rings"] = {"air": 2, "fire": 3, "earth": 2, "water": 2, "void": 2}
    c = schema.ExtractedCharacter.model_validate(payload)
    assert schema.looks_too_sparse(c) is True


# ---------------------------------------------------------------------------
# GEMINI_RESPONSE_SCHEMA structural sanity
# ---------------------------------------------------------------------------


def test_response_schema_is_openapi_style_object() -> None:
    s = schema.GEMINI_RESPONSE_SCHEMA
    assert s["type"] == "OBJECT"
    assert "rings" in s["properties"]
    # Gemini's dialect uses uppercase type names.
    assert s["properties"]["rings"]["type"] == "OBJECT"
    # Rejection flags must be in the required list so the model always
    # sets them one way or the other.
    assert "multi_character_detected" in s["required"]
    assert "not_a_character_sheet" in s["required"]


def test_response_schema_constrains_school_ring_choice_to_enum() -> None:
    enum = schema.GEMINI_RESPONSE_SCHEMA["properties"]["school_ring_choice"]["enum"]
    assert set(enum) == {"Air", "Fire", "Earth", "Water", "Void"}


# ---------------------------------------------------------------------------
# import_llm: happy path
# ---------------------------------------------------------------------------


def test_extract_character_happy_path(monkeypatch) -> None:
    _fake_key(monkeypatch)
    payload = _canonical_llm_payload()

    def handler(req: httpx.Request) -> httpx.Response:
        return _response_200(json.dumps(payload))

    captured = _install_transport(monkeypatch, handler)
    result = llm.extract_character("Kakita Tomoe, Kakita Duelist ...")
    assert isinstance(result, schema.ExtractedCharacter)
    assert result.name == "Kakita Tomoe"
    assert result.rings.fire == 4

    # One request was sent.
    assert len(captured) == 1
    req = captured[0]
    assert req.headers["X-goog-api-key"] == "test-fake-key"
    assert req.url.path.endswith(":generateContent")
    # Primary model is flash by default.
    assert "gemini-2.5-flash" in req.url.path


def test_request_body_wraps_document_and_uses_response_schema(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        # System instruction contains the injection guardrail text.
        sys_text = body["systemInstruction"]["parts"][0]["text"]
        assert "UNTRUSTED DATA" in sys_text
        assert "ignore previous instructions" in sys_text.lower()
        # Document is wrapped in <document>...</document> tags.
        user_text = body["contents"][0]["parts"][0]["text"]
        assert "<document>" in user_text
        assert "</document>" in user_text
        assert "Kakita Tomoe" in user_text
        # Response schema hooked in and JSON mime-type forced.
        cfg = body["generationConfig"]
        assert cfg["responseMimeType"] == "application/json"
        assert cfg["responseSchema"]["type"] == "OBJECT"
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    llm.extract_character("Document text mentioning Kakita Tomoe.")


def test_user_document_is_in_user_role_not_system(monkeypatch) -> None:
    """The system instruction must NOT contain the untrusted document;
    mixing them is the primary attack vector for injection."""
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        sys_text = body["systemInstruction"]["parts"][0]["text"]
        assert "MY_SECRET_DOCUMENT_MARKER" not in sys_text
        # Contents must be a user turn.
        assert body["contents"][0]["role"] == "user"
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    llm.extract_character("MY_SECRET_DOCUMENT_MARKER")


# ---------------------------------------------------------------------------
# Transport retry
# ---------------------------------------------------------------------------


def test_transient_5xx_retries_once_then_succeeds(monkeypatch) -> None:
    _fake_key(monkeypatch)
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(503, json={"error": {"message": "temp"}})
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    result = llm.extract_character("doc")
    assert result.name == "Kakita Tomoe"
    assert call_count["n"] == 2


def test_persistent_5xx_raises_transport_error(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": {"message": "bad gateway"}})

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiTransportError) as info:
        llm.extract_character("doc")
    assert "502" in str(info.value)


def test_429_after_retries_raises_rate_limit(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429,
                              json={"error": {"message": "quota exhausted"}})

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiRateLimitError):
        llm.extract_character("doc")


def test_timeout_retries_then_raises(monkeypatch) -> None:
    _fake_key(monkeypatch)
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        raise httpx.TimeoutException("slow network")

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiTransportError) as info:
        llm.extract_character("doc")
    assert "timed out" in str(info.value)
    # One initial + one retry.
    assert call_count["n"] == 2


def test_timeout_then_success(monkeypatch) -> None:
    _fake_key(monkeypatch)
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.TimeoutException("slow network")
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    result = llm.extract_character("doc")
    assert result.name == "Kakita Tomoe"


def test_generic_http_error_retries_then_raises(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns down")

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiTransportError):
        llm.extract_character("doc")


def test_generic_http_error_retry_then_success(monkeypatch) -> None:
    _fake_key(monkeypatch)
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.ConnectError("dns down")
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    result = llm.extract_character("doc")
    assert result.name == "Kakita Tomoe"


def test_non_retryable_4xx_fails_immediately(monkeypatch) -> None:
    _fake_key(monkeypatch)
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(400,
                              json={"error": {"message": "bad request"}})

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiTransportError) as info:
        llm.extract_character("doc")
    assert "400" in str(info.value)
    # No retry on non-retryable 4xx.
    assert call_count["n"] == 1


def test_non_retryable_4xx_with_non_json_body(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"html login page")

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiTransportError) as info:
        llm.extract_character("doc")
    # Non-JSON body must still surface a usable message.
    assert "401" in str(info.value)


# ---------------------------------------------------------------------------
# Invalid response bodies
# ---------------------------------------------------------------------------


def test_200_with_non_json_body_raises_invalid_response(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiInvalidResponseError):
        llm.extract_character("doc")


def test_empty_candidates_raises_invalid_response(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiInvalidResponseError) as info:
        llm.extract_character("doc")
    assert "no candidates" in str(info.value).lower()


def test_candidate_with_empty_text_raises_invalid_response(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": ""}]},
                            "finishReason": "MAX_TOKENS"}],
        })

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiInvalidResponseError) as info:
        llm.extract_character("doc")
    assert "MAX_TOKENS" in str(info.value)


def test_candidate_body_unparseable_json_raises_invalid_response(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        # Response metadata is JSON, but the candidate text isn't.
        return _response_200("not JSON {")

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiInvalidResponseError) as info:
        llm.extract_character("doc")
    assert "not parsable" in str(info.value).lower()


def test_candidate_body_violates_schema_raises_invalid_response(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        payload = _canonical_llm_payload()
        payload["rings"]["fire"] = "four"  # wrong type
        return _response_200(json.dumps(payload))

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiInvalidResponseError):
        llm.extract_character("doc")


# ---------------------------------------------------------------------------
# API key presence
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_config_error(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(llm.GeminiConfigError):
        llm.extract_character("doc")


def test_blank_api_key_is_treated_as_missing(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(llm.GeminiConfigError):
        llm.extract_character("doc")


# ---------------------------------------------------------------------------
# extract_with_fallback (model-upgrade retry)
# ---------------------------------------------------------------------------


def test_fallback_not_triggered_when_primary_is_good(monkeypatch) -> None:
    _fake_key(monkeypatch)
    calls: List[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    outcome = llm.extract_with_fallback("doc")
    assert outcome.fallback_used is False
    assert "flash" in outcome.model_used
    # Exactly one call: primary model only.
    assert len(calls) == 1


def test_fallback_triggered_when_primary_is_sparse(monkeypatch) -> None:
    _fake_key(monkeypatch)
    calls: List[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if "flash" in req.url.path:
            return _response_200(json.dumps(_sparse_llm_payload()))
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    outcome = llm.extract_with_fallback("doc")
    assert outcome.fallback_used is True
    assert "pro" in outcome.model_used
    assert outcome.character.name == "Kakita Tomoe"
    # One flash, one pro.
    assert len(calls) == 2
    assert any("flash" in c for c in calls)
    assert any("pro" in c for c in calls)


def test_fallback_keeps_primary_when_pro_also_sparse(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return _response_200(json.dumps(_sparse_llm_payload()))

    _install_transport(monkeypatch, handler)
    outcome = llm.extract_with_fallback("doc")
    # Both sparse -> the orchestrator keeps whatever was returned; the
    # subsequent "not a character sheet" handling happens upstream.
    assert outcome.character.name is None


def test_fallback_when_primary_raises(monkeypatch) -> None:
    _fake_key(monkeypatch)
    calls: List[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if "flash" in req.url.path:
            # Primary fails with a non-retryable error.
            return httpx.Response(400, json={"error": {"message": "bad"}})
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    outcome = llm.extract_with_fallback("doc")
    assert outcome.fallback_used is True
    assert "pro" in outcome.model_used
    assert outcome.character.name == "Kakita Tomoe"
    # Warning explains what happened.
    assert any("failed" in w for w in outcome.warnings)


def test_fallback_failure_preserves_primary_result(monkeypatch) -> None:
    """Primary returned sparse; fallback errored. Better to hand back
    what primary gave us than lose the whole extraction."""
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        if "flash" in req.url.path:
            return _response_200(json.dumps(_sparse_llm_payload()))
        return httpx.Response(400, json={"error": {"message": "pro is down"}})

    _install_transport(monkeypatch, handler)
    outcome = llm.extract_with_fallback("doc")
    assert outcome.fallback_used is False
    assert outcome.character.name is None  # primary's sparse result
    assert any("Flash-to-pro fallback failed" in w for w in outcome.warnings)


def test_fallback_prefers_primary_when_pro_worse(monkeypatch) -> None:
    """Rare case: primary returned a half-decent result, pro came back
    sparser. The orchestrator must not downgrade."""
    _fake_key(monkeypatch)

    primary_partial = _sparse_llm_payload()
    # Partial: enough to be 'not sparse' by the heuristic
    primary_partial["name"] = "Kakita Tomoe"
    primary_partial["rings"] = {"air": 2, "fire": 3, "earth": 2, "water": 2, "void": 2}

    def handler(req: httpx.Request) -> httpx.Response:
        if "flash" in req.url.path:
            return _response_200(json.dumps(primary_partial))
        # Pro returns strictly sparse.
        return _response_200(json.dumps(_sparse_llm_payload()))

    _install_transport(monkeypatch, handler)
    outcome = llm.extract_with_fallback("doc")
    # Primary was already "not sparse" -> fallback not triggered.
    assert outcome.fallback_used is False
    assert outcome.character.name == "Kakita Tomoe"


# ---------------------------------------------------------------------------
# extract_single_field
# ---------------------------------------------------------------------------


def test_extract_single_field_with_enum(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        user_text = body["contents"][0]["parts"][-1]["text"]
        assert "ONLY the school_ring_choice" in user_text
        assert "Air, Fire, Earth, Water, Void" in user_text
        # Single-field schema: one "value" key.
        schema_dict = body["generationConfig"]["responseSchema"]
        assert "value" in schema_dict["properties"]
        return _response_200(json.dumps({"value": "Fire"}))

    _install_transport(monkeypatch, handler)
    v = llm.extract_single_field(
        "Document text...",
        "school_ring_choice",
        field_description="Which ring is this school built around?",
        valid_values=["Air", "Fire", "Earth", "Water", "Void"],
    )
    assert v == "Fire"


def test_extract_single_field_without_enum_allows_free_string(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        # No enum when valid_values is None.
        schema_dict = body["generationConfig"]["responseSchema"]
        value_schema = schema_dict["properties"]["value"]
        assert "enum" not in value_schema
        return _response_200(json.dumps({"value": "Kakita Tomoe"}))

    _install_transport(monkeypatch, handler)
    v = llm.extract_single_field(
        "doc", "name",
        field_description="Character name.",
    )
    assert v == "Kakita Tomoe"


def test_extract_single_field_returns_none_when_not_in_source(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return _response_200(json.dumps({"value": None}))

    _install_transport(monkeypatch, handler)
    v = llm.extract_single_field("doc", "name", field_description="x")
    assert v is None


def test_extract_single_field_invalid_json_raises(monkeypatch) -> None:
    _fake_key(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return _response_200("not json")

    _install_transport(monkeypatch, handler)
    with pytest.raises(llm.GeminiInvalidResponseError):
        llm.extract_single_field("doc", "name", field_description="x")


# ---------------------------------------------------------------------------
# Multimodal PDF path
# ---------------------------------------------------------------------------


def _make_small_pdf(pages: int) -> bytes:
    """Build a minimal N-page PDF via reportlab (same library we already
    use in the fixture regenerator)."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for _ in range(pages):
        c.drawString(100, 700, "Page content")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_multimodal_call_sends_image_parts(monkeypatch) -> None:
    _fake_key(monkeypatch)
    pdf_bytes = _make_small_pdf(2)
    observed_parts: List[Dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        observed_parts.extend(body["contents"][0]["parts"])
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    llm.extract_character("minor extracted text", pdf_bytes_for_multimodal=pdf_bytes)

    # Image parts appear before the document text.
    image_parts = [p for p in observed_parts if "inlineData" in p]
    assert len(image_parts) == 2
    for p in image_parts:
        assert p["inlineData"]["mimeType"] == "image/png"
        # Base64 payload must decode to a real PNG header.
        raw = base64.b64decode(p["inlineData"]["data"])
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_multimodal_truncates_long_pdfs_and_records_warning(monkeypatch) -> None:
    _fake_key(monkeypatch)
    monkeypatch.setattr(llm, "IMPORT_MAX_PDF_PAGES", 3)
    pdf_bytes = _make_small_pdf(5)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        image_parts = [p for p in body["contents"][0]["parts"] if "inlineData" in p]
        assert len(image_parts) == 3
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    result = llm.extract_character("", pdf_bytes_for_multimodal=pdf_bytes)
    # The truncation warning lands on the character as an ambiguity entry
    # so Phase 5's Import Notes builder can surface it.
    assert any("multimodal_pdf" == a.field for a in result.ambiguities)
    assert any("beyond the" in a.note for a in result.ambiguities)


# ---------------------------------------------------------------------------
# Environment-driven overrides
# ---------------------------------------------------------------------------


def test_model_env_vars_are_read_per_call(monkeypatch) -> None:
    _fake_key(monkeypatch)
    monkeypatch.setenv("GEMINI_MODEL_PRIMARY", "some-custom-flash")
    seen: List[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        return _response_200(json.dumps(_canonical_llm_payload()))

    _install_transport(monkeypatch, handler)
    llm.extract_character("doc")
    assert any("some-custom-flash" in p for p in seen)


def test_invalid_integer_env_var_falls_through_to_default(monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_MAX_PDF_PAGES", "not-a-number")
    # The getter is called at import-time, so we simply re-exercise it.
    assert llm._env_int("IMPORT_MAX_PDF_PAGES", 10) == 10


def test_invalid_float_env_var_falls_through_to_default(monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_LLM_RETRY_BACKOFF_SEC", "not-a-float")
    assert llm._env_float("IMPORT_LLM_RETRY_BACKOFF_SEC", 2.0) == 2.0
