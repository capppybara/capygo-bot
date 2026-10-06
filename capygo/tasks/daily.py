"""Base class and shared helpers for daily chores.

Each daily is its own registered task, so it can run alone (./run.sh energy-claim),
but it is hidden from the home screen: the auto-daily task runs the enabled dailies
in order and shows one on/off switch per daily.

A daily implements run_daily(ctx) -> bool and returns True when it finished back on
the home screen. It should verify each screen it opens before tapping inside it, so
a missed tap never turns into blind taps on whatever screen is actually up.

Each daily records its own last finish in data/daily_runs.json and runs once per
game day (00:00 UTC reset): a second run the same day is skipped unless confirmed
(the app asks; -p rerun=true on the CLI). Dry runs don't count.

The home screen is the main Adventure screen: the orange Start button is visible and
the capy switch beside it is blue. Tapping that switch flips the game into another
mode (the "Amber Bay" co-op screen) where the switch is red, sits ~40px higher, and
has its tiles flipped; tapping the capy head again flips back.

go_home() gets back from anywhere, one move at a time until home:
  1. capy switch red          -> tap it back to blue (only ever when it's red)
  2. round X close showing     -> tap it (e.g. the energy shop, Guild Info)
  3. "Tap to close" popup      -> tap an empty spot to dismiss it
  4. bottom nav bar showing    -> its middle crossed-swords (Adventure) tab
  5. otherwise (the fallback)  -> the back arrow at the bottom-left
A screen-specific element (the X, the popup, the nav bar) wins over the back arrow,
which most full screens have (Homestead, Amber Bay, Guild). Screens reached from the
bottom nav bar (e.g. the Shop) have no X or back arrow: the way home is the
crossed-swords tab. The selected tab expands and shifts the others, so that tab is
found by its look, not a fixed spot.
"""

from __future__ import annotations

import json
import os
import time
from abc import abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import Match, load_template, ocr_lines
from ..task import Context, Param, Task

# --- run log: when each daily last finished ---------------------------------
# The game's daily reset is 00:00 UTC (the shop's "Refresh Time" countdown lands on
# 5 PM PDT), so a "game day" is the UTC date. In Pacific time that's 5 PM in summer
# and 4 PM in winter: keep every day calculation in UTC, never a fixed local hour.
# Stamps are stored in UTC; only labels are converted to local time, per stamp, so
# they follow daylight saving. The log lives in data/ (gitignored).
RUN_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "daily_runs.json")


def game_day(when: datetime | None = None) -> date:
    return (when or datetime.now(timezone.utc)).astimezone(timezone.utc).date()


def _load_runs() -> dict:
    try:
        with open(RUN_LOG, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def last_run(name: str) -> datetime | None:
    stamp = _load_runs().get(name)
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None


def ran_today(name: str) -> bool:
    when = last_run(name)
    return when is not None and game_day(when) == game_day()


def last_run_label(name: str) -> str:
    """When the daily last finished, in local time (e.g. "5:02 PM")."""
    when = last_run(name)
    return when.astimezone().strftime("%-I:%M %p") if when else "?"


def mark_done(name: str) -> None:
    runs = _load_runs()
    runs[name] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(RUN_LOG), exist_ok=True)
    tmp = RUN_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)
    os.replace(tmp, RUN_LOG)


RERUN_PARAM = Param("rerun", "bool", False, "Run once-a-day dailies again today",
                    hidden=True,
                    help="set by the app's confirmation; -p rerun=true on the CLI")

START_REGION = RelRect(0.30, 0.755, 0.32, 0.075)   # orange Start button (home)
RED_START_REGION = RelRect(0.28, 0.705, 0.35, 0.09)  # its Start button sits higher
SWITCH_ZONE = RelRect(0.631, 0.704, 0.086, 0.137)   # the capy switch in either mode
SWITCH_TILES = RelRect(0.640, 0.755, 0.066, 0.079)  # home's blue tiles (head + arrow)
SWITCH_TAP = Rel(0.673, 0.770)  # the capy head tile in BOTH modes (top / bottom tile)
SWITCH_SETTLE = 4.0             # seconds for the cloud transition after flipping modes
MAX_SWITCH_TAPS = 3             # never flip modes back and forth forever on a misread
NEUTRAL = Rel(0.5, 0.11)  # empty spot above any panel: dismisses a "Tap to close" popup
TAP_TO_CLOSE_REGION = RelRect(0.20, 0.83, 0.60, 0.07)  # a reward popup's "Tap to close"

