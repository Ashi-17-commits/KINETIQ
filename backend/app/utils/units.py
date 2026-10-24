"""Unit conversions for the physics engine."""

from __future__ import annotations

import math


def speed_kmh_to_m_s(speed_kmh: float) -> float:
    """Convert speed from km/h to m/s."""
    return speed_kmh / 3.6


def gradient_percent_to_radians(gradient_percent: float) -> float:
    """Convert road gradient percentage to road angle in radians."""
    return math.atan(gradient_percent / 100.0)


def gradient_percent_to_degrees(gradient_percent: float) -> float:
    """Convert road gradient percentage to road angle in degrees."""
    return math.degrees(gradient_percent_to_radians(gradient_percent))


def minutes_to_hours(duration_minutes: float) -> float:
    """Convert duration from minutes to hours."""
    return duration_minutes / 60.0


def ensure_finite(value: float) -> float:
    """Raise ValueError if value is NaN or infinite."""
    if not math.isfinite(value):
        raise ValueError(f"Non-finite numerical result: {value}")
    return value
