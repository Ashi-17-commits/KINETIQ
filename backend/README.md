# KINETIQ Backend — Intelligent EV Simulation API

Physics-based steady-speed EV energy simulation for the KINETIQ platform. This service estimates tractive forces, battery-side power, state-of-charge, deterministic warnings, and baseline-versus-comparison scenario analysis. It is a **prototype** model, not a certified automotive simulator.

## Overview

- **Stack:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn
- **Prefix:** `/api/v1`
- **Docs:** Swagger UI at `/docs` when the server is running
- **Persistence:** In-memory simulation history only (lost on restart)

## Architecture

| Module | Responsibility |
|--------|----------------|
| `app/main.py` | App factory, CORS, exception handlers |
| `app/api/routes.py` | REST endpoints |
| `app/api/schemas.py` | Request/response contracts |
| `app/core/config.py` | Defaults, bounds, thresholds, settings |
| `app/services/energy_engine.py` | Physics formulas |
| `app/services/battery_service.py` | SOC and energy draw |
| `app/services/fault_engine.py` | Temperature, obstacle, SOC, depletion events |
| `app/services/recommendation_engine.py` | Rule-based recommendations |
| `app/services/simulation_service.py` | Orchestration and history storage |
| `app/services/comparison_service.py` | Two-scenario comparison + sustainability KPIs |
| `app/services/recovery_service.py` | Corrected-scenario recovery evaluation |

## Prerequisites

- Python 3.11 or newer
- PowerShell (Windows) or any shell with `python` on PATH

## Setup (Windows PowerShell)

```powershell
cd C:\Users\HP\Desktop\KINETIQ\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Run the server

```powershell
cd C:\Users\HP\Desktop\KINETIQ\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Generic:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check: `GET http://127.0.0.1:8000/health`

## Environment variables

See `.env.example`:

- `APP_ENV` — `development` or production-style error masking
- `API_HOST`, `API_PORT` — bind settings (use with Uvicorn CLI)
- `CORS_ORIGINS` — comma-separated frontend origins
- `HISTORY_MAX_ENTRIES` — bounded in-memory history size

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness and version |
| GET | `/api/v1/config` | Defaults, bounds, thresholds, assumptions |
| GET | `/api/v1/presets` | Scenario presets (incl. wet-road record-only demo) |
| POST | `/api/v1/simulate` | Run simulation |
| POST | `/api/v1/compare` | Baseline vs comparison + sustainability block |
| POST | `/api/v1/recover` | Re-evaluate corrected scenario after FAULT/WARNING |
| POST | `/api/v1/validate` | Friendly validation preflight |
| GET | `/api/v1/history` | Recent simulations (in-memory) |
| GET | `/api/v1/history/{simulation_id}` | Single stored result |

### Example: simulate

```http
POST /api/v1/simulate
Content-Type: application/json

{
  "scenario_name": "Uphill Test",
  "speed_kmh": 60,
  "initial_soc_percent": 75,
  "battery_temperature_c": 30,
  "gradient_percent": 5,
  "road_surface": "dry",
  "obstacle_distance_m": null,
  "duration_minutes": 10
}
```

**Breaking change:** `obstacle_distance_m` defaults to `null`. When set, require `obstacle_source`: `user_input` or `simulated_scenario`. See `docs/FRONTEND_API.md`.

## Physics model and units

Steady speed, zero longitudinal acceleration.

| Quantity | Formula | Unit |
|----------|---------|------|
| Speed | `v = speed_kmh / 3.6` | m/s |
| Road angle | `theta = atan(gradient_percent / 100)` | rad (deg also returned) |
| Rolling resistance | `F_rr = C_rr * m * g * cos(theta)` | N |
| Aerodynamic drag | `F_drag = 0.5 * rho * C_d * A * v²` | N |
| Grade resistance | `F_grade = m * g * sin(theta)` | N |
| Tractive force | `F_tractive = F_rr + F_drag + F_grade` | N |
| Wheel power | `P_wheel = F_tractive * v / 1000` | kW |
| Battery power | If `P_wheel > 0`: `P_wheel / eta + P_aux`; else `P_aux` only | kW |
| Energy demand | `E = P_battery * duration_minutes / 60` | kWh |
| Distance | `distance_km = speed_kmh * duration_minutes / 60` | km |
| Consumption | `E / distance_km * 100` if distance > 0, else `null` | kWh/100 km |

