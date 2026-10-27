// Render a built report the way readers see it and report layout problems.
// usage: node report_kit/shot.mjs <report.html> <outdir> [selector ...]
//   Full-page screenshots at desktop-light (1280px) and phone-dark (400px), plus 2x element shots for each selector
//   (e.g. "#ch-price" "#tbl-risk") at both widths. Prints, per width: empty charts, table row counts, elements wider
//   than the viewport, and console / page errors.
// env: PLAYWRIGHT module to import (default "playwright"; in Claude cloud sessions /opt/node-tools/node_modules/playwright/index.js)
import fs from 'fs';
import path from 'path';

const [src, outArg, ...sels] = process.argv.slice(2);
if (!src || !outArg) { console.error('usage: node shot.mjs <report.html> <outdir> [selector ...]'); process.exit(1); }
const out = path.resolve(outArg);
fs.mkdirSync(out, { recursive: true });
const { chromium } = (await import(process.env.PLAYWRIGHT || 'playwright')).default;
// the page is a fragment (the artifact host adds the document skeleton); wrap it the same way
const body = fs.readFileSync(src, 'utf8');
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><style>:root{color-scheme:light dark}body{margin:0}[hidden]{display:none!important}</style></head><body>${body}</body></html>`;
const wrapped = path.join(out, 'wrapped.html');
fs.writeFileSync(wrapped, html);
const browser = await chromium.launch();
let problems = 0;
for (const [name, w, scheme] of [['desktop-light', 1280, 'light'], ['phone-dark', 400, 'dark']]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text()); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await page.goto('file://' + wrapped, { waitUntil: 'load' });
  await page.waitForTimeout(900);
  const info = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth + ' / ' + document.documentElement.clientWidth,
    height: document.documentElement.scrollHeight,
    emptyCharts: [...document.querySelectorAll('.chart-box')].filter(e => !e.closest('[hidden]') && !e.querySelector('svg')).map(e => e.id),
    tables: [...document.querySelectorAll('table.tbl')].filter(t => !t.closest('[hidden]')).map(t => (t.id || '-') + ':' + t.querySelectorAll('tbody tr').length),
    tooWide: [...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1 && !e.closest('.tbl-wrap') && !e.closest('.formula') && !e.closest('[hidden]')).slice(0, 8).map(e => e.tagName + '.' + e.className + '#' + e.id + ' ' + Math.round(e.getBoundingClientRect().right)),
    placeholders: (document.body.innerText.match(/【[^】]*】/g) || []).length,
  }));
  if (info.emptyCharts.length || info.tooWide.length || errs.length) problems++;
  console.log(name, JSON.stringify(info));
  if (errs.length) console.log('  errors:', errs.slice(0, 10));
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: true });
  for (const s of sels) {
    const ctx2 = await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, deviceScaleFactor: 2 });
    const p2 = await ctx2.newPage();
    await p2.goto('file://' + wrapped, { waitUntil: 'load' });
    await p2.waitForTimeout(700);
    const e = await p2.$(s);
    if (!e) console.log('  missing selector', s);
    else { await e.scrollIntoViewIfNeeded(); await e.screenshot({ path: path.join(out, `el-${name}-${s.replace(/[^a-z0-9]+/gi, '_')}.png`) }); }
    await ctx2.close();
  }
  await ctx.close();
}
await browser.close();
console.log(problems ? `check the issues above; screenshots in ${out}` : `no layout errors; screenshots in ${out}`);
