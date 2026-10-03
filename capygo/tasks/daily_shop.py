"""Daily: auto-daily-shop.

From the home screen, tap the leftmost bottom-bar icon to open the Shop, then:
  1. Treasure tab (2nd of the 5 tabs above the bottom bar):
       Gem Chest "Get 1" once, Mythic Treasure Chest "Get 1" once.
     Each opens a full-screen reveal ("Tap to continue") that is dismissed.
  2. Pack Shop tab (4th): claim the Free Pack, dismiss the "Rewards" popup.
  3. Back home via the crossed-swords Adventure tab (go_home).

Each "Get 1" is tapped once. A tap counts once its reveal popup shows up (the
Treasure Shop header disappears behind it); if no popup appears, the tap didn't
register (e.g. it only brought the window forward) and it's tapped once more. The
Gem Chest's first draw of the day uses a free key; after that the same button costs
gems, which is why the whole daily is once-a-day. The Free Pack is tapped only while
its title reads "Free Pack (1/1)" (after the claim it reads "(0/1)" and greys out).
Never touched: Top Up (real money) and the gem-priced packs.

Popups are dismissed by tapping near the top of the page (a harmless spot on both
tabs). "Tap to continue" itself sits just above the crossed-swords tab, and a tap
that lands after the reveal closes would take the game home mid-daily.
"""

from __future__ import annotations

import re

from ..geometry import Rel, RelRect
from ..task import Context, register
from .daily import DailyTask, go_home

SHOP_BTN = Rel(0.164, 0.941)                   # leftmost bottom-bar icon
TAB_BAR = RelRect(0.10, 0.83, 0.80, 0.04)      # Equipment .. Top Up (shop is open)
TREASURE_TAB = Rel(0.344, 0.851)               # 2nd tab
PACK_SHOP_TAB = Rel(0.654, 0.851)              # 4th tab
TREASURE_HEAD = RelRect(0.25, 0.08, 0.50, 0.045)   # "Treasure Shop"
PACK_HEAD = RelRect(0.30, 0.255, 0.40, 0.04)       # "Daily Pack"

GEM_GET1 = Rel(0.603, 0.329)                   # Gem Chest "Get 1"
MYTHIC_GET1 = Rel(0.603, 0.573)                # Mythic Treasure Chest "Get 1"

FREE_BTN = Rel(0.734, 0.430)
FREE_TITLE = RelRect(0.13, 0.330, 0.42, 0.036)     # "Free Pack (1/1)" / "(0/1)"

DISMISS = Rel(0.5, 0.17)   # top of the page: closes a reveal / rewards popup


@register("auto-daily-shop")
class DailyShop(DailyTask):
    TITLE = "Daily Shop"
    LABEL = "Daily shop"
    ICON = "🛒"
    DESCRIPTION = ("Open the Shop: draw the Gem Chest and Mythic Treasure Chest once "
                   "each, and claim the free daily pack.")
    START_HINT = "Start on the main Adventure screen."

    # --- checks -----------------------------------------------------------
    def _shop_open(self, ctx: Context) -> bool:
        return ctx.dry_run or "top up" in self.text_in(ctx, TAB_BAR)

    def _on(self, ctx: Context, head: RelRect, word: str) -> bool:
        return ctx.dry_run or word in self.text_in(ctx, head)

    def _back_on(self, ctx: Context, head: RelRect, word: str) -> bool:
        """After dismissing a popup: back on the tab? A reveal can take an extra tap
        to clear, so dismiss again up to twice before giving up."""
        for _ in range(3):
            if self._on(ctx, head, word):
                return True
            if not self.tap(ctx, DISMISS, "dismiss"):
                return False
        return self._on(ctx, head, word)

    # --- steps ------------------------------------------------------------
    def _draw(self, ctx: Context, chest: str, button: Rel) -> bool:
        for attempt in range(2):
            if not self.tap(ctx, button, f"{chest} Get 1"):
                return False
            # The reveal hides the Treasure Shop header; still seeing it means the
            # tap didn't register.
            if ctx.dry_run or not self._on(ctx, TREASURE_HEAD, "treasure shop"):
                break
            if attempt == 0:
                ctx.log.info("%s: no popup after %s Get 1 -> tapping again",
                             self.name, chest)
        else:
            ctx.log.warning("%s: %s Get 1 didn't open anything", self.name, chest)
            return False
        if not self.tap(ctx, DISMISS, "dismiss the reveal"):
            return False
        if not self._back_on(ctx, TREASURE_HEAD, "treasure shop"):
            ctx.log.warning("%s: didn't get back to the Treasure Shop after the %s draw",
                            self.name, chest)
            return False
        return True

    def _claim_free_pack(self, ctx: Context) -> bool:
        if not ctx.dry_run:
            title = self.text_in(ctx, FREE_TITLE)
            m = re.search(r"\((\d+)\s*/\s*\d+\)", title)
            if not (m and int(m.group(1)) >= 1):
                ctx.log.info("%s: free pack already claimed (reads %r)", self.name,
                             title)
                return True
        if not self.tap(ctx, FREE_BTN, "Free pack"):
            return False
        if not self.tap(ctx, DISMISS, "dismiss the reward"):
            return False
        if not self._back_on(ctx, PACK_HEAD, "daily pack"):
            ctx.log.warning("%s: didn't get back to the Pack Shop after the claim",
                            self.name)
            return False
        return True

    def run_daily(self, ctx: Context) -> bool:
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, SHOP_BTN, "Shop (bottom bar)"):
                return False
            if self._shop_open(ctx):
                break
        else:
            ctx.log.warning("%s: the Shop did not open (start on the main Adventure "
                            "screen); skipping", self.name)
            return False

        if not self.tap(ctx, TREASURE_TAB, "Treasure tab"):
            return False
        if not self._on(ctx, TREASURE_HEAD, "treasure shop"):
            ctx.log.warning("%s: the Treasure tab did not open", self.name)
            return False
        if not self._draw(ctx, "Gem Chest", GEM_GET1):
            return False
        if not self._draw(ctx, "Mythic Treasure Chest", MYTHIC_GET1):
            return False

        if not self.tap(ctx, PACK_SHOP_TAB, "Pack Shop tab"):
            return False
        if not self._on(ctx, PACK_HEAD, "daily pack"):
            ctx.log.warning("%s: the Pack Shop tab did not open", self.name)
            return False
        if not self._claim_free_pack(ctx):
            return False

        return go_home(ctx)
