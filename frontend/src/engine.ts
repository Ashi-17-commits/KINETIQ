/**
 * KINETIQ energy engine — deterministic, longitudinal-dynamics EV model.
 * Same inputs always produce the same outputs (no randomness, no clocks).
 *
 * Road-load at each 1 s step:
 *   F = m·a + m·g·Crr·cosθ + m·g·sinθ + ½·ρ·Cd·A·(v + v_wind)²
 * Battery power: traction / η_drive, regen · η_regen (capped), plus auxiliaries
 * and I²R pack losses.
 */

export type Surface = 'dry' | 'wet' | 'gravel' | 'snow';
export type Style = 'eco' | 'normal' | 'aggressive';
export type Traffic = 'steady' | 'free' | 'moderate' | 'heavy';

export interface Vehicle {
  massKg: number;
  cd: number;
  frontalAreaM2: number;
  crrBase: number;
  driveEff: number;      // battery → wheel
  regenEff: number;      // wheel → battery
  maxRegenKw: number;
  maxMotorKw: number;
  capacityKwh: number;
  packVoltage: number;
  packResistanceOhm: number;
  auxBaseKw: number;
}

export interface Conditions {
  distanceKm: number;
  cruiseKmh: number;
  gradePct: number;
  ambientC: number;
  hvac: boolean;
  payloadKg: number;
  headwindKmh: number;
  surface: Surface;
  style: Style;
  traffic: Traffic;
  tirePressureBar: number;
  initialSocPct: number;
  auxExtraKw: number;    // extra constant electrical load (kW) on top of the engine's base load
}

export const DEFAULT_VEHICLE: Vehicle = {
  massKg: 1950,
  cd: 0.24,
  frontalAreaM2: 2.3,
  crrBase: 0.0095,
  driveEff: 0.9,
  regenEff: 0.65,
  maxRegenKw: 70,
  maxMotorKw: 220,
  capacityKwh: 75,
  packVoltage: 400,
  packResistanceOhm: 0.08,
  auxBaseKw: 0.3,
};

export const DEFAULT_CONDITIONS: Conditions = {
  distanceKm: 50,
  cruiseKmh: 90,
  gradePct: 0,
  ambientC: 22,
  hvac: true,
  payloadKg: 150,
  headwindKmh: 0,
  surface: 'dry',
  style: 'normal',
  traffic: 'moderate',
  tirePressureBar: 2.5,
  initialSocPct: 80,
  auxExtraKw: 0,
};

const G = 9.81;
const SURFACE_CRR: Record<Surface, number> = { dry: 1, wet: 1.15, gravel: 1.6, snow: 2.2 };
const STYLE_ACCEL: Record<Style, number> = { eco: 0.9, normal: 1.6, aggressive: 2.8 }; // m/s²
const STYLE_DECEL: Record<Style, number> = { eco: 0.8, normal: 1.6, aggressive: 3.2 }; // m/s²
const TRAFFIC_STOPS_PER_KM: Record<Traffic, number> = { steady: 0, free: 0.1, moderate: 0.6, heavy: 2 };
const STOP_DWELL_S = 15;
const NOMINAL_TIRE_BAR = 2.5;

export interface Breakdown {
  aero: number; rolling: number; grade: number; inertia: number; aux: number; packLoss: number; driveLoss: number; regen: number;
}

export interface TracePoint { km: number; soc: number; kmh: number; kw: number }

export interface Fault { id: string; severity: 'info' | 'warning' | 'critical'; title: string; detail: string }

export interface Result {
  inputs: Conditions;
  energyKwh: number;
  whPerKm: number;
  endSocPct: number;
  usableKwh: number;
  estRangeKm: number;
  durationMin: number;
  avgKmh: number;
  peakKw: number;
  peakCRate: number;
  depletedAtKm: number | null;
  breakdownKwh: Breakdown;
  trace: TracePoint[];
  faults: Fault[];
  /** Range left after arrival at this trip's consumption; null when undefined (e.g. net regen). */
  remainingRangeKm?: number | null;
  remainingRangeNote?: string;
  /** Engine-reported traffic description (always simulated, never live data). */
  trafficLabel?: string;
  /** True when breakdownKwh.inertia is a remainder estimate, not a directly computed value. */
  inertiaEstimated?: boolean;
  /** True when breakdownKwh.driveLoss is a remainder (everything not attributed elsewhere). */
  driveLossRemainder?: boolean;
}

