"""Daily: sale-gift.

From the home screen, open Sale Gift on the left bar (below Privilege Card), claim
the 2 Free gifts on each page of its popup (user), and close it.

Finding the button: the left bar's buttons move from time to time (user), so the
labels are read and the icon just above "Sale Gift" is tapped. The bar scrolls a
little (2026-11-11: five buttons, the last "Super Value Gift"); if the label isn't
in view, the bar is dragged each way and read again. No Sale Gift at all (the sale
ended) is a skip.

The popup (2026-11-11): 4 pages of gift packs ("Mythic Treasure Key Special Gift
Pack", "Key Special Offer", "Pet Special Offer", "Guru Key Special"), each a chain
of tiers: 2 Free ones, then priced ones (2000 jade, ...). The second Free is locked
until the first is claimed; its lock icon pushes "Free" right of the button's
middle. Only a button that reads "Free" and isn't locked is tapped, so a priced one
never is. A claim shows a Rewards popup, closed with a tap; the button then reads
"Obtained".

Pages: the right arrow on the panel's right edge goes to the next page; the last
page has none (that spot is dark). The popup opened on page 1; if it opens on a
later one, the left arrow goes back first. go_home closes it with the X at the
bottom.
"""

from __future__ import annotations

import time

import numpy as np

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import DailyTask, _crop, go_home, tap_to_close_up

BAR = RelRect(0.0, 0.20, 0.25, 0.42)       # the left bar's labels
ICON_ABOVE = 0.03                          # the icon sits this far above its label
BAR_LOW, BAR_HIGH = Rel(0.157, 0.52), Rel(0.157, 0.32)  # drag points to scroll it

GIFT_Y = (0.444, 0.624)                    # the two Free buttons (tiers 1 and 2)
GIFT_X = 0.498
LOCKED_X = 0.515     # "Free" reads at x 0.498; with the lock icon, at 0.531
REWARDS = RelRect(0.30, 0.345, 0.40, 0.06)  # the Rewards popup's banner
CLOSE_REWARDS = Rel(0.5, 0.30)             # any tap closes it; this spot is harmless
PAGE_TITLE = RelRect(0.20, 0.21, 0.60, 0.06)
RIGHT_ARROW, RIGHT_BOX = Rel(0.868, 0.536), RelRect(0.854, 0.524, 0.037, 0.029)
LEFT_ARROW, LEFT_BOX = Rel(0.128, 0.536), RelRect(0.109, 0.524, 0.037, 0.029)
ARROW_BRIGHT = 150   # the cream arrow's median darkest channel: ~204; no arrow: < 20

MAX_PAGES = 8
CLAIM_TRIES = 2
POPUP_TIMEOUT = 4.0
PAGE_TIMEOUT = 3.0


def sale_gift_label(frame) -> Rel | None:
    """Where the left bar's "Sale Gift" label is, or None if it isn't in view."""
    h, w = frame.shape[:2]
    x0, y0, _, _ = BAR.to_pixels(w, h)
    for t, cx, cy in ocr_lines(_crop(frame, BAR)):
        if "sale gift" in t.lower():
            return Rel((x0 + cx) / w, (y0 + cy) / h)
    return None


def gift_state(frame, y: float) -> str | None:
    """The gift button at height y: "free", "locked", "obtained", or None (a price,
    or nothing readable)."""
    h, w = frame.shape[:2]
    region = RelRect(0.34, y - 0.028, 0.32, 0.056)
    x0, _, _, _ = region.to_pixels(w, h)
    for t, cx, _ in ocr_lines(_crop(frame, region)):
        word = t.strip().lower()
        if word == "free":
            return "locked" if (x0 + cx) / w > LOCKED_X else "free"
        if word == "obtained":
            return "obtained"
    return None


def arrow_showing(frame, box: RelRect) -> bool:
    """A page arrow is drawn in `box` (cream); without one the spot is dark."""
    return float(np.median(_crop(frame, box).min(axis=2))) > ARROW_BRIGHT


def rewards_up(frame) -> bool:
    text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, REWARDS))).lower()
    return "rewards" in text or tap_to_close_up(frame)


