"""The PvP fight log: each arena and martial-arts fight, with the opponent's
profile, for building a better opponent picker later (user, 2026-10-09).

Before a fight, scout() opens the opponent's profile (their picture in the
list), reads it (profile.py: exact UID, name, power, HP / ATK / DEF, weapon),
saves the screenshot, and closes it. After the result, record() adds one row to
the log. Scouting never stands in the fight's way: a profile that doesn't open
is logged and the fight goes on.

Everything stays on this Mac, outside the repo:
  ~/Downloads/capy-bot/pvp/fights.csv           one row per fight
  ~/Downloads/capy-bot/pvp/profiles/*.png       each opponent's profile screen
  ~/Downloads/capy-bot/pvp/weapons/unknown-N.png weapon pictures to label
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from decimal import Decimal

from ..geometry import Rel
from ..paths import output_path
from ..task import Context
from .profile import Profile, close_profile, fmt_trillions, open_profile, read_profile

FIGHTS_CSV = os.path.join("pvp", "fights.csv")
PROFILES_DIR = os.path.join("pvp", "profiles")
COLUMNS = [
    "time_utc", "mode", "result",
    "my_power", "my_points",
    "row", "list_power", "list_points",
    "opp_uid", "opp_name", "opp_power", "opp_hp", "opp_atk", "opp_def", "opp_weapon",
    "power_ratio", "profile_png", "note",
]


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


def record(ctx: Context, mode: str, result: str, *, my_power: Decimal | None,
           my_points: int | None, row: int | None, list_power: Decimal | None,
           list_points: int | None, opponent: Profile | None) -> None:
    """Add one fight to fights.csv (with a header row the first time). Never
    raises: the log is a side job."""
    if ctx.dry_run:
        return
    p = opponent or Profile()
    power = p.power if p.power is not None else list_power
    ratio = (f"{power / my_power:.3f}" if power is not None and my_power
             else "")
    row_data = {
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "result": result,
        "my_power": _t(my_power),
        "my_points": "" if my_points is None else my_points,
        "row": "" if row is None else row,
        "list_power": _t(list_power),
        "list_points": "" if list_points is None else list_points,
        "opp_uid": p.uid or "",
        "opp_name": p.name,
        "opp_power": _t(p.power),
        "opp_hp": _t(p.hp),
        "opp_atk": _t(p.atk),
        "opp_def": _t(p.defense),
        "opp_weapon": p.weapon,
        "power_ratio": ratio,
        "profile_png": p.screenshot,
        "note": "; ".join(p.notes) if opponent else "no profile",
    }
    try:
        path = output_path(FIGHTS_CSV)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            if new:
                w.writeheader()
            w.writerow(row_data)
    except OSError as e:
        ctx.log.warning("pvp: couldn't write the fight log: %s", e)