**Assumption:** Regenerative braking is **not** modeled. Non-positive wheel power uses auxiliary load only.

## Default vehicle parameters

| Parameter | Default | Unit |
|-----------|---------|------|
| mass_kg | 1500 | kg |
| rolling_resistance_coefficient | 0.01 | - |
| drag_coefficient | 0.28 | - |
| frontal_area_m2 | 2.2 | m² |
| air_density_kg_m3 | 1.225 | kg/m³ |
| gravity_m_s2 | 9.81 | m/s² |
| drivetrain_efficiency | 0.90 | - |
| auxiliary_power_kw | 1.0 | kW |
| usable_battery_capacity_kwh | 40.0 | kWh |

Default scenario inputs: 60 km/h, 75% SOC, 30 °C, 0% gradient, `road_surface` dry, no obstacle distance, 10 min duration.

**Road surface (PS-53):** `dry` | `wet` | `slippery` is stored on inputs/telemetry. Energy physics are unchanged (`road_surface_energy_effect: not_modelled`).

## Battery conventions

- `available_energy_kwh = capacity * initial_soc / 100`
- `requested_energy_kwh` — model energy demand for the interval (physics engine)
- `energy_supplied_kwh` / `energy_drawn_kwh` — `min(requested, available)`; never equals full request when depleted
- `final_soc = initial_soc - energy_drawn / capacity * 100` (clamped 0–100)
- `trip_completed_in_model` — `false` when requested energy exceeds available energy; `true` when demand ≤ available (including exact equality)
- Depletion when requested energy exceeds available energy

## Fault thresholds (demonstration)

| Rule | Default |
|------|---------|
| Temperature warning | ≥ 45 °C |
| Temperature critical | ≥ 55 °C (precedence over warning) |
| Obstacle proximity | distance **<** 10 m (only if `obstacle_distance_m` supplied) |
| Low SOC | final SOC **<** 20% |
| Depletion | requested energy > available |

Simulation terminal states: **FAULT** (critical/depletion) > **WARNING** > **COMPLETED**. Use **POST /api/v1/recover** with corrected inputs; recovery succeeds only when triggering rules clear. Path planning status: **not_implemented**.

## Testing

```powershell
cd C:\Users\HP\Desktop\KINETIQ\backend
.\.venv\Scripts\Activate.ps1
pytest -v
```

## Frontend integration (React + TypeScript)

**No frontend app is in this repository.** Use **`docs/FRONTEND_API.md`** for TypeScript types, breaking changes, recovery flow, and sustainability fields.

**API base URL (local):** `http://127.0.0.1:8000` — configure CORS via `CORS_ORIGINS`.

Key UI rules:

- Do not show obstacle proximity when `obstacle_distance_m` is `null`.
- When the user enters a distance, send `obstacle_source`: `user_input` or `simulated_scenario` (presets use the latter).
- Show `road_surface` with a note that `road_surface_energy_effect` is `not_modelled`.
- Show `battery.requested_energy_kwh` vs `battery.energy_supplied_kwh` and `trip_completed_in_model`.
- Path planning: display `path_planning_integration.status` as `not_implemented`.

## Limitations

- No auth, database, ML, or external APIs
- No drive-cycle transients or regenerative braking
- Temperature affects warnings only, not energy consumption
- Obstacle rules are not collision or stopping-distance physics

## Future extensions

- **Drive cycles:** Replace constant-speed block with time-step integration over a speed profile array.
- **Regenerative braking:** For `P_wheel < 0`, add bounded recovery efficiency and cap by battery acceptance limits.
