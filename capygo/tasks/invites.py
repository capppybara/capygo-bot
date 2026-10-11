"""Team invitations: the "New Invitation" banner (right edge of the screen) opens
"Team Invitation", one card per invite with the host's name and a ✓ to accept.
A mode selector at its top-left shows one mode's invites at a time; its drop-down
always lists Gulu Mine first, then Hard Chapters, then Holy Grail War (locked).

Shared by auto-gulu and hard-mode-autorun's joining: find the friend's invite
for a mode and accept it. Never the ✗, "Reject all", or the "No longer show
invitation messages" box.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import _crop, find_sprite, tap, wait

BANNER_BAND = (420, 642, 450, 700)                 # px x0, x1, y0, y1: "New Invitation"
BANNER_DY = 13                                     # tap a bit below its label
INVITES_TITLE = RelRect(0.28, 0.179, 0.42, 0.042)  # "Team Invitation"
MODE_LABEL = RelRect(0.218, 0.240, 0.25, 0.032)    # the selector: "Gulu Mine"
MODE_SELECTOR = (220, 240)
INVITE_NAMES = (180, 380, 260, 640)                # px x0, x1, y0, y1: host names
ACCEPT_X, ACCEPT_DY = 476, 21                      # a card's ✓: host name y + 21
NAME_MATCH = 0.8
SETTLE = 1.0
OPEN_TIMEOUT = 8.0


@dataclass(frozen=True)
class Mode:
    word: str                 # what the selector reads for it
    option: tuple[int, int]   # its drop-down entry, px
    title: str                # for the log


MODES = {
    "gulu": Mode("gulu", (220, 277), "Gulu Mine"),        # always first
    "hard": Mode("hard", (220, 314), "Hard Chapters"),    # second
}


def same_name(a: str, b: str) -> bool:
    a, b = re.sub(r"\s", "", a.lower()), re.sub(r"\s", "", b.lower())
    return a == b or SequenceMatcher(None, a, b).ratio() >= NAME_MATCH


def _px(pos: tuple[int, int]) -> Rel:
    return Rel(pos[0] / 642, pos[1] / 951)


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def popup_open(frame) -> bool:
    """The Team Invitation popup is open."""
    return "invitation" in _words(frame, INVITES_TITLE)


def find_banner(frame) -> Rel | None:
    """Where to tap the "New Invitation" banner, if it's showing."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    x0, x1, y0, y1 = BANNER_BAND
    crop = frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]
    for t, cx, cy in ocr_lines(crop):
        if "invitation" in t.lower():
            return Rel((cx / kx + x0) / 642, (cy / ky + y0 + BANNER_DY) / 951)
    return None


def _until(ctx: Context, check: Callable[[], bool], timeout: float = OPEN_TIMEOUT) -> bool:
    end = time.time() + timeout
    while True:
        if check():
            return not wait(ctx, SETTLE)
        if time.time() >= end or wait(ctx, 0.3):
            return False


def _tap(ctx: Context, target, what: str, prefix: str, quiet: bool) -> bool:
    if ctx.should_stop():
        return False
    if not quiet:
        ctx.log.info("%s: tap %s", prefix, what)
    return tap(ctx, target)


def close_popup(ctx: Context, prefix: str, quiet: bool = False) -> bool:
    x = find_sprite(ctx, ctx.frame(), "close_x.png")
    if x is None:
        if not quiet:
            ctx.log.warning("%s: no X to close the invitation popup", prefix)
        return False
    return _tap(ctx, x, "close the invitation popup", prefix, quiet)


def accept(ctx: Context, friend: str, mode: str, banner: Rel | None, *,
           joined: Callable, started: Callable | None = None, prefix: str,
           quiet: bool = False) -> bool | None:
    """Open the invitations (banner None = already open), switch them to `mode`
    (a MODES key), and accept the friend's invite. True = joined (joined(frame)
    holds); False = no invite from them (popup closed); None = a stop or a problem
    (logged). `quiet`: a repeated check while waiting for a host's start - only an
    accept is logged, and a popup that won't open or close (the host may have just
    started: started(frame)) counts as no invite."""
    m = MODES[mode]
    if banner is not None and not _tap(ctx, banner, "New Invitation", prefix, quiet):
        return None
    if ctx.dry_run:
        return True
    if quiet:
        # the host may start any moment: wait only briefly for the popup, and not
        # at all once the run has started
        def popup_or_start() -> bool:
            f = ctx.frame()
            return popup_open(f) or bool(started and started(f))
        if not _until(ctx, popup_or_start, 3.0) or not popup_open(ctx.frame()):
            return False
    elif not _until(ctx, lambda: popup_open(ctx.frame())):
        ctx.log.warning("%s: the Team Invitation popup didn't open", prefix)
        return None
    if m.word not in _words(ctx.frame(), MODE_LABEL):
        if not (_tap(ctx, _px(MODE_SELECTOR), "mode selector", prefix, quiet)
                and _tap(ctx, _px(m.option), m.title, prefix, quiet)):
            return None
        if m.word not in _words(ctx.frame(), MODE_LABEL):
            if not quiet:
                ctx.log.warning("%s: couldn't switch the invitations to %s", prefix,
                                m.title)
            return False if close_popup(ctx, prefix, quiet) or quiet else None
    frame = ctx.frame()
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    x0, x1, y0, y1 = INVITE_NAMES
    crop = frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]
    name_y = next((cy / ky + y0 for t, _, cy in ocr_lines(crop)
                   if same_name(t, friend)), None)
    if name_y is None:
        if not quiet:
            ctx.log.info("%s: no %s invite from %s yet", prefix, m.title, friend)
        return False if close_popup(ctx, prefix, quiet) or quiet else None
    if not _tap(ctx, Rel(ACCEPT_X / 642, (name_y + ACCEPT_DY) / 951),
                f"accept {friend}'s invite (✓)", prefix, False):
        return None
    # the host may start at once, so joined() should count a started run too
    if not _until(ctx, lambda: joined(ctx.frame())):
        ctx.log.warning("%s: accepted, but the team screen didn't show", prefix)
        return None
    ctx.log.info("%s: joined %s's team", prefix, friend)
    return True
