"""Task: compare-guild-power.

Draws every guild collected so far by the hedgemony comparison mode of
get-guild-member-list (-p hedgemony=true) onto one graph. It reads the shared
collection store (data/guild_power.json) and writes a single timestamped PNG to
~/Downloads (hedgemony_guild_comparison_<YYYYMMDDHHMMSS>.png, so runs aren't
overwritten): one line per guild over rank 1..N (its top-N powers, highest first). The curve's
steepness shows how top-heavy a guild is; comparing the lines shows which guild is
stronger and how power is spread. The legend labels each line "guild_name (total T)"
with that guild's top-N total power.

A "session" is everything collected since the last clear, so all guilds gathered in
a cycle land on the same graph. This task does not touch the game, so it works with
the game closed. Collect a few guilds first (open each guild's Info screen and run
get-guild-member-list with Hedgemony comparison on), then run this to graph them.

`clear_after` empties the collection once the graph is written (the intended
end-of-cycle behavior). It defaults to False so the data survives while the
feature is being tested; flip it on to reset the list after graphing.
"""

from __future__ import annotations

import os
import time

from ..task import Context, Param, Task, register

OUT_DIR = os.path.expanduser("~/Downloads")


def _out_path() -> str:
    """A fresh timestamped path so each graph is kept, not overwritten."""
    return os.path.join(OUT_DIR, f"hedgemony_guild_comparison_{time.strftime('%Y%m%d%H%M%S')}.png")


@register("compare-guild-power")
class CompareGuildPower(Task):
    TITLE = "Compare Guild Power"
    ICON = "📊"
    # Driven by the Generate plot button on the Get Guild Member List screen (in
    # hedgemony comparison mode), so it doesn't need its own home card. Still
    # registered, so the button and the CLI can run it.
    HIDDEN = True
    DESCRIPTION = ("Graph the top-N power distribution of every guild collected in "
                   "hedgemony comparison mode, on one chart.")
    START_HINT = ("Collect guilds first: on each guild's Info screen, run Get Guild "
                  "Member List with Hedgemony comparison on. Then run this (the game "
                  "can be closed).")

    PARAMS: list[Param] = []

    def run(self, ctx: Context) -> None:
        from .. import store

        entries = store.guilds()
        if not entries:
            ctx.log.warning("no guilds collected yet -> collect some first with "
                            "Hedgemony comparison on (store: %s)", store.path())
            return

        ctx.log.info("comparing %d guild(s): %s", len(entries),
                     ", ".join(e["name"] for e in entries))
        for e in entries:
            ctx.log.info("  %s: top-%s sum %sT (%s members, collected %s)",
                         e["name"], e.get("top_n", "?"), e.get("sum", "?"),
                         e.get("member_count", "?"), e.get("collected_at", "?"))

        path = self._draw(ctx, entries)
        ctx.log.info("wrote comparison graph -> %s", path)
        ctx.log.info("collection kept (%d guild(s)); use Clear collection to reset",
                     len(entries))

    # --- plotting ---------------------------------------------------------
    @staticmethod
    def _floats(powers) -> list[float]:
        out = []
        for p in powers:
            try:
                out.append(float(p))
            except (TypeError, ValueError):
                continue
        return out

    def _draw(self, ctx: Context, entries: list[dict]) -> str:
        import matplotlib
        matplotlib.use("Agg")  # headless: no window, just write the PNG
        import matplotlib.pyplot as plt

        # Stable label per guild; disambiguate a repeated name with its id.
        names = [e["name"] for e in entries]
        labels = []
        for e in entries:
            lbl = e["name"]
            if names.count(e["name"]) > 1 and e.get("guild_id"):
                lbl = f"{e['name']} #{e['guild_id']}"
            labels.append(lbl)

        series = [self._floats(e.get("powers", [])) for e in entries]
        totals = [sum(s) for s in series]
        max_n = max((len(s) for s in series), default=0)

        cmap = plt.get_cmap("tab10")
        colors = [cmap(i % 10) for i in range(len(entries))]

        # One graph: every collected guild is a line over rank 1..N. The legend
        # carries each guild's total top-N power as "guild_name (total T)", drawn
        # strongest-total first so the legend order matches the lines top to bottom.
        fig, ax = plt.subplots(figsize=(11, 6.5))
        fig.patch.set_facecolor("#FBF3E0")  # capygo cream
        ax.set_facecolor("#FFFDF7")

        order = sorted(range(len(entries)), key=lambda i: totals[i], reverse=True)
        for i in order:
            s = series[i]
            ax.plot(range(1, len(s) + 1), s, marker="o", ms=4, lw=2,
                    color=colors[i], label=f"{labels[i]} ({self._fmt(totals[i])}T)")

        ax.set_xlabel("Rank in top list (1 = strongest)")
        ax.set_ylabel("Power (trillions)")
        if max_n:
            step = 1 if max_n <= 25 else 5
            ax.set_xticks(range(1, max_n + 1, step))
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.3)
        ax.legend(title="Guild (top-N total)", fontsize=9, loc="upper right")

        ax.set_title(f"Guild power comparison — top {max_n}, {len(entries)} guild"
                     f"{'s' if len(entries) != 1 else ''}",
                     fontsize=14, fontweight="bold")
        fig.tight_layout()
        out_path = _out_path()
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    @staticmethod
    def _fmt(v: float) -> str:
        s = f"{v:.2f}"
        return s.rstrip("0").rstrip(".") if "." in s else s
