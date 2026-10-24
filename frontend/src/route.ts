/**
 * Path Planning tab. The map is a static illustration of the sample Mumbai ↔ Pune route.
 * There is no routing service, so results come from one of these clearly labelled sources:
 *  - "Sample route": the illustrative Mumbai ↔ Pune elevation profile (src/routeData.ts),
 *    with energy and time computed segment by segment by the active energy engine,
 *  - "From entered distance": the engine run on a distance the user enters (any other places),
 *  - "Routed by service": POST /api/route, only if ROUTING_AVAILABLE is ever enabled.
 * Every figure shown is recomputed when its inputs change; nothing is a fixed display value.
 */
import type { Conditions } from './engine.ts';
import type { ResultSource, SimVehicle } from './api.ts';
import { planRoute, runSimulation, ROUTING_AVAILABLE, SimError, type RouteRequest } from './api.ts';
import { lineChart } from './charts.ts';
import { ROUTE_SAMPLE } from './sampleData.ts';
import { findKnownRoute, elevationGain, routeSegments, depletionKm, SUPPORTED_PLACES, type ElevationPoint } from './routeData.ts';
import { icon } from './shell.ts';

type Source = 'sample-route' | 'manual' | 'service';
interface Estimate {
  source: Source; engine?: ResultSource; label: string;
  distanceKm: number; durationMin: number; energyKwh: number; capacityKwh: number; vehicle?: SimVehicle;
  /** [distanceKm, energyKwh] per segment in driving order, for depletion along the route. */
  segments: [number, number][];
  elevationIncluded: boolean; elevationGainM: number | null; elevation?: ElevationPoint[]; note?: string;
}

