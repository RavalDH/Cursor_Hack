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


class ZoneStatus(BaseModel):
    """Computed view of one zone, as returned by GET /zones."""

    id: str
    methane: float
    co: float
    temp: float
    airflow: float
    status: Status
    trend: Trend


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
