import './styles.css';
import './simulator.css';
import './pages.css';
import { DEFAULT_CONDITIONS, DEFAULT_VEHICLE, type Conditions, type Result, type Recommendation } from './engine.ts';
import { runSimulation, ENGINE_SOURCE, SimError } from './api.ts';
import { initRoute } from './route.ts';

type Field =
  | { key: keyof Conditions; label: string; kind: 'range'; min: number; max: number; step: number; unit: string }
  | { key: keyof Conditions; label: string; kind: 'seg'; options: [string, string][] }
  | { key: keyof Conditions; label: string; kind: 'toggle' };

const TABS: { id: string; label: string; fields: Field[] }[] = [
  { id: 'vehicle', label: 'Vehicle', fields: [
    { key: 'payloadKg', label: 'Payload (kg)', kind: 'range', min: 0, max: 600, step: 10, unit: 'kg' },
    { key: 'tirePressureBar', label: 'Tyre Pressure (bar)', kind: 'range', min: 1.6, max: 3, step: 0.1, unit: 'bar' },
  ] },
  { id: 'driving', label: 'Driving', fields: [
    { key: 'cruiseKmh', label: 'Speed (km/h)', kind: 'range', min: 20, max: 160, step: 5, unit: 'km/h' },
    { key: 'distanceKm', label: 'Trip Distance (km)', kind: 'range', min: 5, max: 600, step: 5, unit: 'km' },
    { key: 'traffic', label: 'Traffic', kind: 'seg', options: [['free', 'Free'], ['moderate', 'Moderate'], ['heavy', 'Heavy']] },
    { key: 'style', label: 'Driving Style', kind: 'seg', options: [['eco', 'Eco'], ['normal', 'Normal'], ['aggressive', 'Sport']] },
  ] },
  { id: 'environment', label: 'Environment', fields: [
    { key: 'gradePct', label: 'Road Gradient (%)', kind: 'range', min: -8, max: 8, step: 0.5, unit: '%' },
    { key: 'ambientC', label: 'Ambient Temperature (°C)', kind: 'range', min: -20, max: 45, step: 1, unit: '°C' },
    { key: 'headwindKmh', label: 'Headwind (km/h)', kind: 'range', min: -30, max: 60, step: 5, unit: 'km/h' },
    { key: 'surface', label: 'Road Surface', kind: 'seg', options: [['dry', 'Dry'], ['wet', 'Wet'], ['gravel', 'Gravel'], ['snow', 'Snow']] },
  ] },
  { id: 'battery', label: 'Battery', fields: [
    { key: 'initialSocPct', label: 'Starting SOC (%)', kind: 'range', min: 5, max: 100, step: 1, unit: '%' },
    { key: 'hvac', label: 'Climate Control', kind: 'toggle' },
  ] },
];

const PRESETS: Record<string, Partial<Conditions>> = {
  highway: { distanceKm: 250, cruiseKmh: 120, traffic: 'free', style: 'normal', ambientC: 22, gradePct: 0, headwindKmh: 10, surface: 'dry', hvac: true, initialSocPct: 90 },
  city: { distanceKm: 35, cruiseKmh: 45, traffic: 'heavy', style: 'normal', ambientC: 26, gradePct: 0, headwindKmh: 0, surface: 'dry', hvac: true, initialSocPct: 60 },
  winter: { distanceKm: 180, cruiseKmh: 110, traffic: 'moderate', style: 'normal', ambientC: -10, gradePct: 0, headwindKmh: 20, surface: 'snow', hvac: true, tirePressureBar: 2.1, initialSocPct: 70 },
  mountain: { distanceKm: 60, cruiseKmh: 70, traffic: 'free', style: 'aggressive', ambientC: 12, gradePct: 6, headwindKmh: 0, surface: 'wet', hvac: true, payloadKg: 350, initialSocPct: 85 },
};

let current: Conditions = { ...DEFAULT_CONDITIONS };
let result: Result | null = null;
let recs: Recommendation[] = [];
let baseline: Result | null = null;
let controller: AbortController | null = null;

const $ = <T extends Element = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const fmt = (n: number, d = 0) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const avgKw = (r: Result) => (r.durationMin > 0 ? r.energyKwh / (r.durationMin / 60) : 0);

