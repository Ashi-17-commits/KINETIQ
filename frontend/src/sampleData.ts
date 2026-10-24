/**
 * ILLUSTRATIVE PLACEHOLDER DATA — for UI preview only.
 * Nothing here is measured, live, or produced by the simulation engine. Every view that
 * renders these values shows the "Illustrative sample data" badge. Replace with API data
 * once the backend endpoints exist.
 */

export interface ScenarioSample {
  id: 'A' | 'B'; name: string; tag: string; vehicle: string; battery: string;
  load: string; style: string; ac: string; route: string;
  distanceKm: number; energyKwh: number; rangeKm: number; travelMin: number; arrivalPct: number;
}

export const SCENARIOS: [ScenarioSample, ScenarioSample] = [
  { id: 'A', name: 'Scenario A – Base', tag: 'Current Setup', vehicle: 'Compact SUV EV', battery: '40 kWh', load: '2 people', style: 'Normal', ac: 'Moderate (20 °C)', route: 'Mumbai → Pune', distanceKm: 150, energyKwh: 32.5, rangeKm: 123, travelMin: 165, arrivalPct: 5 },
  { id: 'B', name: 'Scenario B', tag: 'Optimised Setup', vehicle: 'Compact SUV EV', battery: '40 kWh', load: '2 people', style: 'Eco', ac: 'Low (24 °C)', route: 'Mumbai → Pune', distanceKm: 150, energyKwh: 26.8, rangeKm: 148, travelMin: 170, arrivalPct: 18 },
];

export const INSIGHTS = {
  '7d': {
    kpis: { efficiency: 5.8, efficiencyDelta: 12, rangeKm: 248, avgKwh100: 17.2, arrivalPct: 18 },
    trend: [['Oct 18', 21.4], ['Oct 19', 19.6], ['Oct 20', 21.0], ['Oct 21', 19.8], ['Oct 22', 20.6], ['Oct 23', 19.1], ['Oct 24', 21.3]] as [string, number][],
  },
  '30d': {
    kpis: { efficiency: 5.5, efficiencyDelta: 6, rangeKm: 236, avgKwh100: 18.1, arrivalPct: 15 },
    trend: [['Sep 25', 19.2], ['Sep 29', 20.4], ['Oct 3', 18.6], ['Oct 7', 21.8], ['Oct 11', 19.4], ['Oct 15', 20.9], ['Oct 19', 18.8], ['Oct 24', 20.1]] as [string, number][],
  },
};

export const BREAKDOWN = [
  { label: 'Propulsion', pct: 68, color: '#6fd6e8' },
  { label: 'AC / Heating', pct: 18, color: '#cdb57e' },
  { label: 'Auxiliary Systems', pct: 8, color: '#7c8cf0' },
  { label: 'Elevation', pct: 6, color: '#e6a560' },
];

export const KEY_INSIGHTS = [
  { icon: 'leaf', title: 'Efficient Driving', text: 'Sample: energy efficiency improved by 12% this week.' },
  { icon: 'mountain', title: 'Route Profile', text: 'Sample: recent routes had notable elevation changes, raising consumption by ~8%.' },
  { icon: 'snow', title: 'AC Usage', text: 'Sample: AC accounts for 18% of total energy. Consider eco mode.' },
  { icon: 'spark', title: 'Potential Savings', text: 'Sample: up to 15% could be saved with smoother acceleration and lower AC usage.' },
];

export const RECOMMENDATIONS = [
  { icon: 'leaf', title: 'Use Eco Driving Mode', text: 'Gentler acceleration typically extends range.' },
  { icon: 'plug', title: 'Plan Charging Stops', text: 'Consider charging before long uphill routes.' },
  { icon: 'snow', title: 'Optimise AC Usage', text: 'Set AC to 24–26 °C for better efficiency.' },
  { icon: 'gauge', title: 'Check Tyre Pressure', text: 'Under-inflated tyres raise rolling resistance.' },
  { icon: 'clock', title: 'Travel Off-Peak', text: 'Fewer stop–start cycles mean less braking loss.' },
];

/** Illustrative route geometry only. Distance, gain, time and energy are derived from it
 *  (src/routeData.ts) and the active energy engine; none are stored here. */
export const ROUTE_SAMPLE = {
  start: 'Mumbai, MH', end: 'Pune, MH',
  elevation: [[0, 20], [12, 40], [25, 120], [38, 260], [50, 420], [62, 560], [72, 700], [80, 640], [92, 600], [104, 560], [116, 600], [126, 560], [138, 560], [150, 560]] as [number, number][],
  stations: [{ x: 38, y: 52, name: 'Sample station 1' }, { x: 66, y: 60, name: 'Sample station 2' }, { x: 84, y: 66, name: 'Sample station 3' }],
};
