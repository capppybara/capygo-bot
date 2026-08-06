#!/usr/bin/env python3
"""CLI entry point.

  python run.py --list                              show available tasks + params
  python run.py pet-armament-chest                  run a task with defaults
  python run.py pet-armament-chest -p runs=5 -p failure_threshold=2
  python run.py pet-armament-chest -n               dry-run (log clicks, don't click)
"""

from __future__ import annotations

import argparse
import sys

import capygo.tasks  # noqa: F401  (registers all tasks)
from capygo.controller import run_task
from capygo.task import _REGISTRY, list_tasks


def _parse_params(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"bad --param {pair!r}, expected key=value")
        k, v = pair.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _print_tasks() -> None:
    print("Available tasks:")
    for name in list_tasks():
        cls = _REGISTRY[name]
        print(f"  {name}")
        for p in getattr(cls, "PARAMS", []):
            rng = ""
            if p.min is not None or p.max is not None:
                rng = f" [{p.min}..{p.max}]"
            print(f"      {p.key}={p.default}{rng}  {p.help}")


def main() -> int:
    parser = argparse.ArgumentParser(description="capygo-bot")
    parser.add_argument("task", nargs="?", help="task name to run")
    parser.add_argument("--list", action="store_true", help="list tasks and exit")
    parser.add_argument(
        "-p", "--param", action="append", metavar="key=value", help="set a task parameter"
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="log clicks without performing them"
    )
    parser.add_argument("--config", help="path to a config.yaml (default: ./config.yaml)")
    args = parser.parse_args()

    if args.list or not args.task:
        _print_tasks()
        return 0

    try:
        run_task(
            args.task,
            params=_parse_params(args.param),
            dry_run=args.dry_run,
            config_path=args.config,
        )
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
