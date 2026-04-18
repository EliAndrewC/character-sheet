"""Fetch a URL safely and hand the bytes to ``import_ingest``.

Security layers (design doc §5.2 and §8):

  * SSRF-block private / loopback / link-local IP ranges (IPv4 + IPv6).
    DNS resolution happens server-side; we compare the *resolved* IP to
    the block list and then fetch from that IP - defeating DNS rebinding.
  * Cap response size at ``IMPORT_MAX_UPLOAD_BYTES`` and stream-abort on
    overflow instead of buffering forever.
  * Cap redirect chain length at ``IMPORT_MAX_REDIRECTS`` (default 3).
  * Timeout each fetch at ``IMPORT_URL_FETCH_TIMEOUT_SEC`` (default 20s).
  * Only follow http/https redirects.

Google Docs and Google Sheets URLs are recognised by pattern and
rerouted to the public ``/export`` endpoint (no OAuth - design §8.1).
Private documents redirect to ``accounts.google.com``; we detect that
and raise ``GoogleDocNotPublicError`` with the dedicated instruction
message.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx

from app.services.import_ingest import (
    IMPORT_MAX_UPLOAD_BYTES,
    IMPORT_MAX_UPLOAD_MB,
    ImportIngestError,
    IngestResult,
    ingest_bytes,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:  # pragma: no cover - deploy bug
        return default


IMPORT_URL_FETCH_TIMEOUT_SEC = _env_int("IMPORT_URL_FETCH_TIMEOUT_SEC", 20)
IMPORT_MAX_REDIRECTS = _env_int("IMPORT_MAX_REDIRECTS", 3)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImportUrlError(ImportIngestError):
    """Base for URL-layer rejections."""
    error_code = "url_error"
    user_message = "We could not fetch that URL."


class UrlSchemeError(ImportUrlError):
    error_code = "url_bad_scheme"
    user_message = "Only HTTP and HTTPS URLs are supported."


class UrlBlockedError(ImportUrlError):
    error_code = "url_blocked_ssrf"
    user_message = (
        "That URL is not allowed. The importer cannot fetch private, "
        "loopback, or link-local network addresses."
    )


class UrlFetchError(ImportUrlError):
    error_code = "url_fetch_failed"

    def __init__(self, status: Optional[int], detail: str = ""):
        self.status = status
        if status is not None:
            self.user_message = (
                f"The URL returned HTTP {status}; we could not fetch "
                "its content."
            )
        else:
            self.user_message = f"Could not fetch that URL: {detail}"
        super().__init__(self.user_message)


class UrlResponseTooLargeError(ImportUrlError):
    error_code = "url_response_too_large"

    def __init__(self) -> None:
        self.user_message = (
            f"The content at that URL is too large to import (over "
            f"{IMPORT_MAX_UPLOAD_MB} MB)."
        )
        super().__init__(self.user_message)


class UrlRedirectChainTooLongError(ImportUrlError):
    error_code = "url_redirect_chain_too_long"
    user_message = (
        f"That URL follows too many redirects (more than "
        f"{IMPORT_MAX_REDIRECTS}). Try pasting the final destination "
        "URL directly."
    )


class GoogleDocNotPublicError(ImportUrlError):
    error_code = "document_not_public"
    user_message = (
        "This document is not publicly accessible. To import it, open "
        "the document in Google, click Share, change \"General access\" "
        "to \"Anyone with the link\" (Viewer), then paste the URL here "
        "again."
    )


# ---------------------------------------------------------------------------
# SSRF defense
# ---------------------------------------------------------------------------

def _is_blocked_ip(ip_str: str) -> bool:
    """True when ``ip_str`` is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:  # pragma: no cover - callers pass resolved IPs only
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


# Overridable for tests.
_RESOLVER: Callable[[str], List[str]] = lambda host: [
    info[4][0] for info in socket.getaddrinfo(host, None)
]


def _resolve_host(host: str) -> List[str]:
    """Return every IP the hostname resolves to.

    A test fixture may monkey-patch ``_RESOLVER`` to simulate DNS rebinding
    without touching the real network.
    """
    try:
        return _RESOLVER(host)
    except socket.gaierror as exc:
        raise UrlFetchError(None, f"DNS lookup failed: {exc}") from exc


