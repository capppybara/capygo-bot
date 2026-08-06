"""Capture the game window as an OpenCV-style BGR image.

Uses CGWindowListCreateImage at nominal resolution, so the returned image is
sized in window points (not Retina pixels). That keeps template coordinates and
window-relative math aligned across displays. `scale` is returned in case a
display reports a non-1:1 ratio; clicks divide by it to get back to points.
"""

from __future__ import annotations

import numpy as np
import Quartz

from .window import GameWindow


class CaptureError(Exception):
    pass


def _cgimage_to_bgr(image) -> np.ndarray:
    width = Quartz.CGImageGetWidth(image)
    height = Quartz.CGImageGetHeight(image)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(image)
    provider = Quartz.CGImageGetDataProvider(image)
    data = Quartz.CGDataProviderCopyData(provider)

    buf = np.frombuffer(data, dtype=np.uint8)
    # Rows may be padded, so reshape using the real stride then trim to width.
    arr = buf.reshape((height, bytes_per_row // 4, 4))[:, :width, :]
    # macOS little-endian ARGB lands in memory as B, G, R, A -> take BGR.
    return np.ascontiguousarray(arr[:, :, :3])


def capture_window(window: GameWindow) -> tuple[np.ndarray, float]:
    """Return (bgr_image, scale). scale = image_width / window_width_in_points."""
    wid = window.window_id()
    bounds = window.bounds()

    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        wid,
        Quartz.kCGWindowImageBoundsIgnoreFraming
        | Quartz.kCGWindowImageNominalResolution,
    )
    if image is None:
        raise CaptureError(
            "CGWindowListCreateImage returned None. Grant Screen Recording "
            "permission to your terminal (System Settings > Privacy & Security "
            "> Screen Recording), then restart it."
        )

    bgr = _cgimage_to_bgr(image)
    scale = bgr.shape[1] / bounds.width if bounds.width else 1.0
    return bgr, scale
