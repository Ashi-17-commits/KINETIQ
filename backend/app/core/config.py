"""Application and vehicle configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VehicleParameters:
    """Centralized vehicle model defaults (prototype assumptions, not certified specs)."""

    # Mass [kg]
    mass_kg: float = 1500.0
    # Rolling resistance coefficient [-]
    rolling_resistance_coefficient: float = 0.01
    # Aerodynamic drag coefficient [-]
    drag_coefficient: float = 0.28
    # Frontal area [m²]
    frontal_area_m2: float = 2.2
    # Air density [kg/m³]
    air_density_kg_m3: float = 1.225
    # Gravitational acceleration [m/s²]
    gravity_m_s2: float = 9.81
    # Drivetrain efficiency [-], (0, 1]
    drivetrain_efficiency: float = 0.90
    # Auxiliary electrical load [kW]
    auxiliary_power_kw: float = 1.0
    # Usable battery capacity [kWh]
    usable_battery_capacity_kwh: float = 40.0
    # Wheel-to-battery efficiency while regenerating [-], [0, 1]
    regen_efficiency: float = 0.80
    # Maximum recoverable braking power at the wheels [kW]
    max_regen_power_kw: float = 50.0
    # Speed below which friction brakes do all braking [km/h]
    regen_min_speed_kmh: float = 5.0
    # Effective-mass multiplier for rotating parts during acceleration [-], >= 1
    rotational_inertia_factor: float = 1.05


class WarningThresholds:
    """Configurable alert thresholds for simulation events."""

    # Battery temperature [°C]
    battery_temperature_warning_c: float = 45.0
    battery_temperature_critical_c: float = 55.0
    # Obstacle proximity [m]
    obstacle_proximity_warning_m: float = 10.0
    # Low state of charge [%]
    low_soc_warning_percent: float = 20.0


class InputBounds:
    """Documented supported input ranges for API validation."""

    speed_kmh_min: float = 0.0
    speed_kmh_max: float = 250.0
    initial_soc_percent_min: float = 0.0
    initial_soc_percent_max: float = 100.0
    battery_temperature_c_min: float = -40.0
    battery_temperature_c_max: float = 80.0
    gradient_percent_min: float = -30.0
    gradient_percent_max: float = 30.0
    obstacle_distance_m_min: float = 0.0
    obstacle_distance_m_max: float = 10_000.0
    duration_minutes_min: float = 0.0
    duration_minutes_max: float = 24 * 60.0


TRAFFIC_SEED_MAX = 2**31 - 1


APP_NAME = "KINETIQ"
API_VERSION = "1.0.0"
BACKEND_VERSION = "1.0.0"

MODEL_ASSUMPTIONS: List[str] = [
    "traffic_profile 'steady' (default): constant speed, zero acceleration, constant battery power.",
    "Other traffic profiles use a synthetic, seeded speed trace (1 s steps) with acceleration limits; "
    "this is simulated traffic, never live traffic or sensor data.",
    "Wheel force = rolling resistance + aerodynamic drag + grade + inertia (mass x rotational factor x acceleration).",
    "Regenerative braking recovers negative wheel power up to max_regen_power_kw at regen_efficiency "
    "above regen_min_speed_kmh; the remainder is lost to friction brakes.",
    "SOC is integrated per step: the trip stops if the battery empties, and regen is not stored above 100% SOC.",
    "Remaining range assumes the rest of the battery is used at this trip's simulated average consumption.",
    "Battery temperature does not modify energy consumption in this version.",
    "Obstacle proximity is a rule-based warning from user-supplied or scenario distance, not sensor detection.",
    "Road surface (dry/wet/slippery) is recorded for analysis; it does not change energy physics in this MVP.",
]

MODEL_LIMITATIONS: List[str] = [
    "Not a manufacturer-certified or homologation-grade simulator.",
    "Traffic profiles are illustrative synthetic patterns, not calibrated drive cycles (e.g. WLTP) or real traffic.",
    "Constant road gradient for the whole trip; no wind, HVAC detail, or motor efficiency maps.",
    "Distance and requested energy cover the full requested duration even if the battery depletes mid-trip.",
    "No database persistence; simulation history is in-memory only.",
    "Recommendations are deterministic rules, not ML or LLM output.",
    "Road surface does not affect rolling resistance or energy in this version (not_modelled).",
    "Path planning is not implemented; optional path_planning input is reserved for future integration.",
]

ROAD_SURFACE_ENERGY_EFFECT = "not_modelled"

PATH_PLANNING_STATUS = "not_implemented"

STATE_MACHINE_DOC = {
    "simulate_flow": ["READY", "RUNNING", "COMPLETED|WARNING|FAULT"],
    "recovery_flow": [
        "FAULT|WARNING",
        "RECOVERY_IN_PROGRESS",
        "RECOVERED|IMPROVED_TO_WARNING|STILL_FAULT",
    ],
}

PATH_PLANNING_INTEGRATION_DOC = {
    "contract_version": "1",
    "status": PATH_PLANNING_STATUS,
    "future_request_fields": [
        "path_planning.route_id",
        "path_planning.waypoints",
        "path_planning.virtual_obstacles",
    ],
    "obstacle_sources_supported": ["user_input", "simulated_scenario"],
    "message": "No path planner connected. Obstacle distance is never inferred from routing.",
}


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    history_max_entries: int = Field(default=100, alias="HISTORY_MAX_ENTRIES")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def default_vehicle_dict() -> dict:
    v = VehicleParameters()
    return {
        "mass_kg": v.mass_kg,
        "rolling_resistance_coefficient": v.rolling_resistance_coefficient,
        "drag_coefficient": v.drag_coefficient,
        "frontal_area_m2": v.frontal_area_m2,
        "air_density_kg_m3": v.air_density_kg_m3,
        "gravity_m_s2": v.gravity_m_s2,
        "drivetrain_efficiency": v.drivetrain_efficiency,
        "auxiliary_power_kw": v.auxiliary_power_kw,
        "usable_battery_capacity_kwh": v.usable_battery_capacity_kwh,
        "regen_efficiency": v.regen_efficiency,
        "max_regen_power_kw": v.max_regen_power_kw,
        "regen_min_speed_kmh": v.regen_min_speed_kmh,
        "rotational_inertia_factor": v.rotational_inertia_factor,
    }


def default_thresholds_dict() -> dict:
    t = WarningThresholds()
    return {
        "battery_temperature_warning_c": t.battery_temperature_warning_c,
        "battery_temperature_critical_c": t.battery_temperature_critical_c,
        "obstacle_proximity_warning_m": t.obstacle_proximity_warning_m,
        "low_soc_warning_percent": t.low_soc_warning_percent,
    }


def default_input_bounds_dict() -> dict:
    b = InputBounds()
    return {
        "speed_kmh": {"min": b.speed_kmh_min, "max": b.speed_kmh_max, "unit": "km/h"},
        "initial_soc_percent": {
            "min": b.initial_soc_percent_min,
            "max": b.initial_soc_percent_max,
            "unit": "%",
        },
        "battery_temperature_c": {
            "min": b.battery_temperature_c_min,
            "max": b.battery_temperature_c_max,
            "unit": "°C",
        },
        "gradient_percent": {
            "min": b.gradient_percent_min,
            "max": b.gradient_percent_max,
            "unit": "%",
        },
        "obstacle_distance_m": {
            "min": b.obstacle_distance_m_min,
            "max": b.obstacle_distance_m_max,
            "unit": "m",
        },
        "duration_minutes": {
            "min": b.duration_minutes_min,
            "max": b.duration_minutes_max,
            "unit": "min",
        },
        "road_surface": {
            "allowed": ["dry", "wet", "slippery"],
            "unit": "category",
        },
        "obstacle_distance_m": {
            "nullable": True,
            "note": "null means no simulated distance supplied; no proximity warning.",
        },
        "obstacle_source": {
            "allowed": ["user_input", "simulated_scenario"],
            "required_when": "obstacle_distance_m is set",
        },
        "traffic_profile": {
            "allowed": ["steady", "free_flow", "moderate_congestion", "stop_and_go"],
            "default": "steady",
            "data_source": "simulated",
            "note": "Synthetic speed pattern generated by the backend; not live traffic data.",
        },
        "traffic_seed": {
            "min": 0,
            "max": TRAFFIC_SEED_MAX,
            "nullable": True,
            "note": "Seed for the synthetic traffic pattern; null uses the default seed (0).",
        },
    }


def road_surface_model_dict() -> dict:
    return {
        "energy_effect": ROAD_SURFACE_ENERGY_EFFECT,
        "supported_values": ["dry", "wet", "slippery"],
        "limitations": [
            "Surface selection is stored on inputs and telemetry only.",
            "Energy physics use the base rolling-resistance coefficient unchanged.",
        ],
    }