# Shared sprites in templates/dailies/, matched at several scales because a screen
# can draw them at different sizes (Guild Info's X is ~90% of the shop's).
#   close_x.png        real X 0.98-1.00; best false spot elsewhere ~0.71
#   back_arrow.png     real arrow 0.95-1.00; best false spot elsewhere ~0.51
#   adventure_tab.png  unselected crossed swords (no badge) 1.00; best other ~0.63,
#                      the selected one on the home screen ~0.75 (home wins first)
SPRITE_THRESHOLD = 0.85
BOTTOM_BAR = RelRect(0.0, 0.88, 1.0, 0.12)  # the nav bar along the bottom
SPRITE_SCALES = [round(s, 2) for s in np.arange(0.70, 1.16, 0.05)]

HOME, SWITCH_RED, SWITCH_UNKNOWN, AWAY = "home", "switch-red", "switch-unknown", "away"


TAP_SETTLE = 1.0  # every tap in a daily is followed by this pause (user: ~1s per tap)


def wait(ctx: Context, seconds: float) -> bool:
    """Sleep in short slices so a stop lands quickly. True if a stop was requested."""
    end = time.time() + seconds
    while True:
        if ctx.should_stop():
            return True
        remaining = end - time.time()
        if remaining <= 0:
            return False
        time.sleep(min(0.2, remaining))


def tap(ctx: Context, target: Rel | Match, settle: float = TAP_SETTLE) -> bool:
    """THE way dailies click: tap a window-relative point (Rel) or a found sprite
    (Match), then pause `settle` seconds so the game can react. False if a stop was
    requested (the caller should bail out)."""
    if ctx.should_stop():
        return False
    if isinstance(target, Match):
        ctx.click_match(target)
    else:
        ctx.click_rel(target)
    return not wait(ctx, settle)


def _crop(frame, region: RelRect):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region.to_pixels(w, h)
    return frame[y0:y1, x0:x1]


def _says_start(frame, region: RelRect) -> bool:
    return "start" in " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def _start_visible(frame) -> bool:
    """The home screen's orange Start button is showing, not covered or dimmed."""
    crop = _crop(frame, START_REGION)
    b, r = float(crop[..., 0].mean()), float(crop[..., 2].mean())
    if r - b < 80:  # ~133 when visible; ~40 under a panel, ~4 under a dimmed popup
        return False
    return _says_start(frame, START_REGION)


def _switch_colors(frame) -> tuple[float, float]:
    """(red, blue) pixel fractions of the capy switch: red over the whole zone (the
    red switch sits higher), blue over home's tiles only. Home (blue): red ~0.01,
    blue ~0.65. Amber Bay (red): ~0.25 / 0.00. A popup's dimming kills both, so the
    screen reads as AWAY.

    Both are measured on the switch's own colors because the chapter scene behind
    it changes: the "Ancient Frogdom" chapter puts an orange brick wall above the
    switch, which the old red test (and a zone-wide blue share) took for the red
    switch, so go_home flipped the mode back and forth. The switch's red is crimson
    (blue >= green, ~(225,97,108)); bricks are orange (blue < green, ~(172,86,60))."""
    c = _crop(frame, SWITCH_ZONE).astype(np.int16)
    b, g, r = c[..., 0], c[..., 1], c[..., 2]
    red = (r > 150) & (r - g > 70) & (r - b > 50) & (b >= g)  # crimson, not orange
    t = _crop(frame, SWITCH_TILES).astype(np.int16)
    tb, tg, tr = t[..., 0], t[..., 1], t[..., 2]
    blue = (tb > tr + 40) & (tb >= tg) & (tb > 90)
    return float(red.mean()), float(blue.mean())


