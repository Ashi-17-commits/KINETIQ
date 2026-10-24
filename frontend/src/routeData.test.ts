// Checks for Path Planning route data helpers. Run: npm test (Node 22.6+).
import assert from 'node:assert/strict';
import { findKnownRoute, elevationGain, routeSegments, depletionKm, MAX_GRADE_PCT } from './routeData.ts';

const t = (name: string, fn: () => void) => { fn(); console.log(`✓ ${name}`); };

const fwd = findKnownRoute('Mumbai, MH', 'Pune, MH')!;
const rev = findKnownRoute('pune', ' MUMBAI ')!;

t('sample route matches in both directions, case-insensitively', () => {
  assert.ok(fwd && !fwd.reversed && rev && rev.reversed);
  assert.equal(rev.start, 'Pune, MH');
});
t('unsupported or identical locations have no route data', () => {
  assert.equal(findKnownRoute('Delhi', 'Agra'), null);
  assert.equal(findKnownRoute('Mumbai', 'Mumbai'), null);
  assert.equal(findKnownRoute('', 'Pune'), null);
});
t('elevation gain is derived from the profile (720 m forward)', () => assert.equal(elevationGain(fwd.elevation), 720));
t('reverse gain equals forward descent', () => {
  const net = fwd.elevation.at(-1)!.m - fwd.elevation[0].m;
  assert.equal(elevationGain(rev.elevation), elevationGain(fwd.elevation) - net);
});
t('segments cover the whole distance and reproduce the net climb', () => {
  for (const r of [fwd, rev]) {
    const segs = routeSegments(r, true);
    assert.ok(Math.abs(segs.reduce((a, s) => a + s.distanceKm, 0) - r.distanceKm) < 1e-9);
    assert.ok(segs.every((s) => Math.abs(s.gradePct) <= MAX_GRADE_PCT && !s.clamped));
    const climbM = segs.reduce((a, s) => a + (s.gradePct / 100) * s.distanceKm * 1000, 0);
    assert.ok(Math.abs(climbM - (r.elevation.at(-1)!.m - r.elevation[0].m)) < 1e-6);
  }
});
t('excluding elevation gives one flat segment', () => {
  assert.deepEqual(routeSegments(fwd, false), [{ distanceKm: fwd.distanceKm, gradePct: 0, clamped: false }]);
});
t('depletion point is found along cumulative energy', () => {
  assert.equal(depletionKm(10, [[50, 4], [50, 4]]), null);
  assert.equal(depletionKm(6, [[50, 4], [50, 4]]), 75);
  assert.equal(depletionKm(5, [[50, 6], [50, -3]]), 50 * (5 / 6)); // empties before the downhill helps
});
