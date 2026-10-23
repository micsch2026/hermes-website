#!/usr/bin/env node
/**
 * verify_bot_cockpit.js — Node-DOM-Stub-Harness für das Cockpit-Template
 * (bot-components.js, 23.10.2026). Kein Netz, keine echten JSONs.
 *
 * Geprüft:
 *   A  _accounts: accounts[] normalisiert + Legacy-Fallback (account + cards)
 *   B  renderAccounts: 2 Karten, Live zuerst, €-Format, Kapitalbewegung
 *   C  renderEquity: indexiert (2 Serien, Basis 100, Gold/Blau, spanGaps)
 *   D  renderEquity: Ein-Konto-Ansicht absolut (1 Serie, €-Achse)
 *   E  renderHistory: 10er-Cap, Live-Filter, Zähler
 *   F  _slotStats: Account-Scope (Live-Slot zeigt NICHT die Demo-Ära)
 *   G  renderBoard: Belegung 3/8, Live-Zeile account-scoped, Demo-Ära-Chip,
 *      Balken mit demselben Wert, Türen + Reserve
 *   H  renderBoard: Leerfall ohne slots
 *
 * Muster: verify_radar.js / verify_bot_curves.js. Run:
 *   node tests/verify_bot_cockpit.js
 */

'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'src', 'templates', 'bot-components.js');

let PASS = 0, FAIL = 0;
function check(name, cond, detail) {
  if (cond) { PASS++; console.log('  PASS  ' + name); }
  else { FAIL++; console.log('  FAIL  ' + name + (detail ? '  ' + detail : '')); }
}
process.on('unhandledRejection', (e) => {
  console.log('  FAIL  unhandledRejection: ' + (e && e.message ? e.message : e));
  FAIL++;
});

// ── Minimal-DOM ───────────────────────────────────────────────
const elements = {};
function makeEl(id) {
  const classes = new Set();
  return {
    id, style: {}, innerHTML: '', textContent: '', className: '',
    children: [], dataset: {},
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
      toggle: (c, on) => { if (on === undefined) { classes.has(c) ? classes.delete(c) : classes.add(c); } else if (on) classes.add(c); else classes.delete(c); },
      toString: () => [...classes].join(' '),
    },
    getContext: () => ({}),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    appendChild(c) { this.children.push(c); return c; },
  };
}
function reg(id) { const e = makeEl(id); elements[id] = e; return e; }
global.window = { location: { origin: 'http://stub' } };
global.document = {
  getElementById: (id) => (Object.prototype.hasOwnProperty.call(elements, id) ? elements[id] : null),
  createElement: (tag) => makeEl('#new:' + tag),
};
global.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });

const charts = [];
function ChartStub(ctx, cfg) { this.ctx = ctx; this.config = cfg; charts.push(this); }
ChartStub.prototype.destroy = function () {};
global.Chart = ChartStub;

let loadErr = null;
try {
  vm.runInThisContext(fs.readFileSync(SRC, 'utf8'), { filename: 'bot-components.js' });
} catch (e) { loadErr = e; }
const BD = global.window.BotDash;
check('bot-components.js geladen, BotDash vorhanden', !loadErr && !!BD,
  loadErr ? String(loadErr).split('\n')[0] : '');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lastChart = () => (charts.length ? charts[charts.length - 1].config : null);

