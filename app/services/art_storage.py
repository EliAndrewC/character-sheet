"""S3 storage primitives for character art.

Art lives under a dedicated prefix (default ``character_art/``) in the
same bucket used by the database backup (``S3_BACKUP_BUCKET``). Objects
are uploaded with ``ACL=public-read`` so they can be linked from the
character list and sheet pages without presigning each request -
character art is public per the feature spec (see Phase 5 of the
implementation plan).

Functions here are called from the art upload/generation routes. No
route logic lives in this module - it is pure S3 + key generation.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Disk-backed test stub
#
# Clicktests can't reach a real S3 bucket, so when
# ``ART_STORAGE_USE_TEST_STUB=1`` is set on the live uvicorn subprocess
# every S3 call is redirected to the local filesystem. The matching
# ``/test-art-stub/{key}`` route (registered by ``app.routes.art`` when
# the same env var is set) serves the bytes back so the browser can
# display them. In production the env var is never set and the stub
# is a no-op.
# ---------------------------------------------------------------------------


_STUB_DIR_ENV = "ART_STORAGE_STUB_DIR"
_DEFAULT_STUB_DIR = "/tmp/l7r_art_stub"


def use_disk_stub() -> bool:
    return os.environ.get("ART_STORAGE_USE_TEST_STUB", "").lower() in (
        "1", "true", "yes", "on",
    )


def _stub_dir() -> str:
    return os.environ.get(_STUB_DIR_ENV, _DEFAULT_STUB_DIR)


def _stub_path(key: str) -> str:
    # Flatten slashes so each S3 key becomes a single file on disk.
    safe = key.replace("/", "__")
    return os.path.join(_stub_dir(), safe)


def _stub_key_from_path(path: str) -> str:
    return os.path.basename(path).replace("__", "/")


def stub_key_encoded(key: str) -> str:
    """Return the single-segment filename the ``/test-art-stub`` route serves."""
    return key.replace("/", "__")


def stub_key_decoded(encoded: str) -> str:
    return encoded.replace("__", "/")


def stub_read_bytes(encoded: str) -> Optional[bytes]:
    """Read a stub file by its encoded filename. Returns None if missing."""
    path = os.path.join(_stub_dir(), encoded)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fp:
        return fp.read()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def art_prefix() -> str:
    """Return the configured S3 key prefix for character art (with trailing /)."""
    prefix = os.environ.get("S3_CHARACTER_ART_PREFIX", "character_art/")
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    return prefix


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def make_art_keys(char_id: int, now: Optional[datetime] = None) -> Tuple[str, str]:
    """Generate ``(full_key, headshot_key)`` for a character.

    Both keys share a timestamp so they sort together and so orphan
    cleanup can treat them as a pair if desired. The full-art key
    prefixes with ``full-`` and the headshot with ``head-`` so a human
    inspecting the bucket can tell them apart.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    prefix = art_prefix()
    full_key = f"{prefix}{char_id}/full-{ts}.webp"
    head_key = f"{prefix}{char_id}/head-{ts}.webp"
    return full_key, head_key


# ---------------------------------------------------------------------------
# S3 client (lazy boto3 import)
# ---------------------------------------------------------------------------


def _get_s3_client(region: str):
    """Create a boto3 S3 client. Lazy-imports boto3.

    Mirrors ``backup._get_s3_client`` so tests use the same patch target.
    """
    import boto3
    return boto3.client("s3", region_name=region)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def upload_art(
    char_id: int,
    full_bytes: bytes,
    headshot_bytes: bytes,
    bucket: str,
    region: str,
    now: Optional[datetime] = None,
) -> Tuple[str, str]:
    """Upload both images to S3 as public-read objects.

    Returns ``(full_key, head_key)`` for the caller to persist on the
    Character row. Raises whatever the underlying S3 client raises -
    the route layer catches and converts to a banner.
    """
    full_key, head_key = make_art_keys(char_id, now)
    if use_disk_stub():
        os.makedirs(_stub_dir(), exist_ok=True)
        with open(_stub_path(full_key), "wb") as fp:
            fp.write(full_bytes)
        with open(_stub_path(head_key), "wb") as fp:
            fp.write(headshot_bytes)
        log.info("Art stubbed to disk: %s + %s", full_key, head_key)
        return full_key, head_key
    client = _get_s3_client(region)
    client.put_object(
        Bucket=bucket,
        Key=full_key,
        Body=full_bytes,
        ContentType="image/webp",
        ACL="public-read",
        CacheControl="public, max-age=604800",
    )
    client.put_object(
        Bucket=bucket,
        Key=head_key,
        Body=headshot_bytes,
        ContentType="image/webp",
        ACL="public-read",
        CacheControl="public, max-age=604800",
    )
    log.info("Art uploaded: s3://%s/%s + %s", bucket, full_key, head_key)
    return full_key, head_key


def delete_art(bucket: str, region: str, *keys: Optional[str]) -> None:
    """Delete one or more S3 objects by key.

    ``None`` keys are ignored so callers can pass
    ``character.art_s3_key`` and ``character.headshot_s3_key`` without
    null-checking first.
    """
    real_keys = [k for k in keys if k]
    if not real_keys:
        return
    if use_disk_stub():
        for key in real_keys:
            path = _stub_path(key)
            if os.path.isfile(path):
                os.unlink(path)
                log.info("Art stub deleted: %s", key)
        return
    client = _get_s3_client(region)
    for key in real_keys:
        client.delete_object(Bucket=bucket, Key=key)
        log.info("Art deleted: s3://%s/%s", bucket, key)


def public_url(key: str, bucket: str, region: str) -> str:
    """Return the public HTTPS URL for an S3 object.

    Objects are uploaded with ``ACL=public-read`` so signing is not
    required. ``us-east-1`` uses the virtual-hosted path without a
    region component; every other region includes the region.

    In stub mode the URL is a local ``/test-art-stub/{encoded_key}``
    path so the browser loads bytes straight off the clicktest server.
    """
    if use_disk_stub():
        return f"/test-art-stub/{stub_key_encoded(key)}"
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{key}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def list_art_keys(bucket: str, region: str) -> list[str]:
    """List every S3 key under the art prefix."""
    if use_disk_stub():
        d = _stub_dir()
        if not os.path.isdir(d):
            return []
        return [_stub_key_from_path(os.path.join(d, f)) for f in os.listdir(d)]
    client = _get_s3_client(region)
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=art_prefix()):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def list_orphaned_keys(
    known_keys: set[str], bucket: str, region: str
) -> list[str]:
    """Return S3 keys under the art prefix that aren't in ``known_keys``.

    ``known_keys`` is the set of every ``Character.art_s3_key`` +
    ``Character.headshot_s3_key`` currently in the database. Anything
    under the art prefix that isn't in that set is an orphan (the
    character was deleted, or the art was replaced) and should be
    deleted by the caller.
    """
    all_keys = list_art_keys(bucket, region)
    return [k for k in all_keys if k not in known_keys]
