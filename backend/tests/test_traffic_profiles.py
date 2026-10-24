"""Simulated traffic profiles, drive-cycle physics, and SOC/range consistency."""

from dataclasses import replace

import pytest

from app.services.battery_service import BatteryInputs, compute_battery_state
from app.services.energy_engine import (
    EnergyInputs,
    VehicleConfig,
    compute_drive_cycle_energy,
    compute_energy,
)
from app.services.traffic_profiles import (
    FREE_FLOW,
    MODERATE_CONGESTION,
    STOP_AND_GO,
    TRAFFIC_PROFILES,
    SpeedTrace,
    generate_speed_trace,
)


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


# ---------- speed trace generation ----------

def test_trace_is_deterministic_per_seed():
    a = generate_speed_trace(STOP_AND_GO, 50, 10, seed=7)
    b = generate_speed_trace(STOP_AND_GO, 50, 10, seed=7)
    c = generate_speed_trace(STOP_AND_GO, 50, 10, seed=8)
    assert a.speeds_m_s == b.speeds_m_s
    assert a.speeds_m_s != c.speeds_m_s


@pytest.mark.parametrize("profile", list(TRAFFIC_PROFILES))
def test_trace_respects_acceleration_limits_and_duration(profile):
    spec = TRAFFIC_PROFILES[profile]
    trace = generate_speed_trace(profile, 80, 12.5, seed=3)
    assert sum(trace.step_durations_s) == pytest.approx(12.5 * 60)
    assert len(trace.speeds_m_s) == len(trace.step_durations_s) + 1
    for i, dt in enumerate(trace.step_durations_s):
        a = (trace.speeds_m_s[i + 1] - trace.speeds_m_s[i]) / dt
        assert a <= spec.max_acceleration_m_s2 + 1e-9
        assert -a <= spec.max_deceleration_m_s2 + 1e-9
    assert min(trace.speeds_m_s) >= 0


def test_profiles_order_by_average_speed(vehicle):
    avg = {}
    for profile in (FREE_FLOW, MODERATE_CONGESTION, STOP_AND_GO):
        out = compute_drive_cycle_energy(generate_speed_trace(profile, 90, 30), 0, vehicle)
        avg[profile] = out.cycle_stats.average_speed_kmh
    assert 0.9 * 90 < avg[FREE_FLOW] <= 90 * 1.03
    assert avg[FREE_FLOW] > avg[MODERATE_CONGESTION] > avg[STOP_AND_GO]


def test_stop_and_go_stops_and_is_speed_capped(vehicle):
    out = compute_drive_cycle_energy(generate_speed_trace(STOP_AND_GO, 120, 20), 0, vehicle)
    assert out.cycle_stats.stop_count >= 5
    assert out.cycle_stats.idle_time_s > 0
    assert out.cycle_stats.max_speed_kmh <= 40 + 1e-6


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        generate_speed_trace("rush_hour", 50, 10)


# ---------- drive-cycle physics ----------

def test_constant_speed_cycle_matches_steady_model(vehicle):
    v = 60 / 3.6
    trace = SpeedTrace("free_flow", 0, 60, tuple([v] * 601), tuple([1.0] * 600))
    cycle = compute_drive_cycle_energy(trace, 2, vehicle)
    steady = compute_energy(EnergyInputs(60, 2, 10), vehicle)
    assert cycle.requested_energy_kwh == pytest.approx(steady.requested_energy_kwh, rel=1e-9)
    assert cycle.distance_km == pytest.approx(steady.distance_km, rel=1e-9)
    assert cycle.aerodynamic_drag_force_n == pytest.approx(steady.aerodynamic_drag_force_n, rel=1e-9)