// ── Fixtures ──────────────────────────────────────────────────
const EH = [
  { timestamp: '2026-09-16T00:00:00+00:00', equity: 1000 },
  { timestamp: '2026-10-01T00:00:00+00:00', equity: 1100 },
  { timestamp: '2026-10-23T00:00:00+00:00', equity: 1200 },
];
const LIVE_PTS = [
  { timestamp: '2026-10-13T00:00:00+00:00', equity: 1000 },
  { timestamp: '2026-10-20T00:00:00+00:00', equity: 990 },
  { timestamp: '2026-10-23T00:00:00+00:00', equity: 975.35 },
];
const D = {
  mode: 'mixed',
  account: { ctid: '48452598', balance: 1194.42, equity: 1190.11 },
  accounts: [
    { ctid: '48452598', is_live: false, label: 'Demo', balance: 1194.42, equity: 1190.11, is_default: true, flows: null },
    { ctid: '48997285', is_live: true, label: 'Echtgeld', balance: 975.35, equity: 975.35, is_default: false,
      flows: { ctid: '48997285', einzahlungen_eur: 0, auszahlungen_eur: 0, transfers_eur: 1000, netto_eur: 1000, n_moves: 1 } },
  ],
  equity_history: EH,
  curves: [{ ctid: '48997285', is_live: true, points: LIVE_PTS }],
  performance: { total_trades: 76, profit_factor: 1.51, win_rate: 50 },
  slots_target: 8,
  slots: [
    { slot_id: 's775', kind: 'strategy', strategy_id: 775, account_id: '48997285', stage: 'live', armed: true,
      since: '2026-09-28T00:00:00+00:00', assets: ['US500'], risk_pct: 1,
      stats: { trades: 60, closed: 60, wins: 31, net_eur: 147.7, win_rate: 51.7, pnl_7d: 27.54, pnl_30d: 147.7,
        by_account: {
          '48452598': { trades: 32, closed: 32, wins: 20, net_eur: 167.26, win_rate: 62.5, pnl_7d: 0, pnl_30d: 167.26 },
          '48997285': { trades: 28, closed: 28, wins: 11, net_eur: -19.56, win_rate: 39.3, pnl_7d: 27.54, pnl_30d: -19.56 },
        } } },
    { slot_id: 'irot', kind: 'strategy', strategy_id: 778, account_id: '48452598', stage: 'demo', armed: null,
      since: '2026-10-01T00:00:00+00:00', stats: { trades: 10, closed: 10, wins: 4, net_eur: -18.18, win_rate: 40, pnl_7d: -3.84, pnl_30d: -18.18,
        by_account: { '48452598': { trades: 10, closed: 10, wins: 4, net_eur: -18.18, win_rate: 40, pnl_7d: -3.84, pnl_30d: -18.18 } } } },
    { slot_id: 'i2', kind: 'rotation', stage: 'shadow', account_id: '48452598', challenge: { candidate: 782, trades: 7, days_left: 4, ready: false } },
    { slot_id: 'i5', kind: 'planned', stage: 'planned', account_id: '48452598' },
    { slot_id: 'i6', kind: 'planned', stage: 'planned', account_id: '48452598' },
    { slot_id: 'i7', kind: 'planned', stage: 'planned', account_id: '48452598' },
  ],
  last_trades: [
    { slot_id: 's775', account_id: '48997285', live: true, strategy_id: 775, symbol: 'US500', direction: 'short', pnl: 4, entry: 7653, exit_price: 7645.3, timestamp: '2026-10-23T15:00:00+00:00', status: 'tp_sl_closed' },
    { slot_id: 's775', account_id: '48997285', live: true, strategy_id: 775, symbol: 'US2000', direction: 'short', pnl: -2, entry: 2765, exit_price: 2769, timestamp: '2026-10-22T15:00:00+00:00', status: 'tp_sl_closed' },
    { slot_id: 'irot', account_id: '48452598', live: false, strategy_id: 778, symbol: 'GER40', direction: 'short', pnl: 11.83, entry: 25180, exit_price: 25067, timestamp: '2026-10-23T10:00:00+00:00', status: 'tp_sl_closed' },
  ],
};

// Elemente, die die Renderer erwarten
['f1-accounts', 'f1-equity-chart', 'f1-eq-seg', 'f1-equity-summary', 'f1-action',
 'f2-accounts', 'f2-equity-chart', 'f2-eq-seg', 'f2-equity-summary',
 'f3-hist-filter', 'f3-hist-count', 'f3-history-body', 'f3-history-table', 'f3-hist-more',
 'f4-board', 'f4-board-sub', 'f4-board-occ', 'f4-board-bars',
 'f5-board', 'f5-board-sub', 'f5-board-occ', 'f5-board-bars',
 'f6-accounts', 'f6-equity-chart', 'f6-eq-seg', 'f6-equity-summary',
].forEach(reg);