/** Air density from ideal gas law at sea-level pressure. */
export function airDensity(tempC: number): number {
  return 101325 / (287.05 * (tempC + 273.15));
}

/** Rolling resistance: surface multiplier and ~+1.5 % per 0.1 bar under-inflation. */
export function rollingCoeff(v: Vehicle, c: Conditions): number {
  const underBar = Math.max(0, NOMINAL_TIRE_BAR - c.tirePressureBar);
  return v.crrBase * SURFACE_CRR[c.surface] * (1 + 0.15 * underBar);
}

/** HVAC load (kW): heating draws more than cooling per °C away from 21 °C. */
export function hvacKw(c: Conditions): number {
  if (!c.hvac) return 0;
  const d = c.ambientC - 21;
  return d < 0 ? Math.min(5, 0.15 * -d + 0.3) : Math.min(3, 0.08 * d + 0.2);
}

/** Usable capacity factor: lithium-ion loses accessible energy in the cold. */
export function capacityFactor(tempC: number): number {
  if (tempC >= 20) return tempC > 40 ? 0.98 : 1;
  return Math.max(0.7, 1 - 0.008 * (20 - tempC));
}

/** Regen acceptance is limited when the pack is cold or near full. */
function regenLimitKw(v: Vehicle, tempC: number, socPct: number): number {
  let k = 1;
  if (tempC < 10) k *= Math.max(0.2, 1 - 0.04 * (10 - tempC));
  if (socPct > 90) k *= Math.max(0, (100 - socPct) / 10);
  return v.maxRegenKw * k;
}

/** Deterministic drive cycle: cruise segments separated by evenly spaced stops. */
function buildCycle(c: Conditions): number[] {
  const vCruise = c.cruiseKmh / 3.6;
  const a = STYLE_ACCEL[c.style];
  const b = STYLE_DECEL[c.style];
  const totalM = c.distanceKm * 1000;
  const stops = Math.floor(c.distanceKm * TRAFFIC_STOPS_PER_KM[c.traffic]);
  const segM = totalM / (stops + 1);
  const speeds: number[] = [];
  for (let s = 0; s <= stops; s++) {
    let x = 0;
    let v = 0;
    const brakeDist = (u: number) => (u * u) / (2 * b);
    while (x < segM) {
      if (segM - x <= brakeDist(v) + v * 0.5 && v > 0) v = Math.max(0, v - b);
      else if (v < vCruise) v = Math.min(vCruise, v + a);
      if (v <= 0 && x > 0) break;
      x += v;
      speeds.push(v);
    }
    if (s < stops) for (let i = 0; i < STOP_DWELL_S; i++) speeds.push(0);
  }
  return speeds;
}

