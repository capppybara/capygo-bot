"""Persistent store for collected guild top-N power lists.

Each hedgemony-comparison run of get-guild-member-list adds one guild's top-N here;
the compare-guild-power task reads them all back to draw a comparison graph and
(optionally) clears the store afterwards.

The file is JSON at data/guild_power.json (the data/ dir is gitignored: this is
local, run-to-run state, not a deliverable). Guilds are keyed by their numeric
guild ID when it could be read (stable + unique), else by name, so re-collecting
the same guild replaces its entry instead of adding a duplicate.

Powers are stored as plain trillion strings (e.g. "1.19", "0.90585") to avoid any
float rounding; callers parse them with Decimal/float as needed.
"""

from __future__ import annotations

import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.join(ROOT, "data", "guild_power.json")


def path() -> str:
    return STORE_PATH


def load() -> dict:
    """Return {"guilds": {key: entry}}. Missing/corrupt file -> empty store."""
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"guilds": {}}
    if not isinstance(data, dict) or "guilds" not in data:
        return {"guilds": {}}
    return data


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, STORE_PATH)  # atomic, so a crash can't truncate the store


def add_guild(guild_id, name: str, powers: list[str], total: str,
              member_count=None, top_n=None) -> int:
    """Record (or replace) one guild's top-N powers. Returns the guild count."""
    data = load()
    key = str(guild_id) if guild_id not in (None, "") else f"name:{name}"
    data["guilds"][key] = {
        "name": name,
        "guild_id": None if guild_id in (None, "") else str(guild_id),
        "member_count": member_count,
        "top_n": top_n if top_n is not None else len(powers),
        "powers": list(powers),
        "sum": total,
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save(data)
    return len(data["guilds"])


def guilds() -> list[dict]:
    """All collected guild entries, newest collection last."""
    data = load()
    return sorted(data["guilds"].values(), key=lambda g: g.get("collected_at", ""))


def clear() -> None:
    _save({"guilds": {}})
