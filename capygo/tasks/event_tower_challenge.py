"""Event: tower-challenge.

Starts on the Events screen (see event.py): Challenge tab -> Tower Challenge card ->
the "Tower of Infinity" screen. Then tap Challenge 5 times; each one is a battle that
ends on a "Victory" or "Defeat" screen (about 10s), checked every 10 seconds.
Finally the back arrow returns to the Events screen for the next event. "Auto Next
Level" stays as the player set it.

Each Challenge costs one ticket (10 a day, refilling). The user chose 5 per run to
stay well inside that, rather than reading the ticket count.

A defeat's result screen is dismissed by tapping the middle of the screen: "Tap to
close" sits right over the tower screen's "Auto Next Level" checkbox, so a tap there
that lands after the result closes would toggle it. Closing the result plays a short
black transition back to the tower screen.

A victory's screen has OK and "Next (3)" instead (2026-11-09: the first win in weeks;
the middle tap did nothing, and with Auto Next Level on the game went on to the next
floor by itself, again and again, while the bot waited for the tower screen). User:
on a win it auto progresses. Each floor counts as one of the RUNS fights, the ones
the game starts too (each is assumed to cost a ticket): under RUNS, the chain runs
on; at RUNS, OK stops it. The top floor's win has only OK.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .event import EventTask, card_at, go_events

TOWER_CARD = Rel(0.35, 0.165)
TOWER_TITLE = RelRect(0.25, 0.135, 0.50, 0.045)  # "Tower of Infinity <n>"
CHALLENGE_BTN = Rel(0.498, 0.943)
RESULT_DISMISS = Rel(0.5, 0.494)                 # middle of the result screen (defeat)
OK_BTN = Rel(0.327, 0.773)                       # a victory's OK, beside "Next (3)"
OK_ALONE = Rel(0.502, 0.772)                     # ... the top floor's, on its own

RUNS = 5                 # user: 5 per run, well inside the 10 daily tickets
POLL = 10.0              # check for the result screen this often (user)
BATTLE_TIMEOUT = 120.0
TRANSITION_TIMEOUT = 10.0
NEXT_TIMEOUT = 10.0      # a win's "Next (3)": the next floor's fight has begun by then


def read_result(frame) -> tuple[str | None, bool, Rel | None]:
    """A result screen: ("victory" / "defeat" / None, whether "Next" shows - a win
    that Auto Next Level carries on from -, where its OK button is if it reads)."""
    h, w = frame.shape[:2]
    lines = [(t.strip().lower(), cx / w, cy / h) for t, cx, cy in ocr_lines(frame)]
    text = " ".join(t for t, _, _ in lines)
    result = "victory" if "victory" in text else "defeat" if "defeat" in text else None
    chained = any(t.startswith("next") and y > 0.7 for t, _, y in lines)
    ok = next((Rel(x, y) for t, x, y in lines if t in ("ok", "0k") and y > 0.7), None)
    return result, chained, ok


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
        return read_result(ctx.frame())[0]

    def _dismiss(self, ctx: Context) -> bool:
        """Close a result screen: a victory's OK (where it reads, which also stops
        Auto Next Level's chain), else the middle of the screen."""
        result, chained, ok = read_result(ctx.frame())
        if result == "victory":
            return self.tap(ctx, ok or (OK_BTN if chained else OK_ALONE), "OK")
        return self.tap(ctx, RESULT_DISMISS, "dismiss the result")

    # --- steps ------------------------------------------------------------
    def _open_tower(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, "challenge"):
            return False
        card = card_at(ctx, "tower challenge", TOWER_CARD)
        if card is None:
            ctx.log.warning("%s: no Tower Challenge card on the Challenge tab", self.name)
            return False
        if not self.tap(ctx, card, "Tower Challenge"):
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
                if not self._dismiss(ctx):
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

    def _next_floor(self, ctx: Context) -> bool:
        """After a win with Auto Next Level on: the result closes on its own when the
        next floor's fight begins. False if it doesn't (or a stop)."""
        end = time.time() + NEXT_TIMEOUT
        while time.time() < end:
            if self.wait(ctx, 1.0):
                return False
            if self._result(ctx) is None:
                return True
        return False

    def run_daily(self, ctx: Context) -> bool:
        if not self._open_tower(ctx):
            return False

        results: list[str] = []
        while len(results) < RUNS:
            if not self.tap(ctx, CHALLENGE_BTN, f"Challenge ({len(results) + 1}/{RUNS})"):
                return False
            while True:  # this fight, then any the game starts after a win
                result = self._battle(ctx)
                if result is None:
                    if not ctx.should_stop():
                        ctx.log.warning("%s: no Victory/Defeat screen within %.0fs",
                                        self.name, BATTLE_TIMEOUT)
                    return False
                results.append(result)
                ctx.log.info("%s: challenge %d -> %s", self.name, len(results), result)
                if ctx.dry_run or result != "victory" or len(results) >= RUNS:
                    break
                if not read_result(ctx.frame())[1]:
                    break  # the top floor: only OK
                ctx.log.info("%s: the game goes on to the next floor (Auto Next Level)",
                             self.name)
                if not self._next_floor(ctx):
                    if ctx.should_stop():
                        return False
                    break  # still showing: closed below, like any result
            if not self._dismiss(ctx):
                return False
            if not self._wait_tower(ctx):
                return False

        ctx.log.info("%s: %d challenges (%d victories, %d defeats)", self.name,
                     len(results), results.count("victory"), results.count("defeat"))
        return go_events(ctx)  # back arrow -> the Events screen, for the next event
