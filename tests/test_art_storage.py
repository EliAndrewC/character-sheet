"""Tests for ``app.services.art_storage``.

Follows the same boto3-mocking pattern as ``tests/test_backup.py``:
patch the module-private ``_get_s3_client`` and assert on the returned
``MagicMock``. Tests never touch a real S3 endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services import art_storage


# ---------------------------------------------------------------------------
# Prefix configuration
# ---------------------------------------------------------------------------


class TestArtPrefix:
    def test_default_prefix(self, monkeypatch):
        monkeypatch.delenv("S3_CHARACTER_ART_PREFIX", raising=False)
        assert art_storage.art_prefix() == "character_art/"

    def test_custom_prefix_respected(self, monkeypatch):
        monkeypatch.setenv("S3_CHARACTER_ART_PREFIX", "custom/")
        assert art_storage.art_prefix() == "custom/"

    def test_trailing_slash_added_if_missing(self, monkeypatch):
        monkeypatch.setenv("S3_CHARACTER_ART_PREFIX", "no_slash")
        assert art_storage.art_prefix() == "no_slash/"


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


class TestMakeArtKeys:
    def test_keys_share_timestamp(self):
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
        full, head = art_storage.make_art_keys(42, now=now)
        # The timestamps inside both keys must match.
        assert "2026-04-19T12-00-00Z" in full
        assert "2026-04-19T12-00-00Z" in head

    def test_keys_use_char_id_subfolder(self):
        full, head = art_storage.make_art_keys(7)
        assert "/7/" in full
        assert "/7/" in head

    def test_full_and_head_keys_are_distinguishable(self):
        full, head = art_storage.make_art_keys(1)
        assert "full-" in full
        assert "head-" in head
        assert full != head

    def test_keys_respect_prefix_env(self, monkeypatch):
        monkeypatch.setenv("S3_CHARACTER_ART_PREFIX", "art/")
        full, head = art_storage.make_art_keys(1)
        assert full.startswith("art/1/")
        assert head.startswith("art/1/")

    def test_keys_default_to_utcnow_when_no_datetime(self):
        """When ``now`` is omitted the function uses ``datetime.now(UTC)``."""
        full, _ = art_storage.make_art_keys(1)
        # Hard to assert the exact timestamp, but the format must match.
        assert full.endswith(".webp")
        # Format: prefix/{id}/full-YYYY-MM-DDTHH-MM-SSZ.webp
        tail = full.split("full-")[1]
        assert tail.endswith(".webp")
        # 20 chars: YYYY-MM-DDTHH-MM-SSZ
        assert len(tail.replace(".webp", "")) == 20


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUploadArt:
    @patch("app.services.art_storage._get_s3_client")
    def test_put_object_called_twice_with_public_read(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

        full_key, head_key = art_storage.upload_art(
            42, b"FULL_BYTES", b"HEAD_BYTES",
            bucket="bucket", region="us-east-1", now=now,
        )

        assert client.put_object.call_count == 2
        calls = client.put_object.call_args_list
        # First call: full art
        full_kwargs = calls[0].kwargs
        assert full_kwargs["Bucket"] == "bucket"
        assert full_kwargs["Key"] == full_key
        assert full_kwargs["Body"] == b"FULL_BYTES"
        assert full_kwargs["ContentType"] == "image/webp"
        # No ACL - AWS disabled bucket ACLs by default after 2023 and
        # we use presigned URLs for public access instead (see
        # ``public_url``). Explicitly assert the ACL key is NOT passed.
        assert "ACL" not in full_kwargs
        # Second call: headshot
        head_kwargs = calls[1].kwargs
        assert head_kwargs["Key"] == head_key
        assert head_kwargs["Body"] == b"HEAD_BYTES"
        assert "ACL" not in head_kwargs

    @patch("app.services.art_storage._get_s3_client")
    def test_returns_keys_that_match_make_art_keys(self, mock_get_client):
        mock_get_client.return_value = MagicMock()
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
        expected_full, expected_head = art_storage.make_art_keys(13, now=now)
        full_key, head_key = art_storage.upload_art(
            13, b"F", b"H", bucket="b", region="us-east-1", now=now,
        )
        assert (full_key, head_key) == (expected_full, expected_head)

    @patch("app.services.art_storage._get_s3_client")
    def test_raises_if_s3_put_fails(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        client.put_object.side_effect = Exception("s3 boom")
        with pytest.raises(Exception, match="s3 boom"):
            art_storage.upload_art(
                42, b"F", b"H", bucket="b", region="us-east-1",
            )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDeleteArt:
    @patch("app.services.art_storage._get_s3_client")
    def test_deletes_each_key(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        art_storage.delete_art("bucket", "us-east-1", "key_a", "key_b")
        assert client.delete_object.call_count == 2
        assert client.delete_object.call_args_list[0].kwargs == {
            "Bucket": "bucket", "Key": "key_a",
        }
        assert client.delete_object.call_args_list[1].kwargs == {
            "Bucket": "bucket", "Key": "key_b",
        }

    @patch("app.services.art_storage._get_s3_client")
    def test_ignores_none_keys(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        art_storage.delete_art("bucket", "us-east-1", None, "real_key", None)
        assert client.delete_object.call_count == 1
        assert client.delete_object.call_args_list[0].kwargs["Key"] == "real_key"

    @patch("app.services.art_storage._get_s3_client")
    def test_no_client_call_when_all_keys_none(self, mock_get_client):
        """Fast-path: don't even create the S3 client if nothing to delete."""
        art_storage.delete_art("bucket", "us-east-1", None, None)
        mock_get_client.assert_not_called()

    @patch("app.services.art_storage._get_s3_client")
    def test_no_args_is_a_no_op(self, mock_get_client):
        art_storage.delete_art("bucket", "us-east-1")
        mock_get_client.assert_not_called()


