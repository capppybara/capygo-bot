"""Task: auto-gulu (Gulu Mine with a friend): hosting, or joining (the Join switch).

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
     Then back to step 2, until the number of runs is done. Each skill screen
     is picked the way joining does it: wait for a fresh "0/2" screen, let it
     settle 2s (the cards slide in), tap the top two, and Select only while the
     screen is still up; a counter still short then (a swallowed tap) gets
     the next card(s) first. (2026-10-06: the old fixed-timing taps missed a pick
     and every later tap landed a screen behind, so the quit never happened.)
     Skills goes in once the skill screen has closed; the Skills panel does NOT
     pause the run, so Skills -> home -> OK keep the user's quick waits.
  7. Stay on (user, 2026-10-08): play each run to the end with the joiner's run
     code (every skill screen picked, then the result's OK). That leaves the
     host on the team screen with the teammate still in: Start Challenge again,
     every 5s until it takes (it may not until the teammate is ready). Not
     started within ~5 minutes: maybe a bug, so Remove the teammate (the red
     button under their name), invite them again, and keep trying. Start is
     only tapped while it reads "Start Challenge": with nobody in, the same
     button is Random Match.

Joining (user, 2026-10-05):
  Already on a Gulu team screen -> carry on. Otherwise, every 10s for up to 30
  minutes: find the "New Invitation" banner (right edge) -> open it ("Team
  Invitation") -> make sure the mode selector (top-left) says Gulu Mine, else
  open it and pick the top option (Gulu Mine is always first) -> find the
  friend's invite -> tap its ✓. No banner / no invite from the friend: close it,
  wait 10s, look again. Never the ✗, "Reject all", or the "No longer show
  invitation messages" box.
  While waiting for the host to start, invites can come in on the team screen:
  the host sometimes can't start (a bug), leaves, and invites from a new room
  (user, 2026-10-08). So until the start the bot loops through: the banner ->
  open it -> accept the friend's invite if there is one -> look for the start.
  Then the run, always played to the end: every 2s look for a skill screen or
  the result. Battle 1 has two screens of 2 picks (the hosting positions and
  waits); battles 2-4 have two screens of 1 pick (the top of 3 cards). The
  result: Victory has an OK button; Defeat closes with a tap. Where that leaves
  you says whether the host stayed: the Gulu team screen -> wait (2s checks) for
  the host's next start, which brings battle 1's 2x2 picks again; home -> the
  invitation flow. Repeat until the number of runs is done.
"""

from __future__ import annotations

import re
import time

import cv2

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Param, Task, register
from .daily import (HOME, _crop, find_sprite, go_home, home_state, save_snapshot, tap,
                    wait)
from .event import TABS, go_events
from . import invites
from .invites import same_name

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
QUIT_TAPS = [  # (what, position, wait after) - user's timings
    ("Skills", SKILLS_BTN, 2.0), ("home", HOME_BTN, 2.0),
]
START_WAIT = 2.0          # user: 2s after Start, then look for the skill screen
HOST_SKILL_TIMEOUT = 30.0  # each skill screen must come up by then
BATTLE_TIMEOUT = 30.0     # after the 2nd Select: the skill screen closes by then
QUIT_TRIES = 3            # Skills -> home again while no exit confirmation shows:
                          # a Skills tap 0.3s after the last skill screen closed
                          # didn't register (2026-10-10 run 2). No settle before the
                          # first try; 1s before each retry (user)
RETRY_WAIT = 1.0
SKILLS_LABEL = RelRect(0.52, 0.84, 0.16, 0.04)     # the battle's "Skills" button text
HOME_TIMEOUT = 15.0
# Stay mode (hosting)
START_LABEL = RelRect(0.20, 0.735, 0.28, 0.040)    # "Start Challenge" / "Random Match"
REMOVE_BTN = (438, 587)                            # red "Remove" under the teammate
REMOVE_LABEL = RelRect(0.60, 0.594, 0.16, 0.040)
DIALOG_AREA = RelRect(0.10, 0.35, 0.80, 0.40)      # where a confirm's OK would be
START_RETRY = 5.0         # user: tap Start again every 5s until the teammate is ready
STUCK_AFTER = 5 * 60      # user: not started in ~5 min -> Remove them, invite again
TEAM_BACK_TIMEOUT = 15.0  # after a result: the team screen is back by then
REMOVE_TIMEOUT = 6.0

