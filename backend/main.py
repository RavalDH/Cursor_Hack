"""FastAPI edge backend for the underground mine gas-safety early-warning system.

================================  HOW TO RUN  ================================
Everything is LOCAL and OFFLINE. No internet is used or required anywhere.

1) Start a local MQTT broker (Mosquitto) — this stands in for the mine mesh:
     # macOS:    brew install mosquitto && mosquitto
     # Ubuntu:   sudo apt install mosquitto && mosquitto
     # Windows:  install Mosquitto, then run `mosquitto` (or run it as a service)
   The broker listens on localhost:1883.

2) (Optional) Copy env defaults:
     cp .env.example .env        # Windows: copy .env.example .env

3) Install dependencies (ideally in a virtualenv):
     pip install -r requirements.txt

4) Start the zone simulator in its own terminal (publishes readings every 1s):
     python simulator.py

5) Start the API:
     uvicorn main:app --reload
   Then open http://localhost:8000/zones , /alert , /health , and POST /ask.

-----------------------------  DEMO SAFETY NET  -----------------------------
No broker handy? Set USE_MQTT=false in .env (or the environment) and skip steps
1 and 4 entirely. The backend then generates identical zone readings on an
internal async timer, so /zones behaves exactly the same. The mesh is the
*story*; MQTT is just the cleanest way to show it.
=============================================================================
"""

import asyncio
import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from answers import answer_question, procedure_for
from config import Settings, get_settings
from models import (
    AlertResponse,
    AskRequest,
    AskResponse,
    HealthResponse,
    ZonesResponse,
    ZoneStatus,
)
from mqtt_client import MqttSubscriber
from simulator import ZoneSimulator
from state import StateStore
from trend import evaluate_zone, severity_rank

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mine.backend")


