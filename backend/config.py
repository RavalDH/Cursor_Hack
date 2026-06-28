"""Application settings, driven by env vars (local .env). Nothing points at the cloud.

Operating parameters live here (gas limits, ventilation tuning, historian, broker);
the mine's shape lives in mine.py.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

import mine


class Settings(BaseSettings):
    """Typed settings, validated once at startup so a bad threshold/port fails at boot."""

    # --- MQTT: local stand-in for the mine mesh ---
    # False = skip MQTT and drive levels from an internal timer (demo safety net).
    use_mqtt: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_base_topic: str = "mine"
    mqtt_keepalive: int = 60

    # --- Levels ---
    # Comma-separated ids; blank = full layout from mine.py. Topic: mine/<level>/gas.
    levels: str = ""
    # The level driven by the drill-and-blast cycle. Must be one of the levels.
    active_blast_level: str = mine.ACTIVE_BLAST_LEVEL

    # --- Trend / history ---
    # Recent readings kept per level for trend + rolling averages.
    history_size: int = 12

    # --- Gas limits (DEMO values — compressed so danger hits in seconds, not legal use) ---
    # Methane, % by volume.
    methane_warning: float = 1.0
    methane_danger: float = 1.5
    # A rising trend only escalates to yellow once methane is in this band, so
    # sensor noise on a calm level can't false-flag it.
    methane_early_warning: float = 0.9

    # Carbon monoxide, ppm. CO clears slowest, so it drives re-entry.
    co_warning: float = 25.0
    co_danger: float = 100.0

    # Nitrogen dioxide, ppm — the other blast gas, toxic at low ppm.
    no2_warning: float = 3.0
    no2_danger: float = 5.0

    # Carbon dioxide, % by volume (normal ~0.04%).
    co2_warning: float = 0.5
    co2_danger: float = 1.5

    # Oxygen, % by volume — here LOW is the hazard. Normal 20.9%.
    o2_warning: float = 19.5
    o2_danger: float = 18.0

    # --- Ventilation-on-demand + post-blast model (demo tuning) ---
    methane_climb_rate: float = 0.16
    # Methane swept out per tick at full fan. Airflow only — never O2 enrichment
    # (more oxygen underground raises explosion risk).
    mitigation_rate: float = 0.11
    # Post-blast peaks on the active level, set well above the re-entry limit so
    # the clear -> re-entry arc is visible.
    blast_co_peak: float = 220.0
    blast_no2_peak: float = 8.0
    # Fraction of post-blast gas cleared per tick at full fan.
    blast_clear_rate: float = 0.18
    # Seconds the level rests (crew working) before the next blast.
    blast_rest_seconds: float = 8.0

    # --- Simulator ---
    publish_interval: float = 1.0

    # --- Offline historian (append-only files on disk, survives restarts) ---
    log_dir: str = "logs"  # relative to the backend folder
    log_retention_days: int = 14
    historian_enabled: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def level_list(self) -> list[str]:
        """Level ids as a clean list, falling back to the full mine layout."""
        configured = [z.strip() for z in self.levels.split(",") if z.strip()]
        return configured or mine.level_ids()

    @property
    def log_path(self) -> Path:
        """Absolute path to the historian/log directory (created on startup)."""
        p = Path(self.log_dir)
        if not p.is_absolute():
            p = Path(__file__).parent / p
        return p

    def topic_for(self, level: str) -> str:
        """Build the gas topic for a level, e.g. 'mine/1200L/gas'."""
        return f"{self.mqtt_base_topic}/{level}/gas"


@lru_cache
def get_settings() -> Settings:
    """Cached Settings, so every module shares one config and .env is read once."""
    return Settings()
