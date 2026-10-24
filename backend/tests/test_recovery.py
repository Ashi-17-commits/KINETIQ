from fastapi.testclient import TestClient

from app.main import create_app


def test_recovery_requires_fault_or_warning():
    client = TestClient(create_app())
    ok = client.post("/api/v1/simulate", json={"speed_kmh": 60, "duration_minutes": 5})
    sim_id = ok.json()["simulation_id"]
    assert ok.json()["status"] == "COMPLETED"
    r = client.post(
        "/api/v1/recover",
        json={
            "prior_simulation_id": sim_id,
            "corrected_scenario": {"speed_kmh": 50, "duration_minutes": 5},
        },
    )
    assert r.status_code == 422


def test_recovery_after_temperature_fault():
    client = TestClient(create_app())
    fault = client.post(
        "/api/v1/simulate",
        json={"battery_temperature_c": 56, "duration_minutes": 5},
    )
    assert fault.json()["status"] == "FAULT"
    sim_id = fault.json()["simulation_id"]
    recovered = client.post(
        "/api/v1/recover",
        json={
            "prior_simulation_id": sim_id,
            "corrected_scenario": {"battery_temperature_c": 30, "duration_minutes": 5},
        },
    )
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["recovery_status"] == "RECOVERED"
    assert body["corrected_simulation"]["status"] == "COMPLETED"


def test_recovery_still_fault_if_condition_remains():
    client = TestClient(create_app())
    fault = client.post(
        "/api/v1/simulate",
        json={"battery_temperature_c": 56, "duration_minutes": 5},
    )
    sim_id = fault.json()["simulation_id"]
    still = client.post(
        "/api/v1/recover",
        json={
            "prior_simulation_id": sim_id,
            "corrected_scenario": {"battery_temperature_c": 56, "duration_minutes": 5},
        },
    )
    assert still.status_code == 200
    assert still.json()["recovery_status"] == "STILL_FAULT"
