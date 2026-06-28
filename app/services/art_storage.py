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
import shutil
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
    # No ACL: AWS disabled bucket ACLs by default after April 2023, and
    # our backup bucket uses the modern "ObjectWriter"/bucket-owner-only
    # ownership model. Public access is granted via presigned URLs in
    # ``public_url`` below instead.
    client.put_object(
        Bucket=bucket,
        Key=full_key,
        Body=full_bytes,
        ContentType="image/webp",
        CacheControl="public, max-age=604800",
    )
    client.put_object(
        Bucket=bucket,
        Key=head_key,
        Body=headshot_bytes,
        ContentType="image/webp",
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


PRESIGN_TTL_SECONDS = 7 * 24 * 3600  # 7 days - max for anonymous access


def public_url(key: str, bucket: str, region: str) -> str:
    """Return a presigned HTTPS URL for an S3 object.

    AWS disabled bucket ACLs by default after 2023, so we can't rely
    on ``ACL=public-read`` for anonymous access. Presigned URLs give
    us the same effect (browser loads the image without credentials)
    with no bucket-policy configuration required. TTL is 7 days (the
    maximum for anonymous presigned URLs); the caller cache-busts via
    ``?v={art_updated_at_epoch}`` so a replaced image still invalidates
    any upstream cache.

    In stub mode the URL is a local ``/test-art-stub/{encoded_key}``
    path so the browser loads bytes straight off the clicktest server.
    """
    if use_disk_stub():
        return f"/test-art-stub/{stub_key_encoded(key)}"
    client = _get_s3_client(region)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )


def _list_keys_under(prefix: str, bucket: str, region: str) -> list[str]:
    """List S3 keys whose name starts with ``prefix`` (stub-aware).

    In stub mode every art object (live *and* archived) shares one flat
    directory, so we must filter by the decoded key's prefix - otherwise
    archived keys would leak into ``list_art_keys`` and the orphan sweep
    would treat them as deletable. Real S3 filters server-side via the
    ``Prefix`` argument, so the two paths stay equivalent."""
    if use_disk_stub():
        d = _stub_dir()
        if not os.path.isdir(d):
            return []
        out: list[str] = []
        for f in os.listdir(d):
            key = _stub_key_from_path(os.path.join(d, f))
            if key.startswith(prefix):
                out.append(key)
        return out
    client = _get_s3_client(region)
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def list_art_keys(bucket: str, region: str) -> list[str]:
    """List every S3 key under the *live* art prefix (excludes archive)."""
    return _list_keys_under(art_prefix(), bucket, region)


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


# ---------------------------------------------------------------------------
# Previous-version archive
#
# When art is replaced or deleted we don't destroy the old object; we
# move it under a separate archive prefix so an editor (or the GM) can
# restore an earlier version. The archive prefix is deliberately
# disjoint from ``art_prefix()`` (note the trailing slash) so the
# live-art orphan sweep never touches it. Retention is bounded per
# character by ``prune_archive``.
# ---------------------------------------------------------------------------


def archive_prefix() -> str:
    """Return the S3 key prefix for retained previous art (trailing /)."""
    prefix = os.environ.get(
        "S3_CHARACTER_ART_ARCHIVE_PREFIX", "character_art_archive/",
    )
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    return prefix


def archive_keep_default() -> int:
    """How many previous versions to keep per character (default 10)."""
    raw = os.environ.get("ART_ARCHIVE_KEEP", "10")
    try:
        return max(0, int(raw))
    except ValueError:
        return 10


def archive_key_for(live_key: str) -> str:
    """Map a live art key to its archive location.

    Preserves the ``{char_id}/{full|head}-{ts}.webp`` tail so the
    timestamp (which records when the art was current) and the
    full/head distinction survive the move.
    """
    live = art_prefix()
    tail = live_key[len(live):] if live_key.startswith(live) else live_key
    return archive_prefix() + tail


