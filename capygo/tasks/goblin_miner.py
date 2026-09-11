"""Task: goblin-miner.

Plays the Goblin Miner minigame: on each underground floor it mines the stone
grid to uncover the hidden Capy King statue, unlocks/claims the statue, then
takes the doorway down to the next floor. It repeats floor after floor until the
pickaxe meter runs out (or Stop/Esc).

Per floor:
  1. Mine a fixed 6-tile pattern (r4c4, r3c2, r5c2, r2c4, r1c2, r6c4). The
     pattern hits the spots a large statue is most likely to occupy, so a big
     statue shows up early. It stops the moment a statue turns up.
  2. Whatever tile the statue first shows on is matched against a library of
     fragment templates (templates/goblin-miner/statue_<size>_<position>.png)
     to identify the statue's SIZE (1x1 / 2x2 / 2x3) and which part is showing.
     That pins the full footprint on the board: the doorway/top-left origin is
     the matched tile minus the fragment's offset.
  3. If nothing showed in the pattern, press Auto-Mine to dig until the statue
     surfaces, then identify it the same way. Refill picks if they run out.
  4. Reveal the rest of the footprint (mine only those tiles -- never a halo),
     open the statue, tap 4x to resolve its rarity orbs, tap once to claim, tap
     the reward summary closed.
  5. Click the doorway that appears at the footprint's top-left -> next floor.

The grid is 5 wide x 6 tall; tile centers are window-relative. Tiles are first
sorted by colour + texture of a patch at each centre:
  stone  uniform light purple-grey (unmined)
  empty  uniform dark (mined, nothing there)
  statue textured grey with dug-out dirt behind it (catches a partial fragment
         too), then template-matched to identify size + position
  door   orange arch (the exit, appears at the statue footprint's top-left)
  reward a saturated coloured token (gem/egg/capybara), auto-collected
The full-screen statue flow is driven by OCR of the on-screen prompt
("Tap to upgrade rarity" -> "Click to claim reward" -> "Tap to close"), so it
adapts to timing instead of counting blind taps.

A statue whose fragment matches no template (a size not yet captured) stops the
run with an "UNIDENTIFIED STATUE" note so it can be snapshotted and added.

Two other tile types are matched by template too: a "bomb" (bomb.png) is claimed
on sight -- each blast clears its whole row and column, which helps surface the
statue -- and a "cracked block" (cracked.png), a buried reward, is claimed at the
end of a floor once the statue is done, before dropping down.
"""

from __future__ import annotations

import glob
import os
import re
import time

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..perception import ocr_lines
from ..task import Context, Param, Task, register

# --- grid geometry (642x951), calibrated live from the tile boundaries ------
GRID_COLS = [0.2687, 0.3832, 0.4984, 0.6137, 0.7290]   # xrel of columns 1..5
GRID_ROWS = [0.3118, 0.3896, 0.4674, 0.5447, 0.6220, 0.6998]  # yrel of rows 1..6
TILE_HALF = 30   # px half-size of the patch sampled at a tile centre (colour stats)
TILE_CROP_HALF = 34  # px half-size of a full-tile crop (template match / capture)

# Mining order, (row, col) 1-indexed. Chosen to surface big statues first.
PATTERN = [(4, 4), (3, 2), (5, 2), (2, 4), (1, 2), (6, 4)]

# Statue footprints. Each size maps to (rows, cols, {position: (drow, dcol)}),
# the offset of each fragment tile from the statue's top-left tile. A fragment
# uncovered at board tile (r,c) with a known position pins the whole footprint:
# origin = (r-drow, c-dcol). The template files are templates/goblin-miner/
# statue_<size>_<position>.png (statue_1x1.png for the single-tile statue). The
# doorway always appears at the top-left tile of the footprint.
STATUE_SIZES = {
    "1x1": (1, 1, {"": (0, 0)}),
    "2x2": (2, 2, {"top_left": (0, 0), "top_right": (0, 1),
                   "bot_left": (1, 0), "bot_right": (1, 1)}),
    "2x3": (3, 2, {"top_left": (0, 0), "top_right": (0, 1),
                   "mid_left": (1, 0), "mid_right": (1, 1),
                   "bot_left": (2, 0), "bot_right": (2, 1)}),
}
FRAGMENT_MATCH_THRESHOLD = 0.70   # min TM_CCOEFF_NORMED to accept a fragment ID
                                  # (real fragments match >=0.87, false ones <=0.57)
