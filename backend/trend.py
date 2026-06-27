"""Per-zone status and trend detection.

This is the heart of the system and the differentiator in the pitch: we don't
wait for gas to *cross* a danger line before reacting. We watch the recent
history and flag a zone that is *climbing* toward danger, so the crew can leave
in an orderly way before it becomes an emergency.

The math is deliberately simple and explainable — when you're justifying a
safety decision to a mine inspector, "the last few readings trended up" beats a
black-box model.
"""

from config import Settings
from models import GasReading, Status, Trend, ZoneStatus

# A reading must rise by at least this much (% methane per reading) on average
# to count as "rising". A small deadband stops normal sensor noise from
# constantly toggling a zone between stable and rising.
_RISING_SLOPE_EPSILON = 0.01


def detect_trend(readings: list[GasReading]) -> Trend:
    """Decide whether methane is rising or stable over the recent window.

    Simple approach: average the step-to-step change in methane across the
    window. If the average step is clearly positive (above a small noise
    deadband), we call it rising; otherwise stable. We use the average slope
    rather than just comparing first vs last so one spiky reading doesn't
    dominate the decision.
    """
    # Need at least two points to have a direction at all.
    if len(readings) < 2:
        return "stable"

    methane_values = [r.methane for r in readings]
    deltas = [
        methane_values[i] - methane_values[i - 1]
        for i in range(1, len(methane_values))
    ]
    average_step = sum(deltas) / len(deltas)

    return "rising" if average_step > _RISING_SLOPE_EPSILON else "stable"


def classify_status(methane: float, trend: Trend, settings: Settings) -> Status:
    """Map a methane level + trend to a green/yellow/red status.

    Rules (demo thresholds — real legal limits differ, see docs/reg854_methane):
      red    : methane at/above the danger threshold (>= 1.5%)
      yellow : in the warning band (1.0%-1.5%) OR rising while below danger
      green  : below the warning level and not rising

    The "OR rising" clause is the early-warning behaviour: a zone climbing while
    still technically "safe" is already worth a warning.
    """
    if methane >= settings.methane_danger:
        return "red"

    if methane >= settings.methane_warning or trend == "rising":
        return "yellow"

    return "green"


def evaluate_zone(
    zone_id: str, readings: list[GasReading], settings: Settings
) -> ZoneStatus | None:
    """Build the full ZoneStatus for one zone from its reading history.

    Returns None when a zone has no readings yet (e.g. its sensor hasn't
    reported since startup) so callers can simply skip it.
    """
    if not readings:
        return None

    latest = readings[-1]
    trend = detect_trend(readings)
    status = classify_status(latest.methane, trend, settings)

    return ZoneStatus(
        id=zone_id,
        methane=round(latest.methane, 3),
        co=round(latest.co, 1),
        temp=round(latest.temp, 1),
        airflow=round(latest.airflow, 2),
        status=status,
        trend=trend,
    )


# Severity ordering used by /alert to pick the single most urgent zone.
# Higher number = more urgent.
_SEVERITY = {"green": 0, "yellow": 1, "red": 2}


def severity_rank(zone: ZoneStatus) -> tuple[int, int, float]:
    """Sort key for choosing the highest-severity zone.

    Order by: status severity, then whether it's rising (a rising yellow is more
    urgent than a stable yellow), then by methane value as the tie-breaker.
    """
    return (
        _SEVERITY[zone.status],
        1 if zone.trend == "rising" else 0,
        zone.methane,
    )
