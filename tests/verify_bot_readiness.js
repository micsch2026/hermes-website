#!/usr/bin/env node
/**
 * verify_bot_readiness.js — ad-hoc-Verifikation (Node, kein Netz):
 * Lädt src/templates/bot-components.js in einen Minimal-DOM-Stub (Muster
 * verify_bot_curves.js) und prüft den neuen Scharfstellen-/Automatik-Status
 * (renderSlots → _slotsStatusStrip, 20.10.2026):
 *   A) Live-Slot ohne Arming → „🔒 bereit für Scharfstellen … wartet auf dein OK“
 *      (Strip amber + Konto-Zeile + Badge „OK nötig“)
 *   B) Challenge ready (Demo) → „⚡ bereit — Fill läuft automatisch …“
 *   C) Challenge läuft → „⏳ Automatik läuft — Challenge #… Tag X/14“
 *   D) nichts offen → „✅ Keine Aktion nötig — alles läuft automatisch“
 *   E) leere Slots → Sektion versteckt, kein Strip, kein Crash
 *
 * Run: node tests/verify_bot_readiness.js  → RESULT: N/N PASS, exit 0/1
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

// ── 1. Minimal-DOM-Stub (Muster verify_bot_curves.js) ──
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
global.window = { location: { origin: 'http://stub' } };
function reg(id) { const e = makeEl(id); elements[id] = e; return e; }
global.document = {
  getElementById: (id) => (Object.prototype.hasOwnProperty.call(elements, id)
    ? elements[id] : null),
  createElement: (tag) => makeEl('#new:' + tag),
};
global.fetch = function () {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
};

// ── 2. Script laden + BotDash-Handle ────────────────────────────────
let loadErr = null;
try {
  vm.runInThisContext(fs.readFileSync(SRC, 'utf8'), { filename: 'bot-components.js' });
} catch (e) { loadErr = e; }
const BD = global.window.BotDash;
check('bot-components.js geladen, BotDash vorhanden', !loadErr && !!BD,
  loadErr ? String(loadErr).split('\n')[0] : '');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

reg('r1-slots-section');
reg('r1-slots-grid');
reg('r1-slots-title');
reg('r1-slots-sub');

(async () => {
  await sleep(0);
  if (fatal) { console.log('FATAL: ' + fatal); process.exit(1); }
  console.log('\nverify_bot_readiness.js — Scharfstellen-/Automatik-Status');
  console.log('='.repeat(60));
  BD.config.prefix = 'r1';
  const gridHtml = () => elements['r1-slots-grid'].innerHTML;

  // ── A: Live unarmed + laufende Challenge ──────────────────────────
  BD.renderSlots({ slots: [
    { slot_id: 'sX', kind: 'strategy', strategy_id: 101, stage: 'live',
      armed: false, account_id: 999, holder: 101, assets: [], challenge: null },
    { slot_id: 'iY', kind: 'rotation', stage: 'shadow', armed: null, holder: null,
      assets: [], challenge: { candidate: 786, day: 1, days_total: 14, trades: 0, net_eur: 0 } },
  ] });
  await sleep(20);
  check('A Strip: „bereit für Scharfstellen“ + „wartet auf dein OK“',
    gridHtml().indexOf('bereit für Scharfstellen') !== -1 &&
    gridHtml().indexOf('wartet auf dein OK') !== -1);
  check('A Strip: amber (action) + Spanning (grid-column)',
    gridHtml().indexOf('grid-column:1/-1') !== -1 &&
    gridHtml().indexOf('rgba(210,153,34,0.12)') !== -1);
  check('A Konto-Zeile: „🔒 bereit für Scharfstellen — dein OK“',
    gridHtml().indexOf('🔒 bereit für Scharfstellen — dein OK') !== -1);
  check('A Badge: „OK nötig“ statt „GESPERRT“',
    gridHtml().indexOf('🔴 LIVE · OK nötig') !== -1 && gridHtml().indexOf('GESPERRT') === -1);
  check('A Live-Wait hat Vorrang vor Challenge-Zeile',
    gridHtml().indexOf('Automatik läuft') === -1);

  // ── B: Challenge ready (Demo) ─────────────────────────────────────
  BD.renderSlots({ slots: [
    { slot_id: 'i4', kind: 'rotation', stage: 'shadow', armed: null, holder: null,
      assets: [], challenge: { candidate: 786, ready: true, day: 5, days_total: 14,
                               trades: 4, net_eur: 12.5, net_positive: true } },
  ] });
  await sleep(20);
  check('B Strip: „⚡ bereit — Fill läuft automatisch“ + Slot + #786',
    gridHtml().indexOf('Fill läuft automatisch beim nächsten Engine-Lauf: i4 (#786)') !== -1);
  check('B Strip: blau (info)',
    gridHtml().indexOf('rgba(59,130,246,0.10)') !== -1);

  // ── C: Challenge läuft ────────────────────────────────────────────
  BD.renderSlots({ slots: [
    { slot_id: 'i2', kind: 'rotation', stage: 'shadow', armed: null, holder: null,
      assets: [], challenge: { candidate: 782, day: 2, days_total: 14, trades: 1, net_eur: -3 } },
  ] });
  await sleep(20);
  check('C Strip: „⏳ Automatik läuft — Challenge #782 · Tag 2/14“',
    gridHtml().indexOf('Automatik läuft — Challenge #782 · Tag 2/14') !== -1);

  // ── D: nichts offen (geplante Plätze zählen nicht) ────────────────
  BD.renderSlots({ slots: [
    { slot_id: 'i5', kind: 'planned', stage: 'planned', holder: null, assets: [],
      challenge: null, note: 'Reserve' },
  ] });
  await sleep(20);
  check('D Strip: „✅ Keine Aktion nötig — alles läuft automatisch“',
    gridHtml().indexOf('Keine Aktion nötig — alles läuft automatisch') !== -1);
  check('D Strip: grün (ok)',
    gridHtml().indexOf('rgba(63,185,80,0.10)') !== -1);

  // ── E: leere Slots → Sektion versteckt, kein Strip, kein Crash ────
  elements['r1-slots-grid'].innerHTML = '';
  BD.renderSlots({ slots: [] });
  await sleep(20);
  check('E leere Slots: Sektion versteckt, Grid leer',
    elements['r1-slots-section'].style.display === 'none' &&
    gridHtml() === '');

  if (fatal) { console.log('\nFATAL: ' + fatal); process.exit(1); }
  console.log('\nRESULT: ' + PASS + '/' + (PASS + FAIL) + ' PASS' + (FAIL ? ' — FAILED' : ''));
  process.exit(FAIL ? 1 : 0);
})();