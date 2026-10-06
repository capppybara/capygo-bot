"""Menu chore: black-market (buy the good deals, claim the free gold).

Starts with the menu drawer open: Black Market (4th) -> a shop of cards in 3
columns under a fixed banner; the list scrolls. Each card: title, an optional red
"NN% Value" tag at its top-right, an icon (tapping it only opens an info tooltip),
"Purchase limit: 1/1", and a price button (purple cubes). Tapping the price opens
"Tips: Confirm Purchase?" (Cancel / OK); OK buys it and raises a "Rewards / Tap to
close" popup. A bought card shows "Purchase limit: 0/1" and a green tick instead
of the price. At the very bottom, a "Gold" section: "Some Gold" (left) says Free
and claims at once (user).

User (2026-10-04): buy these, only when their value tag is 40% or higher:
Silver Chest, Gold Chest, Pet Chest, Gold Key, Pet Egg, Gold Horseshoe (list
positions 3, 4, 5, 7, 8, 11; always in the same order); and claim the free gold.

Cards are found by their title (OCR), so the scroll distance doesn't matter. The
tag is read on its own crop, enlarged (a read of the whole list once took 30% for
80%), and a buy needs two separate reads to agree on >= 40%. The list scrolls by
a drag started in the gap between the 1st and 2nd columns: a drag that starts on
a card can count as a tap on it (that opened a purchase dialog once).
"""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import tap_to_close_up
from .menu import MenuTask, go_menu

WANTED = ["silver chest", "gold chest", "pet chest", "gold key", "pet egg",
          "gold horseshoe"]        # list positions 3, 4, 5, 7, 8, 11
MIN_VALUE = 40                     # user: buy only at a 40%+ value tag
FREE_TITLE = "some gold"           # the Gold section's left card, "Free"
# User (2026-10-05): some days the Gold Key isn't in the shop (a Silver Key sits
# in its place) - that's fine, no flag. The Silver Key is never bought; it's
# listed so a misread can't make it match "Silver Chest" (0.7 similar).
SOMETIMES_MISSING = {"gold key"}
NEVER = ["silver key"]
TITLE_MATCH = 0.8                  # how close an OCR'd title must be to a name

HEADER = RelRect(0.30, 0.255, 0.40, 0.04)   # "Black Market" bar under the banner
LIST_TOP, LIST_BOTTOM = 300, 855           # the scrolling list, in px at 951 high
GAP_X = 240 / 642                          # between the 1st and 2nd columns
# One scroll step ~ one row (238px). A whole card fits on screen while its title
# is between y 300 and 663, a 363px window, so with one-row steps every card is
# whole at least once even if a drag scrolls a bit further than asked. (1.4-row
# steps skipped the Gold Horseshoe: whole on no page.)
DRAG_FROM, DRAG_TO = 0.78, 0.53
INERT = Rel(0.5, 0.15)                     # the banner art: closes tooltips/rewards
# A card, relative to its title's centre (tx, ty), in px at 642x951:
TAG_BOX = (19, 99, 8, 53)                  # x0, x1, y0, y1 of the "NN% Value" tag
PRICE_DY = 176                             # the price button
PRICE_BOX = (-75, 75, 160, 192)
FREE_DY = 28                               # "Some Gold" title -> its "Free" label

OPEN_TIMEOUT = 5.0
DIALOG_TIMEOUT = 3.0
REWARD_TIMEOUT = 4.0
MAX_SCROLLS = 12
POLL = 0.3
SETTLE = 1.0


