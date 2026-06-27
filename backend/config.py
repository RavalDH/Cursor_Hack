"""Application settings.

Everything is driven by environment variables (loaded from a local .env) so the
same code runs on a developer laptop and on an underground edge box without code
changes. There is intentionally nothing here that points at the cloud — the
whole premise is that this runs with the internet switched off.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings, validated once at startup.

    Why pydantic-settings: a typo in a threshold or port is a config bug we want
    to catch at boot, not three hours into a demo. Types are enforced here.
    """

    # --- MQTT: the local stand-in for the mine's self-healing mesh ---
    # When False we skip MQTT entirely and drive zones from an internal timer.
    # This is the live-demo safety net: if Mosquitto isn't running, the demo
    # still shows identical /zones behaviour.
    use_mqtt: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_base_topic: str = "mine"
    mqtt_keepalive: int = 60

    # --- Zones ---
    # Stored as a raw comma-separated string and split lazily; this avoids the
    # JSON-parsing that pydantic-settings applies to list-typed env vars.
    zones: str = "zone1,zone2,zone3,zone4"
    # The single zone whose methane slowly climbs, so the demo has a clear trend.
    climbing_zone: str = "zone3"

    # --- Trend / thresholds (DEMO values; real legal limits differ) ---
    history_size: int = 10
    methane_danger: float = 1.5
    methane_warning: float = 1.0
    # A "rising" trend only escalates a zone to yellow once methane is already in
    # this early-warning band. Without it, normal sensor noise on a calm zone
    # (~0.5%) can read as "rising" and false-flag a safe zone yellow.
    methane_early_warning: float = 0.9
    co_warning: float = 35.0
    co_danger: float = 100.0

    # --- Simulator: gas source + ventilation mitigation model ---
    # How fast the demo zone's methane climbs while a gas inrush is active, in
    # %/tick. Tuned with publish_interval=1s so the zone crosses the 1.5% danger
    # line in roughly 10 seconds from a green baseline — fast enough to narrate
    # live without anyone waiting around.
    methane_climb_rate: float = 0.16
    # How much methane the ventilation fan removes per tick at full speed, in
    # %/tick (scaled by fan_speed/100). Tuned so a red zone, once the fan is
    # ramped up, recovers back to green in ~15-20s. Mitigation is airflow ONLY:
    # we never add oxygen, since enriching oxygen underground worsens explosion
    # risk — the only safe lever is diluting and sweeping the gas out.
    mitigation_rate: float = 0.11

    # --- Simulator ---
    publish_interval: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def zone_list(self) -> list[str]:
        """Zone ids as a clean list, e.g. ['zone1', 'zone2', ...]."""
        return [z.strip() for z in self.zones.split(",") if z.strip()]

    def topic_for(self, zone: str) -> str:
        """Build the gas topic for a zone, e.g. 'mine/zone1/gas'."""
        return f"{self.mqtt_base_topic}/{zone}/gas"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so every module sees the same configuration and we read the .env once.
    """
    return Settings()
