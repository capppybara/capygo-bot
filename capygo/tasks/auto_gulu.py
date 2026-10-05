"""Task: auto-gulu (Gulu Mine with a friend). HOSTING mode; joining comes later.

Gulu Mine is reached from home: Events -> Challenge tab -> the 4th card "Gulu
Mine" -> a panel that always opens on your highest unlocked difficulty ("28
Torment"), with a ◀ to lower it -> "Go to Team" -> the team screen "Gulu
Mine-Torment25": you on the left, an empty partner slot on the right, Random
Match / Invite. Invite -> "Team Invitation" (tabs Recommend / Friend / Guild):
each friend row has an Invite button that turns into "Invited". When the friend
joins, their name shows under the partner slot and Random Match becomes Start
Challenge.

Hosting (user, 2026-10-05):
  1. Already on the Gulu team screen at this difficulty with a partner -> step 5.
  2. Otherwise enter Gulu and pick the difficulty (tap ◀ down from the max).
  3. Invite the friend from the Friend tab (first page only, no scrolling).
  4. Every 10s, for up to 30 minutes, check whether they joined (never
     re-invite); on a timeout the task stops.
  5. The "stay" setting (an app input) picks the loop.
  6. Stay off: Start Challenge, pick the top two skills on both skill screens,
     then quit the run at once: Skills (in battle) -> home (bottom-left) ->
     "Tips: Exiting will immediately settle rewards..." OK -> dismiss the
     "Defeat" result -> home; an occasional second confirmation gets Cancel.
     Then back to step 2, until the number of runs is done. The skill screens
     always look the same, so it's all fixed positions with the user's waits
     (the Skills panel does NOT pause the run: be quick, or the next day's
     skill picker comes up).
  7. Stay on: NOT BUILT YET (the Victory/Defeat end of a full run hasn't been
     captured).
"""

from __future__ import annotations

import re
import time
from difflib import SequenceMatcher

import cv2

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Param, Task, register
from .daily import HOME, _crop, find_sprite, go_home, home_state, tap, wait
from .event import TABS, go_events

CARD_NAME = RelRect(0.12, 0.595, 0.50, 0.05)       # Challenge tab, 4th: "Gulu Mine"
GULU_CARD = Rel(0.35, 0.64)
PANEL_TITLE = RelRect(0.30, 0.125, 0.40, 0.05)     # "Gulu Mine"
LEVEL = RelRect(0.343, 0.421, 0.311, 0.095)        # "28 Torment"
LEVEL_DOWN = Rel(0.215, 0.463)                     # ◀
GO_TO_TEAM = Rel(0.5, 0.835)
TEAM_TITLE = RelRect(0.234, 0.168, 0.545, 0.042)   # "Gulu Mine-Torment25"
PARTNER_NAME = RelRect(0.514, 0.520, 0.327, 0.068)  # their name, once joined (log only)
PLUS_SLOT = RelRect(0.615, 0.447, 0.117, 0.068)    # the empty slot's green "+"
PLUS_SHARE = 0.02          # lime share: empty slot 0.045-0.051, a partner 0.00
INVITE_BTN = Rel(0.678, 0.757)
INVITE_TITLE = RelRect(0.25, 0.125, 0.50, 0.05)    # "Team Invitation"
FRIEND_TAB = Rel(0.500, 0.849)
FRIEND_NAMES = (180, 400, 180, 640)                # px x0, x1, y0, y1: first page
ROW_INVITE_X, ROW_INVITE_DY = 463, 18              # a row's Invite: name y + 18
ROW_STATUS = (400, 530, -12, 48)                   # x0, x1, dy0, dy1: "Invited"

