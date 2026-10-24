import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["application_name"] == "KINETIQ"


def test_config(client):
    r = client.get("/api/v1/config")
    assert r.status_code == 200
    assert r.json()["default_vehicle_parameters"]["mass_kg"] == 1500


def test_presets(client):
    r = client.get("/api/v1/presets")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert "city" in ids and "wet_road_demo" in ids


def test_valid_simulation(client):
    r = client.post(
        "/api/v1/simulate",
        json={"scenario_name": "Test", "speed_kmh": 60, "duration_minutes": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["simulation_id"]
    assert body["physics"]["requested_energy_kwh"] > 0
    assert body["physics"]["road_surface_energy_effect"] == "not_modelled"
    assert body["telemetry"]["data_quality"] == "simulated"
    assert body["inputs"]["obstacle_distance_m"] is None
    assert body["battery"]["final_soc_percent"] < body["battery"]["initial_soc_percent"]
    assert body["recommendations"][0]["reason"]


def test_obstacle_requires_source(client):
    r = client.post(
        "/api/v1/simulate",
        json={"obstacle_distance_m": 5},
    )
    assert r.status_code == 422


def test_obstacle_with_user_input(client):
    r = client.post(
        "/api/v1/simulate",
        json={
            "obstacle_distance_m": 5,
            "obstacle_source": "user_input",
        },
    )
    assert r.status_code == 200
    assert any(e["event_type"] == "OBSTACLE_PROXIMITY" for e in r.json()["events"])


def test_compare_sustainability_block(client):
    r = client.post(
        "/api/v1/compare",
        json={
            "baseline": {"speed_kmh": 100, "duration_minutes": 10},
            "comparison": {"speed_kmh": 60, "duration_minutes": 10},
        },
    )
    assert r.status_code == 200
    s = r.json()["sustainability"]
    assert s["estimated_model_energy_reduction_note"]
    assert s["energy_difference_kwh"] != 0


def test_invalid_soc(client):
    r = client.post("/api/v1/simulate", json={"initial_soc_percent": 150})
    assert r.status_code == 422


def test_negative_speed_rejected(client):
    r = client.post("/api/v1/simulate", json={"speed_kmh": -1})
    assert r.status_code == 422


def test_invalid_duration(client):
    r = client.post("/api/v1/simulate", json={"duration_minutes": -5})
    assert r.status_code == 422


def test_malformed_json(client):
    r = client.post("/api/v1/simulate", content=b"not-json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_compare_endpoint(client):
    baseline = {"speed_kmh": 60, "gradient_percent": 0, "duration_minutes": 10}
    comparison = {"speed_kmh": 60, "gradient_percent": 5, "duration_minutes": 10}
    r = client.post("/api/v1/compare", json={"baseline": baseline, "comparison": comparison})
    assert r.status_code == 200
    metrics = r.json()["metrics"]
    assert metrics["absolute_energy_demand_kwh"] > 0


def test_zero_baseline_percentage_difference(client):
    zero = {"speed_kmh": 0, "duration_minutes": 0, "gradient_percent": 0}
    r = client.post("/api/v1/compare", json={"baseline": zero, "comparison": zero})
    assert r.status_code == 200
    note = r.json()["metrics"]["percent_energy_demand_note"]
    assert note is not None


def test_history_retrieval(client):
    r1 = client.post("/api/v1/simulate", json={"scenario_name": "H1"})
    sim_id = r1.json()["simulation_id"]
    r2 = client.get("/api/v1/history")
    assert r2.status_code == 200
    assert r2.json()["count"] >= 1
    r3 = client.get(f"/api/v1/history/{sim_id}")
    assert r3.status_code == 200
    assert r3.json()["simulation_id"] == sim_id


def test_missing_simulation_id(client):
    r = client.get("/api/v1/history/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_cors_headers(client):
    r = client.options(
        "/api/v1/simulate",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers
