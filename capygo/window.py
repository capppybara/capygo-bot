"""Find the game window and expose its live bounds.

Window enumeration (owner name + bounds) works without Screen Recording
permission. Capturing the window's pixels (see capture.py) does require it.
"""

from __future__ import annotations

from dataclasses import dataclass

import Quartz
from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

from .geometry import Rel


class WindowNotFound(Exception):
    pass


@dataclass
class Bounds:
    x: float
    y: float
    width: float
    height: float


def _on_screen_windows() -> list[dict]:
    return Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )


def list_windows() -> list[dict]:
    """Return simplified info for on-screen windows (for tools/list_windows.py)."""
    out = []
    for w in _on_screen_windows():
        b = w.get("kCGWindowBounds", {})
        out.append(
            {
                "owner": w.get("kCGWindowOwnerName", ""),
                "title": w.get("kCGWindowName", "") or "",
                "pid": w.get("kCGWindowOwnerPID", 0),
                "width": int(b.get("Width", 0)),
                "height": int(b.get("Height", 0)),
            }
        )
    return out


class GameWindow:
    """Locates a single game window by owner name (and optional title filter).

    Bounds are re-read on demand, so a moved or resized window just works.
    """

    def __init__(self, owner: str, title_contains: str = "", min_size: int = 100):
        self.owner = owner
        self.title_contains = title_contains
        self.min_size = min_size

    def _match(self) -> dict:
        candidates = []
        for w in _on_screen_windows():
            owner = w.get("kCGWindowOwnerName", "") or ""
            title = w.get("kCGWindowName", "") or ""
            b = w.get("kCGWindowBounds", {})
            if self.owner.lower() not in owner.lower():
                continue
            if self.title_contains and self.title_contains.lower() not in title.lower():
                continue
            if b.get("Width", 0) < self.min_size or b.get("Height", 0) < self.min_size:
                continue
            candidates.append(w)
        if not candidates:
            raise WindowNotFound(
                f"No on-screen window with owner containing {self.owner!r}. "
                f"Run: python tools/list_windows.py"
            )
        # If several match, take the largest (the game viewport, not a helper window).
        candidates.sort(
            key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"],
            reverse=True,
        )
        return candidates[0]

    def bounds(self) -> Bounds:
        b = self._match()["kCGWindowBounds"]
        return Bounds(b["X"], b["Y"], b["Width"], b["Height"])

    def window_id(self) -> int:
        return int(self._match()["kCGWindowNumber"])

    def pid(self) -> int:
        return int(self._match()["kCGWindowOwnerPID"])

    def to_screen(self, rel: Rel) -> tuple[float, float]:
        """Map a window-relative point to absolute screen coordinates (points)."""
        b = self.bounds()
        return (b.x + rel.x * b.width, b.y + rel.y * b.height)

    def focus(self) -> None:
        """Bring the owning app to the front so it can receive clicks."""
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(self.pid())
        if app is not None:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