def _norm(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _crop_px(frame, x0, x1, y0, y1, scale: int = 1):
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    crop = frame[max(0, int(y0 * ky)):int(y1 * ky), max(0, int(x0 * kx)):int(x1 * kx)]
    if scale > 1 and crop.size:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return crop


def _text(crop) -> str:
    return " ".join(t for t, _, _ in ocr_lines(crop)) if crop.size else ""


def titles(frame) -> dict[str, tuple[int, int]]:
    """Card titles on screen -> their centre (px at 642x951), for the wanted cards
    and the free gold. Matched loosely: OCR read "Pet Egg" as "Pet E9gm" (0.83
    similar), while the closest two wanted titles (Silver/Gold Chest) are 0.6."""
    h, w = frame.shape[:2]
    y0 = int(LIST_TOP * h / 951)
    out = {}
    for text, cx, cy in ocr_lines(frame[y0:int(LIST_BOTTOM * h / 951)]):
        key = _norm(text)
        name = max(WANTED + [FREE_TITLE] + NEVER,
                   key=lambda n: SequenceMatcher(None, key, _norm(n)).ratio())
        if name in NEVER:
            continue  # closest to an item we never buy
        if SequenceMatcher(None, key, _norm(name)).ratio() >= TITLE_MATCH:
            out[name] = (round(cx * 642 / w), round((cy + y0) * 951 / h))
    return out


def value_tag(frame, tx: int, ty: int) -> int | None:
    x0, x1, y0, y1 = TAG_BOX
    m = re.search(r"(\d+)\s*%", _text(_crop_px(frame, tx + x0, tx + x1, ty + y0, ty + y1, 3)))
    return int(m.group(1)) if m else None


def priced(frame, tx: int, ty: int) -> bool:
    """The card still shows a price (not bought yet; a bought card shows a tick)."""
    x0, x1, y0, y1 = PRICE_BOX
    return bool(re.search(r"\d", _text(_crop_px(frame, tx + x0, tx + x1, ty + y0, ty + y1))))


@register("black-market")
class BlackMarket(MenuTask):
    TITLE = "Black Market"
    LABEL = "Black Market deals"
    ICON = "🛒"
    DESCRIPTION = ("Menu -> Black Market: buy Silver/Gold/Pet Chest, Gold Key, Pet Egg "
                   "and Gold Horseshoe when their value tag is 40%+, and claim the free "
                   "gold, then go back.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_item(ctx, "black market"):
            return False
        if ctx.dry_run:
            return go_menu(ctx)
        if not self._wait(ctx, lambda: "black market" in self.text_in(ctx, HEADER),
                          OPEN_TIMEOUT):
            ctx.log.warning("%s: the Black Market did not open", self.name)
            return False

        handled: set[str] = set()
        bought: list[str] = []
        for _ in range(MAX_SCROLLS + 1):
            frame = ctx.frame()
            for name, (tx, ty) in titles(frame).items():
                if name in handled:
                    continue
                if name == FREE_TITLE:
                    if ty + FREE_DY + 15 > LIST_BOTTOM:
                        continue  # its Free label is below the fold: next page
                    handled.add(name)
                    if not self._claim_free(ctx, tx, ty):
                        return False
                    continue
                if ty < LIST_TOP or ty + PRICE_BOX[3] > LIST_BOTTOM:
                    continue  # not the whole card on screen: next page
                handled.add(name)
                result = self._consider(ctx, name, tx, ty)
                if result is None:
                    return False
                if result:
                    bought.append(name)
            if FREE_TITLE in handled:
                break  # the free gold is the last card
            if not self._scroll(ctx):
                break  # the bottom
        absent_ok = [n for n in SOMETIMES_MISSING if n not in handled]
        if absent_ok:
            ctx.log.info("%s: %s not in the shop today", self.name, ", ".join(absent_ok))
        missing = [n for n in WANTED + [FREE_TITLE]
                   if n not in handled and n not in SOMETIMES_MISSING]
        if missing:
            self.flag(ctx, f"didn't find {', '.join(missing)} in the Black Market. "
                           "Check those by hand.")
        ctx.log.info("%s: bought %s", self.name, ", ".join(bought) if bought else "nothing")
        return go_menu(ctx)

    # --- steps ------------------------------------------------------------
    def _consider(self, ctx: Context, name: str, tx: int, ty: int) -> bool | None:
        """Buy one wanted card if it's still for sale with a 40%+ tag. True if
        bought, False if skipped, None if something went wrong (logged)."""
        frame = ctx.frame()
        if not priced(frame, tx, ty):
            ctx.log.info("%s: %s already bought", self.name, name)
            return False
        first = value_tag(frame, tx, ty)
        if self.wait(ctx, POLL):
            return None
        second = value_tag(ctx.frame(), tx, ty)
        if first is None or first != second:
            ctx.log.info("%s: %s value tag unclear (%s / %s) -> skip", self.name, name,
                         first, second)
            return False
        if first < MIN_VALUE:
            ctx.log.info("%s: %s at %d%% value -> skip", self.name, name, first)
            return False
        ctx.log.info("%s: %s at %d%% value -> buy", self.name, name, first)
        return self._buy(ctx, name, tx, ty)

    def _buy(self, ctx: Context, name: str, tx: int, ty: int) -> bool | None:
        price = Rel(tx / 642, (ty + PRICE_DY) / 951)
        for attempt in (1, 2):
            if not self.tap(ctx, price, f"{name} price"):
                return None
            ok = self._wait_ok(ctx)
            if ok is not None:
                break
            if ctx.should_stop():
                return None
            # no confirm dialog: maybe an info tooltip opened; close it and retry
            if not self.tap(ctx, INERT, "close the tooltip"):
                return None
        else:
            ctx.log.warning("%s: no purchase dialog for %s", self.name, name)
            return False
        if not self.tap(ctx, ok, "OK (confirm purchase)"):
            return None
        if not self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
            ctx.log.warning("%s: no reward after buying %s", self.name, name)
            return None
        if not self._dismiss(ctx):
            return None
        return True

    def _claim_free(self, ctx: Context, tx: int, ty: int) -> bool:
        frame = ctx.frame()
        label = _text(_crop_px(frame, tx - 70, tx + 70, ty + FREE_DY - 15, ty + FREE_DY + 15))
        if "free" not in label.lower():
            ctx.log.info("%s: the free gold is already claimed (%r)", self.name, label)
            return True
        if not self.tap(ctx, Rel(tx / 642, (ty + FREE_DY) / 951), "Free gold"):
            return False
        if self._wait(ctx, lambda: tap_to_close_up(ctx.frame()), REWARD_TIMEOUT):
            return self._dismiss(ctx)
        ctx.log.info("%s: no reward popup after the free gold", self.name)
        return not ctx.should_stop()

    def _wait_ok(self, ctx: Context) -> Rel | None:
        """The "Confirm Purchase?" dialog's OK button, if the dialog shows."""
        end = time.time() + DIALOG_TIMEOUT
        while time.time() < end:
            frame = ctx.frame()
            h, w = frame.shape[:2]
            lines = ocr_lines(frame)
            if any("confirm purchase" in t.lower() for t, _, _ in lines):
                for t, cx, cy in lines:
                    if t.strip().upper() == "OK":
                        return Rel(cx / w, cy / h)
            if self.wait(ctx, POLL):
                return None
        return None

    def _dismiss(self, ctx: Context) -> bool:
        """Close a Rewards popup: tap the banner art above its dark band (taps on
        the band are ignored), then wait for it to go."""
        if not self.tap(ctx, INERT, "dismiss the reward"):
            return False
        return self._wait(ctx, lambda: not tap_to_close_up(ctx.frame()), REWARD_TIMEOUT)

    def _scroll(self, ctx: Context) -> bool:
        """One scroll step down. False at the bottom (nothing moved)."""
        h = ctx.frame().shape[0]
        y0, y1 = int(LIST_TOP * h / 951), int(LIST_BOTTOM * h / 951)
        before = ctx.frame()[y0:y1]
        ctx.drag_rel(Rel(GAP_X, DRAG_FROM), Rel(GAP_X, DRAG_TO), steps=30, duration=0.8)
        if self.wait(ctx, SETTLE):
            return False
        after = ctx.frame()[y0:y1]
        return float(np.abs(after.astype(int) - before.astype(int)).mean()) >= 1.0

    def _wait(self, ctx: Context, check, timeout: float) -> bool:
        end = time.time() + timeout
        while True:
            if check():
                return True
            if time.time() >= end or self.wait(ctx, POLL):
                return False
