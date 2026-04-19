"""Imagen-backed character-art generation (Phase 8).

Given an assembled prompt string, ``generate_image`` POSTs to the
Imagen REST endpoint, decodes the returned base64 bytes, and hands
back raw PNG bytes the caller pipes through ``art_image.validate_upload``.

No use of ``google-generativeai``; we make plain ``httpx`` calls, same
pattern as ``import_llm.py`` and ``services/sheets.py`` - keeps the
startup cost low on the 512 MB Fly machine.

Test stub: when ``ART_GEN_USE_TEST_STUB=1`` the HTTP call is skipped
and one of three canned PNGs from
``tests/import_fixtures/art/stub_outputs/`` is returned based on
keywords in the prompt. This lets clicktests drive the full
generation flow end-to-end without a real Imagen API key.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_ART_MODEL = "imagen-4.0-generate-001"
DEFAULT_ASPECT_RATIO = "3:4"   # Matches HEADSHOT_ASPECT_RATIO (3/4 portrait)
DEFAULT_SAMPLE_COUNT = 1


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:  # pragma: no cover - deploy-time typo, not covered by tests
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:  # pragma: no cover - deploy-time typo
        return default


ART_GEN_TIMEOUT_SEC = _env_int("ART_GEN_TIMEOUT_SEC", 60)
ART_GEN_RETRY_BACKOFF_SEC = _env_float("ART_GEN_RETRY_BACKOFF_SEC", 2.0)


def art_model() -> str:
    return os.environ.get("GEMINI_ART_MODEL", DEFAULT_ART_MODEL)


def _stub_mode() -> bool:
    return os.environ.get("ART_GEN_USE_TEST_STUB", "").lower() in (
        "1", "true", "yes", "on",
    )


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ImageGenNotConfiguredError(
            "GEMINI_API_KEY is not set; art generation is disabled."
        )
    return key


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImageGenerationError(Exception):
    """Base class for failures the route layer catches + surfaces."""
    error_code: str = "gen_error"
    user_message: str = (
        "Art generation failed. Please try again in a few minutes."
    )


class ImageGenNotConfiguredError(ImageGenerationError):
    """Missing ``GEMINI_API_KEY``."""
    error_code = "gen_not_configured"
    user_message = (
        "Art generation is not configured on this server. Contact the GM."
    )


class ImageTransportError(ImageGenerationError):
    """Network failure or persistent 5xx from Imagen."""
    error_code = "gen_transport"


class ImageRateLimitError(ImageGenerationError):
    """Imagen returned HTTP 429 after retries (shared quota)."""
    error_code = "gen_rate_limited"
    user_message = (
        "Our image provider is rate-limiting us. Try again shortly."
    )


class ImageInvalidResponseError(ImageGenerationError):
    """200 from Imagen but the body didn't contain PNG bytes."""
    error_code = "gen_invalid_response"


# ---------------------------------------------------------------------------
# Test stub
# ---------------------------------------------------------------------------


_STUB_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "tests" / "import_fixtures" / "art" / "stub_outputs"
)


def _stub_bytes_for(prompt: str) -> bytes:
    """Pick a canned stub PNG based on keywords in the prompt.

    Keywords that reach here are lowercased versions of the clan name;
    the mad-libs prefix always embeds the clan, so this matching is
    deterministic for any real test case.
    """
    p = (prompt or "").lower()
    if "wasp" in p:
        path = _STUB_DIR / "wasp.png"
    elif "scorpion" in p:
        path = _STUB_DIR / "scorpion.png"
    else:
        path = _STUB_DIR / "fallback.png"
    return path.read_bytes()


# ---------------------------------------------------------------------------
# HTTP primitives
# ---------------------------------------------------------------------------


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _imagen_url(model: str) -> str:
    return f"{GEMINI_BASE_URL}/models/{model}:predict"


def _build_request_body(
    prompt: str,
    *,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
) -> dict:
    return {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": sample_count,
            "aspectRatio": aspect_ratio,
        },
    }


def _post_json(
    url: str, body: dict, *, api_key: str, timeout: int,
) -> httpx.Response:
    with httpx.Client(timeout=timeout) as client:
        return client.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": api_key,
            },
        )


def _extract_png_bytes(body: dict) -> bytes:
    """Pull the first generated image's bytes out of the Imagen response.

    Imagen returns ``{"predictions": [{"bytesBase64Encoded": "..."}]}``.
    Any shape deviation raises ``ImageInvalidResponseError`` so the caller
    can convert to a user-visible banner.
    """
    preds = body.get("predictions") if isinstance(body, dict) else None
    if not isinstance(preds, list) or not preds:
        raise ImageInvalidResponseError(
            "Imagen response missing 'predictions'."
        )
    first = preds[0]
    if not isinstance(first, dict):
        raise ImageInvalidResponseError(
            "Imagen response 'predictions[0]' is not an object."
        )
    b64 = first.get("bytesBase64Encoded")
    if not isinstance(b64, str) or not b64:
        raise ImageInvalidResponseError(
            "Imagen response missing 'bytesBase64Encoded'."
        )
    try:
        return base64.b64decode(b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ImageInvalidResponseError(
            "Imagen response bytesBase64Encoded was not valid base64."
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_image(prompt: str, *, max_retries: int = 1) -> bytes:
    """Generate a single image for ``prompt`` and return raw PNG bytes.

    Retries once on transient 5xx / 429 / timeouts, then raises the
    corresponding typed exception. The caller (the async job worker)
    catches these and records the error on the job so the progress
    poller can surface a banner.
    """
    if _stub_mode():
        return _stub_bytes_for(prompt)

    url = _imagen_url(art_model())
    api_key = _api_key()
    body = _build_request_body(prompt)

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            response = _post_json(
                url, body, api_key=api_key, timeout=ART_GEN_TIMEOUT_SEC,
            )
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(ART_GEN_RETRY_BACKOFF_SEC)
                continue
            raise ImageTransportError(
                f"Imagen request timed out after {ART_GEN_TIMEOUT_SEC}s."
            ) from exc
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(ART_GEN_RETRY_BACKOFF_SEC)
                continue
            raise ImageTransportError(
                f"Imagen request failed: {exc}"
            ) from exc

        if response.status_code == 200:
            try:
                parsed = response.json()
            except ValueError as exc:
                raise ImageInvalidResponseError(
                    "Imagen returned 200 but the body was not JSON."
                ) from exc
            return _extract_png_bytes(parsed)

        if response.status_code in _RETRYABLE_STATUS:
            if attempt < max_retries:
                time.sleep(ART_GEN_RETRY_BACKOFF_SEC)
                continue
            if response.status_code == 429:
                raise ImageRateLimitError(
                    "Imagen returned 429 (rate limit / quota) after retries."
                )
            raise ImageTransportError(
                f"Imagen returned HTTP {response.status_code} after retries."
            )

        # Non-retryable 4xx - surface the body for the log so we can
        # diagnose auth / bad-request issues.
        detail = _safe_error_detail(response)
        raise ImageTransportError(
            f"Imagen returned HTTP {response.status_code}: {detail}"
        )

    # Unreachable; the loop always returns or raises.
    raise ImageTransportError(  # pragma: no cover - defensive
        f"Imagen retries exhausted; last error: {last_exc}"
    )


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str):
                return msg
    return json.dumps(body)[:200]


__all__ = [
    "DEFAULT_ART_MODEL",
    "DEFAULT_ASPECT_RATIO",
    "ImageGenerationError",
    "ImageGenNotConfiguredError",
    "ImageInvalidResponseError",
    "ImageRateLimitError",
    "ImageTransportError",
    "art_model",
    "generate_image",
]
