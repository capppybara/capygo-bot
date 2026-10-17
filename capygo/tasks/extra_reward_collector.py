"""Task: extra-reward-collector (user, 2026-10-17).

Starts on an event fund popup with an "Extra Rewards" section (e.g. Goblin
Pachinko's "Marble Fund"; there are other versions, all working the same - user):
a progress bar and, at its right, a present (a badge counts the presents to open,
"(n/10)" under it). Per present (walked through 2026-10-17):
  1. Tap the present -> a big present box, "Common" above it, "Tap to upgrade
     rarity" and four "?" marks below.
  2. Tap the box, waiting 4s before each tap (user: the game lags; 3s settled
     the failed upgrades seen, 4s leaves room for a successful one's longer
     animation), until the "Rewards" popup (e.g. x60 gems, "Tap to close") shows
     - at most 10 taps (user). Seen: 4 taps each try an upgrade (a mark turns ✓
     or ✗), then "Click to claim reward", and the 5th claims.
  3. Close it with a tap ABOVE its dark band (user) - taps on the band are
     ignored, and "Tap to close" sits over the fund's "Go to Event".
  Back on the fund, repeat. Once they're used up the game won't open the
  present (user): the big box not showing up after the tap is the end - no badge
  check. That last tap opens a tooltip of the possible rewards ("Obtain one of
  the rewards."); it's left open, the run ends there (user, 2026-10-17).

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
MAX_BOX_TAPS = 10                    # user: tap the box until the reward, at most 10
                                     # (4 upgrades + the claim, seen; the rest is slack)
REWARD_POLL = 1.0                    # look for the reward once a second while waiting
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
                                 *[("the box", BOX)] * 5,
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
        """Tap the present; once the big box is up, tap it - waiting TAP_WAIT
        before each tap, and watching for the reward meanwhile - until the
        Rewards popup shows, at most MAX_BOX_TAPS (user, 2026-10-17: 4 upgrades,
        then a claim, but don't count: tap until the reward). Then close it.
        OPENED (neither the rarity nor the reward is read - user: save compute);
        NONE_LEFT if the big box didn't show up (they're used up - user); None if
        it went wrong (logged, screen saved) or a stop."""
        if not self._tap(ctx, Rel(present[0] / 642, present[1] / 951), "the present"):
            return None
        if not self._until(ctx, lambda: box_up(ctx.frame()) != ""):
            return None if ctx.should_stop() else NONE_LEFT
        reward = False
        for n in range(1, MAX_BOX_TAPS + 2):  # the last pass only looks
            # the wait before each tap (user), looking for the reward meanwhile
            if self._until(ctx, lambda: tap_to_close_up(ctx.frame()), TAP_WAIT,
                           poll=REWARD_POLL):
                reward = True
                break
            if n > MAX_BOX_TAPS or not self._tap(ctx, BOX, f"the box ({n})", 0):
                break
        if not reward:
            if not ctx.should_stop():
                self._problem(ctx, f"no reward after {MAX_BOX_TAPS} taps on the box")
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

    def _until(self, ctx: Context, check, timeout: float = OPEN_TIMEOUT,
               poll: float = POLL) -> bool:
        end = time.time() + timeout
        while True:
            if check():
                return True
            if time.time() >= end or wait(ctx, min(poll, max(0.0, end - time.time()))):
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