# The run (px at 642x951) and the user's waits after each tap, in seconds.
START_BTN = (217, 718)                             # "Start Challenge"
SKILL_TOP, SKILL_SECOND = (320, 320), (320, 450)   # the top two skill cards
SELECT_BTN = (321, 833)                            # "2/2 Select Skills"
SKILLS_BTN = (358, 818)                            # in battle, bottom bar
HOME_BTN = (105, 852)                              # Skills panel, bottom-left
QUIT_OK = (210, 601)                               # "Tips: Exiting..." OK
RESULT_DISMISS = (321, 104)                        # "Defeat" screen, above it all
CHOOSE_TITLE = RelRect(0.25, 0.140, 0.50, 0.070)   # "Choose skill"
TIPS_TEXT = RelRect(0.10, 0.480, 0.80, 0.075)      # "Exiting will immediately..."
DIALOG_BUTTONS = RelRect(0.15, 0.610, 0.70, 0.045)  # a confirmation's "OK  Cancel"
RUN_TAPS = [  # (what, position, wait after) - user's timings
    ("skill 1", SKILL_TOP, 1.0), ("skill 2", SKILL_SECOND, 1.0),
    ("Select Skills", SELECT_BTN, 3.0),
    ("skill 3", SKILL_TOP, 1.0), ("skill 4", SKILL_SECOND, 1.0),
    ("Select Skills", SELECT_BTN, 3.0),
    ("Skills", SKILLS_BTN, 2.0), ("home", HOME_BTN, 2.0),
]
START_WAIT = 4.0          # user: 2s was too soon for the 1st skill pick
HOME_TIMEOUT = 15.0

JOIN_POLL = 10.0          # user: check every 10 seconds (was 30)
JOIN_TIMEOUT = 30 * 60    # user: give up after 30 minutes and stop
NAME_MATCH = 0.8
SETTLE = 1.0
OPEN_TIMEOUT = 8.0


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def team_level(frame) -> int | None:
    """The difficulty in the team screen's title ("Gulu Mine-Torment25" -> 25), or
    None when that screen isn't up."""
    title = _words(frame, TEAM_TITLE).replace(" ", "")
    if "gulumine" not in title:
        return None
    m = re.search(r"(\d+)$", title)
    return int(m.group(1)) if m else None


def slot_empty(frame) -> bool:
    """The partner slot still shows its green "+" (user: a character replaces it
    when someone joins). Only meaningful on the team screen."""
    hsv = cv2.cvtColor(_crop(frame, PLUS_SLOT), cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[..., i].astype(int) for i in range(3))
    return float(((h >= 30) & (h <= 45) & (s >= 150) & (v >= 170)).mean()) >= PLUS_SHARE


def partner(frame) -> str:
    """Who joined (their name, for the log), or "" while the slot is free."""
    if slot_empty(frame):
        return ""
    return _words(frame, PARTNER_NAME) or "a partner"


def _rel(pos: tuple[int, int]) -> tuple[float, float]:
    return pos[0] / 642, pos[1] / 951


def _same_name(a: str, b: str) -> bool:
    a, b = re.sub(r"\s", "", a.lower()), re.sub(r"\s", "", b.lower())
    return a == b or SequenceMatcher(None, a, b).ratio() >= NAME_MATCH


