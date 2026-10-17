"""Task: extra-reward-collector (user, 2026-10-17).

Starts on an event fund popup with an "Extra Rewards" section (e.g. Goblin
Pachinko's "Marble Fund"; there are other versions, all working the same - user):
a progress bar and, at its right, a present (a badge counts the presents to open,
"(n/10)" under it). Per present (walked through 2026-10-17):
  1. Tap the present -> a big present box, "Common" above it, "Tap to upgrade
     rarity" and four "?" marks below.
  2. Tap the box 4 times, waiting 4s before each (user: the game lags between
     taps; 3s settled the failed upgrades seen, 4s leaves room for a successful
     one's longer animation). Each tap may upgrade the rarity (a mark turns ✓ or ✗); after the 4th
     the line reads "Click to claim reward".
  3. Tap the box again: a "Rewards" popup (e.g. x60 gems) with "Tap to close".
  4. Close it with a tap ABOVE its dark band (user) - taps on the band are
     ignored, and "Tap to close" sits over the fund's "Go to Event".
  Back on the fund, repeat. Once they're used up the game won't open the
  present (user): the big box not showing up after the tap is the end - no badge
  check.

The present is found from the "Extra Rewards" title (its spot can differ between
versions; the present sits at a fixed offset from the title in the one seen).
"Extra Rewards" still reads through the box and reward screens' dim overlay, so
the fund counts as back only once neither is up.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Task, register
from .daily import _crop, save_snapshot, tap, tap_to_close_up, wait

PRESENT_DX, PRESENT_DY = 168, 27     # px: the present, from the "Extra Rewards" title
BOX = Rel(300 / 642, 470 / 951)      # the big present: tap to upgrade, then to claim
BOX_TEXT = RelRect(0.15, 0.745, 0.70, 0.045)  # "Tap to upgrade rarity" / "Click to claim"
ABOVE_BAND = Rel(0.5, 250 / 951)     # closes the Rewards popup (user)
UPGRADE_TAPS = 4                     # user: tap the box 4 times
EXTRA_TAPS = 2                       # more if "upgrade rarity" still shows (a lost tap)
TAP_WAIT = 4.0                       # user: wait before each box tap (the game lags; 3s
                                     # settled the failed upgrades seen - 4s for the rest)
OPEN_TIMEOUT = 6.0
MAX_PRESENTS = 30                    # safety: never loop forever
NONE_LEFT, OPENED = "none left", "opened"
POLL = 0.4


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def find_extra(frame) -> tuple[int, int] | None:
    """The "Extra Rewards" title's centre, px (642x951), or None."""
    h, w = frame.shape[:2]
    for t, cx, cy in ocr_lines(frame):
        if "extra reward" in t.lower():
            return round(cx * 642 / w), round(cy * 951 / h)
    return None


def box_up(frame) -> str:
    """The box screen's line: "upgrade" / "claim", or "" if it isn't up."""
    text = _words(frame, BOX_TEXT)
    return "upgrade" if "upgrade" in text else "claim" if "claim" in text else ""


@register("extra-reward-collector")
class ExtraRewardCollector(Task):
    TITLE = "Extra Reward Collector"
    ICON = "🎁"
    DESCRIPTION = ("Event fund Extra Rewards: open every present - tap it, tap the box 4 "
                   "times to upgrade it, claim, close - until none are left.")
    START_HINT = ("Start on an event fund screen showing Extra Rewards (e.g. Goblin "
                  "Pachinko's Marble Fund).")

    def run(self, ctx: Context) -> None:
        if ctx.dry_run:
            for what, target in (("the present", Rel(488 / 642, 641 / 951)),
                                 *[("the box", BOX)] * (UPGRADE_TAPS + 1),
                                 ("above the reward band", ABOVE_BAND)):
                self._tap(ctx, target, what, 0)
            return
        opened = 0
        while opened < MAX_PRESENTS and not ctx.should_stop():
            frame = self._fund(ctx)
            if frame is None:
                return
            extra = find_extra(frame)
            present = (extra[0] + PRESENT_DX, extra[1] + PRESENT_DY)
            result = self._open(ctx, present)
            if result is None:
                return
            if result == NONE_LEFT:
                ctx.log.info("extra-rewards: the present didn't open - all collected "
                             "-> done, %d opened", opened)
                return
            opened += 1
            ctx.log.info("extra-rewards: present %d opened", opened)
        ctx.log.info("extra-rewards: %d present(s) opened", opened)

    # --- one present ---------------------------------------------------------
    def _open(self, ctx: Context, present: tuple[int, int]) -> str | None:
        """Tap the present, upgrade it 4 times, claim, close. OPENED (neither the
        rarity nor the reward is read - user: save compute); NONE_LEFT if the big box didn't show up (they're used up -
        user); None if it went wrong (logged, screen saved) or a stop."""
        if not self._tap(ctx, Rel(present[0] / 642, present[1] / 951), "the present"):
            return None
        if not self._until(ctx, lambda: box_up(ctx.frame()) != ""):
            return None if ctx.should_stop() else NONE_LEFT
        for n in range(1, UPGRADE_TAPS + EXTRA_TAPS + 1):
            if box_up(ctx.frame()) == "claim":
                break
            if n > UPGRADE_TAPS:
                ctx.log.info("extra-rewards: still upgrading after %d taps (a tap lost "
                             "to the lag?) -> again", n - 1)
            if wait(ctx, TAP_WAIT) or not self._tap(ctx, BOX, f"the box ({n})", 0):
                return None
        if not self._until(ctx, lambda: box_up(ctx.frame()) == "claim", TAP_WAIT + 3):
            self._problem(ctx, "the box never showed Click to claim reward")
            return None
        if not self._tap(ctx, BOX, "the box (claim)"):
            return None
        if not self._until(ctx, lambda: tap_to_close_up(ctx.frame())):
            self._problem(ctx, "no Rewards popup after claiming")
            return None
        if not self._tap(ctx, ABOVE_BAND, "above the reward band (close)"):
            return None
        return OPENED

    # --- helpers -------------------------------------------------------------
    def _fund(self, ctx: Context):
        """The fund screen, clear of the box and reward screens (a frame), or None
        (logged) if it doesn't show."""
        def clear(frame) -> bool:
            return (find_extra(frame) is not None and box_up(frame) == ""
                    and not tap_to_close_up(frame))
        end = time.time() + OPEN_TIMEOUT
        while True:
            frame = ctx.frame()
            if clear(frame):
                return frame
            if time.time() >= end or wait(ctx, POLL):
                break
        if not ctx.should_stop():
            self._problem(ctx, "not on a screen with Extra Rewards (start on an event "
                               "fund's screen)")
        return None

    def _until(self, ctx: Context, check, timeout: float = OPEN_TIMEOUT) -> bool:
        end = time.time() + timeout
        while True:
            if check():
                return True
            if time.time() >= end or wait(ctx, POLL):
                return False

    def _tap(self, ctx: Context, target: Rel, what: str, after: float = 1.0) -> bool:
        if ctx.should_stop():
            return False
        ctx.log.info("extra-rewards: tap %s", what)
        return tap(ctx, target, after)

    @staticmethod
    def _problem(ctx: Context, what: str) -> None:
        shot = save_snapshot(ctx, "extra-rewards")
        ctx.log.warning("extra-rewards: %s -> stopping%s", what,
                        f"; screen saved: {shot}" if shot else "")
