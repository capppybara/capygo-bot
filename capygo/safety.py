"""Kill switch.

The kill switch listens globally for a key (default Esc). Global key listening
needs Accessibility / Input Monitoring permission, same as posting clicks.
"""

from __future__ import annotations

from pynput import keyboard


class KillSwitch:
    """Sets .stop = True when the configured key is pressed. Use as a context manager."""

    def __init__(self, key: str = "esc"):
        self.key = key.lower()
        self.stop = False
        self._listener: keyboard.Listener | None = None

    def _on_press(self, key) -> None:
        name = getattr(key, "name", None) or getattr(key, "char", None)
        if name and name.lower() == self.key:
            self.stop = True

    def __enter__(self) -> "KillSwitch":
        # The global key listener needs Input Monitoring permission. If it can't
        # start (e.g. run headless from the UI), keep going: the Stop button /
        # Ctrl+C (SIGTERM/SIGINT) still stop the run.
        try:
            self._listener = keyboard.Listener(on_press=self._on_press)
            self._listener.start()
        except Exception:
            self._listener = None
        return self

    def __exit__(self, *exc) -> None:
        if self._listener is not None:
            self._listener.stop()
