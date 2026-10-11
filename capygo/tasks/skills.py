"""Skill screens ("Choose skill"): pick the top card(s) and Select.

Shared by auto-gulu and hard-mode-autorun's joining. A screen shows its cards
under the "Choose skill" title and a Select button reading "picked/wanted"
("0/2 Select Skills"). Two layouts so far, told apart by that count: 2-pick
screens have 4 cards, 1-pick screens 3 (Gulu: battle 1 is 2 x 2 picks, battles
2-4 2 x 1; hard mode: 5 x 2 picks, then 1 x 1, then 2 x 1 - user). Picking never
waits for the teammate: each player's screen runs on its own countdown, which
auto-picks when it runs out (so a miss is low stakes).

  - Pick only a FRESH screen (0 picked), after letting it settle (the cards
    slide in; a first pick at once was missed).
  - After the picks, read the count: a tap that didn't register (a connection
    overlay swallowed one) gets the next card down instead.
  - Select only while the screen is still up: Select (321,833) sits inside the
    battle's Skills button (358,818).
  - A screen still up with its picks RESELECT_AFTER after Select had a tap that
    didn't take: finish_screen() picks the missing card / Selects again. Left
    alone it times out, and then the next screen gets only ~3s.

Every screen pick_screen() picks on is saved first (user, 2026-10-10: "take
screen shot of all skill selects - we will process them posthoc", for a smarter
pick later): ~/Downloads/capy-bot/skill-screens/<mode>-<time>.png. Hard mode also
saves its events' offerings there (the treasure's pick, the demon's pact, the
angel's gifts - they're skills too, user).
"""

from __future__ import annotations

import os
import re
import time

import cv2

from ..geometry import Rel, RelRect
from ..paths import output_path
from ..perception import ocr_lines
from ..task import Context
from .daily import _crop, tap

CHOOSE_TITLE = RelRect(0.25, 0.140, 0.50, 0.070)   # "Choose skill"
PICK_COUNT = RelRect(0.31, 0.845, 0.38, 0.060)     # "0/2 Select Skills" / "0/1 ..."
SELECT_BTN = (321, 833)                            # "2/2 Select Skills"
SKILL_TOP, SKILL_SECOND = (320, 320), (320, 450)   # 2-pick screens: the top two cards
SKILL_ONE = (320, 385)                             # 1-pick screens: the top of 3 cards
SPARE_TWO = [(320, 578), (320, 706)]               # 2-pick screens: cards 3 and 4
SPARE_ONE = [(320, 513), (320, 642)]               # 1-pick screens: cards 2 and 3
SELECT_WAIT = 2.0         # user: look again 2s after Select (the next screen shows
                          # ~1s after it)
SKILL_SETTLE = 2.0        # user: wait 2s after spotting a skill screen, then pick
RESELECT_AFTER = 2.0      # a screen still up with picks this long after Select
SCREENS_DIR = "skill-screens"                      # under ~/Downloads/capy-bot


def _rel(pos: tuple[int, int]) -> Rel:
    return Rel(pos[0] / 642, pos[1] / 951)


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def on_skill_screen(frame) -> bool:
    return "choose skill" in _words(frame, CHOOSE_TITLE)


def picks(frame) -> tuple[int, int] | None:
    """The Select button's "picked/wanted" ("0/2 Select Skills" -> (0, 2)); None
    if unreadable."""
    m = re.search(r"(\d)\s*/\s*(\d)", _words(frame, PICK_COUNT))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _tap(ctx: Context, pos: tuple[int, int], what: str, prefix: str,
         after: float = 1.0) -> bool:
    if ctx.should_stop():
        return False
    ctx.log.info("%s: tap %s", prefix, what)
    return tap(ctx, _rel(pos), after)


def save_screen(ctx: Context, frame, mode: str) -> None:
    """Keep a skill screen for reading later. Never raises: a side job."""
    if ctx.dry_run:
        return
    try:
        folder = output_path(SCREENS_DIR)
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        cv2.imwrite(os.path.join(folder, f"{mode or 'skills'}-{stamp}.png"), frame)
    except Exception as e:  # noqa: BLE001 - must never stop a run
        ctx.log.warning("skills: couldn't save the skill screen: %s", e)


def pick_screen(ctx: Context, two_picks: bool, prefix: str, mode: str = "") -> bool:
    """ONE skill screen: the top card(s), Select, then park the cursor on the top
    card. One screen at a time (the caller checks again before the next): a batch
    of two screens kept tapping after the 2nd had closed, and its last Select
    landed on the battle's Skills button. The parked cursor keeps a stray click
    off that button too (user). False on a stop."""
    if not ctx.dry_run:
        save_screen(ctx, ctx.frame(), mode)
    if two_picks:
        taps = [("skill (top)", SKILL_TOP), ("skill (second)", SKILL_SECOND)]
    else:
        taps = [("skill (top)", SKILL_ONE)]
    for what, pos in taps:
        if not _tap(ctx, pos, what, prefix):
            return False
    if not ctx.dry_run:
        got = picks(ctx.frame())
        if got is not None and got[0] < got[1]:
            missing = got[1] - got[0]
            ctx.log.info("%s: only %d/%d picked (a tap didn't register) -> the next "
                         "card%s", prefix, got[0], got[1], "s" if missing > 1 else "")
            spare = SPARE_TWO if two_picks else SPARE_ONE
            for i, pos in enumerate(spare[:missing], 1):
                if not _tap(ctx, pos, f"skill (spare {i})", prefix):
                    return False
    # Never tap Select unless the skill screen is still up: Select sits inside the
    # battle's Skills button.
    if not ctx.dry_run and not on_skill_screen(ctx.frame()):
        ctx.log.info("%s: the skill screen closed before Select", prefix)
        ctx.hover_rel(_rel(SKILL_TOP))
        return True
    if not _tap(ctx, SELECT_BTN, "Select Skills", prefix, SELECT_WAIT):
        return False
    ctx.hover_rel(_rel(SKILL_TOP))
    return True


def finish_screen(ctx: Context, got: tuple[int, int], prefix: str) -> bool:
    """A skill screen still up at "k/N" RESELECT_AFTER after its Select: a tap
    didn't take. Short of picks -> the next unpicked card(s) first; then Select
    again, only while the screen is still up. False on a stop."""
    picked, wanted = got
    if picked < wanted:
        ctx.log.info("%s: the skill screen is stuck at %d/%d -> the next card, then "
                     "Select again", prefix, picked, wanted)
        spare = SPARE_TWO if wanted == 2 else SPARE_ONE
        for i, pos in enumerate(spare[:wanted - picked], 1):
            if not _tap(ctx, pos, f"skill (spare {i})", prefix):
                return False
    else:
        ctx.log.info("%s: the skill screen is still up at %d/%d -> Select didn't "
                     "take, again", prefix, picked, wanted)
    if not on_skill_screen(ctx.frame()):
        return True
    if not _tap(ctx, SELECT_BTN, "Select Skills (again)", prefix, SELECT_WAIT):
        return False
    ctx.hover_rel(_rel(SKILL_TOP))
    return True
