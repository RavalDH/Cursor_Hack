"""Application settings.

Everything is driven by environment variables (loaded from a local .env) so the
same code runs on a developer laptop and on an underground edge box without code
changes. There is intentionally nothing here that points at the cloud — the
whole premise is that this runs with the internet switched off.

The mine's *shape* (which levels exist, how deep, what they do) lives in mine.py;
this file holds the *operating parameters*: gas limits, ventilation tuning, the
data-historian location, and the broker connection.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

import mine


class Settings(BaseSettings):
    """Typed settings, validated once at startup.

    Why pydantic-settings: a typo in a threshold or port is a config bug we want
    to catch at boot, not three hours into a demo. Types are enforced here.
    """

    # --- MQTT: the local stand-in for the mine's self-healing mesh ---
    # When False we skip MQTT entirely and drive levels from an internal timer.
    # This is the live-demo safety net: if Mosquitto isn't running, the demo
    # still shows identical /levels behaviour.
    use_mqtt: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_base_topic: str = "mine"
    mqtt_keepalive: int = 60

    # --- Levels ---
    # Comma-separated level ids. Blank means "use the full layout from mine.py".
    # Topics become mine/<level>/gas, e.g. mine/1200L/gas.
    levels: str = ""
    # The level driven by the drill-and-blast cycle (post-blast CO/NO2 surge,
    # then ventilation clears it for re-entry). Must be one of the levels.
    active_blast_level: str = mine.ACTIVE_BLAST_LEVEL

    # --- Trend / history ---
    # Number of recent readings kept per level for trend + rolling-average work.
    history_size: int = 12

    # --- Gas limits (DEMO values; tuned for a watchable demo, not legal use) ---
    # Methane, % by volume. Reg 854 acts at 1.0 / 1.25 / 2.5; we compress the top
    # end so the demo crosses "danger" in seconds rather than minutes.
    methane_warning: float = 1.0
    methane_danger: float = 1.5
    # A rising trend only escalates a level to yellow once methane is already in
    # this early-warning band, so normal sensor noise on a calm level can't
    # false-flag it.
    methane_early_warning: float = 0.9

    # Carbon monoxide, ppm. CO is the critical post-blast gas (it clears slowest),
    # so it drives re-entry. ~25 ppm is a common occupational limit; danger well
    # above that.
    co_warning: float = 25.0
    co_danger: float = 100.0

    # Nitrogen dioxide, ppm — the other significant blast gas. Low limits.
    no2_warning: float = 3.0
    no2_danger: float = 5.0

    # Carbon dioxide, % by volume. Normal air is ~0.04%.
    co2_warning: float = 0.5
    co2_danger: float = 1.5

    # Oxygen, % by volume. Here LOW is the hazard (displacement/consumption).
    # Normal is 20.9%; below ~19.5% is deficient, below 18% is dangerous.
    o2_warning: float = 19.5
    o2_danger: float = 18.0

    # --- Ventilation-on-demand (VoD) + post-blast model (demo tuning) ---
    # Methane added per tick to a background gas seep while active, %/tick.
    methane_climb_rate: float = 0.16
    # Methane removed per tick at full fan (scaled by fan_speed/100), %/tick.
    # Mitigation is airflow ONLY — never oxygen enrichment, which would worsen
    # explosion risk; the only safe lever is diluting and sweeping gas out.
    mitigation_rate: float = 0.11
    # Peak CO (ppm) immediately after a blast on the active level, before the
    # ramped fan starts clearing it. Chosen well above the re-entry limit so the
    # "no re-entry -> clearing -> re-entry" arc is clearly visible.
    blast_co_peak: float = 220.0
    # Peak NO2 (ppm) just after the blast.
    blast_no2_peak: float = 8.0
    # Fraction of post-blast gas the ventilation clears per tick at full fan.
    blast_clear_rate: float = 0.18
    # Seconds the level sits safe (re-entry granted, crew working) before the
    # next blast in the demo cycle.
    blast_rest_seconds: float = 8.0

    # --- Simulator ---
    publish_interval: float = 1.0

    # --- Offline data historian (time-based logging to disk, not just memory) ---
    # Real environmental systems log to a data historian; underground at the edge
    # we write append-only files locally so the record survives a restart and is
    # auditable offline. Directory is relative to the backend folder by default.
    log_dir: str = "logs"
    # Keep this many days of rotating application logs.
    log_retention_days: int = 14
    # Master switch for the on-disk historian (telemetry + events). The in-memory
    # store always works; this adds the durable offline record on top.
    historian_enabled: bool = True
    # Console log level for the app logger.
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
    """Return a cached Settings instance.

    Cached so every module sees the same configuration and we read the .env once.
    """
    return Settings()
