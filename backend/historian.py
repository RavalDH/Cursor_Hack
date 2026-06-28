"""Offline data historian — the durable record on disk.

Append-only JSON Lines, one file per day. Two streams: telemetry/ for raw
readings, events/ for transitions/alerts/blasts. Writes are locked (paho writes
off-thread) and guarded so a disk error never takes monitoring down.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Historian:
    """Writes telemetry and event records to dated, append-only JSONL files."""

    def __init__(self, base_dir: Path, enabled: bool = True) -> None:
        self._enabled = enabled
        self._base = base_dir
        self._telemetry_dir = base_dir / "telemetry"
        self._events_dir = base_dir / "events"
        self._lock = threading.Lock()
        self._warned = False  # log a recurring write error once, not per line

        if self._enabled:
            try:
                self._telemetry_dir.mkdir(parents=True, exist_ok=True)
                self._events_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Historian writing to %s", self._base)
            except OSError as exc:
                logger.warning(
                    "Could not create historian dirs at %s (%s); disabling "
                    "on-disk historian, monitoring continues from memory.",
                    self._base,
                    exc,
                )
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def _now() -> datetime:
        return datetime.now()

    def _dated_file(self, directory: Path, prefix: str, now: datetime) -> Path:
        """One file per local day, e.g. telemetry/telemetry-2026-06-27.jsonl."""
        return directory / f"{prefix}-{now:%Y-%m-%d}.jsonl"

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        """Append one record as a JSON line. Guarded; never raises to the caller."""
        if not self._enabled:
            return
        try:
            line = json.dumps(record, separators=(",", ":"))
            with self._lock:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except (OSError, TypeError) as exc:
            if not self._warned:
                logger.warning("Historian write failed (%s); further errors muted", exc)
                self._warned = True

    def log_reading(self, level_id: str, reading: Any) -> None:
        """Persist one raw multi-gas reading for a level (high-rate stream)."""
        now = self._now()
        record = {
            "ts": now.isoformat(timespec="seconds"),
            "level": level_id,
            **_reading_to_dict(reading),
        }
        self._append(self._dated_file(self._telemetry_dir, "telemetry", now), record)

    def log_event(self, kind: str, level_id: str | None = None, **fields: Any) -> None:
        """Persist a notable event. `kind` is a tag like "status_change"; extra context as kwargs."""
        now = self._now()
        record: dict[str, Any] = {"ts": now.isoformat(timespec="seconds"), "event": kind}
        if level_id is not None:
            record["level"] = level_id
        record.update(fields)
        self._append(self._dated_file(self._events_dir, "events", now), record)
        # Events are rare and important — mirror into the app log too.
        logger.info("event %s %s", kind, {k: v for k, v in fields.items()})


def _reading_to_dict(reading: Any) -> dict[str, Any]:
    """Pull the gas fields off a GasReading (or any object/dict) defensively."""
    if hasattr(reading, "model_dump"):
        return reading.model_dump()
    if isinstance(reading, dict):
        return reading
    # Last resort: pull known attributes one by one.
    keys = ("methane", "co", "co2", "no2", "o2", "temp", "airflow", "fan_speed")
    return {k: getattr(reading, k, None) for k in keys}
