"""Task: get-guild-member-list.

Walks every member on a Guild Info screen and exports each member's UID and
power to a CSV.

Hedgemony comparison mode (-p hedgemony=true): the same walk as the full CSV mode -
open each member and de-dup by the exact UID - but instead of the per-member CSV it
sums the highest `top_n` powers (default 25), writes a short summary CSV (rank, uid,
power), and adds this guild's top-N to the shared comparison collection so several
guilds can be graphed together (see the compare-guild-power task, or the Generate
plot / Clear collection buttons in the app). Opening each member is what makes de-dup
reliable: reading powers/names straight off the cards fails because different members
share a power and a stylized/non-Latin name OCRs differently across pages, so only
the UID identifies a member exactly. If the run is interrupted (Esc / Stop / Ctrl+C),
the partial roster is discarded - nothing is written and the collection is untouched
- since a half-read roster would give a wrong top-N sum. (The full CSV mode, by
contrast, saves whatever it read so far on an early stop.)

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
(guild_name, member_uid, power). Power is stored as a plain number in trillions
(no unit letter): 1.38T -> 1.38, 905.85B -> 0.90585, 162.48M -> 0.00016248. The
file is written on exit even if stopped early, so an Esc still saves what was
collected.

Templates in templates/get-guild-member-list/ (captured from the live game):
  guild_title    the "Guild Info" banner (confirms we start on the right screen)
  char_title     the "Character Info" banner (confirms a member screen opened)
"""

from __future__ import annotations

import csv
import os
import re
import time
from decimal import Decimal, InvalidOperation

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Param, Task, register

# --- header (fixed while the member list scrolls) -------------------------
GUILD_NAME_REGION = RelRect(0.52, 0.181, 0.34, 0.035)   # value cell -> guild name
GUILD_ID_REGION = RelRect(0.52, 0.212, 0.34, 0.036)     # ID row, below the name
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

# Drag up ~1.5 cards, well under the ~3 read per page, so consecutive pages
# ALWAYS overlap by >=1 whole card. That guarantee is what keeps the overlap
# aligner correct: the top card of every new page is then a genuine repeat, so a
# coincidental coin-value match can never be mistaken for a new member and
# skipped (a bigger step once advanced ~3 cards and dropped a member on a list
# with many equal coin values). Content scrolls a bit further than the finger
# travels (momentum): ~0.066 of the window per 80px card.
SCROLL_FROM = Rel(0.5, 0.70)
SCROLL_TO = Rel(0.5, 0.60)

# --- character screen ------------------------------------------------------
UID_COPY_BTN = Rel(0.815, 0.220)          # copy-to-clipboard button next to the UID
POWER_REGION = RelRect(0.397, 0.576, 0.203, 0.037)  # value below the character
CLOSE_BTN = Rel(0.5, 0.925)               # floating X: closes the top popup

