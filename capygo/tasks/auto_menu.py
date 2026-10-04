"""The menu chores ("auto menu") - a group inside auto-daily.

Like auto events: each menu chore is its own subtask with its own switch on the
Auto Daily screen (under a "Menu" heading). Their base is the open menu drawer
(the list icon under the profile picture): each starts and ends there, and the run
goes home after the last one. The group runs last, after the dailies, events and
guild chores.

  ./run.sh auto-menu      only the menu chores (no card in the app)

To add one: copy _menu_template.py to menu_<name>.py and fill it in, import it in
tasks/__init__.py, and add it to MENU below. Its switch appears in the app
automatically.
"""

from __future__ import annotations

from ..task import register
from .daily import ChoreGroup, ChoreRunner, chore_params
from .menu import go_menu

MENU = [  # run order
    # --- menu chores go here (see _menu_template.py). None built yet. ---
]

MENU_GROUP = ChoreGroup("Menu", MENU, go_menu, "menu")


@register("auto-menu")
class AutoMenu(ChoreRunner):
    """Only the menu chores. No card in the app: they're switches on Auto Daily."""
    TITLE = "Auto Menu"
    ICON = "📋"
    HIDDEN = True
    DESCRIPTION = "Run only the menu chores (they're also part of Auto Daily)."
    START_HINT = "Start on the main Adventure screen."

    GROUPS = [MENU_GROUP]
    PARAMS = chore_params(GROUPS)
