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
from datetime import date, datetime, timezone

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import Match, load_template, ocr_lines
from ..task import Context, Param, Task

# --- run log: when each daily last finished ---------------------------------
# The game's daily reset is 00:00 UTC (the shop's "Refresh Time" countdown lands on
# 5 PM PDT), so a "game day" is the UTC date. The log lives in data/ (gitignored).
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
    """(red, blue) pixel fractions where the capy switch sits in either mode.
    Home (blue): ~0.01 / ~0.60. Amber Bay (red): ~0.28 / 0.00. Every other screen
    seen: <= 0.03 red. A popup's dimming kills both, so the screen reads as AWAY."""
    c = _crop(frame, SWITCH_ZONE).astype(np.int16)
    b, g, r = c[..., 0], c[..., 1], c[..., 2]
    red = (r > 150) & (r - g > 70) & (r - b > 50)   # crimson, not the orange Start
    blue = (b > r + 40) & (b >= g) & (b > 90)
    return float(red.mean()), float(blue.mean())


def home_state(frame) -> str:
    """HOME (Start visible + capy switch blue), SWITCH_RED (the other mode, red
    switch), SWITCH_UNKNOWN (home's Start is up but the switch is neither color), or
    AWAY (another screen, or a popup is up)."""
    red, blue = _switch_colors(frame)
    if red >= 0.15 and _says_start(frame, RED_START_REGION):
        return SWITCH_RED
    if not _start_visible(frame):
        return AWAY
    return HOME if blue >= 0.35 else SWITCH_UNKNOWN


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
        if self.done_today() and not self.params.get("rerun"):
            ctx.log.warning("%s already ran today (at %s) -> skipping. Confirm in the "
                            "app, or pass -p rerun=true, to run it again.",
                            self.name, last_run_label(self.name))
            return
        ok = self.run_daily(ctx)
        if ok and not ctx.dry_run:  # a dry run did nothing, so it doesn't count
            mark_done(self.name)
        elif not ctx.should_stop():
            ctx.log.warning("%s did not finish; returning to the home screen", self.name)
            go_home(ctx)
        ctx.log.info("%s %s", self.name, "done" if ok else "did not finish")

    @abstractmethod
    def run_daily(self, ctx: Context) -> bool:
        """Do the daily. True if it finished back on the home screen."""

    # --- helpers ----------------------------------------------------------
    def wait(self, ctx: Context, seconds: float) -> bool:
        return wait(ctx, seconds)

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
