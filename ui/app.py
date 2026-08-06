"""CapyGo Bot desktop UI entry point.

Run from the project root with the venv active:

    python -m ui.app
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .home import HomeScreen
from .icons import app_icon
from .style import load_stylesheet
from .task_view import TaskScreen


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CapyGo Bot")
        self.resize(560, 810)

        self.stack = QStackedWidget()
        root = QWidget()
        root.setObjectName("Root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.setCentralWidget(root)

        self.home = HomeScreen(self.open_task)
        self.stack.addWidget(self.home)
        self.task_screens: dict[str, TaskScreen] = {}

    def open_task(self, name: str):
        if name not in self.task_screens:
            screen = TaskScreen(name, on_back=self.go_home)
            self.task_screens[name] = screen
            self.stack.addWidget(screen)
        self.stack.setCurrentWidget(self.task_screens[name])

    def go_home(self):
        self.stack.setCurrentWidget(self.home)

    def closeEvent(self, event):
        # Kill any running task subprocess so it doesn't outlive the app.
        for screen in self.task_screens.values():
            proc = getattr(screen, "proc", None)
            if proc is not None:
                proc.kill()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())

    icon = app_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    window = MainWindow()
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
