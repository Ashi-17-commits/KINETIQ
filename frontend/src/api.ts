/**
 * Simulation client.
 *  - VITE_API_URL unset: the deterministic in-browser engine (src/engine.ts) runs.
 *  - VITE_API_URL set:   POST {VITE_API_URL}/api/v1/simulate (FastAPI backend, see
 *    backend/docs/FRONTEND_API.md). The request is mapped from the UI's Conditions and the
 *    SimulationResponse is mapped back into the UI's Result using only backend values.
 * API failures are surfaced as errors, never silently replaced with local numbers.
 */
import { simulate, recommend, DEFAULT_VEHICLE, type Conditions, type Result, type Recommendation, type Fault } from './engine.ts';

/** Which engine produced a result. Every value in one SimResponse comes from that engine only. */
export type ResultSource = 'api' | 'local' | 'local-fallback';
export interface SimVehicle { massKg: number; capacityKwh: number }
export interface SimResponse { result: Result; recommendations: Recommendation[]; source: ResultSource; vehicle: SimVehicle; fallbackReason?: string }
export type EngineSource = 'api' | 'local';

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');
export const ENGINE_SOURCE: EngineSource = API_URL ? 'api' : 'local';

export class SimError extends Error {}

/* ---------- Backend contract (subset of backend/app/api/schemas.py) ---------- */
interface ApiScenario {
  scenario_name?: string;
  speed_kmh: number;
  initial_soc_percent: number;
  battery_temperature_c: number;
  gradient_percent: number;
  road_surface: 'dry' | 'wet' | 'slippery';
  duration_minutes: number;
  traffic_profile: ApiTrafficProfile;
  vehicle_parameters?: { mass_kg?: number; auxiliary_power_kw?: number };
}
export type ApiTrafficProfile = 'steady' | 'free_flow' | 'moderate_congestion' | 'stop_and_go';
/** UI traffic choice → backend traffic_profile (backend traffic is always synthetic/simulated). */
export const TRAFFIC_TO_API: Record<Conditions['traffic'], ApiTrafficProfile> = {
  steady: 'steady', free: 'free_flow', moderate: 'moderate_congestion', heavy: 'stop_and_go',
};
/** Backend vehicle defaults (backend/app/core/config.py VehicleParameters). Payload and extra
 *  auxiliary load are sent as overrides on top of these; the response echo is checked. */
const BACKEND_BASE_MASS_KG = 1500;
const BACKEND_BASE_AUX_KW = 1.0;
/** Inputs the FastAPI physics model does not use; they only affect the in-browser engine. */
export const API_UNMODELLED_INPUTS = ['Driving style', 'Tyre pressure', 'Headwind', 'Climate control / ambient energy effect', 'Road surface energy effect'];
interface ApiTraffic {
  profile: ApiTrafficProfile; data_source: 'simulated'; is_real_world_data: false; description: string;
  average_speed_kmh: number; stop_count: number; idle_time_s: number; note: string;
}
interface ApiSimulation {
  simulation_id: string;
  status: string;
  vehicle_parameters: Record<string, number>;
  physics: {
    rolling_resistance_force_n: number; aerodynamic_drag_force_n: number; grade_resistance_force_n: number;
    wheel_power_kw: number; battery_power_kw: number; requested_energy_kwh: number; distance_km: number;
    consumption_kwh_per_100km: number | null; consumption_unavailable_reason: string | null;
    traction_energy_kwh?: number; regenerated_energy_kwh?: number; auxiliary_energy_kwh?: number;
    peak_battery_power_kw?: number;
  };
  battery: {
    initial_soc_percent: number; final_soc_percent: number; usable_battery_capacity_kwh: number;
    available_energy_kwh: number; requested_energy_kwh: number; battery_depleted: boolean;
    estimated_remaining_range_km?: number | null; remaining_range_note?: string | null;
    depletion_elapsed_minutes?: number | null;
  };
  traffic?: ApiTraffic | null;
  events: { event_id: string; event_type: string; severity: string; message: string; suggested_action: string }[];
  recommendations: { title: string; explanation: string; suggested_action: string }[];
}

