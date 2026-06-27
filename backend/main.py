"""FastAPI edge backend for the underground mine gas-safety early-warning system.

================================  HOW TO RUN  ================================
Everything is LOCAL and OFFLINE. No internet is used or required anywhere.

1) Start a local MQTT broker (Mosquitto) — this stands in for the mine mesh:
     # macOS:    brew install mosquitto && mosquitto
     # Ubuntu:   sudo apt install mosquitto && mosquitto
     # Windows:  install Mosquitto, then run `mosquitto`
   The broker listens on localhost:1883.

2) (Optional) Copy env defaults:
     cp .env.example .env        # Windows: copy .env.example .env

3) Install dependencies (ideally in a virtualenv):
     pip install -r requirements.txt

4) Start the level simulator in its own terminal (publishes readings every 1s):
     python simulator.py

5) Start the API:
     uvicorn main:app --reload
   Then open http://localhost:8000/levels , /alert , /health , and POST /ask.

-----------------------------  DEMO SAFETY NET  -----------------------------
No broker handy? Set USE_MQTT=false in .env (or the environment) and skip steps
1 and 4 entirely. The backend then generates identical level readings on an
internal async timer, so /levels behaves exactly the same. The mesh is the
*story*; MQTT is just the cleanest way to show it.

----------------------------  OFFLINE HISTORIAN  ----------------------------
Every reading and every notable event is also appended to dated JSONL files
under ./logs (telemetry/ and events/), and the app's own log rotates daily in
logs/app.log. That on-disk record survives restarts and is fully offline.
=============================================================================
"""

import asyncio
import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import mine
from answers import answer_question, procedure_for
from config import Settings, get_settings
from historian import Historian
from logging_setup import configure_logging
from models import (
    AlertResponse,
    AskRequest,
    AskResponse,
    HealthResponse,
    LevelStatus,
    LevelsResponse,
    ZonesResponse,
)
from mqtt_client import MqttSubscriber
from simulator import LevelSimulator
from state import StateStore
from trend import evaluate_level, severity_rank

logger = logging.getLogger("mine.backend")


class AppContext:
    """Holds the long-lived objects so handlers don't reach for globals blindly.

    One instance is created at startup and stashed on app.state. Keeping the
    store, settings, historian, optional MQTT subscriber and start time together
    makes the two run modes (MQTT vs internal timer) easy to reason about.
    """

    def __init__(self, settings: Settings, historian: Historian) -> None:
        self.settings = settings
        self.historian = historian
        self.store = StateStore(settings.level_list, settings.history_size)
        self.started_at = time.time()
        self.subscriber: MqttSubscriber | None = None
        self.simulator: LevelSimulator | None = None
        self.timer_task: asyncio.Task | None = None

    @property
    def mqtt_connected(self) -> bool:
        return bool(self.subscriber and self.subscriber.connected)


async def _internal_timer_loop(ctx: AppContext) -> None:
    """Drive levels from the in-process simulator when USE_MQTT is false.

    Uses the exact same LevelSimulator the MQTT publisher uses, so /levels is
    indistinguishable between the two modes. Also mirrors each reading into the
    historian, just like the MQTT path does.
    """
    interval = ctx.settings.publish_interval
    logger.info("Internal timer started (USE_MQTT=false), interval=%.1fs", interval)
    try:
        while True:
            for level, reading in ctx.simulator.step_all().items():
                ctx.store.update(level, reading)
                ctx.historian.log_reading(level, reading)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Internal timer stopped")
        raise


app = FastAPI(title="Mine Gas Safety Edge Backend", version="2.0.0")

# Wide-open CORS: the frontend is served from a separate origin (and during the
# demo we don't know which port), so we allow all. This is an offline LAN tool,
# not a public API, which makes the trade-off acceptable here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Build state, configure offline logging, and start the data source."""
    settings = get_settings()

    # Offline logging first, so everything after this is captured on disk.
    log_file = configure_logging(
        settings.log_path, settings.log_level, settings.log_retention_days
    )
    historian = Historian(settings.log_path, settings.historian_enabled)

    ctx = AppContext(settings, historian)
    app.state.ctx = ctx

    logger.info(
        "Starting %s backend. Levels=%s, blast level=%s, USE_MQTT=%s, log=%s",
        mine.MINE_NAME,
        settings.level_list,
        settings.active_blast_level,
        settings.use_mqtt,
        log_file,
    )
    historian.log_event(
        "startup",
        mine=mine.MINE_NAME,
        levels=settings.level_list,
        use_mqtt=settings.use_mqtt,
    )

    if settings.use_mqtt:
        # Real path: subscribe to the broker. If it's down, start() logs a
        # warning and returns; the app still serves existing state.
        ctx.subscriber = MqttSubscriber(settings, ctx.store, historian)
        ctx.subscriber.start()
    else:
        # Fallback path: generate readings ourselves on an async timer.
        ctx.simulator = LevelSimulator(settings)
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
    ctx.historian.log_event("shutdown", uptime_seconds=round(time.time() - ctx.started_at, 1))
    logger.info("Backend shut down")


