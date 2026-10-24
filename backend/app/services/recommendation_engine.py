"""Deterministic, explainable recommendations from physics and events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.models.domain_types import RoadSurface
from app.models.simulation import EventType
from app.services.energy_engine import EnergyOutputs
from app.services.fault_engine import SimulationEvent


@dataclass(frozen=True)
class Recommendation:
    category: str
    priority: str
    title: str
    explanation: str
    relevant_measurement_value: Optional[float]
    relevant_measurement_unit: Optional[str]
    relevant_measurement: str
    suggested_action: str
    reason: str
    evaluation_hint: Optional[str] = None


def _rec(
    *,
    category: str,
    priority: str,
    title: str,
    explanation: str,
    value: Optional[float],
    unit: Optional[str],
    label: str,
    suggested_action: str,
    reason: str,
    evaluation_hint: Optional[str] = None,
) -> Recommendation:
    measurement = f"{label} = {value:.2f} {unit}" if value is not None and unit else label
    return Recommendation(
        category=category,
        priority=priority,
        title=title,
        explanation=explanation,
        relevant_measurement_value=value,
        relevant_measurement_unit=unit,
        relevant_measurement=measurement,
        suggested_action=suggested_action,
        reason=reason,
        evaluation_hint=evaluation_hint,
    )


def build_recommendations(
    *,
    physics: EnergyOutputs,
    gradient_percent: float,
    speed_kmh: float,
    road_surface: RoadSurface,
    events: List[SimulationEvent],
    baseline_physics: Optional[EnergyOutputs] = None,
    baseline_gradient_percent: Optional[float] = None,
) -> List[Recommendation]:
    recs: List[Recommendation] = []

    if road_surface != "dry":
        recs.append(
            _rec(
                category="road_conditions",
                priority="low",
                title="Road surface recorded (energy not modelled)",
                explanation=(
                    f"Road surface '{road_surface}' is stored for scenario context. "
                    "Energy physics are unchanged in this MVP (road_surface_energy_effect: not_modelled)."
                ),
                value=None,
                unit=None,
                label=f"road_surface={road_surface}",
                suggested_action="Use /api/v1/compare to explore speed or gradient changes that do affect energy.",
                reason="Surface type is an input field without a validated energy model in this version.",
            )
        )

    if abs(physics.grade_resistance_force_n) > 50.0 and gradient_percent > 0:
        recs.append(
            _rec(
                category="driving_conditions",
                priority="medium",
                title="Uphill grade adds resistance",
                explanation=(
                    f"Positive road gradient ({gradient_percent:.1f}%) increases grade resistance "
                    f"({physics.grade_resistance_force_n:.1f} N) in the simulation model."
                ),
                value=physics.grade_resistance_force_n,
                unit="N",
                label="F_grade",
                suggested_action="Compare with a flat-road baseline to quantify uphill impact.",
                reason="Computed grade resistance force is material for this gradient input.",
                evaluation_hint="POST /api/v1/compare with gradient_percent=0 as baseline.",
            )
        )
    elif gradient_percent < 0 and physics.grade_resistance_force_n < -10:
        recs.append(
            _rec(
                category="driving_conditions",
                priority="low",
                title="Downhill grade reduces tractive demand",
                explanation=(
                    f"Negative gradient ({gradient_percent:.1f}%) reduces required tractive force; "
                    "regenerative recovery is not modeled, so battery load may still include auxiliaries."
                ),
                value=physics.grade_resistance_force_n,
                unit="N",
                label="F_grade",
                suggested_action="Inspect battery_power_kw when wheel power is non-positive.",
                reason="Negative grade reduces tractive force in the implemented force balance.",
            )
        )

    drag_share = physics.aerodynamic_drag_force_n / max(abs(physics.tractive_force_n), 1e-6)
    if physics.aerodynamic_drag_force_n > 30.0 and drag_share > 0.25:
        recs.append(
            _rec(
                category="aerodynamics",
                priority="medium",
                title="Aerodynamic drag is material",
                explanation=(
                    f"At {speed_kmh:.0f} km/h, drag force is {physics.aerodynamic_drag_force_n:.1f} N "
                    "(scales with speed squared in this model)."
                ),
                value=physics.aerodynamic_drag_force_n,
                unit="N",
                label="F_drag",
                suggested_action="Try a lower speed in a comparison scenario to estimate drag-related demand change.",
                reason="Drag force magnitude and share of tractive force exceed heuristic thresholds.",
                evaluation_hint="POST /api/v1/compare with a reduced speed_kmh as comparison scenario.",
            )
        )

    if baseline_physics is not None and baseline_gradient_percent is not None:
        if gradient_percent != baseline_gradient_percent:
            delta_e = physics.requested_energy_kwh - baseline_physics.requested_energy_kwh
            recs.append(
                _rec(
                    category="comparison",
                    priority="medium",
                    title="Gradient change affects energy demand",
                    explanation=(
                        f"Compared to baseline gradient {baseline_gradient_percent:.1f}%, "
                        f"requested energy differs by {delta_e:.3f} kWh under the same model."
                    ),
                    value=delta_e,
                    unit="kWh",
                    label="ΔE_demand",
                    suggested_action="Review /api/v1/compare sustainability metrics for structured deltas.",
                    reason="Baseline physics were supplied for this comparison run.",
                )
            )

    for event in events:
        if event.event_type == EventType.OBSTACLE_PROXIMITY:
            recs.append(
                _rec(
                    category="safety_simulation",
                    priority="high",
                    title="Simulated obstacle proximity warning",
                    explanation=event.message,
                    value=event.triggering_value,
                    unit=event.unit,
                    label="obstacle_distance_m",
                    suggested_action=event.suggested_action,
                    reason="User-supplied or scenario distance is below the configured proximity threshold.",
                )
            )
        elif event.event_type == EventType.BATTERY_TEMPERATURE:
            recs.append(
                _rec(
                    category="thermal",
                    priority="high" if event.severity.value == "CRITICAL" else "medium",
                    title="Battery temperature threshold crossed",
                    explanation=event.message,
                    value=event.triggering_value,
                    unit=event.unit,
                    label="battery_temperature_c",
                    suggested_action=event.suggested_action,
                    reason="Simulated temperature crosses a configured demonstration threshold.",
                    evaluation_hint="POST /api/v1/recover with corrected battery_temperature_c after a fault run.",
                )
            )
        elif event.event_type == EventType.LOW_BATTERY:
            recs.append(
                _rec(
                    category="battery",
                    priority="medium",
                    title="Low simulated SOC",
                    explanation=event.message,
                    value=event.triggering_value,
                    unit="%",
                    label="final_soc_percent",
                    suggested_action=event.suggested_action,
                    reason="Final SOC from the battery model is below the low-SOC warning threshold.",
                )
            )
        elif event.event_type == EventType.BATTERY_DEPLETION:
            recs.append(
                _rec(
                    category="battery",
                    priority="critical",
                    title="Battery depletion in scenario",
                    explanation=event.message,
                    value=event.triggering_value,
                    unit="%",
                    label="final_soc_percent",
                    suggested_action=event.suggested_action,
                    reason="Requested interval energy exceeds available battery energy in the simplified model.",
                    evaluation_hint="Shorten duration or increase initial_soc_percent, then POST /api/v1/recover.",
                )
            )

    if not recs:
        recs.append(
            _rec(
                category="general",
                priority="low",
                title="Scenario within nominal simulation bounds",
                explanation=(
                    f"The {'steady-speed' if physics.aggregation == 'steady_state' else 'simulated-traffic'} model produced {physics.requested_energy_kwh:.3f} kWh demand "
                    f"over {physics.distance_km:.3f} km."
                ),
                value=physics.consumption_kwh_per_100km,
                unit="kWh/100 km" if physics.consumption_kwh_per_100km is not None else None,
                label="consumption",
                suggested_action="Adjust inputs or compare against a preset baseline.",
                reason="No warning events and no material heuristic thresholds were exceeded.",
            )
        )

    return recs
