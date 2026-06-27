"""The mine model — the physical layout the rest of the system reasons about.

Real underground mines are not divided into abstract "zones"; they are divided
into **levels**: horizontal working horizons driven off the shaft/ramp at a
fixed depth below surface, named after that depth (e.g. the "1200 Level" sits
~1200 m down). Levels are connected vertically by the shaft and raises and by an
inclined ramp, and air is pushed down *intake* airways, swept across the working
levels, and pulled out through *return* airways.

This module is the single source of truth for that layout. Keeping it separate
from config.py means the mine's shape (how many levels, how deep, what each one
is doing) is described in one obvious place, the way a ventilation engineer would
sketch it, rather than being smeared across the simulator and the API.

Nothing here is copied from any vendor's product — it's a deliberately small,
generic hard-rock layout built only to make the demo behave like a real mine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Level:
    """One working horizon of the mine.

    depth_m       metres below the collar (surface). Levels are named by depth,
                  so id "1200L" is the 1200 m level.
    name          human label spoken/shown in the UI ("1200 Level").
    area          what is physically happening on this level right now — this is
                  what makes the demo read like a mine instead of a dashboard.
    airway        the level's role in the ventilation circuit. Fresh air enters
                  on an "intake" level, does work on a "working" level, and
                  leaves via a "return" level. Gas naturally rides toward return.
    """

    id: str
    depth_m: int
    name: str
    area: str
    airway: str  # "intake" | "working" | "return"


# A compact, realistic hard-rock layout: four levels on ~400 m spacing, one
# fresh-air intake at the top, two working levels in the middle (one of them the
# active production level where blasting happens), and a return airway at the
# bottom that carries spent air back to surface.
MINE_NAME = "North Range Mine"

MINE_LEVELS: list[Level] = [
    Level(
        id="400L",
        depth_m=400,
        name="400 Level",
        area="Fresh-air intake & main haulage drift",
        airway="intake",
    ),
    Level(
        id="800L",
        depth_m=800,
        name="800 Level",
        area="Sublevel development heading",
        airway="working",
    ),
    Level(
        id="1200L",
        depth_m=1200,
        name="1200 Level",
        area="Active production stope (drill & blast)",
        airway="working",
    ),
    Level(
        id="1600L",
        depth_m=1600,
        name="1600 Level",
        area="Return airway & ore pass",
        airway="return",
    ),
]

# The level whose air is driven by the drill-and-blast cycle: a blast there fills
# the heading with CO/NO2, then ventilation clears it for re-entry. This is the
# level that produces the live "blast -> clearing -> re-entry -> safe" story.
ACTIVE_BLAST_LEVEL = "1200L"

_BY_ID: dict[str, Level] = {lvl.id: lvl for lvl in MINE_LEVELS}


def level_ids() -> list[str]:
    """Ids in top-down (shallow-to-deep) order, e.g. ['400L', ...]."""
    return [lvl.id for lvl in MINE_LEVELS]


def get_level(level_id: str) -> Level | None:
    """Look up a level by id, or None if it isn't part of the known layout."""
    return _BY_ID.get(level_id)


def _depth_from_id(level_id: str) -> int:
    """Best-effort depth for an id we weren't told about up front.

    A new sensor can come online on a level that isn't in the static catalog
    (the mesh discovers it). We still want a sensible depth, so we read the
    leading digits of the id ("950L" -> 950) and fall back to 0 if there are
    none.
    """
    match = re.match(r"\s*(\d+)", level_id)
    return int(match.group(1)) if match else 0


def describe(level_id: str) -> Level:
    """Return the Level for an id, synthesising a generic one if unknown.

    This guarantees the API always has depth/area/airway to report, even for a
    level that joined the mesh after startup, so the UI never shows blanks.
    """
    known = _BY_ID.get(level_id)
    if known is not None:
        return known
    depth = _depth_from_id(level_id)
    return Level(
        id=level_id,
        depth_m=depth,
        name=f"{depth} Level" if depth else level_id,
        area="Working area",
        airway="working",
    )
