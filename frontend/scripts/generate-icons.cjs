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
function logo({ bg = 'square', scale = 1, simple = false, dark = false } = {}) {
  const k = {
    paper: dark ? '#17121A' : '#FAF6F2', surface: dark ? '#221A25' : '#FFFFFF',
    track: dark ? '#3A2F3F' : '#ECE3DD', period: dark ? '#F28BA8' : '#C0305B',
    tint: dark ? '#5A2A3C' : '#F1D3DC', fertile: dark ? '#7FD6B9' : '#2E6F5E', ink: dark ? '#F4ECEF' : '#2B2029',
  };
  const R = 318 * scale, W = (simple ? 150 : 124) * scale, FW = 34 * scale;
  const capDeg = (w, r) => (w / 2 / r) * 180 / Math.PI;
  const cap = capDeg(W, R);
  let s = '';
  if (bg === 'square') s += `<rect width="1024" height="1024" fill="${k.paper}"/>`;
  if (bg === 'rounded') s += `<rect width="1024" height="1024" rx="230" fill="${k.paper}"/>`;
  s += `<circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="${k.track}" stroke-width="${W}"/>`;
  s += `<circle cx="${C}" cy="${C}" r="${R - W / 2}" fill="${k.surface}"/>`;
  if (!simple) {
    // "so far" tint behind the period
    s += `<path d="${arc(cap, 172, R)}" fill="none" stroke="${k.tint}" stroke-width="${W}" stroke-linecap="round"/>`;
  }
  // period arc: 12 o'clock, clockwise
  s += `<path d="${arc(cap, 100 - cap, R)}" fill="none" stroke="${k.period}" stroke-width="${W}" stroke-linecap="round"/>`;
  if (!simple) {
    // fertile window + ovulation
    s += `<path d="${arc(132 + capDeg(FW, R), 200 - capDeg(FW, R), R)}" fill="none" stroke="${k.fertile}" stroke-width="${FW}" stroke-linecap="round"/>`;
    // forecast bubbles growing toward the next period
    [[284, 20, .3], [310, 32, .6], [337, 44, 1]].forEach(([d, r, f]) => {
      const [x, y] = pt(d, R);
      s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r * scale}" fill="${k.surface}"/>`;
      s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r * scale}" fill="${k.period}" fill-opacity="${f}" stroke="${k.period}" stroke-width="${8 * scale}"/>`;
    });
    // today
    const [tx, ty] = pt(172, R);
    s += `<circle cx="${tx}" cy="${ty}" r="${34 * scale}" fill="${k.ink}" stroke="${k.surface}" stroke-width="${14 * scale}"/>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">${s}</svg>`;
}
module.exports = { logo };
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
    ['180_tp.png', 180, logo({ bg: 'rounded' })],
    ['logo.png', 1024, logo({ bg: 'rounded' })],
  ];
  fs.writeFileSync(path.join(out, 'logo.svg'), logo({ bg: 'rounded' }) + '\n');
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
