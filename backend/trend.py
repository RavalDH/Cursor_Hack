"""Per-level status, multi-gas classification, trend and re-entry logic.

This is the heart of the system and the differentiator: we don't wait for a gas
to *cross* a danger line before reacting. We watch the recent history and flag a
level that is *climbing* toward danger, so the crew can withdraw in an orderly
way before it becomes an emergency.

A real fixed monitor heads up several gases at once and alarms on the worst, so
we classify every channel (CH4, CO, NO2, CO2, O2) and let the most severe one
drive the level's status. The maths stays deliberately simple and explainable —
when you justify a safety decision to a mine inspector, "the last few CO readings
trended up and crossed the limit" beats a black-box model.
"""

from config import Settings
from models import GasReading, Status, Trend, LevelStatus
import mine

# Average rise (per reading) needed to count a channel as "rising". A small
# deadband stops normal sensor noise from constantly toggling rising/stable.
_RISING_SLOPE_EPSILON = 0.01

# Fan idle baseline (matches LevelSimulator.FAN_IDLE). Above this means the fan
# has actively ramped, i.e. the level is being mitigated right now.
_FAN_IDLE = 20.0

# Order in which gases are considered when picking the one that "drives" a
# level's status among equally-severe channels. CO and methane lead because they
# carry the headline post-blast and flammable hazards.
_METRIC_PRIORITY = ("co", "methane", "no2", "o2", "co2")

# Human labels for the driving metric, used in actions/UI.
_METRIC_LABEL = {
    "co": "carbon monoxide",
    "methane": "methane",
    "no2": "nitrogen dioxide",
    "o2": "oxygen deficiency",
    "co2": "carbon dioxide",
}


def _gas_status(value: float, warning: float, danger: float, lower_is_worse: bool = False) -> Status:
    """Classify one gas channel. For O2, *low* is the hazard, so flip the test."""
    if lower_is_worse:
        if value <= danger:
            return "red"
        if value <= warning:
            return "yellow"
        return "green"
    if value >= danger:
        return "red"
    if value >= warning:
        return "yellow"
    return "green"


def _slope(values: list[float]) -> float:
    """Average step-to-step change across a window (positive = rising)."""
    if len(values) < 2:
        return 0.0
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    return sum(deltas) / len(deltas)


def _is_rising(values: list[float]) -> bool:
    return _slope(values) > _RISING_SLOPE_EPSILON


def detect_trend(readings: list[GasReading]) -> Trend:
    """Backward-compatible methane trend over the recent window."""
    return "rising" if _is_rising([r.methane for r in readings]) else "stable"


_SEVERITY = {"green": 0, "yellow": 1, "red": 2}


def _channel_statuses(latest: GasReading, methane_rising: bool, settings: Settings) -> dict[str, Status]:
    """Status per gas channel for one reading."""
    statuses: dict[str, Status] = {
        "methane": _gas_status(latest.methane, settings.methane_warning, settings.methane_danger),
        "co": _gas_status(latest.co, settings.co_warning, settings.co_danger),
        "no2": _gas_status(latest.no2, settings.no2_warning, settings.no2_danger),
        "co2": _gas_status(latest.co2, settings.co2_warning, settings.co2_danger),
        "o2": _gas_status(latest.o2, settings.o2_warning, settings.o2_danger, lower_is_worse=True),
    }
    # Early warning: methane climbing through the early-warning band escalates to
    # yellow even before it reaches the fixed warning limit — the trend payoff.
    if (
        statuses["methane"] == "green"
        and methane_rising
        and latest.methane >= settings.methane_early_warning
    ):
        statuses["methane"] = "yellow"
    return statuses


def _worst(statuses: dict[str, Status]) -> tuple[Status, str]:
    """Return the worst status and which gas drives it (by severity, then priority)."""
    worst_status: Status = "green"
    for s in statuses.values():
        if _SEVERITY[s] > _SEVERITY[worst_status]:
            worst_status = s
    if worst_status == "green":
        return "green", "none"
    for metric in _METRIC_PRIORITY:
        if statuses.get(metric) == worst_status:
            return worst_status, metric
    return worst_status, "none"


