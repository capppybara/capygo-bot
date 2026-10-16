"""Task: hard-mode-autorun.

Repeatedly runs a Hard Mode chapter at a chosen energy multiple.

Per run:
  1. Select the chapter: open the chapter list, click the jump field, type the
     chapter number, click Jump, click the chapter (confirm the green outline),
     then click Select.
  2. Set the energy multiple: click + under Start until the shown multiple
     matches the target (one of 1, 2, 3, 5, 10, 20).
  3. Click Start (confirm the "no teammates" prompt if solo), then play the run
     as joining does (_play_joined, user 2026-10-13): pick the skills, handle the
     events, until the Victory/Defeat screen (tap to dismiss it back to the main
     screen) OR the starting screen already showing (the result screen was
     dismissed by the game or by the user -- count it and go again either way).
  4. On success (or the starting screen returning), run again (chapter + multiple
     are re-applied every run). Stop on a detected failure, when Start won't
     launch (not enough energy), or when `runs` is reached.

Before each run it also checks the Hard Mode switch next to Start: it must show
the RED icon (Hard Mode on). If it's blue, the task stops and tells the user to
put the game in Hard Mode first.

The multiple is set by clicking - down to 1x then + up to the target, and
verified by reading the Start button's energy cost with OCR (cost == multiple x
the 1x base), retrying if a + click was missed.

A Jump does not always scroll the target to the top (e.g. the last chapter), so
the target card is located by OCR of its "<number>." title and clicked there;
the green-outline color test confirms the selection.

Main-screen buttons (Chapter, +, -, Start) are clicked at fixed positions and
Hard Mode is checked by red color, since their templates pick up each chapter's
background tint. The chapter list has a consistent background, so its buttons use
templates.

The run-finished (Victory/Defeat) screen is dismissed by a tap, not a button.

Joining (user, 2026-10-10: "pretty much same as gulu, but there is an extra step
before host starts where you change the multiplier"): accept the friend's Hard
Chapters invite (invites.py), set the energy multiple on the team screen with
+ / - (reading its "Nx Reward" label), wait for the host's start (meanwhile
taking a new invite from them, should they restart in a new room: that run
starts over fresh, not counted), wait for the run to finish, and go again. The multiple drops back to 1x after every run, when the
host changes chapter, and when the invitations popup is closed (user). So while
waiting for the start, the bot reads the multiple every 2s and sets it whenever
it isn't the target (user, 2026-10-11). It used to read the chapter and set the
multiple once the agreed one showed, but that OCR missed now and then; the
Chapter setting is solo-only now. The check stops once the multiple has read
the same for 10 minutes, and starts again after the invitations popup closes
(user: it's there to catch a reset). It never holds up the start and invite
checks: one + / - tap per pass, after those two.
Seen live 2026-10-10: the team screen is solo's layout ("180.Land of Dragon Sleep
XIII" title at y 149, Start "x15", the +/- multiple, plus a Leave button); the
host can start ~2s after the join, too soon to set the multiple (then it's
skipped for that run - user); the result is solo's Victory screen (its template
matches), closed by a tap, then back on the team screen.

Templates in templates/hard-mode-autorun/ (captured from the live game):
  start_button (also used to detect that a run launched), jump_field,
  jump_button, select_button, confirm_ok (solo "start without a team" prompt),
  finish_success, finish_failure
"""

from __future__ import annotations

import time

import cv2

from ..geometry import Rel, RelRect
from ..local import local_default
from ..task import Context, Param, Task, register
from . import invites, skills
from .daily import _crop, save_snapshot

VALID_MULTIPLES = [1, 2, 3, 5, 10, 20]

# Energy cost shown inside the Start button ("x15" .. "x300"), read by OCR to
# verify the multiple (the cost scales linearly with the multiple).
ENERGY_COST_REGION = RelRect(0.412, 0.755, 0.198, 0.040)
# Joining: the "3x Reward" label under Start shows the multiple itself. Setting
# it by the energy cost failed (2026-10-11): after the 6 resetting "-" taps the
# cost wouldn't read, twice, long before the host started. So joining steps + / -
# one tap at a time, reading this label each time; no label = not the team screen.
REWARD_LABEL = RelRect(0.30, 0.810, 0.40, 0.045)
# An event in a joined run ("You run into a demon!", "You find treasure", ...)
# shows a countdown line along the bottom like the skill screens' ("Skill
# selection countdown (15 seconds)": y ~840 on the demon, y 790 on the treasure);
# on all 440 frames of a 2026-10-10 run, a countdown without the "Choose skill"
# title was exactly the demon event's 15 frames.
EVENT_COUNTDOWN = RelRect(0.10, 0.80, 0.80, 0.17)
# In a run: the top shows "Round: N/15" during battles (also under the event
# screens) and "Choose skill" on skill screens - so started mid-run, the bot
# picks up from there (user, 2026-10-10).
RUN_TOP = RelRect(0.25, 0.135, 0.50, 0.045)
# "You find treasure": a chest (animated, shaking - so not matched by picture,
# user) over an "Open" button (321, 727); Open spawns a skill pick.
OPEN_BUTTON = RelRect(0.25, 0.73, 0.50, 0.07)
# The treasure's skill pick isn't a "Choose skill" screen: "Congrats on gaining"
# (y 183) over "Choose a skill from below" (y 243), then 3 cards; the top card's
# name at y ~283, its description from y ~313 (same on all 7 seen, 2026-10-11/12).
# A tap on a card picks it (user). The 1-pick screen's top card (y 385) is the gap
# between cards 1 and 2 here.
TREASURE_TITLE = RelRect(0.15, 0.170, 0.70, 0.100)
TREASURE_TOP = Rel(330 / 642, 300 / 951)           # inside card 1, however long
# "You run into a demon! Make a demonic pact and gain a skill?" (lose max HP):
# Refuse (209,768) / Sign (431,771). User: agree - Sign (was Refuse).
SIGN_BUTTON = RelRect(0.50, 0.78, 0.30, 0.05)
# "You run into an angel! Choose a gift from the angel!": gift cards below that
# line (Super HP, Restore HP, ...). User: always the first one; a tap picks it.
ANGEL_TEXT = RelRect(0.10, 0.33, 0.80, 0.12)      # the title and "Choose a gift" lines
ANGEL_FIRST_DY = 110      # px: the first gift's middle, below the "Choose a gift" line
OPEN_TAPS = 3             # taps per event (Open / Sign / gift) before leaving it to its
                          # countdown
