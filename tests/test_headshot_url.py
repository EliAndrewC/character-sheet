"""Tests for the ``headshot_url`` / ``full_art_url`` Jinja globals
plus the index-page and character-sheet rendering paths that use them.

``public_url`` delegates to boto3's ``generate_presigned_url`` now
(AWS bucket-ACL deprecation fallout - see ``art_storage.py``). Tests
patch the S3 client so the presign call is deterministic and offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.main import full_art_url, headshot_url
from app.models import Character


@pytest.fixture(autouse=True)
def _mock_s3_client():
    """Turn boto3's presigner into a predictable stub: the URL echoes the
    S3 key so assertions can substring-match without needing real AWS
    creds or bucket-specific signatures."""
    with patch("app.services.art_storage._get_s3_client") as factory:
        client = MagicMock()

        def _presign(_op, *, Params, ExpiresIn):
            return (
                f"https://{Params['Bucket']}.s3.amazonaws.com/"
                f"{Params['Key']}?X-Amz-Expires={ExpiresIn}"
            )

        client.generate_presigned_url.side_effect = _presign
        factory.return_value = client
        yield client


# ---------------------------------------------------------------------------
# headshot_url helper - direct
# ---------------------------------------------------------------------------


class TestHeadshotUrlHelper:
    def test_returns_none_when_no_key(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        char = SimpleNamespace(headshot_s3_key=None, art_updated_at=None)
        assert headshot_url(char) is None

    def test_returns_none_when_bucket_not_configured(self, monkeypatch):
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=None,
        )
        assert headshot_url(char) is None

    def test_returns_presigned_url_without_cache_bust_when_no_updated_at(
        self, monkeypatch
    ):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=None,
        )
        url = headshot_url(char)
        assert "character_art/1/head-x.webp" in url
        assert "X-Amz-Expires" in url
        assert "?v=" not in url  # no cache-bust when art_updated_at is None

    def test_appends_cache_bust_from_art_updated_at(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")
        ts = datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=ts,
        )
        url = headshot_url(char)
        assert "character_art/1/head-x.webp" in url
        # Cache-bust suffix appended after the query string the presigner
        # already produced
        assert f"&v={int(ts.timestamp())}" in url

    def test_passes_bucket_and_region_through_to_presigner(
        self, _mock_s3_client, monkeypatch,
    ):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "custom-bucket")
        monkeypatch.setenv("S3_BACKUP_REGION", "eu-west-1")
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=None,
        )
        headshot_url(char)
        kwargs = _mock_s3_client.generate_presigned_url.call_args.kwargs
        assert kwargs["Params"]["Bucket"] == "custom-bucket"
        assert kwargs["Params"]["Key"] == "character_art/1/head-x.webp"

    def test_works_with_real_character_model(self, client, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        session = client._test_session_factory()
        try:
            ts = datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)
            char = Character(
                name="Real Model",
                headshot_s3_key="character_art/99/head-abc.webp",
                art_updated_at=ts,
            )
            session.add(char)
            session.commit()
            session.refresh(char)
        finally:
            session.close()
        url = headshot_url(char)
        assert url is not None
        assert "character_art/99/head-abc.webp" in url
        assert f"v={int(ts.timestamp())}" in url


# ---------------------------------------------------------------------------
# Index page rendering
# ---------------------------------------------------------------------------


class TestIndexPageRendering:
    def test_shows_headshot_img_when_character_has_art(self, client, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        session = client._test_session_factory()
        char = Character(
            name="Has Art",
            owner_discord_id="183026066498125825",
            school="akodo_bushi",
            is_published=True,
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        )
        session.add(char)
        session.commit()
        session.close()

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"character-headshot" in resp.content
        assert b"character_art/1/head-x.webp" in resp.content
        # Placeholder not rendered for this card
        assert resp.content.count(b"character-headshot-placeholder") == 0

    def test_shows_placeholder_when_character_has_no_art(self, client):
        session = client._test_session_factory()
        char = Character(
            name="No Art",
            owner_discord_id="183026066498125825",
            school="akodo_bushi",
            is_published=True,
        )
        session.add(char)
        session.commit()
        session.close()

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"character-headshot-placeholder" in resp.content
        # No img tag pointing at S3
        assert b"character-headshot\"" not in resp.content

    def test_mixed_cards_render_correct_element_per_character(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        session = client._test_session_factory()
        session.add(Character(
            name="WithArt",
            owner_discord_id="183026066498125825",
            school="akodo_bushi",
            is_published=True,
            headshot_s3_key="character_art/1/head.webp",
            art_updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        ))
        session.add(Character(
            name="WithoutArt",
            owner_discord_id="183026066498125825",
            school="akodo_bushi",
            is_published=True,
        ))
        session.commit()
        session.close()

        resp = client.get("/")
        # Exactly one of each, on the same page
        assert resp.content.count(b'data-testid="character-headshot"') == 1
        assert resp.content.count(b'data-testid="character-headshot-placeholder"') == 1

    def test_index_renders_when_no_bucket_configured(self, client, monkeypatch):
        """If S3 isn't configured, every card shows the placeholder - the
        page must still render without crashing."""
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        session = client._test_session_factory()
        session.add(Character(
            name="Art Config Missing",
            owner_discord_id="183026066498125825",
            school="akodo_bushi",
            is_published=True,
            headshot_s3_key="character_art/1/head.webp",
        ))
        session.commit()
        session.close()
        resp = client.get("/")
        assert resp.status_code == 200
        # Without a bucket, the img src helper returned None, so the
        # placeholder path was taken.
        assert b"character-headshot-placeholder" in resp.content
        assert b"character_art/1/head.webp" not in resp.content


# ---------------------------------------------------------------------------
# full_art_url helper + sheet-page rendering (Phase 6)
# ---------------------------------------------------------------------------


class TestFullArtUrlHelper:
    def test_returns_none_when_no_key(self):
        char = SimpleNamespace(art_s3_key=None, art_updated_at=None)
        assert full_art_url(char) is None

    def test_returns_presigned_url_with_cache_bust(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")
        ts = datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)
        char = SimpleNamespace(
            art_s3_key="character_art/1/full-x.webp",
            art_updated_at=ts,
        )
        url = full_art_url(char)
        assert "character_art/1/full-x.webp" in url
        # Presign adds X-Amz-Expires; our helper appends the cache-bust
        # suffix after the existing query string with ``&``
        assert f"&v={int(ts.timestamp())}" in url

    def test_returns_none_when_bucket_not_configured(self, monkeypatch):
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        char = SimpleNamespace(
            art_s3_key="character_art/1/full-x.webp",
            art_updated_at=None,
        )
        assert full_art_url(char) is None


class TestSheetPageRendering:
    """Verify the View Sheet page emits the art grid when a character has
    art and falls back to the ungridded school section otherwise."""

    def _seed(self, client, **fields):
        session = client._test_session_factory()
        char = Character(
            name="Sheet Art Test",
            owner_discord_id="183026066498125825",
            school="akodo_bushi",
            school_ring_choice="Water",
            is_published=True,
            knacks={"double_attack": 1, "feint": 1, "iaijutsu": 1},
            **fields,
        )
        session.add(char)
        session.commit()
        session.refresh(char)
        session.close()
        return char

    def test_sheet_shows_art_grid_when_character_has_art(self, client, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        ts = datetime(2026, 4, 19, tzinfo=timezone.utc)
        char = self._seed(
            client,
            art_s3_key="character_art/7/full-x.webp",
            headshot_s3_key="character_art/7/head-x.webp",
            art_updated_at=ts,
        )
        resp = client.get(f"/characters/{char.id}")
        assert resp.status_code == 200
        assert b"sheet-art-grid" in resp.content
        assert b"character-full-art" in resp.content
        # Full-art URL rendered
        assert b"character_art/7/full-x.webp" in resp.content
        # Cache-bust query string present
        assert f"v={int(ts.timestamp())}".encode() in resp.content

    def test_sheet_omits_grid_when_character_has_no_art(self, client):
        char = self._seed(client)
        resp = client.get(f"/characters/{char.id}")
        assert resp.status_code == 200
        # No grid wrapper, no img
        assert b"sheet-art-grid" not in resp.content
        assert b"character-full-art" not in resp.content

    def test_sheet_omits_grid_when_bucket_unconfigured(self, client, monkeypatch):
        """art_s3_key set but no bucket configured -> full_art_url() is None,
        grid is skipped, sheet still renders."""
        monkeypatch.delenv("S3_BACKUP_BUCKET", raising=False)
        char = self._seed(
            client,
            art_s3_key="character_art/7/full-x.webp",
        )
        resp = client.get(f"/characters/{char.id}")
        assert resp.status_code == 200
        assert b"sheet-art-grid" not in resp.content
        assert b"character_art/7/full-x.webp" not in resp.content