# Joining: the invitation banner and popup
# Joining: the run
SKILL_ONE = (320, 385)                             # 1-pick screens: the top of 3 cards
# If a pick didn't register (2026-10-06: a connection overlay swallowed a tap),
# the counter reads short before Select: tap the next unpicked card(s) instead.
SPARE_TWO = [(320, 578), (320, 706)]               # 2-pick screens: cards 3 and 4
SPARE_ONE = [(320, 513), (320, 642)]               # 1-pick screens: cards 2 and 3
# User: skill picking never waits for the teammate - each player's screen runs
# on its own timer. So a screen still up showing picks this long after Select
# means a tap didn't take: Select again (and pick the missing card first).
# Left alone, the screen times out and the next one gets only ~3s (2026-10-08).
RESELECT_AFTER = 2.0
PICK_COUNT = RelRect(0.31, 0.845, 0.38, 0.060)     # "0/2 Select Skills" / "0/1 ..."
RESULT_TITLE = RelRect(0.25, 0.385, 0.50, 0.065)   # "Victory" / "Defeat"
RESULT_OK = (320, 812)                             # Victory screen's OK
RESULT_OK_LABEL = RelRect(0.35, 0.830, 0.30, 0.050)
SKILL_POLL = 2.0          # user: look for the skill screen every 2 seconds (was 5)
SELECT_WAIT = 2.0         # user: look again 2s after Select (was 3; the next
                          # screen shows ~1s after Select)
SKILL_SETTLE = 2.0        # user: wait 2s after spotting a skill screen, then pick
START_TIMEOUT = 30 * 60   # waiting for the host to start
RUN_TIMEOUT = 15 * 60     # a run that has started should end well before this
INVITE_POLL = 10.0        # user: look again every 10 seconds
INVITE_TIMEOUT = 30 * 60  # user: give up after 30 minutes

JOIN_POLL = 10.0          # user: check every 10 seconds (was 30)
JOIN_TIMEOUT = 30 * 60    # user: give up after 30 minutes and stop
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


def in_gulu(frame) -> bool:
    """On a Gulu team screen, or a Gulu skill screen (the host already started)."""
    return team_level(frame) is not None or "choose skill" in _words(frame, CHOOSE_TITLE)


def result_title(frame) -> str:
    """ "victory" / "defeat" while a run's result screen is up, else ""."""
    text = _words(frame, RESULT_TITLE)
    return next((r for r in ("victory", "defeat") if r in text), "")


def _dialog_ok(frame) -> Rel | None:
    """A confirm dialog's OK / Confirm button (an exact label in the middle of the
    screen), or None. The plain team screen has none."""
    h, w = frame.shape[:2]
    x0, y0, _, _ = DIALOG_AREA.to_pixels(w, h)
    for t, cx, cy in ocr_lines(_crop(frame, DIALOG_AREA)):
        if t.strip().lower() in ("ok", "confirm"):
            return Rel((x0 + cx) / w, (y0 + cy) / h)
    return None


def _picks(frame) -> tuple[int, int] | None:
    """The Select button's "picked/wanted" ("0/2 Select Skills" -> (0, 2)); None
    if unreadable. Wanted is 2 on battle 1's screens, else 1."""
    m = re.search(r"(\d)\s*/\s*(\d)", _words(frame, PICK_COUNT))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _rel(pos: tuple[int, int]) -> tuple[float, float]:
    return pos[0] / 642, pos[1] / 951


