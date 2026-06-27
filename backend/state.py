"""Thread-safe in-memory store of the latest readings per zone.

Why thread-safe: in MQTT mode the paho client runs its network loop on a
background thread and writes readings here, while FastAPI handlers read from here
on the request thread. Without a lock, the API could read a half-updated zone.
The store is intentionally in-memory only — there is no database, because at the
edge underground we care about *now*, and simplicity means fewer things to fail.
"""

import threading
import time
from collections import deque

from models import GasReading


class ZoneState:
    """Holds a bounded history of readings for a single zone."""

    def __init__(self, zone_id: str, history_size: int) -> None:
        self.zone_id = zone_id
        # A deque with maxlen automatically drops the oldest reading, so we keep
        # exactly the last N without any manual trimming.
        self.readings: deque[GasReading] = deque(maxlen=history_size)
        self.last_update: float | None = None
        # Recovery tracking for the "all clear" message on /alert. We latch
        # `was_red` while a zone is red and clear it on the return to green —
        # because a recovering zone physically passes back through yellow, so a
        # strict red->green adjacency check would almost never fire.
        self.was_red: bool = False
        self.recovered_at: float | None = None

    def add(self, reading: GasReading) -> None:
        self.readings.append(reading)
        self.last_update = time.time()

    @property
    def latest(self) -> GasReading | None:
        return self.readings[-1] if self.readings else None


class StateStore:
    """Central, lock-guarded store for all zones.

    All mutation and reads go through the same lock. The critical sections are
    tiny (append to a deque, copy a list) so contention is a non-issue, and we
    get correctness for free.
    """

    def __init__(self, zone_ids: list[str], history_size: int) -> None:
        self._lock = threading.Lock()
        self._history_size = history_size
        self._zones: dict[str, ZoneState] = {
            zid: ZoneState(zid, history_size) for zid in zone_ids
        }

    def update(self, zone_id: str, reading: GasReading) -> None:
        """Record a new reading for a zone (called by the MQTT/timer writer)."""
        with self._lock:
            # Tolerate readings for a zone we weren't told about at startup so a
            # new sensor coming online on the mesh doesn't get dropped.
            if zone_id not in self._zones:
                self._zones[zone_id] = ZoneState(zone_id, self._history_size)
            self._zones[zone_id].add(reading)

    def get_history(self, zone_id: str) -> list[GasReading]:
        """Return a snapshot copy of one zone's readings (oldest -> newest)."""
        with self._lock:
            zone = self._zones.get(zone_id)
            return list(zone.readings) if zone else []

    def note_status(self, zone_id: str, status: str) -> None:
        """Record a zone's status and timestamp when it recovers to green.

        We latch `was_red` while the zone is red, then stamp recovered_at the
        moment it next reaches green (having passed back down through yellow).
        Idempotent across repeated polls: once cleared, a zone that simply stays
        green won't keep looking freshly recovered.
        """
        with self._lock:
            zone = self._zones.get(zone_id)
            if zone is None:
                return
            if status == "red":
                zone.was_red = True
            elif status == "green" and zone.was_red:
                zone.recovered_at = time.time()
                zone.was_red = False

    def recent_recovery(self, window_seconds: float = 5.0) -> str | None:
        """Return a zone id that recovered red->green within the window, if any."""
        with self._lock:
            now = time.time()
            for zone in self._zones.values():
                if zone.recovered_at and now - zone.recovered_at <= window_seconds:
                    return zone.zone_id
            return None

    def all_zone_ids(self) -> list[str]:
        with self._lock:
            return list(self._zones.keys())

    def zones_with_data(self) -> int:
        """How many zones have at least one reading — used by /health."""
        with self._lock:
            return sum(1 for z in self._zones.values() if z.readings)
