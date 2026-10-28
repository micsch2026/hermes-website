#!/usr/bin/env node
/**
 * verify_trade_focus.js — Node-Checks der Timeframe-Logik des Trade-Fokus-Charts.
 *
 * User-Vorgabe 28.10.2026: Der Chart darf nie feiner zeichnen als das Signal.
 *   4H-Strategie → 4H/1D, 1H-Strategie → 1H/4H/1D, 15m-Strategie → 15m/1H/4H/1D.
 * Geprüft: _tfSeconds (Engine- und Dashboard-Schreibweise), _tfOptions,
 * _aggregateBars (H1→H4, OHLC), _inferTF, _defaultRangeDays.
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

global.window = { location: { origin: 'http://stub' } };
global.document = { getElementById: () => null, createElement: () => ({ appendChild(){}, style:{} }) };
global.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
global.LightweightCharts = undefined;

let loadErr = null;
try { vm.runInThisContext(fs.readFileSync(SRC, 'utf8'), { filename: 'bot-components.js' }); }
catch (e) { loadErr = e; }
const BD = global.window.BotDash;
check('bot-components.js geladen, BotDash._tf vorhanden', !loadErr && !!(BD && BD._tf),
  loadErr ? String(loadErr).split('\n')[0] : '');
if (!BD || !BD._tf) { console.log('TRADE-FOCUS TESTS FAILED'); process.exit(1); }
const T = BD._tf;

// 1) Schreibweisen
check('TF 1h (Engine/Tree) = 3600', T.seconds('1h') === 3600, String(T.seconds('1h')));
check('TF 4h (Engine/Tree) = 14400', T.seconds('4h') === 14400, String(T.seconds('4h')));
check('TF H1 (Dashboard) = 3600', T.seconds('H1') === 3600, String(T.seconds('H1')));
check('TF M15 (Dashboard) = 900', T.seconds('M15') === 900, String(T.seconds('M15')));

// 2) Optionen: nie feiner als die Strategie
const o4 = T.options(14400).map(x => x.l);
const o1 = T.options(3600).map(x => x.l);
const o15 = T.options(900).map(x => x.l);
check('4H-Strategie: 4H/1D, KEIN 1H/15m', JSON.stringify(o4) === JSON.stringify(['4H','1D']), JSON.stringify(o4));
check('1H-Strategie: 1H/4H/1D, KEIN 15m', JSON.stringify(o1) === JSON.stringify(['1H','4H','1D']), JSON.stringify(o1));
check('15m-Strategie: 15m/1H/4H/1D', JSON.stringify(o15) === JSON.stringify(['15m','1H','4H','1D']), JSON.stringify(o15));

// 3) Aggregation H1 → H4 (OHLC + Volumen)
const H1 = [];
const BASE = 1793000000 - (1793000000 % 14400); // auf 4H-Bucket ausrichten
for (let i = 0; i < 8; i++) {
  H1.push({ time: BASE + i * 3600, open: 100 + i, high: 101 + i, low: 99 + i, close: 100.5 + i, volume: 10 });
}
const H4 = T.aggregate(H1, 14400);
check('8×H1 → 2×H4', H4.length === 2, String(H4.length));
check('H4-Open = erstes H1-Open', H4[0].open === 100, String(H4[0].open));
check('H4-Close = letztes H1-Close', Math.abs(H4[0].close - 103.5) < 1e-9, String(H4[0].close));
check('H4-High = max High', H4[0].high === 104, String(H4[0].high));
check('H4-Low = min Low', H4[0].low === 99, String(H4[0].low));
check('H4-Volumen summiert', H4[0].volume === 40, String(H4[0].volume));

// 4) Daten-TF-Erkennung
const infer = T.infer(H1);
check('_inferTF erkennt H1', infer === 3600, String(infer));

// 5) Default-Zeitraum je TF
check('Default 1H = 3 Tage', T.defaultRange(3600) === 3, String(T.defaultRange(3600)));
check('Default 4H = 14 Tage', T.defaultRange(14400) === 14, String(T.defaultRange(14400)));

console.log(PASS + ' PASS, ' + FAIL + ' FAIL');
if (FAIL) { console.log('TRADE-FOCUS TESTS FAILED'); process.exit(1); }
console.log('TRADE-FOCUS TESTS OK');
