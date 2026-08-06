"""Task screen: config form built from the task's PARAMS, Start/Stop, live log.

Runs the task by launching run.py as a subprocess (QProcess). That keeps all the
screen-capture / click / AppKit calls in their own process (off the UI thread),
streams the task's log into the panel, and makes Stop a clean SIGTERM the
controller turns into a graceful loop exit.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from capygo.task import get_task_class

from .icons import task_icon_pixmap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TaskScreen(QWidget):
    def __init__(self, name: str, on_back):
        super().__init__()
        self.name = name
        self.on_back = on_back
        self.cls = get_task_class(name)
        self.proc: QProcess | None = None
        self.controls: dict[str, tuple] = {}
        self._param_rows: list = []  # container widgets, disabled while running

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # --- header ---
        top = QHBoxLayout()
        back = QPushButton("‹  Home")
        back.setObjectName("Back")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self._go_back)
        top.addWidget(back)
        top.addStretch(1)
        root.addLayout(top)

        # header banner: icon sits inside the dark banner next to the title
        banner = QFrame()
        banner.setObjectName("Header")
        hb = QHBoxLayout(banner)
        hb.setContentsMargins(14, 8, 14, 8)
        hb.setSpacing(12)
        icon = QLabel()
        icon.setObjectName("CardIcon")
        pixmap = task_icon_pixmap(name, 40)
        if pixmap is not None:
            icon.setPixmap(pixmap)
        else:
            icon.setText(self.cls.ICON)
        title = QLabel(self.cls.title())
        title.setObjectName("TaskTitle")
        hb.addWidget(icon)
        hb.addWidget(title, 1)
        root.addWidget(banner)

        # --- description (in its own tan box) ---
        desc = QLabel(self.cls.DESCRIPTION)
        desc.setObjectName("TaskDesc")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # --- settings (the "Settings" label sits inside the box) ---
        box = QGroupBox("Settings")
        form = QFormLayout(box)
        form.setContentsMargins(14, 32, 14, 14)
        form.setSpacing(10)
        for p in self.cls.PARAMS:
            row_widget, value_widget = self._make_control(p)
            value_widget.setToolTip(p.help)
            self.controls[p.key] = (p, value_widget)
            self._param_rows.append(row_widget)
            form.addRow(p.label, row_widget)
        self.dry = QCheckBox("Dry run (log clicks without clicking)")
        form.addRow("", self.dry)
        root.addWidget(box)

        hint = QLabel("⚠  Make sure the buttons that will be clicked are fully visible "
                      "and not behind another window. The mouse needs to be able to "
                      "click the buttons directly for the bot to work.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        if self.cls.START_HINT:
            start_hint = QLabel("⚠  " + self.cls.START_HINT)
            start_hint.setObjectName("Hint")
            start_hint.setWordWrap(True)
            root.addWidget(start_hint)

        # --- controls ---
        btns = QHBoxLayout()
        self.start_btn = QPushButton("▶  Start")
        self.start_btn.setObjectName("Start")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setObjectName("Stop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        btns.addWidget(self.start_btn)
        btns.addWidget(self.stop_btn)
        root.addLayout(btns)

        # --- log box (the status label is the box's title, inside the box) ---
        self.log_box = QGroupBox("Idle")
        log_layout = QVBoxLayout(self.log_box)
        log_layout.setContentsMargins(14, 32, 14, 14)
        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log)
        root.addWidget(self.log_box, 1)

    # --- form controls ----------------------------------------------------
    def _make_control(self, p):
        """Return (row_widget, value_widget). row_widget goes in the form;
        value_widget is what _value() reads and what gets disabled."""
        if p.type == "bool":
            w = QCheckBox()
            w.setChecked(bool(p.default))
            return w, w

        spin = QDoubleSpinBox() if p.type == "float" else QSpinBox()
        spin.setRange(
            p.min if p.min is not None else 0,
            p.max if p.max is not None else 1_000_000,
        )
        spin.setValue(p.default)
        spin.setObjectName("ValueField")
        spin.setButtonSymbols(QAbstractSpinBox.NoButtons)  # hide built-in arrows
        spin.setFixedWidth(90)

        up = QPushButton("▲")
        up.setObjectName("SpinUp")
        up.setCursor(Qt.PointingHandCursor)
        up.clicked.connect(spin.stepUp)
        down = QPushButton("▼")
        down.setObjectName("SpinDown")
        down.setCursor(Qt.PointingHandCursor)
        down.clicked.connect(spin.stepDown)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(up)
        col.addWidget(down)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(spin)
        row.addLayout(col)
        row.addStretch(1)

        container = QWidget()
        container.setLayout(row)
        return container, spin

    def _value(self, p, w):
        if p.type == "bool":
            return w.isChecked()
        return w.value()

    # --- run lifecycle ----------------------------------------------------
    def start(self):
        args = ["-u", "run.py", self.name]
        for key, (p, w) in self.controls.items():
            args += ["-p", f"{key}={self._value(p, w)}"]
        if self.dry.isChecked():
            args.append("--dry-run")

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", ROOT)
        env.insert("PYTHONUNBUFFERED", "1")
        # So the task process exits if this app is killed (see run.py).
        env.insert("CAPYGO_PARENT_PID", str(os.getpid()))

        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(ROOT)
        self.proc.setProcessEnvironment(env)
        self.proc.setProgram(sys.executable)
        self.proc.setArguments(args)
        self.proc.readyReadStandardOutput.connect(
            lambda: self._append(self.proc.readAllStandardOutput())
        )
        self.proc.readyReadStandardError.connect(
            lambda: self._append(self.proc.readAllStandardError())
        )
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)

        self.log.clear()
        self._append_text(f"$ {os.path.basename(sys.executable)} {' '.join(args)}\n")
        self.proc.start()
        self._set_running(True)

    def stop(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.log_box.setTitle("Stopping…")
            self.proc.terminate()  # SIGTERM -> controller sets kill.stop (graceful)
            proc = self.proc
            QTimer.singleShot(
                6000,
                lambda: proc.kill() if proc.state() != QProcess.NotRunning else None,
            )

    def _on_finished(self, exit_code, exit_status):
        self._set_running(False)
        self.log_box.setTitle("Stopped" if exit_code else "Finished")

    def _on_error(self, err):
        self._append_text(f"[process error] {err}\n")

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        for row in self._param_rows:
            row.setEnabled(not running)
        self.dry.setEnabled(not running)
        if running:
            self.log_box.setTitle("Running…")

    # --- log helpers ------------------------------------------------------
    def _append(self, qbytes):
        self._append_text(bytes(qbytes.data()).decode(errors="replace"))

    def _append_text(self, text: str):
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)

    def _go_back(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.stop()
        self.on_back()