/** Conditions → backend scenario. The backend models steady speed over a duration, so
 *  duration = distance / speed; pack temperature is taken as ambient; gravel/snow → slippery. */
export function toApiScenario(c: Conditions): ApiScenario {
  return {
    speed_kmh: c.cruiseKmh,
    initial_soc_percent: c.initialSocPct,
    battery_temperature_c: c.ambientC,
    gradient_percent: c.gradePct,
    road_surface: c.surface === 'dry' || c.surface === 'wet' ? c.surface : 'slippery',
    duration_minutes: Math.min(24 * 60, (c.distanceKm / Math.max(c.cruiseKmh, 1)) * 60),
    traffic_profile: TRAFFIC_TO_API[c.traffic] ?? 'steady',
    vehicle_parameters: {
      mass_kg: BACKEND_BASE_MASS_KG + Math.max(0, c.payloadKg),
      auxiliary_power_kw: BACKEND_BASE_AUX_KW + Math.max(0, c.auxExtraKw ?? 0),
    },
  };
}

const SEVERITY: Record<string, Fault['severity']> = { CRITICAL: 'critical', WARNING: 'warning', INFO: 'info' };
const J_PER_KWH = 3.6e6;

/** Backend SimulationResponse → UI Result. Quantities the backend does not model
 *  (regen, acceleration, pack I²R, stop-start trace) are reported as zero, not invented. */
export function fromApiSimulation(s: ApiSimulation, c: Conditions): Omit<SimResponse, 'source'> {
  const p = s.physics, b = s.battery;
  const sent = toApiScenario(c).vehicle_parameters!;
  if (s.vehicle_parameters.mass_kg !== sent.mass_kg || s.vehicle_parameters.auxiliary_power_kw !== sent.auxiliary_power_kw) {
    throw new SimError('Backend did not apply the payload / auxiliary-load overrides that were sent.');
  }
  if (p.consumption_kwh_per_100km == null || !Number.isFinite(p.consumption_kwh_per_100km)) {
    throw new SimError(`Backend could not compute consumption${p.consumption_unavailable_reason ? `: ${p.consumption_unavailable_reason}` : ''}.`);
  }
  const whPerKm = p.consumption_kwh_per_100km * 10;
  const distM = p.distance_km * 1000;
  // Backend forces are distance-weighted averages, so force × distance = work for both steady and traffic runs.
  const wheel = (f: number) => Math.max(0, f) * distM / J_PER_KWH;
  const durationMin = (c.distanceKm / Math.max(c.cruiseKmh, 1)) * 60;
  const auxKw = s.vehicle_parameters.auxiliary_power_kw ?? 0;
  const aux = p.auxiliary_energy_kwh ?? auxKw * durationMin / 60;
  const aero = wheel(p.aerodynamic_drag_force_n), rolling = wheel(p.rolling_resistance_force_n), grade = wheel(p.grade_resistance_force_n);
  const regen = p.regenerated_energy_kwh ?? 0;
  const eta = s.vehicle_parameters.drivetrain_efficiency ?? 1;
  let inertia = 0, driveLoss: number;
  if (p.traction_energy_kwh !== undefined) {
    // traction (battery side) = wheel work / η. Acceleration = wheel work not explained by road loads (residual, ≥ 0).
    driveLoss = p.traction_energy_kwh * (1 - eta);
    inertia = Math.max(0, p.traction_energy_kwh * eta - aero - rolling - grade);
  } else {
    driveLoss = Math.max(0, b.requested_energy_kwh - aero - rolling - grade - aux);
  }
  const capacity = b.usable_battery_capacity_kwh;
  const t = s.traffic ?? null;
  const avgKmh = t ? t.average_speed_kmh : c.cruiseKmh;
  const depletedAtKm = !b.battery_depleted ? null
    : b.depletion_elapsed_minutes != null && t?.profile === 'steady' ? (b.depletion_elapsed_minutes / 60) * c.cruiseKmh
    : whPerKm > 0 ? (b.available_energy_kwh * 1000) / whPerKm : null;
  const peakKw = p.peak_battery_power_kw ?? p.battery_power_kw;
  const trafficLabel = t
    ? `${t.profile.replace(/_/g, ' ')} (simulated, not live traffic) · avg ${avgKmh.toFixed(0)} km/h · ${t.stop_count} stops`
    : undefined;

  const result: Result = {
    inputs: { ...c },
    energyKwh: b.requested_energy_kwh,
    whPerKm,
    endSocPct: b.final_soc_percent,
    usableKwh: capacity,
    estRangeKm: whPerKm > 0 ? (capacity * 1000) / whPerKm : 0,
    durationMin,
    avgKmh,
    peakKw,
    peakCRate: capacity > 0 ? peakKw / capacity : 0,
    depletedAtKm,
    breakdownKwh: { aero, rolling, grade, inertia, aux, packLoss: 0, regen, driveLoss },
    // Backend returns trip totals only (no per-second SOC), so the chart shows start/end points.
    trace: [
      { km: 0, soc: b.initial_soc_percent, kmh: avgKmh, kw: p.battery_power_kw },
      ...(depletedAtKm !== null ? [{ km: depletedAtKm, soc: 0, kmh: avgKmh, kw: p.battery_power_kw }] : []),
      { km: p.distance_km, soc: b.final_soc_percent, kmh: avgKmh, kw: p.battery_power_kw },
    ],
    remainingRangeKm: b.estimated_remaining_range_km ?? null,
    remainingRangeNote: b.remaining_range_note ?? (b.estimated_remaining_range_km === undefined ? 'Backend did not report remaining range.' : undefined),
    trafficLabel,
    faults: s.events.map((e) => ({
      id: e.event_id, severity: SEVERITY[e.severity] ?? 'info',
      title: e.event_type.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (m) => m.toUpperCase()),
      detail: `${e.message} ${e.suggested_action}`.trim(),
    })),
  };
  const recommendations: Recommendation[] = s.recommendations.map((r) => ({
    title: r.title, detail: `${r.explanation} ${r.suggested_action}`.trim(), savingWhKm: NaN, savingPct: NaN,
  }));
  return { result, recommendations, vehicle: { massKg: s.vehicle_parameters.mass_kg, capacityKwh: capacity } };
}

