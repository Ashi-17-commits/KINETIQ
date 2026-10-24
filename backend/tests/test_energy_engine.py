import math
from dataclasses import replace

import pytest

from app.services.energy_engine import EnergyInputs, VehicleConfig, compute_energy


@pytest.fixture
def vehicle() -> VehicleConfig:
    return VehicleConfig(
        mass_kg=1500.0,
        rolling_resistance_coefficient=0.01,
        drag_coefficient=0.28,
        frontal_area_m2=2.2,
        air_density_kg_m3=1.225,
        gravity_m_s2=9.81,
        drivetrain_efficiency=0.90,
        auxiliary_power_kw=1.0,
        usable_battery_capacity_kwh=40.0,
    )


def test_baseline_flat_road(vehicle):
    out = compute_energy(EnergyInputs(60, 0, 10), vehicle)
    assert out.grade_resistance_force_n == pytest.approx(0.0, abs=1e-6)
    assert out.rolling_resistance_force_n > 0
    assert out.aerodynamic_drag_force_n > 0
    assert out.wheel_power_kw > 0
    assert out.battery_power_kw > out.wheel_power_kw / vehicle.drivetrain_efficiency - 0.01
    assert out.distance_km == pytest.approx(10.0)
    assert out.consumption_kwh_per_100km is not None


def test_zero_speed_auxiliary_only(vehicle):
    out = compute_energy(EnergyInputs(0, 0, 10), vehicle)
    assert out.wheel_power_kw == pytest.approx(0.0)
    assert out.battery_power_kw == pytest.approx(vehicle.auxiliary_power_kw)
    assert out.requested_energy_kwh == pytest.approx(vehicle.auxiliary_power_kw * (10 / 60))
    assert out.distance_km == pytest.approx(0.0)
    assert out.consumption_kwh_per_100km is None


def test_positive_uphill_gradient(vehicle):
    flat = compute_energy(EnergyInputs(60, 0, 10), vehicle)
    uphill = compute_energy(EnergyInputs(60, 5, 10), vehicle)
    assert uphill.grade_resistance_force_n > 0
    assert uphill.tractive_force_n > flat.tractive_force_n
    assert uphill.requested_energy_kwh > flat.requested_energy_kwh


def test_negative_downhill_gradient(vehicle):
    downhill = compute_energy(EnergyInputs(60, -5, 10), vehicle)
    assert downhill.grade_resistance_force_n < 0
    flat = compute_energy(EnergyInputs(60, 0, 10), vehicle)
    assert downhill.tractive_force_n < flat.tractive_force_n


def test_speed_increases_drag_and_energy(vehicle):
    low = compute_energy(EnergyInputs(40, 0, 10), vehicle)
    high = compute_energy(EnergyInputs(80, 0, 10), vehicle)
    assert high.aerodynamic_drag_force_n > low.aerodynamic_drag_force_n
    assert high.requested_energy_kwh > low.requested_energy_kwh


def test_unit_conversions(vehicle):
    out = compute_energy(EnergyInputs(36, 0, 60), vehicle)
    v = 36 / 3.6
    f_drag = 0.5 * vehicle.air_density_kg_m3 * vehicle.drag_coefficient * vehicle.frontal_area_m2 * v**2
    assert out.aerodynamic_drag_force_n == pytest.approx(f_drag, rel=1e-6)


def test_negative_wheel_power_regenerates(vehicle):
    out = compute_energy(EnergyInputs(60, -15, 10), vehicle)
    assert out.wheel_power_kw < 0
    braking_kw = -out.wheel_power_kw
    regen_wheel_kw = min(braking_kw, vehicle.max_regen_power_kw)
    expected = -regen_wheel_kw * vehicle.regen_efficiency + vehicle.auxiliary_power_kw
    assert out.battery_power_kw == pytest.approx(expected)
    assert out.battery_power_kw < 0  # net charging on a steep descent
    assert out.regenerated_energy_kwh > 0
    assert out.friction_braking_energy_kwh == pytest.approx(max(0.0, braking_kw - regen_wheel_kw) / 6)


def test_regen_disabled_matches_previous_auxiliary_only_behaviour(vehicle):
    no_regen = replace(vehicle, max_regen_power_kw=0.0)
    out = compute_energy(EnergyInputs(60, -15, 10), no_regen)
    assert out.battery_power_kw == pytest.approx(vehicle.auxiliary_power_kw)
    assert out.regenerated_energy_kwh == 0


def test_regen_capped_by_max_power(vehicle):
    capped = replace(vehicle, max_regen_power_kw=5.0)
    out = compute_energy(EnergyInputs(60, -15, 10), capped)
    assert out.peak_regen_power_kw == pytest.approx(5.0 * vehicle.regen_efficiency)
    assert out.friction_braking_energy_kwh > 0


def test_steady_energy_breakdown_sums_to_net(vehicle):
    for grade in (-15, -2, 0, 5):
        out = compute_energy(EnergyInputs(60, grade, 10), vehicle)
        net = out.traction_energy_kwh - out.regenerated_energy_kwh + out.auxiliary_energy_kwh
        assert out.requested_energy_kwh == pytest.approx(net)


def test_energy_distance_consistency(vehicle):
    out = compute_energy(EnergyInputs(60, 0, 10), vehicle)
    assert out.requested_energy_kwh == pytest.approx(out.battery_power_kw * (10 / 60), rel=1e-9)
    assert out.distance_km == pytest.approx(60 * 10 / 60, rel=1e-9)
    assert out.consumption_kwh_per_100km == pytest.approx(
        out.requested_energy_kwh / out.distance_km * 100, rel=1e-9
    )


def test_zero_distance_consumption_unavailable(vehicle):
    out = compute_energy(EnergyInputs(0, 0, 10), vehicle)
    assert out.consumption_kwh_per_100km is None
    assert out.consumption_unavailable_reason


def test_finite_outputs(vehicle):
    out = compute_energy(EnergyInputs(60, 3, 10), vehicle)
    for field in out.__dataclass_fields__:
        val = getattr(out, field)
        if isinstance(val, float):
            assert math.isfinite(val)


def test_invalid_vehicle_mass():
    v = VehicleConfig(
        mass_kg=0,
        rolling_resistance_coefficient=0.01,
        drag_coefficient=0.28,
        frontal_area_m2=2.2,
        air_density_kg_m3=1.225,
        gravity_m_s2=9.81,
        drivetrain_efficiency=0.90,
        auxiliary_power_kw=1.0,
        usable_battery_capacity_kwh=40.0,
    )
    with pytest.raises(ValueError):
        compute_energy(EnergyInputs(60, 0, 10), v)
