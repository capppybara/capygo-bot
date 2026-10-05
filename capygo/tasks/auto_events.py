"""The event chores ("auto events") - a group inside auto-daily.

"Auto events" is just the collective name: each event is its own subtask with its
own switch on the Auto Daily screen (under the "Events" heading), and auto-daily
runs the switched-on events after the dailies. The events' base screen is the
Events screen, not home: every event starts and ends there so the next one carries
on from it, and the run goes home only after the last one. A failed event is logged
and skipped; each runs once per game day unless confirmed again.

  ./run.sh auto-daily -p tower_challenge=false   skip one event
  ./run.sh tower-challenge                       run one event on its own
  ./run.sh auto-events                           only the events (no card in the app)

To add an event: copy _event_template.py to event_<name>.py and fill it in (or, for
another "like the champions" plaza, subclass PlazaLikes from event_plaza.py), import
it in tasks/__init__.py, and add it to EVENTS below. Its switch appears in the app
automatically.
"""

from __future__ import annotations

from ..task import register
from .daily import ChoreGroup, ChoreRunner, chore_params
from .event import go_events
from .event_arena import AutoArena
from .event_dungeon_dive import DungeonDive
from .event_goblin_miner import GoblinMinerEvent
from .event_holy_grail_war import HolyGrailWar
from .event_martial_arts import MartialArts
from .event_tower_challenge import TowerChallenge

EVENTS = [  # run order
    # Challenge tab
    TowerChallenge,
    DungeonDive,
    GoblinMinerEvent,
    # Arena tab
    AutoArena,
    HolyGrailWar,
    MartialArts,
    # --- future events go here (see _event_template.py). Maybe later: ---
    # Arena tab:     Seal Battle
    # (Nothing to build for Gulu Mine on the Challenge tab or the Dungeon tab: no
    # daily chores there.)
]

EVENTS_GROUP = ChoreGroup("Events", EVENTS, go_events, "Events screen")


@register("auto-events")
class AutoEvents(ChoreRunner):
    """Only the events. No card in the app: the events are switches on Auto Daily."""
    TITLE = "Auto Events"
    ICON = "🏆"
    HIDDEN = True
    DESCRIPTION = "Run only the event chores (they're also part of Auto Daily)."
    START_HINT = "Start on the main Adventure screen."

    GROUPS = [EVENTS_GROUP]
    PARAMS = chore_params(GROUPS)
