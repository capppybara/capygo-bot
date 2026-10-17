"""Base class and shared helpers for guild chores (run by auto-guild / auto-daily).

The guild screen opens from the home screen's "Guild" button, left of Start: a map
with Guild Hall, Guild Expedition, Armament Cache, Guild Raid, Shop, Guild Trade
(a ship with a "Waiting period" countdown), and a back arrow. It's the base for
guild chores: each starts there, opens its place, and backs out to it again.

Planned (user, 2026-10-04): Guild Hall and Guild Trade; maybe Guild Raid later.

Popups can cover the map right after arriving (2026-10-09: "Current League Rank"
with its "Tap to close" at y 882, below where other popups put it), and the
map's labels still read under the dimming, so open_place closes any popup first.
That popup made Guild Hall's tap only close it, and, still up after Guild Hall
gave up, Guild Trade's too. (Guild Trade's label then read "Waiting for
Captain's Appointment": that's about the guild's own ship; plundering others
still works - user.)
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import NEUTRAL, ScreenTask, _crop, find_sprite, go_screen

GUILD_BTN = Rel(0.176, 0.781)                     # "Guild" icon, left of Start on home
HALL_LABEL = RelRect(0.36, 0.250, 0.30, 0.04)     # "Guild Hall"
TRADE_LABEL = RelRect(0.48, 0.812, 0.30, 0.04)    # "Guild Trade"
POPUP_TEXT = RelRect(0.20, 0.80, 0.60, 0.17)      # a popup's "Tap to close" (y 882)
MAX_POPUPS = 3

# Where each place sits on the guild map (from a screenshot; not tapped yet).
PLACE_TIMEOUT = 5.0   # a place's screen shows by then (else it's tapped again)
PLACES = {"guild hall": Rel(0.498, 0.200),
          "guild expedition": Rel(0.285, 0.336),
          "armament cache": Rel(0.720, 0.331),
          "guild raid": Rel(0.316, 0.547),
          "shop": Rel(0.748, 0.542),
          "guild trade": Rel(0.639, 0.736)}


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def on_guild(frame) -> bool:
    """The guild map is up: the Guild Hall and Guild Trade labels both read."""
    return "guild hall" in _words(frame, HALL_LABEL) and \
        "guild trade" in _words(frame, TRADE_LABEL)


def go_guild(ctx: Context) -> bool:
    """Get to the guild screen from anywhere (see go_screen)."""
    return go_screen(ctx, "Guild", on_guild, GUILD_BTN)


class GuildTask(ScreenTask):
    """A guild chore: run_daily starts on the guild screen and returns True once
    it's back there."""
    go_base = staticmethod(go_guild)

    def clear_map(self, ctx: Context) -> bool:
        """Close whatever popup covers the guild map: a "Tap to close" one (a tap
        above it) or one with an X. False only on a stop."""
        if ctx.dry_run:
            return True
        if self.wait(ctx, 1.0):  # popups come up just after arriving
            return False
        for _ in range(MAX_POPUPS):
            frame = ctx.frame()
            if "taptoclose" in _words(frame, POPUP_TEXT).replace(" ", ""):
                target, what = NEUTRAL, "dismiss the popup"
            else:
                target, what = find_sprite(ctx, frame, "close_x.png"), "close the popup (X)"
                if target is None:
                    return True
            if not self.tap(ctx, target, what):
                return False
        return True

    def open_place(self, ctx: Context, place: str, opened=None,
                   timeout: float = PLACE_TIMEOUT) -> bool:
        """Tap one of the guild map's places (a PLACES key), after closing any
        popup over the map. With `opened` (a check on a frame): True once it
        shows; if the map is still there after `timeout`, the place is tapped
        once more (2026-10-16: the Guild Hall tap, 1.4s after arriving on the
        map, didn't take, and the donations were skipped)."""
        if not self.clear_map(ctx):
            return False
        if not ctx.dry_run and not on_guild(ctx.frame()):
            ctx.log.warning("%s: not on the guild screen", self.name)
            return False
        for attempt in (1, 2):
            if not self.tap(ctx, PLACES[place], place.title()):
                return False
            if ctx.dry_run or opened is None:
                return True
            end = time.time() + timeout
            while time.time() < end:
                if opened(ctx.frame()):
                    return True
                if self.wait(ctx, 0.5):
                    return False
            if attempt == 1 and on_guild(ctx.frame()):
                ctx.log.info("%s: %s didn't open -> tapping it again", self.name,
                             place.title())
                continue
            break
        ctx.log.warning("%s: %s didn't open", self.name, place.title())
        return False
