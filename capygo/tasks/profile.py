"""A player's profile ("Character Info"): open it, read it, close it.

Shared by get-guild-member-list (each member's UID and power) and the PvP fight
log (each opponent before a fight; see pvp.py). Tapping a player's picture opens
the screen: the "Character Info" banner, an info box (Name, UID with a copy
button, Guild, Chapter), the six gear slots beside the character, the power
under the character with HP / ATK / DEF below it, then Pets.

  - The UID is exact: the copy button next to it puts it on the clipboard.
  - Power and the stats are OCR'd and stored in trillions (1.38T -> 1.38,
    905.85B -> 0.90585, 162.48M -> 0.00016248).
  - The weapon is the top-left gear slot. Its picture is matched against the
    labeled pictures in templates/profile/weapons/<name>.png (user: fewer than 10
    kinds). A picture that matches none is saved once to
    ~/Downloads/capy-bot/pvp/weapons/unknown-N.png and reported as "unknown-N":
    rename it to the weapon's name and move it into templates/profile/weapons/
    to teach it.

UID, power and the close button are the positions get-guild-member-list has
always used. Name, the stats and the weapon slot were placed from a half-size
screenshot of the guild-trade profile and still need checking on a live one.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import cv2

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
# Not checked on a live profile yet (from a half-size guild-trade screenshot):
NAME_REGION = RelRect(0.30, 0.150, 0.60, 0.040)     # the info box's "Name" row
STATS_REGION = RelRect(0.20, 0.600, 0.60, 0.040)    # HP / ATK / DEF, under the power
WEAPON_SLOT = RelRect(0.184, 0.300, 0.118, 0.084)   # the top-left gear slot

TITLE_MATCH = 0.85
WEAPON_MATCH = 0.80       # a labeled weapon picture counts from here
UNKNOWN_SAME = 0.90       # an unknown picture this close to a saved one is that one
CLIP_SENTINEL = "capygo-none"  # seeded before a copy so a stale value can't fool us

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
                                             key=lambda l: l[1]))
    return re.sub(r"^\s*name\s*:?\s*", "", text, flags=re.I).strip()


def read_stats(frame) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """HP, ATK, DEF under the power, in trillions (None where unread)."""
    vals = _values(frame, STATS_REGION)
    vals += [None] * (3 - len(vals))
    return vals[0], vals[1], vals[2]


# --- the weapon ---------------------------------------------------------------
def _weapon_icon(frame):
    """The weapon picture: the top-left gear slot, grey, trimmed to its middle so
    the slot's level text and stars count less."""
    slot = cv2.cvtColor(_crop(frame, WEAPON_SLOT), cv2.COLOR_BGR2GRAY)
    h, w = slot.shape[:2]
    return slot[int(h * 0.15):int(h * 0.80), int(w * 0.15):int(w * 0.85)]


def _best_match(icon, folder: str, prefix: str = "") -> tuple[str, float]:
    best, score = "", 0.0
    if not os.path.isdir(folder):
        return best, score
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".png") or not f.startswith(prefix):
            continue
        ref = cv2.imread(os.path.join(folder, f), cv2.IMREAD_GRAYSCALE)
        if ref is None:
            continue
        ref = cv2.resize(ref, (icon.shape[1], icon.shape[0]))
        s = float(cv2.matchTemplate(icon, ref, cv2.TM_CCOEFF_NORMED).max())
        if s > score:
            best, score = f[:-4], s
    return best, score


def read_weapon(frame) -> str:
    """The weapon's name from its picture, or "unknown-N" for one not labeled yet
    (its picture is saved for labeling, once per kind)."""
    icon = _weapon_icon(frame)
    name, score = _best_match(icon, WEAPONS_DIR)
    if name and score >= WEAPON_MATCH:
        return name
    unknown = output_path(os.path.join("pvp", "weapons"))
    os.makedirs(unknown, exist_ok=True)
    seen, score = _best_match(icon, unknown, "unknown-")
    if seen and score >= UNKNOWN_SAME:
        return seen
    n = 1 + sum(f.startswith("unknown-") for f in os.listdir(unknown))
    cv2.imwrite(os.path.join(unknown, f"unknown-{n}.png"), icon)
    return f"unknown-{n}"


# --- all of it ----------------------------------------------------------------
def read_profile(ctx: Context, save_to: str | None = None) -> Profile:
    """Read the open Character Info screen. `save_to`: also save the screenshot
    there (a .png path)."""
    frame = ctx.frame()
    p = Profile()
    p.uid = read_uid(ctx)
    p.name = read_name(frame)
    p.power = read_power(frame)
    p.hp, p.atk, p.defense = read_stats(frame)
    try:
        p.weapon = read_weapon(frame)
    except Exception as e:  # a weapon read must never break a fight
        p.notes.append(f"weapon: {e}")
    if save_to and cv2.imwrite(save_to, frame):
        p.screenshot = save_to
    return p
