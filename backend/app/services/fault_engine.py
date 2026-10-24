"""Deterministic fault and warning event generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import WarningThresholds
from app.models.simulation import EventSeverity, EventType, TemperatureState


@dataclass(frozen=True)
class SimulationEvent:
    event_id: str
    event_type: EventType
    severity: EventSeverity
    triggering_value: float
    threshold: Optional[float]
    unit: str
    message: str
    suggested_action: str
    elapsed_simulation_minutes: float


def classify_temperature(
    temperature_c: float,
    thresholds: WarningThresholds,
) -> TemperatureState:
    if temperature_c >= thresholds.battery_temperature_critical_c:
        return TemperatureState.CRITICAL
    if temperature_c >= thresholds.battery_temperature_warning_c:
        return TemperatureState.WARNING
    return TemperatureState.NORMAL


def generate_events(
    *,
    battery_temperature_c: float,
    obstacle_distance_m: float | None,
    final_soc_percent: float,
    battery_depleted: bool,
    thresholds: WarningThresholds,
    elapsed_simulation_minutes: float,
) -> List[SimulationEvent]:
    events: List[SimulationEvent] = []

    temp_state = classify_temperature(battery_temperature_c, thresholds)
    if temp_state == TemperatureState.CRITICAL:
        events.append(
            SimulationEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.BATTERY_TEMPERATURE,
                severity=EventSeverity.CRITICAL,
                triggering_value=battery_temperature_c,
                threshold=thresholds.battery_temperature_critical_c,
                unit="°C",
                message=(
                    f"Simulated battery temperature {battery_temperature_c:.1f} °C exceeds "
                    f"critical demonstration threshold {thresholds.battery_temperature_critical_c:.1f} °C."
                ),
                suggested_action=(
                    "Review thermal inputs; this is a simulation threshold, not a diagnosis of battery damage."
                ),
                elapsed_simulation_minutes=elapsed_simulation_minutes,
            )
        )
    elif temp_state == TemperatureState.WARNING:
        events.append(
            SimulationEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.BATTERY_TEMPERATURE,
                severity=EventSeverity.WARNING,
                triggering_value=battery_temperature_c,
                threshold=thresholds.battery_temperature_warning_c,
                unit="°C",
                message=(
                    f"Simulated battery temperature {battery_temperature_c:.1f} °C exceeds "
                    f"warning demonstration threshold {thresholds.battery_temperature_warning_c:.1f} °C."
                ),
                suggested_action="Consider reducing thermal stress in subsequent scenarios.",
                elapsed_simulation_minutes=elapsed_simulation_minutes,
            )
        )

    if obstacle_distance_m is not None and obstacle_distance_m < thresholds.obstacle_proximity_warning_m:
        events.append(
            SimulationEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.OBSTACLE_PROXIMITY,
                severity=EventSeverity.WARNING,
                triggering_value=obstacle_distance_m,
                threshold=thresholds.obstacle_proximity_warning_m,
                unit="m",
                message=(
                    f"Obstacle distance {obstacle_distance_m:.1f} m is below configured "
                    f"proximity warning threshold {thresholds.obstacle_proximity_warning_m:.1f} m."
                ),
                suggested_action=(
                    "This is a rule-based proximity warning, not collision prediction or stopping distance."
                ),
                elapsed_simulation_minutes=elapsed_simulation_minutes,
            )
        )

    if final_soc_percent < thresholds.low_soc_warning_percent:
        events.append(
            SimulationEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.LOW_BATTERY,
                severity=EventSeverity.WARNING,
                triggering_value=final_soc_percent,
                threshold=thresholds.low_soc_warning_percent,
                unit="%",
                message=(
                    f"Simulated final SOC {final_soc_percent:.2f}% is below low-battery "
                    f"threshold {thresholds.low_soc_warning_percent:.1f}%."
                ),
                suggested_action="Reduce energy demand or increase initial charge in the scenario.",
                elapsed_simulation_minutes=elapsed_simulation_minutes,
            )
        )

    if battery_depleted:
        events.append(
            SimulationEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.BATTERY_DEPLETION,
                severity=EventSeverity.CRITICAL,
                triggering_value=final_soc_percent,
                threshold=0.0,
                unit="%",
                message=(
                    "Requested interval energy exceeds available battery energy; "
                    "battery treated as depleted for this simulation."
                ),
                suggested_action=(
                    "Shorten duration, reduce speed or gradient, or increase initial SOC, then re-run."
                ),
                elapsed_simulation_minutes=elapsed_simulation_minutes,
            )
        )

    return events
