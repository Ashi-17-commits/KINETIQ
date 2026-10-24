import './styles.css';
import { createDitherVeil } from './ditherVeil.ts';
import { DEFAULT_VEHICLE } from './engine.ts';
import { ENGINE_SOURCE, fetchBackendVehicle } from './api.ts';

const root = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Start the intro once the hero vehicle is decoded (or immediately if it fails).
const img = document.querySelector<HTMLImageElement>('.hero-img')!;
const start = () => requestAnimationFrame(() => root.classList.add('ready'));
if (img.complete) start();
else { img.addEventListener('load', start, { once: true }); img.addEventListener('error', start, { once: true }); }
setTimeout(start, 2500);

// Nav: condense on scroll, mobile menu toggle.
const nav = document.querySelector<HTMLElement>('.nav')!;
const menuBtn = nav.querySelector<HTMLButtonElement>('.menu-btn')!;
addEventListener('scroll', () => nav.classList.toggle('scrolled', scrollY > 40), { passive: true });
menuBtn.addEventListener('click', () => menuBtn.setAttribute('aria-expanded', String(nav.classList.toggle('open'))));
nav.querySelectorAll('.nav-links a').forEach((a) => a.addEventListener('click', () => nav.classList.remove('open')));

// Theme rail: 01–04, auto-advances with the progress ring; click to select.
const copy = [
  'Explore how driving conditions, battery behaviour and trip variables influence EV energy consumption.',
  'See how speed, traffic and extra load change every watt-hour you spend per kilometre.',
  'Compare a baseline with a modified trip (gradient, simulated traffic, payload, accessory load) using a deterministic physics engine.',
  'Turn simulated insight into efficient habits — and arrive with more charge to spare.',
];
const buttons = [...document.querySelectorAll<HTMLButtonElement>('.slide-list button')];
const num = document.getElementById('slide-num')!;
const lead = document.getElementById('slide-copy')!;
const ring = document.querySelector<SVGCircleElement>('.ring')!;
let current = 0;
let timer = 0;

function go(i: number) {
  current = (i + copy.length) % copy.length;
  buttons.forEach((b, j) => b.classList.toggle('active', j === current));
  num.textContent = String(current + 1).padStart(2, '0');
  lead.classList.add('swap');
  setTimeout(() => { lead.textContent = copy[current]; lead.classList.remove('swap'); }, reduced ? 0 : 380);
  ring.style.animation = 'none';
  void ring.getBoundingClientRect();
  ring.style.animation = '';
  schedule();
}
function schedule() {
  clearTimeout(timer);
  if (!reduced) timer = window.setTimeout(() => go(current + 1), 6000);
}
buttons.forEach((b) => b.addEventListener('click', () => go(Number(b.dataset.i))));
if (getComputedStyle(document.querySelector('.slides')!).display !== 'none') schedule();

// Subtle pointer parallax on the vehicle (desktop, motion allowed).
const frame = document.querySelector<HTMLElement>('.hero-frame')!;
if (!reduced && matchMedia('(pointer: fine)').matches) {
  let tx = 0, ty = 0, x = 0, y = 0, raf = 0;
  const loop = () => {
    x += (tx - x) * 0.06; y += (ty - y) * 0.06;
    frame.style.translate = `${x.toFixed(2)}px ${y.toFixed(2)}px`;
    raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.05 ? requestAnimationFrame(loop) : 0;
  };
  addEventListener('pointermove', (e) => {
    tx = (e.clientX / innerWidth - 0.5) * -14;
    ty = (e.clientY / innerHeight - 0.5) * -8;
    if (!raf) raf = requestAnimationFrame(loop);
  }, { passive: true });
}

// Dither Veil on the car: the vehicle photo is dithered into gold dots, clipped to the
// car's alpha mask (CSS), and a wandering cyan-rimmed window lifts the dither as it drifts.
const veil = document.querySelector<HTMLElement>('.car-veil');
if (veil) {
  const mount = () => {
    try {
      createDitherVeil(veil, {
        src: '/img/hero-vehicle.jpg',
        fit: 'cover',
        pattern: 'bayer',
        pixelSize: 2,
        levels: 2,
        inkColor: '#000000',
        paperColor: '#cdb57e',
        contrast: 1.2,
        brightness: 0.03,
        revealRadius: 150,
        softness: 0.45,
        linger: 1.6,
        rim: 0.16,
        rimColor: '#6fd6e8',
        revealTo: 'ink',
        wander: true,
        clickBurst: false,
        maxDpr: 1.5,
        staticFrame: reduced,
        eventTarget: document.querySelector<HTMLElement>('.hero')!,
        onReady: () => veil.classList.add('on'),
      });
    } catch {
      veil.remove(); // No WebGL2: the car photo stays exactly as is.
    }
  };
  // Mount once the car's push-in settles, so the dither aligns with the final frame.
  setTimeout(mount, reduced ? 0 : 2600);
}

