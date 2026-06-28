"""Pydantic models — the contract with the frontend, and our input validation.

Readings carry the full multi-gas picture (CH4, CO, CO2, NO2, O2, airflow,
temp), like a real fixed environmental station.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Closed sets, so an impossible value (e.g. "orange") is a type error.
Status = Literal["green", "yellow", "red"]
Trend = Literal["rising", "stable"]


class GasReading(BaseModel):
    """One raw reading from a level's sensor station.

    Newer gas fields default to fresh-air values so an older/partial payload
    still validates instead of being dropped.
    """

    methane: float = Field(..., description="Methane (flammable), % by volume")
    co: float = Field(..., description="Carbon monoxide, parts per million")
    temp: float = Field(..., description="Temperature, degrees Celsius")
    airflow: float = Field(..., description="Airflow, cubic metres per second")
    co2: float = Field(default=0.04, description="Carbon dioxide, % by volume")
    no2: float = Field(default=0.0, description="Nitrogen dioxide, parts per million")
    o2: float = Field(default=20.9, description="Oxygen, % by volume")
    fan_speed: float = Field(default=20.0, description="Ventilation fan speed, %")


class LevelStatus(BaseModel):
    """Computed view of one level (GET /levels): raw gas values plus our read on them."""

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
    # Gas driving the status ("co", "methane", ...); "none" when all green.
    metric: str
    # Live fan speed 0-100%; rises automatically under ventilation-on-demand.
    fan_speed: float
    # True while the fan is ramped above idle (actively mitigating).
    mitigation: bool
    # Rolling CO average — short-horizon stand-in for a TWA, governs re-entry.
    twa_co: float
    # Re-entry for a level working a blast cycle: None if N/A, else cleared/not.
    re_entry_allowed: bool | None = None
    # Blast-cycle phrase, e.g. "clearing blast gases". None on ordinary levels.
    clearance: str | None = None
    # Concrete safety steps in progress — the "solve".
    actions: list[str] = Field(default_factory=list)


class LevelsResponse(BaseModel):
    """Envelope for GET /levels."""

    mine: str
    levels: list[LevelStatus]


class ZonesResponse(BaseModel):
    """Legacy envelope for GET /zones — identical objects under "zones"."""

    zones: list[LevelStatus]


class Citation(BaseModel):
    """Pointer to the Reg 854 source that grounds an answer (no citation = a guess)."""

    source: str
    text: str


class AlertResponse(BaseModel):
    """GET /alert. When nothing's wrong only `alert: false` is set; rest stay None."""

    alert: bool
    # `zone` duplicates `level` for the original /alert contract.
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
    # Set when no level is alerting but one just recovered red->green (all-clear).
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
