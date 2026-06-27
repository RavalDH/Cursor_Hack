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

    Each zone gets a small random walk around a baseline (sensors are noisy and
    conditions drift). The designated climbing zone adds a slow, steady methane
    increase on top so it eventually trips yellow and then red.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._climbing_zone = settings.climbing_zone
        # Per-zone current values. Starting methane is comfortably green.
        self._state: dict[str, dict[str, float]] = {}
        for zone in settings.zone_list:
            self._state[zone] = {
                "methane": random.uniform(0.3, 0.6),
                "co": random.uniform(5.0, 15.0),
                "temp": random.uniform(22.0, 28.0),
                "airflow": random.uniform(4.0, 6.0),
            }

    def _drift(self, value: float, step: float, low: float, high: float) -> float:
        """Random-walk a value by +/- step and clamp it to a plausible range."""
        value += random.uniform(-step, step)
        return max(low, min(high, value))

    def step_zone(self, zone: str) -> GasReading:
        """Advance one zone by a single tick and return its new reading."""
        s = self._state[zone]

        # Normal background drift for every metric.
        s["co"] = self._drift(s["co"], 1.5, 0.0, 40.0)
        s["temp"] = self._drift(s["temp"], 0.3, 18.0, 38.0)
        s["airflow"] = self._drift(s["airflow"], 0.2, 1.0, 8.0)

        if zone == self._climbing_zone:
            # Steady upward creep plus a little noise. ~+0.02%/tick means the
            # zone crosses the 1.5% danger line within a minute or two — long
            # enough to narrate, short enough for a live demo.
            s["methane"] = self._drift(s["methane"], 0.01, 0.0, 5.0) + 0.02
            # As methane builds we also let airflow sag, mimicking the real link
            # between failing ventilation and accumulating gas.
            s["airflow"] = max(1.0, s["airflow"] - 0.05)
        else:
            s["methane"] = self._drift(s["methane"], 0.03, 0.2, 0.95)

        return GasReading(
            methane=round(s["methane"], 3),
            co=round(s["co"], 1),
            temp=round(s["temp"], 1),
            airflow=round(s["airflow"], 2),
        )

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
