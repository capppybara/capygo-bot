"""Guild chore: guild-hall (donate 5 times).

Starts on the guild screen: Guild Hall -> the "Guild Info" panel -> Donate -> the
"Guild Donation" popup ("Chances Left Today: 5"). User: tap the donate button 5
times; the game stops you after 5. The first donation of the day is free; the
others cost 25 purple cubes each (user-approved). Each one raises a "Rewards"
popup; after the 5th the game closes the donation popup itself and greys out
Guild Info's Donate button (no more "!"). Then back to the guild screen (X).

Closing a reward: tap just below the reward's dark band. A tap ON the band does
nothing, and the next tap meant for donate then only closed the reward (that's
how the first walkthrough "lost" taps). Below the band is a blank text line of
the donation popup, so a stray tap there is harmless.

Each donation is checked by its count going down; a donation that doesn't take
gets tapped again, and if the count still won't move it stops with a flag.
"""

from __future__ import annotations

import re
import time

from ..geometry import Rel, RelRect
from ..task import Context, register
from .daily import _crop, tap_to_close_up
from .guild import GuildTask, go_guild

INFO_TITLE = RelRect(0.30, 0.075, 0.40, 0.05)       # "Guild Info" (reads under popups too)
DONATE_BTN = Rel(0.500, 0.833)                       # Guild Info's Donate (bottom middle)
DONATE_COLOR = RelRect(0.41, 0.815, 0.18, 0.04)      # inside it: blue = open, grey = done
DONATION_TITLE = RelRect(0.25, 0.350, 0.50, 0.045)  # "Guild Donation"
GIVE_BTN = Rel(0.498, 0.665)                         # "Free" / "25" (purple cubes)
CHANCES = RelRect(0.30, 0.700, 0.40, 0.04)           # "Chances Left Today: N"
REWARD_DISMISS = Rel(0.5, 0.600)                     # just below the reward's dark band

DONATIONS = 5          # user: 5 a day (the game's own limit)
OPEN_TIMEOUT = 5.0
REWARD_TIMEOUT = 4.0
TRIES = 3              # taps per donation before giving up
POLL = 0.3
SETTLE = 1.0


def donate_open(frame) -> bool:
    """Guild Info's Donate button is still blue (donations left). It turns grey
    once today's are done: blue-minus-red ~88 vs ~25."""
    c = _crop(frame, DONATE_COLOR).astype(int)
    return float((c[..., 0] - c[..., 2]).mean()) > 55


@register("guild-hall")
class GuildHall(GuildTask):
    TITLE = "Guild Hall"
    LABEL = "Guild hall donations"
    ICON = "🏰"
    DESCRIPTION = ("Guild -> Guild Hall -> Donate: donate 5 times (the first is free, "
                   "then 25 purple cubes each), then go back.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_place(ctx, "guild hall"):
            return False
        if ctx.dry_run:
            return go_guild(ctx)
        if not self._wait(ctx, lambda: "guild info" in self.text_in(ctx, INFO_TITLE),
                          OPEN_TIMEOUT):
            ctx.log.warning("%s: Guild Info did not open", self.name)
            return False
        if not donate_open(ctx.frame()):
            ctx.log.info("%s: Donate is greyed out - today's donations are done",
                         self.name)
            return go_guild(ctx)

        if not self.tap(ctx, DONATE_BTN, "Donate"):
            return False
        if not self._wait(ctx, lambda: "guild donation" in self.text_in(
                ctx, DONATION_TITLE), OPEN_TIMEOUT):
            ctx.log.warning("%s: the Guild Donation popup did not open", self.name)
            return False
        if self.wait(ctx, SETTLE):
            return False

        done = 0
        left = self._chances(ctx)
        while left and done < DONATIONS:
            if not self._donate(ctx, left):
                return False
            done += 1
            left = self._chances(ctx)  # None once the game closes the popup (all done)
            ctx.log.info("%s: donation %d done (%s left today)", self.name, done,
                         left if left is not None else 0)
        ctx.log.info("%s: %d donation(s) made", self.name, done)
        return go_guild(ctx)  # X -> the guild screen

    # --- steps ------------------------------------------------------------
    def _donate(self, ctx: Context, left: int) -> bool:
        """One donation: tap the donate button until the Rewards popup shows, close
        it, and check the count went down. False (with a flag) if it won't."""
        for attempt in range(1, TRIES + 1):
            if not self.tap(ctx, GIVE_BTN, f"donate ({left} left)"):
                return False
            if self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
                break
            if ctx.should_stop():
                return False
            ctx.log.info("%s: no reward yet (try %d/%d)", self.name, attempt, TRIES)
        else:
            self.flag(ctx, f"the donation didn't go through ({left} left today). "
                           "Donate by hand.")
            return False
        if not self.tap(ctx, REWARD_DISMISS, "close the reward"):
            return False
        if not self._wait(ctx, lambda: not tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
            ctx.log.warning("%s: the reward popup won't close", self.name)
            return False
        if self.wait(ctx, SETTLE):
            return False
        now = self._chances(ctx)
        if now is not None and now >= left:
            self.flag(ctx, f"a donation showed a reward but the count stayed at {left}. "
                           "Check Guild Hall donations.")
            return False
        return True

    def _chances(self, ctx: Context) -> int | None:
        """'Chances Left Today: N' -> N; None when the popup isn't up."""
        m = re.search(r"today:?\s*(\d+)", self.text_in(ctx, CHANCES))
        return int(m.group(1)) if m else None

    def _wait(self, ctx: Context, check, timeout: float) -> bool:
        """Poll check() until it holds (True) or the timeout/stop (False)."""
        end = time.time() + timeout
        while True:
            if check():
                return True
            if time.time() >= end or self.wait(ctx, POLL):
                return False
