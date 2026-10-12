"""Task: holy-grail-war-fights (the Qualifiers).

Events -> Arena tab -> Holy Grail War -> "Hero Plaza" -> Schedule -> "Qualifiers":
6 teams (rank, team name, power, points, a Challenge button showing your tickets
"8/2"), Free Refresh at the top right, your points and ranking below. Same screen
and flow as the Martial Arts Qualifiers, so this is martial-arts-tournament with
its own layout (user, 2026-10-11: "similar to martial-arts-tournament"). The
differences (user):
  1. A challenge takes 2 tickets ("8/2"): with a set number of fights, up to 2
     tickets are bought per fight (one per Purchase, Challenge again after each).
     With 0, the run ends when Challenge opens the Purchase popup (under 2 left).
  2. It's 2v2: each row is a team, and its power is the two players' total
     (checked: 1.54T + 1.02T on "Team Details" = the row's 2.57T). So "Your team
     power" is yours plus your teammate's. Tapping a row anywhere but Challenge
     opens "Team Details" (the two players, an X below): never tapped on purpose,
     closed whenever it shows up.
  3. No profile scouting: the log is pvp/holy-grail-war.csv (pvp.record_team) with
     the team's name, power and points as the list shows them, and the result.
     The name is read with Vision's accurate model and Korean / Japanese /
     Chinese on (English alone dropped "팀카피" entirely), three times at
     different sizes, keeping the most common read.

Layout (642x951, seen 2026-10-11): rows 78px apart; a row's name at its points'
y - 29 (x 150..420), power at x 186..250 and points at x 288..345 on the points'
line, Challenge's label at the points' y - 8 and the "8/2" at y - 25. After the
scroll that shows all 6, row 1's name is cut off and its button half hidden, so
picking row 1 scrolls back up first (as in martial). If Holy Grail War opens on
"Select Division" (a new season's pick), there's nothing to fight: it stops.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import cv2

from ..geometry import Rel, RelRect
from ..perception import NAME_LANGUAGES, ocr_lines
from ..task import Context, Param, register
from .daily import find_sprite
from .event import TABS, go_events
from .event_holy_grail_war import HolyGrailWar
from .event_plaza import SELECT_TITLE, TITLE_REGION
from .martial_arts_tournament import (SCHEDULE_BTN, SNIPE_UTC, STAGE_TITLE, TITLE_TAP, Foe,
                                      ListLayout, MartialArtsTournament, _px, _words)
from . import pvp

HGW = ListLayout(power_x=(186, 250), points_x=(288, 345), find_x=(288, 345),
                 challenge_dy=-8, tickets_dy=-25, ticket_cost=2, tappable=(213, 586))
MY_POINTS = RelRect(0.33, 0.710, 0.17, 0.040)       # your points ("1034")
NAME_X, NAME_DY, NAME_HALF = (140, 420), -29, 16    # a row's team name, px
NAME_READS = (3, 4, 2)                              # upscales: read the name at each
NAME_PAD = 20                                       # px of border: a crop edge cut "H"
TEAM_TITLE = RelRect(0.25, 0.255, 0.50, 0.050)      # "Team Details" (row tapped)
TEAM_CLOSE = (320, 762)                             # its X, if the sprite isn't found


def read_team_name(frame, points_y: float) -> tuple[str, bool]:
    """The team name of the row whose points sit at `points_y`: the most common
    of NAME_READS reads, and whether at least two agreed."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    y = points_y + NAME_DY
    crop = frame[int((y - NAME_HALF) * ky):int((y + NAME_HALF) * ky),
                 int(NAME_X[0] * kx):int(NAME_X[1] * kx)]
    reads = []
    for scale in NAME_READS:
        big = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        big = cv2.copyMakeBorder(big, NAME_PAD, NAME_PAD, NAME_PAD, NAME_PAD,
                                 cv2.BORDER_REPLICATE)
        text = " ".join(t for t, _, _ in ocr_lines(big, "accurate", NAME_LANGUAGES)).strip()
        if text:
            reads.append(text)
    if not reads:
        return "", False
    name, n = Counter(reads).most_common(1)[0]
    return name, n >= 2


