"""Importing this package registers all tasks.

Add a new task module here so its @register decorator runs.
"""

from . import auto_daily  # noqa: F401
from . import auto_events  # noqa: F401
from . import compare_guild_power  # noqa: F401
from . import daily_adventure_assistant  # noqa: F401
from . import daily_calendar  # noqa: F401
from . import daily_claim_cards  # noqa: F401
from . import daily_energy_claim  # noqa: F401
from . import daily_shop  # noqa: F401
from . import event_arena  # noqa: F401
from . import event_dungeon_dive  # noqa: F401
from . import event_goblin_miner  # noqa: F401
from . import event_holy_grail_war  # noqa: F401
from . import event_martial_arts  # noqa: F401
from . import event_tower_challenge  # noqa: F401
from . import get_guild_member_list  # noqa: F401
from . import goblin_miner  # noqa: F401
from . import hard_mode_autorun  # noqa: F401
from . import pet_armament_chest  # noqa: F401
