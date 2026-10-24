# Frontend API mapping (PS-53)

No React app is in this repository yet. Use this guide when connecting a Vite frontend.

## Breaking changes (document in UI release notes)

1. **`obstacle_distance_m` default is `null`** — omit proximity warnings unless the user or a preset supplies a distance.
2. **`obstacle_source` required** when distance is set: `user_input` | `simulated_scenario`.
3. **Dashboard KPIs** — prefer `response.telemetry` over duplicating `physics` / `battery`.
4. **Recommendations** — include `reason`, `relevant_measurement_value`, `relevant_measurement_unit`, `evaluation_hint`.

## Base URL

`http://127.0.0.1:8000` or `import.meta.env.VITE_API_BASE_URL`

## TypeScript (sketch)

```typescript
export type RoadSurface = "dry" | "wet" | "slippery";
export type ObstacleSource = "user_input" | "simulated_scenario";

export interface SimulationRequest {
  scenario_name?: string;
  speed_kmh?: number;
  initial_soc_percent?: number;
  battery_temperature_c?: number;
  gradient_percent?: number;
  road_surface?: RoadSurface;
  obstacle_distance_m?: number | null;
  obstacle_source?: ObstacleSource | null;
  duration_minutes?: number;
  path_planning?: Record<string, never> | null;
}

export interface Telemetry {
  data_quality: "simulated";
  speed_kmh: number;
  road_surface: RoadSurface;
  requested_energy_kwh: number;
  energy_supplied_kwh: number;
  consumption_kwh_per_100km: number | null;
  status: string;
}

export interface SimulationResponse {
  simulation_id: string;
  status: string;
  telemetry: Telemetry;
  battery: {
    requested_energy_kwh: number;
    energy_supplied_kwh: number;
    trip_completed_in_model: boolean;
  };
  physics: {
    road_surface_energy_effect: "not_modelled";
  };
}
```

## Recovery flow

1. Run simulate → if `status` is `FAULT` or `WARNING`, show recovery panel.
2. User adjusts inputs (e.g. lower temperature).
3. `POST /api/v1/recover` with `prior_simulation_id` and `corrected_scenario`.
4. Display `recovery_status`; do not mark recovered locally without API response.

## Compare / sustainability

Use `sustainability.estimated_model_energy_reduction_percent` with the disclaimer from `estimated_model_energy_reduction_note`.
