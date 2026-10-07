"""Kill the game, open it again, and get back to the home screen.

Any task can call restart_game(ctx, reason) when the game is stuck (e.g. a fight
that froze). It ends the game's process, relaunches it from its app, waits through
the loading screens, and closes every start-up notice until the home screen shows
and stays clear. The steps are public too: game_running, quit_game, launch_game
(also brings up a game that isn't running), and wait_for_home (the notice-closing
part on its own). From the command line: ./run.sh restart-game.

The game is an iPhone app running on the Mac. It never answers a normal quit
request (an AppleScript "quit" hung for 20s), so it is ended with a signal:
SIGTERM, then SIGKILL if it's still running after QUIT_TIMEOUT. Its process is
found by bundle ID, so this works with the window hidden or on another Space.

Seen on a relaunch: splash -> "Checking for updates" -> "Logging in" -> a series
of notices -> home. 2026-10-06 17:38 brought eight (home in 46s): Game Notice,
an Epic Special Offer, Moonlit Adventure, Limited-Time Inheritance UP, Martial
Arts Tournament, Champion Team, Today's Showdown, a 10% Bonus ad. Most have an X;
Moonlit Adventure and Inheritance UP have only Go buttons. Every notice says "Do
not show again today" (a checkbox the bot never taps). Each one is closed the way
go_home closes popups (the X, "Tap to close", the back arrow), else by an OK /
Close button, else (no X but "Do not show") by a tap on an empty spot above the
panel. Other unplaced screens (loading) get an empty-spot tap now and then. Home
only counts once it has stayed clear for HOME_STEADY seconds, because a notice can
pop up just after the home screen shows.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time

from ..geometry import Rel
from ..perception import ocr_lines
from ..task import Context, Task, register
from ..window import WindowNotFound
from .daily import (_MOVE_LOG, MAX_SWITCH_TAPS, NEUTRAL, SWITCH_SETTLE, TAP_SETTLE,
                    next_move, save_snapshot, tap, wait)

QUIT_TIMEOUT = 10.0       # the game gets this long to quit before it's forced
KILL_TIMEOUT = 5.0        # and this long to vanish after the forced kill
LAUNCH_TIMEOUT = 90.0     # the relaunched game's window must show by then
LOAD_TIMEOUT = 180.0      # then the home screen, through loading and notices
HOME_STEADY = 3.0         # home must stay clear this long: notices can come late
UNKNOWN_TAP_EVERY = 4     # a screen nothing places: tap an empty spot every 4th look

# Buttons that close a notice, looked for on screens nothing else places. Exact
# labels only, and never on a screen that mentions money.
CLOSE_LABELS = {"ok", "close", "confirm", "got it"}
MONEY_WORDS = ("$", "top up", "purchase", "buy", "pay", "recharge")
NOTICE_HINTS = ("do not show", "don't show")  # every notice's "Do not show again today"


def _bundle(ctx: Context) -> str:
    return ctx.config["window"].get("bundle_id", "com.habby.capybara")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by someone else
        return True


def game_pids(ctx: Context) -> list[int]:
    """The game's running processes, found by bundle ID (with or without a window)."""
    from AppKit import NSRunningApplication

    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(_bundle(ctx))
    return [pid for pid in (int(a.processIdentifier()) for a in apps or [])
            if pid > 0 and _alive(pid)]


def game_running(ctx: Context) -> bool:
    return bool(game_pids(ctx))


def game_on_screen(ctx: Context) -> bool:
    try:
        ctx.window.bounds()
        return True
    except WindowNotFound:
        return False


def quit_game(ctx: Context) -> bool:
    """End the game's process: SIGTERM, then SIGKILL after QUIT_TIMEOUT. True once
    it's gone (also when it wasn't running)."""
    pids = game_pids(ctx)
    if not pids:
        ctx.log.info("restart: the game isn't running")
        return True
    for sig, timeout in ((signal.SIGTERM, QUIT_TIMEOUT), (signal.SIGKILL, KILL_TIMEOUT)):
        if sig == signal.SIGKILL:
            ctx.log.warning("restart: the game didn't quit; forcing it")
        for pid in pids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        end = time.time() + timeout
        while any(_alive(p) for p in pids):
            if time.time() >= end:
                break
            if wait(ctx, 0.5):
                return False
        else:
            ctx.log.info("restart: the game is closed (pid %s)",
                         ", ".join(map(str, pids)))
            return True
    ctx.log.warning("restart: the game is still running after a forced kill")
    return False