@register("sale-gift")
class SaleGift(DailyTask):
    TITLE = "Sale Gift"
    LABEL = "Sale gift"
    ICON = "🎁"
    DESCRIPTION = ("Open Sale Gift (left bar), claim the 2 Free gifts on each page, "
                   "and close it.")
    START_HINT = "Start on the main Adventure screen."

    # --- open -------------------------------------------------------------
    def _find_button(self, ctx: Context) -> Rel | None:
        """The Sale Gift icon, wherever it is on the left bar."""
        for drag in (None, (BAR_LOW, BAR_HIGH), (BAR_HIGH, BAR_LOW)):
            if drag:
                ctx.log.info("%s: no Sale Gift label in view -> scroll the left bar",
                             self.name)
                ctx.drag_rel(*drag)
                if self.wait(ctx, 1.0):
                    return None
            label = sale_gift_label(ctx.frame())
            if label:
                return Rel(label.x, label.y - ICON_ABOVE)
        return None

    def _is_open(self, ctx: Context) -> bool:
        return gift_state(ctx.frame(), GIFT_Y[0]) is not None

    # --- claim ------------------------------------------------------------
    def _close_rewards(self, ctx: Context) -> bool:
        """After a Free tap: close the Rewards popup once it shows (if it does).
        False only on a stop."""
        end = time.time() + POPUP_TIMEOUT
        while not rewards_up(ctx.frame()):
            if time.time() > end:
                return True  # no popup: the caller reads the button again
            if self.wait(ctx, 0.5):
                return False
        if not self.tap(ctx, CLOSE_REWARDS, "close the Rewards popup"):
            return False
        end = time.time() + POPUP_TIMEOUT
        while rewards_up(ctx.frame()) and time.time() < end:
            if self.wait(ctx, 0.5):
                return False
        return True

    def _claim(self, ctx: Context, n: int, page: str) -> str | None:
        """Claim gift n (1 or 2) on this page. Its outcome for the log; None on a
        stop."""
        y = GIFT_Y[n - 1]
        state = gift_state(ctx.frame(), y)
        if state == "locked" and n > 1:  # the first was just claimed: a moment
            if self.wait(ctx, 1.0):
                return None
            state = gift_state(ctx.frame(), y)
        if state != "free":
            return {"obtained": "already obtained", "locked": "locked"}.get(
                state, "no Free button")
        for _ in range(CLAIM_TRIES):
            if not self.tap(ctx, Rel(GIFT_X, y), f"Free ({page}, gift {n})"):
                return None
            if not self._close_rewards(ctx):
                return None
            state = gift_state(ctx.frame(), y)
            if state == "obtained":
                return "claimed"
            if state != "free":
                break
        return f"not claimed (the button reads {state or 'nothing'})"

    def _turn(self, ctx: Context, arrow: Rel, what: str) -> bool:
        """Tap a page arrow; True once the page's title has changed."""
        before = self.text_in(ctx, PAGE_TITLE)
        if not self.tap(ctx, arrow, what):
            return False
        end = time.time() + PAGE_TIMEOUT
        while time.time() < end:
            if self.text_in(ctx, PAGE_TITLE) != before:
                return True
            if self.wait(ctx, 0.5):
                return False
        ctx.log.warning("%s: the page didn't change after the %s", self.name, what)
        return False

    def run_daily(self, ctx: Context) -> bool:
        button = self._find_button(ctx)
        if button is None:
            if ctx.should_stop():
                return False
            self.skip(ctx, "no Sale Gift button on the left bar")
            return go_home(ctx)
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, button, "Sale Gift"):
                return False
            if ctx.dry_run or self._is_open(ctx):
                break
        else:
            ctx.log.warning("%s: the Sale Gift popup did not open", self.name)
            return False
        if ctx.dry_run:
            ctx.log.info("%s: dry run - would claim the 2 Free gifts on each page",
                         self.name)
            return go_home(ctx)

        for _ in range(MAX_PAGES):  # back to page 1 if it opened on a later one
            if not arrow_showing(ctx.frame(), LEFT_BOX):
                break
            if not self._turn(ctx, LEFT_ARROW, "left arrow"):
                return False

        claimed = 0
        for _ in range(MAX_PAGES):
            page = self.text_in(ctx, PAGE_TITLE) or "?"
            for n in (1, 2):
                outcome = self._claim(ctx, n, page)
                if outcome is None:
                    return False
                ctx.log.info("%s: %s, gift %d: %s", self.name, page, n, outcome)
                claimed += outcome == "claimed"
            if not arrow_showing(ctx.frame(), RIGHT_BOX):
                break  # the last page
            if not self._turn(ctx, RIGHT_ARROW, "right arrow"):
                return False
        ctx.log.info("%s: %d Free gifts claimed", self.name, claimed)
        return go_home(ctx)  # the X at the bottom
