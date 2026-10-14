#!/usr/bin/env node
/**
 * verify_bot_curves.js — ad-hoc-Verifikation (Node, kein Netz):
 * Lädt src/templates/bot-components.js in einen Minimal-DOM-Stub
 * (window, document.getElementById/createElement → Auto-Objekte,
 * Chart-Stub, der die Chart-Config captured, fetch-Stub) und prüft die
 * Echtgeld-Konto-Kurven (renderEquity) + Echtgeld-KPI-Karten (renderKPIs)
 * gegen INLINE-Fixtures (kein Live-JSON).
 *
 * Muster: verify_radar.js. Run: node tests/verify_bot_curves.js
 *   → RESULT: N/N PASS, exit 0/1
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'src', 'templates', 'bot-components.js');

let PASS = 0, FAIL = 0;
let fatal = null;
function check(name, cond, detail) {
  if (cond) { PASS++; console.log('  PASS  ' + name); }
  else { FAIL++; console.log('  FAIL  ' + name + (detail ? '  ' + detail : '')); }
}
process.on('unhandledRejection', (e) => {
  fatal = (e && e.stack) ? String(e.stack).split('\n').slice(0, 3).join(' | ') : String(e);
});

// ── 1. Minimal-DOM-Stub (Muster verify_radar.js + createElement) ──
const elements = {};
function makeEl(id) {
  return {
    id, style: {}, innerHTML: '', textContent: '', className: '',
    children: [], parentElement: null, dataset: {},
    getContext: () => ({}),
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {},
    appendChild(c) { this.children.push(c); if (c && c.id) elements[c.id] = c;
                     if (c) c.parentElement = this; return c; },
  };
}
let _tmpSeq = 0;
global.window = { location: { origin: 'http://stub' } };
// Strikt wie das echte DOM: unbekannte IDs -> null (der -ext-Guard in
// renderKPIs darf nicht durch Auto-Erzeugen ausgehebelt werden). Benoetigte
// Elemente werden explizit registriert (Canvas / kpi-row).
function reg(id) { const e = makeEl(id); elements[id] = e; return e; }
global.document = {
  getElementById: (id) => (Object.prototype.hasOwnProperty.call(elements, id)
    ? elements[id] : null),
  createElement: (tag) => makeEl('#new:' + tag + ':' + (_tmpSeq++)),
};
global.fetch = function () {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
};

// ── 2. Chart-Stub: captured jede neue Chart-Config ──
const charts = [];
function ChartStub(ctx, cfg) { this.ctx = ctx; this.config = cfg; charts.push(this); }
ChartStub.prototype.destroy = function () {};
global.Chart = ChartStub;

// ── 3. Script laden + BotDash-Handle ────────────────────────────────
let loadErr = null;
try {
  vm.runInThisContext(fs.readFileSync(SRC, 'utf8'), { filename: 'bot-components.js' });
} catch (e) { loadErr = e; }
const BD = global.window.BotDash;
check('bot-components.js geladen, BotDash vorhanden', !loadErr && !!BD,
  loadErr ? String(loadErr).split('\n')[0] : '');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lastChart = () => (charts.length ? charts[charts.length - 1].config : null);

// Benoetigte Stub-Elemente explizit registrieren (Container/Canvas existieren).
reg('f1-equity-chart');
reg('f2-equity-chart');
reg('f3-kpi-row');
reg('f4-kpi-row');

(async () => {
  await sleep(0);
  if (fatal) { finish(); return; }
  console.log('\nverify_bot_curves.js — Echtgeld-Konten-Kurven + Karten');
  console.log('='.repeat(60));

  // ── F1: OHNE curves → exakt 2 Datasets wie heute ──────────────────
  BD.config.prefix = 'f1';
  BD.renderEquity({
    equity_history: { snapshots: [
      { timestamp: '2026-10-14T00:00:00+00:00', equity: 1000 },
      { timestamp: '2026-10-14T00:05:00+00:00', equity: 1010 },
    ] },
  });
  const cfg1 = lastChart();
  check('F1 ohne curves: genau 2 Datasets',
    !!cfg1 && cfg1.data.datasets.length === 2,
    cfg1 ? 'ist: ' + cfg1.data.datasets.length : 'keine Chart-Config');
  check('F1 ohne curves: labels/values wie heute',
    !!cfg1 && cfg1.data.labels.length === 2 &&
    cfg1.data.datasets[0].data[0] === 1000 && cfg1.data.datasets[0].data[1] === 1010 &&
    cfg1.data.datasets[1].yAxisID === 'y1');

  // ── F2: MIT curve (teils disjunkte ISO-Timestamps) → 3 Datasets ───
  const T0 = '2026-10-14T00:00:00+00:00';
  const T1 = '2026-10-14T00:05:00+00:00';
  const T2 = '2026-10-14T00:10:00+00:00';
  const T3 = '2026-10-14T00:15:00+00:00';   // nur in der Kontokurve
  BD.config.prefix = 'f2';
  BD.renderEquity({
    equity_history: { snapshots: [
      { timestamp: T0, equity: 1000 },
      { timestamp: T1, equity: 1010 },
      { timestamp: T2, equity: 1005 },
    ] },
    curves: [{
      ctid: '47490067', is_live: true, label: 'Echtgeld-Konto 47490067',
      points: [
        { timestamp: T1, equity: 1120.44 },   // Overlap mit Basis
        { timestamp: T3, equity: 1125.00 },   // disjoint
      ],
    }],
  });
  const cfg2 = lastChart();
  check('F2 mit curve: genau 3 Datasets',
    !!cfg2 && cfg2.data.datasets.length === 3,
    cfg2 ? 'ist: ' + cfg2.data.datasets.length : 'keine Chart-Config');
  check('F2 Label-Union chronologisch (4 Labels inkl. disjoint T3)',
    !!cfg2 && cfg2.data.labels.length === 4 &&
    cfg2.data.labels[0] === T0 && cfg2.data.labels[1] === T1 &&
    cfg2.data.labels[2] === T2 && cfg2.data.labels[3] === T3,
    cfg2 ? JSON.stringify(cfg2.data.labels) : '');
  const cur = (cfg2 && cfg2.data.datasets[2]) || {};
  check('F2 Kurven-Dataset: label + rot + width2 + pointRadius0',
    cur.label === 'Echtgeld-Konto 47490067' && cur.borderColor === '#ef4444' &&
    cur.borderWidth === 2 && cur.pointRadius === 0 && cur.fill === false &&
    cur.spanGaps === false && cur.yAxisID === 'y',
    JSON.stringify({ label: cur.label, borderColor: cur.borderColor }));
  check('F2 Echtgeld-Werte an korrekten Indizes, nulls sonst',
    cur.data && cur.data[0] === null && cur.data[1] === 1120.44 &&
    cur.data[2] === null && cur.data[3] === 1125.00,
    JSON.stringify(cur.data));
  check('F2 Basis-Serie auf Union gemappt (null bei disjoint T3)',
    cfg2 && cfg2.data.datasets[0].data[0] === 1000 &&
    cfg2.data.datasets[0].data[1] === 1010 &&
    cfg2.data.datasets[0].data[2] === 1005 &&
    cfg2.data.datasets[0].data[3] === null,
    cfg2 ? JSON.stringify(cfg2.data.datasets[0].data) : '');

  // Tooltip-Konvention
  const tip = cfg2 && cfg2.options.plugins.tooltip.callbacks.label;
  check('F2 Tooltip: Basis €, Drawdown %, Kontokurve €…(Echtgeld ctid)',
    typeof tip === 'function' &&
    tip({ datasetIndex: 0, parsed: { y: 1000 } }) === ' €1000.00' &&
    tip({ datasetIndex: 1, parsed: { y: -2.5 } }) === ' -2.50%' &&
    tip({ datasetIndex: 2, dataset: { _ctid: '47490067' }, parsed: { y: 1120.44 } })
      === ' €1120.44 (Echtgeld 47490067)');

  // ── F3: account_cards → -ext-Karte mit €1120.44 ───────────────────
  BD.config.prefix = 'f3';
  BD.renderKPIs({
    account_cards: [{ ctid: '47490067', is_live: true, label: 'Echtgeld',
                      balance: 1120.44, equity: 1120.44 }],
  });
  await sleep(0);
  const card = elements['f3-ext-47490067'];
  const row = elements['f3-kpi-row'];
  check('F3 Echtgeld-Karte angelegt (id f3-ext-47490067)', !!card);
  check('F3 Karte haengt an f3-kpi-row', !!row && row.children.indexOf(card) >= 0);
  check('F3 Karte: Label + €1120.44 + Equity-Zeile',
    !!card && card.innerHTML.indexOf('🔴 Echtgeld 47490067') >= 0 &&
    card.innerHTML.indexOf('€1120.44') >= 0 &&
    card.innerHTML.indexOf('Equity: €1120.44') >= 0,
    card ? card.innerHTML : 'keine Karte');
  // erneuter Aufruf darf nicht duplizieren
  BD.renderKPIs({
    account_cards: [{ ctid: '47490067', is_live: true, balance: 1120.44, equity: 1120.44 }],
  });
  check('F3 zweiter Aufruf: keine Duplikat-Karte',
    row && row.children.filter((c) => c.id === 'f3-ext-47490067').length === 1,
    row ? 'children=' + row.children.length : 'keine Row');

  // ── F4: OHNE cards → keine Karte ──────────────────────────────────
  BD.config.prefix = 'f4';
  BD.renderKPIs({ account_cards: [] });
  await sleep(0);
  const f4cards = Object.keys(elements).filter((k) => k.indexOf('f4-ext-') === 0);
  check('F4 ohne cards: keine -ext-Karte', f4cards.length === 0,
    'gefunden: ' + JSON.stringify(f4cards));

  check('keine unhandled Rejections', fatal === null, fatal || '');
  finish();
})().catch((e) => { fatal = String((e && e.stack) || e); finish(); });

function finish() {
  console.log('\nRESULT: ' + PASS + '/' + (PASS + FAIL) + ' PASS');
  process.exit(fatal || FAIL > 0 ? 1 : 0);
}
