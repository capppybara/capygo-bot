"""Event: auto-arena.

Starts on the Events screen: Arena tab -> Arena card (1st) -> the arena leaderboard
("Diamond Battle"; the league name changes, so only "battle" is checked). Your own
row sits in a banner above the Challenge button (power under your name, points at
the right). Challenge opens a "Challenge" popup listing 4 opponents (power, points,
an "x1 Challenge" button each), plus a ticket "+", Free Refresh, and a round X.

The plan (user, 2026-10-03): attack RUNS times. Goal: fight the highest-points
opponent you can beat. Each attack:
  1. Read your power and points from the banner.
  2. Tap Challenge and pick (user, 2026-10-04; powers come in B and T, 1T = 1000B,
     compared in trillions). Beatable = power < 1.2x yours. First choice: the
     beatable opponent with the most points among those MORE than 10 points above
     yours. None -> use the Free Refresh (only while it says "Free") and look
     again. Still none -> the beatable opponent with the most points. Nobody
     beatable at all -> stop the arena and flag it (the user handles it by hand).
  3. Tap its "x1 Challenge": a black loading screen, then the fight screen. Give it
     a couple of seconds, then tap Skip.
  4. The result ("Victory"/"Defeat", points +/-) has an OK button; OK goes back to
     the leaderboard, which reloads (empty for a moment). Repeat.

Out of tickets, x1 Challenge opens a "Purchase" popup (Arena Tickets, 10 purple
cubes) instead of a fight: that means done (user). It closes the popup and the list
and finishes; it never taps Purchase.

Every screen change is waited out: poll until the next screen shows, then let it
settle before tapping (user). If neither the fight nor the Purchase popup shows, it
stops and flags it.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from decimal import Decimal

import cv2

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import _crop, find_sprite, save_snapshot, tap_to_close_up
from .event import EventTask, go_events
from . import pvp
from .profile import close_profile, is_open as profile_open, to_trillions

ARENA_CARD = Rel(0.35, 0.165)                    # 1st card on the Arena tab
CARD_NAME = RelRect(0.12, 0.095, 0.50, 0.05)     # "Arena"
ARENA_TITLE = RelRect(0.20, 0.075, 0.42, 0.05)   # "Diamond Battle" (league name)
MY_POWER = RelRect(0.43, 0.79, 0.19, 0.04)       # your banner: "4.72T" under your name
MY_POINTS = RelRect(0.73, 0.765, 0.19, 0.05)     # your banner: "1394" at the right
CHALLENGE_BTN = Rel(0.498, 0.932)                # orange Challenge, tickets "0/1" under it
POPUP_TITLE = RelRect(0.30, 0.29, 0.40, 0.05)    # "Challenge"
FREE_REFRESH = Rel(0.718, 0.379)                 # green Free Refresh (new opponents)
REFRESH_LABEL = RelRect(0.62, 0.35, 0.20, 0.06)  # "Free Refresh", then "20 Refresh"
OPPONENT_BTNS = [Rel(0.718, y) for y in (0.457, 0.543, 0.628, 0.714)]
# Each row's picture, left of its power: opens the opponent's profile for the
# fight log (pvp.py). NOT checked on a live list yet - a guess from the layout.
OPPONENT_PICS = [Rel(0.215, y) for y in (0.457, 0.543, 0.628, 0.714)]  # "x1 Challenge"
ROW_Y = [0.468, 0.554, 0.640, 0.724]             # each row's power/points line
ROW_H = 0.034
POWER_X = (0.29, 0.46)                           # power column (left of the points)
POINTS_X = (0.47, 0.60)                          # points column
LIST_READS = 3                                   # re-read the list while a row is missing
POPUP_CLOSE = Rel(0.5, 0.825)                    # round X under the list
PURCHASE_TITLE = RelRect(0.30, 0.31, 0.40, 0.045)  # "Purchase" = out of tickets
PURCHASE_CLOSE = Rel(0.5, 0.714)                 # its round X (over row 4: tap once)
SKIP_BTN = Rel(0.609, 0.848)                     # fight screen: green Skip (next to x4)
SKIP_LABEL = RelRect(0.53, 0.825, 0.16, 0.045)
RESULT_TITLE = RelRect(0.25, 0.37, 0.50, 0.08)   # "Victory" / "Defeat"
OK_BTN = Rel(0.5, 0.937)                         # result screen (replay is at the right
OK_LABEL = RelRect(0.35, 0.915, 0.30, 0.05)      # edge above it - never tap that)
MAX_POWER_RATIO = Decimal("1.2")                 # user: fight only below 1.2x my power
MIN_POINT_GAP = 10                               # user: prefer > 10 points above mine
RUNS = 5

POLL = 0.5             # how often a wait checks the screen
SETTLE = 1.0           # pause once a screen shows, before tapping in it
LOAD_TIMEOUT = 10.0    # leaderboard (re)load, opponent list
FIGHT_TIMEOUT = 15.0   # black loading screen -> fight screen
FIGHT_SETTLE = 2.0     # user: give the fight screen a couple of seconds before Skip
SKIP_RETRY = 6.0       # no result this long after Skip -> tap Skip again
RESULT_TIMEOUT = 30.0
LIST_TIMEOUT = 5.0     # Challenge -> opponent list; then clear the screen and retry
CHALLENGE_TRIES = 3
DISMISS = Rel(0.5, 0.87)  # the board's "Maintain current ranking..." line: inert
NO_TICKETS = "no tickets"

POWER_TEXT = re.compile(r"\d[\d.,]*\s*[KMBT]", re.IGNORECASE)  # a unit is required


@dataclass
class Opponent:
    row: int          # 0-3, top to bottom
    power: Decimal    # in trillions
    points: int


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def _power(text: str) -> Decimal | None:
    """'2.81T' / '905.85B' -> trillions. None without a unit: a dropped unit would
    make a strong opponent look weak."""
    m = POWER_TEXT.search(text or "")
    return to_trillions(m.group(0)) if m else None


def _points(text: str) -> int | None:
    digits = (text or "").replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


def read_me(frame) -> tuple[Decimal | None, int | None]:
    """Your power (trillions) and points from the banner above Challenge."""
    power = points = None
    for text, _, _ in ocr_lines(_crop(frame, MY_POWER)):
        power = power or _power(text)
    for text, _, _ in ocr_lines(_crop(frame, MY_POINTS)):
        points = points or _points(text)
    return power, points


def _cell(frame, xs: tuple[float, float], y: float) -> str:
    crop = _crop(frame, RelRect(xs[0], y - ROW_H / 2, xs[1] - xs[0], ROW_H))
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return " ".join(t for t, _, _ in ocr_lines(crop))


def read_opponents(frame) -> list[Opponent]:
    """The opponents in the Challenge popup whose power and points both read. Each
    value gets its own small crop: one read of the whole list sometimes took the T
    of "2.46T" for a 1, which dropped that row."""
    out = []
    for row, y in enumerate(ROW_Y):
        power, points = _power(_cell(frame, POWER_X, y)), _points(_cell(frame, POINTS_X, y))
        if power is not None and points is not None:
            out.append(Opponent(row, power, points))
    return out


def pick_opponent(opponents: list[Opponent], my_power: Decimal,
                  min_points: int | None = None) -> Opponent | None:
    """The most points among those below MAX_POWER_RATIO x my power (ties: the
    weaker one); with min_points, only those with more points than that."""
    pool = [o for o in opponents if o.power < my_power * MAX_POWER_RATIO
            and (min_points is None or o.points > min_points)]
    return max(pool, key=lambda o: (o.points, -o.power), default=None)


def board_ready(frame) -> bool:
    """The leaderboard is up and loaded (your banner reads; it's blank while the
    board reloads after a fight)."""
    return "battle" in _words(frame, ARENA_TITLE) and read_me(frame)[0] is not None


def list_open(frame) -> bool:
    return "challenge" in _words(frame, POPUP_TITLE)


def fight_up(frame) -> bool:
    return "skip" in _words(frame, SKIP_LABEL)


def result_up(frame) -> bool:
    """The fight's result screen: its OK button, or the big Victory/Defeat."""
    if "ok" in _words(frame, OK_LABEL).split():
        return True
    title = _words(frame, RESULT_TITLE)
    return "victory" in title or "defeat" in title