@register("auto-gulu")
class AutoGulu(Task):
    TITLE = "Auto Gulu"
    ICON = "💎"
    DESCRIPTION = ("Gulu Mine with a friend. Hosting: enter Gulu at your difficulty, "
                   "invite your friend, wait for them, and run it the number of times "
                   "you set.")
    START_HINT = ("Start anywhere in the game. If you're already on the Gulu team "
                  "screen with your friend in it, it carries on from there.")
    PARAMS = [
        Param("difficulty", "int", 25, "Difficulty", min=1, max=999,
              help="Gulu Mine difficulty to host (the panel opens on your max)"),
        Param("friend", "str", "pinkdolly", "Friend to invite",
              help="their name on your Friend list (first page)"),
        Param("runs", "int", 4, "Runs", min=1, max=100),
        Param("stay", "bool", False, "Stay",
              help="hosting: stay in the run to the end instead of quitting it"),
    ]

    def run(self, ctx: Context) -> None:
        p = self.params
        ctx.log.info("auto-gulu: hosting difficulty %d with %s, %d run(s), stay=%s",
                     p["difficulty"], p["friend"], p["runs"], p["stay"])
        if p["stay"]:
            ctx.log.warning("auto-gulu: the stay loop (step 7) isn't built yet -> "
                            "stopping")
            return
        for n in range(1, p["runs"] + 1):
            if ctx.should_stop() or not self._team_ready(ctx):
                break
            ctx.log.info("auto-gulu: run %d/%d", n, p["runs"])
            if not self._run_and_quit(ctx):
                ctx.log.warning("auto-gulu: run %d didn't finish cleanly -> stopping", n)
                break
            ctx.log.info("auto-gulu: run %d/%d done", n, p["runs"])
        else:
            ctx.log.info("auto-gulu: all %d run(s) done", p["runs"])

    # --- step 6: run, then quit at once ----------------------------------------
    def _run_and_quit(self, ctx: Context) -> bool:
        """Start, pick the top two skills twice, quit via Skills -> home -> OK,
        dismiss the result, and get home. Fixed positions and the user's waits."""
        if not self._tap(ctx, Rel(*_rel(START_BTN)), "Start Challenge", START_WAIT):
            return False
        if not ctx.dry_run and "choose skill" not in _words(ctx.frame(), CHOOSE_TITLE):
            ctx.log.warning("auto-gulu: no skill screen after Start")
            return False
        for what, pos, after in RUN_TAPS:
            if not self._tap(ctx, Rel(*_rel(pos)), what, after):
                return False
        if not ctx.dry_run and "exiting" not in _words(ctx.frame(), TIPS_TEXT):
            ctx.log.warning("auto-gulu: no exit confirmation after home")
            return False
        if not self._tap(ctx, Rel(*_rel(QUIT_OK)), "OK (leave the run)", 2.0):
            return False
        if not self._second_confirmation(ctx):
            return False
        if not self._tap(ctx, Rel(*_rel(RESULT_DISMISS)), "dismiss the result", 2.0):
            return False
        if ctx.dry_run:
            return True
        end = time.time() + HOME_TIMEOUT
        while time.time() < end:
            if home_state(ctx.frame()) == HOME:
                return True
            if not self._second_confirmation(ctx):
                return False
            if wait(ctx, 0.5):
                return False
        ctx.log.warning("auto-gulu: not home after leaving the run; backing out")
        return go_home(ctx)

    def _second_confirmation(self, ctx: Context) -> bool:
        """User: an occasional second confirmation shows up; its button sits about
        where the first one's OK was, so if a dialog's buttons are showing, tap
        that spot. False only on a stop."""
        if ctx.dry_run or "cancel" not in _words(ctx.frame(), DIALOG_BUTTONS):
            return True
        return self._tap(ctx, Rel(*_rel(QUIT_OK)), "second confirmation", 2.0)

    # --- steps 1-4 ----------------------------------------------------------
    def _team_ready(self, ctx: Context) -> bool:
        """Get to the Gulu team screen at the difficulty with the friend joined."""
        level = self.params["difficulty"]
        if not ctx.dry_run:
            frame = ctx.frame()
            on = team_level(frame)
            if on == level:
                who = partner(frame)
                if who:
                    ctx.log.info("auto-gulu: already on the team screen with %s", who)
                    return True
                ctx.log.info("auto-gulu: on the team screen, nobody joined yet")
                return self._invite(ctx) and self._wait_join(ctx)
            if on is not None:
                ctx.log.info("auto-gulu: on a Torment%d team, want %d -> leaving", on,
                             level)
        if not self._enter(ctx):
            return False
        return self._invite(ctx) and self._wait_join(ctx)

    def _enter(self, ctx: Context) -> bool:
        """Events -> Challenge -> Gulu Mine -> the difficulty -> Go to Team."""
        target = self.params["difficulty"]
        if not go_events(ctx):
            ctx.log.warning("auto-gulu: couldn't get to the Events screen")
            return False
        if not self._tap(ctx, TABS["challenge"], "Challenge tab"):
            return False
        if not ctx.dry_run and "gulu" not in _words(ctx.frame(), CARD_NAME):
            ctx.log.warning("auto-gulu: no Gulu Mine card on the Challenge tab")
            return False
        if not self._tap(ctx, GULU_CARD, "Gulu Mine"):
            return False
        if ctx.dry_run:
            return self._tap(ctx, GO_TO_TEAM, "Go to Team")
        if not self._until(ctx, lambda: "gulu" in _words(ctx.frame(), PANEL_TITLE)):
            ctx.log.warning("auto-gulu: the Gulu Mine panel didn't open")
            return False
        for _ in range(200):
            m = re.search(r"\d+", _words(ctx.frame(), LEVEL))
            now = int(m.group()) if m else None
            if now is None:
                ctx.log.warning("auto-gulu: couldn't read the difficulty")
                return False
            if now == target:
                break
            if now < target:
                ctx.log.warning("auto-gulu: difficulty %d is above your max (%d)",
                                target, now)
                return False
            if not tap(ctx, LEVEL_DOWN, 0.9):
                return False
        if not self._tap(ctx, GO_TO_TEAM, f"Go to Team (difficulty {target})"):
            return False
        if not self._until(ctx, lambda: team_level(ctx.frame()) == target):
            ctx.log.warning("auto-gulu: the Torment%d team screen didn't open", target)
            return False
        return True

    def _invite(self, ctx: Context) -> bool:
        """Invite the friend from the Friend tab's first page (never scroll)."""
        friend = self.params["friend"]
        if not self._tap(ctx, INVITE_BTN, "Invite"):
            return False
        if ctx.dry_run:
            return True
        if not self._until(ctx, lambda: "invitation" in _words(ctx.frame(), INVITE_TITLE)):
            ctx.log.warning("auto-gulu: the Team Invitation popup didn't open")
            return False
        if not self._tap(ctx, FRIEND_TAB, "Friend tab"):
            return False
        frame = ctx.frame()
        h, w = frame.shape[:2]
        kx, ky = w / 642, h / 951
        x0, x1, y0, y1 = FRIEND_NAMES
        crop = frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]
        name_y = next((cy / ky + y0 for t, _, cy in ocr_lines(crop)
                       if _same_name(t, friend)), None)
        if name_y is None:
            ctx.log.warning("auto-gulu: %s isn't on the first page of your friends "
                            "(offline, or further down) -> stopping", friend)
            self._close_popup(ctx)
            return False
        if not self._tap(ctx, Rel(ROW_INVITE_X / 642, (name_y + ROW_INVITE_DY) / 951),
                         f"Invite {friend}"):
            return False
        sx0, sx1, dy0, dy1 = ROW_STATUS
        status = " ".join(t for t, _, _ in ocr_lines(ctx.frame()[
            int((name_y + dy0) * ky):int((name_y + dy1) * ky), int(sx0 * kx):int(sx1 * kx)]))
        if "vited" not in status.lower():  # OCR has read "Invited" as "Unvited"
            ctx.log.warning("auto-gulu: %s's row reads %r, not Invited", friend, status)
        return self._close_popup(ctx)

    def _wait_join(self, ctx: Context) -> bool:
        """Check every 10s, up to 30 minutes, for a partner; never re-invite."""
        if ctx.dry_run:
            return True
        start = time.time()
        next_note = start + 300
        while True:
            frame = ctx.frame()
            if team_level(frame) is None:  # first: elsewhere the name spot has junk
                ctx.log.warning("auto-gulu: left the team screen while waiting")
                return False
            who = partner(frame)
            if who:
                ctx.log.info("auto-gulu: %s joined after %.0fs", who, time.time() - start)
                return True
            if time.time() - start >= JOIN_TIMEOUT:
                ctx.log.warning("auto-gulu: nobody joined in %d minutes -> stopping",
                                JOIN_TIMEOUT // 60)
                return False
            if time.time() >= next_note:
                next_note += 300
                ctx.log.info("auto-gulu: still waiting for %s (%.0f min)",
                             self.params["friend"], (time.time() - start) / 60)
            if wait(ctx, JOIN_POLL):
                return False

    # --- helpers ------------------------------------------------------------
    def _close_popup(self, ctx: Context) -> bool:
        x = find_sprite(ctx, ctx.frame(), "close_x.png")
        if x is None:
            ctx.log.warning("auto-gulu: no X to close the invitation popup")
            return False
        return self._tap(ctx, x, "close the invitation popup")

    def _tap(self, ctx: Context, target, what: str, after: float = 1.0) -> bool:
        """Log, tap, then wait `after` seconds. False if a stop was requested."""
        if ctx.should_stop():
            return False
        ctx.log.info("auto-gulu: tap %s", what)
        return tap(ctx, target, after)

    def _until(self, ctx: Context, check, timeout: float = OPEN_TIMEOUT) -> bool:
        end = time.time() + timeout
        while True:
            if check():
                return not wait(ctx, SETTLE)
            if time.time() >= end or wait(ctx, 0.3):
                return False
