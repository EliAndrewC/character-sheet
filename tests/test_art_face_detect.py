"""Tests for ``app.services.art_face_detect``.

Most branches are exercised via mocks so detection can be tested
without a real-face fixture. A single integration test runs the real
Haar cascade against the abstract (no-face) fixture and asserts the
fallback path fires end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services import art_face_detect as mod
from app.services.art_face_detect import (
    _expand_to_aspect_ratio,
    _fallback_bbox,
    _get_cascade,
    _run_cascade,
    detect_face,
)
from app.services.art_image import HEADSHOT_ASPECT_RATIO

FIXTURE_DIR = Path(__file__).parent / "import_fixtures" / "art"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cascade_cache():
    """Prevent leaks of the cached Haar cascade across tests."""
    mod._cascade = None
    yield
    mod._cascade = None


def _solid_rgb(size: tuple[int, int], color: tuple[int, int, int] = (150, 100, 80)) -> Image.Image:
    return Image.new("RGB", size, color=color)


# ---------------------------------------------------------------------------
# _fallback_bbox: geometry
# ---------------------------------------------------------------------------


class TestFallbackBbox:
    def test_square_image_uses_height_limited_3_4(self):
        # 800x800 - wider than 3:4 portrait. Largest fit: 600x800.
        bbox = _fallback_bbox((800, 800), HEADSHOT_ASPECT_RATIO)
        x, y, w, h = bbox
        # Width must be 600 (height-limited since image is square but portrait fits tall)
        assert w == 600
        assert h == 800
        # Centered horizontally
        assert x == 100
        assert y == 0

    def test_tall_image_width_limited(self):
        # 400x800 - already 1:2, width is the limiting factor for 3:4 portrait
        # img_w/ratio = 400/0.75 = 533 <= img_h=800, so width-limited
        bbox = _fallback_bbox((400, 800), HEADSHOT_ASPECT_RATIO)
        x, y, w, h = bbox
        assert w == 400
        assert h == 533
        assert x == 0
        assert y == (800 - 533) // 2

    def test_exact_three_four_ratio_image(self):
        # 600x800 is exactly 3:4 - the bbox equals the whole image
        bbox = _fallback_bbox((600, 800), HEADSHOT_ASPECT_RATIO)
        assert bbox == (0, 0, 600, 800)

    def test_wide_image_height_limited(self):
        # 1600x600 - very wide. Height limits: h=600, w=600*0.75=450.
        bbox = _fallback_bbox((1600, 600), HEADSHOT_ASPECT_RATIO)
        x, y, w, h = bbox
        assert h == 600
        assert w == 450
        assert x == (1600 - 450) // 2
        assert y == 0

    def test_output_aspect_ratio_within_one_pixel(self):
        """Aspect ratio coercion must produce exactly 3:4 within rounding."""
        for size in [(800, 800), (600, 800), (400, 800), (1600, 600), (1024, 768)]:
            _x, _y, w, h = _fallback_bbox(size, HEADSHOT_ASPECT_RATIO)
            # Error in pixels when reprojecting w back against h*ratio
            expected_w = h * HEADSHOT_ASPECT_RATIO
            assert abs(w - expected_w) <= 1, (
                f"size={size}: w={w}, expected {expected_w}"
            )


# ---------------------------------------------------------------------------
# _expand_to_aspect_ratio: geometry
# ---------------------------------------------------------------------------


class TestExpandToAspectRatio:
    def test_normal_face_fits_in_large_image(self):
        # Face at center of 1200x1600 image. Face 200x200.
        # target_h = 440, target_w = 330. Should fit comfortably.
        bbox = _expand_to_aspect_ratio((500, 700, 200, 200), (1200, 1600),
                                         HEADSHOT_ASPECT_RATIO)
        assert bbox is not None
        x, y, w, h = bbox
        # 3:4 within rounding
        assert abs(w - h * HEADSHOT_ASPECT_RATIO) <= 1
        # Width ~330, height ~440
        assert w == 330
        assert h == 440
        # Face center (600, 800) sits slightly above bbox center
        assert x == pytest.approx(600 - 165, abs=1)
        # top = 800 - 0.45 * 440 = 800 - 198 = 602
        assert y == pytest.approx(602, abs=1)

    def test_face_too_close_to_left_edge_returns_none(self):
        # Face at top-left. Expansion would go negative on left.
        result = _expand_to_aspect_ratio((0, 400, 200, 200), (1200, 1600),
                                          HEADSHOT_ASPECT_RATIO)
        assert result is None

    def test_face_too_close_to_top_edge_returns_none(self):
        # Face at top. Expansion with upward bias goes above y=0.
        result = _expand_to_aspect_ratio((500, 0, 200, 200), (1200, 1600),
                                          HEADSHOT_ASPECT_RATIO)
        assert result is None

    def test_face_too_close_to_right_edge_returns_none(self):
        # Face near right edge of a 1200-wide image.
        result = _expand_to_aspect_ratio((1100, 700, 200, 200), (1200, 1600),
                                          HEADSHOT_ASPECT_RATIO)
        assert result is None

    def test_face_too_close_to_bottom_edge_returns_none(self):
        # Face near bottom edge. target_h = 440, so need 240px below face
        # center. Image height 1600, face center 1500. 1500+240 > 1600.
        result = _expand_to_aspect_ratio((500, 1400, 200, 200), (1200, 1600),
                                          HEADSHOT_ASPECT_RATIO)
        assert result is None

    def test_very_large_face_doesnt_fit(self):
        # Face fills most of the image - expansion impossible.
        result = _expand_to_aspect_ratio((50, 50, 700, 700), (800, 800),
                                          HEADSHOT_ASPECT_RATIO)
        assert result is None

    def test_output_has_exactly_target_aspect_ratio(self):
        """When expansion succeeds, the aspect ratio matches within 1 px."""
        bbox = _expand_to_aspect_ratio((500, 700, 200, 200), (1200, 1600),
                                         HEADSHOT_ASPECT_RATIO)
        assert bbox is not None
        _x, _y, w, h = bbox
        assert abs(w - h * HEADSHOT_ASPECT_RATIO) <= 1

    def test_upward_bias_places_face_above_bbox_center(self):
        """Face center should be above the vertical midline of the bbox."""
        bbox = _expand_to_aspect_ratio((500, 700, 200, 200), (1200, 1600),
                                         HEADSHOT_ASPECT_RATIO)
        assert bbox is not None
        x, y, w, h = bbox
        face_cy = 700 + 100  # 800
        bbox_mid_y = y + h / 2
        assert face_cy < bbox_mid_y  # face center above bbox center


# ---------------------------------------------------------------------------
# _run_cascade + _get_cascade
# ---------------------------------------------------------------------------


class TestGetCascade:
    def test_cascade_is_cached(self):
        """Second call returns the same object without reloading the XML."""
        first = _get_cascade()
        second = _get_cascade()
        assert first is second

    def test_first_call_loads(self):
        """Cache starts empty (autouse fixture reset) then fills."""
        assert mod._cascade is None
        _get_cascade()
        assert mod._cascade is not None


class TestRunCascade:
    def test_solid_color_returns_no_faces(self):
        """A plain solid image has no face structure; expect []."""
        img = _solid_rgb((800, 800), color=(150, 150, 150))
        assert _run_cascade(img) == []

    def test_abstract_fixture_returns_no_faces(self):
        """The committed abstract_no_face.png must NOT trip the cascade."""
        img = Image.open(FIXTURE_DIR / "abstract_no_face.png").convert("RGB")
        assert _run_cascade(img) == []

    def test_returned_faces_are_python_ints(self):
        """The cascade returns numpy int32; we must normalise to int so
        downstream arithmetic and JSON serialisation behave."""
        fake_detections = [[10, 20, 100, 100]]

        # Patch cv2 inside the module
        import numpy as np
        with patch("cv2.CascadeClassifier") as cls:
            inst = MagicMock()
            cls.return_value = inst
            inst.detectMultiScale.return_value = np.array(fake_detections, dtype=np.int32)
            # Force reload via cache reset
            mod._cascade = None
            result = _run_cascade(_solid_rgb((512, 512)))
        assert result == [(10, 20, 100, 100)]
        for coord in result[0]:
            assert isinstance(coord, int)


# ---------------------------------------------------------------------------
# detect_face: full pipeline
# ---------------------------------------------------------------------------


class TestDetectFace:
    def test_no_detection_falls_back(self, monkeypatch):
        monkeypatch.setattr(mod, "_run_cascade", lambda img: [])
        img = _solid_rgb((800, 800))
        bbox = detect_face(img)
        # Matches the fallback for a 800x800 3:4-portrait bbox: (100, 0, 600, 800)
        assert bbox == _fallback_bbox((800, 800), HEADSHOT_ASPECT_RATIO)

    def test_single_detection_expands_when_it_fits(self, monkeypatch):
        monkeypatch.setattr(mod, "_run_cascade",
                             lambda img: [(500, 700, 200, 200)])
        img = _solid_rgb((1200, 1600))
        bbox = detect_face(img)
        # Must be the expanded version, not the fallback
        expected = _expand_to_aspect_ratio(
            (500, 700, 200, 200), (1200, 1600), HEADSHOT_ASPECT_RATIO
        )
        assert bbox == expected

    def test_expansion_overflow_falls_back(self, monkeypatch):
        """Detected face sits near the edge; expansion overflows; fallback fires."""
        monkeypatch.setattr(mod, "_run_cascade",
                             lambda img: [(0, 0, 200, 200)])
        img = _solid_rgb((800, 800))
        bbox = detect_face(img)
        assert bbox == _fallback_bbox((800, 800), HEADSHOT_ASPECT_RATIO)

    def test_multiple_detections_picks_largest(self, monkeypatch):
        """When the cascade returns several faces, the largest (by area)
        is treated as the primary subject."""
        monkeypatch.setattr(mod, "_run_cascade", lambda img: [
            (50, 50, 80, 80),         # small face
            (500, 700, 200, 200),     # big face (the subject)
            (900, 900, 60, 60),       # even smaller
        ])
        img = _solid_rgb((1200, 1600))
        bbox = detect_face(img)
        expected = _expand_to_aspect_ratio(
            (500, 700, 200, 200), (1200, 1600), HEADSHOT_ASPECT_RATIO
        )
        assert bbox == expected

    def test_custom_aspect_ratio_is_respected(self, monkeypatch):
        """Passing a different aspect ratio threads through to both the
        expansion and the fallback."""
        monkeypatch.setattr(mod, "_run_cascade", lambda img: [])
        img = _solid_rgb((800, 800))
        # Square bbox
        bbox = detect_face(img, aspect_ratio=1.0)
        x, y, w, h = bbox
        assert w == h  # square


# ---------------------------------------------------------------------------
# End-to-end smoke: real cascade + real (non-face) fixture
# ---------------------------------------------------------------------------


class TestEndToEndNoFaceFixture:
    def test_abstract_fixture_yields_fallback_bbox(self):
        """Running the real cascade on the committed abstract fixture
        returns the fallback (centered 3:4 rectangle). This verifies the
        whole pipeline - lazy cascade load, cascade invocation, fallback
        selection - wires together correctly."""
        img = Image.open(FIXTURE_DIR / "abstract_no_face.png").convert("RGB")
        bbox = detect_face(img)
        assert bbox == _fallback_bbox(img.size, HEADSHOT_ASPECT_RATIO)


class TestEndToEndRealPortrait:
    """End-to-end tests against committed campaign-art fixtures.

    These verify that the cascade actually detects faces in real
    portraits and that both code paths (expansion-succeeds and
    expansion-overflows) fire correctly.
    """

    def test_portrait_with_headroom_produces_expanded_bbox(self):
        """``portrait_clear_face.jpg`` has a real face with adequate
        headroom. The cascade detects it and the expansion succeeds
        (NOT falling back)."""
        import json
        img = Image.open(FIXTURE_DIR / "portrait_clear_face.jpg").convert("RGB")
        expected = json.loads(
            (FIXTURE_DIR / "portrait_clear_face.expected.json").read_text()
        )
        bbox = detect_face(img)
        # Must not equal the fallback - this fixture exercises the
        # "expansion succeeds" path
        assert bbox != _fallback_bbox(img.size, HEADSHOT_ASPECT_RATIO)
        # Must match the pre-computed bbox within tolerance
        tol = expected["tolerance_px"]
        for actual, exp in zip(bbox, expected["bbox"]):
            assert abs(actual - exp) <= tol, (
                f"bbox {bbox} differs from expected {expected['bbox']} by more than {tol}px"
            )
        # Must be exactly 3:4 within rounding
        _x, _y, w, h = bbox
        assert abs(w - h * HEADSHOT_ASPECT_RATIO) <= 1

    def test_small_image_with_face_falls_back(self):
        """``very_small_face.jpg`` has a detectable face in a canvas too
        small for the 2.2x-face-height expansion to fit. The fallback
        must fire even though a face was detected."""
        img = Image.open(FIXTURE_DIR / "very_small_face.jpg").convert("RGB")
        bbox = detect_face(img)
        # Fallback fires (not because of no detection, but because
        # expansion overflows in this tight canvas).
        assert bbox == _fallback_bbox(img.size, HEADSHOT_ASPECT_RATIO)
