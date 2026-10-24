"""Physics-based steady-speed energy consumption model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.utils.units import (
    ensure_finite,
    gradient_percent_to_degrees,
    gradient_percent_to_radians,
    minutes_to_hours,
    speed_kmh_to_m_s,
)


@dataclass(frozen=True)
class VehicleConfig:
    """Vehicle parameters for energy calculations."""

    mass_kg: float
    rolling_resistance_coefficient: float
    drag_coefficient: float
    frontal_area_m2: float
    air_density_kg_m3: float
    gravity_m_s2: float
    drivetrain_efficiency: float
    auxiliary_power_kw: float
    usable_battery_capacity_kwh: float


@dataclass(frozen=True)
class EnergyInputs:
    speed_kmh: float
    gradient_percent: float
    duration_minutes: float


@dataclass(frozen=True)
class EnergyOutputs:
    road_angle_rad: float
    road_angle_deg: float
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


def validate_vehicle_config(config: VehicleConfig) -> None:
    if config.mass_kg <= 0:
        raise ValueError("mass_kg must be positive")
    if config.rolling_resistance_coefficient < 0:
        raise ValueError("rolling_resistance_coefficient must be non-negative")
    if config.drag_coefficient < 0:
        raise ValueError("drag_coefficient must be non-negative")
    if config.frontal_area_m2 < 0:
        raise ValueError("frontal_area_m2 must be non-negative")
    if config.air_density_kg_m3 < 0:
        raise ValueError("air_density_kg_m3 must be non-negative")
    if not (0 < config.drivetrain_efficiency <= 1):
        raise ValueError("drivetrain_efficiency must be in (0, 1]")
    if config.auxiliary_power_kw < 0:
        raise ValueError("auxiliary_power_kw must be non-negative")
    if config.usable_battery_capacity_kwh <= 0:
        raise ValueError("usable_battery_capacity_kwh must be positive")


def compute_energy(
    inputs: EnergyInputs,
    vehicle: VehicleConfig,
) -> EnergyOutputs:
    """
    Compute steady-speed energy demand from first-principles forces.

    Regenerative braking is not modeled: when wheel power is <= 0, battery power
    equals auxiliary load only.
    """
    validate_vehicle_config(vehicle)

    theta = gradient_percent_to_radians(inputs.gradient_percent)
    theta_deg = gradient_percent_to_degrees(inputs.gradient_percent)
    v = speed_kmh_to_m_s(inputs.speed_kmh)
    t_hours = minutes_to_hours(inputs.duration_minutes)

    m = vehicle.mass_kg
    g = vehicle.gravity_m_s2
    c_rr = vehicle.rolling_resistance_coefficient

    f_rr = c_rr * m * g * math.cos(theta)
    f_drag = 0.5 * vehicle.air_density_kg_m3 * vehicle.drag_coefficient * vehicle.frontal_area_m2 * v**2
    f_grade = m * g * math.sin(theta)
    f_tractive = f_rr + f_drag + f_grade

    p_wheel_kw = f_tractive * v / 1000.0

    if p_wheel_kw > 0:
        p_battery_kw = p_wheel_kw / vehicle.drivetrain_efficiency + vehicle.auxiliary_power_kw
    else:
        p_battery_kw = vehicle.auxiliary_power_kw

    e_demand_kwh = p_battery_kw * t_hours
    distance_km = inputs.speed_kmh * inputs.duration_minutes / 60.0

    consumption: Optional[float] = None
    consumption_reason: Optional[str] = None
    if distance_km > 0:
        consumption = e_demand_kwh / distance_km * 100.0
    else:
        consumption_reason = "Simulated distance is zero; kWh/100 km is undefined."

    outputs = EnergyOutputs(
        road_angle_rad=ensure_finite(theta),
        road_angle_deg=ensure_finite(theta_deg),
        rolling_resistance_force_n=ensure_finite(f_rr),
        aerodynamic_drag_force_n=ensure_finite(f_drag),
        grade_resistance_force_n=ensure_finite(f_grade),
        tractive_force_n=ensure_finite(f_tractive),
        longitudinal_acceleration_m_s2=0.0,
        wheel_power_kw=ensure_finite(p_wheel_kw),
        battery_power_kw=ensure_finite(p_battery_kw),
        requested_energy_kwh=ensure_finite(e_demand_kwh),
        distance_km=ensure_finite(distance_km),
        consumption_kwh_per_100km=ensure_finite(consumption) if consumption is not None else None,
        consumption_unavailable_reason=consumption_reason,
    )
    return outputs