# ---------------------------------------------------------------------------
# Public URL
# ---------------------------------------------------------------------------


class TestPublicUrl:
    @patch("app.services.art_storage._get_s3_client")
    def test_delegates_to_boto3_presigned_url(self, mock_get_client):
        client = MagicMock()
        client.generate_presigned_url.return_value = (
            "https://my-bucket.s3.amazonaws.com/character_art/1/full-x.webp"
            "?X-Amz-Signature=abc"
        )
        mock_get_client.return_value = client
        url = art_storage.public_url(
            "character_art/1/full-x.webp",
            bucket="my-bucket", region="us-east-1",
        )
        assert "X-Amz-Signature" in url
        client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "character_art/1/full-x.webp"},
            ExpiresIn=art_storage.PRESIGN_TTL_SECONDS,
        )

    @patch("app.services.art_storage._get_s3_client")
    def test_presign_ttl_is_7_days(self, mock_get_client):
        mock_get_client.return_value = MagicMock()
        art_storage.public_url("k", bucket="b", region="us-east-1")
        assert art_storage.PRESIGN_TTL_SECONDS == 7 * 24 * 3600


# ---------------------------------------------------------------------------
# List + orphan detection
# ---------------------------------------------------------------------------


class TestListArtKeys:
    @patch("app.services.art_storage._get_s3_client")
    def test_lists_keys_across_pages(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [
                {"Key": "character_art/1/full-x.webp"},
                {"Key": "character_art/1/head-x.webp"},
            ]},
            {"Contents": [
                {"Key": "character_art/2/full-y.webp"},
            ]},
        ]
        keys = art_storage.list_art_keys("bucket", "us-east-1")
        assert keys == [
            "character_art/1/full-x.webp",
            "character_art/1/head-x.webp",
            "character_art/2/full-y.webp",
        ]

    @patch("app.services.art_storage._get_s3_client")
    def test_empty_page(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{}]
        keys = art_storage.list_art_keys("bucket", "us-east-1")
        assert keys == []


class TestListOrphanedKeys:
    @patch("app.services.art_storage.list_art_keys")
    def test_returns_keys_not_in_known_set(self, mock_list):
        mock_list.return_value = [
            "character_art/1/full-x.webp",
            "character_art/1/head-x.webp",
            "character_art/2/full-stale.webp",   # orphan
            "character_art/3/head-stale.webp",   # orphan
        ]
        known = {
            "character_art/1/full-x.webp",
            "character_art/1/head-x.webp",
        }
        orphans = art_storage.list_orphaned_keys(known, "bucket", "us-east-1")
        assert set(orphans) == {
            "character_art/2/full-stale.webp",
            "character_art/3/head-stale.webp",
        }

    @patch("app.services.art_storage.list_art_keys")
    def test_no_orphans_when_all_known(self, mock_list):
        mock_list.return_value = ["character_art/1/full-x.webp"]
        known = {"character_art/1/full-x.webp"}
        orphans = art_storage.list_orphaned_keys(known, "bucket", "us-east-1")
        assert orphans == []

    @patch("app.services.art_storage.list_art_keys")
    def test_all_orphans_when_known_empty(self, mock_list):
        mock_list.return_value = ["character_art/1/full-x.webp"]
        orphans = art_storage.list_orphaned_keys(set(), "bucket", "us-east-1")
        assert orphans == ["character_art/1/full-x.webp"]


# ---------------------------------------------------------------------------
# Lazy boto3 import
# ---------------------------------------------------------------------------


class TestGetS3Client:
    def test_returns_s3_client(self):
        pytest.importorskip("boto3")
        client = art_storage._get_s3_client("us-east-1")
        assert client is not None
        assert client.meta.region_name == "us-east-1"
        assert client.meta.service_model.service_name == "s3"


# ---------------------------------------------------------------------------
# Disk-backed stub (used only by the clicktest subprocess)
# ---------------------------------------------------------------------------


