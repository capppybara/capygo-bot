# CapyGo Bot

Automate repetitive actions in **CapyBara Go!** on macOS. It watches the game
window, finds buttons on screen, and clicks them for you. The first (and only)
automation so far opens **Pet Armament chests**.

> **Tested only on a MacBook Pro M3 16" using the native Capybara Go! Mac app at
> its default window size.** No guarantees it works in a different setup (other
> Macs, window sizes, an emulator, or a mirrored phone).

## Run it

**Before the first run:** open Capybara Go! in its Mac window, and grant your
terminal two macOS permissions under **System Settings → Privacy & Security**
(then restart the terminal):

- **Screen Recording** — so it can see the game window.
- **Accessibility** — so it can click and so the Esc stop-key works.

Then launch the app:

```bash
./run.sh
```

(The first run creates a virtual environment and installs dependencies, so it
takes a minute. You can also double-click `launch.command` in Finder.)

Pick a task, set its options, and press **Start**. The log panel shows every
click and decision live. **Stop** ends it. Tick **Dry run** to watch what it
*would* click without actually clicking.

> **Keep the game window in front with its buttons visible while it runs.** The
> bot clicks at on-screen positions, so if a button is hidden behind another
> window (or the game is minimized or on another Space), the click misses and the
> task stalls. The window doesn't need to be full screen, just unobstructed.

## Pet Armament Chest — how the settings work

The bot works one chest at a time: it hits **Unlock**, takes the **3 free
upgrades**, then decides whether to keep paying to upgrade or to **Open** (collect)
the chest and move on. Each upgrade either succeeds (✓) or fails (✗).

Three settings control it:

- **Total runs** — how many chests to open before it stops.

- **Free failure threshold** — after the 3 free upgrades, if the number of
  failures is **this many or more**, it opens the chest instead of spending gems
  on paid upgrades. Lower = pickier (bails on slightly-unlucky chests); higher =
  more willing to pay. **`0` means free upgrades only** — it never pays, just
  takes the free result and moves on.

- **Total failure threshold** — once you're in the paid stage, the moment the
  **total** failures (free + paid) reach **this many**, it opens the chest and
  starts the next one.

Both thresholds mean the same thing: *"give up on this chest once failures reach
this number."* Defaults are `10 / 2 / 2`.

Before starting, make sure you're on the **locked chest screen with the Unlock
button** showing.

## Notes

- Press **Esc** any time to stop (needs the Accessibility permission above).
- Automating a game may violate its terms of service. Use on your own account at
  your own risk.
- Every run also writes a timestamped log to `logs/`.

---

## Developer notes

Each automation is a **task** (a plugin). Coordinates are **window-relative**, so
moving or resizing the game window doesn't break anything. Buttons are found by
**template matching** against small reference PNGs. The UI auto-discovers tasks
from a registry and builds each task's settings form from its declared params, so
adding a task needs no UI changes.

### Layout

```
run.py                     CLI entry point (a task run, headless)
run.sh                     launcher: GUI with no args, CLI with args
config.yaml                window owner, match threshold, kill key
capygo/
  window.py                find the game window + live bounds
  capture.py               window -> BGR image (Quartz)
  perception.py            template matching (Match, RelRect region search)
  input.py                 synthetic clicks (Quartz)
  safety.py                Esc kill switch
  task.py                  Task / StepTask base classes + registry + Context
  controller.py            wires config + window + task; per-run logging
  tasks/
    pet_armament_chest.py  first task
templates/<task-name>/     button/icon PNGs matched at runtime
ui/                        PySide6 app (home + task screens, theme, assets)
tools/
  list_windows.py          find the window owner name for config.yaml
  grab_window.py           save a window screenshot (to crop new templates)
```

### Manual setup (instead of run.sh)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ui.app                 # GUI
```

### Command line

`run.sh` with arguments runs a task headless (no GUI):

```bash
./run.sh pet-armament-chest -p runs=20 -p free_failure_threshold=2 -p failure_threshold=2
./run.sh pet-armament-chest -n          # --dry-run
./run.sh --list                         # list tasks and their params
```

Handy while building templates:

```bash
python tools/list_windows.py capy       # confirm the window owner
python tools/grab_window.py             # save logs/window.png to crop from
```

### Adding a task

1. Create `capygo/tasks/my_task.py`:

   ```python
   from ..task import Context, StepTask, register

   @register("my-task")
   class MyTask(StepTask):
       TITLE, ICON = "My Task", "🎯"
       def step(self, ctx: Context) -> bool:
           btn = ctx.find("some_button")
           if btn.found:
               ctx.click_match(btn)
               return True    # keep going
           return False       # stop

   ```

2. Import it in `capygo/tasks/__init__.py`.
3. Put its templates in `templates/my-task/` (and optionally an icon at
   `ui/assets/my-task.png`, else the `ICON` emoji is used).

`StepTask` fits simple "click until gone" loops. For a stateful strategy
(counters, stages), subclass `Task` and write `run(ctx)` yourself — that's what
`pet_armament_chest` does. `Context` gives you `frame()`, `find()`,
`click_match()`, `click_rel()`, `should_stop()`, and template helpers.

The task screen and CLI both read the task's `PARAMS`, so declaring a param is
all it takes to get a labeled input in the UI and a `-p key=value` flag.
