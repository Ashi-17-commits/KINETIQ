"""API route handlers."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Request

from app.api.presets import PRESETS
from app.api.schemas import (
    CompareRequest,
    CompareResponse,
    ConfigResponse,
    HealthResponse,
    HistoryListResponse,
    PresetSchema,
    RecoverRequest,
    RecoverResponse,
    RoadSurfaceModelSchema,
    SimulationResponse,
    SimulationScenarioRequest,
    StateMachineSchema,
    ValidateRequest,
    ValidateResponse,
)
from app.core.config import (
    APP_NAME,
    BACKEND_VERSION,
    MODEL_ASSUMPTIONS,
    MODEL_LIMITATIONS,
    PATH_PLANNING_INTEGRATION_DOC,
    STATE_MACHINE_DOC,
    default_input_bounds_dict,
    default_thresholds_dict,
    default_vehicle_dict,
    road_surface_model_dict,
)
from app.services.comparison_service import ComparisonService
from app.services.energy_engine import VehicleConfig, validate_vehicle_config
from app.services.recovery_service import RecoveryService
from app.services.simulation_service import SimulationService, merge_vehicle_params, _vehicle_from_dict

router = APIRouter()

BREAKING_CHANGES = [
    "obstacle_distance_m default changed from 50 m to null (no proximity warning unless explicitly supplied).",
    "obstacle_source is required when obstacle_distance_m is set (user_input | simulated_scenario).",
    "Simulation responses include telemetry, execution_trace, path_planning_integration, and extended recommendations.",
]


def _get_sim_service(request: Request) -> SimulationService:
    return request.app.state.simulation_service


def _get_compare_service(request: Request) -> ComparisonService:
    return request.app.state.comparison_service


def _get_recovery_service(request: Request) -> RecoveryService:
    return request.app.state.recovery_service


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        application_name=APP_NAME,
        backend_version=BACKEND_VERSION,
    )


@router.get("/api/v1/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    rsm = road_surface_model_dict()
    return ConfigResponse(
        default_vehicle_parameters=default_vehicle_dict(),
        default_scenario_inputs={
            "speed_kmh": 60.0,
            "initial_soc_percent": 75.0,
            "battery_temperature_c": 30.0,
            "gradient_percent": 0.0,
            "road_surface": "dry",
            "obstacle_distance_m": None,
            "obstacle_source": None,
            "duration_minutes": 10.0,
            "traffic_profile": "steady",
            "traffic_seed": None,
        },
        input_bounds=default_input_bounds_dict(),
        warning_thresholds=default_thresholds_dict(),
        road_surface_model=RoadSurfaceModelSchema(**rsm),
        state_machine=StateMachineSchema(**STATE_MACHINE_DOC),
        path_planning_integration=PATH_PLANNING_INTEGRATION_DOC,
        units={
            "mass_kg": "kg",
            "rolling_resistance_coefficient": "-",
            "drag_coefficient": "-",
            "frontal_area_m2": "m²",
            "air_density_kg_m3": "kg/m³",
            "gravity_m_s2": "m/s²",
            "drivetrain_efficiency": "-",
            "auxiliary_power_kw": "kW",
            "usable_battery_capacity_kwh": "kWh",
            "regen_efficiency": "-",
            "max_regen_power_kw": "kW",
            "regen_min_speed_kmh": "km/h",
            "rotational_inertia_factor": "-",
            "traffic_profile": "category (simulated)",
            "speed_kmh": "km/h",
            "initial_soc_percent": "%",
            "battery_temperature_c": "°C",
            "gradient_percent": "%",
            "road_surface": "category",
            "obstacle_distance_m": "m",
            "duration_minutes": "min",
        },
        model_assumptions=list(MODEL_ASSUMPTIONS),
        model_limitations=list(MODEL_LIMITATIONS),
        breaking_changes=BREAKING_CHANGES,
    )


@router.get("/api/v1/presets", response_model=List[PresetSchema])
def list_presets() -> List[PresetSchema]:
    return PRESETS


@router.post("/api/v1/simulate", response_model=SimulationResponse)
def simulate(body: SimulationScenarioRequest, request: Request) -> SimulationResponse:
    _validate_vehicle_overrides(body)
    service = _get_sim_service(request)
    result = service.run_simulation(body.to_service_dict(), store=True)
    return SimulationResponse(**result)


@router.post("/api/v1/compare", response_model=CompareResponse)
def compare(body: CompareRequest, request: Request) -> CompareResponse:
    _validate_vehicle_overrides(body.baseline)
    _validate_vehicle_overrides(body.comparison)
    service = _get_compare_service(request)
    return CompareResponse(
        **service.compare(
            body.baseline.to_service_dict(),
            body.comparison.to_service_dict(),
            baseline_name=body.baseline_name,
            comparison_name=body.comparison_name,
        )
    )


@router.post("/api/v1/validate", response_model=ValidateResponse)
def validate_scenario(body: ValidateRequest) -> ValidateResponse:
    messages: list[str] = []
    try:
        _validate_vehicle_overrides(body.scenario)
        messages.append("Scenario inputs pass Pydantic validation.")
        messages.append("Vehicle overrides satisfy configuration constraints.")
        if body.scenario.obstacle_distance_m is None:
            messages.append("No obstacle distance supplied; proximity warning will not be generated.")
        if body.scenario.road_surface != "dry":
            messages.append("Road surface is recorded; energy effect is not_modelled in this MVP.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ValidateResponse(valid=True, scenario=body.scenario, messages=messages)


@router.post("/api/v1/recover", response_model=RecoverResponse)
def recover(body: RecoverRequest, request: Request) -> RecoverResponse:
    _validate_vehicle_overrides(body.corrected_scenario)
    service = _get_recovery_service(request)
    outcome = service.recover(body.prior_simulation_id, body.corrected_scenario.to_service_dict())
    if outcome.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Simulation not found")
    if outcome.get("error") == "invalid_prior_state":
        raise HTTPException(
            status_code=422,
            detail={
                "message": outcome["detail"],
                "prior_status": outcome["prior_status"],
            },
        )
    return RecoverResponse(**outcome)


@router.get("/api/v1/history", response_model=HistoryListResponse)
def history(request: Request) -> HistoryListResponse:
    service = _get_sim_service(request)
    items = service.history.list_recent()
    simulations = [SimulationResponse(**item) for item in items]
    return HistoryListResponse(count=len(simulations), simulations=simulations)


@router.get("/api/v1/history/{simulation_id}", response_model=SimulationResponse)
def history_by_id(simulation_id: str, request: Request) -> SimulationResponse:
    service = _get_sim_service(request)
    record = service.history.get(simulation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return SimulationResponse(**record)


def _validate_vehicle_overrides(scenario: SimulationScenarioRequest) -> None:
    if not scenario.vehicle_parameters:
        return
    merged = merge_vehicle_params(scenario.vehicle_parameters.model_dump(exclude_none=True))
    vehicle = _vehicle_from_dict(merged)
    validate_vehicle_config(vehicle)
