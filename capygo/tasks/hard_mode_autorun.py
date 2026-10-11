"""Task: hard-mode-autorun.

Repeatedly runs a Hard Mode chapter at a chosen energy multiple.

Per run:
  1. Select the chapter: open the chapter list, click the jump field, type the
     chapter number, click Jump, click the chapter (confirm the green outline),
     then click Select.
  2. Set the energy multiple: click + under Start until the shown multiple
     matches the target (one of 1, 2, 3, 5, 10, 20).
  3. Click Start (confirm the "no teammates" prompt if solo), then poll for the
     run to finish: the Victory/Defeat screen (tap to dismiss it back to the main
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
Chapters invite (invites.py), set the energy multiple on the team screen (the
same + / - and cost check as solo), wait for the host's start (meanwhile taking
a new invite from them, should they restart in a new room), wait for the run to
finish, and go again. The multiple belongs to the host's chapter (user): set it
once they've picked, and again whenever they change chapter; it also drops back
to 1x after every run. So the bot remembers the energy cost it set, sets the
multiple again (from 1x) before each run when the cost isn't that, and, while
waiting for the start, does the same if the cost changes (a new chapter). The joiner's screens hadn't been seen when this was
written: it logs every step and stops (with a screenshot) on anything unexpected.

Templates in templates/hard-mode-autorun/ (captured from the live game):
  start_button (also used to detect that a run launched), jump_field,
  jump_button, select_button, confirm_ok (solo "start without a team" prompt),
  finish_success, finish_failure
"""

from __future__ import annotations

import time

import cv2

from ..geometry import Rel, RelRect
from ..task import Context, Param, Task, register
from . import invites
from .daily import save_snapshot

VALID_MULTIPLES = [1, 2, 3, 5, 10, 20]