def home_state(frame) -> str:
    """HOME (Start visible + capy switch blue), SWITCH_RED (the other mode, red
    switch), SWITCH_UNKNOWN (home's Start is up but the switch is neither color), or
    AWAY (another screen, or a popup is up)."""
    red, blue = _switch_colors(frame)
    if red >= 0.15 and blue < 0.10 and _says_start(frame, RED_START_REGION):
        return SWITCH_RED
    if not _start_visible(frame):
        return AWAY
    return HOME if blue >= 0.50 else SWITCH_UNKNOWN


def find_sprite(ctx: Context, frame, name: str,
                region: RelRect | None = None) -> Match | None:
    """A shared sprite from templates/dailies/ (e.g. "close_x.png"), wherever (within
    `region`, if given) and at whatever size it is drawn; None if it isn't showing."""
    path = os.path.join(os.path.dirname(ctx.templates_dir), "dailies", name)
    tpl = load_template(path)
    ox = oy = 0
    search = frame
    if region is not None:
        h, w = frame.shape[:2]
        ox, oy, x1, y1 = region.to_pixels(w, h)
        search = frame[oy:y1, ox:x1]
    best = Match(False, 0.0, 0, 0)
    for s in SPRITE_SCALES:
        t = cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        if t.shape[0] > search.shape[0] or t.shape[1] > search.shape[1]:
            continue
        res = cv2.matchTemplate(search, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score > best.score:
            best = Match(score >= SPRITE_THRESHOLD, float(score),
                         ox + loc[0] + t.shape[1] // 2, oy + loc[1] + t.shape[0] // 2)
    return best if best.found else None


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "logs")


def save_snapshot(ctx: Context, label: str) -> str | None:
    """Save the current screen to logs/<label>-<timestamp>.png, so a failed chore
    can be worked out afterwards. None in a dry run or if the capture fails."""
    if ctx.dry_run:
        return None
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.png")
        return path if cv2.imwrite(path, ctx.frame()) else None
    except Exception:  # a failed screenshot must never break the run
        return None


def tap_to_close_up(frame) -> bool:
    """A reward popup's "Tap to close" is showing. The text is drawn over whatever
    is behind the popup, so OCR can glue it to that ("...Daily ChancTap to close");
    match with spaces removed and accept either half."""
    crop = _crop(frame, TAP_TO_CLOSE_REGION)
    text = "".join(t for t, _, _ in ocr_lines(crop)).lower().replace(" ", "")
    return "taptoclose" in text or "toclose" in text or "tapto" in text


def next_move(ctx: Context, frame):
    """The next step toward home, as (move, target): target is a Rel or a Match to
    tap, or None for "home" (done), "stuck" (give up) and "unknown" (nothing to tap
    yet - e.g. mid-transition)."""
    state = home_state(frame)
    if state == HOME:
        return "home", None
    if state == SWITCH_UNKNOWN:
        return "stuck", None
    if state == SWITCH_RED:
        return "switch", SWITCH_TAP
    x = find_sprite(ctx, frame, "close_x.png")
    if x is not None:
        return "x", x
    if tap_to_close_up(frame):
        return "dismiss", NEUTRAL
    adventure = find_sprite(ctx, frame, "adventure_tab.png", BOTTOM_BAR)
    if adventure is not None:
        return "adventure", adventure
    back = find_sprite(ctx, frame, "back_arrow.png")
    if back is not None:
        return "back", back
    return "unknown", None


_MOVE_LOG = {
    "switch": "capy switch is red -> tap it back to blue",
    "x": "tap the X",
    "dismiss": "dismiss the popup",
    "adventure": "tap the crossed-swords Adventure tab",
    "back": "tap the back arrow",
    "unknown": "nothing to back out with -> tap an empty spot",
}


def go_home(ctx: Context, max_steps: int = 10) -> bool:
    """Back out to the home screen, one move at a time. True once it's there."""
    if ctx.dry_run:
        return True
    switch_taps = 0
    unknowns = 0
    for _ in range(max_steps):
        if ctx.should_stop():
            return False
        move, target = next_move(ctx, ctx.frame())
        if move == "home":
            return True
        if move == "stuck":
            ctx.log.warning("on the main screen, but the capy switch is neither blue "
                            "nor red")
            return False
        if move == "switch":
            if switch_taps >= MAX_SWITCH_TAPS:
                ctx.log.warning("the capy switch is still red after %d taps",
                                switch_taps)
                return False
            switch_taps += 1
        if move == "unknown":
            unknowns += 1
            if unknowns == 1:  # often just a transition: give it a moment first
                if wait(ctx, 1.0):
                    return False
                continue
            target = NEUTRAL
        else:
            unknowns = 0
        ctx.log.info("back to home: %s", _MOVE_LOG[move])
        if not tap(ctx, target, SWITCH_SETTLE if move == "switch" else TAP_SETTLE):
            return False
    return home_state(ctx.frame()) == HOME


QUIT_TIMEOUT = 10.0       # the game gets this long to quit before it's forced
LAUNCH_TIMEOUT = 90.0     # relaunched game: its window must show by then
LOAD_TIMEOUT = 180.0      # then the home screen, through loading and popups


def restart_game(ctx: Context) -> bool:
    """Quit the game and open it again, then get to the home screen. For when the
    game is stuck (e.g. a frozen fight). True once on the home screen."""
    if ctx.dry_run:
        ctx.log.info("DRY-RUN restart the game")
        return True
    import subprocess

    import os

    win = ctx.config["window"]
    app = win.get("app_path", "/Applications/CapybaraGo!.app")
    launch = (["open", app] if os.path.isdir(app)
              else ["open", "-b", win.get("bundle_id", "com.habby.capybara")])
    pid = _game_pid(ctx)
    shot = save_snapshot(ctx, "before-restart") if _window_on_screen(ctx) else None
    ctx.log.warning("restarting the game (it looks stuck)%s",
                    f"; screen saved: {shot}" if shot else "")
    # The game is an iPhone app running on the Mac: it never answers an
    # AppleScript "quit" (that hung for 20s), so end its process with a signal:
    # SIGTERM first, SIGKILL after QUIT_TIMEOUT. No extra macOS permission needed.
    if pid:
        subprocess.run(["kill", "-TERM", str(pid)], capture_output=True)
    end = time.time() + QUIT_TIMEOUT
    while _window_up(ctx) and time.time() < end:
        if wait(ctx, 0.5):
            return False
    if _window_up(ctx):
        ctx.log.warning("the game didn't quit; forcing it")
        if pid:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True)
        if wait(ctx, 2.0):
            return False
    ctx.log.info("the game is closed; opening it again")
    subprocess.run(launch, capture_output=True, timeout=20)
    end = time.time() + LAUNCH_TIMEOUT
    while not _window_on_screen(ctx):
        if time.time() >= end:
            ctx.log.warning("the game's window didn't come back")
            return False
        if wait(ctx, 1.0):
            return False
    ctx.log.info("the game's window is back; waiting for the home screen")
    end = time.time() + LOAD_TIMEOUT
    unknowns = 0
    while time.time() < end:
        if ctx.should_stop():
            return False
        frame = ctx.frame()
        move, target = next_move(ctx, frame)
        if move == "home":
            ctx.log.info("the game restarted and is on the home screen")
            return True
        if move in ("unknown", "stuck"):  # loading, or a start-up screen
            unknowns += 1
            if unknowns % 4 == 0:   # every few seconds, tap an empty spot
                ctx.log.info("restart: tap an empty spot")
                tap(ctx, NEUTRAL)
            elif wait(ctx, 1.0):
                return False
            continue
        unknowns = 0
        ctx.log.info("restart: %s", _MOVE_LOG.get(move, move))
        if not tap(ctx, target, SWITCH_SETTLE if move == "switch" else TAP_SETTLE):
            return False
    shot = save_snapshot(ctx, "restart-not-home")
    ctx.log.warning("the restarted game didn't reach the home screen%s",
                    f"; screen saved: {shot}" if shot else "")
    return False


