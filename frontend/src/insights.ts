import './styles.css';
import './simulator.css';
import './pages.css';
import { renderSidebar, SAMPLE_BADGE, icon } from './shell.ts';
import { lineChart, donut } from './charts.ts';
import { INSIGHTS, BREAKDOWN, KEY_INSIGHTS, RECOMMENDATIONS } from './sampleData.ts';

renderSidebar('insights');
document.getElementById('badge')!.innerHTML = SAMPLE_BADGE;

function render(period: keyof typeof INSIGHTS) {
  const { kpis, trend } = INSIGHTS[period];
  const k: [string, string, string, string, string][] = [
    ['spark', 'Energy Efficiency', `${kpis.efficiency}`, 'km/kWh', `↑ ${kpis.efficiencyDelta}%`],
    ['battery', 'Estimated Range', `${kpis.rangeKm}`, 'km', ''],
    ['wave', 'Avg. Energy Consumption', `${kpis.avgKwh100}`, 'kWh/100km', ''],
    ['plug', 'Predicted Arrival Battery', `${kpis.arrivalPct}`, '%', ''],
  ];
  document.getElementById('ins-kpis')!.innerHTML = k.map(([ic, l, v, u, d], i) => `
    <div class="ikpi${i === 0 ? ' is-hl' : ''}"><span class="ikpi-ic">${icon(ic)}</span><div><span class="ikpi-l">${l}</span>
    <span class="ikpi-v">${v}<small>${u}</small>${d ? `<em>${d}</em>` : ''}</span></div></div>`).join('');
  document.getElementById('trend')!.innerHTML = lineChart(trend.map(([x, y]) => ({ x, y })), {
    unit: '', yMax: 40, height: 220, aria: 'Energy consumption trend (illustrative sample)',
  });
}

document.getElementById('mix')!.innerHTML = donut(BREAKDOWN, '100%', 'Total Energy') +
  `<ul class="mix-legend">${BREAKDOWN.map((b) => `<li><i style="background:${b.color}"></i>${b.label}<b>${b.pct}%</b></li>`).join('')}</ul>`;
document.getElementById('key-insights')!.innerHTML = KEY_INSIGHTS.map((x) => `<li><span class="ki-ic">${icon(x.icon)}</span><div><b>${x.title}</b><p>${x.text}</p></div></li>`).join('');

const list = document.getElementById('rec-list')!;
const btn = document.getElementById('view-all')!;
const drawRecs = (all: boolean) => {
  list.innerHTML = RECOMMENDATIONS.slice(0, all ? undefined : 3).map((r) => `<li><span class="ki-ic">${icon(r.icon)}</span><div><b>${r.title}</b><p>${r.text}</p></div></li>`).join('');
  btn.textContent = all ? 'Show Less' : 'View All';
  btn.setAttribute('aria-expanded', String(all));
};
btn.addEventListener('click', () => drawRecs(btn.getAttribute('aria-expanded') !== 'true'));
drawRecs(false);

const period = document.getElementById('period') as HTMLSelectElement;
period.addEventListener('change', () => render(period.value as keyof typeof INSIGHTS));
render('7d');
