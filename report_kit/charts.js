/* ---------- helpers ---------- */
const NS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function txt(parent, x, y, s, cls, anchor) {
  const t = sv('text', { x, y, class: cls || 'ax', 'text-anchor': anchor || 'start' }, parent);
  t.textContent = s;
  return t;
}
const pct = (v, d = 1) => (v === null || v === undefined || !isFinite(v)) ? '—' : (v * 100).toFixed(d) + '%';
const spct = (v, d = 1) => (v === null || v === undefined || !isFinite(v)) ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v * 100).toFixed(d) + '%';
const num = (v, d = 0) => (v === null || v === undefined || !isFinite(v)) ? '—' : (v < 0 ? '−' : '') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const usd = (v, d = 2) => '$' + num(v, d);
function niceTicks(min, max, n) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min, step0 = span / (n || 5);
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const e = step0 / mag;
  const step = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag;
  const lo = Math.floor(min / step + 1e-9) * step, hi = Math.ceil(max / step - 1e-9) * step;
  const out = [];
  for (let v = lo; v <= hi + step * 1e-6; v += step) out.push(+v.toFixed(10));
  return out;
}
function tipOf(el) {
  let t = el.querySelector(':scope > .tt');
  if (!t) { t = document.createElement('div'); t.className = 'tt'; t.hidden = true; el.appendChild(t); }
  return t;
}
function showTip(el, x, y, title, rows, desc) {
  const t = tipOf(el);
  t.replaceChildren();
  if (title) { const h = document.createElement('div'); h.className = 'tt-h'; h.textContent = title; t.appendChild(h); }
  rows.forEach(r => {
    const d = document.createElement('div'); d.className = 'tt-r';
    if (r.cls) { const k = document.createElement('span'); k.className = 'tt-k ' + r.cls; d.appendChild(k); }
    const b = document.createElement('b'); b.textContent = r.value; d.appendChild(b);
    if (r.label) { const l = document.createElement('span'); l.className = 'tt-l'; l.textContent = r.label; d.appendChild(l); }
    t.appendChild(d);
  });
  if (desc) { const p = document.createElement('div'); p.className = 'tt-desc'; p.textContent = desc; t.appendChild(p); }
  t.hidden = false;
  const W = el.clientWidth, tw = t.offsetWidth, th = t.offsetHeight;
  let left = x + 14; if (left + tw > W - 2) left = x - tw - 14; if (left < 2) left = Math.max(2, Math.min(W - tw - 2, x - tw / 2));
  let top = y - th - 10; if (top < 2) top = y + 14;
  t.style.left = left + 'px'; t.style.top = top + 'px';
}
function hideTip(el) { const t = el.querySelector(':scope > .tt'); if (t) t.hidden = true; }
function svgRoot(el, W, H, label) {
  el.replaceChildren();
  const s = sv('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': label || '' });
  el.appendChild(s);
  return s;
}
function shortDate(d) { return d.slice(2, 4) + '/' + d.slice(5, 7); }
function monthTicks(dates, iw) {
  const idx = [];
  for (let i = 1; i < dates.length; i++) if (dates[i].slice(5, 7) !== dates[i - 1].slice(5, 7)) idx.push(i);
  const maxLabels = Math.max(3, Math.floor(iw / 62));
  const step = Math.ceil(idx.length / maxLabels);
  return idx.filter((_, k) => k % step === 0);
}
function barPath(x, y0, y1, w, r) {
  const h = Math.abs(y1 - y0); r = Math.min(r, h, w / 2);
  if (h < 0.5) return `M${x},${y0}H${x + w}`;
  if (y1 < y0) return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`;
  return `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}Z`;
}

/* ---------- line chart (crosshair + tooltip, keyboard arrows) ---------- */
function lineChart(el, cfg) {
  const W = Math.max(280, el.clientWidth), H = cfg.height || 260;
  const narrow = W < 480;
  const m = { t: 12, r: cfg.r || 12, b: 28, l: cfg.l || (narrow ? 40 : 50) };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const n = cfg.x.length;
  const svg = svgRoot(el, W, H, cfg.aria);
  const vals = [];
  cfg.series.forEach(s => s.values.forEach(v => { if (v !== null && isFinite(v)) vals.push(v); }));
  let lo = cfg.yMin !== undefined ? cfg.yMin : Math.min(...vals);
  let hi = cfg.yMax !== undefined ? cfg.yMax : Math.max(...vals);
  let ys, ticks;
  if (cfg.ylog) {
    const a = Math.log10(lo * 0.92), b = Math.log10(hi * 1.06);
    ys = v => m.t + ih - (Math.log10(v) - a) / (b - a) * ih;
    ticks = cfg.logTicks.filter(t => t >= lo * 0.92 && t <= hi * 1.06);
  } else {
    ticks = niceTicks(lo, hi, narrow ? 4 : (cfg.yTicks || 5));
    const a = ticks[0], b = ticks[ticks.length - 1];
    ys = v => m.t + ih - (v - a) / (b - a) * ih;
  }
  const xs = i => m.l + (n <= 1 ? iw / 2 : i * iw / (n - 1));
  const g = sv('g', {}, svg);
  ticks.forEach(t => { const y = ys(t); sv('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: t === 0 && !cfg.ylog ? 'zero' : 'grid' }, g); txt(g, m.l - 6, y + 4, cfg.yfmt(t), 'ax', 'end'); });
  sv('line', { x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih, class: 'axl' }, g);
  const xt = cfg.labels ? cfg.labels.map((_, i) => i).filter((i) => i % Math.max(1, Math.ceil(n / Math.floor(iw / (narrow ? 44 : 56)))) === 0) : monthTicks(cfg.x, iw);
  xt.forEach(i => { const x = xs(i); sv('line', { x1: x, x2: x, y1: m.t + ih, y2: m.t + ih + 4, class: 'axl' }, g); txt(g, x, H - 8, cfg.labels ? cfg.labels[i] : shortDate(cfg.x[i]), 'ax', 'middle'); });
  (cfg.refs || []).forEach(r => { const y = ys(r.y); sv('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'ref' }, g); const left = r.side === 'left'; txt(g, left ? m.l + 4 : W - m.r - 2, y - 5, r.label, 'ax ref-t', left ? 'start' : 'end'); });
  cfg.series.forEach(s => {
    let d = '', pen = false, first = null, last = null;
    s.values.forEach((v, i) => { if (v === null || !isFinite(v)) { pen = false; return; } const x = xs(i), y = ys(v); d += (pen ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1); pen = true; if (first === null) first = i; last = i; });
    if (s.area && first !== null) {
      const base = cfg.ylog ? m.t + ih : ys(Math.max(ticks[0], Math.min(0, ticks[ticks.length - 1])));
      sv('path', { d: d + `L${xs(last).toFixed(1)},${base}L${xs(first).toFixed(1)},${base}Z`, class: s.area }, svg);
    }
    sv('path', { d, class: 'ln ' + s.cls + (s.thin ? ' thin' : '') }, svg);
    if (s.endLabel && last !== null) {
      sv('circle', { cx: xs(last), cy: ys(s.values[last]), r: 4, class: 'dot ' + s.cls }, svg);
    }
  });
  if (cfg.points) cfg.series.forEach(s => s.values.forEach((v, i) => { if (v !== null) sv('circle', { cx: xs(i), cy: ys(v), r: 4, class: 'dot ' + s.cls }, svg); }));
  const hl = sv('line', { class: 'xhair', y1: m.t, y2: m.t + ih, x1: 0, x2: 0, visibility: 'hidden' }, svg);
  const dots = cfg.series.map(s => sv('circle', { r: 4.5, class: 'dot ' + s.cls, cx: 0, cy: 0, visibility: 'hidden' }, svg));
  const markerLayer = sv('g', {}, svg);
  const ov = sv('rect', { x: m.l, y: m.t, width: iw, height: ih, class: 'ov' }, svg);
  svg.insertBefore(ov, markerLayer);
  let cur = n - 1;
  function show(i, py) {
    cur = i; const x = xs(i);
    hl.setAttribute('x1', x); hl.setAttribute('x2', x); hl.setAttribute('visibility', 'visible');
    const rows = [];
    cfg.series.forEach((s, k) => {
      const v = s.values[i];
      if (v === null || !isFinite(v)) { dots[k].setAttribute('visibility', 'hidden'); return; }
      dots[k].setAttribute('cx', x); dots[k].setAttribute('cy', ys(v)); dots[k].setAttribute('visibility', 'visible');
      rows.push({ cls: s.cls, value: (cfg.tfmt || cfg.yfmt)(v), label: s.label });
    });
    showTip(el, x, py === undefined ? m.t + 30 : py, cfg.labels ? cfg.labels[i] : cfg.x[i], rows);
  }
  function hide() { hideTip(el); hl.setAttribute('visibility', 'hidden'); dots.forEach(d => d.setAttribute('visibility', 'hidden')); }
  ov.addEventListener('pointermove', ev => { const r = svg.getBoundingClientRect(); const i = Math.max(0, Math.min(n - 1, Math.round((ev.clientX - r.left - m.l) / iw * (n - 1)))); show(i, ev.clientY - r.top); });
  ov.addEventListener('pointerleave', hide);
  svg.setAttribute('tabindex', '0');
  svg.addEventListener('focus', () => show(cur));
  svg.addEventListener('blur', hide);
  svg.addEventListener('keydown', ev => {
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') { ev.preventDefault(); const step = ev.shiftKey ? 10 : 1; show(Math.max(0, Math.min(n - 1, cur + (ev.key === 'ArrowLeft' ? -step : step)))); }
  });
  if (cfg.markers) {
    cfg.markers.forEach(mk => {
      const v = cfg.series[0].values[mk.i]; if (v === null) return;
      const cx = xs(mk.i), cy = ys(v) - (mk.up ? 14 : -14);
      sv('line', { x1: cx, x2: cx, y1: ys(v), y2: cy, class: 'xhair' }, markerLayer);
      const c = sv('circle', { cx, cy, r: narrow ? 6.5 : 8, class: 'mk ' + mk.cls, tabindex: 0, role: 'button', 'aria-label': mk.aria }, markerLayer);
      if (!narrow) { const t = txt(markerLayer, cx, cy + 3.3, String(mk.n), 'mk-t', 'middle'); }
      const open = () => showTip(el, cx, cy, mk.title, mk.rows, mk.desc);
      c.addEventListener('pointerenter', open); c.addEventListener('focus', open);
      c.addEventListener('pointerleave', () => hideTip(el)); c.addEventListener('blur', () => hideTip(el));
    });
  }
}

/* ---------- vertical bar chart (grouped, supports negatives) ---------- */
function barChart(el, cfg) {
  const W = Math.max(280, el.clientWidth), H = cfg.height || 240;
  const narrow = W < 480;
  // rotateNarrow: long category names are tilted on phones instead of colliding
  const rot = narrow && cfg.rotateNarrow;
  const m = { t: cfg.valueLabels ? 22 : 12, r: 10, b: rot ? 58 : 28, l: cfg.l || (narrow ? 40 : 50) };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const svg = svgRoot(el, W, H, cfg.aria);
  const all = []; cfg.series.forEach(s => s.values.forEach(v => { if (v !== null) all.push(v); }));
  const ticks = niceTicks(Math.min(0, ...all), Math.max(0, ...all), narrow ? 4 : 5);
  const a = ticks[0], b = ticks[ticks.length - 1];
  const ys = v => m.t + ih - (v - a) / (b - a) * ih;
  const g = sv('g', {}, svg);
  ticks.forEach(t => { const y = ys(t); sv('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: t === 0 ? 'zero' : 'grid' }, g); txt(g, m.l - 6, y + 4, cfg.yfmt(t), 'ax', 'end'); });
  const nc = cfg.labels.length, ns = cfg.series.length;
  const band = iw / nc;
  const bw = Math.max(3, Math.min(24, (band * 0.72 - (ns - 1) * 2) / ns));
  const gw = bw * ns + (ns - 1) * 2;
  const every = cfg.every || (rot ? 1 : Math.max(1, Math.ceil(nc / Math.floor(iw / (narrow ? 34 : 46)))));
  cfg.labels.forEach((lab, i) => {
    const cx = m.l + band * (i + 0.5);
    if (cfg.axisLabels) { if (cfg.axisLabels[i]) txt(g, m.l + band * i, H - 8, cfg.axisLabels[i], 'ax', 'middle'); }
    else if (rot) { const ly = H - m.b + 14; txt(g, cx + 4, ly, lab, 'ax', 'end').setAttribute('transform', `rotate(-40 ${cx + 4} ${ly})`); }
    else if (i % every === 0) txt(g, cx, H - 8, lab, 'ax', 'middle');
    cfg.series.forEach((s, k) => {
      const v = s.values[i]; if (v === null || v === undefined) return;
      const x = cx - gw / 2 + k * (bw + 2);
      const cls = typeof s.cls === 'function' ? s.cls(v, i) : s.cls;
      const p = sv('path', { d: barPath(x, ys(0), ys(v), bw, 4), class: 'bar ' + cls, tabindex: 0, role: 'img', 'aria-label': `${lab} ${s.label} ${cfg.tfmt(v)}` }, svg);
      const open = () => showTip(el, x + bw / 2, Math.min(ys(v), ys(0)), lab, [{ cls, value: cfg.tfmt(v), label: s.label }]);
      p.addEventListener('pointerenter', open); p.addEventListener('focus', open);
      p.addEventListener('pointerleave', () => hideTip(el)); p.addEventListener('blur', () => hideTip(el));
      if (cfg.valueLabels && (cfg.valueLabels === true || cfg.valueLabels(i, k)) && !narrow) {
        txt(svg, x + bw / 2, v >= 0 ? ys(v) - 5 : ys(v) + 13, cfg.vfmt ? cfg.vfmt(v) : cfg.tfmt(v), 'vlab', 'middle');
      }
    });
  });
}

/* ---------- horizontal bar chart (diverging around zero) ---------- */
function hbarChart(el, cfg) {
  const W = Math.max(280, el.clientWidth);
  const narrow = W < 480;
  const row = cfg.row || 22;
  const lw = Math.min(cfg.labelWidth || 150, W * (narrow ? 0.42 : 0.38));
  const m = { t: 8, r: 44, b: 24, l: lw + 8 };
  const H = m.t + m.b + row * cfg.items.length;
  const iw = W - m.l - m.r;
  const svg = svgRoot(el, W, H, cfg.aria);
  const vals = cfg.items.map(d => d.v);
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals), narrow ? 3 : 5);
  const a = ticks[0], b = ticks[ticks.length - 1];
  const xs = v => m.l + (v - a) / (b - a) * iw;
  const g = sv('g', {}, svg);
  const tickEvery = narrow && ticks.length > 4 ? 2 : 1;
  ticks.forEach((t, j) => { const x = xs(t); sv('line', { x1: x, x2: x, y1: m.t, y2: H - m.b, class: t === 0 ? 'zero' : 'grid' }, g); if (j % tickEvery === 0 || t === 0) txt(g, x, H - 7, cfg.fmt(t), 'ax', 'middle'); });
  cfg.items.forEach((d, i) => {
    const y = m.t + i * row, bh = Math.min(14, row - 6), yy = y + (row - bh) / 2;
    let lab = d.label;
    const maxChars = Math.floor(lw / 11.5);
    if (lab.length > maxChars) lab = lab.slice(0, maxChars - 1) + '…';
    txt(g, m.l - 8, y + row / 2 + 4, lab, 'lbl', 'end');
    const x0 = xs(0), x1 = xs(d.v);
    const left = Math.min(x0, x1), w = Math.max(1, Math.abs(x1 - x0));
    const r = Math.min(4, w / 2);
    const dpath = d.v >= 0
      ? `M${left},${yy}H${left + w - r}Q${left + w},${yy} ${left + w},${yy + r}V${yy + bh - r}Q${left + w},${yy + bh} ${left + w - r},${yy + bh}H${left}Z`
      : `M${left + w},${yy}H${left + r}Q${left},${yy} ${left},${yy + r}V${yy + bh - r}Q${left},${yy + bh} ${left + r},${yy + bh}H${left + w}Z`;
    const cls = d.cls || (d.v >= 0 ? 'fpos' : 'fneg');
    const p = sv('path', { d: dpath, class: 'bar ' + cls, tabindex: 0, role: 'img', 'aria-label': `${d.label} ${cfg.fmt(d.v)}` }, svg);
    const open = () => showTip(el, x1, y + 4, d.title || d.label, [{ cls, value: cfg.tfmt ? cfg.tfmt(d) : cfg.fmt(d.v), label: d.sub || '' }], d.desc);
    p.addEventListener('pointerenter', open); p.addEventListener('focus', open);
    p.addEventListener('pointerleave', () => hideTip(el)); p.addEventListener('blur', () => hideTip(el));
    // a long negative bar leaves no room before the category labels, so its value goes inside the bar
    if (d.v < 0 && x1 - m.l < 34 && w > 40) txt(svg, x1 + 5, y + row / 2 + 4, cfg.fmt(d.v), 'vlab-in', 'start');
    else txt(svg, d.v >= 0 ? x1 + 5 : x1 - 5, y + row / 2 + 4, cfg.fmt(d.v), 'vlab', d.v >= 0 ? 'start' : 'end');
  });
}

/* ---------- 100% stacked horizontal bars ---------- */
function stackChart(el, cfg) {
  const W = Math.max(280, el.clientWidth);
  const narrow = W < 480;
  const row = 34, lw = Math.min(170, W * 0.4);
  const m = { t: 6, r: 10, b: 22, l: lw + 8 };
  const H = m.t + m.b + row * cfg.items.length;
  const iw = W - m.l - m.r;
  const svg = svgRoot(el, W, H, cfg.aria);
  const g = sv('g', {}, svg);
  [0, 0.25, 0.5, 0.75, 1].forEach(t => { const x = m.l + t * iw; sv('line', { x1: x, x2: x, y1: m.t, y2: H - m.b, class: 'grid' }, g); txt(g, x, H - 6, (t * 100) + '%', 'ax', 'middle'); });
  cfg.items.forEach((d, i) => {
    const y = m.t + i * row + 8, bh = 18;
    txt(g, m.l - 8, y + 13, d.label, 'lbl', 'end');
    const w1 = d.share * iw;
    const p1 = sv('path', { d: `M${m.l},${y}H${m.l + w1 - 1}V${y + bh}H${m.l}Z`, class: 'bar f1', tabindex: 0, role: 'img', 'aria-label': `${d.label} 可解释 ${pct(d.share)}` }, svg);
    const p2 = sv('path', { d: `M${m.l + w1 + 1},${y}H${m.l + iw - 4}Q${m.l + iw},${y} ${m.l + iw},${y + 4}V${y + bh - 4}Q${m.l + iw},${y + bh} ${m.l + iw - 4},${y + bh}H${m.l + w1 + 1}Z`, class: 'bar fmid', tabindex: 0, role: 'img', 'aria-label': `${d.label} 特有 ${pct(1 - d.share)}` }, svg);
    [[p1, 'f1', d.share, '模型可解释'], [p2, 'fmid', 1 - d.share, '公司特有']].forEach(([p, cls, v, lab]) => {
      const open = () => showTip(el, m.l + (cls === 'f1' ? w1 / 2 : w1 + (iw - w1) / 2), y, d.label, [{ cls, value: pct(v), label: lab }]);
      p.addEventListener('pointerenter', open); p.addEventListener('focus', open);
      p.addEventListener('pointerleave', () => hideTip(el)); p.addEventListener('blur', () => hideTip(el));
    });
    if (w1 > 46) txt(svg, m.l + 6, y + 13, pct(d.share), 'vlab-in', 'start');
    else txt(svg, m.l + w1 + 6, y + 13, pct(d.share), 'vlab', 'start');
  });
}

/* ---------- scatter with fit line ---------- */
function scatterChart(el, cfg) {
  const W = Math.max(280, el.clientWidth), H = cfg.height || 280;
  const narrow = W < 480;
  const m = { t: 10, r: 12, b: 30, l: narrow ? 40 : 48 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const svg = svgRoot(el, W, H, cfg.aria);
  const xt = niceTicks(Math.min(...cfg.x), Math.max(...cfg.x), narrow ? 4 : 6), yt = niceTicks(Math.min(...cfg.y), Math.max(...cfg.y), narrow ? 4 : 6);
  const xs = v => m.l + (v - xt[0]) / (xt[xt.length - 1] - xt[0]) * iw;
  const ys = v => m.t + ih - (v - yt[0]) / (yt[yt.length - 1] - yt[0]) * ih;
  const g = sv('g', {}, svg);
  yt.forEach(t => { const y = ys(t); sv('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: t === 0 ? 'zero' : 'grid' }, g); txt(g, m.l - 6, y + 4, pct(t, 0), 'ax', 'end'); });
  xt.forEach(t => { const x = xs(t); sv('line', { x1: x, x2: x, y1: m.t, y2: m.t + ih, class: t === 0 ? 'zero' : 'grid' }, g); txt(g, x, H - 10, pct(t, 0), 'ax', 'middle'); });
  cfg.x.forEach((x, i) => sv('circle', { cx: xs(x), cy: ys(cfg.y[i]), r: 2.6, class: 'pt' }, svg));
  const x0 = xt[0], x1 = xt[xt.length - 1];
  const clipY = v => Math.max(yt[0], Math.min(yt[yt.length - 1], v));
  sv('line', { x1: xs(x0), y1: ys(clipY(cfg.a + cfg.b * x0)), x2: xs(x1), y2: ys(clipY(cfg.a + cfg.b * x1)), class: 'fit' }, svg);
  txt(svg, W - m.r - 4, m.t + 14, `β = ${cfg.b.toFixed(2)}`, 'lbl', 'end');
  const hit = sv('circle', { r: 6, cx: 0, cy: 0, class: 'dot c2', visibility: 'hidden' }, svg);
  const ov = sv('rect', { x: m.l, y: m.t, width: iw, height: ih, class: 'ov' }, svg);
  ov.addEventListener('pointermove', ev => {
    const r = svg.getBoundingClientRect(); const px = ev.clientX - r.left, py = ev.clientY - r.top;
    let best = -1, bd = 1e9;
    cfg.x.forEach((x, i) => { const dx = xs(x) - px, dy = ys(cfg.y[i]) - py, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } });
    if (best < 0 || bd > 900) { hideTip(el); hit.setAttribute('visibility', 'hidden'); return; }
    hit.setAttribute('cx', xs(cfg.x[best])); hit.setAttribute('cy', ys(cfg.y[best])); hit.setAttribute('visibility', 'visible');
    showTip(el, xs(cfg.x[best]), ys(cfg.y[best]), cfg.dates[best], [{ cls: 'c1', value: spct(cfg.y[best]), label: cfg.yName || '个股超额收益' }, { cls: 'c2', value: spct(cfg.x[best]), label: cfg.xName || '基准超额收益' }]);
  });
  ov.addEventListener('pointerleave', () => { hideTip(el); hit.setAttribute('visibility', 'hidden'); });
}


/* ---------- multi-part 100% stacked horizontal bars ---------- */
function stackMulti(el, cfg) {
  const W = Math.max(280, el.clientWidth);
  const row = 34, lw = Math.min(cfg.labelWidth || 90, W * 0.3);
  const m = { t: 6, r: 10, b: 22, l: lw + 8 };
  const H = m.t + m.b + row * cfg.rows.length;
  const iw = W - m.l - m.r;
  const svg = svgRoot(el, W, H, cfg.aria);
  const g = sv('g', {}, svg);
  [0, 0.25, 0.5, 0.75, 1].forEach(t => { const x = m.l + t * iw; sv('line', { x1: x, x2: x, y1: m.t, y2: H - m.b, class: 'grid' }, g); txt(g, x, H - 6, (t * 100) + '%', 'ax', 'middle'); });
  cfg.rows.forEach((r, i) => {
    const y = m.t + i * row + 8, bh = 18;
    txt(g, m.l - 8, y + 13, r.label, 'lbl', 'end');
    const tot = r.parts.reduce((a, p) => a + p.v, 0);
    let x = m.l;
    r.parts.forEach((p, k) => {
      const w = p.v / tot * iw;
      const gap = k < r.parts.length - 1 ? 2 : 0;
      const rect = sv('rect', { x: x, y: y, width: Math.max(0.5, w - gap), height: bh, class: 'bar ' + p.cls, tabindex: 0, role: 'img', 'aria-label': `${r.label} ${p.name} ${pct(p.v / tot)}` }, svg);
      const cx = x + w / 2;
      const open = () => showTip(el, cx, y, r.label, [{ cls: p.cls, value: pct(p.v / tot), label: p.name + (cfg.vfmt ? '（' + cfg.vfmt(p.v) + '）' : '') }]);
      rect.addEventListener('pointerenter', open); rect.addEventListener('focus', open);
      rect.addEventListener('pointerleave', () => hideTip(el)); rect.addEventListener('blur', () => hideTip(el));
      if (w > 42) txt(svg, x + 5, y + 13, pct(p.v / tot, 0), 'vlab-in' + (p.cls === 'f3' || p.cls === 'f4' ? ' dark' : ''), 'start');
      x += w;
    });
  });
}
