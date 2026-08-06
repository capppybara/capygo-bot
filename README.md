# capygo-bot

A small perception-action framework for automating repetitive actions in
CapyBara Go! running in a native Mac window.

> **Tested only on a MacBook Pro M3 16" using the native Capybara Go! Mac app.**
> No guarantees it works in a different setup (other Macs, window sizes, an
> emulator, or a mirrored phone).

Each automation is a **task** (a plugin). Coordinates are **window-relative**,
so moving or resizing the game window does not break anything. Buttons are
found by **template matching** against small reference PNGs.

> **While a task runs, keep the game window in front with its buttons visible.**
> The bot clicks at on-screen coordinates, so if a button is hidden behind
> another window (or the game is minimized / on another Space), the click lands
> on the wrong place and the task stalls. The game does not need to be full
> screen, just unobstructed where the buttons are.

## Layout

```
run.py                     CLI entry point
config.yaml                window owner, loop timing, thresholds, safety
capygo/
  window.py                find the game window + live bounds
  capture.py               window -> BGR image
  perception.py            template matching (Match objects)
  input.py                 synthetic clicks (Quartz)
  safety.py                kill switch + jittered delays
  task.py                  Task / StepTask base classes + registry + Context
  controller.py            wires config + window + task together
  tasks/
    pet_armament_chest.py  first task
templates/<task-name>/     button PNGs for each task
tools/
  list_windows.py          find the window owner name for config
  grab_window.py           save a window screenshot (to crop templates)
```

## Setup

```bash
cd capygo-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### macOS permissions (one time)

Grant these to the app that runs the script (Terminal, iTerm, or VS Code),
under System Settings > Privacy & Security. Restart the terminal after.

- **Screen Recording** — required to capture the window.
- **Accessibility** — required to post clicks and to run the kill-switch listener.

## Desktop UI

A themed PySide6 app: a home screen of task cards, and per-task screens with a
config form (built from the task's `PARAMS`), Start/Stop, and a live log.

Launch it with the run script (creates `.venv` and installs deps on first run):

```bash
./run.sh
```

Or double-click `launch.command` in Finder. Click a task, set its options, press
**Start**. The app runs the task as a subprocess and streams its log into the
panel; **Stop** ends it gracefully. New tasks appear on the home screen
automatically once registered.

The same script runs a task headless on the command line (handy for scripting):

```bash
./run.sh pet-armament-chest -p runs=20 -p failure_threshold=2
```

## First run

```bash
# 1. Confirm the window is found (owner is already set in config.yaml)
python tools/list_windows.py capy

# 2. Confirm capture + permissions by saving a screenshot
python tools/grab_window.py

# 3. Run for real (press Esc any time to stop). Start with one chest:
python run.py pet-armament-chest -p runs=1

# 4. Once happy, run many with your own threshold:
python run.py pet-armament-chest -p runs=20 -p failure_threshold=2
```

Templates for `pet-armament-chest` are already captured in
`templates/pet-armament-chest/` (`unlock_button`, `free_upgrade_button`,
`open_button`, `upgrade_button`, `check`, `cross`, `question`). Recapture any of
them with `tools/grab_window.py` + Preview if the game art changes.

## Adding a task

1. Create `capygo/tasks/my_task.py`:

   ```python
   from ..task import Context, StepTask, register

   @register("my-task")
   class MyTask(StepTask):
       def step(self, ctx: Context) -> bool:
           btn = ctx.find("some_button")
           if btn.found:
               ctx.click_match(btn)
               return True
           return False   # stop
   ```

2. Import it in `capygo/tasks/__init__.py`.
3. Put its templates in `templates/my-task/`.

Tasks that need a different click strategy can subclass `Task` directly and
implement `run(ctx)` for full control instead of the step loop.

## Safety

- Press the kill key (default **Esc**) to stop immediately.
- `max_iterations` in config caps every run.
- `--dry-run` logs clicks without performing them.
- Automating a game may violate its terms of service. Use on your own account
  at your own risk.
```
