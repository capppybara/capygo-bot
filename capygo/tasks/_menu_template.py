"""TEMPLATE for a new menu chore - copy, don't import.

  1. Copy this file to menu_<name>.py (e.g. menu_mail.py).
  2. Fill in the name, the item, and the steps in run_daily.
  3. Import it in tasks/__init__.py and add the class to MENU in auto_menu.py.

The rules every menu chore follows (see menu.py and daily.py):
  - run_daily starts with the menu drawer open and must end with it open again
    (go_menu), so the next chore carries on from it. Return False if something
    went wrong: the runner logs it, gets back to the drawer, and moves on.
  - Tap through self.tap(ctx, target, "what"): it logs and waits ~1s after.
  - Check a screen opened before tapping inside it (self.text_in on a title), and
    wait for slow screens to load and settle before tapping.
  - Each chore runs once per game day automatically (the app asks before a re-run).
"""

from __future__ import annotations

from ..geometry import Rel, RelRect
from ..task import Context, register
from .menu import MenuTask, go_menu

SCREEN_TITLE = RelRect(0.25, 0.07, 0.50, 0.05)  # something that proves it opened


@register("new-menu-chore")                   # unique task name, kebab-case
class NewMenuChore(MenuTask):
    TITLE = "New Menu Chore"
    LABEL = "New menu chore"                  # the switch label on Auto Daily
    ICON = "📋"
    DESCRIPTION = "Menu -> <item>: <what it does>, then go back."
    START_HINT = "Start on the main Adventure screen."

    def run_daily(self, ctx: Context) -> bool:
        if not self.open_item(ctx, "mail"):   # a key of menu.ITEMS
            return False
        if not ctx.dry_run and "title word" not in self.text_in(ctx, SCREEN_TITLE):
            ctx.log.warning("%s: the item did not open", self.name)
            return False

        # ... the chore's steps: self.tap(ctx, Rel(x, y), "what") ...

        return go_menu(ctx)                   # back to the menu drawer
