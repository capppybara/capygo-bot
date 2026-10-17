"""Task: extra-reward-collector (user, 2026-10-17).

Starts on an event fund popup with an "Extra Rewards" section (e.g. Goblin
Pachinko's "Marble Fund"; there are other versions, all working the same - user):
a progress bar and, at its right, a present with a pink-red badge counting the
presents to open, "(n/10)" under it. Per present (walked through 2026-10-17):
  1. Tap the present -> a big present box, "Common" above it, "Tap to upgrade
     rarity" and four "?" marks below.
  2. Tap the box 4 times, waiting 3s before each (user: the game lags between
     taps). Each tap may upgrade the rarity (a mark turns ✓ or ✗); after the 4th
     the line reads "Click to claim reward".
  3. Tap the box again: a "Rewards" popup (e.g. x60 gems) with "Tap to close".
  4. Close it with a tap ABOVE its dark band (user) - taps on the band are
     ignored, and "Tap to close" sits over the fund's "Go to Event".
  Back on the fund, the badge is one lower. Repeat until it's gone.

The present is found from the "Extra Rewards" title (its spot can differ between
versions; the present sits at a fixed offset from the title in the one seen). The
badge is found by its colour, not read: its digit doesn't OCR. "Extra Rewards"
still reads through the box and reward screens' dim overlay, so the badge is only
checked once neither is up.
"""

from __future__ import annotations

import re
import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Task, register
from .daily import _crop, save_snapshot, tap, tap_to_close_up, wait

PRESENT_DX, PRESENT_DY = 168, 27     # px: the present, from the "Extra Rewards" title
BADGE_DX, BADGE_DY = 29, -21         # px: its count badge, from the present
BADGE_BOX = 12                       # px: half the badge check's square
BADGE_SHARE = 0.15                   # pink share in it: badge 0.35, none 0.00
BOX = Rel(300 / 642, 470 / 951)      # the big present: tap to upgrade, then to claim
BOX_TEXT = RelRect(0.15, 0.745, 0.70, 0.045)  # "Tap to upgrade rarity" / "Click to claim"
RARITY = RelRect(0.20, 0.150, 0.60, 0.060)    # "Common" (above the box)
REWARD_ITEMS = RelRect(0.10, 0.345, 0.80, 0.230)  # "Rewards" + its band's "x60"s (the title
                                                  # in the crop: alone, "x60" read upside down)
ABOVE_BAND = Rel(0.5, 250 / 951)     # closes the Rewards popup (user)
UPGRADE_TAPS = 4                     # user: tap the box 4 times
EXTRA_TAPS = 2                       # more if "upgrade rarity" still shows (a lost tap)
TAP_WAIT = 3.0                       # user: wait 3s before each box tap (the game lags)
OPEN_TIMEOUT = 6.0
MAX_PRESENTS = 30                    # safety: never loop forever
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


def badge_up(frame, present: tuple[int, int]) -> bool:
    """The present's pink-red count badge is showing (presents left)."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    x, y = present[0] + BADGE_DX, present[1] + BADGE_DY
    c = frame[int((y - BADGE_BOX) * ky):int((y + BADGE_BOX) * ky),
              int((x - BADGE_BOX) * kx):int((x + BADGE_BOX) * kx)].astype(int)
    if c.size == 0:
        return False
    b, g, r = c[..., 0], c[..., 1], c[..., 2]
    pink = (r > 205) & (g > 55) & (g < 135) & (b > 90) & (b < 170) & (r - b > 60)
    return float(pink.mean()) >= BADGE_SHARE


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
            if not badge_up(frame, present):
                ctx.log.info("extra-rewards: no presents left (no badge) -> done, %d "
                             "opened", opened)
                return
            result = self._open(ctx, present)
            if result is None:
                return
            opened += 1
            ctx.log.info("extra-rewards: present %d: %s", opened, result)
        ctx.log.info("extra-rewards: %d present(s) opened", opened)

    # --- one present ---------------------------------------------------------
    def _open(self, ctx: Context, present: tuple[int, int]) -> str | None:
        """Tap the present, upgrade it 4 times, claim, close. "<rarity>, <reward>"
        for the log, or None if it went wrong (logged, screen saved) or a stop."""
        if not self._tap(ctx, Rel(present[0] / 642, present[1] / 951), "the present"):
            return None
        if not self._until(ctx, lambda: box_up(ctx.frame()) != ""):
            self._problem(ctx, "the present didn't open")
            return None
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
        rarity = _words(ctx.frame(), RARITY).strip() or "?"
        if not self._tap(ctx, BOX, "the box (claim)"):
            return None
        if not self._until(ctx, lambda: tap_to_close_up(ctx.frame())):
            self._problem(ctx, "no Rewards popup after claiming")
            return None
        reward = ", ".join(re.findall(r"x\s*[\d.,]+[kmb]?", _words(ctx.frame(),
                                                                   REWARD_ITEMS))) or "?"
        if not self._tap(ctx, ABOVE_BAND, "above the reward band (close)"):
            return None
        return f"{rarity}, {reward}"

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
