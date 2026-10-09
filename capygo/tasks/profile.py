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
    saved once, in color, to ~/Downloads/capy-bot/pvp/weapons/unknown-N.png and
    reported as "unknown-N": rename it to the weapon's name and move it into
    templates/profile/weapons/ to teach it.

Positions measured on a live profile (2026-10-09, a guild member's): Name "MKM"
at y 182 (a guild role tag like "Leader" can follow it), UID copy button
(523, 209), power 33.11T at y 565, HP 86.73B / ATK 32.8B / DEF 450.82M at y 599,
the weapon slot (sword badge) at x 118-192, y 298-372 (black border to black
border; its gems start at 373). The banner rests at y 137 (171 while the screen
still slides in).
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
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

UID_COPY_BTN = Rel(0.815, 0.220)          # copy-to-clipboard button next to the UID
POWER_REGION = RelRect(0.397, 0.576, 0.203, 0.037)  # value below the character
CLOSE_BTN = Rel(0.5, 0.925)               # floating X: closes the top popup
NAME_REGION = RelRect(0.506, 0.177, 0.327, 0.029)   # the Name value cell
STATS_REGION = RelRect(0.218, 0.615, 0.561, 0.029)  # HP / ATK / DEF, under the power
WEAPON_SLOT = RelRect(0.1838, 0.3134, 0.1168, 0.0789)  # the top-left slot square
ROLE_TAGS = ("vice leader", "leader", "elite", "member")  # guild role after a name

TITLE_MATCH = 0.85
TITLE_REST_Y = 137        # px at 951 high: the banner's y once the screen stops sliding
WEAPON_MATCH = 0.85       # same weapon >= 0.99, another weapon <= 0.62 (50 profiles)
CLIP_SENTINEL = "capygo-none"  # seeded before a copy so a stale value can't fool us
SETTLE_TIMEOUT = 3.0      # the screen slides and fades in
STILL_DIFF = 2.0          # two frames this alike (and the banner at rest) = settled
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


def _values(frame, region: RelRect) -> list[Decimal]:
    """Every number-with-unit in a region, left to right, in trillions."""
    found = []
    for text, cx, _ in sorted(ocr_lines(_crop(frame, region)), key=lambda l: l[1]):
        for m in re.finditer(r"\d[\d.,]*\s*[KMBTkmbt]?", text):
            v = to_trillions(m.group(0))
            if v is not None:
                found.append(v)
    return found


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
    """Close Character Info with the floating X. True once it's gone."""
    for _ in range(3):
        ctx.click_rel(CLOSE_BTN)
        time.sleep(0.7)
        if not is_open(ctx.frame()):
            return True
    return not is_open(ctx.frame())


def read_uid(ctx: Context) -> str | None:
    """The exact UID: tap the copy button, read the clipboard."""
    for _ in range(3):
        ctx.set_clipboard(CLIP_SENTINEL)
        ctx.click_rel(UID_COPY_BTN)
        time.sleep(0.35)
        clip = ctx.read_clipboard().strip()
        if clip.isdigit():
            return clip
        time.sleep(0.2)
    return None


def read_power(frame) -> Decimal | None:
    """The power under the character, in trillions."""
    vals = _values(frame, POWER_REGION)
    return vals[0] if vals else None


def read_name(frame) -> str:
    """The info box's Name value (OCR; a stylized or non-Latin name may read
    poorly)."""
    text = " ".join(t for t, _, _ in sorted(ocr_lines(_crop(frame, NAME_REGION)),
                                             key=lambda l: l[1])).strip()
    for tag in ROLE_TAGS:  # a guild-mate's role tag sits right after the name
        if text.lower().endswith(" " + tag):
            return text[:-len(tag) - 1].strip()
    return text


def read_stats(frame) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """HP, ATK, DEF under the power, in trillions (None where unread)."""
    vals = _values(frame, STATS_REGION)
    vals += [None] * (3 - len(vals))
    return vals[0], vals[1], vals[2]


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


def _best_match(sig, folder: str, prefix: str = "") -> tuple[str, float]:
    """The slot picture in `folder` most like `sig`: (file stem, score)."""
    best, score = "", 0.0
    if not os.path.isdir(folder):
        return best, score
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".png") or not f.startswith(prefix):
            continue
        slot = cv2.imread(os.path.join(folder, f))
        if slot is None:
            continue
        s = float(cv2.matchTemplate(sig, _signature(slot), cv2.TM_CCOEFF_NORMED).max())
        if s > score:
            best, score = f[:-4], s
    return best, score


