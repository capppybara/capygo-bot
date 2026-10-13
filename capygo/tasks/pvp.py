"""The PvP fight log: each arena and martial-arts fight, with the opponent's
profile, for building a better opponent picker later (user, 2026-10-09).

Before a fight, scout() opens the opponent's profile (their picture in the
list), reads it (profile.py: exact UID, name, power, HP / ATK / DEF, weapon),
saves the screenshot, and closes it. After the result, record() adds one row to
the log. Scouting never stands in the fight's way: a profile that doesn't open
is logged and the fight goes on.

Holy Grail War (2v2) fights get their own log, record_team(): only what the
list shows - the team's name, power and points - and the result (user,
2026-10-11). Both logs have a season column (season(): user, 2026-10-13).

Everything stays on this Mac, outside the repo:
  ~/Downloads/capy-bot/pvp/fights.csv           one row per fight
  ~/Downloads/capy-bot/pvp/holy-grail-war.csv   one row per Holy Grail War fight
  ~/Downloads/capy-bot/pvp/profiles/*.png       each opponent's profile screen
  ~/Downloads/capy-bot/pvp/weapons/unknown-N.png weapon pictures to label
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from ..geometry import Rel
from ..paths import output_path
from ..task import Context
from .profile import Profile, close_profile, fmt_trillions, open_profile, read_profile

FIGHTS_CSV = os.path.join("pvp", "fights.csv")
PROFILES_DIR = os.path.join("pvp", "profiles")
# won: 1 = victory, 0 = defeat, blank = not known (the result didn't read, no result
# screen, a stuck fight). User: no point changes - the gain follows the point gap
# (my_points vs opp_points), which every row has. opp_power: from the profile, or
# from the opponent list when the profile couldn't be read (user; noted then).
# opp_points: always from the list (a profile shows no points).
COLUMNS = [
    "time_utc", "mode", "season", "won",
    "my_power", "my_points", "opp_points",
    "opp_uid", "opp_name", "opp_power", "opp_hp", "opp_atk", "opp_def", "opp_weapon",
    "power_ratio", "profile_png", "note",
]


TEAM_CSV = os.path.join("pvp", "holy-grail-war.csv")
# season: season("hgw"); my_power: your team's power (the task's setting, both
# players); my_points and opp_points from the list, like fights.csv; opp_team as
# the list shows it.
TEAM_COLUMNS = ["time_utc", "season", "won", "my_power", "my_points", "opp_team",
                "opp_power", "opp_points", "note"]
# Seasons (user, 2026-10-13): each starts on a Saturday and lasts a week; the
# number goes up by itself. Holy Grail War: one every 4 weeks, season 1 from
# 2026-10-10. Martial Arts: one every 2 weeks, season 1 from 2026-10-03 (season 2
# from 2026-10-17). A fight outside a season week, or in the arena: blank.
SEASONS = {           # mode: (season 1's first day, days from one season to the next)
    "hgw": (date(2026, 10, 10), 28),
    "martial": (date(2026, 10, 3), 14),
}
SEASON_DAYS = 7       # a season's length


def season(mode: str, when: datetime | None = None) -> int | None:
    """The season `when` (default: now) falls in for `mode` ("hgw", "martial"):
    1 for the week from its first day, 2 for the week `every` days later, ...
    None outside a season week (user: a season lasts one week), before season 1,
    or for a mode without seasons. By the UTC date."""
    if mode not in SEASONS:
        return None
    first, every = SEASONS[mode]
    when = when or datetime.now(timezone.utc)
    days = (when.astimezone(timezone.utc).date() - first).days
    if days < 0 or days % every >= SEASON_DAYS:
        return None
    return days // every + 1


def _t(v: Decimal | None) -> str:
    return "" if v is None else fmt_trillions(v)


def scout(ctx: Context, at: Rel, mode: str) -> Profile | None:
    """Open the opponent's profile at `at` (their picture), read it, save the
    screenshot, and close it. None if it didn't open (nothing to close) or on a
    dry run. Raises nothing: a failed read leaves the fields empty."""
    if ctx.dry_run:
        ctx.log.info("pvp: DRY-RUN open the opponent's profile")
        return None
    if not open_profile(ctx, at):
        ctx.log.info("pvp: the opponent's profile didn't open; fighting without it")
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    png = output_path(os.path.join(PROFILES_DIR, f"{stamp}-{mode}.png"))
    os.makedirs(os.path.dirname(png), exist_ok=True)
    try:
        p = read_profile(ctx, save_to=png)
    except Exception as e:  # a bad read must never stop the fight
        ctx.log.warning("pvp: couldn't read the profile: %s", e)
        p = Profile(notes=[f"read failed: {e}"])
    if not close_profile(ctx):
        ctx.log.warning("pvp: the profile didn't close")
        p.notes.append("profile didn't close")
    ctx.log.info("pvp: opponent uid=%s name=%r power=%sT weapon=%s", p.uid or "?",
                 p.name, _t(p.power) or "?", p.weapon or "?")
    if p.new_weapon:  # listed under "Needs your attention" at the end of the run
        msg = (f"a weapon not seen before, saved as ~/Downloads/capy-bot/pvp/weapons/"
               f"{p.weapon}.png (on {p.name or p.uid or 'an opponent'}'s profile). Rename "
               f"the file to the weapon's name to teach it.")
        ctx.log.warning("pvp: %s", msg)
        ctx.flags.append(("pvp", msg))
    return p


def won(result: str | None) -> str:
    """The won column: "1" for a victory, "0" for a defeat, "" when not known."""
    return {"victory": "1", "defeat": "0"}.get(result or "", "")


def record(ctx: Context, mode: str, result: str | None, *, my_power: Decimal | None,
           my_points: int | None, list_power: Decimal | None,
           list_points: int | None, opponent: Profile | None) -> None:
    """Add one fight to fights.csv (with a header row the first time). `result` is
    the fight's "victory" / "defeat" / anything else (not known). Never raises: the
    log is a side job."""
    if ctx.dry_run:
        return
    p = opponent or Profile()
    notes = list(p.notes) if opponent else ["no profile"]
    power = p.power
    if power is None and list_power is not None:
        power = list_power
        notes.append("power from the list")
    ratio = (f"{power / my_power:.3f}" if power is not None and my_power
             else "")
    now = datetime.now(timezone.utc)
    n = season(mode, now)
    row_data = {
        "time_utc": now.isoformat(timespec="seconds"),
        "mode": mode,
        "season": "" if n is None else n,
        "won": won(result),
        "my_power": _t(my_power),
        "my_points": "" if my_points is None else my_points,
        "opp_points": "" if list_points is None else list_points,
        "opp_uid": p.uid or "",
        "opp_name": p.name,
        "opp_power": _t(power),
        "opp_hp": _t(p.hp),
        "opp_atk": _t(p.atk),
        "opp_def": _t(p.defense),
        "opp_weapon": p.weapon,
        "power_ratio": ratio,
        "profile_png": p.screenshot,
        "note": "; ".join(notes),
    }
    _upgrade_csv(ctx, FIGHTS_CSV, COLUMNS, lambda r: r.get("mode", ""))
    _append(ctx, FIGHTS_CSV, COLUMNS, row_data)


def record_team(ctx: Context, result: str | None, *, my_power: Decimal | None,
                my_points: int | None, team: str, power: Decimal | None,
                points: int | None, note: str = "") -> None:
    """Add one Holy Grail War fight to holy-grail-war.csv (with a header row the
    first time). Never raises: the log is a side job."""
    if ctx.dry_run:
        return
    now = datetime.now(timezone.utc)
    _upgrade_csv(ctx, TEAM_CSV, TEAM_COLUMNS, lambda r: "hgw")
    _append(ctx, TEAM_CSV, TEAM_COLUMNS, {
        "time_utc": now.isoformat(timespec="seconds"),
        "season": season("hgw", now),
        "won": won(result),
        "my_power": _t(my_power),
        "my_points": "" if my_points is None else my_points,
        "opp_team": team,
        "opp_power": _t(power),
        "opp_points": "" if points is None else points,
        "note": note,
    })


def team_results() -> dict[str, str]:
    """Holy Grail War: each team's latest result this season, by name as logged
    ("1" won, "0" lost, "" not known), from holy-grail-war.csv - the fights this
    run logged included. {} outside a season week or without a log."""
    now = season("hgw")
    if now is None:
        return {}
    try:
        with open(output_path(TEAM_CSV), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return {}
    last: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: r.get("time_utc", "")):
        if r.get("season") == str(now) and r.get("opp_team"):
            last[r["opp_team"]] = r.get("won", "")
    return last


def _upgrade_csv(ctx: Context, rel_path: str, columns: list[str], mode_of) -> None:
    """A log from before the season column: add it to every row (from its
    time_utc and mode_of(row)), keeping a copy as <name>-before-season.csv.bak.
    Never raises."""
    path = output_path(rel_path)
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return  # no log yet: it's written with the season column
    if not rows or "season" in rows[0]:
        return
    try:
        os.replace(path, path.replace(".csv", "-before-season.csv.bak"))
        for r in rows:
            n = season(mode_of(r), datetime.fromisoformat(r["time_utc"]))
            r["season"] = "" if n is None else n
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        ctx.log.info("pvp: added the season column to %s", path)
    except (OSError, ValueError, KeyError) as e:
        ctx.log.warning("pvp: couldn't add the season column: %s", e)


def _append(ctx: Context, rel_path: str, columns: list[str], row: dict) -> None:
    try:
        path = output_path(rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns)
            if new:
                w.writeheader()
            w.writerow(row)
    except OSError as e:
        ctx.log.warning("pvp: couldn't write the fight log: %s", e)
