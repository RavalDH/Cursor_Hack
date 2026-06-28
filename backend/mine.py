"""The mine model — the physical layout the rest of the system reasons about.

Real mines are divided into *levels* (working horizons at a fixed depth), not
abstract zones. Air is pushed down intake airways, across the working levels,
and out the return. Single source of truth for the layout; a small generic
hard-rock mine, not copied from any product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Level:
    """One working horizon of the mine."""

    id: str
    depth_m: int  # metres below surface; levels are named by depth ("1200L")
    name: str
    area: str  # what's happening here now — makes it read like a mine
    airway: str  # ventilation role: "intake" | "working" | "return"


# Four levels on ~400 m spacing: intake on top, two working (one blasts), return
# at the bottom.
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

# The level that runs the drill-and-blast cycle (the live blast->clear->re-entry story).
ACTIVE_BLAST_LEVEL = "1200L"

_BY_ID: dict[str, Level] = {lvl.id: lvl for lvl in MINE_LEVELS}


def level_ids() -> list[str]:
    """Ids in top-down (shallow-to-deep) order, e.g. ['400L', ...]."""
    return [lvl.id for lvl in MINE_LEVELS]


def get_level(level_id: str) -> Level | None:
    """Look up a level by id, or None if it isn't part of the known layout."""
    return _BY_ID.get(level_id)


def _depth_from_id(level_id: str) -> int:
    """Best-effort depth from the id's leading digits ("950L" -> 950), else 0."""
    match = re.match(r"\s*(\d+)", level_id)
    return int(match.group(1)) if match else 0


def describe(level_id: str) -> Level:
    """Level for an id, synthesising a generic one if unknown, so the API never returns blanks."""
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
