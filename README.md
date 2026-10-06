# CapyGo Bot

CapyGo Bot plays repetitive parts of **CapyBara Go!** for you on macOS. It
watches the game window, reads what is on screen, and taps for you. You pick an
automation in a desktop app, set a few options, and press Start.

> **Tested only on a MacBook Pro M3 16" with the native Capybara Go! Mac app at
> its default window size.** Other Macs, window sizes, emulators, or a mirrored
> phone may not work.

## Contents

- [Getting started](#getting-started)
- [Automations](#automations)
- [Auto Daily](#auto-daily)
- [Auto Gulu](#auto-gulu)
- [Get Guild Member List](#get-guild-member-list)
- [Goblin Miner](#goblin-miner)
- [Hard Mode Autorun](#hard-mode-autorun)
- [Martial Arts Tournament](#martial-arts-tournament)
- [Pet Armament Chest](#pet-armament-chest)
- [Files it writes](#files-it-writes)
- [Developer guide](#developer-guide)

## Getting started

### 1. Grant permissions (once)

In **System Settings → Privacy & Security**, give the app you launch the bot from
(Terminal, or your terminal app) these permissions, then restart it:

- **Screen Recording**, so the bot can see the game window.
- **Accessibility**, so it can tap.
- **Input Monitoring**, so the Esc stop key works.

### 2. Launch the app

Open Capybara Go! in its Mac window, then run:

```bash
./run.sh
```

The first launch creates a virtual environment and installs dependencies, so it
takes a minute. You can also double-click `launch.command` in Finder.

### 3. Run an automation

1. Pick an automation on the home screen.
2. Set its options. Each screen says which game screen to start on.
3. Press **Start**. The log shows every tap and decision as it happens.

Tick **Dry run** (next to the log status) to see what it would tap without
tapping anything.

**Keep the game window visible while it runs.** The bot taps screen positions.
A window on top of the game, a minimized game, or a game on another Space makes
those taps miss. The window does not need to be full screen.

### Stopping

Any of these stops a run within a second:

- the **Stop** button in the app;
- the **Esc** key (needs Input Monitoring);
- **Ctrl+C**, when you run it from the command line.

## Automations

| Automation | What it does | Start on |
|---|---|---|
| [Auto Daily](#auto-daily) | Runs your daily chores, events, guild and menu chores in one go | The main Adventure screen |
| [Auto Gulu](#auto-gulu) | Plays Gulu Mine with a friend, hosting or joining | Anywhere |
| [Get Guild Member List](#get-guild-member-list) | Exports a guild's members (UID and power) to a CSV, or collects top powers to compare guilds | A guild's Guild Info screen |
| [Goblin Miner](#goblin-miner) | Mines Goblin Miner floors for the Capy King statue | The Goblin Miner grid |
| [Hard Mode Autorun](#hard-mode-autorun) | Runs a Hard Mode chapter over and over | The Hard Mode screen |
| [Martial Arts Tournament](#martial-arts-tournament) | Fights the Qualifiers opponents worth the most points that you can beat, now or at 6:50 AM | Anywhere |
| [Pet Armament Chest](#pet-armament-chest) | Opens Pet Armament chests, upgrading when it is worth it | The locked chest screen |

## Auto Daily

Auto Daily runs your daily chores in one go and leaves the game on the home
screen. The chores are in four groups, and each chore has its own on/off switch
in the app (**Select all** and **Select none** set them all at once).

**Start on:** the main Adventure screen.

### How a run works

The groups always run in this order: Dailies, Events, Guild, Menu. The Menu
group stays last so its daily-tasks claim picks up the tasks the other chores
finished.

Each group has a base screen. Every chore in the group starts there and returns
there when done, so the next chore carries on from it.

| Group | Base screen |
|---|---|
| Dailies | The home screen: the Adventure screen with Start showing and the capy switch next to it blue |
| Events | The Events screen (Events button, bottom-right of home) |
| Guild | The guild screen (Guild button, left of Start) |
| Menu | The menu drawer (the list icon under your profile picture) |

To get back to a base screen, the bot backs out step by step. If the capy switch
is red (the other game mode), it taps the switch back to blue. Otherwise it
closes an open X, dismisses a "Tap to close" popup, or taps the back arrow.

A chore that fails is logged, its screen is saved to `logs/`, and the run moves
on to the next chore. If the bot cannot reach a group's base screen, it skips
that group and carries on with the next one.

### Once a day

Each chore runs once per game day and tracks that on its own. The game day
resets at midnight UTC (5 PM Pacific in summer, 4 PM in winter). If a switched-on
chore already ran today, the app asks before starting: **Run again**, **Skip
it**, or **Cancel**. Dry runs do not count as a run.

### End-of-run summary

The log ends with a summary: what finished, what was skipped, and a **Needs your
attention** list. That list has everything a chore flagged for you to handle by
hand, such as the arena running out of beatable opponents. It also lists every
chore that failed, with the path of its saved screenshot.

### Dailies

| Chore | What it does |
|---|---|
| Energy claim | Opens the energy shop (bolt at the top). Watches the free ad twice, buys energy with gems twice, claims the Daily Pack, closes the shop. |
| Adventure assistant | Opens the floating robot bubble. On the Shortcut, Feature and Shop tabs it taps Execute, waits for Completed (10 seconds at most), and taps it. Then closes the assistant. |
| Daily shop | Opens the Shop (leftmost bottom-bar icon). On Treasure it taps Get 1 once on the Gem Chest and once on the Mythic Treasure Chest. On Pack Shop it claims the Free Pack. Never touches Top Up or gem-priced packs. |
| Claim cards | Opens Privilege Card (top of the left bar) and taps Claim all. |
| Claim calendar | Opens Calendar (right-hand bar) and claims the reward chest. |
| Capymon | Equip (helmet) → Capymon. See below. |

**Capymon** does three things on the Card Table, then one in the Grand Voyage:

1. **Gift packs:** claims the free welfare package (AD) and buys the Gem Work
   Gift Pack (500 purple cubes). It finds each pack by its row title, because
   sold-out packs move down the list.
2. **Draws:** taps Draw 10 times until the game refuses, first with tickets,
   then with the day's purple-cube draws. It skips each draw animation.
3. **Points chests:** claims every points-bar chest with a red "!".
4. **Travel:** in Capy Grand Voyage → Travel, it collects a finished travel and
   sends the team out again for 20 hours.

### Events

| Chore | What it does |
|---|---|
| Tower challenge | Challenge tab → Tower Challenge. Taps Challenge 5 times, waiting for each Victory or Defeat screen. |
| Dungeon dive vouchers | Challenge tab → Dungeon Dive. Buys 2 challenge vouchers with gems (300). The game allows 2 a day. |
| Goblin miner | Challenge tab → Goblin Miner. Runs the [Goblin Miner](#goblin-miner) automation until the picks run out. |
| Arena attacks | Arena tab → Arena. Attacks up to 5 times (see below). |
| Holy Grail War likes | Arena tab → Holy Grail War. Likes both champions on the Supreme, Dauntless and Rising Star plazas. |
| Martial Arts likes | Arena tab → Martial Arts Tournament. Likes all three champions in the Supreme, Valiant and Novice zones. |

**Arena attacks** picks each opponent by these rules:

1. Only opponents below 1.2x your power count. B and T are converted (1T = 1000B).
2. Among those, it fights the one with the most points, if that is more than 10
   points above yours.
3. If none qualifies, it uses the Free Refresh once (only while it is free) and
   looks again.
4. If there is still none, it fights the one below 1.2x with the most points.
5. If nobody is below 1.2x, it stops and flags it for you.

It skips each fight and taps OK on the result. When you are out of tickets, the
game offers to sell one. The bot closes that offer and finishes. It never buys
tickets.

### Guild

| Chore | What it does |
|---|---|
| Guild hall donations | Guild Hall → Donate. Donates until "Chances Left Today" reaches 0: 5 a day, the first free, then 25 purple cubes each. |
| Guild trade plunder | Guild Trade → Others' Trades. Plunders boats until "Looted today" reaches 4/4 (see below). |

**Guild trade plunder** looks at the gilded boats (gold barge with a crown) and
golden boats (orange sail) on the map. It plunders a boat only if all of these
hold:

- the panel's banner is UR orange (the map sometimes shows a boat as gold
  wrongly);
- the boat can still be plundered;
- its power is under 6T;
- a golden chest or 200 badges sits in the first two cargo slots.

If the sea has both a chest boat and a badge boat, it takes the chest. A lost
fight just moves on. With no suitable boat it taps the free Refresh, up to 30
times, then flags it.

### Menu

| Chore | What it does |
|---|---|
| Log In reward | Opens Log In and claims the day whose header reads Claim. |
| Black Market deals | Buys Silver Chest, Gold Chest, Pet Chest, Gold Key, Pet Egg and Gold Horseshoe only when their value tag is 40% or more, then claims the free gold at the bottom. |
| Daily tasks claim | Opens Tasks and claims every finished daily task. Never taps Claim All. |

### Not built

- **Maybe later:** Seal Battle (Arena tab) and Guild Raid.
- **Nothing to automate:** Gulu Mine and the Dungeon tab have no daily chores.
  Gulu Mine has its own automation, [Auto Gulu](#auto-gulu).

## Auto Gulu

Auto Gulu plays Gulu Mine with one friend for the number of runs you set. It can
host the run or join the friend's run.

**Start on:** anywhere. If the game is already on the Gulu team screen with your
friend in it, it carries on from there.

| Setting | Default | Mode | Meaning |
|---|---|---|---|
| Join instead of host | off | both | Off: host. On: join the friend's run. |
| Friend | pinkdolly | both | Who to invite (hosting), or whose invite to accept (joining) |
| Runs | 4 | both | How many runs to play |
| Difficulty (hosting) | 25 | hosting | The Gulu Mine difficulty to host |
| Stay (hosting) | off | hosting | Play each run to the end instead of quitting it (not built yet) |

### Hosting

For each run, the bot:

1. Opens Events → Challenge → Gulu Mine. The panel opens on your highest
   difficulty, so it taps ◀ until the number matches your setting.
2. Taps Go to Team, then Invite, and invites the friend from the Friend tab.
3. Checks every 10 seconds for the friend to join, for up to 30 minutes. It
   never invites twice. On a timeout it stops.
4. Taps Start Challenge, picks the top two skills on both skill screens, then
   quits the run at once: Skills → home → OK. It dismisses the result and lands
   on the home screen.

The skill screens always look the same, so the bot taps fixed positions with
set waits. The Skills panel does not pause the run, so the quit has to be quick.

### Joining

For each run, the bot:

1. Checks every 10 seconds, for up to 30 minutes, for the "New Invitation"
   banner. It opens it, makes sure the invitations are Gulu Mine's, and accepts
   the friend's invite. It never taps Reject or "No longer show".
2. Plays the run to the end. Every 5 seconds it looks for a skill screen and
   picks the top cards: two picks on each of battle 1's two screens, one pick
   on each later screen.
3. Taps OK on the Victory or Defeat screen.

Where the result screen leaves you tells the bot whether the host stayed. Back
on the Gulu team screen means the host stayed, so it waits for the next start.
Back home means the host left, so it looks for the next invite.

## Get Guild Member List

This automation saves every member of a guild, with their UID and power, to a
CSV.

**Start on:** the guild's Guild Info screen (the one with the member list).

| Setting | Default | Meaning |
|---|---|---|
| Guild name (optional) | blank | Name for the file. Blank reads it from the screen. |
| Hedgemony comparison | off | Also collect the guild's top powers to compare guilds (see below) |
| Top N to sum | 25 | How many of the highest powers hedgemony mode adds up |

For each member it opens their character screen, copies the UID with the
in-game copy button, reads the power under the character, and closes the screen.
It scrolls the list itself and skips repeats by UID, so everyone appears exactly
once.

If the guild name is not in the English alphabet, the file uses the guild's
numeric ID instead.

**Output:** `~/Downloads/capy-bot/capygo_<guild>_member_list.csv` with columns
`guild_name, member_uid, power`. Power is in trillions with no unit letter, so
`1.38T` is stored as `1.38` and `905.85B` as `0.90585`. If you stop early, it
still saves the members read so far.

### Hedgemony comparison

Hedgemony mode does the same walk, then also:

- writes `~/Downloads/capy-bot/capygo_<guild>_top<N>_power.csv` with the top N
  members (`guild_name, rank, member_uid, power_trillions`) and a total row;
- adds the guild's top N to a local collection, so you can graph several guilds
  together.

If you stop a hedgemony run early, it discards that guild's partial results.

With hedgemony on, the screen shows a **Hedgemony collection** box with the
guilds collected so far:

- **Generate plot** draws every collected guild on one graph, one line per guild
  over rank 1 to N, and opens it. The legend shows each guild's top-N total. The
  graph is saved as
  `~/Downloads/capy-bot/hedgemony_guild_comparison_<YYYYMMDDHHMMSS>.png`.
- **Clear collection** empties the collection, after a confirmation.

The plot does not need the game open.

## Goblin Miner

Goblin Miner mines the Goblin Miner minigame floor by floor until the pickaxe
meter runs out.

**Start on:** the Goblin Miner screen (the stone grid).

| Setting | Default | Meaning |
|---|---|---|
| Stop below picks | 0 | Stop before a floor once the picks are at or below this. 0 mines until the picks run out. |

On each floor the bot:

1. Mines a fixed 6-tile pattern. A 2x2 or 2x3 statue always sits under one of
   these tiles. If no statue shows, it uses Auto-Mine to find the 1x1 statue.
2. Matches the uncovered piece against saved statue pieces to learn the statue's
   size and position.
3. Uncovers the rest of the statue, opens it, resolves its rarity orbs, and
   claims the reward.
4. Claims any cracked blocks (buried rewards), then takes the doorway to the
   next floor.

It also taps any bomb it uncovers, since a bomb clears its row and column. When
the picks run out, it claims the free Pickaxe +15 refill and keeps going until
the refills are used up.

## Hard Mode Autorun

Hard Mode Autorun runs one Hard Mode chapter over and over at a set energy
multiple.

**Start on:** the Hard Mode screen with Hard Mode on (the switch next to Start is
red, not blue).

| Setting | Default | Meaning |
|---|---|---|
| Chapter | 180 | The Hard Mode chapter to run |
| Energy multiple | 20x | Energy (and reward) per run: 1x, 2x, 3x, 5x, 10x or 20x |
| Number of runs | 10 | How many runs before it stops |

Each run it selects the chapter, sets the multiple, presses Start, and waits for
the result. It checks the energy cost on the Start button to confirm the
multiple. It stops early when a run is lost, when energy runs short, or when
Hard Mode is off.

## Martial Arts Tournament

Martial Arts Tournament spends your Qualifier tickets on the opponents worth the
most points that you can beat. It runs now, or waits and runs just before the
round closes (sniping).

**Start on:** anywhere. It opens Events → Arena → Martial Arts Tournament →
Schedule (the Qualifiers) itself.

| Setting | Default | Meaning |
|---|---|---|
| Your CP (T) | 5.23 | Your power in trillions; opponents are compared against it |
| Power ratio | 1.1 | Fight only opponents below this x your CP |
| Sniping mode | off | Wait for 6:50 AM Pacific and use every attack then |
| Max attacks (0 = all) | 0 | Stop after this many attacks; 0 uses every ticket |

For each attack the bot:

1. Scrolls the list a little so all 6 opponents show, and reads each one's power
   and points. B and T are converted (1T = 1000B).
2. Fights the one with the most points whose power is below the ratio x your CP.
3. If none qualifies, taps Refresh (free or paid) and looks again, raising the
   ratio by 0.1 each time: 1.1, 1.2, up to 1.6 after 5 refreshes. If there is
   still none, it stops.
4. Skips the fight and taps OK on the result, like the arena.

**Normal mode** attacks until the tickets run out. **Sniping mode** waits for the
next 13:50 UTC: 6:50 AM Pacific in summer, 5:50 AM in winter. The round closes at
14:00 UTC and challenges stop 5 minutes before that, so it has 5 minutes. It
stops starting fights 20 seconds before the cutoff. One attack takes about 15
seconds, so 9 tickets take about 2.5 minutes. While it waits it keeps the Mac
awake; the app must stay open and the game window visible.

## Pet Armament Chest

Pet Armament Chest opens chests one at a time. For each chest it takes the 3
free upgrades, then decides whether to pay for more upgrades or open the chest.
Each upgrade succeeds (✓) or fails (✗).

**Start on:** the locked chest screen with the Unlock button.

| Setting | Default | Meaning |
|---|---|---|
| Total runs | 10 | How many chests to open |
| Free failure threshold | 2 | After the free upgrades, open the chest if it has this many failures or more. 0 means free upgrades only, never pay. |
| Total failure threshold | 2 | In the paid stage, open the chest once total failures reach this |

## Files it writes

| Path | What |
|---|---|
| `logs/<task>-<time>.log` | A log of every run |
| `logs/failed-<chore>-<time>.png` | The screen when an Auto Daily chore failed |
| `~/Downloads/capy-bot/` | CSV exports and comparison graphs |
| `data/daily_runs.json` | When each Auto Daily chore last ran |
| `data/guild_power.json` | The hedgemony collection |

Automating a game may break its terms of service. Use it on your own account at
your own risk.

---

## Developer guide

### How it works

Each automation is a **task** registered in a registry. The app finds the tasks
and builds each settings form from the task's declared parameters, so a new task
needs no UI changes.

- **Positions are window-relative** (fractions of the window), so moving the
  window does not break anything.
- **Screens are recognized** by text recognition (Apple Vision OCR), by color
  checks, or by matching small reference images (`templates/`).
- **Taps** are synthetic mouse events. Each one brings the game window to the
  front first.
- **The app runs each task as a separate process** (`run.py`), and streams its
  log into the window. Stop sends that process a stop signal.

### Project layout

```
run.py                      command-line entry point (runs one task)
run.sh                      launcher: the app with no arguments, a task with arguments
config.yaml                 window owner name, match threshold, stop key
capygo/
  window.py                 find the game window and its position
  capture.py                capture the window as an image
  perception.py             template matching and OCR
  input.py                  synthetic taps, drags and cursor moves
  safety.py                 the Esc stop key
  task.py                   Task base classes, Param, the registry, Context
  controller.py             wires config, window and task together; run logs
  paths.py, store.py        output folder; the hedgemony collection
  tasks/
    auto_daily.py           Auto Daily: the four groups and their order
    daily.py                shared chore engine: going home, once-a-day, summary
    daily_*.py              the Dailies
    event.py, event_*.py    the Events screen and each event
    guild.py, guild_*.py    the guild screen and each guild chore
    menu.py, menu_*.py      the menu drawer and each menu chore
    auto_events.py, auto_guild.py, auto_menu.py   each group's chore list
    _event_template.py, _guild_template.py, _menu_template.py   copy to add a chore
    auto_gulu.py            Auto Gulu
    get_guild_member_list.py, compare_guild_power.py
    goblin_miner.py, hard_mode_autorun.py, pet_armament_chest.py
    martial_arts_tournament.py
templates/<task-name>/      reference images matched at runtime
ui/                         the PySide6 app: home and task screens, theme, icons
tools/
  list_windows.py           find the game window's owner name for config.yaml
  grab_window.py            save a window screenshot to crop new templates from
```

### Command line

`run.sh` with arguments runs one task without the app. `-p key=value` sets a
setting, `-n` is a dry run, and `--list` shows every task and its settings.

```bash
./run.sh --list
./run.sh auto-daily                        # every chore
./run.sh auto-daily -p energy_claim=false  # skip one chore
./run.sh auto-daily -p rerun=true          # also re-run chores that ran today
./run.sh energy-claim                      # one chore on its own
./run.sh auto-events                       # only the Events group (also auto-guild, auto-menu)
./run.sh auto-gulu -p difficulty=25 -p friend=pinkdolly -p runs=4
./run.sh auto-gulu -p join=true -p runs=4
./run.sh get-guild-member-list -p hedgemony=true -p top_n=25
./run.sh compare-guild-power               # graph the hedgemony collection
./run.sh goblin-miner -p min_picks=0
./run.sh hard-mode-autorun -p chapter=180 -p energy_multiple=20 -p runs=10
./run.sh martial-arts-tournament -p my_cp=5.23 -p ratio=1.1
./run.sh martial-arts-tournament -p sniping=true   # waits for 6:50 AM Pacific
./run.sh pet-armament-chest -p runs=20 -n
```

Manual setup, instead of `run.sh`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m ui.app
```

### Adding an automation

1. Create `capygo/tasks/my_task.py`:

   ```python
   from ..task import Context, Param, Task, register

   @register("my-task")
   class MyTask(Task):
       TITLE, ICON = "My Task", "🎯"
       DESCRIPTION = "What it does, in one line."
       START_HINT = "Which game screen to start on."
       PARAMS = [Param("runs", "int", 5, "Runs", min=1, max=100)]

       def run(self, ctx: Context) -> None:
           for _ in range(self.params["runs"]):
               if ctx.should_stop():
                   return
               ...
   ```

2. Import it in `capygo/tasks/__init__.py`.
3. Put its reference images in `templates/my-task/`. An icon at
   `ui/assets/my-task.png` replaces the emoji on the home screen.

Each `Param` becomes an input in the app and a `-p key=value` flag. `Context`
gives you `frame()`, `find()`, `click_rel()`, `click_match()`, `drag_rel()`,
`hover_rel()` and `should_stop()`.

### Adding an Auto Daily chore

Copy the template for the group: `_event_template.py`, `_guild_template.py` or
`_menu_template.py` (a daily follows any `daily_*.py` file). Import the new file
in `capygo/tasks/__init__.py` and add the class to the group's list in
`auto_daily.py`, `auto_events.py`, `auto_guild.py` or `auto_menu.py`. Its switch
shows up in the app on its own. A chore's `run_daily` starts and must end on the
group's base screen, and `self.flag(ctx, "...")` adds a line to the end-of-run
summary.