def test_inertial_work_equals_kinetic_energy_change(vehicle):
    # Ideal vehicle (no losses, no resistive forces): accelerate 0 -> 20 m/s then hold.
    ideal = replace(
        vehicle, rolling_resistance_coefficient=0, drag_coefficient=0, drivetrain_efficiency=1.0,
        auxiliary_power_kw=0, rotational_inertia_factor=1.0,
    )
    speeds = tuple([float(i) for i in range(21)] + [20.0] * 10)
    trace = SpeedTrace("free_flow", 0, 72, speeds, tuple([1.0] * (len(speeds) - 1)))
    out = compute_drive_cycle_energy(trace, 0, ideal)
    kinetic_kwh = 0.5 * ideal.mass_kg * 20.0**2 / 3.6e6
    assert out.requested_energy_kwh == pytest.approx(kinetic_kwh, rel=1e-9)


def test_braking_recovers_energy_with_regen(vehicle):
    speeds = tuple([20.0 - i for i in range(21)])  # 20 m/s -> 0 at 1 m/s²
    trace = SpeedTrace("stop_and_go", 0, 72, speeds, tuple([1.0] * 20))
    with_regen = compute_drive_cycle_energy(trace, 0, vehicle)
    without = compute_drive_cycle_energy(trace, 0, replace(vehicle, max_regen_power_kw=0))
    assert with_regen.regenerated_energy_kwh > 0
    assert with_regen.requested_energy_kwh < without.requested_energy_kwh
    # Regen can never return more than the kinetic energy available.
    kinetic_kwh = 0.5 * vehicle.mass_kg * vehicle.rotational_inertia_factor * 20.0**2 / 3.6e6
    assert with_regen.regenerated_energy_kwh < kinetic_kwh * vehicle.regen_efficiency


@pytest.mark.parametrize("profile", list(TRAFFIC_PROFILES))
@pytest.mark.parametrize("grade", [-6, 0, 4])
def test_cycle_energy_breakdown_is_consistent(vehicle, profile, grade):
    out = compute_drive_cycle_energy(generate_speed_trace(profile, 70, 15), grade, vehicle)
    net = out.traction_energy_kwh - out.regenerated_energy_kwh + out.auxiliary_energy_kwh
    assert out.requested_energy_kwh == pytest.approx(net, rel=1e-9, abs=1e-12)
    assert sum(out.energy_steps_kwh) == pytest.approx(out.requested_energy_kwh, rel=1e-9, abs=1e-12)
    assert out.battery_power_kw * 15 / 60 == pytest.approx(out.requested_energy_kwh, rel=1e-9, abs=1e-12)
    assert out.consumption_kwh_per_100km == pytest.approx(out.requested_energy_kwh / out.distance_km * 100)
    assert out.aggregation == "drive_cycle_average"


def test_stop_and_go_costs_more_per_km_at_city_speed(vehicle):
    steady = compute_energy(EnergyInputs(50, 0, 30), vehicle)
    sg = compute_drive_cycle_energy(generate_speed_trace(STOP_AND_GO, 50, 30), 0, vehicle)
    assert sg.consumption_kwh_per_100km > steady.consumption_kwh_per_100km


def test_congestion_reduces_drag_at_highway_speed(vehicle):
    steady = compute_energy(EnergyInputs(110, 0, 30), vehicle)
    mc = compute_drive_cycle_energy(generate_speed_trace(MODERATE_CONGESTION, 110, 30), 0, vehicle)
    assert mc.aerodynamic_drag_force_n < steady.aerodynamic_drag_force_n


# ---------- battery integration ----------

def test_mid_trip_depletion_detected_even_if_net_energy_fits():
    # 5 kWh available: draw 4, draw 3 (empties), then regen 3 -> net 4 kWh would "fit".
    out = compute_battery_state(
        BatteryInputs(
            initial_soc_percent=12.5, usable_battery_capacity_kwh=40, requested_energy_kwh=4,
            energy_steps_kwh=(4, 3, -3), step_durations_s=(60, 60, 60),
        )
    )
    assert out.battery_depleted
    assert out.final_soc_percent == 0
    assert out.depletion_elapsed_minutes == pytest.approx(1 + 1 / 3)


