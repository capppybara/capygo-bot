"""Icon loading. Uses PNGs from ui/assets/ when present, else emoji fallback.

  ui/assets/app_icon.png        window / app icon
  ui/assets/<task-name>.png     per-task icon (e.g. pet-armament-chest.png)
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _path(filename: str) -> str | None:
    p = os.path.join(ASSETS, filename)
    return p if os.path.exists(p) else None


def task_icon_pixmap(task_name: str, size: int) -> QPixmap | None:
    p = _path(f"{task_name}.png")
    if not p:
        return None
    return QPixmap(p).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def app_icon() -> QIcon | None:
    p = _path("app_icon.png")
    return QIcon(p) if p else None


def app_icon_pixmap(size: int) -> QPixmap | None:
    p = _path("app_icon.png")
    if not p:
        return None
    return QPixmap(p).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
