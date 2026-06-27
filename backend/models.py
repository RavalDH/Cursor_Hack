"""Pydantic request/response models.

These models are the contract between the backend and the frontend. They also do
double duty as input validation: a malformed /ask body is rejected by FastAPI
with a 422 before our handler code ever runs, so we never have to hand-check
types.

The reading now carries the multi-gas picture a real fixed environmental station
reports (CH4, CO, CO2, NO2, O2, plus airflow and temperature), not just methane.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Status and trend are closed sets — using Literal means an impossible value
# (e.g. status "orange") is a programming error caught by type checkers/tests.
Status = Literal["green", "yellow", "red"]
Trend = Literal["rising", "stable"]


class GasReading(BaseModel):
    """A single raw reading published by a level's sensor station over MQTT.

    Mirrors a real fixed multi-gas head: a flammable-gas channel (methane) plus
    toxic/asphyxiant channels (CO, CO2, NO2, O2), airflow and temperature. New
    gas fields carry sensible fresh-air defaults so an older/partial payload
    still validates rather than being dropped.
    """

    methane: float = Field(..., description="Methane (flammable), % by volume")
    co: float = Field(..., description="Carbon monoxide, parts per million")
    temp: float = Field(..., description="Temperature, degrees Celsius")
    airflow: float = Field(..., description="Airflow, cubic metres per second")
    co2: float = Field(default=0.04, description="Carbon dioxide, % by volume")
    no2: float = Field(default=0.0, description="Nitrogen dioxide, parts per million")
    o2: float = Field(default=20.9, description="Oxygen, % by volume")
    # Current ventilation fan speed (0-100%) for this level. Defaults to the idle
    # baseline so payloads that predate fan control still validate.
    fan_speed: float = Field(default=20.0, description="Ventilation fan speed, %")


class LevelStatus(BaseModel):
    """Computed view of one level, as returned by GET /levels.

    Carries both the raw multi-gas values and the system's interpretation:
    overall status, what's driving it, the trend, whether ventilation is actively
    mitigating, the rolling CO average used for re-entry, and the concrete
    actions in progress.
    """

    id: str
    name: str
    depth_m: int
    area: str
    airway: str

    methane: float
    co: float
    co2: float
    no2: float
    o2: float
    temp: float
    airflow: float

    status: Status
    trend: Trend
    # The gas currently driving this level's status (e.g. "co" right after a
    # blast, "methane" for a seep). "none" when green on all channels.
    metric: str
    # Live ventilation fan speed (0-100%). Rises automatically under VoD control.
    fan_speed: float
    # True while the fan is ramped above idle, i.e. the level is being
    # auto-mitigated right now.
    mitigation: bool
    # Rolling average CO (ppm) over the recent window — a short-horizon stand-in
    # for the TWA a real monitor reports, used to judge post-blast re-entry.
    twa_co: float
    # Re-entry state for a level working a blast cycle: None when not applicable,
    # True once the air has cleared below the re-entry limit, False while the
    # crew must stay out.
    re_entry_allowed: bool | None = None
    # Short status phrase for the ventilation/blast cycle, e.g. "clearing blast
    # gases" or "re-entry granted". None on ordinary levels.
    clearance: str | None = None
    # The concrete safety steps being taken/advised — the "solve".
    actions: list[str] = Field(default_factory=list)


class LevelsResponse(BaseModel):
    """Envelope for GET /levels."""

    mine: str
    levels: list[LevelStatus]


class ZonesResponse(BaseModel):
    """Backward-compatible envelope for GET /zones (deprecated alias).

    The original contract used "zones"; the system now models mine "levels". This
    keeps an existing UI that polls /zones working — the objects are identical.
    """

    zones: list[LevelStatus]


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
    # Primary identifier of the alerting level. `zone` duplicates `level` for
    # backward compatibility with the original /alert contract.
    level: str | None = None
    zone: str | None = None
    name: str | None = None
    depth_m: int | None = None
    metric: str | None = None
    value: float | None = None
    threshold: float | None = None
    trend: Trend | None = None
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    # Recovery signal: when no level is alerting but one just came back from red
    # to green, we surface it here so the UI/voice can give an "all clear" line
    # instead of going silent.
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
    mine: str
    mqtt_connected: bool
    levels_tracked: int
    historian_enabled: bool
    uptime_seconds: float
