// Generates the app logo and every icon size from one SVG source, drawn after the CycleRing dial:
// a lap of the cycle with the period arc from 12 o'clock, the "so far" tint, the fertile window,
// today's dot and the forecast bubbles growing toward the next period.
// Usage: node scripts/generate-icons.cjs  (renders with Playwright's Chromium, which is not a project dependency)
const C = 512;
function pt(deg, r) { const a = (deg - 90) * Math.PI / 180; return [C + r * Math.cos(a), C + r * Math.sin(a)]; }
function arc(d0, d1, r) {
  const [x0, y0] = pt(d0, r), [x1, y1] = pt(d1, r);
  return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${d1 - d0 > 180 ? 1 : 0} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
}
// Each theme is the app's primary colour as the tile with the mark in its on-primary colour, so the logo
// flips with the theme just like the brand colour does. berry = light (#A62A57), rose = dark (#F28BA8).
const THEMES = {
  berry: {
    bg: '#A62A57', track: 'rgba(255,255,255,.2)', tint: 'rgba(255,255,255,.34)', period: '#FFFFFF',
    fertile: '#A8E8D3', bubble: '#FFFFFF', bubbleBase: '#A62A57', ink: '#2B2029', halo: '#FFFFFF',
  },
  rose: {
    bg: '#F28BA8', track: 'rgba(42,15,27,.16)', tint: 'rgba(42,15,27,.26)', period: '#2A0F1B',
    fertile: '#1F5244', bubble: '#2A0F1B', bubbleBase: '#F28BA8', ink: '#FFFFFF', halo: '#2A0F1B',
  },
};
function logo({ bg = 'square', scale = 1, simple = false, theme = 'berry' } = {}) {
  const k = THEMES[theme];
  const R = 318 * scale, W = (simple ? 150 : 124) * scale, FW = 34 * scale;
  const capDeg = (w, r) => (w / 2 / r) * 180 / Math.PI;
  const cap = capDeg(W, R);
  let s = '';
  if (bg === 'square') s += `<rect width="1024" height="1024" fill="${k.bg}"/>`;
  if (bg === 'rounded') s += `<rect width="1024" height="1024" rx="230" fill="${k.bg}"/>`;
  s += `<circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="${k.track}" stroke-width="${W}"/>`;
  if (!simple) {
    // "so far" tint behind the period
    s += `<path d="${arc(cap, 172, R)}" fill="none" stroke="${k.tint}" stroke-width="${W}" stroke-linecap="round"/>`;
  }
  // period arc: 12 o'clock, clockwise
  s += `<path d="${arc(cap, 100 - cap, R)}" fill="none" stroke="${k.period}" stroke-width="${W}" stroke-linecap="round"/>`;
  if (!simple) {
    // fertile window
    s += `<path d="${arc(132 + capDeg(FW, R), 200 - capDeg(FW, R), R)}" fill="none" stroke="${k.fertile}" stroke-width="${FW}" stroke-linecap="round"/>`;
    // forecast bubbles growing toward the next period
    [[284, 20, .3], [310, 32, .6], [337, 44, 1]].forEach(([d, r, f]) => {
      const [x, y] = pt(d, R);
      s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r * scale}" fill="${k.bubbleBase}"/>`;
      s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r * scale}" fill="${k.bubble}" fill-opacity="${f}" stroke="${k.bubble}" stroke-width="${8 * scale}"/>`;
    });
    // today
    const [tx, ty] = pt(172, R);
    s += `<circle cx="${tx}" cy="${ty}" r="${34 * scale}" fill="${k.ink}" stroke="${k.halo}" stroke-width="${14 * scale}"/>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">${s}</svg>`;
}
// Browser-tab icon: the simplified ring, switching to the dark-theme tile with the system colour scheme
function favicon() {
  const inner = (theme) => logo({ bg: 'rounded', simple: true, theme }).replace(/^<svg[^>]*>|<\/svg>$/g, '');
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
    + '<style>.d{display:none}@media (prefers-color-scheme:dark){.l{display:none}.d{display:inline}}</style>'
    + `<g class="l">${inner('berry')}</g><g class="d">${inner('rose')}</g></svg>`;
}
module.exports = { logo, favicon };
if (require.main === module) {
  const fs = require('fs');
  const path = require('path');
  const { chromium } = require('playwright');
  const out = path.join(__dirname, '..', 'public', 'assets', 'icons');
  const ios = [16, 20, 29, 32, 40, 50, 57, 58, 60, 64, 72, 76, 80, 87, 100, 114, 120, 128, 144, 152, 167, 180, 192, 256, 512, 1024];
  const android = [48, 72, 96, 144, 192, 512];
  const jobs = [
    // iOS masks the corners itself: full-bleed square, simplified ring when tiny
    ...ios.map((s) => [`ios/${s}.png`, s, logo({ simple: s <= 32 })]),
    // maskable: everything inside the 80% safe zone
    ...android.map((s) => [`android/android-launchericon-${s}-${s}.png`, s, logo({ scale: 0.78 })]),
    // in-app logo (navbar, sidebar, footer) and PNG favicon fallback, one per theme
    ['180_tp.png', 180, logo({ bg: 'rounded' })],
    ['180_tp_dark.png', 180, logo({ bg: 'rounded', theme: 'rose' })],
    ['logo.png', 1024, logo({ bg: 'rounded' })],
  ];
  fs.writeFileSync(path.join(out, 'logo.svg'), logo({ bg: 'rounded' }) + '\n');
  fs.writeFileSync(path.join(out, 'logo-dark.svg'), logo({ bg: 'rounded', theme: 'rose' }) + '\n');
  fs.writeFileSync(path.join(out, 'favicon.svg'), favicon() + '\n');
  (async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    for (const [file, size, svg] of jobs) {
      await page.setViewportSize({ width: size, height: size });
      await page.setContent(`<style>*{margin:0}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
      await page.screenshot({ path: path.join(out, file), omitBackground: true });
    }
    await browser.close();
  })();
}