def launch_game(ctx: Context) -> bool:
    """Open the game from its app (config window.app_path; the bundle ID if that's
    missing) and wait for its window. True once it's on screen. If the game is
    already running, this just brings it up."""
    win = ctx.config["window"]
    app = win.get("app_path", "/Applications/CapybaraGo!.app")
    cmd = ["open", app] if os.path.isdir(app) else ["open", "-b", _bundle(ctx)]
    ctx.log.info("restart: opening the game")
    subprocess.run(cmd, capture_output=True, timeout=20)
    end = time.time() + LAUNCH_TIMEOUT
    while not game_on_screen(ctx):
        if time.time() >= end:
            ctx.log.warning("restart: the game's window didn't show within %.0fs",
                            LAUNCH_TIMEOUT)
            return False
        if wait(ctx, 1.0):
            return False
    return True


def _read_notice(frame) -> tuple[str, Rel] | None:
    """What to tap on a screen nothing else places, as (log text, target): its OK /
    Close button (never on a screen that mentions money), or an empty spot for a
    notice without an X. None if it reads as neither (e.g. a loading screen)."""
    lines = ocr_lines(frame)
    text = " ".join(t for t, _, _ in lines).lower()
    if not any(w in text for w in MONEY_WORDS):
        h, w = frame.shape[:2]
        for t, cx, cy in lines:
            if t.strip().lower() in CLOSE_LABELS:
                return "tap the notice's OK / Close", Rel(cx / w, cy / h)
    if any(hint in text for hint in NOTICE_HINTS):
        return "notice without an X -> tap an empty spot", NEUTRAL
    return None


def wait_for_home(ctx: Context, timeout: float = LOAD_TIMEOUT) -> bool:
    """Through the loading screens and start-up notices to the home screen. True
    once home has stayed clear for HOME_STEADY seconds."""
    end = time.time() + timeout
    closed = unknowns = switches = 0
    home_since = None
    while time.time() < end:
        if ctx.should_stop():
            return False
        frame = ctx.frame()
        move, target = next_move(ctx, frame)
        if move == "home":
            home_since = home_since or time.time()
            if time.time() - home_since >= HOME_STEADY:
                ctx.log.info("restart: on the home screen (%d tap%s to close notices)",
                             closed, "" if closed == 1 else "s")
                return True
            if wait(ctx, 1.0):
                return False
            continue
        home_since = None
        if move == "stuck":  # home's Start is up but the switch isn't settled yet
            if wait(ctx, 1.0):
                return False
            continue
        if move == "unknown":  # loading, or a notice nothing else places
            unknowns += 1
            notice = _read_notice(frame) if unknowns >= 2 else None
            if notice is not None:
                what, target = notice
                unknowns = 0
                closed += 1
            elif unknowns % UNKNOWN_TAP_EVERY == 0:
                what, target = "tap an empty spot", NEUTRAL
            else:
                if wait(ctx, 1.0):
                    return False
                continue
        else:
            unknowns = 0
            if move == "switch":
                switches += 1
                if switches > MAX_SWITCH_TAPS:
                    ctx.log.warning("restart: the capy switch is still red after %d "
                                    "taps", MAX_SWITCH_TAPS)
                    return False
            else:
                closed += 1
            what = _MOVE_LOG[move]
        ctx.log.info("restart: %s", what)
        if not tap(ctx, target, SWITCH_SETTLE if move == "switch" else TAP_SETTLE):
            return False
    ctx.log.warning("restart: no steady home screen within %.0fs", timeout)
    return False


def restart_game(ctx: Context, reason: str = "it looks stuck") -> bool:
    """Kill the game, open it again, and get to the home screen, closing the
    start-up notices on the way. True once home. Safe to call from any task."""
    if ctx.dry_run:
        ctx.log.info("DRY-RUN restart the game (%s)", reason)
        return True
    shot = save_snapshot(ctx, "before-restart")
    ctx.log.warning("restarting the game: %s%s", reason,
                    f"; screen saved: {shot}" if shot else "")
    start = time.time()
    if quit_game(ctx) and launch_game(ctx) and wait_for_home(ctx):
        ctx.log.info("the game restarted in %.0fs", time.time() - start)
        return True
    if not ctx.should_stop():
        shot = save_snapshot(ctx, "restart-not-home")
        ctx.log.warning("the restart didn't reach the home screen%s",
                        f"; screen saved: {shot}" if shot else "")
    return False


@register("restart-game")
class RestartGame(Task):
    """./run.sh restart-game: the restart on its own."""

    TITLE = "Restart the game"
    ICON = "🔄"
    HIDDEN = True
    DESCRIPTION = ("Kill the game, open it again, and get to the home screen, "
                   "closing the start-up notices.")

    def run(self, ctx: Context) -> None:
        restart_game(ctx, "asked for")
