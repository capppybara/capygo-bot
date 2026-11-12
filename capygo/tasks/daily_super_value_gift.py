"""Daily: super-value-gift.

From the home screen, open Super Value Gift on the left bar (below Sale Gift), claim
the Free gift on its Daily Special tab, then on its Seven-Day Pilgrimage tab
(bottom right) scroll to the next Check in button and tap it (user). Runs in the
Last group, just before Sale gift (user, 2026-11-11).

Finding the button: by its label, scrolling the left bar (left_bar.py). It's the
bar's last button, cut off at the bottom until the bar is scrolled; its label reads
"Super" (OCR: "(Super", "Supers") over "Value Gift", so "super" is matched. None
on the bar is a skip.

The screen (2026-11-11) is full-size with a back arrow and two tabs at the bottom
right: Daily Special and Seven-Day Pilgrimage. It opened on Daily Special.
- Daily Special: a grid of packs. The Welfare Pack's button reads "Free"
  (claimed: "Already purchased"); the rest cost jade (100 / 200 / 300, a 500
  bundle). Only a button reading "Free" is tapped.
- Seven-Day Pilgrimage: Day 1-7 rows, each with a button on the right: "Already"
  (checked in), "Check in" (today's, green), "Not" (a later day, grey). The list
  scrolls; Day 4 sat at the bottom of the first view. The "Already purchased"
  button above the list is the paid tier: never tapped (the list area starts
  below it). A "Not" in view means today's check-in is done. The event ends
  (2026-11-11: "Ends in 3 days 18 hours"); no Pilgrimage tab is logged, not a
  failure.
Each claim shows a Rewards popup, closed with a tap on the top banner's middle
(clear of the Pilgrimage banner's "5000% Rebate" badge on the left). go_home leaves
with the back arrow.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import NEUTRAL, DailyTask, _crop, go_home
from .left_bar import close_rewards, left_bar_button

BUTTON_GUESS = Rel(0.157, 0.506)            # where it was, scrolled (dry runs only)
TABS = RelRect(0.55, 0.925, 0.43, 0.075)    # Daily Special / Seven-Day Pilgrimage
TAB_ABOVE = 0.02
PACKS = RelRect(0.08, 0.33, 0.84, 0.57)     # Daily Special's pack grid
DAYS = RelRect(0.60, 0.33, 0.36, 0.56)      # the Pilgrimage rows' buttons
PILGRIMAGE_HEADER = RelRect(0.55, 0.22, 0.43, 0.045)  # "Days checked in 4/7"
CLOSE_REWARDS = NEUTRAL                     # the top banner's middle
LIST_DRAG = (Rel(0.35, 0.80), Rel(0.35, 0.45))  # finger up: later days show

OPEN_TIMEOUT = 3.0
TAB_TIMEOUT = 3.0
MAX_SCROLLS = 3
CLAIM_TRIES = 2


def lines_in(frame, region: RelRect) -> list[tuple[str, float, float]]:
    """OCR lines in a region: (lower-case text, x, y), window-relative."""
    h, w = frame.shape[:2]
    x0, y0, _, _ = region.to_pixels(w, h)
    return [(t.strip().lower(), (x0 + cx) / w, (y0 + cy) / h)
            for t, cx, cy in ocr_lines(_crop(frame, region))]


def tab_at(frame, word: str) -> Rel | None:
    """Where to tap the bottom tab whose label contains `word` ("special" /
    "pilgrimage"): a little above that label line (y ~0.975, near the edge)."""
    return next((Rel(x, y - TAB_ABOVE) for t, x, y in lines_in(frame, TABS)
                 if word in t), None)


def free_button(frame) -> Rel | None:
    """Daily Special's Free button (the Welfare Pack's), or None."""
    return next((Rel(x, y) for t, x, y in lines_in(frame, PACKS) if t == "free"), None)


def day_buttons(frame) -> list[tuple[str, float, float]]:
    """The Pilgrimage buttons in view, top to bottom: ("check in" / "already" /
    "not", x, y)."""
    found = []
    for t, x, y in lines_in(frame, DAYS):
        word = t.replace(" ", "").replace("-", "")
        if word.startswith("checkin"):
            found.append(("check in", x, y))
        elif word.startswith("already"):
            found.append(("already", x, y))
        elif word == "not":
            found.append(("not", x, y))
    return sorted(found, key=lambda b: b[2])


@register("super-value-gift")
class SuperValueGift(DailyTask):
    TITLE = "Super Value Gift"
    LABEL = "Super value gift"
    ICON = "🎀"
    DESCRIPTION = ("Open Super Value Gift (left bar), claim the Daily Special free "
                   "gift, and check in on the Seven-Day Pilgrimage.")
    START_HINT = "Start on the main Adventure screen."

    def _wait_for(self, ctx: Context, check, timeout: float) -> bool:
        end = time.time() + timeout
        while not check(ctx.frame()):
            if time.time() > end or self.wait(ctx, 0.5):
                return False
        return True

    def _open_tab(self, ctx: Context, word: str, what: str, ready) -> bool | None:
        """Tap a bottom tab and wait for its page. None if the tab isn't there."""
        tab = tab_at(ctx.frame(), word)
        if tab is None:
            return None
        if not self.tap(ctx, tab, what):
            return False
        return self._wait_for(ctx, ready, TAB_TIMEOUT)

    # --- Daily Special ----------------------------------------------------
    def _free_gift(self, ctx: Context) -> str | None:
        """Claim the Free gift. The outcome for the log; None on a stop."""
        opened = self._open_tab(ctx, "special", "the Daily Special tab",
                                lambda f: free_button(f) is not None
                                or "already purchased" in " ".join(
                                    t for t, _, _ in lines_in(f, PACKS)))
        if ctx.should_stop():
            return None
        if opened is None:
            return "no Daily Special tab"
        for _ in range(CLAIM_TRIES):
            button = free_button(ctx.frame())
            if button is None:
                text = " ".join(t for t, _, _ in lines_in(ctx.frame(), PACKS))
                return ("already claimed" if "already purchased" in text
                        else "no Free button")
            if not self.tap(ctx, button, "Free (Welfare Pack)"):
                return None
            landed = close_rewards(ctx, self.name, CLOSE_REWARDS)
            if landed is None:
                return None
            if landed:
                return "claimed"
        return "the Free tap showed no Rewards popup"

    # --- Seven-Day Pilgrimage ---------------------------------------------
    def _check_in(self, ctx: Context) -> str | None:
        """Tap today's Check in, scrolling the days to find it. The outcome for the
        log; None on a stop."""
        opened = self._open_tab(ctx, "pilgrimage", "the Seven-Day Pilgrimage tab",
                                lambda f: "checked" in " ".join(
                                    t for t, _, _ in lines_in(f, PILGRIMAGE_HEADER)))
        if ctx.should_stop():
            return None
        if opened is None:
            return "no Seven-Day Pilgrimage tab (the event may have ended)"
        if not opened:
            return "the Seven-Day Pilgrimage page didn't show"
        tries = 0
        for scroll in range(MAX_SCROLLS + 1):
            buttons = day_buttons(ctx.frame())
            check = next(((x, y) for b, x, y in buttons if b == "check in"), None)
            if check:
                if tries >= CLAIM_TRIES:
                    return "Check in showed no Rewards popup"
                tries += 1
                if not self.tap(ctx, Rel(*check), "Check in"):
                    return None
                landed = close_rewards(ctx, self.name, CLOSE_REWARDS)
                if landed is None:
                    return None
                if landed:
                    return "checked in"
                continue  # read again (and tap again)
            if any(b == "not" for b, _, _ in buttons):
                return "already checked in today"
            if scroll < MAX_SCROLLS:
                ctx.log.info("%s: no Check in in view -> scroll the days", self.name)
                ctx.drag_rel(*LIST_DRAG)
                if self.wait(ctx, 1.0):
                    return None
        return "no Check in button (all 7 days done?)"

    def run_daily(self, ctx: Context) -> bool:
        button = left_bar_button(ctx, "super", self.name, BUTTON_GUESS)
        if button is None:
            if ctx.should_stop():
                return False
            self.skip(ctx, "no Super Value Gift button on the left bar")
            return go_home(ctx)
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, button, "Super Value Gift"):
                return False
            if ctx.dry_run or self._wait_for(
                    ctx, lambda f: tab_at(f, "special") or tab_at(f, "pilgrimage"),
                    OPEN_TIMEOUT):
                break
        else:
            ctx.log.warning("%s: the Super Value Gift screen did not open", self.name)
            return False
        if ctx.dry_run:
            ctx.log.info("%s: dry run - would claim the free gift and check in",
                         self.name)
            return go_home(ctx)

        free = self._free_gift(ctx)
        if free is None:
            return False
        ctx.log.info("%s: Daily Special free gift: %s", self.name, free)
        if free not in ("claimed", "already claimed"):
            self.flag(ctx, f"Daily Special free gift: {free}")
        check = self._check_in(ctx)
        if check is None:
            return False
        ctx.log.info("%s: Seven-Day Pilgrimage: %s", self.name, check)
        if check in ("the Seven-Day Pilgrimage page didn't show",
                     "Check in showed no Rewards popup"):
            self.flag(ctx, f"Seven-Day Pilgrimage: {check}")
        return go_home(ctx)  # the back arrow
