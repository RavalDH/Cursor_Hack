"""MQTT subscriber: bridges the broker (the "mesh") into the state store.

Runs paho's loop on a background thread. Two hard rules: a bad payload is logged
and skipped (never crashes the subscriber), and an unreachable broker never
stops the app — paho reconnects and /levels keeps serving existing state.
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
        """Connect and start the loop. A failed connect is logged, not fatal — paho keeps retrying."""
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
        # One wildcard sub covers every level, including ones that join later.
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
            # Pydantic validates here; a bad payload raises and is caught below.
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
