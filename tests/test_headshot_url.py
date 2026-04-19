"""Tests for the ``headshot_url`` Jinja global + index-page rendering."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.main import headshot_url
from app.models import Character


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

    def test_returns_public_url_without_cache_bust_when_no_updated_at(
        self, monkeypatch
    ):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=None,
        )
        url = headshot_url(char)
        assert url == "https://b.s3.amazonaws.com/character_art/1/head-x.webp"

    def test_appends_cache_bust_from_art_updated_at(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        monkeypatch.setenv("S3_BACKUP_REGION", "us-east-1")
        ts = datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=ts,
        )
        url = headshot_url(char)
        assert url == (
            f"https://b.s3.amazonaws.com/character_art/1/head-x.webp"
            f"?v={int(ts.timestamp())}"
        )

    def test_respects_non_default_region(self, monkeypatch):
        monkeypatch.setenv("S3_BACKUP_BUCKET", "b")
        monkeypatch.setenv("S3_BACKUP_REGION", "eu-west-1")
        char = SimpleNamespace(
            headshot_s3_key="character_art/1/head-x.webp",
            art_updated_at=None,
        )
        url = headshot_url(char)
        assert url == (
            "https://b.s3.eu-west-1.amazonaws.com/character_art/1/head-x.webp"
        )

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
