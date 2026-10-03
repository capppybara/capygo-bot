# CapyGo Bot

Automate repetitive actions in **CapyBara Go!** on macOS. It watches the game
window, finds buttons on screen, and clicks them for you. Four automations so
far: opening **Pet Armament chests**, **auto-running Hard Mode** chapters at a
chosen energy multiple, **exporting a guild's member list** (each member's UID
and power) to a CSV, and mining the **Goblin Miner** minigame floor by floor for
the Capy King statue.

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

## Hard Mode Autorun — how the settings work

The bot runs a Hard Mode chapter over and over for you. Each run it re-selects
the chapter, sets the energy multiple, presses **Start**, waits for the battle to
finish, then does it again. It reads the energy cost inside the Start button to
confirm the multiple is right (and nudges it if a click was missed), and it
double-checks the win/lose screen before counting a run.

Three settings control it:

- **Chapter** — which Hard Mode chapter to run (default `180`).

- **Energy multiple** — how much energy (and reward) per run: `1x`, `2x`, `3x`,
  `5x`, `10x`, or `20x` (default `20x`). The arrows step through only those
  values.

- **Number of runs** — how many times to run before it stops (default `10`).

It stops early if a run is **lost**, if there isn't **enough energy** to start,
or if **Hard Mode is off**.

Before starting, be on the **Hard Mode screen** (chapter + **Start** visible)
with **Hard Mode on** — the switch next to Start must show the **red** icon, not
blue. If it's blue, the bot stops and asks you to turn Hard Mode on first.

## Get Guild Member List — how it works

The bot walks every member on a guild's **Info** screen and saves each one's UID
and power to a spreadsheet. For each member it opens their character screen,
copies the UID with the in-game copy button (exact, not guessed), reads the
power shown under the character, then moves to the next. It scrolls the list
itself and de-duplicates by UID, so it captures everyone exactly once.

There's nothing to set up: it reads the guild name off the screen (you can type
it in the one optional box if you'd rather name the file yourself). If the name
isn't in the English alphabet (a Korean name, say, which won't read cleanly), it
uses the guild's numeric **ID** instead so the file still gets a sensible name.

The result is written to `~/Downloads/capy-bot/capygo_<guild>_member_list.csv` with
columns `guild_name, member_uid, power`. Power is a plain number **in trillions**
with no unit letter (so `905.85B` is stored as `0.90585`, `1.38T` as `1.38`). If
you stop it early, it still saves whoever was collected so far.

**Hedgemony comparison mode** (the toggle in the app, or `-p hedgemony=true`): a
fast, read-only pass. It scrolls the list and reads the power shown under each name
(the sword-icon value on the card) without opening anyone, then adds up the highest
powers and reports the total. Use `-p top_n=25` to set how many of the top members to
sum (default 25). It writes a short summary to
`~/Downloads/capy-bot/capygo_<guild>_top<N>_power.csv` (rank, power, and a `TOP_N_SUM` row)
instead of doing the full per-member walk. It cross-checks the number of cards it
read against the guild's member count, so a miss is flagged in the log.

Before starting, open the guild's **Info** screen — the one titled "Guild Info"
with the member list.

Each hedgemony run also adds that guild's top-N to a local collection
(`data/guild_power.json`), keyed by guild ID so re-running a guild just updates it.
Collect several guilds this way (open each one's Info screen, Start with the toggle
on), then use the **Generate plot** button to graph them together and **Clear
collection** to reset when you're done.

## Comparison plot (Generate plot / Clear collection)

With Hedgemony comparison on, the Get Guild Member List screen shows a **Hedgemony
collection** box with the guilds collected so far and two buttons:

- **Generate plot** draws every collected guild onto one graph and saves it to
  `~/Downloads/capy-bot/hedgemony_guild_comparison_<YYYYMMDDHHMMSS>.png` (timestamped, so each
  run is kept), then opens it: one line per guild over rank 1..N (its top powers,
  strongest first), so you can see which guild is stronger and how top-heavy each is.
  The legend labels each line `guild_name (total T)` with that guild's top-N total.
- **Clear collection** empties the collection (with a confirmation), so it's
  unambiguous when the collected guilds are reset.

The plot doesn't touch the game, so the game can be closed for it. From the CLI the
same graph is produced by `./run.sh compare-guild-power`.

## Goblin Miner — how it works

The bot plays the **Goblin Miner** minigame floor by floor. Each floor it digs
the stone grid to uncover the hidden **Capy King statue**, unlocks and claims
the statue, then takes the doorway down to the next floor. It keeps going until
the pickaxe meter runs out.

Each floor it:

1. Mines a fixed **6-tile pattern** (the spots a large statue is most likely to
   sit on, so a big statue shows up early), stopping the moment a statue appears.
