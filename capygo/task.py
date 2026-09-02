"""Task framework: a registry of pluggable automations plus a shared Context.

Add a task by subclassing Task (or StepTask) and decorating it with
@register("task-name"). Drop its templates in templates/<task-name>/.

Two base classes cover the common shapes:
  StepTask  the "keep clicking until a stop condition" loop. Implement step().
  Task      full control. Implement run() yourself for custom strategies.

Tasks declare their configurable knobs in PARAMS (a list of Param). Values come
from the CLI (-p key=value) today and from the UI later; both funnel through
configure(), which validates + clamps and exposes them as self.params[key].
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .geometry import Rel, RelRect
from .perception import Match, find_template, load_template
from .window import GameWindow

_REGISTRY: dict[str, type["Task"]] = {}


# --- configurable parameters ---------------------------------------------
@dataclass
class Param:
    key: str
    type: str  # "int" | "float" | "bool"
    default: Any
    label: str
    min: float | None = None
    max: float | None = None
    help: str = ""
    choices: list | None = None  # if set, the value snaps to the nearest of these
    suffix: str = ""  # display-only unit shown after the value in the UI (e.g. "x")

    def coerce(self, value: Any) -> Any:
        if self.type == "int":
            v = int(value)
        elif self.type == "float":
            v = float(value)
        elif self.type == "bool":
            v = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
        else:
            v = value
        if self.choices:
            return min(self.choices, key=lambda c: abs(c - v))
        if self.min is not None and v < self.min:
            v = type(v)(self.min)
        if self.max is not None and v > self.max:
            v = type(v)(self.max)
        return v


def register(name: str):
    def deco(cls: type["Task"]) -> type["Task"]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def get_task(name: str, params: dict | None = None) -> "Task":
    if name not in _REGISTRY:
        raise KeyError(f"Unknown task {name!r}. Available: {', '.join(list_tasks())}")
    task = _REGISTRY[name]()
    task.configure(params or {})
    return task


def get_task_class(name: str) -> type["Task"]:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown task {name!r}. Available: {', '.join(list_tasks())}")
    return _REGISTRY[name]


def list_tasks() -> list[str]:
    return sorted(_REGISTRY)


class Context:
    """Everything a task needs, wired to the live window. Handed to run()/step().

    Coordinate model:
      - click_rel(Rel) uses window-relative fractions (survives move + resize).
      - find()/click_match() use template matches in frame pixels, converted to
        screen points via the current capture scale.
    """

    def __init__(
        self,
        window: GameWindow,
        capture_fn,
        config: dict,
        logger: logging.Logger,
        kill,
        templates_dir: str,
        dry_run: bool = False,
    ):
        self.window = window
        self._capture = capture_fn
        self.config = config
        self.log = logger
        self.kill = kill
        self.templates_dir = templates_dir
        self.dry_run = dry_run

        self.iteration = 0
        self._scale = 1.0
        self._threshold = config["match"]["threshold"]
        self._click_jitter = config["safety"]["click_jitter_px"]

    # --- perception -------------------------------------------------------
    def frame(self):
        img, self._scale = self._capture(self.window)
        return img

    def template_path(self, name: str) -> str:
        return os.path.join(self.templates_dir, f"{name}.png")

    def has_template(self, name: str) -> bool:
        return os.path.exists(self.template_path(name))

    def find(
        self, template_name: str, frame=None, region: RelRect | None = None, threshold: float | None = None
    ) -> Match:
        if frame is None:
            frame = self.frame()
        tpl = load_template(self.template_path(template_name))
        return find_template(frame, tpl, threshold if threshold is not None else self._threshold, region)

    # --- action -----------------------------------------------------------
    def click_rel(self, rel: Rel) -> None:
        sx, sy = self.window.to_screen(rel)
        self._do_click(sx, sy, f"rel({rel.x:.3f},{rel.y:.3f})")

    def click_match(self, match: Match) -> None:
        b = self.window.bounds()
        sx = b.x + match.x / self._scale
        sy = b.y + match.y / self._scale
        self._do_click(sx, sy, f"match(score={match.score:.2f})")

    def _do_click(self, sx: float, sy: float, label: str) -> None:
        # The human-readable action line is logged by the task (run x/total -
        # click button - reason). Keep the low-level coords at debug level.
        if self.dry_run:
            self.log.debug("DRY-RUN click %s at screen (%.0f, %.0f)", label, sx, sy)
            return
        from .input import click_screen

        self.window.focus()
        click_screen(sx, sy, jitter_px=self._click_jitter)
        self.log.debug("clicked %s at screen (%.0f, %.0f)", label, sx, sy)

    def drag_rel(self, start: Rel, end: Rel, steps: int = 25, duration: float = 0.6) -> None:
        """Click-and-drag between two window-relative points (e.g. to scroll a list)."""
        b = self.window.bounds()
        x0, y0 = b.x + start.x * b.width, b.y + start.y * b.height
        x1, y1 = b.x + end.x * b.width, b.y + end.y * b.height
        if self.dry_run:
            self.log.debug("DRY-RUN drag rel(%.3f,%.3f)->rel(%.3f,%.3f)",
                           start.x, start.y, end.x, end.y)
            return
        from .input import drag_screen

        self.window.focus()
        drag_screen(x0, y0, x1, y1, steps=steps, duration=duration)
        self.log.debug("dragged screen (%.0f,%.0f)->(%.0f,%.0f)", x0, y0, x1, y1)

    def read_clipboard(self) -> str:
        from .input import read_clipboard

        return read_clipboard()

    def set_clipboard(self, text: str) -> None:
        from .input import write_clipboard

        write_clipboard(text)

    def type_text(self, text: str) -> None:
        """Type into the currently focused field (click the field first)."""
        text = str(text)
        if self.dry_run:
            self.log.info("DRY-RUN type %r", text)
            return
        from .input import type_text

        self.window.focus()
        type_text(text)
        self.log.debug("typed %r", text)

    def read_number(self, region: RelRect, frame=None):
        """OCR an integer out of a window-relative region (None if unreadable)."""
        if frame is None:
            frame = self.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = region.to_pixels(w, h)
        from .perception import read_int

        return read_int(frame[y0:y1, x0:x1])

    # --- flow control -----------------------------------------------------
    def should_stop(self) -> bool:
        if self.kill.stop:
            self.log.info("kill switch pressed; stopping")
            return True
        return False


class Task(ABC):
    name: str = "unnamed"
    PARAMS: list[Param] = []

    # Display metadata for the UI (optional; sensible fallbacks below).
    TITLE: str | None = None
    ICON: str = "🎮"
    DESCRIPTION: str = ""
    START_HINT: str = ""  # task-specific precondition shown on the task screen

    @classmethod
    def title(cls) -> str:
        return cls.TITLE or cls.name.replace("-", " ").title()

    def configure(self, params: dict) -> None:
        self.params = {p.key: p.coerce(params.get(p.key, p.default)) for p in self.PARAMS}

    @abstractmethod
    def run(self, ctx: Context) -> None:
        ...


class StepTask(Task):
    """Runs step(ctx) in a loop until it returns False or a safety limit trips.

    Owns its own pacing via DELAY; override it per task (tasks that need
    animation-aware timing should subclass Task and write run() directly).
    """

    DELAY = 0.5  # seconds between steps

    def run(self, ctx: Context) -> None:
        while not ctx.should_stop():
            ctx.iteration += 1
            keep_going = self.step(ctx)
            if not keep_going:
                ctx.log.info("task step requested stop after %d steps", ctx.iteration)
                break
            time.sleep(self.DELAY)

    @abstractmethod
    def step(self, ctx: Context) -> bool:
        """Do one unit of work. Return True to continue, False to stop."""
        ...
