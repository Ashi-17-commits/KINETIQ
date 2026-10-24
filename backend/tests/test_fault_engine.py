import pytest

from app.core.config import WarningThresholds
from app.models.simulation import EventSeverity, EventType
from app.services.fault_engine import classify_temperature, generate_events


@pytest.fixture
def thresholds():
    return WarningThresholds()


def test_temperature_below_warning(thresholds):
    assert classify_temperature(30, thresholds).value == "NORMAL"
    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=50,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    assert not any(e.event_type == EventType.BATTERY_TEMPERATURE for e in events)


def test_temperature_at_warning(thresholds):
    events = generate_events(
        battery_temperature_c=45,
        obstacle_distance_m=50,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    temp = [e for e in events if e.event_type == EventType.BATTERY_TEMPERATURE]
    assert len(temp) == 1
    assert temp[0].severity == EventSeverity.WARNING


def test_temperature_at_critical(thresholds):
    events = generate_events(
        battery_temperature_c=55,
        obstacle_distance_m=50,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    temp = [e for e in events if e.event_type == EventType.BATTERY_TEMPERATURE]
    assert len(temp) == 1
    assert temp[0].severity == EventSeverity.CRITICAL


def test_obstacle_below_threshold(thresholds):
    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=5,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    assert any(e.event_type == EventType.OBSTACLE_PROXIMITY for e in events)


def test_obstacle_at_threshold_not_triggered(thresholds):
    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=10,
        final_soc_percent=50,
        battery_depleted=False,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    assert not any(e.event_type == EventType.OBSTACLE_PROXIMITY for e in events)


def test_low_soc(thresholds):
    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=50,
        final_soc_percent=15,
        battery_depleted=False,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    assert any(e.event_type == EventType.LOW_BATTERY for e in events)


def test_battery_depletion(thresholds):
    events = generate_events(
        battery_temperature_c=30,
        obstacle_distance_m=50,
        final_soc_percent=0,
        battery_depleted=True,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    assert any(e.event_type == EventType.BATTERY_DEPLETION for e in events)


def test_multiple_simultaneous_events(thresholds):
    events = generate_events(
        battery_temperature_c=56,
        obstacle_distance_m=3,
        final_soc_percent=10,
        battery_depleted=True,
        thresholds=thresholds,
        elapsed_simulation_minutes=10,
    )
    types = {e.event_type for e in events}
    assert EventType.BATTERY_TEMPERATURE in types
    assert EventType.OBSTACLE_PROXIMITY in types
    assert EventType.LOW_BATTERY in types
    assert EventType.BATTERY_DEPLETION in types
