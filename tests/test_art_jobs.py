"""Tests for the disk-backed ``art_jobs`` staging registry.

The registry persists each staged record under
``$STAGED_ART_DIR/{staging_id}/`` so the data survives the 15-minute
in-memory TTL the registry used to enforce, plus Fly machine restarts.
A background sweep purges anything older than 24h via
``cleanup_older_than``.

These tests exercise the persistence layer directly. Higher-level
flow tests live in ``test_art_routes.py`` and
``test_art_generate_jobs.py``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import art_jobs


@pytest.fixture(autouse=True)
def _staging_dir(tmp_path, monkeypatch):
    """Point the registry at a per-test tempdir so tests can't see
    each other's staged records and don't touch ``/data``."""
    staging = tmp_path / "staged_art"
    monkeypatch.setenv("STAGED_ART_DIR", str(staging))
    yield staging


def _staging_root() -> Path:
    return Path(os.environ["STAGED_ART_DIR"])


class TestAtomicWrite:
    def test_unlinks_tempfile_when_replace_fails(self, monkeypatch, tmp_path):
        """If ``os.replace`` raises mid-write, the tempfile we created
        must not leak. The original exception is re-raised so the
        caller can decide what to do."""
        target_dir = tmp_path / "staged_art"
        target_dir.mkdir()
        target = target_dir / "out.bin"

        def boom(*_args, **_kwargs):
            raise OSError("simulated cross-fs rename failure")
        monkeypatch.setattr(art_jobs.os, "replace", boom)

        with pytest.raises(OSError, match="simulated"):
            art_jobs._atomic_write(target, b"payload")

        # No tempfile left behind, no target written.
        assert not target.exists()
        leftovers = [p for p in target_dir.iterdir()]
        assert leftovers == []


class TestStageArt:
    def test_upload_mode_persists_bytes_and_metadata(self):
        sid = art_jobs.stage_art(
            user_id="u1", char_id=42,
            full_bytes=b"PNGDATA", width=512, height=768,
            source="upload",
        )
        # The stage dir must exist on disk.
        stage_dir = _staging_root() / sid
        assert stage_dir.is_dir()
        # Metadata sidecar exists and round-trips.
        meta = json.loads((stage_dir / "meta.json").read_text("utf-8"))
        assert meta["user_id"] == "u1"
        assert meta["char_id"] == 42
        assert meta["source"] == "upload"
        assert meta["width"] == 512
        assert meta["height"] == 768
        # Image bytes were written.
        image_files = [p for p in stage_dir.iterdir() if p.name != "meta.json"]
        assert any(p.read_bytes() == b"PNGDATA" for p in image_files)

    def test_generate_mode_persists_prompt_with_empty_bytes(self):
        """Phase-7 prompt-review staging creates the slot before the
        image exists. Bytes are filled in later by update_staged_bytes."""
        sid = art_jobs.stage_art(
            user_id="u2", char_id=7,
            source="generated", prompt="a samurai under sakura",
        )
        meta = json.loads((_staging_root() / sid / "meta.json").read_text("utf-8"))
        assert meta["source"] == "generated"
        assert meta["prompt"] == "a samurai under sakura"
        assert meta["width"] == 0 and meta["height"] == 0

    def test_two_records_dont_collide(self):
        sid_a = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"AAA")
        sid_b = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"BBB")
        assert sid_a != sid_b
        assert art_jobs.get_staged(sid_a).full_bytes == b"AAA"
        assert art_jobs.get_staged(sid_b).full_bytes == b"BBB"


class TestGetStaged:
    def test_returns_record_for_existing_id(self):
        sid = art_jobs.stage_art(
            user_id="u1", char_id=99, full_bytes=b"x", width=1, height=2,
            source="upload",
        )
        rec = art_jobs.get_staged(sid)
        assert rec is not None
        assert rec.id == sid
        assert rec.user_id == "u1"
        assert rec.char_id == 99
        assert rec.full_bytes == b"x"
        assert rec.width == 1
        assert rec.height == 2
        assert rec.source == "upload"

    def test_returns_none_for_unknown_id(self):
        assert art_jobs.get_staged("does-not-exist") is None

    def test_survives_simulated_process_restart(self):
        """The whole point of disk-backing: stage in one 'process',
        wipe any in-memory state, re-read in another 'process', and
        the record still resolves."""
        sid = art_jobs.stage_art(
            user_id="u1", char_id=5, full_bytes=b"persistent", width=10, height=20,
            source="generated", prompt="a horse",
        )
        # Simulate a process restart by clearing any module-level cache
        # the implementation might add. Files on disk are the source of
        # truth, so the record must still be visible.
        for attr in ("_CACHE", "_MEMO"):
            cache = getattr(art_jobs, attr, None)
            if isinstance(cache, dict):
                cache.clear()
        rec = art_jobs.get_staged(sid)
        assert rec is not None
        assert rec.full_bytes == b"persistent"
        assert rec.width == 10 and rec.height == 20
        assert rec.prompt == "a horse"


class TestUpdateStagedPrompt:
    def test_overwrites_prompt_on_disk(self):
        sid = art_jobs.stage_art(
            user_id="u1", char_id=1, source="generated", prompt="original",
        )
        art_jobs.update_staged_prompt(sid, "edited")
        rec = art_jobs.get_staged(sid)
        assert rec.prompt == "edited"
        # Other metadata untouched.
        assert rec.source == "generated"
        assert rec.user_id == "u1"

    def test_no_op_for_unknown_id(self):
        # Must not raise.
        art_jobs.update_staged_prompt("does-not-exist", "p")


class TestUpdateStagedBytes:
    def test_writes_bytes_through_to_disk(self):
        sid = art_jobs.stage_art(
            user_id="u1", char_id=1, source="generated", prompt="p",
        )
        art_jobs.update_staged_bytes(
            sid, full_bytes=b"generated-image", width=384, height=512,
        )
        rec = art_jobs.get_staged(sid)
        assert rec.full_bytes == b"generated-image"
        assert rec.width == 384
        assert rec.height == 512
        # Existing metadata wasn't clobbered.
        assert rec.source == "generated"
        assert rec.prompt == "p"

    def test_no_op_for_unknown_id(self):
        # Should not raise even if the staging dir doesn't exist.
        art_jobs.update_staged_bytes(
            "does-not-exist", full_bytes=b"x", width=1, height=1,
        )


class TestClearStaged:
    def test_removes_staging_directory(self):
        sid = art_jobs.stage_art(
            user_id="u1", char_id=1, full_bytes=b"x",
        )
        stage_dir = _staging_root() / sid
        assert stage_dir.is_dir()
        art_jobs.clear_staged(sid)
        assert not stage_dir.exists()
        assert art_jobs.get_staged(sid) is None

    def test_unknown_id_is_a_noop(self):
        # Must not raise.
        art_jobs.clear_staged("does-not-exist")


class TestCleanupOlderThan:
    def _backdate(self, sid: str, age: timedelta) -> None:
        """Force the meta.json's recorded created_at into the past.

        We backdate the JSON value rather than the file mtime so that
        the cleanup logic stays mtime-independent (atomic_write would
        bump mtime on any sidecar update)."""
        meta_path = _staging_root() / sid / "meta.json"
        meta = json.loads(meta_path.read_text("utf-8"))
        old = datetime.now(timezone.utc) - age
        meta["created_at"] = old.isoformat()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    def test_purges_records_older_than_cutoff(self):
        old = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"old")
        fresh = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"new")
        self._backdate(old, timedelta(hours=25))

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        purged = art_jobs.cleanup_older_than(cutoff)

        assert purged == 1
        assert art_jobs.get_staged(old) is None
        assert art_jobs.get_staged(fresh) is not None

    def test_returns_zero_when_nothing_to_purge(self):
        art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"x")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        assert art_jobs.cleanup_older_than(cutoff) == 0

    def test_handles_empty_root(self):
        # No stage_art calls; sweep should not crash even if the dir
        # doesn't exist yet.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        assert art_jobs.cleanup_older_than(cutoff) == 0

    def test_skips_non_directory_entries_in_root(self):
        """A stray file in the staging root (e.g. lost+found, .DS_Store)
        should be ignored, not crash the sweep."""
        sid = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"x")
        (_staging_root() / "stray.txt").write_text("not a stage", encoding="utf-8")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        assert art_jobs.cleanup_older_than(cutoff) == 0
        assert art_jobs.get_staged(sid) is not None

    def test_skips_dirs_with_malformed_created_at(self):
        sid = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"x")
        meta_path = _staging_root() / sid / "meta.json"
        meta = json.loads(meta_path.read_text("utf-8"))
        meta["created_at"] = "not-a-timestamp"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        cutoff = datetime.now(timezone.utc) + timedelta(hours=1)
        assert art_jobs.cleanup_older_than(cutoff) == 0
        assert (_staging_root() / sid).is_dir()

    def test_skips_dirs_with_unreadable_metadata(self):
        """A dir with a missing or malformed meta.json should be left
        alone. Better to leak a stray dir than to delete data we don't
        understand; an admin can clean it up if it accumulates."""
        sid = art_jobs.stage_art(user_id="u1", char_id=1, full_bytes=b"x")
        (_staging_root() / sid / "meta.json").write_text("not json", encoding="utf-8")
        cutoff = datetime.now(timezone.utc) + timedelta(hours=1)  # everything "old"
        purged = art_jobs.cleanup_older_than(cutoff)
        assert purged == 0
        assert (_staging_root() / sid).is_dir()