def safety_actions(status: Status, metric: str) -> list[str]:
    """Concrete escalating safety steps — the "solve" — for a level.

    Mirrors the Reg 854 response: a yellow level gets early, reversible measures
    (ramp ventilation, notify the supervisor); a red level gets the full
    withdrawal sequence. Cutting power to non-flameproof gear and stopping
    ignition-capable work matter for methane because it only explodes with a
    spark — remove the source and you buy time to get people out.
    """
    label = _METRIC_LABEL.get(metric, metric)
    if status == "red":
        actions = [
            "Ventilation fan at maximum airflow",
            "Withdraw crew to fresh air, barricade the level",
        ]
        if metric == "methane":
            actions.insert(1, "Cut power to non-flameproof equipment; stop ignition-capable work")
        if metric in ("co", "no2"):
            actions.insert(1, "Don escape respirators; no re-entry until air is re-tested")
        if metric == "o2":
            actions.insert(1, "Oxygen-deficient: do not enter without supplied air")
        return actions
    if status == "yellow":
        return [f"Ventilation ramping up to clear {label}", "Notify supervisor"]
    return ["Normal operation"]


def evaluate_level(
    level_id: str, readings: list[GasReading], settings: Settings
) -> LevelStatus | None:
    """Build the full LevelStatus for one level from its reading history.

    Returns None when a level has no readings yet (its sensor hasn't reported
    since startup) so callers can simply skip it.
    """
    if not readings:
        return None

    latest = readings[-1]
    methane_rising = _is_rising([r.methane for r in readings])
    statuses = _channel_statuses(latest, methane_rising, settings)
    status, metric = _worst(statuses)

    # Overall trend follows the driving gas; when green, fall back to methane so
    # an early climb still reads as "rising".
    trend_metric = metric if metric != "none" else "methane"
    trend: Trend = "rising" if _is_rising([getattr(r, trend_metric) for r in readings]) else "stable"

    co_values = [r.co for r in readings]
    twa_co = round(sum(co_values) / len(co_values), 1)

    mitigation = latest.fan_speed > _FAN_IDLE

    # Re-entry only means something on a level working a blast cycle. CO governs
    # it because it clears slowest; the crew may return once CO is back under the
    # warning limit and the level is no longer red.
    re_entry_allowed: bool | None = None
    clearance: str | None = None
    if level_id == settings.active_blast_level:
        re_entry_allowed = latest.co < settings.co_warning and status != "red"
        clearance = "re-entry granted" if re_entry_allowed else "clearing blast gases"

    info = mine.describe(level_id)
    return LevelStatus(
        id=level_id,
        name=info.name,
        depth_m=info.depth_m,
        area=info.area,
        airway=info.airway,
        methane=round(latest.methane, 3),
        co=round(latest.co, 1),
        co2=round(latest.co2, 3),
        no2=round(latest.no2, 2),
        o2=round(latest.o2, 2),
        temp=round(latest.temp, 1),
        airflow=round(latest.airflow, 2),
        status=status,
        trend=trend,
        metric=metric,
        fan_speed=round(latest.fan_speed, 1),
        mitigation=mitigation,
        twa_co=twa_co,
        re_entry_allowed=re_entry_allowed,
        clearance=clearance,
        actions=safety_actions(status, metric),
    )


def severity_rank(level: LevelStatus) -> tuple[int, int, float]:
    """Sort key for choosing the highest-severity level for /alert.

    Order by status severity, then whether it's rising (a rising yellow is more
    urgent than a stable one), then a numeric tie-breaker.
    """
    return (
        _SEVERITY[level.status],
        1 if level.trend == "rising" else 0,
        level.co + level.methane,
    )
