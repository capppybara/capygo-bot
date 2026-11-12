"""Daily: sale-gift.

From the home screen, open Sale Gift on the left bar (below Privilege Card), claim
the 2 Free gifts on each page of its popup (user), and close it. It runs after
every other Auto Daily chore, in its own group (user, 2026-11-11).

Finding the button: the left bar's buttons move from time to time (user), so the
labels are read and the icon just above "Sale Gift" is tapped. The bar scrolls a
little (2026-11-11: five buttons, the last "Super Value Gift"); if the label isn't
in view, the bar is dragged each way and read again. No Sale Gift at all (the sale
ended) is a skip.

The popup: pages of gift packs. The number of pages changes (user); on 2026-11-11
there were 4 ("Mythic Treasure Key Special Gift Pack", "Key Special Offer", "Pet
Special Offer", "Guru Key Special"). Each page is a chain of tiers: 2 Free ones,
then priced ones (2000 jade, ...), with more Free ones further down that stay
locked behind a priced one. A locked Free has a lock icon that pushes "Free" right
of the button's middle. Only a button that reads "Free" and isn't locked is tapped,
so a priced one never is. A claim shows a Rewards popup, closed with a tap; the
button then reads "Obtained".

The list isn't at a fixed scroll: reopened, each page scrolls itself to its
current tier (2026-11-11: Obtained at the top, then the 2000-jade tier, then a
locked Free). So the Free buttons are found by reading the whole list, every
time. A page with nothing left to claim (user: it happens) is passed over.

Pages: the right arrow on the panel's right edge goes to the next page, until a
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
from .daily import DailyTask, _crop, find_sprite, go_home, tap_to_close_up

BAR = RelRect(0.0, 0.20, 0.25, 0.42)       # the left bar's labels
ICON_ABOVE = 0.03                          # the icon sits this far above its label
BAR_LOW, BAR_HIGH = Rel(0.157, 0.52), Rel(0.157, 0.32)  # drag points to scroll it

TIERS = RelRect(0.30, 0.32, 0.40, 0.55)     # the tier list: timer to page dots
GIFT_X = 0.498                              # a tier's button, mid-panel
LOCKED_X = 0.515     # "Free" reads at x 0.498; with the lock icon, at 0.530
CLOSE_BAND = RelRect(0.35, 0.90, 0.30, 0.10)  # the popup's X
REWARDS = RelRect(0.30, 0.345, 0.40, 0.06)  # the Rewards popup's banner
CLOSE_REWARDS = Rel(0.5, 0.30)             # any tap closes it; this spot is harmless
PAGE_TITLE = RelRect(0.20, 0.21, 0.60, 0.06)
RIGHT_ARROW, RIGHT_BOX = Rel(0.868, 0.536), RelRect(0.854, 0.524, 0.037, 0.029)
LEFT_ARROW, LEFT_BOX = Rel(0.128, 0.536), RelRect(0.109, 0.524, 0.037, 0.029)
ARROW_BRIGHT = 150   # the cream arrow's median darkest channel: ~204; no arrow: < 20

MAX_PAGES = 20       # a guard against a loop, not the expected count
MAX_TAPS = 4         # Free taps per page (2 gifts; room for a missed tap)
MAX_MISSES = 2       # Free taps with no Rewards popup before moving on
POPUP_TIMEOUT = 4.0
PAGE_TIMEOUT = 3.0
OPEN_TIMEOUT = 3.0


def sale_gift_label(frame) -> Rel | None:
    """Where the left bar's "Sale Gift" label is, or None if it isn't in view."""
    h, w = frame.shape[:2]
    x0, y0, _, _ = BAR.to_pixels(w, h)
    for t, cx, cy in ocr_lines(_crop(frame, BAR)):
        if "sale gift" in t.lower():
            return Rel((x0 + cx) / w, (y0 + cy) / h)
    return None


def free_buttons(frame) -> list[tuple[float, bool]]:
    """Every "Free" button in view, top to bottom, as (y, locked)."""
    h, w = frame.shape[:2]
    x0, y0, _, _ = TIERS.to_pixels(w, h)
    return sorted((round((y0 + cy) / h, 3), (x0 + cx) / w > LOCKED_X)
                  for t, cx, cy in ocr_lines(_crop(frame, TIERS))
                  if t.strip().lower() == "free")


def tiers_text(frame) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, TIERS))).lower()


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
        """The popup: its X at the bottom, and Free / Obtained tiers."""
        frame = ctx.frame()
        text = tiers_text(frame)
        return (find_sprite(ctx, frame, "close_x.png", CLOSE_BAND) is not None
                and ("free" in text or "obtained" in text))

    def _wait_open(self, ctx: Context) -> bool:
        """The popup is up within OPEN_TIMEOUT (so a slow one isn't tapped again)."""
        end = time.time() + OPEN_TIMEOUT
        while not self._is_open(ctx):
            if time.time() > end or self.wait(ctx, 0.5):
                return False
        return True

    def _free_now(self, ctx: Context) -> list[float]:
        """The unlocked Free buttons' heights, read twice to be sure the list has
        stopped scrolling (it scrolls itself to the current tier)."""
        last = None
        for _ in range(4):
            found = free_buttons(ctx.frame())
            if found == last:
                break
            last = found
            if self.wait(ctx, 0.5):
                return []
        return [y for y, locked in last if not locked]

    # --- claim ------------------------------------------------------------
    def _close_rewards(self, ctx: Context) -> bool | None:
        """After a Free tap: close the Rewards popup once it shows. True if it
        showed (the claim landed), False if it didn't, None on a stop."""
        end = time.time() + POPUP_TIMEOUT
        while not rewards_up(ctx.frame()):
            if time.time() > end:
                return False
            if self.wait(ctx, 0.5):
                return None
        if not self.tap(ctx, CLOSE_REWARDS, "close the Rewards popup"):
            return None
        end = time.time() + POPUP_TIMEOUT
        while rewards_up(ctx.frame()) and time.time() < end:
            if self.wait(ctx, 0.5):
                return None
        return True

    def _claim_page(self, ctx: Context, page: str) -> int | None:
        """Claim every unlocked Free on this page (the 2nd unlocks once the 1st is
        claimed). How many were claimed; None on a stop."""
        claimed = misses = 0
        for _ in range(MAX_TAPS):
            free = self._free_now(ctx)
            if ctx.should_stop():
                return None
            if not free:
                break
            if not self.tap(ctx, Rel(GIFT_X, free[0]), f"Free ({page})"):
                return None
            landed = self._close_rewards(ctx)
            if landed is None:
                return None
            if landed:
                claimed += 1
                continue
            misses += 1
            if misses >= MAX_MISSES:
                ctx.log.warning("%s: %s: no Rewards popup after %d Free taps -> next "
                                "page", self.name, page, misses)
                break
        return claimed

    def _turn(self, ctx: Context, arrow: Rel, what: str) -> bool:
        """Tap a page arrow; True once the page's title has changed."""
        before = self.text_in(ctx, PAGE_TITLE)
        if not self.tap(ctx, arrow, what):
            return False
        end = time.time() + PAGE_TIMEOUT
        while time.time() < end:
            if self.text_in(ctx, PAGE_TITLE) != before:
                return not self.wait(ctx, 0.5)  # let the list settle
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
            if ctx.dry_run or self._wait_open(ctx):
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

        claimed = pages = 0
        while True:
            pages += 1
            page = self.text_in(ctx, PAGE_TITLE) or "?"
            got = self._claim_page(ctx, page)
            if got is None:
                return False
            ctx.log.info("%s: page %d (%s): %s", self.name, pages, page,
                         f"{got} claimed" if got else "nothing to claim")
            claimed += got
            if not arrow_showing(ctx.frame(), RIGHT_BOX):
                break  # the last page
            if pages >= MAX_PAGES:
                ctx.log.warning("%s: still a next page after %d -> stopping",
                                self.name, pages)
                break
            if not self._turn(ctx, RIGHT_ARROW, "right arrow"):
                return False
        ctx.log.info("%s: %d Free gifts claimed over %d pages", self.name, claimed,
                     pages)
        return go_home(ctx)  # the X at the bottom