class AppContext:
    """Holds the long-lived objects so handlers don't reach for globals blindly.

    One instance is created at startup and stashed on app.state. Keeping the
    store, settings, optional MQTT subscriber, and start time together makes the
    two run modes (MQTT vs internal timer) easy to reason about.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = StateStore(settings.zone_list, settings.history_size)
        self.started_at = time.time()
        self.subscriber: MqttSubscriber | None = None
        self.simulator: ZoneSimulator | None = None
        self.timer_task: asyncio.Task | None = None

    @property
    def mqtt_connected(self) -> bool:
        return bool(self.subscriber and self.subscriber.connected)


async def _internal_timer_loop(ctx: AppContext) -> None:
    """Drive zones from the in-process simulator when USE_MQTT is false.

    This uses the exact same ZoneSimulator the MQTT publisher uses, so /zones is
    indistinguishable between the two modes. This is the live-demo safety net.
    """
    interval = ctx.settings.publish_interval
    logger.info("Internal timer started (USE_MQTT=false), interval=%.1fs", interval)
    try:
        while True:
            for zone, reading in ctx.simulator.step_all().items():
                ctx.store.update(zone, reading)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Internal timer stopped")
        raise


app = FastAPI(title="Mine Gas Safety Edge Backend", version="1.0.0")

# Wide-open CORS: the frontend is served from a separate origin (and during the
# demo we don't know which port), so we allow all. This is an offline LAN tool,
# not a public API, which makes the trade-off acceptable here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Must stay False alongside allow_origins=["*"]: the CORS spec forbids the
    # wildcard origin together with credentials. The frontend doesn't send
    # cookies/auth, so this loses us nothing and keeps the headers valid.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Build state and start whichever data source the config selected."""
    settings = get_settings()
    ctx = AppContext(settings)
    app.state.ctx = ctx

    logger.info(
        "Starting backend. Zones=%s, climbing=%s, USE_MQTT=%s",
        settings.zone_list,
        settings.climbing_zone,
        settings.use_mqtt,
    )

    if settings.use_mqtt:
        # Real path: subscribe to the broker. If it's down, start() logs a
        # warning and returns; the app still serves existing state.
        ctx.subscriber = MqttSubscriber(settings, ctx.store)
        ctx.subscriber.start()
    else:
        # Fallback path: generate readings ourselves on an async timer.
        ctx.simulator = ZoneSimulator(settings)
        ctx.timer_task = asyncio.create_task(_internal_timer_loop(ctx))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Tear down the MQTT client or the timer task cleanly."""
    ctx: AppContext = app.state.ctx
    if ctx.subscriber:
        ctx.subscriber.stop()
    if ctx.timer_task:
        ctx.timer_task.cancel()
        try:
            await ctx.timer_task
        except asyncio.CancelledError:
            pass
    logger.info("Backend shut down")


def _current_zone_statuses(ctx: AppContext) -> list[ZoneStatus]:
    """Compute the status/trend for every zone that has data.

    Side effect: records each zone's status in the store so red->green
    recoveries are detected. Both /zones and /alert call this, and the frontend
    polls /zones every couple of seconds, so transitions are caught reliably.
    """
    statuses: list[ZoneStatus] = []
    for zone_id in ctx.store.all_zone_ids():
        history = ctx.store.get_history(zone_id)
        zone_status = evaluate_zone(zone_id, history, ctx.settings)
        if zone_status is not None:
            statuses.append(zone_status)
            ctx.store.note_status(zone_id, zone_status.status)
    return statuses


def _zone_label(zone_id: str) -> str:
    """Turn 'zone3' into a spoken-friendly 'Zone 3' for the all-clear message."""
    if zone_id.lower().startswith("zone") and zone_id[4:].isdigit():
        return f"Zone {zone_id[4:]}"
    return zone_id


@app.get("/zones", response_model=ZonesResponse)
async def get_zones() -> ZonesResponse:
    """Return the latest computed status for every zone.

    Works from whatever is already in state, so it keeps responding even if the
    broker is unreachable — that's the graceful-degradation requirement.
    """
    try:
        ctx: AppContext = app.state.ctx
        return ZonesResponse(zones=_current_zone_statuses(ctx))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error building /zones response")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to read zones", "detail": str(exc)},
        )


@app.get("/alert", response_model=AlertResponse)
async def get_alert() -> AlertResponse:
    """Return the single highest-severity zone needing action, if any.

    Fires when a zone is red, or yellow-and-rising (the early-warning case). The
    response carries the exact procedure and a Reg 854 citation so the frontend
    can speak/show it directly.
    """
    try:
        ctx: AppContext = app.state.ctx
        statuses = _current_zone_statuses(ctx)
        if not statuses:
            return AlertResponse(alert=False)

        worst = max(statuses, key=severity_rank)

        # Alert only on genuine concern: red, or a yellow that's actively rising.
        fires = worst.status == "red" or (
            worst.status == "yellow" and worst.trend == "rising"
        )
        if not fires:
            # Nothing alarming right now. But if a zone just came back from red
            # to green, give an explicit "all clear" so the demo's voice line
            # has something reassuring to say instead of falling silent.
            recovered_zone = ctx.store.recent_recovery()
            if recovered_zone is not None:
                label = _zone_label(recovered_zone)
                return AlertResponse(
                    alert=False,
                    recovered=True,
                    recovered_zone=recovered_zone,
                    message=(
                        f"{label} stabilized. Ventilation restored airflow. "
                        "Everything is under control now."
                    ),
                )
            return AlertResponse(alert=False)

        # Methane is the driver of the demo trend; report it as the metric.
        answer, citations = procedure_for("methane", worst.status, ctx.settings)
        return AlertResponse(
            alert=True,
            zone=worst.id,
            metric="methane",
            value=worst.methane,
            threshold=ctx.settings.methane_danger,
            trend=worst.trend,
            answer=answer,
            citations=citations,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error building /alert response")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to evaluate alert", "detail": str(exc)},
        )


@app.post("/ask", response_model=AskResponse)
async def post_ask(request: AskRequest) -> AskResponse:
    """Answer a free-text safety question from local docs (template, no LLM).

    AskRequest validation means an empty/missing question already returns 422
    before we get here, satisfying the malformed-input requirement.
    """
    try:
        answer, citations = answer_question(request.question)
        return AskResponse(answer=answer, citations=citations)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error answering /ask")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to answer question", "detail": str(exc)},
        )


@app.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Quick operational snapshot for the demo and for sanity checks."""
    try:
        ctx: AppContext = app.state.ctx
        return HealthResponse(
            status="ok",
            mqtt_connected=ctx.mqtt_connected,
            zones_tracked=ctx.store.zones_with_data(),
            uptime_seconds=round(time.time() - ctx.started_at, 1),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error building /health response")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to read health", "detail": str(exc)},
        )
