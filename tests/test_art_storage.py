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

    def test_list_art_keys_excludes_archived_keys(self, tmp_path):
        """Live + archived objects share the flat stub dir; the live
        listing must not return archived keys (else the orphan sweep
        would delete them)."""
        (tmp_path / "character_art__5__full-x.webp").write_bytes(b"live")
        (tmp_path / "character_art_archive__5__full-x.webp").write_bytes(b"arch")
        with patch("app.services.art_storage._get_s3_client") as factory:
            keys = art_storage.list_art_keys("b", "us-east-1")
            factory.assert_not_called()
        assert keys == ["character_art/5/full-x.webp"]

    def test_archive_art_moves_file_to_archive_prefix(self, tmp_path):
        (tmp_path / "character_art__5__full-x.webp").write_bytes(b"payload")
        with patch("app.services.art_storage._get_s3_client") as factory:
            created = art_storage.archive_art(
                "b", "us-east-1", "character_art/5/full-x.webp",
            )
            factory.assert_not_called()
        assert created == ["character_art_archive/5/full-x.webp"]
        # The live file is gone and the archive file holds the bytes.
        assert not (tmp_path / "character_art__5__full-x.webp").exists()
        moved = tmp_path / "character_art_archive__5__full-x.webp"
        assert moved.read_bytes() == b"payload"

    def test_archive_art_skips_missing_source_but_returns_key(self, tmp_path):
        with patch("app.services.art_storage._get_s3_client") as factory:
            created = art_storage.archive_art(
                "b", "us-east-1", "character_art/5/gone.webp",
            )
            factory.assert_not_called()
        assert created == ["character_art_archive/5/gone.webp"]

    def test_copy_object_key_copies_in_stub(self, tmp_path):
        (tmp_path / "character_art_archive__5__full-x.webp").write_bytes(b"src")
        with patch("app.services.art_storage._get_s3_client") as factory:
            art_storage.copy_object_key(
                "character_art_archive/5/full-x.webp",
                "character_art/5/full-new.webp",
                bucket="b", region="us-east-1",
            )
            factory.assert_not_called()
        # Source preserved, destination written.
        assert (tmp_path / "character_art_archive__5__full-x.webp").exists()
        assert (tmp_path / "character_art__5__full-new.webp").read_bytes() == b"src"

    def test_list_archived_keys_filters_by_char_in_stub(self, tmp_path):
        (tmp_path / "character_art_archive__5__full-x.webp").write_bytes(b"a")
        (tmp_path / "character_art_archive__9__full-y.webp").write_bytes(b"b")
        with patch("app.services.art_storage._get_s3_client") as factory:
            keys = art_storage.list_archived_keys(5, bucket="b", region="us-east-1")
            factory.assert_not_called()
        assert keys == ["character_art_archive/5/full-x.webp"]


class TestArchivePrefix:
    def test_default_prefix(self, monkeypatch):
        monkeypatch.delenv("S3_CHARACTER_ART_ARCHIVE_PREFIX", raising=False)
        assert art_storage.archive_prefix() == "character_art_archive/"

    def test_custom_prefix_respected(self, monkeypatch):
        monkeypatch.setenv("S3_CHARACTER_ART_ARCHIVE_PREFIX", "arch/")
        assert art_storage.archive_prefix() == "arch/"

    def test_trailing_slash_added(self, monkeypatch):
        monkeypatch.setenv("S3_CHARACTER_ART_ARCHIVE_PREFIX", "arch")
        assert art_storage.archive_prefix() == "arch/"

    def test_archive_prefix_is_disjoint_from_live_prefix(self, monkeypatch):
        """The orphan sweep lists the live prefix; the archive prefix must
        not be a string-prefix of it (else archives would be swept)."""
        monkeypatch.delenv("S3_CHARACTER_ART_PREFIX", raising=False)
        monkeypatch.delenv("S3_CHARACTER_ART_ARCHIVE_PREFIX", raising=False)
        live = art_storage.art_prefix()
        archive = art_storage.archive_prefix()
        assert not archive.startswith(live)
        # A concrete archive key must not start with the live prefix.
        assert not f"{archive}5/full-x.webp".startswith(live)


class TestArchiveKeepDefault:
    def test_default_is_ten(self, monkeypatch):
        monkeypatch.delenv("ART_ARCHIVE_KEEP", raising=False)
        assert art_storage.archive_keep_default() == 10

    def test_custom_value(self, monkeypatch):
        monkeypatch.setenv("ART_ARCHIVE_KEEP", "3")
        assert art_storage.archive_keep_default() == 3

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("ART_ARCHIVE_KEEP", "-4")
        assert art_storage.archive_keep_default() == 0

    def test_invalid_falls_back_to_ten(self, monkeypatch):
        monkeypatch.setenv("ART_ARCHIVE_KEEP", "lots")
        assert art_storage.archive_keep_default() == 10


