/** Tiny dependency-free SVG chart builders shared by Scenarios, Insights and Path Planning. */
const fmt = (n: number, d = 0) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

/** Axis max that splits into 4 round steps (e.g. 37 → 40, 700 → 800). */
function niceMax(v: number) {
  const raw = Math.max(v, 1) / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? raw;
  return Math.ceil(v / step) * step === v ? v : step * 4 >= v ? step * 4 : Math.ceil(v / step) * step;
}

/** Vertical bars with value labels. */
export function barChart(bars: { label: string; sub?: string; value: number; color: string }[], unit: string, aria: string) {
  const W = 420, H = 230, L = 40, B = 42, T = 26;
  const max = niceMax(Math.max(...bars.map((b) => b.value)) * 1.15);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const slot = (W - L - 10) / bars.length, bw = Math.min(64, slot * 0.5);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => max * f);
  return `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" role="img" aria-label="${aria}">
    ${ticks.map((t) => `<line x1="${L}" x2="${W - 6}" y1="${y(t)}" y2="${y(t)}" class="c-grid"/><text x="${L - 8}" y="${y(t) + 4}" text-anchor="end" class="c-ax">${fmt(t)}</text>`).join('')}
    ${bars.map((b, i) => {
      const cx = L + slot * (i + 0.5), top = y(b.value);
      return `<rect x="${cx - bw / 2}" y="${top}" width="${bw}" height="${y(0) - top}" rx="3" fill="${b.color}" class="c-bar"/>
        <text x="${cx}" y="${top - 7}" text-anchor="middle" class="c-val">${fmt(b.value, b.value % 1 ? 1 : 0)} ${unit}</text>
        <text x="${cx}" y="${H - 22}" text-anchor="middle" class="c-lab">${b.label}</text>
        ${b.sub ? `<text x="${cx}" y="${H - 8}" text-anchor="middle" class="c-ax">${b.sub}</text>` : ''}`;
    }).join('')}</svg>`;
}

/** Line (optionally filled) over labelled x positions. */
export function lineChart(points: { x: string; y: number }[], opts: { unit: string; aria: string; area?: boolean; color?: string; yMax?: number; height?: number }) {
  const W = 520, H = opts.height ?? 200, L = 40, B = 24, T = 10, R = 12;
  const max = opts.yMax ?? niceMax(Math.max(...points.map((p) => p.y)) * 1.1);
  const x = (i: number) => L + (i / Math.max(points.length - 1, 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const color = opts.color ?? 'var(--cyan)';
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join('');
  const every = Math.ceil(points.length / 7);
  return `<svg viewBox="0 0 ${W} ${H}" class="chart-svg" role="img" aria-label="${opts.aria}">
    ${[0, 0.25, 0.5, 0.75, 1].map((f) => `<line x1="${L}" x2="${W - R}" y1="${y(max * f)}" y2="${y(max * f)}" class="c-grid"/><text x="${L - 8}" y="${y(max * f) + 4}" text-anchor="end" class="c-ax">${fmt(max * f)}${f === 1 ? ` ${opts.unit}` : ''}</text>`).join('')}
    ${points.map((p, i, a) => ((i % every === 0 && a.length - 1 - i >= every) || i === a.length - 1 ? `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" class="c-ax">${p.x}</text>` : '')).join('')}
    ${opts.area ? `<path d="${d}L${x(points.length - 1)},${y(0)}L${x(0)},${y(0)}Z" fill="${color}" opacity="0.12"/>` : ''}
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2" class="c-line"/>
    ${opts.area ? '' : points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.y)}" r="3" fill="${color}"/>`).join('')}</svg>`;
}

/** Donut with centre label. */
export function donut(segs: { label: string; pct: number; color: string }[], centre: string, sub: string) {
  const r = 42, C = 2 * Math.PI * r;
  let off = 0;
  return `<svg viewBox="0 0 120 120" class="donut" role="img" aria-label="${segs.map((s) => `${s.label} ${s.pct}%`).join(', ')}">
    <circle cx="60" cy="60" r="${r}" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="14"/>
    ${segs.map((s) => { const len = (s.pct / 100) * C; const el = `<circle cx="60" cy="60" r="${r}" fill="none" stroke="${s.color}" stroke-width="14" stroke-dasharray="${len - 1.5} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 60 60)"/>`; off += len; return el; }).join('')}
    <text x="60" y="60" text-anchor="middle" class="d-v">${centre}</text><text x="60" y="75" text-anchor="middle" class="d-s">${sub}</text></svg>`;
}
