"""Event: tower-challenge.

Starts on the Events screen (see event.py): Challenge tab -> Tower Challenge card ->
the tower screen ("Tower of <name> <n>": Tower of Infinity 10 was followed by Tower
of Origin 1, 2026-11-10, so only "tower of" is checked). Then tap Challenge 5 times; each one is a battle that
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

A tower has 10 floors. The bar at the left reads "n/10" for the floor being fought:
10/10 means floor 10 is next, and the tower isn't cleared yet (2026-11-17: the bot
took 10/10 for cleared and tapped the bar's Clear Reward chest, which did nothing
useful). Winning floor 10 (a win with only OK) leads to a "Congrats" screen:
"Congratulations on clearing Tower of <name> <n>. Please claim your reward", with a
chest in the middle and the tower's name moved down to a plaque at the bottom. The
tower screen's title spot is empty there, so a Challenge tap on it looked like a fight
that began, and the bot waited 120s for a result (2026-11-17). The same screen shows
when the tower is opened later with the reward unclaimed. The chest opens a "Rewards"
popup; its "Tap to close" sits over "Auto Next Level" again, so it's closed with a tap
above it. Then the next tower's Floor 1 shows (Tower of Origin 1 -> 2, 1/10) and
Challenge carries on.

A Challenge tap can do nothing (2026-11-10: the tap ~1.5s after a defeat's screen
closed; the bot then waited 120s for a result that never came). So each tap is
checked: a fight's screen has the tower's name higher up (above "Floor <n>"), so the
title leaving its spot means the fight began. If it's still there, Challenge again.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .event import EventTask, card_at, go_events

TOWER_CARD = Rel(0.35, 0.165)
TOWER_TITLE = RelRect(0.25, 0.135, 0.50, 0.045)  # "Tower of <name> <n>"
CHALLENGE_BTN = Rel(0.498, 0.943)
RESULT_DISMISS = Rel(0.5, 0.494)                 # middle of the result screen (defeat)
OK_BTN = Rel(0.327, 0.773)                       # a victory's OK, beside "Next (3)"
OK_ALONE = Rel(0.502, 0.772)                     # ... the top floor's, on its own
CLAIM_CHEST = Rel(0.502, 0.641)                  # the Congrats screen's chest
REWARDS_CLOSE = Rel(0.5, 0.2)                    # above the Rewards popup
REWARDS_TOP = 0.32       # the popup's "Rewards" title reads at y ~0.37; the tower
                         # screen's own "Rewards" (the floor's rewards) at ~0.28

RUNS = 5                 # user: 5 per run, well inside the 10 daily tickets
POLL = 10.0              # check for the result screen this often (user)
BATTLE_TIMEOUT = 120.0
TRANSITION_TIMEOUT = 10.0
NEXT_TIMEOUT = 10.0      # a win's "Next (3)": the next floor's fight has begun by then
CLAIM_TIMEOUT = 20.0     # the Congrats chest tapped -> the next tower's screen
CHEST_RETAP = 4.0        # the Congrats screen still up this long after a chest tap
START_TIMEOUT = 5.0      # Challenge tapped -> the tower screen gone (the fight began)
START_TRIES = 3          # Challenge taps before giving up
POPUP_WORDS = ("top-up", "top up", "purchase", "not enough")  # don't tap over these
CLEARED = "cleared"      # _battle: the Congrats screen showed, no fight


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


def claim_screen(frame) -> bool:
    """The "Congrats" screen of a cleared tower: "Please claim your reward"."""
    text = "".join(t for t, _, _ in ocr_lines(frame)).lower().replace(" ", "")
    return "claimyourreward" in text or "congratulationsonclearing" in text


def rewards_popup(frame) -> bool:
    """The Rewards popup the Congrats chest opens."""
    h = frame.shape[0]
    return any(t.strip().lower() == "rewards" and cy / h > REWARDS_TOP
               for t, _, cy in ocr_lines(frame))


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
            if self._has(ctx, TOWER_TITLE, "tower of"):
                return True
            if not ctx.dry_run and claim_screen(ctx.frame()):
                return self._claim_tower(ctx)
            if not ctx.dry_run and self._result(ctx):
                if not self._dismiss(ctx):
                    return False
                continue
            if self.wait(ctx, 1.0):
                return False
        ctx.log.warning("%s: not on the tower screen", self.name)
        return False

    def _claim_tower(self, ctx: Context) -> bool:
        """The Congrats screen of a cleared tower: tap its chest, close the Rewards
        popup, and wait for the next tower's screen."""
        ctx.log.info("%s: the tower is cleared -> claim its reward", self.name)
        if not self.tap(ctx, CLAIM_CHEST, "the reward chest"):
            return False
        tapped = time.time()
        end = time.time() + CLAIM_TIMEOUT
        while time.time() < end:
            if self.wait(ctx, 1.0):
                return False
            frame = ctx.frame()
            if claim_screen(frame):
                if time.time() - tapped >= CHEST_RETAP:
                    if not self.tap(ctx, CLAIM_CHEST, "the reward chest again"):
                        return False
                    tapped = time.time()
                continue
            if "tower of" in self.text_in(ctx, TOWER_TITLE):
                ctx.log.info("%s: on to %s", self.name, self.text_in(ctx, TOWER_TITLE))
                return True
            if rewards_popup(frame):
                if not self.tap(ctx, REWARDS_CLOSE, "close the Rewards"):
                    return False
        ctx.log.warning("%s: the next tower didn't show after claiming the reward",
                        self.name)
        return False

    def _start_fight(self, ctx: Context, n: int) -> bool:
        """Tap Challenge until the fight begins: the tower title leaves its spot.
        A tap the game ignored gets another, up to START_TRIES; not over a popup.
        A Congrats screen (its title spot is empty too) is claimed first."""
        for attempt in range(1, START_TRIES + 1):
            what = f"Challenge ({n}/{RUNS})" + (f", try {attempt}" if attempt > 1 else "")
            if not self.tap(ctx, CHALLENGE_BTN, what):
                return False
            if ctx.dry_run:
                return True
            began = self._began(ctx)
            if began is None:
                return False
            if began:
                return True
            text = " ".join(t for t, _, _ in ocr_lines(ctx.frame())).lower()
            if any(w in text for w in POPUP_WORDS):
                ctx.log.warning("%s: a popup over the tower screen; not tapping again",
                                self.name)
                return False
        ctx.log.warning("%s: Challenge didn't start a fight after %d taps",
                        self.name, START_TRIES)
        return False

    def _began(self, ctx: Context) -> bool | None:
        """After a Challenge tap: True once the fight began, False to tap again,
        None on a stop or a failed claim."""
        end = time.time() + START_TIMEOUT
        while time.time() < end:
            if "tower of" not in self.text_in(ctx, TOWER_TITLE):
                if not claim_screen(ctx.frame()):
                    return True
                # the last floor's OK led to the Congrats screen; the tap did nothing
                return False if self._claim_tower(ctx) else None
            if self.wait(ctx, 0.5):
                return None
        ctx.log.info("%s: still on the tower screen %.0fs after Challenge",
                     self.name, START_TIMEOUT)
        return False

    def _battle(self, ctx: Context) -> str | None:
        """Wait for the Victory/Defeat screen, checking every POLL seconds. CLEARED
        if the Congrats screen shows instead: the Challenge tap began no fight."""
        if ctx.dry_run:
            return "(dry run)"
        end = time.time() + BATTLE_TIMEOUT
        while time.time() < end:
            if self.wait(ctx, POLL):
                return None
            frame = ctx.frame()
            result = read_result(frame)[0]
            if result:
                return result
            if claim_screen(frame):
                return CLEARED
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
        claims = 0  # Congrats screens met in place of a fight
        while len(results) < RUNS:
            if not self._start_fight(ctx, len(results) + 1):
                return False
            while True:  # this fight, then any the game starts after a win
                result = self._battle(ctx)
                if result is None:
                    if not ctx.should_stop():
                        ctx.log.warning("%s: no Victory/Defeat screen within %.0fs",
                                        self.name, BATTLE_TIMEOUT)
                    return False
                if result == CLEARED:
                    break
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
            if result == CLEARED:
                if claims:  # a second cleared tower in one run: something's off
                    ctx.log.warning("%s: the Congrats screen again", self.name)
                    return False
                claims += 1
                ctx.log.info("%s: no fight began: the Congrats screen", self.name)
                if not self._claim_tower(ctx):
                    return False
                continue
            if not self._dismiss(ctx):
                return False
            if not self._wait_tower(ctx):
                return False

        ctx.log.info("%s: %d challenges (%d victories, %d defeats)", self.name,
                     len(results), results.count("victory"), results.count("defeat"))
        return go_events(ctx)  # back arrow -> the Events screen, for the next event
