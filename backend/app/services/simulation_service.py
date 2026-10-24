"""Orchestrates physics, battery, events, and recommendations."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.core.config import (
    MODEL_ASSUMPTIONS,
    MODEL_LIMITATIONS,
    PATH_PLANNING_INTEGRATION_DOC,
    ROAD_SURFACE_ENERGY_EFFECT,
    WarningThresholds,
    default_vehicle_dict,
)
from app.models.simulation import BatteryState, SimulationStatus, resolve_final_status
from app.services.battery_service import BatteryInputs, compute_battery_state
from app.services.energy_engine import EnergyInputs, VehicleConfig, compute_energy
from app.services.fault_engine import generate_events
from app.services.history_store import HistoryStore
from app.services.recommendation_engine import build_recommendations


def _vehicle_from_dict(data: dict) -> VehicleConfig:
    return VehicleConfig(
        mass_kg=data["mass_kg"],
        rolling_resistance_coefficient=data["rolling_resistance_coefficient"],
        drag_coefficient=data["drag_coefficient"],
        frontal_area_m2=data["frontal_area_m2"],
        air_density_kg_m3=data["air_density_kg_m3"],
        gravity_m_s2=data["gravity_m_s2"],
        drivetrain_efficiency=data["drivetrain_efficiency"],
        auxiliary_power_kw=data["auxiliary_power_kw"],
        usable_battery_capacity_kwh=data["usable_battery_capacity_kwh"],
    )


def merge_vehicle_params(overrides: Optional[dict]) -> dict:
    base = default_vehicle_dict()
    if overrides:
        for key, value in overrides.items():
            if value is not None and key in base:
                base[key] = value
    return base


class SimulationService:
    def __init__(self, history: HistoryStore, thresholds: Optional[WarningThresholds] = None) -> None:
        self.history = history
        self.thresholds = thresholds or WarningThresholds()

    def run_simulation(
        self,
        scenario: dict[str, Any],
        *,
        store: bool = True,
        baseline_physics: Optional[Any] = None,
        baseline_gradient: Optional[float] = None,
    ) -> dict[str, Any]:
        sim_id = str(uuid.uuid4())
        vehicle_dict = merge_vehicle_params(scenario.get("vehicle_parameters"))
        vehicle = _vehicle_from_dict(vehicle_dict)

        speed = scenario["speed_kmh"]
        gradient = scenario["gradient_percent"]
        duration = scenario["duration_minutes"]
        initial_soc = scenario["initial_soc_percent"]
        battery_temp = scenario["battery_temperature_c"]
        road_surface = scenario.get("road_surface", "dry")
        obstacle_m = scenario.get("obstacle_distance_m")
        obstacle_source = scenario.get("obstacle_source")

        physics = compute_energy(
            EnergyInputs(speed_kmh=speed, gradient_percent=gradient, duration_minutes=duration),
            vehicle,
        )
        battery = compute_battery_state(
            BatteryInputs(
                initial_soc_percent=initial_soc,
                usable_battery_capacity_kwh=vehicle.usable_battery_capacity_kwh,
                requested_energy_kwh=physics.requested_energy_kwh,
            )
        )

        battery_state = battery.battery_state
        if not battery.battery_depleted and battery.final_soc_percent < self.thresholds.low_soc_warning_percent:
            battery_state = BatteryState.LOW

        events = generate_events(
            battery_temperature_c=battery_temp,
            obstacle_distance_m=obstacle_m,
            final_soc_percent=battery.final_soc_percent,
            battery_depleted=battery.battery_depleted,
            thresholds=self.thresholds,
            elapsed_simulation_minutes=duration,
        )

        terminal_status = resolve_final_status(events)
        recommendations = build_recommendations(
            physics=physics,
            gradient_percent=gradient,
            speed_kmh=speed,
            road_surface=road_surface,
            events=events,
            baseline_physics=baseline_physics,
            baseline_gradient_percent=baseline_gradient,
        )

        result = {
            "simulation_id": sim_id,
            "scenario_name": scenario.get("scenario_name"),
            "status": terminal_status.value,
            "execution_trace": {
                "previous_status": SimulationStatus.RUNNING.value,
                "terminal_status": terminal_status.value,
            },
            "inputs": {
                "speed_kmh": speed,
                "initial_soc_percent": initial_soc,
                "battery_temperature_c": battery_temp,
                "gradient_percent": gradient,
                "road_surface": road_surface,
                "obstacle_distance_m": obstacle_m,
                "obstacle_source": obstacle_source,
                "duration_minutes": duration,
            },
            "vehicle_parameters": vehicle_dict,
            "physics": {
                "road_angle_rad": physics.road_angle_rad,
                "road_angle_deg": physics.road_angle_deg,
                "road_surface_energy_effect": ROAD_SURFACE_ENERGY_EFFECT,
                "rolling_resistance_force_n": physics.rolling_resistance_force_n,
                "aerodynamic_drag_force_n": physics.aerodynamic_drag_force_n,
                "grade_resistance_force_n": physics.grade_resistance_force_n,
                "tractive_force_n": physics.tractive_force_n,
                "longitudinal_acceleration_m_s2": physics.longitudinal_acceleration_m_s2,
                "wheel_power_kw": physics.wheel_power_kw,
                "battery_power_kw": physics.battery_power_kw,
                "requested_energy_kwh": physics.requested_energy_kwh,
                "distance_km": physics.distance_km,
                "consumption_kwh_per_100km": physics.consumption_kwh_per_100km,
                "consumption_unavailable_reason": physics.consumption_unavailable_reason,
            },
            "battery": {
                "initial_soc_percent": battery.initial_soc_percent,
                "final_soc_percent": battery.final_soc_percent,
                "usable_battery_capacity_kwh": battery.usable_battery_capacity_kwh,
                "available_energy_kwh": battery.available_energy_kwh,
                "requested_energy_kwh": battery.requested_energy_kwh,
                "energy_drawn_kwh": battery.energy_drawn_kwh,
                "energy_supplied_kwh": battery.energy_supplied_kwh,
                "battery_depleted": battery.battery_depleted,
                "battery_state": battery_state.value,
                "depletion_note": battery.depletion_note,
                "trip_completed_in_model": battery.trip_completed_in_model,
            },
            "telemetry": {
                "data_quality": "simulated",
                "speed_kmh": speed,
                "battery_temperature_c": battery_temp,
                "initial_soc_percent": battery.initial_soc_percent,
                "final_soc_percent": battery.final_soc_percent,
                "wheel_power_kw": physics.wheel_power_kw,
                "battery_power_kw": physics.battery_power_kw,
                "requested_energy_kwh": physics.requested_energy_kwh,
                "energy_supplied_kwh": battery.energy_supplied_kwh,
                "distance_km": physics.distance_km,
                "consumption_kwh_per_100km": physics.consumption_kwh_per_100km,
                "gradient_percent": gradient,
                "road_surface": road_surface,
                "status": terminal_status.value,
            },
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "severity": e.severity.value,
                    "triggering_value": e.triggering_value,
                    "threshold": e.threshold,
                    "unit": e.unit,
                    "message": e.message,
                    "suggested_action": e.suggested_action,
                    "elapsed_simulation_minutes": e.elapsed_simulation_minutes,
                }
                for e in events
            ],
            "recommendations": [
                {
                    "category": r.category,
                    "priority": r.priority,
                    "title": r.title,
                    "explanation": r.explanation,
                    "relevant_measurement_value": r.relevant_measurement_value,
                    "relevant_measurement_unit": r.relevant_measurement_unit,
                    "relevant_measurement": r.relevant_measurement,
                    "suggested_action": r.suggested_action,
                    "reason": r.reason,
                    "evaluation_hint": r.evaluation_hint,
                }
                for r in recommendations
            ],
            "path_planning_integration": {
                "contract_version": PATH_PLANNING_INTEGRATION_DOC["contract_version"],
                "status": PATH_PLANNING_INTEGRATION_DOC["status"],
                "obstacle_source": obstacle_source,
                "message": PATH_PLANNING_INTEGRATION_DOC["message"],
            },
            "assumptions": list(MODEL_ASSUMPTIONS),
            "limitations": list(MODEL_LIMITATIONS),
            "units": {
                "speed": "km/h",
                "distance": "km",
                "energy": "kWh",
                "power": "kW",
                "force": "N",
                "angle": "deg and rad",
                "soc": "%",
                "temperature": "°C",
                "road_surface": "category",
            },
        }

        if store:
            self.history.add(sim_id, result)
        return result
