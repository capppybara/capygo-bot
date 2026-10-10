"""A player's profile ("Character Info"): open it, read it, close it.

Shared by get-guild-member-list (each member's UID and power) and the PvP fight
log (each opponent before a fight; see pvp.py). Tapping a player's picture opens
the screen: the "Character Info" banner, an info box (Name, UID with a copy
button, Guild, Chapter), the six gear slots beside the character, the power
under the character with HP / ATK / DEF below it, then Pets.

  - The UID is exact: the copy button next to it puts it on the clipboard.
  - Power and the stats are OCR'd and stored in trillions (1.38T -> 1.38,
    905.85B -> 0.90585, 162.48M -> 0.00016248).
  - The weapon is the top-left gear slot. A snapshot of the whole slot (the
    square, without the gems under it - user) is compared with the labeled slot
    pictures in templates/profile/weapons/<name>.png (user: fewer than 10 kinds).
    The comparison uses the weapon art's thick black outline only: the slot's
    border, its sword badge, the "Ex.N" level, the rarity ("SS") and the "+N"
    enhancement are masked out (user: "+N" made the same weapon look like new
    ones), and the slot's color doesn't count. On 50 guild profiles one weapon
    always scored >= 0.99 against itself and <= 0.62 against the others. The
    slot is the per-pixel median of 3 frames, because the icons are animated: a
    sheen passes through them now and then (user). A slot that matches none is
    saved once, in color, as ~/Downloads/capy-bot/pvp/weapons/unknown-N.png and
    reported as "unknown-N", with a line in unknown.csv there (when it was first
    seen, on whose profile, that profile's screenshot). To name it, rename the
    file (unknown-8.png -> laser-gun.png): pictures named in that folder count
    like the repo's from the next run on (user, 2026-10-09: "capture and store
    unknown / unclassified weapons as it runs"). Named in the repo so far (user):
    BBC, op-bow, stick, hammer, nerd-bow, amogus-bow, skibidy-six-seven-sword.

The screen is laid out a little differently depending on where it's opened from:
an arena opponent's (2026-10-09) is taller than a guild member's, with its info
box 21px higher, its power 14px and its gear 8px. So the parts are found from
anchors (layout()): the Name / UID rows from their labels, the weapon slot from
its black right border (x 191), the power and HP / ATK / DEF from the slot's top.
Guild member's: Name y 182, UID y 209 (copy button x 523), slot square x 118-192
y 298-372 (its gems start at 373), power y 565, stats y 599. Arena opponent's:
160, 190, slot top 289, power 551, stats 585. The screen slides in (its banner
starts ~34px lower), so reading waits until the banner stops moving.
"""

from __future__ import annotations

import csv
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import cv2
import numpy as np

from ..geometry import Rel, RelRect
from ..paths import output_path
from ..perception import find_template, load_template, ocr_lines
from ..task import Context

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "templates", "profile")
TITLE_TEMPLATE = os.path.join(TEMPLATES, "char_title.png")   # "Character Info"
WEAPONS_DIR = os.path.join(TEMPLATES, "weapons")             # <weapon name>.png
LOCAL_WEAPONS = os.path.join("pvp", "weapons")   # under ~/Downloads/capy-bot
UNKNOWN_INDEX = os.path.join(LOCAL_WEAPONS, "unknown.csv")

CLOSE_BTN = Rel(0.5, 0.925)               # the floating X, if its sprite isn't found
# Layout, px at 642x951 (see layout()):
LABELS = (215, 300, 120, 300)             # x0, x1, y0, y1: the info box's labels
VALUE_X = (325, 535)                      # the info box's value cells
COPY_X = 523                              # the UID's copy button, on the UID row
ROW_H = 14                                # half a row's height
SLOT_X, SLOT_SIZE = 118, 75               # the weapon slot: x 118-192, 75px square
SLOT_EDGE_X = 191                         # its right border: black from slot top + 3
SLOT_SEARCH = (250, 500)                  # where to look for that border
POWER_X, POWER_DY = (255, 385), (250, 282)   # the power: y = slot top + 250..282
STATS_X, STATS_DY = (140, 500), (284, 316)   # HP / ATK / DEF: slot top + 284..316
DEFAULT_LAYOUT = (182, 209, 298)          # name y, UID y, slot top (a guild member's)
ROLE_TAGS = ("vice leader", "leader", "elite", "member")  # guild role after a name

