/**
 * Path Planning tab. The map is a static illustration. Values come from one of three
 * clearly labelled sources:
 *  - "Illustrative sample data": placeholder Mumbai → Pune figures shown before planning,
 *  - "From entered distance": the energy engine run on a distance the user enters,
 *  - "Routed by service": POST /api/route when VITE_API_URL is set.
 */
import { DEFAULT_VEHICLE, type Conditions } from './engine.ts';
import { planRoute, runSimulation, ROUTING_AVAILABLE, SimError, type RouteRequest } from './api.ts';
import { lineChart } from './charts.ts';
import { ROUTE_SAMPLE } from './sampleData.ts';
import { SAMPLE_BADGE, icon } from './shell.ts';

type Source = 'sample' | 'engine' | 'service';
interface Estimate {
  source: Source; distanceKm: number; durationMin: number; energyKwh: number;
  elevationGainM: number | null; elevation?: { km: number; m: number }[]; note?: string;
}

const $ = <T extends Element = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const fmt = (n: number, d = 0) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const hm = (m: number) => (m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`);
const CAPACITY = DEFAULT_VEHICLE.capacityKwh;

const SAMPLE: Estimate = {
  source: 'sample', distanceKm: ROUTE_SAMPLE.distanceKm, durationMin: ROUTE_SAMPLE.travelMin,
  energyKwh: ROUTE_SAMPLE.energyKwh, elevationGainM: ROUTE_SAMPLE.elevationGainM,
  elevation: ROUTE_SAMPLE.elevation.map(([km, m]) => ({ km, m })),
};
const badge = (s: Source) => (s === 'sample' ? SAMPLE_BADGE
  : `<span class="sample-badge live">${s === 'engine' ? 'From entered distance' : 'Routed by service'}</span>`);

let current: Estimate | null = SAMPLE;

export function initRoute(getConditions: () => Conditions) {
  initViewTabs();
  const form = $<HTMLFormElement>('#route-form');
  const soc = $<HTMLInputElement>('#r-soc');
  $('#r-manual').hidden = ROUTING_AVAILABLE;
  let ctrl: AbortController | null = null;

  // Clear buttons, battery slider, map layers.
  form.querySelectorAll<HTMLButtonElement>('[data-clear]').forEach((b) => b.addEventListener('click', () => {
    const input = document.getElementById(b.dataset.clear!) as HTMLInputElement;
    input.value = ''; input.focus();
  }));
  const syncSoc = () => {
    soc.style.setProperty('--p', `${((Number(soc.value) - 5) / 95) * 100}%`);
    $('#r-soc-out').textContent = soc.value;
    renderBattery();
  };
  soc.addEventListener('input', syncSoc);
  const stationsToggle = $<HTMLInputElement>('#r-stations');
  const setLayer = (name: string, on: boolean) => {
    document.querySelector(`.layer[data-layer="${name}"]`)?.setAttribute('aria-pressed', String(on));
    if (name === 'stations') { $('#stations').hidden = !on; stationsToggle.checked = on; }
    if (name === 'elevation') $('#elev-panel').hidden = !on;
  };
  document.querySelectorAll<HTMLButtonElement>('.layer[data-layer]').forEach((b) =>
    b.addEventListener('click', () => setLayer(b.dataset.layer!, b.getAttribute('aria-pressed') !== 'true')));
  stationsToggle.addEventListener('change', () => setLayer('stations', stationsToggle.checked));
  $('#stations').innerHTML = ROUTE_SAMPLE.stations.map((s) =>
    `<span class="station" style="left:${s.x}%;top:${s.y}%" title="${s.name} (illustrative)">${icon('plug')}</span>`).join('');

  syncSoc();
  render();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const start = String(fd.get('start') ?? '').trim();
    const end = String(fd.get('end') ?? '').trim();
    if (!start || !end) return status('error', 'Enter both a start and an end location.');
    ctrl?.abort();
    const c = (ctrl = new AbortController());
    status('loading');
    try {
      let est: Estimate;
      const conditions = { ...getConditions(), initialSocPct: Number(soc.value) };
      if (ROUTING_AVAILABLE) {
        const req: RouteRequest = {
          start, end,
          routeType: fd.get('routeType') as RouteRequest['routeType'],
          includeElevation: fd.has('includeElevation'),
          avoidSteep: fd.has('avoidSteep'),
          conditions,
        };
        const r = await planRoute(req, c.signal);
        const gain = r.elevation ? r.elevation.reduce((g, p, i, a) => g + (i ? Math.max(0, p.m - a[i - 1].m) : 0), 0) : null;
        est = { source: 'service', distanceKm: r.distanceKm, durationMin: r.durationMin, energyKwh: r.energyKwh, elevationGainM: gain, elevation: r.elevation };
      } else {
        const dist = Number(fd.get('routeDistanceKm'));
        const grade = Number(fd.get('routeGradePct') || 0);
        if (!Number.isFinite(dist) || dist < 1 || dist > 1000) {
          throw new SimError('No routing service is connected. Enter a known route distance (1–1000 km) to estimate energy.');
        }
        const { result } = await runSimulation({ ...conditions, distanceKm: dist, gradePct: Math.max(-8, Math.min(8, grade)) }, c.signal);
        est = {
          source: 'engine', distanceKm: dist, durationMin: result.durationMin, energyKwh: result.energyKwh, elevationGainM: null,
          note: `Estimate for ${start} → ${end} uses your entered distance and Drive settings; the path itself is not calculated.`,
        };
      }
      if (c.signal.aborted) return;
      current = est;
      render();
      status('ready', est.note ?? '');
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      current = null;
      render();
      status('error', err instanceof SimError ? err.message : 'Unexpected error while planning the route.');
    }
  });
}

function render() {
  renderSummary();
  renderBattery();
  renderElevation();
}

function renderSummary() {
  const e = current;
  $('#sum-src').innerHTML = e ? badge(e.source) : '';
  const rows: [string, string, string][] = [
    ['pin', 'Distance', e ? `${fmt(e.distanceKm)} km` : '—'],
    ['clock', 'Est. Travel Time', e ? hm(e.durationMin) : '—'],
    ['mountain', 'Elevation Gain', e?.elevationGainM != null ? `${fmt(e.elevationGainM)} m` : '—'],
    ['spark', 'Est. Energy Consumption', e ? `${fmt(e.energyKwh, 1)} kWh` : '—'],
  ];
  $('#route-summary').innerHTML = rows.map(([ic, l, v]) => `<div><dt><span class="m-ic">${icon(ic)}</span>${l}</dt><dd>${v}</dd></div>`).join('');
}

function renderBattery() {
  const box = $('#battery-est');
  const pct = Number($<HTMLInputElement>('#r-soc').value);
  const nowKwh = (pct / 100) * CAPACITY;
  if (!current) { box.innerHTML = '<p class="hint">No estimate available.</p>'; return; }
  const arrival = ((nowKwh - current.energyKwh) / CAPACITY) * 100;
  const arrivalTxt = arrival <= 0 ? 'Depleted before arrival' : `${fmt(arrival)}% (${fmt((arrival / 100) * CAPACITY, 1)} kWh)`;
  const level = arrival < 10 ? 'crit' : arrival < 20 ? 'warn' : '';
  box.innerHTML = `
    <div class="bat-bar ${level}" role="img" aria-label="Battery ${pct}% now, ${fmt(Math.max(0, arrival))}% on arrival"><i style="width:${pct}%"></i><b style="width:${Math.max(0, arrival)}%"></b></div>
    <dl class="sum sum-sm">
      <div><dt>Current Battery</dt><dd>${pct}% (${fmt(nowKwh, 1)} kWh)</dd></div>
      <div><dt>Estimated Consumption</dt><dd>${fmt(current.energyKwh, 1)} kWh</dd></div>
      <div><dt>Predicted Battery on Arrival</dt><dd class="${level}">${arrivalTxt}</dd></div>
    </dl>
    ${arrival < 15 ? `<p class="bat-warn">${icon('warn')}Recommended to charge before departure or stop at a charging station.</p>` : ''}
    <p class="hint">Reference vehicle, ${CAPACITY} kWh usable capacity at 20 °C.</p>`;
}

function renderElevation() {
  const body = $('#elev-body');
  const pts = current?.elevation;
  $('#elev-src').innerHTML = pts && current ? badge(current.source) : '';
  if (!pts || pts.length < 2) {
    body.innerHTML = `<p class="elev-empty">${ROUTING_AVAILABLE ? 'The routing service returned no elevation data.' : 'Elevation data requires a connected routing service.'}</p>`;
    return;
  }
  body.innerHTML = lineChart(pts.map((p) => ({ x: `${fmt(p.km)} km`, y: p.m })), {
    unit: 'm', area: true, color: 'var(--gold)', height: 170,
    aria: `Elevation profile (${current!.source === 'sample' ? 'illustrative sample' : 'from routing service'})`,
  });
}

function status(state: 'loading' | 'ready' | 'error', msg = '') {
  const btn = $<HTMLButtonElement>('.plan-btn');
  btn.setAttribute('aria-busy', String(state === 'loading'));
  $('.plan-label').textContent = state === 'loading' ? 'Planning…' : 'Plan Route';
  $('#route-status').innerHTML = state === 'error'
    ? `<div class="sim-error"><b>Route unavailable.</b> ${esc(msg)}</div>`
    : msg ? `<p class="route-note">${esc(msg)}</p>` : '';
}

/* ---------- Drive / Path Planning tabs ---------- */
function initViewTabs() {
  const tabs = [...document.querySelectorAll<HTMLButtonElement>('.view-tabs [role=tab]')];
  const show = (id: 'drive' | 'route') => {
    tabs.forEach((t) => {
      const on = t.id === `vt-${id}`;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')!)!.hidden = !on;
    });
    document.body.dataset.view = id;
  };
  tabs.forEach((t) => t.addEventListener('click', () => {
    const id = t.id === 'vt-route' ? 'route' : 'drive';
    show(id);
    history.replaceState(null, '', id === 'route' ? '#route' : location.pathname + location.search);
  }));
  $('.view-tabs').addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const next = tabs.find((t) => t.getAttribute('aria-selected') !== 'true')!;
    next.click(); next.focus();
  });
  // Sidebar anchors (#scenarios, #insights, #top) live in the Drive view.
  const sync = () => show(location.hash === '#route' ? 'route' : 'drive');
  addEventListener('hashchange', sync);
  sync();
}