export function simulate(c: Conditions, veh: Vehicle = DEFAULT_VEHICLE): Result {
  const m = veh.massKg + c.payloadKg;
  const rho = airDensity(c.ambientC);
  const crr = rollingCoeff(veh, c);
  const theta = Math.atan(c.gradePct / 100);
  const wind = c.headwindKmh / 3.6;
  const usableKwh = veh.capacityKwh * capacityFactor(c.ambientC);
  const aux = veh.auxBaseKw + hvacKw(c) + Math.max(0, c.auxExtraKw ?? 0);
  const speeds = buildCycle(c);

  const bd: Breakdown = { aero: 0, rolling: 0, grade: 0, inertia: 0, aux: 0, packLoss: 0, driveLoss: 0, regen: 0 };
  let kwh = 0, dist = 0, peakKw = 0, peakC = 0, prev = 0;
  let depletedAtKm: number | null = null;
  let soc = c.initialSocPct;
  const trace: TracePoint[] = [];
  const traceEvery = Math.max(1, Math.floor(speeds.length / 240));
  const J2KWH = 1 / 3.6e6;

  speeds.forEach((v, i) => {
    const acc = v - prev; // Δt = 1 s
    prev = v;
    const vAir = v + wind;
    const fAero = v > 0 ? 0.5 * rho * veh.cd * veh.frontalAreaM2 * vAir * Math.abs(vAir) : 0;
    const fRoll = v > 0 ? m * G * crr * Math.cos(theta) : 0;
    const fGrade = v > 0 ? m * G * Math.sin(theta) : 0;
    const fInert = m * 1.05 * acc; // 5 % rotating-mass allowance
    const pWheel = (fAero + fRoll + fGrade + fInert) * v; // W

    let pBatt: number;
    if (pWheel >= 0) {
      const capped = Math.min(pWheel, veh.maxMotorKw * 1000);
      pBatt = capped / veh.driveEff;
      bd.driveLoss += (pBatt - capped) * J2KWH;
    } else {
      const rec = Math.min(-pWheel * veh.regenEff, regenLimitKw(veh, c.ambientC, soc) * 1000);
      pBatt = -rec;
      bd.regen += rec * J2KWH;
    }
    pBatt += aux * 1000;
    const amps = pBatt / veh.packVoltage;
    const loss = amps * amps * veh.packResistanceOhm;
    pBatt += loss;

    if (pWheel > 0) {
      bd.aero += Math.max(0, fAero * v) * J2KWH;
      bd.rolling += fRoll * v * J2KWH;
      bd.grade += Math.max(0, fGrade * v) * J2KWH;
      bd.inertia += Math.max(0, fInert * v) * J2KWH;
    }
    bd.aux += aux * 1000 * J2KWH;
    bd.packLoss += loss * J2KWH;

    kwh += pBatt * J2KWH;
    dist += v;
    soc = c.initialSocPct - (kwh / usableKwh) * 100;
    if (soc <= 0 && depletedAtKm === null) depletedAtKm = dist / 1000;
    peakKw = Math.max(peakKw, pBatt / 1000);
    peakC = Math.max(peakC, pBatt / 1000 / veh.capacityKwh);
    if (i % traceEvery === 0 || i === speeds.length - 1)
      trace.push({ km: dist / 1000, soc: Math.max(0, soc), kmh: v * 3.6, kw: pBatt / 1000 });
  });

  const km = dist / 1000;
  const whPerKm = km > 0 ? (kwh * 1000) / km : 0;
  const result: Result = {
    inputs: { ...c },
    energyKwh: kwh,
    whPerKm,
    endSocPct: Math.max(0, soc),
    usableKwh,
    estRangeKm: whPerKm > 0 ? (usableKwh * 1000) / whPerKm : 0,
    durationMin: speeds.length / 60,
    avgKmh: speeds.length ? km / (speeds.length / 3600) : 0,
    peakKw,
    peakCRate: peakC,
    depletedAtKm,
    breakdownKwh: bd,
    trace,
    faults: [],
  };
  result.faults = evaluateFaults(result, veh);
  return result;
}

