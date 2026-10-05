"""Daily: capymon (user, 2026-10-04).

From home: the helmet (2nd bottom-bar button, "Equip") -> Capymon (rightmost of the
middle bar) -> the Capymon screen. Then:

  Card Table tab (leftmost bottom tab):
    1. The "Capymon gift pack" button (right side) -> "Gift Pack": claim the free
       welfare package (AD button; instant with the ad privilege) and buy the Gem
       Work Gift Pack (500 purple cubes; buys on the first tap, NO confirm, so
       it's tapped only while its row says "Limit: 1/1"). Never the Top-up banner
       or the gem-priced packs. Close (X).
    2. "Draw 10 times" until you can't (user: "includes spending gems"): tickets
       first, then purple cubes (3000 per 10-draw, 20 cube draws a day: "Remaining
       Diamond Draws"). Each draw: Skip (top right), then close the 10 results.
       When none are left the button opens an "Item Acquisition" panel instead:
       close it and stop.
    3. The points bar's milestone chests that show a red "!": tap each, close
       the reward.
  Capymon tab -> "Capy Grand Voyage" -> the sea map -> Travel -> "Travel Team":
    4. A finished travel ("Travel completed") -> Island Travel -> Claim -> close
       the reward.
    5. The empty slot ("+ Send Capymon...") -> the setup: 24 hours preset, minus
       once (= 20 hours, checked), Quick (fills the team), Dispatch (energy).
       Close (X).
  The voyage map's "adventure" button (bottom-left) goes straight home.

Reward popups are closed by tapping a title ABOVE their dark band (taps on the
band are ignored): the screen/panel title of wherever the popup came from.
"""

from __future__ import annotations

import re
import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import DailyTask, _crop, find_sprite, go_home, tap_to_close_up

EQUIP_BTN = Rel(0.304, 0.943)                    # helmet, 2nd in the bottom bar
CAPYMON_BTN = Rel(0.813, 0.512)                  # rightmost of Equip's middle bar
TITLE = RelRect(0.10, 0.030, 0.40, 0.045)        # "Capymon" / "Card Table" (top-left)
TABS = {"card table": Rel(0.369, 0.952), "capymon": Rel(0.527, 0.952)}
TITLE_TAP = Rel(0.25, 0.055)                     # the screen title: closes rewards

# Card Table
GIFT_BTN = Rel(0.828, 0.385)                     # "Capymon gift pack" (right side)
GIFT_TITLE_TAP = Rel(0.5, 0.179)                 # "Gift Pack" title (above the band)
GIFT_HEADER = RelRect(0.25, 0.155, 0.50, 0.05)   # "Gift Pack"
GIFT_LIST = (95, 545, 335, 790)                  # the pack rows, px x0, x1, y0, y1
# Packs are found by their row TITLE: sold-out packs move to the bottom when the
# popup reopens, so the top rows can be the gem-priced packs. A pack's button sits
# 65px below its title, at x 463; its limit text is in the row (title-10..+110).
GIFT_PACKS = [("free welfare package", "ad"), ("gem work gift pack", "500")]
GIFT_BTN_X, GIFT_BTN_DY = 463, 65
LIMIT_CELL = (380, 530, 14, 44)    # "Limit: 1/1", x0, x1, then y relative to the title
LABEL_CELL = (400, 530, 30, 90)    # the button's label ("AD" / "500"), same
DRAW10_BTN = Rel(0.685, 0.810)
DRAW10_LABEL = RelRect(0.545, 0.778, 0.30, 0.065)  # "15/10" (tickets) or "117.4K/3000"
DRAW_SKIP = Rel(0.843, 0.059)
SKIP_LABEL = RelRect(0.75, 0.037, 0.19, 0.047)
DIAMOND_DRAWS = RelRect(0.23, 0.857, 0.55, 0.032)  # "Remaining Diamond Draws: N"
ACQ_TITLE = RelRect(0.25, 0.17, 0.50, 0.05)      # "Item Acquisition" = no draws left
MAX_DRAWS = 6                                    # 15 tickets + 2 cube draws = 3 today
CHEST_X = [226, 296, 365, 435, 504]              # points-bar chests 20..100, px
CHEST_Y = 168
# Capymon / Grand Voyage
VOYAGE_BTN = Rel(0.822, 0.832)                   # "Capy Grand Voyage"
TRAVEL_BTN = Rel(0.836, 0.493)                   # right column of the sea map
TRAVEL_PANEL = RelRect(0.25, 0.155, 0.50, 0.05)  # "Travel Team"
TRAVEL_TITLE_TAP = Rel(0.5, 0.180)
SLOT1 = Rel(0.5, 0.442)                          # the first team slot
SLOT1_TEXT = RelRect(0.15, 0.395, 0.70, 0.10)    # "Travel completed" / "Send Capymon"
ISLAND_TITLE = RelRect(0.25, 0.090, 0.50, 0.050)  # "Island Travel" (setup)
CLAIM_TRAVEL = Rel(0.5, 0.713)                   # Island Travel (finished): Claim
H24_BTN = Rel(0.725, 0.763)
MINUS_BTN = Rel(0.360, 0.766)
HOURS = RelRect(0.39, 0.747, 0.22, 0.042)        # "20hours"
QUICK_BTN = Rel(0.349, 0.858)
DISPATCH_BTN = Rel(0.636, 0.860)
ADVENTURE_BTN = Rel(0.173, 0.927)                # sea map bottom-left: home
TRAVEL_HOURS = 20