def test_regen_not_stored_above_full_battery():
    out = compute_battery_state(
        BatteryInputs(
            initial_soc_percent=99, usable_battery_capacity_kwh=40, requested_energy_kwh=-1.0,
            energy_steps_kwh=(-1.0,),
        )
    )
    assert out.final_soc_percent == 100
    assert out.regen_energy_not_stored_kwh == pytest.approx(0.6)
    assert out.energy_drawn_kwh == pytest.approx(-0.4)


# ---------- API ----------

@pytest.mark.parametrize("capacity", [40.0, 77.0])
@pytest.mark.parametrize("profile", ["steady", "free_flow", "moderate_congestion", "stop_and_go"])
def test_api_soc_energy_range_consistent_with_capacity(client, profile, capacity):
    r = client.post(
        "/api/v1/simulate",
        json={
            "speed_kmh": 70, "duration_minutes": 20, "initial_soc_percent": 80,
            "traffic_profile": profile, "vehicle_parameters": {"usable_battery_capacity_kwh": capacity},
        },
    )
    assert r.status_code == 200
    body = r.json()
    p, b = body["physics"], body["battery"]
    assert b["usable_battery_capacity_kwh"] == capacity
    assert b["available_energy_kwh"] == pytest.approx(capacity * 0.8)
    assert b["final_soc_percent"] == pytest.approx(80 - b["energy_drawn_kwh"] / capacity * 100)
    assert b["energy_drawn_kwh"] == pytest.approx(p["requested_energy_kwh"])
    assert b["remaining_energy_kwh"] == pytest.approx(capacity * b["final_soc_percent"] / 100)
    assert b["estimated_remaining_range_km"] == pytest.approx(
        b["remaining_energy_kwh"] / p["consumption_kwh_per_100km"] * 100
    )
    assert body["telemetry"]["estimated_remaining_range_km"] == b["estimated_remaining_range_km"]


@pytest.mark.parametrize("profile", ["steady", "stop_and_go"])
def test_api_traffic_is_labelled_simulated(client, profile):
    body = client.post("/api/v1/simulate", json={"traffic_profile": profile}).json()
    t = body["traffic"]
    assert t["profile"] == profile
    assert t["data_source"] == "simulated"
    assert t["is_real_world_data"] is False
    assert "not live traffic" in t["note"]
    assert body["telemetry"]["traffic_data_source"] == "simulated"
    assert body["inputs"]["traffic_profile"] == profile


def test_api_default_profile_is_steady_and_unchanged(client):
    default = client.post("/api/v1/simulate", json={"speed_kmh": 60, "duration_minutes": 10}).json()
    explicit = client.post(
        "/api/v1/simulate", json={"speed_kmh": 60, "duration_minutes": 10, "traffic_profile": "steady"}
    ).json()
    assert default["physics"]["aggregation"] == "steady_state"
    assert default["physics"]["requested_energy_kwh"] == explicit["physics"]["requested_energy_kwh"]
    assert default["physics"]["longitudinal_acceleration_m_s2"] == 0.0


def test_api_seed_reproducible(client):
    req = {"traffic_profile": "moderate_congestion", "traffic_seed": 11, "duration_minutes": 15}
    a = client.post("/api/v1/simulate", json=req).json()
    b = client.post("/api/v1/simulate", json=req).json()
    assert a["physics"]["requested_energy_kwh"] == b["physics"]["requested_energy_kwh"]
    assert a["traffic"]["seed"] == 11


@pytest.mark.parametrize("bad", [{"traffic_profile": "rush_hour"}, {"traffic_seed": -1}])
def test_api_rejects_invalid_traffic_inputs(client, bad):
    assert client.post("/api/v1/simulate", json=bad).status_code == 422


def test_compare_reports_traffic_change(client):
    r = client.post(
        "/api/v1/compare",
        json={
            "baseline": {"speed_kmh": 50, "duration_minutes": 20},
            "comparison": {"speed_kmh": 50, "duration_minutes": 20, "traffic_profile": "stop_and_go"},
        },
    )
    assert r.status_code == 200
    fields = {c["field"] for c in r.json()["changed_inputs"]}
    assert "traffic_profile" in fields
