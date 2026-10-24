import './styles.css';
import './simulator.css';
import './pages.css';
import { renderSidebar, SAMPLE_BADGE, icon } from './shell.ts';
import { barChart } from './charts.ts';
import { SCENARIOS, type ScenarioSample } from './sampleData.ts';

renderSidebar('scenarios');
document.getElementById('badge')!.innerHTML = SAMPLE_BADGE;

const [A, B] = SCENARIOS;
const pct = (a: number, b: number) => ((b - a) / a) * 100;
const hm = (m: number) => `${Math.floor(m / 60)} h ${m % 60} min`;
const signed = (v: number) => `${v > 0 ? '↑ +' : '↓ −'}${Math.abs(v).toFixed(0)}%`;

function card(s: ScenarioSample, accent: string) {
  return `<section class="panel scen" style="--accent:${accent}" aria-label="${s.name}">
    <header class="scen-head"><div><h2>${s.name}</h2><p>${s.tag}</p></div><a class="btn btn-ghost btn-xs" href="/simulator/">✎ Edit</a></header>
    <div class="scen-car"><img src="/img/hero-vehicle.jpg" alt="" loading="lazy" /><div><b>${s.vehicle}</b><span>${s.battery}</span></div></div>
    <dl class="scen-rows">
      <dt>Vehicle Load</dt><dd>${s.load}</dd><dt>Driving Style</dt><dd>${s.style}</dd>
      <dt>AC Usage</dt><dd>${s.ac}</dd><dt>Route</dt><dd>${s.route}</dd>
    </dl></section>`;
}
document.getElementById('card-a')!.outerHTML = card(A, '#7c8cf0');
document.getElementById('card-b')!.outerHTML = card(B, 'var(--cyan)');

const dE = pct(A.energyKwh, B.energyKwh), dR = pct(A.rangeKm, B.rangeKm);
const diffs = [
  { ic: 'car', l: 'Driving Style', v: `${A.style} → ${B.style}`, c: '' },
  { ic: 'snow', l: 'AC Usage', v: 'Moderate → Low', c: '' },
  { ic: 'battery', l: 'Estimated Energy', v: signed(dE), c: dE < 0 ? 'good' : 'bad' },
  { ic: 'leaf', l: 'Estimated Range', v: signed(dR), c: dR > 0 ? 'good' : 'bad' },
];
document.getElementById('diffs')!.innerHTML = diffs.map((d) => `<li><span class="d-ic">${icon(d.ic)}</span><div><span>${d.l}</span><b class="${d.c}">${d.v}</b></div></li>`).join('');

const METRICS = {
  energy: { key: 'energyKwh', unit: 'kWh', title: 'Energy consumption by scenario', better: -1 },
  range: { key: 'rangeKm', unit: 'km', title: 'Estimated range by scenario', better: 1 },
  time: { key: 'travelMin', unit: 'min', title: 'Travel time by scenario', better: -1 },
} as const;
type MetricKey = keyof typeof METRICS;

function drawChart(m: MetricKey) {
  const { key, unit, title, better } = METRICS[m];
  const delta = pct(A[key], B[key]);
  document.getElementById('cmp-chart')!.innerHTML =
    `<p class="cmp-delta ${delta * better > 0 ? 'good' : 'bad'}">Scenario B vs A: ${delta > 0 ? '+' : '−'}${Math.abs(delta).toFixed(0)}%</p>` +
    barChart([
      { label: 'Scenario A', sub: 'Base', value: A[key], color: '#6c7be8' },
      { label: 'Scenario B', sub: 'Optimised', value: B[key], color: '#4cc3d9' },
    ], unit, `${title} (illustrative sample)`);
  document.querySelectorAll<HTMLButtonElement>('.metric-tabs button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.m === m)));
}
document.querySelector('.metric-tabs')!.addEventListener('click', (e) => {
  const b = (e.target as HTMLElement).closest<HTMLButtonElement>('button[data-m]');
  if (b) drawChart(b.dataset.m as MetricKey);
});
drawChart('energy');

const rows: [string, string, string, string][] = [
  ['pin', 'Distance', `${A.distanceKm} km`, `${B.distanceKm} km`],
  ['spark', 'Energy Consumption', `${A.energyKwh} kWh`, `${B.energyKwh} kWh`],
  ['wave', 'Estimated Range', `${A.rangeKm} km`, `${B.rangeKm} km`],
  ['clock', 'Est. Travel Time', hm(A.travelMin), hm(B.travelMin)],
  ['battery', 'Predicted Arrival Battery', `${A.arrivalPct}%`, `${B.arrivalPct}%`],
];
document.getElementById('metrics')!.innerHTML = `<thead><tr><th>Metric</th><th>Scenario A</th><th>Scenario B</th></tr></thead><tbody>${rows.map(([ic, l, a, b]) => `<tr><td><span class="m-ic">${icon(ic)}</span>${l}</td><td>${a}</td><td>${b}</td></tr>`).join('')}</tbody>`;

// Comparison / Saved tabs
const tabs = [...document.querySelectorAll<HTMLButtonElement>('.view-tabs [role=tab]')];
tabs.forEach((t) => t.addEventListener('click', () => tabs.forEach((x) => {
  const on = x === t;
  x.setAttribute('aria-selected', String(on));
  x.tabIndex = on ? 0 : -1;
  document.getElementById(x.getAttribute('aria-controls')!)!.hidden = !on;
})));
