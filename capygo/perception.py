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
