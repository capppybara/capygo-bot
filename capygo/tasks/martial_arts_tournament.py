"""Task: martial-arts-tournament (the Qualifiers).

Events -> Arena tab -> Martial Arts Tournament ("Martial Arts Hall") -> Schedule
-> "Qualifiers": 6 opponents (rank, power, points, a Challenge button showing your
tickets "9/1"), Free Refresh at the top right, your points and ranking below. The
top 64 advance; no challenges in the last 5 minutes of the round.

User (2026-10-05): take the points you can win. Each attack:
  1. Read all 6 opponents: 5 fit on screen, so the list is scrolled down a
     little (a click on the title first, or the drag doesn't register).
  2. Fight the one with the most points whose power is below RATIO x your CP
     (both app inputs; B and T are converted). None -> Refresh (free or paid),
     up to 5 times, raising the ratio by 0.1 each time (1.1 -> 1.2 -> ... 1.6).
     Still none -> stop and flag it.
  3. The fight is the arena's: Skip (every 5s while it shows), then OK on the
     result. If Skip is still showing after 30s the fight is stuck (it never
     goes back to the list): the game is restarted (once per run), the bot goes
     back to the Qualifiers and carries on.
  4. Out of tickets, Challenge opens a "Purchase" ticket popup instead of a
     fight. With "Max attacks" at 0 that ends the run (closed, nothing bought).
     With a number set, that many attacks are always done (user): it buys a
     ticket and taps Challenge again. If neither the fight nor that popup
     shows, Challenge is tapped once more.
Normal mode attacks until the tickets run out. Sniping mode waits for the next
13:50 UTC (6:50 AM Pacific in summer, 5:50 AM in winter: 10 minutes before the
round closes at 14:00 UTC, so 5 minutes before challenges stop) and uses every
attack then; it stops starting new fights 20 seconds before the 5-minute cutoff.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import cv2

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Param, Task, register
from .daily import (_crop, find_sprite, go_home, save_snapshot, tap, tap_to_close_up,
                    wait)
from .event import TABS, go_events
from .event_arena import OK_BTN, OK_LABEL, RESULT_TITLE, SKIP_BTN, _power, fight_up
from . import pvp
from .event_martial_arts import MartialArts
from .profile import close_profile, is_open as profile_open
from .restart import restart_game

HALL_TITLE = RelRect(0.30, 0.070, 0.40, 0.050)     # "Martial Arts Hall"
SCHEDULE_BTN = Rel(0.671, 0.955)
STAGE_TITLE = RelRect(0.30, 0.045, 0.40, 0.045)    # "Qualifiers"
TITLE_TAP = (321, 62)                              # the title: inert, wakes the window
REFRESH_BTN = (484, 140)
REFRESH_LABEL = RelRect(0.67, 0.122, 0.17, 0.045)  # "Free Refresh" / a price
LIST_Y = (180, 610)                                # the opponent list, px
ROW_FIND_X = (320, 410)                            # the points column, to find rows
POWER_X, POINTS_X = (239, 312), (322, 408)        # power: right of the sword icon
PLAUSIBLE = (Decimal("0.1"), Decimal(100))         # 100B..100T: one read is enough
ROW_H = 32
CHALLENGE_X = 485                                  # a row's button: points y - 2
TICKETS_DY = -21                                   # "9/1" above "Challenge"
TAPPABLE = (205, 595)                              # a row's button is fully on screen
MY_POINTS = RelRect(0.33, 0.680, 0.17, 0.042)      # your points ("1123")
# A row's picture (left of the name, right of the rank): opens the opponent's
# profile for the fight log (pvp.py). From a screenshot, not tapped live yet.
PIC_X, PIC_DY = 180, -10                           # px; y = the row's points y + DY
SCROLL_DOWN = ((116, 560), (116, 440))             # rank column: no buttons there
SCROLL_UP = ((116, 300), (116, 560))

REFRESHES = 5             # user: up to 5, paid or free
RATIO_STEP = Decimal("0.1")
SNIPE_UTC = "13:50"       # user: 6:50 AM Pacific in summer (a hidden setting)
WINDOW = timedelta(minutes=5)  # the snipe time to the cutoff (no challenges in
                               # the round's last 5 minutes)
CUTOFF_MARGIN = 20        # don't start a fight this close to the cutoff
FIGHT_TIMEOUT = 15.0
PURCHASE_TEXT = RelRect(0.10, 0.20, 0.80, 0.35)    # out of tickets: "Purchase ..." popup
PURCHASE_CLOSE = Rel(0.5, 0.714)                   # its X, if the sprite isn't found
NO_TICKETS, STUCK = "no tickets", "stuck"
RESTARTS = 1              # restart the game at most this often per run
FIGHT_SETTLE = 2.0        # user (arena): a couple of seconds before Skip
SKIP_RETRY = 5.0         # user: tap Skip every 5 seconds while it shows
RESULT_TIMEOUT = 30.0    # user: Skip still showing after 30s = stuck
FROZEN_AFTER = 10.0       # a fight screen this long without any change = frozen
STILL_DIFF = 1.0          # mean pixel change (80x120 grey) below this = no change
OPEN_TIMEOUT = 8.0
POLL = 0.5
SETTLE = 1.0


class _Stillness:
    """Spots a frozen fight: the screen not changing at all for FROZEN_AFTER
    seconds (a running fight always animates). 2026-10-06's snipe hit one: the
    fight sat on screen, Skip did nothing, and no result came."""

    def __init__(self):
        self.last = None
        self.since = time.time()
        self.reported = False

    def frozen(self, frame) -> bool:
        """True once, the first time the screen has been still long enough."""
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (80, 120),
                           interpolation=cv2.INTER_AREA).astype("int16")
        if self.last is None or abs(small - self.last).mean() >= STILL_DIFF:
            self.last, self.since = small, time.time()
            return False
        if not self.reported and time.time() - self.since >= FROZEN_AFTER:
            self.reported = True
            return True
        return False


@dataclass
class Foe:
    power: Decimal    # trillions
    points: int
    y: int            # px of its points text (the button is at y - 2)


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def _cell(frame, xs: tuple[int, int], y: float, scale: int = 2) -> str:
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    crop = frame[int((y - ROW_H / 2) * ky):int((y + ROW_H / 2) * ky),
                 int(xs[0] * kx):int(xs[1] * kx)]
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return " ".join(t for t, _, _ in ocr_lines(crop))


def _power_at(frame, y: float) -> Decimal | None:
    """A row's power. The crop starts after the sword icon: with the icon in it,
    OCR added stray digits ("112.54T" for 2.54T, "412.58T" live). A read with no
    unit ("2.131") is retried at a shifted crop or size. A value between 100B and
    100T is taken at once; one outside that range is suspicious (user: read
    again) and counts only once a second read agrees. None if that never
    happens: the opponent is skipped rather than guessed."""
    seen: list[Decimal] = []
    for dy, scale in ((0, 2), (0, 3), (-1, 2), (1, 2), (-1, 3), (1, 3)):
        power = _power(_cell(frame, POWER_X, y + dy, scale))
        if power is None:
            continue
        if PLAUSIBLE[0] <= power <= PLAUSIBLE[1] or power in seen:
            return power
        seen.append(power)
    return None


def read_foes(frame) -> list[Foe]:
    """The opponents whose power and points both read on this screen."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    y0, y1 = LIST_Y
    col = frame[int(y0 * ky):int(y1 * ky), int(ROW_FIND_X[0] * kx):int(ROW_FIND_X[1] * kx)]
    foes = []
    for t, _, cy in ocr_lines(col):
        y = cy / ky + y0
        points = re.sub(r"\D", "", _cell(frame, POINTS_X, y))
        power = _power_at(frame, y)
        if points and power is not None:
            foes.append(Foe(power, int(points), round(y)))
    return foes


