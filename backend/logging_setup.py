"""Logging config: console plus a daily-rotating logs/app.log.

The file is the durable record of what the software did (startups, MQTT
connects/drops, errors) — separate from the historian, which logs mine data.
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(log_dir: Path, level: str = "INFO", retention_days: int = 14) -> Path:
    """Set up console + daily-rotating file logging once. Idempotent under --reload. Returns the file."""
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

    # Roll at midnight, keep `retention_days` days; dated suffix added on rollover.
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
