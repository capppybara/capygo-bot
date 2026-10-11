"""Per-machine settings kept out of the repo: config.local.yaml next to
config.yaml (git-ignored; config.local.example.yaml shows the format).

For anything personal, such as the friend's in-game name the multiplayer modes
(Auto Gulu, hard mode joining) default to - names stay out of the code (user,
2026-10-10). A missing file or key gives the fallback.
"""

from __future__ import annotations

import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_CONFIG = os.path.join(ROOT, "config.local.yaml")


def local_default(key: str, fallback=""):
    """The value under `defaults:` in config.local.yaml, or `fallback`."""
    try:
        with open(LOCAL_CONFIG, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return fallback
    value = (data.get("defaults") or {}).get(key) if isinstance(data, dict) else None
    return fallback if value is None else value
