#!/usr/bin/env node
/**
 * verify_llm_chart.js — ad-hoc-Verifikation (Node, kein Netz):
 * Extrahiert das inline-<script> aus src/content/supervisor.html und führt es
 * in einem Minimal-DOM-Stub (window, document.getElementById, setInterval-Stub,
 * fetch-Stub per URL-Route) gegen INLINE-Fixtures aus. Prüft die Sektion
 * „🔋 LLM-Budget (OpenRouter)" (13.10.2026): Karten, Chart-SVG und Fallbacks.
 *
 * Run: node tests/verify_llm_chart.js   → RESULT: X/X PASS, exit 0/1
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'src', 'content', 'supervisor.html');

let PASS = 0, FAIL = 0;
let fatal = null;
function check(name, cond, detail) {
  if (cond) { PASS++; console.log('  PASS  ' + name); }
  else { FAIL++; console.log('  FAIL  ' + name + (detail ? '  ' + detail : '')); }
}
process.on('unhandledRejection', (e) => {
  fatal = (e && e.stack) ? String(e.stack).split('\n').slice(0, 3).join(' | ') : String(e);
});

// ── 1. Skript-Text extrahieren ───────────────────────────────────────
const html = fs.readFileSync(SRC, 'utf8');
const m = html.match(/<script>([\s\S]*)<\/script>/);
if (!m) { console.log('FAIL  inline-<script> nicht gefunden'); process.exit(1); }
const scriptText = m[1];

// ── 2. Minimal-DOM-Stub ──────────────────────────────────────────────
function makeEl(id) {
  return {
    id, style: {}, innerHTML: '', textContent: '', className: '',
    children: [], parentElement: null, dataset: {},
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {}, appendChild(c) { this.children.push(c); return c; },
  };
}
let elements = {};
function resetDom() {
  elements = {};
  global.window = { location: { origin: 'http://stub' } };
  global.document = { getElementById: (id) => elements[id] || (elements[id] = makeEl(id)) };
  global.setInterval = function () { return 0; };
  global.clearInterval = function () {};
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// URL-Router: Supervisor-JSON -> {}, OpenRouter -> Fixture (oder Reject)
function fetchRouter(llm) {
  return function (url) {
    if (String(url).indexOf('/api/openrouter/status.json') >= 0) {
      if (llm && llm.__reject) return Promise.reject(new Error(llm.__reject));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(llm) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  };
}

async function runScenario(llm) {
  resetDom();
  global.fetch = fetchRouter(llm);
  vm.runInThisContext(scriptText, { filename: 'supervisor-inline.js' });
  await sleep(20);
  return elements;
}

// ── 3. INLINE-Fixtures ───────────────────────────────────────────────
const NOW = new Date().toISOString();
const LLM_OK = {
  schema: 'openrouter_v1', generated_at: NOW, fetched_at: NOW,
  fetch_ok: true, fetch_error: null,
  balance: { total_credits: 50.0, total_usage: 32.748434992,
             remaining: 17.251565008, used_pct: 65.5 },
  spend: { daily: 2.269183113, weekly: 8.24302122, monthly: 32.748434992,
           burn_7d_per_day: 1.1776, runway_days: 14.6 },
  history: [
    [1750000000.0, 20.5, 29.5],
    [1750003600.0, 19.5, 30.5],
    [1750007200.0, 18.5, 31.5],
    [1750010800.0, 17.251565, 32.748435],
  ],
  history_n: 4,
  history_first_iso: '2026-06-15T10:00:00+00:00',
  history_last_iso: '2026-06-15T13:00:00+00:00',
};
const LLM_ONE = Object.assign({}, LLM_OK, {
  history: [[1750010800.0, 17.251565, 32.748435]],
  history_n: 1,
});

(async () => {
  // ── Szenario A: gefüllte Historie (4 Punkte) ──────────────────────
  const A = await runScenario(LLM_OK);
  const bal = A['sv-llm-balance'] ? A['sv-llm-balance'].innerHTML : '';
  const spent = A['sv-llm-spent'] ? A['sv-llm-spent'].innerHTML : '';
  const chart = A['sv-llm-chart'] ? A['sv-llm-chart'].innerHTML : '';
  const note = A['sv-llm-note'] ? A['sv-llm-note'].textContent : '';
  const since = A['sv-llm-since'] ? A['sv-llm-since'].textContent : '';
  console.log('\nverify_llm_chart.js — LLM-Budget (OpenRouter)');
  console.log('='.repeat(60));
  check('(A1) Guthaben zeigt 17,25 $', bal.includes('17,25 $'), bal.slice(0, 120));
  check('(A2) Verbraucht zeigt 32,75 $', spent.includes('32,75 $'), spent.slice(0, 120));
  check('(A3) Chart enthält <svg> + <polyline>',
    chart.includes('<svg') && chart.includes('<polyline'), chart.slice(0, 80));
  check('(A4) Note enthält Quelle: OpenRouter',
    note.includes('Quelle: OpenRouter'), note);
  check('(A5) since enthält "Historie ab"', since.includes('Historie ab'), since);
  check('(A6) Chart-Cap nennt Messpunkte',
    chart.includes('4 Messpunkte'), chart.slice(-120));
  check('(A7) Reichweite ≈ 14,6 Tage (spend.runway_days — Regress 13.10.)',
    bal.includes('14,6 Tage Reichweite'), bal.slice(0, 200));
  check('(A8) used_pct de-DE formatiert (65,5 %)',
    spent.includes('65,5 %'), spent.slice(0, 200));

  // ── Szenario B: Historie mit nur 1 Punkt → kein SVG ───────────────
  const B = await runScenario(LLM_ONE);
  const chartB = B['sv-llm-chart'] ? B['sv-llm-chart'].innerHTML : '';
  check('(B1) 1 Punkt: Chart ohne <svg>', !chartB.includes('<svg'), chartB.slice(0, 120));
  check('(B2) 1 Punkt: Hinweis "Historie wird aufgebaut"',
    chartB.includes('Historie wird aufgebaut'), chartB.slice(0, 120));

  // ── Szenario C: OpenRouter-Fetch lehnt ab ─────────────────────────
  const C = await runScenario({ __reject: 'HTTP 500' });
  const noteC = C['sv-llm-note'] ? C['sv-llm-note'].textContent : '';
  check('(C1) Note enthält "nicht erreichbar"',
    noteC.includes('nicht erreichbar'), noteC);

  check('keine unhandled Rejections', fatal === null, fatal || '');

  console.log('\nRESULT: ' + PASS + '/' + (PASS + FAIL) + ' PASS');
  process.exit(fatal || FAIL > 0 ? 1 : 0);
})().catch((e) => { fatal = String(e && e.stack || e); 
  console.log('\nRESULT: ' + PASS + '/' + (PASS + FAIL) + ' PASS');
  process.exit(1);
});
