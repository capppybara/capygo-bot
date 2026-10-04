"""Task: auto-daily.

Runs the daily chores, then the event chores (auto_events.py), the guild chores
(auto_guild.py) and the menu chores (auto_menu.py), in one go, skipping any
switched off. The app shows one on/off switch per chore, under "Dailies", "Events",
"Guild" and "Menu" headings (a group with no chores yet shows nothing); from the
CLI:

  ./run.sh auto-daily                          run every daily and event
  ./run.sh auto-daily -p energy_claim=false    skip energy-claim

The dailies' base is the home screen; the events' base is the Events screen, the
guild chores' the guild screen, the menu chores' the open menu drawer (see their
auto_*.py). The run ends on the home screen.

Each daily is also its own task (./run.sh energy-claim) with its own templates
folder (templates/<daily-name>/), which stays in effect when auto-daily runs it.

Each daily tracks its own last finish (data/daily_runs.json) and runs once per game
day: one that already ran today is skipped. The app asks before Start (Run again /
Skip it / Cancel) via already_done_today(); on the CLI pass -p rerun=true.

Every daily starts and ends on the home screen: the main Adventure screen with the
orange Start button showing and the capy switch beside it blue. auto-daily gets
there before the first daily, and after each daily - finished or not - it returns
there before moving on. A daily that fails (or crashes) is logged and skipped.
Getting home handles the other game mode too: if the capy switch is red, it's tapped
back to blue. If home still can't be reached, auto-daily stops, because every daily's
taps assume that screen. (The engine is ChoreRunner in daily.py, shared with
auto-events.)

To add a daily: write a DailyTask subclass in its own daily_<name>.py, register it
with @register("<name>"), import it in tasks/__init__.py, and append it to DAILIES.
"""

from __future__ import annotations

from ..task import register
from .auto_events import EVENTS_GROUP
from .auto_guild import GUILD_GROUP
from .auto_menu import MENU_GROUP
from .daily import ChoreGroup, ChoreRunner, chore_params, go_home
from .daily_adventure_assistant import AdventureAssistant
from .daily_calendar import ClaimCalendar
from .daily_claim_cards import ClaimCards
from .daily_energy_claim import EnergyClaim
from .daily_shop import DailyShop

DAILIES = [EnergyClaim, AdventureAssistant, DailyShop, ClaimCards,
           ClaimCalendar]  # run order


@register("auto-daily")
class AutoDaily(ChoreRunner):
    TITLE = "Auto Daily"
    ICON = "📅"
    DESCRIPTION = ("Run your daily chores and events in one go. Switch each one on "
                   "or off below.")
    START_HINT = ("Start on the main Adventure screen. If the capy switch next to "
                  "Start is red, the bot taps it back to blue first.")

    GROUPS = [ChoreGroup("Dailies", DAILIES, go_home, "home screen"), EVENTS_GROUP,
              GUILD_GROUP, MENU_GROUP]
    PARAMS = chore_params(GROUPS)