def _current_level_statuses(ctx: AppContext) -> list[LevelStatus]:
    """Compute the status/trend for every level that has data.

    Side effect: records each level's status in the store and writes an event to
    the historian whenever a level's status changes (e.g. green->yellow->red and
    back). Both /levels and /alert call this, and the frontend polls /levels
    every couple of seconds, so transitions are caught reliably.
    """
    statuses: list[LevelStatus] = []
    for level_id in ctx.store.all_level_ids():
        history = ctx.store.get_history(level_id)
        level_status = evaluate_level(level_id, history, ctx.settings)
        if level_status is None:
            continue
        statuses.append(level_status)
        transition = ctx.store.note_status(level_id, level_status.status)
        if transition is not None:
            old, new = transition
            ctx.historian.log_event(
                "status_change",
                level_id=level_id,
                **{
                    "from": old,
                    "to": new,
                    "metric": level_status.metric,
                    "methane": level_status.methane,
                    "co": level_status.co,
                },
            )
    return statuses


@app.get("/levels", response_model=LevelsResponse)
async def get_levels() -> LevelsResponse:
    """Return the latest computed status for every level.

    Works from whatever is already in state, so it keeps responding even if the
    broker is unreachable — the graceful-degradation requirement.
    """
    try:
        ctx: AppContext = app.state.ctx
        return LevelsResponse(mine=mine.MINE_NAME, levels=_current_level_statuses(ctx))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error building /levels response")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to read levels", "detail": str(exc)},
        )


@app.get("/zones", response_model=ZonesResponse)
async def get_zones() -> ZonesResponse:
    """Deprecated alias for /levels, kept so an existing UI polling /zones works.

    Returns the identical level objects under the legacy "zones" key.
    """
    try:
        ctx: AppContext = app.state.ctx
        return ZonesResponse(zones=_current_level_statuses(ctx))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error building /zones response")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to read zones", "detail": str(exc)},
        )


@app.get("/alert", response_model=AlertResponse)
async def get_alert() -> AlertResponse:
    """Return the single highest-severity level needing action, if any.

    Fires when a level is red, or yellow-and-rising (the early-warning case). The
    response carries the exact procedure and a Reg 854 citation so the frontend
    can speak/show it directly.
    """
    try:
        ctx: AppContext = app.state.ctx
        statuses = _current_level_statuses(ctx)
        if not statuses:
            return AlertResponse(alert=False)

        worst = max(statuses, key=severity_rank)

        fires = worst.status == "red" or (
            worst.status == "yellow" and worst.trend == "rising"
        )
        if not fires:
            # Nothing alarming. If a level just recovered red->green, give an
            # explicit "all clear" so the demo's voice has something reassuring
            # to say instead of falling silent.
            recovered_level = ctx.store.recent_recovery()
            if recovered_level is not None:
                info = mine.describe(recovered_level)
                return AlertResponse(
                    alert=False,
                    recovered=True,
                    recovered_zone=recovered_level,
                    message=(
                        f"{info.name} stabilized. Ventilation restored airflow "
                        "and the air has cleared. Re-entry granted."
                    ),
                )
            return AlertResponse(alert=False)

        # Report the gas actually driving the level's status (CO right after a
        # blast, methane for a seep, etc.).
        metric = worst.metric if worst.metric != "none" else "methane"
        answer, citations = procedure_for(metric, worst.status, ctx.settings)
        value, threshold = _metric_value_threshold(worst, metric, ctx.settings)

        ctx.historian.log_event(
            "alert", level_id=worst.id, metric=metric, status=worst.status, value=value
        )
        return AlertResponse(
            alert=True,
            level=worst.id,
            zone=worst.id,
            name=worst.name,
            depth_m=worst.depth_m,
            metric=metric,
            value=value,
            threshold=threshold,
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


def _metric_value_threshold(level: LevelStatus, metric: str, settings: Settings) -> tuple[float, float]:
    """The current value and danger threshold for the gas driving an alert."""
    table = {
        "methane": (level.methane, settings.methane_danger),
        "co": (level.co, settings.co_danger),
        "no2": (level.no2, settings.no2_danger),
        "co2": (level.co2, settings.co2_danger),
        "o2": (level.o2, settings.o2_danger),
    }
    return table.get(metric, (level.methane, settings.methane_danger))


@app.post("/ask", response_model=AskResponse)
async def post_ask(request: AskRequest) -> AskResponse:
    """Answer a free-text safety question from local docs (template, no LLM)."""
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
            mine=mine.MINE_NAME,
            mqtt_connected=ctx.mqtt_connected,
            levels_tracked=ctx.store.levels_with_data(),
            historian_enabled=ctx.historian.enabled,
            uptime_seconds=round(time.time() - ctx.started_at, 1),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error building /health response")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to read health", "detail": str(exc)},
        )