class TestDiskStub:
    @pytest.fixture(autouse=True)
    def _enable_stub(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ART_STORAGE_USE_TEST_STUB", "1")
        monkeypatch.setenv("ART_STORAGE_STUB_DIR", str(tmp_path))
        yield

    def test_use_disk_stub_env_var(self, monkeypatch):
        monkeypatch.delenv("ART_STORAGE_USE_TEST_STUB", raising=False)
        assert art_storage.use_disk_stub() is False
        monkeypatch.setenv("ART_STORAGE_USE_TEST_STUB", "true")
        assert art_storage.use_disk_stub() is True
        monkeypatch.setenv("ART_STORAGE_USE_TEST_STUB", "off")
        assert art_storage.use_disk_stub() is False

    def test_upload_writes_to_disk_instead_of_s3(self, tmp_path, monkeypatch):
        # _get_s3_client must NOT be touched in stub mode
        with patch("app.services.art_storage._get_s3_client") as client_factory:
            full_key, head_key = art_storage.upload_art(
                42, b"FULL", b"HEAD", bucket="b", region="us-east-1",
                now=datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc),
            )
            client_factory.assert_not_called()
        # Both bytes appear at the expected flattened paths
        flat_full = tmp_path / full_key.replace("/", "__")
        flat_head = tmp_path / head_key.replace("/", "__")
        assert flat_full.read_bytes() == b"FULL"
        assert flat_head.read_bytes() == b"HEAD"

    def test_delete_removes_files(self, tmp_path):
        full = tmp_path / "character_art__1__full-x.webp"
        head = tmp_path / "character_art__1__head-x.webp"
        full.write_bytes(b"A")
        head.write_bytes(b"B")
        with patch("app.services.art_storage._get_s3_client") as client_factory:
            art_storage.delete_art(
                "b", "us-east-1",
                "character_art/1/full-x.webp",
                "character_art/1/head-x.webp",
            )
            client_factory.assert_not_called()
        assert not full.exists()
        assert not head.exists()

    def test_delete_silently_ignores_missing_files(self, tmp_path):
        with patch("app.services.art_storage._get_s3_client") as client_factory:
            # Must not raise even though the file never existed
            art_storage.delete_art(
                "b", "us-east-1", "character_art/1/never-there.webp",
            )
            client_factory.assert_not_called()

    def test_public_url_in_stub_mode_is_local_path(self):
        url = art_storage.public_url(
            "character_art/1/full-x.webp", bucket="b", region="us-east-1",
        )
        assert url == "/test-art-stub/character_art__1__full-x.webp"

    def test_list_art_keys_reads_directory(self, tmp_path):
        (tmp_path / "character_art__1__full-a.webp").write_bytes(b"x")
        (tmp_path / "character_art__2__head-b.webp").write_bytes(b"y")
        with patch("app.services.art_storage._get_s3_client") as client_factory:
            keys = art_storage.list_art_keys("b", "us-east-1")
            client_factory.assert_not_called()
        assert set(keys) == {
            "character_art/1/full-a.webp",
            "character_art/2/head-b.webp",
        }

    def test_list_art_keys_empty_when_no_stub_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ART_STORAGE_STUB_DIR", str(tmp_path / "missing"))
        assert art_storage.list_art_keys("b", "us-east-1") == []

    def test_stub_read_bytes_returns_none_for_unknown(self, tmp_path):
        assert art_storage.stub_read_bytes("never-there__file.webp") is None

    def test_stub_read_bytes_returns_bytes_for_known(self, tmp_path):
        (tmp_path / "character_art__1__full-x.webp").write_bytes(b"payload")
        data = art_storage.stub_read_bytes("character_art__1__full-x.webp")
        assert data == b"payload"

    def test_stub_key_encode_decode_roundtrip(self):
        original = "character_art/9/full-2026-04-19T00-00-00Z.webp"
        encoded = art_storage.stub_key_encoded(original)
        assert "/" not in encoded
        assert art_storage.stub_key_decoded(encoded) == original


class TestTestArtStubRoute:
    """The ``/test-art-stub/{key}`` route serves bytes from the disk stub."""

    def test_route_returns_bytes_when_stub_on(
        self, client, monkeypatch, tmp_path,
    ):
        monkeypatch.setenv("ART_STORAGE_USE_TEST_STUB", "1")
        monkeypatch.setenv("ART_STORAGE_STUB_DIR", str(tmp_path))
        (tmp_path / "character_art__1__full-x.webp").write_bytes(b"webp-data")
        resp = client.get("/test-art-stub/character_art__1__full-x.webp")
        assert resp.status_code == 200
        assert resp.content == b"webp-data"
        assert resp.headers["content-type"] == "image/webp"

    def test_route_404_for_missing_key(
        self, client, monkeypatch, tmp_path,
    ):
        monkeypatch.setenv("ART_STORAGE_USE_TEST_STUB", "1")
        monkeypatch.setenv("ART_STORAGE_STUB_DIR", str(tmp_path))
        resp = client.get("/test-art-stub/nope.webp")
        assert resp.status_code == 404

    def test_route_404_when_stub_off(self, client, monkeypatch):
        monkeypatch.delenv("ART_STORAGE_USE_TEST_STUB", raising=False)
        resp = client.get("/test-art-stub/anything")
        assert resp.status_code == 404