TITLE_MATCH = 0.85
WEAPON_MATCH = 0.85       # same weapon >= 0.99, another weapon <= 0.62 (50 profiles)
CLIP_SENTINEL = "capygo-none"  # seeded before a copy so a stale value can't fool us
SETTLE_TIMEOUT = 3.0      # the screen slides and fades in
STILL_DIFF = 2.0          # two frames this alike (banner not moving) = settled
SLOT_FRAMES = 3           # median of this many frames: drops the icon's passing sheen
SIG = 75                  # the slot is compared at 75x75 px (its size at 642x951)
DARK = 60                 # grey below this = the art's black outline

# Power in trillions with no unit letter: T stays, B/M/K (and a bare number) are
# scaled down.
POWER_UNIT_TO_TRILLION = {
    "T": Decimal(1),
    "B": Decimal("0.001"),
    "M": Decimal("0.000001"),
    "K": Decimal("0.000000001"),
    "": Decimal(10) ** -12,
}


@dataclass
class Profile:
    uid: str | None = None
    name: str = ""
    power: Decimal | None = None      # trillions
    hp: Decimal | None = None         # trillions
    atk: Decimal | None = None
    defense: Decimal | None = None
    weapon: str = ""                  # a weapon name, "unknown-N", or "" if unread
    new_weapon: bool = False          # its picture was just saved as a new unknown
    screenshot: str = ""              # where the profile screen was saved, if it was
    notes: list[str] = field(default_factory=list)


# --- numbers ------------------------------------------------------------------
def to_trillions(raw: str) -> Decimal | None:
    """Parse a power reading like '905.85B' into a Decimal in trillions
    (Decimal('0.90585')). None if it can't be parsed.

    Sanitizes a misread leading digit on a sub-T value: the game rolls K/M/B up to
    the next unit at 1000, so such a value always has a 1-3 digit integer part. A
    longer one means OCR fused the sword icon onto the number as a stray leading
    digit ("9864.97B" for "864.97B" -> 9.86T instead of 0.86T); the extra leading
    digits are dropped."""
    m = re.match(r"\s*([\d,]*\.?\d+)\s*([KMBTkmbt]?)", raw or "")
    if not m:
        return None
    numstr = m.group(1).replace(",", "")
    unit = m.group(2).upper()
    if unit in ("K", "M", "B"):
        intpart, _, frac = numstr.partition(".")
        while len(intpart) > 3:  # >999 is impossible for a sub-T unit
            intpart = intpart[1:]
        numstr = f"{intpart}.{frac}" if frac else intpart
    try:
        val = Decimal(numstr)
    except InvalidOperation:
        return None
    return val * POWER_UNIT_TO_TRILLION[unit]


