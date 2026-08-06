#!/usr/bin/env python3
"""List on-screen windows so you can set config.yaml `window.owner`.

Owner names and sizes show without any special permission. Titles may be blank
until Screen Recording permission is granted; matching on owner is enough.

  python tools/list_windows.py            all windows
  python tools/list_windows.py capy       filter by substring (owner or title)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capygo.window import list_windows  # noqa: E402


def main() -> int:
    needle = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    rows = list_windows()
    rows.sort(key=lambda r: r["width"] * r["height"], reverse=True)

    print(f"{'OWNER':<28} {'SIZE':>12}  TITLE")
    print("-" * 70)
    for r in rows:
        if needle and needle not in r["owner"].lower() and needle not in r["title"].lower():
            continue
        size = f'{r["width"]}x{r["height"]}'
        print(f'{r["owner"][:28]:<28} {size:>12}  {r["title"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
