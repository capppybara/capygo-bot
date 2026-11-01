"""Task: arena-sniping (user, 2026-10-31).

The Arena's day ends at 16:00 UTC (the card's "Ends" and the board's timer count down
to it). This waits for the Start time (15:45 UTC by default: 8:45 AM Pacific in
summer, 7:45 AM in winter), restarts the game a minute before, opens the Arena -
its landing page is the leaderboard - and then does one of two things:

  Hold the lead (the default): check your place every 10 seconds, until 20 seconds
  before the end. Ahead of the next place by the set lead: no attack. Not first, or
  the next place catching up: attack until the lead is back. The board only updates
  on entry (or after a fight), so a check is: the back arrow at the bottom left,
  then the Arena card again.

  Fights: that many fights, then done (or the end, if it comes first).

Who to fight (user): 2nd place; if you can't beat them, 3rd place. The board is only
read for points; a player's power is read off the Challenge list alone (user), so
they're found there by their points, and only then judged. "Can't beat" = power at
or above the ratio x yours, a player you rarely beat (pvp.rarely_beaten), or one who
beat you this run. Your own row doesn't count: placed 2nd or 3rd yourself, the other
one is the target.

The list is refreshed until the target shows, up to "Refreshes per fight" (20 gems
each after the free one). Points move, so every LOOK_BACK_AFTER refreshes it goes
back to the board for a fresh look (your place, and the target's points). Out of
refreshes, or neither place beatable: the most points below the ratio on the list.

Out of tickets, x1 Challenge opens the Purchase popup: it buys TICKETS_PER_BUY at once
(user: for speed) and taps x1 Challenge again. Never anything that looks like real
money (martial_arts_tournament.purchase_popup). A fight that doesn't finish, or a
board that doesn't come back, restarts the game (up to RESTARTS) and carries on.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ..geometry import Rel
from ..task import Context, Param, get_task, register
from . import pvp
from .daily import go_home, tap, wait
from .event import TABS, card_at, go_events, on_events
from .event_arena import (ARENA_CARD, FIGHT_SETTLE, FIGHT_TIMEOUT, FREE_REFRESH, LOAD_TIMEOUT,
                          OPPONENT_BTNS, OPPONENT_PICS, POPUP_CLOSE, REFRESH_LABEL, Opponent,
                          board_points, board_ready, fight_up, list_open, purchase_up,
                          read_me, read_opponents)
from .martial_arts_tournament import CUTOFF_MARGIN, MartialArtsTournament, _Tagged, _words
from .restart import restart_game

SNIPE_UTC = "15:45"        # user: 8:45 AM Pacific, summer time
STOP_UTC = "16:00"         # the Arena's day ends (card "Ends" + board timer, seen 5 days)
CHECK_EVERY = 10.0         # user: seconds between looks at your place
ENTER_GUESS = 4.0          # back out + re-enter, until a run has timed one
TICKETS_PER_BUY = 5        # user: 5 at a time, for speed
RESTARTS = 3               # a missed check late in the window can lose first place
MAX_LOOKS = 4              # reads of the board or the list while a row is missing
LOOK_GAP = 0.4
LOOK_BACK_AFTER = 10       # refreshes before a fresh look at the board (~25s)
TARGET_RANKS = (2, 3)      # user: 2nd place, else 3rd place
POWER_SLACK = Decimal("0.03")  # the same player, by power: within 3% (a misread digit)

PLACE_Y = (168, 245, 321)  # px: the middle of the board's 1st, 2nd and 3rd rows
BACK_ARROW = Rel(123 / 642, 900 / 951)  # the board's back arrow, bottom left
BACK_TIMEOUT = 3.0         # back arrow -> the Events screen

BLOCKED, NO_TARGET, LOOK_AGAIN, CANT_BUY = "blocked", "no target", "look again", "can't buy"


class Place:
    """One leaderboard row. points is None if it didn't read."""

    def __init__(self, rank: int, points: int | None):
        self.rank, self.points = rank, points

    def __repr__(self) -> str:
        return f"{self.rank}: {self.points}"


def read_board(frame) -> list[Place]:
    """The points of the 1st, 2nd and 3rd rows of the leaderboard."""
    return [Place(rank, board_points(frame, y)) for rank, y in enumerate(PLACE_Y, 1)]


