"""Event: dungeon-dive.

Starts on the Events screen: Challenge tab -> Dungeon Dive card (2nd) -> the
"Dungeon Floor <n>" screen. Then it buys two Dungeon Dive Challenge vouchers with
gems: tap the ticket "+" at the top-left corner -> "Purchase" popup (1 voucher) ->
"+" once (2 vouchers, 300 gems) -> Purchase -> a Rewards popup. Then it backs out to
the Events screen (the purchase popup closes itself after buying). It doesn't
challenge; it only buys the vouchers (user's call).

The game allows at most 2 voucher purchases a day, so the quantity isn't verified
(user: it can't be messed up). The one check is that the Purchase popup opened, so
the "+" and Purchase taps never land blind on the dungeon screen.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .event import EventTask, go_events

DUNGEON_CARD = Rel(0.35, 0.33)                    # 2nd card on the Challenge tab
CARD_NAME = RelRect(0.12, 0.265, 0.50, 0.05)      # "Dungeon Dive"
FLOOR_TITLE = RelRect(0.25, 0.205, 0.50, 0.05)    # "Dungeon Floor <n>"
TICKET_PLUS = Rel(0.137, 0.054)                   # ticket "+" at the top-left corner
POPUP_TITLE = RelRect(0.30, 0.31, 0.40, 0.045)    # "Purchase"
QTY_PLUS = Rel(0.608, 0.496)                      # "+" next to the quantity
PURCHASE_BTN = Rel(0.498, 0.601)                  # green "Purchase xN"


@register("dungeon-dive")
class DungeonDive(EventTask):
    TITLE = "Dungeon Dive"
    LABEL = "Dungeon dive vouchers"
    ICON = "🏰"
    DESCRIPTION = ("Events -> Challenge -> Dungeon Dive: buy 2 challenge vouchers with "
                   "gems (ticket + at the top-left), then go back.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, "challenge"):
            return False
        if not ctx.dry_run and "dungeon dive" not in self.text_in(ctx, CARD_NAME):
            ctx.log.warning("%s: no Dungeon Dive card on the Challenge tab", self.name)
            return False
        if not self.tap(ctx, DUNGEON_CARD, "Dungeon Dive"):
            return False
        if not ctx.dry_run and "dungeon floor" not in self.text_in(ctx, FLOOR_TITLE):
            ctx.log.warning("%s: the Dungeon Floor screen did not open", self.name)
            return False

        if not self.tap(ctx, TICKET_PLUS, "ticket +"):
            return False
        if not ctx.dry_run and "purchase" not in self.text_in(ctx, POPUP_TITLE):
            ctx.log.warning("%s: the voucher Purchase popup did not open", self.name)
            return False
        if not self.tap(ctx, QTY_PLUS, "+ (2 vouchers)"):
            return False
        if not self.tap(ctx, PURCHASE_BTN, "Purchase"):
            return False

        return go_events(ctx)  # dismiss the reward, back arrow -> the Events screen
