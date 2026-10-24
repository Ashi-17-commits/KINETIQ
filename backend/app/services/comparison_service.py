"""Baseline versus comparison scenario analysis."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from app.services.energy_engine import EnergyInputs, compute_energy
from app.services.simulation_service import SimulationService, merge_vehicle_params, _vehicle_from_dict


def _pct_diff(baseline: Optional[float], comparison: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    if baseline is None or comparison is None:
        return None, "One or both values are unavailable."
    if baseline <= 0:
        return None, "Baseline value is zero or negative; percentage difference is not defined."
    return (comparison - baseline) / baseline * 100.0, None


def _model_reduction_percent(baseline: float, comparison: float) -> Tuple[Optional[float], Optional[str]]:
    if baseline <= 0:
        return None, "Baseline energy is not positive; estimated model energy reduction is not defined."
    return (baseline - comparison) / baseline * 100.0, (
        "Model-based estimate only; not a verified on-road energy saving."
    )


def _changed_inputs(base: dict, comp: dict) -> List[dict]:
    changes: List[dict] = []
    keys = sorted(set(base.keys()) | set(comp.keys()))
    for key in keys:
        if key == "vehicle_parameters":
            bv = base.get("vehicle_parameters") or {}
            cv = comp.get("vehicle_parameters") or {}
            for vk in sorted(set(bv.keys()) | set(cv.keys())):
                if bv.get(vk) != cv.get(vk):
                    changes.append(
                        {"field": f"vehicle_parameters.{vk}", "baseline": bv.get(vk), "comparison": cv.get(vk)}
                    )
            continue
        if base.get(key) != comp.get(key):
            changes.append({"field": key, "baseline": base.get(key), "comparison": comp.get(key)})
    return changes


def _event_signatures(events: List[dict]) -> set:
    return {(e["event_type"], e["severity"]) for e in events}


def _scenario_slice(scenario: dict) -> dict:
    out = {
        "scenario_name": scenario.get("scenario_name"),
        "speed_kmh": scenario.get("speed_kmh"),
        "initial_soc_percent": scenario.get("initial_soc_percent"),
        "battery_temperature_c": scenario.get("battery_temperature_c"),
        "gradient_percent": scenario.get("gradient_percent"),
        "road_surface": scenario.get("road_surface", "dry"),
        "obstacle_distance_m": scenario.get("obstacle_distance_m"),
        "obstacle_source": scenario.get("obstacle_source"),
        "duration_minutes": scenario.get("duration_minutes"),
    }
    if scenario.get("vehicle_parameters"):
        out["vehicle_parameters"] = scenario["vehicle_parameters"]
    return out


def _baseline_physics_for(scenario: dict):
    vehicle_dict = merge_vehicle_params(scenario.get("vehicle_parameters"))
    vehicle = _vehicle_from_dict(vehicle_dict)
    return compute_energy(
        EnergyInputs(
            speed_kmh=scenario["speed_kmh"],
            gradient_percent=scenario["gradient_percent"],
            duration_minutes=scenario["duration_minutes"],
        ),
        vehicle,
    )


def _explain_change(field: str, baseline: Any, comparison: Any) -> str:
    explanations = {
        "speed_kmh": "Speed affects aerodynamic drag (~v²) and wheel power in the steady-speed model.",
        "gradient_percent": "Road gradient changes grade resistance F_grade = m·g·sin(θ).",
        "duration_minutes": "Longer duration scales energy E = P_battery × time; distance scales with duration at constant speed.",
        "initial_soc_percent": "Initial SOC changes available energy but not tractive physics in this model.",
        "battery_temperature_c": "Temperature affects warning events only; not energy physics in this MVP.",
        "road_surface": "Road surface is recorded; energy effect is not_modelled in this MVP.",
        "obstacle_distance_m": "Obstacle distance affects proximity warnings only, not energy physics.",
    }
    if field in explanations:
        return explanations[field]
    if field.startswith("vehicle_parameters."):
        return "Vehicle parameter override changes force or power calculations in the physics engine."
    return "Input change may affect simulated energy demand or events under the implemented model."


def _why_results_changed(changed: List[dict]) -> List[dict]:
    return [
        {
            "input_field": c["field"],
            "baseline": c["baseline"],
            "comparison": c["comparison"],
            "model_explanation": _explain_change(c["field"], c["baseline"], c["comparison"]),
        }
        for c in changed
    ]


class ComparisonService:
    def __init__(self, simulation_service: SimulationService) -> None:
        self.simulation_service = simulation_service

    def compare(
        self,
        baseline_scenario: dict[str, Any],
        comparison_scenario: dict[str, Any],
        *,
        baseline_name: Optional[str] = None,
        comparison_name: Optional[str] = None,
    ) -> dict[str, Any]:
        baseline_result = self.simulation_service.run_simulation(baseline_scenario, store=True)
        base_physics = _baseline_physics_for(baseline_scenario)
        comparison_result = self.simulation_service.run_simulation(
            comparison_scenario,
            store=True,
            baseline_physics=base_physics,
            baseline_gradient=baseline_scenario["gradient_percent"],
        )

        bp = baseline_result["physics"]
        cp = comparison_result["physics"]
        bb = baseline_result["battery"]
        cb = comparison_result["battery"]

        abs_e = cp["requested_energy_kwh"] - bp["requested_energy_kwh"]
        abs_dist = cp["distance_km"] - bp["distance_km"]
        abs_soc = cb["final_soc_percent"] - bb["final_soc_percent"]

        abs_cons: Optional[float] = None
        cons_note: Optional[str] = None
        if bp["consumption_kwh_per_100km"] is not None and cp["consumption_kwh_per_100km"] is not None:
            abs_cons = cp["consumption_kwh_per_100km"] - bp["consumption_kwh_per_100km"]
        else:
            cons_note = "Consumption per 100 km unavailable for one or both scenarios."

        pct_e, pct_e_note = _pct_diff(bp["requested_energy_kwh"], cp["requested_energy_kwh"])
        pct_cons, pct_cons_note = _pct_diff(bp["consumption_kwh_per_100km"], cp["consumption_kwh_per_100km"])

        reduction_pct, reduction_note = _model_reduction_percent(
            bp["requested_energy_kwh"],
            cp["requested_energy_kwh"],
        )

        base_events = _event_signatures(baseline_result["events"])
        comp_events = _event_signatures(comparison_result["events"])
        only_baseline = base_events - comp_events
        only_comparison = comp_events - base_events

        observations: List[str] = []
        if abs_e > 0:
            observations.append(
                f"Comparison scenario requires {abs_e:.3f} kWh more requested energy under the implemented model."
            )
        elif abs_e < 0:
            observations.append(
                f"Comparison scenario requires {abs(abs_e):.3f} kWh less requested energy under the implemented model."
            )
        else:
            observations.append("Requested energy demand is identical between scenarios.")

        changed = _changed_inputs(_scenario_slice(baseline_scenario), _scenario_slice(comparison_scenario))
        if changed:
            observations.append("Input parameter differences are listed in changed_inputs and why_results_changed.")

        return {
            "baseline_name": baseline_name or baseline_scenario.get("scenario_name"),
            "comparison_name": comparison_name or comparison_scenario.get("scenario_name"),
            "baseline_inputs": _scenario_slice(baseline_scenario),
            "comparison_inputs": _scenario_slice(comparison_scenario),
            "baseline_result": baseline_result,
            "comparison_result": comparison_result,
            "metrics": {
                "absolute_energy_demand_kwh": abs_e,
                "absolute_consumption_kwh_per_100km": abs_cons,
                "consumption_difference_note": cons_note,
                "absolute_distance_km": abs_dist,
                "final_soc_difference_percent": abs_soc,
                "percent_energy_demand_difference": pct_e,
                "percent_energy_demand_note": pct_e_note,
                "percent_consumption_difference": pct_cons,
                "percent_consumption_note": pct_cons_note,
            },
            "sustainability": {
                "baseline_energy_demand_kwh": bp["requested_energy_kwh"],
                "comparison_energy_demand_kwh": cp["requested_energy_kwh"],
                "baseline_consumption_kwh_per_100km": bp["consumption_kwh_per_100km"],
                "comparison_consumption_kwh_per_100km": cp["consumption_kwh_per_100km"],
                "baseline_distance_km": bp["distance_km"],
                "comparison_distance_km": cp["distance_km"],
                "baseline_final_soc_percent": bb["final_soc_percent"],
                "comparison_final_soc_percent": cb["final_soc_percent"],
                "energy_difference_kwh": abs_e,
                "energy_difference_percent": pct_e,
                "energy_difference_note": pct_e_note,
                "estimated_model_energy_reduction_percent": reduction_pct,
                "estimated_model_energy_reduction_note": reduction_note,
            },
            "changed_inputs": changed,
            "event_differences": {
                "only_in_baseline": [list(x) for x in sorted(only_baseline)],
                "only_in_comparison": [list(x) for x in sorted(only_comparison)],
            },
            "observations": observations,
            "why_results_changed": _why_results_changed(changed),
        }