POLL = 0.3
SETTLE = 1.0
OPEN_TIMEOUT = 6.0
REWARD_TIMEOUT = 4.0


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def chest_badges(frame) -> list[Rel]:
    """Points-bar chests with a red "!" just above their top-right corner
    (badge 0.18-0.19 red, none 0.00; the locked chests' red locks sit lower)."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    out = []
    for cx in CHEST_X:
        box = frame[int(134 * ky):int(153 * ky), int((cx + 10) * kx):int((cx + 33) * kx)]
        b, g, r = (box[..., i].astype(int) for i in range(3))
        if float(((r > 170) & (g < 120) & (b < 130)).mean()) >= 0.10:
            out.append(Rel(cx / 642, CHEST_Y / 951))
    return out


@register("capymon")
class Capymon(DailyTask):
    TITLE = "Capymon"
    LABEL = "Capymon"
    ICON = "🃏"
    DESCRIPTION = ("Equip -> Capymon: Card Table gift packs (free + 500 cubes), 10-draws "
                   "until none are left (cubes too), points chests; Grand Voyage travel: "
                   "collect, then send for 20 hours. Then home.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.tap(ctx, EQUIP_BTN, "Equip (helmet)"):
            return False
        if not self.tap(ctx, CAPYMON_BTN, "Capymon"):
            return False
        if ctx.dry_run:
            return go_home(ctx)
        if not self._wait(ctx, lambda: "capymon" in _words(ctx.frame(), TITLE)):
            ctx.log.warning("%s: the Capymon screen did not open", self.name)
            return False

        if not self.tap(ctx, TABS["card table"], "Card Table tab"):
            return False
        if not self._wait(ctx, lambda: "card table" in _words(ctx.frame(), TITLE)):
            ctx.log.warning("%s: the Card Table did not open", self.name)
            return False
        if not (self._gift_packs(ctx) and self._draws(ctx) and self._chests(ctx)):
            return False

        if not self.tap(ctx, TABS["capymon"], "Capymon tab"):
            return False
        if self.wait(ctx, SETTLE) or not self._travel(ctx):
            return False
        if not self.tap(ctx, ADVENTURE_BTN, "adventure (home)"):
            return False
        return go_home(ctx)

    # --- Card Table -------------------------------------------------------
    def _gift_packs(self, ctx: Context) -> bool:
        if not self.tap(ctx, GIFT_BTN, "Capymon gift pack"):
            return False
        if not self._wait(ctx, lambda: "gift pack" in _words(ctx.frame(), GIFT_HEADER)):
            ctx.log.warning("%s: the Gift Pack didn't open", self.name)
            return False
        if self.wait(ctx, SETTLE):
            return False
        for title, button in GIFT_PACKS:
            btn = self._pack_button(ctx, title, button)
            if btn is None:
                continue
            if not self.tap(ctx, btn, title):
                return False
            if self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
                if not self._close_reward(ctx, GIFT_TITLE_TAP):
                    return False
            else:
                ctx.log.warning("%s: no reward from %s", self.name, title)
        return self._close_x(ctx)

    def _pack_button(self, ctx: Context, title: str, button: str) -> Rel | None:
        """The button of the pack whose row TITLE reads `title`, if it's still
        available today ("1/1" in its row, its button reading `button`); else None
        (logged). Never a position guess: the rows reorder."""
        frame = ctx.frame()
        h, w = frame.shape[:2]
        kx, ky = w / 642, h / 951
        x0, x1, y0, y1 = GIFT_LIST
        crop = frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]
        ty = next((cy / ky + y0 for t, _, cy in ocr_lines(crop)
                   if title in t.lower()), None)
        if ty is None:
            ctx.log.info("%s: %s not in the list (sold out today)", self.name, title)
            return None
        def cell(c):
            cx0, cx1, dy0, dy1 = c
            part = frame[int((ty + dy0) * ky):int((ty + dy1) * ky), int(cx0 * kx):int(cx1 * kx)]
            return " ".join(t for t, _, _ in ocr_lines(part)).lower()
        limit, label = cell(LIMIT_CELL), cell(LABEL_CELL)
        if not re.search(r"1\s*/\s*1", limit) or "sold" in label:
            ctx.log.info("%s: %s already taken today (%r)", self.name, title, limit)
            return None
        if button not in label:
            ctx.log.warning("%s: %s button reads %r, not %r -> skip", self.name, title,
                            label, button)
            return None
        return Rel(GIFT_BTN_X / 642, (ty + GIFT_BTN_DY) / 951)

    def _draws(self, ctx: Context) -> bool:
        """10-draws until the game won't (tickets, then the day's cube draws)."""
        done = 0
        while done < MAX_DRAWS:
            frame = ctx.frame()
            label = _words(frame, DRAW10_LABEL)
            m = re.search(r"draws:?\s*(\d+)", _words(frame, DIAMOND_DRAWS))
            diamonds = int(m.group(1)) if m else 0
            t = re.search(r"(\d+)\s*/\s*10\b", label)
            tickets = int(t.group(1)) if t else 0
            if tickets < 10 and diamonds < 10:
                break
            if not self.tap(ctx, DRAW10_BTN, f"Draw 10 times ({label.split(' draw')[0]})"):
                return False
            if not self._wait(ctx, lambda: "skip" in _words(ctx.frame(), SKIP_LABEL)
                              or "acquisition" in _words(ctx.frame(), ACQ_TITLE)):
                ctx.log.warning("%s: the draw didn't start", self.name)
                return False
            if "acquisition" in _words(ctx.frame(), ACQ_TITLE):
                ctx.log.info("%s: no draws left (Item Acquisition)", self.name)
                return self._close_x(ctx)
            if not self.tap(ctx, DRAW_SKIP, "Skip"):
                return False
            if self.wait(ctx, 0.5) or not self.tap(ctx, TITLE_TAP, "close the results"):
                return False
            if not self._wait(ctx, lambda: "draw 10" in _words(ctx.frame(), DRAW10_LABEL)):
                ctx.log.warning("%s: the results didn't close", self.name)
                return False
            done += 1
        ctx.log.info("%s: %d ten-draw(s)", self.name, done)
        return True

    def _chests(self, ctx: Context) -> bool:
        for _ in range(len(CHEST_X)):
            badges = chest_badges(ctx.frame())
            if not badges:
                return True
            if not self.tap(ctx, badges[0], "points chest"):
                return False
            if self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
                if not self._close_reward(ctx, TITLE_TAP):
                    return False
        return True

    # --- Grand Voyage -----------------------------------------------------
    def _travel(self, ctx: Context) -> bool:
        if not self.tap(ctx, VOYAGE_BTN, "Capy Grand Voyage"):
            return False
        if self.wait(ctx, SETTLE) or not self.tap(ctx, TRAVEL_BTN, "Travel"):
            return False
        if not self._wait(ctx, lambda: "travel team" in _words(ctx.frame(), TRAVEL_PANEL)):
            ctx.log.warning("%s: the Travel Team panel didn't open", self.name)
            return False
        if "completed" in _words(ctx.frame(), SLOT1_TEXT):
            if not self.tap(ctx, SLOT1, "Travel completed"):
                return False
            if not self.tap(ctx, CLAIM_TRAVEL, "Claim (travel rewards)"):
                return False
            if self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
                if not self._close_reward(ctx, TRAVEL_TITLE_TAP):
                    return False
        if "send" in _words(ctx.frame(), SLOT1_TEXT):
            if not self._dispatch(ctx):
                return False
        else:
            ctx.log.info("%s: the team is still travelling", self.name)
        return self._close_x(ctx)

    def _dispatch(self, ctx: Context) -> bool:
        if not self.tap(ctx, SLOT1, "Send Capymon"):
            return False
        if not self._wait(ctx, lambda: "island travel" in _words(ctx.frame(), ISLAND_TITLE)):
            ctx.log.warning("%s: the travel setup didn't open", self.name)
            return False
        if not (self.tap(ctx, H24_BTN, "24 hours") and self.tap(ctx, MINUS_BTN, "minus")):
            return False
        hours = _words(ctx.frame(), HOURS)
        if f"{TRAVEL_HOURS}hour" not in hours.replace(" ", ""):
            self.flag(ctx, f"the travel time read {hours!r}, not {TRAVEL_HOURS} hours; "
                           "didn't dispatch. Send the team by hand.")
            return self._close_x(ctx)
        if not self.tap(ctx, QUICK_BTN, "Quick (fill the team)"):
            return False
        if not self.tap(ctx, DISPATCH_BTN, f"Dispatch ({TRAVEL_HOURS}h)"):
            return False
        return self._wait(ctx, lambda: "travel team" in _words(ctx.frame(), TRAVEL_PANEL))

    # --- helpers ----------------------------------------------------------
    def _close_reward(self, ctx: Context, at: Rel) -> bool:
        if not self.tap(ctx, at, "close the reward"):
            return False
        return self._wait(ctx, lambda: not tap_to_close_up(ctx.frame()), REWARD_TIMEOUT)

    def _close_x(self, ctx: Context) -> bool:
        x = find_sprite(ctx, ctx.frame(), "close_x.png")
        if x is None:
            ctx.log.warning("%s: no X to close", self.name)
            return False
        return self.tap(ctx, x, "close (X)")

    def _wait(self, ctx: Context, check, timeout: float = OPEN_TIMEOUT) -> bool:
        end = time.time() + timeout
        while True:
            if check():
                return True
            if time.time() >= end or self.wait(ctx, POLL):
                return False