# Energy cost shown inside the Start button ("x15" .. "x300"), read by OCR to
# verify the multiple (the cost scales linearly with the multiple).
ENERGY_COST_REGION = RelRect(0.412, 0.755, 0.198, 0.040)

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
                  "anywhere; it waits for the friend's invite.")

    PARAMS = [
        Param("chapter", "int", 180, "Chapter", min=1, max=9999,
              help="hard mode chapter number to run"),
        Param("energy_multiple", "int", 20, "Energy multiple", min=1, max=20,
              choices=VALID_MULTIPLES, suffix="x",
              help="energy multiple to run at (1, 2, 3, 5, 10, or 20)"),
        Param("runs", "int", 10, "Number of runs", min=1, max=9999,
              help="how many runs before stopping"),
        Param("join", "bool", False, "Join a friend's run",
              help="accept the friend's Hard Chapters invite instead of running solo "
                   "(the host picks the chapter; your energy multiple still applies)"),
        Param("friend", "str", "pinkdolly", "Friend (joining)",
              help="whose invite to accept"),
    ]

    JOIN_POLL = 2.0          # look for the start / the team screen this often
    COST_CHANGED_READS = 2   # the cost read differently this many times in a row:
                             # the host changed chapter -> set the multiple again
    INVITE_POLL = 10.0       # and for the friend's invite this often
    INVITE_TIMEOUT = 30 * 60
    START_TIMEOUT = 30 * 60  # waiting for the host to start

    STEP_WAIT = 0.8       # settle after a menu click
    FINISH_POLL = 30.0    # seconds between finish-screen checks
    FINISH_TIMEOUT = 600  # give up waiting for a finish after this many seconds

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

    def _select_multiple(self, ctx: Context, target: int, run_no: int, total: int,
                         reset: bool = False) -> bool:
        if target not in VALID_MULTIPLES:
            target = min(VALID_MULTIPLES, key=lambda v: abs(v - target))
        target_i = VALID_MULTIPLES.index(target)
        want = None  # target energy cost, once the 1x base is known

        for attempt in range(1, 3):
            # The multiple defaults to 1x on entry, so attempt 1 reads the base
            # there directly (no reset, per the game's behavior). A second attempt
            # resets with '-' (it floors at 1x) in case entry wasn't at 1x; so does
            # every attempt with `reset` (a joiner's screen may hold any multiple).
            if attempt > 1 or reset:
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

    def _wait_for_finish(self, ctx: Context) -> str:
        t0 = time.time()
        while time.time() - t0 < self.FINISH_TIMEOUT:
            if self._sleep(ctx, self.FINISH_POLL):  # interruptible poll interval
                return "stopped"
            frame = ctx.frame()
            # Already back on the starting screen (Start button showing): the run
            # ended and the result screen was dismissed for us -- by the game, or
            # by the user tapping it. Count it and move on, win or lose, instead
            # of waiting out the timeout for a Victory/Defeat screen that's gone.
            if self._present(ctx, "start_button", frame):
                return "restart"
            if self._present(ctx, "finish_failure", frame):
                return "failure"
            if self._present(ctx, "finish_success", frame):
                return "success"
        return "timeout"

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

    def _ensure_multiple(self, ctx: Context, run_no: int, total: int) -> bool:
        """Set the multiple, unless the screen already shows the cost it was set to
        (only at 1x: the multiple drops back to 1x after every run - user). Always
        from 1x: the screen may hold any multiple. Remembers the cost it set."""
        cost = self._read_cost(ctx)
        if self.set_cost is not None and cost == self.set_cost:
            ctx.log.info("hard-mode join: the multiple is still set (cost x%d)", cost)
            return True
        if not self._select_multiple(ctx, self.params["energy_multiple"], run_no, total,
                                     reset=True):
            return False
        self.set_cost = self._read_cost(ctx)
        return True

    def _join(self, ctx: Context) -> bool:
        """Accept the friend's Hard Chapters invite: look for the banner every 10s
        (and for the team screen every 2s, in case we're already in), up to 30
        minutes."""
        friend = self.params["friend"]
        start = time.time()
        next_banner = start
        while time.time() - start < self.INVITE_TIMEOUT:
            if ctx.should_stop():
                return False
            frame = ctx.frame()
            if self._team_screen(ctx, frame):
                ctx.log.info("hard-mode join: on the team screen")
                return True
            if time.time() >= next_banner:
                next_banner = time.time() + self.INVITE_POLL
                opened = invites.popup_open(frame)
                banner = None if opened else invites.find_banner(frame)
                if opened or banner is not None:
                    got = invites.accept(ctx, friend, "hard", banner,
                                         joined=lambda f: self._team_screen(ctx, f),
                                         prefix="hard-mode join")
                    if got is None:
                        self._snap(ctx, "hard-join-accept")
                        return False
                    if got:
                        return True
            if self._sleep(ctx, self.JOIN_POLL):
                return False
        ctx.log.warning("hard-mode join: no invite from %s in %d minutes -> stopping",
                        friend, self.INVITE_TIMEOUT // 60)
        return False

    def _wait_host_start(self, ctx: Context) -> bool:
        """Until the team screen goes away (the host started): every round, look
        for a new invite from the friend (a new room, if their start failed) and
        take it. True once the run has started."""
        friend = self.params["friend"]
        start = time.time()
        gone = changed = 0
        while time.time() - start < self.START_TIMEOUT:
            if ctx.should_stop():
                return False
            frame = ctx.frame()
            if self._team_screen(ctx, frame):
                gone = 0
                # The host changed chapter: the cost isn't what was set any more.
                cost = ctx.read_number(ENERGY_COST_REGION, frame=frame)
                changed = changed + 1 if cost is not None and self.set_cost is not None \
                    and cost != self.set_cost else 0
                if changed >= self.COST_CHANGED_READS:
                    ctx.log.info("hard-mode join: the energy cost changed (x%s -> x%s): "
                                 "a new chapter? setting the multiple again",
                                 self.set_cost, cost)
                    self.set_cost = None
                    if not self._ensure_multiple(ctx, 0, 0):
                        return False
                    changed = 0
                    continue
                banner = invites.find_banner(frame)
                if banner is not None:
                    got = invites.accept(
                        ctx, friend, "hard", banner, joined=lambda f: self._team_screen(ctx, f),
                        started=lambda f: not self._team_screen(ctx, f) and not invites.popup_open(f),
                        prefix="hard-mode join", quiet=True)
                    if got is None:
                        return False
                    if got:
                        ctx.log.info("hard-mode join: moved to %s's new room", friend)
                        self.set_cost = None
                        return self._ensure_multiple(ctx, 0, 0) and self._wait_host_start(ctx)
                    continue
            elif not invites.popup_open(frame):
                gone += 1
                if gone >= 2:  # two looks in a row off the team screen: started
                    ctx.log.info("hard-mode join: the host started the run")
                    return True
            if self._sleep(ctx, self.JOIN_POLL):
                return False
        ctx.log.warning("hard-mode join: the host didn't start in %d minutes",
                        self.START_TIMEOUT // 60)
        return False

    def _join_loop(self, ctx: Context) -> None:
        multiple = self.params["energy_multiple"]
        total = self.params["runs"]
        ctx.log.info("hard-mode join: %s's runs at %dx, %d run(s)",
                     self.params["friend"], multiple, total)
        done = 0
        self.set_cost = None   # the energy cost the multiple was set to
        while done < total and not ctx.should_stop():
            if not self._join(ctx):
                break
            if not self._ensure_multiple(ctx, done + 1, total):
                self._snap(ctx, "hard-join-multiple")
                break
            if not self._wait_host_start(ctx):
                self._snap(ctx, "hard-join-start")
                break
            result = self._wait_for_finish(ctx)
            ctx.log.info("hard-mode join: run %d/%d result: %s", done + 1, total, result)
            if result in ("success", "failure"):
                if not self._tap_until_main(ctx) and not self._team_screen(ctx):
                    ctx.log.info("hard-mode join: not back on a team screen after the "
                                 "result (the host may have left)")
            elif result != "restart":
                self._snap(ctx, "hard-join-finish")
                break
            done += 1
        ctx.log.info("hard-mode join done: %d/%d runs", done, total)

    # --- main loop --------------------------------------------------------
    def run(self, ctx: Context) -> None:
        if self.params.get("join"):
            self._join_loop(ctx)
            return
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

            result = self._wait_for_finish(ctx)
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