function isApiSimulation(x: unknown): x is ApiSimulation {
  const s = x as ApiSimulation;
  return !!s && typeof s === 'object' && !!s.physics && !!s.battery && Array.isArray(s.events) && Array.isArray(s.recommendations) &&
    ['requested_energy_kwh', 'final_soc_percent', 'usable_battery_capacity_kwh', 'initial_soc_percent'].every((k) => Number.isFinite((s.battery as never)[k])) &&
    ['distance_km', 'battery_power_kw', 'aerodynamic_drag_force_n'].every((k) => Number.isFinite((s.physics as never)[k]));
}

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string })?.msg).filter(Boolean).join('; ');
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message);
  return '';
}

const LOCAL_TRAFFIC_LABEL: Record<Conditions['traffic'], string> = {
  steady: 'steady', free: 'free flow', moderate: 'moderate congestion', heavy: 'stop-and-go',
};

function runLocal(c: Conditions, source: ResultSource, fallbackReason?: string): SimResponse {
  const r = simulate(c);
  const remainingKwh = r.depletedAtKm !== null ? 0 : (r.usableKwh * r.endSocPct) / 100;
  const result: Result = {
    ...r,
    remainingRangeKm: r.whPerKm > 0 ? (remainingKwh * 1000) / r.whPerKm : null,
    remainingRangeNote: r.whPerKm > 0 ? "In-browser estimate at this trip's consumption." : 'Undefined: net consumption is not positive.',
    trafficLabel: `${LOCAL_TRAFFIC_LABEL[c.traffic]} (in-browser stop model, simulated) · avg ${r.avgKmh.toFixed(0)} km/h`,
  };
  return { result, recommendations: recommend(result), source, fallbackReason,
    vehicle: { massKg: DEFAULT_VEHICLE.massKg, capacityKwh: DEFAULT_VEHICLE.capacityKwh } };
}

