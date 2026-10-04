"""Event: tower-challenge.

Starts on the Events screen (see event.py): Challenge tab -> Tower Challenge card ->
the "Tower of Infinity" screen. Then tap Challenge 5 times; each one is a battle that
ends on a "Victory" or "Defeat" screen (about 10s), checked every 10 seconds.
Finally the back arrow returns to the Events screen for the next event. "Auto Next
Level" stays as the player set it.

Each Challenge costs one ticket (10 a day, refilling). The user chose 5 per run to
stay well inside that, rather than reading the ticket count.

The result screen is dismissed by tapping the middle of the screen: "Tap to close"
sits right over the tower screen's "Auto Next Level" checkbox, so a tap there that
lands after the result closes would toggle it. Closing the result plays a short
black transition back to the tower screen.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .event import EventTask, go_events

FIRST_CARD = RelRect(0.12, 0.10, 0.50, 0.05)     # "Tower Challenge" (1st card)
TOWER_CARD = Rel(0.35, 0.165)
TOWER_TITLE = RelRect(0.25, 0.135, 0.50, 0.045)  # "Tower of Infinity <n>"
CHALLENGE_BTN = Rel(0.498, 0.943)
RESULT_DISMISS = Rel(0.5, 0.494)                 # middle of the result screen

RUNS = 5                 # user: 5 per run, well inside the 10 daily tickets
POLL = 10.0              # check for the result screen this often (user)
BATTLE_TIMEOUT = 120.0
TRANSITION_TIMEOUT = 10.0


@register("tower-challenge")
class TowerChallenge(EventTask):
    TITLE = "Tower Challenge"
    LABEL = "Tower challenge"
    ICON = "🗼"
    DESCRIPTION = ("Events -> Challenge -> Tower Challenge: tap Challenge 5 times, "
                   "then go back.")
    START_HINT = "Start on the main Adventure screen."

    # --- reads ------------------------------------------------------------
    def _has(self, ctx: Context, region: RelRect, word: str) -> bool:
        return ctx.dry_run or word in self.text_in(ctx, region)

    def _result(self, ctx: Context) -> str | None:
        text = " ".join(t for t, _, _ in ocr_lines(ctx.frame())).lower()
        if "victory" in text:
            return "victory"
        if "defeat" in text:
            return "defeat"
        return None

    # --- steps ------------------------------------------------------------
    def _open_tower(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, "challenge"):
            return False
        if not self._has(ctx, FIRST_CARD, "tower challenge"):
            ctx.log.warning("%s: the Challenge tab did not open", self.name)
            return False
        if not self.tap(ctx, TOWER_CARD, "Tower Challenge"):
            return False
        return self._wait_tower(ctx)

    def _wait_tower(self, ctx: Context) -> bool:
        """Back on (or arrived at) the tower screen, through the black transition.
        A result screen still showing gets another dismiss tap."""
        end = time.time() + TRANSITION_TIMEOUT
        while time.time() < end:
            if self._has(ctx, TOWER_TITLE, "tower of infinity"):
                return True
            if not ctx.dry_run and self._result(ctx):
                if not self.tap(ctx, RESULT_DISMISS, "dismiss the result"):
                    return False
                continue
            if self.wait(ctx, 1.0):
                return False
        ctx.log.warning("%s: not on the Tower of Infinity screen", self.name)
        return False

    def _battle(self, ctx: Context) -> str | None:
        """Wait for the Victory/Defeat screen, checking every POLL seconds."""
        if ctx.dry_run:
            return "(dry run)"
        end = time.time() + BATTLE_TIMEOUT
        while time.time() < end:
            if self.wait(ctx, POLL):
                return None
            result = self._result(ctx)
            if result:
                return result
        return None

    def run_daily(self, ctx: Context) -> bool:
        if not self._open_tower(ctx):
            return False

        results: list[str] = []
        for n in range(1, RUNS + 1):
            if not self.tap(ctx, CHALLENGE_BTN, f"Challenge ({n}/{RUNS})"):
                return False
            result = self._battle(ctx)
            if result is None:
                if not ctx.should_stop():
                    ctx.log.warning("%s: no Victory/Defeat screen within %.0fs",
                                    self.name, BATTLE_TIMEOUT)
                return False
            results.append(result)
            ctx.log.info("%s: challenge %d -> %s", self.name, n, result)
            if not self.tap(ctx, RESULT_DISMISS, "dismiss the result"):
                return False
            if not self._wait_tower(ctx):
                return False

        ctx.log.info("%s: %d challenges (%d victories, %d defeats)", self.name,
                     len(results), results.count("victory"), results.count("defeat"))
        return go_events(ctx)  # back arrow -> the Events screen, for the next event
