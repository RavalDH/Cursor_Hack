"""MQTT subscriber: bridges the local broker (the 'mesh') into our state store.

This runs paho's network loop on a background thread. It subscribes to every
level's gas topic, validates each payload, writes good readings into the shared
StateStore, and mirrors them into the offline historian. Two hard rules live
here:

  * A malformed payload must NEVER crash the subscriber — log a warning, skip it,
    keep listening. Underground, one flaky sensor cannot take down monitoring for
    the whole mine.
  * The app must keep running even if the broker is unreachable. We connect with
    auto-reconnect and let paho handle a broker that comes up later, so /levels
    still serves whatever state we already have.
"""

import json
import logging

from config import Settings
from historian import Historian
from models import GasReading
from state import StateStore

logger = logging.getLogger(__name__)


class MqttSubscriber:
    """Owns the paho client and routes incoming readings into state + historian."""

    def __init__(self, settings: Settings, store: StateStore, historian: Historian | None = None) -> None:
        self._settings = settings
        self._store = store
        self._historian = historian
        self.connected = False
        self._client = self._build_client()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _build_client(self):
        """Create a paho client across paho-mqtt 1.x / 2.x API differences."""
        import paho.mqtt.client as mqtt

        try:
            return mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2, client_id="mine-backend"
            )
        except (AttributeError, TypeError):
            return mqtt.Client(client_id="mine-backend")

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Attempt to connect and start the background loop.

        Failure to reach the broker is logged and swallowed: the rest of the app
        must come up regardless (graceful degradation). paho keeps retrying the
        connection on its own thread once loop_start is running.
        """
        host, port = self._settings.mqtt_host, self._settings.mqtt_port
        try:
            logger.info("Connecting to MQTT broker at %s:%s", host, port)
            self._client.connect_async(host, port, self._settings.mqtt_keepalive)
            self._client.loop_start()
        except Exception as exc:  # noqa: BLE001 - never let MQTT sink startup
            logger.warning(
                "Could not start MQTT client (%s). Continuing without live MQTT; "
                "/levels will serve existing state.",
                exc,
            )

    def stop(self) -> None:
        """Cleanly stop the loop and disconnect (called on app shutdown)."""
        try:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT client stopped")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error during MQTT shutdown: %s", exc)

    # --- callbacks ---------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        """Subscribe to all level topics once connected."""
        self.connected = True
        topic = f"{self._settings.mqtt_base_topic}/+/gas"
        # A single wildcard subscription covers every level, including levels that
        # join the mesh later — we don't have to know the level list up front.
        client.subscribe(topic)
        logger.info("MQTT connected; subscribed to %s", topic)

    def _on_disconnect(self, client, userdata, *args) -> None:
        """Mark disconnected; paho's loop will keep trying to reconnect."""
        self.connected = False
        logger.warning("MQTT disconnected; will attempt to reconnect")

    def _on_message(self, client, userdata, msg) -> None:
        """Validate and store one incoming reading. Must never raise."""
        try:
            level_id = self._level_from_topic(msg.topic)
            if level_id is None:
                logger.warning("Ignoring message on unexpected topic: %s", msg.topic)
                return

            payload = json.loads(msg.payload.decode("utf-8"))
            # Pydantic validates types here; a bad payload raises and is caught.
            reading = GasReading(**payload)
            self._store.update(level_id, reading)
            if self._historian is not None:
                self._historian.log_reading(level_id, reading)
            logger.debug("Stored reading for %s: %s", level_id, reading)
        except json.JSONDecodeError:
            logger.warning("Malformed JSON on %s; skipping", msg.topic)
        except Exception as exc:  # noqa: BLE001 - one bad msg must not kill us
            logger.warning("Invalid reading on %s (%s); skipping", msg.topic, exc)

    def _level_from_topic(self, topic: str) -> str | None:
        """Extract the level id from 'mine/<level>/gas'."""
        parts = topic.split("/")
        if len(parts) == 3 and parts[0] == self._settings.mqtt_base_topic and parts[2] == "gas":
            return parts[1]
        return None
