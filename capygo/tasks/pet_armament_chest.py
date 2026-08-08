"""Task: pet-armament-chest.

Verified flow (one "run" = one chest collected):

  Unlock                     start a chest; button becomes Free Upgrade
  Free Upgrade (x3, free)    reveals slots; then splits into Open + Upgrade
  Open + Upgrade screen      read the 6 status slots (check / cross / question):
                             - free stage (first 3 revealed, from the free upgrades):
                               Open once free failures >= free_failure_threshold,
                               else go paid (0 = free upgrades only)
                             - paid stage (>3 revealed): Open once total failures
                               (free + paid) >= failure_threshold, else Upgrade
                             each successful Upgrade promotes the chest tier
                             (e.g. green 60% -> purple 45%); each fail adds an X
  Open                       collects the chest -> Rewards popup
  Rewards popup              "Tap to close" -> back to Unlock (next chest)

A run is counted only when a Rewards popup is actually dismissed, so a click
that fails to register can never be miscounted as progress.

Robustness: every iteration waits for a *stable* frame before acting, so the bot
never clicks during a transition/animation (that was the original failure mode:
an Open click fired mid-animation, did nothing, and was wrongly counted).

Templates in templates/pet-armament-chest/ (all captured from the live game):
  unlock_button, free_upgrade_button, open_button, upgrade_button,
  check, cross, question, tap_to_close
"""

from __future__ import annotations

import time

import numpy as np

from ..geometry import Rel, RelRect
from ..task import Context, Param, Task, register

# The 6 status slots, as window-relative centers (measured from the live UI).
SLOT_Y = 0.6293
SLOT_XS = [0.3134, 0.3881, 0.4624, 0.5369, 0.6115, 0.6862]
SLOTS = [Rel(x, SLOT_Y) for x in SLOT_XS]
SLOT_BOX = 0.05  # half-size (window fraction) of the box cropped per slot

ICONS = ["check", "cross", "question"]
ICON_MATCH_MIN = 0.70  # below this, a slot reads as "unknown" (mid-animation)

# Search only the bottom-left for the single "Unlock" button, so the bottom-right
# "Unlock 10 at once" button can never be matched or clicked.
UNLOCK_REGION = RelRect(0.0, 0.68, 0.50, 0.30)

# Compact single-char symbols for logging the status bar.
SYM = {"check": "✓", "cross": "✗", "question": "?", "unknown": "·"}


def _slots_str(slots) -> str:
    return "".join(SYM.get(s, "?") for s in slots)


