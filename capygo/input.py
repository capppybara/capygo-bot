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


def drag_screen(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    steps: int = 25,
    duration: float = 0.6,
    hold_before: float = 0.15,
    hold_after: float = 0.1,
) -> None:
    """Left-button drag from (x0, y0) to (x1, y1) in screen points.

    Moves in small steps so the game reads it as a swipe (a single jump is
    treated as a teleport and won't scroll a list). Press, brief pause, glide,
    pause, release.
    """
    def move(kind, x, y):
        _post(Quartz.CGEventCreateMouseEvent(None, kind, (float(x), float(y)),
                                             Quartz.kCGMouseButtonLeft))

    move(Quartz.kCGEventMouseMoved, x0, y0)
    move(Quartz.kCGEventLeftMouseDown, x0, y0)
    time.sleep(hold_before)
    for i in range(1, steps + 1):
        t = i / steps
        move(Quartz.kCGEventLeftMouseDragged, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        time.sleep(duration / steps)
    time.sleep(hold_after)
    move(Quartz.kCGEventLeftMouseUp, x1, y1)


def read_clipboard() -> str:
    """Return the current clipboard text ("" if empty / non-text)."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    return NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString) or ""


def write_clipboard(text: str) -> None:
    """Replace the clipboard contents with `text` (used to seed a sentinel before
    clicking an in-game "copy" button, so a stale value can't be mistaken for a
    fresh copy)."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


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
