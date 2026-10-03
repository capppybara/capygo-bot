"""Task: auto-daily.

Runs the daily chores in one go, in DAILIES order, skipping any switched off. The
app shows one on/off switch per daily (built from DAILIES); from the CLI:

  ./run.sh auto-daily                          run every daily
  ./run.sh auto-daily -p energy_claim=false    skip energy-claim

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
taps assume that screen.

To add a daily: write a DailyTask subclass in its own daily_<name>.py, register it
with @register("<name>"), import it in tasks/__init__.py, and append it to DAILIES.
"""

from __future__ import annotations

import os

from ..task import Context, Param, Task, register
from .daily import RERUN_PARAM, go_home, last_run_label, mark_done
from .daily_adventure_assistant import AdventureAssistant
from .daily_claim_cards import ClaimCards
from .daily_energy_claim import EnergyClaim
from .daily_shop import DailyShop

DAILIES = [EnergyClaim, AdventureAssistant, DailyShop, ClaimCards]  # run order


@register("auto-daily")
class AutoDaily(Task):
    TITLE = "Auto Daily"
    ICON = "📅"
    DESCRIPTION = "Run your daily chores in one go. Switch each daily on or off below."
    START_HINT = ("Start on the main Adventure screen. If the capy switch next to "
                  "Start is red, the bot taps it back to blue first.")

    PARAMS = [Param(d.param_key(), "bool", True, d.label(), help=d.DESCRIPTION)
              for d in DAILIES] + [RERUN_PARAM]

    @classmethod
    def already_done_today(cls, params: dict) -> list[tuple[str | None, str, str]]:
        return [(d.param_key(), d.label(), last_run_label(d.name)) for d in DAILIES
                if params.get(d.param_key()) and d.done_today()]

    def run(self, ctx: Context) -> None:
        enabled = [d for d in DAILIES if self.params.get(d.param_key())]
        skipped = [d for d in enabled if d.done_today() and not self.params.get("rerun")]
        for d in skipped:
            ctx.log.warning("%s already ran today (at %s) -> skipping. Confirm in the "
                            "app, or pass -p rerun=true, to run it again.",
                            d.name, last_run_label(d.name))
        enabled = [d for d in enabled if d not in skipped]
        if not enabled:
            ctx.log.warning("no dailies to run")
            return
        ctx.log.info("dailies to run: %s", ", ".join(d.name for d in enabled))

        if not go_home(ctx):
            if not ctx.should_stop():
                ctx.log.warning("couldn't get to the home screen (Start button with "
                                "the capy switch blue) -> not starting")
            return

        own_templates = ctx.templates_dir
        templates_root = os.path.dirname(own_templates)
        finished: list[str] = []
        failed: list[str] = []
        for cls in enabled:
            if ctx.should_stop():
                break
            ctx.log.info("--- %s ---", cls.name)
            daily = cls()
            daily.configure({})
            ctx.templates_dir = os.path.join(templates_root, cls.name)
            try:
                ok = daily.run_daily(ctx)
            except Exception:  # one broken daily shouldn't sink the rest
                ctx.log.exception("%s crashed", cls.name)
                ok = False
            finally:
                ctx.templates_dir = own_templates
            if ctx.should_stop():
                break
            if ok:
                finished.append(cls.name)
                if not ctx.dry_run:  # a dry run did nothing, so it doesn't count
                    mark_done(cls.name)
                ctx.log.info("%s done", cls.name)
            else:
                failed.append(cls.name)
                ctx.log.warning("%s did not finish; returning to the home screen and "
                                "moving on", cls.name)
            if not go_home(ctx):
                if not ctx.should_stop():
                    ctx.log.warning("couldn't get back to the home screen after %s -> "
                                    "stopping auto-daily", cls.name)
                break

        ctx.log.info("auto-daily: %d of %d done%s%s%s", len(finished), len(enabled),
                     f" ({', '.join(finished)})" if finished else "",
                     f"; failed: {', '.join(failed)}" if failed else "",
                     f"; skipped (already ran today): "
                     f"{', '.join(d.name for d in skipped)}" if skipped else "")
