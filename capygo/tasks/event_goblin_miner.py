"""Event: goblin-miner-event.

Starts on the Events screen: Challenge tab -> Goblin Miner card (3rd) -> the Goblin
Miner screen, then hands over to the existing goblin-miner task (goblin_miner.py),
which mines floors until the picks run out. Then the back arrow returns to the Events
screen for the next event.

The miner loads its statue / bomb / cracked-block templates from ctx.templates_dir,
so that points at templates/goblin-miner/ while it runs. (The event can't share the
name "goblin-miner": that's the standalone task's name.)
"""

from __future__ import annotations

import os
import time

from ..geometry import Rel, RelRect
from ..task import Context, register
from .event import EventTask, go_events
from .goblin_miner import GoblinMiner

THIRD_CARD = RelRect(0.12, 0.430, 0.50, 0.05)    # "Goblin Miner" on the Challenge tab
GOBLIN_CARD = Rel(0.35, 0.47)
OPEN_TIMEOUT = 8.0


@register("goblin-miner-event")
class GoblinMinerEvent(EventTask):
    TITLE = "Goblin Miner (event)"
    LABEL = "Goblin miner"
    ICON = "⛏️"
    DESCRIPTION = ("Events -> Challenge -> Goblin Miner, then run the Goblin Miner "
                   "task until the picks run out, and go back.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, "challenge"):
            return False
        if not ctx.dry_run and "goblin miner" not in self.text_in(ctx, THIRD_CARD):
            ctx.log.warning("%s: no Goblin Miner card on the Challenge tab", self.name)
            return False
        if not self.tap(ctx, GOBLIN_CARD, "Goblin Miner"):
            return False

        miner = GoblinMiner()
        miner.configure({})
        if ctx.dry_run:
            ctx.log.info("%s: (dry run) would run goblin-miner here", self.name)
        else:
            end = time.time() + OPEN_TIMEOUT
            while not miner._on_mining_screen(ctx):
                if time.time() > end:
                    ctx.log.warning("%s: the Goblin Miner screen did not open",
                                    self.name)
                    return False
                if self.wait(ctx, 1.0):
                    return False
            ctx.log.info("%s: running goblin-miner", self.name)
            own_templates = ctx.templates_dir
            ctx.templates_dir = os.path.join(os.path.dirname(own_templates),
                                             "goblin-miner")
            try:
                miner.run(ctx)
            finally:
                ctx.templates_dir = own_templates
            if ctx.should_stop():
                return False
        return go_events(ctx)  # back arrow -> the Events screen, for the next event
