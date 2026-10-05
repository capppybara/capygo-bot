"""Guild chore: guild-trade (plunder 4 boats).

Starts on the guild screen: Guild Trade -> the bottom-right tab "Others' Trades" ->
the "Plunder" sea, with "Looted today: N/4" at the top right. Tapping a boat
selects it; the panel at the bottom shows its rarity banner, "Times plundered:
x/y", owner, power, cargo and a Plunder button. A plunder is a fight like the
arena's (Skip, then a Victory/Defeat screen with OK); a win counts toward 4.

Rules (user, 2026-10-04):
  - Targets, found on the MAP only: a gilded boat (gold barge with a crown,
    plunderable once) or a golden boat (orange sail, twice). A gilded boat always
    has its owner's avatar above it, which opens their profile - tap the hull
    below it instead.
  - The map sometimes shows a boat as gold when it isn't: after tapping, the
    panel's banner must be the UR orange too.
  - Power below 6T, and one of the first 2 cargo slots is a golden chest or 200
    badges (the badge emblem, matched by picture, with "x200" under it). Both
    pictures are templates in templates/guild-trade/. Nothing past slot 2 matters, and the
    cargo row is never dragged (a press on an item opens its info).
  - A lost fight: move on. No suitable boat left: Refresh (free, no limit).
  - Stop at 4 looted today.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import load_template, ocr_lines
from ..task import Context, register
from .daily import _crop, find_sprite, tap_to_close_up
from .event_arena import SKIP_BTN, _power, fight_up
from .guild import GuildTask, go_guild

TITLE = RelRect(0.10, 0.035, 0.32, 0.045)          # "Guild Trade" / "Plunder"
OTHERS_TAB = Rel(0.821, 0.952)                     # "Others' Trades", bottom-right
LOOTED = RelRect(0.62, 0.035, 0.34, 0.045)         # "Looted today: N/4"
SEA = RelRect(0.097, 0.089, 0.612, 0.484)          # the boats (left of the big ship)
REFRESH_BTN = Rel(0.413, 0.589)                    # green Refresh above the panel
BANNER = RelRect(0.514, 0.627, 0.171, 0.019)       # panel banner: UR = orange-red
PLUNDERED = RelRect(0.28, 0.650, 0.30, 0.030)      # "Times plundered: x/y"
POWER = RelRect(0.31, 0.712, 0.14, 0.030)          # the owner's power
SLOTS = [RelRect(x0 / 642, 716 / 951, (x1 - x0) / 642, 60 / 951)
         for x0, x1 in ((95, 151), (152, 208))]    # cargo slots 1 and 2
PLUNDER_BTN = Rel(0.500, 0.845)
RESULT_TITLE = RelRect(0.25, 0.37, 0.50, 0.08)     # "Victory" / "Defeat"
OK_BTN = Rel(0.5, 0.816)                           # higher than the arena's OK
OK_LABEL = RelRect(0.35, 0.795, 0.30, 0.045)
PROFILE_TITLE = RelRect(0.25, 0.095, 0.50, 0.05)   # "Character Info" (a boat owner's)

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "templates", "guild-trade")   # chest.png, badge.png

TARGET = 4                 # the game's daily cap
MAX_POWER = Decimal(6)     # user: < 6T
MAX_REFRESHES = 30         # Refresh is free, but don't loop forever
CHEST_MATCH = 0.75         # chest.png: real 0.91-1.00, anything else <= 0.26
BADGE_MATCH = 0.70         # badge.png (the emblem only): badges 0.86-1.00, else <= 0.42
MIN_BADGES = 200           # user: "x200" (other badge stacks show x40)
POLL = 0.5
SETTLE = 1.0
SELECT_SETTLE = 1.2        # tap a boat -> its panel
LOAD_TIMEOUT = 10.0
FIGHT_TIMEOUT = 15.0
FIGHT_SETTLE = 2.0         # user: give the fight a couple of seconds before Skip
SKIP_RETRY = 6.0
RESULT_TIMEOUT = 30.0


@dataclass
class Boat:
    kind: str     # "gilded" / "golden" (as seen on the map)
    at: Rel       # where to tap


@dataclass
class Panel:
    ur: bool
    plundered: tuple[int, int] | None
    power: Decimal | None
    chest: bool
    badge: bool


def _words(frame, region: RelRect, scale: int = 1) -> str:
    crop = _crop(frame, region)
    if scale > 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return " ".join(t for t, _, _ in ocr_lines(crop))


def on_plunder(frame) -> bool:
    return "plunder" in _words(frame, TITLE).lower() and looted(frame) is not None


def looted(frame) -> int | None:
    m = re.search(r"today:?\s*(\d+)\s*/\s*\d+", _words(frame, LOOTED).lower())
    return int(m.group(1)) if m else None


def find_boats(frame) -> list[Boat]:
    """Gilded and golden boats on the sea, by their gold: a tall gold blob is a
    gilded boat's hull (tap ~10px below its middle, clear of the owner's avatar
    above it); a wide one is a golden boat's orange sail."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = SEA.to_pixels(w, h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    hh, s, v = (hsv[..., i].astype(int) for i in range(3))
    gold = ((hh >= 12) & (hh <= 26) & (s >= 120) & (v >= 200)).astype(np.uint8)
    n, _, stats, centers = cv2.connectedComponentsWithStats(gold, 8)
    k = w / 642                                  # sizes were measured at 642px wide
    boats = []
    for i in range(1, n):
        bw, bh, area = stats[i][2], stats[i][3], stats[i][4]
        cx, cy = centers[i][0] + x0, centers[i][1] + y0
        # The gilded hull shimmers: its gold read 810px in one frame, 226px in
        # another, so a tall blob counts from 150px. Sails are steadier (~730px);
        # their small top halves (~190px) must not count, so wide ones need 400.
        if bh > 1.5 * bw and area >= 150 * k * k:
            boats.append(Boat("gilded", Rel(cx / w, (cy + 10 * k) / h)))
        elif bw > bh and area >= 400 * k * k:
            boats.append(Boat("golden", Rel(cx / w, cy / h)))
    return boats


