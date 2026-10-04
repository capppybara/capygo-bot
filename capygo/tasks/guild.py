"""Base class and shared helpers for guild chores (run by auto-guild / auto-daily).

The guild screen opens from the home screen's "Guild" button, left of Start: a map
with Guild Hall, Guild Expedition, Armament Cache, Guild Raid, Shop, Guild Trade
(a ship with a "Waiting period" countdown), and a back arrow. It's the base for
guild chores: each starts there, opens its place, and backs out to it again.

Planned (user, 2026-10-04): Guild Hall and Guild Trade; maybe Guild Raid later.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import ScreenTask, _crop, go_screen

GUILD_BTN = Rel(0.176, 0.781)                     # "Guild" icon, left of Start on home
HALL_LABEL = RelRect(0.36, 0.250, 0.30, 0.04)     # "Guild Hall"
TRADE_LABEL = RelRect(0.48, 0.812, 0.30, 0.04)    # "Guild Trade"

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


def go_guild(ctx: Context) -> bool:
    """Get to the guild screen from anywhere (see go_screen)."""
    return go_screen(ctx, "Guild", on_guild, GUILD_BTN)


class GuildTask(ScreenTask):
    """A guild chore: run_daily starts on the guild screen and returns True once
    it's back there."""
    go_base = staticmethod(go_guild)

    def open_place(self, ctx: Context, place: str) -> bool:
        """Tap one of the guild map's places (a PLACES key)."""
        if not ctx.dry_run and not on_guild(ctx.frame()):
            ctx.log.warning("%s: not on the guild screen", self.name)
            return False
        return self.tap(ctx, PLACES[place], place.title())