def purchase_up(frame) -> bool:
    return "purchase" in _words(frame, PURCHASE_TITLE)


@register("auto-arena")
class AutoArena(EventTask):
    TITLE = "Auto Arena"
    LABEL = "Arena attacks"
    ICON = "⚔️"
    DESCRIPTION = ("Events -> Arena -> Arena: attack 5 times, each time the opponent "
                   "below 1.2x your power with the most points, preferring those more "
                   "than 10 points above you, then go back.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, "arena"):
            return False
        if not ctx.dry_run and "arena" not in self.text_in(ctx, CARD_NAME):
            ctx.log.warning("%s: no Arena card on the Arena tab", self.name)
            return False
        if not self.tap(ctx, ARENA_CARD, "Arena"):
            return False
        if ctx.dry_run:
            return go_events(ctx)

        results: list[str] = []
        start_points = None
        for n in range(1, RUNS + 1):
            if not self._wait_for(ctx, "the arena leaderboard", board_ready,
                                  LOAD_TIMEOUT):
                return False
            power, points = read_me(ctx.frame())
            start_points = start_points if start_points is not None else points
            ctx.log.info("%s: attack %d/%d - you: power %sT, %s points", self.name, n,
                         RUNS, power, points)
            result = self._attack(ctx, n, power, points)
            if result is None:
                return False
            if result == NO_TICKETS:
                ctx.log.info("%s: out of tickets after %d attack(s) -> done", self.name,
                             n - 1)
                break
            results.append(result)
            ctx.log.info("%s: attack %d -> %s", self.name, n, result)

        end_points = None
        if self._wait_for(ctx, "the arena leaderboard", board_ready, LOAD_TIMEOUT):
            end_points = read_me(ctx.frame())[1]
        ctx.log.info("%s: %d attacks (%d victories, %d defeats), points %s -> %s",
                     self.name, len(results), results.count("victory"),
                     results.count("defeat"), start_points, end_points)
        return go_events(ctx)  # back arrow -> the Events screen, for the next event

    def _attack(self, ctx: Context, n: int, my_power: Decimal,
                my_points: int | None) -> str | None:
        """One attack from the loaded leaderboard: pick, fight, Skip, OK. The result
        ("victory"/"defeat"/"unknown"), NO_TICKETS (back on the leaderboard), or
        None if it went wrong (logged)."""
        for attempt in range(1, CHALLENGE_TRIES + 1):
            if not self.tap(ctx, CHALLENGE_BTN, "Challenge"):
                return None
            if self._wait_for(ctx, None, list_open, LIST_TIMEOUT):
                break
            if ctx.should_stop():
                return None
            ctx.log.info("%s: the opponent list didn't open (try %d/%d); clearing the "
                         "screen and trying again", self.name, attempt, CHALLENGE_TRIES)
            if not self._clear_to_board(ctx):
                return None
        else:
            ctx.log.warning("%s: the opponent list didn't open after %d tries",
                            self.name, CHALLENGE_TRIES)
            return None
        pick = self._choose(ctx, my_power, my_points)
        if pick is None:
            self.flag(ctx, f"stopped at attack {n}/{RUNS} - no opponent below "
                           f"{MAX_POWER_RATIO}x your power ({my_power * MAX_POWER_RATIO:.2f}T"
                           f"; you: {my_power}T, {my_points} points), even after a "
                           f"refresh. Handle the rest by hand.")
            return None
        ctx.log.info("%s: pick row %d (%d points, %sT)", self.name, pick.row + 1,
                     pick.points, pick.power)
        # The fight log (user, 2026-10-09): look at the opponent's profile first.
        opponent = pvp.scout(ctx, OPPONENT_PICS[pick.row], "arena")
        if not ctx.dry_run and not self._back_on_list(ctx):
            return None
        if not self.tap(ctx, OPPONENT_BTNS[pick.row], f"x1 Challenge (row {pick.row + 1})"):
            return None
        if not self._wait_for(ctx, "the fight screen",
                              lambda f: fight_up(f) or purchase_up(f), FIGHT_TIMEOUT,
                              settle=0):
            self.flag(ctx, f"stopped at attack {n}/{RUNS} - the fight didn't start "
                           f"(neither the fight nor the ticket popup showed). Check the "
                           f"arena.")
            return None
        if purchase_up(ctx.frame()):  # no tickets: never buy, just close it and the list
            if not self.tap(ctx, PURCHASE_CLOSE, "close the ticket Purchase popup"):
                return None
            if not self.tap(ctx, POPUP_CLOSE, "close the opponent list"):
                return None
            return NO_TICKETS
        if self.wait(ctx, FIGHT_SETTLE):  # user: give the fight a couple of seconds
            return None
        result = self._finish_fight(ctx)
        pvp.record(ctx, "arena", result or "no result", my_power=my_power,
                   my_points=my_points, row=pick.row + 1, list_power=pick.power,
                   list_points=pick.points, opponent=opponent)
        return result

    def _back_on_list(self, ctx: Context) -> bool:
        """After the profile look: the opponent list must be showing again before a
        row's Challenge is tapped. A profile still up gets closed once more."""
        if profile_open(ctx.frame()):
            close_profile(ctx)
        if self._wait_for(ctx, None, list_open, LIST_TIMEOUT):
            return True
        shot = save_snapshot(ctx, "arena-after-profile")
        self.flag(ctx, "the opponent list wasn't showing after looking at a profile"
                       + (f" (screen saved: {shot})" if shot else "") + ". Check the arena.")
        return False

    def _clear_to_board(self, ctx: Context) -> bool:
        """Something took the Challenge tap (2026-10-04: on the first visit of a new
        season the list didn't open; most likely a season popup ate the tap). Close
        whatever is on top (an X, or a "Tap to close" popup) and wait for the
        leaderboard again."""
        frame = ctx.frame()
        x = find_sprite(ctx, frame, "close_x.png")
        if x is not None:
            if not self.tap(ctx, x, "close X"):
                return False
        elif tap_to_close_up(frame):
            if not self.tap(ctx, DISMISS, "dismiss the popup"):
                return False
        return self._wait_for(ctx, "the arena leaderboard", board_ready, LOAD_TIMEOUT)

    def _finish_fight(self, ctx: Context) -> str | None:
        """Skip the fight and close its result with OK, ending on the leaderboard.
        "victory"/"defeat", "unknown" if the result wasn't read, or None on a
        timeout or stop.

        2026-10-04 (first Master Battle fight): the game was back on the
        leaderboard while the old code still waited for the result's OK and kept
        tapping Skip, so the run failed although the fight was won. Now the
        leaderboard coming back also means the fight is over, Skip is only tapped
        while the fight screen shows (the result screen still shows a dimmed Skip,
        so the result is checked first), and the screen is saved if Skip needs a
        second tap, to see what was showing."""
        end = time.time() + RESULT_TIMEOUT
        last_skip = None
        saved = False
        while time.time() < end:
            frame = ctx.frame()
            if result_up(frame):
                if self.wait(ctx, SETTLE):
                    return None
                text = self.text_in(ctx, RESULT_TITLE)
                result = next((r for r in ("victory", "defeat") if r in text), "unknown")
                if not self.tap(ctx, OK_BTN, "OK"):
                    return None
                return result
            if board_ready(frame):
                ctx.log.info("%s: back on the leaderboard - the fight is over", self.name)
                return "unknown"
            if fight_up(frame) and (last_skip is None
                                    or time.time() - last_skip >= SKIP_RETRY):
                if last_skip is not None and not saved:
                    saved = True
                    shot = save_snapshot(ctx, "arena-skip-again")
                    ctx.log.info("%s: no result yet; tapping Skip again%s", self.name,
                                 f" (screen saved: {shot})" if shot else "")
                if not self.tap(ctx, SKIP_BTN, "Skip"):
                    return None
                last_skip = time.time()
                continue
            if self.wait(ctx, POLL):
                return None
        ctx.log.warning("%s: no result screen within %.0fs", self.name, RESULT_TIMEOUT)
        return None

    def _wait_for(self, ctx: Context, what: str | None, check, timeout: float,
                  settle: float = SETTLE) -> bool:
        """Poll until check(frame) holds, then let the screen settle. False on a
        timeout (logged, if `what` names the screen) or a stop."""
        end = time.time() + timeout
        while True:
            if check(ctx.frame()):
                return not self.wait(ctx, settle)
            if time.time() >= end:
                if what:
                    ctx.log.warning("%s: %s didn't show within %.0fs", self.name, what,
                                    timeout)
                return False
            if self.wait(ctx, POLL):
                return False

    def _choose(self, ctx: Context, my_power: Decimal,
                my_points: int | None) -> Opponent | None:
        """Pick from the open Challenge list (user, 2026-10-04): the most points
        among opponents below 1.2x my power that have more than 10 points over
        mine. None of those -> use the Free Refresh once (only while it says
        "Free", so no gems) and look again. Still none -> the most points below
        1.2x my power. None only if nobody is below 1.2x."""
        opponents = self._read_list(ctx)
        if my_points is None:  # can't tell who's above me: take the best beatable
            ctx.log.warning("%s: your points didn't read; picking the best opponent "
                            "below %sx your power", self.name, MAX_POWER_RATIO)
            return pick_opponent(opponents, my_power)
        floor = my_points + MIN_POINT_GAP
        pick = pick_opponent(opponents, my_power, floor)
        if pick is not None:
            return pick
        if "free" in self.text_in(ctx, REFRESH_LABEL):
            ctx.log.info("%s: no opponent below %sx your power with more than %d "
                         "points; Free Refresh", self.name, MAX_POWER_RATIO, floor)
            if not self.tap(ctx, FREE_REFRESH, "Free Refresh"):
                return None
            if not self._wait_for(ctx, "the refreshed list", list_open, LOAD_TIMEOUT):
                return None
            opponents = self._read_list(ctx)
            pick = pick_opponent(opponents, my_power, floor)
            if pick is not None:
                return pick
        else:
            ctx.log.info("%s: no free refresh left", self.name)
        pick = pick_opponent(opponents, my_power)
        if pick is not None:
            ctx.log.info("%s: nobody with more than %d points below %sx your power; "
                         "taking the best one below %sx", self.name, floor,
                         MAX_POWER_RATIO, MAX_POWER_RATIO)
        return pick

    def _read_list(self, ctx: Context) -> list[Opponent]:
        """Read the open Challenge list, re-reading while a row is missing."""
        opponents = read_opponents(ctx.frame())
        for _ in range(LIST_READS - 1):  # a row can still misread now and then
            if len(opponents) == len(ROW_Y) or self.wait(ctx, POLL):
                break
            opponents = read_opponents(ctx.frame())
        for o in opponents:
            ctx.log.info("%s:   row %d: power %sT, %d points", self.name, o.row + 1,
                         o.power, o.points)
        return opponents
