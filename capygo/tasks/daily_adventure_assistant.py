"""Daily: adventure-assistant.

From the home screen, tap the floating robot-head bubble to open the Adventure
Assistant. The bubble sits on the home island, and the island isn't always drawn in
the same place (seen at x 239-413, y 302-492 on a 642x951 window, three spots in one
evening), so the bubble is found by its picture (templates/dailies/robot_bubble.png)
anywhere on the screen. It is tapped only in the open middle of the screen: outside
that, a side icon or a bottom button is drawn over that spot. Then on each of the Shortcut, Feature and Shop tabs: tap Execute and wait
for the run to finish, then tap Completed to get back. Finally close it with the X.

While a run is going, an "Assistant Log" screen shows "Waiting" and its bottom button
reads "Interrupted" - tapping that would stop the run, so it is left alone. When the
run is done the same button reads "Completed" (about 5s; give up after 10s).

The Shop tab's button bar has an extra "Add Item" button, which pushes Execute to the
right (x~463 vs ~429 on the other tabs). So Execute is found by reading the button
bar on every tab instead of being tapped at a fixed spot.

Whenever the chore can't go on, the reason is raised as a flag, so the end-of-run
summary says what went wrong (e.g. "the robot bubble isn't on the home screen")
instead of only "did not finish".
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import Match, ocr_lines
from ..task import Context, register
from .daily import (HOME, SPRITE_THRESHOLD, SWITCH_RED, SWITCH_UNKNOWN, DailyTask,
                    best_sprite, home_state)

# The robot head inside the bubble, searched over the whole screen: 0.92-1.00 on home
# screens (10 spots), at most 0.52 on any other saved screen.
ROBOT_SPRITE = "robot_bubble.png"
# The open middle of the home screen, clear of the top bar, the side icon bars and
# the buttons at the bottom. The bubble is tapped only in here.
CLEAR = RelRect(0.22, 0.11, 0.56, 0.51)
ROBOT_BTN = Rel(0.645, 0.508)    # where the bubble usually is (dry runs only)
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

    def _fail(self, ctx: Context, reason: str) -> bool:
        """Give up with a reason: logged now and listed in the end-of-run summary."""
        if not ctx.should_stop():
            self.flag(ctx, reason)
        return False

    def _run_tab(self, ctx: Context, name: str, tab: Rel) -> bool:
        if not self.tap(ctx, tab, f"{name} tab"):
            return False
        if not self._is_open(ctx):
            return self._fail(ctx, f"the assistant closed after tapping the {name} tab")
        if ctx.dry_run:
            ctx.log.info("%s: tap Execute (%s tab)", self.name, name)
        else:
            execute = self._find_execute(ctx)
            if execute is None:
                return self._fail(ctx, f"no Execute button on the {name} tab")
            if not self.tap(ctx, execute, f"Execute ({name} tab)"):
                return False
        if not self._wait_completed(ctx):
            return self._fail(ctx, f"the {name} tab's run didn't finish within "
                                   f"{RUN_TIMEOUT:.0f}s (its log never read Completed)")
        return self.tap(ctx, COMPLETED_BTN, "Completed")

    @staticmethod
    def _covered_by(bubble: Match, w: int, h: int) -> str | None:
        """What's drawn over the bubble's spot, or None if it's in the open middle."""
        x, y = bubble.x / w, bubble.y / h
        if y < CLEAR.y:
            return "the top bar"
        if y > CLEAR.y + CLEAR.h:
            return "the buttons at the bottom"
        if x < CLEAR.x:
            return "the left icon bar"
        if x > CLEAR.x + CLEAR.w:
            return "the right icon bar"
        return None

    def _why_no_bubble(self, frame, best: Match) -> str:
        """Why the bubble wasn't found on this frame."""
        state = home_state(frame)
        if state == SWITCH_RED:
            return ("the game was in the red-switch co-op mode, not on the home screen, "
                    "so there was no robot bubble to tap")
        if state == SWITCH_UNKNOWN:
            return ("the capy switch next to Start couldn't be read, so this may not be "
                    "the home screen; no robot bubble found")
        if state != HOME:
            return ("the game wasn't on the home screen (the Start button was covered "
                    "or missing), so there was no robot bubble to tap")
        return (f"the robot bubble isn't on the home screen (closest look-alike "
                f"{best.score:.2f} at ({best.x}, {best.y}); a match needs "
                f"{SPRITE_THRESHOLD:.2f}). The island may be dragged so the bubble is "
                f"off screen. Drag it back, or open the assistant by hand")

    def _open(self, ctx: Context) -> bool:
        """Find the robot bubble and tap it; True once the assistant is open."""
        bubble = ROBOT_BTN
        for attempt in range(2):  # the first tap can just bring the window forward
            if not ctx.dry_run:
                frame = ctx.frame()
                best = best_sprite(ctx, frame, ROBOT_SPRITE)
                if not best.found:
                    if attempt and self._is_open(ctx):  # it opened late
                        return True
                    return self._fail(ctx, self._why_no_bubble(frame, best))
                h, w = frame.shape[:2]
                ctx.log.info("%s: robot bubble at (%d, %d), match %.2f",
                             self.name, best.x, best.y, best.score)
                covered = self._covered_by(best, w, h)
                if covered:
                    return self._fail(ctx, (
                        f"the robot bubble is at ({best.x}, {best.y}), where "
                        f"{covered} is drawn, so a tap there could hit that instead. "
                        f"Drag the island so the bubble is in the middle, or open the "
                        f"assistant by hand"))
                bubble = best
            if not self.tap(ctx, bubble, "robot bubble"):
                return False
            if self._is_open(ctx):
                return True
        where = "" if ctx.dry_run else f" at ({bubble.x}, {bubble.y})"
        return self._fail(ctx, f"tapped the robot bubble{where} twice, but the Adventure "
                               f"Assistant didn't open")

    def run_daily(self, ctx: Context) -> bool:
        if not self._open(ctx):
            return False

        for name, tab in TABS:
            if not self._run_tab(ctx, name, tab):
                return False

        for _attempt in range(2):
            if not self.tap(ctx, CLOSE_BTN, "close"):
                return False
            if ctx.dry_run or not self._is_open(ctx):
                return True
        return self._fail(ctx, "the assistant was still open after tapping its X twice")