def read_panel(frame) -> Panel:
    r, _, b = (float(c) for c in _crop(frame, BANNER).reshape(-1, 3).mean(0)[::-1])
    m = re.search(r"(\d)\s*/\s*(\d)", _words(frame, PLUNDERED))
    chest = badge = False
    for slot in SLOTS:  # the prize is always in slot 1 or 2 (user)
        tile = _crop(frame, slot)
        if _match(tile, "chest") >= CHEST_MATCH:
            chest = True
        elif _match(tile, "badge") >= BADGE_MATCH and _count(frame, slot) >= MIN_BADGES:
            badge = True
    return Panel(ur=r > 180 and r - b > 100,
                 plundered=(int(m.group(1)), int(m.group(2))) if m else None,
                 power=_power(_words(frame, POWER, scale=2)), chest=chest, badge=badge)


def _match(tile, name: str) -> float:
    return float(cv2.matchTemplate(tile, _template(name), cv2.TM_CCOEFF_NORMED).max())


def _count(frame, slot: RelRect) -> int:
    """A cargo tile's "x200" count (0 if unreadable)."""
    m = re.search(r"[x×]\s*(\d+)", _words(frame, slot, scale=3).lower())
    return int(m.group(1)) if m else 0


@lru_cache(maxsize=None)
def _template(name: str):
    return load_template(os.path.join(TEMPLATES, f"{name}.png"))


def why_not(p: Panel) -> str | None:
    """None if the selected boat is worth plundering, else the reason it isn't."""
    if not p.ur:
        return "not UR (the map showed gold, the banner doesn't)"
    if p.plundered is None or p.plundered[0] >= p.plundered[1]:
        return f"already plundered ({p.plundered})"
    if p.power is None:
        return "power unreadable"
    if p.power >= MAX_POWER:
        return f"too strong ({p.power}T)"
    if not (p.chest or p.badge):
        return "no chest or 200 badges in the first 2 slots"
    return None


