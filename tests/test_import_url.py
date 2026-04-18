"""Tests for app/services/import_url.py.

Phase 3: the URL fetcher. We exercise the SSRF defenses, size cap,
redirect cap, Google Docs / Sheets rewriting, and public-access check.
No real HTTP happens; every request is served by ``httpx.MockTransport``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List

import httpx
import pytest

from app.services import import_ingest as ing
from app.services import import_url as url


FIXTURES = Path(__file__).parent / "import_fixtures"
HAPPY = FIXTURES / "happy_path"
URL_FIX = FIXTURES / "url"


# ---------------------------------------------------------------------------
# Helpers: inject a fake resolver (no real DNS) and a fake httpx transport.
# ---------------------------------------------------------------------------

def _fake_resolver(mapping: Dict[str, str]) -> Callable[[str], List[str]]:
    def resolver(host: str) -> List[str]:
        if host in mapping:
            return [mapping[host]]
        # Default for anything else: a genuinely public IP (Google DNS) so
        # non-SSRF tests aren't blocked. The TEST-NET-3 range (203.0.113/24)
        # looks public but is flagged by ipaddress.is_reserved, so we avoid
        # it here even though it's conventional for documentation.
        return ["8.8.8.8"]
    return resolver


def _install_transport(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _client)


def _install_resolver(monkeypatch, mapping: Dict[str, str] | None = None) -> None:
    monkeypatch.setattr(url, "_RESOLVER", _fake_resolver(mapping or {}))


# ---------------------------------------------------------------------------
# SSRF defenses
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", [
    "http://127.0.0.1/character.txt",
    "http://127.1.1.1/",
    "http://10.0.0.1/internal",
    "http://192.168.1.100/",
    "http://172.16.5.5/",
    "http://169.254.169.254/",  # AWS metadata
    "http://[::1]/",
    "http://[fc00::1]/",         # IPv6 unique local
])
def test_literal_private_addresses_are_blocked(target: str, monkeypatch) -> None:
    _install_resolver(monkeypatch)
    with pytest.raises(url.UrlBlockedError):
        url.ingest_url(target)


def test_dns_rebind_resolving_to_private_ip_is_blocked(monkeypatch) -> None:
    """Host looks public, but DNS returns a private IP. The SSRF check
    must resolve and then refuse - not trust the hostname."""
    _install_resolver(monkeypatch, {"evil.example.com": "10.0.0.5"})
    # Transport should never be called because SSRF aborts first.
    _install_transport(monkeypatch, lambda req: pytest.fail(
        "fetch should not happen for SSRF-blocked URL"
    ))
    with pytest.raises(url.UrlBlockedError):
        url.ingest_url("http://evil.example.com/char.txt")


def test_non_http_scheme_rejected(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    with pytest.raises(url.UrlSchemeError):
        url.ingest_url("ftp://example.com/char.txt")


def test_missing_host_rejected(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    with pytest.raises(url.UrlSchemeError):
        url.ingest_url("http:///no-host")


# ---------------------------------------------------------------------------
# Happy HTTP fetch of a plaintext character sheet
# ---------------------------------------------------------------------------

def test_fetch_public_plaintext_url(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"example.com": "93.184.216.34"})
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, content=body
        )
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/character.txt")
    assert result.fmt == "txt"
    assert "Kakita Tomoe" in result.text


# ---------------------------------------------------------------------------
# Size cap (streaming abort mid-download)
# ---------------------------------------------------------------------------

def test_oversize_response_is_aborted(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    big = b"x" * (ing.IMPORT_MAX_UPLOAD_BYTES + 1024)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"},
                              content=big)
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.UrlResponseTooLargeError) as info:
        url.ingest_url("https://bulky.example.com/log")
    assert "1 MB" in info.value.user_message


# ---------------------------------------------------------------------------
# 4xx / errors
# ---------------------------------------------------------------------------

def test_4xx_response_surfaced_as_fetch_failed(monkeypatch) -> None:
    _install_resolver(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"forbidden")
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.UrlFetchError) as info:
        url.ingest_url("https://example.com/character.txt")
    assert info.value.status == 403
    assert "403" in info.value.user_message


def test_transport_error_surfaced_as_fetch_failed(monkeypatch) -> None:
    _install_resolver(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.UrlFetchError) as info:
        url.ingest_url("https://example.com/character.txt")
    assert info.value.status is None
    assert "boom" in info.value.user_message


def test_dns_failure_surfaced_as_fetch_failed(monkeypatch) -> None:
    import socket

    def resolver(host: str):
        raise socket.gaierror("nope")

    monkeypatch.setattr(url, "_RESOLVER", resolver)
    with pytest.raises(url.UrlFetchError):
        url.ingest_url("https://example.com/foo")


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------

def test_redirect_chain_too_long(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    hops = {
        "/a": "/b",
        "/b": "/c",
        "/c": "/d",
        "/d": "/e",
    }

    def handler(req: httpx.Request) -> httpx.Response:
        dest = hops.get(req.url.path)
        if dest is None:
            return httpx.Response(200, content=b"ok")
        return httpx.Response(302, headers={"location": dest})
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.UrlRedirectChainTooLongError):
        url.ingest_url("https://short.example.com/a")


def test_redirect_within_cap_is_followed(monkeypatch) -> None:
    """Three redirects land on a plaintext body on the fourth request."""
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()
    hops = {"/1": "/2", "/2": "/3"}

    def handler(req: httpx.Request) -> httpx.Response:
        dest = hops.get(req.url.path)
        if dest is not None:
            return httpx.Response(302, headers={"location": dest})
        return httpx.Response(200,
                              headers={"content-type": "text/plain"},
                              content=body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/1")
    assert "Kakita Tomoe" in result.text


def test_redirect_with_empty_location_rejected(monkeypatch) -> None:
    _install_resolver(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": ""})
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.UrlFetchError):
        url.ingest_url("https://example.com/lost")


def test_redirect_to_non_http_scheme_rejected(monkeypatch) -> None:
    _install_resolver(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302,
                              headers={"location": "ftp://example.com/x"})
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.UrlSchemeError):
        url.ingest_url("https://example.com/lost")


def test_relative_redirect_resolves_against_base(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if req.url.path == "/docs/1":
            return httpx.Response(302, headers={"location": "final.txt"})
        return httpx.Response(200,
                              headers={"content-type": "text/plain"},
                              content=body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/docs/1")
    # Second request should resolve to /docs/final.txt.
    assert any("docs/final.txt" in s for s in seen)
    assert "Kakita Tomoe" in result.text


def test_absolute_path_redirect_preserves_host(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/1":
            return httpx.Response(302, headers={"location": "/final.txt"})
        return httpx.Response(200,
                              headers={"content-type": "text/plain"},
                              content=body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/1")
    assert "Kakita Tomoe" in result.text


# ---------------------------------------------------------------------------
# Google Docs / Sheets
# ---------------------------------------------------------------------------

DOC_URL = (
    "https://docs.google.com/document/d/1AbCdEfGh_ijklmnopqrSTUVWXYZ0123456/edit"
)
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1XyZaBcDeFgHiJkLmNoPqRsTuVwXyZ9876543210/edit#gid=0"
)


def test_public_google_doc_is_rewritten_to_export_and_fetched(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"docs.google.com": "142.250.0.1"})
    body = (HAPPY / "happy_plaintext.txt").read_bytes()
    seen_urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_urls.append(str(req.url))
        return httpx.Response(200,
                              headers={"content-type": "text/plain; charset=utf-8"},
                              content=body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url(DOC_URL)
    # Export URL rewrite must have happened.
    assert any("/export?format=txt" in s for s in seen_urls)
    assert "Kakita Tomoe" in result.text
    assert result.fmt == "txt"


def test_public_google_sheet_is_rewritten_to_csv_export(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"docs.google.com": "142.250.0.1"})
    csv_body = (URL_FIX / "happy_google_sheet_body.csv").read_bytes()
    seen_urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_urls.append(str(req.url))
        return httpx.Response(200,
                              headers={"content-type": "text/csv; charset=utf-8"},
                              content=csv_body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url(SHEET_URL)
    assert any("/export?format=csv" in s for s in seen_urls)
    assert "Kakita Tomoe" in result.text


def test_private_google_doc_detected_via_accounts_redirect(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"docs.google.com": "142.250.0.1"})

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={
            "location": "https://accounts.google.com/ServiceLogin?continue=..."
        })
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.GoogleDocNotPublicError) as info:
        url.ingest_url(DOC_URL)
    assert "Anyone with the link" in info.value.user_message


def test_private_google_doc_detected_via_html_login_page(monkeypatch) -> None:
    """Some private-doc exports return 200 with the HTML sign-in page
    inline rather than a redirect. Detect via content-type."""
    _install_resolver(monkeypatch, {"docs.google.com": "142.250.0.1"})

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200,
                              headers={"content-type": "text/html; charset=utf-8"},
                              content=b"<html><body>Sign in</body></html>")
    _install_transport(monkeypatch, handler)

    with pytest.raises(url.GoogleDocNotPublicError):
        url.ingest_url(DOC_URL)


# ---------------------------------------------------------------------------
# URL fixture descriptors round-trip correctly (belt-and-braces)
# ---------------------------------------------------------------------------

def test_all_ssrf_url_fixture_targets_are_still_blocked(monkeypatch) -> None:
    """Sanity check: every SSRF descriptor's URL truly resolves to a
    blocked address given our defenses. Guards against regressions where
    the SSRF block list drifts out of sync with the fixtures."""
    import json

    _install_resolver(monkeypatch, {
        "rebind.example.invalid": "10.0.0.5",
    })

    for name in ("url_ssrf_localhost", "url_ssrf_private", "url_dns_rebinding"):
        spec = json.loads((URL_FIX / f"{name}.fixture.json").read_text())
        with pytest.raises(url.UrlBlockedError):
            url.ingest_url(spec["url"])


# ---------------------------------------------------------------------------
# Filename / content-type guessing
# ---------------------------------------------------------------------------

def test_filename_guess_uses_url_path_when_present(monkeypatch) -> None:
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_html.html").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        # No content-type: forces the extension hint to do the work.
        return httpx.Response(200, content=body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/sheets/character.html")
    assert result.fmt == "html"


def test_filename_guess_falls_back_to_content_type(monkeypatch) -> None:
    """URL has no extension; content-type is what libmagic needs."""
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, content=body
        )
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/raw/latest")
    assert result.fmt == "txt"
    assert "Kakita Tomoe" in result.text


@pytest.mark.parametrize("content_type,expected_fmt", [
    ("text/html", "html"),
    ("text/markdown", "md"),
    ("application/pdf", "pdf"),
])
def test_filename_guess_from_content_type_covers_common_types(
    content_type: str, expected_fmt: str, monkeypatch
) -> None:
    """URLs without a meaningful path extension must still route to the
    right extractor via the content-type hint."""
    _install_resolver(monkeypatch)
    fixture_map = {
        "html": "happy_html.html",
        "md": "happy_markdown.md",
        "pdf": "happy_pdf_text.pdf",
    }
    body = (HAPPY / fixture_map[expected_fmt]).read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200,
                              headers={"content-type": content_type},
                              content=body)
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://example.com/download")
    assert result.fmt == expected_fmt


def test_filename_guess_returns_none_for_unknown_content_type(monkeypatch) -> None:
    """Extensionless URL + unknown content-type: the guesser returns None
    and detect_format falls back to libmagic-only detection."""
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200,
                              headers={"content-type": "application/x-weird"},
                              content=body)
    _install_transport(monkeypatch, handler)

    # libmagic still identifies plain text from the bytes.
    result = url.ingest_url("https://example.com/raw/latest")
    assert result.fmt == "txt"


def test_ip_literal_public_address_is_allowed(monkeypatch) -> None:
    """When the URL host is already a public IP literal, we skip DNS and
    still go through the block-list check."""
    _install_resolver(monkeypatch)
    body = (HAPPY / "happy_plaintext.txt").read_bytes()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, content=body
        )
    _install_transport(monkeypatch, handler)

    result = url.ingest_url("https://8.8.8.8/character.txt")
    assert "Kakita Tomoe" in result.text
