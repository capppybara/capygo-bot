"""Home screen: a card per registered task, each launching its task screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import capygo.tasks  # noqa: F401  (registers all tasks)
from capygo.task import get_task_class, list_tasks

from .icons import app_icon_pixmap, task_icon_pixmap


class TaskCard(QFrame):
    """A clickable card showing a task's icon, title, and description."""

    def __init__(self, name: str, on_click):
        super().__init__()
        self.name = name
        self.on_click = on_click
        cls = get_task_class(name)

        self.setObjectName("TaskCard")
        self.setCursor(Qt.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 16, 18, 16)
        row.setSpacing(16)

        icon = QLabel()
        icon.setObjectName("CardIcon")
        icon.setAlignment(Qt.AlignTop)
        pixmap = task_icon_pixmap(name, 48)
        if pixmap is not None:
            icon.setPixmap(pixmap)
        else:
            icon.setText(cls.ICON)
        row.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(4)
        title = QLabel(cls.title())
        title.setObjectName("CardTitle")
        desc = QLabel(cls.DESCRIPTION)
        desc.setObjectName("CardDesc")
        desc.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(desc)
        row.addLayout(col, 1)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.on_click(self.name)


class HomeScreen(QWidget):
    def __init__(self, on_select):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(12)

        header = QFrame()
        header.setObjectName("Header")
        hb = QHBoxLayout(header)
        hb.setContentsMargins(16, 8, 16, 8)
        hb.setSpacing(10)
        hb.addStretch(1)
        app_pm = app_icon_pixmap(40)
        if app_pm is not None:
            logo = QLabel()
            logo.setPixmap(app_pm)
            hb.addWidget(logo)
        htitle = QLabel("CapyGo Bot")
        htitle.setObjectName("HeaderTitle")
        hb.addWidget(htitle)
        hb.addStretch(1)
        lay.addWidget(header)

        sub = QLabel("Pick an automation to run")
        sub.setObjectName("SubHeader")
        lay.addWidget(sub)
        lay.addSpacing(10)

        for name in list_tasks():
            lay.addWidget(TaskCard(name, on_select))

        lay.addStretch(1)

        note = QLabel("Built and tested on a MacBook Pro M3 16\" with the native "
                      "Capybara Go! Mac app using the default window size. "
                      "No guarantees it works in a different setup.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        lay.addWidget(note)