@register("guild-trade")
class GuildTrade(GuildTask):
    TITLE = "Guild Trade"
    LABEL = "Guild trade plunder"
    ICON = "🏴‍☠️"
    DESCRIPTION = ("Guild -> Guild Trade -> Others' Trades: plunder gilded/golden boats "
                   "under 6T with a chest or 200 badges up front, until 4 are looted, "
                   "then go back.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_place(ctx, "guild trade"):
            return False
        if ctx.dry_run:
            return go_guild(ctx)
        if not self._wait_for(ctx, "Guild Trade",
                              lambda f: "guild trade" in _words(f, TITLE).lower(),
                              LOAD_TIMEOUT):
            return False
        if not self.tap(ctx, OTHERS_TAB, "Others' Trades"):
            return False
        if not self._wait_for(ctx, "the Plunder sea", on_plunder, LOAD_TIMEOUT):
            return False

        tried: set[tuple[int, int]] = set()   # boats already checked on this sea
        refreshes = wins = losses = 0
        while True:
            count = looted(ctx.frame())
            if count is None:
                if not self._wait_for(ctx, "the Plunder sea", on_plunder, LOAD_TIMEOUT):
                    return False
                continue
            if count >= TARGET:
                ctx.log.info("%s: looted %d/%d today -> done (%d won, %d lost this run)",
                             self.name, count, TARGET, wins, losses)
                break
            boat = self._pick(ctx, tried)
            if ctx.should_stop():
                return False
            if boat is None:
                if refreshes >= MAX_REFRESHES:
                    self.flag(ctx, f"no suitable boat after {refreshes} refreshes "
                                   f"(looted {count}/{TARGET}). Plunder the rest by hand.")
                    return False
                refreshes += 1
                ctx.log.info("%s: no suitable boat here -> Refresh (%d)", self.name,
                             refreshes)
                if not self.tap(ctx, REFRESH_BTN, "Refresh"):
                    return False
                if self.wait(ctx, SETTLE):
                    return False
                tried.clear()
                continue
            result = self._plunder(ctx)
            if result is None:
                return False
            wins += result == "victory"
            losses += result == "defeat"
            ctx.log.info("%s: plunder -> %s", self.name, result)
        return go_guild(ctx)  # back arrow -> the guild screen

    # --- steps ------------------------------------------------------------
    def _pick(self, ctx: Context, tried: set) -> Boat | None:
        """Tap the map's gilded/golden boats not checked yet on this sea, one at a
        time, until one passes the panel checks (left selected). None if none do."""
        for boat in find_boats(ctx.frame()):
            key = (round(boat.at.x * 30), round(boat.at.y * 30))
            if key in tried:
                continue
            tried.add(key)
            if not self.tap(ctx, boat.at, f"{boat.kind} boat"):
                return None
            if self.wait(ctx, SELECT_SETTLE - 1.0):  # tap already waited ~1s
                return None
            frame = ctx.frame()
            if "character info" in _words(frame, PROFILE_TITLE).lower():
                # the tap caught the owner's avatar after all: close it, move on
                ctx.log.info("%s: opened the owner's profile by mistake; closing it",
                             self.name)
                x = find_sprite(ctx, frame, "close_x.png")
                if x is None or not self.tap(ctx, x, "close X"):
                    return None
                continue
            panel = read_panel(frame)
            reason = why_not(panel)
            if reason is None:
                ctx.log.info("%s: %s boat %sT, %s -> plunder", self.name, boat.kind,
                             panel.power, "chest" if panel.chest else "200 badges")
                return boat
            ctx.log.info("%s: skip %s boat: %s", self.name, boat.kind, reason)
        return None

    def _plunder(self, ctx: Context) -> str | None:
        """Plunder the selected boat: fight, Skip, OK, back on the sea. The result
        ("victory"/"defeat"/"unknown", or "no fight" if it didn't start), or None
        on a stop or a timeout (logged)."""
        if not self.tap(ctx, PLUNDER_BTN, "Plunder"):
            return None
        if not self._wait_for(ctx, None, fight_up, FIGHT_TIMEOUT, settle=FIGHT_SETTLE):
            if ctx.should_stop():
                return None
            ctx.log.info("%s: the fight didn't start; clearing the screen", self.name)
            frame = ctx.frame()
            x = find_sprite(ctx, frame, "close_x.png")
            if x is not None:
                self.tap(ctx, x, "close X")
            elif tap_to_close_up(frame):
                self.tap(ctx, OK_BTN, "dismiss the popup")
            return "no fight" if self._wait_for(ctx, "the Plunder sea", on_plunder,
                                                LOAD_TIMEOUT) else None
        end = time.time() + RESULT_TIMEOUT
        last_skip = None
        while time.time() < end:
            frame = ctx.frame()
            title = _words(frame, RESULT_TITLE).lower()
            if "victory" in title or "defeat" in title or \
                    "ok" in _words(frame, OK_LABEL).lower().split():
                if self.wait(ctx, SETTLE):
                    return None
                result = next((r for r in ("victory", "defeat")
                               if r in _words(ctx.frame(), RESULT_TITLE).lower()), "unknown")
                if not self.tap(ctx, OK_BTN, "OK"):
                    return None
                if not self._wait_for(ctx, "the Plunder sea", on_plunder, LOAD_TIMEOUT):
                    return None
                return result
            if on_plunder(frame):
                return "unknown"  # the result closed itself
            if fight_up(frame) and (last_skip is None
                                    or time.time() - last_skip >= SKIP_RETRY):
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
