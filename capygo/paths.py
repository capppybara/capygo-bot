"""Where the bot writes the files it produces.

All user-facing output (CSVs, the comparison graph, ...) goes under one folder so
it's easy to find and doesn't clutter ~/Downloads.
"""

from __future__ import annotations

import os

OUTPUT_DIR = os.path.expanduser("~/Downloads/capy-bot")


def output_path(name: str) -> str:
    """Absolute path for an output file `name` inside OUTPUT_DIR (created if needed)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, name)
