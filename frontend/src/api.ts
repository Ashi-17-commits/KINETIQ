/**
 * Simulation client. With VITE_API_URL set, results come from the FastAPI backend
 * (POST {VITE_API_URL}/api/simulate → { result, recommendations }); otherwise the
 * deterministic in-browser engine runs. API failures are surfaced as errors, never
 * silently replaced with local numbers.
 */
import { simulate, recommend, type Conditions, type Result, type Recommendation } from './engine.ts';

export interface SimResponse { result: Result; recommendations: Recommendation[] }
export type EngineSource = 'api' | 'local';

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');
export const ENGINE_SOURCE: EngineSource = API_URL ? 'api' : 'local';

export class SimError extends Error {}

function isResponse(x: unknown): x is SimResponse {
  const r = (x as SimResponse)?.result;
  return !!r && Array.isArray((x as SimResponse).recommendations) &&
    ['energyKwh', 'whPerKm', 'endSocPct', 'estRangeKm', 'durationMin', 'avgKmh', 'peakKw'].every((k) => Number.isFinite((r as never)[k])) &&
    Array.isArray(r.trace) && Array.isArray(r.faults) && !!r.breakdownKwh;
}

export async function runSimulation(c: Conditions, signal?: AbortSignal): Promise<SimResponse> {
  if (!API_URL) {
    const result = simulate(c);
    return { result, recommendations: recommend(result) };
  }
  const timeout = AbortSignal.timeout(15000);
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(c),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError' && signal?.aborted) throw e;
    throw new SimError(timeout.aborted ? 'The simulation service timed out.' : 'Cannot reach the simulation service.');
  }
  if (!res.ok) {
    const detail = await res.json().then((j) => j?.detail, () => null);
    throw new SimError(`Simulation service error ${res.status}${typeof detail === 'string' ? `: ${detail}` : ''}.`);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!isResponse(body)) throw new SimError('The simulation service returned an unexpected response.');
  return body;
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
export const ROUTING_AVAILABLE = !!API_URL;

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
