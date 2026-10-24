"""Road driving presets (convenience input bundles, same physics model)."""

from app.api.schemas import PresetSchema, SimulationScenarioRequest

PRESETS: list[PresetSchema] = [
    PresetSchema(
        id="city",
        label="City",
        description=(
            "Lower steady speed, flat road — illustrative city driving (not stop-and-go). "
            "Obstacle distance is an explicit simulated_scenario input, not sensor data."
        ),
        parameters=SimulationScenarioRequest(
            scenario_name="City preset",
            speed_kmh=35.0,
            initial_soc_percent=75.0,
            battery_temperature_c=28.0,
            gradient_percent=0.0,
            road_surface="dry",
            obstacle_distance_m=25.0,
            obstacle_source="simulated_scenario",
            duration_minutes=15.0,
        ),
    ),
    PresetSchema(
        id="highway",
        label="Highway",
        description="Higher stable speed, flat road — illustrative highway cruise.",
        parameters=SimulationScenarioRequest(
            scenario_name="Highway preset",
            speed_kmh=100.0,
            initial_soc_percent=75.0,
            battery_temperature_c=32.0,
            gradient_percent=0.0,
            road_surface="dry",
            obstacle_distance_m=80.0,
            obstacle_source="simulated_scenario",
            duration_minutes=20.0,
        ),
    ),
    PresetSchema(
        id="uphill",
        label="Uphill",
        description="Positive gradient with moderate speed — illustrative uphill steady driving.",
        parameters=SimulationScenarioRequest(
            scenario_name="Uphill preset",
            speed_kmh=50.0,
            initial_soc_percent=75.0,
            battery_temperature_c=35.0,
            gradient_percent=6.0,
            road_surface="dry",
            obstacle_distance_m=40.0,
            obstacle_source="simulated_scenario",
            duration_minutes=12.0,
        ),
    ),
    PresetSchema(
        id="wet_road_demo",
        label="Wet road (record-only)",
        description="Wet surface label for PS-53 demos; energy physics unchanged (not_modelled).",
        parameters=SimulationScenarioRequest(
            scenario_name="Wet road demo",
            speed_kmh=60.0,
            road_surface="wet",
            obstacle_distance_m=None,
            obstacle_source=None,
            duration_minutes=10.0,
        ),
    ),
]
