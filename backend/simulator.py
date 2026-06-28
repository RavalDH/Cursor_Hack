"""Simulated per-level sensor readings, modelled on a drill-and-blast cycle.

Two jobs:
  1. Standalone publisher (`python simulator.py`) pushing readings to MQTT.
  2. `LevelSimulator`, imported by main.py so the USE_MQTT=false timer produces
     identical readings without a broker.

The active level loops blast -> clear -> re-entry: a blast loads CO/NO2, the fan
ramps (ventilation-on-demand) to clear it, and CO (slowest to clear) governs
re-entry. Other levels sit on fresh air. Numbers tuned to be watchable in seconds.
"""

import json
import logging
import random
import time

from config import Settings, get_settings
from models import GasReading

logger = logging.getLogger(__name__)


class LevelSimulator:
    """Generates multi-gas readings for all levels.

    Closed-loop ventilation-on-demand: the fan ramps as gas builds and eases as
    the air clears. Airflow is the only lever — never O2 enrichment, which raises
    explosion risk.
    """

    # Fan dynamics (% of full speed); ramp faster than ease so it reacts hard.
    FAN_IDLE = 20.0
    FAN_RAMP = 18.0  # +%/tick while a hazard is present
    FAN_EASE = 10.0  # -%/tick once the level is clear
    _AIRFLOW_BASE = 3.0
    _AIRFLOW_RANGE = 6.0

    # Fresh-air baselines.
    _O2_FRESH = 20.9
    _CO2_FRESH = 0.04

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._blast_level = settings.active_blast_level

        # Blast-cycle state for the active level: "working" (counting to next
        # blast) or "clearing" (venting post-blast gases).
        self._phase = "working"
        self._rest_ticks = 0
        # CO must fall below this before re-entry (CO clears slowest).
        self._reentry_co = settings.co_warning

        self._state: dict[str, dict[str, float]] = {}
        for level in settings.level_list:
            self._state[level] = {
                "methane": random.uniform(0.3, 0.6),
                "co": random.uniform(3.0, 12.0),
                "co2": self._CO2_FRESH + random.uniform(0.0, 0.03),
                "no2": random.uniform(0.0, 0.3),
                "o2": self._O2_FRESH - random.uniform(0.0, 0.1),
                "temp": random.uniform(22.0, 30.0),
                "airflow": self._AIRFLOW_BASE + 0.2 * self._AIRFLOW_RANGE,
                "fan": self.FAN_IDLE,
            }

    def _drift(self, value: float, step: float, low: float, high: float) -> float:
        """Random-walk a value by +/- step and clamp it to a plausible range."""
        value += random.uniform(-step, step)
        return max(low, min(high, value))

    def step_level(self, level: str) -> GasReading:
        """Advance one level by a single tick and return its new reading."""
        s = self._state[level]

        # Temp and CO2 just drift gently on every level.
        s["temp"] = self._drift(s["temp"], 0.3, 18.0, 42.0)
        s["co2"] = self._drift(s["co2"], 0.01, self._CO2_FRESH, 2.0)

        if level == self._blast_level:
            self._step_blast_cycle(s)
            self._apply_ventilation(s)
            # Re-entry check belongs here only — it mutates the shared phase state.
            self._check_reentry(s)
        else:
            self._step_background(s)
            self._apply_ventilation(s)

        return GasReading(
            methane=round(s["methane"], 3),
            co=round(s["co"], 1),
            co2=round(s["co2"], 3),
            no2=round(s["no2"], 2),
            o2=round(s["o2"], 2),
            temp=round(s["temp"], 1),
            airflow=round(s["airflow"], 2),
            fan_speed=round(s["fan"], 1),
        )

    def _step_blast_cycle(self, s: dict[str, float]) -> None:
        """Run the active level: rest -> blast -> clearing -> rest."""
        if self._phase == "working":
            # Calm working air with a touch of noise.
            s["methane"] = self._drift(s["methane"], 0.03, 0.2, 0.7)
            s["co"] = self._drift(s["co"], 1.5, 2.0, 15.0)
            s["no2"] = self._drift(s["no2"], 0.1, 0.0, 0.5)
            s["o2"] = self._drift(s["o2"], 0.05, 20.6, self._O2_FRESH)

            self._rest_ticks += 1
            rest_limit = self._settings.blast_rest_seconds / self._settings.publish_interval
            if self._rest_ticks >= rest_limit:
                self._fire_blast(s)
        else:  # clearing: a small methane seep keeps the flammable channel alive
            s["methane"] = max(0.3, s["methane"] - 0.02)

    def _fire_blast(self, s: dict[str, float]) -> None:
        """Inject post-blast gases into the heading and start clearing."""
        s["co"] = self._settings.blast_co_peak + random.uniform(-15.0, 15.0)
        s["no2"] = self._settings.blast_no2_peak + random.uniform(-1.0, 1.0)
        s["methane"] = max(s["methane"], self._settings.methane_warning + 0.2)
        s["o2"] = 19.6  # fumes displace some oxygen
        self._phase = "clearing"
        self._rest_ticks = 0
        logger.info("Blast fired on %s: CO=%.0f ppm, NO2=%.1f ppm", self._blast_level, s["co"], s["no2"])

    def _step_background(self, s: dict[str, float]) -> None:
        """Keep non-blast levels gently safe on fresh air."""
        s["methane"] += (0.5 - s["methane"]) * 0.15 + random.uniform(-0.03, 0.03)
        s["methane"] = max(0.0, s["methane"])
        s["co"] = self._drift(s["co"], 1.2, 0.0, 15.0)
        s["no2"] = self._drift(s["no2"], 0.05, 0.0, 0.4)
        s["o2"] = self._drift(s["o2"], 0.03, 20.6, self._O2_FRESH)

    def _hazard_present(self, s: dict[str, float]) -> bool:
        """True if any channel is into its warning band — triggers VoD ramp."""
        st = self._settings
        return (
            s["methane"] >= st.methane_warning
            or s["co"] >= st.co_warning
            or s["no2"] >= st.no2_warning
            or s["co2"] >= st.co2_warning
            or s["o2"] <= st.o2_warning
        )

    def _apply_ventilation(self, s: dict[str, float]) -> None:
        """Ramp the fan on any hazard, then remove gas proportional to airflow."""
        if self._hazard_present(s):
            s["fan"] = min(100.0, s["fan"] + self.FAN_RAMP)
        else:
            s["fan"] = max(self.FAN_IDLE, s["fan"] - self.FAN_EASE)

        fan_frac = s["fan"] / 100.0

        # Methane: linear sweep-out with airflow.
        s["methane"] = max(0.0, s["methane"] - fan_frac * self._settings.mitigation_rate)

        # Post-blast gases decay proportionally with airflow.
        clear = fan_frac * self._settings.blast_clear_rate
        s["co"] = max(2.0, s["co"] - s["co"] * clear)
        s["no2"] = max(0.0, s["no2"] - s["no2"] * clear)
        s["co2"] = max(self._CO2_FRESH, s["co2"] - (s["co2"] - self._CO2_FRESH) * clear)

        # Oxygen recovers toward fresh air.
        s["o2"] = min(self._O2_FRESH, s["o2"] + (self._O2_FRESH - s["o2"]) * clear)

        s["airflow"] = self._AIRFLOW_BASE + fan_frac * self._AIRFLOW_RANGE

    def _check_reentry(self, s: dict[str, float]) -> None:
        """Once the blast level's CO clears the limit, grant re-entry and rest again."""
        if self._phase == "clearing" and s["co"] <= self._reentry_co:
            self._phase = "working"
            self._rest_ticks = 0
            logger.info("%s cleared for re-entry (CO=%.0f ppm)", self._blast_level, s["co"])

    def step_all(self) -> dict[str, GasReading]:
        """Advance every level one tick; returns {level_id: reading}."""
        return {level: self.step_level(level) for level in self._settings.level_list}


def _build_client(settings: Settings):
    """Create a paho client, tolerating both paho-mqtt 1.x and 2.x APIs."""
    import paho.mqtt.client as mqtt

    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mine-simulator")
    except (AttributeError, TypeError):
        return mqtt.Client(client_id="mine-simulator")


def run_publisher(settings: Settings | None = None) -> None:
    """Connect to the broker and publish readings for every level forever."""
    settings = settings or get_settings()
    simulator = LevelSimulator(settings)
    client = _build_client(settings)

    logger.info(
        "Simulator connecting to MQTT broker at %s:%s",
        settings.mqtt_host,
        settings.mqtt_port,
    )
    client.connect(settings.mqtt_host, settings.mqtt_port, settings.mqtt_keepalive)
    client.loop_start()

    try:
        while True:
            for level, reading in simulator.step_all().items():
                topic = settings.topic_for(level)
                payload = json.dumps(reading.model_dump())
                client.publish(topic, payload)
                logger.debug("Published to %s: %s", topic, payload)
            time.sleep(settings.publish_interval)
    except KeyboardInterrupt:
        logger.info("Simulator stopped by user")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    run_publisher()
