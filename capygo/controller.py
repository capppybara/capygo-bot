"""Load config, build the shared Context, and run a task."""

from __future__ import annotations

import logging
import os
import signal
import time

import yaml

from .capture import capture_window
from .safety import KillSwitch
from .task import Context, get_task
from .window import GameWindow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path: str | None = None) -> dict:
    path = path or os.path.join(ROOT, "config.yaml")
    with open(path, "r") as f:
        return yaml.safe_load(f)


def setup_run_logging(task_name: str):
    """Configure the 'capygo' logger for one run.

    Emits `HH:MM:SS.mmm - <message>` to stderr (which the UI panel streams) and
    to a per-run file logs/<task>-<timestamp>.log. Returns (logger, log_path).
    """
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    log_path = os.path.join(ROOT, "logs", f"{task_name}-{time.strftime('%Y%m%d-%H%M%S')}.log")

    logger = logging.getLogger("capygo")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d - %(message)s", datefmt="%H:%M:%S")
    for handler in (logging.StreamHandler(), logging.FileHandler(log_path)):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger, log_path


def build_runtime(task_name, params, kill, logger, config, dry_run=False):
    """Wire config + window + task into a ready-to-run (task, Context) pair."""
    window = GameWindow(
        owner=config["window"]["owner"],
        title_contains=config["window"].get("title_contains", ""),
    )
    task = get_task(task_name, params)
    ctx = Context(
        window=window,
        capture_fn=capture_window,
        config=config,
        logger=logger,
        kill=kill,
        templates_dir=os.path.join(ROOT, "templates", task_name),
        dry_run=dry_run,
    )
    return task, ctx


def run_task(
    task_name: str,
    params: dict | None = None,
    dry_run: bool = False,
    config_path: str | None = None,
) -> None:
    config = load_config(config_path)
    log, log_path = setup_run_logging(task_name)

    log.info("run start: task=%s params=%s dry_run=%s", task_name, params or {}, dry_run)
    log.info("log file: %s", log_path)
    with KillSwitch(config["safety"]["kill_key"]) as kill:
        # SIGTERM (UI Stop) and SIGINT (Ctrl+C) request a graceful stop: the loop
        # checks kill.stop each iteration and exits cleanly.
        def _request_stop(signum, frame):
            kill.stop = True

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

        task, ctx = build_runtime(task_name, params, kill, log, config, dry_run)
        task.run(ctx)
    log.info("task %r finished after %d steps", task_name, ctx.iteration)
