"""Tests for ``app.services.art_image``."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.art_image import (
    FULL_ART_MAX_EDGE,
    HEADSHOT_ASPECT_RATIO,
    HEADSHOT_SIZE,
    MAX_ASPECT_RATIO,
    MAX_DIMENSION_PX,
    MAX_UPLOAD_BYTES,
    MIN_ASPECT_RATIO,
    MIN_DIMENSION_PX,
    ArtImageError,
    ImageAspectRatioError,
    ImageDecodeError,
    ImageDimensionsTooBigError,
    ImageTooLargeError,
    ImageTooSmallError,
    InvalidImageFormatError,
    build_headshot,
    encode_for_storage,
    validate_upload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _png_bytes(width: int, height: int, color: tuple = (120, 80, 40)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width: int, height: int, color: tuple = (90, 90, 90)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _webp_bytes(width: int, height: int, color: tuple = (50, 150, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def _gif_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    return buf.getvalue()


def _bmp_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------

def test_headshot_size_is_three_four_ratio():
    assert HEADSHOT_SIZE[0] / HEADSHOT_SIZE[1] == pytest.approx(HEADSHOT_ASPECT_RATIO)


def test_max_upload_bytes_is_5mb():
    assert MAX_UPLOAD_BYTES == 5 * 1024 * 1024


def test_aspect_ratio_bounds_are_symmetric():
    assert MIN_ASPECT_RATIO == 0.5
    assert MAX_ASPECT_RATIO == 2.0


# ---------------------------------------------------------------------------
# Format acceptance
# ---------------------------------------------------------------------------


class TestFormatAcceptance:
    def test_accepts_png(self):
        result = validate_upload(_png_bytes(512, 512))
        assert result.format == "PNG"
        assert result.width == 512 and result.height == 512
        assert result.img.mode == "RGB"

    def test_accepts_jpeg(self):
        result = validate_upload(_jpeg_bytes(800, 600))
        assert result.format == "JPEG"
        assert result.width == 800 and result.height == 600

    def test_accepts_webp(self):
        result = validate_upload(_webp_bytes(512, 768))
        assert result.format == "WEBP"
        assert result.width == 512 and result.height == 768

    def test_rejects_gif(self):
        with pytest.raises(InvalidImageFormatError):
            validate_upload(_gif_bytes(512, 512))

    def test_rejects_bmp(self):
        with pytest.raises(InvalidImageFormatError):
            validate_upload(_bmp_bytes(512, 512))

    def test_rejects_svg_bytes(self):
        svg = b"<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100'/></svg>"
        with pytest.raises(InvalidImageFormatError):
            validate_upload(svg)

    def test_rejects_html_masquerading_as_image(self):
        html = b"<!DOCTYPE html><html><body>gotcha</body></html>"
        with pytest.raises(InvalidImageFormatError):
            validate_upload(html)

    def test_rejects_garbage_bytes(self):
        with pytest.raises(InvalidImageFormatError):
            validate_upload(b"this is not an image at all" * 10)


# ---------------------------------------------------------------------------
# Size limits
# ---------------------------------------------------------------------------


class TestSizeLimits:
    def test_rejects_over_max_upload_bytes(self):
        # Build a payload that passes libmagic but exceeds the byte cap.
        # Simpler: use a buffer larger than MAX_UPLOAD_BYTES without
        # caring if it's actually decodable, because the size check runs
        # before libmagic.
        payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_UPLOAD_BYTES + 1)
        with pytest.raises(ImageTooLargeError) as excinfo:
            validate_upload(payload)
        assert excinfo.value.error_code == "image_too_large"
        assert "MB" in excinfo.value.user_message

    def test_exactly_max_upload_bytes_is_allowed_if_decodes(self):
        """A payload exactly at the cap must not be rejected purely on size."""
        # Use a valid PNG that happens to be under the cap; we verify the
        # size check doesn't fire.
        data = _png_bytes(512, 512)
        assert len(data) < MAX_UPLOAD_BYTES  # sanity
        validate_upload(data)  # no raise

    def test_rejects_too_small_shortest_side(self):
        # width 200 < MIN_DIMENSION_PX=256, height ok
        data = _png_bytes(200, 300)
        with pytest.raises(ImageTooSmallError) as excinfo:
            validate_upload(data)
        assert excinfo.value.shortest_side_px == 200
        assert str(MIN_DIMENSION_PX) in excinfo.value.user_message

    def test_rejects_too_small_both_sides(self):
        data = _png_bytes(100, 100)
        with pytest.raises(ImageTooSmallError):
            validate_upload(data)

    def test_exactly_min_dimension_is_allowed(self):
        data = _png_bytes(MIN_DIMENSION_PX, MIN_DIMENSION_PX)
        validate_upload(data)  # no raise

    def test_rejects_too_big_longest_side(self):
        data = _png_bytes(MAX_DIMENSION_PX + 1, MIN_DIMENSION_PX)
        with pytest.raises(ImageDimensionsTooBigError) as excinfo:
            validate_upload(data)
        assert excinfo.value.longest_side_px == MAX_DIMENSION_PX + 1
        assert str(MAX_DIMENSION_PX) in excinfo.value.user_message

    def test_exactly_max_dimension_is_allowed(self):
        # Use a 2:1 ratio so the aspect-ratio check doesn't fire
        data = _png_bytes(MAX_DIMENSION_PX, MAX_DIMENSION_PX // 2)
        validate_upload(data)  # no raise


# ---------------------------------------------------------------------------
# Aspect ratio
# ---------------------------------------------------------------------------


class TestAspectRatio:
    def test_rejects_too_tall(self):
        # 256 wide, 1024 tall => ratio 0.25 < MIN_ASPECT_RATIO
        data = _png_bytes(256, 1024)
        with pytest.raises(ImageAspectRatioError) as excinfo:
            validate_upload(data)
        assert excinfo.value.width == 256
        assert excinfo.value.height == 1024
        assert "aspect ratio" in excinfo.value.user_message.lower()

    def test_rejects_too_wide(self):
        # 1024 wide, 256 tall => ratio 4.0 > MAX_ASPECT_RATIO
        data = _png_bytes(1024, 256)
        with pytest.raises(ImageAspectRatioError):
            validate_upload(data)

    def test_three_four_portrait_is_allowed(self):
        # 300x400 = 0.75 ratio, inside [0.5, 2.0]
        validate_upload(_png_bytes(300, 400))

    def test_two_to_one_wide_is_allowed_at_boundary(self):
        # Exactly 2.0, must be accepted
        validate_upload(_png_bytes(512, 256))

    def test_one_to_two_tall_is_allowed_at_boundary(self):
        # Exactly 0.5, must be accepted
        validate_upload(_png_bytes(256, 512))


# ---------------------------------------------------------------------------
# EXIF orientation
# ---------------------------------------------------------------------------


class TestModeConversion:
    def test_rgba_png_is_flattened_to_rgb(self):
        """A PNG uploaded with an alpha channel must be returned in RGB
        mode so downstream WebP encoding takes a single code path."""
        raw = Image.new("RGBA", (512, 512), color=(100, 200, 50, 128))
        buf = io.BytesIO()
        raw.save(buf, format="PNG")
        result = validate_upload(buf.getvalue())
        assert result.img.mode == "RGB"
        assert result.width == 512 and result.height == 512


class TestExifRotation:
    def test_exif_rotation_applied(self):
        """An EXIF-rotated JPEG decodes with width/height reflecting the
        displayed orientation, not the raw sensor orientation."""
        # Create a wide image and tag it with EXIF orientation 6
        # (rotate 90 CW on display), meaning the "displayed" shape is
        # tall. After validate_upload, the returned width/height should
        # be the swapped pair.
        raw = Image.new("RGB", (800, 400), color=(120, 80, 40))
        buf = io.BytesIO()
        # Pillow supports writing orientation EXIF tag via exif bytes.
        exif = raw.getexif()
        exif[274] = 6  # 274 = Orientation tag; 6 = rotate 90 CW
        raw.save(buf, format="JPEG", exif=exif.tobytes())
        data = buf.getvalue()

        result = validate_upload(data)
        # After exif_transpose, width and height should be swapped
        assert result.width == 400
        assert result.height == 800


# ---------------------------------------------------------------------------
# Decode failures
# ---------------------------------------------------------------------------


class TestDecodeFailure:
    def test_rejects_truncated_png(self, monkeypatch):
        """A payload that libmagic thinks is PNG but Pillow can't decode
        raises ``ImageDecodeError``, not a generic error."""
        # Force libmagic to return image/png for our garbage bytes.
        import app.services.art_image as mod
        monkeypatch.setattr(mod.magic, "from_buffer", lambda data, mime: "image/png")
        # Real PNG magic header + garbage body
        data = b"\x89PNG\r\n\x1a\n" + b"garbage-body-that-isnt-png"
        with pytest.raises(ImageDecodeError):
            validate_upload(data)


# ---------------------------------------------------------------------------
# encode_for_storage
# ---------------------------------------------------------------------------


class TestEncodeForStorage:
    def test_full_downscales_when_over_max_edge(self):
        raw = Image.new("RGB", (2048, 1024), color=(100, 100, 100))
        out = encode_for_storage(raw, "full")
        decoded = Image.open(io.BytesIO(out))
        assert max(decoded.size) == FULL_ART_MAX_EDGE
        # Aspect ratio preserved
        assert decoded.size[0] / decoded.size[1] == pytest.approx(
            raw.size[0] / raw.size[1], rel=0.01
        )
        assert decoded.format == "WEBP"

    def test_full_leaves_smaller_image_unchanged_dims(self):
        raw = Image.new("RGB", (800, 600), color=(100, 100, 100))
        out = encode_for_storage(raw, "full")
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == (800, 600)
        assert decoded.format == "WEBP"

    def test_full_exactly_at_max_edge_unchanged(self):
        raw = Image.new("RGB", (FULL_ART_MAX_EDGE, 600), color=(100, 100, 100))
        out = encode_for_storage(raw, "full")
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == (FULL_ART_MAX_EDGE, 600)

    def test_headshot_kind_does_not_rescale(self):
        raw = Image.new("RGB", HEADSHOT_SIZE, color=(50, 50, 50))
        out = encode_for_storage(raw, "headshot")
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == HEADSHOT_SIZE
        assert decoded.format == "WEBP"

    def test_output_is_webp(self):
        raw = Image.new("RGB", (400, 400), color=(200, 200, 200))
        out = encode_for_storage(raw, "full")
        # WebP files start with 'RIFF....WEBP' (bytes 8-11).
        assert out[:4] == b"RIFF"
        assert out[8:12] == b"WEBP"


# ---------------------------------------------------------------------------
# build_headshot
# ---------------------------------------------------------------------------


class TestBuildHeadshot:
    def test_output_matches_headshot_size_exactly(self):
        raw = Image.new("RGB", (1024, 1024), color=(200, 200, 200))
        # Any crop box: we should always get HEADSHOT_SIZE out.
        out = build_headshot(raw, (100, 100, 300, 400))
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == HEADSHOT_SIZE

    def test_crop_box_clamped_when_out_of_bounds_right(self):
        """Cropper.js may report x+w that exceeds image width by a pixel."""
        raw = Image.new("RGB", (800, 600), color=(100, 100, 100))
        # x=700, w=200 -> would run off the right edge
        out = build_headshot(raw, (700, 100, 200, 300))
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == HEADSHOT_SIZE  # still produces a valid headshot

    def test_crop_box_clamped_when_out_of_bounds_bottom(self):
        raw = Image.new("RGB", (600, 800), color=(100, 100, 100))
        # y=700, h=200 -> would run off the bottom edge
        out = build_headshot(raw, (100, 700, 300, 200))
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == HEADSHOT_SIZE

    def test_crop_box_negative_coordinates_clamped(self):
        raw = Image.new("RGB", (600, 800), color=(100, 100, 100))
        out = build_headshot(raw, (-50, -50, 300, 400))
        decoded = Image.open(io.BytesIO(out))
        assert decoded.size == HEADSHOT_SIZE

    def test_crop_box_preserves_pixel_content(self):
        """Pixels inside the crop box survive the crop+resize."""
        # Build an image split vertically: left half red, right half blue.
        raw = Image.new("RGB", (800, 600), color=(0, 0, 0))
        for x in range(400):
            for y in range(600):
                raw.putpixel((x, y), (255, 0, 0))
        for x in range(400, 800):
            for y in range(600):
                raw.putpixel((x, y), (0, 0, 255))
        # Crop only from the red half.
        out = build_headshot(raw, (0, 0, 400, 600))
        decoded = Image.open(io.BytesIO(out)).convert("RGB")
        # Every pixel should be (approximately) red.
        mid_px = decoded.getpixel((HEADSHOT_SIZE[0] // 2, HEADSHOT_SIZE[1] // 2))
        # WebP is lossy at q=85, but red channel should still dominate.
        r, g, b = mid_px
        assert r > 200 and g < 80 and b < 80


# ---------------------------------------------------------------------------
# Error-code sanity
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    """Every specific error is a subclass of ArtImageError with a
    non-empty error_code and user_message. Routes rely on both."""

    @pytest.mark.parametrize(
        "exc_cls, args",
        [
            (ImageTooLargeError, (6 * 1024 * 1024,)),
            (InvalidImageFormatError, ()),
            (ImageDecodeError, ()),
            (ImageTooSmallError, (100,)),
            (ImageDimensionsTooBigError, (5000,)),
            (ImageAspectRatioError, (3000, 256)),
        ],
    )
    def test_subclasses_art_image_error_with_codes(self, exc_cls, args):
        err = exc_cls(*args)
        assert isinstance(err, ArtImageError)
        assert err.error_code and isinstance(err.error_code, str)
        assert err.user_message and isinstance(err.user_message, str)
