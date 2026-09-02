"""Task: get-guild-member-list.

Walks every member on a Guild Info screen and exports each member's UID and
power to a CSV.

Per member:
  1. Click the member's profile picture -> the Character Info screen opens.
  2. Read the UID by clicking the in-game copy-to-clipboard button next to it and
     reading the clipboard (exact, not OCR).
  3. Read the power (the value right below the center character display) by OCR.
  4. Close the Character Info screen (back to the guild list, same scroll spot).

The member list is the scrollable bottom half of the panel; the header (guild
name, member count) stays fixed while it scrolls. Members are processed a page at
a time: every fully-visible card is read, then the list is dragged up ~2 cards
and the next page is read. Cards are located by OCR of the right-side power pill,
which sits at each card's vertical center (the profile-picture height). Members
are de-duplicated by UID, so the overlap between pages costs a little time but
never skips anyone. It stops when the list can't scroll further (bottom reached)
or every member (from the "N/M" count) has been seen.

Output: ~/Downloads/capygo_<guild>_member_list.csv with columns
(guild_name, member_uid, power). The file is written on exit even if stopped
early, so an Esc still saves what was collected.

Templates in templates/get-guild-member-list/ (captured from the live game):
  guild_title    the "Guild Info" banner (confirms we start on the right screen)
  char_title     the "Character Info" banner (confirms a member screen opened)
"""

from __future__ import annotations

import csv
import os
import re
import time

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Param, Task, register

# --- header (fixed while the member list scrolls) -------------------------
GUILD_NAME_REGION = RelRect(0.52, 0.181, 0.34, 0.035)   # value cell -> guild name
MEMBER_COUNT_REGION = RelRect(0.555, 0.328, 0.11, 0.028)  # "47/48"

# --- member list layout (642x951) -----------------------------------------
PROFILE_X = 0.223         # xrel of every card's profile picture
# Cards are located by their coin value (the gold number under the name): it is
# present and numeric on every card, unlike the right-side pill, which reads "0"
# for low-activity members and then isn't recognized as text at all.
COIN_X = (0.33, 0.46)     # xrel band of the coin value
COIN_TO_CENTER = 0.019    # the coin value sits ~18px below the card's vertical center
FULL_TOP = 0.575          # a card is fully visible (safe to open) when its center
FULL_BOTTOM = 0.825       #   y is within [FULL_TOP, FULL_BOTTOM]
LIST_REGION = RelRect(0.10, 0.560, 0.80, 0.300)  # for bottom-of-list detection

# Drag up to advance ~2 cards, i.e. less than the ~3 read per page, so pages
# overlap by ~1 card and nothing is skipped (UID de-dup drops the repeats).
# Content scrolls a bit further than the finger travels (momentum), so ~0.13 of
# the window advances roughly two 80px cards.
SCROLL_FROM = Rel(0.5, 0.72)
SCROLL_TO = Rel(0.5, 0.588)
SCROLL_TO_FIRM = Rel(0.5, 0.50)  # a firmer retry if a drag doesn't take

# --- character screen ------------------------------------------------------
UID_COPY_BTN = Rel(0.815, 0.220)          # copy-to-clipboard button next to the UID
POWER_REGION = RelRect(0.397, 0.576, 0.203, 0.037)  # value below the character
CLOSE_BTN = Rel(0.5, 0.925)               # floating X: closes the top popup

CLIP_SENTINEL = "capygo-none"  # seeded before a copy so a stale value can't fool us
MAX_PAGES = 80                 # safety cap (a full guild is ~48 members)


