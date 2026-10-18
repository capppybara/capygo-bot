"""Base class and shared helpers for event chores (run by auto-events).

Events live behind the home screen's "Events" button. That Events screen - bottom
tabs Arena / Challenge / Dungeon plus a back arrow - is the base for event chores:
each event starts there, picks its tab and card, does its work, and backs out to it
again, so the next event carries on from there. auto-events goes home only after
the last event. Run alone (./run.sh tower-challenge), an event goes to the Events
screen first and home at the end.
"""

from __future__ import annotations

import time

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import ScreenTask, _crop, go_screen

EVENTS_BTN = Rel(0.832, 0.789)                   # "Events", home screen bottom-right
EVENT_TABS = RelRect(0.35, 0.935, 0.55, 0.045)   # "Arena Challenge Dungeon"
TABS = {"arena": Rel(0.442, 0.958),
        "challenge": Rel(0.623, 0.958),
        "dungeon": Rel(0.800, 0.958)}


CARDS = RelRect(0.10, 0.07, 0.80, 0.83)   # an Events tab's cards (not the top bar or tabs)
CARD_DY = 40 / 951                         # a card's title -> its middle (tap there)
CARD_TIMEOUT = 3.0                         # the tab's cards show by then


def card_at(ctx: Context, words: str, fallback: Rel) -> Rel | None:
    """Where to tap the open Events tab's card whose title contains `words`
    (lower case), found by reading the titles: cards move when an event comes or
    goes (2026-10-17: Seal Battle left the Arena tab, the cards below moved up
    one, and the likes tapped the wrong cards - user). `fallback` (the old fixed
    spot) on a dry run. None if the card isn't on the tab."""
    if ctx.dry_run:
        return fallback
    end = time.time() + CARD_TIMEOUT
    while True:
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = CARDS.to_pixels(w, h)
        for t, _, cy in ocr_lines(frame[y0:y1, x0:x1]):
            if words in t.lower():
                return Rel(0.35, (y0 + cy) / h + CARD_DY)
        if time.time() >= end or ctx.should_stop():
            return None
        time.sleep(0.3)


def on_events(frame) -> bool:
    """The Events screen (any tab) is up: its bottom tabs read Challenge + Dungeon."""
    text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, EVENT_TABS))).lower()
    return "challenge" in text and "dungeon" in text


def go_events(ctx: Context) -> bool:
    """Get to the Events screen from anywhere (see go_screen)."""
    return go_screen(ctx, "Events", on_events, EVENTS_BTN)


class EventTask(ScreenTask):
    """An event chore: run_daily starts on the Events screen and returns True once
    it's back there."""
    go_base = staticmethod(go_events)

    def open_tab(self, ctx: Context, tab: str) -> bool:
        """Tap one of the Events screen's bottom tabs (arena/challenge/dungeon)."""
        if not ctx.dry_run and not on_events(ctx.frame()):
            ctx.log.warning("%s: not on the Events screen", self.name)
            return False
        return self.tap(ctx, TABS[tab], f"{tab.title()} tab")
