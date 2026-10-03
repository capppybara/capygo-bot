"""Daily: adventure-assistant.

From the home screen, tap the floating robot-head bubble to open the Adventure
Assistant. Then on each of the Shortcut, Feature and Shop tabs: tap Execute and wait
for the run to finish, then tap Completed to get back. Finally close it with the X.

While a run is going, an "Assistant Log" screen shows "Waiting" and its bottom button
reads "Interrupted" - tapping that would stop the run, so it is left alone. When the
run is done the same button reads "Completed" (about 5s; give up after 10s).

The Shop tab's button bar has an extra "Add Item" button, which pushes Execute to the
right (x~463 vs ~429 on the other tabs). So Execute is found by reading the button
bar on every tab instead of being tapped at a fixed spot.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import Match, ocr_lines
from ..task import Context, register
from .daily import DailyTask

ROBOT_BTN = Rel(0.645, 0.508)    # the floating robot-head bubble on the home screen
TABS = [("Shortcut", Rel(0.234, 0.835)),
        ("Feature", Rel(0.411, 0.835)),
        ("Shop", Rel(0.589, 0.835))]
TITLE_REGION = RelRect(0.25, 0.110, 0.50, 0.050)  # "Adventure Assistant" banner
BAR_REGION = RelRect(0.15, 0.70, 0.70, 0.075)     # Log / (Add Item) / Execute
LOG_BUTTON = RelRect(0.30, 0.74, 0.40, 0.08)      # "Interrupted" -> "Completed"
COMPLETED_BTN = Rel(0.498, 0.779)
CLOSE_BTN = Rel(0.498, 0.925)                     # floating X under the panel
RUN_TIMEOUT = 10.0  # observed runs take 4.4-5.2s


@register("adventure-assistant")
class AdventureAssistant(DailyTask):
    TITLE = "Adventure Assistant"
    LABEL = "Adventure assistant"
    ICON = "🤖"
    DESCRIPTION = ("Open the Adventure Assistant (the robot bubble) and run Execute on "
                   "the Shortcut, Feature and Shop tabs.")
    START_HINT = "Start on the main Adventure screen."

    def _is_open(self, ctx: Context) -> bool:
        if ctx.dry_run:
            return True
        return "adventure assistant" in self.text_in(ctx, TITLE_REGION)

    def _find_execute(self, ctx: Context) -> Match | None:
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = BAR_REGION.to_pixels(w, h)
        for text, cx, cy in ocr_lines(frame[y0:y1, x0:x1]):
            if "execute" in text.lower():
                return Match(True, 1.0, x0 + cx, y0 + cy)
        return None

    def _wait_completed(self, ctx: Context) -> bool:
        """Wait (up to RUN_TIMEOUT) for the log's button to read "Completed"."""
        if ctx.dry_run:
            return True
        end = time.time() + RUN_TIMEOUT
        while time.time() < end:
            if "completed" in self.text_in(ctx, LOG_BUTTON):
                return True
            if self.wait(ctx, 0.5):
                return False
        return False

    def _run_tab(self, ctx: Context, name: str, tab: Rel) -> bool:
        if not self.tap(ctx, tab, f"{name} tab"):
            return False
        if not self._is_open(ctx):
            ctx.log.warning("adventure-assistant: the assistant closed on the %s tab",
                            name)
            return False
        if ctx.dry_run:
            ctx.log.info("%s: tap Execute (%s tab)", self.name, name)
        else:
            execute = self._find_execute(ctx)
            if execute is None:
                ctx.log.warning("adventure-assistant: no Execute button on the %s tab",
                                name)
                return False
            if not self.tap(ctx, execute, f"Execute ({name} tab)"):
                return False
        if not self._wait_completed(ctx):
            if not ctx.should_stop():
                ctx.log.warning("adventure-assistant: the %s run didn't finish within "
                                "%.0fs", name, RUN_TIMEOUT)
            return False
        return self.tap(ctx, COMPLETED_BTN, "Completed")

    def run_daily(self, ctx: Context) -> bool:
        for _attempt in range(2):  # the first tap can just bring the window forward
            if not self.tap(ctx, ROBOT_BTN, "robot bubble"):
                return False
            if self._is_open(ctx):
                break
        else:
            ctx.log.warning("adventure-assistant: the Adventure Assistant did not open "
                            "(start on the main Adventure screen); skipping")
            return False

        for name, tab in TABS:
            if not self._run_tab(ctx, name, tab):
                return False

        for _attempt in range(2):
            if not self.tap(ctx, CLOSE_BTN, "close"):
                return False
            if ctx.dry_run or not self._is_open(ctx):
                return True
        ctx.log.warning("adventure-assistant: the assistant is still open")
        return False
