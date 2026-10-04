"""Daily: claim-calendar.

From the home screen, tap Calendar on the right-hand bar to open the Event Calendar,
tap the chest at the top-right of its banner (it carries a red "!" while there's
something to claim), dismiss the Rewards popup, and close the calendar.

The chest tap counts once its "Rewards ... Tap to close" popup appears; if it
doesn't, the tap didn't register and it's tapped once more (harmless when there's
nothing left to claim). Dismissing the popup and the X are what go_home() does here.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .daily import DailyTask, go_home, tap_to_close_up

CALENDAR_BTN = Rel(0.841, 0.249)                 # "Calendar" on the right-hand bar
CHEST = Rel(0.782, 0.271)                        # chest at the banner's top-right
BANNER = RelRect(0.16, 0.20, 0.32, 0.10)         # "Event Calendar": it's open


@register("claim-calendar")
class ClaimCalendar(DailyTask):
    TITLE = "Claim Calendar"
    LABEL = "Claim calendar"
    ICON = "📆"
    DESCRIPTION = ("Open the Event Calendar (right-hand bar), tap its reward chest, "
                   "and close it.")
    START_HINT = "Start on the main Adventure screen."

    def _open(self, ctx: Context) -> bool:
        return ctx.dry_run or "calendar" in self.text_in(ctx, BANNER)

    def run_daily(self, ctx: Context) -> bool:
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, CALENDAR_BTN, "Calendar"):
                return False
            if self._open(ctx):
                break
        else:
            ctx.log.warning("%s: the Event Calendar did not open (start on the main "
                            "Adventure screen); skipping", self.name)
            return False

        for attempt in range(2):
            if not self.tap(ctx, CHEST, "calendar chest"):
                return False
            if ctx.dry_run or tap_to_close_up(ctx.frame()):
                break
            if attempt == 0:
                ctx.log.info("%s: no Rewards popup after the chest -> tapping again",
                             self.name)
        else:
            ctx.log.info("%s: no Rewards popup (nothing left to claim?)", self.name)

        return go_home(ctx)  # dismisses the popup, then the X
