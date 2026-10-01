#!/usr/bin/env node
/**
 * verify_overview_charts.js — ad-hoc-Verifikation (Node, kein npm):
 * Führt den Seiten-<script>-Block aus src/content/index.html in node:vm
 * mit Stubs aus und prüft, dass die E3-Charts gegen
 * tests/fixtures/overview_small.json rendern.
 *
 * Run: node tests/verify_overview_charts.js   → alle PASS / exit 1 bei FAIL
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'src', 'content', 'index.html');
const FIXTURE = path.join(__dirname, 'fixtures', 'overview_small.json');

let PASS = 0, FAIL = 0;
function check(name, cond, detail) {
  if (cond) { PASS++; console.log('  PASS  ' + name); }
  else { FAIL++; console.log('  FAIL  ' + name + (detail ? '  ' + detail : '')); }
}

// ── 1. Seiten-Script extrahieren ─────────────────────────────
const raw = fs.readFileSync(SRC, 'utf8');
const blocks = [];
let pos = 0;
while (true) {
  const i = raw.indexOf('<script', pos);
  if (i < 0) break;
  const gt = raw.indexOf('>', i);
  const end = raw.indexOf('</script>', gt);
  if (gt < 0 || end < 0) break;
  blocks.push({ attrs: raw.slice(i + 7, gt), body: raw.slice(gt + 1, end) });
  pos = end + 9;
}
const pageBlocks = blocks.filter((b) => !/\bsrc=/.test(b.attrs) && b.body.trim().length > 0);
check('genau 1 ausführbarer inline <script>-Block gefunden', pageBlocks.length === 1,
  'gefunden: ' + pageBlocks.length);

// ── 2. Stubs ─────────────────────────────────────────────────
function makeEl(key) {
  return {
    key, id: key, tagName: 'DIV',
    innerHTML: '', textContent: '', className: '',
    style: {}, dataset: {}, children: [],
    clientWidth: 800, clientHeight: 300,
    insertAdjacentHTML(position, html) { this._adjacent = (this._adjacent || '') + html; },
    appendChild(c) { this.children.push(c); return c; },
    remove() {},
    addEventListener() {},
    querySelector() { return makeEl(key + '>' + arguments[0]); },
    querySelectorAll() { return []; },
  };
}

const byId = new Map();      // id → Element-Stub (stabil)
const bySel = new Map();     // querySelector-Selektor → Stub (stabil, für Captures)
const documentStub = {
  getElementById(id) {
    if (!byId.has(id)) byId.set(id, makeEl('#' + id));
    return byId.get(id);
  },
  querySelector(sel) {
    if (!bySel.has(sel)) bySel.set(sel, makeEl(sel));
    return bySel.get(sel);
  },
  querySelectorAll() { return []; },
  addEventListener() {},
  createElement(tag) { return makeEl('<' + tag + '>'); },
};

const windowStub = {
  location: { origin: 'https://hermes.local' },
  addEventListener() {},
  lucide: { createIcons() {} },
};
const fixture = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
const fetchCalls = [];
function fetchStub(url, opts) {
  fetchCalls.push({ url, opts });
  return Promise.resolve({ ok: true, status: 200, json() { return Promise.resolve(fixture); } });
}

// LightweightCharts-Stub: createChart zählen, Serien + setData sammeln
const charts = [];
function makeChart(container, opts) {
  const priceScales = {};
  const chart = { container, opts, series: [], priceScales,
    applyOptions(o) { Object.assign(chart.opts, o || {}); },
    remove() {} };
  chart.priceScale = (id) => {
    if (!priceScales[id]) {
      priceScales[id] = { id, opts: {}, applyOptions(o) { Object.assign(this.opts, o || {}); } };
    }
    return priceScales[id];
  };
  chart.timeScale = () => ({ fitContent() { chart._fitContentCalls = (chart._fitContentCalls || 0) + 1; } });
  const addSeries = (kind) => (sopts) => {
    const s = { kind, opts: sopts, data: [] };
    s.setData = (d) => { s.data = d; };
    s.setMarkers = () => {};
    s.update = () => {};
    s.applyOptions = () => {};
    chart.series.push(s);
    return s;
  };
  chart.addLineSeries = addSeries('line');
  chart.addHistogramSeries = addSeries('histogram');
  return chart;
}
const LightweightChartsStub = {
  createChart(container, opts) {
    const c = makeChart(container, opts);
    charts.push(c);
    return c;
  },
};
windowStub.LightweightCharts = LightweightChartsStub;

// ── 3. Script in vm ausführen ────────────────────────────────
const sandbox = {
  document: documentStub,
  window: windowStub,
  lucide: windowStub.lucide,
  LightweightCharts: LightweightChartsStub,
  fetch: fetchStub,
  setInterval: () => 0,
  clearInterval: () => {},
  console,
};
vm.createContext(sandbox);
let threw = null;
try {
  vm.runInContext(pageBlocks[0].body, sandbox, { filename: 'index.html:inline' });
} catch (e) {
  threw = e;
}

// ── 4. Assertions nach dem Promise-Zyklus ────────────────────
setTimeout(() => {
  console.log('\nverify_overview_charts.js — ad-hoc-Verifikation');
  console.log('='.repeat(60));

  check('(f) Seiten-Script ohne Exception ausgeführt', threw === null,
    threw ? (threw.stack || String(threw)).split('\n').slice(0, 3).join(' | ') : '');

  const corrHtml = byId.has('chart-corr') ? byId.get('chart-corr').innerHTML : '';
  const monthlyHtml = byId.has('chart-monthly') ? byId.get('chart-monthly').innerHTML : '';
  const fleetHtml = bySel.has('#fleet-table tbody') ? bySel.get('#fleet-table tbody').innerHTML : '';
  const equityHtml = byId.has('chart-equity') ? byId.get('chart-equity').innerHTML : '';
  const pnlHtml = byId.has('chart-pnl-daily') ? byId.get('chart-pnl-daily').innerHTML : '';

  // (a) 2 createChart-Aufrufe, je Chart ≥1 Serie mit nicht-leerem setData
  check('(a) 2 createChart-Aufrufe (Equity + PnL-Daily)', charts.length === 2, 'ist: ' + charts.length);
  check('(a) Equity-Chart hat ≥1 Serie mit nicht-leerem setData',
    charts.length > 0 && charts[0].series.some((s) => s.data && s.data.length > 0),
    charts.length ? charts[0].series.map((s) => s.kind + ':' + s.data.length).join(', ') : 'kein Chart');
  check('(a) PnL-Daily-Chart hat ≥1 Serie mit nicht-leerem setData',
    charts.length > 1 && charts[1].series.some((s) => s.data && s.data.length > 0),
    charts.length > 1 ? charts[1].series.map((s) => s.kind + ':' + s.data.length).join(', ') : 'kein Chart');
  check('(a) PnL-Daily ist Histogram-Serie', charts.length > 1 && charts[1].series.some((s) => s.kind === 'histogram'));

  // (b) Equity-Serien == 2 Bots + 1 Gesamt
  const lineSeries = charts.length ? charts[0].series.filter((s) => s.kind === 'line') : [];
  check('(b) Equity-Linien-Serien == 2 Bots + 1 Gesamt == 3', lineSeries.length === 3, 'ist: ' + lineSeries.length);
  const total = lineSeries.length ? lineSeries[0] : null;
  check('(b) Gesamt-Serie nutzt total_equity_curve (4 Punkte)', !!total && total.data.length === 4,
    total ? 'ist: ' + total.data.length : 'keine Serie');

  // (b2) Zwei Maßstäbe (Fix 2026-10-01): Gesamt auf eigener linker Achse,
  //      Bot-Serien bleiben auf der Standard-Achse (rechts).
  check('(b2) Gesamt-Serie nutzt priceScaleId "left"', !!total && total.opts.priceScaleId === 'left',
    total ? 'ist: ' + total.opts.priceScaleId : 'keine Serie');
  const eqChart = charts.length ? charts[0] : null;
  check('(b2) Equity-Chart: linke Preisachse sichtbar konfiguriert',
    !!eqChart && eqChart.opts.leftPriceScale && eqChart.opts.leftPriceScale.visible === true,
    eqChart ? JSON.stringify(eqChart.opts.leftPriceScale) : 'kein Chart');
  check('(b2) Bot-Serien ohne eigene Skala (rechts, Default)',
    lineSeries.length === 3 && lineSeries.slice(1).every((s) => s.opts.priceScaleId === undefined));
  check('(b2) priceScale("left") gestylt (textColor gesetzt)',
    !!eqChart && !!eqChart.priceScales['left'] && eqChart.priceScales['left'].opts.textColor !== undefined);

  // (b3) Zeitachse (Feedback 01.10.): genau EIN fitContent beim ersten Render
  check('(b3) fitContent genau 1× beim ersten Render (volle Zeitachse)',
    !!eqChart && eqChart._fitContentCalls === 1,
    eqChart ? 'calls: ' + (eqChart._fitContentCalls || 0) : 'kein Chart');

  // (c) #chart-corr: 3×3 Zellen
  const corrCells = (corrHtml.match(/class="corr-cell/g) || []).length;
  check('(c) #chart-corr enthält 3×3 Zellen', corrCells === 9, 'ist: ' + corrCells);

  // (d) #chart-monthly: 3 Monate × 3 Balken
  const rects = (monthlyHtml.match(/<rect/g) || []).length;
  const months = new Set((monthlyHtml.match(/data-month="[^"]+"/g) || []).map((m) => m)).size;
  check('(d) #chart-monthly enthält 9 Balken (3 Monate × 3)', rects === 9, 'ist: ' + rects);
  check('(d) #chart-monthly enthält 3 verschiedene Monate', months === 3, 'ist: ' + months);

  // (e) Sparkline-SVGs == 2 (eine je Bot in der Fleet-Tabelle)
  const sparks = (fleetHtml.match(/class="spark"/g) || []).length;
  check('(e) 2 Sparkline-SVGs in der Fleet-Tabelle', sparks === 2, 'ist: ' + sparks);
  check('(e) Fleet-Tabelle ohne colspan="12"', !fleetHtml.includes('colspan="12"'));

  // defensive Pfad-Checks (kein Crash bei Hinweistexten)
  check('kein Fehler-/Guard-Hinweis im Equity-Chart (Lib-Stub geladen)',
    equityHtml.length === 0 || equityHtml.includes('ov-legend') || !equityHtml.includes('nicht geladen'));
  check('kein Fehler-/Guard-Hinweis im PnL-Daily-Chart', !pnlHtml.includes('nicht geladen'));
  check('fetch wurde mit overview.json aufgerufen',
    fetchCalls.length >= 1 && fetchCalls[0].url.includes('/api/overview/overview.json'));

  // (g) Gates-Strip (A+B, 2026-10-01): Markt + Release + Nächster Block + Skips
  const mktHtml = byId.has('gate-market') ? byId.get('gate-market').innerHTML : '';
  const relHtml = byId.has('gate-release') ? byId.get('gate-release').innerHTML : '';
  const nxtHtml = byId.has('gate-next') ? byId.get('gate-next').innerHTML : '';
  const blkHtml = byId.has('gate-blocks') ? byId.get('gate-blocks').innerHTML : '';
  check('(g) gate-market: grüner Dot + "offen" (market_open=true)',
    mktHtml.includes('ov-dot fresh') && mktHtml.includes('offen'), mktHtml.slice(0, 90));
  check('(g) gate-release: "an" + Klassen (FX + Indizes, Metalle aus)',
    relHtml.includes('<b>an</b>') && relHtml.includes('FX + Indizes') && relHtml.includes('Metalle aus'),
    relHtml.slice(0, 120));
  check('(g) gate-next: NFP-Fenster 02.10. 14:00–14:30 BZ',
    nxtHtml.includes('Non-Farm') && nxtHtml.includes('02.10. 14:00–14:30') && nxtHtml.includes('30 min vor'),
    nxtHtml.slice(0, 140));
  check('(g) gate-blocks: 2 Skips (executor 1, shadow 1)',
    blkHtml.includes('<b>2</b>') && blkHtml.includes('executor 1') && blkHtml.includes('shadow 1'),
    blkHtml.slice(0, 140));

  console.log('\n' + '='.repeat(60));
  console.log(`RESULT: ${PASS} PASS, ${FAIL} FAIL`);
  console.log('='.repeat(60));
  process.exit(FAIL ? 1 : 0);
}, 300);
