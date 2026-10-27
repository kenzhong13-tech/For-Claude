// Print a built report (HTML) to an A4 PDF with headless Chromium.
// usage: node report_kit/make_pdf.mjs <report.html> <out.pdf> "<footer text>"
// env:   PLAYWRIGHT  module to import (default "playwright")
//        FONT_DIR    optional folder with @fontsource Noto Sans SC / Noto Serif SC unpacked as sans/package and
//                    serif/package; when set, these local fonts replace the Google Fonts link (for offline machines)
import fs from 'fs';

const [src, out, footer = ''] = process.argv.slice(2);
const { chromium } = (await import(process.env.PLAYWRIGHT || 'playwright')).default;
const F = process.env.FONT_DIR;
let body = fs.readFileSync(src, 'utf8');
let fonts = '';
if (F) {
  body = body.replace(/<link rel="(stylesheet|preconnect)"[^>]*>/g, '');
  fonts = ['sans/package/400.css', 'sans/package/500.css', 'sans/package/700.css', 'serif/package/600.css', 'serif/package/700.css']
    .map(p => `<link rel="stylesheet" href="file://${F}/${p}">`).join('');
}
// Chromium evaluates print media queries against the full A4 width (794px) but lays content out in the
// 703px between the 12mm margins, so render at a 794px viewport with a 703px body to match the printed layout.
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${fonts}
<style>:root{color-scheme:light}body{margin:0;width:703px}[hidden]{display:none!important}
@page{size:A4;margin:14mm 12mm 16mm}
@media print{.wrap{padding-left:0!important;padding-right:0!important;max-width:none}.mast .wrap{padding-block:6px 18px}main{padding-block:0}
section{padding-top:22px}figure{padding:10px 12px 8px}.tiles{break-inside:avoid}h2{break-after:avoid}h3{break-after:avoid}
body{font-size:10.5pt}.chart-box svg{max-width:100%;height:auto}.tbl-wrap{overflow:visible}table.tbl{font-size:11.5px}
.two:has(.tbl-wrap){grid-template-columns:minmax(0,1fr)!important}.tbl td.w{min-width:150px}
#tbl-events,#tbl-q,#tbl-cov{font-size:10.5px}#tbl-events th,#tbl-events td,#tbl-q th,#tbl-q td,#tbl-cov th,#tbl-cov td{padding:4px 4px}
.tbl th,.tbl td{padding:5px 8px}.keypoints li{padding:9px 12px 9px 46px}}
</style></head><body>${body}</body></html>`;
const tmp = out.replace(/\.pdf$/, '.print.html');
fs.writeFileSync(tmp, html);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 794, height: 1100 }, colorScheme: 'light' });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
await page.emulateMedia({ media: 'print', colorScheme: 'light' });
await page.goto('file://' + fs.realpathSync(tmp), { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(600);
const over = await page.evaluate(() => [...document.querySelectorAll('.tbl-wrap, figure, .card, .two > *')]
  .filter(e => e.scrollWidth > e.clientWidth + 2).map(e => (e.querySelector('table,[id]')?.id || e.className) + ':' + e.scrollWidth + '>' + e.clientWidth));
await page.pdf({
  path: out, format: 'A4', printBackground: true, preferCSSPageSize: true,
  displayHeaderFooter: true, headerTemplate: '<span></span>',
  footerTemplate: '<div style="width:100%;font-size:8px;color:#888;padding:0 12mm;display:flex;justify-content:space-between;font-family:sans-serif">'
    + `<span>${footer}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
});
await browser.close();
fs.unlinkSync(tmp);
console.log('pdf written:', out, '| overflowing blocks:', over, '| page errors:', errs);