// Hover: a brief champagne sweep over the nose when the pointer reaches the car's front.
// Hit-tested via the hero because the copy block overlaps part of the car.
const fx = document.querySelector<HTMLElement>('.car-fx');
if (fx && !reduced && matchMedia('(pointer: fine)').matches) {
  let inside = false;
  fx.querySelector('.hover-sheen')!.addEventListener('animationend', () => fx.classList.remove('hover'));
  document.querySelector('.hero')!.addEventListener('pointermove', (e) => {
    const r = fx.getBoundingClientRect();
    const x = ((e as PointerEvent).clientX - r.left) / r.width;
    const y = ((e as PointerEvent).clientY - r.top) / r.height;
    const over = x > 0.02 && x < 0.62 && y > 0.4 && y < 0.82;
    if (over && !inside && root.classList.contains('ready') && !fx.classList.contains('hover')) fx.classList.add('hover');
    inside = over;
  }, { passive: true });
}

// Vehicle parameters for the HUD callouts and the blueprint section: always those of the engine
// the Simulator actually uses (FastAPI backend when configured, else the in-browser engine).
type Spec = { vals: Record<string, string>; text: Record<string, string>; src: string };
const pct = (x: number) => String(Math.round(x * 100));
const localSpec = (src: string): Spec => {
  const V = DEFAULT_VEHICLE;
  return {
    src,
    vals: {
      cd: V.cd.toFixed(2), area: V.frontalAreaM2.toFixed(1), crr: V.crrBase.toFixed(4), mass: V.massKg.toLocaleString('en-US'),
      kwhu: `${V.capacityKwh} kWh`, kw: `${V.maxMotorKw} kW`,
    },
    text: {
      'kw-label': 'Motor',
      rolling: 'Tyre deformation, scaled by road surface and tyre pressure.',
      'rolling-val': `C<sub>rr</sub> <b>${V.crrBase.toFixed(4)}</b> on dry asphalt`,
      battery: 'Drivetrain efficiency, I&sup2;R pack losses and temperature-limited regeneration.',
      'battery-val': `<b>${V.capacityKwh}</b> kWh &middot; <b>${V.packVoltage}</b> V &middot; regen <b>${pct(V.regenEff)}</b>%`,
    },
  };
};
const backendSpec = (v: Record<string, number>): Spec => ({
  src: 'Specs shown: the FastAPI backend’s default vehicle, the one the Simulator uses.',
  vals: {
    cd: v.drag_coefficient.toFixed(2), area: v.frontal_area_m2.toFixed(1), crr: v.rolling_resistance_coefficient.toFixed(4),
    mass: v.mass_kg.toLocaleString('en-US'), kwhu: `${v.usable_battery_capacity_kwh} kWh`, kw: `${v.max_regen_power_kw} kW`,
  },
  text: {
    'kw-label': 'Max regen',
    rolling: 'Tyre rolling loss, a constant coefficient in the backend model.',
    'rolling-val': `C<sub>rr</sub> <b>${v.rolling_resistance_coefficient.toFixed(4)}</b>`,
    battery: 'Drivetrain efficiency while driving; regeneration recovers braking energy up to a power limit.',
    'battery-val': `<b>${v.usable_battery_capacity_kwh}</b> kWh &middot; drive <b>${pct(v.drivetrain_efficiency)}</b>% &middot; regen <b>${pct(v.regen_efficiency)}</b>%`,
  },
});
const applySpec = (s: Spec) => {
  document.querySelectorAll<HTMLElement>('[data-v]').forEach((el) => { el.textContent = s.vals[el.dataset.v!] ?? ''; });
  document.querySelectorAll<HTMLElement>('[data-t]').forEach((el) => { el.innerHTML = s.text[el.dataset.t!] ?? el.innerHTML; });
  document.querySelectorAll<HTMLElement>('.spec-src').forEach((el) => { el.textContent = s.src; });
};
if (ENGINE_SOURCE === 'api') {
  document.querySelectorAll<HTMLElement>('[data-v]').forEach((el) => { el.textContent = '…'; });
  fetchBackendVehicle().then((v) => applySpec(v ? backendSpec(v)
    : localSpec('Specs shown: the in-browser reference EV. The backend could not be reached, so the Simulator would run its labelled fallback engine.')));
} else {
  applySpec(localSpec('Specs shown: the in-browser reference EV, the engine the Simulator uses (no backend configured).'));
}

// Blueprint: scroll progress drives the photo → wireframe morph and the active step.
const bp = document.querySelector<HTMLElement>('.blueprint');
if (bp) {
  const steps = [...bp.querySelectorAll('.bp-steps li')];
  const pts = [...bp.querySelectorAll('.bp-pt')];
  let active = -1, ticking = false;
  const update = () => {
    ticking = false;
    const r = bp.getBoundingClientRect();
    const p = Math.min(1, Math.max(0, -r.top / (r.height - innerHeight)));
    bp.style.setProperty('--p', p.toFixed(3));
    const i = Math.min(steps.length - 1, Math.floor(p * steps.length));
    if (i !== active) {
      active = i;
      steps.forEach((s, j) => s.classList.toggle('active', j === i));
      pts.forEach((s, j) => s.classList.toggle('active', j === i));
    }
  };
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  addEventListener('resize', update);
  update();
}
