"""Menu chore: login-claim (the Log In sign-in reward).

Starts with the menu drawer open: Log In (the bottom item) -> the "7-day Sign-in
Event" panel: a tile per day, claimed ones ticked, today's with a green "Claim"
header. User: tap it, then dismiss the popup. The Claim tile moves each day, so
it's found by reading "Claim" among the tile headers (Day 7 is a wider
"Ultimate" row). Claiming raises a "Rewards / Tap to close" popup, closed with a
tap ABOVE its dark band (taps on the band are ignored), on the panel's title,
which does nothing once the popup is gone. Then the panel's X -> the drawer.
No "Claim" header = already claimed today -> just close the panel.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import _crop, tap_to_close_up
from .menu import MenuTask, go_menu

PANEL_TITLE = RelRect(0.25, 0.165, 0.50, 0.07)   # "7-day Sign-in Event"
DAYS = RelRect(0.15, 0.24, 0.70, 0.43)           # the day tiles and their headers
TILE_BELOW_HEADER = 0.058                         # header -> the tile's reward (55px)
REWARD_DISMISS = Rel(0.5, 0.20)                   # the panel title, above the band
OPEN_TIMEOUT = 5.0
REWARD_TIMEOUT = 4.0
POLL = 0.3


@register("login-claim")
class LoginClaim(MenuTask):
    TITLE = "Log In Reward"
    LABEL = "Log In reward"
    ICON = "📆"
    DESCRIPTION = ("Menu -> Log In: claim today's 7-day sign-in reward, then close it.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_item(ctx, "log in"):
            return False
        if ctx.dry_run:
            return go_menu(ctx)
        if not self._wait(ctx, lambda: "sign-in" in self.text_in(ctx, PANEL_TITLE),
                          OPEN_TIMEOUT):
            ctx.log.warning("%s: the sign-in panel did not open", self.name)
            return False

        header = self._claim_header(ctx)
        if header is None:
            ctx.log.info("%s: nothing to claim (already claimed today)", self.name)
            return go_menu(ctx)  # the panel's X -> the drawer
        body = Rel(header.x, header.y + TILE_BELOW_HEADER)
        for target, what in ((body, "Claim"), (header, "Claim header")):
            if not self.tap(ctx, target, what):
                return False
            if self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
                break
            if ctx.should_stop():
                return False
        else:
            ctx.log.warning("%s: tapping Claim raised no reward", self.name)
            return False
        if not self.tap(ctx, REWARD_DISMISS, "dismiss the reward"):
            return False
        if not self._wait(ctx, lambda: not tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
            ctx.log.warning("%s: the reward popup won't close", self.name)
            return False
        return go_menu(ctx)  # the panel's X -> the drawer

    def _claim_header(self, ctx: Context) -> Rel | None:
        """Where today's green "Claim" header is, or None if no day reads Claim."""
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, _, _ = DAYS.to_pixels(w, h)
        for text, cx, cy in ocr_lines(_crop(frame, DAYS)):
            if text.strip().lower() == "claim":
                return Rel((cx + x0) / w, (cy + y0) / h)
        return None

    def _wait(self, ctx: Context, check, timeout: float) -> bool:
        """Poll check() until it holds (True) or the timeout/stop (False)."""
        end = time.time() + timeout
        while True:
            if check():
                return True
            if time.time() >= end or self.wait(ctx, POLL):
                return False
