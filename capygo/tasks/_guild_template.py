"""TEMPLATE for a new guild chore - copy, don't import.

  1. Copy this file to guild_<name>.py (e.g. guild_trade.py).
  2. Fill in the name, the place, and the steps in run_daily.
  3. Import it in tasks/__init__.py and add the class to GUILD in auto_guild.py.

The rules every guild chore follows (see guild.py and daily.py):
  - run_daily starts on the guild screen and must end back there (go_guild), so
    the next chore carries on from it. Return False if something went wrong: the
    runner logs it, backs out to the guild screen, and moves on.
  - Tap through self.tap(ctx, target, "what"): it logs and waits ~1s after.
  - Check a screen opened before tapping inside it (self.text_in on a title), and
    wait for slow screens to load and settle before tapping.
  - Each chore runs once per game day automatically (the app asks before a re-run).
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .guild import GuildTask, go_guild

SCREEN_TITLE = RelRect(0.25, 0.07, 0.50, 0.05)  # something that proves it opened


@register("new-guild-chore")                  # unique task name, kebab-case
class NewGuildChore(GuildTask):
    TITLE = "New Guild Chore"
    LABEL = "New guild chore"                 # the switch label on Auto Daily
    ICON = "🏰"
    DESCRIPTION = "Guild -> <place>: <what it does>, then go back."
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_place(ctx, "guild hall"):  # a key of guild.PLACES
            return False
        if not ctx.dry_run and "title word" not in self.text_in(ctx, SCREEN_TITLE):
            ctx.log.warning("%s: the place did not open", self.name)
            return False

        # ... the chore's steps: self.tap(ctx, Rel(x, y), "what") ...

        return go_guild(ctx)                  # back to the guild screen