# Power is stored in trillions with no unit letter: T stays as-is, B/M/K (and a
# bare number) are scaled down to trillions. So 1.38T -> 1.38, 905.85B -> 0.90585,
# 162.48M -> 0.00016248.
POWER_UNIT_TO_TRILLION = {
    "T": Decimal(1),
    "B": Decimal("0.001"),
    "M": Decimal("0.000001"),
    "K": Decimal("0.000000001"),
    "": Decimal(10) ** -12,
}

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
        Param("hedgemony", "bool", False, "Hedgemony comparison",
              help="walk the roster (opening each member for the exact UID, like the "
                   "CSV mode) and add this guild's top N to the comparison collection "
                   "instead of writing the per-member CSV. Use Generate plot / Clear "
                   "collection below."),
        Param("top_n", "int", 25, "Top N to sum", min=1, max=200,
              help="in hedgemony comparison mode, how many of the highest powers to "
                   "collect and add up"),
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
    @staticmethod
    def _is_english(s: str) -> bool:
        """True if the name is plain English letters (ASCII, with a letter). A
        non-English name (Korean, etc.) OCRs to non-ASCII junk, which we'd rather
        replace with the numeric guild ID than put in a filename."""
        s = s.strip()
        return bool(s) and all(ord(c) < 128 for c in s) and any(c.isalpha() for c in s)

    def _read_guild_id(self, ctx: Context, frame=None):
        """The numeric guild ID from the row below the name (e.g. 96880), or None."""
        if frame is None:
            frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = GUILD_ID_REGION.to_pixels(w, h)
        from ..perception import read_int

        return read_int(frame[y0:y1, x0:x1])

    def _read_guild_name(self, ctx: Context) -> str:
        override = self.params.get("guild_name", "").strip()
        if override:
            return override
        frame = ctx.frame()
        lines = self._ocr_otsu(frame, GUILD_NAME_REGION)
        name = " ".join(t for t, _, _ in lines).strip()
        if self._is_english(name):
            return name
        # A non-English (or unreadable) name -> use the numeric guild ID instead.
        gid = self._read_guild_id(ctx, frame)
        if gid is not None:
            ctx.log.info("guild name %r is not English -> using guild ID %d", name, gid)
            return str(gid)
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
    @staticmethod
    def _to_trillions_decimal(raw: str):
        """Parse a power reading like '905.85B' into a Decimal in trillions
        (Decimal('0.90585')). None if it can't be parsed. Kept as a Decimal so
        hedgemony mode can add powers up without float rounding.

        Sanitizes a misread leading digit on a sub-T value: the game rolls K/M/B up
        to the next unit at 1000, so such a value always has a 1-3 digit integer
        part. A longer one means OCR fused the sword icon onto the number as a stray
        leading digit ("9864.97B" for "864.97B" -> 9.86T instead of 0.86T); the
        extra leading digits are dropped."""
        m = re.match(r"\s*([\d,]*\.?\d+)\s*([KMBTkmbt]?)", raw or "")
        if not m:
            return None
        numstr = m.group(1).replace(",", "")
        unit = m.group(2).upper()
        if unit in ("K", "M", "B"):
            intpart, _, frac = numstr.partition(".")
            while len(intpart) > 3:  # >999 is impossible for a sub-T unit
                intpart = intpart[1:]
            numstr = f"{intpart}.{frac}" if frac else intpart
        try:
            val = Decimal(numstr)
        except InvalidOperation:
            return None
        return val * POWER_UNIT_TO_TRILLION[unit]

    @staticmethod
    def _fmt_trillions(tri: Decimal) -> str:
        """A Decimal in trillions as a plain fixed-point string, no trailing
        zeros, never scientific notation ('0.90585', '1.19', '30.5')."""
        s = format(tri, "f")
        return s.rstrip("0").rstrip(".") if "." in s else s

    @classmethod
    def _to_trillions(cls, raw: str):
        """Convert a power reading like '905.85B' to a plain number in trillions
        ('0.90585'), dropping the unit letter. None if it can't be parsed."""
        tri = cls._to_trillions_decimal(raw)
        return None if tri is None else cls._fmt_trillions(tri)

    def _read_power(self, ctx: Context):
        """OCR the power under the character and return it in trillions as a plain
        number (e.g. '1.38T' -> '1.38', '905.85B' -> '0.90585'); None if unread."""
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = POWER_REGION.to_pixels(w, h)
        for text, _cx, _cy in ocr_lines(frame[y0:y1, x0:x1]):
            m = re.search(r"\d[\d.,]*\s*[KMBTkmbt]?", text)
            if m:
                return self._to_trillions(m.group(0))
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
        first member no matter where the list was left. Each down-drag is retried a
        few times before concluding the top is reached: a single drag occasionally
        stalls, and treating one stall as 'already at top' would leave the list
        wherever it was (e.g. at the bottom from a previous run)."""
        for _ in range(MAX_PAGES):
            if ctx.should_stop():
                return
            moved = False
            before = ctx.frame()
            for _try in range(3):
                ctx.drag_rel(Rel(0.5, 0.60), Rel(0.5, 0.82))
                if self._sleep(ctx, 0.8):
                    return
                if not self._list_unchanged(before, ctx.frame()):
                    moved = True
                    break
            if not moved:
                return  # genuinely at the top (didn't budge across retries)

    def _scroll_down(self, ctx: Context) -> bool:
        """Drag the list up one small step. Returns True if the list moved. Retries
        the SAME small drag if it didn't take (a drag occasionally doesn't register);
        it never uses a larger drag, which could overshoot the overlap. Three no-move
        attempts mean the list is at the bottom."""
        before = ctx.frame()
        for _ in range(3):
            ctx.drag_rel(SCROLL_FROM, SCROLL_TO)
            if self._sleep(ctx, 1.0):
                return False
            if not self._list_unchanged(before, ctx.frame()):
                return True
        return False

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

    # --- hedgemony comparison -----------------------------------------------
    def _write_power_summary(self, ctx: Context, guild: str,
                             top: list[tuple[str, Decimal]], total: Decimal) -> str:
        safe = re.sub(r"[^\w\-]+", "_", guild).strip("_") or "guild"
        path = os.path.expanduser(f"~/Downloads/capygo_{safe}_top{len(top)}_power.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["guild_name", "rank", "member_uid", "power_trillions"])
            for i, (uid, p) in enumerate(top, 1):
                wr.writerow([guild, i, uid, self._fmt_trillions(p)])
            wr.writerow([guild, f"TOP_{len(top)}_SUM", "", self._fmt_trillions(total)])
        ctx.log.info("wrote top-%d power summary -> %s", len(top), path)
        return path

    def _run_hedgemony(self, ctx: Context) -> None:
        """Same walk as the full CSV mode - open each member, de-dup by the exact UID
        (content-based keys fail: same-power members collide and a stylized/CJK name
        OCRs differently across pages). Then, instead of the per-member CSV, sum the
        top-N powers and add the guild to the comparison collection."""
        if not self._present(ctx, "guild_title"):
            ctx.log.warning("not on the Guild Info screen -> open a guild's info "
                            "first and start again")
            return
        guild = self._read_guild_name(ctx)
        target = self._read_member_count(ctx)
        top_n = self.params["top_n"]
        ctx.log.info("hedgemony comparison: guild %s (members: %s), summing top %d",
                     guild, target if target else "?", top_n)

        members: dict[str, str] = {}  # uid -> power (trillions), exact UID de-dup
        self._sweep(ctx, members, target, skip_overlap=True)
        if target and len(members) < target and not ctx.should_stop():
            ctx.log.info("re-checking for %d missed member(s) (full pass)",
                         target - len(members))
            self._sweep(ctx, members, target, skip_overlap=False)

        # Interrupted (Esc / Stop / Ctrl+C): throw the partial run away. A half-read
        # roster would give a wrong top-N sum and a misleading comparison, so nothing
        # is written and the collection is left untouched.
        if ctx.should_stop():
            ctx.log.info("interrupted -> discarding this run (%d members read, "
                         "nothing saved)", len(members))
            return

        powers: list[tuple[str, Decimal]] = []
        for uid, p in members.items():
            if not p:
                continue
            try:
                powers.append((uid, Decimal(p)))  # members already hold trillions
            except InvalidOperation:
                continue
        if not powers:
            ctx.log.warning("collected no member powers")
            return
        if target and len(powers) != target:
            ctx.log.warning("collected %d of %d members (stopped early, or a UID/power "
                            "couldn't be read)", len(powers), target)

        powers.sort(key=lambda t: t[1], reverse=True)
        n = min(top_n, len(powers))
        top = powers[:n]
        total = sum((d for _, d in top), Decimal(0))
        ctx.log.info("top %d: %s", n,
                     ", ".join(self._fmt_trillions(d) + "T" for _, d in top))
        ctx.log.info("=== TOP %d POWER SUM = %sT  (collected %d of %s members) ===",
                     n, self._fmt_trillions(total), len(powers),
                     target if target else "?")
        # We opened every member, so keep the full roster too (not just the top-N).
        self._write_csv(ctx, guild, members)
        self._write_power_summary(ctx, guild, top, total)
        self._collect_into_store(ctx, guild, top, total, target, n)

    def _collect_into_store(self, ctx: Context, guild: str,
                            top: list[tuple[str, Decimal]], total: Decimal,
                            member_count, n: int) -> None:
        """Append this run's top-N to the shared collection so several guilds can
        be graphed side by side later by the compare-guild-power task."""
        from .. import store

        gid = self._read_guild_id(ctx)
        count = store.add_guild(
            gid, guild,
            [self._fmt_trillions(d) for _, d in top],
            self._fmt_trillions(total),
            member_count=member_count, top_n=n,
        )
        names = ", ".join(g["name"] for g in store.guilds())
        ctx.log.info("added %s to the guild-power collection (now %d: %s)",
                     guild, count, names)
        ctx.log.info("run compare-guild-power to graph them side by side")

    # --- one top-to-bottom pass -------------------------------------------
    def _sweep(self, ctx: Context, members: dict, target, skip_overlap: bool) -> None:
        """Walk the list top to bottom once, reading each new member into `members`.

        skip_overlap=True (fast pass): skip the cards a page shares with the
        previous one, so each member is opened just once. skip_overlap=False
        (recovery pass): open every fully-visible card and rely on UID de-dup;
        slower, but coin values can't cause a skip, so it always finds a member
        the fast pass missed (e.g. several equal coin values in a row).
        """
        self._scroll_to_top(ctx)
        page = 0
        stale = 0
        prev_coins: list[str] = []
        while not ctx.should_stop() and page < MAX_PAGES:
            page += 1
            cards = self._visible_cards(ctx.frame())
            coins = [coin for _, coin in cards]
            skip = self._overlap(prev_coins, coins) if skip_overlap else 0
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
                return
            if target and len(members) >= target:
                ctx.log.info("collected all %d members", target)
                return
            # The fast pass expects each page to add someone; a run of empty pages
            # means it's stuck. The recovery pass legitimately re-sees known members
            # page after page, so there it relies on bottom detection alone.
            if skip_overlap:
                stale = stale + 1 if new_here == 0 else 0
                if stale >= 2:
                    ctx.log.info("no new members over 2 pages -> stopping")
                    return
            if not self._scroll_down(ctx):
                ctx.log.info("reached the bottom of the member list")
                return

    # --- main loop --------------------------------------------------------
    def run(self, ctx: Context) -> None:
        if self.params.get("hedgemony"):
            self._run_hedgemony(ctx)
            return
        if not self._present(ctx, "guild_title"):
            ctx.log.warning("not on the Guild Info screen -> open a guild's info first "
                            "and start again")
            return

        guild = self._read_guild_name(ctx)
        target = self._read_member_count(ctx)
        ctx.log.info("guild: %s (members: %s)", guild, target if target else "?")

        members: dict[str, str] = {}  # uid -> power, in discovery order
        try:
            self._sweep(ctx, members, target, skip_overlap=True)
            # If the exact count is known and we came up short, sweep once more
            # opening every card (no coin-based skipping), which cannot skip a
            # member. Only runs on the rare miss, so the fast pass stays fast.
            if (target and len(members) < target and not ctx.should_stop()):
                ctx.log.info("re-checking for %d missed member(s) (full pass)",
                             target - len(members))
                self._sweep(ctx, members, target, skip_overlap=False)
        finally:
            self._write_csv(ctx, guild, members)
            if target and len(members) < target:
                ctx.log.warning("collected %d of %d members - stopped before the end "
                                "(the list stopped scrolling, or a game popup "
                                "interrupted). The CSV has what was read so far.",
                                len(members), target)
            ctx.log.info("get-guild-member-list done: %d members", len(members))
