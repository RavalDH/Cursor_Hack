"""Thread-safe in-memory store of the latest readings per level.

The "right now" view; durability lives in historian.py. Locked because in MQTT
mode paho writes from its network thread while request handlers read here.
"""

import threading
import time
from collections import deque

from models import GasReading


class LevelState:
    """Holds a bounded history of readings for a single level."""

    def __init__(self, level_id: str, history_size: int) -> None:
        self.level_id = level_id
        # maxlen deque keeps exactly the last N readings, no manual trimming.
        self.readings: deque[GasReading] = deque(maxlen=history_size)
        self.last_update: float | None = None
        # Last status, for detecting transitions in the event log.
        self.last_status: str | None = None
        # Recovery latch for the all-clear: set on red, cleared on the return to
        # green. (A recovering level passes back through yellow, so a strict
        # red->green adjacency check would rarely fire.)
        self.was_red: bool = False
        self.recovered_at: float | None = None

    def add(self, reading: GasReading) -> None:
        self.readings.append(reading)
        self.last_update = time.time()

    @property
    def latest(self) -> GasReading | None:
        return self.readings[-1] if self.readings else None


class StateStore:
    """Central, lock-guarded store for all levels."""

    def __init__(self, level_ids: list[str], history_size: int) -> None:
        self._lock = threading.Lock()
        self._history_size = history_size
        self._levels: dict[str, LevelState] = {
            lid: LevelState(lid, history_size) for lid in level_ids
        }

    def update(self, level_id: str, reading: GasReading) -> None:
        """Record a new reading for a level (called by the MQTT/timer writer)."""
        with self._lock:
            # Accept a level we didn't know at startup (new sensor on the mesh).
            if level_id not in self._levels:
                self._levels[level_id] = LevelState(level_id, self._history_size)
            self._levels[level_id].add(reading)

    def get_history(self, level_id: str) -> list[GasReading]:
        """Return a snapshot copy of one level's readings (oldest -> newest)."""
        with self._lock:
            level = self._levels.get(level_id)
            return list(level.readings) if level else []

    def note_status(self, level_id: str, status: str) -> tuple[str, str] | None:
        """Record status; return (old, new) on change, else None. Maintains the recovery latch."""
        with self._lock:
            level = self._levels.get(level_id)
            if level is None:
                return None

            old = level.last_status
            transition = (old, status) if old is not None and old != status else None
            level.last_status = status

            if status == "red":
                level.was_red = True
            elif status == "green" and level.was_red:
                level.recovered_at = time.time()
                level.was_red = False

            return transition

    def recent_recovery(self, window_seconds: float = 5.0) -> str | None:
        """Return a level id that recovered red->green within the window, if any."""
        with self._lock:
            now = time.time()
            for level in self._levels.values():
                if level.recovered_at and now - level.recovered_at <= window_seconds:
                    return level.level_id
            return None

    def all_level_ids(self) -> list[str]:
        with self._lock:
            return list(self._levels.keys())

    def levels_with_data(self) -> int:
        """How many levels have at least one reading — used by /health."""
        with self._lock:
            return sum(1 for lvl in self._levels.values() if lvl.readings)
