"""Home screen: a card per registered task, each launching its task screen."""

from __future__ import annotations

import re

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import capygo.tasks  # noqa: F401  (registers all tasks)
from capygo.task import get_task_class, list_tasks

from .icons import app_icon_pixmap, task_icon_pixmap
from .task_view import task_process


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

        # "Pick an automation" with a Restart game button beside it (user): one
        # click runs the restart-game task (kill the game, open it again, get to
        # its home screen) in the background, no task screen.
        bar = QHBoxLayout()
        bar.setSpacing(8)
        sub = QLabel("Pick an automation to run")
        sub.setObjectName("SubHeader")
        bar.addWidget(sub)
        bar.addStretch(1)
        self.restart_note = QLabel("")
        self.restart_note.setObjectName("SubHeader")
        bar.addWidget(self.restart_note)
        self.restart_btn = QPushButton("Restart game")
        self.restart_btn.setObjectName("SmallBtn")
        self.restart_btn.setCursor(Qt.PointingHandCursor)
        self.restart_btn.setToolTip("Kill the game, open it again, and get to its "
                                    "home screen, closing the start-up notices")
        self.restart_btn.clicked.connect(self._restart_game)
        bar.addWidget(self.restart_btn)
        lay.addLayout(bar)
        self.restart_proc: QProcess | None = None
        self._restart_out: list[bytes] = []

        # Everything below the header scrolls, so each card keeps its full height
        # (with many tasks the window used to squeeze them and cut off their text).
        listing = QWidget()
        listing.setObjectName("HomeList")
        col = QVBoxLayout(listing)
        col.setContentsMargins(0, 0, 10, 0)  # room for the scrollbar
        col.setSpacing(12)

        for name in list_tasks():
            if getattr(get_task_class(name), "HIDDEN", False):
                continue  # e.g. compare-guild-power: reached via a button, not a card
            col.addWidget(TaskCard(name, on_select))

        col.addStretch(1)

        note = QLabel("Built and tested on a MacBook Pro M3 16\" with the native "
                      "Capybara Go! Mac app using the default window size. "
                      "No guarantees it works in a different setup.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        col.addWidget(note)

        scroll = QScrollArea()
        scroll.setObjectName("HomeScroll")
        scroll.setWidget(listing)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)

    # --- the Restart game button -------------------------------------------------
    def _restart_game(self) -> None:
        if self.restart_proc is not None and self.restart_proc.state() != QProcess.NotRunning:
            return
        self._restart_out = []
        proc = task_process(self, ["-u", "run.py", "restart-game"])
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self._restart_out.append(bytes(proc.readAllStandardOutput())))
        proc.finished.connect(self._restart_done)
        proc.errorOccurred.connect(self._restart_error)
        self.restart_proc = proc
        self.restart_btn.setEnabled(False)
        self.restart_btn.setText("Restarting…")
        self.restart_note.setText("")
        proc.start()

    def _restart_done(self, exit_code, exit_status) -> None:
        out = b"".join(self._restart_out).decode(errors="replace")
        m = re.search(r"the game restarted in (\d+)s", out)
        self.restart_btn.setEnabled(True)
        self.restart_btn.setText("Restart game")
        self.restart_note.setText(f"Game restarted ({m.group(1)}s)" if m and exit_code == 0
                                  else "Restart failed, see logs/")

    def _restart_error(self, err) -> None:
        if err == QProcess.FailedToStart:  # no finished() follows
            self.restart_btn.setEnabled(True)
            self.restart_btn.setText("Restart game")
            self.restart_note.setText("Couldn't start the restart")
