"""Task: pet-synthesis (user, 2026-10-06).

Equip -> Pets -> Pet Synthesis, then Synthesize until the game won't any more.

From home: the helmet (2nd bottom-bar button, "Equip") -> Pets (2nd in Equip's
middle bar) -> the Pets page: pets in the yard, Show Pets / Battle / Build, the egg
hatchers, and a bottom bar of Pet List / Pet Resonance / Pet Synthesis beside the
back arrow. Pet Synthesis opens a "Pet Synthesis" popup: "The following surplus
pet fragments will be synthesized into a new pet", a grid of fragment tiles (e.g.
x15, x20, x20, x111, x153), a Synthesize button, and an X below the popup.

The task starts wherever the player is (user: "check if i'm already on the page"):
in the Pet Synthesis popup -> synthesizes at once; on the Pets page -> opens it; on
the Equip screen -> Pets; anywhere else -> home first. go_pets() is reusable.

User: "click synthesize until it stops letting you" (the game decides when; no
need to count fragments). One synthesis, as seen live 2026-10-06:
  Synthesize -> a "Tips" confirm ("Pet fragments will be consumed to synthesize.
  Continue?", Cancel / OK) -> OK -> "Rewards" (the new pets; "Tap to close") ->
  closed with a tap on the Pet Synthesis title, above the reward's dark band ->
  back on the PETS PAGE (the popup closes) -> Pet Synthesis again.
At the end the popup reads "No surplus pet fragments available" and Synthesize
does nothing (live: 24 syntheses, ~6.7s each).
The bot repeats that until a step doesn't happen (Pet Synthesis won't open, or
Synthesize brings no Tips), saving a screenshot of that end screen. Then it
closes whatever is open (Cancel on a Tips, the X on the popup) and goes home.
OK is tapped only when the Tips text says fragments will be consumed.
"""

from __future__ import annotations

import time
from typing import Callable

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Task, register
from .daily import _crop, go_home, save_snapshot, tap, tap_to_close_up, wait

EQUIP_BTN = Rel(0.304, 0.943)                  # helmet, 2nd in the bottom bar (home)
EQUIP_BAR = RelRect(0.10, 0.515, 0.80, 0.045)  # Equip's middle bar: Adventurer, Pets...
EQUIP_LABELS = ("adventurer", "pets", "collectible", "mount", "artifact", "speciali")
PETS_BTN = Rel(0.290, 0.512)                   # Pets, 2nd in that bar
PETS_BAR = RelRect(0.36, 0.945, 0.64, 0.045)   # Pets page: Pet Resonance / Pet Synthesis
SYNTH_OPEN = Rel(0.810, 0.935)                 # Pet Synthesis (bottom-right)
SYNTH_TITLE = RelRect(0.25, 0.205, 0.50, 0.050)  # the popup's "Pet Synthesis"
TITLE_TAP = Rel(0.5, 0.233)                    # that title: closes the Rewards popup
SYNTH_BTN = Rel(0.498, 0.658)                  # Synthesize
SYNTH_CLOSE = Rel(0.5, 0.822)                  # the X below the popup
TIPS_TEXT = RelRect(0.15, 0.475, 0.70, 0.075)  # "Pet fragments will be consumed to..."
TIPS_OK = Rel(0.670, 0.632)                    # (430, 601)
TIPS_CANCEL = Rel(0.332, 0.632)                # (213, 601)
OPEN_TIMEOUT = 6.0
TIPS_TIMEOUT = 3.0        # Synthesize -> the Tips confirm
REWARD_TIMEOUT = 6.0      # OK -> the Rewards popup
REWARD_SETTLE = 1.5       # the new pets animate in before the popup takes a tap
MAX_SYNTHESES = 50        # never loop forever on a misread
POLL = 0.3


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def on_equip(frame) -> bool:
    """The Equip screen: two or more of its middle bar's labels read (the small
    labels OCR unevenly: "pets" came out as "p ets" or "el ts")."""
    text = _words(frame, EQUIP_BAR)
    return sum(label in text for label in EQUIP_LABELS) >= 2


def on_pets(frame) -> bool:
    """The Pets page: its bottom bar reads Pet Resonance / Pet Synthesis (the
    stylized "Pet List" doesn't OCR). Still true under the Pet Synthesis popup."""
    text = _words(frame, PETS_BAR)
    return "synthesis" in text or "resonance" in text


def on_synthesis(frame) -> bool:
    """The Pet Synthesis popup is open."""
    return "synthesis" in _words(frame, SYNTH_TITLE)


def tips_up(frame) -> bool:
    """The synthesis confirm: "Pet fragments will be consumed to synthesize.
    Continue?" (the only dialog whose OK the bot taps)."""
    text = _words(frame, TIPS_TEXT)
    return "fragments" in text and "consumed" in text


def _until(ctx: Context, check: Callable, timeout: float = OPEN_TIMEOUT) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if ctx.should_stop():
            return False
        if check(ctx.frame()):
            return True
        time.sleep(POLL)
    return False


