"""Physics-based longitudinal energy model (steady speed or simulated drive cycle)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.services.traffic_profiles import SpeedTrace
from app.utils.units import (
    ensure_finite,
    gradient_percent_to_degrees,
    gradient_percent_to_radians,
    minutes_to_hours,
    speed_kmh_to_m_s,
)

J_PER_KWH = 3.6e6
STOPPED_SPEED_M_S = 0.1


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
    # Wheel-to-battery efficiency while regenerating (motor, inverter, charge losses) [-]
    regen_efficiency: float = 0.80
    # Maximum braking power the motor can recover at the wheels [kW]
    max_regen_power_kw: float = 50.0
    # Below this speed friction brakes do all the braking [km/h]
    regen_min_speed_kmh: float = 5.0
    # Effective-mass multiplier for rotating parts during acceleration [-]
    rotational_inertia_factor: float = 1.05


@dataclass(frozen=True)
class EnergyInputs:
    speed_kmh: float
    gradient_percent: float
    duration_minutes: float


@dataclass(frozen=True)
class DriveCycleStats:
    """Summary of a simulated speed trace (not measured data)."""

    average_speed_kmh: float
    max_speed_kmh: float
    stop_count: int
    idle_time_s: float
    max_acceleration_m_s2: float
    max_deceleration_m_s2: float
    rms_acceleration_m_s2: float
    time_step_s: float


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
    # "steady_state" or "drive_cycle_average" (forces distance-weighted, powers time-averaged)
    aggregation: str = "steady_state"
    traction_energy_kwh: float = 0.0
    regenerated_energy_kwh: float = 0.0
    friction_braking_energy_kwh: float = 0.0
    auxiliary_energy_kwh: float = 0.0
    peak_battery_power_kw: float = 0.0
    peak_regen_power_kw: float = 0.0
    cycle_stats: Optional[DriveCycleStats] = None
    # Net battery energy per time step [kWh] and step lengths [s], for SOC integration.
    energy_steps_kwh: tuple[float, ...] = field(default=(), repr=False)
    step_durations_s: tuple[float, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class _StepPower:
    f_rr: float
    f_drag: float
    f_grade: float
    f_inertia: float
    wheel_kw: float
    traction_kw: float  # battery-side propulsion power (>= 0)
    regen_kw: float  # battery-side recovered power (>= 0)
    friction_kw: float  # wheel braking power lost in friction brakes (>= 0)
    battery_kw: float  # net battery power, incl. auxiliary (negative = charging)


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
    if not (0 <= config.regen_efficiency <= 1):
        raise ValueError("regen_efficiency must be in [0, 1]")
    if config.max_regen_power_kw < 0:
        raise ValueError("max_regen_power_kw must be non-negative")
    if config.regen_min_speed_kmh < 0:
        raise ValueError("regen_min_speed_kmh must be non-negative")
    if config.rotational_inertia_factor < 1:
        raise ValueError("rotational_inertia_factor must be >= 1")


def _step_power(v_avg: float, accel: float, theta: float, vehicle: VehicleConfig) -> _StepPower:
    m = vehicle.mass_kg
    g = vehicle.gravity_m_s2
    f_rr = vehicle.rolling_resistance_coefficient * m * g * math.cos(theta)
    f_drag = 0.5 * vehicle.air_density_kg_m3 * vehicle.drag_coefficient * vehicle.frontal_area_m2 * v_avg**2
    f_grade = m * g * math.sin(theta)
    f_inertia = m * vehicle.rotational_inertia_factor * accel
    wheel_kw = (f_rr + f_drag + f_grade + f_inertia) * v_avg / 1000.0

    traction_kw = regen_kw = friction_kw = 0.0
    if wheel_kw > 0:
        traction_kw = wheel_kw / vehicle.drivetrain_efficiency
    elif wheel_kw < 0:
        braking_kw = -wheel_kw
        regen_wheel_kw = 0.0
        if v_avg * 3.6 >= vehicle.regen_min_speed_kmh:
            regen_wheel_kw = min(braking_kw, vehicle.max_regen_power_kw)
        regen_kw = regen_wheel_kw * vehicle.regen_efficiency
        friction_kw = braking_kw - regen_wheel_kw

    battery_kw = traction_kw - regen_kw + vehicle.auxiliary_power_kw
    return _StepPower(f_rr, f_drag, f_grade, f_inertia, wheel_kw, traction_kw, regen_kw, friction_kw, battery_kw)


def _consumption(energy_kwh: float, distance_km: float) -> tuple[Optional[float], Optional[str]]:
    if distance_km > 0:
        return ensure_finite(energy_kwh / distance_km * 100.0), None
    return None, "Simulated distance is zero; kWh/100 km is undefined."


def compute_energy(
    inputs: EnergyInputs,
    vehicle: VehicleConfig,
) -> EnergyOutputs:
    """
    Steady-speed energy demand (zero acceleration) from first-principles forces.

    When wheel power is negative (e.g. steep downhill) the motor regenerates up to
    max_regen_power_kw at regen_efficiency; the rest is dissipated by friction brakes.
    """
    validate_vehicle_config(vehicle)

    theta = gradient_percent_to_radians(inputs.gradient_percent)
    theta_deg = gradient_percent_to_degrees(inputs.gradient_percent)
    v = speed_kmh_to_m_s(inputs.speed_kmh)
    t_hours = minutes_to_hours(inputs.duration_minutes)

    p = _step_power(v, 0.0, theta, vehicle)
    e_demand_kwh = p.battery_kw * t_hours
    distance_km = inputs.speed_kmh * inputs.duration_minutes / 60.0
    consumption, consumption_reason = _consumption(e_demand_kwh, distance_km)

    return EnergyOutputs(
        road_angle_rad=ensure_finite(theta),
        road_angle_deg=ensure_finite(theta_deg),
        rolling_resistance_force_n=ensure_finite(p.f_rr),
        aerodynamic_drag_force_n=ensure_finite(p.f_drag),
        grade_resistance_force_n=ensure_finite(p.f_grade),
        tractive_force_n=ensure_finite(p.f_rr + p.f_drag + p.f_grade),
        longitudinal_acceleration_m_s2=0.0,
        wheel_power_kw=ensure_finite(p.wheel_kw),
        battery_power_kw=ensure_finite(p.battery_kw),
        requested_energy_kwh=ensure_finite(e_demand_kwh),
        distance_km=ensure_finite(distance_km),
        consumption_kwh_per_100km=consumption,
        consumption_unavailable_reason=consumption_reason,
        aggregation="steady_state",
        traction_energy_kwh=ensure_finite(p.traction_kw * t_hours),
        regenerated_energy_kwh=ensure_finite(p.regen_kw * t_hours),
        friction_braking_energy_kwh=ensure_finite(p.friction_kw * t_hours),
        auxiliary_energy_kwh=ensure_finite(vehicle.auxiliary_power_kw * t_hours),
        peak_battery_power_kw=ensure_finite(max(p.battery_kw, 0.0)),
        peak_regen_power_kw=ensure_finite(p.regen_kw),
        energy_steps_kwh=(e_demand_kwh,),
        step_durations_s=(inputs.duration_minutes * 60.0,),
    )


def compute_drive_cycle_energy(
    trace: SpeedTrace,
    gradient_percent: float,
    vehicle: VehicleConfig,
) -> EnergyOutputs:
    """
    Integrate energy over a simulated speed trace.

    Each step uses the mean speed and constant acceleration between its boundary
    speeds, so inertial work equals the exact change in kinetic energy. Reported
    forces are distance-weighted averages (work / distance) and powers are
    time averages, so force × distance and power × time stay consistent.
    """
    validate_vehicle_config(vehicle)
    if not trace.step_durations_s:
        return compute_energy(EnergyInputs(trace.target_speed_kmh, gradient_percent, 0.0), vehicle)

    theta = gradient_percent_to_radians(gradient_percent)
    theta_deg = gradient_percent_to_degrees(gradient_percent)

    w_rr = w_drag = w_grade = w_inertia = 0.0  # J
    e_wheel = e_trac = e_regen = e_fric = e_batt = 0.0  # kWh
    dist_m = 0.0
    total_s = 0.0
    peak_batt = peak_regen = 0.0
    max_acc = max_dec = 0.0
    sum_a2 = 0.0
    idle_s = 0.0
    stops = 0
    steps: list[float] = []

    speeds = trace.speeds_m_s
    for i, dt in enumerate(trace.step_durations_s):
        v0, v1 = speeds[i], speeds[i + 1]
        v_avg = 0.5 * (v0 + v1)
        a = (v1 - v0) / dt
        p = _step_power(v_avg, a, theta, vehicle)
        ds = v_avg * dt

        w_rr += p.f_rr * ds
        w_drag += p.f_drag * ds
        w_grade += p.f_grade * ds
        w_inertia += p.f_inertia * ds
        h = dt / 3600.0
        e_wheel += p.wheel_kw * h
        e_trac += p.traction_kw * h
        e_regen += p.regen_kw * h
        e_fric += p.friction_kw * h
        e_step = p.battery_kw * h
        e_batt += e_step
        steps.append(e_step)

        dist_m += ds
        total_s += dt
        peak_batt = max(peak_batt, p.battery_kw)
        peak_regen = max(peak_regen, p.regen_kw)
        max_acc = max(max_acc, a)
        max_dec = max(max_dec, -a)
        sum_a2 += a * a * dt
        if v0 <= STOPPED_SPEED_M_S and v1 <= STOPPED_SPEED_M_S:
            idle_s += dt
        if v0 > STOPPED_SPEED_M_S and v1 <= STOPPED_SPEED_M_S:
            stops += 1

    distance_km = dist_m / 1000.0
    if dist_m > 0:
        f_rr, f_drag, f_grade = w_rr / dist_m, w_drag / dist_m, w_grade / dist_m
        f_tractive = (w_rr + w_drag + w_grade + w_inertia) / dist_m
    else:
        standstill = _step_power(0.0, 0.0, theta, vehicle)
        f_rr, f_drag, f_grade = standstill.f_rr, 0.0, standstill.f_grade
        f_tractive = f_rr + f_grade

    consumption, consumption_reason = _consumption(e_batt, distance_km)
    total_h = total_s / 3600.0

    stats = DriveCycleStats(
        average_speed_kmh=ensure_finite(dist_m / total_s * 3.6),
        max_speed_kmh=ensure_finite(max(speeds) * 3.6),
        stop_count=stops,
        idle_time_s=ensure_finite(idle_s),
        max_acceleration_m_s2=ensure_finite(max_acc),
        max_deceleration_m_s2=ensure_finite(max_dec),
        rms_acceleration_m_s2=ensure_finite(math.sqrt(sum_a2 / total_s)),
        time_step_s=trace.step_durations_s[0],
    )

    return EnergyOutputs(
        road_angle_rad=ensure_finite(theta),
        road_angle_deg=ensure_finite(theta_deg),
        rolling_resistance_force_n=ensure_finite(f_rr),
        aerodynamic_drag_force_n=ensure_finite(f_drag),
        grade_resistance_force_n=ensure_finite(f_grade),
        tractive_force_n=ensure_finite(f_tractive),
        longitudinal_acceleration_m_s2=ensure_finite((speeds[-1] - speeds[0]) / total_s),
        wheel_power_kw=ensure_finite(e_wheel / total_h),
        battery_power_kw=ensure_finite(e_batt / total_h),
        requested_energy_kwh=ensure_finite(e_batt),
        distance_km=ensure_finite(distance_km),
        consumption_kwh_per_100km=consumption,
        consumption_unavailable_reason=consumption_reason,
        aggregation="drive_cycle_average",
        traction_energy_kwh=ensure_finite(e_trac),
        regenerated_energy_kwh=ensure_finite(e_regen),
        friction_braking_energy_kwh=ensure_finite(e_fric),
        auxiliary_energy_kwh=ensure_finite(vehicle.auxiliary_power_kw * total_h),
        peak_battery_power_kw=ensure_finite(peak_batt),
        peak_regen_power_kw=ensure_finite(peak_regen),
        cycle_stats=stats,
        energy_steps_kwh=tuple(steps),
        step_durations_s=trace.step_durations_s,
    )
