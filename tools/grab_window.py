#!/usr/bin/env python3
"""Capture the game window to a PNG.

Use it to (a) confirm capture + permissions work, and (b) get an image to crop
button templates from in Preview.

  python tools/grab_window.py                 -> logs/window.png
  python tools/grab_window.py shot.png        -> custom path

Requires Screen Recording permission for your terminal.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402

from capygo.capture import capture_window  # noqa: E402
from capygo.controller import ROOT, load_config  # noqa: E402
from capygo.window import GameWindow  # noqa: E402


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "logs", "window.png")
    config = load_config()
    window = GameWindow(
        owner=config["window"]["owner"],
        title_contains=config["window"].get("title_contains", ""),
    )
    bounds = window.bounds()
    print(f"window bounds: x={bounds.x:.0f} y={bounds.y:.0f} "
          f"{bounds.width:.0f}x{bounds.height:.0f}")

    frame, scale = capture_window(window)
    cv2.imwrite(out, frame)
    print(f"saved {frame.shape[1]}x{frame.shape[0]} image (scale={scale:.2f}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