BOMB_MATCH_THRESHOLD = 0.65       # min TM_CCOEFF_NORMED to accept a bomb tile
                                  # (templates/goblin-miner/bomb.png)
CRACKED_MATCH_THRESHOLD = 0.65    # min TM_CCOEFF_NORMED to accept a cracked block
                                  # (templates/goblin-miner/cracked.png)

# --- buttons / fixed taps --------------------------------------------------
AUTO_MINE_BTN = Rel(0.805, 0.181)   # green "Auto-Mine" button, top right
REVEAL_TAP = Rel(0.5, 0.5)          # taps the statue reveal screen (upgrade/claim)
CLOSE_TAP = Rel(0.5, 0.86)          # "Tap to close" on a reward summary

# --- reading the screen ----------------------------------------------------
PICK_REGION = RelRect(0.42, 0.935, 0.28, 0.042)   # the "N/100" pickaxe counter
                                                  # (wide enough for 3-digit N)
PROMPT_BAND = RelRect(0.10, 0.70, 0.80, 0.20)     # where the statue prompts sit
TITLE_BAND = RelRect(0.13, 0.090, 0.70, 0.080)    # the "Goblin Miner" header
                                                  # (generous -- a tight band OCRs
                                                  # empty and mis-reads the screen)

# When picks run out, the bottom counter is replaced by a green "Pickaxe x15"
# button (a free +15 refill, a couple of uses per period). Tapping it grants the
# picks instantly (a reward summary to tap closed), so the run can keep going
# until the refill is used up.
REFILL_BTN = Rel(0.5, 0.936)
REFILL_REGION = RelRect(0.30, 0.905, 0.40, 0.052)  # the button's label ("Pickaxe")

# Auto-Mine pops a "Tips: Statue found, auto-mining ends" dialog when it uncovers
# the statue; click OK to get back to the board.
TIPS_OK_BTN = Rel(0.5, 0.631)
TIPS_REGION = RelRect(0.15, 0.46, 0.70, 0.12)   # the tip's message line


