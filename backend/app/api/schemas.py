"""Pydantic request and response models."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import InputBounds
from app.models.domain_types import ObstacleSource, RoadSurface


def _finite(v: float, name: str) -> float:
    if not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number")
    return v


class PathPlanningInput(BaseModel):
    """Optional stub for future path-planning integration (MVP: no routing executed)."""

    model_config = ConfigDict(extra="ignore")


class VehicleParametersOverride(BaseModel):
    mass_kg: Optional[float] = Field(None, description="Vehicle mass [kg]")
    rolling_resistance_coefficient: Optional[float] = Field(None, description="Rolling resistance coefficient [-]")
    drag_coefficient: Optional[float] = Field(None, description="Drag coefficient [-]")
    frontal_area_m2: Optional[float] = Field(None, description="Frontal area [m²]")
    air_density_kg_m3: Optional[float] = Field(None, description="Air density [kg/m³]")
    gravity_m_s2: Optional[float] = Field(None, description="Gravity [m/s²]")
    drivetrain_efficiency: Optional[float] = Field(None, description="Drivetrain efficiency [-]")
    auxiliary_power_kw: Optional[float] = Field(None, description="Auxiliary load [kW]")
    usable_battery_capacity_kwh: Optional[float] = Field(None, description="Usable battery capacity [kWh]")


class SimulationScenarioRequest(BaseModel):
    scenario_name: Optional[str] = None
    speed_kmh: float = Field(60.0, description="Vehicle speed [km/h]")
    initial_soc_percent: float = Field(75.0, description="Initial state of charge [%]")
    battery_temperature_c: float = Field(30.0, description="Battery temperature [°C]")
    gradient_percent: float = Field(0.0, description="Road gradient [%]")
    road_surface: RoadSurface = Field("dry", description="Road surface category (energy effect not_modelled in MVP)")
    obstacle_distance_m: Optional[float] = Field(
        None,
        description="User/simulated obstacle distance [m]; null if unavailable",
    )
    obstacle_source: Optional[ObstacleSource] = Field(
        None,
        description="Required when obstacle_distance_m is set",
    )
    duration_minutes: float = Field(10.0, description="Simulation duration [min]")
    vehicle_parameters: Optional[VehicleParametersOverride] = None
    path_planning: Optional[PathPlanningInput] = Field(
        None,
        description="Reserved; path planning not implemented",
    )

    @field_validator(
        "speed_kmh",
        "initial_soc_percent",
        "battery_temperature_c",
        "gradient_percent",
        "duration_minutes",
    )
    @classmethod
    def validate_finite_scalar(cls, v: float, info) -> float:
        return _finite(v, info.field_name)

    @field_validator("obstacle_distance_m")
    @classmethod
    def validate_obstacle_finite(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        return _finite(v, "obstacle_distance_m")

    @model_validator(mode="after")
    def validate_ranges_and_obstacle(self) -> "SimulationScenarioRequest":
        b = InputBounds()
        checks = [
            (self.speed_kmh, b.speed_kmh_min, b.speed_kmh_max, "speed_kmh"),
            (self.initial_soc_percent, b.initial_soc_percent_min, b.initial_soc_percent_max, "initial_soc_percent"),
            (
                self.battery_temperature_c,
                b.battery_temperature_c_min,
                b.battery_temperature_c_max,
                "battery_temperature_c",
            ),
            (self.gradient_percent, b.gradient_percent_min, b.gradient_percent_max, "gradient_percent"),
            (self.duration_minutes, b.duration_minutes_min, b.duration_minutes_max, "duration_minutes"),
        ]
        for value, lo, hi, name in checks:
            if value < lo or value > hi:
                raise ValueError(f"{name} must be between {lo} and {hi}")

        if self.obstacle_distance_m is not None:
            if self.obstacle_distance_m < b.obstacle_distance_m_min or self.obstacle_distance_m > b.obstacle_distance_m_max:
                raise ValueError(
                    f"obstacle_distance_m must be between {b.obstacle_distance_m_min} and {b.obstacle_distance_m_max}"
                )
            if not self.obstacle_source:
                raise ValueError("obstacle_source is required when obstacle_distance_m is provided")
        elif self.obstacle_source is not None:
            raise ValueError("obstacle_source must be null when obstacle_distance_m is not provided")

        return self

    def to_service_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        if self.vehicle_parameters:
            vp = self.vehicle_parameters.model_dump(exclude_none=True)
            data["vehicle_parameters"] = vp if vp else None
        if self.path_planning is not None:
            data["path_planning"] = {}
        return data


class CompareRequest(BaseModel):
    baseline: SimulationScenarioRequest
    comparison: SimulationScenarioRequest
    baseline_name: Optional[str] = None
    comparison_name: Optional[str] = None


class ValidateRequest(BaseModel):
    scenario: SimulationScenarioRequest


class RecoverRequest(BaseModel):
    prior_simulation_id: str
    corrected_scenario: SimulationScenarioRequest


class HealthResponse(BaseModel):
    status: str
    application_name: str
    backend_version: str


class ErrorResponse(BaseModel):
    detail: str | List[Any]


class ExecutionTraceSchema(BaseModel):
    previous_status: str
    terminal_status: str


class SimulationEventSchema(BaseModel):
    event_id: str
    event_type: str
    severity: str
    triggering_value: float
    threshold: Optional[float]
    unit: str
    message: str
    suggested_action: str
    elapsed_simulation_minutes: float


class RecommendationSchema(BaseModel):
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


class PhysicsResultSchema(BaseModel):
    road_angle_rad: float
    road_angle_deg: float
    road_surface_energy_effect: str
    rolling_resistance_force_n: float
    aerodynamic_drag_force_n: float
    grade_resistance_force_n: float
    tractive_force_n: float
    longitudinal_acceleration_m_s2: float
    wheel_power_kw: float
    battery_power_kw: float
    requested_energy_kwh: float
    distance_km: float
    consumption_kwh_per_100km: Optional[float]
    consumption_unavailable_reason: Optional[str]


class BatteryResultSchema(BaseModel):
    initial_soc_percent: float
    final_soc_percent: float
    usable_battery_capacity_kwh: float
    available_energy_kwh: float
    requested_energy_kwh: float
    energy_drawn_kwh: float
    energy_supplied_kwh: float
    battery_depleted: bool
    battery_state: str
    depletion_note: Optional[str]
    trip_completed_in_model: bool


class TelemetrySchema(BaseModel):
    data_quality: Literal["simulated"]
    speed_kmh: float
    battery_temperature_c: float
    initial_soc_percent: float
    final_soc_percent: float
    wheel_power_kw: float
    battery_power_kw: float
    requested_energy_kwh: float
    energy_supplied_kwh: float
    distance_km: float
    consumption_kwh_per_100km: Optional[float]
    gradient_percent: float
    road_surface: RoadSurface
    status: str


class PathPlanningIntegrationSchema(BaseModel):
    contract_version: str
    status: str
    obstacle_source: Optional[ObstacleSource]
    message: str


class SimulationResponse(BaseModel):
    simulation_id: str
    scenario_name: Optional[str]
    status: str
    execution_trace: ExecutionTraceSchema
    inputs: Dict[str, Any]
    vehicle_parameters: Dict[str, float]
    physics: PhysicsResultSchema
    battery: BatteryResultSchema
    telemetry: TelemetrySchema
    events: List[SimulationEventSchema]
    recommendations: List[RecommendationSchema]
    path_planning_integration: PathPlanningIntegrationSchema
    assumptions: List[str]
    limitations: List[str]
    units: Dict[str, str]


class ValidateResponse(BaseModel):
    valid: bool
    scenario: SimulationScenarioRequest
    messages: List[str]


class PresetSchema(BaseModel):
    id: str
    label: str
    description: str
    parameters: SimulationScenarioRequest


class RoadSurfaceModelSchema(BaseModel):
    energy_effect: str
    supported_values: List[str]
    limitations: List[str]


class StateMachineSchema(BaseModel):
    simulate_flow: List[str]
    recovery_flow: List[str]


class ConfigResponse(BaseModel):
    default_vehicle_parameters: Dict[str, float]
    default_scenario_inputs: Dict[str, Any]
    input_bounds: Dict[str, Any]
    warning_thresholds: Dict[str, float]
    road_surface_model: RoadSurfaceModelSchema
    state_machine: StateMachineSchema
    path_planning_integration: Dict[str, Any]
    units: Dict[str, str]
    model_assumptions: List[str]
    model_limitations: List[str]
    breaking_changes: List[str]


class HistoryListResponse(BaseModel):
    count: int
    simulations: List[SimulationResponse]


class RecoveryActionSchema(BaseModel):
    condition: str
    satisfied: bool
    required_input_guidance: str


class ActiveFaultSchema(BaseModel):
    event_type: str
    severity: str
    triggering_value: float
    threshold: Optional[float]
    unit: str


class RecoverResponse(BaseModel):
    prior_simulation_id: str
    prior_status: str
    recovery_status: str
    recovery_in_progress: bool
    corrected_simulation: SimulationResponse
    active_faults_before: List[ActiveFaultSchema]
    active_faults_after: List[ActiveFaultSchema]
    recovery_actions: List[RecoveryActionSchema]
    message: str


class WhyChangedSchema(BaseModel):
    input_field: str
    baseline: Any
    comparison: Any
    model_explanation: str


class SustainabilityMetricsSchema(BaseModel):
    baseline_energy_demand_kwh: float
    comparison_energy_demand_kwh: float
    baseline_consumption_kwh_per_100km: Optional[float]
    comparison_consumption_kwh_per_100km: Optional[float]
    baseline_distance_km: float
    comparison_distance_km: float
    baseline_final_soc_percent: float
    comparison_final_soc_percent: float
    energy_difference_kwh: float
    energy_difference_percent: Optional[float]
    energy_difference_note: Optional[str]
    estimated_model_energy_reduction_percent: Optional[float]
    estimated_model_energy_reduction_note: Optional[str]


class CompareMetricsSchema(BaseModel):
    absolute_energy_demand_kwh: float
    absolute_consumption_kwh_per_100km: Optional[float]
    consumption_difference_note: Optional[str]
    absolute_distance_km: float
    final_soc_difference_percent: float
    percent_energy_demand_difference: Optional[float]
    percent_energy_demand_note: Optional[str]
    percent_consumption_difference: Optional[float]
    percent_consumption_note: Optional[str]


class CompareResponse(BaseModel):
    baseline_name: Optional[str]
    comparison_name: Optional[str]
    baseline_inputs: Dict[str, Any]
    comparison_inputs: Dict[str, Any]
    baseline_result: SimulationResponse
    comparison_result: SimulationResponse
    metrics: CompareMetricsSchema
    sustainability: SustainabilityMetricsSchema
    changed_inputs: List[Dict[str, Any]]
    event_differences: Dict[str, List[List[str]]]
    observations: List[str]
    why_results_changed: List[WhyChangedSchema]