def read_weapon(slot) -> str:
    """The weapon's name from a snapshot of its slot (a crop of WEAPON_SLOT), or
    "unknown-N" for one not labeled yet (saved for labeling, once per kind)."""
    sig = _signature(slot)
    name, score = _best_match(sig, WEAPONS_DIR)
    if name and score >= WEAPON_MATCH:
        return re.sub(r"[-_]\d+$", "", name)  # bow_2 -> bow
    unknown = output_path(os.path.join("pvp", "weapons"))
    os.makedirs(unknown, exist_ok=True)
    seen, score = _best_match(sig, unknown, "unknown-")
    if seen and score >= WEAPON_MATCH:
        return seen
    n = 1 + sum(f.startswith("unknown-") for f in os.listdir(unknown))
    cv2.imwrite(os.path.join(unknown, f"unknown-{n}.png"), slot)
    return f"unknown-{n}"


# --- all of it ----------------------------------------------------------------
def _at_rest(frame) -> bool:
    """The banner has stopped sliding (it starts ~34px lower)."""
    m = find_template(frame, load_template(TITLE_TEMPLATE), TITLE_MATCH)
    return m.found and abs(m.y - TITLE_REST_Y * frame.shape[0] / 951) <= 3


def _settled(ctx: Context):
    """A frame once the profile has finished sliding and fading in: the banner at
    rest and two frames in a row alike around the power (a frame grabbed at once
    had no name or power and a blank weapon; two caught it mid-slide)."""
    def part(f):
        return cv2.cvtColor(_crop(f, POWER_REGION), cv2.COLOR_BGR2GRAY).astype(np.float32)
    prev = ctx.frame()
    end = time.time() + SETTLE_TIMEOUT
    while time.time() < end:
        time.sleep(0.25)
        cur = ctx.frame()
        if _at_rest(cur) and float(np.abs(part(cur) - part(prev)).mean()) < STILL_DIFF:
            return cur
        prev = cur
    return prev


def _weapon_slot(ctx: Context, frame):
    """The weapon slot as the per-pixel median of SLOT_FRAMES frames ~0.25s apart:
    the icon's sheen passes, so the median drops it."""
    slots = [_crop(frame, WEAPON_SLOT)]
    for _ in range(SLOT_FRAMES - 1):
        time.sleep(0.25)
        slots.append(_crop(ctx.frame(), WEAPON_SLOT))
    return np.median(np.stack(slots), axis=0).astype(np.uint8)


def read_profile(ctx: Context, save_to: str | None = None) -> Profile:
    """Read the open Character Info screen. `save_to`: also save the screenshot
    there (a .png path)."""
    p = Profile()
    frame = _settled(ctx)
    slot = _weapon_slot(ctx, frame)
    # The UID last: its copy button pops a "copied" notice across the middle of
    # the screen (a gold band right over the weapon slot).
    p.uid = read_uid(ctx)
    p.name = read_name(frame)
    p.power = read_power(frame)
    p.hp, p.atk, p.defense = read_stats(frame)
    try:
        p.weapon = read_weapon(slot)
    except Exception as e:  # a weapon read must never break a fight
        p.notes.append(f"weapon: {e}")
    if save_to and cv2.imwrite(save_to, frame):
        p.screenshot = save_to
    return p