/* ---------- Controls ---------- */
function buildControls() {
  const tabs = $('.tabs');
  tabs.innerHTML = TABS.map((t, i) => `<button type="button" role="tab" id="tab-${t.id}" aria-controls="pane-${t.id}" aria-selected="${i === 1}" tabindex="${i === 1 ? 0 : -1}">${t.label}</button>`).join('');
  const form = $<HTMLFormElement>('#controls');
  form.innerHTML = TABS.map((t, i) => `
    <div class="pane" role="tabpanel" id="pane-${t.id}" aria-labelledby="tab-${t.id}" ${i === 1 ? '' : 'hidden'}>
      ${t.fields.map(fieldHtml).join('')}
      ${t.id === 'vehicle' ? `<p class="vehicle-note">Reference vehicle: ${fmt(DEFAULT_VEHICLE.massKg)} kg, C<sub>d</sub> ${DEFAULT_VEHICLE.cd}, ${DEFAULT_VEHICLE.capacityKwh} kWh pack, ${DEFAULT_VEHICLE.maxMotorKw} kW motor.</p>` : ''}
    </div>`).join('');

  tabs.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLButtonElement>('[role=tab]');
    if (b) selectTab(b);
  });
  tabs.addEventListener('keydown', (e) => {
    const all = [...tabs.querySelectorAll<HTMLButtonElement>('[role=tab]')];
    const i = all.indexOf(document.activeElement as HTMLButtonElement);
    if (i < 0 || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
    const next = all[(i + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
    selectTab(next); next.focus();
  });

  form.addEventListener('input', (e) => {
    const el = e.target as HTMLInputElement;
    const key = el.name as keyof Conditions;
    if (!key) return;
    let value: Conditions[keyof Conditions];
    if (el.type === 'checkbox') value = el.checked;
    else if (el.type === 'range' || el.type === 'number') {
      const n = Number(el.value);
      if (!Number.isFinite(n) || el.value === '') return;
      value = Math.min(Number(el.max), Math.max(Number(el.min), n));
    } else value = el.value as Conditions[keyof Conditions];
    current = { ...current, [key]: value } as Conditions;
    $<HTMLSelectElement>('#preset').value = 'custom';
    syncControls(el);
    scheduleRun();
  });
}

function fieldHtml(f: Field) {
  const id = `f-${f.key}`;
  if (f.kind === 'range') return `
    <div class="field"><label for="${id}">${f.label}</label>
      <div class="range-row"><input type="range" id="${id}" name="${f.key}" min="${f.min}" max="${f.max}" step="${f.step}" />
      <input type="number" class="num" name="${f.key}" min="${f.min}" max="${f.max}" step="${f.step}" aria-label="${f.label}" /></div></div>`;
  if (f.kind === 'seg') return `
    <fieldset class="field seg"><legend>${f.label}</legend><div class="seg-row">
      ${f.options.map(([v, l]) => `<label><input type="radio" name="${f.key}" value="${v}" /><span>${l}</span></label>`).join('')}</div></fieldset>`;
  return `<label class="field toggle" for="${id}"><span>${f.label}</span><input type="checkbox" id="${id}" name="${f.key}" role="switch" /><i></i></label>`;
}

function selectTab(b: HTMLButtonElement) {
  document.querySelectorAll<HTMLButtonElement>('[role=tab]').forEach((t) => {
    const on = t === b;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute('aria-controls')!)!.hidden = !on;
  });
}

function syncControls(except?: Element) {
  for (const [k, v] of Object.entries(current)) {
    document.querySelectorAll<HTMLInputElement>(`[name="${k}"]`).forEach((el) => {
      if (el === except) return;
      if (el.type === 'checkbox') el.checked = Boolean(v);
      else if (el.type === 'radio') el.checked = el.value === v;
      else el.value = String(v);
    });
  }
  document.querySelectorAll<HTMLInputElement>('input[type=range]').forEach((r) => {
    const p = ((Number(r.value) - Number(r.min)) / (Number(r.max) - Number(r.min))) * 100;
    r.style.setProperty('--p', `${p}%`);
  });
}

/* ---------- Running ---------- */
let timer = 0;
function scheduleRun() {
  clearTimeout(timer);
  timer = window.setTimeout(run, ENGINE_SOURCE === 'api' ? 350 : 120);
}

function setStatus(state: 'loading' | 'ready' | 'error', message = '') {
  document.body.dataset.state = state;
  const btn = $<HTMLButtonElement>('#run');
  btn.setAttribute('aria-busy', String(state === 'loading'));
  $('.run-label').textContent = state === 'loading' ? 'Simulating…' : 'Run Simulation';
  const s = $('#status');
  s.innerHTML = state === 'error'
    ? `<div class="sim-error"><b>Simulation unavailable.</b> ${esc(message)} No results are shown until a run succeeds. <button type="button" class="btn btn-ghost btn-xs" id="retry">Retry</button></div>`
    : '';
  if (state === 'error') $('#retry').addEventListener('click', () => run());
}

async function run() {
  clearTimeout(timer);
  controller?.abort();
  const ctrl = (controller = new AbortController());
  setStatus('loading');
  try {
    if (!baseline) baseline = (await runSimulation(DEFAULT_CONDITIONS, ctrl.signal)).result;
    const res = await runSimulation(current, ctrl.signal);
    if (ctrl.signal.aborted) return;
    result = res.result;
    recs = res.recommendations;
    setStatus('ready');
  } catch (e) {
    if ((e as Error).name === 'AbortError') return;
    result = null;
    recs = [];
    setStatus('error', e instanceof SimError ? e.message : 'Unexpected error while simulating.');
  }
  render();
}

/* ---------- Rendering ---------- */
function delta(cur: number, base: number | undefined, d = 0, invert = false) {
  if (base === undefined) return '<span class="dl">—</span>';
  const diff = cur - base;
  if (Math.abs(diff) < 10 ** -d / 2) return '<span class="dl">—</span>';
  const good = invert ? diff < 0 : diff > 0;
  return `<span class="dl ${good ? 'up' : 'down'}">${diff > 0 ? '+' : ''}${fmt(diff, d)}</span>`;
}

function gauge(label: string, unit: string, value: number | null, max: number, d = 0, cls = '') {
  const L = 160; // arc length for the 240° track (r = 38)
  const frac = value === null ? 0 : Math.max(0, Math.min(1, value / max));
  return `<div class="gauge ${cls}">
    <svg viewBox="0 0 100 74" aria-hidden="true"><path d="M17.1 66.3 A38 38 0 1 1 82.9 66.3" class="g-track" pathLength="${L}"/>
      <path d="M17.1 66.3 A38 38 0 1 1 82.9 66.3" class="g-val" pathLength="${L}" style="stroke-dasharray:${(frac * L).toFixed(1)} ${L}"/></svg>
    <span class="g-v">${value === null ? '—' : fmt(value, d)}</span><span class="g-u">${unit}</span><span class="g-l">${label}</span></div>`;
}

function renderGauges() {
  const r = result;
  const socCls = r && (r.depletedAtKm !== null || r.endSocPct < 10) ? 'crit' : r && r.endSocPct < 20 ? 'warn' : '';
  $('#gauges').innerHTML =
    gauge('Avg Speed', 'km/h', r ? r.avgKmh : null, 160) +
    gauge('Avg Battery Power', 'kW', r ? avgKw(r) : null, 80, 1) +
    gauge('Arrival SOC', '%', r ? (r.depletedAtKm !== null ? 0 : r.endSocPct) : null, 100, 0, socCls) +
    gauge('Consumption', 'kWh/100km', r ? r.whPerKm / 10 : null, 50, 1);
}

function renderHotspots() {
  const r = result;
  const set = (k: string, v: string) => { document.querySelector(`.hot[data-k="${k}"] b`)!.textContent = v; };
  set('battery', r ? `${fmt(r.energyKwh, 1)} kWh drawn` : '—');
  set('inverter', r ? `${fmt(r.breakdownKwh.driveLoss, 2)} kWh` : '—');
  set('motor', r ? `${fmt(r.peakKw)} kW` : '—');
  set('wheels', r ? `${fmt(r.breakdownKwh.regen, 2)} kWh` : '—');
}

function renderKpis() {
  const r = result, b = baseline ?? undefined;
  if (!r) { $('#kpis').innerHTML = ''; return; }
  const k = [
    ['Energy required', fmt(r.energyKwh, 1), 'kWh', delta(r.energyKwh, b?.energyKwh, 1, true)],
    ['Est. full range', fmt(r.estRangeKm), 'km', delta(r.estRangeKm, b?.estRangeKm)],
    ['Trip time', fmt(r.durationMin), 'min', delta(r.durationMin, b?.durationMin, 0, true)],
    ['Peak pack power', fmt(r.peakKw), 'kW', `<span class="dl">${fmt(r.peakCRate, 2)} C</span>`],
  ];
  $('#kpis').innerHTML = k.map(([l, v, u, d]) => `
    <div class="kpi"><span class="k-l">${l}</span><span class="k-v">${v}<small>${u}</small></span><span class="k-d">${d} <em>vs baseline</em></span></div>`).join('');
}

function niceStep(raw: number) {
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? raw;
}

function renderChart() {
  const svg = $<SVGSVGElement>('#soc-chart');
  if (!result) { svg.innerHTML = '<text x="320" y="124" text-anchor="middle" class="ax">No simulation result</text>'; return; }
  const W = 640, H = 240, L = 40, R = 12, T = 14, B = 30;
  const maxKm = Math.max(result.inputs.distanceKm, baseline?.inputs.distanceKm ?? 0, 1);
  const x = (km: number) => L + (km / maxKm) * (W - L - R);
  const y = (soc: number) => T + (1 - soc / 100) * (H - T - B);
  const path = (r: Result) => r.trace.map((p, i) => `${i ? 'L' : 'M'}${x(p.km).toFixed(1)},${y(p.soc).toFixed(1)}`).join('');
  const area = (r: Result) => `${path(r)}L${x(r.trace.at(-1)!.km).toFixed(1)},${y(0)}L${x(0)},${y(0)}Z`;
  const step = niceStep(maxKm / 5);
  const xt: number[] = [];
  for (let v = 0; v <= maxKm + 1e-9; v += step) xt.push(v);
  svg.innerHTML = `
    <defs><linearGradient id="g-cur" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cdb57e" stop-opacity=".28"/><stop offset="1" stop-color="#cdb57e" stop-opacity="0"/></linearGradient></defs>
    ${[0, 25, 50, 75, 100].map((t) => `<line x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}" class="grid"/><text x="${L - 8}" y="${y(t) + 4}" class="ax" text-anchor="end">${t}%</text>`).join('')}
    ${xt.map((t) => `<text x="${x(t)}" y="${H - 8}" class="ax" text-anchor="middle">${fmt(t)}</text>`).join('')}
    <text x="${W - R}" y="${H - 8}" class="ax" text-anchor="end">km</text>
    <line x1="${L}" x2="${W - R}" y1="${y(20)}" y2="${y(20)}" class="reserve"/><text x="${W - R}" y="${y(20) - 5}" class="ax warn" text-anchor="end">20% reserve</text>
    ${baseline ? `<path d="${path(baseline)}" class="base-line"/>` : ''}
    <path d="${area(result)}" fill="url(#g-cur)"/>
    <path d="${path(result)}" class="cur-line" pathLength="1"/>
    ${result.depletedAtKm !== null ? `<circle cx="${x(result.depletedAtKm)}" cy="${y(0)}" r="5" class="dep"/>` : ''}`;
}

function renderBreakdown() {
  if (!result) { $('#breakdown').innerHTML = '<p class="explain">No simulation result.</p>'; return; }
  const b = result.breakdownKwh;
  const rows: [string, number, string][] = [
    ['Aerodynamic drag', b.aero, ''], ['Rolling resistance', b.rolling, ''], ['Climbing', b.grade, ''],
    ['Acceleration', b.inertia, ''], ['Drivetrain losses', b.driveLoss, ''], ['Climate & auxiliaries', b.aux, ''],
    ['Pack I²R losses', b.packLoss, ''], ['Regen recovered', -b.regen, 'regen'],
  ];
  const max = Math.max(...rows.map((r) => Math.abs(r[1])), 0.001);
  const top = rows.slice(0, 7).reduce((a, r) => (r[1] > a[1] ? r : a));
  $('#breakdown').innerHTML = rows.filter((r) => Math.abs(r[1]) >= 0.005).map(([l, v, c]) => `
    <div class="bd-row ${c} ${l === top[0] ? 'top' : ''}"><span class="bd-l">${l}</span>
      <span class="bd-bar"><i style="width:${(Math.abs(v) / max) * 100}%"></i></span><span class="bd-v">${v < 0 ? '−' : ''}${fmt(Math.abs(v), 2)}</span></div>`).join('') +
    `<p class="explain">Largest load: <b>${top[0].toLowerCase()}</b> at ${fmt((top[1] / Math.max(result.energyKwh + b.regen, 0.001)) * 100)}% of gross demand.</p>`;
}

function renderFaults() {
  if (!result) { $('#fault-count').textContent = ''; $('#faults').innerHTML = ''; return; }
  const f = result.faults;
  $('#fault-count').textContent = f.length ? `${f.length} active` : 'none';
  $('#faults').innerHTML = f.length
    ? f.map((x) => `<li class="${x.severity}"><span class="sev">${x.severity}</span><div><b>${esc(x.title)}</b><p>${esc(x.detail)}</p></div></li>`).join('')
    : '<li class="ok"><span class="sev">ok</span><div><b>All rules passing</b><p>No reserve, power, thermal or tyre rules triggered for this scenario.</p></div></li>';
}

function renderRecs() {
  if (!result) { $('#recs').innerHTML = ''; return; }
  $('#recs').innerHTML = recs.length
    ? recs.map((r) => `<li><div><b>${esc(r.title)}</b><p>${esc(r.detail)}</p></div>${Number.isFinite(r.savingWhKm) ? `<span class="save">−${fmt(r.savingWhKm)} Wh/km<small>${fmt(r.savingPct, 1)}%</small></span>` : ''}</li>`).join('')
    : '<li class="none"><div><b>Already efficient</b><p>No single change tested saves more than 1% for this scenario.</p></div></li>';
}

function renderCompare() {
  const b = baseline, r = result;
  if (!b || !r) { $('#compare').innerHTML = '<tbody><tr><td>Run a successful simulation to compare scenarios.</td></tr></tbody>'; return; }
  const rows: [string, string, string, string][] = [
    ['Distance', `${fmt(b.inputs.distanceKm)} km`, `${fmt(r.inputs.distanceKm)} km`, delta(r.inputs.distanceKm, b.inputs.distanceKm)],
    ['Cruise speed', `${b.inputs.cruiseKmh} km/h`, `${r.inputs.cruiseKmh} km/h`, delta(r.inputs.cruiseKmh, b.inputs.cruiseKmh)],
    ['Temperature', `${b.inputs.ambientC} °C`, `${r.inputs.ambientC} °C`, delta(r.inputs.ambientC, b.inputs.ambientC)],
    ['Energy required', `${fmt(b.energyKwh, 1)} kWh`, `${fmt(r.energyKwh, 1)} kWh`, delta(r.energyKwh, b.energyKwh, 1, true)],
    ['Consumption', `${fmt(b.whPerKm)} Wh/km`, `${fmt(r.whPerKm)} Wh/km`, delta(r.whPerKm, b.whPerKm, 0, true)],
    ['Arrival SOC', `${fmt(b.endSocPct, 1)} %`, `${fmt(r.endSocPct, 1)} %`, delta(r.endSocPct, b.endSocPct, 1)],
    ['Est. full range', `${fmt(b.estRangeKm)} km`, `${fmt(r.estRangeKm)} km`, delta(r.estRangeKm, b.estRangeKm)],
    ['Usable capacity', `${fmt(b.usableKwh, 1)} kWh`, `${fmt(r.usableKwh, 1)} kWh`, delta(r.usableKwh, b.usableKwh, 1)],
    ['Regen recovered', `${fmt(b.breakdownKwh.regen, 2)} kWh`, `${fmt(r.breakdownKwh.regen, 2)} kWh`, delta(r.breakdownKwh.regen, b.breakdownKwh.regen, 2)],
    ['Alerts', `${b.faults.length}`, `${r.faults.length}`, delta(r.faults.length, b.faults.length, 0, true)],
  ];
  $('#compare').innerHTML = `<thead><tr><th>Metric</th><th>Baseline</th><th>Current</th><th>Δ</th></tr></thead><tbody>${rows.map((c) => `<tr><td>${c[0]}</td><td>${c[1]}</td><td>${c[2]}</td><td>${c[3]}</td></tr>`).join('')}</tbody>`;
}

function render() {
  renderGauges();
  renderHotspots();
  renderKpis();
  renderChart();
  renderBreakdown();
  renderFaults();
  renderRecs();
  renderCompare();
}

/* ---------- Wiring ---------- */
function applyPreset(name: string) {
  const p = PRESETS[name];
  if (!p) return;
  current = { ...DEFAULT_CONDITIONS, ...p };
  $<HTMLSelectElement>('#preset').value = name;
  syncControls();
  run();
}

buildControls();
initRoute(() => current);
$('#engine-src').textContent = ENGINE_SOURCE === 'api' ? 'Engine · FastAPI' : 'Engine · in-browser (deterministic)';
$<HTMLSelectElement>('#preset').addEventListener('change', (e) => {
  const v = (e.target as HTMLSelectElement).value;
  if (v !== 'custom') applyPreset(v);
});
$('#run').addEventListener('click', () => run());
$('#reset-inputs').addEventListener('click', () => {
  current = { ...DEFAULT_CONDITIONS };
  $<HTMLSelectElement>('#preset').value = 'custom';
  syncControls();
  run();
});
$('#set-base').addEventListener('click', () => { if (result) { baseline = result; render(); } });
$('#reset-base').addEventListener('click', () => { baseline = null; run(); });

const demo = new URLSearchParams(location.search).get('demo');
syncControls();
render();
if (demo && PRESETS[demo]) applyPreset(demo);
else run();