def go_pets(ctx: Context) -> bool:
    """Get to the Pets page from anywhere. True once it's showing."""
    frame = ctx.frame()
    if on_pets(frame):
        ctx.log.info("pets: already on the Pets page")
        return True
    if on_equip(frame):
        ctx.log.info("pets: on the Equip screen")
    else:
        if not go_home(ctx):
            ctx.log.warning("pets: couldn't get to the home screen")
            return False
        ctx.log.info("pets: tap Equip (helmet)")
        if not tap(ctx, EQUIP_BTN):
            return False
        if not ctx.dry_run and not _until(ctx, on_equip):
            ctx.log.warning("pets: the Equip screen didn't open")
            return False
    ctx.log.info("pets: tap Pets")
    if not tap(ctx, PETS_BTN):
        return False
    if not ctx.dry_run and not _until(ctx, on_pets):
        ctx.log.warning("pets: the Pets page didn't open")
        return False
    return True


@register("pet-synthesis")
class PetSynthesis(Task):
    TITLE = "Pet Synthesis"
    ICON = "🥚"
    DESCRIPTION = "Equip -> Pets -> Pet Synthesis: Synthesize until it won't any more."
    START_HINT = "Start anywhere in the game, or already on the Pets page."

    def run(self, ctx: Context) -> None:
        if ctx.dry_run:
            if go_pets(ctx):
                for target, what in ((SYNTH_OPEN, "Pet Synthesis"), (SYNTH_BTN, "Synthesize"),
                                     (TIPS_OK, "OK"), (TITLE_TAP, "the title (close Rewards)")):
                    self._tap(ctx, target, what)
            return
        made = self._synthesize(ctx)
        ctx.log.info("pet-synthesis: %d %s", made, "synthesis" if made == 1 else "syntheses")
        if ctx.should_stop():
            return
        frame = ctx.frame()
        if tips_up(frame):
            if not self._tap(ctx, TIPS_CANCEL, "Cancel"):
                return
            frame = ctx.frame()
        if on_synthesis(frame) and not self._tap(ctx, SYNTH_CLOSE, "X (close)"):
            return
        go_home(ctx)

    def _tap(self, ctx: Context, target: Rel, what: str) -> bool:
        ctx.log.info("pet-synthesis: tap %s", what)
        return tap(ctx, target)

    def _end(self, ctx: Context, why: str) -> None:
        shot = save_snapshot(ctx, "pet-synthesis-end")
        ctx.log.info("pet-synthesis: %s -> done%s", why,
                     f"; screen saved: {shot}" if shot else "")

    def _synthesize(self, ctx: Context) -> int:
        """Open Pet Synthesis, Synthesize, OK, close the Rewards; again until a step
        doesn't happen. The number of syntheses."""
        made = 0
        while made < MAX_SYNTHESES and not ctx.should_stop():
            frame = ctx.frame()
            if tips_up(frame):  # left open (e.g. a stopped run): start over
                if not self._tap(ctx, TIPS_CANCEL, "Cancel (a leftover Tips)"):
                    break
                continue
            if tap_to_close_up(frame):  # a leftover Rewards popup
                if not self._tap(ctx, TITLE_TAP, "the title (close Rewards)"):
                    break
                continue
            if on_synthesis(frame):
                if made == 0:
                    ctx.log.info("pet-synthesis: already in Pet Synthesis")
            else:
                if made == 0 and not go_pets(ctx):
                    ctx.log.warning("pet-synthesis: couldn't get to the Pets page")
                    break
                if not self._tap(ctx, SYNTH_OPEN, "Pet Synthesis"):
                    break
                if not _until(ctx, on_synthesis):
                    self._end(ctx, "Pet Synthesis didn't open")
                    break
            if not self._tap(ctx, SYNTH_BTN, "Synthesize"):
                break
            if not _until(ctx, tips_up, TIPS_TIMEOUT):
                self._end(ctx, "Synthesize brought no confirm")
                break
            if not self._tap(ctx, TIPS_OK, "OK"):
                break
            if not _until(ctx, tap_to_close_up, REWARD_TIMEOUT):
                shot = save_snapshot(ctx, "pet-synthesis-no-reward")
                ctx.log.warning("pet-synthesis: no Rewards after OK%s",
                                f"; screen saved: {shot}" if shot else "")
                break
            made += 1
            ctx.log.info("pet-synthesis: synthesis %d done", made)
            if not self._close_rewards(ctx):
                break
        return made

    def _close_rewards(self, ctx: Context) -> bool:
        if wait(ctx, REWARD_SETTLE):
            return False
        for _ in range(3):
            if not self._tap(ctx, TITLE_TAP, "the title (close Rewards)"):
                return False
            if not tap_to_close_up(ctx.frame()):
                return True
        ctx.log.warning("pet-synthesis: the Rewards popup won't close")
        return False