(async () => {
  await sleep(0);
  console.log('\nverify_bot_cockpit.js — Cockpit-Template');
  console.log('='.repeat(60));

  // ── A: _accounts ────────────────────────────────────────────
  BD.config.prefix = 'f1';
  BD.renderAccounts(D);
  const accHtml = elements['f1-accounts'].innerHTML;
  check('A  Konten: 2 Karten, Live zuerst', (accHtml.match(/class="cp-acct /g) || []).length === 2 &&
    accHtml.indexOf('cp-acct live') < accHtml.indexOf('cp-acct demo'));
  check('A  Konten: €-Format de-DE', accHtml.includes('1.194,42 €') && accHtml.includes('975,35 €'));
  check('A  Konten: Kapitalbewegung Live', accHtml.includes('Transfers 1.000,00 €') && accHtml.includes('Netto 1.000,00 €'));

  // Legacy-Fallback: kein accounts[] → account + account_cards
  BD.renderAccounts({ account: { ctid: '1', balance: 100, equity: 100 }, mode: 'demo',
    account_cards: [{ ctid: '2', is_live: true, balance: 50, equity: 50, label: 'Echtgeld' }] });
  check('A  Konten-Fallback: account + account_cards → 2 Karten',
    (elements['f1-accounts'].innerHTML.match(/class="cp-acct /g) || []).length === 2);

  // ── B: Equity indexiert ────────────────────────────────────
  BD.config.prefix = 'f2';
  BD.setEquityView('indexed');
  BD.renderEquity(D);
  const c1 = lastChart();
  check('B  Indexiert: 2 Datasets', !!c1 && c1.data.datasets.length === 2, c1 ? String(c1.data.datasets.length) : 'kein Chart');
  check('B  Indexiert: Serien starten bei 100',
    c1.data.datasets[0].data.filter(x => x != null)[0] === 100 &&
    c1.data.datasets[1].data.filter(x => x != null)[0] === 100);
  check('B  Indexiert: Gold=Echtgeld, Blau=Demo',
    c1.data.datasets[0].borderColor === '#f0b940' && c1.data.datasets[1].borderColor === '#5b8def');
  check('B  Indexiert: spanGaps true', c1.data.datasets.every(d => d.spanGaps === true));
  check('B  Indexiert: Demo endet bei 120', Math.abs(c1.data.datasets[1].data.filter(x => x != null).pop() - 120) < 0.01);

  // ── C: Ein-Konto absolut ───────────────────────────────────
  BD.setEquityView('live');
  BD.renderEquity(D);
  const c2 = lastChart();
  check('C  Live-Ansicht: 1 Dataset absolut', !!c2 && c2.data.datasets.length === 1 &&
    c2.data.datasets[0].data.filter(x => x != null).pop() === 975.35);
  check('C  Live-Ansicht: Label Echtgeld', c2.data.datasets[0].label.includes('Echtgeld'));

  // ── D: Historie ─────────────────────────────────────────────
  BD.config.prefix = 'f3';
  BD.setHistoryFilter('all');
  BD.renderHistory(D);
  check('D  Historie: Cap 10 (3 Trades → 3 Zeilen)', (elements['f3-history-body'].innerHTML.match(/<tr/g) || []).length === 3);
  check('D  Historie: Zähler nutzt Gesamtzahl 76', elements['f3-hist-count'].textContent.includes('76 Trades') &&
    elements['f3-hist-count'].textContent.includes('3 geladen'));
  BD.setHistoryFilter('live');
  BD.renderHistory(D);
  const liveRows = (elements['f3-history-body'].innerHTML.match(/<tr/g) || []).length;
  check('D  Historie: Live-Filter → nur 2 Live-Trades', liveRows === 2, 'ist: ' + liveRows);
  BD.setHistoryFilter('all');

  // ── E: Account-Scope ───────────────────────────────────────
  const stLive = BD.slotStats ? BD.slotStats(D.slots[0]) : null;
  check('E  Slot-Stats: Live-Slot nutzt Live-Konto (-19,56)',
    stLive && stLive.pnl_30d === -19.56 && stLive.closed === 28,
    stLive ? JSON.stringify(stLive) : 'nicht exportiert');

  // ── F: Board ────────────────────────────────────────────────
  BD.config.prefix = 'f4';
  BD.renderBoard(D);
  await sleep(50);
  const board = elements['f4-board'].innerHTML;
  check('F  Board: 2/8 Belegung', elements['f4-board-sub'].textContent === '2/8 belegt',
    elements['f4-board-sub'].textContent);
  check('F  Board: Live-Zeile mit Live-PnL', board.includes('-19,56 €') && !board.match(/s775[\s\S]{0,400}\+147,70 €/));
  check('F  Board: Demo-Ära-Chip', board.includes('Demo-Ära') && board.includes('167,26 €'));
  check('F  Board: Türen + Reserve', board.includes('7/3') && board.includes('3 Reserve-Plätze'));
  check('F  Balken: account-scoped (-19,56 €)', elements['f4-board-bars'].innerHTML.includes('-19,56 €'));

  // ── G: Leerfall ─────────────────────────────────────────────
  BD.config.prefix = 'f5';
  BD.renderBoard({ slots: [], slots_target: 0 });
  await sleep(30);
  check('G  Leerfall: "Keine Slot-Konfiguration"', elements['f5-board'].innerHTML.includes('Keine Slot-Konfiguration'));

  // ── H: Einzelkonto (kein Segmented Control) ─────────────────
  BD.config.prefix = 'f6';
  BD.setEquityView(null);
  BD.renderEquity({ accounts: [D.accounts[0]], equity_history: EH });
  check('H  Einzelkonto: Segment-Control versteckt', elements['f6-eq-seg'].style.display === 'none');
  check('H  Einzelkonto: 1 Dataset', lastChart().data.datasets.length === 1);

  console.log('\nRESULT: ' + PASS + '/' + (PASS + FAIL) + ' PASS');
  process.exit(FAIL ? 1 : 0);
})();
