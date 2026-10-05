"""Menu chore: tasks-claim (claim finished daily tasks).

Starts with the menu drawer open: Tasks (3rd) -> the "Tasks" panel: Weekly and
Daily points bars (each with a "Claim All" button), then the "Daily Task" list.
A finished task has a green "Claim" button; claiming it (+10 points, no popup)
drops its row to the bottom (ticked), so the next one moves up. User: claim them
until the end, just by tapping the TOP row's Claim; never "Claim All" at the top,
never "Go" (an unfinished task), and no dragging in the menu. Stops when the top
row's button isn't a green Claim. Then the panel's red square X (top-right; the
shared round-X sprite doesn't match it) -> the drawer.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, register
from .daily import _crop
from .menu import MenuTask, on_menu

PANEL_TITLE = RelRect(0.30, 0.150, 0.40, 0.050)  # "Tasks"
TOP_TITLE = RelRect(0.257, 0.418, 0.413, 0.057)  # the top task's name
TOP_BTN = Rel(0.752, 0.447)                      # the top task's button
TOP_BTN_TEXT = RelRect(0.685, 0.426, 0.137, 0.042)
TOP_BTN_COLOR = RelRect(0.693, 0.431, 0.125, 0.032)
CLOSE_X = Rel(0.822, 0.171)                      # the red square X
MAX_CLAIMS = 40


def _words(frame, region: RelRect) -> str:
    return " ".join(t for t, _, _ in ocr_lines(_crop(frame, region))).lower()


def top_claimable(frame) -> bool:
    """The top task's button is a green "Claim" (green share ~0.72; "Go" is orange,
    0.00)."""
    c = _crop(frame, TOP_BTN_COLOR).astype(int)
    b, g, r = c[..., 0], c[..., 1], c[..., 2]
    green = float(((g > 180) & (g > r + 20) & (b < 120)).mean())
    return green >= 0.3 and "claim" in _words(frame, TOP_BTN_TEXT)


@register("tasks-claim")
class TasksClaim(MenuTask):
    TITLE = "Daily Tasks"
    LABEL = "Daily tasks claim"
    ICON = "📋"
    DESCRIPTION = ("Menu -> Tasks: claim every finished daily task (top row first), "
                   "never Claim All, then close.")
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_item(ctx, "tasks"):
            return False
        if ctx.dry_run:
            return self.tap(ctx, CLOSE_X, "close (X)")
        if "tasks" not in self.text_in(ctx, PANEL_TITLE):
            ctx.log.warning("%s: the Tasks panel did not open", self.name)
            return False
        claimed = stuck = 0
        while claimed < MAX_CLAIMS:
            frame = ctx.frame()
            if not top_claimable(frame):
                break
            title = _words(frame, TOP_TITLE)
            if not self.tap(ctx, TOP_BTN, f"Claim ({title})"):
                return False
            if _words(ctx.frame(), TOP_TITLE) == title:
                stuck += 1  # the row didn't drop: maybe a slow frame, try once more
                if stuck >= 2:
                    self.flag(ctx, f"claiming {title!r} didn't move it. Check Tasks.")
                    break
                continue
            stuck = 0
            claimed += 1
        ctx.log.info("%s: claimed %d task(s)", self.name, claimed)
        if not self.tap(ctx, CLOSE_X, "close (X)"):
            return False
        if not on_menu(ctx.frame()):
            ctx.log.warning("%s: not back on the menu drawer after closing", self.name)
            return False
        return True