2. Matches the uncovered piece against a library of fragment templates to work
   out the statue's **size** (1×1, 2×2, or 2×3) and which part is showing, which
   pins the whole statue's footprint on the grid. If nothing showed in the
   pattern, it presses **Auto-Mine** to dig until the statue surfaces, then
   identifies it the same way.
3. Uncovers the rest of the footprint (only those tiles, never a halo), opens the
   statue, taps to resolve its four rarity orbs, claims the reward, and closes
   the summary.
4. Claims any leftover **cracked blocks** (buried rewards), then clicks the
   **doorway** that appears at the footprint's top-left, dropping to the next
   floor.

Along the way it also grabs any **bomb** it uncovers — a bomb clears its whole
row and column, which helps expose the statue.

**When picks run out** it claims the free **Pickaxe +15** refill at the bottom of
the screen and keeps digging; once that refill is used up, it stops. One setting,
**Stop below picks**, lets you keep a reserve (stop before a floor once the meter
is at or below it); `0` mines until the board can no longer be cleared.

Before starting, open the **Goblin Miner** screen (the stone grid titled "Goblin
Miner").

## Auto Daily — how it works

Runs your daily chores in one go, in a fixed order. The task screen has one switch
per daily, so you can turn any of them off. Each daily is also its own task you can
run alone from the command line.

Every daily starts and ends on the home screen: the main **Adventure** screen with
the Start button showing and the capy switch next to it set to blue. Auto Daily gets
there before the first daily. After each daily, finished or not, it backs out to the
home screen and moves on to the next one. To get home it checks, in order: if the
capy switch is red (the other game mode), it taps the switch back to blue; if a round
X close button is showing, it taps that; if a "Tap to close" popup is up, it dismisses
it; otherwise it taps the back arrow at the bottom-left. Failed dailies are listed in
the log at the end. If it still can't reach the home screen, it stops.

Each daily runs once per game day, and each tracks that on its own. The game day
resets at midnight UTC (5 PM Pacific in summer, 4 PM in winter). If you press Start
and a switched-on daily already ran today, the app asks first: **Run again**, **Skip
it** (run the rest without it), or **Cancel**. From the command line, an already-run
daily is skipped unless you add `-p rerun=true`. Dry runs don't count as a run.

Before starting, be on the main Adventure screen.

Dailies so far:

- **Energy claim** — taps the energy bolt at the top to open the energy shop,
  watches the free ad twice, buys energy with gems twice, claims the Daily Pack,
  and closes the shop. It checks the shop is actually open before each tap.
  (Re-running it the same day would buy energy with gems again, which the
  once-a-day check prevents unless you confirm.)
- **Adventure assistant** — taps the floating robot bubble to open the Adventure
  Assistant, then on the Shortcut, Feature and Shop tabs taps Execute, waits for the
  run to finish (the button turns from "Interrupted" to "Completed", usually ~5s,
  10s max), taps Completed, and finally closes the assistant. It finds Execute by
  reading the button bar, since the Shop tab has an extra "Add Item" button.
- **Daily shop** — taps the leftmost bottom-bar icon to open the Shop. On the
  Treasure tab it taps "Get 1" once on the Gem Chest and once on the Mythic
  Treasure Chest (the first Gem Chest draw of the day uses a free key; later ones
  cost gems), dismissing each reveal. On the Pack Shop tab it claims the Free Pack
  if it's still 1/1. Then it goes home with the crossed-swords tab. It never
  touches Top Up or the gem-priced packs.
- **Claim cards** — taps Privilege Card (top of the left bar), taps Claim all,
  dismisses the rewards, and goes back with the back arrow.

Every tap in a daily is followed by a ~1 second pause so the game can catch up.

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
    pet_armament_chest.py  chest-opening task
    hard_mode_autorun.py   Hard Mode auto-run task (OCR + color checks)
    get_guild_member_list.py  guild members -> CSV (OCR + clipboard copy)
    goblin_miner.py        Goblin Miner minigame: mine floors for the statue
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
./run.sh hard-mode-autorun -p chapter=180 -p energy_multiple=20 -p runs=2
./run.sh get-guild-member-list          # exports to ~/Downloads/capy-bot
./run.sh get-guild-member-list -p hedgemony=true            # collect top 25 powers
./run.sh get-guild-member-list -p hedgemony=true -p top_n=10 # collect top 10 powers
./run.sh compare-guild-power            # graph all collected guilds
./run.sh goblin-miner -p min_picks=0    # mine floors until picks run out
./run.sh auto-daily                     # run every daily
./run.sh auto-daily -p energy_claim=false  # skip one daily
./run.sh energy-claim                   # run one daily on its own
./run.sh auto-daily -p rerun=true       # run dailies that already ran today again
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