def _game_window_info(ctx: Context) -> dict | None:
    """The game's main window, on screen or not (hidden, minimized, other Space)."""
    import Quartz

    owner = ctx.window.owner.lower()
    for w in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                               Quartz.kCGNullWindowID) or []:
        if owner in (w.get("kCGWindowOwnerName") or "").lower():
            b = w.get("kCGWindowBounds", {})
            if b.get("Width", 0) >= 300 and b.get("Height", 0) >= 300:
                return w
    return None


def _window_up(ctx: Context) -> bool:
    """The game is running (its window exists, on screen or not)."""
    return _game_window_info(ctx) is not None


def _game_pid(ctx: Context) -> int | None:
    w = _game_window_info(ctx)
    return int(w["kCGWindowOwnerPID"]) if w else None


def _window_on_screen(ctx: Context) -> bool:
    from ..window import WindowNotFound

    try:
        ctx.window.bounds()
        return True
    except WindowNotFound:
        return False


def go_screen(ctx: Context, name: str, on_screen: Callable, button: Rel,
              max_steps: int = 12) -> bool:
    """Get to a screen opened by a home-screen button (Events, Guild, the menu) from
    anywhere: from home tap the button; from inside it (or a popup) back out with
    go_home's moves until on_screen(frame) holds."""
    if ctx.dry_run:
        return True
    opened = 0
    unknowns = 0
    for _ in range(max_steps):
        if ctx.should_stop():
            return False
        frame = ctx.frame()
        if on_screen(frame):
            return True
        if home_state(frame) == HOME:
            if opened >= 2:
                ctx.log.warning("tapped %s twice but it didn't open", name)
                return False
            opened += 1
            ctx.log.info("to %s: tap %s", name, name)
            if not tap(ctx, button):
                return False
            continue
        move, target = next_move(ctx, frame)
        if move == "stuck":
            ctx.log.warning("on the main screen, but the capy switch is neither blue "
                            "nor red")
            return False
        if move == "unknown":
            unknowns += 1
            if unknowns == 1:  # often just a transition: give it a moment
                if wait(ctx, 1.0):
                    return False
                continue
            target = NEUTRAL
        else:
            unknowns = 0
        ctx.log.info("to %s: %s", name, move)
        if not tap(ctx, target, SWITCH_SETTLE if move == "switch" else TAP_SETTLE):
            return False
    return on_screen(ctx.frame())


