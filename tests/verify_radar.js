#!/usr/bin/env node
/**
 * verify_radar.js — ad-hoc-Verifikation (Node, kein Netz):
 * Lädt src/templates/bot-components.js in einen Minimal-DOM-Stub
 * (window, document.getElementById → Auto-Objekte mit style/innerHTML,
 * fetch-Stub) und prüft das Rotations-Radar v2 (13.10.2026) gegen
 * INLINE-Fixtures (kein Live-JSON).
 *
 * Run: node tests/verify_radar.js   → RESULT: X/X PASS, exit 0/1
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

// ── 1. Minimal-DOM-Stub (Muster AGENTS.md / verify_overview_charts.js) ──
const elements = {};
function makeEl(id) {
  return {
    id, style: {}, innerHTML: '', textContent: '', className: '',
    children: [], parentElement: null, dataset: {},
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {}, appendChild(c) { this.children.push(c); return c; },
  };
}
global.window = { location: { origin: 'http://stub' } };
global.document = {
  getElementById: (id) => elements[id] || (elements[id] = makeEl(id)),
};
global.fetch = function () {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ strategies: [] }) });
};

// ── 2. Script laden + BotDash-Handle ─────────────────────────────────
let loadErr = null;
try {
  vm.runInThisContext(fs.readFileSync(SRC, 'utf8'), { filename: 'bot-components.js' });
} catch (e) { loadErr = e; }
const BD = global.window.BotDash;
check('bot-components.js geladen, BotDash vorhanden', !loadErr && !!BD,
  loadErr ? String(loadErr).split('\n')[0] : '');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 3. INLINE-Fixtures ───────────────────────────────────────────────
const SLOTS = [{
  slot_id: 's372', kind: 'strategy', strategy_id: 372, active: true,
  assets: ['EURAUD'], risk_pct: 2.5, since: '2026-09-01T08:00:00+00:00',
  holder: 372, challenge: null,
  stats: { trades: 9, closed: 9, wins: 7, net_eur: 12.34, win_rate: 77.8,
           pnl_7d: 3.2, pnl_30d: 12.34 },
}];

// Haupt-Fixture: 10 Kandidaten, wave belegt, 1 Challenge läuft (111),
// 1 reif-fillbarer Kandidat (999 ready) wäre erst mit open wave S4 — hier open=false.
function cand(id, over) {
  return Object.assign({
    strategy_id: id, score: 5.0, eur_per_trade: 5.0, n_class: 30,
    net_class: 10, trades_28d: 6, pairs: ['AUDCAD'], reasons: [],
    pf: 1.75, oos_trades: 40, status: 'active',
    ci95: 3.21, ci_n: 12, ev_grade: 'green', challenge: null,
    fillable: true, lacks: 'frei — Challenge startet automatisch',
  }, over || {});
}
const CANDS = [
  cand(111, { eur_per_trade: 10.0, ci95: 10.58, ci_n: 4, challenge: { slot_id: 'srot', candidate: 111, trades: 2, need_trades: 1, net_eur: 5.0, days_left: 11, ready: false }, fillable: true, lacks: 'Challenge läuft: 2/3 · Frist in 11 d' }),
  cand(222, { reasons: ['cluster_cap:FX:2'], fillable: false, lacks: 'Cluster-Cap voll' }),
  cand(333, { reasons: ['deferred:no_pairs'], fillable: false, lacks: 'kein Tree/Pairs (deferred)' }),
  cand(444, { ci95: null, ci_n: 0, oos_trades: null, pf: null, lacks: 'frei — Challenge startet automatisch' }),
  cand(555, { reasons: ['pair_disjoint:srot'], fillable: false, lacks: 'Paar-Konflikt mit Geschwister-Slots' }),
  cand(666, { ev_grade: 'red', ci95: null, ci_n: 0, fillable: true, lacks: 'Evidenz dünn (n<10)' }),
  cand(777, { reasons: ['pair_cap_tf:JPY:2'], fillable: false, lacks: 'TF-Bucket belegt' }),
  cand(888, { reasons: ['pair_cap:AUDCAD'], fillable: false, lacks: 'Pair-Cap erreicht' }),
  cand(999, { reasons: ['min_asset_trades'], fillable: false, lacks: 'ohne ≥5 Klassentrades' }),
  cand(1010, { reasons: ['inactive'], fillable: false, lacks: '>42 d inaktiv' }),
];
const RADAR_MAIN = {
  target_class: 'FX', generated_at: '2026-10-13T07:00:00+00:00',
  pool_size: 14, excluded: 9, shown: 10, n_fillable: 3, n_blocked: 7,
  excluded_breakdown: [
    { reason: 'min_asset_trades', count: 3 }, { reason: 'inactive', count: 2 },
    { reason: 'not_selected', count: 2 }, { reason: 'asset_bust', count: 1 },
    { reason: 'catalog_status:rejected', count: 1 },
  ],
  fills_30d: 1,
  wave: { wave_days: 7, last_fill_ts: '2026-10-09T08:00:00+00:00',
          last_fill_label: 'srot ← #663', unlock_ts: '2026-10-16T08:00:00+00:00',
          open: false },
  challenges_active: [
    { slot_id: 'srot', candidate: 111, trades: 1, need_trades: 2, net_eur: 10.0, days_left: 12, ready: false },
  ],
  candidates: CANDS,
};

async function renderWith(prefix, data) {
  BD.config.prefix = prefix;
  BD.renderSlots(data);
  await sleep(300);
  return elements[prefix + '-radar'];
}

(async () => {
  await sleep(0);
  if (fatal) { finish(); return; }

  // ── Szenario 1: gefülltes Radar v2 ──
  const b1 = await renderWith('bt1', { slots: SLOTS, rotation_radar: RADAR_MAIN });
  const h1 = b1 ? b1.innerHTML : '';
  console.log('\nverify_radar.js — Rotations-Radar v2');
  console.log('='.repeat(60));
  check('(1a) Radar sichtbar bei gefülltem Fixture',
    !!b1 && b1.style.display !== 'none' && h1.length > 0,
    b1 ? 'display=' + b1.style.display : 'kein Element');
  check('(1b) Header enthält pool_size + excluded + Top',
    h1.includes('14 Kandidaten') && h1.includes('Top 10 gezeigt') && h1.includes('9 exkludiert'),
    'header: ' + (h1.match(/Kandidaten-Pool[^<]*/) || ['?'])[0]);
  check('(2) Ausschluss-Zeile mappt Label (ohne ≥5 Klassentrades)',
    h1.includes('Ausschlüsse u. a.:') && h1.includes('ohne ≥5 Klassentrades') &&
    h1.includes('(3)') && h1.includes('Mehrfachnennungen möglich'));
  check('(3a) Timeline: Letzte Fills + Label + Wave-Cap frei ab',
    h1.includes('⏱ Letzte Fills: 1 in 30 d') && h1.includes('srot ← #663') &&
    h1.includes('Wave-Cap: frei ab'),
    'timeline: ' + (h1.match(/⏱[^<]*/) || ['?'])[0]);
  check('(3b) Timeline: Hinweis „Stillstand" vorhanden',
    h1.includes('Hinweis: Bei dieser Challenge-Frequenz ist ein Stillstand von Tagen normal (n klein).'));
  check('(4) Challenges-Zeile enthält 1/3',
    h1.includes('Challenges: srot #111 1/3'),
    'ch: ' + (h1.match(/Challenges:[^<]*/) || ['?'])[0]);
  const stgCount = (h1.match(/class="radar-stg"/g) || []).length;
  check('(5) 10 Zeilen × 5 Stufen-Boxen == 50 radar-stg', stgCount === 50,
    'ist: ' + stgCount);
  check('(6) KI-Spalte: ± + (n= vorhanden (und KI n/a für null-ci)',
    h1.includes('±') && h1.includes('(n=') && h1.includes('KI n/a'),
    'ev: ' + (h1.match(/10\.00[^<]*/) || ['?'])[0]);
  check('(7a) Blockierter Kandidat: grauer Chip Cluster-Cap + ⚙',
    h1.includes('⚙') && h1.includes('⚙ Cluster-Cap<') &&
    h1.includes('rgba(139,148,158,0.12)') && h1.includes('#8b949e'));
  check('(7b) Blockierter Kandidat: lacks-Text sichtbar',
    h1.includes('>Cluster-Cap voll<') && h1.includes('>kein Tree/Pairs (deferred)<'));
  check('(7c) Füllbarer Kandidat: ✓ füllbar',
    h1.includes('✓ füllbar'));
  check('(8) challenge-Lauf-Text: Challenge läuft: 2/3',
    h1.includes('Challenge läuft: 2/3'));
  check('(9) Explainer-Bullet Defekt-Nachweis vorhanden',
    h1.includes('Defekt-Nachweis') && h1.includes('kein PnL-Ranking'));

  // ── Szenario 2: leerer Pool → sichtbar + Lernphase ──
  const b2 = await renderWith('bt2', {
    slots: SLOTS,
    rotation_radar: {
      target_class: 'FX', generated_at: '2026-10-13T07:00:00+00:00',
      pool_size: 0, excluded: 0, shown: 0, n_fillable: 0, n_blocked: 0,
      excluded_breakdown: [], fills_30d: 0,
      wave: { wave_days: 7, last_fill_ts: null, last_fill_label: null,
              unlock_ts: null, open: true },
      challenges_active: [],
      candidates: [],
    },
  });
  const h2 = b2 ? b2.innerHTML : '';
  check('(10) Leerer Pool: Box sichtbar + Lernphase + Timeline offen',
    !!b2 && b2.style.display !== 'none' && h2.includes('Lernphase') &&
    h2.includes('Keine Kandidaten im Pool') && h2.includes('Wave-Cap: frei') &&
    h2.includes('noch kein Fill'));

  // ── Szenario 3: rotation_radar null → versteckt + geleert (nach Vollbild) ──
  BD.config.prefix = 'bt3';
  BD.renderSlots({ slots: SLOTS, rotation_radar: RADAR_MAIN });
  await sleep(300);
  BD.renderSlots({ slots: SLOTS, rotation_radar: null });
  await sleep(300);
  const b3 = elements['bt3-radar'];
  check('(11) rotation_radar null: Box versteckt, innerHTML leer',
    !!b3 && b3.style.display === 'none' && b3.innerHTML === '',
    'display=' + (b3 ? b3.style.display : '?') + ' len=' + (b3 ? b3.innerHTML.length : '?'));

  // ── Szenario 4: Altdaten-Shape (ohne wave/ci95) → rendert ohne Exception ──
  const b4 = await renderWith('bt4', {
    slots: SLOTS,
    rotation_radar: {
      target_class: 'FX', generated_at: '2026-10-11T07:00:00+00:00',
      pool_size: 5, excluded: 2,
      candidates: [
        { strategy_id: 5, score: 2.0, eur_per_trade: 3.0, n_class: 20,
          net_class: 30, trades_28d: 5, pairs: [], reasons: ['cluster_cap'],
          pf: null, oos_trades: null },
        { strategy_id: 7, score: 1.5, eur_per_trade: 1.0, n_class: 8,
          net_class: -3, trades_28d: 2, pairs: [], reasons: [],
          pf: 1.2, oos_trades: 15 },
      ],
    },
  });
  const h4 = b4 ? b4.innerHTML : '';
  check('(12a) Altdaten: rendert ohne Exception, 2 Zeilen (10 Stufen-Boxen)',
    (h4.match(/class="radar-stg"/g) || []).length === 10 &&
    h4.includes('#5') && h4.includes('#7'));
  check('(12b) Altdaten: Header-Fallback Top = candidates.length',
    h4.includes('Top 2 gezeigt') && h4.includes('5 Kandidaten'));
  check('(12c) Altdaten: keine Timeline (wave fehlt), Chip grau',
    !h4.includes('⏱') && !h4.includes('Wave-Cap: ') && h4.includes('⚙') &&
    h4.includes('⚙ Cluster-Cap<'));

  check('keine unhandled Rejections', fatal === null, fatal || '');

  finish();
})().catch((e) => { fatal = String(e && e.stack || e); finish(); });

function finish() {
  console.log('\nRESULT: ' + PASS + '/' + (PASS + FAIL) + ' PASS');
  process.exit(fatal || FAIL > 0 ? 1 : 0);
}
