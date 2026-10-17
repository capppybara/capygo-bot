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
- [Extra Reward Collector](#extra-reward-collector)
- [Get Guild Member List](#get-guild-member-list)
- [Goblin Miner](#goblin-miner)
- [Hard Mode Autorun](#hard-mode-autorun)
- [Martial Arts Tournament](#martial-arts-tournament)
- [Holy Grail War](#holy-grail-war)
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

Personal settings live in `config.local.yaml`, which git ignores. Copy
`config.local.example.yaml` to it and fill in your own values: your friend's
in-game name (the default Friend for Auto Gulu and hard mode joining), your Holy
Grail War team power, your hard mode chapter and multiple, and your
Gulu difficulty. Without it, the app starts from neutral values (1T, chapter 1,
1x, difficulty 1, no friend).

The app also remembers each automation's settings: when you press Start, they're
saved to `data/app_settings.json` (git ignores it too) and filled in the next
time you open that automation. Auto Daily's chore switches are the exception:
they start all on every time.

### 3. Run an automation

1. Pick an automation on the home screen.
2. Set its options. Each screen says which game screen to start on.
3. Press **Start**. The log shows every tap and decision as it happens.

Tick **Dry run** (next to the log status) to see what it would tap without
tapping anything.

If the game gets stuck, press **Restart game** on the home screen, next to "Pick
an automation to run". It kills the game, opens it again, and closes the
start-up notices until the game's home screen shows. A note beside the button
says how it went.

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
| [Extra Reward Collector](#extra-reward-collector) | Opens every Extra Rewards present on an event fund, upgrading each one | An event fund's screen with Extra Rewards |
| [Get Guild Member List](#get-guild-member-list) | Exports a guild's members (UID and power) to a CSV, or collects top powers to compare guilds | A guild's Guild Info screen |
| [Goblin Miner](#goblin-miner) | Mines Goblin Miner floors for the Capy King statue | The Goblin Miner grid |
| [Hard Mode Autorun](#hard-mode-autorun) | Runs a Hard Mode chapter over and over | The Hard Mode screen |
| [Martial Arts Tournament](#martial-arts-tournament) | Fights the Qualifiers opponents worth the most points that you can beat, now or at 6:50 AM | Anywhere |
| [Holy Grail War](#holy-grail-war) | Fights the Holy Grail War Qualifiers teams worth the most points that you can beat (2v2) | Anywhere |
| [Pet Armament Chest](#pet-armament-chest) | Opens Pet Armament chests, upgrading when it is worth it | The locked chest screen |
| [Pet Synthesis](#pet-synthesis) | Turns surplus pet fragments into new pets until none are left | Anywhere |

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

The log ends with a summary:

- what finished;
- what was skipped because it already ran today;
- what was skipped because the game had nothing for it, with the reason (for
  example, Holy Grail War during its division-pick phase has no likes). These
  aren't marked done, so a later run tries them again;
- a **Needs your attention** list: everything a chore flagged for you to handle
  by hand, such as the arena running out of beatable opponents, and every chore
  that failed, with the path of its saved screenshot.

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
   Gift Pack (500 gems). It finds each pack by its row title, because
   sold-out packs move down the list.
2. **Draws:** taps Draw 10 times until the game refuses, first with tickets,
   then with the day's gem draws. It skips each draw animation.
3. **Points chests:** claims every points-bar chest with a red "!".
4. **Travel:** in Capy Grand Voyage → Travel, it collects a finished travel and
   sends the team out again for 20 hours, or for 24 hours before 2 AM UTC
   (7 PM Pacific in summer, 6 PM in winter).

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
| Guild hall donations | Guild Hall → Donate. Donates until "Chances Left Today" reaches 0: 5 a day, the first free, then 25 gems each. |
| Guild trade plunder | Guild Trade → Others' Trades. Plunders boats until "Looted today" reaches 4/4 (see below). |

**Guild trade plunder** looks at the gilded boats (gold barge with a crown) and
golden boats (orange sail) on the map. It plunders a boat only if all of these
hold:

- the panel's banner is UR orange (the map sometimes shows a boat as gold
  wrongly);
- the boat can still be plundered;
- its owner's power is below 1.2x yours (the Arena's rule). Your power is the one
  the Arena chore last read; it runs first. If the Arena has never run, Guild
  trade skips itself with a note;
- a golden chest or 200 badges sits in the first two cargo slots.

If the sea has both a chest boat and a badge boat, it takes the chest. A lost
fight just moves on. With no suitable boat it taps the free Refresh, up to 30
times, then flags it.

Popups can cover Guild Trade, such as the "Bountiful Return" letter with its
Rewards when a guild-mate's ship comes back. The bot closes any popup it finds
before each step: a reward with a tap above it, a panel with its X.

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
| Friend | from `config.local.yaml` | both | Who to invite (hosting), or whose invite to accept (joining) |
| Runs | 4 | both | How many runs to play |
| Difficulty (hosting) | from `config.local.yaml` (else 1) | hosting | The Gulu Mine difficulty to host |
| Stay (hosting) | off | hosting | Play each run to the end instead of quitting it |

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

For each skill screen the bot waits until it shows "0/2", gives the cards 2
seconds to slide in, then picks. If the counter still reads short (a tap didn't
register), it picks the next card down. It taps Select only while the screen is
still up. The Skills panel does not pause the run, so the quit has to be quick. If a
run fails, the bot saves a screenshot to `logs/`.

With **Stay** on, the bot plays each run to the end instead of quitting:

1. It picks skills on every skill screen, the same way joining does, and taps OK
   on the result. That leaves it on the team screen with the friend still in.
2. It taps Start Challenge every 5 seconds until the next run starts. The start
   may not take until the friend is ready.
3. If no run starts within 5 minutes, it taps Remove under the friend's name,
   invites them again, and keeps trying. A second 5 minutes without a start
   stops the bot.

If the friend leaves, the bot invites them again. It taps the button only while
it reads Start Challenge. With nobody in, the same button reads Random Match.

### Joining

For each run, the bot:

1. Checks every 10 seconds, for up to 30 minutes, for the "New Invitation"
   banner. It opens it, makes sure the invitations are Gulu Mine's, and accepts
   the friend's invite. If their invite isn't there, it taps Reject all, then
   switches to Hard Chapters and taps Reject all there too, then closes the
   popup. It never taps "No longer show".
2. Plays the run to the end. Every 2 seconds it looks for a skill screen and
   picks the top cards: two picks on each of battle 1's two screens, one pick
   on each later screen.
3. Taps OK on the Victory or Defeat screen.

While it waits for the host to start, the bot opens the invitation banner
when it shows, at most every 10 seconds. Sometimes the host can't start, leaves,
and invites you from a new room; the bot then accepts that new invite. If the
banner holds only other players' invites, the bot rejects them in every mode, so
the banner comes back only for a new invite. If the popup can't be switched to
Gulu Mine, it closes the popup without rejecting anything.

Where the result screen leaves you tells the bot whether the host stayed. Back
on the Gulu team screen means the host stayed, so it waits for the next start.
Back home means the host left, so it looks for the next invite.

## Extra Reward Collector

Extra Reward Collector opens every present waiting in an event fund's Extra
Rewards section (for example Goblin Pachinko's Marble Fund; other funds work the
same way).

**Start on:** the fund's screen, with the Extra Rewards section showing.

For each present the bot:

1. Taps the present. A big present box opens with "Tap to upgrade rarity".
2. Taps the box 4 times, waiting 4 seconds before each tap, since the game lags.
   Each tap can upgrade the present's rarity. If the box still asks for upgrades
   after 4 taps (a tap got lost), it taps again, up to 2 more times.
3. Taps the box once more to claim, then closes the Rewards popup with a tap
   above its dark band.

It repeats until the big present no longer opens (the game won't open it once
they're used up). It doesn't read the rarity or the reward. If another screen
doesn't come up, it saves a screenshot and stops.

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
multiple, on your own or by joining a friend's run.

**Start on:** solo, the Hard Mode screen with Hard Mode on (the switch next to
Start is red, not blue). Joining, anywhere: it waits for the friend's invite.

| Setting | Default | Meaning |
|---|---|---|
| Chapter (solo) | from `config.local.yaml` (else 1) | The Hard Mode chapter to run solo. Joining runs the host's chapter |
| Energy multiple | from `config.local.yaml` (else 1x) | Energy (and reward) per run: 1x, 2x, 3x, 5x, 10x or 20x |
| Number of runs | 10 | How many runs before it stops |
| Join a friend's run | off | On: join the friend's Hard Chapters runs instead of running solo |
| Host (joining) | from `config.local.yaml` | Whose invite to accept. Change it to play with someone else |

Each solo run it selects the chapter, sets the multiple, presses Start, and plays
the run the same way joining does (below): it picks the skills and handles the
events until the result. It checks the energy cost on the Start button to confirm the
multiple. It stops early when a run is lost, when energy runs short, or when
Hard Mode is off.

Joining, the bot:

1. Accepts the host's Hard Chapters invite. If it isn't there, the bot taps
   Reject all in Hard Chapters and in Gulu Mine, so other invites don't keep the
   banner up.
2. Reads your multiple every 2 seconds on the team screen and sets it whenever it
   isn't your setting. It resets to 1x after each run, when the host changes
   chapter, and when the invitations popup closes. It stops checking once the
   multiple has read the same for 10 minutes, and checks again after the
   invitations popup closes. If the host starts too fast, it skips the multiple
   for that run. If the host doesn't start within 30 minutes, it stops. Each
   pass looks for the start first, then makes one + or - tap if the multiple
   needs it. The invitations wait until the multiple is set, and open at most
   every 10 seconds.
   If the host makes a new room and invites you again, the bot accepts and
   starts that run over. The run you left isn't counted.
3. Plays the run: picks the top skill(s) on each skill screen, opens the
   treasure chest and takes its top skill, signs the demon's pact, and takes the
   angel's first gift. Other events run out their countdown.
4. Closes the result and waits for the next start. A kick and re-invite is fine:
   it accepts the new invite and doesn't count a run.

If something goes wrong mid-way, it doesn't stop: it saves a screenshot, waits
for the run to end (the Victory or Defeat screen, or back on the team screen),
and starts over. Only 10 problems in a row with no run in between stop it.
You can start it in the middle of a run too: it plays the rest of it.

## Martial Arts Tournament

Martial Arts Tournament spends your Qualifier tickets on the opponents worth the
most points that you can beat. It runs now, or waits and runs just before the
round closes (sniping).

**Start on:** anywhere. It opens Events → Arena → Martial Arts Tournament →
Schedule (the Qualifiers) itself.

| Setting | Default | Meaning |
|---|---|---|
| Your CP (T) | your power from the Arena (else 1) | Your power in trillions; opponents are compared against it. Used only with Follow Arena off: Martial Arts' own value, which starts from the Arena's reading the first time and is yours to change |
| Follow Arena | on | Use your power as the Arena chore last read it (shown greyed in Your CP), at the time of the run. Off: use Your CP. The app remembers which you chose |
| Power ratio | 1.1 | Fight only opponents below this x your CP |
| Sniping mode | off | Wait for 6:50 AM Pacific and use every attack then |
| Attacks (0 = until tickets run out) | 0 | 0 uses every ticket and stops. A number: always do that many, buying tickets if needed |
| Log opponents | on | Before each fight, open the opponent's profile and log it with the result in `~/Downloads/capy-bot/pvp/` (about 4 seconds a fight) |

For each attack the bot:

1. Scrolls the list a little so all 6 opponents show, and reads each one's power
   and points. B and T are converted (1T = 1000B).
2. Fights the one with the most points whose power is below the ratio x your CP,
   skipping a player you've fought 5 or more times and beaten less than 40% of
   the time (arena and martial fights together, by UID). The UID is on their
   profile, so once anyone in the log has 5 fights, the bot opens candidates'
   profiles best first until one passes. That's the profile the fight log opens
   anyway, so it only costs time (about 4 seconds) for each player it skips.
3. If none qualifies, taps Refresh (free or paid) and looks again, raising the
   ratio by 0.1 each time: 1.1, 1.2, up to 1.6 after 5 refreshes. If there is
   still none, it stops.
4. Skips the fight and taps OK on the result, like the arena. If Skip is still
   showing after 30 seconds, the fight is stuck: it restarts the game (once per
   run), goes back to the Qualifiers, and carries on.

Out of tickets, Challenge opens a ticket Purchase popup instead of a fight. With
**Attacks** at 0 the bot closes it and finishes. With a number set, it always
does that many attacks, buying a ticket each time it runs out.

**Seasons.** A Martial Arts season starts on a Saturday and lasts a week, and a
new one starts every 2 weeks. Season 1 ran 2026-10-03 to 10-09, season 2 runs
2026-10-17 to 10-23, and so on. Each fight's row in `fights.csv` gets its
season; a fight outside a season week, and every arena row, leaves it blank.

**Normal mode** attacks until the tickets run out. **Sniping mode** waits for the
next 13:50 UTC: 6:50 AM Pacific in summer, 5:50 AM in winter. The round closes at
14:00 UTC and challenges stop 5 minutes before that, so it has 5 minutes. It
stops starting fights 20 seconds before the cutoff. One attack takes about 15
seconds, so 9 tickets take about 2.5 minutes. While it waits it keeps the Mac
awake; the app must stay open and the game window visible. It starts one minute
before the snipe time: it restarts the game (about 30 seconds), closes the
start-up notices, and goes straight to the Qualifiers. The cutoff doesn't
change. With less than 45 seconds to go, it skips the restart.

## Holy Grail War

Holy Grail War fights the Holy Grail War Qualifiers the same way Martial Arts
Tournament fights its own: the team worth the most points that you can beat, now
or just before the round closes. Teams here are 2v2.

**Start on:** anywhere. It opens Events → Arena → Holy Grail War → Schedule (the
Qualifiers) itself. If Holy Grail War is on its division pick (Select Division),
there's nothing to fight and it stops.

| Setting | Default | Meaning |
|---|---|---|
| Your team power (T) | from `config.local.yaml` (else 1) | Your power plus your teammate's, in trillions. The list shows each team's total, so teams are compared against this |
| Power ratio | 1.1 | Fight only teams below this x your team power |
| Sniping mode | off | Wait for 6:50 AM Pacific and use every fight then |
| Fights (0 = until tickets run out) | 0 | 0 fights until fewer than 2 tickets are left. A number: always do that many, buying tickets if needed |

How it differs from Martial Arts Tournament:

- **It remembers this season.** Before picking, it looks up each team in this
  season's log by name. A team that beat you the last time you fought them this
  season is skipped (the log says so). A team you haven't fought this season, or
  beat last time, is picked as usual: the most points below the power limit.
  Fights from the same run count, so a loss is remembered right away.

- **2 tickets a fight.** The Challenge button shows your tickets as "8/2". With a
  number of fights set, it buys 2 tickets at once for each fight it can't afford:
  it taps + in the Purchase popup until the quantity reads 2, then buys.
- **Teams.** Tapping a row anywhere except Challenge opens Team Details (the two
  players). The bot never taps there on purpose and closes Team Details if it
  shows up.
- **Its own log.** No profiles are opened. Each fight adds a row to
  `~/Downloads/capy-bot/pvp/holy-grail-war.csv`: the season, the team's name,
  power and points as the list shows them, your points, and `won`. Names are read in
  English, Korean, Japanese and Chinese, three times each; the most common read
  is kept, and the `note` column says when the reads differed.

Sniping starts at 13:49 UTC with a game restart, then goes straight to the
fights, like Martial Arts.

**Seasons.** A Holy Grail War season starts on a Saturday and lasts a week, and
a new one starts every 4 weeks. The bot counts them itself: season 1 started
Saturday 2026-10-10, season 2 starts 2026-11-07, and so on. Each fight's row
gets the season it was fought in; a fight outside a season week gets none.
Martial Arts has seasons too (see Martial Arts Tournament). The Qualifiers run for
more than a day and close at 14:00 UTC (7:00 AM Pacific in summer), so start it
on the last day.

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

## Pet Synthesis

Pet Synthesis turns surplus pet fragments into new pets. It keeps going until
the game has no fragments left to use. It has no settings.

**Start on:** anywhere. If you are already on the Pets page or in the Pet
Synthesis popup, it starts there. Otherwise it goes home, then Equip, then Pets.

Each synthesis:

1. Opens Pet Synthesis (bottom right of the Pets page).
2. Taps Synthesize, then OK on the "fragments will be consumed" confirm. The bot
   taps OK only on that confirm.
3. Closes the Rewards popup with the new pets, which returns to the Pets page.

When the popup reads "No surplus pet fragments available", Synthesize does
nothing. The bot then closes the popup and goes home. Each synthesis takes about
7 seconds.

## Files it writes

| Path | What |
|---|---|
| `logs/<task>-<time>.log` | A log of every run |
| `logs/failed-<chore>-<time>.png` | The screen when an Auto Daily chore failed |
| `~/Downloads/capy-bot/` | CSV exports and comparison graphs |
| `~/Downloads/capy-bot/pvp/fights.csv` | Every arena and martial fight: the season (martial only), the opponent's UID, name, power, stats and weapon, and `won` (1 = won, 0 = lost, blank = not known) |
| `~/Downloads/capy-bot/pvp/holy-grail-war.csv` | Every Holy Grail War fight: the season, the team's name, power and points, and `won` |
| `~/Downloads/capy-bot/pvp/players.csv` | One row per arena and martial opponent (by UID): fights, wins, losses, win rate, and their latest fight. Rebuilt from `fights.csv` after every fight, so it's always current |
| `~/Downloads/capy-bot/pvp/profiles/` | Each opponent's profile screen |
| `~/Downloads/capy-bot/pvp/weapons/unknown-N.png` | Each weapon not seen before, saved the first time it shows up. Rename the file to the weapon's name to teach it. |
| `~/Downloads/capy-bot/pvp/weapons/unknown.csv` | When each unknown weapon was first seen, and on whose profile |
| `~/Downloads/capy-bot/skill-screens/` | Every skill choice in Gulu and hard mode runs (gulu-*.png, hard-*.png; hard mode includes the treasure, demon and angel offerings), for working out a smarter pick later |
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
config.yaml                 window owner name, app path, match threshold, stop key
config.local.yaml           personal defaults (friend, CP, chapter, ...); git-ignored,
                            see config.local.example.yaml
data/app_settings.json      each automation's settings from its last Start; git-ignored
data/my_power.json          your power as the Arena last read it (Guild trade's limit)
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
    restart.py              kill the game, open it again, close the start-up notices
    profile.py              a player's Character Info: open, read (UID, power, weapon), close
    pvp.py                  the fight log: look at the opponent first, record the result
    daily_*.py              the Dailies
    event.py, event_*.py    the Events screen and each event
    guild.py, guild_*.py    the guild screen and each guild chore
    menu.py, menu_*.py      the menu drawer and each menu chore
    auto_events.py, auto_guild.py, auto_menu.py   each group's chore list
    _event_template.py, _guild_template.py, _menu_template.py   copy to add a chore
    auto_gulu.py            Auto Gulu
    get_guild_member_list.py, compare_guild_power.py
    goblin_miner.py, hard_mode_autorun.py, pet_armament_chest.py, pet_synthesis.py
    extra_reward_collector.py
    martial_arts_tournament.py
    holy_grail_war_fights.py  Holy Grail War: the martial task with its own layout
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
./run.sh auto-gulu -p difficulty=25 -p friend=<their name> -p runs=4
./run.sh auto-gulu -p join=true -p runs=4
./run.sh get-guild-member-list -p hedgemony=true -p top_n=25
./run.sh compare-guild-power               # graph the hedgemony collection
./run.sh extra-reward-collector             # on an event fund's Extra Rewards
./run.sh goblin-miner -p min_picks=0
./run.sh hard-mode-autorun -p chapter=180 -p energy_multiple=20 -p runs=10
./run.sh martial-arts-tournament -p my_cp=5.23 -p ratio=1.1
./run.sh martial-arts-tournament -p sniping=true   # waits for 6:50 AM Pacific
./run.sh holy-grail-war-fights -p my_cp=6.41 -p max_attacks=3
./run.sh pet-armament-chest -p runs=20 -n
./run.sh pet-synthesis
./run.sh restart-game                      # kill the game, reopen it, get to home
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

If the game gets stuck, `restart_game(ctx, reason)` from `capygo/tasks/restart.py`
kills it, opens it again, and closes each start-up notice until the home screen
stays clear for 3 seconds. It returns True once home. Its steps are public too:
`quit_game`, `launch_game` (also starts a game that isn't running) and
`wait_for_home`.

### Adding an Auto Daily chore

Copy the template for the group: `_event_template.py`, `_guild_template.py` or
`_menu_template.py` (a daily follows any `daily_*.py` file). Import the new file
in `capygo/tasks/__init__.py` and add the class to the group's list in
`auto_daily.py`, `auto_events.py`, `auto_guild.py` or `auto_menu.py`. Its switch
shows up in the app on its own. A chore's `run_daily` starts and must end on the
group's base screen, and `self.flag(ctx, "...")` adds a line to the end-of-run
summary.