@register("holy-grail-war-fights")
class HolyGrailWarFights(MartialArtsTournament):
    TITLE = "Holy Grail War"
    ICON = "🏆"
    HOME_AFTER = "martial-arts-tournament"  # user: under Martial Arts in the app
    DESCRIPTION = ("Qualifiers (2v2): fight the team with the most points below your "
                   "team's power limit until the tickets run out, now or at 6:50 AM "
                   "(sniping).")
    START_HINT = ("Start anywhere in the game. Set your team's power first: yours plus "
                  "your teammate's, as the list shows teams.")
    TAG = "hgw"
    LAYOUT = HGW
    MY_POINTS = MY_POINTS
    BUYS_PER_FIGHT = 2          # user: a challenge takes 2 tickets
    team, team_note = "", ""    # the fought team's name, for the log
    PARAMS = [
        Param("my_cp", "float", 6.41, "Your team power (T)", min=0.01, max=10000,
              help="you plus your teammate, in trillions; teams are compared against it"),
        Param("ratio", "float", 1.1, "Power ratio", min=0.5, max=5,
              help="fight only teams below this x your team power (+0.1 per refresh)"),
        Param("sniping", "bool", False, "Sniping mode",
              help="wait for 6:50 AM Pacific (13:50 UTC) and use every fight then"),
        Param("max_attacks", "int", 0, "Fights (0 = until tickets run out)", min=0,
              max=99, help="a number: always do that many, buying 2 tickets a fight "
                           "if needed"),
        Param("snipe_utc", "str", SNIPE_UTC, "Snipe time (UTC, HH:MM)", hidden=True,
              help="for tests: -p snipe_utc=HH:MM; the cutoff is 5 minutes later"),
    ]

    # --- getting there -----------------------------------------------------------
    def _open_qualifiers(self, ctx: Context) -> bool:
        if not go_events(ctx):
            self._log.warning("couldn't get to the Events screen")
            return False
        if not (self._tap(ctx, TABS["arena"], "Arena tab")
                and self._tap(ctx, HolyGrailWar.CARD, "Holy Grail War")):
            return False
        if not ctx.dry_run:
            def opened() -> bool:
                f = ctx.frame()
                return ("hero plaza" in _words(f, TITLE_REGION)
                        or "select division" in _words(f, SELECT_TITLE))
            if not self._until(ctx, opened):
                self._log.warning("the Hero Plaza didn't open")
                return False
            if "select division" in _words(ctx.frame(), SELECT_TITLE):
                self._log.warning("Holy Grail War is on its division pick (Select "
                                  "Division): no fights now")
                return False
        if not self._tap(ctx, SCHEDULE_BTN, "Schedule"):
            return False
        if not ctx.dry_run and not self._until(
                ctx, lambda: "qualifier" in _words(ctx.frame(), STAGE_TITLE)):
            self._log.warning("the Qualifiers didn't open (another stage?)")
            return False
        return self._tap(ctx, _px(TITLE_TAP), "title (wake the list)")

    # --- the hooks ---------------------------------------------------------------
    def _before_fight(self, ctx: Context, foe: Foe) -> bool:
        """Read the team's name for the log (no tap: a row tap opens Team Details)."""
        self.team, self.team_note = "", ""
        if ctx.dry_run:
            return True
        self._close_team(ctx)
        self.team, sure = read_team_name(ctx.frame(), foe.y)
        if not self.team:
            self.team_note = "name not read"
        elif not sure:
            self.team_note = "name reads differed"
        self._log.info("team %r%s", self.team or "?",
                       f" ({self.team_note})" if self.team_note else "")
        return True

    def _record(self, ctx: Context, result: str, cp: Decimal, my_points: int | None,
                foe: Foe) -> None:
        pvp.record_team(ctx, result, my_power=cp, my_points=my_points,
                        team=self.team, power=foe.power, points=foe.points,
                        note=self.team_note)

    def _wrong_screen(self, frame) -> bool:
        """Team Details: the Challenge tap landed on the row instead."""
        return "team details" in _words(frame, TEAM_TITLE)

    def _scroll(self, ctx: Context, drag) -> None:
        super()._scroll(ctx, drag)
        self._close_team(ctx)  # a drag taken as a tap opens Team Details

    def _close_team(self, ctx: Context) -> None:
        """Close Team Details if it's up (a row was tapped)."""
        if ctx.dry_run or not self._wrong_screen(ctx.frame()):
            return
        x = find_sprite(ctx, ctx.frame(), "close_x.png")
        self._tap(ctx, x if x is not None else Rel(TEAM_CLOSE[0] / 642, TEAM_CLOSE[1] / 951),
                  "close Team Details")