@register("goblin-miner")
class GoblinMiner(Task):
    TITLE = "Goblin Miner"
    ICON = "⛏️"
    DESCRIPTION = ("Mine each Goblin Miner floor for the Capy King statue, "
                   "unlock and claim it, then descend -- until picks run out.")

    PARAMS = [
        Param("min_picks", "int", 0, "Stop below picks", min=0, max=100,
              help="stop before a floor when the pickaxe meter is at or below "
                   "this (0 = go until the board can no longer be cleared)"),
    ]

    # --- timing that survives a Stop --------------------------------------
    def _sleep(self, ctx: Context, seconds: float) -> bool:
        """Sleep in <=0.3s slices; return True if a stop was requested."""
        end = time.time() + seconds
        while True:
            if ctx.should_stop():
                return True
            remaining = end - time.time()
            if remaining <= 0:
                return False
            time.sleep(min(0.3, remaining))

    # --- tile classification ----------------------------------------------
    def _tile_patch(self, frame, r: int, c: int):
        h, w = frame.shape[:2]
        cx = int(GRID_COLS[c - 1] * w)
        cy = int(GRID_ROWS[r - 1] * h)
        return frame[cy - TILE_HALF:cy + TILE_HALF, cx - TILE_HALF:cx + TILE_HALF]

    def _classify(self, frame, r: int, c: int) -> str:
        patch = self._tile_patch(frame, r, c).astype(float)  # BGR, HxWx3
        if patch.size == 0:
            return "unknown"
        flat = patch.reshape(-1, 3)
        mean = flat.mean(0)                        # [B, G, R]
        bright = float(mean.mean())
        std = float(flat.std(0).mean())
        blue, red = mean[0], mean[2]
        # Per-pixel makeup: statues are desaturated grey with a chunk of dark
        # dug-out dirt behind the figure; rewards/doors are strongly coloured.
        b, g, rr = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
        mx = np.maximum(np.maximum(b, g), rr)
        mn = np.minimum(np.minimum(b, g), rr)
        colored = float(((mx > 75) & ((mx - mn) > 40)).mean())  # saturated pixels
        dark = float((mx < 70).mean())                          # revealed dirt
        if bright < 60 and std < 12:
            return "empty"
        if std < 12 and bright >= 100:
            return "stone"
        if red > blue + 25 and std > 12 and colored > 0.1:
            return "door"
        # A statue tile is textured (std) but not coloured, with dug-out dirt
        # behind it -- this catches a partial fragment (mostly stone + a grey
        # sliver) as well as a full statue, and rejects a cracked/glint tile
        # (which has no dark dirt yet).
        if std > 15 and colored < 0.05 and dark > 0.15:
            return "statue"
        if std > 15:
            return "reward"
        return "unknown"

    def _scan(self, frame) -> dict[tuple[int, int], str]:
        return {(r, c): self._classify(frame, r, c)
                for r in range(1, 7) for c in range(1, 6)}

    def _tiles_of(self, board: dict, kind: str) -> list[tuple[int, int]]:
        return [rc for rc, k in board.items() if k == kind]

    def _tile_rel(self, r: int, c: int) -> Rel:
        return Rel(GRID_COLS[c - 1], GRID_ROWS[r - 1])

    # --- statue identification by template match --------------------------
    def _tile_crop(self, frame, r: int, c: int):
        """A full-tile crop, aligned the same way the fragment templates were
        captured, so a live tile can be matched against them."""
        h, w = frame.shape[:2]
        cx = int(GRID_COLS[c - 1] * w)
        cy = int(GRID_ROWS[r - 1] * h)
        return frame[cy - TILE_CROP_HALF:cy + TILE_CROP_HALF,
                     cx - TILE_CROP_HALF:cx + TILE_CROP_HALF]

    def _fragments(self, ctx: Context) -> dict:
        """Load the statue fragment library (cached): {(size, position): image}
        from templates/goblin-miner/statue_*.png."""
        if getattr(self, "_frag_cache", None) is None:
            frags = {}
            for path in glob.glob(os.path.join(ctx.templates_dir, "statue_*.png")):
                parts = os.path.basename(path)[:-4].split("_", 2)  # statue,<size>,<pos>
                size = parts[1]
                pos = parts[2] if len(parts) > 2 else ""
                img = cv2.imread(path)
                if img is not None and size in STATUE_SIZES:
                    frags[(size, pos)] = img
            self._frag_cache = frags
        return self._frag_cache

    def _identify(self, ctx: Context, frame=None):
        """Match every revealed tile against the fragment library. Return the
        best (size, position, r, c, score) above threshold, else None. With no
        frame given, popups are cleared first and a fresh frame grabbed -- a
        reward-summary overlay turns dimmed tiles into phantom matches otherwise."""
        frags = self._fragments(ctx)
        if not frags:
            return None
        if frame is None:
            self._clear_popups(ctx)
            frame = ctx.frame()
        board = self._scan(frame)
        best = None
        for (r, c), kind in board.items():
            if kind in ("stone", "empty", "door"):
                continue
            tile = self._tile_crop(frame, r, c)
            for (size, pos), tm in frags.items():
                t = tile
                if t.shape != tm.shape:
                    t = cv2.resize(t, (tm.shape[1], tm.shape[0]))
                score = float(cv2.matchTemplate(t, tm, cv2.TM_CCOEFF_NORMED).max())
                if score >= FRAGMENT_MATCH_THRESHOLD and (best is None or score > best[4]):
                    best = (size, pos, r, c, score)
        return best

    def _bomb_template(self, ctx: Context):
        """Load templates/goblin-miner/bomb.png once (None if missing)."""
        if not hasattr(self, "_bomb_tmpl"):
            path = os.path.join(ctx.templates_dir, "bomb.png")
            self._bomb_tmpl = cv2.imread(path) if os.path.exists(path) else None
        return self._bomb_tmpl

    def _find_bomb(self, ctx: Context, frame):
        """Best revealed tile matching the bomb template, as (r, c, score), else
        None."""
        tmpl = self._bomb_template(ctx)
        if tmpl is None:
            return None
        best = None
        for (r, c), kind in self._scan(frame).items():
            if kind in ("stone", "empty"):
                continue
            tile = self._tile_crop(frame, r, c)
            t = tile if tile.shape == tmpl.shape else \
                cv2.resize(tile, (tmpl.shape[1], tmpl.shape[0]))
            score = float(cv2.matchTemplate(t, tmpl, cv2.TM_CCOEFF_NORMED).max())
            if score >= BOMB_MATCH_THRESHOLD and (best is None or score > best[2]):
                best = (r, c, score)
        return best

    def _claim_bombs(self, ctx: Context) -> bool:
        """Click every revealed bomb (each clears its whole row + column, which
        helps surface the statue). Loops because one blast can reveal another
        bomb. Returns True if any were claimed."""
        claimed = False
        for _ in range(8):
            if ctx.should_stop():
                break
            bomb = self._find_bomb(ctx, ctx.frame())
            if not bomb:
                break
            r, c, score = bomb
            ctx.log.info("claiming bomb at r%dc%d (match %.2f)", r, c, score)
            ctx.click_rel(self._tile_rel(r, c))
            self._sleep(ctx, 1.2)
            self._clear_popups(ctx)          # a blast may raise a rewards summary
            claimed = True
        return claimed

    def _cracked_template(self, ctx: Context):
        """Load templates/goblin-miner/cracked.png once (None if missing)."""
        if not hasattr(self, "_cracked_tmpl"):
            path = os.path.join(ctx.templates_dir, "cracked.png")
            self._cracked_tmpl = cv2.imread(path) if os.path.exists(path) else None
        return self._cracked_tmpl

    def _claim_cracked(self, ctx: Context) -> bool:
        """Click every revealed cracked block (each hides a reward). Done at the
        end of a floor, after the statue is claimed. Skips it when out of picks
        (a click would do nothing). Returns True if any were claimed."""
        tmpl = self._cracked_template(ctx)
        if tmpl is None:
            return False
        claimed = False
        for _ in range(12):
            if ctx.should_stop():
                break
            picks = self._read_picks(ctx)
            if picks is not None and picks <= 0:
                break
            frame = ctx.frame()
            found = None
            for (r, c), kind in self._scan(frame).items():
                if kind in ("stone", "empty", "door", "statue"):
                    continue
                tile = self._tile_crop(frame, r, c)
                t = tile if tile.shape == tmpl.shape else \
                    cv2.resize(tile, (tmpl.shape[1], tmpl.shape[0]))
                if float(cv2.matchTemplate(t, tmpl, cv2.TM_CCOEFF_NORMED).max()) \
                        >= CRACKED_MATCH_THRESHOLD:
                    found = (r, c)
                    break
            if not found:
                break
            r, c = found
            ctx.log.info("claiming cracked block at r%dc%d", r, c)
            ctx.click_rel(self._tile_rel(r, c))
            self._sleep(ctx, 0.9)
            self._clear_popups(ctx)
            claimed = True
        return claimed

    def _real_statue(self, ctx: Context):
        """The largest 4-connected clump of "statue" tiles -- a real statue is a
        contiguous 1/4/6-tile blob, so this drops scattered noise. Clears popups
        first so a dimmed overlay is not read as statue tiles."""
        self._clear_popups(ctx)
        statue = set(self._tiles_of(self._scan(ctx.frame()), "statue"))
        best, seen = [], set()
        for start in statue:
            if start in seen:
                continue
            comp, stack = [], [start]
            while stack:
                t = stack.pop()
                if t in seen or t not in statue:
                    continue
                seen.add(t)
                comp.append(t)
                (tr, tc) = t
                stack += [(tr - 1, tc), (tr + 1, tc), (tr, tc - 1), (tr, tc + 1)]
            if len(comp) > len(best):
                best = comp
        return best

    def _footprint(self, size: str, pos: str, r: int, c: int):
        """The board tiles a statue occupies, given one identified fragment."""
        rows, cols, offsets = STATUE_SIZES[size]
        dr, dc = offsets[pos]
        r0, c0 = r - dr, c - dc                       # statue's top-left tile
        return [(r0 + i, c0 + j) for i in range(rows) for j in range(cols)
                if 1 <= r0 + i <= 6 and 1 <= c0 + j <= 5]

    def _reveal_footprint(self, ctx: Context, footprint) -> None:
        """Mine the still-covered tiles of a statue's footprint (only stone
        tiles, so an already-revealed statue tile is never clicked -- clicking
        one would open the reveal early)."""
        for (r, c) in footprint:
            if ctx.should_stop():
                return
            if self._classify(ctx.frame(), r, c) == "stone":
                self._mine_tile(ctx, r, c)

    # --- reading numbers / prompts ----------------------------------------
    def _read_picks(self, ctx: Context, frame=None):
        """Current picks from the "N/100" counter, or None if unreadable. Must be
        an "N/100" -- when picks run out the counter is replaced by the refill
        button ("Pickaxe x15 (2/2)"), whose "(2/2)" must NOT be read as picks."""
        frame = frame if frame is not None else ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = PICK_REGION.to_pixels(w, h)
        text = " ".join(t for t, _, _ in ocr_lines(frame[y0:y1, x0:x1]))
        m = re.search(r"(\d+)\s*/\s*100", text)
        return int(m.group(1)) if m else None

    def _refill_available(self, ctx: Context, frame=None) -> bool:
        """True when the free "Pickaxe x15" refill button is showing (it replaces
        the counter once picks run low)."""
        frame = frame if frame is not None else ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = REFILL_REGION.to_pixels(w, h)
        text = " ".join(t for t, _, _ in ocr_lines(frame[y0:y1, x0:x1])).lower()
        return "pickaxe" in text

    def _try_refill(self, ctx: Context) -> bool:
        """Claim the free pickaxe refill if it is offered. Success is signalled by
        the "Pickaxe x15" reward summary appearing ("Tap to close"); if no summary
        shows after tapping, the refill is used up (or a purchase prompt appeared,
        which we never confirm) -> return False. Taps twice because the first tap
        can just resurface the window."""
        if not self._refill_available(ctx):
            return False
        ctx.log.info("out of picks -> claiming the pickaxe refill")
        for _ in range(2):
            ctx.click_rel(REFILL_BTN)
            self._sleep(ctx, 1.5)
            if self._prompt(ctx) == "close":        # reward summary = granted
                self._dismiss_close_popup(ctx)
                picks = self._read_picks(ctx)
                ctx.log.info("refilled picks%s",
                             f" -> {picks}" if picks is not None else "")
                return True
        ctx.log.info("refill did not grant (used up?) -> stopping")
        return False

    def _prompt(self, ctx: Context, frame=None) -> str:
        """The active statue prompt: 'upgrade' | 'claim' | 'close' | ''."""
        frame = frame if frame is not None else ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = PROMPT_BAND.to_pixels(w, h)
        text = " ".join(t for t, _, _ in ocr_lines(frame[y0:y1, x0:x1])).lower()
        # Order matters: a reward summary ("Tap to close") is drawn over the
        # faded "Click to claim reward" prompt, so check 'close' before 'claim'.
        # ('reward' is no use as a close-signal -- "claim reward" contains it.)
        if "upgrade" in text:
            return "upgrade"
        if "close" in text:
            return "close"
        if "claim" in text:
            return "claim"
        return ""

    def _on_mining_screen(self, ctx: Context, frame=None) -> bool:
        frame = frame if frame is not None else ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = TITLE_BAND.to_pixels(w, h)
        text = " ".join(t for t, _, _ in ocr_lines(frame[y0:y1, x0:x1])).lower()
        return "goblin" in text or "miner" in text

    # --- actions -----------------------------------------------------------
    def _mine_tile(self, ctx: Context, r: int, c: int) -> str:
        """Click a tile until it stops being stone (buried tiles need 2 hits).

        Returns the tile's final class.
        """
        for _ in range(3):
            ctx.click_rel(self._tile_rel(r, c))
            if self._sleep(ctx, 0.7):
                break
            kind = self._classify(ctx.frame(), r, c)
            if kind not in ("stone", "unknown"):
                return kind
        return self._classify(ctx.frame(), r, c)

    def _board_settled(self, ctx: Context):
        """Scan repeatedly until two consecutive scans agree (no animation in
        flight), or a short budget runs out; return the last board."""
        prev = self._scan(ctx.frame())
        for _ in range(10):
            if ctx.should_stop():
                return prev
            self._sleep(ctx, 0.5)
            cur = self._scan(ctx.frame())
            if cur == prev:
                return cur
            prev = cur
        return prev

    def _report_unidentified(self, ctx: Context, statue) -> None:
        """A statue is showing but none of the fragment templates matched (a size
        not yet in the library, e.g. a 2x2). Halt so it can be captured."""
        ctx.log.warning(
            "UNIDENTIFIED STATUE: %d statue tile(s) at %s and no template matched "
            "-> stopping so it can be captured (a size not yet in the library, "
            "probably a 2x2). Left untouched.",
            len(statue), sorted(statue))

    def _handle_statue(self, ctx: Context, statue_tiles: list[tuple[int, int]]) -> bool:
        """Open the statue, resolve its orbs, claim, close. Returns True on success."""
        rs = sum(r for r, _ in statue_tiles) / len(statue_tiles)
        cs = sum(c for _, c in statue_tiles) / len(statue_tiles)
        center = Rel(
            float(np.interp(cs, range(1, 6), GRID_COLS)),
            float(np.interp(rs, range(1, 7), GRID_ROWS)),
        )
        ctx.log.info("opening statue at ~r%.1fc%.1f", rs, cs)

        # Click to open the reveal screen, confirming it actually opened -- the
        # first click after the window backgrounds only resurfaces it, so retry.
        opened = False
        for _ in range(3):
            ctx.click_rel(center)
            self._sleep(ctx, 1.0)
            if not self._on_mining_screen(ctx):
                opened = True
                break
        if not opened:
            ctx.log.warning("statue reveal did not open")
            return False

        # Drive the reveal by its on-screen prompt: 4x upgrade -> claim ->
        # close the reward summary -> back on the grid. Closing the reward
        # summary is the last step, so once it is gone we are done -- do NOT wait
        # to re-OCR the "Goblin Miner" title, which flakes and once made a
        # successful claim read as a failure.
        for _ in range(14):
            if ctx.should_stop():
                return False
            prompt = self._prompt(ctx)
            if prompt in ("upgrade", "claim"):
                ctx.click_rel(REVEAL_TAP)
                self._sleep(ctx, 0.7)
            elif prompt == "close":
                self._dismiss_close_popup(ctx)   # reward summary -> back on grid
                self._board_settled(ctx)
                return True
            elif self._on_mining_screen(ctx):
                return True
            else:
                self._sleep(ctx, 0.5)
        return self._on_mining_screen(ctx)

    def _is_fresh_floor(self, board: dict) -> bool:
        """A just-loaded floor is a near-full grid of stone with nothing revealed
        (distinct from a mid-floor board, which has empties + the statue/door)."""
        return (len(self._tiles_of(board, "stone")) >= 25
                and not self._tiles_of(board, "statue")
                and not self._tiles_of(board, "door"))

    def _take_doorway(self, ctx: Context) -> bool:
        """Click the exit doorway and confirm we dropped to a fresh floor.

        Re-taps only while the doorway is still there: a first tap can merely
        resurface the window, but a blind second tap after a successful descent
        would land on -- and mine -- a tile of the next floor, so we confirm a
        fresh floor before deciding we advanced."""
        for _ in range(8):
            if ctx.should_stop():
                return False
            self._clear_popups(ctx)                 # a popup would garble the scan
            board = self._scan(ctx.frame())
            if self._is_fresh_floor(board):
                return True                         # already descended
            doors = self._tiles_of(board, "door")
            # A real doorway is exactly one orange tile; a whole row/several
            # "door" tiles is a dimmed-popup artifact, so wait it out.
            if len(doors) != 1:
                self._sleep(ctx, 0.6)
                continue
            r, c = doors[0]
            ctx.log.info("taking doorway at r%dc%d", r, c)
            ctx.click_rel(self._tile_rel(r, c))
            self._sleep(ctx, 2.0)
            if self._is_fresh_floor(self._scan(ctx.frame())):
                return True
        return False

    def _dismiss_tips(self, ctx: Context, frame=None) -> bool:
        """Click OK on the "Statue found, auto-mining ends" tip if it is up."""
        frame = frame if frame is not None else ctx.frame()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = TIPS_REGION.to_pixels(w, h)
        text = " ".join(t for t, _, _ in ocr_lines(frame[y0:y1, x0:x1])).lower()
        if "auto-mining" in text or "statue found" in text:
            ctx.log.info("dismissing 'statue found' tip")
            ctx.click_rel(TIPS_OK_BTN)
            self._sleep(ctx, 1.0)
            return True
        return False

    def _dismiss_close_popup(self, ctx: Context) -> bool:
        """Close any reward summary that is up ("Tap to close"). Returns True if
        one was dismissed."""
        dismissed = False
        for _ in range(4):
            if ctx.should_stop() or self._prompt(ctx) != "close":
                break
            ctx.click_rel(CLOSE_TAP)
            self._sleep(ctx, 1.0)
            dismissed = True
        return dismissed

    def _clear_popups(self, ctx: Context) -> None:
        """Dismiss any popups covering the board (the 'statue found' tip and the
        'Rewards' summary that every Auto-Mine click raises), so a board scan
        reads real tiles instead of a dimmed overlay."""
        for _ in range(6):
            if ctx.should_stop():
                return
            if self._dismiss_tips(ctx):
                continue
            if self._prompt(ctx) == "close":
                ctx.click_rel(CLOSE_TAP)
                self._sleep(ctx, 1.0)
                continue
            return

    def _auto_mine(self, ctx: Context) -> str:
        """Dig with Auto-Mine until the statue surfaces or picks run out.

        Each Auto-Mine click digs a batch and always raises a popup: the
        "Statue found, auto-mining ends" tip (the statue is now revealed) or a
        "Rewards" summary (loot claimed, keep digging). So this clicks in a loop,
        resolving the popup each time. Outcomes:
          "statue"  the statue is showing -> identify + handle it
          "empty"   the refill button is up (out of picks) -> refill
          "timeout" the click budget ran out"""
        for _ in range(30):
            if ctx.should_stop():
                return "timeout"
            # No point clicking Auto-Mine with no picks. Out of picks shows as
            # either the refill button or a "0/100" counter (refills used up).
            if self._refill_available(ctx):
                return "empty"
            picks = self._read_picks(ctx)
            if picks is not None and picks <= 0:
                return "empty"
            ctx.log.info("Auto-Mine")
            ctx.click_rel(AUTO_MINE_BTN)
            # Wait out this click's popup (every click raises one when it digs):
            # the "statue found" tip means the statue is now revealed; a rewards
            # summary means loot was claimed and there's more to dig.
            tip = False
            for _ in range(12):
                if ctx.should_stop():
                    return "timeout"
                self._sleep(ctx, 0.5)
                if self._dismiss_tips(ctx):             # statue found -> revealed
                    tip = True
                    break
                if self._prompt(ctx) == "close":        # rewards -> dig again
                    self._dismiss_close_popup(ctx)
                    break
                if self._refill_available(ctx):         # out of picks
                    return "empty"
            # Let the board settle, then confirm a statue by an actual template
            # match -- not a raw colour read, which flickers during the dig.
            self._clear_popups(ctx)
            self._board_settled(ctx)
            if tip or self._identify(ctx):
                return "statue"
            # nothing yet -> click Auto-Mine again
        ctx.log.info("Auto-Mine did not finish within the click budget")
        return "timeout"

    # --- main loop ---------------------------------------------------------
    def run(self, ctx: Context) -> None:
        # Confirm the mining screen, retrying a few times: the very first frame
        # can catch a transition (clouds) or a leftover popup.
        on_screen = False
        for _ in range(4):
            ctx.window.focus()
            self._clear_popups(ctx)
            if self._on_mining_screen(ctx):
                on_screen = True
                break
            self._sleep(ctx, 0.8)
        if not on_screen:
            ctx.log.warning("not on the Goblin Miner screen -> open Goblin Miner "
                            "and start again")
            return

        min_picks = self.params["min_picks"]
        floors = 0
        while not ctx.should_stop():
            picks = self._read_picks(ctx)
            ctx.log.info("floor %d start (picks: %s)", floors + 1,
                         picks if picks is not None else "?")
            # Out of picks at floor start (button showing, or below the reserve):
            # claim a refill, else stop.
            if self._refill_available(ctx) or (picks is not None and picks <= min_picks):
                if not self._try_refill(ctx):
                    ctx.log.info("out of picks and no refill left -> stopping")
                    break

            # Clear any leftover popups, claim any bombs (each clears its row +
            # column, which can surface the statue), clear the reward popups the
            # blasts raise, then settle the board (also lets the task pick up an
            # already-mined floor).
            self._clear_popups(ctx)
            self._claim_bombs(ctx)
            self._clear_popups(ctx)
            board = self._board_settled(ctx)

            # A doorway already showing (statue claimed): claim any leftover
            # cracked blocks, then descend. A real doorway is exactly one tile;
            # more means a popup slipped through.
            if len(self._tiles_of(board, "door")) == 1 and \
                    not self._tiles_of(board, "statue"):
                self._claim_cracked(ctx)
                if not self._take_doorway(ctx):
                    ctx.log.warning("doorway vanished -> stopping")
                    break
                floors += 1
                ctx.log.info("floor cleared (%d total)", floors)
                continue

            # 1. Identify a statue. Rely on the fragment TEMPLATE MATCH, not the
            #    raw "statue" colour class -- a reward popup overlay turns dimmed
            #    tiles into phantom "statue" tiles, which must not drive control
            #    flow. Mine the pattern, then Auto-Mine, until a fragment matches,
            #    claiming bombs (each clears a row+column) and clearing the reward
            #    popups they raise.
            frag = self._identify(ctx)
            if not frag:
                for (r, c) in PATTERN:
                    if ctx.should_stop():
                        break
                    if board.get((r, c)) in ("stone", "unknown"):
                        self._mine_tile(ctx, r, c)
                    self._claim_bombs(ctx)
                    self._clear_popups(ctx)
                    frag = self._identify(ctx)
                    if frag:                        # stop digging once found
                        break

            unidentified = None
            if not frag:
                while not ctx.should_stop():
                    outcome = self._auto_mine(ctx)
                    self._claim_bombs(ctx)
                    self._clear_popups(ctx)
                    frag = self._identify(ctx)
                    if frag:
                        break
                    if outcome == "statue":
                        # A statue is revealed but no template matched it -- a
                        # size not in the library (all three are captured, so
                        # this is rare). Report the real (contiguous) blob.
                        unidentified = self._real_statue(ctx)
                        break
                    if outcome == "empty" and self._try_refill(ctx):
                        continue
                    break

            if ctx.should_stop():
                break

            if not frag:
                if unidentified:
                    self._report_unidentified(ctx, unidentified)
                else:
                    ctx.log.info("no statue reached (out of picks?) -> stopping")
                break

            # 2. Reveal the rest of the footprint, then open + claim + descend.
            size, pos, r, c, score = frag
            footprint = self._footprint(size, pos, r, c)
            ctx.log.info("statue %s (%s) at r%dc%d match=%.2f -> footprint %s",
                         size, pos or "single", r, c, score, sorted(footprint))
            self._reveal_footprint(ctx, footprint)
            if not self._handle_statue(ctx, footprint):
                ctx.log.warning("statue flow did not return to the grid -> stopping")
                break
            # With the statue done, claim any cracked blocks (buried rewards)
            # before dropping down.
            self._claim_cracked(ctx)
            if not self._take_doorway(ctx):
                ctx.log.warning("no doorway found -> stopping")
                break

            floors += 1
            ctx.log.info("floor cleared (%d total)", floors)

        ctx.log.info("goblin-miner done: %d floor(s) cleared", floors)