@dataclass
class ChoreGroup:
    """A run of chores that share a base screen: every chore in the group starts
    and ends there (dailies: home; events: the Events screen)."""
    name: str                            # also the section heading in the app
    chores: list                         # DailyTask subclasses, in run order
    go_base: Callable[[Context], bool]   # gets to the base screen from anywhere
    base: str                            # base screen name, for the log


def chore_params(groups) -> list[Param]:
    """One on/off switch per chore, under its group's heading, plus the hidden
    re-run flag."""
    return [Param(c.param_key(), "bool", True, c.label(), help=c.DESCRIPTION,
                  section=g.name)
            for g in groups for c in g.chores] + [RERUN_PARAM]


class ChoreRunner(Task):
    """Runs groups of chores (DailyTask subclasses) in order - the engine behind
    auto-daily. Subclasses set GROUPS and PARAMS = chore_params(GROUPS).

    Only switched-on chores run. Each group gets to its base screen first, and every
    chore in it starts and ends there (go_base runs after each one, finished or not).
    finish() runs at the very end (back home). A chore that fails (or crashes) is
    logged and skipped. If a group's base screen can't be reached, the rest of that
    group is skipped and the next group still runs. A chore that already finished
    this game day is skipped unless `rerun` is set (the app asks before Start)."""

    GROUPS: list[ChoreGroup] = []

    @classmethod
    def chores(cls) -> list:
        return [c for g in cls.GROUPS for c in g.chores]

    def finish(self, ctx: Context) -> None:
        """After the last chore: leave the game on the home screen."""
        go_home(ctx)

    @classmethod
    def already_done_today(cls, params: dict) -> list[tuple[str | None, str, str]]:
        return [(c.param_key(), c.label(), last_run_label(c.name)) for c in cls.chores()
                if params.get(c.param_key()) and c.done_today()]

    def _run_one(self, ctx: Context, cls) -> bool:
        own_templates = ctx.templates_dir
        ctx.templates_dir = os.path.join(os.path.dirname(own_templates), cls.name)
        chore = cls()
        chore.configure({})
        try:
            return chore.run_daily(ctx)
        except Exception:  # one broken chore shouldn't sink the rest
            ctx.log.exception("%s crashed", cls.name)
            return False
        finally:
            ctx.templates_dir = own_templates

    def run(self, ctx: Context) -> None:
        enabled = [c for c in self.chores() if self.params.get(c.param_key())]
        skipped = [c for c in enabled if c.done_today() and not self.params.get("rerun")]
        for c in skipped:
            ctx.log.warning("%s already ran today (at %s) -> skipping. Confirm in the "
                            "app, or pass -p rerun=true, to run it again.",
                            c.name, last_run_label(c.name))
        todo = [c for c in enabled if c not in skipped]
        if not todo:
            ctx.log.warning("nothing to run")
            return
        ctx.log.info("to run: %s", ", ".join(c.name for c in todo))

        finished: list[str] = []
        failed: dict[str, str] = {}  # chore name -> why, for the summary
        for group in self.GROUPS:
            chores = [c for c in group.chores if c in todo]
            if not chores or ctx.should_stop():
                continue
            ctx.log.info("=== %s ===", group.name)
            if not group.go_base(ctx):
                if ctx.should_stop():
                    break
                ctx.log.warning("couldn't get to the %s -> skipping %s", group.base,
                                ", ".join(c.name for c in chores))
                for c in chores:
                    failed[c.name] = f"not run: couldn't get to the {group.base}"
                continue
            for i, cls in enumerate(chores):
                if ctx.should_stop():
                    break
                ctx.log.info("--- %s ---", cls.name)
                ok = self._run_one(ctx, cls)
                if ctx.should_stop():
                    break
                if ok:
                    finished.append(cls.name)
                    if not ctx.dry_run:  # a dry run did nothing, so it doesn't count
                        mark_done(cls.name)
                    ctx.log.info("%s done", cls.name)
                else:
                    shot = save_snapshot(ctx, f"failed-{cls.name}")
                    failed[cls.name] = "did not finish (see the log above)" + (
                        f"; screen saved: {shot}" if shot else "")
                    ctx.log.warning("%s did not finish; returning to the %s and moving "
                                    "on%s", cls.name, group.base,
                                    f" (screen saved: {shot})" if shot else "")
                if not group.go_base(ctx):
                    if ctx.should_stop():
                        break
                    rest = chores[i + 1:]
                    ctx.log.warning("couldn't get back to the %s after %s -> skipping "
                                    "the rest of %s%s", group.base, cls.name, group.name,
                                    f" ({', '.join(c.name for c in rest)})" if rest else "")
                    for c in rest:
                        failed[c.name] = f"not run: couldn't get back to the {group.base}"
                    break

        if not ctx.should_stop():
            self.finish(ctx)
        self._summary(ctx, todo, finished, failed, skipped)

    def _summary(self, ctx: Context, todo, finished, failed, skipped) -> None:
        """The end-of-run summary in the log: what ran, what was skipped, and a
        "Needs your attention" list - every flag a chore raised (things to handle
        by hand, e.g. the arena running out of beatable opponents) and every chore
        that failed, with its saved screen."""
        log = ctx.log
        log.info("==================== %s summary ====================", self.title())
        if ctx.kill.stop:
            log.info("Stopped early.")
        log.info("Done %d of %d%s", len(finished), len(todo),
                 f": {', '.join(finished)}" if finished else "")
        if skipped:
            log.info("Skipped, already ran today: %s", ", ".join(c.name for c in skipped))
        attention = [[who, what] for who, what in ctx.flags]
        for name, why in failed.items():
            flags = [line for line in attention if line[0] == name]
            if flags:  # its flag already says what went wrong; add the screen to it
                shot = why.partition("screen saved: ")[2]
                if shot:
                    flags[-1][1] += f" (screen saved: {shot})"
            else:
                attention.append([name, why])
        attention = [f"{who}: {what}" for who, what in attention]
        if attention:
            log.warning("Needs your attention (%d):", len(attention))
            for line in attention:
                log.warning("  • %s", line)
        else:
            log.info("Nothing needs your attention.")


