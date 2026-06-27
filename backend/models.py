"""Pydantic request/response models.

These models are the contract between the backend and the frontend (see PLAN.md
section 6). They also do double duty as input validation: a malformed /ask body
is rejected by FastAPI with a 422 before our handler code ever runs, so we never
have to hand-check types.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Status and trend are closed sets — using Literal means an impossible value
# (e.g. status "orange") is a programming error caught by type checkers/tests.
Status = Literal["green", "yellow", "red"]
Trend = Literal["rising", "stable"]


class GasReading(BaseModel):
    """A single raw reading published by a zone sensor over MQTT.

    Used to validate inbound MQTT payloads. If a payload doesn't fit this shape
    we log a warning and skip it rather than crashing the subscriber.
    """

    methane: float = Field(..., description="Methane concentration, % by volume")
    co: float = Field(..., description="Carbon monoxide, parts per million")
    temp: float = Field(..., description="Temperature, degrees Celsius")
    airflow: float = Field(..., description="Airflow, cubic metres per second")
    # Current ventilation fan speed (0-100%) for this zone. Defaults to the idle
    # baseline so older payloads that predate fan control still validate and are
    # simply treated as "fan idling" rather than being rejected.
    fan_speed: float = Field(default=20.0, description="Ventilation fan speed, %")


class ZoneStatus(BaseModel):
    """Computed view of one zone, as returned by GET /zones."""

    id: str
    methane: float
    co: float
    temp: float
    airflow: float
    status: Status
    trend: Trend
    # Live ventilation fan speed (0-100%). Rises automatically as methane climbs.
    fan_speed: float
    # True while the fan is actively ramped above idle, i.e. the zone is being
    # auto-mitigated right now. Lets the UI show a "ventilating" indicator.
    mitigation: bool
    # The concrete safety steps being taken/advised for this zone's status — the
    # "solve". Empty (or normal-operation) when green.
    actions: list[str] = Field(default_factory=list)


class ZonesResponse(BaseModel):
    """Envelope for GET /zones."""

    zones: list[ZoneStatus]


class Citation(BaseModel):
    """A pointer back to the Reg 854 source text that grounds an answer.

    Grounding matters here: safety guidance that can't be traced to a regulation
    is just a guess, and underground that's unacceptable.
    """

    source: str
    text: str


class AlertResponse(BaseModel):
    """GET /alert response.

    When nothing is wrong, only `alert: false` is set and the rest stay None so
    the frontend can branch on a single boolean.
    """

    alert: bool
    zone: str | None = None
    metric: str | None = None
    value: float | None = None
    threshold: float | None = None
    trend: Trend | None = None
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    # Recovery signal: when no zone is alerting but one just came back from red
    # to green, we surface it here so the UI/voice can give an "all clear" line
    # instead of going silent. Silence after an alarm reads as "did it fix
    # itself or did the system die?" — an explicit all-clear is reassuring.
    recovered: bool = False
    recovered_zone: str | None = None
    message: str | None = None


class AskRequest(BaseModel):
    """POST /ask body. A blank question is rejected (min_length=1 -> 422)."""

    question: str = Field(..., min_length=1, description="Free-text safety question")


class AskResponse(BaseModel):
    """POST /ask response: a template answer plus its citations."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """GET /health response — quick liveness/operational snapshot."""

    status: str
    mqtt_connected: bool
    zones_tracked: int
    uptime_seconds: float
