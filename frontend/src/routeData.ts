/**
 * Route data available to Path Planning. There is no routing service, so the only route
 * with geometry/elevation is the illustrative Mumbai ↔ Pune sample in sampleData.ts.
 * Everything here is pure (no DOM) so it can be unit-tested.
 */
import { ROUTE_SAMPLE } from './sampleData.ts';

export interface ElevationPoint { km: number; m: number }
export interface KnownRoute { start: string; end: string; distanceKm: number; elevation: ElevationPoint[]; reversed: boolean }
export interface RouteSegment { distanceKm: number; gradePct: number; clamped: boolean }

/** Gradient range the energy engines accept from the UI. */
export const MAX_GRADE_PCT = 8;

/** Locations that have route data (for the location inputs' suggestions). */
export const SUPPORTED_PLACES: string[] = [ROUTE_SAMPLE.start, ROUTE_SAMPLE.end];

/** "Mumbai, MH" / "mumbai" / " MUMBAI MH " → "mumbai". */
const placeKey = (s: string) => s.toLowerCase().replace(/[^a-z\s]/g, ' ').trim().split(/\s+/)[0] ?? '';

const SAMPLE_POINTS: ElevationPoint[] = ROUTE_SAMPLE.elevation.map(([km, m]) => ({ km, m }));

/** The sample route in either direction, or null if the start/end pair has no route data. */
export function findKnownRoute(start: string, end: string): KnownRoute | null {
  const s = placeKey(start), e = placeKey(end);
  const a = placeKey(ROUTE_SAMPLE.start), b = placeKey(ROUTE_SAMPLE.end);
  if (!s || !e || s === e) return null;
  const distanceKm = SAMPLE_POINTS.at(-1)!.km;
  if (s === a && e === b) {
    return { start: ROUTE_SAMPLE.start, end: ROUTE_SAMPLE.end, distanceKm, elevation: SAMPLE_POINTS, reversed: false };
  }
  if (s === b && e === a) {
    const reversed = SAMPLE_POINTS.map((p) => ({ km: distanceKm - p.km, m: p.m })).reverse();
    return { start: ROUTE_SAMPLE.end, end: ROUTE_SAMPLE.start, distanceKm, elevation: reversed, reversed: true };
  }
  return null;
}

/** Total climb along the profile (sum of positive elevation changes), metres. */
export function elevationGain(points: ElevationPoint[]): number {
  let gain = 0;
  for (let i = 1; i < points.length; i++) gain += Math.max(0, points[i].m - points[i - 1].m);
  return gain;
}

/**
 * Split a route into constant-gradient segments between elevation points. Without
 * elevation, the whole route is one flat segment. Gradients outside ±MAX_GRADE_PCT are
 * clamped (and flagged) because the engines are only driven within that range.
 */
export function routeSegments(route: KnownRoute, includeElevation: boolean): RouteSegment[] {
  if (!includeElevation) return [{ distanceKm: route.distanceKm, gradePct: 0, clamped: false }];
  const segs: RouteSegment[] = [];
  const pts = route.elevation;
  for (let i = 1; i < pts.length; i++) {
    const d = pts[i].km - pts[i - 1].km;
    if (d <= 0) continue;
    const raw = ((pts[i].m - pts[i - 1].m) / (d * 1000)) * 100;
    const grade = Math.max(-MAX_GRADE_PCT, Math.min(MAX_GRADE_PCT, raw));
    segs.push({ distanceKm: d, gradePct: grade, clamped: grade !== raw });
  }
  return segs;
}

/**
 * Where the battery runs out along cumulative segment energies, or null if it never does.
 * Linear within a segment. `segments` are [distanceKm, energyKwh] in driving order.
 */
export function depletionKm(availableKwh: number, segments: [number, number][]): number | null {
  let km = 0, used = 0;
  for (const [d, e] of segments) {
    if (e > 0 && used + e > availableKwh) return km + d * Math.max(0, (availableKwh - used) / e);
    km += d;
    used += e;
  }
  return null;
}
