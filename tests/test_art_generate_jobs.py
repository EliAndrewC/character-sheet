"""Tests for the ``art_generate_jobs`` async registry.

Exercise the worker path directly by installing a synchronous
dispatcher, so each ``submit_job`` fully completes (success or
failure) before the test checks state.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.services import (
    art_generate,
    art_generate_jobs,
    art_image,
    art_jobs,
    art_rate_limit,
)


@pytest.fixture(autouse=True)
def _sync_runner():
    art_generate_jobs.set_runner(lambda fn: fn())
    with art_generate_jobs._LOCK:
        art_generate_jobs._JOBS.clear()
    with art_jobs._LOCK:
        art_jobs._STAGED.clear()
    art_rate_limit.reset_all()
    yield
    art_generate_jobs.reset_runner()
    with art_generate_jobs._LOCK:
        art_generate_jobs._JOBS.clear()
    with art_jobs._LOCK:
        art_jobs._STAGED.clear()
    art_rate_limit.reset_all()


def _png_bytes(width: int = 384, height: int = 512) -> bytes:
    img = Image.new("RGB", (width, height), color=(60, 80, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _stage_prompt(prompt: str, *, user="u1", char_id=1) -> str:
    return art_jobs.stage_art(
        user_id=user, char_id=char_id,
        source="generated", prompt=prompt,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_success_fills_staged_bytes_and_records_generation(self):
        sid = _stage_prompt("prompt A")
        with patch(
            "app.services.art_generate.generate_image",
            return_value=_png_bytes(),
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="prompt A",
            )
        assert job.state == art_generate_jobs.STATE_SUCCEEDED
        staged = art_jobs.get_staged(sid)
        assert staged.full_bytes != b""
        assert staged.width > 0 and staged.height > 0
        # Rate limit recorded the win
        assert art_rate_limit.count_recent("u1") == 1

    def test_stage_reports_done_on_success(self):
        sid = _stage_prompt("p")
        with patch(
            "app.services.art_generate.generate_image",
            return_value=_png_bytes(),
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.stage == "Done"
        assert job.is_terminal() is True


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


class TestFailures:
    def test_rate_limit_error_marks_job_failed(self):
        sid = _stage_prompt("p")
        err = art_generate.ImageRateLimitError(
            "Imagen returned 429 (rate limit / quota) after retries."
        )
        with patch(
            "app.services.art_generate.generate_image", side_effect=err,
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.state == art_generate_jobs.STATE_FAILED
        assert job.error_code == "gen_rate_limited"
        assert "rate-limit" in job.error_message.lower()
        # Failed generations do NOT count against rate limit
        assert art_rate_limit.count_recent("u1") == 0

    def test_transport_error_marks_job_failed(self):
        sid = _stage_prompt("p")
        with patch(
            "app.services.art_generate.generate_image",
            side_effect=art_generate.ImageTransportError("network down"),
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.state == art_generate_jobs.STATE_FAILED
        assert job.error_code == "gen_transport"

    def test_not_configured_marks_job_failed(self):
        sid = _stage_prompt("p")
        with patch(
            "app.services.art_generate.generate_image",
            side_effect=art_generate.ImageGenNotConfiguredError("no key"),
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.error_code == "gen_not_configured"

    def test_invalid_image_bytes_fail_the_job(self):
        """Imagen returns 200 with bytes Pillow can't decode."""
        sid = _stage_prompt("p")
        with patch(
            "app.services.art_generate.generate_image",
            return_value=b"not-an-image",
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.state == art_generate_jobs.STATE_FAILED
        # From art_image: the not-a-valid-format branch
        assert job.error_code in {"invalid_image_format", "image_decode_error"}

    def test_out_of_spec_generated_image_fails_the_job(self):
        """Imagen returned a real image that fails our ratio / dim checks."""
        # 1024x256 = 4:1, way outside the 0.5-2.0 band
        bad = _png_bytes(width=1024, height=256)
        sid = _stage_prompt("p")
        with patch(
            "app.services.art_generate.generate_image", return_value=bad,
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.state == art_generate_jobs.STATE_FAILED
        assert job.error_code == "image_aspect_ratio"

    def test_expired_staging_slot_fails_the_job(self):
        """If the staging slot was reaped between submit and worker run,
        the job fails cleanly instead of corrupting state."""
        sid = _stage_prompt("p")
        # Simulate reaping AFTER submit_job (and while the worker runs)
        # by clearing before the mocked generate_image would be called.
        call_counter = {"n": 0}

        def fake_gen(prompt):
            # First (and only) call: clear the staging slot before
            # the worker tries to fill bytes into it.
            call_counter["n"] += 1
            art_jobs.clear_staged(sid)
            return _png_bytes()

        # We need the worker to actually read the staged row *before*
        # generate_image runs (it does - see _execute_job). So we
        # instead clear before submit_job by stealing the runner
        # temporarily.
        art_jobs.clear_staged(sid)
        with patch(
            "app.services.art_generate.generate_image", return_value=_png_bytes(),
        ):
            job = art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        assert job.state == art_generate_jobs.STATE_FAILED
        assert job.error_code == "staging_expired"


# ---------------------------------------------------------------------------
# Registry lifecycle
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_get_job_returns_none_for_unknown_id(self):
        assert art_generate_jobs.get_job("does-not-exist") is None

    def test_threaded_runner_actually_spawns_a_thread(self, monkeypatch):
        """Exercise the default (non-patched) ``_threaded_dispatch`` so
        the pragma-less code path has coverage. We force a quick failure
        so the spawned thread terminates within ~100 ms."""
        art_generate_jobs.reset_runner()
        sid = _stage_prompt("p")
        # Patch generate_image to raise immediately so the worker runs,
        # marks the job failed, and exits before the test times out.
        with patch(
            "app.services.art_generate.generate_image",
            side_effect=art_generate.ImageTransportError("boom"),
        ):
            art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
            import time
            for _ in range(50):
                job = art_generate_jobs.get_job(sid)
                if job and job.is_terminal():
                    break
                time.sleep(0.01)
        assert job is not None
        assert job.state == art_generate_jobs.STATE_FAILED
        assert job.error_code == "gen_transport"

    def test_reaper_drops_terminal_jobs_after_ttl(self):
        from datetime import datetime, timedelta, timezone
        sid = _stage_prompt("p")
        with patch(
            "app.services.art_generate.generate_image",
            return_value=_png_bytes(),
        ):
            art_generate_jobs.submit_job(
                user_id="u1", char_id=1, staging_id=sid, prompt="p",
            )
        # Force-expire the job
        with art_generate_jobs._LOCK:
            art_generate_jobs._JOBS[sid].updated_at = (
                datetime.now(timezone.utc)
                - art_generate_jobs._TERMINAL_TTL
                - timedelta(seconds=1)
            )
        # Next submit reaps expired entries
        art_generate_jobs.submit_job(
            user_id="u2", char_id=2, staging_id="new-sid", prompt="p2",
        )
        assert art_generate_jobs.get_job(sid) is None
