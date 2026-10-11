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
  - Both a chest boat and a 200-badges boat on the sea: take the chest one.
  - A lost fight: move on. No suitable boat left: Refresh (free, no limit).
  - Stop at 4 looted today.

Popups (user, 2026-10-07: "build in some fail safes to dismiss popups"): opening
Guild Trade can bring a "Bountiful Return" letter (a guild-mate's cargo ship came
back; dividends) under a "Rewards / Tap to close" popup, and the sea can be
covered by a boat owner's Character Info or a cargo item's info. Neither the
Guild Trade screen nor the Plunder sea has a round X or "Tap to close" of its
own, and both still READ as themselves under a popup's dimming, so every wait
and every turn of the plunder loop first closes whatever popup is up: a reward
with a tap above its band, a panel with its X.
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
from .daily import NEUTRAL, _crop, find_sprite, tap_to_close_up
from .event_arena import SKIP_BTN, _power, fight_up
from .guild import GuildTask, go_guild

TITLE = RelRect(0.10, 0.035, 0.32, 0.045)          # "Guild Trade" / "Plunder"
OTHERS_TAB = Rel(0.821, 0.952)                     # "Others' Trades", bottom-right
LOOTED = RelRect(0.62, 0.035, 0.34, 0.045)         # "Looted today: N/4"
SEA = RelRect(0.097, 0.089, 0.806, 0.484)          # the whole sea (x 62-580, y 84-544)
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
GONE_AFTER = 5.0           # still on the sea this long after Plunder: the boat is gone
GONE = "gone"
SKIP_RETRY = 6.0
RESULT_TIMEOUT = 30.0
MAX_POPUPS = 6             # popups closed in a row before giving up (a loop)
MAX_BOAT_H = 150           # px: a gold piece taller than this is no boat (the big ship)
MAX_BOAT_AREA = 2500       # px: nor one bigger (a gilded hull ~800, a sail ~770)


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
    above it); a wide one is a golden boat's orange sail.

    2026-10-10 (user: a once-plundered golden boat wasn't taken again): such a
    boat has a flame drawn on its sail, which split the gold into small pieces
    (185 + 192 + 399 + ...), none a wide 400. So for sails the flame's red-orange
    counts as sail (-> one 774px piece). Not for hulls: red near a gilded hull
    (its owner's avatar) mustn't pull the tap point up onto the avatar. The sea
    used to stop at x 455, left of a big ship that filled the right side; boats
    now sit out to x ~545 and were cut in half, so the whole width is searched
    and anything far bigger than a boat (that big ship) is ignored."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = SEA.to_pixels(w, h)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    hh, s, v = (hsv[..., i].astype(int) for i in range(3))
    gold = ((hh >= 12) & (hh <= 26) & (s >= 120) & (v >= 200)).astype(np.uint8)
    flame = ((hh <= 11) & (s >= 120) & (v >= 180)).astype(np.uint8)
    k = w / 642                                  # sizes were measured at 642px wide

    def blobs(mask):
        n, _, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
        for i in range(1, n):
            bw, bh, area = stats[i][2], stats[i][3], stats[i][4]
            if bh > MAX_BOAT_H * k or area > MAX_BOAT_AREA * k * k:
                continue  # not a boat (the big ship)
            yield bw, bh, area, centers[i][0] + x0, centers[i][1] + y0

    boats = []
    # The gilded hull shimmers: its gold read 810px in one frame, 226px in
    # another, so a tall blob counts from 150px.
    for bw, bh, area, cx, cy in blobs(gold):
        if bh > 1.5 * bw and area >= 150 * k * k:
            boats.append(Boat("gilded", Rel(cx / w, (cy + 10 * k) / h)))
    # Sails are steadier (~730px); their small top halves (~190px) must not
    # count, so wide ones need 400.
    for bw, bh, area, cx, cy in blobs(gold | flame):
        if bw > bh and area >= 400 * k * k and not any(
                abs(b.at.x * w - cx) < 40 * k and abs(b.at.y * h - cy) < 60 * k
                for b in boats):
            boats.append(Boat("golden", Rel(cx / w, cy / h)))
    return boats


def _key(boat: Boat) -> tuple[int, int]:
    """A boat's identity on this sea: its map position, rounded."""
    return round(boat.at.x * 30), round(boat.at.y * 30)


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

        # Boats already checked since the last plunder or refresh. After EVERY
        # plunder this resets (user): all gold boats are checked again before a
        # refresh, which catches a second eligible boat and a boat that allows 2
        # plunders. Boats lost to, or found gone, are skipped until a refresh.
        tried: set[tuple[int, int]] = set()
        skip: set[tuple[int, int]] = set()
        refreshes = wins = losses = 0
        while True:
            if not self._close_popups(ctx):
                return False
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
                skip.clear()
                continue
            result = self._plunder(ctx)
            if result is None:
                return False
            wins += result == "victory"
            losses += result == "defeat"
            ctx.log.info("%s: plunder -> %s", self.name, result)
            if result == GONE:
                # user: no battle = a fake boat, and the game refreshes the boats
                # itself -> a new sea: forget it all, let it settle, check again
                tried.clear()
                skip.clear()
                if self.wait(ctx, SETTLE):
                    return False
                continue
            if result == "defeat":
                skip.add(_key(boat))
            tried = set(skip)  # check every other gold boat again
        return go_guild(ctx)  # back arrow -> the guild screen

    # --- steps ------------------------------------------------------------
    def _pick(self, ctx: Context, tried: set) -> Boat | None:
        """Tap the map's gilded/golden boats not checked yet on this sea, one at a
        time, and leave the one to plunder selected. None if none passes.

        A chest beats 200 badges (user): a chest boat is taken at once; a badge
        boat is kept in reserve while the rest are checked for a chest, and is
        selected again if none has one."""
        reserve = last = None
        for boat in find_boats(ctx.frame()):
            key = _key(boat)
            if key in tried:
                continue
            tried.add(key)
            panel = self._select(ctx, boat)
            last = boat
            if ctx.should_stop():
                return None
            if panel is None:
                continue
            reason = why_not(panel)
            if reason is not None:
                ctx.log.info("%s: skip %s boat: %s", self.name, boat.kind, reason)
            elif panel.chest:
                ctx.log.info("%s: %s boat %sT, chest -> plunder", self.name, boat.kind,
                             panel.power)
                return boat
            elif reserve is None:
                ctx.log.info("%s: %s boat %sT, 200 badges -> kept in case no chest "
                             "boat turns up", self.name, boat.kind, panel.power)
                reserve = boat
            else:
                ctx.log.info("%s: %s boat %sT, 200 badges -> another badge boat (one "
                             "is already kept)", self.name, boat.kind, panel.power)
        if reserve is None:
            return None
        if reserve is not last:  # later taps selected other boats: select it again
            panel = self._select(ctx, reserve)
            if panel is None or why_not(panel) is not None:
                ctx.log.info("%s: the 200-badges boat didn't check out again", self.name)
                return None
        ctx.log.info("%s: no chest boat; plunder the %s boat with 200 badges", self.name,
                     reserve.kind)
        return reserve

    def _select(self, ctx: Context, boat: Boat) -> Panel | None:
        """Tap a boat and read its panel. None if the tap opened the owner's
        profile instead (closed again) or a stop came."""
        if not self.tap(ctx, boat.at, f"{boat.kind} boat"):
            return None
        if self.wait(ctx, SELECT_SETTLE - 1.0):  # tap already waited ~1s
            return None
        frame = ctx.frame()
        if "character info" in _words(frame, PROFILE_TITLE).lower():
            # the tap caught the owner's avatar after all: close it, move on
            ctx.log.info("%s: opened the owner's profile by mistake; closing it",
                         self.name)
        elif self._popup(ctx, frame) is not None:
            ctx.log.info("%s: a popup opened instead of the boat's panel; closing it",
                         self.name)
        else:
            return read_panel(frame)
        self._close_popups(ctx, frame)
        return None

    def _plunder(self, ctx: Context) -> str | None:
        """Plunder the selected boat: fight, Skip, OK, back on the sea. The result
        ("victory"/"defeat"/"unknown", or "no fight" if it didn't start), or None
        on a stop or a timeout (logged)."""
        if not self.tap(ctx, PLUNDER_BTN, "Plunder"):
            return None
        started = self._fight_or_gone(ctx)
        if started is None:
            return None
        if started == GONE:
            ctx.log.info("%s: that boat is gone (cleared from the sea) -> next boat",
                         self.name)
            return GONE
        if not started:
            if ctx.should_stop():
                return None
            ctx.log.info("%s: the fight didn't start; clearing the screen", self.name)
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

    def _fight_or_gone(self, ctx: Context) -> bool | str | None:
        """After Plunder: True once the fight screen is up (then settled); GONE if
        the sea stays on screen for GONE_AFTER seconds without ever going to the
        loading screen (user: a boat that doesn't exist any more just clears when
        plundered, and the game then refreshes the boats itself); False if no fight
        by FIGHT_TIMEOUT; None on a stop."""
        start = time.time()
        left_sea = False
        while time.time() - start < FIGHT_TIMEOUT:
            frame = ctx.frame()
            if fight_up(frame):
                return not self.wait(ctx, FIGHT_SETTLE) or None
            if not on_plunder(frame):
                left_sea = True  # the black loading screen: a fight is coming
            elif not left_sea and time.time() - start >= GONE_AFTER:
                return GONE
            if self.wait(ctx, POLL):
                return None
        return False

    def _wait_for(self, ctx: Context, what: str | None, check, timeout: float,
                  settle: float = SETTLE) -> bool:
        """Poll until check(frame) holds, then let the screen settle. A popup in the
        way is closed first (the screens read as themselves under one), and each
        closed popup gives the screen another `timeout`. False on a timeout
        (logged, if `what` names the screen) or a stop."""
        end = time.time() + timeout
        popups = 0
        while True:
            frame = ctx.frame()
            popup = self._popup(ctx, frame) if popups < MAX_POPUPS else None
            if popup is not None:
                popups += 1
                what_popup, target = popup
                if not self.tap(ctx, target, f"close {what_popup}"):
                    return False
                end = max(end, time.time() + timeout)
                continue
            if check(frame):
                return not self.wait(ctx, settle)
            if time.time() >= end:
                if what:
                    ctx.log.warning("%s: %s didn't show within %.0fs", self.name, what,
                                    timeout)
                return False
            if self.wait(ctx, POLL):
                return False

    def _popup(self, ctx: Context, frame) -> tuple[str, Rel] | None:
        """A popup covering the screen, as (what, where to tap to close it): a
        reward's "Tap to close" (a tap above its band) or a panel's round X.
        None if the screen is clear."""
        if tap_to_close_up(frame):
            return "the reward popup", NEUTRAL
        x = find_sprite(ctx, frame, "close_x.png")
        if x is not None:
            return "the popup (X)", x
        return None

    def _close_popups(self, ctx: Context, frame=None) -> bool:
        """Close popups until the screen is clear (e.g. Rewards over a Bountiful
        Return letter: two in a row). False on a stop, or if MAX_POPUPS in a row
        didn't clear it (logged)."""
        for _ in range(MAX_POPUPS):
            popup = self._popup(ctx, frame if frame is not None else ctx.frame())
            if popup is None:
                return True
            what, target = popup
            if not self.tap(ctx, target, f"close {what}"):
                return False
            frame = None
        if self._popup(ctx, ctx.frame()) is None:
            return True
        ctx.log.warning("%s: %d popups in a row and still one up", self.name, MAX_POPUPS)
        return False
