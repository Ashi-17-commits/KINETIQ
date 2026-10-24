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

## Simulated traffic profiles (optional, additive)

Request fields (both optional; omitting them keeps the original steady-speed behaviour):

- `traffic_profile`: `"steady"` (default) | `"free_flow"` | `"moderate_congestion"` | `"stop_and_go"`.
  For non-steady profiles `speed_kmh` is the free-flow **target** speed; the backend generates a
  synthetic, acceleration-limited speed trace (1 s steps) and integrates energy over it.
- `traffic_seed`: integer ≥ 0 for a reproducible pattern (default seed 0).

**Traffic is always simulated.** `response.traffic.data_source` is `"simulated"` and
`is_real_world_data` is `false`. Never present it as live traffic.

New response fields (all optional in the schema):

- `traffic`: profile, seed, target/average/max speed, stop count, idle time, acceleration stats, note.
- `physics`: `aggregation` (`steady_state` | `drive_cycle_average`), `traction_energy_kwh`,
  `regenerated_energy_kwh`, `friction_braking_energy_kwh`, `auxiliary_energy_kwh`,
  `peak_battery_power_kw`, `peak_regen_power_kw`.
  For drive cycles, forces are distance-weighted averages and powers are time averages.
- `battery`: `remaining_energy_kwh`, `estimated_remaining_range_km`, `remaining_range_note`,
  `regen_energy_not_stored_kwh`, `depletion_elapsed_minutes`.

Behaviour change: regenerative braking is now modelled. On steep descents `requested_energy_kwh`
and `consumption_kwh_per_100km` can be **negative** (net charging); range is then `null` with a note.
Set `vehicle_parameters.max_regen_power_kw = 0` to reproduce the old no-regen result.
