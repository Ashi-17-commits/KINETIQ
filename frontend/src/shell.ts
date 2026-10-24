/** Shared sidebar for the dashboard pages (same markup/classes as the Simulator sidebar). */
export type NavKey = 'simulator' | 'scenarios' | 'insights';

const ICONS = {
  home: '<path d="M3 11 12 4l9 7v9h-6v-6H9v6H3z"/>',
  simulator: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  scenarios: '<path d="M4 6h16M4 12h10M4 18h6"/>',
  insights: '<path d="M12 3a6 6 0 0 0-3.5 10.9V17h7v-3.1A6 6 0 0 0 12 3zM9.5 21h5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.5v.01"/>',
};
const link = (href: string, icon: keyof typeof ICONS, label: string, active: boolean) =>
  `<a href="${href}"${active ? ' class="active" aria-current="page"' : ''}><svg viewBox="0 0 24 24">${ICONS[icon]}</svg>${label}</a>`;

export function renderSidebar(active: NavKey) {
  const aside = document.querySelector<HTMLElement>('aside.side')!;
  aside.innerHTML = `
    <a class="side-brand" href="/" aria-label="KINETIQ home"><span class="brand-mark" aria-hidden="true"><i></i><i></i></span>KINETIQ</a>
    <nav class="side-nav">
      ${link('/', 'home', 'Home', false)}
      ${link('/simulator/', 'simulator', 'Simulator', active === 'simulator')}
      ${link('/scenarios/', 'scenarios', 'Scenarios', active === 'scenarios')}
      ${link('/insights/', 'insights', 'Insights', active === 'insights')}
    </nav>
    <nav class="side-foot">${link('/#about', 'help', 'Help', false)}</nav>`;
}

/** Badge shown on every view that renders placeholder figures. */
export const SAMPLE_BADGE = '<span class="sample-badge" title="Placeholder values for UI preview. Not live data and not calculated.">Illustrative sample data</span>';

const GLYPHS: Record<string, string> = {
  leaf: '<path d="M5 19C5 10 11 5 20 4c-1 9-6 15-15 15z"/><path d="M5 19 13 11"/>',
  mountain: '<path d="m3 19 6-9 4 5 3-3 5 7z"/>',
  snow: '<path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9"/>',
  spark: '<path d="M13 2 5 14h6l-1 8 8-12h-6z"/>',
  plug: '<path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 0 1-10 0zM12 16v5"/>',
  gauge: '<path d="M4 16a8 8 0 1 1 16 0"/><path d="m12 16 4-5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  battery: '<rect x="6" y="5" width="12" height="16" rx="2"/><path d="M10 2.5h4M9 13h6"/>',
  wave: '<path d="m3 15 4-5 4 3 4-6 6 7"/>',
  pin: '<path d="M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
  route: '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7"/>',
  warn: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.01"/>',
  car: '<path d="M4 15l1.6-5a2 2 0 0 1 1.9-1.4h9a2 2 0 0 1 1.9 1.4L20 15v3h-2.5M4 15v3h2.5M4 15h16"/><circle cx="8" cy="18" r="1.6"/><circle cx="16" cy="18" r="1.6"/>',
};
export const icon = (name: string) => `<svg viewBox="0 0 24 24" class="ic" aria-hidden="true">${GLYPHS[name] ?? GLYPHS.spark}</svg>`;