def tickets(frame, foes: list[Foe]) -> int | None:
    """Your tickets, from the "9/1" on the Challenge buttons (most common read)."""
    reads = []
    for f in foes:
        m = re.search(r"(\d+)\s*/\s*1\b", _cell(frame, (455, 530), f.y + TICKETS_DY))
        if m:
            reads.append(int(m.group(1)))
    return max(set(reads), key=reads.count) if reads else None


def best(foes: list[Foe], cap: Decimal) -> Foe | None:
    """Most points among those below the power cap (ties: the weaker one)."""
    ok = [f for f in foes if f.power < cap]
    return max(ok, key=lambda f: (f.points, -f.power), default=None)


def next_snipe(hhmm: str = SNIPE_UTC, now: datetime | None = None) -> datetime:
    """The next time `hhmm` (UTC) comes round. 13:50 UTC = 6:50 AM Pacific in
    summer, 5:50 AM in winter."""
    hour, minute = (int(v) for v in hhmm.strip().split(":"))
    now = now or datetime.now(timezone.utc)
    t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def _px(pos: tuple[int, int]) -> Rel:
    return Rel(pos[0] / 642, pos[1] / 951)


@register("martial-arts-tournament")
class MartialArtsTournament(Task):
    TITLE = "Martial Arts Tournament"
    ICON = "🥋"
    DESCRIPTION = ("Qualifiers: fight the opponent with the most points below your "
                   "power limit until the tickets run out, now or at 6:50 AM (sniping).")
    START_HINT = "Start anywhere in the game. Set your CP (power) first."
    PARAMS = [
        Param("my_cp", "float", 4.7, "Your CP (T)", min=0.01, max=10000,
              help="your power in trillions; opponents are compared against it"),
        Param("ratio", "float", 1.1, "Power ratio", min=0.5, max=5,
              help="fight only opponents below this x your CP (+0.1 per refresh)"),
        Param("sniping", "bool", False, "Sniping mode",
              help="wait for 6:50 AM Pacific (13:50 UTC) and use every attack then"),
        Param("max_attacks", "int", 0, "Attacks (0 = until tickets run out)", min=0,
              max=99, help="a number: always do that many, buying tickets if needed"),
        Param("scout", "bool", True, "Log opponents",
              help="open each opponent's profile before the fight and log it with the "
                   "result in ~/Downloads/capy-bot/pvp/ (about 4s a fight)"),
        Param("snipe_utc", "str", SNIPE_UTC, "Snipe time (UTC, HH:MM)", hidden=True,
              help="for tests: -p snipe_utc=HH:MM; the cutoff is 5 minutes later"),
    ]

    def run(self, ctx: Context) -> None:
        p = self.params
        cp = Decimal(str(p["my_cp"]))
        deadline = None
        if p["sniping"]:
            at = next_snipe(p["snipe_utc"])
            local = at.astimezone().strftime("%a %-I:%M %p %Z")
            ctx.log.info("martial: sniping - waiting until %s (%s UTC)", local,
                         at.strftime("%H:%M"))
            if not self._wait_until(ctx, at):
                return
            deadline = at + WINDOW - timedelta(seconds=CUTOFF_MARGIN)
        started = time.time()
        if not self._open_qualifiers(ctx):
            return
        done = self._attacks(ctx, cp, Decimal(str(p["ratio"])), p["max_attacks"], deadline)
        ctx.log.info("martial: %d attack(s) in %.0fs", done, time.time() - started)
        go_home(ctx)

    # --- getting there -----------------------------------------------------------
    def _wait_until(self, ctx: Context, at: datetime) -> bool:
        """Sleep until `at`, keeping the Mac awake (caffeinate) and stoppable."""
        keep_awake = None
        if not ctx.dry_run:
            try:
                keep_awake = subprocess.Popen(
                    ["caffeinate", "-di", "-w", str(os.getpid())])
            except OSError:
                ctx.log.warning("martial: couldn't keep the Mac awake (caffeinate)")
        try:
            next_note = time.time()
            while True:
                left = (at - datetime.now(timezone.utc)).total_seconds()
                if left <= 0 or ctx.dry_run:
                    return True
                if time.time() >= next_note:
                    ctx.log.info("martial: %s to go", str(timedelta(seconds=int(left))))
                    next_note = time.time() + (600 if left > 900 else 60)
                if wait(ctx, min(5.0, left)):
                    return False
        finally:
            if keep_awake is not None:
                keep_awake.terminate()

    def _open_qualifiers(self, ctx: Context) -> bool:
        if not go_events(ctx):
            ctx.log.warning("martial: couldn't get to the Events screen")
            return False
        if not (self._tap(ctx, TABS["arena"], "Arena tab")
                and self._tap(ctx, MartialArts.CARD, "Martial Arts Tournament")):
            return False
        if not ctx.dry_run and not self._until(
                ctx, lambda: "martial" in _words(ctx.frame(), HALL_TITLE)):
            ctx.log.warning("martial: the Martial Arts Hall didn't open")
            return False
        if not self._tap(ctx, SCHEDULE_BTN, "Schedule"):
            return False
        if not ctx.dry_run and not self._until(
                ctx, lambda: "qualifier" in _words(ctx.frame(), STAGE_TITLE)):
            ctx.log.warning("martial: the Qualifiers didn't open (another stage?)")
            return False
        return self._tap(ctx, _px(TITLE_TAP), "title (wake the list)")

    # --- the attacks -------------------------------------------------------------
    def _attacks(self, ctx: Context, cp: Decimal, base: Decimal, limit: int,
                 deadline: datetime | None) -> int:
        done = 0
        self.restarts = 0
        while not ctx.should_stop():
            if limit and done >= limit:
                ctx.log.info("martial: %d attack(s) done (the limit)", done)
                break
            if deadline and datetime.now(timezone.utc) >= deadline:
                ctx.log.info("martial: too close to the cutoff -> stopping")
                break
            if ctx.dry_run:  # nothing to read: show one attack's taps and stop
                self._tap(ctx, _px((CHALLENGE_X, 383)), "Challenge")
                self._tap(ctx, SKIP_BTN, "Skip")
                self._tap(ctx, OK_BTN, "OK")
                return 1
            foe = self._choose(ctx, cp, base)
            if foe is None:
                break
            points = re.sub(r"\D", "", _words(ctx.frame(), MY_POINTS))
            self.opponent = None
            result = self._fight(ctx, foe, buy=limit > 0)
            if result not in (None, NO_TICKETS):  # a fight happened: log it
                pvp.record(ctx, "martial", result, my_power=cp,
                           my_points=int(points) if points else None, row=None,
                           list_power=foe.power, list_points=foe.points,
                           opponent=self.opponent)
            if result == NO_TICKETS:
                ctx.log.info("martial: out of tickets (the Purchase popup) -> done")
                break
            if result == STUCK:
                if self.restarts >= RESTARTS:
                    ctx.log.warning("martial: stuck again after a restart -> stopping")
                    break
                if deadline and datetime.now(timezone.utc) >= deadline:
                    ctx.log.warning("martial: stuck, and no time left to restart")
                    break
                self.restarts += 1
                if not (restart_game(ctx, "the fight is stuck")
                        and self._open_qualifiers(ctx)):
                    break
                continue
            if result is None:
                break
            done += 1
            ctx.log.info("martial: attack %d -> %s (your points: %s)", done, result,
                         _words(ctx.frame(), MY_POINTS) or "?")
        return done

    def _choose(self, ctx: Context, cp: Decimal, base: Decimal) -> Foe | None:
        """Scroll down, read all 6, pick; refresh (up to 5, ratio +0.1 each)."""
        ratio = base
        for refresh in range(REFRESHES + 1):
            self._scroll(ctx, SCROLL_DOWN)
            frame = ctx.frame()
            foes = read_foes(frame)
            left = tickets(frame, foes)  # for the log; the Purchase popup ends the run
            cap = cp * ratio
            for f in foes:
                ctx.log.info("martial:   %sT, %d points%s", f.power, f.points,
                             "" if f.power < cap else "  (too strong)")
            foe = best(foes, cap)
            if foe is not None:
                ctx.log.info("martial: pick %sT, %d points (below %sx = %.2fT; "
                             "tickets %s)", foe.power, foe.points, ratio, cap, left)
                return foe
            if refresh == REFRESHES:
                break
            label = _words(frame, REFRESH_LABEL)
            ctx.log.info("martial: nobody below %sx -> Refresh %d/%d (%s)", ratio,
                         refresh + 1, REFRESHES, label or "?")
            if not self._tap(ctx, _px(REFRESH_BTN), "Refresh", 2.0):
                return None
            ratio += RATIO_STEP
        ctx.log.warning("martial: no opponent below %sx your CP after %d refreshes -> "
                        "stopping; attack the rest by hand", ratio, REFRESHES)
        return None

    def _fight(self, ctx: Context, foe: Foe, buy: bool = False) -> str | None:
        """Tap the foe's Challenge (scrolling up first if it's row 1), Skip the
        fight, OK the result. "victory"/"defeat"/"unknown", or None if no fight."""
        if not TAPPABLE[0] <= foe.y - 2 <= TAPPABLE[1]:
            self._scroll(ctx, SCROLL_UP)
            match = [f for f in read_foes(ctx.frame())
                     if f.power == foe.power and f.points == foe.points]
            if not match:
                ctx.log.warning("martial: lost track of the pick after scrolling")
                self._snapshot(ctx, "martial-lost-pick")
                return None
            foe = match[0]
        # The fight log (user, 2026-10-09): look at the opponent's profile first.
        if self.params.get("scout", True):
            self.opponent = pvp.scout(ctx, _px((PIC_X, foe.y + PIC_DY)), "martial")
            if not ctx.dry_run and not self._back_on_qualifiers(ctx):
                return None
        started = None
        bought = False
        for attempt in (1, 2, 3):
            if not self._tap(ctx, _px((CHALLENGE_X, foe.y - 2)), "Challenge"):
                return None
            started = self._fight_or_purchase(ctx)
            if started == NO_TICKETS and buy and not bought:
                # user: a set number of attacks is always done, buying tickets
                if not self._buy_ticket(ctx):
                    return None
                bought = True
                continue
            if started in ("fight", NO_TICKETS, None):
                break
            # neither the fight nor the Purchase popup: maybe a lost tap
            ctx.log.info("martial: no fight after Challenge (try %d/2)", attempt)
            x = find_sprite(ctx, ctx.frame(), "close_x.png")
            if x is not None:
                self._tap(ctx, x, "close the popup")
        if started is None:
            return None
        if started == NO_TICKETS:
            self._close_purchase(ctx)
            return NO_TICKETS
        if started != "fight":
            ctx.log.warning("martial: the fight didn't start after 2 tries -> stopping")
            self._snapshot(ctx, "martial-no-fight")
            return None
        if wait(ctx, FIGHT_SETTLE):
            return None
        end = time.time() + RESULT_TIMEOUT
        last_skip = 0.0
        still = _Stillness()
        while time.time() < end:
            frame = ctx.frame()
            if still.frozen(frame):
                ctx.log.warning("martial: the fight froze (no change for %.0fs) - a game "
                                "issue, not the bot", FROZEN_AFTER)
            title = _words(frame, RESULT_TITLE)
            if "victory" in title or "defeat" in title or "ok" in _words(
                    frame, OK_LABEL).split():
                if wait(ctx, SETTLE):
                    return None
                result = next((r for r in ("victory", "defeat")
                               if r in _words(ctx.frame(), RESULT_TITLE)), "unknown")
                if not self._ok(ctx):
                    return None
                return result
            if "qualifier" in _words(frame, STAGE_TITLE):
                return "unknown"  # back on the list already
            if fight_up(frame) and time.time() - last_skip >= SKIP_RETRY:
                if not self._tap(ctx, SKIP_BTN, "Skip"):
                    return None
                last_skip = time.time()
                continue
            if wait(ctx, POLL):
                return None
        stuck = fight_up(ctx.frame())
        ctx.log.warning("martial: no result screen within %.0fs%s%s", RESULT_TIMEOUT,
                        " (the fight was frozen)" if still.reported else "",
                        "; Skip still showing -> the fight is stuck" if stuck else "")
        self._snapshot(ctx, "martial-no-result")
        return STUCK if stuck else None

    def _ok(self, ctx: Context) -> bool:
        """The result's OK: the arena's spot if it reads there, else wherever "OK"
        is (the result screen here isn't confirmed yet)."""
        frame = ctx.frame()
        if "ok" in _words(frame, OK_LABEL).split():
            target = OK_BTN
        else:
            h, w = frame.shape[:2]
            ok = next(((cx, cy) for t, cx, cy in ocr_lines(frame)
                       if t.strip().upper() == "OK"), None)
            target = Rel(ok[0] / w, ok[1] / h) if ok else OK_BTN
        if not self._tap(ctx, target, "OK", 2.0):
            return False
        return self._until(ctx, lambda: "qualifier" in _words(ctx.frame(), STAGE_TITLE))

    def _back_on_qualifiers(self, ctx: Context) -> bool:
        """After the profile look: the Qualifiers list must be showing again before
        a row's Challenge is tapped. A profile still up gets closed once more."""
        if profile_open(ctx.frame()):
            close_profile(ctx)
        if self._until(ctx, lambda: "qualifier" in _words(ctx.frame(), STAGE_TITLE)):
            return True
        self._snapshot(ctx, "martial-after-profile")
        return False

    def _fight_or_purchase(self, ctx: Context) -> str | None:
        """After Challenge: "fight" once the fight screen shows, NO_TICKETS on the
        Purchase (ticket) popup (user: that's how you know you're out), "" if
        neither shows within FIGHT_TIMEOUT, None on a stop."""
        end = time.time() + FIGHT_TIMEOUT
        while time.time() < end:
            frame = ctx.frame()
            if fight_up(frame):
                return "fight"
            if "purchase" in _words(frame, PURCHASE_TEXT):
                return NO_TICKETS
            if wait(ctx, POLL):
                return None
        return ""

    def _buy_ticket(self, ctx: Context) -> bool:
        """Buy one ticket from the Purchase popup: tap its "Purchase" button (the
        lowest "Purchase" text; the title is the top one). Never anything that
        looks like real money. True once the popup has closed."""
        frame = ctx.frame()
        h, w = frame.shape[:2]
        lines = [(t.lower(), cx, cy) for t, cx, cy in ocr_lines(frame)]
        words = " ".join(t for t, _, _ in lines)
        if "top up" in words or "top-up" in words or "$" in words:
            ctx.log.warning("martial: the ticket popup looks like real money -> not "
                            "buying")
            self._snapshot(ctx, "martial-ticket-popup")
            self._close_purchase(ctx)
            return False
        buttons = [(cx, cy) for t, cx, cy in lines if "purchase" in t or t.strip() == "buy"]
        if len(buttons) < 2:  # need the title AND a button below it
            ctx.log.warning("martial: no Purchase button found on the ticket popup")
            self._snapshot(ctx, "martial-ticket-popup")
            self._close_purchase(ctx)
            return False
        cx, cy = max(buttons, key=lambda b: b[1])
        ctx.log.info("martial: out of tickets -> buying one (a set number of attacks)")
        if not self._tap(ctx, Rel(cx / w, cy / h), "Purchase (1 ticket)", 2.0):
            return False
        if tap_to_close_up(ctx.frame()):
            self._tap(ctx, _px(TITLE_TAP), "close the reward")
        if "purchase" in _words(ctx.frame(), PURCHASE_TEXT):
            ctx.log.warning("martial: the ticket popup is still open after buying")
            self._snapshot(ctx, "martial-ticket-popup")
            self._close_purchase(ctx)
            return False
        return True

    def _close_purchase(self, ctx: Context) -> None:
        """Close the ticket Purchase popup. Never buys."""
        x = find_sprite(ctx, ctx.frame(), "close_x.png")
        self._tap(ctx, x if x is not None else PURCHASE_CLOSE, "close the Purchase popup")

    # --- helpers -----------------------------------------------------------------
    @staticmethod
    def _snapshot(ctx: Context, label: str) -> None:
        """Save the screen to logs/ when something goes wrong, so it can be seen."""
        shot = save_snapshot(ctx, label)
        if shot:
            ctx.log.warning("martial: screen saved: %s", shot)

    def _scroll(self, ctx: Context, drag) -> None:
        (x0, y0), (x1, y1) = drag
        ctx.drag_rel(_px((x0, y0)), _px((x1, y1)), steps=30, duration=0.8)
        wait(ctx, 1.0)

    def _tap(self, ctx: Context, target, what: str, after: float = 1.0) -> bool:
        if ctx.should_stop():
            return False
        ctx.log.info("martial: tap %s", what)
        return tap(ctx, target, after)

    def _until(self, ctx: Context, check, timeout: float = OPEN_TIMEOUT) -> bool:
        end = time.time() + timeout
        while True:
            if check():
                return not wait(ctx, SETTLE)
            if time.time() >= end or wait(ctx, POLL):
                return False