OPEN_PICK_WAIT = 6.0      # Open -> its skill screen shows by then

# Main-screen buttons sit at fixed positions (642x951) and never move; their
# templates would pick up each chapter's background tint, so we click the
# positions and verify by result (OCR cost / green outline) instead of matching.
# Chapter is tapped on its "Chap..." LABEL, left part: the "New Invitation" tab
# can slide over the right half of the button (icon) and never folds away on its
# own; at the label's height the button stays uncovered from x~375 to ~405 px
# (user's call; live-verified with the tab out, 2026-10-04). The old spot
# (0.612, 0.669) sat right on the tab's edge and opened the friends panel.
CHAPTER_BTN = Rel(0.600, 0.689)
START_BTN = Rel(0.463, 0.744)
PLUS_BTN = Rel(0.682, 0.834)
MINUS_BTN = Rel(0.322, 0.834)
# Hard Mode switch next to Start: red = on, blue = off (checked by color).
HARDMODE_REGION = RelRect(0.673, 0.715, 0.065, 0.080)
HARDMODE_RED_MIN = 0.25

# The run-finished (Victory/Defeat) screen is dismissed by a tap on a neutral spot.
FINISH_CONTINUE = Rel(0.5, 0.735)

# A chapter card is located by OCR of its "<number>." title (a Jump doesn't
# always scroll it to the top, e.g. for the last chapter), clicked at its
# thumbnail, and confirmed by the bright-green outline on the card's left edge.
CHAPTER_CARD_X = 0.234       # thumbnail x fraction
CHAPTER_LIST_Y = (90, 810)   # card region in px (excludes the top/bottom bars)
OUTLINE_X = (0.100, 0.122)   # left-edge strip x fractions
OUTLINE_GREEN_MIN = 0.20     # fraction of green pixels in the strip = selected


