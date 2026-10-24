import pytest

from app.models.simulation import BatteryState
from app.services.battery_service import BatteryInputs, compute_battery_state


def test_normal_consumption():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=75, usable_battery_capacity_kwh=40, requested_energy_kwh=2)
    )
    assert out.energy_drawn_kwh == 2
    assert out.final_soc_percent == pytest.approx(70.0)
    assert not out.battery_depleted


def test_minimum_soc():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=0, usable_battery_capacity_kwh=40, requested_energy_kwh=1)
    )
    assert out.available_energy_kwh == 0
    assert out.energy_drawn_kwh == 0
    assert out.final_soc_percent == 0


def test_maximum_soc():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=100, usable_battery_capacity_kwh=40, requested_energy_kwh=1)
    )
    assert out.available_energy_kwh == 40
    assert out.final_soc_percent == pytest.approx(97.5)


def test_demand_equals_available():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=50, usable_battery_capacity_kwh=40, requested_energy_kwh=20)
    )
    assert out.energy_drawn_kwh == pytest.approx(20)
    assert out.energy_supplied_kwh == pytest.approx(20)
    assert out.final_soc_percent == pytest.approx(0)
    assert not out.battery_depleted
    assert out.trip_completed_in_model is True


def test_demand_exceeds_available():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=50, usable_battery_capacity_kwh=40, requested_energy_kwh=25)
    )
    assert out.battery_depleted
    assert out.battery_state == BatteryState.DEPLETED
    assert out.energy_drawn_kwh == pytest.approx(20)
    assert out.energy_supplied_kwh == pytest.approx(20)
    assert out.requested_energy_kwh == pytest.approx(25)
    assert out.final_soc_percent == 0
    assert out.trip_completed_in_model is False


def test_final_soc_clamped():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=150, usable_battery_capacity_kwh=40, requested_energy_kwh=0)
    )
    assert out.initial_soc_percent == 100
    assert out.final_soc_percent == 100
