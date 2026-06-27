"""Simulated per-level sensor readings, modelled on a real drill-and-blast cycle.

Two jobs in one file:
  1. The standalone publisher (`python simulator.py`) that pushes readings to the
     local MQTT broker, standing in for the real sensor stations on each level.
  2. The reusable generation logic (`LevelSimulator`), imported by main.py so the
     USE_MQTT=false internal-timer fallback produces *identical* readings without
     a broker. Sharing the logic is what makes the two modes indistinguishable at
     the /levels output — the demo's safety net.

What it models (and why it reads like a mine):
  * Every level reports a full multi-gas picture: CH4, CO, CO2, NO2, O2, plus
    airflow and temperature — what a real fixed environmental station heads up.
  * The active production level runs the **drill-and-blast cycle**: a blast fills
    the heading with carbon monoxide and nitrogen dioxide (and a little methane),
    oxygen dips, and then **ventilation-on-demand** ramps the fan to clear the
    gases. CO clears slowest, so CO is what governs **re-entry** — exactly as in
    practice. Once the air is below the re-entry limit, the cycle rests and then
    blasts again, so the full "blast -> clearing -> re-entry -> safe" arc plays
    on a loop for the demo.
  * Other levels sit safely on fresh air with gentle sensor noise.

The numbers are tuned to be watchable in seconds, not physically rigorous.
"""

import json
import logging
import random
import time

from config import Settings, get_settings
from models import GasReading

logger = logging.getLogger(__name__)


class LevelSimulator:
    """Generates a stream of realistic multi-gas readings for all levels.

    Ventilation is a closed loop: as any hazardous gas builds, the fan ramps to
    push more fresh air through the level, which dilutes and sweeps the gas out;
    as the air clears, the fan eases back to an idle baseline to save energy
    (this is ventilation-on-demand). The only mitigation lever is airflow — we
    never enrich oxygen, because more oxygen underground raises explosion risk.
    """

    # Fan dynamics (percent of full speed). Idle is a non-zero baseline because a
    # level always gets *some* fresh air; ramp is faster than ease so the system
    # reacts hard to danger but powers down gently.
    FAN_IDLE = 20.0
    FAN_RAMP = 18.0  # +%/tick while a hazard is present
    FAN_EASE = 10.0  # -%/tick once the level is clear
    # Airflow (m^3/s) is a direct function of fan speed.
    _AIRFLOW_BASE = 3.0
    _AIRFLOW_RANGE = 6.0

    # Fresh-air baselines for the non-flammable channels.
    _O2_FRESH = 20.9
    _CO2_FRESH = 0.04

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._blast_level = settings.active_blast_level

        # Drill-and-blast cycle state for the active level.
        #   "working"  -> crew on the level, air clear, counting down to next blast
        #   "clearing" -> blast has happened, ventilation clearing gases
        self._phase = "working"
        self._rest_ticks = 0
        # Re-entry limit: air must fall below the CO warning before the crew may
        # return. CO is the governing gas because it clears slowest.
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

        # Temperature and CO2 just drift gently on every level.
        s["temp"] = self._drift(s["temp"], 0.3, 18.0, 42.0)
        s["co2"] = self._drift(s["co2"], 0.01, self._CO2_FRESH, 2.0)

        if level == self._blast_level:
            self._step_blast_cycle(s)
            self._apply_ventilation(s)
            # The drill-and-blast phase machine is owned by this level alone, so
            # the re-entry check must run here and only here — never in the shared
            # ventilation step, where another level's low CO could reset it.
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
        """Drive the active level through rest -> blast -> clearing -> rest.

        While "working" we count down a rest period, then fire a blast that loads
        the heading with CO, NO2, a little methane and a dip in O2. We then switch
        to "clearing"; the ventilation step pulls those gases back down. Once CO
        is back under the re-entry limit we grant re-entry and rest again.
        """
        if self._phase == "working":
            # Calm, working air with a touch of noise.
            s["methane"] = self._drift(s["methane"], 0.03, 0.2, 0.7)
            s["co"] = self._drift(s["co"], 1.5, 2.0, 15.0)
            s["no2"] = self._drift(s["no2"], 0.1, 0.0, 0.5)
            s["o2"] = self._drift(s["o2"], 0.05, 20.6, self._O2_FRESH)

            self._rest_ticks += 1
            rest_limit = self._settings.blast_rest_seconds / self._settings.publish_interval
            if self._rest_ticks >= rest_limit:
                self._fire_blast(s)
        else:  # clearing — gases set by the blast, ventilation draws them down
            # A small ongoing methane seep keeps the flammable channel alive while
            # the toxic gases dominate the clearing story.
            s["methane"] = max(0.3, s["methane"] - 0.02)

    def _fire_blast(self, s: dict[str, float]) -> None:
        """Inject post-blast gases into the heading and start clearing."""
        s["co"] = self._settings.blast_co_peak + random.uniform(-15.0, 15.0)
        s["no2"] = self._settings.blast_no2_peak + random.uniform(-1.0, 1.0)
        s["methane"] = max(s["methane"], self._settings.methane_warning + 0.2)
        s["o2"] = 19.6  # blast fumes displace some oxygen
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
        """Ventilation-on-demand: ramp the fan on any hazard, then dilute via air.

        Decide the fan response from the current air, then apply this tick's
        airflow-driven removal. Removal scales with fan speed — full fan clears
        fastest — and is strictly airflow-based (never oxygen enrichment).
        """
        if self._hazard_present(s):
            s["fan"] = min(100.0, s["fan"] + self.FAN_RAMP)
        else:
            s["fan"] = max(self.FAN_IDLE, s["fan"] - self.FAN_EASE)

        fan_frac = s["fan"] / 100.0

        # Methane: linear sweep-out proportional to airflow.
        s["methane"] = max(0.0, s["methane"] - fan_frac * self._settings.mitigation_rate)

        # Post-blast gases decay proportionally (exponential-style) with airflow.
        clear = fan_frac * self._settings.blast_clear_rate
        s["co"] = max(2.0, s["co"] - s["co"] * clear)
        s["no2"] = max(0.0, s["no2"] - s["no2"] * clear)
        s["co2"] = max(self._CO2_FRESH, s["co2"] - (s["co2"] - self._CO2_FRESH) * clear)

        # Oxygen recovers toward fresh air as ventilation restores it.
        s["o2"] = min(self._O2_FRESH, s["o2"] + (self._O2_FRESH - s["o2"]) * clear)

        # Airflow tracks fan speed directly: more fan, more fresh air.
        s["airflow"] = self._AIRFLOW_BASE + fan_frac * self._AIRFLOW_RANGE

    def _check_reentry(self, s: dict[str, float]) -> None:
        """Grant re-entry once the BLAST level's CO clears the limit.

        Called only while processing the active blast level, because it mutates
        the shared drill-and-blast phase state. Once CO is back under the re-entry
        limit, the post-blast gases are considered cleared: re-entry is granted
        and the cycle returns to its working/rest phase.
        """
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
