"""PS-53 Phase 3 integration checks (road surface, battery boundaries, path planning)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import PATH_PLANNING_STATUS
from app.main import create_app
from app.services.battery_service import BatteryInputs, compute_battery_state


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize("surface", ["dry", "wet", "slippery"])
def test_all_road_surfaces_accepted(client, surface):
    r = client.post("/api/v1/simulate", json={"road_surface": surface, "duration_minutes": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["inputs"]["road_surface"] == surface
    assert body["physics"]["road_surface_energy_effect"] == "not_modelled"
    assert body["telemetry"]["road_surface"] == surface


def test_road_surface_does_not_change_energy(client):
    base = {"speed_kmh": 60, "gradient_percent": 0, "duration_minutes": 10}
    dry = client.post("/api/v1/simulate", json={**base, "road_surface": "dry"}).json()
    wet = client.post("/api/v1/simulate", json={**base, "road_surface": "wet"}).json()
    assert dry["physics"]["requested_energy_kwh"] == wet["physics"]["requested_energy_kwh"]


def test_obstacle_sources_preserved(client):
    user = client.post(
        "/api/v1/simulate",
        json={"obstacle_distance_m": 5, "obstacle_source": "user_input", "duration_minutes": 1},
    ).json()
    sim = client.post(
        "/api/v1/simulate",
        json={"obstacle_distance_m": 5, "obstacle_source": "simulated_scenario", "duration_minutes": 1},
    ).json()
    assert user["inputs"]["obstacle_source"] == "user_input"
    assert sim["inputs"]["obstacle_source"] == "simulated_scenario"


def test_path_planning_not_implemented(client):
    r = client.post("/api/v1/simulate", json={"path_planning": {}, "duration_minutes": 1})
    assert r.status_code == 200
    assert r.json()["path_planning_integration"]["status"] == PATH_PLANNING_STATUS


def test_battery_demand_below_available():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=75, usable_battery_capacity_kwh=40, requested_energy_kwh=5)
    )
    assert out.trip_completed_in_model is True
    assert out.energy_supplied_kwh == pytest.approx(5)
    assert out.requested_energy_kwh == pytest.approx(5)


def test_battery_zero_demand_zero_available():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=0, usable_battery_capacity_kwh=40, requested_energy_kwh=0)
    )
    assert out.available_energy_kwh == 0
    assert out.energy_supplied_kwh == 0
    assert out.requested_energy_kwh == 0
    assert not out.battery_depleted
    assert out.trip_completed_in_model is True


def test_battery_zero_available_positive_demand():
    out = compute_battery_state(
        BatteryInputs(initial_soc_percent=0, usable_battery_capacity_kwh=40, requested_energy_kwh=1)
    )
    assert out.energy_supplied_kwh == 0
    assert out.requested_energy_kwh == 1
    assert out.battery_depleted
    assert out.trip_completed_in_model is False


def test_simulation_battery_fields_consistent_on_depletion(client):
    r = client.post(
        "/api/v1/simulate",
        json={
            "initial_soc_percent": 1,
            "speed_kmh": 120,
            "duration_minutes": 120,
            "gradient_percent": 10,
        },
    )
    assert r.status_code == 200
    b = r.json()["battery"]
    assert b["requested_energy_kwh"] > b["energy_supplied_kwh"]
    assert b["trip_completed_in_model"] is False
    assert b["battery_depleted"] is True
    assert b["final_soc_percent"] == 0


def test_recovery_insufficient_correction_keeps_warning(client):
    warn = client.post(
        "/api/v1/simulate",
        json={"battery_temperature_c": 46, "duration_minutes": 5},
    )
    assert warn.json()["status"] == "WARNING"
    sim_id = warn.json()["simulation_id"]
    partial = client.post(
        "/api/v1/recover",
        json={
            "prior_simulation_id": sim_id,
            "corrected_scenario": {"battery_temperature_c": 46, "duration_minutes": 5},
        },
    )
    assert partial.status_code == 200
    assert partial.json()["recovery_status"] == "STILL_FAULT"
    assert partial.json()["recovery_in_progress"] is True
