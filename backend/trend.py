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

# The fan's idle baseline (matches ZoneSimulator.FAN_IDLE). Anything above this
# means the fan has actively ramped, i.e. the zone is being mitigated right now.
_FAN_IDLE = 20.0


def safety_actions(status: Status) -> list[str]:
    """The concrete safety steps for a zone at a given status — the "solve".

    These mirror the escalating Reg 854 response: a yellow zone gets early,
    reversible measures (ramp ventilation, tell the supervisor); a red zone gets
    the full withdrawal sequence. Cutting power to non-flameproof equipment and
    stopping ignition-capable work matter because methane only explodes with an
    ignition source — remove the spark and you buy time to get people out.
    """
    if status == "red":
        return [
            "Fan at maximum airflow",
            "Cut power to non-flameproof equipment",
            "Stop ignition-capable work",
            "Evacuate zone - withdraw to fresh air",
        ]
    if status == "yellow":
        return ["Ventilation fan ramping up", "Notify supervisor"]
    return ["Normal operation"]


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
      yellow : in the warning band (>= 1.0%), OR rising while already in the
               early-warning band (>= 0.9%)
      green  : below the early-warning band, or rising only at baseline noise

    The early-warning band is what makes the trend useful without being jumpy: a
    zone climbing *toward* danger flags early, but random noise on a calm zone
    sitting at ~0.5% can't flip it yellow.
    """
    if methane >= settings.methane_danger:
        return "red"

    if methane >= settings.methane_warning:
        return "yellow"

    if trend == "rising" and methane >= settings.methane_early_warning:
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

    # Fan is actively mitigating whenever it has ramped above its idle baseline.
    mitigation = latest.fan_speed > _FAN_IDLE

    return ZoneStatus(
        id=zone_id,
        methane=round(latest.methane, 3),
        co=round(latest.co, 1),
        temp=round(latest.temp, 1),
        airflow=round(latest.airflow, 2),
        status=status,
        trend=trend,
        fan_speed=round(latest.fan_speed, 1),
        mitigation=mitigation,
        actions=safety_actions(status),
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
