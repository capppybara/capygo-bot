"""TEMPLATE for a new auto-events event - copy, don't import.

  1. Copy this file to event_<name>.py (e.g. event_seal_battle.py).
  2. Fill in the name, the card position, and the steps in run_daily.
  3. Import it in tasks/__init__.py and add the class to EVENTS in auto_events.py.

The rules every event follows (see event.py and daily.py):
  - run_daily starts on the Events screen and must end back there (go_events),
    so the next event carries on from it. Return False if something went wrong:
    the runner logs it, backs out to the Events screen, and moves on.
  - Tap through self.tap(ctx, target, "what"): it logs and waits ~1s after.
  - Check a screen opened before tapping inside it (self.text_in on a title, or
    find_sprite for a picture), so a missed tap never becomes blind taps.
  - No OCR of names; position taps are fine when the layout is fixed.
  - Each event runs once per game day automatically (the app asks before a re-run).
  - If it's another "like the champions" plaza, subclass PlazaLikes from
    event_plaza.py instead (see event_martial_arts.py): it's just positions.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .event import EventTask, go_events

CARD = Rel(0.35, 0.165)                       # the event's card on its Events tab
SCREEN_TITLE = RelRect(0.25, 0.07, 0.50, 0.05)  # something that proves it opened


@register("new-event")                        # unique task name, kebab-case
class NewEvent(EventTask):
    TITLE = "New Event"
    LABEL = "New event"                       # the switch label in Auto Events
    ICON = "🎯"
    DESCRIPTION = "Events -> <tab> -> <card>: <what it does>, then go back."
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, "arena"):   # "arena" / "challenge" / "dungeon"
            return False
        if not self.tap(ctx, CARD, "New Event"):
            return False
        if not ctx.dry_run and "title word" not in self.text_in(ctx, SCREEN_TITLE):
            ctx.log.warning("%s: the event screen did not open", self.name)
            return False

        # ... the event's steps: self.tap(ctx, Rel(x, y), "what") ...

        return go_events(ctx)                 # back to the Events screen
