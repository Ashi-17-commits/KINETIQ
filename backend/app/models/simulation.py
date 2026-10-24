"""Simulation domain enums and state machine."""

from __future__ import annotations

from enum import Enum


class SimulationStatus(str, Enum):
    """Simulation lifecycle states."""

    READY = "READY"
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    FAULT = "FAULT"
    RECOVERY = "RECOVERY"
    COMPLETED = "COMPLETED"


class EventSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    BATTERY_TEMPERATURE = "BATTERY_TEMPERATURE"
    OBSTACLE_PROXIMITY = "OBSTACLE_PROXIMITY"
    LOW_BATTERY = "LOW_BATTERY"
    BATTERY_DEPLETION = "BATTERY_DEPLETION"


class BatteryState(str, Enum):
    NORMAL = "NORMAL"
    LOW = "LOW"
    DEPLETED = "DEPLETED"


class TemperatureState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def resolve_final_status(events: list) -> SimulationStatus:
    """
    Determine terminal simulation status from generated events.

    Precedence: FAULT (CRITICAL or depletion) > WARNING > COMPLETED.
    """
    has_critical = any(
        e.severity == EventSeverity.CRITICAL
        or e.event_type == EventType.BATTERY_DEPLETION
        for e in events
    )
    has_warning = any(e.severity == EventSeverity.WARNING for e in events)

    if has_critical:
        return SimulationStatus.FAULT
    if has_warning:
        return SimulationStatus.WARNING
    return SimulationStatus.COMPLETED
