// Sanity checks for the energy engine. Run: npm test (Node 22.6+).
import assert from 'node:assert/strict';
import { simulate, recommend, DEFAULT_CONDITIONS as D } from './engine.ts';

const base = simulate(D);
const t = (name: string, fn: () => void) => { fn(); console.log(`✓ ${name}`); };

t('deterministic', () => assert.deepEqual(simulate(D), base));
t('plausible consumption (100–250 Wh/km)', () => assert.ok(base.whPerKm > 100 && base.whPerKm < 250, `${base.whPerKm}`));
t('distance matches request (±1%)', () => assert.ok(Math.abs(base.trace.at(-1)!.km - D.distanceKm) / D.distanceKm < 0.01));
t('SOC conserves energy', () => assert.ok(Math.abs(D.initialSocPct - base.endSocPct - (base.energyKwh / base.usableKwh) * 100) < 1e-6));
t('higher speed costs more', () => assert.ok(simulate({ ...D, cruiseKmh: 130 }).whPerKm > base.whPerKm));
t('cold costs more and shrinks capacity', () => {
  const c = simulate({ ...D, ambientC: -10 });
  assert.ok(c.whPerKm > base.whPerKm && c.usableKwh < base.usableKwh);
});
t('uphill costs more, downhill regenerates', () => {
  assert.ok(simulate({ ...D, gradePct: 5 }).whPerKm > base.whPerKm);
  assert.ok(simulate({ ...D, gradePct: -5 }).breakdownKwh.regen > base.breakdownKwh.regen);
});
t('low tyre pressure raises rolling loss and alerts', () => {
  const r = simulate({ ...D, tirePressureBar: 1.8 });
  assert.ok(r.breakdownKwh.rolling > base.breakdownKwh.rolling);
  assert.ok(r.faults.some((f) => f.id === 'tire'));
});
t('infeasible trip flagged critical', () => {
  const r = simulate({ ...D, distanceKm: 600, initialSocPct: 20 });
  assert.ok(r.depletedAtKm !== null && r.faults[0].severity === 'critical');
});
t('recommendations are real savings', () => {
  const recs = recommend(simulate({ ...D, cruiseKmh: 130, style: 'aggressive' }));
  assert.ok(recs.length > 0 && recs.every((r) => r.savingWhKm > 0));
});
console.log(`\nDefault scenario: ${base.whPerKm.toFixed(0)} Wh/km, ${base.energyKwh.toFixed(2)} kWh, arrival SOC ${base.endSocPct.toFixed(1)} %`);
