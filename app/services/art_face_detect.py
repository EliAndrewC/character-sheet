"""Face detection for seeding the Cropper.js default bbox.

Uses OpenCV Haar cascades locally. ``cv2`` is imported lazily so the
cold start of unrelated routes isn't hit by a 35 MB import.

``detect_face`` returns a bbox that matches the target aspect ratio
(3:4 portrait by default). If no face is found, or the expanded bbox
would spill outside the image bounds, the fallback is the largest
centered rectangle matching the aspect ratio that fits in the image.
The user always has the final say in the Cropper.js UI; this seeds the
default.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from PIL import Image

from app.services.art_image import HEADSHOT_ASPECT_RATIO

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Total headshot height, expressed as a multiple of the detected face
# height. 2.2 gives enough headroom above the forehead and a little
# below the chin without introducing too much surrounding scene.
HEADSHOT_HEIGHT_VS_FACE = 2.2

# Where the face center should sit inside the headshot, measured from
# the top as a fraction of headshot height. 0.45 = slightly above the
# vertical midpoint, which keeps the forehead in the frame.
FACE_VERTICAL_CENTER_IN_HEADSHOT = 0.45

# Haar cascade tuning. Accepted as-is from the OpenCV docs; tightening
# ``minNeighbors`` suppresses spurious detections at the cost of some
# recall, which is the right trade-off for "seed the default".
CASCADE_SCALE_FACTOR = 1.1
CASCADE_MIN_NEIGHBORS = 5

# Relative minimum face size (as a fraction of the shorter image edge).
# Below this, the detection is probably noise. The plan accepts less
# recall here because the fallback is safe.
CASCADE_MIN_FACE_EDGE_FRACTION = 0.05


# ---------------------------------------------------------------------------
# Lazy cascade loading
# ---------------------------------------------------------------------------

_cascade = None


def _get_cascade():
    """Load and cache the frontal-face Haar cascade."""
    global _cascade
    if _cascade is None:
        import cv2
        path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        _cascade = cv2.CascadeClassifier(path)
    return _cascade


# ---------------------------------------------------------------------------
# Cascade invocation
# ---------------------------------------------------------------------------


def _run_cascade(img: Image.Image) -> List[Tuple[int, int, int, int]]:
    """Run the frontal-face Haar cascade on a PIL image.

    Returns a list of ``(x, y, w, h)`` tuples. Empty list means no
    faces were detected with sufficient confidence.
    """
    import cv2
    import numpy as np

    gray = np.array(img.convert("L"))
    cascade = _get_cascade()
    shortest_edge = min(img.size)
    min_face = max(1, int(shortest_edge * CASCADE_MIN_FACE_EDGE_FRACTION))
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=CASCADE_SCALE_FACTOR,
        minNeighbors=CASCADE_MIN_NEIGHBORS,
        minSize=(min_face, min_face),
    )
    # detectMultiScale returns np.ndarray of int32; normalise to python ints.
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _expand_to_aspect_ratio(
    face_bbox: Tuple[int, int, int, int],
    image_size: Tuple[int, int],
    aspect_ratio: float,
) -> Optional[Tuple[int, int, int, int]]:
    """Expand a face bbox to the target aspect ratio, biased upward.

    Returns the expanded ``(x, y, w, h)`` or ``None`` if the expanded
    bbox would spill outside the image. In the ``None`` case the caller
    falls back to the largest centered rectangle.

    ``aspect_ratio`` is ``width / height``. For 3:4 portrait, pass 0.75.
    """
    fx, fy, fw, fh = face_bbox
    img_w, img_h = image_size

    face_cx = fx + fw / 2
    face_cy = fy + fh / 2

    target_h = fh * HEADSHOT_HEIGHT_VS_FACE
    target_w = target_h * aspect_ratio

    top = face_cy - FACE_VERTICAL_CENTER_IN_HEADSHOT * target_h
    left = face_cx - target_w / 2

    # Check bounds: if the expanded bbox would spill, bail.
    if (
        left < 0
        or top < 0
        or left + target_w > img_w
        or top + target_h > img_h
    ):
        return None

    return (
        int(round(left)),
        int(round(top)),
        int(round(target_w)),
        int(round(target_h)),
    )


def _fallback_bbox(
    image_size: Tuple[int, int],
    aspect_ratio: float,
) -> Tuple[int, int, int, int]:
    """Return the largest centered rectangle matching ``aspect_ratio``
    that fits inside ``image_size``."""
    img_w, img_h = image_size

    # We want max (w, h) such that w/h == aspect_ratio, w <= img_w, h <= img_h.
    # Try width-limited first.
    w_wide = img_w
    h_wide = w_wide / aspect_ratio
    if h_wide <= img_h:
        w = int(w_wide)
        h = int(round(h_wide))
    else:
        h = img_h
        w = int(round(h * aspect_ratio))

    x = (img_w - w) // 2
    y = (img_h - h) // 2
    return (x, y, w, h)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_face(
    img: Image.Image,
    aspect_ratio: float = HEADSHOT_ASPECT_RATIO,
) -> Tuple[int, int, int, int]:
    """Return a suggested headshot bbox for ``img``.

    Pipeline:
      1. Run the Haar cascade.
      2. Pick the largest detection (a proxy for "most confident").
      3. Expand it to the target aspect ratio with an upward bias.
      4. If the expansion won't fit, fall back to the largest centered
         rectangle matching the aspect ratio.

    The returned bbox is ``(x, y, w, h)`` in pixel coordinates.
    """
    faces = _run_cascade(img)
    if not faces:
        log.debug("No face detected; using fallback bbox")
        return _fallback_bbox(img.size, aspect_ratio)

    best_face = max(faces, key=lambda f: f[2] * f[3])
    expanded = _expand_to_aspect_ratio(best_face, img.size, aspect_ratio)
    if expanded is None:
        log.debug("Expanded bbox wouldn't fit; using fallback")
        return _fallback_bbox(img.size, aspect_ratio)
    return expanded
