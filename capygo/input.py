"""Post synthetic mouse clicks at absolute screen coordinates.

Requires Accessibility permission for the app that launches the bot. In dry-run
mode nothing is posted; the intended click is only logged by the caller.
"""

from __future__ import annotations

import random
import time

import Quartz


def _post(event) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def click_screen(x: float, y: float, jitter_px: int = 0, hold: float = 0.03) -> None:
    """Move to (x, y) in screen points and left-click, with optional jitter."""
    if jitter_px:
        x += random.uniform(-jitter_px, jitter_px)
        y += random.uniform(-jitter_px, jitter_px)
    pos = (float(x), float(y))

    move = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, pos, Quartz.kCGMouseButtonLeft
    )
    _post(move)

    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, pos, Quartz.kCGMouseButtonLeft
    )
    _post(down)
    time.sleep(hold)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, pos, Quartz.kCGMouseButtonLeft
    )
    _post(up)


def type_text(text: str, per_char_delay: float = 0.04) -> None:
    """Type `text` into the focused field (as Unicode key events)."""
    for ch in text:
        down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        _post(down)
        up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        _post(up)
        time.sleep(per_char_delay)
