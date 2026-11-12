"""Helpers for the chores behind the home screen's left bar (Sale Gift, Super Value
Gift): finding a button by its label, and closing the Rewards popup a claim shows.

The left bar's buttons move from time to time (user), so a button is found by its
label and the icon just above it is tapped. The bar holds more than it shows
(2026-11-11: Privilege Card, Growth Fund, 7 Days, Sale Gift, Super Value Gift) and
scrolls a little: at the top, the last label is cut off by the bar's bottom edge
("Super" at y 0.56, "Value Gift" hidden). A label not in view, or below
BAR_BOTTOM, gets the bar dragged and read again. The first drag can just bring the
game window forward without scrolling (2026-11-11), so each direction is dragged
twice.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import _crop, tap, tap_to_close_up, wait

LEFT_BAR = RelRect(0.0, 0.20, 0.25, 0.42)   # the bar's labels
BAR_BOTTOM = 0.55     # a label lower than this is cut off (top state: "Super" 0.56)
ICON_ABOVE = 0.03     # a button's icon sits this far above its label
SHOW_LOWER = (Rel(0.157, 0.52), Rel(0.157, 0.32))  # finger up: lower buttons show
SHOW_UPPER = (Rel(0.157, 0.32), Rel(0.157, 0.52))
DRAGS = (None, SHOW_LOWER, SHOW_LOWER, SHOW_UPPER, SHOW_UPPER)

REWARDS = RelRect(0.30, 0.345, 0.40, 0.06)  # a Rewards popup's banner (y 0.374)
POPUP_TIMEOUT = 4.0


def bar_labels(frame) -> list[tuple[str, float, float]]:
    """The left bar's label lines: (lower-case text, x, y), window-relative."""
    h, w = frame.shape[:2]
    x0, y0, _, _ = LEFT_BAR.to_pixels(w, h)
    return [(t.lower(), (x0 + cx) / w, (y0 + cy) / h)
            for t, cx, cy in ocr_lines(_crop(frame, LEFT_BAR))]


def left_bar_button(ctx: Context, words: str, who: str, fallback: Rel) -> Rel | None:
    """Where to tap the left-bar button whose label contains `words` (lower case),
    scrolling the bar if it's out of view or cut off. None if it isn't on the bar
    (or a stop). `fallback` on a dry run (no screen reads)."""
    if ctx.dry_run:
        return fallback
    cut_off = None
    for drag in DRAGS:
        if drag:
            ctx.log.info("%s: %s -> scroll the left bar", who,
                         "its label is cut off" if cut_off else "no label in view")
            ctx.drag_rel(*drag)
            if wait(ctx, 1.0):
                return None
        hit = next(((x, y) for t, x, y in bar_labels(ctx.frame()) if words in t), None)
        if hit and hit[1] <= BAR_BOTTOM:
            return Rel(hit[0], hit[1] - ICON_ABOVE)
        cut_off = hit or cut_off
    if cut_off:  # never fully in view: its icon still shows above the label
        return Rel(cut_off[0], cut_off[1] - ICON_ABOVE)
    return None


def rewards_up(frame) -> bool:
    """A "Rewards ... Tap to close" popup is showing."""
    text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, REWARDS))).lower()
    return "rewards" in text or tap_to_close_up(frame)


def close_rewards(ctx: Context, who: str, spot: Rel) -> bool | None:
    """After a claim tap: wait for the Rewards popup and close it with a tap at
    `spot`. True if it showed (the claim landed), False if it didn't, None on a
    stop."""
    end = time.time() + POPUP_TIMEOUT
    while not rewards_up(ctx.frame()):
        if time.time() > end:
            return False
        if wait(ctx, 0.5):
            return None
    ctx.log.info("%s: tap close the Rewards popup", who)
    if not tap(ctx, spot):
        return None
    end = time.time() + POPUP_TIMEOUT
    while rewards_up(ctx.frame()) and time.time() < end:
        if wait(ctx, 0.5):
            return None
    return True
