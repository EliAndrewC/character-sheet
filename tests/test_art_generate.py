"""Tests for ``app.services.art_generate``.

Covers the real Imagen HTTP path (mocked via ``httpx.MockTransport``),
the stub mode used by e2e tests, and all the typed error branches.
"""

from __future__ import annotations

import base64
import io
from typing import Callable
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

from app.services import art_generate


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _png_bytes(width: int = 384, height: int = 512) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 120, 140))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _imagen_response(png: bytes) -> httpx.Response:
    b64 = base64.b64encode(png).decode("ascii")
    return httpx.Response(
        200, json={"predictions": [{"bytesBase64Encoded": b64}]},
    )


def _install_transport(
    monkeypatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Swap ``httpx.Client`` so every ``.post`` in this test uses ``handler``."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)


def _fast_retries(monkeypatch) -> None:
    monkeypatch.setattr(art_generate, "ART_GEN_RETRY_BACKOFF_SEC", 0.0)


@pytest.fixture(autouse=True)
def _real_mode(monkeypatch):
    """Most tests exercise the real HTTP path; the stub-mode tests opt in."""
    monkeypatch.delenv("ART_GEN_USE_TEST_STUB", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _fast_retries(monkeypatch)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_model(self, monkeypatch):
        monkeypatch.delenv("GEMINI_ART_MODEL", raising=False)
        assert art_generate.art_model() == "imagen-4.0-generate-001"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("GEMINI_ART_MODEL", "custom-model-x")
        assert art_generate.art_model() == "custom-model-x"

    def test_api_key_missing_raises_not_configured(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(art_generate.ImageGenNotConfiguredError):
            art_generate._api_key()

    def test_api_key_whitespace_only_raises_not_configured(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "   ")
        with pytest.raises(art_generate.ImageGenNotConfiguredError):
            art_generate._api_key()


# ---------------------------------------------------------------------------
# Happy path via mocked httpx
# ---------------------------------------------------------------------------


class TestGenerateImageHappyPath:
    def test_returns_decoded_png_bytes(self, monkeypatch):
        png = _png_bytes()
        _install_transport(monkeypatch, lambda _req: _imagen_response(png))
        out = art_generate.generate_image("any prompt")
        assert out == png

    def test_posts_to_predict_endpoint(self, monkeypatch):
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            seen["body"] = req.content
            seen["api_key"] = req.headers.get("X-goog-api-key")
            return _imagen_response(_png_bytes())

        _install_transport(monkeypatch, handler)
        art_generate.generate_image("prompt X")
        assert seen["url"].endswith(":predict")
        # httpx serialises without spaces between keys/values
        assert b'"prompt":"prompt X"' in seen["body"]
        assert b'"aspectRatio":"3:4"' in seen["body"]
        assert seen["api_key"] == "fake-key"

    def test_custom_model_used_in_url(self, monkeypatch):
        monkeypatch.setenv("GEMINI_ART_MODEL", "imagen-4.0-preview")
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            return _imagen_response(_png_bytes())

        _install_transport(monkeypatch, handler)
        art_generate.generate_image("p")
        assert "imagen-4.0-preview" in seen["url"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestRetryAndErrors:
    def test_500_retries_once_then_raises_transport_error(self, monkeypatch):
        calls = {"n": 0}

        def handler(_req):
            calls["n"] += 1
            return httpx.Response(500, text="upstream broken")

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageTransportError):
            art_generate.generate_image("p")
        # Retry happens once: 2 total calls
        assert calls["n"] == 2

    def test_429_retries_then_raises_rate_limit_error(self, monkeypatch):
        def handler(_req):
            return httpx.Response(429, text="quota exhausted")

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageRateLimitError):
            art_generate.generate_image("p")

    def test_transient_500_then_success(self, monkeypatch):
        """First attempt returns 500, retry returns 200 - expect success."""
        calls = {"n": 0}

        def handler(_req):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(500)
            return _imagen_response(_png_bytes())

        _install_transport(monkeypatch, handler)
        out = art_generate.generate_image("p")
        assert len(out) > 0
        assert calls["n"] == 2

    def test_timeout_raises_transport_error(self, monkeypatch):
        def handler(_req):
            raise httpx.TimeoutException("slow")

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageTransportError):
            art_generate.generate_image("p")

    def test_generic_http_error_raises_transport_error(self, monkeypatch):
        def handler(_req):
            raise httpx.ConnectError("unreachable")

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageTransportError):
            art_generate.generate_image("p")

    def test_non_retryable_4xx_raises_transport_error(self, monkeypatch):
        def handler(_req):
            return httpx.Response(
                400, json={"error": {"message": "bad prompt structure"}},
            )

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageTransportError, match="bad prompt"):
            art_generate.generate_image("p")

    def test_400_with_non_json_body_falls_back_to_truncated_text(self, monkeypatch):
        def handler(_req):
            return httpx.Response(400, text="raw text error" * 100)

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageTransportError, match="raw text"):
            art_generate.generate_image("p")

    def test_400_with_json_but_no_error_key(self, monkeypatch):
        """Errors that aren't shaped like Google's ``{"error": {"message": ...}}``
        fall through to a truncated JSON dump."""
        def handler(_req):
            return httpx.Response(400, json={"unexpected": "payload"})

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageTransportError, match="unexpected"):
            art_generate.generate_image("p")


