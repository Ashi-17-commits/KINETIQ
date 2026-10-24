from app.core.config import ROAD_SURFACE_ENERGY_EFFECT
from app.services.energy_engine import EnergyInputs, VehicleConfig, compute_energy


def test_road_surface_does_not_change_physics():
    vehicle = VehicleConfig(
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
    inputs = EnergyInputs(60, 0, 10)
    a = compute_energy(inputs, vehicle)
    b = compute_energy(inputs, vehicle)
    assert a.requested_energy_kwh == b.requested_energy_kwh
    assert ROAD_SURFACE_ENERGY_EFFECT == "not_modelled"


def test_obstacle_null_skips_proximity_event():
    from app.core.config import WarningThresholds
    from app.services.fault_engine import generate_events

    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=None,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=WarningThresholds(),
        elapsed_simulation_minutes=10,
    )
    assert not any(e.event_type.value == "OBSTACLE_PROXIMITY" for e in events)


def test_obstacle_simulated_below_threshold():
    from app.core.config import WarningThresholds
    from app.services.fault_engine import generate_events

    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=5,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=WarningThresholds(),
        elapsed_simulation_minutes=10,
    )
    assert any(e.event_type.value == "OBSTACLE_PROXIMITY" for e in events)
