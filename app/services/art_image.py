"""Character art: validation, re-encoding, and headshot cropping.

Given raw uploaded bytes, ``validate_upload`` decodes the image, enforces
size/aspect-ratio constraints, and returns a Pillow image normalised for
EXIF orientation. ``encode_for_storage`` re-encodes to WebP for S3.
``build_headshot`` produces the cropped thumbnail that the list page
displays at a fixed 3:4 portrait size.

The same validator is reused for Gemini-generated art so generated
images must pass the same ratio/size checks as user uploads.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal, Tuple

import magic
from PIL import Image, ImageOps, UnidentifiedImageError


# ---------------------------------------------------------------------------
# Constants (design doc "Image constraints")
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_DIMENSION_PX = 256              # shortest side
MAX_DIMENSION_PX = 4096             # longest side
MIN_ASPECT_RATIO = 0.5              # 1:2 tall
MAX_ASPECT_RATIO = 2.0              # 2:1 wide

# Headshot: 3:4 portrait. Matches where a face sits in a photo.
HEADSHOT_SIZE: Tuple[int, int] = (180, 240)
HEADSHOT_ASPECT_RATIO = 3 / 4       # width / height

# Full art is downscaled so the longest edge is this many pixels before
# upload. Keeps bandwidth reasonable.
FULL_ART_MAX_EDGE = 1024

# Mapping from libmagic MIME string -> Pillow format string.
_ACCEPTED_MIME_TO_FORMAT = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ArtImageError(Exception):
    """Base class for validation/encode failures.

    Subclasses set ``error_code`` and ``user_message`` so routes can turn
    them into HTTP responses without duplicating copy.
    """

    error_code: str = "art_image_error"
    user_message: str = "We could not process this image."


class ImageTooLargeError(ArtImageError):
    error_code = "image_too_large"

    def __init__(self, size_bytes: int):
        self.size_bytes = size_bytes
        mb = size_bytes / (1024 * 1024)
        self.user_message = (
            f"This image is {mb:.1f} MB. The upload limit is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
        super().__init__(self.user_message)


class InvalidImageFormatError(ArtImageError):
    error_code = "invalid_image_format"
    user_message = "Only PNG, JPG, and WEBP images are supported."


class ImageDecodeError(ArtImageError):
    error_code = "image_decode_error"
    user_message = "We could not decode this image. It may be corrupted."


class ImageTooSmallError(ArtImageError):
    error_code = "image_too_small"

    def __init__(self, shortest_side_px: int):
        self.shortest_side_px = shortest_side_px
        self.user_message = (
            f"This image is too small. Its shortest side is "
            f"{shortest_side_px} px; the minimum is {MIN_DIMENSION_PX} px."
        )
        super().__init__(self.user_message)


class ImageDimensionsTooBigError(ArtImageError):
    error_code = "image_dimensions_too_big"

    def __init__(self, longest_side_px: int):
        self.longest_side_px = longest_side_px
        self.user_message = (
            f"This image is too large in pixels. Its longest side is "
            f"{longest_side_px} px; the maximum is {MAX_DIMENSION_PX} px."
        )
        super().__init__(self.user_message)


class ImageAspectRatioError(ArtImageError):
    error_code = "image_aspect_ratio"

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        ratio = width / height
        self.user_message = (
            f"This image's aspect ratio is {ratio:.2f}. Only images "
            f"between {MIN_ASPECT_RATIO:.2f} (tall) and "
            f"{MAX_ASPECT_RATIO:.2f} (wide) are supported. Try cropping "
            "your image closer to a square before uploading."
        )
        super().__init__(self.user_message)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ValidatedImage:
    """Return value of ``validate_upload``.

    ``img`` is always in RGB mode so downstream encoders can emit WebP
    without worrying about palette/alpha nuances. Call ``img.close()``
    when done to free Pillow's internal buffer.
    """

    img: Image.Image
    format: str     # "PNG" / "JPEG" / "WEBP"
    width: int
    height: int


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_upload(data: bytes) -> ValidatedImage:
    """Validate and decode an uploaded image.

    Enforces (in order): size cap, libmagic format check, Pillow decode,
    pixel dimensions, aspect ratio. Returns a ``ValidatedImage`` with the
    Pillow image EXIF-normalised and converted to RGB.

    Raises the most specific ``ArtImageError`` subclass on failure.

    ``content_type`` from the HTTP layer is NOT trusted - we detect
    format from the bytes themselves. That matches the importer's
    approach and defeats spoofed extensions.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageTooLargeError(len(data))

    mime = magic.from_buffer(data, mime=True)
    pil_format = _ACCEPTED_MIME_TO_FORMAT.get(mime)
    if pil_format is None:
        raise InvalidImageFormatError()

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError() from exc

    # Normalise EXIF orientation first so width/height reflect what the
    # user sees, not the raw sensor orientation.
    img = ImageOps.exif_transpose(img)
    # Flatten to RGB. WebP encoders accept RGBA too, but keeping one
    # mode throughout means the downstream code paths are the same.
    if img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    shortest = min(width, height)
    longest = max(width, height)

    if shortest < MIN_DIMENSION_PX:
        raise ImageTooSmallError(shortest)
    if longest > MAX_DIMENSION_PX:
        raise ImageDimensionsTooBigError(longest)

    ratio = width / height
    if ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
        raise ImageAspectRatioError(width, height)

    return ValidatedImage(img=img, format=pil_format, width=width, height=height)


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def encode_for_storage(img: Image.Image, kind: Literal["full", "headshot"]) -> bytes:
    """Re-encode an image to WebP for S3 storage.

    ``kind="full"`` downscales so the longest edge is
    ``FULL_ART_MAX_EDGE`` (no-op if already smaller). ``kind="headshot"``
    assumes the image is already at ``HEADSHOT_SIZE`` - caller is
    expected to have run ``build_headshot`` first.

    Always emits WebP quality=85. Strips EXIF (Pillow does this by
    default when the source image has been through ``exif_transpose``).
    """
    if kind == "full":
        longest = max(img.size)
        if longest > FULL_ART_MAX_EDGE:
            # thumbnail() preserves aspect ratio while fitting within the box
            scaled = img.copy()
            scaled.thumbnail(
                (FULL_ART_MAX_EDGE, FULL_ART_MAX_EDGE),
                Image.Resampling.LANCZOS,
            )
        else:
            scaled = img
    elif kind == "headshot":
        scaled = img
    else:  # pragma: no cover - type checker catches this already
        raise ValueError(f"Unknown kind: {kind!r}")

    buf = io.BytesIO()
    scaled.save(buf, format="WEBP", quality=85, method=6)
    return buf.getvalue()


def build_headshot(
    img: Image.Image,
    crop_box: Tuple[int, int, int, int],
) -> bytes:
    """Crop ``img`` to ``crop_box`` and return WebP bytes at ``HEADSHOT_SIZE``.

    ``crop_box`` is ``(x, y, w, h)`` in pixels, matching the coordinate
    space the Cropper.js UI reports. The function clamps the box to the
    image bounds so a slightly-off drag from the UI doesn't raise.
    """
    width, height = img.size
    x, y, w, h = crop_box
    # Clamp to image bounds so a ~1 px rounding error from Cropper.js
    # doesn't blow up the whole save flow.
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))

    cropped = img.crop((x, y, x + w, y + h))
    resized = cropped.resize(HEADSHOT_SIZE, Image.Resampling.LANCZOS)
    return encode_for_storage(resized, "headshot")