@register("get-guild-member-list")
class GetGuildMemberList(Task):
    TITLE = "Get Guild Member List"
    ICON = "📋"
    DESCRIPTION = ("Scroll a guild's member list and export each member's UID and "
                   "power to a CSV in ~/Downloads.")
    START_HINT = ("Open the guild's Info screen (the one titled \"Guild Info\" with "
                  "the member list) before starting.")

    PARAMS = [
        Param("guild_name", "str", "", "Guild name (optional)",
              help="used for the CSV name/column; leave blank to read it from the "
                   "screen"),
    ]

    # --- small helpers ----------------------------------------------------
    def _present(self, ctx: Context, name: str, frame=None) -> bool:
        return ctx.has_template(name) and ctx.find(name, frame=frame).found

    def _sleep(self, ctx: Context, seconds: float) -> bool:
        """Sleep in short slices so a stop is noticed within ~0.3s. Returns True if
        a stop was requested during the wait."""
        end = time.time() + seconds
        while True:
            if ctx.should_stop():
                return True
            remaining = end - time.time()
            if remaining <= 0:
                return False
            time.sleep(min(0.3, remaining))

    def _wait_template(self, ctx: Context, name: str, timeout: float) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if ctx.should_stop():
                return False
            if self._present(ctx, name):
                return True
            time.sleep(0.25)
        return self._present(ctx, name)

    def _ocr_otsu(self, frame, region: RelRect):
        """OCR a region after 4x upscale + Otsu threshold (reads the stylized game
        font far better than the raw crop)."""
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = region.to_pixels(w, h)
        crop = frame[y0:y1, x0:x1]
        up = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return ocr_lines(cv2.cvtColor(th, cv2.COLOR_GRAY2BGR))

    # --- header reads -----------------------------------------------------
    def _read_guild_name(self, ctx: Context) -> str:
        override = self.params.get("guild_name", "").strip()
        if override:
            return override
        lines = self._ocr_otsu(ctx.frame(), GUILD_NAME_REGION)
        name = " ".join(t for t, _, _ in lines).strip()
        return name or "guild"

    def _read_member_count(self, ctx: Context):
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = MEMBER_COUNT_REGION.to_pixels(w, h)
        for text, _cx, _cy in ocr_lines(frame[y0:y1, x0:x1]):
            m = re.search(r"(\d+)\s*/\s*(\d+)", text)
            if m:
                n, d = int(m.group(1)), int(m.group(2))
                if 0 < n <= d <= 200:
                    return n
        return None

    # --- one member -------------------------------------------------------
    def _read_power(self, ctx: Context):
        """OCR the power value under the character (e.g. '1.38T'); None if unread."""
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = POWER_REGION.to_pixels(w, h)
        for text, _cx, _cy in ocr_lines(frame[y0:y1, x0:x1]):
            m = re.search(r"\d[\d.,]*\s*[KMBTkmbt]?", text)
            if m:
                return m.group(0).replace(" ", "").upper()
        return None

    def _read_member(self, ctx: Context, y_rel: float):
        """Open the member whose profile picture is at (PROFILE_X, y_rel), read its
        UID + power, and close back to the list. Returns (uid, power), or None if
        the Character Info screen never opened (so the list wasn't disturbed and the
        close button must NOT be pressed)."""
        opened = False
        for attempt in range(2):  # the first click can only resurface the window
            ctx.click_rel(Rel(PROFILE_X, y_rel))
            if self._wait_template(ctx, "char_title", timeout=2.5):
                opened = True
                break
        if not opened:
            return None

        uid = None
        for _ in range(3):  # copy to clipboard and read it back
            ctx.set_clipboard(CLIP_SENTINEL)
            ctx.click_rel(UID_COPY_BTN)
            time.sleep(0.35)
            clip = ctx.read_clipboard().strip()
            if clip.isdigit():
                uid = clip
                break
            time.sleep(0.2)

        power = self._read_power(ctx)
        self._close_char(ctx)
        return uid, power

    def _close_char(self, ctx: Context) -> bool:
        for _ in range(3):
            ctx.click_rel(CLOSE_BTN)
            time.sleep(0.7)
            if not self._present(ctx, "char_title"):
                return True
        return not self._present(ctx, "char_title")

    # --- list scanning ----------------------------------------------------
    def _visible_cards(self, frame) -> list[tuple[float, str]]:
        """(center_yrel, coin_value) for every fully-visible card, top to bottom.
        Each card is located by its coin value (a number under the name); the card
        center is just above that. The coin value doubles as a cheap per-card label
        used to skip the page overlap without re-opening cards."""
        h, w = frame.shape[:2]
        items = []
        for text, cx, cy in ocr_lines(frame):
            xr = cx / w
            if not (COIN_X[0] <= xr <= COIN_X[1] and re.match(r"^\s*\d", text)):
                continue
            m = re.search(r"\d[\d.,]*\s*[KMBTkmbt]?", text)
            if not m:
                continue
            center = cy / h - COIN_TO_CENTER
            if FULL_TOP <= center <= FULL_BOTTOM:
                items.append((center, m.group(0).replace(" ", "").upper()))
        items.sort(key=lambda t: t[0])
        merged: list[tuple[float, str]] = []
        for c, coin in items:  # collapse an OCR split of one value into two lines
            if not merged or abs(c - merged[-1][0]) > 0.03:
                merged.append((c, coin))
        return merged

    @staticmethod
    def _overlap(prev_coins: list[str], coins: list[str]) -> int:
        """How many cards at the top of the current page were already read on the
        previous page: the longest leading run of `coins` that is a suffix of
        `prev_coins`. Matching a run of coin values (in order), not one value,
        makes a false skip essentially impossible; an OCR mismatch just shortens
        the run, so a card is re-opened (and de-duped) rather than skipped."""
        for k in range(min(len(coins), len(prev_coins)), 0, -1):
            if coins[:k] == prev_coins[-k:]:
                return k
        return 0

    def _list_unchanged(self, a, b) -> bool:
        h, w = a.shape[:2]
        x0, y0, x1, y1 = LIST_REGION.to_pixels(w, h)
        ra = a[y0:y1, x0:x1].astype(np.int16)
        rb = b[y0:y1, x0:x1].astype(np.int16)
        return float(np.mean(np.abs(ra - rb))) < 2.5

    def _scroll_to_top(self, ctx: Context) -> None:
        """Drag the list down until it stops moving, so a run always starts at the
        first member no matter where the list was left."""
        for _ in range(MAX_PAGES):
            if ctx.should_stop():
                return
            before = ctx.frame()
            ctx.drag_rel(Rel(0.5, 0.60), Rel(0.5, 0.82))
            if self._sleep(ctx, 0.8):
                return
            if self._list_unchanged(before, ctx.frame()):
                return

    def _scroll_down(self, ctx: Context) -> bool:
        """Drag the list up one step. Returns True if the list actually moved."""
        before = ctx.frame()
        ctx.drag_rel(SCROLL_FROM, SCROLL_TO)
        if self._sleep(ctx, 1.0):
            return False
        after = ctx.frame()
        if not self._list_unchanged(before, after):
            return True
        # A drag can occasionally not register; try once more, firmer.
        ctx.drag_rel(SCROLL_FROM, SCROLL_TO_FIRM)
        if self._sleep(ctx, 1.0):
            return False
        return not self._list_unchanged(before, ctx.frame())

    # --- CSV --------------------------------------------------------------
    def _write_csv(self, ctx: Context, guild: str, members: dict) -> str:
        safe = re.sub(r"[^\w\-]+", "_", guild).strip("_") or "guild"
        path = os.path.expanduser(f"~/Downloads/capygo_{safe}_member_list.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["guild_name", "member_uid", "power"])
            for uid, power in members.items():
                wr.writerow([guild, uid, power or ""])
        ctx.log.info("wrote %d members -> %s", len(members), path)
        return path

    # --- main loop --------------------------------------------------------
    def run(self, ctx: Context) -> None:
        if not self._present(ctx, "guild_title"):
            ctx.log.warning("not on the Guild Info screen -> open a guild's info first "
                            "and start again")
            return

        guild = self._read_guild_name(ctx)
        target = self._read_member_count(ctx)
        ctx.log.info("guild: %s (members: %s)", guild, target if target else "?")

        members: dict[str, str] = {}  # uid -> power, in discovery order
        try:
            self._scroll_to_top(ctx)  # always begin at the first member
            page = 0
            stale = 0
            prev_coins: list[str] = []  # coin values of the previous page's cards
            while not ctx.should_stop() and page < MAX_PAGES:
                page += 1
                cards = self._visible_cards(ctx.frame())
                coins = [coin for _, coin in cards]
                skip = self._overlap(prev_coins, coins)  # cards already read last page
                prev_coins = coins
                new_here = 0
                for center, _coin in cards[skip:]:
                    if ctx.should_stop():
                        break
                    res = self._read_member(ctx, center)
                    if res is None:
                        ctx.log.debug("a card did not open; skipping (page %d)", page)
                        continue
                    uid, power = res
                    if not uid:
                        ctx.log.info("read a member but could not copy its UID; skipping")
                        continue
                    if uid in members:
                        continue
                    members[uid] = power
                    new_here += 1
                    ctx.log.info("[%d%s] uid=%s power=%s",
                                 len(members), f"/{target}" if target else "",
                                 uid, power or "?")

                if ctx.should_stop():
                    break
                if target and len(members) >= target:
                    ctx.log.info("collected all %d members", target)
                    break
                stale = stale + 1 if new_here == 0 else 0
                if stale >= 2:
                    ctx.log.info("no new members over 2 pages -> stopping")
                    break
                if not self._scroll_down(ctx):
                    ctx.log.info("reached the bottom of the member list")
                    break
        finally:
            self._write_csv(ctx, guild, members)
            if target and len(members) < target:
                ctx.log.warning("collected %d of %d members - stopped before the end "
                                "(the list stopped scrolling, or a game popup "
                                "interrupted). The CSV has what was read so far.",
                                len(members), target)
            ctx.log.info("get-guild-member-list done: %d members", len(members))
