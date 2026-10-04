"""Base class and shared helpers for menu chores (run by auto-menu / auto-daily).

The menu is a drawer that slides in from the left when you tap the list icon under
the profile picture (home screen, top-left). It lists Backpack, Mail, Tasks, Black
Market, Ranking, Friends, Video, Log In, and more below (the list scrolls), with an
X at the bottom (go_home's shared close-X sprite matches it). It's the base for
menu chores: each starts with the drawer open, opens its item, and comes back to
the drawer again.
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context
from .daily import ScreenTask, _crop, go_screen

MENU_BTN = Rel(0.162, 0.167)                    # list icon under the profile picture
MENU_TOP = RelRect(0.20, 0.22, 0.28, 0.13)      # "Backpack", "Mail"

# The drawer's items, top to bottom, before any scrolling (from a screenshot; not
# tapped yet). More items sit below Log In.
ITEMS = {"backpack": Rel(0.28, 0.251),
         "mail": Rel(0.28, 0.335),
         "tasks": Rel(0.28, 0.420),
         "black market": Rel(0.28, 0.504),
         "ranking": Rel(0.28, 0.588),
         "friends": Rel(0.28, 0.672),
         "video": Rel(0.28, 0.756),
         "log in": Rel(0.28, 0.840)}


def on_menu(frame) -> bool:
    """The menu drawer is open: its top items read Backpack and Mail."""
    text = " ".join(t for t, _, _ in ocr_lines(_crop(frame, MENU_TOP))).lower()
    return "backpack" in text and "mail" in text


def go_menu(ctx: Context) -> bool:
    """Get to the open menu drawer from anywhere (see go_screen)."""
    return go_screen(ctx, "the menu", on_menu, MENU_BTN)


class MenuTask(ScreenTask):
    """A menu chore: run_daily starts with the menu drawer open and returns True
    once it's back there."""
    go_base = staticmethod(go_menu)

    def open_item(self, ctx: Context, item: str) -> bool:
        """Tap one of the drawer's items (an ITEMS key)."""
        if not ctx.dry_run and not on_menu(ctx.frame()):
            ctx.log.warning("%s: the menu isn't open", self.name)
            return False
        return self.tap(ctx, ITEMS[item], item.title())
