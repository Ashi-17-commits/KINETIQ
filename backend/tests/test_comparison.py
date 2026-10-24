from app.services.comparison_service import ComparisonService
from app.services.history_store import HistoryStore
from app.services.simulation_service import SimulationService


def _scenario(**kwargs):
    base = {
        "speed_kmh": 60.0,
        "initial_soc_percent": 75.0,
        "battery_temperature_c": 30.0,
        "gradient_percent": 0.0,
        "obstacle_distance_m": None,
        "obstacle_source": None,
        "road_surface": "dry",
        "duration_minutes": 10.0,
    }
    base.update(kwargs)
    return base


def test_identical_inputs_same_physics():
    history = HistoryStore()
    svc = SimulationService(history)
    cmp_svc = ComparisonService(svc)
    s = _scenario()
    result = cmp_svc.compare(s, s)
    bp = result["baseline_result"]["physics"]
    cp = result["comparison_result"]["physics"]
    assert bp["requested_energy_kwh"] == cp["requested_energy_kwh"]
    assert result["metrics"]["absolute_energy_demand_kwh"] == 0
    assert result["metrics"]["percent_energy_demand_difference"] == 0


def test_gradient_change_increases_grade_force():
    history = HistoryStore()
    svc = SimulationService(history)
    cmp_svc = ComparisonService(svc)
    result = cmp_svc.compare(_scenario(gradient_percent=0), _scenario(gradient_percent=5))
    bg = result["baseline_result"]["physics"]["grade_resistance_force_n"]
    cg = result["comparison_result"]["physics"]["grade_resistance_force_n"]
    assert cg > bg
    assert result["metrics"]["absolute_energy_demand_kwh"] > 0