/**
 * Backend first when VITE_API_URL is set. Only when the backend is unreachable (network
 * error, timeout, 502/503/504) does the local engine run, labelled 'local-fallback'.
 * Validation errors (4xx) and malformed responses are surfaced, never masked by a fallback.
 * `opts.source` pins a run to one engine (keeps baseline and current comparable).
 */
export async function runSimulation(c: Conditions, signal?: AbortSignal, opts: { source?: ResultSource } = {}): Promise<SimResponse> {
  if (!API_URL || opts.source === 'local') return runLocal(c, 'local');
  if (opts.source === 'local-fallback') return runLocal(c, 'local-fallback', 'Pinned to the fallback engine to match the current result.');
  try {
    return { ...(await fetchApi(c, signal)), source: 'api' };
  } catch (e) {
    if (e instanceof Unreachable && opts.source !== 'api') return runLocal(c, 'local-fallback', e.message);
    if (e instanceof Unreachable) throw new SimError(e.message);
    throw e;
  }
}

class Unreachable extends Error {}

async function fetchApi(c: Conditions, signal?: AbortSignal): Promise<Omit<SimResponse, 'source'>> {
  const timeout = AbortSignal.timeout(15000);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(toApiScenario(c)),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError' && signal?.aborted) throw e;
    throw new Unreachable(timeout.aborted ? 'The simulation service timed out.' : 'Cannot reach the simulation service.');
  }
  if ([502, 503, 504].includes(res.status)) throw new Unreachable(`Simulation service unavailable (${res.status}).`);
  if (!res.ok) {
    const detail = detailText(await res.json().then((j) => j?.detail, () => null));
    throw new SimError(`Simulation service error ${res.status}${detail ? `: ${detail}` : ''}.`);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!isApiSimulation(body)) throw new SimError('The simulation service returned an unexpected response.');
  return fromApiSimulation(body, c);
}

/* ---------- Path planning (requires backend) ----------
 * POST {VITE_API_URL}/api/route
 *   body:     RouteRequest
 *   response: RouteResponse  (elevation optional; omitted when not requested/available)
 * There is no client-side router: without VITE_API_URL, routing is reported as unavailable.
 */
export interface RouteRequest {
  start: string;
  end: string;
  routeType: 'fastest' | 'efficient' | 'scenic';
  includeElevation: boolean;
  avoidSteep: boolean;
  conditions: Conditions;
}
export interface RouteResponse {
  distanceKm: number;
  durationMin: number;
  energyKwh: number;
  socUsedPct: number;
  elevation?: { km: number; m: number }[];
}
// The backend reserves path_planning but exposes no routing endpoint yet (see /api/v1/config).
export const ROUTING_AVAILABLE = false;

export async function planRoute(req: RouteRequest, signal?: AbortSignal): Promise<RouteResponse> {
  if (!API_URL) throw new SimError('No routing service is connected.');
  const timeout = AbortSignal.timeout(20000);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError' && signal?.aborted) throw e;
    throw new SimError(timeout.aborted ? 'The routing service timed out.' : 'Cannot reach the routing service.');
  }
  if (!res.ok) {
    const detail = await res.json().then((j) => j?.detail, () => null);
    throw new SimError(`Routing service error ${res.status}${typeof detail === 'string' ? `: ${detail}` : ''}.`);
  }
  const b = (await res.json().catch(() => null)) as RouteResponse | null;
  const ok = !!b && ['distanceKm', 'durationMin', 'energyKwh', 'socUsedPct'].every((k) => Number.isFinite((b as never)[k])) &&
    (b.elevation === undefined || (Array.isArray(b.elevation) && b.elevation.every((p) => Number.isFinite(p.km) && Number.isFinite(p.m))));
  if (!ok) throw new SimError('The routing service returned an unexpected response.');
  return b!;
}