const $ = <T extends Element = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const fmt = (n: number, d = 0) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const hm = (m: number) => (m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`);
const ENGINE_NAME: Record<ResultSource, string> = { api: 'FastAPI', local: 'local engine', 'local-fallback': 'local FALLBACK' };
const SAMPLE_PAIR = `${ROUTE_SAMPLE.start} ↔ ${ROUTE_SAMPLE.end}`;

const badge = (e: Estimate) => {
  const eng = ENGINE_NAME[e.engine ?? 'local'];
  if (e.source === 'sample-route') return `<span class="sample-badge" title="Route geometry and elevation are illustrative sample data; energy and time are computed by the ${eng} engine.">Sample route · energy by ${eng}</span>`;
  if (e.source === 'manual') return `<span class="sample-badge live">From entered distance · ${eng}</span>`;
  return '<span class="sample-badge live">Routed by service</span>';
};

let current: Estimate | null = null;

export function initRoute(getConditions: () => Conditions) {
  const form = $<HTMLFormElement>('#route-form');
  const soc = $<HTMLInputElement>('#r-soc');
  const startIn = $<HTMLInputElement>('#r-start');
  const endIn = $<HTMLInputElement>('#r-end');
  const elevIn = $<HTMLInputElement>('#r-elev');
  const stationsToggle = $<HTMLInputElement>('#r-stations');
  let ctrl: AbortController | null = null;
  let plannedKey = '';

  $('#route-places').innerHTML = SUPPORTED_PLACES.map((p) => `<option value="${esc(p)}"></option>`).join('');
  const planKey = () => JSON.stringify([startIn.value.trim(), endIn.value.trim(), elevIn.checked, soc.value,
    new FormData(form).get('routeDistanceKm'), new FormData(form).get('routeGradePct'), getConditions()]);

  /** Show the manual-distance fields only for start/end pairs without route data. */
  const syncLocations = () => {
    const known = ROUTING_AVAILABLE || !!findKnownRoute(startIn.value, endIn.value);
    $('#r-manual').hidden = known;
    renderMapChip(known);
    return known;
  };

  /** Locations changed: re-plan a supported route; otherwise drop the stale estimate. */
  const onLocationsChange = () => {
    if (syncLocations()) { plan(); return; }
    ctrl?.abort();
    current = null;
    plannedKey = '';
    render();
    const s = startIn.value.trim(), e = endIn.value.trim();
    status('ready', s && e
      ? `No route data for ${s} → ${e}. Only the sample ${SAMPLE_PAIR} route has route data, and no routing service is connected. Enter a known distance below to estimate energy; the path itself will not be calculated.`
      : 'Enter both a start and an end location.');
  };

  form.querySelectorAll<HTMLButtonElement>('[data-clear]').forEach((b) => b.addEventListener('click', () => {
    const input = document.getElementById(b.dataset.clear!) as HTMLInputElement;
    input.value = ''; input.focus();
    onLocationsChange();
  }));
  startIn.addEventListener('change', onLocationsChange);
  endIn.addEventListener('change', onLocationsChange);

  const syncSoc = () => {
    soc.style.setProperty('--p', `${((Number(soc.value) - 5) / 95) * 100}%`);
    $('#r-soc-out').textContent = soc.value;
    renderBattery();
  };
  soc.addEventListener('input', syncSoc);
  // On release, re-run the engine at the new starting SOC so every figure comes from one run.
  soc.addEventListener('change', () => { if (current) plan(); });
  elevIn.addEventListener('change', () => { if (current) plan(); else renderElevation(); });

  const setLayer = (name: string, on: boolean) => {
    document.querySelector(`.layer[data-layer="${name}"]`)?.setAttribute('aria-pressed', String(on));
    if (name === 'stations') { $('#stations').hidden = !on; stationsToggle.checked = on; }
    if (name === 'elevation') $('#elev-panel').hidden = !on;
  };
  document.querySelectorAll<HTMLButtonElement>('.layer[data-layer]').forEach((b) =>
    b.addEventListener('click', () => setLayer(b.dataset.layer!, b.getAttribute('aria-pressed') !== 'true')));
  stationsToggle.addEventListener('change', () => setLayer('stations', stationsToggle.checked));
  $('#stations').innerHTML = ROUTE_SAMPLE.stations.map((s) =>
    `<span class="station" style="left:${s.x}%;top:${s.y}%" title="${esc(s.name)}: illustrative sample marker, not a real or live charging station">${icon('plug')}</span>`).join('');

  async function plan() {
    const start = startIn.value.trim();
    const end = endIn.value.trim();
    if (!start || !end) return status('error', 'Enter both a start and an end location.');
    ctrl?.abort();
    const c = (ctrl = new AbortController());
    const key = planKey();
    status('loading');
    try {
      const conditions: Conditions = { ...getConditions(), initialSocPct: Number(soc.value) };
      const known = findKnownRoute(start, end);
      let est: Estimate;
      if (ROUTING_AVAILABLE) {
        const req: RouteRequest = {
          start, end, routeType: new FormData(form).get('routeType') as RouteRequest['routeType'],
          includeElevation: elevIn.checked, avoidSteep: $<HTMLInputElement>('#r-steep').checked, conditions,
        };
        const r = await planRoute(req, c.signal);
        est = {
          // The route service contract carries no battery capacity, so arrival SOC is not shown.
          source: 'service', label: `${start} → ${end}`, capacityKwh: NaN,
          distanceKm: r.distanceKm, durationMin: r.durationMin, energyKwh: r.energyKwh, segments: [[r.distanceKm, r.energyKwh]],
          elevationIncluded: !!r.elevation, elevationGainM: r.elevation ? elevationGain(r.elevation) : null, elevation: r.elevation,
        };
      } else if (known) {
        // Segment-wise: each constant-gradient stretch of the sample profile is run through the
        // active engine with the Drive settings; all segments are pinned to the first run's engine.
        const segs = routeSegments(known, elevIn.checked);
        const first = await runSimulation({ ...conditions, distanceKm: segs[0].distanceKm, gradePct: segs[0].gradePct }, c.signal);
        const rest = await Promise.all(segs.slice(1).map((s) =>
          runSimulation({ ...conditions, distanceKm: s.distanceKm, gradePct: s.gradePct }, c.signal, { source: first.source })));
        const runs = [first, ...rest];
        const segEnergy: [number, number][] = runs.map((r, i) => [segs[i].distanceKm, (r.result.whPerKm * segs[i].distanceKm) / 1000]);
        const durationMin = runs.reduce((a, r, i) => a + (segs[i].distanceKm / Math.max(r.result.avgKmh, 1)) * 60, 0);
        est = {
          source: 'sample-route', engine: first.source, label: `${known.start} → ${known.end}`,
          distanceKm: known.distanceKm, durationMin, energyKwh: segEnergy.reduce((a, [, e]) => a + e, 0),
          capacityKwh: first.result.usableKwh, vehicle: first.vehicle, segments: segEnergy,
          elevationIncluded: elevIn.checked, elevationGainM: elevIn.checked ? elevationGain(known.elevation) : null, elevation: known.elevation,
          note: `${known.start} → ${known.end}: illustrative sample route profile. Energy and time computed over ${segs.length} ${segs.length === 1 ? 'flat segment' : 'gradient segments'} by the ${ENGINE_NAME[first.source]} engine using your Drive settings (speed ${conditions.cruiseKmh} km/h, traffic, payload, auxiliary load); it updates when you return here after changing them.`,
        };
      } else {
        const fd = new FormData(form);
        const dist = Number(fd.get('routeDistanceKm'));
        const grade = Number(fd.get('routeGradePct') || 0);
        if (!fd.get('routeDistanceKm') || !Number.isFinite(dist) || dist < 1 || dist > 1000) {
          throw new SimError(`No route data for ${start} → ${end} (only the sample ${SAMPLE_PAIR} route exists) and no routing service is connected. Enter a known route distance (1–1000 km) to estimate energy.`);
        }
        const { result, source, vehicle } = await runSimulation({ ...conditions, distanceKm: dist, gradePct: Math.max(-8, Math.min(8, grade)) }, c.signal);
        const energyKwh = (result.whPerKm * dist) / 1000;
        est = {
          source: 'manual', engine: source, label: `${start} → ${end}`, capacityKwh: result.usableKwh, vehicle,
          distanceKm: dist, durationMin: (dist / Math.max(result.avgKmh, 1)) * 60, energyKwh, segments: [[dist, energyKwh]],
          elevationIncluded: false, elevationGainM: null,
          note: `Estimate for ${start} → ${end} uses your entered distance and average gradient with the Drive settings; the path itself is not calculated and the map does not show it.`,
        };
      }
      if (c.signal.aborted) return;
      current = est;
      plannedKey = key;
      render();
      status('ready', est.note ?? '');
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      current = null;
      plannedKey = '';
      render();
      status('error', err instanceof SimError ? err.message : 'Unexpected error while planning the route.');
    }
  }

  form.addEventListener('submit', (e) => { e.preventDefault(); plan(); });

  initViewTabs(() => {
    // Drive settings may have changed since the last plan: never show a stale estimate.
    if (planKey() !== plannedKey && syncLocations()) plan();
  });
  syncSoc();
  syncLocations();
  render();
  // Planning runs when the Path Planning tab is shown (onShowRoute above) or on Plan Route.
}

function renderMapChip(knownRoute: boolean) {
  $('#map-chip').textContent = knownRoute
    ? `Illustrative map of the sample ${SAMPLE_PAIR} route · static visual, not a live map`
    : `Illustrative map of the sample ${SAMPLE_PAIR} route only · it does not show your entered route`;
}

function render() {
  renderSummary();
  renderBattery();
  renderElevation();
  renderVehicle();
}

function renderSummary() {
  const e = current;
  $('#sum-src').innerHTML = e ? badge(e) : '';
  const gain = !e ? '—'
    : e.elevationGainM != null ? `${fmt(e.elevationGainM)} m`
    : e.source === 'sample-route' ? 'Not included' : 'No elevation data';
  const rows: [string, string, string][] = [
    ['pin', 'Distance', e ? `${fmt(e.distanceKm)} km` : '—'],
    ['clock', 'Est. Travel Time', e ? hm(e.durationMin) : '—'],
    ['mountain', 'Elevation Gain', gain],
    ['spark', 'Est. Energy Consumption', e ? `${fmt(e.energyKwh, 1)} kWh` : '—'],
  ];
  $('#route-summary').innerHTML = rows.map(([ic, l, v]) => `<div><dt><span class="m-ic">${icon(ic)}</span>${l}</dt><dd>${v}</dd></div>`).join('');
}

function renderBattery() {
  const box = $('#battery-est');
  const pct = Number($<HTMLInputElement>('#r-soc').value);
  if (!current || !Number.isFinite(current.capacityKwh)) { box.innerHTML = '<p class="hint">No estimate available. Plan a route to calculate battery use.</p>'; return; }
  const CAPACITY = current.capacityKwh;
  const nowKwh = (pct / 100) * CAPACITY;
  const depKm = depletionKm(nowKwh, current.segments);
  const arrival = Math.min(100, ((nowKwh - current.energyKwh) / CAPACITY) * 100);
  const arrivalTxt = depKm !== null ? `Depleted at ~${fmt(depKm)} km of ${fmt(current.distanceKm)} km` : `${fmt(arrival)}% (${fmt((arrival / 100) * CAPACITY, 1)} kWh)`;
  const shown = depKm !== null ? 0 : Math.max(0, arrival);
  const level = depKm !== null || arrival < 10 ? 'crit' : arrival < 20 ? 'warn' : '';
  box.innerHTML = `
    <div class="bat-bar ${level}" role="img" aria-label="Battery ${pct}% now, ${fmt(shown)}% on arrival"><i style="width:${pct}%"></i><b style="width:${shown}%"></b></div>
    <dl class="sum sum-sm">
      <div><dt>Current Battery</dt><dd>${pct}% (${fmt(nowKwh, 1)} kWh)</dd></div>
      <div><dt>Estimated Consumption</dt><dd>${fmt(current.energyKwh, 1)} kWh</dd></div>
      <div><dt>Predicted Battery on Arrival</dt><dd class="${level}">${arrivalTxt}</dd></div>
    </dl>
    ${depKm !== null || arrival < 15 ? `<p class="bat-warn">${icon('warn')}Recommended to charge before departure. Station markers on the map are illustrative samples, not real stations.</p>` : ''}
    <p class="hint">Same engine as the energy figure (${ENGINE_NAME[current.engine ?? 'local']}): ${fmt(CAPACITY, 1)} kWh usable capacity.${arrival >= 100 ? ' Arrival is capped at 100%.' : ''}</p>`;
}

function renderElevation() {
  const body = $('#elev-body');
  const e = current;
  $('#elev-src').innerHTML = e?.elevation && e.elevationIncluded ? badge(e) : '';
  if (!e) { body.innerHTML = '<p class="elev-empty">Plan a route to see its elevation profile.</p>'; return; }
  if (!e.elevation || e.elevation.length < 2) {
    body.innerHTML = `<p class="elev-empty">${e.source === 'manual' ? 'No elevation data for entered routes; the estimate uses your average gradient.' : 'The routing service returned no elevation data.'}</p>`;
    return;
  }
  if (!e.elevationIncluded) {
    body.innerHTML = '<p class="elev-empty">Elevation is excluded from this estimate (flat road assumed). Turn on "Include Elevation Data" to use the profile.</p>';
    return;
  }
  body.innerHTML = lineChart(e.elevation.map((p) => ({ x: `${fmt(p.km)} km`, y: p.m })), {
    unit: 'm', area: true, color: 'var(--gold)', height: 170,
    aria: `Elevation profile, ${e.label} (${e.source === 'sample-route' ? 'illustrative sample' : 'from routing service'})`,
  });
}

function renderVehicle() {
  const v = current?.vehicle;
  const opt = $<HTMLSelectElement>('#r-vehicle').options[0];
  opt.textContent = v && current
    ? `${current.engine === 'api' ? 'FastAPI default EV' : 'KINETIQ local reference EV'} (${fmt(v.massKg)} kg, ${fmt(current.capacityKwh, 1)} kWh usable)`
    : 'Vehicle of the active engine';
  $('#r-vehicle-note').textContent = 'Only the active engine\'s configured vehicle is available (payload from Drive settings); no other vehicle presets exist yet.';
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
function initViewTabs(onShowRoute: () => void) {
  const tabs = [...document.querySelectorAll<HTMLButtonElement>('.view-tabs [role=tab]')];
  const show = (id: 'drive' | 'route') => {
    tabs.forEach((t) => {
      const on = t.id === `vt-${id}`;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')!)!.hidden = !on;
    });
    document.body.dataset.view = id;
    if (id === 'route') onShowRoute();
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