@register("auto-gulu")
class AutoGulu(Task):
    TITLE = "Auto Gulu"
    ICON = "💎"
    DESCRIPTION = ("Gulu Mine with a friend, the number of times you set. Host: enter "
                   "Gulu at your difficulty and invite them. Join: accept their invite.")
    START_HINT = ("Start anywhere in the game. If you're already on the Gulu team "
                  "screen with your friend in it, it carries on from there.")
    PARAMS = [
        Param("join", "bool", False, "Join instead of host",
              help="on: wait for the friend's invite and join it; off: host"),
        Param("friend", "str", "pinkdolly", "Friend",
              help="hosting: who to invite; joining: whose invite to accept"),
        Param("runs", "int", 4, "Runs", min=1, max=100),
        Param("difficulty", "int", 25, "Difficulty (hosting)", min=1, max=999,
              help="Gulu Mine difficulty to host (the panel opens on your max)"),
        Param("stay", "bool", False, "Stay (hosting)",
              help="hosting: stay in the run to the end instead of quitting it"),
    ]

    def run(self, ctx: Context) -> None:
        p = self.params
        if p["join"]:
            ctx.log.info("auto-gulu: joining %s's Gulu, %d run(s)", p["friend"],
                         p["runs"])
            self._join_loop(ctx)
            return
        ctx.log.info("auto-gulu: hosting difficulty %d with %s, %d run(s), stay=%s",
                     p["difficulty"], p["friend"], p["runs"], p["stay"])
        if p["stay"]:
            self._stay_loop(ctx)
            return
        for n in range(1, p["runs"] + 1):
            if ctx.should_stop() or not self._team_ready(ctx):
                break
            ctx.log.info("auto-gulu: run %d/%d", n, p["runs"])
            if not self._run_and_quit(ctx):
                shot = None if ctx.should_stop() else save_snapshot(ctx, "gulu-host-failed")
                ctx.log.warning("auto-gulu: run %d didn't finish cleanly -> stopping%s",
                                n, f"; screen saved: {shot}" if shot else "")
                break
            ctx.log.info("auto-gulu: run %d/%d done", n, p["runs"])
        else:
            ctx.log.info("auto-gulu: all %d run(s) done", p["runs"])

    # --- joining: find and accept the friend's invite ----------------------------
    def _join(self, ctx: Context) -> bool:
        """Accept the friend's Gulu invite: look every 10s, up to 30 minutes. Every
        2s in between, check whether the game is in Gulu after all: after a run's
        result the team screen can load late (2026-10-08: checked once, too soon,
        and the bot then waited for an invite while the host had already started
        the next run)."""
        if ctx.dry_run:
            return self._accept_from_popup(ctx, Rel(0.810, 0.595)) is not False
        start = time.time()
        next_note = start + 300
        next_banner = start
        while time.time() - start < INVITE_TIMEOUT:
            frame = ctx.frame()
            if in_gulu(frame):
                ctx.log.info("auto-gulu: already in Gulu")
                return True
            if time.time() >= next_banner:
                next_banner = time.time() + INVITE_POLL
                already_open = invites.popup_open(frame)
                banner = None if already_open else self._find_banner(frame)
                if already_open or banner is not None:
                    result = self._accept_from_popup(ctx, banner)
                    if result is None:   # a stop, or it couldn't get back
                        return False
                    if result:
                        return True
            if time.time() >= next_note:
                next_note += 300
                ctx.log.info("auto-gulu: still waiting for %s's invite (%.0f min)",
                             self.params["friend"], (time.time() - start) / 60)
            if wait(ctx, SKILL_POLL):
                return False
        ctx.log.warning("auto-gulu: no invite from %s in %d minutes -> stopping",
                        self.params["friend"], INVITE_TIMEOUT // 60)
        return False

    @staticmethod
    def _find_banner(frame) -> Rel | None:
        return invites.find_banner(frame)

    def _accept_from_popup(self, ctx: Context, banner: Rel | None,
                           quiet: bool = False) -> bool | None:
        """Accept the friend's Gulu Mine invite (invites.accept). A started run
        (a skill screen) counts as joined: the host may start at once."""
        return invites.accept(
            ctx, self.params["friend"], "gulu", banner, joined=in_gulu,
            started=lambda f: "choose skill" in _words(f, CHOOSE_TITLE),
            prefix="auto-gulu", quiet=quiet)

    # --- joining: play each run to the end ---------------------------------------
    def _join_loop(self, ctx: Context) -> None:
        """User: the joiner always finishes the run. Where the result screen leaves
        it tells whether the host stayed (no setting needed): back on the Gulu
        team screen -> wait for the host's next start; home -> the invitation
        flow (_join skips it when already in Gulu)."""
        runs = self.params["runs"]
        done = 0
        while done < runs and not ctx.should_stop():
            if not self._join(ctx):
                return
            result = self._play_run(ctx)
            if result is None:
                return
            done += 1
            ctx.log.info("auto-gulu: run %d/%d done (%s)", done, runs, result)
            if done < runs and not ctx.dry_run and wait(ctx, 2.0):
                return
        if done >= runs:
            ctx.log.info("auto-gulu: all %d run(s) done", runs)

    def _play_run(self, ctx: Context, hosting: bool = False) -> str | None:
        """Play a run to the end. Joining: from the team screen (or a skill screen
        already up), waiting for the host's start. Hosting (stay): right after a
        Start that took. Every 2s look for a skill screen or the result. Battle 1
        has two 2-pick screens, battles 2-4 two 1-pick screens; all taps at fixed
        positions with the user's waits. Each skill screen is handled on its own
        and the screen is checked again right after (no 2s wait), so nothing is
        tapped once a screen has closed. Ends on the result: OK ->
        "victory"/"defeat". None on a stop, a timeout, or (joining) the team
        going away before a start (logged)."""
        if ctx.dry_run:
            for two in (True, True, False, False):
                if not self._pick_skills(ctx, two_picks=two):
                    return None
            return "dry run"
        started = time.time() if hosting else None
        wait_start = time.time()
        stuck_since = None
        while True:
            frame = ctx.frame()
            result = result_title(frame)
            if result:
                return self._dismiss_result(ctx, frame, result)
            if "choose skill" in _words(frame, CHOOSE_TITLE):
                started = started or time.time()
                picks = _picks(frame)
                # Pick only a FRESH screen (0 picked): re-picking un-picks cards.
                # A screen that stays up with picks after its Select had a tap
                # that didn't take (picking never waits for the teammate - user):
                # finish it once RESELECT_AFTER has passed.
                if picks is not None and picks[0] > 0:
                    stuck_since = stuck_since or time.time()
                    if time.time() - stuck_since >= RESELECT_AFTER:
                        stuck_since = None
                        if not self._finish_screen(ctx, picks):
                            return None
                        continue
                else:
                    stuck_since = None
                if picks is not None and picks[0] == 0:
                    ctx.log.info("auto-gulu: skill screen (%d pick%s)", picks[1],
                                 "s" if picks[1] > 1 else "")
                    # user: the first pick was missed - the cards were still
                    # coming in; let the screen settle first (hosting does the
                    # same, in _host_skill_screen)
                    if wait(ctx, SKILL_SETTLE):
                        return None
                    if not self._pick_skills(ctx, two_picks=picks[1] == 2):
                        return None
                    continue  # check again at once: the next screen may be up
                if wait(ctx, 0.5):  # picked already, or unreadable: look again soon
                    return None
                continue
            if started is None:
                if not in_gulu(frame) and home_state(frame) == HOME:
                    ctx.log.info("auto-gulu: back home before a start (the host left)")
                    return None if self._join(ctx) is False else \
                        self._play_run(ctx)
                if time.time() - wait_start >= START_TIMEOUT:
                    ctx.log.warning("auto-gulu: the host didn't start in %d minutes",
                                    START_TIMEOUT // 60)
                    return None
                # User: invites can come in on the team screen. Sometimes the host
                # can't start (a bug), leaves, and invites from a new room: take
                # that invite. So until the start, loop through: the banner ->
                # open it, accept the friend's invite if there is one -> look for
                # the start again. These checks pace the loop instead of a sleep.
                banner = self._find_banner(frame) if team_level(frame) is not None \
                    else None
                if banner is not None:
                    got = self._accept_from_popup(ctx, banner, quiet=True)
                    if got is None:
                        return None
                    if got:
                        ok = _dialog_ok(ctx.frame())  # "leave this team?", if asked
                        if ok is not None and not self._tap(ctx, ok, "OK (move rooms)"):
                            return None
                        ctx.log.info("auto-gulu: moved to %s's new room",
                                     self.params["friend"])
                        wait_start = time.time()
                    continue
                if wait(ctx, 1.0):  # no banner: nothing to check but the start
                    return None
                continue
            elif time.time() - started >= RUN_TIMEOUT:
                self.flag(ctx, f"a Gulu run didn't end within {RUN_TIMEOUT // 60} "
                               "minutes. Check the game.")
                return None
            if wait(ctx, SKILL_POLL):
                return None

    def _finish_screen(self, ctx: Context, picks: tuple[int, int]) -> bool:
        """A skill screen still up at "k/N" RESELECT_AFTER after its Select: a tap
        didn't take. Short of picks -> the next unpicked card(s) first; then
        Select again, only while the screen is still up (Select sits inside the
        battle's Skills button). False on a stop."""
        picked, wanted = picks
        if picked < wanted:
            ctx.log.info("auto-gulu: the skill screen is stuck at %d/%d -> the next "
                         "card, then Select again", picked, wanted)
            spare = SPARE_TWO if wanted == 2 else SPARE_ONE
            for i, pos in enumerate(spare[:wanted - picked], 1):
                if not self._tap(ctx, Rel(*_rel(pos)), f"skill (spare {i})", 1.0):
                    return False
        else:
            ctx.log.info("auto-gulu: the skill screen is still up at %d/%d -> Select "
                         "didn't take, again", picked, wanted)
        if "choose skill" not in _words(ctx.frame(), CHOOSE_TITLE):
            return True
        if not self._tap(ctx, Rel(*_rel(SELECT_BTN)), "Select Skills (again)",
                         SELECT_WAIT):
            return False
        ctx.hover_rel(Rel(*_rel(SKILL_TOP)))
        return True

    def _pick_skills(self, ctx: Context, two_picks: bool) -> bool:
        """ONE skill screen: the top card(s), Select, then park the cursor on the
        top card. One screen at a time (the caller checks again before the next):
        a run-4 batch of both screens kept tapping after the 2nd screen had
        closed, and its last "Select" (321,833) lands inside the battle's Skills
        button (358,818), opening the Skills panel. The parked cursor keeps a
        stray click off that button too (user)."""
        if two_picks:
            taps = [("skill (top)", SKILL_TOP, 1.0), ("skill (second)", SKILL_SECOND, 1.0)]
        else:
            taps = [("skill (top)", SKILL_ONE, 1.0)]
        for what, pos, after in taps:
            if not self._tap(ctx, Rel(*_rel(pos)), what, after):
                return False
        if not ctx.dry_run:
            picks = _picks(ctx.frame())
            if picks is not None and picks[0] < picks[1]:
                missing = picks[1] - picks[0]
                ctx.log.info("auto-gulu: only %d/%d picked (a tap didn't register) "
                             "-> the next card%s", picks[0], picks[1],
                             "s" if missing > 1 else "")
                spare = SPARE_TWO if two_picks else SPARE_ONE
                for i, pos in enumerate(spare[:missing], 1):
                    if not self._tap(ctx, Rel(*_rel(pos)), f"skill (spare {i})", 1.0):
                        return False
        # Never tap Select unless the skill screen is still up: Select sits inside
        # the battle's Skills button.
        if not ctx.dry_run and "choose skill" not in _words(ctx.frame(), CHOOSE_TITLE):
            ctx.log.info("auto-gulu: the skill screen closed before Select")
            ctx.hover_rel(Rel(*_rel(SKILL_TOP)))
            return True
        if not self._tap(ctx, Rel(*_rel(SELECT_BTN)), "Select Skills", SELECT_WAIT):
            return False
        ctx.hover_rel(Rel(*_rel(SKILL_TOP)))
        return True

    def _dismiss_result(self, ctx: Context, frame, result: str) -> str | None:
        """Close the result screen: its OK button (Victory or Defeat, always at
        RESULT_OK when there is one - user), else a tap above everything (the
        quit-Defeat screen just says "Tap to close"). Retried until it's gone."""
        for _ in range(3):
            if "ok" in _words(frame, RESULT_OK_LABEL).split():
                target, what = Rel(*_rel(RESULT_OK)), f"OK ({result})"
            else:
                target, what = Rel(*_rel(RESULT_DISMISS)), f"dismiss ({result})"
            if not self._tap(ctx, target, what, 2.0):
                return None
            frame = ctx.frame()
            if not result_title(frame):
                return result
        ctx.log.warning("auto-gulu: the %s screen won't close", result)
        return None

    # --- step 6: run, then quit at once ----------------------------------------
    def _run_and_quit(self, ctx: Context) -> bool:
        """Start, pick the top two skills on both skill screens, quit via Skills ->
        home -> OK, dismiss the result, and get home."""
        if not self._tap(ctx, Rel(*_rel(START_BTN)), "Start Challenge", START_WAIT):
            return False
        for n in (1, 2):
            if not self._host_skill_screen(ctx, n):
                return False
        if not ctx.dry_run and not self._battle_on(ctx):
            ctx.log.warning("auto-gulu: the skill screen didn't close")
            return False
        quit_asked = self._ask_quit(ctx)
        if quit_asked is None:
            return False
        if not quit_asked:
            # 2026-10-10: the bot stopped here and left the game mid-battle; play
            # the run out instead (like Stay) and carry on
            ctx.log.warning("auto-gulu: couldn't leave the run -> playing it to the end "
                            "instead")
            result = self._play_run(ctx, hosting=True)
            if result is None:
                return False
            ctx.log.info("auto-gulu: played the run to the end (%s)", result)
            return True
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

    def _ask_quit(self, ctx: Context) -> bool | None:
        """Skills (in battle) -> home, until the "Exiting will immediately settle
        rewards" confirmation shows: True. If it doesn't and the battle's Skills
        button still shows (the panel never opened), again, up to QUIT_TRIES.
        False if it never came; None on a stop."""
        for attempt in range(1, QUIT_TRIES + 1):
            if attempt > 1 and wait(ctx, RETRY_WAIT):
                return None
            for what, pos, after in QUIT_TAPS:
                if not self._tap(ctx, Rel(*_rel(pos)), what, after):
                    return None
            if ctx.dry_run:
                return True
            frame = ctx.frame()
            if "exiting" in _words(frame, TIPS_TEXT):
                return True
            if "skills" not in _words(frame, SKILLS_LABEL):
                ctx.log.warning("auto-gulu: no exit confirmation, and not the battle "
                                "either")
                return False
            ctx.log.info("auto-gulu: no exit confirmation - the Skills panel didn't "
                         "open (try %d/%d)", attempt, QUIT_TRIES)
        return False

    def _host_skill_screen(self, ctx: Context, n: int) -> bool:
        """Wait for skill screen n to come up fresh ("0/2"), let it settle, and
        pick. The previous screen still up with its picks RESELECT_AFTER later
        gets finished (a Select that didn't take). False if screen n doesn't come
        up within HOST_SKILL_TIMEOUT, or on a stop."""
        if ctx.dry_run:
            return self._pick_skills(ctx, two_picks=True)
        end = time.time() + HOST_SKILL_TIMEOUT
        stuck_since = None
        while time.time() < end:
            frame = ctx.frame()
            if "choose skill" in _words(frame, CHOOSE_TITLE):
                picks = _picks(frame)
                if picks is not None and picks[0] > 0:
                    stuck_since = stuck_since or time.time()
                    if time.time() - stuck_since >= RESELECT_AFTER:
                        stuck_since = None
                        if not self._finish_screen(ctx, picks):
                            return False
                        continue
                else:
                    stuck_since = None
                if picks is not None and picks[0] == 0:
                    ctx.log.info("auto-gulu: skill screen %d", n)
                    if wait(ctx, SKILL_SETTLE):
                        return False
                    return self._pick_skills(ctx, two_picks=picks[1] == 2)
            if wait(ctx, 0.5):
                return False
        ctx.log.warning("auto-gulu: skill screen %d didn't come up within %.0fs", n,
                        HOST_SKILL_TIMEOUT)
        return False

    def _battle_on(self, ctx: Context) -> bool:
        """The last skill screen has closed (the battle is on). No settle after it:
        the Skills panel must go in quickly (a missed Skills tap is retried)."""
        end = time.time() + BATTLE_TIMEOUT
        while "choose skill" in _words(ctx.frame(), CHOOSE_TITLE):
            if time.time() >= end or wait(ctx, 0.5):
                return False
        return True

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
                       if same_name(t, friend)), None)
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

    # --- step 7: stay - play each run to the end, start again -------------------
    def _stay_loop(self, ctx: Context) -> None:
        runs = self.params["runs"]
        for n in range(1, runs + 1):
            if ctx.should_stop() or not self._team_ready(ctx):
                break
            ctx.log.info("auto-gulu: run %d/%d (stay)", n, runs)
            result = self._start_when_ready(ctx) and self._play_run(ctx, hosting=True)
            if not result:
                shot = None if ctx.should_stop() else save_snapshot(ctx, "gulu-host-failed")
                ctx.log.warning("auto-gulu: run %d didn't finish cleanly -> stopping%s",
                                n, f"; screen saved: {shot}" if shot else "")
                break
            ctx.log.info("auto-gulu: run %d/%d done (%s)", n, runs, result)
            # the result's OK leads back to the team screen: let it load, so
            # _team_ready sees it (else it would enter Gulu from scratch)
            if n < runs and not ctx.dry_run and not self._until(
                    ctx, lambda: team_level(ctx.frame()) is not None, TEAM_BACK_TIMEOUT):
                ctx.log.warning("auto-gulu: not back on the team screen after the "
                                "result; entering Gulu again")
        else:
            ctx.log.info("auto-gulu: all %d run(s) done", runs)

    def _start_when_ready(self, ctx: Context) -> bool:
        """Tap Start Challenge, again every 5s, until a skill screen shows. Not
        started within STUCK_AFTER: Remove the teammate and invite them again
        (once). A teammate who left is invited again. False on a stop, a failed
        re-invite, or no start even after re-inviting."""
        if ctx.dry_run:
            return self._tap(ctx, Rel(*_rel(START_BTN)), "Start Challenge", START_WAIT)
        since = time.time()
        tries = 0
        reinvited = False
        while not ctx.should_stop():
            frame = ctx.frame()
            if "choose skill" in _words(frame, CHOOSE_TITLE):
                return True
            if team_level(frame) is not None:
                if not partner(frame):
                    ctx.log.info("auto-gulu: the teammate left -> inviting again")
                    if not (self._invite(ctx) and self._wait_join(ctx)):
                        return False
                    since, tries = time.time(), 0
                    continue
                if "start" in _words(frame, START_LABEL):  # never Random Match
                    tries += 1
                    if tries == 1 or tries % 12 == 0:
                        ctx.log.info("auto-gulu: tap Start Challenge%s", "" if tries == 1
                                     else f" (try {tries}; the teammate isn't ready?)")
                    if not tap(ctx, Rel(*_rel(START_BTN)), 0.5):
                        return False
                    end = time.time() + START_RETRY
                    while time.time() < end:  # a start brings the skill screen in ~3s
                        if "choose skill" in _words(ctx.frame(), CHOOSE_TITLE):
                            return True
                        if wait(ctx, 0.5):
                            return False
            if time.time() - since >= STUCK_AFTER:
                if reinvited:
                    ctx.log.warning("auto-gulu: still no start %d minutes after "
                                    "inviting %s again", STUCK_AFTER // 60,
                                    self.params["friend"])
                    return False
                ctx.log.warning("auto-gulu: no start in %d minutes (%d tries) -> remove "
                                "the teammate and invite them again", STUCK_AFTER // 60,
                                tries)
                if not (self._remove_partner(ctx) and self._invite(ctx)
                        and self._wait_join(ctx)):
                    return False
                reinvited = True
                since, tries = time.time(), 0
                continue
            if wait(ctx, 0.5 if tries else START_RETRY):
                return False
        return False

    def _remove_partner(self, ctx: Context) -> bool:
        """Kick the teammate: the red Remove under their name. A confirm dialog,
        if one comes up (not seen yet), gets its OK. True once the slot is free."""
        if "remove" not in _words(ctx.frame(), REMOVE_LABEL):
            ctx.log.warning("auto-gulu: no Remove button under the teammate")
            return False
        if not self._tap(ctx, Rel(*_rel(REMOVE_BTN)), "Remove (the teammate)"):
            return False
        end = time.time() + REMOVE_TIMEOUT
        confirmed = False
        while time.time() < end:
            frame = ctx.frame()
            if team_level(frame) is not None and slot_empty(frame):
                ctx.log.info("auto-gulu: the teammate is removed")
                return True
            ok = None if confirmed else _dialog_ok(frame)
            if ok is not None:
                if not self._tap(ctx, ok, "OK (confirm Remove)"):
                    return False
                confirmed = True
                continue
            if wait(ctx, 0.5):
                return False
        ctx.log.warning("auto-gulu: the teammate is still in after Remove")
        return False

    # --- helpers ------------------------------------------------------------
    def _close_popup(self, ctx: Context, quiet: bool = False) -> bool:
        x = find_sprite(ctx, ctx.frame(), "close_x.png")
        if x is None:
            if not quiet:
                ctx.log.warning("auto-gulu: no X to close the invitation popup")
            return False
        if quiet:
            return tap(ctx, x)
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
