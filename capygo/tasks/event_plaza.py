"""Shared flow for the "like the champions" events (Holy Grail War, Martial Arts).

Each opens a plaza showing a division's champions, each with a thumbs-up (20 gems
per like). The flow: open the event's card on its Events tab, like every champion
on the plaza it opens to (the registered division), then use the top-left division
button to switch to each other division in turn and like every champion again,
then back out to the Events screen. Each like raises a reward popup, dismissed by
tapping the plaza title.

Everything is tapped by position - the thumbs-ups sit in the same spots on every
division's plaza, and no names are read (user's call: it only has to tap the
thumbs-ups). Two checks: the plaza opened (its title), and the thumbs-ups are
there. In some phases a plaza has no thumbs-up buttons; then nothing is tapped
there. The thumbs-up is found by its picture (templates/dailies/thumbs_up.png),
in grayscale so both the blue "not liked yet" and grey "liked" states count, and
at several sizes (the Martial Arts Hall draws it at ~90%). Real ones score
0.89-1.00, other screens <= 0.34, thumbs dimmed under a reward popup up to ~0.80.
"""

from __future__ import annotations

import os
import time

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import load_template
from ..task import Context
from .event import EventTask, go_events

TITLE_REGION = RelRect(0.30, 0.070, 0.40, 0.050)  # "Hero Plaza" / "Martial Arts Hall"
# 2026-10-09: Holy Grail War opened on "Select Division" (Rising Star / Dauntless /
# Supreme, a new season's pick) instead of its plaza. That choice is the player's.
SELECT_TITLE = RelRect(0.25, 0.130, 0.50, 0.035)  # "Select Division"
DISMISS = Rel(0.5, 0.11)                           # plaza title: closes a reward popup
THUMB_ROW = RelRect(0.156, 0.47, 0.716, 0.22)      # where the thumbs-ups sit
THUMB_SCALES = [round(s, 2) for s in np.arange(0.80, 1.21, 0.05)]
THUMB_THRESHOLD = 0.85
DIVISION_SETTLE = 2.0                              # the plaza redraws after a switch
OPEN_TIMEOUT = 6.0


class PlazaLikes(EventTask):
    """Set these in a subclass."""
    TAB = "arena"                      # Events tab the card is on
    CARD: Rel                          # the event's card on that tab
    TITLE_WORD: str                    # plaza title, lower case
    THUMBS: list[tuple[str, Rel]]      # (label, position) of each thumbs-up
    PICKER_BTN: Rel                    # top-left division button
    FIRST: str                         # division it opens to (the registered one)
    DIVISIONS: list[tuple[str, Rel]]   # then each of these picker options, in order

    def _thumbs_present(self, ctx: Context) -> bool:
        if ctx.dry_run:
            return True
        path = os.path.join(os.path.dirname(ctx.templates_dir), "dailies",
                            "thumbs_up.png")
        tpl = cv2.cvtColor(load_template(path), cv2.COLOR_BGR2GRAY)
        frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = THUMB_ROW.to_pixels(w, h)
        row = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        for s in THUMB_SCALES:
            t = cv2.resize(tpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            if cv2.minMaxLoc(cv2.matchTemplate(row, t, cv2.TM_CCOEFF_NORMED))[1] \
                    >= THUMB_THRESHOLD:
                return True
        return False

    def _like_all(self, ctx: Context, division: str) -> bool:
        """Like every champion - unless this plaza has no thumbs-ups, then skip."""
        if not self._thumbs_present(ctx):
            ctx.log.info("%s: no thumbs-up buttons on the %s plaza -> skipping",
                         self.name, division)
            return True
        for label, thumb in self.THUMBS:
            if not self.tap(ctx, thumb, f"{division} {label} thumbs-up"):
                return False
            if not self.tap(ctx, DISMISS, "dismiss"):
                return False
        return True

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_tab(ctx, self.TAB):
            return False
        if not self.tap(ctx, self.CARD, self.TITLE):
            return False
        if not ctx.dry_run:
            end = time.time() + OPEN_TIMEOUT
            while self.TITLE_WORD not in self.text_in(ctx, TITLE_REGION):
                if "select division" in self.text_in(ctx, SELECT_TITLE):
                    self.flag(ctx, "it opened on Select Division (a new season's "
                                   "division pick: Rising Star / Dauntless / Supreme). "
                                   "Pick one in the game; the bot won't choose for you. "
                                   "No likes today.")
                    return go_events(ctx)
                if time.time() > end:
                    ctx.log.warning("%s: the plaza did not open", self.name)
                    return False
                if self.wait(ctx, 0.5):
                    return False

        if not self._thumbs_present(ctx):
            ctx.log.info("%s: no thumbs-up buttons on the plaza -> nothing to like, "
                         "back to Events", self.name)
            return go_events(ctx)
        if not self._like_all(ctx, self.FIRST):
            return False
        for name, option in self.DIVISIONS:
            if not self.tap(ctx, self.PICKER_BTN, "division picker"):
                return False
            if not self.tap(ctx, option, name):
                return False
            if self.wait(ctx, DIVISION_SETTLE - 1.0):  # tap already waited ~1s
                return False
            if not self._like_all(ctx, name):
                return False

        return go_events(ctx)  # back arrow -> the Events screen, for the next event