class TestInvalidResponseBody:
    def test_200_but_non_json_body_raises(self, monkeypatch):
        def handler(_req):
            return httpx.Response(
                200, content=b"not json", headers={"Content-Type": "application/json"},
            )

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageInvalidResponseError):
            art_generate.generate_image("p")

    def test_200_missing_predictions(self, monkeypatch):
        def handler(_req):
            return httpx.Response(200, json={"not_predictions": []})

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageInvalidResponseError,
                            match="missing 'predictions'"):
            art_generate.generate_image("p")

    def test_200_predictions_not_a_list(self, monkeypatch):
        def handler(_req):
            return httpx.Response(200, json={"predictions": "oops"})

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageInvalidResponseError):
            art_generate.generate_image("p")

    def test_200_predictions_item_not_an_object(self, monkeypatch):
        def handler(_req):
            return httpx.Response(200, json={"predictions": [["string", "list"]]})

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageInvalidResponseError,
                            match="not an object"):
            art_generate.generate_image("p")

    def test_200_missing_bytes_base64_encoded(self, monkeypatch):
        def handler(_req):
            return httpx.Response(200, json={"predictions": [{"foo": "bar"}]})

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageInvalidResponseError,
                            match="missing 'bytesBase64Encoded'"):
            art_generate.generate_image("p")

    def test_200_invalid_base64(self, monkeypatch):
        def handler(_req):
            return httpx.Response(
                200,
                json={"predictions": [{"bytesBase64Encoded": "!!!not-base64!!!"}]},
            )

        _install_transport(monkeypatch, handler)
        with pytest.raises(art_generate.ImageInvalidResponseError,
                            match="not valid base64"):
            art_generate.generate_image("p")


# ---------------------------------------------------------------------------
# Stub mode
# ---------------------------------------------------------------------------


class TestStubMode:
    def test_wasp_prompt_returns_wasp_stub(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", "1")
        out = art_generate.generate_image(
            "A portrait of a Wasp clan noble..."
        )
        # The committed fixture decodes
        img = Image.open(io.BytesIO(out))
        assert img.size == (384, 512)
        assert img.format == "PNG"

    def test_scorpion_prompt_returns_scorpion_stub(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", "1")
        out = art_generate.generate_image(
            "A portrait of a Scorpion clan noble..."
        )
        img = Image.open(io.BytesIO(out))
        assert img.size == (384, 512)

    def test_unknown_keyword_returns_fallback_stub(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", "1")
        out = art_generate.generate_image("some unrelated text")
        img = Image.open(io.BytesIO(out))
        assert img.size == (384, 512)

    def test_stub_mode_does_not_hit_http(self, monkeypatch):
        """Stub mode must not touch httpx.Client at all (no API key needed)."""
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", "1")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        called = {"n": 0}

        def handler(_req):
            called["n"] += 1
            return httpx.Response(500)

        _install_transport(monkeypatch, handler)
        art_generate.generate_image("anything")
        assert called["n"] == 0

    def test_stub_returns_distinct_content_per_keyword(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", "1")
        wasp = art_generate.generate_image("A portrait of a Wasp clan noble.")
        scorpion = art_generate.generate_image(
            "A portrait of a Scorpion clan noble."
        )
        fallback = art_generate.generate_image("neutral content")
        assert wasp != scorpion != fallback != wasp


class TestStubModeDetection:
    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
    def test_truthy_values_enable_stub(self, monkeypatch, val):
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", val)
        assert art_generate._stub_mode() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
    def test_falsy_values_leave_stub_off(self, monkeypatch, val):
        monkeypatch.setenv("ART_GEN_USE_TEST_STUB", val)
        assert art_generate._stub_mode() is False
