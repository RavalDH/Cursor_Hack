"""Centralised logging configuration — console plus a time-rotated file on disk.

Two destinations on purpose:

  * **Console** — what you watch live during the demo.
  * **A daily-rotating file** (`logs/app.log`, rolled at midnight, kept N days) —
    the durable offline record of what the software itself did: startups, MQTT
    connects/drops, skipped bad payloads, errors. This is separate from the
    historian's telemetry/event streams, which capture mine *data*; this captures
    application *behaviour*. Both live under the same offline log directory.

Rotating by time (not size) matches the "time-based logging" requirement and
makes it trivial to find "what did the box do last Tuesday night".
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(log_dir: Path, level: str = "INFO", retention_days: int = 14) -> Path:
    """Set up root logging once: console + daily-rotating file. Returns the file.

    Idempotent — safe to call from app startup even if uvicorn's --reload imports
    the module more than once; handlers are only attached the first time.
    """
    global _CONFIGURED

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    if _CONFIGURED:
        return log_file

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Roll at midnight, keep `retention_days` days of history. The dated suffix
    # (app.log.2026-06-27) is added automatically on rollover.
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        backupCount=retention_days,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _CONFIGURED = True
    return log_file
