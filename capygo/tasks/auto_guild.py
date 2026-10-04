"""The guild chores ("auto guild") - a group inside auto-daily.

Like auto events: each guild chore is its own subtask with its own switch on the
Auto Daily screen (under a "Guild" heading). Their base is the guild screen: each
starts and ends there, and the run goes home after the last one.

  ./run.sh auto-guild      only the guild chores (no card in the app)

To add one: copy _guild_template.py to guild_<name>.py and fill it in, import it in
tasks/__init__.py, and add it to GUILD below. Its switch appears in the app
automatically.
"""

from __future__ import annotations

from ..task import register
from .daily import ChoreGroup, ChoreRunner, chore_params
from .guild import go_guild

GUILD = [  # run order
    # --- guild chores go here (see _guild_template.py). Not built yet: ---
    # Guild Hall, Guild Trade (planned); maybe Guild Raid later
]

GUILD_GROUP = ChoreGroup("Guild", GUILD, go_guild, "guild screen")


@register("auto-guild")
class AutoGuild(ChoreRunner):
    """Only the guild chores. No card in the app: they're switches on Auto Daily."""
    TITLE = "Auto Guild"
    ICON = "🏰"
    HIDDEN = True
    DESCRIPTION = "Run only the guild chores (they're also part of Auto Daily)."
    START_HINT = "Start on the main Adventure screen."

    GROUPS = [GUILD_GROUP]
    PARAMS = chore_params(GROUPS)