def archive_art(bucket: str, region: str, *keys: Optional[str]) -> list[str]:
    """Move live art objects into the archive prefix (copy then delete).

    ``None`` keys are ignored so callers can pass
    ``character.art_s3_key`` / ``headshot_s3_key`` directly. Returns the
    list of archive keys created.
    """
    real = [k for k in keys if k]
    created: list[str] = []
    if not real:
        return created
    if use_disk_stub():
        os.makedirs(_stub_dir(), exist_ok=True)
        for key in real:
            akey = archive_key_for(key)
            src = _stub_path(key)
            if os.path.isfile(src):
                shutil.move(src, _stub_path(akey))
            created.append(akey)
        return created
    client = _get_s3_client(region)
    for key in real:
        akey = archive_key_for(key)
        client.copy_object(
            Bucket=bucket, Key=akey,
            CopySource={"Bucket": bucket, "Key": key},
        )
        client.delete_object(Bucket=bucket, Key=key)
        created.append(akey)
    return created


def copy_object_key(
    src_key: str, dst_key: str, *, bucket: str, region: str,
) -> None:
    """Copy one object to a new key, leaving the source in place.

    Used by restore to copy an archived version back to a fresh live key
    without consuming the archived copy.
    """
    if use_disk_stub():
        os.makedirs(_stub_dir(), exist_ok=True)
        shutil.copyfile(_stub_path(src_key), _stub_path(dst_key))
        return
    client = _get_s3_client(region)
    client.copy_object(
        Bucket=bucket, Key=dst_key,
        CopySource={"Bucket": bucket, "Key": src_key},
    )


def list_archived_keys(char_id: int, *, bucket: str, region: str) -> list[str]:
    """List every archived art key for a single character."""
    return _list_keys_under(f"{archive_prefix()}{char_id}/", bucket, region)


def list_all_archived_keys(bucket: str, region: str) -> list[str]:
    """List every archived art key across all characters."""
    return _list_keys_under(archive_prefix(), bucket, region)


def _parse_archive_basename(key: str) -> Optional[Tuple[str, str]]:
    """Return ``(kind, ts)`` from an archive key, or ``None`` if the
    basename doesn't match the ``{full|head}-{ts}.webp`` pattern."""
    base = key.rsplit("/", 1)[-1]
    if not base.endswith(".webp"):
        return None
    stem = base[: -len(".webp")]
    for kind in ("full", "head"):
        marker = kind + "-"
        if stem.startswith(marker):
            return kind, stem[len(marker):]
    return None


def archived_versions(char_id: int, *, bucket: str, region: str) -> list[dict]:
    """Return a character's retained versions, newest first.

    Each item is ``{"ts": token, "full_key": str, "head_key": str|None}``.
    Full and head objects share a timestamp token and are grouped into
    one version; a token with no full object is skipped (nothing to
    restore). The ISO-style token sorts lexically by time.
    """
    by_ts: dict[str, dict] = {}
    for key in list_archived_keys(char_id, bucket=bucket, region=region):
        parsed = _parse_archive_basename(key)
        if parsed is None:
            continue
        kind, ts = parsed
        slot = by_ts.setdefault(
            ts, {"ts": ts, "full_key": None, "head_key": None},
        )
        slot[f"{kind}_key"] = key
    versions = [v for v in by_ts.values() if v["full_key"]]
    versions.sort(key=lambda v: v["ts"], reverse=True)
    return versions


def prune_archive(
    char_id: int, *, bucket: str, region: str, keep: Optional[int] = None,
) -> int:
    """Delete archived versions beyond the newest ``keep``. Returns count."""
    if keep is None:
        keep = archive_keep_default()
    stale = archived_versions(char_id, bucket=bucket, region=region)[keep:]
    to_delete: list[str] = []
    for v in stale:
        to_delete.append(v["full_key"])
        if v["head_key"]:
            to_delete.append(v["head_key"])
    if to_delete:
        delete_art(bucket, region, *to_delete)
    return len(to_delete)


def delete_archive_for_char(char_id: int, *, bucket: str, region: str) -> int:
    """Hard-delete every archived art object for a character. Returns count."""
    keys = list_archived_keys(char_id, bucket=bucket, region=region)
    if keys:
        delete_art(bucket, region, *keys)
    return len(keys)