class TestArchiveKeyFor:
    def test_maps_live_key_into_archive_prefix(self, monkeypatch):
        monkeypatch.delenv("S3_CHARACTER_ART_PREFIX", raising=False)
        monkeypatch.delenv("S3_CHARACTER_ART_ARCHIVE_PREFIX", raising=False)
        akey = art_storage.archive_key_for("character_art/5/full-x.webp")
        assert akey == "character_art_archive/5/full-x.webp"

    def test_non_prefixed_key_is_prepended(self, monkeypatch):
        monkeypatch.delenv("S3_CHARACTER_ART_ARCHIVE_PREFIX", raising=False)
        # Defensive: a key that doesn't start with the live prefix still
        # lands under the archive prefix.
        assert art_storage.archive_key_for("old_full") == (
            "character_art_archive/old_full"
        )


class TestArchiveArt:
    @patch("app.services.art_storage._get_s3_client")
    def test_copies_then_deletes_each_live_key(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        created = art_storage.archive_art(
            "bucket", "us-east-1",
            "character_art/5/full-x.webp",
            "character_art/5/head-x.webp",
        )
        assert created == [
            "character_art_archive/5/full-x.webp",
            "character_art_archive/5/head-x.webp",
        ]
        assert client.copy_object.call_count == 2
        first = client.copy_object.call_args_list[0].kwargs
        assert first["Bucket"] == "bucket"
        assert first["Key"] == "character_art_archive/5/full-x.webp"
        assert first["CopySource"] == {
            "Bucket": "bucket", "Key": "character_art/5/full-x.webp",
        }
        deleted = {c.kwargs["Key"] for c in client.delete_object.call_args_list}
        assert deleted == {
            "character_art/5/full-x.webp", "character_art/5/head-x.webp",
        }

    @patch("app.services.art_storage._get_s3_client")
    def test_ignores_none_keys(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        created = art_storage.archive_art(
            "b", "us-east-1", None, "character_art/1/full.webp", None,
        )
        assert created == ["character_art_archive/1/full.webp"]
        assert client.copy_object.call_count == 1

    @patch("app.services.art_storage._get_s3_client")
    def test_no_client_when_all_none(self, mock_get_client):
        assert art_storage.archive_art("b", "us-east-1", None, None) == []
        mock_get_client.assert_not_called()


class TestCopyObjectKey:
    @patch("app.services.art_storage._get_s3_client")
    def test_copies_without_deleting_source(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        art_storage.copy_object_key(
            "character_art_archive/5/full-x.webp",
            "character_art/5/full-new.webp",
            bucket="b", region="us-east-1",
        )
        client.copy_object.assert_called_once_with(
            Bucket="b", Key="character_art/5/full-new.webp",
            CopySource={"Bucket": "b", "Key": "character_art_archive/5/full-x.webp"},
        )
        client.delete_object.assert_not_called()


class TestListArchivedKeys:
    @patch("app.services.art_storage._get_s3_client")
    def test_lists_under_char_prefix(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [
                {"Key": "character_art_archive/5/full-a.webp"},
                {"Key": "character_art_archive/5/head-a.webp"},
            ]},
        ]
        keys = art_storage.list_archived_keys(5, bucket="b", region="us-east-1")
        assert keys == [
            "character_art_archive/5/full-a.webp",
            "character_art_archive/5/head-a.webp",
        ]
        # Paginated under the per-character archive prefix.
        _, kwargs = paginator.paginate.call_args
        assert kwargs["Prefix"] == "character_art_archive/5/"

    @patch("app.services.art_storage._get_s3_client")
    def test_list_all_uses_bare_archive_prefix(self, mock_get_client):
        client = MagicMock()
        mock_get_client.return_value = client
        paginator = MagicMock()
        client.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{"Contents": []}]
        art_storage.list_all_archived_keys("b", "us-east-1")
        _, kwargs = paginator.paginate.call_args
        assert kwargs["Prefix"] == "character_art_archive/"


class TestArchivedVersions:
    @patch("app.services.art_storage.list_archived_keys")
    def test_groups_full_and_head_and_sorts_newest_first(self, mock_list):
        mock_list.return_value = [
            "character_art_archive/5/full-2026-01-01T00-00-00Z.webp",
            "character_art_archive/5/head-2026-01-01T00-00-00Z.webp",
            "character_art_archive/5/full-2026-03-09T08-00-00Z.webp",
            "character_art_archive/5/head-2026-03-09T08-00-00Z.webp",
        ]
        versions = art_storage.archived_versions(5, bucket="b", region="r")
        assert [v["ts"] for v in versions] == [
            "2026-03-09T08-00-00Z", "2026-01-01T00-00-00Z",
        ]
        assert versions[0]["full_key"].endswith("full-2026-03-09T08-00-00Z.webp")
        assert versions[0]["head_key"].endswith("head-2026-03-09T08-00-00Z.webp")

    @patch("app.services.art_storage.list_archived_keys")
    def test_skips_non_matching_and_full_less_versions(self, mock_list):
        mock_list.return_value = [
            "character_art_archive/5/full-2026-01-01T00-00-00Z.webp",
            "character_art_archive/5/head-2026-02-02T00-00-00Z.webp",  # no full
            "character_art_archive/5/notes.txt",                        # not webp
            "character_art_archive/5/thumb-2026-01-01T00-00-00Z.webp",  # bad kind
        ]
        versions = art_storage.archived_versions(5, bucket="b", region="r")
        # Only the one ts that has a full key survives.
        assert len(versions) == 1
        assert versions[0]["ts"] == "2026-01-01T00-00-00Z"
        assert versions[0]["head_key"] is None


class TestPruneArchive:
    @patch("app.services.art_storage.delete_art")
    @patch("app.services.art_storage.list_archived_keys")
    def test_deletes_versions_beyond_keep(self, mock_list, mock_delete):
        # Three versions; keep newest 1 -> the two oldest (4 objects) go.
        mock_list.return_value = [
            f"character_art_archive/5/{k}-{ts}.webp"
            for ts in ("2026-01-01T00-00-00Z",
                       "2026-02-01T00-00-00Z",
                       "2026-03-01T00-00-00Z")
            for k in ("full", "head")
        ]
        n = art_storage.prune_archive(5, bucket="b", region="r", keep=1)
        assert n == 4
        deleted = set(mock_delete.call_args.args[2:])
        assert deleted == {
            "character_art_archive/5/full-2026-01-01T00-00-00Z.webp",
            "character_art_archive/5/head-2026-01-01T00-00-00Z.webp",
            "character_art_archive/5/full-2026-02-01T00-00-00Z.webp",
            "character_art_archive/5/head-2026-02-01T00-00-00Z.webp",
        }

    @patch("app.services.art_storage.delete_art")
    @patch("app.services.art_storage.list_archived_keys")
    def test_nothing_deleted_within_limit(self, mock_list, mock_delete):
        mock_list.return_value = [
            "character_art_archive/5/full-2026-03-01T00-00-00Z.webp",
            "character_art_archive/5/head-2026-03-01T00-00-00Z.webp",
        ]
        assert art_storage.prune_archive(5, bucket="b", region="r", keep=5) == 0
        mock_delete.assert_not_called()

    @patch("app.services.art_storage.delete_art")
    @patch("app.services.art_storage.list_archived_keys")
    def test_uses_default_keep_when_unspecified(self, mock_list, mock_delete, monkeypatch):
        monkeypatch.setenv("ART_ARCHIVE_KEEP", "0")
        mock_list.return_value = [
            "character_art_archive/5/full-2026-03-01T00-00-00Z.webp",
        ]
        # keep=0 -> everything is stale
        assert art_storage.prune_archive(5, bucket="b", region="r") == 1


class TestDeleteArchiveForChar:
    @patch("app.services.art_storage.delete_art")
    @patch("app.services.art_storage.list_archived_keys")
    def test_deletes_all_archived_keys(self, mock_list, mock_delete):
        mock_list.return_value = [
            "character_art_archive/5/full-x.webp",
            "character_art_archive/5/head-x.webp",
        ]
        assert art_storage.delete_archive_for_char(5, bucket="b", region="r") == 2
        assert mock_delete.call_args.args[2:] == (
            "character_art_archive/5/full-x.webp",
            "character_art_archive/5/head-x.webp",
        )

    @patch("app.services.art_storage.delete_art")
    @patch("app.services.art_storage.list_archived_keys")
    def test_noop_when_empty(self, mock_list, mock_delete):
        mock_list.return_value = []
        assert art_storage.delete_archive_for_char(5, bucket="b", region="r") == 0
        mock_delete.assert_not_called()


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