def fmt_trillions(tri: Decimal) -> str:
    """A Decimal in trillions as a plain fixed-point string, no trailing zeros,
    never scientific notation ('0.90585', '1.19', '30.5')."""
    s = format(tri, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _crop(frame, region: RelRect):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region.to_pixels(w, h)
    return frame[y0:y1, x0:x1]


# --- the screen ---------------------------------------------------------------
def is_open(frame) -> bool:
    """The Character Info banner is showing."""
    return find_template(frame, load_template(TITLE_TEMPLATE), TITLE_MATCH).found


def _wait_open(ctx: Context, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if ctx.should_stop():
            return False
        if is_open(ctx.frame()):
            return True
        time.sleep(0.25)
    return is_open(ctx.frame())


def open_profile(ctx: Context, at: Rel, timeout: float = 2.5) -> bool:
    """Tap a player's picture at `at` and wait for Character Info. Two tries: the
    first click can only bring the window to the front. False if it never opened
    (then nothing needs closing)."""
    for _ in range(2):
        ctx.click_rel(at)
        if _wait_open(ctx, timeout):
            return True
    return False


def close_profile(ctx: Context) -> bool:
    """Close Character Info with its floating X (found by its sprite: it sits
    lower on the taller arena layout). True once it's gone."""
    from .daily import find_sprite

    for _ in range(3):
        x = find_sprite(ctx, ctx.frame(), "close_x.png")
        if x is not None:
            ctx.click_match(x)
        else:
            ctx.click_rel(CLOSE_BTN)
        time.sleep(0.7)
        if not is_open(ctx.frame()):
            return True
    return not is_open(ctx.frame())


@dataclass
class Layout:
    """Where this profile's parts are, px at 642x951."""
    name_y: float
    uid_y: float
    slot_top: float


def _slot_top(frame) -> float | None:
    """The weapon slot's top: its right border is a black line from 3px below it."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    y0, y1 = int(SLOT_SEARCH[0] * ky), int(SLOT_SEARCH[1] * ky)
    col = frame[y0:y1, int(SLOT_EDGE_X * kx)].mean(axis=1) < 50
    start = None
    for i, dark in enumerate(list(col) + [False]):
        if dark and start is None:
            start = i
        elif not dark and start is not None:
            if i - start >= 50 * ky:
                return (y0 + start) / ky - 3
            start = None
    return None


def layout(frame) -> Layout:
    """Find the Name / UID rows (their labels) and the weapon slot (its border).
    Anything not found falls back to a guild member's layout."""
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    x0, x1, y0, y1 = LABELS
    rows = {}
    for t, _, cy in ocr_lines(frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]):
        rows.setdefault(t.strip().lower(), cy / ky + y0)
    name_y, uid_y, top = DEFAULT_LAYOUT
    return Layout(rows.get("name", name_y), rows.get("uid", uid_y),
                  _slot_top(frame) or top)


def _px(frame, x0, x1, y0, y1):
    h, w = frame.shape[:2]
    kx, ky = w / 642, h / 951
    return frame[int(y0 * ky):int(y1 * ky), int(x0 * kx):int(x1 * kx)]


def _values_px(frame, x0, x1, y0, y1) -> list[Decimal]:
    """Every number-with-unit in a box (px at 642x951), left to right, in
    trillions."""
    found = []
    for text, _, _ in sorted(ocr_lines(_px(frame, x0, x1, y0, y1)), key=lambda l: l[1]):
        for m in re.finditer(r"\d[\d.,]*\s*[KMBTkmbt]?", text):
            v = to_trillions(m.group(0))
            if v is not None:
                found.append(v)
    return found


def read_uid(ctx: Context, lay: Layout | None = None) -> str | None:
    """The exact UID: tap the copy button on the UID row, read the clipboard."""
    lay = lay or layout(ctx.frame())
    button = Rel(COPY_X / 642, lay.uid_y / 951)
    for _ in range(3):
        ctx.set_clipboard(CLIP_SENTINEL)
        ctx.click_rel(button)
        time.sleep(0.35)
        clip = ctx.read_clipboard().strip()
        if clip.isdigit():
            return clip
        time.sleep(0.2)
    return None


def read_uid_text(frame, lay: Layout | None = None) -> str | None:
    """The UID by OCR of its row (digits only): a fallback for the copy."""
    lay = lay or layout(frame)
    text = " ".join(t for t, _, _ in ocr_lines(
        _px(frame, *VALUE_X, lay.uid_y - ROW_H, lay.uid_y + ROW_H)))
    digits = re.sub(r"\D", "", text)
    return digits or None


def read_power(frame, lay: Layout | None = None) -> Decimal | None:
    """The power under the character, in trillions."""
    lay = lay or layout(frame)
    vals = _values_px(frame, *POWER_X, lay.slot_top + POWER_DY[0], lay.slot_top + POWER_DY[1])
    return vals[0] if vals else None


def read_name(frame, lay: Layout | None = None) -> str:
    """The info box's Name value (OCR; a stylized or non-Latin name may read
    poorly)."""
    lay = lay or layout(frame)
    text = " ".join(t for t, _, _ in sorted(ocr_lines(_px(
        frame, *VALUE_X, lay.name_y - ROW_H, lay.name_y + ROW_H)), key=lambda l: l[1])).strip()
    for tag in ROLE_TAGS:  # a guild-mate's role tag sits right after the name
        if text.lower().endswith(" " + tag):
            return text[:-len(tag) - 1].strip()
    return text


def read_stats(frame, lay: Layout | None = None
               ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """HP, ATK, DEF under the power, in trillions (None where unread)."""
    lay = lay or layout(frame)
    vals = _values_px(frame, *STATS_X, lay.slot_top + STATS_DY[0], lay.slot_top + STATS_DY[1])
    vals += [None] * (3 - len(vals))
    return vals[0], vals[1], vals[2]


def weapon_slot(frame, lay: Layout | None = None):
    """The weapon slot square (the top-left gear slot, without its gems)."""
    lay = lay or layout(frame)
    return _px(frame, SLOT_X, SLOT_X + SLOT_SIZE, lay.slot_top, lay.slot_top + SLOT_SIZE)


# --- the weapon ---------------------------------------------------------------
def _sig_mask():
    """What the comparison looks at, in the 75x75 slot: not the border, the sword
    badge (top-left), the "Ex.N" level (top-right), the rarity (bottom-left) or
    the "+N" (bottom-right)."""
    m = np.ones((SIG, SIG), np.float32)
    m[:7, :] = m[-7:, :] = 0
    m[:, :7] = m[:, -7:] = 0
    m[:22, :22] = 0
    m[:20, 26:] = 0
    m[56:, :26] = 0
    m[54:, 50:] = 0
    return m


_MASK = _sig_mask()


def _signature(slot):
    """The weapon art's black outline, blurred: what gets compared."""
    g = cv2.cvtColor(cv2.resize(slot, (SIG, SIG)), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur((g < DARK).astype(np.float32) * _MASK, (7, 7), 0)


def _best_match(sig, folder: str, unknown: bool) -> tuple[str, float]:
    """The slot picture in `folder` most like `sig`, among the unknown-N ones or
    the named ones: (file stem, score)."""
    best, score = "", 0.0
    if not os.path.isdir(folder):
        return best, score
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".png") or f.startswith("unknown-") != unknown:
            continue
        slot = cv2.imread(os.path.join(folder, f))
        if slot is None:
            continue
        s = float(cv2.matchTemplate(sig, _signature(slot), cv2.TM_CCOEFF_NORMED).max())
        if s > score:
            best, score = f[:-4], s
    return best, score


def _next_unknown(local: str) -> int:
    """The next unknown number: past every one ever used, in the folder or in
    unknown.csv, so a renamed (named) picture's number is never reused."""
    used = [int(m.group(1)) for f in os.listdir(local)
            if (m := re.fullmatch(r"unknown-(\d+)\.png", f))]
    try:
        with open(output_path(UNKNOWN_INDEX), encoding="utf-8") as f:
            used += [int(m.group(1)) for line in f
                     if (m := re.match(r"unknown-(\d+),", line))]
    except OSError:
        pass
    return 1 + max(used, default=0)


def read_weapon(slot) -> tuple[str, bool]:
    """The weapon's name from a snapshot of its slot (weapon_slot()), and
    whether it was just saved as a new unknown. Looks at the repo's named
    pictures, then the ones named on this Mac, then the unknowns; a weapon in
    none is saved as the next unknown-N.png."""
    sig = _signature(slot)
    local = output_path(LOCAL_WEAPONS)
    os.makedirs(local, exist_ok=True)
    name, score = max(_best_match(sig, WEAPONS_DIR, unknown=False),
                      _best_match(sig, local, unknown=False), key=lambda m: m[1])
    if name and score >= WEAPON_MATCH:
        return re.sub(r"[-_]\d+$", "", name), False  # bow_2 -> bow
    seen, score = _best_match(sig, local, unknown=True)
    if seen and score >= WEAPON_MATCH:
        return seen, False
    label = f"unknown-{_next_unknown(local)}"
    cv2.imwrite(os.path.join(local, f"{label}.png"), slot)
    return label, True


def _index_unknown(p: "Profile") -> None:
    """A line in unknown.csv for a weapon just saved as unknown: when, whose
    profile, and that profile's screenshot."""
    path = output_path(UNKNOWN_INDEX)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["weapon", "first_seen_utc", "uid", "name", "profile_png"])
        w.writerow([p.weapon, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    p.uid or "", p.name, p.screenshot])


# --- all of it ----------------------------------------------------------------
def _banner_y(frame) -> int | None:
    m = find_template(frame, load_template(TITLE_TEMPLATE), TITLE_MATCH)
    return m.y if m.found else None


def _settled(ctx: Context):
    """A frame once the profile has finished sliding and fading in: the banner
    in the same place in two frames in a row and the info box below it still
    (a frame grabbed at once had no name or power and a blank weapon; two caught
    it mid-slide)."""
    def part(f, y):
        h, w = f.shape[:2]
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return g[max(0, y + int(40 * h / 951)):y + int(160 * h / 951), int(100 * w / 642):int(540 * w / 642)]
    prev = ctx.frame()
    prev_y = _banner_y(prev)
    end = time.time() + SETTLE_TIMEOUT
    while time.time() < end:
        time.sleep(0.25)
        cur = ctx.frame()
        y = _banner_y(cur)
        if y is not None and prev_y is not None and abs(y - prev_y) <= 1 and \
                float(np.abs(part(cur, y) - part(prev, y)).mean()) < STILL_DIFF:
            return cur
        prev, prev_y = cur, y
    return prev


def _weapon_slot(ctx: Context, frame, lay: Layout):
    """The weapon slot as the per-pixel median of SLOT_FRAMES frames ~0.25s apart:
    the icon's sheen passes, so the median drops it."""
    slots = [weapon_slot(frame, lay)]
    for _ in range(SLOT_FRAMES - 1):
        time.sleep(0.25)
        slots.append(weapon_slot(ctx.frame(), lay))
    return np.median(np.stack(slots), axis=0).astype(np.uint8)


def read_profile(ctx: Context, save_to: str | None = None) -> Profile:
    """Read the open Character Info screen. `save_to`: also save the screenshot
    there (a .png path)."""
    p = Profile()
    frame = _settled(ctx)
    lay = layout(frame)
    slot = _weapon_slot(ctx, frame, lay)
    # The UID last: its copy button pops a "copied" notice across the middle of
    # the screen (a gold band right over the weapon slot). OCR if the copy fails.
    p.uid = read_uid(ctx, lay) or read_uid_text(frame, lay)
    p.name = read_name(frame, lay)
    p.power = read_power(frame, lay)
    p.hp, p.atk, p.defense = read_stats(frame, lay)
    try:
        p.weapon, p.new_weapon = read_weapon(slot)
    except Exception as e:  # a weapon read must never break a fight
        p.notes.append(f"weapon: {e}")
    if save_to and cv2.imwrite(save_to, frame):
        p.screenshot = save_to
    if p.new_weapon:
        try:
            _index_unknown(p)
        except OSError as e:
            p.notes.append(f"unknown.csv: {e}")
    return p
