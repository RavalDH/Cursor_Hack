"""Simulated zone gas readings.

Two jobs in one file:
  1. The standalone publisher (run as `python simulator.py`) that pushes
     readings to the local MQTT broker, standing in for real sensor nodes.
  2. The reusable generation logic (`ZoneSimulator`), imported by main.py so the
     USE_MQTT=false internal-timer fallback produces *identical* readings without
     a broker. Sharing the logic is what makes the two modes indistinguishable
     at the /zones output, which is the whole point of the safety net.

The numbers are not physically rigorous — they're chosen to look realistic and,
crucially, to give the demo a clear story: one zone steadily climbs methane
toward danger so the audience sees green -> yellow -> red unfold.
"""

import json
import logging
import random
import time

from config import Settings, get_settings
from models import GasReading

logger = logging.getLogger(__name__)


class ZoneSimulator:
    """Generates a stream of realistic-looking readings for all zones.

    The model now includes a closed ventilation-control loop, because the point
    of the system is not just to alarm but to *act*. Real mine ventilation works
    exactly this way: as gas builds, fans ramp to push more fresh air through the
    zone, which dilutes and sweeps the gas out; as the gas clears, the fans ease
    back to an idle baseline to save power. Critically, the only mitigation lever
    is airflow — we never enrich oxygen, because more oxygen underground raises
    explosion risk rather than lowering it.

    The designated climbing zone models an intermittent gas inrush (a strata
    release/blast): gas pours in until the zone hits danger, the source is then
    brought under control, and the ramped fan clears the zone back to green. The
    cycle then repeats so the full green -> red -> ventilating -> green arc can be
    shown live at any moment.
    """

    # Fan dynamics (percent of full speed). Idle is a non-zero baseline because
    # a zone is always getting *some* fresh air; ramp is faster than ease so the
    # system reacts aggressively to danger but powers down gently.
    FAN_IDLE = 20.0
    FAN_RAMP = 15.0  # +%/tick while the zone is elevated
    FAN_EASE = 10.0  # -%/tick once the zone is back below the warning level
    # Airflow (m^3/s) is a direct function of fan speed: idle gives a baseline
    # sweep, full speed roughly doubles it.
    _AIRFLOW_BASE = 3.0
    _AIRFLOW_RANGE = 5.0

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._climbing_zone = settings.climbing_zone

        # Gas-source phase for the demo zone: "leaking" = inrush adding gas,
        # "venting" = source controlled, fan clearing the residual gas.
        self._source_phase = "leaking"
        # When venting drops methane back to this baseline, a fresh inrush starts.
        self._reset_level = 0.4
        # The inrush overshoots a little past the danger line before the source
        # is "controlled". Without this, mitigation pulls methane back under 1.5
        # within a tick or two and the red state is too brief to see or alarm on;
        # the overshoot keeps the zone clearly red for several seconds.
        self._peak_level = settings.methane_danger + 0.3

        # Per-zone current values, including the live fan speed. Starting methane
        # is comfortably green and the fan starts idling.
        self._state: dict[str, dict[str, float]] = {}
        for zone in settings.zone_list:
            self._state[zone] = {
                "methane": random.uniform(0.3, 0.6),
                "co": random.uniform(5.0, 15.0),
                "temp": random.uniform(22.0, 28.0),
                "airflow": self._AIRFLOW_BASE + 0.2 * self._AIRFLOW_RANGE,
                "fan": self.FAN_IDLE,
            }

    def _drift(self, value: float, step: float, low: float, high: float) -> float:
        """Random-walk a value by +/- step and clamp it to a plausible range."""
        value += random.uniform(-step, step)
        return max(low, min(high, value))

    def step_zone(self, zone: str) -> GasReading:
        """Advance one zone by a single tick and return its new reading."""
        s = self._state[zone]

        # CO and temperature just drift; they aren't part of the methane control
        # loop but keep the readings feeling alive.
        s["co"] = self._drift(s["co"], 1.5, 0.0, 40.0)
        s["temp"] = self._drift(s["temp"], 0.3, 18.0, 38.0)

        # 1) Move methane: the climbing zone has a gas source; others just hover.
        if zone == self._climbing_zone:
            self._step_gas_source(s)
        else:
            self._step_background_methane(s)

        # 2) Run the fan control loop + airflow mitigation for every zone.
        self._apply_fan_loop(s)

        return GasReading(
            methane=round(s["methane"], 3),
            co=round(s["co"], 1),
            temp=round(s["temp"], 1),
            airflow=round(s["airflow"], 2),
            fan_speed=round(s["fan"], 1),
        )

    def _step_gas_source(self, s: dict[str, float]) -> None:
        """Add/withhold methane for the demo zone's intermittent inrush.

        While "leaking", gas pours in at the configured climb rate until the
        zone reaches danger; at that point we consider the source controlled
        (e.g. blasting stopped, fissure isolated) and switch to "venting" so the
        already-ramped fan can clear the residual gas. Once cleared back to the
        reset baseline, a new inrush begins and the arc repeats.
        """
        noise = random.uniform(-0.005, 0.005)
        if self._source_phase == "leaking":
            s["methane"] = s["methane"] + self._settings.methane_climb_rate + noise
            if s["methane"] >= self._peak_level:
                self._source_phase = "venting"
        else:  # venting — no new gas; mitigation in _apply_fan_loop draws it down
            if s["methane"] <= self._reset_level:
                self._source_phase = "leaking"

    def _step_background_methane(self, s: dict[str, float]) -> None:
        """Keep non-climbing zones gently mean-reverting around a safe level.

        These zones have no gas source, so they should sit calmly green. We
        mean-revert toward a low baseline with a little noise; combined with the
        idle-fan mitigation below this settles them around ~0.5%.
        """
        target = 0.55
        s["methane"] += (target - s["methane"]) * 0.15 + random.uniform(-0.03, 0.03)

    def _apply_fan_loop(self, s: dict[str, float]) -> None:
        """Auto-mitigation: ramp the fan on elevated gas, then dilute via airflow.

        Order matches the real control logic: decide the fan response from the
        current gas level, then apply this tick's airflow-driven removal. We ramp
        whenever methane is at or above the warning level (covers yellow and red)
        and otherwise ease back toward idle. Mitigation removes methane in
        proportion to fan speed — full fan clears fastest — and is strictly
        airflow-based (never oxygen).
        """
        if s["methane"] >= self._settings.methane_warning:
            s["fan"] = min(100.0, s["fan"] + self.FAN_RAMP)
        else:
            s["fan"] = max(self.FAN_IDLE, s["fan"] - self.FAN_EASE)

        removal = (s["fan"] / 100.0) * self._settings.mitigation_rate
        s["methane"] = max(0.0, s["methane"] - removal)

        # Airflow tracks fan speed directly: more fan, more fresh air.
        s["airflow"] = self._AIRFLOW_BASE + (s["fan"] / 100.0) * self._AIRFLOW_RANGE

    def step_all(self) -> dict[str, GasReading]:
        """Advance every zone one tick; returns {zone_id: reading}."""
        return {zone: self.step_zone(zone) for zone in self._settings.zone_list}


def _build_client(settings: Settings):
    """Create a paho client, tolerating both paho-mqtt 1.x and 2.x APIs."""
    import paho.mqtt.client as mqtt

    # paho-mqtt 2.x requires an explicit callback API version; 1.x has no such
    # argument. Try the 2.x signature first and fall back so either works.
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mine-simulator")
    except (AttributeError, TypeError):
        return mqtt.Client(client_id="mine-simulator")


def run_publisher(settings: Settings | None = None) -> None:
    """Connect to the broker and publish readings for every zone forever."""
    settings = settings or get_settings()
    simulator = ZoneSimulator(settings)
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
            for zone, reading in simulator.step_all().items():
                topic = settings.topic_for(zone)
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
