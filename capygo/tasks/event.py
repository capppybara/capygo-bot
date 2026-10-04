"""Base class and shared helpers for event chores (run by auto-events).

Events live behind the home screen's "Events" button. That Events screen - bottom
tabs Arena / Challenge / Dungeon plus a back arrow - is the base for event chores:
each event starts there, picks its tab and card, does its work, and backs out to it
again, so the next event carries on from there. auto-events goes home only after
the last event. Run alone (./run.sh tower-challenge), an event goes to the Events
screen first and home at the end.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import (HOME, NEUTRAL, SWITCH_SETTLE, TAP_SETTLE, DailyTask, _crop,
                    go_home, home_state, next_move, tap, wait)

EVENTS_BTN = Rel(0.832, 0.789)                   # "Events", home screen bottom-right
EVENT_TABS = RelRect(0.35, 0.935, 0.55, 0.045)   # "Arena Challenge Dungeon"
TABS = {"arena": Rel(0.442, 0.958),
        "challenge": Rel(0.623, 0.958),
        "dungeon": Rel(0.800, 0.958)}


def on_events(frame) -> bool:
    """The Events screen (any tab) is up: its bottom tabs read Challenge + Dungeon."""
    text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, EVENT_TABS))).lower()
    return "challenge" in text and "dungeon" in text


def go_events(ctx: Context, max_steps: int = 12) -> bool:
    """Get to the Events screen from anywhere: from home tap Events; from inside an
    event (or a popup) back out with go_home's moves until the Events tabs show."""
    if ctx.dry_run:
        return True
    opened = 0
    unknowns = 0
    for _ in range(max_steps):
        if ctx.should_stop():
            return False
        frame = ctx.frame()
        if on_events(frame):
            return True
        if home_state(frame) == HOME:
            if opened >= 2:
                ctx.log.warning("tapped Events twice but the Events screen didn't open")
                return False
            opened += 1
            ctx.log.info("to Events: tap Events")
            if not tap(ctx, EVENTS_BTN):
                return False
            continue
        move, target = next_move(ctx, frame)
        if move == "stuck":
            ctx.log.warning("on the main screen, but the capy switch is neither blue "
                            "nor red")
            return False
        if move == "unknown":
            unknowns += 1
            if unknowns == 1:  # often just a transition: give it a moment
                if wait(ctx, 1.0):
                    return False
                continue
            target = NEUTRAL
        else:
            unknowns = 0
        ctx.log.info("to Events: %s", move)
        if not tap(ctx, target, SWITCH_SETTLE if move == "switch" else TAP_SETTLE):
            return False
    return on_events(ctx.frame())


class EventTask(DailyTask):
    """An event chore: run_daily starts on the Events screen and returns True once
    it's back there."""

    def prepare(self, ctx: Context) -> bool:
        return go_events(ctx)

    def wrap_up(self, ctx: Context, ok: bool) -> None:
        if not ok:
            ctx.log.warning("%s did not finish; returning to the home screen", self.name)
        go_home(ctx)

    def open_tab(self, ctx: Context, tab: str) -> bool:
        """Tap one of the Events screen's bottom tabs (arena/challenge/dungeon)."""
        if not ctx.dry_run and not on_events(ctx.frame()):
            ctx.log.warning("%s: not on the Events screen", self.name)
            return False
        return self.tap(ctx, TABS[tab], f"{tab.title()} tab")
