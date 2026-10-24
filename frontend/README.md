# KINETIQ — EV Intelligence Simulator

A cinematic landing page and a working EV energy simulator, driven by a deterministic, physics-based engine.

## Run

```bash
npm install
npm run dev        # http://localhost:5173  (simulator at /simulator/)
npm test           # engine sanity checks (Node 22.6+)
npm run build      # type-check + production build → dist/
npm run preview    # serve dist/
```

## Stack and trade-off

The requested stack was React + TypeScript + Vite. This build uses **Vite + TypeScript without React**:

- **Kept:** TypeScript (typed engine, `tsc` in the build) and Vite (dev server, multi-page build, so `/simulator/` is a real route).
- **Dropped:** React. Two pages with local state don't need a component runtime. The result has zero runtime dependencies (~6 KB gzipped JS for the simulator).
- **Cost:** UI updates are manual DOM rendering in `src/simulator.ts`. If the app grows (more pages, shared state, many components), moving to React is straightforward because the engine (`src/engine.ts`) is UI-agnostic.

## Structure

```
index.html              Landing page (hero + Technology / Use Cases / About)
simulator/index.html    Simulator page
src/engine.ts           Physics engine, fault rules, recommendations (pure, deterministic)
src/engine.test.ts      Engine sanity tests
src/simulator.ts/.css   Simulator UI
src/landing.ts          Hero motion and interactions
src/styles.css          Shared design tokens, nav, buttons, hero
public/img/hero-vehicle.jpg       Vehicle plate cropped from the approved reference
design-references/kinetiq-final-hero.webp   Approved hero reference (source of truth)
```

## Engine model

The engine runs 1-second steps over a deterministic drive cycle: cruise segments separated by evenly spaced stops, whose count depends on traffic, with accelerations set by driving style.

- Road load: `F = m·a·1.05 + m·g·Crr·cosθ + m·g·sinθ + ½·ρ·Cd·A·(v+v_wind)²`. Air density comes from temperature.
- Rolling resistance scales with road surface (wet ×1.15, gravel ×1.6, snow ×2.2) and rises by +15 % per bar of under-inflation below 2.5 bar.
- Battery power = traction ÷ 0.90 drivetrain efficiency, minus regen × 0.65. Regen is capped at 70 kW and further limited when the pack is cold or above 90 % SOC.
- Auxiliary load is 0.3 kW plus HVAC. Heating and cooling loads scale with the gap from 21 °C.
- Pack: 75 kWh, 400 V, 80 mΩ, with I²R losses. Usable capacity drops 0.8 %/°C below 20 °C (floor 70 %).
- SOC = initial SOC − energy ÷ usable capacity.
- **Faults** are rules on the calculated result: depletion, arrival SOC below 10 % or 20 %, motor power limit, C-rate above 2, cold or hot pack, low tyre pressure, low-grip surface, restricted regen.
- **Recommendations** are counterfactual: each candidate change is re-simulated, and only changes that save at least 1 % are shown, with their measured saving.
- **Baseline vs current:** the baseline starts at the default scenario. "Set current as baseline" freezes the current result, and all KPI deltas and the SOC chart compare against it.

Every number, bar and chart line on `/simulator/` comes from `simulate()`. Nothing is mocked or random.

## Assumptions and limitations

- The reference vehicle parameters are generic, not those of any specific manufacturer. The output is an educational estimate, not a range guarantee.
- The drive cycle is synthetic and repeatable. It is not a WLTP/EPA cycle or a recorded route, and it uses one constant average grade.
- The model has no thermal dynamics: battery temperature equals ambient. There is no cell-level model, no SOC-dependent voltage, and no motor efficiency map (efficiency is constant).
- Energy figures for infeasible trips are the energy *required*, which can exceed what the pack holds.
- The hero vehicle image is cropped and inpainted from the 1942×809 approved reference, then upscaled 1.5×. Replace `public/img/hero-vehicle.jpg` with a high-resolution render of the same composition for production. Glint overlay positions in `src/styles.css` (`.glint-l`, `.glint-r`) are percentages of that image.
- Fonts (Playfair Display, Montserrat) load from Google Fonts. System serif and sans-serif fonts are the fallbacks.
- Motion respects `prefers-reduced-motion`.

## Car shader (Dither Veil)

`src/ditherVeil.ts` is a framework-free port of React Bits' [Dither Veil](https://www.reactbits.dev/animations/dither-veil). It keeps the upstream shaders and adds `revealTo`, `eventTarget`, `maxDpr` and `staticFrame`. It renders `hero-vehicle.jpg` as gold ordered dither. `public/img/hero-vehicle-mask.png` (a GrabCut alpha mask of the car) clips it to the car silhouette, and it is screen-blended so the original photo stays intact. A wandering window with a thin cyan rim lifts the dither as it drifts, and the pointer steers it.

- **Dependency:** adds `ogl` (~20 KB gzipped).
- **Reduced motion:** renders one static frame.
- **No WebGL2:** the layer is removed and the photo is shown unchanged.
- **Replacing the car image:** if you replace `hero-vehicle.jpg`, regenerate the mask to match.

## Backend integration (FastAPI)

`src/api.ts` is the only data path for the simulator page.

- **`VITE_API_URL` not set:** the deterministic in-browser engine runs.
- **`VITE_API_URL` set** (e.g. `VITE_API_URL=http://localhost:8000 npm run dev`): every run calls `POST {VITE_API_URL}/api/simulate`.
  - **Request body:** the `Conditions` JSON.
  - **Expected response:** `{ "result": Result, "recommendations": Recommendation[] }`, with the types defined in `src/engine.ts`.
  - **Failures:** network errors, timeouts (15 s), non-2xx responses and malformed bodies show an error banner with Retry. All gauges and results then display "—". The page never falls back to local numbers.

The CAD visual (`public/img/ev-cad.jpg`) is the supplied cutaway render with its baked-in transparency background replaced by navy. Its power-flow hotspots show calculated values (energy drawn, drivetrain losses, peak power, regen), not live telemetry.

### Path Planning tab (`/simulator/#route`)

The map (`public/images/route-map.png`) is a **static illustration**. The generated source image had a route summary, an elevation chart and zoom controls baked in; these were painted out so the map implies no route data.

- **With `VITE_API_URL` set:** "Plan Route" calls `POST /api/route`.
  - **Request body:** `{ start, end, routeType, includeElevation, avoidSteep, conditions }`.
  - **Expected response:** `{ distanceKm, durationMin, energyKwh, socUsedPct, elevation?: [{ km, m }] }`, with types in `src/api.ts`.
  - **Display:** the cards and the elevation chart show only these returned values.
- **Without a backend:** routing is reported as unavailable. Entering a known distance and average gradient runs the energy engine with the current Drive settings. The cards are labelled "From entered distance", and no path or elevation is calculated.
- **Out of scope:** obstacle detection.
