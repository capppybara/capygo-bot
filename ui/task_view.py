"""Task screen: config form built from the task's PARAMS, Start/Stop, live log.

Runs the task by launching run.py as a subprocess (QProcess). That keeps all the
screen-capture / click / AppKit calls in their own process (off the UI thread),
streams the task's log into the panel, and makes Stop a clean SIGTERM the
controller turns into a graceful loop exit.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from capygo.task import get_task_class

from .icons import task_icon_pixmap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ChoiceSpinBox(QSpinBox):
    """A spin box whose value is constrained to a fixed list of choices.

    The up/down arrows step through the choices in order (not by a fixed
    increment, since they aren't evenly spaced), and a typed value snaps to the
    nearest choice. Used for parameters like the energy multiple (1, 2, 3, 5,
    10, 20)."""

    def __init__(self, choices, parent=None):
        super().__init__(parent)
        self._choices = sorted(int(c) for c in choices)
        self.setRange(self._choices[0], self._choices[-1])

    def _nearest_index(self, value: int) -> int:
        return min(range(len(self._choices)), key=lambda i: abs(self._choices[i] - value))

    def stepBy(self, steps: int) -> None:
        idx = self._nearest_index(self.value())
        idx = max(0, min(len(self._choices) - 1, idx + (1 if steps > 0 else -1)))
        self.setValue(self._choices[idx])

    def valueFromText(self, text: str) -> int:
        import re

        m = re.search(r"-?\d+", text)
        v = int(m.group()) if m else self.value()
        return self._choices[self._nearest_index(v)]


def task_process(parent, args) -> QProcess:
    """A QProcess (not started) that runs `python <args>` from the project root,
    the way the app runs every task (e.g. ["-u", "run.py", "restart-game"])."""
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONPATH", ROOT)
    env.insert("PYTHONUNBUFFERED", "1")
    # So the task process exits if this app is killed (see run.py).
    env.insert("CAPYGO_PARENT_PID", str(os.getpid()))
    proc = QProcess(parent)
    proc.setWorkingDirectory(ROOT)
    proc.setProcessEnvironment(env)
    proc.setProgram(sys.executable)
    proc.setArguments(args)
    return proc


class TaskScreen(QWidget):
    def __init__(self, name: str, on_back):
        super().__init__()
        self.name = name
        self.on_back = on_back
        self.cls = get_task_class(name)
        self.proc: QProcess | None = None
        self.controls: dict[str, tuple] = {}
        self._param_rows: list = []  # container widgets, disabled while running
        self._pending_on_finish = None  # callback(exit_code) after a launched run
        self.collection_box: QGroupBox | None = None

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

        # --- settings: a title row, then the form ---
        # The form scrolls inside the box, so a long list of switches (Auto Daily)
        # never gets cut off or squeezes the log: it shows in full while it fits and
        # scrolls once it doesn't. Chore switches (params with a section) sit two
        # per row under their section heading; other params keep label | field rows.
        box = QGroupBox()
        box.setObjectName("SettingsBox")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 8, 4, 8)
        box_layout.setSpacing(6)
        box_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)  # no taller than its form
        form_widget = QWidget()
        form_widget.setObjectName("SettingsForm")
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(8)
        section, grid, n = "", None, 0
        for p in self.cls.PARAMS:
            if p.hidden:  # set by the app itself (e.g. the re-run confirmation)
                continue
            if p.section and p.section != section:  # e.g. "Dailies", "Events"
                section = p.section
                heading = QLabel(section)
                heading.setObjectName("FormSection")
                form.addRow(heading)
                holder = QWidget()
                grid = QGridLayout(holder)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setHorizontalSpacing(12)
                grid.setVerticalSpacing(6)
                grid.setColumnStretch(0, 1)
                grid.setColumnStretch(1, 1)
                form.addRow(holder)
                n = 0
            if p.section and p.type == "bool":  # a chore switch: two per row
                switch = QCheckBox(p.label)
                switch.setChecked(bool(p.default))
                switch.setToolTip(p.help)
                grid.addWidget(switch, n // 2, n % 2)
                n += 1
                self.controls[p.key] = (p, switch)
                self._param_rows.append(switch)
                continue
            row_widget, value_widget = self._make_control(p)
            value_widget.setToolTip(p.help)
            self.controls[p.key] = (p, value_widget)
            self._param_rows.append(row_widget)
            form.addRow(p.label, row_widget)

        # Title row; chore switches get Select all / Select none right beside it,
        # outside the scrolling list so they stay in reach. Every chore starts on.
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Settings")
        title.setObjectName("BoxTitle")
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)  # box stays snug
        head.addWidget(title)
        self._switch_keys = [k for k, (p, _) in self.controls.items()
                             if p.type == "bool" and p.section]
        if self._switch_keys:
            head.addSpacing(6)
            for text, on in (("Select all", True), ("Select none", False)):
                b = QPushButton(text)
                b.setObjectName("SmallBtn")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, on=on: self._set_switches(on))
                self._param_rows.append(b)  # disabled while running, like the switches
                head.addWidget(b)
        head.addStretch(1)
        box_layout.addLayout(head)
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidget(form_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        full = form_widget.sizeHint().height()
        scroll.setMaximumHeight(full)            # never taller than the form itself
        scroll.setMinimumHeight(min(full, 150))  # but always shows a few rows
        box_layout.addWidget(scroll)
        root.addWidget(box, 1)

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

        # --- collection actions (only for a task with a hedgemony toggle) ---
        # Shown while the toggle is on: generate the side-by-side comparison plot
        # from everything collected, or clear the collection so it's unambiguous
        # when the collected guilds are reset.
        if "hedgemony" in self.controls:
            self._build_collection_box(root)
            _, toggle = self.controls["hedgemony"]
            toggle.toggled.connect(self._on_hedgemony_toggled)
            self._on_hedgemony_toggled(toggle.isChecked())

        # --- log box: a header row (status label + dry-run) over the log ---
        self.log_box = QGroupBox()
        log_layout = QVBoxLayout(self.log_box)
        log_layout.setContentsMargins(14, 8, 14, 12)
        log_layout.setSpacing(6)

        log_header = QHBoxLayout()
        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("LogStatus")
        self.dry = QCheckBox("Dry run (log clicks without clicking)")
        log_header.addWidget(self.status_label)
        log_header.addStretch(1)
        log_header.addWidget(self.dry)
        log_layout.addLayout(log_header)

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

        if p.type == "str":
            w = QLineEdit()
            w.setText(str(p.default))
            w.setObjectName("ValueField")
            w.setFixedWidth(180)
            if p.help:
                w.setPlaceholderText(p.help)
            return w, w

        if getattr(p, "choices", None):
            spin = ChoiceSpinBox(p.choices)
        else:
            spin = QDoubleSpinBox() if p.type == "float" else QSpinBox()
            spin.setRange(
                p.min if p.min is not None else 0,
                p.max if p.max is not None else 1_000_000,
            )
        if getattr(p, "suffix", ""):
            spin.setSuffix(p.suffix)
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

    def _set_switches(self, on: bool) -> None:
        for key in self._switch_keys:
            self.controls[key][1].setChecked(on)

    def _value(self, p, w):
        if p.type == "bool":
            return w.isChecked()
        if p.type == "str":
            return w.text()
        return w.value()

    # --- collection actions (hedgemony comparison) ------------------------
    def _build_collection_box(self, root) -> None:
        box = QGroupBox("Hedgemony collection")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 20, 14, 12)
        v.setSpacing(10)

        self.collection_status = QLabel()
        self.collection_status.setObjectName("TaskDesc")
        self.collection_status.setWordWrap(True)
        v.addWidget(self.collection_status)

        row = QHBoxLayout()
        self.plot_btn = QPushButton("📊  Generate plot")
        self.plot_btn.setObjectName("Start")
        self.plot_btn.setCursor(Qt.PointingHandCursor)
        self.plot_btn.clicked.connect(self._generate_plot)
        self.clear_btn = QPushButton("🗑  Clear collection")
        self.clear_btn.setObjectName("Stop")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_collection)
        row.addWidget(self.plot_btn)
        row.addWidget(self.clear_btn)
        row.addStretch(1)
        v.addLayout(row)

        self.collection_box = box
        root.addWidget(box)
        self._refresh_collection_status()

    def _on_hedgemony_toggled(self, on: bool) -> None:
        if self.collection_box is not None:
            self.collection_box.setVisible(bool(on))
        if on:
            self._refresh_collection_status()

    def _refresh_collection_status(self) -> None:
        if self.collection_box is None:
            return
        from capygo import store

        entries = store.guilds()
        if entries:
            names = ", ".join(e["name"] for e in entries)
            self.collection_status.setText(
                f"{len(entries)} guild(s) collected: {names}")
        else:
            self.collection_status.setText(
                "No guilds collected yet. Turn on Hedgemony comparison and Start on "
                "each guild's Info screen to collect them.")

    def _generate_plot(self) -> None:
        if self.proc and self.proc.state() != QProcess.NotRunning:
            return
        from capygo import store

        if not store.guilds():
            QMessageBox.information(self, "Generate plot",
                                    "No guilds collected yet. Collect at least one "
                                    "first (Hedgemony comparison on, then Start).")
            return
        self._start_proc(["-u", "run.py", "compare-guild-power"],
                         on_finish=self._open_latest_plot)

    def _open_latest_plot(self, exit_code: int) -> None:
        if exit_code != 0:
            return
        import glob

        from capygo.paths import OUTPUT_DIR

        files = sorted(glob.glob(os.path.join(
            OUTPUT_DIR, "hedgemony_guild_comparison_*.png")))
        if files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(files[-1]))

    def _clear_collection(self) -> None:
        if self.proc and self.proc.state() != QProcess.NotRunning:
            return
        from capygo import store

        n = len(store.guilds())
        if n == 0:
            QMessageBox.information(self, "Clear collection",
                                    "The collection is already empty.")
            return
        resp = QMessageBox.question(
            self, "Clear collection",
            f"Remove all {n} collected guild(s) from the comparison collection?\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        store.clear()
        self._append_text(f"[cleared {n} guild(s) from the collection]\n")
        self._refresh_collection_status()

    # --- run lifecycle ----------------------------------------------------
    def start(self):
        values = {key: self._value(p, w) for key, (p, w) in self.controls.items()}
        extra: list[str] = []
        done = self.cls.already_done_today(values)
        if done:  # once-a-day work that already ran this game day: ask first
            choice = self._confirm_rerun(done)
            if choice == "cancel":
                return
            if choice == "rerun":
                extra = ["-p", "rerun=true"]
            else:  # "skip": switch those dailies off for this run only
                for key, _label, _when in done:
                    values[key] = False
        args = ["-u", "run.py", self.name]
        for key, value in values.items():
            args += ["-p", f"{key}={value}"]
        args += extra
        if self.dry.isChecked():
            args.append("--dry-run")
        self._start_proc(args)

    def _confirm_rerun(self, done) -> str:
        """Ask before repeating once-a-day work. Returns "rerun", "skip" or "cancel".
        "Skip" (run everything else) is offered only when each item is a switch."""
        lines = "\n".join(f"•  {label} (ran at {when})" for _key, label, when in done)
        box = QMessageBox(self)
        box.setWindowTitle("Already ran today")
        box.setText(f"Already ran today:\n{lines}\n\nRun it again?")
        box.setInformativeText("The game day resets at midnight UTC "
                               "(5 PM Pacific in summer, 4 PM in winter).")
        rerun = box.addButton("Run again", QMessageBox.AcceptRole)
        skip = None
        if all(key for key, _label, _when in done):
            skip = box.addButton("Skip it" if len(done) == 1 else "Skip them",
                                 QMessageBox.ActionRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(skip or cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is rerun:
            return "rerun"
        if skip is not None and clicked is skip:
            return "skip"
        return "cancel"

    def _start_proc(self, args, on_finish=None):
        self._pending_on_finish = on_finish
        self.proc = task_process(self, args)
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
            self.status_label.setText("Stopping…")
            self.proc.terminate()  # SIGTERM -> controller sets kill.stop (graceful)
            proc = self.proc
            QTimer.singleShot(
                6000,
                lambda: proc.kill() if proc.state() != QProcess.NotRunning else None,
            )

    def _on_finished(self, exit_code, exit_status):
        self._set_running(False)
        self.status_label.setText("Stopped" if exit_code else "Finished")
        cb, self._pending_on_finish = self._pending_on_finish, None
        if cb:
            cb(exit_code)
        self._refresh_collection_status()  # a collection run may have added a guild

    def _on_error(self, err):
        self._append_text(f"[process error] {err}\n")

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        for row in self._param_rows:
            row.setEnabled(not running)
        self.dry.setEnabled(not running)
        if self.collection_box is not None:
            self.plot_btn.setEnabled(not running)
            self.clear_btn.setEnabled(not running)
        if running:
            self.status_label.setText("Running…")

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