@register("pet-armament-chest")
class PetArmamentChest(Task):
    TITLE = "Pet Armament Chest"
    ICON = "🧰"  # fallback only; ui/assets/pet-armament-chest.png is shown when present
    DESCRIPTION = ("Unlock chest and upgrade until it reaches your failure threshold, "
                   "open and repeat.")
    START_HINT = ("Make sure you are on the locked chest screen with the Unlock "
                  "button before starting the bot.")

    PARAMS = [
        Param("runs", "int", 10, "Total runs", min=1, max=999,
              help="how many chests to collect before stopping"),
        Param("free_failure_threshold", "int", 2, "Free failure threshold", min=0, max=3,
              help="Open instead of going paid once free-stage failures reach this many "
                   "(0 = free upgrades only)"),
        Param("failure_threshold", "int", 2, "Total failure threshold", min=1, max=6,
              help="Open the chest once total failures (free + paid) reach this many"),
    ]

    # Hard cap on wall-clock time between one click and the next.
    MAX_BETWEEN_CLICKS = 2.0
    # Let a transition begin after a click before we start watching for stability.
    POST_CLICK = 0.4
    # Wait for the screen to settle, but never longer than the cap allows.
    STABLE_MAX_WAIT = MAX_BETWEEN_CLICKS - POST_CLICK  # 1.6s
    STABLE_INTERVAL = 0.3
    STABLE_DIFF = 3.0  # mean abs pixel diff below which a frame counts as settled

    # --- frame stability --------------------------------------------------
    def _stable_frame(self, ctx: Context):
        """Capture until the screen stops changing, so we never act mid-animation."""
        prev = None
        t0 = time.time()
        while time.time() - t0 < self.STABLE_MAX_WAIT:
            frame = ctx.frame()
            if prev is not None:
                diff = float(np.mean(np.abs(frame.astype(np.int16) - prev.astype(np.int16))))
                if diff < self.STABLE_DIFF:
                    return frame
            prev = frame
            time.sleep(self.STABLE_INTERVAL)
        return prev  # best effort: return the last frame after the timeout

    # --- slot reading -----------------------------------------------------
    def _classify_slot(self, ctx: Context, frame, slot: Rel) -> str:
        from ..perception import find_template, load_template

        h, w = frame.shape[:2]
        cx, cy = int(slot.x * w), int(slot.y * h)
        half = int(SLOT_BOX * w)
        box = frame[max(0, cy - half):cy + half, max(0, cx - half):cx + half]

        best_name, best_score = "unknown", 0.0
        for name in ICONS:
            if not ctx.has_template(name):
                continue
            tpl = load_template(ctx.template_path(name))
            if box.shape[0] < tpl.shape[0] or box.shape[1] < tpl.shape[1]:
                continue
            m = find_template(box, tpl, 0.0)
            if m.score > best_score:
                best_name, best_score = name, m.score
        return best_name if best_score >= ICON_MATCH_MIN else "unknown"

    def _read_slots(self, ctx: Context, frame) -> list[str]:
        return [self._classify_slot(ctx, frame, s) for s in SLOTS]

    # --- decision (pure, unit-testable) -----------------------------------
    @staticmethod
    def _decide(slots, free_threshold: int, threshold: int):
        """On an Open+Upgrade screen, choose the next action.

        Returns (action, reason) where action is "open" or "upgrade".
          free stage  (<=3 slots revealed): Open once free failures reach
                      free_threshold, else go paid.
          paid stage  (>3 revealed): Open once total failures reach threshold.
        Both stages quit on failures >= their threshold.
        """
        revealed = sum(1 for s in slots if s in ("check", "cross"))
        x = slots.count("cross")  # total failures so far (free + paid)
        bar = _slots_str(slots)
        if revealed <= 3:  # free stage
            if x >= free_threshold:
                return "open", f"{bar} free fails {x}>={free_threshold}, stop"
            return "upgrade", f"{bar} free fails {x}/{free_threshold} -> paid"
        # paid stage
        if x >= threshold:
            return "open", f"{bar} X={x}/{threshold} threshold reached"
        return "upgrade", f"{bar} X={x}/{threshold}"

    # --- helpers ----------------------------------------------------------
    def _act(self, ctx: Context, match, run_no: int, total: int, button: str, reason: str) -> None:
        """Log one action line in the format `run x/total - click B - reason`, then click."""
        ctx.log.info("run %d/%d - click %s - %s", run_no, total, button, reason)
        ctx.click_match(match)
        time.sleep(self.POST_CLICK)

    # --- main loop --------------------------------------------------------
    def run(self, ctx: Context) -> None:
        total = self.params["runs"]
        threshold = self.params["failure_threshold"]
        free_threshold = self.params["free_failure_threshold"]
        runs_done = 0
        ctx.log.info("pet-armament-chest: runs=%d free_failure_threshold=%d "
                     "failure_threshold=%d", total, free_threshold, threshold)

        while runs_done < total and not ctx.should_stop():
            ctx.iteration += 1
            run_no = runs_done + 1  # the chest currently being worked on
            frame = self._stable_frame(ctx)

            # Rewards popup: collecting is complete -> dismiss and count the run.
            rewards = ctx.find("tap_to_close", frame=frame)
            if rewards.found:
                self._act(ctx, rewards, run_no, total, "Tap to close", "collect rewards")
                runs_done += 1
                continue

            # Start of a chest.
            unlock = ctx.find("unlock_button", frame=frame, region=UNLOCK_REGION)
            if unlock.found:
                self._act(ctx, unlock, run_no, total, "Unlock", "start chest")
                continue

            # Free reveals.
            free_up = ctx.find("free_upgrade_button", frame=frame)
            if free_up.found:
                self._act(ctx, free_up, run_no, total, "Free Upgrade", "free reveal")
                continue

            # Decision screen: Open + Upgrade both present.
            open_btn = ctx.find("open_button", frame=frame)
            upgrade_btn = ctx.find("upgrade_button", frame=frame)

            if open_btn.found and upgrade_btn.found:
                slots = self._read_slots(ctx, frame)
                action, reason = self._decide(slots, free_threshold, threshold)
                btn = open_btn if action == "open" else upgrade_btn
                self._act(ctx, btn, run_no, total, action.capitalize(), reason)
                continue

            # Only Open remains (chest maxed): collect it.
            if open_btn.found:
                bar = _slots_str(self._read_slots(ctx, frame))
                self._act(ctx, open_btn, run_no, total, "Open", f"{bar} chest maxed")
                continue

            # Nothing recognized on a settled frame (mid-animation): wait and retry.
            ctx.log.debug("run %d/%d - waiting (no known control)", run_no, total)

        ctx.log.info("pet-armament-chest done: %d/%d runs collected", runs_done, total)
