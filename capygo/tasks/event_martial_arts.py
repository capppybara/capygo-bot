"""Event: martial-arts.

Events -> Arena tab -> Martial Arts Tournament (3rd card) -> the "Martial Arts
Hall". Same flow as holy-grail-war (event_plaza.py) but with three champions per
zone: likes all three on the Supreme zone it opens to, then switches with the
top-left button to the middle option (Valiant) and the top option (Novice), liking
all three each time, then backs out to the Events screen.
"""

from __future__ import annotations

from ..geometry import Rel
from ..task import register
from .event_plaza import PlazaLikes


@register("martial-arts")
class MartialArts(PlazaLikes):
    TITLE = "Martial Arts"
    LABEL = "Martial Arts likes"
    ICON = "🥋"
    DESCRIPTION = ("Events -> Arena -> Martial Arts Tournament: like all three "
                   "champions in the Supreme, Valiant and Novice zones, then go back.")
    START_HINT = "Start on the main Adventure screen."

    CARD = Rel(0.35, 0.475)
    TITLE_WORD = "martial arts hall"
    THUMBS = [("center", Rel(0.502, 0.519)), ("left", Rel(0.251, 0.641)),
              ("right", Rel(0.749, 0.641))]
    PICKER_BTN = Rel(0.171, 0.185)
    FIRST = "Supreme"
    DIVISIONS = [("Valiant", Rel(0.249, 0.353)),       # picker: middle option
                 ("Novice", Rel(0.249, 0.268))]        # picker: top option
