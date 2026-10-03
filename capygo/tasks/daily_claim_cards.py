"""Daily: claim-cards.

From the home screen, tap Privilege Card (the top button of the left bar), tap
"Claim all", dismiss the Rewards popup, and go back with the back arrow.

The Claim all tap counts once its "Rewards ... Tap to close" popup appears; if it
doesn't, the tap didn't register and it's tapped once more. (When nothing is left to
claim no popup comes, and the extra tap is harmless.) Dismissing the popup and the
back arrow are exactly what go_home() does from this screen.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .daily import DailyTask, go_home, tap_to_close_up

PRIVILEGE_BTN = Rel(0.162, 0.258)               # top button of the left bar
CLAIM_ALL = Rel(0.498, 0.950)
CLAIM_ALL_TEXT = RelRect(0.35, 0.925, 0.30, 0.05)  # "Claim all": the screen is open


@register("claim-cards")
class ClaimCards(DailyTask):
    TITLE = "Claim Cards"
    LABEL = "Claim cards"
    ICON = "💳"
    DESCRIPTION = ("Open Privilege Card (top of the left bar), tap Claim all, and go "
                   "back.")
    START_HINT = "Start on the main Adventure screen."

    def _open(self, ctx: Context) -> bool:
        return ctx.dry_run or "claim all" in self.text_in(ctx, CLAIM_ALL_TEXT)

    def run_daily(self, ctx: Context) -> bool:
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, PRIVILEGE_BTN, "Privilege Card"):
                return False
            if self._open(ctx):
                break
        else:
            ctx.log.warning("%s: the Privilege Card screen did not open (start on the "
                            "main Adventure screen); skipping", self.name)
            return False

        for attempt in range(2):
            if not self.tap(ctx, CLAIM_ALL, "Claim all"):
                return False
            if ctx.dry_run or tap_to_close_up(ctx.frame()):
                break
            if attempt == 0:
                ctx.log.info("%s: no Rewards popup after Claim all -> tapping again",
                             self.name)
        else:
            ctx.log.info("%s: no Rewards popup (nothing left to claim?)", self.name)

        return go_home(ctx)  # dismisses the popup, then the back arrow
