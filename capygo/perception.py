"""Turn captured frames into matches.

Today: template matching (find a button/icon by its cropped reference image).
Later: OCR and color checks can be added here behind the same Match interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from .geometry import RelRect


@dataclass
class Match:
    found: bool
    score: float
    x: int  # center, in frame pixels
    y: int


@lru_cache(maxsize=64)
def load_template(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Template not found or unreadable: {path}")
    return img


def find_template(
    frame: np.ndarray,
    template: np.ndarray,
    threshold: float,
    region: RelRect | None = None,
) -> Match:
    """Best match of `template` in `frame`. If `region` is set, search only there."""
    ox, oy = 0, 0
    search = frame
    if region is not None:
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = region.to_pixels(w, h)
        search = frame[y0:y1, x0:x1]
        ox, oy = x0, y0

    if (
        search.shape[0] < template.shape[0]
        or search.shape[1] < template.shape[1]
    ):
        return Match(False, 0.0, 0, 0)

    res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    th, tw = template.shape[:2]
    cx = ox + max_loc[0] + tw // 2
    cy = oy + max_loc[1] + th // 2
    return Match(max_val >= threshold, float(max_val), cx, cy)


def read_int(bgr, upscale: int = 3):
    """OCR a small image with Apple Vision and return the last integer in it.

    Returns None if nothing numeric is read. Taking the last digit run is robust
    to a leading glyph (e.g. a lightning icon read as a stray digit).
    """
    import re

    from ocrmac import ocrmac
    from PIL import Image

    if upscale != 1:
        bgr = cv2.resize(bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    result = ocrmac.OCR(Image.fromarray(rgb), language_preference=["en-US"]).recognize()
    text = " ".join(t for t, _, _ in result)
    runs = re.findall(r"[0-9]+", text)
    return int(runs[-1]) if runs else None


def ocr_lines(bgr):
    """Return [(text, cx_px, cy_px)] for each text line Apple Vision finds.

    Coordinates are in pixels of `bgr`, top-left origin (Vision reports a
    bottom-left origin, converted here).
    """
    from ocrmac import ocrmac
    from PIL import Image

    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    result = ocrmac.OCR(Image.fromarray(rgb), language_preference=["en-US"]).recognize()
    out = []
    for text, _conf, (bx, by, bw, bh) in result:
        cx = int((bx + bw / 2) * w)
        cy = int((1 - (by + bh / 2)) * h)
        out.append((text, cx, cy))
    return out
