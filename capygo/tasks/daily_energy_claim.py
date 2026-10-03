"""Daily: energy-claim.

From the main Adventure screen, tap the energy bolt at the top (2950/60 with a
green plus) to open the energy "Purchase" screen, then:
  1. Watch the free ad twice (AD button), dismissing the reward popup each time.
  2. Buy energy with gems twice (the gem button; its price rises after each buy,
     e.g. 90 -> 120, so the tap is by position, never by the number).
  3. Claim the Daily Pack once.
  4. Close the screen with the X.

Each action raises a "Rewards ... Tap to close" popup. It is dismissed by tapping
the "Purchase" title: that spot is harmless whether or not the popup is still up,
whereas "Tap to close" sits right over the X and an extra tap there would close the
whole screen early. Taps already used up for the day (a grayed AD button, a
"Claimed" pack) do nothing, so the sequence is safe to repeat - but re-running on the
same game day buys energy with gems again.

Before every action the screen is checked to still be the Purchase screen (OCR of
its title), so a missed tap can't turn into taps on the main screen.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .daily import DailyTask

ENERGY_BTN = Rel(0.432, 0.060)   # energy bolt on the main screen's top bar
AD_BTN = Rel(0.329, 0.475)       # "watch ad" for x15 energy
GEM_BTN = Rel(0.665, 0.477)      # x15 energy for gems (price rises per buy)
CLAIM_BTN = Rel(0.721, 0.617)    # Daily Pack "Claim"
CLOSE_BTN = Rel(0.498, 0.881)    # floating X under the panel
DISMISS = Rel(0.5, 0.215)        # the "Purchase" title: closes a reward popup
TITLE_REGION = RelRect(0.30, 0.185, 0.40, 0.06)

AD_TIMES = 2
GEM_TIMES = 2


@register("energy-claim")
class EnergyClaim(DailyTask):
    TITLE = "Energy Claim"
    LABEL = "Energy claim"
    ICON = "⚡"
    DESCRIPTION = ("Open the energy shop from the bolt at the top: watch both free "
                   "ads, buy energy with gems twice, claim the Daily Pack, close.")
    START_HINT = "Start on the main Adventure screen."

    def _is_open(self, ctx: Context) -> bool:
        if ctx.dry_run:  # nothing is clicked in a dry run, so the screen never opens
            return True
        return "purchase" in self.text_in(ctx, TITLE_REGION)

    def _ensure_open(self, ctx: Context) -> bool:
        """True if the Purchase screen is up. A reward popup that hasn't closed yet
        still shows the title, so a miss here means one more dismiss, then a
        recheck."""
        if self._is_open(ctx):
            return True
        if not self.tap(ctx, DISMISS, "dismiss"):
            return False
        return self._is_open(ctx)

    def run_daily(self, ctx: Context) -> bool:
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, ENERGY_BTN, "energy bolt"):
                return False
            if self._is_open(ctx):
                break
        else:
            ctx.log.warning("energy-claim: the Purchase screen did not open "
                            "(start on the main Adventure screen); skipping")
            return False

        steps = ([(AD_BTN, "watch ad")] * AD_TIMES
                 + [(GEM_BTN, "buy energy with gems")] * GEM_TIMES
                 + [(CLAIM_BTN, "claim Daily Pack")])
        for rel, what in steps:
            if not self._ensure_open(ctx):
                ctx.log.warning("energy-claim: the Purchase screen closed "
                                "unexpectedly; stopping")
                return False
            if not self.tap(ctx, rel, what):
                return False
            if not self.tap(ctx, DISMISS, "dismiss reward"):
                return False

        for _attempt in range(2):  # a second X if the first only closed a popup
            if not self.tap(ctx, CLOSE_BTN, "close"):
                return False
            if ctx.dry_run or not self._is_open(ctx):
                return True
        ctx.log.warning("energy-claim: the Purchase screen is still open")
        return False