def _check_ssrf(url: str) -> str:
    """Resolve ``url``'s host, assert no resolved IP is blocked.

    Returns the host (unchanged) so the caller can use it in a Host header.
    Raises ``UrlBlockedError`` if any resolution is private/loopback/etc.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlSchemeError(parsed.scheme)

    host = parsed.hostname or ""
    if not host:
        raise UrlSchemeError("missing host")

    # If the host itself is already a literal IP, check it directly.
    try:
        ipaddress.ip_address(host)
        if _is_blocked_ip(host):
            raise UrlBlockedError()
        return host
    except ValueError:
        pass  # not an IP literal; resolve below

    for ip in _resolve_host(host):
        if _is_blocked_ip(ip):
            raise UrlBlockedError()
    return host


# ---------------------------------------------------------------------------
# Google Docs / Sheets routing
# ---------------------------------------------------------------------------

_GOOGLE_DOC_RE = re.compile(
    r"^https://docs\.google\.com/document/d/([A-Za-z0-9_-]+)"
)
_GOOGLE_SHEET_RE = re.compile(
    r"^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)"
)


def _google_export_url(url: str) -> Optional[Tuple[str, str, str]]:
    """If ``url`` is a Google Docs/Sheets URL, return
    ``(export_url, kind, doc_id)``; else ``None``.

    ``kind`` is "document" or "spreadsheet"; callers may use it to pick
    the expected content type for the public-access check.
    """
    m = _GOOGLE_DOC_RE.match(url)
    if m:
        doc_id = m.group(1)
        return (
            f"https://docs.google.com/document/d/{doc_id}/export?format=txt",
            "document",
            doc_id,
        )
    m = _GOOGLE_SHEET_RE.match(url)
    if m:
        doc_id = m.group(1)
        return (
            f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv",
            "spreadsheet",
            doc_id,
        )
    return None


def _is_google_login_redirect(response: httpx.Response) -> bool:
    """Public Google exports return 200 with text/plain or text/csv. Private
    docs redirect to accounts.google.com or serve an HTML login page.
    """
    if response.status_code in (301, 302, 303, 307, 308):
        loc = response.headers.get("location", "")
        return "accounts.google.com" in loc
    # If the server returned 200 with HTML (not text/plain/csv), it's
    # almost certainly the "Sign in to continue" page served in lieu of
    # the export.
    ctype = response.headers.get("content-type", "").lower()
    if response.status_code == 200 and ctype.startswith("text/html"):
        return True
    return False


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


@dataclass
class FetchedBytes:
    data: bytes
    final_url: str
    content_type: str


def _fetch_bytes(url: str, *, allow_google_auth_check: bool = False) -> FetchedBytes:
    """Fetch ``url`` with every defense applied.

    When ``allow_google_auth_check`` is True (used for Google Docs / Sheets
    exports), a redirect to ``accounts.google.com`` raises
    ``GoogleDocNotPublicError`` instead of being followed.
    """
    redirects = 0
    current = url
    while True:
        _check_ssrf(current)  # re-check on every hop

        try:
            with httpx.Client(
                follow_redirects=False,
                timeout=IMPORT_URL_FETCH_TIMEOUT_SEC,
            ) as client:
                with client.stream("GET", current) as response:
                    if _is_redirect(response):
                        if allow_google_auth_check and _is_google_login_redirect(response):
                            raise GoogleDocNotPublicError()
                        redirects += 1
                        if redirects > IMPORT_MAX_REDIRECTS:
                            raise UrlRedirectChainTooLongError()
                        loc = response.headers.get("location", "")
                        if not loc:
                            raise UrlFetchError(response.status_code, "redirect with no Location")
                        current = _absolute_url(current, loc)
                        parsed_next = urlparse(current)
                        if parsed_next.scheme not in ("http", "https"):
                            raise UrlSchemeError(parsed_next.scheme)
                        continue

                    if (
                        allow_google_auth_check
                        and _is_google_login_redirect(response)
                    ):
                        raise GoogleDocNotPublicError()

                    if response.status_code >= 400:
                        raise UrlFetchError(response.status_code)

                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > IMPORT_MAX_UPLOAD_BYTES:
                            raise UrlResponseTooLargeError()

                    return FetchedBytes(
                        data=bytes(data),
                        final_url=current,
                        content_type=response.headers.get("content-type", ""),
                    )
        except httpx.HTTPError as exc:
            raise UrlFetchError(None, str(exc)) from exc


def _is_redirect(response: httpx.Response) -> bool:
    return response.status_code in (301, 302, 303, 307, 308)


def _absolute_url(base: str, loc: str) -> str:
    """Resolve a Location header against the current request URL."""
    parsed = urlparse(loc)
    if parsed.scheme and parsed.netloc:
        return loc
    # Relative redirect; merge with base.
    base_parsed = urlparse(base)
    return urlunparse((
        base_parsed.scheme,
        base_parsed.netloc,
        loc if loc.startswith("/") else base_parsed.path.rsplit("/", 1)[0] + "/" + loc,
        "",
        "",
        "",
    ))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ingest_url(url: str) -> IngestResult:
    """Fetch ``url`` and return an ``IngestResult``.

    Google Docs / Sheets URLs are rewritten to their public export
    endpoints. All other HTTP(S) URLs are fetched directly with SSRF
    defenses.
    """
    google = _google_export_url(url)
    if google is not None:
        export_url, kind, _doc_id = google
        fetched = _fetch_bytes(export_url, allow_google_auth_check=True)
        # Google's public CSV export for spreadsheets returns text/csv;
        # the plaintext export for docs returns text/plain. Either way we
        # hand the bytes to the ingest layer with the right filename hint.
        ext = "csv" if kind == "spreadsheet" else "txt"
        return ingest_bytes(
            fetched.data,
            filename=f"google_{kind}.{ext}",
            enforce_size_limit=False,  # already enforced mid-stream
        )

    fetched = _fetch_bytes(url)
    # Give the ingester a filename hint so libmagic's "text/plain" detection
    # for ``.md`` / ``.csv`` / etc. has a tiebreaker available.
    guessed = _guess_filename_from_url(url, fetched.content_type)
    return ingest_bytes(
        fetched.data,
        filename=guessed,
        enforce_size_limit=False,
    )


def _guess_filename_from_url(url: str, content_type: str) -> Optional[str]:
    parsed = urlparse(url)
    last = parsed.path.rsplit("/", 1)[-1]
    if "." in last:
        return last
    # Content-Type fallback so libmagic has a hint for unusual cases.
    ct = content_type.lower().split(";", 1)[0].strip()
    if ct == "text/html":
        return "page.html"
    if ct == "text/plain":
        return "page.txt"
    if ct == "text/markdown":
        return "page.md"
    if ct == "application/pdf":
        return "page.pdf"
    return None


__all__ = [
    "ingest_url",
    "ImportUrlError",
    "UrlSchemeError",
    "UrlBlockedError",
    "UrlFetchError",
    "UrlResponseTooLargeError",
    "UrlRedirectChainTooLongError",
    "GoogleDocNotPublicError",
    "IMPORT_URL_FETCH_TIMEOUT_SEC",
    "IMPORT_MAX_REDIRECTS",
]