@register("hard-mode-autorun")
class HardModeAutorun(Task):
    TITLE = "Hard Mode Autorun"
    ICON = "⚔️"
    DESCRIPTION = ("Auto-run a Hard Mode chapter at a chosen energy multiple, "
                   "repeating until the run count, a failure, or low energy.")
    START_HINT = ("Solo: start on the Hard Mode screen (chapter + Start visible) with Hard "
                  "Mode ON - the switch next to Start must be red, not blue. Joining: start "
                  "anywhere; it waits for the host's invite.")

    PARAMS = [
        Param("chapter", "int", local_default("hard_chapter", 1), "Chapter (solo)", min=1, max=9999,
              help="hard mode chapter number to run solo; joining runs the host's "
                   "chapter"),
        Param("energy_multiple", "int", local_default("hard_multiple", 1), "Energy multiple", min=1, max=20,
              choices=VALID_MULTIPLES, suffix="x",
              help="energy multiple to run at (1, 2, 3, 5, 10, or 20)"),
        Param("runs", "int", 10, "Number of runs", min=1, max=9999,
              help="how many runs before stopping"),
        Param("join", "bool", False, "Join a friend's run",
              help="accept the friend's Hard Chapters invite instead of running solo "
                   "(the host picks the chapter; your energy multiple still applies)"),
        Param("friend", "str", local_default("friend"), "Host (joining)",
              help="whose invite to accept (default: friend in config.local.yaml)"),
    ]

    prefix = "hard-mode join"  # log prefix in the run (_play_joined): solo sets its own
    JOIN_POLL = 2.0          # look for the start / the team screen this often
    SKILL_POLL = 2.0         # in the run: look for a skill screen this often
    RUN_TIMEOUT = 15 * 60    # a joined run ends well before this
    RESULT_TAPS = 6          # taps to close the result screen before giving up
    RECOVER_POLL = 5.0       # after a problem: look for the run's end this often
    RECOVER_TIMEOUT = 15 * 60
    MAX_RECOVERIES = 10      # problems in a row (no run in between) before stopping (user)
    INVITE_POLL = 10.0       # and for the friend's invite this often
    INVITE_TIMEOUT = 30 * 60
    START_TIMEOUT = 30 * 60  # waiting for the host to start
    MULTIPLE_WATCH = 10 * 60  # stop checking the multiple once it's read the same
                              # this long (user, 2026-10-11)
    MULTIPLE_TAPS = 3         # taps that don't move the multiple before leaving it

    STEP_WAIT = 0.8       # settle after a menu click

    # --- small helpers ----------------------------------------------------
    def _click(self, ctx: Context, name: str, label: str, reason: str, wait=None) -> bool:
        m = ctx.find(name)
        if not m.found:
            ctx.log.info("could not find %s (score %.2f)", name, m.score)
            return False
        ctx.log.info("click %s - %s", label, reason)
        ctx.click_match(m)
        time.sleep(self.STEP_WAIT if wait is None else wait)
        return True

    def _click_pos(self, ctx: Context, rel: Rel, label: str, reason: str, wait=None) -> None:
        """Click a fixed main-screen position (tint-robust; verified by result)."""
        ctx.log.info("click %s - %s", label, reason)
        ctx.click_rel(rel)
        time.sleep(self.STEP_WAIT if wait is None else wait)

    def _hardmode_on(self, ctx: Context, frame=None) -> bool:
        """True if the switch next to Start is red (Hard Mode on) vs blue (off)."""
        if frame is None:
            frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = HARDMODE_REGION.to_pixels(w, h)
        hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, (0, 90, 90), (12, 255, 255)) | \
            cv2.inRange(hsv, (168, 90, 90), (180, 255, 255))
        return float(red.mean()) / 255 >= HARDMODE_RED_MIN

    def _present(self, ctx: Context, name: str, frame=None) -> bool:
        return ctx.has_template(name) and ctx.find(name, frame=frame).found

    # --- phase 1: chapter -------------------------------------------------
    def _find_chapter_y(self, ctx: Context, target: int, frame):
        """Pixel y of the target chapter's title card (via OCR of "<num>."), or None."""
        import re

        from ..perception import ocr_lines

        lo, hi = CHAPTER_LIST_Y
        for text, _cx, cy in ocr_lines(frame):
            m = re.match(r"^\s*(\d+)[.\s]", text.strip())
            if m and int(m.group(1)) == target and lo <= cy <= hi:
                return cy
        return None

    def _chapter_outlined_at(self, ctx: Context, title_y: int, frame=None) -> bool:
        """True if the card at title_y shows the bright-green selected outline."""
        if frame is None:
            frame = ctx.frame()
        h, w = frame.shape[:2]
        x0, x1 = int(OUTLINE_X[0] * w), int(OUTLINE_X[1] * w)
        y0, y1 = max(0, title_y - 15), min(h, title_y + 95)
        hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
        return float(green.mean()) / 255 >= OUTLINE_GREEN_MIN

    def _open_chapter_list(self, ctx: Context, run_no: int, total: int) -> bool:
        """Open the chapter list, retrying the Chapter click until it opens.

        Right after a run the main screen can still be settling, so a single
        click + fixed wait sometimes misses; poll for the jump field instead.

        The "New Invitation" tab can slide over the right half of the Chapter
        button, so CHAPTER_BTN is on the uncovered left part of its label. Should a
        click still open another panel, confirm we're on the main screen (Start
        visible) before re-clicking, and stop cleanly if not rather than clicking
        the Chapter position on the wrong screen.
        """
        for attempt in range(3):
            if attempt > 0 and not self._present(ctx, "start_button"):
                ctx.log.info("not on the main screen after clicking Chapter (a popup may "
                             "have opened, e.g. the invitation tab) -> stop")
                return False
            self._click_pos(ctx, CHAPTER_BTN, "Chapter", f"run {run_no}/{total}: open list")
            for _ in range(6):
                if self._present(ctx, "jump_field"):
                    return True
                time.sleep(0.5)
        return False

    def _select_chapter(self, ctx: Context, chapter: int, run_no: int, total: int) -> bool:
        if not self._open_chapter_list(ctx, run_no, total):
            ctx.log.info("chapter list did not open -> stop")
            return False
        if not self._click(ctx, "jump_field", "jump field", "focus"):
            return False
        ctx.type_text(chapter)
        time.sleep(0.3)
        if not self._click(ctx, "jump_button", "Jump", f"to chapter {chapter}"):
            return False
        time.sleep(self.STEP_WAIT)
        # Find the target card by OCR (it isn't always scrolled to the top).
        frame = ctx.frame()
        ty = self._find_chapter_y(ctx, chapter, frame)
        if ty is None:
            ctx.log.info("chapter %d not found in the list -> stop", chapter)
            return False
        click = Rel(CHAPTER_CARD_X, min(0.98, (ty + 42) / frame.shape[0]))
        ctx.log.info("click chapter %d (title at y=%d)", chapter, ty)
        ctx.click_rel(click)
        time.sleep(self.STEP_WAIT)
        if not self._chapter_outlined_at(ctx, ty):
            ctx.log.info("chapter not outlined green; clicking again")
            ctx.click_rel(click)
            time.sleep(self.STEP_WAIT)
        if not self._chapter_outlined_at(ctx, ty):
            ctx.log.info("chapter %d not selected (no green outline) -> stop", chapter)
            return False
        return self._click(ctx, "select_button", "Select", f"confirm chapter {chapter}")

    # --- phase 2: multiple (reset to 1x, + up to target, verify cost via OCR) --
    def _read_cost(self, ctx: Context):
        for _ in range(3):  # Vision OCR is occasionally flaky; retry
            c = ctx.read_number(ENERGY_COST_REGION)
            if c is not None:
                return c
            time.sleep(0.3)
        return None

    def _select_multiple(self, ctx: Context, target: int, run_no: int, total: int) -> bool:
        if target not in VALID_MULTIPLES:
            target = min(VALID_MULTIPLES, key=lambda v: abs(v - target))
        target_i = VALID_MULTIPLES.index(target)
        want = None  # target energy cost, once the 1x base is known

        for attempt in range(1, 3):
            # The multiple defaults to 1x on entry, so attempt 1 reads the base
            # there directly (no reset, per the game's behavior). A second attempt
            # resets with '-' (it floors at 1x) in case entry wasn't at 1x.
            if attempt > 1:
                for _ in range(len(VALID_MULTIPLES)):
                    self._click_pos(ctx, MINUS_BTN, "-", "reset to 1x", wait=0.3)
            base = self._read_cost(ctx)  # 1x cost, varies by chapter
            if base is None:
                ctx.log.info("could not read the 1x energy cost (attempt %d)", attempt)
                continue
            want = target * base

            # Closed loop: step toward the target, then read the cost to confirm
            # the real multiple (cost / base) and correct with + / - until it
            # matches. Self-heals a missed click without a full reset.
            cur_i = 0  # entry / post-reset state is 1x
            for _ in range(2 + len(VALID_MULTIPLES)):
                delta = target_i - cur_i
                btn, lbl = (PLUS_BTN, "+") if delta > 0 else (MINUS_BTN, "-")
                for _ in range(abs(delta)):
                    self._click_pos(ctx, btn, lbl, f"toward {target}x", wait=0.3)
                cost = self._read_cost(ctx)
                if cost is None:
                    ctx.log.info("could not read the energy cost while setting the multiple")
                    break
                if cost == want:
                    ctx.log.info("multiple = %dx (energy cost x%d verified)", target, cost)
                    return True
                cur = min(VALID_MULTIPLES, key=lambda v: abs(v - cost / base))
                cur_i = VALID_MULTIPLES.index(cur)
                ctx.log.info("cost x%s reads as %dx (want x%d for %dx); adjusting",
                             cost, cur, want, target)
        ctx.log.warning("could not set the %dx multiple reliably -> stopping", target)
        return False

    # --- phase 3/4: run + wait --------------------------------------------
    def _sleep(self, ctx: Context, seconds: float) -> bool:
        """Sleep in short slices so a stop (Esc / Stop button) is noticed within
        ~0.3s instead of only after the whole wait. Returns True if a stop was
        requested during the wait (the caller should bail out)."""
        end = time.time() + seconds
        while True:
            if ctx.should_stop():
                return True
            remaining = end - time.time()
            if remaining <= 0:
                return False
            time.sleep(min(0.3, remaining))

    def _tap_until_main(self, ctx: Context, timeout: float = 45) -> bool:
        """Tap the results screen(s) back to main, re-tapping until Start returns.

        After a ~minutes-long run the game is usually backgrounded, so the first
        tap only resurfaces the window instead of dismissing anything; there can
        also be more than one result screen (Victory -> rewards -> main) before
        the main screen. So tap, poll for the main screen, and tap again if it
        hasn't come back. Start is checked before each tap, so we never tap on
        the main screen itself.
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            if ctx.should_stop():
                return False
            if self._present(ctx, "start_button"):
                return True
            self._click_pos(ctx, FINISH_CONTINUE, "continue", "dismiss results", wait=2.0)
        return self._present(ctx, "start_button")

    # --- joining a friend's run ---------------------------------------------------
    def _team_screen(self, ctx: Context, frame=None) -> bool:
        """On a Hard Mode screen where the multiple can be set: its energy cost
        ("x15") reads under Start. (Guess for the joiner's team screen: the same
        controls as solo - to be checked live.)"""
        if frame is None:
            frame = ctx.frame()
        return not invites.popup_open(frame) and \
            ctx.read_number(ENERGY_COST_REGION, frame=frame) is not None

    def _snap(self, ctx: Context, label: str) -> None:
        shot = save_snapshot(ctx, label)
        if shot:
            ctx.log.warning("hard-mode join: screen saved: %s", shot)

    def _read_multiple(self, frame) -> int | None:
        """The multiple from the "3x Reward" label under Start, or None (not on the
        team screen, or a misread: not one of VALID_MULTIPLES)."""
        import re

        from ..perception import ocr_lines

        text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, REWARD_LABEL)))
        m = re.search(r"(\d+)\s*[xX×]\s*reward", text, flags=re.I)
        return int(m.group(1)) if m and int(m.group(1)) in VALID_MULTIPLES else None

    def _in_run(self, ctx: Context, frame) -> bool:
        """In a run already: a battle ("Round: N/15"), a skill screen, an event or
        the result."""
        from ..perception import ocr_lines

        top = " ".join(t for t, _, _ in ocr_lines(_crop(frame, RUN_TOP))).lower()
        return "round" in top or "choose skill" in top or self._event_up(frame) or \
            self._present(ctx, "finish_success", frame) or \
            self._present(ctx, "finish_failure", frame)

    def _join(self, ctx: Context) -> str | None:
        """Get into the friend's team: "team" once on the team screen, "run" if
        already in a run (started mid-run: play it from here). Otherwise accept
        their Hard Chapters invite: look for the banner every 10s (and for the
        team screen every 2s), up to 30 minutes. None on a stop or a timeout,
        "problem" if an accept went wrong."""
        friend = self.params["friend"]
        start = time.time()
        next_banner = start
        while time.time() - start < self.INVITE_TIMEOUT:
            if ctx.should_stop():
                return None
            frame = ctx.frame()
            if self._team_screen(ctx, frame):
                ctx.log.info("hard-mode join: on the team screen")
                return "team"
            if self._in_run(ctx, frame):
                ctx.log.info("hard-mode join: already in a run -> playing it from here")
                return "run"
            if time.time() >= next_banner:
                next_banner = time.time() + self.INVITE_POLL
                opened = invites.popup_open(frame)
                banner = None if opened else invites.find_banner(frame)
                if opened or banner is not None:
                    got = invites.accept(ctx, friend, "hard", banner,
                                         joined=lambda f: self._team_screen(ctx, f)
                                         or self._in_run(ctx, f),
                                         prefix="hard-mode join")
                    if got is None:
                        return None if ctx.should_stop() else "problem"
                    if got:
                        return "team"
            if self._sleep(ctx, self.JOIN_POLL):
                return None
        ctx.log.warning("hard-mode join: no invite from %s in %d minutes -> stopping",
                        friend, self.INVITE_TIMEOUT // 60)
        return None

    def _wait_host_start(self, ctx: Context) -> str | None:
        """Until the run starts. "started" as soon as a run screen shows ("Round:
        N/15", a skill screen, an event, a result - user: detect the start and
        proceed); "new room" once a new invite from the friend is accepted (their
        start failed and they made a new room: the caller starts that run over
        fresh, not counted - user); None on a stop or no start in START_TIMEOUT;
        else what went wrong.

        Each pass checks, in order: the run's start, then the multiple (at most
        ONE + / - tap toward the target, then the start again - user, 2026-10-11:
        the multiple must never hold up the start), then, once the multiple needs
        no tap, the invitation banner (user, 2026-10-12: the multiple first). The multiple resets after every run,
        when the host changes chapter, and when the invitations popup closes
        (user), so it's read every JOIN_POLL - until it has read the same for
        MULTIPLE_WATCH, and again after the popup closes. MULTIPLE_TAPS taps that
        don't move it (e.g. too little energy) and it's left there until it
        changes. The chapter isn't read: its OCR missed now and then. Other screens
        (loading, transitions): wait."""
        friend = self.params["friend"]
        target = self.params["energy_multiple"]
        if target not in VALID_MULTIPLES:
            target = min(VALID_MULTIPLES, key=lambda v: abs(v - target))
        start = time.time()
        last = None          # the multiple last read on the team screen
        same_since = start   # ... reading `last` since
        taps = 0             # taps at `last` that didn't move it
        watching = True      # still checking the multiple
        next_banner = 0.0    # open the invitations no more often than INVITE_POLL
        while time.time() - start < self.START_TIMEOUT:
            if ctx.should_stop():
                return None
            frame = ctx.frame()
            if self._in_run(ctx, frame):
                if last != target:  # user: the host can start fast; skip it this time
                    ctx.log.info("hard-mode join: the run started before the multiple "
                                 "was set -> skipped this run")
                ctx.log.info("hard-mode join: the host started the run")
                return "started"
            if not self._team_screen(ctx, frame):
                if self._sleep(ctx, self.JOIN_POLL):
                    return None
                continue
            cur = self._read_multiple(frame) if watching else None
            if cur is not None:
                if cur != last:
                    if cur == target:
                        ctx.log.info("hard-mode join: multiple = %dx", cur)
                    last, same_since, taps = cur, time.time(), 0
                elif time.time() - same_since >= self.MULTIPLE_WATCH:
                    ctx.log.info("hard-mode join: the multiple has read %dx for %d minutes "
                                 "-> no longer checking it", cur, self.MULTIPLE_WATCH // 60)
                    watching = False
                if watching and cur != target:
                    if taps < self.MULTIPLE_TAPS:
                        up = VALID_MULTIPLES.index(cur) < VALID_MULTIPLES.index(target)
                        taps += 1
                        self._click_pos(ctx, PLUS_BTN if up else MINUS_BTN,
                                        "+" if up else "-", f"{cur}x -> {target}x",
                                        wait=0.4)
                        continue  # the start again before the next tap
                    if taps == self.MULTIPLE_TAPS:
                        taps += 1  # logged once
                        ctx.log.info("hard-mode join: the multiple won't move from %dx "
                                     "-> leaving it until it changes", cur)
            # The invitations: once the multiple needs no tap (user, 2026-10-12: set
            # it first), and at most every INVITE_POLL (it ran non-stop: another
            # mode's invites kept the banner up).
            banner = invites.find_banner(frame) if time.time() >= next_banner else None
            if banner is not None:
                next_banner = time.time() + self.INVITE_POLL
                got = invites.accept(
                    ctx, friend, "hard", banner, joined=lambda f: self._team_screen(ctx, f),
                    started=lambda f: self._in_run(ctx, f),
                    prefix="hard-mode join", quiet=True)
                if got is None:
                    return None if ctx.should_stop() else "a new invite couldn't be accepted"
                if got:
                    ctx.log.info("hard-mode join: moved to %s's new room -> starting this "
                                 "run fresh", friend)
                    return "new room"
                # closing the invitations resets the multiple (user): check it again
                watching, same_since, taps = True, time.time(), 0
                continue
            if self._sleep(ctx, self.JOIN_POLL):
                return None
        ctx.log.warning("hard-mode join: the host didn't start in %d minutes",
                        self.START_TIMEOUT // 60)
        return None

    def _play_joined(self, ctx: Context) -> str:
        """The run, from the start to its result. Skill screens are picked as they
        come, one at a time, with the shared skills.py (user, 2026-10-10: 2 picks x
        5 screens, then 1 pick x 1, then 1 pick x 2 - same layouts as Gulu's; after
        the 3rd battle a skill pick, then a random event). The events ("You run
        into a demon!": Refuse / Sign, ...) are left to their countdown for now.
        Any order works: each screen is handled as it shows. Back on a team screen
        with none of that seen is "no run": not a run at all (e.g. the host kicked
        us - we land in our own room - and will re-invite: user), not counted. "success" / "failure" (the result screen is up),
        "restart" (already back on the team screen), "timeout" or "stopped"."""
        start = time.time()
        stuck_since = None
        in_event = False
        open_taps = 0
        played = False   # a skill screen or an event was seen (a result alone isn't:
        self.played = False  # started on a Victory screen, none of it was played)
        while time.time() - start < self.RUN_TIMEOUT:
            if ctx.should_stop():
                return "stopped"
            frame = ctx.frame()
            if self._event_up(frame):
                played = self.played = True
                sign = self._label_at(frame, SIGN_BUTTON, "sign")
                if sign is not None and open_taps < OPEN_TAPS:
                    if open_taps == 0:  # its skill is an offering too (user)
                        skills.save_screen(ctx, frame, "hard")
                    open_taps += 1  # the demon's pact (user: agree)
                    self._click_pos(ctx, sign, "Sign", "the demon's pact", wait=1.0)
                    in_event = True
                    continue
                gift = self._angel_gift(frame)
                if gift is not None and open_taps < OPEN_TAPS:
                    if open_taps == 0:  # its gifts are skills too (user)
                        skills.save_screen(ctx, frame, "hard")
                    open_taps += 1  # the angel (user: always the first gift)
                    self._click_pos(ctx, gift, "the first gift", "the angel", wait=1.0)
                    in_event = True
                    continue
                button = self._label_at(frame, OPEN_BUTTON, "open")
                if button is not None and open_taps < OPEN_TAPS:
                    # "You find treasure": Open spawns a skill pick -> run the
                    # single-pick steps on it right away (user)
                    open_taps += 1
                    self._click_pos(ctx, button, "Open", "the treasure chest", wait=0.5)
                    in_event = True
                    if not self._pick_after_open(ctx):
                        return "stopped"
                    continue
                if not in_event:  # once per event: its screen, for building handlers
                    shot = save_snapshot(ctx, "hard-event")
                    ctx.log.info("%s: an event (left to its countdown)%s", self.prefix,
                                 f"; screen saved: {shot}" if shot else "")
                in_event = True
                if self._sleep(ctx, self.SKILL_POLL):
                    return "stopped"
                continue
            in_event = False
            open_taps = 0
            if self._present(ctx, "finish_failure", frame):
                return "failure"
            if self._present(ctx, "finish_success", frame):
                return "success"
            if self._present(ctx, "start_button", frame):
                return "restart" if played else "no run"
            if skills.on_skill_screen(frame):
                played = self.played = True
                got = skills.picks(frame)
                if got is not None and got[0] > 0:  # picked, still up: a tap didn't take?
                    stuck_since = stuck_since or time.time()
                    if time.time() - stuck_since >= skills.RESELECT_AFTER:
                        stuck_since = None
                        if not skills.finish_screen(ctx, got, self.prefix):
                            return "stopped"
                        continue
                else:
                    stuck_since = None
                if got is not None and got[0] == 0:
                    ctx.log.info("%s: skill screen (%d pick%s)", self.prefix, got[1],
                                 "s" if got[1] > 1 else "")
                    if self._sleep(ctx, skills.SKILL_SETTLE):
                        return "stopped"
                    if not skills.pick_screen(ctx, got[1] == 2, self.prefix, mode="hard"):
                        return "stopped"
                    continue  # look again at once: the next screen may be up
                if self._sleep(ctx, 0.5):
                    return "stopped"
                continue
            if self._sleep(ctx, self.SKILL_POLL):
                return "stopped"
        return "timeout"

    def _pick_after_open(self, ctx: Context) -> bool:
        """After the treasure's Open: wait for its skill screen ("Congrats on
        gaining" / "Choose a skill from below", TREASURE_TITLE) and tap the top card
        once - tapping a skill there picks it and moves on, no Select (user). It
        used to wait for a "Choose skill" title, which this screen doesn't have, so
        it never picked (2026-10-12). If no skill screen shows in OPEN_PICK_WAIT
        its screen is saved (the run loop / the countdown take it from there).
        False only on a stop."""
        end = time.time() + OPEN_PICK_WAIT
        while time.time() < end:
            if ctx.should_stop():
                return False
            if self._treasure_pick_up(ctx.frame()):
                if self._sleep(ctx, skills.SKILL_SETTLE):
                    return False
                skills.save_screen(ctx, ctx.frame(), "hard")
                self._click_pos(ctx, TREASURE_TOP, "skill (top)", "the treasure's skill",
                                wait=1.0)
                ctx.hover_rel(Rel(skills.SKILL_TOP[0] / 642, skills.SKILL_TOP[1] / 951))
                return True
            if self._sleep(ctx, 0.5):
                return False
        self._snap(ctx, "hard-treasure-pick")
        ctx.log.info("%s: no skill screen after Open", self.prefix)
        return True

    @staticmethod
    def _treasure_pick_up(frame) -> bool:
        """The treasure's skill pick is showing."""
        from ..perception import ocr_lines

        text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, TREASURE_TITLE))).lower()
        return "congrats" in text or "choose a skill" in text

    @staticmethod
    def _angel_gift(frame) -> Rel | None:
        """The angel event's first gift card (below its "Choose a gift" line), or
        None if this isn't the angel."""
        from ..perception import ocr_lines

        h, w = frame.shape[:2]
        _, y0, _, _ = ANGEL_TEXT.to_pixels(w, h)
        for text, _, cy in ocr_lines(_crop(frame, ANGEL_TEXT)):
            if "gift" in text.lower():
                return Rel(0.5, (y0 + cy + ANGEL_FIRST_DY * h / 951) / h)
        return None

    @staticmethod
    def _label_at(frame, region: RelRect, label: str) -> Rel | None:
        """An event button reading exactly `label` ("open", "sign") in `region`,
        or None."""
        from ..perception import ocr_lines

        h, w = frame.shape[:2]
        x0, y0, _, _ = region.to_pixels(w, h)
        for text, cx, cy in ocr_lines(_crop(frame, region)):
            if text.strip().lower() == label:
                return Rel((x0 + cx) / w, (y0 + cy) / h)
        return None

    @staticmethod
    def _event_up(frame) -> bool:
        """A run event is up: a countdown along the bottom, but not a skill screen."""
        from ..perception import ocr_lines

        text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, EVENT_COUNTDOWN))).lower()
        return "countdown" in text and not skills.on_skill_screen(frame)

    def _dismiss_result(self, ctx: Context) -> bool:
        """Close the Victory / Defeat screen with taps, only while it shows (the
        host may have left: a tap at that spot on the home screen would hit
        Start). True once it's gone."""
        for _ in range(self.RESULT_TAPS):
            frame = ctx.frame()
            if not (self._present(ctx, "finish_success", frame)
                    or self._present(ctx, "finish_failure", frame)):
                return True
            self._click_pos(ctx, FINISH_CONTINUE, "continue", "dismiss the result",
                            wait=2.0)
            if ctx.should_stop():
                return False
        ctx.log.warning("hard-mode join: the result screen won't close")
        return False

    def _join_loop(self, ctx: Context) -> None:
        """Run after run. Something going wrong doesn't end the task (user,
        2026-10-11: "add some durability"): it's logged with a screenshot, the bot
        waits for the run to end (_recover) and starts the loop over. A stop ends
        it at once; MAX_RECOVERIES problems in a row with no run in between end it
        too (something is really broken)."""
        if not self.params["friend"].strip():
            ctx.log.warning("hard-mode join: no Host set -> enter their in-game name, "
                            "or set defaults: friend: in config.local.yaml")
            return
        multiple = self.params["energy_multiple"]
        total = self.params["runs"]
        ctx.log.info("hard-mode join: %s's runs at %dx, %d run(s)",
                     self.params["friend"], multiple, total)
        done = problems = 0
        while done < total and not ctx.should_stop():
            try:
                outcome = self._one_run(ctx, done + 1, total)
            except Exception as e:  # noqa: BLE001 - a bug mustn't end the task either
                ctx.log.exception("hard-mode join: error")
                outcome = f"an error ({e})"
            if outcome == "stop" or ctx.should_stop():
                break
            if outcome == "done":
                done += 1
                problems = 0
            elif outcome != "again":  # a problem: say what, wait for the end, go again
                problems += 1
                if problems > self.MAX_RECOVERIES:
                    ctx.log.warning("hard-mode join: %d problems in a row -> stopping",
                                    problems)
                    break
                if not self._recover(ctx, outcome):
                    break
        ctx.log.info("hard-mode join done: %d/%d runs", done, total)

    def _one_run(self, ctx: Context, run_no: int, total: int) -> str:
        """One pass: join, wait for the start, play, close the result. "done" (a
        run played), "again" (nothing to count - go round), "stop" (a stop, or no
        invite / no start in 30 minutes), or what went wrong."""
        where = self._join(ctx)
        if where is None:
            return "stop"  # a stop, or no invite in 30 minutes
        if where == "problem":
            return "the invite couldn't be accepted"
        if where == "team":
            started = self._wait_host_start(ctx)
            if started == "new room":
                return "again"  # fresh, as a new run; nothing counted (user)
            if started != "started":
                return started or "stop"  # None: a stop / no start in 30 min
        result = self._play_joined(ctx)
        if result == "stopped":
            return "stop"
        if result == "no run":
            ctx.log.info("hard-mode join: back on a team screen with no run played "
                         "(kicked? the host can re-invite) -> waiting again")
            return "again"
        if result == "timeout":
            return f"no result within {self.RUN_TIMEOUT // 60} minutes"
        if result in ("success", "failure") and not self.played:
            # a result screen the bot didn't play (started on it): close it
            ctx.log.info("hard-mode join: a result from before the start -> closing it, "
                         "not counted")
            return "again" if self._dismiss_result(ctx) else "the result won't close"
        ctx.log.info("hard-mode join: run %d/%d result: %s", run_no, total, result)
        if result in ("success", "failure") and not self._dismiss_result(ctx):
            return "the result won't close"
        return "done"

    def _recover(self, ctx: Context, why: str) -> bool:
        """After a problem: wait (checking every 5s, up to RECOVER_TIMEOUT) for the
        run to end - a Victory / Defeat screen (closed), or back on a team screen or
        home - so the loop can start over. False on a stop or if nothing turns up."""
        self._snap(ctx, "hard-join-problem")
        ctx.log.warning("hard-mode join: %s -> waiting for the run to end, then starting "
                        "over", why)
        from .daily import HOME, home_state

        end = time.time() + self.RECOVER_TIMEOUT
        while time.time() < end:
            if self._sleep(ctx, self.RECOVER_POLL):
                return False
            frame = ctx.frame()
            if self._present(ctx, "finish_success", frame) or \
                    self._present(ctx, "finish_failure", frame):
                ctx.log.info("hard-mode join: the run ended -> closing its result")
                if self._dismiss_result(ctx):
                    return True
                continue
            if self._team_screen(ctx, frame) or home_state(frame) == HOME:
                ctx.log.info("hard-mode join: back on a team / home screen -> starting over")
                return True
        ctx.log.warning("hard-mode join: nothing turned up in %d minutes -> stopping",
                        self.RECOVER_TIMEOUT // 60)
        return False

    # --- main loop --------------------------------------------------------
    def run(self, ctx: Context) -> None:
        if self.params.get("join"):
            self._join_loop(ctx)
            return
        self.prefix = "hard-mode"
        chapter = self.params["chapter"]
        multiple = self.params["energy_multiple"]
        total = self.params["runs"]
        ctx.log.info("hard-mode-autorun: chapter=%d multiple=%dx runs=%d",
                     chapter, multiple, total)

        runs_done = 0
        while runs_done < total and not ctx.should_stop():
            run_no = runs_done + 1
            # Hard Mode must be ON: the switch by Start shows the red icon.
            if not self._hardmode_on(ctx):
                ctx.log.warning("Hard Mode is OFF (the switch next to Start is blue). "
                                "Put the game in Hard Mode first, then start again.")
                break
            if not self._select_chapter(ctx, chapter, run_no, total):
                break
            if ctx.should_stop():
                break
            if not self._select_multiple(ctx, multiple, run_no, total):
                break
            if ctx.should_stop():
                break
            self._click_pos(ctx, START_BTN, "Start", f"run {run_no}/{total}")
            # Solo runs prompt "start the battle without teammates?" -> OK.
            for _ in range(4):
                if self._sleep(ctx, 0.7):
                    break
                if self._present(ctx, "confirm_ok"):
                    self._click(ctx, "confirm_ok", "OK", "confirm start without a team")
                    break
            if ctx.should_stop():
                break
            # If the run didn't launch (Start still on screen), it's out of energy.
            self._sleep(ctx, 1.5)
            if ctx.should_stop():
                break
            if self._present(ctx, "start_button"):
                ctx.log.warning("run did not start (not enough energy) -> stopping")
                break

            # The run itself as joining plays it (user, 2026-10-13): pick the skills,
            # handle the events, until the result. Solo's own end and stop-on-a-loss
            # stay. "no run" (Start back with no skill screen seen) still means the
            # run ended: it launched (checked above).
            result = self._play_joined(ctx)
            if result == "no run":
                result = "restart"
            ctx.log.info("run %d/%d result: %s", run_no, total, result)
            if result == "success":
                if not self._tap_until_main(ctx):
                    ctx.log.warning("could not get back to the main screen after the run "
                                    "-> stopping")
                    break
                time.sleep(1.5)  # let the main screen settle before the next run
                runs_done += 1
                continue
            if result == "restart":
                # Already back on the starting screen -> the run is done; go again.
                time.sleep(1.5)  # let the main screen settle before the next run
                runs_done += 1
                continue
            if result == "failure":
                ctx.log.info("run failed -> stopping")
            else:
                ctx.log.info("finish not detected (%s) -> stopping", result)
            break

        ctx.log.info("hard-mode-autorun done: %d/%d runs completed", runs_done, total)
