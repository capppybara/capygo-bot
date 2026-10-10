"""Base class and shared helpers for guild chores (run by auto-guild / auto-daily).

The guild screen opens from the home screen's "Guild" button, left of Start: a map
with Guild Hall, Guild Expedition, Armament Cache, Guild Raid, Shop, Guild Trade
(a ship with a "Waiting period" countdown), and a back arrow. It's the base for
guild chores: each starts there, opens its place, and backs out to it again.

Planned (user, 2026-10-04): Guild Hall and Guild Trade; maybe Guild Raid later.

Popups can cover the map right after arriving (2026-10-09: "Current League Rank"
with its "Tap to close" at y 882, below where other popups put it), and the
map's labels still read under the dimming, so open_place closes any popup first.
Guild Trade can also be waiting for the guild to appoint a captain (the label
under it reads "Waiting for Captain's Appointment"): nothing to plunder then.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import NEUTRAL, ScreenTask, _crop, find_sprite, go_screen

GUILD_BTN = Rel(0.176, 0.781)                     # "Guild" icon, left of Start on home
HALL_LABEL = RelRect(0.36, 0.250, 0.30, 0.04)     # "Guild Hall"
TRADE_LABEL = RelRect(0.48, 0.812, 0.30, 0.04)    # "Guild Trade"
TRADE_STATUS = RelRect(0.50, 0.843, 0.28, 0.032)  # under it: "Waiting for Captain's..."
POPUP_TEXT = RelRect(0.20, 0.80, 0.60, 0.17)      # a popup's "Tap to close" (y 882)
MAX_POPUPS = 3

# Where each place sits on the guild map (from a screenshot; not tapped yet).
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


def trade_needs_captain(frame) -> bool:
    """Guild Trade is waiting for the guild to appoint a captain (no trading)."""
    return "captain" in _words(frame, TRADE_STATUS)


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

    def open_place(self, ctx: Context, place: str) -> bool:
        """Tap one of the guild map's places (a PLACES key), after closing any
        popup over the map."""
        if not self.clear_map(ctx):
            return False
        if not ctx.dry_run and not on_guild(ctx.frame()):
            ctx.log.warning("%s: not on the guild screen", self.name)
            return False
        return self.tap(ctx, PLACES[place], place.title())
