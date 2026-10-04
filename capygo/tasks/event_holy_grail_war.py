"""Event: holy-grail-war.

Events -> Arena tab -> Holy Grail War (4th card) -> the "Hero Plaza". Likes both
champions on the Supreme division it opens to, then switches with the top-left
button to the middle option (Dauntless) and the top option (Rising Star), liking
both each time, then backs out to the Events screen. The flow is shared with
martial-arts (event_plaza.py).
"""

from __future__ import annotations

from ..geometry import Rel
from ..task import register
from .event_plaza import PlazaLikes


@register("holy-grail-war")
class HolyGrailWar(PlazaLikes):
    TITLE = "Holy Grail War"
    LABEL = "Holy Grail War likes"
    ICON = "👍"
    DESCRIPTION = ("Events -> Arena -> Holy Grail War: like both champions in the "
                   "Supreme, Dauntless and Rising Star divisions, then go back.")
    START_HINT = "Start on the main Adventure screen."

    CARD = Rel(0.35, 0.64)
    TITLE_WORD = "hero plaza"
    THUMBS = [("left", Rel(0.319, 0.611)), ("right", Rel(0.685, 0.611))]
    PICKER_BTN = Rel(0.171, 0.195)
    FIRST = "Supreme"
    DIVISIONS = [("Dauntless", Rel(0.249, 0.337)),     # picker: middle option
                 ("Rising Star", Rel(0.249, 0.252))]   # picker: top option