/** Rule-based fault/alert evaluation over the calculated result. */
export function evaluateFaults(r: Result, veh: Vehicle = DEFAULT_VEHICLE): Fault[] {
  const c = r.inputs;
  const f: Fault[] = [];
  if (r.depletedAtKm !== null)
    f.push({ id: 'depleted', severity: 'critical', title: 'Trip not feasible', detail: `Battery reaches 0 % at ${r.depletedAtKm.toFixed(1)} km of ${c.distanceKm} km.` });
  else if (r.endSocPct < 10)
    f.push({ id: 'low-soc', severity: 'critical', title: 'Critical arrival SOC', detail: `Arrival SOC ${r.endSocPct.toFixed(1)} % is below the 10 % reserve.` });
  else if (r.endSocPct < 20)
    f.push({ id: 'reserve', severity: 'warning', title: 'Low arrival SOC', detail: `Arrival SOC ${r.endSocPct.toFixed(1)} % is below the 20 % comfort reserve.` });
  if (r.peakKw >= veh.maxMotorKw / veh.driveEff * 0.98)
    f.push({ id: 'power-limit', severity: 'warning', title: 'Motor power limited', detail: `Demand reached the ${veh.maxMotorKw} kW motor limit; acceleration is being capped.` });
  if (r.peakCRate > 2)
    f.push({ id: 'c-rate', severity: 'warning', title: 'High discharge C-rate', detail: `Peak ${r.peakCRate.toFixed(2)} C exceeds the 2 C stress threshold.` });
  if (c.ambientC < 0)
    f.push({ id: 'cold', severity: 'warning', title: 'Cold pack', detail: `At ${c.ambientC} °C usable capacity drops to ${(capacityFactor(c.ambientC) * 100).toFixed(0)} % and regen is limited.` });
  if (c.ambientC > 40)
    f.push({ id: 'hot', severity: 'warning', title: 'Thermal derate risk', detail: `Ambient ${c.ambientC} °C may trigger pack cooling and power derate.` });
  if (c.tirePressureBar < 2.2)
    f.push({ id: 'tire', severity: 'warning', title: 'Low tyre pressure', detail: `${c.tirePressureBar.toFixed(1)} bar is below the 2.5 bar nominal, raising rolling resistance.` });
  if (c.initialSocPct > 90 && r.breakdownKwh.regen < 0.5 && c.gradePct < 0)
    f.push({ id: 'regen-full', severity: 'info', title: 'Regen restricted', detail: 'Pack is near full on a descent, so regenerative braking is limited.' });
  if (c.surface === 'snow' || c.surface === 'gravel')
    f.push({ id: 'surface', severity: 'info', title: 'Low-grip surface', detail: `${c.surface[0].toUpperCase() + c.surface.slice(1)} raises rolling resistance ${c.surface === 'snow' ? '2.2×' : '1.6×'} over dry asphalt.` });
  return f;
}

export interface Recommendation { title: string; detail: string; savingWhKm: number; savingPct: number }

/** Counterfactual recommendations: each one is a real re-simulation with one input changed. */
export function recommend(base: Result, veh: Vehicle = DEFAULT_VEHICLE): Recommendation[] {
  const c = base.inputs;
  const candidates: { title: string; why: string; patch: Partial<Conditions> }[] = [];
  if (c.cruiseKmh > 60) candidates.push({ title: `Cruise at ${c.cruiseKmh - 10} km/h`, why: 'Aero drag grows with the square of speed.', patch: { cruiseKmh: c.cruiseKmh - 10 } });
  if (c.style !== 'eco') candidates.push({ title: 'Switch to eco driving', why: 'Gentler acceleration reduces inertial losses and peak pack current.', patch: { style: 'eco' } });
  if (c.tirePressureBar < NOMINAL_TIRE_BAR) candidates.push({ title: `Inflate tyres to ${NOMINAL_TIRE_BAR} bar`, why: 'Under-inflation increases rolling resistance.', patch: { tirePressureBar: NOMINAL_TIRE_BAR } });
  if (c.hvac && Math.abs(c.ambientC - 21) > 6) candidates.push({ title: 'Precondition cabin while plugged in', why: 'Removes most of the HVAC load from the trip.', patch: { hvac: false } });
  if (c.payloadKg > 200) candidates.push({ title: `Reduce payload by ${Math.round(c.payloadKg / 2)} kg`, why: 'Mass affects rolling, grade and acceleration energy.', patch: { payloadKg: Math.round(c.payloadKg / 2) } });
  if (c.traffic === 'heavy') candidates.push({ title: 'Shift trip off-peak', why: 'Fewer stop–start cycles lose less energy to braking.', patch: { traffic: 'moderate' } });

  return candidates
    .map(({ title, why, patch }) => {
      const alt = simulate({ ...c, ...patch }, veh);
      const saving = base.whPerKm - alt.whPerKm;
      const rangeGain = alt.estRangeKm - base.estRangeKm;
      return {
        title,
        detail: `${why} Simulated: ${alt.whPerKm.toFixed(0)} Wh/km, range ${rangeGain >= 0 ? '+' : ''}${rangeGain.toFixed(0)} km.`,
        savingWhKm: saving,
        savingPct: base.whPerKm > 0 ? (saving / base.whPerKm) * 100 : 0,
      };
    })
    .filter((r) => r.savingPct >= 1)
    .sort((a, b) => b.savingWhKm - a.savingWhKm);
}
