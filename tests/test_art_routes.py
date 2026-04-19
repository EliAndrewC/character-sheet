"""HTTP-level tests for character art routes.

All S3 traffic is mocked at the ``_get_s3_client`` layer the same way
``test_backup.py`` and ``test_art_storage.py`` do it. These tests
exercise:

- permission (logged-out, logged-in-non-editor, owner, admin, grantee)
- validation (oversized, wrong format, wrong aspect ratio)
- the upload -> stage -> crop -> save pipeline end-to-end
- the delete endpoint
- the "art-is-metadata" invariant: art changes never flip is_published
  and never create a new version row
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.models import Character, User as UserModel
from app.services import art_jobs


USER_ID = "183026066498125825"  # owner / admin in conftest
OTHER_ID = "999000111"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _png_bytes(width: int, height: int, color: tuple = (120, 80, 40)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width: int, height: int, color: tuple = (140, 60, 20)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _webp_bytes(width: int, height: int, color: tuple = (20, 100, 180)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def _make_character(client, *, owner_id: str = USER_ID, **fields) -> Character:
    """Insert a Character through the same session the route handlers use."""
    session = client._test_session_factory()
    try:
        char = Character(name="Test Hero", owner_discord_id=owner_id, **fields)
        session.add(char)
        session.commit()
        session.refresh(char)
        return char
    finally:
        session.close()


def _refresh(client, char_id: int) -> Character:
    session = client._test_session_factory()
    try:
        return session.query(Character).filter(Character.id == char_id).first()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clear_staging_registry():
    """Each test runs against a fresh staging registry."""
    with art_jobs._LOCK:
        art_jobs._STAGED.clear()
    yield
    with art_jobs._LOCK:
        art_jobs._STAGED.clear()


@pytest.fixture(autouse=True)
def _s3_env(monkeypatch):
    monkeypatch.setenv("S3_BACKUP_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")


@pytest.fixture()
def s3_client():
    """Patch the S3 client used by ``art_storage`` and yield the mock."""
    with patch("app.services.art_storage._get_s3_client") as get_client:
        client = MagicMock()
        get_client.return_value = client
        yield client


# ---------------------------------------------------------------------------
# GET /characters/{id}/art
# ---------------------------------------------------------------------------


class TestLandingPage:
    def test_loads_for_owner_without_existing_art(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/art")
        assert resp.status_code == 200
        assert b"art-upload-form" in resp.content
        # No "current art panel" when no art exists
        assert b"current-art-panel" not in resp.content

    def test_shows_current_art_panel_when_headshot_set(self, client):
        char = _make_character(client, headshot_s3_key="character_art/1/head-x.webp")
        resp = client.get(f"/characters/{char.id}/art")
        assert resp.status_code == 200
        assert b"current-art-panel" in resp.content
        # Public URL rendered into the page
        assert b"test-bucket.s3.amazonaws.com" in resp.content

    def test_hides_current_art_panel_when_bucket_unset(self, client, monkeypatch):
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        char = _make_character(client, headshot_s3_key="k")
        resp = client.get(f"/characters/{char.id}/art")
        assert resp.status_code == 200
        # With no bucket, no URL is rendered and the panel is hidden
        assert b"current-art-panel" not in resp.content

    def test_404_for_missing_character(self, client):
        resp = client.get("/characters/9999/art")
        assert resp.status_code == 404

    def test_403_when_not_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        # Swap the test user header to a non-editor
        resp = client.get(
            f"/characters/{char.id}/art",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403

    def test_redirects_to_login_when_anonymous(self, client):
        char = _make_character(client)
        # Use a fresh TestClient without the X-Test-User header
        from fastapi.testclient import TestClient
        from app.main import app
        app.dependency_overrides.update(client.app.dependency_overrides)
        anon = TestClient(app)
        resp = anon.get(f"/characters/{char.id}/art", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/auth/login"

    def test_surfaces_art_error_query_param(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/art?art_error=upload_failed")
        assert resp.status_code == 200
        assert b"art-error-banner" in resp.content
        assert b"upload to S3 failed" in resp.content


# ---------------------------------------------------------------------------
# POST /characters/{id}/art/upload
# ---------------------------------------------------------------------------


class TestUploadEndpoint:
    @pytest.mark.parametrize("fmt,bytes_fn", [
        ("png", _png_bytes),
        ("jpg", _jpeg_bytes),
        ("webp", _webp_bytes),
    ])
    def test_valid_upload_redirects_to_crop(self, client, fmt, bytes_fn):
        char = _make_character(client)
        data = bytes_fn(512, 512)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": (f"hero.{fmt}", data, f"image/{fmt}")},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert f"/characters/{char.id}/art/crop/" in resp.headers["location"]
        # Staging slot exists under the redirect target
        staging_id = resp.headers["location"].rsplit("/", 1)[-1]
        staged = art_jobs.get_staged(staging_id)
        assert staged is not None
        assert staged.char_id == char.id
        assert staged.user_id == USER_ID
        assert staged.source == "upload"

    def test_oversized_upload_rejected_413(self, client):
        char = _make_character(client)
        # Build something bigger than MAX_UPLOAD_BYTES (5 MB)
        junk = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("huge.png", junk, "image/png")},
        )
        assert resp.status_code == 413
        assert b"limit is 5 MB" in resp.content

    def test_wrong_format_rejected_422(self, client):
        char = _make_character(client)
        # A GIF - libmagic says image/gif, we reject
        gif = Image.new("RGB", (300, 300), color=(0, 0, 0))
        buf = io.BytesIO()
        gif.save(buf, format="GIF")
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("anim.gif", buf.getvalue(), "image/gif")},
        )
        assert resp.status_code == 422
        assert b"PNG, JPG, and WEBP" in resp.content

    def test_wrong_aspect_ratio_rejected_422(self, client):
        char = _make_character(client)
        # 1024 x 256 = 4:1 ratio, outside the allowed 0.5-2.0 band
        data = _png_bytes(1024, 256)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("wide.png", data, "image/png")},
        )
        assert resp.status_code == 422
        assert b"aspect ratio" in resp.content

    def test_empty_upload_rejected_400(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert resp.status_code == 400

    def test_403_for_non_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        data = _png_bytes(512, 512)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("hero.png", data, "image/png")},
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403

    def test_404_for_missing_character(self, client):
        data = _png_bytes(512, 512)
        resp = client.post(
            "/characters/9999/art/upload",
            files={"file": ("hero.png", data, "image/png")},
        )
        assert resp.status_code == 404

    def test_error_page_shows_current_headshot_when_present(self, client):
        """When an upload fails but the character already has art, the
        landing-with-error response must still render the current-art
        thumbnail URL (not drop the panel)."""
        char = _make_character(
            client, headshot_s3_key="character_art/3/head-old.webp",
        )
        # Upload something the validator rejects (wrong aspect ratio)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("wide.png", _png_bytes(1024, 256), "image/png")},
        )
        assert resp.status_code == 422
        assert b"current-art-panel" in resp.content
        assert b"test-bucket.s3.amazonaws.com" in resp.content


# ---------------------------------------------------------------------------
# GET /characters/{id}/art/crop/{sid}
# ---------------------------------------------------------------------------


class TestCropPage:
    def _upload_and_get_staging_id(self, client, char_id: int) -> str:
        data = _png_bytes(512, 512)
        resp = client.post(
            f"/characters/{char_id}/art/upload",
            files={"file": ("hero.png", data, "image/png")},
            follow_redirects=False,
        )
        return resp.headers["location"].rsplit("/", 1)[-1]

    def test_renders_cropper_for_valid_staging_id(self, client):
        char = _make_character(client)
        sid = self._upload_and_get_staging_id(client, char.id)
        resp = client.get(f"/characters/{char.id}/art/crop/{sid}")
        assert resp.status_code == 200
        assert b"art-crop-form" in resp.content
        # Cropper.js CSS is linked
        assert b"cropperjs/cropper.min.css" in resp.content
        # Default bbox pulled from detect_face
        assert b'name="x"' in resp.content
        assert b'name="y"' in resp.content
        assert b'name="w"' in resp.content
        assert b'name="h"' in resp.content

    def test_404_for_unknown_staging_id(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/art/crop/not-a-real-id")
        assert resp.status_code == 404

    def test_404_when_staging_id_belongs_to_different_character(self, client):
        char_a = _make_character(client)
        char_b = _make_character(client)
        sid = self._upload_and_get_staging_id(client, char_a.id)
        # Try to access char_a's staged upload via char_b's URL
        resp = client.get(f"/characters/{char_b.id}/art/crop/{sid}")
        assert resp.status_code == 404

    def test_404_when_staging_id_belongs_to_different_user(self, client):
        char = _make_character(client)
        sid = self._upload_and_get_staging_id(client, char.id)
        # Make the character editable by the other user too
        session = client._test_session_factory()
        session.add(UserModel(discord_id=OTHER_ID, display_name="Other"))
        # The character's owner is USER_ID; add OTHER_ID to editors
        refreshed = session.query(Character).filter(Character.id == char.id).first()
        refreshed.editor_discord_ids = [OTHER_ID]
        session.commit()
        session.close()
        # Other user can reach the edit page but can't steal someone
        # else's staged upload
        resp = client.get(
            f"/characters/{char.id}/art/crop/{sid}",
            headers={"X-Test-User": f"{OTHER_ID}:Other"},
        )
        assert resp.status_code == 404

    def test_403_for_non_editor_on_crop_page(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.get(
            f"/characters/{char.id}/art/crop/anything",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /characters/{id}/art/staged/{sid}
# ---------------------------------------------------------------------------


class TestStagedImageEndpoint:
    def test_returns_image_bytes(self, client):
        char = _make_character(client)
        data = _png_bytes(400, 400)
        resp = client.post(
            f"/characters/{char.id}/art/upload",
            files={"file": ("hero.png", data, "image/png")},
            follow_redirects=False,
        )
        sid = resp.headers["location"].rsplit("/", 1)[-1]
        img = client.get(f"/characters/{char.id}/art/staged/{sid}")
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/png"
        assert img.headers["cache-control"] == "private, no-store"
        # Validate bytes decode as a PNG
        decoded = Image.open(io.BytesIO(img.content))
        assert decoded.size == (400, 400)

    def test_404_for_unknown_sid(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/art/staged/not-real")
        assert resp.status_code == 404

    def test_404_when_sid_belongs_to_different_character(self, client):
        char_a = _make_character(client)
        char_b = _make_character(client)
        data = _png_bytes(400, 400)
        resp = client.post(
            f"/characters/{char_a.id}/art/upload",
            files={"file": ("hero.png", data, "image/png")},
            follow_redirects=False,
        )
        sid = resp.headers["location"].rsplit("/", 1)[-1]
        resp2 = client.get(f"/characters/{char_b.id}/art/staged/{sid}")
        assert resp2.status_code == 404

    def test_403_for_non_editor_on_staged(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.get(
            f"/characters/{char.id}/art/staged/anything",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /characters/{id}/art/crop/{sid}
# ---------------------------------------------------------------------------


class TestCropSave:
    def _upload(self, client, char_id: int) -> str:
        resp = client.post(
            f"/characters/{char_id}/art/upload",
            files={"file": ("h.png", _png_bytes(800, 800), "image/png")},
            follow_redirects=False,
        )
        return resp.headers["location"].rsplit("/", 1)[-1]

    def test_happy_path_uploads_to_s3_and_updates_character(self, client, s3_client):
        char = _make_character(client)
        sid = self._upload(client, char.id)
        resp = client.post(
            f"/characters/{char.id}/art/crop/{sid}",
            data={"x": 100, "y": 100, "w": 300, "h": 400},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/characters/{char.id}/edit?art_saved=1"
        # S3 saw two put_objects (full + headshot)
        assert s3_client.put_object.call_count == 2
        calls = s3_client.put_object.call_args_list
        assert all(c.kwargs["ACL"] == "public-read" for c in calls)
        # Character row updated
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key is not None
        assert refreshed.headshot_s3_key is not None
        assert refreshed.art_source == "upload"
        assert refreshed.art_prompt is None
        assert refreshed.art_updated_at is not None
        # Staging slot cleaned up
        assert art_jobs.get_staged(sid) is None

    def test_overwrites_previous_art_and_cleans_up_old_keys(self, client, s3_client):
        char = _make_character(
            client,
            art_s3_key="old_full", headshot_s3_key="old_head",
        )
        sid = self._upload(client, char.id)
        client.post(
            f"/characters/{char.id}/art/crop/{sid}",
            data={"x": 10, "y": 10, "w": 300, "h": 400},
            follow_redirects=False,
        )
        # Old keys got deleted
        delete_keys = [c.kwargs["Key"] for c in s3_client.delete_object.call_args_list]
        assert "old_full" in delete_keys
        assert "old_head" in delete_keys
        # New keys are now on the row
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key != "old_full"
        assert refreshed.headshot_s3_key != "old_head"

    def test_art_change_does_not_flip_is_published(self, client, s3_client):
        """Art is metadata - saving art must not create a Draft or flip
        is_published. This is the key invariant from Phase 4's plan."""
        # Seed a published character with a consistent snapshot so the
        # clean baseline is "no unpublished changes".
        char = _make_character(client, is_published=True)
        session = client._test_session_factory()
        refreshed = session.query(Character).filter(Character.id == char.id).first()
        refreshed.published_state = refreshed.to_dict()
        session.commit()
        session.close()
        # Sanity-check the baseline before saving art
        baseline = _refresh(client, char.id)
        assert baseline.has_unpublished_changes is False

        sid = self._upload(client, char.id)
        client.post(
            f"/characters/{char.id}/art/crop/{sid}",
            data={"x": 10, "y": 10, "w": 300, "h": 400},
            follow_redirects=False,
        )
        after = _refresh(client, char.id)
        # is_published stayed True and no new diff appeared
        assert after.is_published is True
        assert after.has_unpublished_changes is False
        # Art actually got saved despite the metadata invariant
        assert after.art_s3_key is not None

    def test_storage_not_configured_redirects_with_error(self, client, monkeypatch):
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        char = _make_character(client)
        sid = self._upload(client, char.id)
        resp = client.post(
            f"/characters/{char.id}/art/crop/{sid}",
            data={"x": 10, "y": 10, "w": 300, "h": 400},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "art_error=storage_not_configured" in resp.headers["location"]

    def test_s3_upload_failure_redirects_with_error(self, client, s3_client):
        s3_client.put_object.side_effect = Exception("s3 boom")
        char = _make_character(client)
        sid = self._upload(client, char.id)
        resp = client.post(
            f"/characters/{char.id}/art/crop/{sid}",
            data={"x": 10, "y": 10, "w": 300, "h": 400},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "art_error=upload_failed" in resp.headers["location"]
        # Character row unchanged because the S3 put failed
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key is None

    def test_expired_staging_id_redirects_with_error(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/crop/nope-not-real",
            data={"x": 10, "y": 10, "w": 300, "h": 400},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "art_error=expired" in resp.headers["location"]

    def test_old_key_cleanup_failure_does_not_block_save(self, client, s3_client):
        """If the old-art delete fails, we still update the row. Orphan
        sweep (Phase 9) handles the S3 leftover."""
        char = _make_character(
            client,
            art_s3_key="old_full", headshot_s3_key="old_head",
        )
        sid = self._upload(client, char.id)
        s3_client.delete_object.side_effect = Exception("delete failed")
        resp = client.post(
            f"/characters/{char.id}/art/crop/{sid}",
            data={"x": 10, "y": 10, "w": 300, "h": 400},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "art_saved=1" in resp.headers["location"]
        # New art still persisted even though old-key delete threw
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key != "old_full"

    def test_403_for_non_editor_on_crop_save(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.post(
            f"/characters/{char.id}/art/crop/anything",
            data={"x": 1, "y": 1, "w": 10, "h": 10},
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /characters/{id}/art/delete
# ---------------------------------------------------------------------------


class TestDeleteEndpoint:
    def test_happy_path_deletes_s3_and_clears_columns(self, client, s3_client):
        char = _make_character(
            client,
            art_s3_key="full_k", headshot_s3_key="head_k",
        )
        resp = client.post(
            f"/characters/{char.id}/art/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/characters/{char.id}/edit?art_deleted=1"
        delete_keys = [c.kwargs["Key"] for c in s3_client.delete_object.call_args_list]
        assert "full_k" in delete_keys
        assert "head_k" in delete_keys
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key is None
        assert refreshed.headshot_s3_key is None
        assert refreshed.art_source is None
        assert refreshed.art_prompt is None
        assert refreshed.art_updated_at is not None

    def test_delete_when_no_art_is_noop_redirect(self, client, s3_client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == f"/characters/{char.id}/art"
        s3_client.delete_object.assert_not_called()

    def test_delete_when_bucket_not_configured_still_clears_columns(
        self, client, monkeypatch
    ):
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        char = _make_character(
            client, art_s3_key="k1", headshot_s3_key="k2",
        )
        resp = client.post(
            f"/characters/{char.id}/art/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key is None
        assert refreshed.headshot_s3_key is None

    def test_delete_when_s3_raises_still_clears_columns(self, client, s3_client):
        s3_client.delete_object.side_effect = Exception("s3 down")
        char = _make_character(
            client, art_s3_key="k1", headshot_s3_key="k2",
        )
        resp = client.post(
            f"/characters/{char.id}/art/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # DB columns cleared despite S3 failure; orphans get swept later
        refreshed = _refresh(client, char.id)
        assert refreshed.art_s3_key is None

    def test_delete_does_not_flip_is_published(self, client, s3_client):
        char = _make_character(
            client, art_s3_key="k1", headshot_s3_key="k2",
            is_published=True,
        )
        session = client._test_session_factory()
        refreshed = session.query(Character).filter(Character.id == char.id).first()
        refreshed.published_state = refreshed.to_dict()
        session.commit()
        session.close()
        assert _refresh(client, char.id).has_unpublished_changes is False

        client.post(f"/characters/{char.id}/art/delete", follow_redirects=False)
        after = _refresh(client, char.id)
        assert after.is_published is True
        assert after.has_unpublished_changes is False
        assert after.art_s3_key is None

    def test_403_for_non_editor_on_delete(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.post(
            f"/characters/{char.id}/art/delete",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403

    def test_404_for_missing_character_on_delete(self, client):
        resp = client.post("/characters/9999/art/delete")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Edit page integrations
# ---------------------------------------------------------------------------


class TestEditPageIntegration:
    def test_art_saved_banner_renders(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/edit?art_saved=1")
        assert resp.status_code == 200
        assert b"art-saved-banner" in resp.content

    def test_art_deleted_banner_renders(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/edit?art_deleted=1")
        assert resp.status_code == 200
        assert b"art-deleted-banner" in resp.content

    def test_character_art_menu_appears_on_edit_page(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/edit")
        assert resp.status_code == 200
        assert b"character-art-menu" in resp.content

    def test_delete_option_only_shows_when_art_exists(self, client):
        # Without art
        char_no = _make_character(client)
        resp_no = client.get(f"/characters/{char_no.id}/edit")
        assert b'data-action="delete-art"' not in resp_no.content
        # With art
        char_yes = _make_character(
            client, headshot_s3_key="character_art/2/head-x.webp",
        )
        resp_yes = client.get(f"/characters/{char_yes.id}/edit")
        assert b'data-action="delete-art"' in resp_yes.content

    def test_overwrite_modal_only_shows_when_art_exists(self, client):
        char_no = _make_character(client)
        assert b"art-overwrite-modal" not in client.get(
            f"/characters/{char_no.id}/edit"
        ).content
        char_yes = _make_character(
            client, headshot_s3_key="character_art/2/head-x.webp",
        )
        assert b"art-overwrite-modal" in client.get(
            f"/characters/{char_yes.id}/edit"
        ).content


# ---------------------------------------------------------------------------
# Staging registry TTL + reap
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 7: Generate-with-AI wizard
# ---------------------------------------------------------------------------


class TestGenerateGenderPage:
    def test_renders_for_owner(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/art/generate")
        assert resp.status_code == 200
        assert b"art-gen-gender-page" in resp.content
        assert b"gender-male" in resp.content
        assert b"gender-female" in resp.content

    def test_403_for_non_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.get(
            f"/characters/{char.id}/art/generate",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403

    def test_404_for_missing_character(self, client):
        assert client.get("/characters/9999/art/generate").status_code == 404


class TestGenerateOptionsPage:
    def test_renders_with_wasp_selected_by_default(self, client):
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options?gender=male"
        )
        assert resp.status_code == 200
        assert b"art-gen-options-page" in resp.content
        # Wasp is pre-selected in the dropdown
        assert b'value="Wasp"' in resp.content
        assert b"selected" in resp.content
        # Age defaults to 20
        assert b'value="20"' in resp.content
        # Age checkbox is disabled (mandatory)
        assert b"age-checkbox" in resp.content
        assert b"disabled" in resp.content
        # Gender carried forward via hidden input
        assert b'name="gender" value="male"' in resp.content

    def test_all_clan_options_present_in_dropdown(self, client):
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options?gender=female"
        )
        assert resp.status_code == 200
        from app.game_data import CLAN_COLORS
        for clan_name in CLAN_COLORS:
            assert f'value="{clan_name}"'.encode() in resp.content, (
                f"missing clan option: {clan_name}"
            )

    def test_both_armor_choices_in_select(self, client):
        """Exactly the two dropdown options from Eli's spec."""
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options?gender=male"
        )
        assert resp.status_code == 200
        assert b"is not wearing armor and has on a kimono" in resp.content
        assert b"is wearing samurai armor" in resp.content

    def test_fixed_suffix_text_rendered(self, client):
        """The suffix sits at the bottom as non-editable display text."""
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options?gender=male"
        )
        assert b"prompt-suffix" in resp.content
        assert b"Make a colored, photo-realistic" in resp.content

    def test_pronoun_baked_into_template_context(self, client):
        """The subject pronoun is computed server-side from gender and
        threaded into the Alpine state as ``subject`` so the rows read
        'He is approximately...' / 'She is approximately...'."""
        char = _make_character(client)
        male = client.get(
            f"/characters/{char.id}/art/generate/options?gender=male"
        )
        female = client.get(
            f"/characters/{char.id}/art/generate/options?gender=female"
        )
        # Look for the JSON-encoded subject passed to the Alpine factory
        assert b'"He"' in male.content
        assert b'"She"' in female.content

    def test_missing_gender_redirects_to_step_1(self, client):
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == (
            f"/characters/{char.id}/art/generate"
        )

    def test_invalid_gender_redirects_to_step_1(self, client):
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options?gender=banana",
            follow_redirects=False,
        )
        assert resp.status_code == 303

    def test_403_for_non_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.get(
            f"/characters/{char.id}/art/generate/options?gender=male",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


class TestGenerateAssemble:
    def test_happy_path_stages_prompt_and_redirects(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/generate/assemble",
            data={
                "gender": "male",
                "clan": "Wasp",
                "age": "30",
                "holding": "a katana",
                "expression": "",
                "armor_choice": "",
                "armor_modifier": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/art/generate/review/" in resp.headers["location"]
        # The staged record has the assembled prompt
        sid = resp.headers["location"].rsplit("/", 1)[-1]
        staged = art_jobs.get_staged(sid)
        assert staged is not None
        assert staged.source == "generated"
        assert staged.char_id == char.id
        assert "Wasp clan noble" in staged.prompt
        assert "He is approximately 30 years old." in staged.prompt
        assert "He is holding a katana." in staged.prompt

    def test_armor_choice_passes_through_to_staged_prompt(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/generate/assemble",
            data={
                "gender": "female", "clan": "Wasp", "age": "25",
                "holding": "", "expression": "",
                "armor_choice": "is wearing samurai armor",
                "armor_modifier": "ornate",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        sid = resp.headers["location"].rsplit("/", 1)[-1]
        staged = art_jobs.get_staged(sid)
        assert "She is wearing samurai armor ornate." in staged.prompt

    def test_invalid_age_bounces_back_to_step_1(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/generate/assemble",
            data={
                "gender": "male", "clan": "Wasp", "age": "999",
                "holding": "", "expression": "", "armor_choice": "",
                "armor_modifier": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/art/generate")

    def test_invalid_clan_bounces_back_to_step_1(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/generate/assemble",
            data={
                "gender": "male", "clan": "Goblin", "age": "20",
                "holding": "", "expression": "", "armor_choice": "",
                "armor_modifier": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/art/generate")

    def test_invalid_armor_choice_bounces_back_to_step_1(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/generate/assemble",
            data={
                "gender": "male", "clan": "Wasp", "age": "20",
                "holding": "", "expression": "",
                "armor_choice": "leather jerkin",
                "armor_modifier": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/art/generate")

    def test_403_for_non_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.post(
            f"/characters/{char.id}/art/generate/assemble",
            data={
                "gender": "male", "clan": "Wasp", "age": "20",
                "holding": "", "expression": "", "armor_choice": "",
                "armor_modifier": "",
            },
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


class TestGenerateReviewPage:
    def _stage_prompt(self, char_id: int, prompt: str) -> str:
        return art_jobs.stage_art(
            user_id=USER_ID, char_id=char_id,
            source="generated", prompt=prompt,
        )

    def test_renders_textarea_with_staged_prompt(self, client):
        char = _make_character(client)
        sid = self._stage_prompt(char.id, "A portrait of a Wasp clan noble.")
        resp = client.get(
            f"/characters/{char.id}/art/generate/review/{sid}"
        )
        assert resp.status_code == 200
        assert b"art-gen-review-page" in resp.content
        assert b"prompt-textarea" in resp.content
        assert b"A portrait of a Wasp clan noble." in resp.content

    def test_404_for_unknown_staging_id(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/art/generate/review/nope")
        assert resp.status_code == 404

    def test_404_when_staging_id_belongs_to_different_user(self, client):
        char = _make_character(client)
        # Stage a prompt under a different user
        sid = art_jobs.stage_art(
            user_id=OTHER_ID, char_id=char.id,
            source="generated", prompt="secret",
        )
        resp = client.get(f"/characters/{char.id}/art/generate/review/{sid}")
        assert resp.status_code == 404

    def test_404_when_staging_id_belongs_to_different_character(self, client):
        char_a = _make_character(client)
        char_b = _make_character(client)
        sid = self._stage_prompt(char_a.id, "prompt")
        resp = client.get(
            f"/characters/{char_b.id}/art/generate/review/{sid}"
        )
        assert resp.status_code == 404

    def test_404_when_staging_slot_is_upload_not_generated(self, client):
        """Don't leak upload bytes to the generate-review endpoint - a
        staging slot that came from Phase 4's upload flow must not be
        readable as a generate-review prompt."""
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=USER_ID, char_id=char.id,
            full_bytes=b"fake-bytes", width=256, height=256,
            source="upload",
        )
        resp = client.get(f"/characters/{char.id}/art/generate/review/{sid}")
        assert resp.status_code == 404

    def test_403_for_non_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.get(
            f"/characters/{char.id}/art/generate/review/any",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


class TestGenerateSubmit:
    """Submit route - kicks off an async Imagen job (Phase 8)."""

    @pytest.fixture(autouse=True)
    def _enabled_and_sync(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_ENABLED", "true")
        from app.services import art_generate_jobs, art_rate_limit
        art_rate_limit.reset_all()
        art_generate_jobs.set_runner(lambda fn: fn())
        with art_generate_jobs._LOCK:
            art_generate_jobs._JOBS.clear()
        yield
        art_generate_jobs.reset_runner()
        with art_generate_jobs._LOCK:
            art_generate_jobs._JOBS.clear()
        art_rate_limit.reset_all()

    def _make_and_stage(self, client):
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=USER_ID, char_id=char.id,
            source="generated", prompt="original prompt",
        )
        return char, sid

    def _png(self, w=384, h=512):
        from PIL import Image
        img = Image.new("RGB", (w, h), color=(120, 90, 60))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_happy_path_returns_ok_json_and_job_runs(self, client):
        char, sid = self._make_and_stage(client)
        with patch(
            "app.services.art_generate.generate_image",
            return_value=self._png(),
        ):
            resp = client.post(
                f"/characters/{char.id}/art/generate/submit/{sid}",
                data={"prompt": "edited final prompt"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        # Staged prompt was overwritten with the edited version
        assert art_jobs.get_staged(sid).prompt == "edited final prompt"
        # Job ran to success (sync runner + mocked generator)
        from app.services import art_generate_jobs
        job = art_generate_jobs.get_job(sid)
        assert job is not None
        assert job.state == art_generate_jobs.STATE_SUCCEEDED

    def test_503_when_kill_switch_off(self, client, monkeypatch):
        char, sid = self._make_and_stage(client)
        monkeypatch.setenv("ART_GEN_ENABLED", "false")
        resp = client.post(
            f"/characters/{char.id}/art/generate/submit/{sid}",
            data={"prompt": "p"},
        )
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "gen_disabled"

    def test_429_when_rate_limit_hit(self, client, monkeypatch):
        from app.services import art_rate_limit
        char, sid = self._make_and_stage(client)
        monkeypatch.setenv("ART_GEN_RATE_LIMIT_PER_DAY", "2")
        # Seed two generations so the third hits the cap
        art_rate_limit.record_generation(USER_ID)
        art_rate_limit.record_generation(USER_ID)
        resp = client.post(
            f"/characters/{char.id}/art/generate/submit/{sid}",
            data={"prompt": "p"},
        )
        assert resp.status_code == 429
        assert resp.json()["error_code"] == "gen_rate_limited"

    def test_404_for_unknown_staging_id(self, client):
        char = _make_character(client)
        resp = client.post(
            f"/characters/{char.id}/art/generate/submit/unknown",
            data={"prompt": "x"},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "staging_not_found"

    def test_404_when_staging_slot_is_not_generated(self, client):
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=USER_ID, char_id=char.id,
            full_bytes=b"fake", width=256, height=256, source="upload",
        )
        resp = client.post(
            f"/characters/{char.id}/art/generate/submit/{sid}",
            data={"prompt": "x"},
        )
        assert resp.status_code == 404

    def test_403_for_non_editor(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.post(
            f"/characters/{char.id}/art/generate/submit/any",
            data={"prompt": "x"},
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


class TestGenerateStatusEndpoint:
    """The review page polls this to drive the in-place UI state machine."""

    @pytest.fixture(autouse=True)
    def _sync(self, monkeypatch):
        monkeypatch.setenv("ART_GEN_ENABLED", "true")
        from app.services import art_generate_jobs, art_rate_limit
        art_rate_limit.reset_all()
        art_generate_jobs.set_runner(lambda fn: fn())
        with art_generate_jobs._LOCK:
            art_generate_jobs._JOBS.clear()
        yield
        art_generate_jobs.reset_runner()
        with art_generate_jobs._LOCK:
            art_generate_jobs._JOBS.clear()
        art_rate_limit.reset_all()

    def _png(self):
        from PIL import Image
        img = Image.new("RGB", (384, 512), color=(200, 100, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_succeeded_payload_includes_crop_urls_and_bbox(self, client):
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=USER_ID, char_id=char.id,
            source="generated", prompt="p",
        )
        with patch(
            "app.services.art_generate.generate_image",
            return_value=self._png(),
        ):
            client.post(
                f"/characters/{char.id}/art/generate/submit/{sid}",
                data={"prompt": "p"},
            )
        resp = client.get(
            f"/characters/{char.id}/art/generate/status/{sid}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "succeeded"
        assert body["image_url"] == (
            f"/characters/{char.id}/art/staged/{sid}"
        )
        assert body["save_url"] == (
            f"/characters/{char.id}/art/crop/{sid}"
        )
        assert len(body["default_bbox"]) == 4
        assert body["aspect_ratio"] == pytest.approx(0.75)
        assert body["image_width"] > 0

    def test_failed_payload_includes_error_code_and_message(self, client):
        from app.services import art_generate
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=USER_ID, char_id=char.id,
            source="generated", prompt="p",
        )
        with patch(
            "app.services.art_generate.generate_image",
            side_effect=art_generate.ImageRateLimitError("quota"),
        ):
            client.post(
                f"/characters/{char.id}/art/generate/submit/{sid}",
                data={"prompt": "p"},
            )
        body = client.get(
            f"/characters/{char.id}/art/generate/status/{sid}"
        ).json()
        assert body["state"] == "failed"
        assert body["error_code"] == "gen_rate_limited"
        assert body["error_message"]

    def test_404_for_unknown_staging_id(self, client):
        char = _make_character(client)
        resp = client.get(
            f"/characters/{char.id}/art/generate/status/unknown"
        )
        assert resp.status_code == 404

    def test_404_for_status_of_another_users_job(self, client):
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=OTHER_ID, char_id=char.id,
            source="generated", prompt="secret",
        )
        with patch(
            "app.services.art_generate.generate_image",
            return_value=self._png(),
        ):
            # Submit as OTHER_ID; editing-header for OTHER_ID
            client.post(
                f"/characters/{char.id}/art/generate/submit/{sid}",
                data={"prompt": "p"},
                headers={"X-Test-User": f"{OTHER_ID}:Other"},
            )
        # Our default USER_ID tries to read the job - forbidden
        assert client.get(
            f"/characters/{char.id}/art/generate/status/{sid}"
        ).status_code == 404

    def test_403_for_non_editor_on_status(self, client):
        char = _make_character(client, owner_id=OTHER_ID)
        resp = client.get(
            f"/characters/{char.id}/art/generate/status/any",
            headers={"X-Test-User": "plainuser:Nobody"},
        )
        assert resp.status_code == 403


class TestReviewTemplateHasCropper:
    """The review template is now a single-page flow - Cropper.js
    library + CSS must be loaded (they're needed once generation
    succeeds)."""

    def test_cropperjs_assets_linked_on_review_page(self, client):
        char = _make_character(client)
        sid = art_jobs.stage_art(
            user_id=USER_ID, char_id=char.id,
            source="generated", prompt="some prompt",
        )
        resp = client.get(
            f"/characters/{char.id}/art/generate/review/{sid}"
        )
        assert resp.status_code == 200
        assert b"cropperjs/cropper.min.css" in resp.content
        assert b"cropperjs/cropper.min.js" in resp.content
        # The save-form and crop section exist in the DOM (hidden until
        # generation succeeds via x-show / x-cloak).
        assert b"art-gen-crop-section" in resp.content
        assert b"art-gen-save-form" in resp.content


class TestEditPageGenerateLink:
    def test_generate_with_ai_appears_in_art_dropdown(self, client):
        char = _make_character(client)
        resp = client.get(f"/characters/{char.id}/edit")
        assert resp.status_code == 200
        assert b'data-action="generate-with-ai"' in resp.content
        assert f"/characters/{char.id}/art/generate".encode() in resp.content


class TestUpdateStagedBytes:
    def test_fills_in_bytes_on_existing_slot(self):
        sid = art_jobs.stage_art(
            user_id="u1", char_id=1, source="generated", prompt="test",
        )
        staged = art_jobs.get_staged(sid)
        assert staged.full_bytes == b""
        assert staged.width == 0
        assert staged.height == 0
        art_jobs.update_staged_bytes(
            sid, full_bytes=b"generated-image-bytes", width=512, height=768,
        )
        updated = art_jobs.get_staged(sid)
        assert updated.full_bytes == b"generated-image-bytes"
        assert updated.width == 512
        assert updated.height == 768
        # Metadata untouched
        assert updated.prompt == "test"
        assert updated.source == "generated"


class TestStagingRegistryTTL:
    def test_reaper_drops_expired_entries(self):
        from datetime import datetime, timedelta, timezone
        sid = art_jobs.stage_art(
            user_id="u1", char_id=1, full_bytes=b"x", width=256, height=256,
        )
        # Force-expire it
        with art_jobs._LOCK:
            art_jobs._STAGED[sid].created_at = (
                datetime.now(timezone.utc) - art_jobs.STAGING_TTL - timedelta(seconds=1)
            )
        # Any call to stage_art/get_staged triggers the reaper
        assert art_jobs.get_staged(sid) is None

    def test_clear_staged_is_a_noop_for_unknown_id(self):
        art_jobs.clear_staged("does-not-exist")  # must not raise