class DailyTask(Task):
    HIDDEN = True       # reached through auto-daily, not its own home card
    LABEL: str = ""     # the switch label on the auto-daily screen
    # Each daily tracks its own last finish in the run log. Once it has finished this
    # game day it is skipped (the app asks first; -p rerun=true on the CLI).
    ONCE_PER_DAY = True
    PARAMS = [RERUN_PARAM]

    @classmethod
    def param_key(cls) -> str:
        """The auto-daily switch key, e.g. "energy-claim" -> "energy_claim"."""
        return cls.name.replace("-", "_")

    @classmethod
    def label(cls) -> str:
        return cls.LABEL or cls.title()

    @classmethod
    def done_today(cls) -> bool:
        return cls.ONCE_PER_DAY and ran_today(cls.name)

    @classmethod
    def already_done_today(cls, params: dict) -> list[tuple[str | None, str, str]]:
        if cls.done_today():
            return [(None, cls.label(), last_run_label(cls.name))]
        return []

    def run(self, ctx: Context) -> None:
        """Running this one chore on its own (the runners call run_daily directly)."""
        if self.done_today() and not self.params.get("rerun"):
            ctx.log.warning("%s already ran today (at %s) -> skipping. Confirm in the "
                            "app, or pass -p rerun=true, to run it again.",
                            self.name, last_run_label(self.name))
            return
        if not self.prepare(ctx):
            if not ctx.should_stop():
                ctx.log.warning("%s: couldn't get to its starting screen", self.name)
            return
        ok = self.run_daily(ctx)
        if ok and not ctx.dry_run:  # a dry run did nothing, so it doesn't count
            mark_done(self.name)
        if not ok and not ctx.should_stop():
            shot = save_snapshot(ctx, f"failed-{self.name}")
            if shot:
                ctx.log.warning("%s: screen saved: %s", self.name, shot)
        if not ctx.should_stop():
            self.wrap_up(ctx, ok)
        ctx.log.info("%s %s", self.name, "done" if ok else "did not finish")

    def prepare(self, ctx: Context) -> bool:
        """Standalone run: get to the screen run_daily starts on. Dailies start on the
        home screen, where the player launches them, so there's nothing to do."""
        return True

    def wrap_up(self, ctx: Context, ok: bool) -> None:
        """Standalone run: leave the game on the home screen."""
        if not ok:
            ctx.log.warning("%s did not finish; returning to the home screen", self.name)
        go_home(ctx)

    @abstractmethod
    def run_daily(self, ctx: Context) -> bool:
        """Do the daily. True if it finished back on the home screen."""

    # --- helpers ----------------------------------------------------------
    def wait(self, ctx: Context, seconds: float) -> bool:
        return wait(ctx, seconds)

    def flag(self, ctx: Context, message: str) -> None:
        """Something the player should handle by hand: logged now, and listed under
        "Needs your attention" in the runner's end-of-run summary."""
        ctx.log.warning("%s: FLAG - %s", self.name, message)
        ctx.flags.append((self.name, message))

    def tap(self, ctx: Context, target: Rel | Match, what: str) -> bool:
        """Log and tap (a Rel or a found Match), then the standard ~1s pause. False
        if a stop was requested (the caller should bail out)."""
        if ctx.should_stop():
            return False
        ctx.log.info("%s: tap %s", self.name, what)
        return tap(ctx, target)

    @staticmethod
    def text_in(ctx: Context, region: RelRect) -> str:
        """Lower-cased OCR text inside a window-relative region of a fresh frame."""
        crop = _crop(ctx.frame(), region)
        return " ".join(t for t, _, _ in ocr_lines(crop)).lower()


class ScreenTask(DailyTask):
    """A chore that lives behind a home-screen button (Events, Guild, the menu):
    run_daily starts on that screen and returns True once it's back there, so the
    group's chores run back to back. Subclasses set go_base to the screen's go_*
    function (e.g. go_base = staticmethod(go_events)). Run alone, it goes to that
    screen first and home at the end."""
    go_base: Callable[[Context], bool]

    def prepare(self, ctx: Context) -> bool:
        return self.go_base(ctx)

    def wrap_up(self, ctx: Context, ok: bool) -> None:
        if not ok:
            ctx.log.warning("%s did not finish; returning to the home screen", self.name)
        go_home(ctx)