def lead_over_next(places: list[Place], points: int | None) -> int | None:
    """Your lead over the next place, if the top row is yours (your banner's points;
    tied, the lead is 0 either way). None if it isn't, or the rows didn't read."""
    if points is None or places[0].points != points or places[1].points is None:
        return None
    return points - places[1].points


def targets(places: list[Place], points: int | None) -> list[Place]:
    """2nd and 3rd place, without your own row. Only one row is yours: tied with
    someone, the other row with those points is them, and the list finds them by it."""
    mine = next((s for s in places if s.points == points), None)
    return [s for s in places if s.rank in TARGET_RANKS and s is not mine
            and s.points is not None]


def close_power(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= POWER_SLACK * b


def in_window(start: str, stop: str, now: datetime | None = None
              ) -> tuple[datetime, datetime]:
    """(start, stop) as datetimes, both UTC: today's window, or the next day's once
    today's is over. Started inside the window, `start` is already past."""
    def at_time(day: datetime, hhmm: str) -> datetime:
        hour, minute = (int(v) for v in hhmm.strip().split(":"))
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    now = now or datetime.now(timezone.utc)
    begin, end = at_time(now, start), at_time(now, stop)
    if end <= begin:
        end += timedelta(days=1)
    if now >= end:
        begin, end = begin + timedelta(days=1), end + timedelta(days=1)
    return begin, end


@register("arena-sniping")
class ArenaSniping(MartialArtsTournament):
    TITLE = "Arena Sniping"
    ICON = "🎯"
    DESCRIPTION = ("Near the end of the Arena's day: hold first place by a set lead, "
                   "checking every 10 seconds, or fight a set number of times. Fights "
                   "2nd place, or 3rd if you can't beat them.")
    START_HINT = ("Start any time before the Start time and leave it running: it waits, "
                  "restarts the game a minute before, and opens the Arena itself.")
    TAG = "arena-snipe"
    TICKETS_PER_BUY = TICKETS_PER_BUY
    PARAMS = [
        Param("snipe_utc", "str", SNIPE_UTC, "Start (UTC, HH:MM)",
              help="when to start; the game restarts 1 minute before. It ends at 16:00 UTC"),
        Param("lead", "int", 20, "Lead (points)", min=1, max=9999,
              help="with Hold the lead on: attack whenever you're ahead of the next "
                   "place by less than this"),
        Param("hold_lead", "bool", True, "Hold the lead", beside="lead", locks="fights",
              help="check your place every 10 seconds until the end, and attack only "
                   "when the lead is short. Off: do the set number of fights"),
        Param("fights", "int", 5, "Fights", min=1, max=99,
              help="with Hold the lead off: fight this many times, buying tickets if needed"),
        Param("ratio", "float", 1.2, "Power ratio", min=0.5, max=5,
              help="a place counts as beatable below this x your power"),
        Param("max_refreshes", "int", 50, "Refreshes per fight", min=0, max=500,
              help="how many times to refresh the list looking for 2nd or 3rd place, per "
                   "fight (20 gems each after the free one)"),
        Param("scout", "bool", True, "Log opponents",
              help="open each opponent's profile before the fight: it logs them and "
                   "skips players you rarely beat (about 4s a fight)"),
        Param("stop_utc", "str", STOP_UTC, "Stop (UTC, HH:MM)", hidden=True,
              help="the end of the Arena's day; for tests: -p stop_utc=HH:MM"),
    ]

    def run(self, ctx: Context) -> None:
        self._log = _Tagged(ctx.log, {"tag": self.TAG})
        p = self.params
        self._arena = get_task("auto-arena")  # the arena's screens and fight, shared
        self._arena.name = self.TAG
        self._reset_run()
        try:
            at, end = in_window(p["snipe_utc"], p["stop_utc"])
        except ValueError:
            self._log.warning("the Start time isn't HH:MM: %s", p["snipe_utc"])
            return
        deadline = end - timedelta(seconds=CUTOFF_MARGIN)
        self._log.info("%s, from %s (%s UTC) to %s UTC",
                       f"holding a {p['lead']}-point lead" if p["hold_lead"]
                       else f"{p['fights']} fight(s)",
                       at.astimezone().strftime("%a %-I:%M %p %Z"), at.strftime("%H:%M"),
                       end.strftime("%H:%M"))
        if datetime.now(timezone.utc) < at:
            if not self._fresh_start(ctx, at):
                return
        else:
            self._log.info("already inside the window -> starting now")
        if not self._open_arena(ctx):
            return
        started = time.time()
        done = self._snipe(ctx, deadline)
        self._log.info("%d fight(s) in %.0fs; %d refreshes (%d gems)", done,
                       time.time() - started, self._refreshes, self._gems)
        go_home(ctx)

    def _reset_run(self) -> None:
        self._avoid: list[Decimal] = []  # powers of those you can't beat, found this run
        self._cant_beat: set[int] = set()  # their points when last seen: no need to
                                           # refresh for them while those still hold
        self._restarts = 0
        self._refreshes = self._gems = 0
        self._searched = 0               # refreshes towards this fight
        self._enter_secs = ENTER_GUESS

    # --- the loop ----------------------------------------------------------------
    def _snipe(self, ctx: Context, deadline: datetime) -> int:
        p = self.params
        hold = p["hold_lead"]
        if ctx.dry_run:  # nothing to read: show one check's and one fight's taps
            self._tap(ctx, BACK_ARROW, "back arrow")
            self._tap(ctx, ARENA_CARD, "Arena")
            self._tap(ctx, OPPONENT_BTNS[0], "x1 Challenge")
            return 0
        done = 0
        last = time.time()
        while not ctx.should_stop():
            if datetime.now(timezone.utc) >= deadline:
                self._log.info("too close to the end -> stopping")
                break
            if not hold and done >= p["fights"]:
                self._log.info("%d fight(s) done (the setting)", done)
                break
            if not self._board_up(ctx):
                if ctx.should_stop() or not self._recover(ctx, "the board didn't show"):
                    break
                continue
            power, points, places = self._read_place(ctx)
            lead = lead_over_next(places, points)
            if hold and lead is not None and lead >= p["lead"]:
                self._log.info("first, ahead by %d (you %s, next %s) -> no attack", lead,
                               points, places[1].points)
            elif hold and (points is None or places[0].points is None):
                self._log.info("your place didn't read (you %s, first %s) -> no attack "
                               "this time", points, places[0].points)
            else:
                self._log.info("%s (you %s, top 3: %s) -> attack",
                               f"ahead by only {lead}" if lead is not None else "not first",
                               points, places)
                result = self._attack(ctx, power, points, places, deadline)
                if result == BLOCKED:
                    if ctx.should_stop() or not self._recover(ctx, "the fight didn't finish"):
                        break
                    continue
                if result == CANT_BUY:
                    self._log.warning("out of tickets and couldn't buy more -> stopping")
                    break
                if result not in (NO_TARGET, LOOK_AGAIN):
                    done += 1
                    self._log.info("fight %d -> %s", done, result)
                    last = time.time()
                    continue  # the board reloads after a fight: read it straight away
                if result == NO_TARGET and not hold:
                    self._log.warning("nobody to fight -> stopping")
                    break
            if not self._check_again(ctx, last, deadline):
                break
            last = time.time()
        return done

    def _board_up(self, ctx: Context) -> bool:
        return self._arena._wait_for(ctx, "the arena leaderboard", board_ready, LOAD_TIMEOUT,
                                     settle=0.3)

    def _read_place(self, ctx: Context) -> tuple[Decimal | None, int | None, list[Place]]:
        """Your power (only your banner shows it) and points, and the top 3's points,
        read again while something is missing (a row can still be loading)."""
        power = points = None
        places: list[Place] = []
        for _ in range(MAX_LOOKS):
            frame = ctx.frame()
            power, points = read_me(frame)
            places = read_board(frame)
            if (power is not None and points is not None
                    and all(s.points is not None for s in places)):
                break
            if wait(ctx, LOOK_GAP):
                break
        return power, points, places

    def _check_again(self, ctx: Context, last: float, deadline: datetime) -> bool:
        """Wait out the rest of the CHECK_EVERY since the `last` look, leaving time to
        back out, then back out and re-enter: the board is fresh when it's read. False
        on a stop or if the Arena can't be got back."""
        rest = last + CHECK_EVERY - self._enter_secs - time.time()
        left = (deadline - datetime.now(timezone.utc)).total_seconds()
        if left <= 0:
            return True  # the loop ends it, on the board
        if rest > 0 and wait(ctx, min(rest, left)):
            return False
        begun = time.time()
        if self._reenter(ctx):
            self._enter_secs = time.time() - begun
            return True
        return not ctx.should_stop() and self._recover(ctx, "couldn't re-enter the Arena")

    def _reenter(self, ctx: Context) -> bool:
        """The back arrow, then the Arena card (user: that's what refreshes the board)."""
        for _ in range(2):  # the arrow's tap can be lost
            if not tap(ctx, BACK_ARROW, 0.3):
                return False
            if self._until_frame(ctx, on_events, BACK_TIMEOUT):
                break
        else:
            if not go_events(ctx):
                return False
        card = card_at(ctx, "arena", ARENA_CARD)
        if card is None or not tap(ctx, card, 0.3):
            return False
        return self._arena._season_popups(ctx)

    def _until_frame(self, ctx: Context, check, timeout: float) -> bool:
        end = time.time() + timeout
        while not ctx.should_stop():
            if check(ctx.frame()):
                return True
            if time.time() >= end:
                return False
            time.sleep(0.2)
        return False

    def _recover(self, ctx: Context, why: str) -> bool:
        """Restart the game and go back to the Arena, RESTARTS times a run at most."""
        if self._restarts >= RESTARTS:
            self._log.warning("%s, after %d restarts -> stopping", why, self._restarts)
            self._snapshot(ctx, "stopped")
            return False
        self._restarts += 1
        self._log.warning("%s -> restarting the game (%d/%d)", why, self._restarts, RESTARTS)
        self._snapshot(ctx, "recover")
        return restart_game(ctx, why) and self._open_arena(ctx)

    def _open_arena(self, ctx: Context) -> bool:
        if not go_events(ctx):
            self._log.warning("couldn't get to the Events screen")
            return False
        if not self._tap(ctx, TABS["arena"], "Arena tab"):
            return False
        card = card_at(ctx, "arena", ARENA_CARD)
        if card is None:
            self._log.warning("no Arena card on the Arena tab")
            return False
        if not self._tap(ctx, card, "Arena"):
            return False
        return ctx.dry_run or self._arena._season_popups(ctx)

    # --- one fight ---------------------------------------------------------------
    def _can_beat(self, o: Opponent, cap: Decimal) -> bool:
        return o.power < cap and not any(close_power(o.power, a) for a in self._avoid)

    def _attack(self, ctx: Context, power: Decimal | None, points: int | None,
                places: list[Place], deadline: datetime) -> str:
        """Open the list, find the target, fight. "victory"/"defeat"/"unknown"; back on
        the board with NO_TARGET, or LOOK_AGAIN after LOOK_BACK_AFTER refreshes;
        CANT_BUY; BLOCKED if it went wrong or on a stop."""
        if power is None:  # needed for the ratio; board_ready has just read it
            self._log.warning("your power didn't read")
            return NO_TARGET
        if not self._arena._open_list(ctx):
            return BLOCKED
        cap = power * Decimal(str(self.params["ratio"]))
        wanted = [s for s in targets(places, points) if s.points not in self._cant_beat]
        self._log.info("target: %s (beatable below %.2fT)",
                       ", then ".join(f"place {s.rank} on {s.points} points" for s in wanted)
                       or "nobody in 2nd or 3rd", cap)
        round_refreshes = 0
        limit = self.params["max_refreshes"]
        while True:
            rows = self._list_rows(ctx)
            if not rows:  # something's over the list: don't tap Refresh on it
                self._log.warning("the Challenge list didn't read")
                self._snapshot(ctx, "list")
                return BLOCKED
            pick = next((o for o in rows if wanted and o.points == wanted[0].points), None)
            if pick is not None and not self._can_beat(pick, cap):
                self._log.info("place %d is %sT: can't beat them", wanted[0].rank, pick.power)
                self._cant_beat.add(pick.points)
                wanted.pop(0)
                continue
            if pick is None and (not wanted or self._searched >= limit):
                pick = self._next_best(rows, wanted, cap)
            if pick is None:
                if self._searched >= limit or datetime.now(timezone.utc) >= deadline:
                    self._log.info("nobody to fight after %d refreshes", self._searched)
                    self._searched = 0
                    self._tap(ctx, POPUP_CLOSE, "close the list")
                    return NO_TARGET
                if round_refreshes >= LOOK_BACK_AFTER:
                    self._log.info("%d refreshes -> a fresh look at the board", self._searched)
                    self._tap(ctx, POPUP_CLOSE, "close the list")
                    return LOOK_AGAIN
                if not self._refresh(ctx):
                    return BLOCKED
                self._searched += 1
                round_refreshes += 1
                continue
            opponent = None
            if self.params.get("scout", True):
                opponent = pvp.scout(ctx, OPPONENT_PICS[pick.row], "arena")
                if not self._arena._back_on_list(ctx):
                    return BLOCKED
                bad = pvp.rarely_beaten(opponent.uid if opponent else None)
                if bad is not None:
                    self._log.info("skip uid %s: won %d of %d against them (%.0f%%)",
                                   opponent.uid, bad[0], bad[1], 100 * bad[0] / bad[1])
                    self._avoid.append(pick.power)
                    self._cant_beat.add(pick.points)
                    wanted = [s for s in wanted if s.points not in self._cant_beat]
                    continue
            result = self._fight_row(ctx, pick)
            if result in (None, CANT_BUY):
                return result or BLOCKED
            self._searched = 0
            pvp.record(ctx, "arena", result, my_power=power, my_points=points,
                       list_power=pick.power, list_points=pick.points, opponent=opponent)
            if result == "defeat":  # the plainest "can't beat them" there is
                self._log.info("lost to %sT -> not fighting them again this run", pick.power)
                self._avoid.append(pick.power)
            return result

    def _next_best(self, rows: list[Opponent], wanted: list[Place], cap: Decimal
                   ) -> Opponent | None:
        """The target isn't coming: any other wanted place on the list, else the most
        points below the cap."""
        for s in wanted:
            hit = next((o for o in rows if o.points == s.points and self._can_beat(o, cap)),
                       None)
            if hit is not None:
                return hit
        pick = max((o for o in rows if self._can_beat(o, cap)),
                   key=lambda o: (o.points, -o.power), default=None)
        if pick is not None:
            self._log.info("taking the most points below the ratio: %sT, %d points",
                           pick.power, pick.points)
        return pick

    def _list_rows(self, ctx: Context) -> list[Opponent]:
        """The Challenge list's rows, in one log line (a run can read it hundreds of
        times). [] if it isn't up or doesn't read."""
        rows: list[Opponent] = []
        for _ in range(MAX_LOOKS):
            frame = ctx.frame()
            if list_open(frame):
                rows = read_opponents(frame)
                if len(rows) == len(OPPONENT_BTNS):
                    break
            if wait(ctx, LOOK_GAP):
                break
        self._log.info("list: %s", ", ".join(f"{o.power}T {o.points}" for o in rows) or "-")
        return rows

    def _refresh(self, ctx: Context) -> bool:
        """One tap on Refresh (its label says "Free" or the price), once the list
        shows it, and the list back."""
        label = _words(ctx.frame(), REFRESH_LABEL)
        if "refresh" not in label:
            self._log.warning("no Refresh button on the list (%r)", label)
            self._snapshot(ctx, "refresh")
            return False
        self._refreshes += 1
        if "free" not in label:
            self._gems += int("".join(c for c in label if c.isdigit()) or 0)
        if not self._tap(ctx, FREE_REFRESH, f"Refresh ({label})"):
            return False
        return self._arena._wait_for(ctx, "the refreshed list", list_open, LOAD_TIMEOUT,
                                     settle=0.3)

    def _fight_row(self, ctx: Context, pick: Opponent) -> str | None:
        """x1 Challenge on the row, buying tickets if the Purchase popup comes up, then
        the arena's Skip and OK. The result; CANT_BUY if the tickets couldn't be
        bought; None if there was no fight."""
        for bought in (False, True):
            if not self._tap(ctx, OPPONENT_BTNS[pick.row], f"x1 Challenge (row {pick.row + 1})"):
                return None
            if not self._arena._wait_for(ctx, "the fight screen",
                                         lambda f: fight_up(f) or purchase_up(f),
                                         FIGHT_TIMEOUT, settle=0):
                return None
            if fight_up(ctx.frame()):
                break
            if bought:
                return None  # bought, and the popup again: don't go on buying
            if not self._buy_ticket(ctx):
                return None if ctx.should_stop() else CANT_BUY
            if not self._arena._wait_for(ctx, "the list after buying", list_open, LOAD_TIMEOUT,
                                         settle=0.3):
                return None
        if wait(ctx, FIGHT_SETTLE):
            return None
        return self._arena._finish_fight(ctx)
