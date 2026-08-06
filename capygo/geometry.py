"""Window-relative coordinate types.

All positions the tasks care about are expressed as fractions of the game
window, so they survive the window being moved or resized. They are converted
to absolute screen coordinates only at the moment of a click, using the live
window bounds (see window.GameWindow.to_screen).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rel:
    """A point as fractions of the window (0.0 = left/top, 1.0 = right/bottom)."""

    x: float
    y: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0 and 0.0 <= self.y <= 1.0):
            raise ValueError(f"Rel out of range: {self.x}, {self.y}")


@dataclass(frozen=True)
class RelRect:
    """A rectangle as fractions of the window. Used to limit a search to a region."""

    x: float
    y: float
    w: float
    h: float

    def to_pixels(self, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        """Return (x0, y0, x1, y1) in frame pixels for slicing a captured image."""
        x0 = int(self.x * frame_w)
        y0 = int(self.y * frame_h)
        x1 = int((self.x + self.w) * frame_w)
        y1 = int((self.y + self.h) * frame_h)
        return x0, y0, x1, y1
