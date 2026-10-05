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
     Then back to step 2, until the number of runs is done. The skill screens
     always look the same, so it's all fixed positions with the user's waits
     (the Skills panel does NOT pause the run: be quick, or the next day's
     skill picker comes up).
  7. Stay on: NOT BUILT YET (the Victory/Defeat end of a full run hasn't been
     captured).

Joining (user, 2026-10-05):
  Already on a Gulu team screen -> carry on. Otherwise, every 10s for up to 30
  minutes: find the "New Invitation" banner (right edge) -> open it ("Team
  Invitation") -> make sure the mode selector (top-left) says Gulu Mine, else
  open it and pick the top option (Gulu Mine is always first) -> find the
  friend's invite -> tap its ✓. No banner / no invite from the friend: close it,
  wait 10s, look again. Never the ✗, "Reject all", or the "No longer show
  invitation messages" box.
  Then the run, always played to the end: every 5s look for a skill screen or
  the result. Battle 1 has two screens of 2 picks (the hosting positions and
  waits); battles 2-4 have two screens of 1 pick (the top of 3 cards). The
  result: Victory has an OK button; Defeat closes with a tap. Where that leaves
  you says whether the host stayed: the Gulu team screen -> wait (5s checks) for
  the host's next start, which brings battle 1's 2x2 picks again; home -> the
  invitation flow. Repeat until the number of runs is done.
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

# Joining: the invitation banner and popup
BANNER_BAND = (420, 642, 450, 700)                 # px x0, x1, y0, y1: "New Invitation"
BANNER_DY = 13                                     # tap a bit below its label
INVITES_TITLE = RelRect(0.28, 0.179, 0.42, 0.042)  # "Team Invitation"
MODE_LABEL = RelRect(0.218, 0.240, 0.25, 0.032)    # the selector: "Gulu Mine"
MODE_SELECTOR = (220, 240)
MODE_TOP_OPTION = (220, 277)                       # drop-down: Gulu Mine is always first
INVITE_NAMES = (180, 380, 260, 640)                # px x0, x1, y0, y1: host names
ACCEPT_X, ACCEPT_DY = 476, 21                      # a card's ✓: host name y + 21
# Joining: the run
SKILL_ONE = (320, 385)                             # 1-pick screens: the top of 3 cards
PICK_COUNT = RelRect(0.31, 0.845, 0.38, 0.060)     # "0/2 Select Skills" / "0/1 ..."
RESULT_TITLE = RelRect(0.25, 0.385, 0.50, 0.065)   # "Victory" / "Defeat"
RESULT_OK = (320, 812)                             # Victory screen's OK
RESULT_OK_LABEL = RelRect(0.35, 0.830, 0.30, 0.050)
SKILL_POLL = 5.0          # user: look for the skill screen every 5 seconds
START_TIMEOUT = 30 * 60   # waiting for the host to start
RUN_TIMEOUT = 15 * 60     # a run that has started should end well before this
INVITE_POLL = 10.0        # user: look again every 10 seconds
INVITE_TIMEOUT = 30 * 60  # user: give up after 30 minutes

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


def in_gulu(frame) -> bool:
    """On a Gulu team screen, or a Gulu skill screen (the host already started)."""
    return team_level(frame) is not None or "choose skill" in _words(frame, CHOOSE_TITLE)


def result_title(frame) -> str:
    """ "victory" / "defeat" while a run's result screen is up, else ""."""
    text = _words(frame, RESULT_TITLE)
    return next((r for r in ("victory", "defeat") if r in text), "")


def _picks(frame) -> int:
    """How many skills this screen wants (2 on battle 1's screens, else 1)."""
    m = re.search(r"/\s*(\d)", _words(frame, PICK_COUNT))
    return int(m.group(1)) if m else 1


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

    # --- joining: find and accept the friend's invite ----------------------------
    def _join(self, ctx: Context) -> bool:
        """Accept the friend's Gulu invite: look every 10s, up to 30 minutes."""
        if ctx.dry_run:
            return self._accept_from_popup(ctx, Rel(0.810, 0.595)) is not False
        if in_gulu(ctx.frame()):
            ctx.log.info("auto-gulu: already in Gulu")
            return True
        start = time.time()
        next_note = start + 300
        while time.time() - start < INVITE_TIMEOUT:
            frame = ctx.frame()
            already_open = "invitation" in _words(frame, INVITES_TITLE)
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
            if wait(ctx, INVITE_POLL):
                return False
        ctx.log.warning("auto-gulu: no invite from %s in %d minutes -> stopping",
                        self.params["friend"], INVITE_TIMEOUT // 60)
        return False

    @staticmethod
    def _find_banner(frame) -> Rel | None:
        """Where to tap the "New Invitation" banner, if it's showing."""
        h, w = frame.shape[:2]
        kx, ky = w / 642, h / 951
        x0, x1, y0, y1 = BANNER_BAND
        crop = frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]
        for t, cx, cy in ocr_lines(crop):
            if "invitation" in t.lower():
                return Rel((cx / kx + x0) / 642, (cy / ky + y0 + BANNER_DY) / 951)
        return None

    def _accept_from_popup(self, ctx: Context, banner: Rel | None) -> bool | None:
        """Open the invitations (banner None = already open), make sure they're
        Gulu Mine's, and accept the friend's. True = joined; False = no invite
        from them (popup closed); None = a stop or a problem (logged)."""
        friend = self.params["friend"]
        if banner is not None and not self._tap(ctx, banner, "New Invitation"):
            return None
        if ctx.dry_run:
            return True
        if not self._until(ctx, lambda: "invitation" in _words(ctx.frame(), INVITES_TITLE)):
            ctx.log.warning("auto-gulu: the Team Invitation popup didn't open")
            return None
        if "gulu" not in _words(ctx.frame(), MODE_LABEL):
            if not (self._tap(ctx, Rel(*_rel(MODE_SELECTOR)), "mode selector")
                    and self._tap(ctx, Rel(*_rel(MODE_TOP_OPTION)), "Gulu Mine (top)")):
                return None
            if "gulu" not in _words(ctx.frame(), MODE_LABEL):
                ctx.log.warning("auto-gulu: couldn't switch the invitations to Gulu "
                                "Mine")
                return None if not self._close_popup(ctx) else False
        frame = ctx.frame()
        h, w = frame.shape[:2]
        kx, ky = w / 642, h / 951
        x0, x1, y0, y1 = INVITE_NAMES
        crop = frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]
        name_y = next((cy / ky + y0 for t, _, cy in ocr_lines(crop)
                       if _same_name(t, friend)), None)
        if name_y is None:
            ctx.log.info("auto-gulu: no Gulu invite from %s yet", friend)
            return False if self._close_popup(ctx) else None
        if not self._tap(ctx, Rel(ACCEPT_X / 642, (name_y + ACCEPT_DY) / 951),
                         f"accept {friend}'s invite (✓)"):
            return None
        # the host may start at once, so the skill screen counts as joined too
        if not self._until(ctx, lambda: in_gulu(ctx.frame())):
            ctx.log.warning("auto-gulu: accepted, but no Gulu team screen")
            return None
        ctx.log.info("auto-gulu: joined %s's team", friend)
        return True

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
            result = self._play_joined_run(ctx)
            if result is None:
                return
            done += 1
            ctx.log.info("auto-gulu: run %d/%d done (%s)", done, runs, result)
            if done < runs and not ctx.dry_run and wait(ctx, 2.0):
                return
        if done >= runs:
            ctx.log.info("auto-gulu: all %d run(s) done", runs)

    def _play_joined_run(self, ctx: Context) -> str | None:
        """From the team screen (or a skill screen already up): every 5s look for
        a skill screen or the result. Battle 1 has two 2-pick screens, battles 2-4
        two 1-pick screens; all taps at fixed positions with the user's waits.
        Ends on the result: OK -> "victory"/"defeat". None on a stop, a timeout,
        or the team going away before a start (logged)."""
        if ctx.dry_run:
            for _ in range(2):
                for what, pos, after in RUN_TAPS[:6]:
                    if not self._tap(ctx, Rel(*_rel(pos)), what, after):
                        return None
            return "dry run"
        started = None
        wait_start = time.time()
        while True:
            frame = ctx.frame()
            result = result_title(frame)
            if result:
                return self._dismiss_result(ctx, frame, result)
            if "choose skill" in _words(frame, CHOOSE_TITLE):
                started = started or time.time()
                if not self._pick_skills(ctx, two_picks=_picks(frame) == 2):
                    return None
                continue
            if started is None:
                if not in_gulu(frame) and home_state(frame) == HOME:
                    ctx.log.info("auto-gulu: back home before a start (the host left)")
                    return None if self._join(ctx) is False else \
                        self._play_joined_run(ctx)
                if time.time() - wait_start >= START_TIMEOUT:
                    ctx.log.warning("auto-gulu: the host didn't start in %d minutes",
                                    START_TIMEOUT // 60)
                    return None
            elif time.time() - started >= RUN_TIMEOUT:
                self.flag(ctx, f"a joined run didn't end within {RUN_TIMEOUT // 60} "
                               "minutes. Check the game.")
                return None
            if wait(ctx, SKILL_POLL):
                return None

    def _pick_skills(self, ctx: Context, two_picks: bool) -> bool:
        """Both skill screens of one battle, top cards, user's waits."""
        if two_picks:
            ctx.log.info("auto-gulu: skill screen: 2 picks x 2")
            taps = RUN_TAPS[:6]
        else:
            ctx.log.info("auto-gulu: skill screen: 1 pick x 2")
            taps = [("skill", SKILL_ONE, 1.0), ("Select Skills", SELECT_BTN, 3.0)] * 2
        for what, pos, after in taps:
            if not self._tap(ctx, Rel(*_rel(pos)), what, after):
                return False
        return True

    def _dismiss_result(self, ctx: Context, frame, result: str) -> str | None:
        """Victory shows an OK button; the Defeat screen closes with a tap above."""
        if "ok" in _words(frame, RESULT_OK_LABEL).split():
            ok = self._tap(ctx, Rel(*_rel(RESULT_OK)), f"OK ({result})", 2.0)
        else:
            ok = self._tap(ctx, Rel(*_rel(RESULT_DISMISS)), f"dismiss ({result})", 2.0)
        return result if ok else None

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
