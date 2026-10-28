/*
 * bot-components.js — Shared Bot Dashboard Components
 *
 * Requires: Chart.js, LightweightCharts (loaded by template)
 * All functions are namespaced under BotDash.* to avoid collisions.
 *
 * Usage:
 *   BotDash.init(config);        // call once on page load
 *   BotDash.loadDashboard();     // call on interval
 */
(function() {
'use strict';

/* ═══════════════════════════════════════════════════════════
 *  CONFIG (set by BotDash.init)
 * ═══════════════════════════════════════════════════════════ */
var C = {
  prefix: 'bot',       // CSS prefix for this page
  apiBase: '',          // e.g. '/api/fx'
  dashboardPath: '',    // e.g. '/api/fx/dashboard.json'
  chartsPath: '',       // e.g. '/api/fx/charts/'
  heatmapPath: '',      // e.g. '/api/fx/performance_heatmap.json'
  refreshInterval: 60000,
  hasEquity: true,
  hasSignals: true,
  hasCandlestick: true,
  hasHeatmap: true,
};

var _chartInstances = {};
var _candleChart = null;
var _allTradeMarkers = [];
var _rsiChart = null;
var _currentPair = null;
var _allPairs = [];
var _showTradeLines = true;

/* ═══════════════════════════════════════════════════════════
 *  HELPERS
 * ═══════════════════════════════════════════════════════════ */

function el(id) { return document.getElementById(id); }

function safeFetch(path, opts) {
  var url = window.location.origin + path +
    (path.indexOf('?') >= 0 ? '&' : '?') + '_t=' + Date.now();
  opts = opts || {};
  opts.cache = 'no-store';
  opts.credentials = 'same-origin';
  return fetch(url, opts);
}

/** Format ISO timestamp → Berlin time. Always appends 'Z' if missing. */
function fmtTime(iso) {
  if (!iso) return '—';
  try {
    if (typeof iso === 'number') iso = new Date(iso * 1000);
    else {
      if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(iso)) iso += 'Z';
      iso = new Date(iso);
    }
    return iso.toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit',
      timeZone: 'Europe/Berlin'
    });
  } catch(e) { return String(iso); }
}

function fmtPrice(p, pair) {
  if (p == null) return '—';
  if (String(pair || '').indexOf('JPY') >= 0) return Number(p).toFixed(3);
  return Number(p).toFixed(5);
}

function fmtPnl(val) {
  if (val == null) return '—';
  return (val >= 0 ? '+' : '') + Number(val).toFixed(2);
}

function pnlClass(val) {
  return Number(val) >= 0 ? 'bot-pnl-pos' : 'bot-pnl-neg';
}

function fmtCloseReason(status, close_reason) {
  if (close_reason) return close_reason;
  if (!status) return '—';
  var map = {
    tp_hit:           { label: 'TP',        cls: 'bot-badge-buy' },
    sl_hit:           { label: 'SL',        cls: 'bot-badge-sell' },
    timeout:          { label: 'Timeout',   cls: 'bot-badge-warn' },
    manually_closed:  { label: 'Manuell',   cls: '' },
    closed_by_us:     { label: 'Bot Close', cls: '' },
    closed:           { label: 'Closed',    cls: '' },
    tp_sl_closed:     { label: 'TP/SL',     cls: '' },
    test_close:       { label: 'Test',      cls: 'bot-badge-warn' },
    phantom_closed:   { label: 'Phantom',   cls: '' },
  };
  var m = map[status];
  if (m) {
    return m.cls ? '<span class="bot-badge ' + m.cls + '">' + m.label + '</span>' : m.label;
  }
  return status;
}

function dotClass(active) {
  return 'bot-status-dot ' + (active ? 'green' : 'red');
}

function fmtDuration(openedAt) {
  if (!openedAt) return '—';
  try {
    var s = openedAt;
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
    var opened = new Date(s);
    var diffMs = Date.now() - opened.getTime();
    var diffH = diffMs / 3600000;
    if (diffH < 1) return Math.round(diffMs / 60000) + 'm';
    if (diffH < 24) return diffH.toFixed(1) + 'h';
    return Math.floor(diffH / 24) + 'd ' + Math.floor(diffH % 24) + 'h';
  } catch(e) { return '—'; }
}

function fmtVolume(vol) {
  if (vol == null) return '—';
  var lots = vol / 10000000;
  if (lots >= 1) return lots.toFixed(1) + ' lot';
  return (lots * 100).toFixed(0) + ' ct';
}

function findNearestBarTime(bars, isoTime) {
  if (!isoTime || !bars || bars.length === 0) return null;
  var ts;
  if (typeof isoTime === 'number') {
    ts = isoTime > 1e12 ? isoTime / 1000 : isoTime;
  } else {
    var s = isoTime;
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
    ts = new Date(s).getTime() / 1000;
  }
  if (isNaN(ts)) return null;
  var best = null, bestDiff = Infinity;
  for (var i = 0; i < bars.length; i++) {
    var diff = Math.abs(bars[i].time - ts);
    if (diff < bestDiff) { bestDiff = diff; best = bars[i].time; }
  }
  return best;
}

/* ═══════════════════════════════════════════════════════════
 *  RENDERERS — Common Sections
 * ═══════════════════════════════════════════════════════════ */

/** Status bar: dot, status text, mode badge, last update */
function renderStatus(d) {
  var isActive = d.status ? d.status.active !== false : true;
  var isPaused = !!(d.paused || (d.status && d.status.paused));
  var mode = d.mode || (d.demo ? 'demo' : 'live');

  var dot = el(C.prefix + '-dot');
  if (dot) dot.className = isPaused ? 'bot-status-dot gray' : dotClass(isActive);

  var statusEl = el(C.prefix + '-status');
  if (statusEl) {
    var msg = (d.status && d.status.message) || '';
    // Builder-Jargon ("Scanning 7 pairs") → Anzeige-Sprache.
    var scan = /^Scanning\s+(\d+)\s+pairs?/i.exec(msg);
    if (scan) msg = 'läuft · ' + scan[1] + (String(scan[1]) === '1' ? ' Asset' : ' Assets');
    statusEl.textContent = isPaused
      ? (msg || '⏸ GEPARKT — kein Trading')
      : (isActive ? (msg || 'läuft') : 'gestört');
  }

  var badge = el(C.prefix + '-mode-badge');
  if (badge) {
    if (mode === 'mixed') {
      // LIVE/DEMO-Split (13.10.2026): Bot handelt auf Live- UND Demo-Konto
      badge.textContent = 'LIVE + DEMO';
      badge.className = 'bot-badge bot-badge-live';
    } else {
      badge.textContent = mode.toUpperCase();
      badge.className = 'bot-badge ' + (mode === 'live' ? 'bot-badge-live' : 'bot-badge-demo');
    }
  }

  var upd = el(C.prefix + '-last-update');
  if (upd) upd.textContent = 'Daten: ' + fmtTime(d.timestamp || d.last_update);

  // Health banner
  var banner = el(C.prefix + '-health-banner');
  if (!banner) return;
  var healthText = el(C.prefix + '-health-text');
  var healthTime = el(C.prefix + '-health-time');
  var st = d.status || {};
  var bannerVisible = false;

  // Market-closed detection: if message says "Market closed", it's NOT an error.
  // FX market: closed Fri 21:00 — Sun 21:00 UTC. Sync pauses, stale data is expected.
  var msgLower = (st.message || '').toLowerCase();
  var isMarketClosed = msgLower.indexOf('market closed') >= 0;
  // Geparkter Bot: kein Fehler-Banner, sondern Info-Banner (25.09.2026)
  var isPaused = !!(d.paused || st.paused);

  if (isPaused) {
    banner.className = 'bot-health-banner visible info';
    if (healthText) healthText.textContent = st.message || '⏸ GEPARKT — kein Trading, kein Auto-Heal';
    if (healthTime) healthTime.textContent = '';
    bannerVisible = true;
  } else if (!isActive && !isMarketClosed) {
    banner.className = 'bot-health-banner visible error';
    if (healthText) healthText.textContent = st.last_error_msg || st.message || 'Connection lost';
    if (healthTime) healthTime.textContent = 'since ' + fmtTime(st.last_error);
    bannerVisible = true;
  } else if (st.consecutive_errors > 0) {
    banner.className = 'bot-health-banner visible warn';
    if (healthText) healthText.textContent = st.consecutive_errors + ' recent error(s). Last: ' + (st.last_error_msg || 'unknown');
    if (healthTime) healthTime.textContent = 'last OK: ' + fmtTime(st.last_success);
    bannerVisible = true;
  } else if (isMarketClosed) {
    banner.className = 'bot-health-banner visible info';
    if (healthText) healthText.textContent = st.message || '🔒 Market closed — sync paused';
    if (healthTime) healthTime.textContent = '';
    bannerVisible = true;
  }
  // (kein separates "Data may be stale"-Banner: FIX 2026-08-21)
  // Die Früschheits-Bewertung gehört dem Status-Builder (is_healthy, max_age 20min):
  // bei zu altem last_success setzt der Builder active=false → der "Bot inactive"-
  // Branch oben (Zeile 191) zeigt den Grund ehrenhaft an. Eine zweite, eigene
  // health_age-Schwelle hier führte nur zu einer irreitenden Dauerwarnung auf
  // 15-min-Zyklus-Bots (Standort: align sync ~3min, Executor-Heartbeat ~15min).
  if (!bannerVisible) banner.className = 'bot-health-banner';
}

/** KPI Cards: Balance, Equity, Positions, Daily P&L, Total P&L */
function renderKPIs(d) {
  // Balance — flexible path: account.balance / live_balance.balance / balance
  var bal = (d.account && d.account.balance != null) ? d.account.balance : (d.live_balance ? d.live_balance.balance : d.balance);
  var eq  = (d.account && d.account.equity  != null) ? d.account.equity  : (d.live_balance ? d.live_balance.equity  : d.equity);
  var balEl = el(C.prefix + '-balance');
  if (balEl) balEl.textContent = bal != null ? '€' + Number(bal).toFixed(2) : '—';
  var eqEl = el(C.prefix + '-equity-sub');
  if (eqEl) eqEl.textContent = eq != null ? 'Equity: €' + Number(eq).toFixed(2) : '';

  // Positions
  var rawPos = d.positions || [];
  var pos = Array.isArray(rawPos) ? rawPos : (rawPos.open || []);
  var posEl = el(C.prefix + '-positions-count');
  if (posEl) posEl.textContent = pos.length;
  var posSub = el(C.prefix + '-positions-sub');
  if (posSub) {
    var margin = d.performance ? d.performance.total_margin_eur : null;
    var marginText = margin != null ? ' | Margin: €' + margin.toFixed(2) : '';
    posSub.textContent = pos.length + ' open' + marginText;
  }

  // Daily P&L
  var daily = d.daily_pnl != null ? d.daily_pnl
    : (d.performance ? (d.performance.daily_pnl || 0) : 0);
  var dailyEl = el(C.prefix + '-daily-pnl');
  if (dailyEl) {
    dailyEl.textContent = fmtPnl(daily) + ' EUR';
    dailyEl.className = 'bot-card-value ' + pnlClass(daily);
  }
  // Fix 08.10.2026: trades_today/daily/realized liegen im performance-Block des
  // Builders (build_trend_status.py) — Top-Level-Felder existieren nicht (mehr).
  // Fallback-Kette: Top-Level (Legacy) -> performance{}.
  var perf = d.performance || {};
  var tradesToday = (d.trades_today != null ? d.trades_today : (perf.trades_today || 0));
  var ttEl = el(C.prefix + '-trades-today');
  if (ttEl) ttEl.textContent = tradesToday + ' trade' + (tradesToday === 1 ? '' : 's') + ' today';

  // Total P&L — Gesamtwert der aktuellen Strategie(n) (performance.total_pnl,
  // konsistent zu den W/L-Zählern); Fallback: realisiert+offen (Alt-Vertrag).
  var realized = (d.realized_pnl != null ? d.realized_pnl : (perf.realized_pnl || 0));
  var unrealized = (d.unrealized_pnl != null ? d.unrealized_pnl : (perf.unrealized_pnl || perf.open_pnl || 0));
  var totalPnl = (d.total_pnl != null ? d.total_pnl
    : (perf.total_pnl != null ? perf.total_pnl : realized + unrealized));
  var totalEl = el(C.prefix + '-total-pnl');
  if (totalEl) {
    totalEl.textContent = fmtPnl(totalPnl) + ' EUR';
    totalEl.className = 'bot-card-value ' + pnlClass(totalPnl);
  }
  var wrSub = el(C.prefix + '-winrate-sub');
  if (wrSub) wrSub.textContent = (perf.total_trades || 0) + ' total trades';

  // Echtgeld-Konten-Karten (LIVE/DEMO-Split). Ohne account_cards: nichts.
  var cards = d.account_cards || [];
  if (cards.length) {
    var kpiRow = el(C.prefix + '-kpi-row');
    for (var ci = 0; ci < cards.length; ci++) {
      var card = cards[ci] || {};
      var ctid = card.ctid != null ? String(card.ctid) : '';
      var cardId = C.prefix + '-ext-' + ctid;
      if (el(cardId)) continue;      // schon gerendert → nicht duplizieren
      if (!kpiRow) continue;
      var cdiv = document.createElement('div');
      cdiv.className = 'bot-card';
      cdiv.id = cardId;
      cdiv.style.padding = 'var(--s-3) var(--s-4)';
      // 18.10.2026: Karten-Typ aus dem Datenvertrag (is_live/label) —
      // bot5/7 = 🔴 Echtgeld-Host, bot9 = 🧪 Demo-Seite. Default bleibt Echtgeld.
      var _cardLive = card.is_live !== false;
      var _cardLbl = card.label || (_cardLive ? 'Echtgeld' : 'Demo');
      cdiv.innerHTML =
        '<div class="bot-card-title">' + (_cardLive ? '🔴 ' : '🧪 ') + _cardLbl + ' ' + ctid + '</div>' +
        '<div class="bot-card-value">€' + Number(card.balance || 0).toFixed(2) + '</div>' +
        '<div class="bot-card-sub">Equity: €' + Number(card.equity || 0).toFixed(2) + '</div>';
      kpiRow.appendChild(cdiv);
    }
  }
}

/** Performance metrics: Win Rate, PF, Expectancy, Max DD */
function renderPerformance(d) {
  var perf = d.performance || {};
  var totalTrades = perf.total_trades || 0;
  var wins = perf.wins || perf.winning_trades || perf.win_count || 0;
  var losses = perf.losses || perf.losing_trades || perf.loss_count || 0;
  var wr = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) + '%' : '—';

  var wrEl = el(C.prefix + '-winrate');
  if (wrEl) {
    wrEl.textContent = totalTrades > 0 ? wr : '—';
    if (totalTrades > 0) {
      var wrNum = (wins / totalTrades) * 100;
      wrEl.className = 'bot-card-value ' + (wrNum >= 50 ? 'bot-pnl-pos' : 'bot-pnl-neg');
    } else {
      wrEl.className = 'bot-card-value';
    }
  }
  var wrDetail = el(C.prefix + '-winrate-detail');
  if (wrDetail) wrDetail.textContent = totalTrades > 0 ? (wins + 'W / ' + losses + 'L') : 'Warten auf Trades';

  var pf = perf.profit_factor;
  var pfEl = el(C.prefix + '-profit-factor');
  if (pfEl) {
    pfEl.textContent = totalTrades > 0 && pf != null ? Number(pf).toFixed(2) : '—';
    if (totalTrades > 0 && pf != null) {
      pfEl.className = 'bot-card-value ' + (pf >= 1.5 ? 'bot-pnl-pos' : 'bot-pnl-neg');
    } else {
      pfEl.className = 'bot-card-value';
    }
  }

  var exp = perf.expectancy;
  var expEl = el(C.prefix + '-expectancy');
  if (expEl) {
    if (totalTrades > 0 && exp != null) {
      expEl.textContent = 'Exp: ' + (exp >= 0 ? '+' : '') + Number(exp).toFixed(2) + ' EUR';
      expEl.className = 'bot-card-sub ' + pnlClass(exp);
    } else {
      expEl.textContent = 'Exp: —';
      expEl.className = 'bot-card-sub';
    }
  }

  var dd = perf.max_drawdown || perf.max_drawdown_pct || 0;
  var ddEl = el(C.prefix + '-max-dd');
  if (ddEl) {
    ddEl.textContent = 'DD: ' + Number(dd).toFixed(2) + '%';
    ddEl.className = 'bot-card-value ' + (dd <= 10 ? 'bot-pnl-pos' : 'bot-pnl-neg');
  }

  // Margin utilization (F12)
  var mu = perf.margin_utilization_pct;
  var muEl = el(C.prefix + '-margin-util');
  if (muEl) {
    muEl.textContent = 'Margin: ' + (mu != null ? Number(mu).toFixed(1) + '%' : '—');
    muEl.className = 'bot-card-sub ' + (mu <= 50 ? 'bot-pnl-pos' : mu <= 80 ? '' : 'bot-pnl-neg');
  }
}

var _ageTimer = null;

/** Data age indicator — ticks every second */
function renderDataAge(d) {
  var ageEl = el(C.prefix + '-data-age');
  if (!ageEl) return;

  var ts = d.timestamp || d.generated_at;
  if (!ts) { ageEl.textContent = ''; return; }

  // Clear previous timer
  if (_ageTimer) clearInterval(_ageTimer);

  function tick() {
    var dataTime = new Date(ts.endsWith('Z') || /[+\-]\d{2}:?\d{2}$/.test(ts) ? ts : ts + 'Z');
    var now = new Date();
    var diffSec = Math.max(0, Math.floor((now - dataTime) / 1000));
    var min = Math.floor(diffSec / 60);
    var sec = diffSec % 60;
    var text = min > 0 ? (min + 'm ' + sec + 's') : (sec + 's');
    ageEl.textContent = '· vor ' + text;

    // Color: green <2min, neutral 2-5min, dim >5min
    if (diffSec < 120) {
      ageEl.style.color = '#22c55e';
      ageEl.style.opacity = '0.8';
    } else if (diffSec < 300) {
      ageEl.style.color = '';
      ageEl.style.opacity = '0.6';
    } else {
      ageEl.style.color = '#f59e0b';
      ageEl.style.opacity = '0.8';
    }
  }

  tick();
  _ageTimer = setInterval(tick, 1000);
}

/** 16.10.2026 (User): 💰 ECHTGELD / 🧪 DEMO-Kennzeichnung — offene Positionen + Trade-Historie.
 *  row.live kommt aus build_trend_status.py (Registry: Konto is_live; null = unbekannt). */
function _liveBadge(row) {
  if (!row) return '';
  var acct = row.account_id ? ' (Konto ' + escHtml(row.account_id) + ')' : '';
  if (row.live === true) {
    return '<span class="bot-badge bot-badge-gold" style="font-size:10px" title="ECHTGELD' + acct + '">💰 ECHTGELD</span>';
  }
  if (row.live === false) {
    return '<span class="bot-badge" style="font-size:10px" title="DEMO' + acct + '">🧪 DEMO</span>';
  }
  return '';
}

/** Open positions table — columns from C.position_columns config */
function renderPositions(d) {
  var tbody = el(C.prefix + '-positions-body');
  if (!tbody) return;
  var raw = d.positions || [];
  var pos = Array.isArray(raw) ? raw : (raw.open || []);
  var cols = C.position_columns;

  // If no column config, fall back to legacy hardcoded columns
  if (!cols || !cols.length) {
    _renderPositionsLegacy(tbody, pos);
    return;
  }

  // Generate thead if it exists and is empty
  var thead = tbody.parentElement ? tbody.parentElement.querySelector('thead tr') : null;
  if (thead && thead.children.length <= 1) {
    var thHtml = '';
    for (var c = 0; c < cols.length; c++) {
      thHtml += '<th>' + cols[c].label + '</th>';
    }
    thead.innerHTML = thHtml;
  }

  if (pos.length === 0) {
    tbody.innerHTML = '<tr><td colspan="' + cols.length + '" class="bot-no-data">No open positions</td></tr>';
    return;
  }

  var html = '';
  _focusStore.pos = {};
  for (var i = 0; i < pos.length; i++) {
    var p = pos[i];
    var sym = p.symbol || p.pair || '—';
    var fk = _putFocus('pos', _focusFromPosition(d, p));
    html += '<tr class="bot-pos-row" title="Chart mit Trade-Fokus öffnen" onclick="BotDash.openTradeChart(\'' + escHtml(sym) + '\',\'' + fk + '\')">';
    for (var c = 0; c < cols.length; c++) {
      var col = cols[c];
      var val = _resolveField(p, col.field || col.key);
      var _lb = (c === 0) ? _liveBadge(p) : '';
      html += '<td>' + (_lb ? _lb + ' ' : '') + _fmtCell(val, col.fmt, p) + '</td>';
    }
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

/** Resolve nested field like "tradeData.volume" */
function _resolveField(obj, field) {
  if (!field) return null;
  var parts = field.split('.');
  var v = obj;
  for (var i = 0; i < parts.length; i++) {
    if (v == null) return null;
    v = v[parts[i]];
  }
  return v;
}

/** Format a cell value based on fmt type */
function _fmtCell(val, fmt, row) {
  if (val == null || val === '') return '—';
  switch (fmt) {
    case 'bold': return '<b>' + val + '</b>';
    case 'lots':
      // cTrader volume: 10000000 = 1 lot
      var lots = Number(val) / 10000000;
      return lots.toFixed(2) + ' Lots';
    case 'direction':
      var d = String(val).toLowerCase();
      if (d === 'sell' || d === 'short')
        return '<span class="bot-badge bot-badge-sell">Verkaufen</span>';
      return '<span class="bot-badge bot-badge-buy">Kaufen</span>';
    case 'price':
      var sym = row.symbol || row.pair || '';
      return fmtPrice(val, sym);
    case 'pnl':
      var pnlOut = '<span class="' + pnlClass(val) + '"><b>' + fmtPnl(val) + '</b></span>';
      // FIX 2026-10-16: Markt geschlossen (o. kein frischer Feed) → Wert basiert auf
      // letztem verfügbaren Kurs; Stand-Kennzeichnung via live_price_asof (Tooltip).
      if (row && row.live_price_asof) {
        pnlOut += ' <span title="Letzter verfügbarer Kurs — Stand ' + fmtTime(row.live_price_asof) + '" style="font-size:10px;color:var(--c-text-dim);cursor:help">⏸</span>';
      }
      return pnlOut;
    case 'datetime':
      // Show UTC time like cTrader: DD/MM/YYYY HH:MM:SS
      try {
        var dt = typeof val === 'number' ? new Date(val) : new Date(val);
        var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
        return pad(dt.getUTCDate()) + '/' + pad(dt.getUTCMonth()+1) + '/' + dt.getUTCFullYear()
          + ' ' + pad(dt.getUTCHours()) + ':' + pad(dt.getUTCMinutes()) + ':' + pad(dt.getUTCSeconds());
      } catch(e) { return String(val); }
    case 'duration':
      return fmtDuration(val);
    case 'margin':
      return '€' + Number(val).toFixed(2);
    case 'score':
      var sc = Number(val);
      var cls = sc >= 60 ? 'bot-pnl-pos' : (sc >= 50 ? '' : 'bot-pnl-neg');
      return '<span class="' + cls + '"><b>' + sc + '</b></span>';
    case 'strategy':
      // Multibot: Strategie-ID (#NNN) + Slot-Badge (s534/d5/i4/...) — konsistent zur Trade-History
      var sidStr = String(val).replace(/^#/, '');
      if (!sidStr) return '—';
      var stratOut = '<b>#' + escHtml(sidStr) + '</b>';
      var slotVal = (row && row.slot_id != null && row.slot_id !== '') ? String(row.slot_id) : '';
      if (slotVal) stratOut += ' <span class="bot-badge bot-badge-warn" style="font-size:10px" title="Slot">' + escHtml(slotVal) + '</span>';
      return stratOut;
    default:
      return String(val);
  }
}

/** Legacy hardcoded positions renderer (fallback when no column config) */
function _renderPositionsLegacy(tbody, pos) {
  if (pos.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" class="bot-no-data">No open positions</td></tr>';
    return;
  }
  var html = '';
  for (var i = 0; i < pos.length; i++) {
    var p = pos[i];
    var dir = (p.direction || p.side || '').toLowerCase();
    var dirBadge = (dir === 'sell' || dir === 'short')
      ? '<span class="bot-badge bot-badge-sell">SHORT</span>'
      : '<span class="bot-badge bot-badge-buy">LONG</span>';
    var upnl = p.unrealized_pnl != null ? p.unrealized_pnl : (p.pnl || 0);
    var sym = p.symbol || p.pair || '—';
    var stratId = p.strategy_id || '—';
    var fkL = _putFocus('pos', _focusFromPosition({}, p));
    html += '<tr class="bot-pos-row" title="Chart mit Trade-Fokus öffnen" onclick="BotDash.openTradeChart(\'' + escHtml(sym) + '\',\'' + fkL + '\')">';
    var _lbLeg = _liveBadge(p);
    html += '<td style="font-size:var(--text-xs);color:var(--c-text-dim)">' + (_lbLeg ? _lbLeg + ' ' : '') + stratId + '</td>';
    html += '<td><b>' + sym + '</b></td>';
    html += '<td>' + dirBadge + '</td>';
    var sc = p.score != null ? p.score : '—';
    var scClass = sc >= 60 ? 'bot-pnl-pos' : (sc >= 50 ? '' : 'bot-pnl-neg');
    html += '<td style="font-size:var(--text-xs)" class="' + scClass + '"><b>' + sc + '</b></td>';
    html += '<td>' + fmtPrice(p.entry_price || p.entry, sym) + '</td>';
    html += '<td>' + fmtPrice(p.sl_price || p.sl, sym) + '</td>';
    html += '<td>' + fmtPrice(p.tp_price || p.tp, sym) + '</td>';
    var margin = p.margin_eur;
    html += '<td>' + (margin != null ? '€' + Number(margin).toFixed(2) : '—') + '</td>';
    html += '<td style="font-size:var(--text-xs)">' + fmtVolume(p.volume) + '</td>';
    html += '<td class="' + pnlClass(upnl) + '"><b>' + fmtPnl(upnl) + '</b></td>';
    html += '<td style="font-size:var(--text-xs)">' + fmtDuration(p.opened_at || p.timestamp) + '</td>';
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

/** Trade history table (last 20) */
function renderHistory(d) {
  var tbody = el(C.prefix + '-history-body');
  if (!tbody) return;
  var trades = (d.trade_history || d.round_trips || d.last_trades || []).slice();
  // Sort by open time descending (newest first)
  trades.sort(function(a, b) {
    var ta = a.timestamp || a.closed_at || '';
    var tb = b.timestamp || b.closed_at || '';
    return tb.localeCompare(ta);
  });

  // Exit-Spalte nur zeigen, wenn Trades ein Exit-Feld tragen (Log-Gap: exit_price fehlt oft)
  var _htbl = el(C.prefix + '-history-table');
  if (_htbl && _htbl.classList) {
    var hasExit = false;
    for (var x = 0; x < trades.length; x++) {
      var _et = trades[x];
      if (_et.close_price || _et.exit_price || _et.current_price) { hasExit = true; break; }
    }
    if (hasExit) _htbl.classList.remove('no-exit'); else _htbl.classList.add('no-exit');
  }
  if (trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="bot-no-data">No completed trades</td></tr>';
    return;
  }
  var html = '';
  var limit = Math.min(trades.length, 20);
  for (var i = 0; i < limit; i++) {
    var t = trades[i];
    var dir = (t.direction || t.side || '').toLowerCase();
    var dirBadge = (dir === 'sell' || dir === 'short')
      ? '<span class="bot-badge bot-badge-sell">SHORT</span>'
      : '<span class="bot-badge bot-badge-buy">LONG</span>';
    var pnl = t.pnl != null ? t.pnl : (t.realized_pnl || t.profit || 0);
    var dur = t.duration || (t.duration_hours != null ? Number(t.duration_hours).toFixed(1) + 'h'
      : (t.hold_time_hours ? Number(t.hold_time_hours).toFixed(1) + 'h' : '—'));
    var sym = t.symbol || t.pair || '—';
    // 19.10.2026: fehlt eine strategy_id (z. B. bot4-Testpfad, strategy_id=0), den
    // ENGINE-Namen aus dem Trade-Record zeigen statt „—" — sonst wirken Trades ohne
    // deployte Strategie wie nicht zugeordnet.
    var stratId = t.strategy_id || t.strategy || '—';
    var _slot = (t.slot_id != null && t.slot_id !== '') ? t.slot_id : '';
    var slotBadge = _slot ? ' <span class="bot-badge bot-badge-warn" style="font-size:10px" title="Slot">' + escHtml(_slot) + '</span>' : '';
    var _lbH = _liveBadge(t);
    html += '<tr class="bot-pos-row" onclick="BotDash.openChart(\'' + sym + '\')">';
    html += '<td style="font-size:var(--text-xs);color:var(--c-text-dim)">' + stratId + slotBadge + (_lbH ? ' ' + _lbH : '') + '</td>';
    html += '<td>' + fmtTime(t.timestamp || t.close_time || t.closed_at) + '</td>';
    html += '<td><b>' + sym + '</b></td>';
    html += '<td>' + dirBadge + '</td>';
    html += '<td>' + fmtPrice(t.entry_price || t.open_price || t.entry, sym) + '</td>';
    html += '<td>' + fmtPrice(t.close_price || t.exit_price || t.current_price, sym) + '</td>';
    var histMargin = t.margin_eur;
    html += '<td style="font-size:var(--text-xs)">' + (histMargin != null ? '€' + Number(histMargin).toFixed(2) : '—') + '</td>';
    html += '<td class="' + pnlClass(pnl) + '"><b>' + fmtPnl(pnl) + '</b></td>';
    html += '<td style="font-size:var(--text-xs)">' + dur + '</td>';
    html += '<td>' + fmtCloseReason(t.status, t.close_reason) + '</td>';
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

/** HTML-Escape (Slots-Sektion, A2b) */
function escHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* ═══════════════════════════════════════════════════════════
 *  MULTIBOT-SLOTS — Strategie-Metadaten aus shadow_portfolio.json
 *  (Namen, Beschreibung, TF/Tier, OOS-Referenz; 15-Min-Refresh, gecacht)
 * ═══════════════════════════════════════════════════════════ */

var _spCache = null;
var _spLoading = false;
var _spWaiters = [];
var _lastSlotsD = null;

function _loadShadowPortfolio(cb) {
  if (_spCache) { cb(_spCache); return; }
  try {
    if (typeof fetch !== 'function' || !window || !window.location || !window.location.origin) { cb(null); return; }
  } catch (e) { cb(null); return; }
  // Läuft bereits ein Fetch? → Callback in die Warteschlange (statt cb(null),
  // sonst bleibt z.B. die Lab-Validierungstabelle beim ersten Load leer).
  if (_spLoading) { _spWaiters.push(cb); return; }
  _spLoading = true;
  function _flush(data) {
    var w = _spWaiters; _spWaiters = [];
    cb(data);
    for (var i = 0; i < w.length; i++) { try { w[i](data); } catch (e) {} }
  }
  try {
    safeFetch('/api/strategy-lab/shadow_portfolio.json').then(function(r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function(d) {
      _spCache = d; _spLoading = false;
      _flush(d);
    }).catch(function() { _spLoading = false; _flush(null); });
  } catch (e) { _spLoading = false; _flush(null); }
}

function _spShortName(nm) {
  return String(nm || '').replace(/^RCP-CLUSTER:\s*/, '').replace(/\s*\(\d{8}_\d{6}\)\s*$/, '');
}

/** Slot-Kacheln + Slot-Historie (Multibot; Datenlayer A1, Rendering A2b; Detail-Ausbau 2026-09-28) */
function renderSlots(d) {
  var wrap = el(C.prefix + '-slots-section');
  if (!wrap) return;
  var slots = d.slots || [];
  if (!slots.length) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  _lastSlotsD = d;
  _loadShadowPortfolio(function(sp) { _renderSlotsInner(_lastSlotsD || d, sp); });
}

/* 🎯 Rotations-Radar v2 (13.10.2026): Top-10-Kandidaten mit Stufen-Bewertung
 * (S0 Pool-Fit … S4 Fill-bereit), 95%-KI, Wave-Timeline („Warum bewegt sich
 * nichts"), Ausschluss-Breakdown. Altdaten-tolerant: fehlen neue Felder
 * (wave/ci95/…), degradiert die Anzeige — nie crashen. */

/** Datum-only Format (Timeline; wie fmtTime, ohne Uhrzeit). */
function fmtDate(iso) {
  if (!iso) return '—';
  try {
    if (typeof iso === 'number') iso = new Date(iso * 1000);
    else {
      if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(iso)) iso += 'Z';
      iso = new Date(iso);
    }
    return iso.toLocaleDateString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      timeZone: 'Europe/Berlin'
    });
  } catch(e) { return String(iso); }
}

/** Mini-Box der Stufen-Spalte (10px, 14px breit, Glyph + Tooltip). */
function _radarStage(glyph, color, title) {
  return '<span class="radar-stg" title="' + escHtml(title) + '" style="display:inline-block;width:14px;height:14px;line-height:14px;text-align:center;font-size:10px;border-radius:3px;margin-right:2px;color:' + color + ';background:rgba(139,148,158,0.10)">' + glyph + '</span>';
}

/** Stufen-Spalte je Kandidat: S0 Pool-Fit / S1 Evidenz / S2 Slot-Fit /
 *  S3 Challenge / S4 Fill-bereit (Semantik Spec D4.4). */
function _radarStageCell(c, wave) {
  var GRAY = '#8b949e', GREEN = '#3fb950', YELLOW = '#d29922', RED = '#f85149';
  var evCol = c.ev_grade === 'green' ? GREEN : (c.ev_grade === 'yellow' ? YELLOW : RED);
  var ch = c.challenge || null;
  var fillable = !!c.fillable;
  var ready = !!(ch && ch.ready);
  var s4ok = fillable && ready && !!(wave && wave.open);
  return _radarStage('✓', GREEN, 'S0 Pool-Fit: im Kandidaten-Pool (Score-Ordnung)') +
    _radarStage('●', evCol, 'S1 Evidenz: saubere KLASSEN-Trades n=' + (c.n_class != null ? c.n_class : '—') + ' (' + escHtml(c.ev_grade || 'red') + ')') +
    (fillable ? _radarStage('✓', GREEN, 'S2 Slot-Fit: keine Blockgründe — Pfade/Caps frei')
              : _radarStage('✕', GRAY, 'S2 Slot-Fit: blockiert — ' + escHtml(c.lacks || 'Gründe siehe Status'))) +
    (ready ? _radarStage('✓', GREEN, 'S3 Challenge: reif (≥3 saubere Trades, netto>0)')
      : (ch ? _radarStage('◐', YELLOW, 'S3 Challenge: läuft — ' + escHtml(c.lacks || ''))
            : _radarStage('–', GRAY, 'S3 Challenge: keine aktiv'))) +
    (s4ok ? _radarStage('✓', GREEN, 'S4 Fill-bereit: Challenge reif + Wave-Cap offen')
          : _radarStage('–', GRAY, 'S4 Fill-bereit: wartet (Challenge/Wave-Cap)'));
}

/** Timeline „Warum bewegt sich nichts?" (Spec D4.3; nur wenn wave vorhanden). */
function _radarTimeline(r) {
  var w = r.wave;
  if (!w) return '';
  var f30 = (r.fills_30d != null) ? r.fills_30d : 0;
  var h = '<div style="font-size:var(--text-xs);margin:0 0 4px">';
  if (w.last_fill_ts) {
    h += '⏱ Letzte Fills: ' + f30 + ' in 30 d · letzter: ' + escHtml(w.last_fill_label || '—') + ' (' + fmtDate(w.last_fill_ts) + ')';
  } else {
    h += '⏱ Letzte Fills: ' + f30 + ' in 30 d · noch kein Fill';
  }
  h += '</div>';
  h += '<div style="font-size:var(--text-xs);margin:0 0 4px">Wave-Cap: ' +
    (w.open ? 'frei' : ('frei ab ' + fmtDate(w.unlock_ts))) + '</div>';
  var ca = r.challenges_active || [];
  if (ca.length) {
    var parts = [];
    for (var i = 0; i < ca.length; i++) {
      var e = ca[i];
      parts.push(escHtml(e.slot_id || '—') + ' #' + escHtml(e.candidate != null ? e.candidate : '?') + ' ' + (e.trades || 0) + '/3' + (e.ready ? ' ✓' : ''));
    }
    h += '<div style="font-size:var(--text-xs);margin:0 0 4px">Challenges: ' + parts.join(' · ') + '</div>';
  }
  h += '<div style="font-size:10px;color:var(--c-text-dim);margin:0 0 6px">Hinweis: Bei dieser Challenge-Frequenz ist ein Stillstand von Tagen normal (n klein).</div>';
  return h;
}

/** Ausschluss-Breakdown-Zeile (Spec D4.2; Label-Map, Fallback rohes Token). */
function _radarExclusionLine(r) {
  var bd = r.excluded_breakdown || [];
  if (!bd.length) return '';
  var map = {
    'min_asset_trades': 'ohne ≥5 Klassentrades',
    'not_selected': 'nicht in Shadow-Auswahl',
    'inactive': '>42 d inaktiv',
    'catalog_status:rejected': 'Katalog rejected',
    'catalog_status:archived': 'Katalog archiviert',
    'asset_bust': 'Asset-Bust',
    'global_bust': 'Bust'
  };
  var parts = [];
  for (var i = 0; i < bd.length; i++) {
    var tok = bd[i].reason;
    parts.push(escHtml(map[tok] || tok) + ' (' + bd[i].count + ')');
  }
  return '<div style="font-size:10px;color:var(--c-text-dim);margin-bottom:8px">Ausschlüsse u. a.: ' + parts.join(' · ') + ' (Mehrfachnennungen möglich)</div>';
}

function _renderRotationRadar(d, spById, nameById) {
  var box = el(C.prefix + '-radar');
  if (!box) return;
  var r = d.rotation_radar;
  if (!r) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  var cands = r.candidates || [];
  function candName(sid) {
    var m = spById[sid] || spById[String(sid)];
    if (m && m.name) return _spShortName(m.name);
    return nameById[sid] || nameById[String(sid)] || '';
  }
  var h = '';
  h += '<div style="font-weight:700;font-size:var(--text-md);margin-bottom:2px">🎯 Rotations-Radar</div>';
  h += '<div style="font-size:10px;color:var(--c-text-dim);margin-bottom:8px">Kandidaten-Pool ' +
    escHtml(r.target_class || '') + ' · Stand ' + fmtTime(r.generated_at) + ' · ' +
    (function(){
      var uniq = (r.pool_unique != null) ? r.pool_unique : null;
      var asg = (r.assignments != null) ? r.assignments : null;
      if (uniq != null && asg != null) {
        var tip = asg + ' = Bot/Slot-Zuordnungen, ' + uniq + ' = eindeutige Strategien (Stand ' + fmtTime(r.generated_at) + ')';
        return '<span title="' + escHtml(tip) + '">' + uniq + ' Kandidaten · ' + asg + ' Zielzuordnungen</span>';
      }
      return (r.pool_size || 0) + ' Kandidaten';
    })() + ' · Top ' + (r.shown != null ? r.shown : cands.length) +
    ' gezeigt (' + (r.excluded || 0) + ' exkludiert)</div>';
  h += _radarExclusionLine(r);
  h += _radarTimeline(r);
  if (!cands.length) {
    h += '<div style="font-size:var(--text-xs);color:var(--c-text-dim)">Keine Kandidaten im Pool — Lernphase bzw. keine qualifizierte Strategie für diese Klasse.</div>';
  } else {
    h += '<table style="width:100%;border-collapse:collapse;font-size:var(--text-xs)">' +
      '<thead><tr style="color:var(--c-text-dim);text-align:left">' +
      '<th style="padding:2px 6px">Strategie</th><th>Stufen</th><th>Evidenz</th><th>OOS</th><th>Netto</th><th>Status</th></tr></thead><tbody>';
    for (var i = 0; i < cands.length; i++) {
      var c = cands[i];
      var nm = candName(c.strategy_id);
      var reasons = c.reasons || [];
      var status;
      if (c.fillable) {
        status = '<span style="color:#3fb950">✓ füllbar</span>';
      } else {
        var chips = [];
        for (var x = 0; x < reasons.length; x++) {
          chips.push('<span title="' + escHtml(reasons[x]) + '" style="display:inline-block;font-size:10px;padding:0 5px;border-radius:3px;background:rgba(139,148,158,0.12);color:#8b949e;border:1px solid rgba(139,148,158,0.3);margin-right:3px">⚙ ' + escHtml(_radarReasonShort(reasons[x])) + '</span>');
        }
        status = chips.join('');
      }
      var evCell;
      if (c.ci95 != null) {
        evCell = (c.eur_per_trade != null ? Number(c.eur_per_trade).toFixed(2) : '—') +
          ' ±' + Number(c.ci95).toFixed(2) + ' €/T · (n=' + (c.ci_n != null ? c.ci_n : '—') + ')';
      } else {
        evCell = 'n=' + (c.ci_n != null ? c.ci_n : 0) + ' · KI n/a';
      }
      var oosCell = (c.pf != null)
        ? Number(c.pf).toFixed(2) + ' (' + (c.oos_trades != null ? c.oos_trades : 0) + ')'
        : '—';
      h += '<tr style="border-top:1px solid var(--c-border)">';
      h += '<td style="padding:3px 6px"><b>#' + escHtml(c.strategy_id) + '</b>' + (nm ? ' <span style="color:var(--c-text-dim)">' + escHtml(nm) + '</span>' : '') + '</td>';
      h += '<td style="white-space:nowrap">' + _radarStageCell(c, r.wave) + '</td>';
      h += '<td style="white-space:nowrap">' + evCell + '</td>';
      h += '<td>' + oosCell + '</td>';
      h += '<td class="' + pnlClass(c.net_class || 0) + '">' + fmtPnl(c.net_class || 0) + ' €</td>';
      h += '<td style="white-space:nowrap">' + status +
        '<div style="font-size:10px;color:var(--c-text-dim)">' + escHtml(c.lacks || '') + '</div></td></tr>';
    }
    h += '</tbody></table>';
  }
  var slots = d.slots || [];
  var rows = [];
  for (var j = 0; j < slots.length; j++) {
    var s = slots[j];
    var st = s.stats || {};
    if (st.pnl_7d == null && st.pnl_30d == null) continue;
    rows.push('<span style="margin-right:12px"><b>' + escHtml(s.slot_id) + '</b> 7d <span class="' + pnlClass(st.pnl_7d || 0) + '">' + fmtPnl(st.pnl_7d || 0) + ' €</span> · 30d <span class="' + pnlClass(st.pnl_30d || 0) + '">' + fmtPnl(st.pnl_30d || 0) + ' €</span></span>');
  }
  if (rows.length) {
    h += '<div style="font-size:10px;color:var(--c-text-dim);margin-top:8px">Slot-Performance (geschlossene Trades): ' + rows.join('') + '</div>';
  }
  h += '<details style="margin-top:8px"><summary style="cursor:pointer;font-size:var(--text-xs);color:#7ab4ff">Wie führt der Bot aus?</summary>' +
    '<ul style="font-size:var(--text-xs);color:var(--c-text-dim);margin:6px 0 0 16px;padding:0">' +
    '<li>Alle Slots scannen jeden Zyklus; ausgeführt wird nach <b>Signal-Score</b> (Baum-Konfidenz), höchster zuerst.</li>' +
    '<li>Gate-Kette je Signal: Familie-Dedup → Slot-Heat → Global-Heat → Richtung → Währungs-Buckets → Margin → min_score. Wer zuerst durchkommt, bekommt den freien Platz (FCFS).</li>' +
    '<li><b>No-Deferred:</b> jedes Signal wird genau 1× verarbeitet — kein Nachholen; die nächste Bar ist die nächste Chance.</li>' +
    '<li><b>Rotation:</b> Tür tauscht nur bei Schwäche (Bust/Zombie/Parität); Kandidat braucht ≥3 saubere Challenge-Trades netto&gt;0 (14-Tage-Frist) + fail-closed Precheck; max. 1 Fill je Bot/7 Tage.</li>' +
    '<li><b>Entfernen nur als Defekt-Nachweis</b> (Bust/Zombie/Unterperformance, n≥10) — kein PnL-Ranking (Rang-Persistenz ≈ 0).</li>' +
    '</ul></details>';
  box.innerHTML = h;
  box.style.display = '';
}

function _radarReasonShort(x) {
  var m = { 'pair_disjoint': 'Paar-Konflikt', 'cluster_cap': 'Cluster-Cap', 'deferred:no_pairs': 'ohne Tree/Pairs', 'pair_cap_tf': 'XAU/XAG-Bucket belegt', 'pair_cap': 'Paar-Cap' };
  var s = String(x);
  for (var k in m) { if (s.indexOf(k) === 0) return m[k]; }
  if (s.indexOf('deferred') === 0) return 'ohne Tree/Pairs';  // v2: generisch
  return s.split(':')[0];
}

function _renderSlotsInner(d, sp) {
  var slots = d.slots || [];
  var spById = {};
  if (sp && sp.strategies) {
    for (var i = 0; i < sp.strategies.length; i++) spById[sp.strategies[i].id] = sp.strategies[i];
  }
  // Fallback-Namen aus Trades (falls shadow_portfolio.json nicht erreichbar)
  var nameById = {};
  var trs = (d.last_trades || d.trade_history || d.trades || []);
  for (var i2 = 0; i2 < trs.length; i2++) {
    var t = trs[i2];
    if (t && t.strategy_id != null && t.strategy && !nameById[t.strategy_id]) {
      nameById[t.strategy_id] = t.strategy;
    }
  }
  function sidLabel(sid) {
    if (sid == null || sid === '') return '—';
    var m = spById[sid] || spById[String(sid)];
    if (m && m.name) return '#' + sid + ' · ' + _spShortName(m.name);
    var nm = nameById[sid] || nameById[String(sid)];
    return '#' + sid + (nm ? ' · ' + nm : '');
  }
  function chipsAndMeta(sid, slot) {
    var m = spById[sid] || spById[String(sid)] || {};
    var assets = (m.assets && m.assets.length) ? m.assets : ((slot && slot.assets) || []);
    var chips = '';
    for (var a = 0; a < assets.length; a++) {
      chips += '<span style="display:inline-block;font-size:10px;padding:1px 6px;border-radius:3px;background:var(--c-surface-2);border:1px solid var(--c-border);margin:0 4px 4px 0">' + escHtml(assets[a]) + '</span>';
    }
    var bits = [];
    if (m.timeframe) bits.push(String(m.timeframe).toUpperCase());
    if (m.tier) bits.push('Tier ' + escHtml(m.tier));
    if (slot && slot.risk_pct != null) bits.push('Budget ' + slot.risk_pct + ' %');
    return '<div style="margin:4px 0">' + chips + (bits.length ? '<span style="font-size:10px;color:var(--c-text-dim)">' + bits.join(' · ') + '</span>' : '') + '</div>';
  }
  function descBlock(sid, compact) {
    var m = spById[sid] || spById[String(sid)];
    var dd = (m && m.desc) || {};
    var h = '';
    if (dd.tag) h += '<div style="display:inline-block;font-size:10px;font-weight:700;background:rgba(120,180,255,0.12);color:#7ab4ff;border:1px solid rgba(120,180,255,0.25);border-radius:3px;padding:1px 6px;margin-bottom:4px">' + escHtml(dd.tag) + '</div>';
    if (dd.was) {
      var wasTxt = String(dd.was);
      if (compact && wasTxt.length > 180) wasTxt = wasTxt.slice(0, 180) + '…';
      h += '<div style="font-size:var(--text-xs);color:var(--c-text-2);margin-bottom:4px">' + escHtml(wasTxt) + '</div>';
    }
    if (dd.gut && !compact) h += '<div style="font-size:var(--text-xs);color:#10b981"><b>Stärken:</b> ' + escHtml(dd.gut) + '</div>';
    if (dd.nicht && !compact) h += '<div style="font-size:var(--text-xs);color:#f59e0b"><b>Schwächen:</b> ' + escHtml(dd.nicht) + '</div>';
    if (dd.ausmacht && !compact) h += '<div style="font-size:var(--text-xs);color:var(--c-text-2)"><b>Profil:</b> ' + escHtml(dd.ausmacht) + '</div>';
    if (dd.ergaenzt && !compact) h += '<div style="font-size:var(--text-xs);color:var(--c-text-2)"><b>Portfolio:</b> ' + escHtml(dd.ergaenzt) + '</div>';
    return h;
  }
  function statsRows(st) {
    st = st || {};
    var h = '';
    h += '<div style="display:flex;justify-content:space-between;font-size:var(--text-xs);margin-bottom:4px"><span>Trades</span><b>' + (st.trades || 0) + '</b></div>';
    h += '<div style="display:flex;justify-content:space-between;font-size:var(--text-xs);margin-bottom:4px"><span>Win-Rate</span><b>' + (st.closed ? (st.win_rate || 0) + '%' : '—') + '</b></div>';
    h += '<div style="display:flex;justify-content:space-between;font-size:var(--text-xs)"><span>Netto</span><b class="' + pnlClass(st.net_eur || 0) + '">' + fmtPnl(st.net_eur || 0) + ' €</b></div>';
    return h;
  }
  function oosLine(sid) {
    var m = spById[sid] || spById[String(sid)];
    if (!m) return '';
    var bits = [];
    if (m.oos_pf != null) bits.push('PF ' + Number(m.oos_pf).toFixed(2));
    if (m.oos_pnl != null) bits.push((m.oos_pnl >= 0 ? '+' : '') + Math.round(m.oos_pnl) + ' €');
    if (!bits.length) return '';
    return '<div style="font-size:10px;color:var(--c-text-dim);margin-top:4px">OOS-Referenz (Lab-WFO): ' + bits.join(' · ') + '</div>';
  }

  var sub = el(C.prefix + '-slots-sub');
  var nRot = 0;
  var nFilled = 0;
  var nPlanned = 0;
  for (var j = 0; j < slots.length; j++) {
    if (slots[j].kind === 'rotation') nRot++;
    if (slots[j].kind === 'planned') nPlanned++;
    if (slots[j].strategy_id != null || slots[j].holder != null) nFilled++;
  }

  // Unified-Modell (Umbau 11.10.): Einzel-Bot (1 Slot, keine Türen/Reserve)
  // = „Strategie"; Multibot = „Strategien & Slots". Kein „Multibot"-Wording mehr.
  var _isSingle = (slots.length === 1 && !nRot && !nPlanned);
  var _ttl = el(C.prefix + '-slots-title');
  if (_ttl) _ttl.textContent = _isSingle ? '🧩 Strategie' : '🧩 Strategien & Slots';

  if (sub) {
    if (_isSingle) {
      var _s0 = slots[0];
      sub.textContent = 'Strategie ' + sidLabel(_s0.strategy_id) +
        (_s0.since ? ' · seit ' + fmtTime(_s0.since) : '');
    } else {
      var _tgt = (typeof d.slots_target === 'number') ? d.slots_target : null;
      var _total = _tgt ? Math.max(_tgt, slots.length) : null;
      sub.textContent = (_total ? nFilled + '/' + _total + ' Strategien belegt (max. ' + _total + ' vorgesehen)'
                                : nFilled + '/' + slots.length + ' Strategien belegt') +
        (nRot ? ' · ' + nRot + ' Rotationsslot' + (nRot === 1 ? '' : 's') : '') +
        (nPlanned ? ' · ' + nPlanned + (nPlanned === 1 ? ' Platz' : ' Plätze') + ' vorbereitet (scharf erst nach Kandidat-Verdikt)' : '') +
        (nRot ? ' · Rotation nur bei Schwäche (Bust/Zombie/Parität)' : '');
    }
  }

  // Scharfstellen-/Automatik-Status (20.10.2026, User): EINE klare Zeile über
  // den Kacheln. „🔒 bereit für Scharfstellen“ = Live-Slot/Fill wartet auf
  // Michaels OK; sonst Automatik-Zustände (Fill läuft / Challenge läuft / ok).
  function _slotsStatusStrip(sl) {
    var liveWait = [], fillReady = [], chRun = [];
    for (var i0 = 0; i0 < sl.length; i0++) {
      var s0 = sl[i0];
      if (!s0 || s0.kind === 'planned') continue;
      var ch0 = s0.challenge;
      if (s0.stage === 'live' && s0.armed === false) { liveWait.push(s0.slot_id); continue; }
      if (ch0 && ch0.candidate != null) {
        if (ch0.ready) {
          if (s0.stage === 'live') liveWait.push(s0.slot_id + ' (#' + ch0.candidate + ')');
          else fillReady.push(s0.slot_id + ' (#' + ch0.candidate + ')');
        } else {
          chRun.push('#' + ch0.candidate + ' Tag ' + (ch0.day || 1) + '/' + (ch0.days_total || 14));
        }
      }
    }
    var lvl, txt;
    if (liveWait.length) {
      lvl = 'action';
      txt = '🔒 bereit für Scharfstellen: ' + liveWait.join(', ') + ' — wartet auf dein OK';
    } else if (fillReady.length) {
      lvl = 'info';
      txt = '⚡ bereit — Fill beim nächsten Engine-Lauf möglich: ' + fillReady.join(', ');
    } else if (chRun.length) {
      lvl = 'info';
      txt = '⏳ Automatik läuft — Challenge ' + chRun.join(' · ');
    } else {
      lvl = 'ok';
      txt = '✅ Keine Aktion nötig — alles läuft automatisch';
    }
    var col = lvl === 'action' ? '#d29922' : (lvl === 'info' ? '#3b82f6' : '#3fb950');
    var bg = lvl === 'action' ? 'rgba(210,153,34,0.12)' : (lvl === 'info' ? 'rgba(59,130,246,0.10)' : 'rgba(63,185,80,0.10)');
    return '<div id="' + C.prefix + '-slots-status" style="grid-column:1/-1;font-size:var(--text-xs);color:' + col + ';background:' + bg + ';border:1px solid ' + col + '55;border-radius:var(--r-md);padding:6px 10px">' + escHtml(txt) + '</div>';
  }

  var html = _slotsStatusStrip(slots);
  // Stufen-Modell (13.10.2026): 🔴 LIVE (echtes Geld; nur wenn armed) /
  // 🟡 DEMO / 🔵 SHADOW (angezeigt, handelt nur im Shadow) / GEPLANT.
  var _hasLive = false, _hasDemo = false;
  for (var j0 = 0; j0 < slots.length; j0++) {
    if (slots[j0].stage === 'live') _hasLive = true;
    else if (slots[j0].stage === 'demo') _hasDemo = true;
  }
  function stageBadge(s) {
    if (s.stage === 'live') return '<span class="bot-badge bot-badge-live">🔴 LIVE' + (s.armed === false ? ' · OK nötig' : '') + '</span>';
    if (s.stage === 'demo') return '<span class="bot-badge" style="background:rgba(210,153,34,0.14);color:#d29922;border:1px solid rgba(210,153,34,0.4)">🟡 DEMO</span>';
    if (s.stage === 'shadow') return '<span class="bot-badge" style="background:rgba(59,130,246,0.12);color:#3b82f6;border:1px solid rgba(59,130,246,0.35)">🔵 SHADOW</span>';
    return '';
  }
  for (var k = 0; k < slots.length; k++) {
    var s = slots[k];
    var isRot = s.kind === 'rotation';
    var isPlanned = s.kind === 'planned';
    var kindBadge = isRot
      ? '<span class="bot-badge bot-badge-warn">ROTATION</span>'
      : isPlanned
        ? '<span class="bot-badge" style="background:var(--c-surface-2);color:var(--c-text-dim);border:1px solid var(--c-border)">GEPLANT</span>'
        : '<span class="bot-badge bot-badge-buy">STRATEGIE</span>';
    html += '<div class="bot-card" style="padding:var(--s-3);border:1px ' + (isPlanned ? 'dashed' : 'solid') + ' var(--c-border)' + (isPlanned ? ';opacity:0.85' : '') + '">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;gap:var(--s-2);margin-bottom:var(--s-2)">';
    html += '<b style="font-size:var(--text-md)">' + escHtml(s.slot_id) + '</b><span>' + kindBadge + stageBadge(s) + '</span></div>';
    // Konto-Zeile nur wenn der Bot mindestens einen Live-Slot hat und die Kachel
    // eine Strategie zeigt (Split-Bots: bot5/bot7). Reine Demo-Bots: kein Rauschen.
    if (_hasLive && s.kind === 'strategy' && s.account_id != null) {
      var _accTxt = 'Konto ' + s.account_id +
        (s.stage === 'live' ? (s.armed === false ? ' · 🔒 bereit für Scharfstellen — dein OK' : ' · LIVE-Host') :
         s.stage === 'demo' ? ' · Demo' : '');
      html += '<div style="font-size:10px;color:var(--c-text-dim);margin:-2px 0 4px">' + escHtml(_accTxt) + '</div>';
    }

    if (isPlanned) {
      html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim)">' +
        escHtml(s.note || 'Reserve-Platz — wird scharf gestellt, sobald ein Kandidat überzeugt.') + '</div>';
    } else if (!isRot) {
      var m0 = spById[s.strategy_id] || spById[String(s.strategy_id)];
      var nm0 = (m0 && m0.name) ? _spShortName(m0.name) : (nameById[s.strategy_id] || nameById[String(s.strategy_id)] || '');
      html += '<div style="font-size:var(--text-sm);margin-bottom:4px"><b>#' + escHtml(s.strategy_id) + '</b> ' +
        (nm0 ? '<span title="' + escHtml((m0 && m0.name) || nm0) + '">' + escHtml(nm0) + '</span>' : '') + '</div>';
      html += descBlock(s.strategy_id, false);
      html += chipsAndMeta(s.strategy_id, s);
      if (s.tech && s.tech.summary) html += '<div style="font-size:10px;color:var(--c-text-dim);margin:2px 0 4px">⚙️ ' + escHtml(s.tech.summary) + '</div>';
      html += statsRows(s.stats);
      html += oosLine(s.strategy_id);
      if (s.challenge && s.challenge.candidate != null) {
        var ce = s.challenge;
        var ceInfo = ' · Trades ' + (ce.trades || 0) + '/3';
        if (ce.ready) ceInfo += ' · ✅ ready';
        else if (ce.need_trades) ceInfo += ' · noch ' + ce.need_trades;
        else ceInfo += ' · wartet auf +Fenster';
        html += '<div style="font-size:10px;color:#d29922;margin-top:4px">🔄 Engine-Challenge #' + escHtml(ce.candidate) + ceInfo + (ce.days_left != null ? ' · Frist ' + ce.days_left + ' T' : '') + '</div>';
      }
    } else {
      var ch = s.challenge;
      if (s.holder != null) {
        html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim);margin-bottom:4px">Bestückt: ' + escHtml(sidLabel(s.holder)) + '</div>';
        html += descBlock(s.holder, true);
        html += statsRows(s.stats);
        html += oosLine(s.holder);
      } else if (ch && ch.candidate != null) {
        var cand = ch.candidate;
        var cm = spById[cand] || spById[String(cand)];
        html += '<div style="font-size:var(--text-xs);margin-bottom:4px">🔄 Challenge <b>#' + escHtml(cand) + '</b> · Tag ' + (ch.day || 1) + '/' + (ch.days_total || 14) + '</div>';
        if (cm && cm.name) html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim);margin-bottom:4px">' + escHtml(_spShortName(cm.name)) + '</div>';
        html += descBlock(cand, true);
        var pct = Math.max(2, Math.min(100, Math.round(((ch.day || 1) / (ch.days_total || 14)) * 100)));
        html += '<div style="height:6px;border-radius:3px;background:var(--c-border);overflow:hidden;margin:4px 0 6px"><div style="height:100%;width:' + pct + '%;background:#3b82f6"></div></div>';
        html += '<div style="display:flex;justify-content:space-between;font-size:var(--text-xs)"><span>Trades ' + (ch.trades || 0) + '/3</span><b class="' + pnlClass(ch.net_eur || 0) + '">' + fmtPnl(ch.net_eur || 0) + ' €</b></div>';
        if (ch.ready) html += '<div style="font-size:10px;color:#3fb950;margin-top:2px">✅ Readiness erreicht — Engine-Fill beim nächsten Lauf möglich</div>';
        else if ((ch.trades || 0) >= 3 && !ch.net_positive) html += '<div style="font-size:10px;color:#d29922;margin-top:2px">wartet auf positives Fenster</div>';
        else html += '<div style="font-size:10px;color:var(--c-text-dim);margin-top:2px">noch ' + (ch.need_trades != null ? ch.need_trades : Math.max(0, 3 - (ch.trades || 0))) + ' saubere Trades bis Readiness' + (ch.days_left != null ? ' · Frist in ' + ch.days_left + ' T' : '') + '</div>';
        html += oosLine(cand);
      } else {
        html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim)">frei — wartet auf Challenge</div>';
      }
    }
    if (s.since) html += '<div style="font-size:10px;color:var(--c-text-dim);margin-top:6px">seit ' + fmtTime(s.since) + '</div>';
    html += '</div>';
  }
  var grid = el(C.prefix + '-slots-grid');
  if (grid) grid.innerHTML = html;

  // Slot-Historie-Tabelle
  var hb = el(C.prefix + '-slot-history-body');
  var hist = d.slot_history || [];
  if (hb) {
    if (!hist.length) {
      hb.innerHTML = '<tr><td colspan="5" class="bot-no-data">—</td></tr>';
    } else {
      var reasonMap = { deploy: 'Deploy', rotation: 'Rotation', backfill: 'Backfill', legacy: 'Altbestand' };
      var hh = '';
      for (var m = 0; m < hist.length; m++) {
        var e = hist[m];
        var sidTxt = e.strategy_id != null ? sidLabel(e.strategy_id) : '—';
        hh += '<tr>';
        hh += '<td><b>' + escHtml(e.slot_id || '—') + '</b></td>';
        hh += '<td>' + escHtml(sidTxt) + '</td>';
        hh += '<td>' + fmtTime(e.from) + '</td>';
        hh += '<td>' + (e.to ? fmtTime(e.to) : '<span style="color:#22c55e">läuft</span>') + '</td>';
        hh += '<td>' + escHtml(reasonMap[e.reason] || e.reason || '—') + '</td>';
        hh += '</tr>';
      }
      hb.innerHTML = hh;
    }
  }

  // 🎯 Rotations-Radar (09.10.2026): Kandidaten + Fit + Slot-Performance + Explainer
  _renderRotationRadar(d, spById, nameById);
}

/** Signal overview grid */
function renderSignals(d) {
  var grid = el(C.prefix + '-signal-grid');
  if (!grid) return;
  var pairs = d.pairs || [];
  var indicators = d.indicators || {};
  var signals = d.signals || d.active_signals || [];
  _allPairs = pairs.map(function(p) { return p.symbol || p; });

  // If no pairs but we have assets+indicators, build pairs from them
  if (pairs.length === 0 && d.assets && d.assets.length > 0) {
    pairs = d.assets.map(function(sym) { return { symbol: sym, indicators: indicators[sym] || {} }; });
    _allPairs = d.assets;
  }

  var sigLookup = {};
  for (var s = 0; s < signals.length; s++) sigLookup[signals[s].symbol] = signals[s];

  var html = '';
  for (var i = 0; i < pairs.length; i++) {
    var p = pairs[i];
    var sym = typeof p === "string" ? p : p.symbol;
    var ind = (typeof p === "object" ? p.indicators : null) || indicators[sym] || {};
    var sig = sigLookup[sym];

    var rsi = ind.rsi;
    var status = ind.signal_status || '—';
    var direction = 'neutral';
    if (sig) direction = sig.direction || 'neutral';
    var dirColor = direction === 'long' ? '#22c55e' : (direction === 'short' ? '#ef4444' : 'var(--c-text-dim)');
    var dirLabel = direction === 'long' ? '▲ LONG' : (direction === 'short' ? '▼ SHORT' : '—');

    html += '<div class="bot-signal-card" onclick="BotDash.openChart(\'' + sym + '\')" data-pair="' + sym + '">';
    html += '<div class="bot-signal-pair">' + sym + '</div>';
    html += '<div class="bot-signal-status" style="color:' + dirColor + '">' + dirLabel + '</div>';
    html += '<div style="font-size:var(--text-xs);margin-top:var(--s-1)">';
    html += '<span style="font-weight:600">' + status + '</span>';
    if (rsi != null) html += ' <span style="color:var(--c-text-dim)">RSI ' + Number(rsi).toFixed(0) + '</span>';
    if (ind.bb_squeeze) html += ' <span style="color:#f59e0b">26A1Squeeze</span>';
    html += '</div>';
    var price = p.live_price;
    if (price) html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim)">@ ' + price + '</div>';
    html += '<div style="font-size:10px;color:var(--c-text-dim);margin-top:4px;opacity:0.6">📊 Chart</div>';
    html += '</div>';
  }
  grid.innerHTML = html || '<div class="bot-no-data">No signals</div>';
}

/** Kontoverlauf (Chart.js) — reiner Kontoverlauf; optional + Kontokurven (blau) */
/* Legacy-Renderer (bis 22.10.2026). Wird nicht mehr aufgerufen — der Cockpit-
 * Renderer weiter unten (renderEquity) übernimmt. Bleibt für Vergleichszwecke
 * im File, bis die Candlestick-Helfer separat aufgeräumt werden. */
function renderEquityLegacy(d) {
  var canvas = el(C.prefix + '-equity-chart');
  if (!canvas) return;
  var data = d.equity_history || d.balance_history || {};
  var snapshots = data.snapshots || data;
  if (!Array.isArray(snapshots) || snapshots.length === 0) return;

  // Kontokurven (LIVE/DEMO-Split; User-Vereinfachung 14.10.2026: reiner
  // Kontoverlauf als EINE blaue Linie — keine Farbcodierung, keine Legende).
  var curves = d.curves || [];

  var baseLabels = [], values = [];
  for (var i = 0; i < snapshots.length; i++) {
    var s = snapshots[i];
    var val = s.equity || s.balance || s.value || 0;
    baseLabels.push(s.timestamp || s.date || '');
    values.push(val);
  }

  // Label-Union chronologisch (String-Sort reicht fuer ISO-Timestamps) +
  // Index-Maps: Basis- und Kontowerte werden auf die Union-Labels gelegt,
  // fehlende Stellen bleiben null — UND mit spanGaps:true durchgezogen
  // verbunden (Fix 16.10.2026: Fremd-Timestamps der Union zerschnitten die
  // Linien sonst in Einzelpunkte — bot5/bot7 'gepunktet'/unlesbar, bot7 nur
  // 15 von 559 Nachbar-Paaren).
  var labels, eqData, extraDatasets = [];
  // Union nur noetig, wenn Kontokurven vorhanden sind. Sonst Fast-Path
  // (labels = baseLabels).
  if (curves.length === 0) {
    labels = baseLabels; eqData = values;
  } else {
    var labelSet = {};
    for (var bi = 0; bi < baseLabels.length; bi++) labelSet[baseLabels[bi]] = true;
    for (var ci = 0; ci < curves.length; ci++) {
      var pts = (curves[ci] && curves[ci].points) || [];
      for (var pi = 0; pi < pts.length; pi++) {
        var lt = (pts[pi] && (pts[pi].timestamp || pts[pi].date)) || '';
        labelSet[lt] = true;
      }
    }
    labels = Object.keys(labelSet).sort();
    var indexOf = {};
    for (var li = 0; li < labels.length; li++) indexOf[labels[li]] = li;

    // Punkt-Wert (equity > balance > value) auf die Union-Labels legen.
    var _mapPts = function (arr) {
      var out = labels.map(function () { return null; });
      for (var j = 0; j < (arr || []).length; j++) {
        var p = arr[j] || {};
        var key = p.timestamp || p.date || '';
        var idx = indexOf[key];
        var v = p.equity != null ? p.equity
              : (p.balance != null ? p.balance
              : (p.value != null ? p.value : null));
        if (idx !== undefined && v != null) out[idx] = v;
      }
      return out;
    };

    eqData = labels.map(function () { return null; });
    for (var bj = 0; bj < baseLabels.length; bj++) {
      var bIdx = indexOf[baseLabels[bj]];
      if (bIdx !== undefined) eqData[bIdx] = values[bj];
    }
    for (var k = 0; k < curves.length; k++) {
      var cur = curves[k] || {};
      // 18.10.2026: Demo-Kurven (bot9-Demo-Seite) 🧪/silber, Echtgeld 💰/gold.
      var _curLive = cur.is_live !== false;
      extraDatasets.push({
        label: (_curLive ? '💰 ' : '🧪 ') +
          (cur.label || (cur.ctid != null
            ? (_curLive ? 'Echtgeld-Konto ' : 'Demo-Konto ') + cur.ctid
            : (_curLive ? 'Echtgeld' : 'Demo'))),
        data: _mapPts(cur.points),
        borderColor: _curLive ? '#f0b940' : '#9aa4b2',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
        spanGaps: true,
        yAxisID: 'y',
        _ctid: cur.ctid != null ? String(cur.ctid) : '',
      });
    }
  }

  // Y-Achsen-Spanne ueber Basis + Kontokurven.
  var minVal = Infinity, maxVal = -Infinity;
  function _scan(arr) {
    for (var z = 0; z < arr.length; z++) {
      var v = arr[z];
      if (v != null) { if (v < minVal) minVal = v; if (v > maxVal) maxVal = v; }
    }
  }
  _scan(eqData);
  for (var es = 0; es < extraDatasets.length; es++) _scan(extraDatasets[es].data);

  // Y-Axis padding: ensure at least ±1.5% (or ±15 EUR) span around balance so micro-cent fluctuations don't look like crashes
  var yMin = undefined, yMax = undefined;
  if (minVal !== Infinity && maxVal !== -Infinity) {
    var mid = (minVal + maxVal) / 2;
    var range = maxVal - minVal;
    var minSpan = Math.max(15, mid * 0.03); // at least 15 EUR or 3% total span
    if (range < minSpan) {
      yMin = Math.floor(mid - minSpan / 2);
      yMax = Math.ceil(mid + minSpan / 2);
    }
  }

  var _split = curves.length > 0;   // LIVE/DEMO-Split → 2 Kurven (Demo + Echtgeld)
  // 18.10.2026: Basis-Konto-Typ aus d.demo — Demo-Bots (bot5/7) 🧪,
  // LIVE-Bot mit Demo-Seite (bot9) 💰; ohne Split weiterhin "Kontoverlauf".
  var _baseLabel = _split
    ? ((d.demo === false ? '💰 Echtgeld-Konto' : '🧪 Demo-Konto')
       + (d.account_id ? ' ' + d.account_id : ''))
    : 'Kontoverlauf';
  var datasets = [
    {
      label: _baseLabel,
      data: eqData,
      borderColor: '#5b8def',
      backgroundColor: 'rgba(91,141,239,0.08)',
      fill: true,
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true,   // Union-Labels: Null-Luecken durchgezogen (Fix 16.10.)
      yAxisID: 'y',
    }
  ];
  for (var ds = 0; ds < extraDatasets.length; ds++) datasets.push(extraDatasets[ds]);

  // ── Arming-/Era-Marker (Equity P1, 14.10.2026) ──
  // chart.$markers = [{idx,label}]; idx = erster Label-Index >= ts (ISO-Vergleich).
  // Quelle: Basis-d.markers (falls vorhanden) + je Kurve c.markers.
  var markers = [];
  var _addMarkers = function (list) {
    if (!Array.isArray(list)) return;
    for (var mi = 0; mi < list.length; mi++) {
      var m = list[mi] || {};
      var mts = m.ts || m.timestamp || '';
      if (!mts) continue;
      var idx = -1;
      for (var lj = 0; lj < labels.length; lj++) {
        if (String(labels[lj]) >= String(mts)) { idx = lj; break; }
      }
      if (idx >= 0) markers.push({ idx: idx, label: m.label || '' });
    }
  };
  if (Array.isArray(d.markers)) _addMarkers(d.markers);
  for (var mki = 0; mki < curves.length; mki++) {
    _addMarkers(curves[mki] && curves[mki].markers);
  }
  var markerPlugin = {
    id: 'equityMarkers',
    markers: markers,
    afterDatasetsDraw: function (chart) {
      var mk = (chart && chart.$markers) || this.markers || [];
      if (!mk.length) return;
      var ctx = chart.ctx;
      var xa = chart.scales && chart.scales.x;
      var ya = chart.scales && chart.scales.y;
      if (!ctx || !xa || !ya) return;
      ctx.save();
      for (var mj = 0; mj < mk.length; mj++) {
        var x = xa.getPixelForValue(mk[mj].idx);
        if (x == null || isNaN(x)) continue;
        ctx.beginPath();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = 'rgba(156,163,175,0.85)';
        ctx.lineWidth = 1;
        ctx.moveTo(x, ya.top);
        ctx.lineTo(x, ya.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        if (mk[mj].label) {
          ctx.fillStyle = '#9ca3af';
          ctx.font = '10px sans-serif';
          ctx.textAlign = 'left';
          ctx.fillText(mk[mj].label, x + 3, ya.top + 10);
        }
      }
      ctx.restore();
    }
  };

  if (_chartInstances.equity) _chartInstances.equity.destroy();
  _chartInstances.equity = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets
    },
    plugins: [markerPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        // Legende nur im LIVE/DEMO-Split (2 Serien) — eindeutige Beschriftung
        // Demo/Echtgeld (User 16.10.2026); Fast-Path (1 Linie) bleibt ohne Legende.
        legend: {
          display: _split,
          position: 'top',
          labels: { boxWidth: 10, boxHeight: 10, color: '#9ca3af', font: { size: 10 } },
        },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              var _ds = ctx.dataset || (ctx.chart && ctx.chart.data
                && ctx.chart.data.datasets[ctx.datasetIndex]) || {};
              var _name = _ds.label || (ctx.datasetIndex === 0 ? 'Kontoverlauf' : 'Echtgeld');
              return _name + ': €' + ctx.parsed.y.toFixed(2);
            }
          }
        }
      },
      scales: {
        x: { display: true, ticks: {
          color: '#9ca3af', maxTicksLimit: 10, maxRotation: 0, font: { size: 10 },
          // Horizontaler Maßstab (16.10.2026): deutsches Kurz-Datum „TT.MM."
          // (Jahr nur bei Jahreswechsel) statt langem ISO — lesbar auf dunklem Grund.
          callback: function(value) {
            var _lbl = String(this.getLabelForValue ? this.getLabelForValue(value) : '');
            var _m = _lbl.match(/^(\d{4})-(\d{2})-(\d{2})/);
            if (!_m) return _lbl;
            var _lastYear = String((labels && labels.length ? labels[labels.length - 1] : '')).slice(0, 4);
            return _m[3] + '.' + _m[2] + '.' + (_m[1] === _lastYear ? '' : _m[1].slice(2));
          }
        },
        // Ticks gleichmäßig in der ZEIT (~alle 4 Tage) statt nach Label-Index —
        // die Union-Labels sind zeitlich ungleich verteilt (Downsampling + Kontokurven).
        afterBuildTicks: function(axis) {
          var n = (labels && labels.length) || 0;
          if (n < 3) return;
          var _ts = function(l) { return Date.parse(String(l).slice(0, 19) + 'Z'); };
          var t0 = _ts(labels[0]), t1 = _ts(labels[n - 1]);
          if (!isFinite(t0) || !isFinite(t1) || t1 <= t0) return;
          var want = 8, out = [];
          for (var i = 0; i <= want; i++) {
            var target = t0 + (t1 - t0) * i / want;
            var lo = 0, hi = n - 1;
            while (lo < hi) { var mid = (lo + hi) >> 1; if (_ts(labels[mid]) < target) lo = mid + 1; else hi = mid; }
            if (!out.length || out[out.length - 1].value !== lo) out.push({ value: lo });
          }
          axis.ticks = out;
        },
        grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { position: 'left', min: yMin, max: yMax, ticks: { color: '#5b8def', callback: function(v) { return '€' + v.toFixed(0); } }, grid: { color: 'rgba(255,255,255,0.04)' } }
      }
    }
  });
  if (_chartInstances.equity) _chartInstances.equity.$markers = markers;

  // Summary — Basis-Serie (Default-Konto) + optionale Era-/Kapital-Chips.
  var summary = el(C.prefix + '-equity-summary');
  if (summary) {
    var first = values[0] || 0;
    var last = values[values.length - 1] || 0;
    var tradeCount = (d.last_trades && d.last_trades.length) || 0;
    var note = tradeCount === 0 ? '<span style="color:var(--c-text-dim);margin-left:auto;font-style:italic">ℹ️ Startwert nach Deploy (noch keine Trades der aktuellen Strategie)</span>' : '';

    var _fmtEur = function (n) {
      n = Number(n) || 0;
      try {
        return n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      } catch (e) { return n.toFixed(2); }
    };
    var chips = '';
    for (var ek = 0; ek < curves.length; ek++) {
      var eras = curves[ek] && curves[ek].eras;
      if (!Array.isArray(eras)) continue;
      for (var ei = 0; ei < eras.length; ei++) {
        var e = eras[ei] || {};
        var pv = Number(e.pnl_eur) || 0;
        chips += '<span class="bot-era-chip" style="margin-left:var(--s-2)">📜 '
          + (e.label || '') + ': ' + (pv >= 0 ? '+' : '−')
          + _fmtEur(Math.abs(pv)) + ' €</span>';
      }
    }
    var flows = d.account_flows || [];
    if (Array.isArray(flows)) {
      for (var fi = 0; fi < flows.length; fi++) {
        var f = flows[fi] || {};
        chips += '<span class="bot-cap-chip" style="margin-left:var(--s-2)">💶 '
          + (f.ctid || '') + ' Kapital: Einz. +' + _fmtEur(f.einzahlungen_eur)
          + ' · Ausz. −' + _fmtEur(Math.abs(Number(f.auszahlungen_eur) || 0))
          + ' · Transfers ' + _fmtEur(f.transfers_eur)
          + ' · Netto ' + _fmtEur(f.netto_eur) + ' €</span>';
      }
    }

    summary.innerHTML =
      '<span>Start: <b>€' + first.toFixed(2) + '</b></span>' +
      '<span>Current: <b>€' + last.toFixed(2) + '</b></span>' +
      '<span>P&L: <b class="' + pnlClass(last - first) + '">' + fmtPnl(last - first) + '</b></span>' +
      note + chips;
  }
}

/* ═══════════════════════════════════════════════════════════
 *  CANDLESTICK CHART (LightweightCharts)
 * ═══════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════
 *  CANDLESTICK CHART — Trade-Fokus (2026-10-28)
 *
 *  Ein Chart für zwei Aufgaben:
 *   1. Übersicht (Pair-Chips): Kerzen + offene Positionen + Trade-Marker
 *   2. Trade-Fokus (Klick auf Position/Historie): genau EIN Trade,
 *      automatisches Zeitfenster + Timeframe, Entry/SL/TP/JETZT/Exit
 *      als beschriftete PreislInien, Risiko-/Chance-Zonen, Kurzprofil.
 * ═══════════════════════════════════════════════════════════ */

var _chartFocus = null;              // aktives Fokus-Objekt
var _chartLiveBar = false;           // letzte Kerze = laufende Teilkerze
var _candleSeries = null;            // aktive Candlestick-Serie (Live-Update)
var _botChartBars = null;            // gerenderte Bars inkl. Live-Teilkerze
var _livePriceLine = null;           // JETZT-Preislinie fuer applyOptions()
var _focusStore = { pos: {}, hist: {} };
var _focusSeq = 0;
var _chartTF = 'base';               // 'base' (Strategie-TF) | 3600 | 14400 | 86400
var _chartTFUsed = 900;
var _baseTFUsed = 0;
var _stratTFUsed = 0;
var _chartRangeTouched = false;
var _showIndicators = true;
var _lastChartData = null;
var _lastChartPair = null;
var _chartRange = 3;                 // Tage in der Übersicht (Default 3T)
var _chartResizeObs = null;

function _epochOf(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return v > 1e12 ? Math.floor(v / 1000) : Math.floor(v);
  var s = String(v);
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
  var t = new Date(s).getTime();
  return isNaN(t) ? null : Math.floor(t / 1000);
}

function _tfSeconds(tf) {
  if (typeof tf === 'number') return tf;
  var s = String(tf || 'M15').trim().toUpperCase();
  // Beide Schreibweisen: Engine/Trees nutzen "4h"/"1h", Dashboard "H1".
  var m = s.match(/^(\d+)\s*([MHD])$/);
  if (m) {
    var n = parseInt(m[1], 10);
    return m[2] === 'M' ? Math.max(60, n * 60) : (m[2] === 'H' ? n * 3600 : n * 86400);
  }
  m = s.match(/^([MHD])(\d+)$/);
  if (m) {
    var k = parseInt(m[2], 10);
    return m[1] === 'M' ? Math.max(60, k * 60) : (m[1] === 'H' ? k * 3600 : k * 86400);
  }
  return 900;
}

function _isLong(side) {
  var s = String(side || '').toLowerCase();
  return !(s === 'sell' || s === 'short');
}

function _parseDuration(s) {
  if (s === null || s === undefined) return 0;
  if (typeof s === 'number') return s * 3600;
  var total = 0, found = false;
  var re = /(\d+(?:[.,]\d+)?)\s*(d|h|m|s)/gi, m;
  while ((m = re.exec(String(s)))) {
    var n = parseFloat(m[1].replace(',', '.'));
    var u = m[2].toLowerCase();
    total += n * (u === 'd' ? 86400 : u === 'h' ? 3600 : u === 'm' ? 60 : 1);
    found = true;
  }
  return found ? total : 0;
}

function _fmtDurSec(sec) {
  if (sec === null || sec === undefined) return '—';
  if (sec < 60) return Math.round(sec) + 's';
  var m = Math.floor(sec / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (d > 0) return d + 'd ' + (h % 24) + 'h';
  if (h > 0) return h + 'h ' + (m % 60) + 'm';
  return m + 'm';
}

function _pipOf(d) {
  return Number((d && d.config && d.config.pip_size) || 0) || 0;
}

function _decimals(pip, price) {
  if (pip > 0) {
    var dec = Math.round(-Math.log(pip) / Math.LN10);
    return Math.max(0, Math.min(6, dec + 1));
  }
  var p = Math.abs(Number(price) || 1);
  if (p < 10) return 5;
  if (p < 1000) return 3;
  return 2;
}

function _fmtP(v, pip) {
  if (v === null || v === undefined || isNaN(Number(v))) return '—';
  return Number(v).toFixed(_decimals(pip, v));
}

function _fmtPips(v) {
  if (v === null || v === undefined || isNaN(Number(v))) return '—';
  var n = Number(v);
  return (n > 0 ? '+' : '') + n.toFixed(1) + ' p';
}

function _fmtEur(v) {
  if (v === null || v === undefined || isNaN(Number(v))) return '—';
  var n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + ' \u20ac';
}

function _fmtR(v) {
  if (v === null || v === undefined || isNaN(Number(v))) return '—';
  var n = Number(v);
  return (n > 0 ? '+' : '') + n.toFixed(2) + 'R';
}

function _putFocus(kind, obj) {
  var store = _focusStore[kind] || (_focusStore[kind] = {});
  var key = (kind === 'pos' ? 'p' : 'h') + (++_focusSeq);
  store[key] = obj;
  return key;
}

function _slotTF(d, key) {
  var fallback = (d && d.timeframe) || 'H1';
  if (!d || !d.slots || key === null || key === undefined || key === '') return fallback;
  var k = String(key);
  for (var i = 0; i < d.slots.length; i++) {
    var s = d.slots[i];
    if (String(s.slot_id) === k || String(s.strategy_id) === k) {
      return s.timeframe || fallback;
    }
  }
  return fallback;
}

/** Bot-TF für die Übersicht: häufigste Slot-TF (nicht der H1-Default). */
function _botTF(d) {
  if (!d || !d.slots || !d.slots.length) return (d && d.timeframe) || 'H1';
  var counts = {}, best = null, bestN = 0;
  for (var i = 0; i < d.slots.length; i++) {
    var tf = d.slots[i].timeframe;
    if (!tf) continue;
    counts[tf] = (counts[tf] || 0) + 1;
    if (counts[tf] > bestN) { bestN = counts[tf]; best = tf; }
  }
  return best || d.timeframe || 'H1';
}

/** Daten-TF aus den Bars (Median-Diff) — das Chart-JSON-Label ist nur Fallback. */
function _inferTF(bars) {
  if (!bars || bars.length < 3) return 900;
  var counts = {}, best = 0, bestTF = 900;
  for (var i = 1; i < Math.min(bars.length, 240); i++) {
    var dt = bars[i].time - bars[i - 1].time;
    if (dt <= 0 || dt > 7 * 86400) continue;
    counts[dt] = (counts[dt] || 0) + 1;
    if (counts[dt] > best) { best = counts[dt]; bestTF = dt; }
  }
  return bestTF;
}

function _strategyBaseTF(d, f) {
  var tf = (f && f.tf) || (f ? _slotTF(d, f.slot_id || f.strategy_id) : _botTF(d));
  return _tfSeconds(tf || (d && d.timeframe) || 'H1');
}

function _tfOptions(base) {
  var opts = [{ v: 'base', l: _tfLabel(base) }];
  if (base < 3600) opts.push({ v: 3600, l: '1H' });
  if (base < 14400) opts.push({ v: 14400, l: '4H' });
  if (base < 86400) opts.push({ v: 86400, l: '1D' });
  return opts;
}

function _defaultRangeDays(base) {
  if (base >= 86400) return 90;
  if (base >= 14400) return 14;
  return 3;
}

function _slotTech(d, slotId) {
  if (!slotId || !d || !d.slots) return '';
  for (var i = 0; i < d.slots.length; i++) {
    if (String(d.slots[i].slot_id) === String(slotId)) {
      return (d.slots[i].tech && d.slots[i].tech.summary) || '';
    }
  }
  return '';
}

/** Fokus-Objekt aus einer offenen Position (dashboard.positions.open[]). */
function _focusFromPosition(d, p) {
  return {
    kind: 'position',
    symbol: p.symbol || p.pair || '',
    entry: Number(p.entry_price || p.entry || p.price) || null,
    sl: Number(p.sl_price || p.sl) || null,
    tp: Number(p.tp_price || p.tp) || null,
    side: p.direction || p.side || 'long',
    entry_ts: _epochOf(p.opened_at || p.entry_time || p.timestamp),
    current: Number(p.live_price) || null,
    pnl: (p.pnl !== null && p.pnl !== undefined) ? Number(p.pnl) : null,
    risk_eur: Number(p.risk_eur) || null,
    reward_eur: Number(p.reward_eur) || null,
    volume: p.volume,
    strategy_id: p.strategy_id || '',
    slot_id: p.slot_id || '',
    account_id: p.account_id || '',
    live: p.live,
    tf: _slotTF(d, p.slot_id || p.strategy_id),
    tech: _slotTech(d, p.slot_id)
  };
}

/** Fokus-Objekt aus einer Historie-Zeile (dashboard.last_trades[]). */
function _focusFromTrade(d, t) {
  return {
    kind: 'trade',
    symbol: t.symbol || t.pair || '',
    entry: Number(t.entry_price || t.entry || t.open_price || t.price) || null,
    sl: Number(t.sl_price || t.sl) || null,
    tp: Number(t.tp_price || t.tp) || null,
    exit_price: Number(t.exit_price || t.close_price || t.current_price) || null,
    side: t.direction || t.side || 'long',
    entry_ts: _epochOf(t.timestamp || t.opened_at || t.entry_time),
    exit_ts: _epochOf(t.closed_at || t.exit_time),
    pnl: (t.pnl !== null && t.pnl !== undefined) ? Number(t.pnl) : null,
    risk_eur: Number(t.risk_eur) || null,
    reward_eur: Number(t.reward_eur) || null,
    duration: t.duration,
    close_reason: t.close_reason || t.status || '',
    strategy_id: t.strategy_id || '',
    slot_id: t.slot_id || '',
    account_id: t.account_id || '',
    live: t.live,
    tf: _slotTF(d, t.slot_id || t.strategy_id),
    tech: _slotTech(d, t.slot_id)
  };
}

function openTradeChart(pair, key) {
  openChart(pair, key);
}

function openChart(pair, focusKey) {
  var panel = el(C.prefix + '-chart-panel');
  if (!panel) return;
  var f = null;
  if (focusKey) f = _focusStore.pos[focusKey] || _focusStore.hist[focusKey] || null;
  if (f) f.symbol = pair;
  _chartFocus = f;
  _chartTF = 'base';
  _baseTFUsed = 0;
  _stratTFUsed = 0;
  _lastChartData = null;
  _lastChartPair = pair;
  _currentPair = pair;
  panel.className = 'bot-chart-panel active' + (f ? ' focus' : '');

  // Signal-Karten markieren
  var cards = document.querySelectorAll('.bot-signal-card');
  for (var i = 0; i < cards.length; i++) {
    if (cards[i].classList) cards[i].classList.toggle('bot-active-card', cards[i].getAttribute('data-pair') === pair);
  }

  _paintChartChrome();
  setTimeout(function () { panel.scrollIntoView({ behavior: 'smooth', block: f ? 'start' : 'nearest' }); }, 100);
  _loadChart(pair);
}

function _loadChart(pair) {
  safeFetch(C.chartsPath + pair + '.json').then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (d) {
    if (_currentPair !== pair) return;
    _lastChartData = d;
    _renderCandlestick(d);
  }).catch(function (e) {
    console.warn('Chart load failed:', e);
  });
}

function _paintChartChrome() {
  var f = _chartFocus;
  var pn = el(C.prefix + '-chart-pair');
  if (pn) pn.textContent = (_currentPair || '—') + (f ? ' · Trade-Fokus' : '');
  var st = el(C.prefix + '-chart-strategy');
  if (st) {
    if (f) {
      var s = f.strategy_id ? '#' + f.strategy_id : '';
      if (f.slot_id) s += (s ? ' · ' : '') + f.slot_id;
      st.textContent = s || 'Trade';
      st.style.display = '';
    } else {
      st.textContent = '';
      st.style.display = 'none';
    }
  }
  _paintRangeNav();
  _paintLegend();
  var tt = el(C.prefix + '-trade-toggle');
  if (tt) tt.style.display = f ? 'none' : '';
  _renderFocusBar(_lastChartData);
}

function _paintRangeNav() {
  var nav = el(C.prefix + '-range-nav');
  if (!nav) return;
  var html = '';
  if (_chartFocus) {
    var _base = _baseTFUsed || _strategyBaseTF(_lastDash || _lastChartData, _chartFocus);
    var opts = _tfOptions(_base);
    for (var i = 0; i < opts.length; i++) {
      html += '<span class="bot-range-chip' + (_chartTF === opts[i].v ? ' bot-range-active' : '') +
        '" onclick="BotDash.setChartTF(\'' + opts[i].v + '\')">' + opts[i].l + '</span>';
    }
    html += '<span class="btf-tf-note">Signal-TF ' + _tfLabel(_stratTFUsed || _base) + ' · Chart ' + _tfLabel(_chartTFUsed || _base) + '</span>';
  } else {
    var r = [{ d: 1, l: '1T' }, { d: 3, l: '3T' }, { d: 7, l: '7T' }, { d: 14, l: '14T' }, { d: 0, l: 'All' }];
    for (var j = 0; j < r.length; j++) {
      html += '<span class="bot-range-chip' + (_chartRange === r[j].d ? ' bot-range-active' : '') +
        '" data-days="' + r[j].d + '" onclick="BotDash.setRange(' + r[j].d + ')">' + r[j].l + '</span>';
    }
    html += '<span class="btf-tf-note">Chart-TF ' + _tfLabel(_baseTFUsed || _strategyBaseTF(_lastDash, null)) + '</span>';
  }
  nav.innerHTML = html;
}

function _tfLabel(tf) {
  if (tf >= 86400) return '1D';
  if (tf >= 14400) return '4H';
  if (tf >= 3600) return '1H';
  return '15m';
}

function _paintLegend() {
  var lg = el(C.prefix + '-chart-legend');
  if (!lg) return;
  var h = '';
  if (_chartFocus) {
    h += '<span><i class="btf-dot" style="background:#38bdf8"></i>Einstieg</span>';
    h += '<span><i class="btf-dot" style="background:#ef4444"></i>SL</span>';
    h += '<span><i class="btf-dot" style="background:#22c55e"></i>TP</span>';
    if (_chartFocus.kind === 'position') h += '<span><i class="btf-dot" style="background:#facc15"></i>Jetzt</span>';
    else h += '<span><i class="btf-dot" style="background:#e2e8f0"></i>Exit</span>';
    h += '<span class="muted">Risiko-/Chance-Zone schattiert</span>';
  } else {
    h += '<span><i class="btf-dot" style="background:#22c55e"></i>▲ Long</span>';
    h += '<span><i class="btf-dot" style="background:#ef4444"></i>▼ Short</span>';
    h += '<span><i class="btf-dot" style="background:#94a3b8"></i>○ Exit</span>';
    h += '<span class="muted">Offene Position = Linien · Klick auf Zeile = Trade-Fokus</span>';
  }
  lg.innerHTML = h;
}

function setChartTF(tf) {
  _chartTF = (tf === 'base' || tf === 3600 || tf === 14400 || tf === 86400) ? tf : 'base';
  _paintRangeNav();
  if (_lastChartData) _renderCandlestick(_lastChartData);
}

function clearFocus() {
  _chartFocus = null;
  _chartTF = 'base';
  _baseTFUsed = 0;
  _stratTFUsed = 0;
  var panel = el(C.prefix + '-chart-panel');
  if (panel) panel.className = 'bot-chart-panel active';
  _paintChartChrome();
  if (_lastChartData) _renderCandlestick(_lastChartData);
}

function toggleIndicators() {
  _showIndicators = !_showIndicators;
  var b = el(C.prefix + '-ind-toggle');
  if (b) {
    b.textContent = _showIndicators ? '📈 Indikatoren: ON' : '📈 Indikatoren: OFF';
    b.style.color = _showIndicators ? '#22c55e' : 'var(--c-text-dim)';
  }
  if (_lastChartData) _renderCandlestick(_lastChartData);
}

/* ── Zeitfenster / Timeframe / Aggregation ─────────────────── */

function _focusExitTs(f) {
  if (!f) return null;
  if (f.kind === 'position') return Math.floor(Date.now() / 1000);
  if (f.exit_ts) return f.exit_ts;
  if (f.duration) {
    var s = _parseDuration(f.duration);
    if (s && f.entry_ts) return f.entry_ts + s;
  }
  return null;
}

function _focusWindow(f, exitTs, tf, raw) {
  var lastBar = raw[raw.length - 1].time;
  var hardEnd = lastBar + (f.kind === 'position' ? 12 : 6) * tf;
  var end = Math.min(exitTs || hardEnd, hardEnd);
  var pre = 40 * tf, post = (f.kind === 'position' ? 12 : 20) * tf;
  var start = (f.entry_ts || end - 40 * tf) - pre;
  var stop = end + post;
  if (stop - start < 45 * tf) {
    var mid = (start + stop) / 2;
    start = mid - 22 * tf;
    stop = mid + 22 * tf;
  }
  return { start: start, end: stop };
}

function _overviewWindow(raw, days) {
  var end = raw[raw.length - 1].time + 900;
  if (!days) return { start: raw[0].time, end: end };
  return { start: Math.max(raw[0].time, end - days * 86400), end: end };
}

function _sliceBars(raw, win, tf) {
  var out = [], i;
  for (i = 0; i < raw.length; i++) {
    if (raw[i].time >= win.start - tf && raw[i].time <= win.end + tf) out.push(raw[i]);
  }
  if (out.length < 8) out = raw.slice(-200);
  return _aggregateBars(out, tf);
}

function _aggregateBars(bars, tf) {
  if (!tf || tf <= 900) return bars.slice();
  var out = [], cur = null, i;
  for (i = 0; i < bars.length; i++) {
    var b = bars[i];
    var bt = Math.floor(b.time / tf) * tf;
    if (!cur || cur.time !== bt) {
      cur = { time: bt, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume || 0 };
      out.push(cur);
    } else {
      if (b.high > cur.high) cur.high = b.high;
      if (b.low < cur.low) cur.low = b.low;
      cur.close = b.close;
      cur.volume += b.volume || 0;
    }
    // Indikatoren: letzter M15-Wert im Bucket (Stand Bucket-Schluss)
    if (b.rsi != null) cur.rsi = b.rsi;
    if (b.bb_upper != null) { cur.bb_upper = b.bb_upper; cur.bb_middle = b.bb_middle; cur.bb_lower = b.bb_lower; }
    if (b.kc_upper != null) { cur.kc_upper = b.kc_upper; cur.kc_lower = b.kc_lower; }
    if (b.partial) cur.partial = true;
  }
  return out;
}

/* Laufende (noch nicht geschlossene) Kerze anhängen.
   History_1h liefert nur geschlossene Bars; ohne diesen Schritt endet der Chart
   eine Stunde in der Vergangenheit. High/Low sind Näherung aus letztem Close +
   Live-Kurs (echte Intra-Bar-Extreme liefert die H1-Historie nicht). */
function _withLiveBar(bars, d, liveOverride) {
  if (!bars || !bars.length || !d) return bars;
  var live = Number(liveOverride) || Number(d.live_price);
  if (!live) return bars;
  if (d.market_open === false) return bars;
  var step = _tfSeconds(d.timeframe) || _inferTF(bars);
  if (!step || step < 60) return bars;
  var now = Math.floor(Date.now() / 1000);
  var bucket = Math.floor(now / step) * step;
  var last = bars[bars.length - 1];
  if (bucket <= last.time) return bars;
  if (bucket - last.time > step * 6) return bars;   // Wochenende/Feiertag/Stale
  var open = Number(last.close);
  var out = bars.slice();
  out.push({
    time: bucket, open: open, high: Math.max(open, live),
    low: Math.min(open, live), close: live, volume: 0, partial: true
  });
  return out;
}

function _matchChartTrade(d, f) {
  if (!f || !d) return null;
  var arr = (d.live_trades || []).concat(d.open_positions || []);
  var best = null, bestDiff = 6 * 3600;
  var tol = Math.max(0.00001, Math.abs(Number(f.entry) || 0) * 0.002);
  for (var i = 0; i < arr.length; i++) {
    var t = arr[i];
    if (!t || !t.entry_time) continue;
    if (f.side && t.side && _isLong(f.side) !== _isLong(t.side)) continue;
    if (Math.abs(Number(t.price) - Number(f.entry)) > tol) continue;
    var dt = f.entry_ts ? Math.abs(t.entry_time - f.entry_ts) : 0;
    if (dt < bestDiff) { bestDiff = dt; best = t; }
  }
  return best;
}

function _excursion(bars, entryTs, exitTs, side, entry) {
  if (!bars || !bars.length || !entryTs) return null;
  var hi = -Infinity, lo = Infinity;
  for (var i = 0; i < bars.length; i++) {
    var b = bars[i];
    if (b.time < entryTs - 900 || (exitTs && b.time > exitTs + 900)) continue;
    if (b.high > hi) hi = b.high;
    if (b.low < lo) lo = b.low;
  }
  if (hi === -Infinity) return null;
  var isLong = _isLong(side);
  return {
    mfe: isLong ? hi - entry : entry - lo,
    mae: isLong ? entry - lo : hi - entry
  };
}

/* ── Chart rendern ─────────────────────────────────────────── */

function _renderCandlestick(d) {
  var container = el(C.prefix + '-candle-chart');
  var rsiContainer = el(C.prefix + '-rsi-chart');
  var rsiLabel = el(C.prefix + '-rsi-label');
  if (!container) return;
  if (typeof LightweightCharts === 'undefined') return;

  if (_candleChart) { _candleChart.remove(); _candleChart = null; }
  if (_rsiChart) { _rsiChart.remove(); _rsiChart = null; }
  if (_chartResizeObs) { _chartResizeObs.disconnect(); _chartResizeObs = null; }
  _candleSeries = null; _livePriceLine = null; _botChartBars = null;

  var f = _chartFocus;
  var _srcBars = d.bars || [];
  var _liveNow = (f && f.kind === 'position' && Number(f.current)) ? Number(f.current) : null;
  var raw = _withLiveBar(_srcBars, d, _liveNow);
  _chartLiveBar = raw.length > _srcBars.length;
  if (!raw.length) return;
  var cfg = d.config || {};
  var pip = _pipOf(d);
  var rawTF = _inferTF(raw);
  var stratTF = _strategyBaseTF(_lastDash || d, f);
  var baseTF = Math.max(stratTF, rawTF);

  // Chart-JSON ist die Wahrheit für Entry/Exit-Zeiten (Historie hat kein closed_at)
  if (f) {
    var match = _matchChartTrade(d, f);
    if (match) {
      if (!f.entry_ts) f.entry_ts = match.entry_time;
      if (!f.entry) f.entry = Number(match.price) || null;
      if (!f.sl && match.sl) f.sl = Number(match.sl) || null;
      if (!f.tp && match.tp) f.tp = Number(match.tp) || null;
      if (!f.exit_price && match.exit_price) f.exit_price = Number(match.exit_price) || null;
      if (f.kind === 'trade' && !f.exit_ts) f.exit_ts = _epochOf(match.exit_time);
    }
  }
  if (f && !f.entry_ts) f.entry_ts = raw[raw.length - 1].time - 24 * 3600;

  var exitTs = f ? _focusExitTs(f) : null;
  var tf = _chartTF === 'base' ? baseTF : Math.max(Number(_chartTF) || 0, baseTF);
  if (tf < baseTF) tf = baseTF;
  _chartTFUsed = tf;
  _baseTFUsed = baseTF;
  _stratTFUsed = stratTF;
  _paintRangeNav();

  if (!f && !_chartRangeTouched && baseTF >= 14400 && _chartRange === 3) {
    _chartRange = _defaultRangeDays(baseTF);
    _paintRangeNav();
  }

  var win = f ? _focusWindow(f, exitTs, tf, raw) : _overviewWindow(raw, _chartRange);
  var bars = _sliceBars(raw, win, tf);
  if (!bars.length) return;

  var isLong = _isLong(f ? f.side : 'long');
  var entry = f ? Number(f.entry) : null;
  var sl = f ? Number(f.sl) : null;
  var tp = f ? Number(f.tp) : null;
  var exitP = f ? Number(f.exit_price) : null;
  var current = null;
  if (f) {
    current = (f.kind === 'position')
      ? (Number(f.current) || Number(d.live_price) || bars[bars.length - 1].close)
      : exitP;
  }

  var dec = _decimals(pip, bars[bars.length - 1].close);
  container.style.height = f ? '380px' : '300px';

  _candleChart = LightweightCharts.createChart(container, {
    width: container.clientWidth || 800,
    height: container.clientHeight || (f ? 380 : 300),
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#9ca3af', fontSize: 11 },
    grid: {
      vertLines: { color: 'rgba(255,255,255,0.045)' },
      horzLines: { color: 'rgba(255,255,255,0.045)' }
    },
    crosshair: {
      mode: 0,
      vertLine: { color: 'rgba(226,232,240,0.30)', width: 1, style: 2, labelBackgroundColor: '#334155' },
      horzLine: { color: 'rgba(226,232,240,0.30)', width: 1, style: 2, labelBackgroundColor: '#334155' }
    },
    rightPriceScale: {
      borderColor: 'rgba(255,255,255,0.10)',
      scaleMargins: { top: 0.08, bottom: 0.08 }
    },
    timeScale: {
      borderColor: 'rgba(255,255,255,0.10)',
      timeVisible: true, secondsVisible: false, rightOffset: 5,
      barSpacing: f ? 8 : 4
    }
  });

  var candleSeries = _candleChart.addCandlestickSeries({
    upColor: '#1f7a4d', downColor: '#9b2c2c',
    borderUpColor: '#26a65b', borderDownColor: '#c0392b',
    wickUpColor: '#26a65b', wickDownColor: '#c0392b',
    priceFormat: { type: 'price', precision: dec, minMove: Math.pow(10, -dec) },
    priceLineVisible: !f,
    lastValueVisible: !f
  });

  candleSeries.setData(bars.map(function (b) {
    return { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close };
  }));

  // ── Y-Achse: Trade-Level müssen immer sichtbar sein ──
  if (f) {
    var lo = Infinity, hi = -Infinity, i;
    for (i = 0; i < bars.length; i++) {
      if (bars[i].low < lo) lo = bars[i].low;
      if (bars[i].high > hi) hi = bars[i].high;
    }
    var lv = [entry, sl, tp, current, exitP];
    for (i = 0; i < lv.length; i++) {
      var v = Number(lv[i]);
      if (isFinite(v) && v > 0) { if (v < lo) lo = v; if (v > hi) hi = v; }
    }
    if (isFinite(lo) && isFinite(hi) && hi > lo) {
      var pad = Math.max((hi - lo) * 0.09, Math.abs(hi) * 0.0002);
      var yLo = lo - pad, yHi = hi + pad;
      candleSeries.applyOptions({
        autoscaleInfoProvider: function () { return { priceRange: { minValue: yLo, maxValue: yHi } }; }
      });
    }
  }

  // ── Zonen + Preislinien ──
  if (f && entry && sl && tp && entry > 0) {
    _drawBand(_candleChart, bars, sl, entry, 'rgba(239,68,68,0.10)');
    _drawBand(_candleChart, bars, tp, entry, 'rgba(34,197,94,0.10)');
    // Keine In-Plot-Titel: Die Titel zeichnete LightweightCharts rechts IN die
    // Kerzenfläche und verdeckte genau den aktuellen Bereich. Preise bleiben als
    // Achsen-Label, die Zuordnung Preis+EUR steht in der Level-Leiste über dem Chart.
    candleSeries.createPriceLine({ price: entry, color: '#38bdf8', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '' });
    candleSeries.createPriceLine({ price: sl, color: '#ef4444', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '' });
    candleSeries.createPriceLine({ price: tp, color: '#22c55e', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '' });
    if (f.kind === 'trade' && exitP) {
      candleSeries.createPriceLine({ price: exitP, color: '#e2e8f0', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: '' });
    }
    if (f.kind === 'position' && current) {
      _livePriceLine = candleSeries.createPriceLine({ price: current, color: '#facc15', lineWidth: 3, lineStyle: 0, axisLabelVisible: true, title: '' });
    }
  }

  // ── Marker + Tooltip-Daten ──
  _allTradeMarkers = [];
  var markers = [];
  if (f) {
    var et = findNearestBarTime(bars, f.entry_ts);
    if (et) {
      markers.push({
        time: et, position: isLong ? 'belowBar' : 'aboveBar',
        color: isLong ? '#22c55e' : '#ef4444',
        shape: isLong ? 'arrowUp' : 'arrowDown', text: 'EINTRITT'
      });
    }
    if (f.kind === 'trade' && f.exit_ts) {
      var xt = findNearestBarTime(bars, f.exit_ts);
      if (xt) {
        markers.push({
          time: xt, position: isLong ? 'aboveBar' : 'belowBar',
          color: (Number(f.pnl) >= 0 ? '#22c55e' : '#ef4444'),
          shape: 'circle', text: 'EXIT'
        });
      }
    }
    _allTradeMarkers.push({
      entryTime: f.entry_ts, exitTime: f.exit_ts || f.entry_ts,
      entryPrice: entry, exitPrice: exitP || entry,
      direction: isLong ? 'long' : 'short',
      pnl: Number(f.pnl) || 0, pnlEur: Number(f.pnl) || 0,
      symbol: f.symbol || _currentPair || '',
      sl: sl, tp: tp,
      riskEur: f.risk_eur, rewardEur: f.reward_eur,
      strategy: f.strategy_id ? '#' + f.strategy_id : '',
      closeReason: f.close_reason || (f.kind === 'position' ? 'offen' : ''),
      isProfit: (Number(f.pnl) || 0) >= 0
    });
  } else if (_showTradeLines) {
    markers = _renderLiveMarkers(candleSeries, d.live_trades || [], bars, d.open_positions || []);
    if (_chartRange <= 14 && d.trade_lines && d.trade_lines.length) {
      _renderTradeLines(_candleChart, candleSeries, d.trade_lines, bars, 0.7);
    }
    if (d.open_positions && d.open_positions.length) {
      _renderOpenPositions(_candleChart, d.open_positions, bars);
    }
    // Backtest-/OPEN-Marker aus dem Builder (nur wenn Trades eingeblendet)
    if (d.markers && d.markers.length) {
      for (var m = 0; m < d.markers.length; m++) {
        var mm = d.markers[m];
        if (mm.type && mm.type !== 'trade') continue;
        var mt = findNearestBarTime(bars, mm.time);
        if (!mt) continue;
        markers.push({
          time: mt,
          position: mm.position || (mm.side === 'long' ? 'belowBar' : 'aboveBar'),
          color: mm.color || '#94a3b8',
          shape: mm.shape || 'arrowUp',
          text: mm.text || ''
        });
      }
    }
  }
  if (markers.length) {
    markers.sort(function (a, b) { return a.time - b.time; });
    candleSeries.setMarkers(markers);
  } else {
    candleSeries.setMarkers([]);
  }

  // ── Indikatoren (BB/KC/RSI) auf der ANGEZEIGTEN TF ──
  var _ind = _calcIndicators(bars, cfg);
  if (_showIndicators) _drawIndicatorLines(_candleChart, bars, _ind);

  // ── X-Achse: exakt das Trade-Fenster ──
  if (f) {
    _candleChart.timeScale().setVisibleRange({ from: win.start, to: win.end });
  } else if (_chartRange > 0) {
    _candleChart.timeScale().setVisibleRange({
      from: Math.max(bars[0].time, win.start),
      to: Math.max(bars[bars.length - 1].time, win.end)
    });
  } else {
    _candleChart.timeScale().fitContent();
  }

  _candleSeries = candleSeries;
  _botChartBars = bars;
  // Test-/Diagnose-Hook (E2E: Preisachse, Serien, Fenster ohne Canvas-OCR prüfen)
  window.__botChart = {
    chart: _candleChart, series: candleSeries, bars: bars, focus: f, tf: tf,
    updateLive: _updateLiveChart,
    setLive: function (v) { if (_chartFocus) _chartFocus.current = Number(v) || _chartFocus.current; _updateLiveChart(); }
  };

  if (typeof ResizeObserver !== 'undefined') {
    _chartResizeObs = new ResizeObserver(function () {
      if (_candleChart && container.clientWidth > 0) _candleChart.applyOptions({ width: container.clientWidth });
    });
    _chartResizeObs.observe(container);
  }
  if (f) _renderLevelLegend(f);

  // ── RSI ──
  _renderRsi(d, bars, cfg, _ind, rsiContainer, rsiLabel);

  // ── Config-Chips (nur Übersicht) ──
  var configEl = el(C.prefix + '-chart-config');
  if (configEl) {
    if (f) {
      configEl.innerHTML = '';
      configEl.style.display = 'none';
    } else {
      configEl.style.display = '';
      var chips = '';
      for (var k in cfg) {
        if (Object.prototype.hasOwnProperty.call(cfg, k) && cfg[k] !== '' && cfg[k] !== null) {
          chips += '<span class="bot-config-chip">' + k + ': ' + cfg[k] + '</span>';
        }
      }
      configEl.innerHTML = chips;
    }
  }

  _renderFocusBar(d);
  _subscribeLiveTooltip(_candleChart, container);
}

function _drawBand(chart, bars, price, base, color) {
  if (!chart.addBaselineSeries || !bars.length) return;
  var s = chart.addBaselineSeries({
    baseValue: { type: 'price', price: base },
    topLineColor: 'rgba(0,0,0,0)',
    bottomLineColor: 'rgba(0,0,0,0)',
    topFillColor1: color, topFillColor2: color,
    bottomFillColor1: color, bottomFillColor2: color,
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
    autoscaleInfoProvider: function () { return null; }
  });
  s.setData([
    { time: bars[0].time, value: price },
    { time: bars[bars.length - 1].time, value: price }
  ]);
}

function _valData(bars, vals) {
  var out = [];
  for (var i = 0; i < bars.length; i++) {
    if (vals[i] !== null && vals[i] !== undefined && isFinite(vals[i])) {
      out.push({ time: bars[i].time, value: vals[i] });
    }
  }
  return out;
}

function _smaAt(vals, p) {
  var out = new Array(vals.length).fill(null), sum = 0;
  for (var i = 0; i < vals.length; i++) {
    sum += vals[i];
    if (i >= p) sum -= vals[i - p];
    if (i >= p - 1) out[i] = sum / p;
  }
  return out;
}

function _emaAt(vals, p) {
  var out = new Array(vals.length).fill(null);
  if (vals.length < p) return out;
  var sum = 0, i;
  for (i = 0; i < p; i++) sum += vals[i];
  out[p - 1] = sum / p;
  var k = 2 / (p + 1);
  for (i = p; i < vals.length; i++) out[i] = vals[i] * k + out[i - 1] * (1 - k);
  return out;
}

function _rsiAt(closes, p) {
  var out = new Array(closes.length).fill(null);
  if (closes.length <= p) return out;
  var gain = 0, loss = 0, i, ch;
  for (i = 1; i <= p; i++) {
    ch = closes[i] - closes[i - 1];
    if (ch >= 0) gain += ch; else loss -= ch;
  }
  gain /= p; loss /= p;
  out[p] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  for (i = p + 1; i < closes.length; i++) {
    ch = closes[i] - closes[i - 1];
    var g = ch > 0 ? ch : 0, l = ch < 0 ? -ch : 0;
    gain = (gain * (p - 1) + g) / p;
    loss = (loss * (p - 1) + l) / p;
    out[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  }
  return out;
}

function _atrAt(highs, lows, closes, p) {
  var out = new Array(closes.length).fill(null);
  if (closes.length <= p) return out;
  var tr = [0], i;
  for (i = 1; i < closes.length; i++) {
    tr[i] = Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1]));
  }
  var sum = 0;
  for (i = 1; i <= p; i++) sum += tr[i];
  out[p] = sum / p;
  for (i = p + 1; i < closes.length; i++) out[i] = (out[i - 1] * (p - 1) + tr[i]) / p;
  return out;
}

/** Indikatoren für die ANGEZEIGTEN Bars (nicht die Basis-TF) — bei 4H-Aggregation
 *  müssen BB/KC/RSI aus 4H-Kerzen kommen, sonst zeigt der Chart H1-Werte im 4H-Mantel. */
function _calcIndicators(bars, cfg) {
  var closes = [], highs = [], lows = [];
  for (var i = 0; i < bars.length; i++) {
    closes.push(bars[i].close);
    highs.push(bars[i].high);
    lows.push(bars[i].low);
  }
  var p = cfg || {};
  var rp = p.rsi_period || 14;
  var bp = p.bb_period || 20;
  var bm = p.bb_mult || 2;
  var kp = p.kc_period || 14;
  var km = p.kc_mult || 1.5;
  var rsi = _rsiAt(closes, rp);
  var mid = _smaAt(closes, bp);
  var up = new Array(bars.length).fill(null);
  var lo = new Array(bars.length).fill(null);
  for (var j = bp - 1; j < closes.length; j++) {
    var mean = mid[j], sq = 0;
    for (var q = j - bp + 1; q <= j; q++) { var dv = closes[q] - mean; sq += dv * dv; }
    var sd = Math.sqrt(sq / bp);
    up[j] = mean + bm * sd;
    lo[j] = mean - bm * sd;
  }
  var ema = _emaAt(closes, kp);
  var atr = _atrAt(highs, lows, closes, kp);
  var ku = new Array(bars.length).fill(null);
  var kl = new Array(bars.length).fill(null);
  for (var z = 0; z < bars.length; z++) {
    if (ema[z] !== null && atr[z] !== null) { ku[z] = ema[z] + km * atr[z]; kl[z] = ema[z] - km * atr[z]; }
  }
  return { rsi: rsi, bb_up: up, bb_mid: mid, bb_lo: lo, kc_up: ku, kc_lo: kl };
}

function _drawIndicatorLines(chart, bars, ind) {
  if (!ind) return;
  var up = _valData(bars, ind.bb_up);
  var mid = _valData(bars, ind.bb_mid);
  var lo = _valData(bars, ind.bb_lo);
  if (up.length > 1 && lo.length > 1) {
    _addLine(chart, up, 'rgba(96,165,250,0.55)', 1, 0);
    _addLine(chart, lo, 'rgba(96,165,250,0.55)', 1, 0);
    _addLine(chart, mid, 'rgba(96,165,250,0.28)', 1, 2);
  }
  var ku = _valData(bars, ind.kc_up);
  var kl = _valData(bars, ind.kc_lo);
  if (ku.length > 1 && kl.length > 1) {
    _addLine(chart, ku, 'rgba(192,132,252,0.45)', 1, 0);
    _addLine(chart, kl, 'rgba(192,132,252,0.45)', 1, 0);
  }
}

function _addLine(chart, data, color, width, style) {
  var s = chart.addLineSeries({
    color: color, lineWidth: width, lineStyle: style || 0,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    autoscaleInfoProvider: function () { return null; }
  });
  s.setData(data);
}

/* Live-Update der letzten Kerze + JETZT-Linie (Dashboard-Refresh, 60s).
   Chart-JSON ist ein Snapshot; der frische Kurs kommt aus der offenen Position. */
function _updateLiveChart() {
  if (!_candleSeries || !_botChartBars || !_chartLiveBar || !_chartFocus) return;
  if (_chartFocus.kind !== 'position') return;
  var live = Number(_chartFocus.current);
  if (!live) return;
  var bars = _botChartBars;
  var last = bars[bars.length - 1];
  if (!last) return;
  var tf = _chartTFUsed || 3600;
  var bucket = Math.floor(Date.now() / 1000 / tf) * tf;
  if (last.partial && bucket === last.time) {
    var high = Math.max(last.high, live), low = Math.min(last.low, live);
    _candleSeries.update({ time: bucket, open: last.open, high: high, low: low, close: live });
    last.high = high; last.low = low; last.close = live;
  } else if (bucket > last.time) {
    var open = last.close;
    var bar = {
      time: bucket, open: open, high: Math.max(open, live),
      low: Math.min(open, live), close: live, volume: 0, partial: true
    };
    _candleSeries.update(bar);
    bars.push(bar);
  } else {
    return;
  }
  if (_livePriceLine) _livePriceLine.applyOptions({ price: live });
}

function _renderRsi(d, bars, cfg, ind, container, label) {
  var data = (ind && ind.rsi) ? _valData(bars, ind.rsi) : [];
  if (!container || !_showIndicators || data.length < 2) {
    if (container) { container.style.display = 'none'; }
    if (label) { label.style.display = 'none'; }
    return;
  }
  container.style.display = '';
  if (label) label.style.display = '';

  _rsiChart = LightweightCharts.createChart(container, {
    width: container.clientWidth || 800,
    height: container.clientHeight || 100,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b8b9e', fontSize: 10 },
    grid: { vertLines: { color: 'rgba(255,255,255,0.025)' }, horzLines: { color: 'rgba(255,255,255,0.025)' } },
    timeScale: { visible: false },
    rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)', scaleMargins: { top: 0.1, bottom: 0.1 } }
  });
  var s = _rsiChart.addLineSeries({
    color: '#a78bfa', lineWidth: 1.5,
    priceLineVisible: false, lastValueVisible: false,
    autoscaleInfoProvider: function () { return { priceRange: { minValue: 0, maxValue: 100 } }; }
  });
  s.setData(data);
  var os = cfg.rsi_oversold || 30;
  var ob = cfg.rsi_overbought || 70;
  s.createPriceLine({ price: os, color: 'rgba(34,197,94,0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OS' });
  s.createPriceLine({ price: ob, color: 'rgba(239,68,68,0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OB' });
  s.createPriceLine({ price: 50, color: 'rgba(255,255,255,0.10)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });

  if (label) {
    label.textContent = 'RSI ' + (cfg.rsi_period || 14) + ' · ' + data[data.length - 1].value.toFixed(1);
  }
  if (typeof ResizeObserver !== 'undefined') {
    var obs = new ResizeObserver(function () {
      if (_rsiChart && container.clientWidth > 0) _rsiChart.applyOptions({ width: container.clientWidth });
    });
    obs.observe(container);
  }
}

/* ── Kurzprofil über dem Chart ─────────────────────────────── */

function _setupLine(d, f) {
  var bits = [];
  if (f && f.tech) bits.push(f.tech);
  var c = (d && d.config) || {};
  if (c.rsi_period) bits.push('RSI ' + c.rsi_period + ' (' + (c.rsi_oversold || 30) + '/' + (c.rsi_overbought || 70) + ')');
  if (c.bb_period) bits.push('BB ' + c.bb_period + '/' + (c.bb_mult || 2));
  if (c.kc_period) bits.push('KC ' + c.kc_period + '/' + (c.kc_mult || 1.5));
  return bits.slice(0, 6).join(' · ');
}

function _renderLevelLegend(f) {
  var box = el(C.prefix + '-level-legend');
  if (!box) return;
  if (!f) { box.style.display = 'none'; box.innerHTML = ''; return; }
  var pip = _pipOf(_lastChartData);
  var isLong = _isLong(f.side);
  var cur = (f.kind === 'position')
    ? (Number(f.current) || Number(_lastChartData && _lastChartData.live_price) || null)
    : (Number(f.exit_price) || null);
  var h = '<span class="bll-item"><i style="background:#38bdf8"></i>EINTRITT <b>' + _fmtP(f.entry, pip) + '</b></span>';
  h += '<span class="bll-item"><i style="background:#ef4444"></i>SL <b>' + _fmtP(f.sl, pip) + '</b>' +
    (f.risk_eur != null ? ' <span class="bll-eur down">' + _fmtEur(-Math.abs(f.risk_eur)) + '</span>' : '') + '</span>';
  h += '<span class="bll-item"><i style="background:#22c55e"></i>TP <b>' + _fmtP(f.tp, pip) + '</b>' +
    (f.reward_eur != null ? ' <span class="bll-eur up">' + _fmtEur(Math.abs(f.reward_eur)) + '</span>' : '') + '</span>';
  if (f.kind === 'position' && cur) {
    h += '<span class="bll-item"><i style="background:#facc15"></i>JETZT <b>' + _fmtP(cur, pip) + '</b>' +
      (f.pnl != null ? ' <span class="bll-eur ' + (Number(f.pnl) >= 0 ? 'up' : 'down') + '">' + fmtPnl(f.pnl) + ' €</span>' : '') + '</span>';
  } else if (f.kind === 'trade' && cur) {
    h += '<span class="bll-item"><i style="background:#e2e8f0"></i>EXIT <b>' + _fmtP(cur, pip) + '</b>' +
      (f.pnl != null ? ' <span class="bll-eur ' + (Number(f.pnl) >= 0 ? 'up' : 'down') + '">' + fmtPnl(f.pnl) + ' €</span>' : '') + '</span>';
  }
  if (_chartLiveBar) {
    h += '<span class="bll-item" title="Letzte Kerze = laufende Teilkerze (High/Low aus letztem Close + Live-Kurs)">' +
      '<i style="background:#facc15"></i>LIVE</span>';
  }
  box.innerHTML = h;
  box.style.display = '';
}

function _renderFocusBar(d) {
  var box = el(C.prefix + '-trade-focus');
  if (!box) return;
  var f = _chartFocus;
  if (!f) {
    box.style.display = 'none';
    box.innerHTML = '';
    _renderLevelLegend(null);
    return;
  }
  box.style.display = 'block';

  var pip = _pipOf(d);
  var entry = Number(f.entry) || null;
  var sl = Number(f.sl) || null;
  var tp = Number(f.tp) || null;
  var exitP = Number(f.exit_price) || null;
  var isLong = _isLong(f.side);
  var cur = entry;
  if (f.kind === 'position') {
    cur = Number(f.current) || Number(d && d.live_price) ||
      (d && d.bars && d.bars.length ? d.bars[d.bars.length - 1].close : entry);
  } else {
    cur = exitP || entry;
  }
  var endTs = _focusExitTs(f);
  var dur = (endTs && f.entry_ts) ? Math.max(0, endTs - f.entry_ts) : 0;
  var risk = (entry && sl) ? Math.abs(entry - sl) : 0;
  var reward = (entry && tp) ? Math.abs(tp - entry) : 0;
  var move = (cur !== null && entry !== null) ? (isLong ? cur - entry : entry - cur) : 0;
  var r = risk ? move / risk : null;
  var prog = reward ? move / reward : null;
  var rr = risk ? reward / risk : null;
  var exc = (d && d.bars && entry) ? _excursion(d.bars, f.entry_ts, endTs, f.side, entry) : null;
  // Live-Kurs kann frischer sein als der letzte Chart-Bar → MFE/MAE damit erweitern.
  if (exc) { exc.mfe = Math.max(exc.mfe, move); exc.mae = Math.max(exc.mae, -move); }

  var dp = pip;
  var pips = (pip && cur !== null && entry !== null) ? move / pip : null;
  var slPips = (pip && sl && entry) ? (isLong ? sl - entry : entry - sl) / pip : null;
  var tpPips = (pip && tp && entry) ? (isLong ? tp - entry : entry - tp) / pip : null;

  var resTxt, resCls;
  if (f.kind === 'position') { resTxt = 'OFFEN'; resCls = 'open'; }
  else if (f.pnl !== null && f.pnl !== undefined && !isNaN(Number(f.pnl))) {
    resTxt = Number(f.pnl) >= 0 ? 'GEWINN' : 'VERLUST';
    resCls = Number(f.pnl) >= 0 ? 'win' : 'loss';
  } else { resTxt = 'GESCHLOSSEN'; resCls = 'open'; }

  var entryTick = (risk && reward) ? (risk / (risk + reward)) * 100 : 50;
  var mkPos = (prog === null) ? entryTick : Math.max(0, Math.min(100, prog * 100));
  var mkCls = (prog !== null && prog < 0) ? 'down' : 'up';

  var h = '<div class="btf-head">' +
    '<div class="btf-title">' +
      '<span class="btf-dir ' + (isLong ? 'buy' : 'sell') + '">' + (isLong ? 'LONG' : 'SHORT') + '</span>' +
      '<b class="btf-sym">' + escHtml(f.symbol || _currentPair || '') + '</b>' +
      (f.strategy_id ? '<span class="btf-id">#' + escHtml(f.strategy_id) + (f.slot_id ? ' · ' + escHtml(f.slot_id) : '') + '</span>' : '') +
      '<span class="btf-id">TF ' + _tfLabel(_stratTFUsed || _strategyBaseTF(d, f)) + '</span>' +
      '<span class="btf-when">' + (f.entry_ts ? fmtTime(f.entry_ts) : '—') +
        (f.kind === 'trade' ? ' → ' + (f.exit_ts ? fmtTime(f.exit_ts) : 'Ende') : ' → jetzt') + '</span>' +
    '</div>' +
    '<div class="btf-actions">' +
      '<span class="btf-res ' + resCls + '">' + resTxt + '</span>' +
      (f.close_reason ? '<span class="btf-id">' + escHtml(f.close_reason) + '</span>' : '') +
      '<button class="btf-btn" onclick="BotDash.clearFocus()">◀ Übersicht</button>' +
    '</div>' +
  '</div>';

  h += '<div class="btf-grid">' +
    '<div class="btf-cell"><span>Einstieg</span><b>' + _fmtP(entry, dp) + '</b><small>' + (f.entry_ts ? fmtTime(f.entry_ts) : '—') + '</small></div>' +
    '<div class="btf-cell"><span>' + (f.kind === 'position' ? 'Jetzt' : 'Exit') + '</span><b class="' + (move >= 0 ? 'up' : 'down') + '">' + _fmtP(cur, dp) + '</b><small>' +
      (pips !== null ? _fmtPips(pips) + ' · ' : '') + _fmtR(r) + '</small></div>' +
    '<div class="btf-cell"><span>Stop-Loss</span><b class="down">' + _fmtP(sl, dp) + '</b><small>' +
      (slPips !== null ? _fmtPips(slPips) + ' · ' : '') + (f.risk_eur != null ? _fmtEur(-Math.abs(f.risk_eur)) + ' · ' : '') + (risk ? _fmtR(-1) : '—') + '</small></div>' +
    '<div class="btf-cell"><span>Take-Profit</span><b class="up">' + _fmtP(tp, dp) + '</b><small>' +
      (tpPips !== null ? _fmtPips(tpPips) + ' · ' : '') + (f.reward_eur != null ? _fmtEur(Math.abs(f.reward_eur)) + ' · ' : '') + (reward ? _fmtR(1) : '—') + '</small></div>' +
    '<div class="btf-cell"><span>R:R</span><b>' + (rr !== null ? rr.toFixed(2) : '—') + '</b><small>' +
      (f.risk_eur != null || f.reward_eur != null
        ? 'Risiko ' + _fmtEur(-Math.abs(f.risk_eur || 0)) + ' / ' + _fmtEur(Math.abs(f.reward_eur || 0))
        : (risk && pip ? 'Risiko ' + Math.abs(risk / pip).toFixed(1) + ' p' : '')) + '</small></div>' +
    '<div class="btf-cell"><span>Dauer</span><b>' + _fmtDurSec(dur) + '</b><small>' +
      (f.pnl !== null && f.pnl !== undefined ? fmtPnl(f.pnl) + ' €' : (f.kind === 'position' ? 'offen' : '—')) + '</small></div>' +
  '</div>';

  if (risk && reward) {
    h += '<div class="btf-track">' +
      '<div class="btf-bar">' +
        '<div class="btf-zone-loss" style="width:' + entryTick.toFixed(1) + '%"></div>' +
        '<div class="btf-zone-win" style="left:' + entryTick.toFixed(1) + '%"></div>' +
        '<div class="btf-entry-tick" style="left:' + entryTick.toFixed(1) + '%"></div>' +
        '<div class="btf-mk ' + mkCls + '" style="left:' + mkPos.toFixed(1) + '%"></div>' +
      '</div>' +
      '<div class="btf-scale"><span>SL ' + _fmtP(sl, dp) + (f.risk_eur != null ? ' \u00b7 ' + _fmtEur(-Math.abs(f.risk_eur)) : '') + '</span><span class="btf-entry">Einstieg ' + _fmtP(entry, dp) + '</span><span>TP ' + _fmtP(tp, dp) + (f.reward_eur != null ? ' \u00b7 ' + _fmtEur(Math.abs(f.reward_eur)) : '') + '</span></div>' +
    '</div>';
  }

  h += '<div class="btf-foot">' +
    '<span>Fortschritt <b class="' + (r !== null && r < 0 ? 'down' : 'up') + '">' + _fmtR(r) + '</b>' +
      (prog !== null ? ' · ' + (prog * 100).toFixed(0) + '% Richtung TP' : '') + '</span>' +
    (exc ? '<span>Max. Buchgewinn <b class="up">' + _fmtR(risk ? exc.mfe / risk : null) + '</b></span>' +
      '<span>Max. Gegenwind <b class="down">' + _fmtR(risk ? -exc.mae / risk : null) + '</b></span>' : '') +
    '<span class="btf-setup">' + escHtml(_setupLine(d, f)) + '</span>' +
  '</div>';

  box.innerHTML = h;
  _renderLevelLegend(f);
}

/* ── Overlays ─────────────────────────────────────────────── */

function _renderLiveMarkers(candleSeries, liveTrades, bars, openPos) {
  if (!bars || !bars.length) return [];
  var markers = [];
  var i;
  for (i = 0; i < liveTrades.length; i++) {
    var t = liveTrades[i];
    var entryPrice = Number(t.price) || 0;
    if (!entryPrice) continue;
    var isLongT = _isLong(t.side);
    var et = findNearestBarTime(bars, t.entry_time);
    if (!et) continue;
    var xt = t.exit_time ? findNearestBarTime(bars, t.exit_time) : null;
    var win = (Number(t.pnl_pips) || 0) >= 0;
    markers.push({
      time: et, position: isLongT ? 'belowBar' : 'aboveBar',
      color: win ? '#22c55e' : '#ef4444',
      shape: isLongT ? 'arrowUp' : 'arrowDown', text: ''
    });
    if (xt && xt > et) {
      markers.push({ time: xt, position: isLongT ? 'aboveBar' : 'belowBar', color: win ? '#22c55e' : '#ef4444', shape: 'circle', text: '' });
    }
    _allTradeMarkers.push({
      entryTime: t.entry_time, exitTime: t.exit_time || t.entry_time,
      entryPrice: entryPrice, exitPrice: Number(t.exit_price) || entryPrice,
      direction: isLongT ? 'long' : 'short',
      pnl: Number(t.pnl_eur) || 0, pnlEur: Number(t.pnl_eur) || 0,
      symbol: t.symbol || _currentPair || '',
      sl: t.sl, tp: t.tp,
      strategy: '', closeReason: t.result || '',
      isProfit: win
    });
  }
  // Offene Positionen bekommen ihren OPEN-Pfeil aus d.markers (Builder).
  return markers;
}

function _renderTradeLines(chart, candleSeries, tradeLines, bars, alpha) {
  for (var i = 0; i < tradeLines.length; i++) {
    var tl = tradeLines[i];
    var et = findNearestBarTime(bars, tl.entry_time);
    var xt = findNearestBarTime(bars, tl.exit_time);
    if (!et) continue;
    var pnl = Number(tl.pnl_pips) || 0;
    var isWin = pnl >= 0;
    var clr = isWin ? 'rgba(34,197,94,' + alpha + ')' : 'rgba(239,68,68,' + alpha + ')';
    var line = chart.addLineSeries({
      color: clr, lineWidth: 2, lineStyle: tl.dashed ? 2 : 0,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      autoscaleInfoProvider: function () { return null; }
    });
    line.setData([
      { time: et, value: Number(tl.price) || Number(tl.entry_price) },
      { time: xt || et, value: Number(tl.exit_price) || Number(tl.price) || Number(tl.entry_price) }
    ]);
  }
}

function _renderOpenPositions(chart, positions, bars) {
  if (!bars || !bars.length) return;
  var lastBarTime = bars[bars.length - 1].time;
  for (var i = 0; i < positions.length; i++) {
    var p = positions[i];
    var entry = Number(p.price || p.entry_price || p.entry);
    if (!entry) continue;
    var et = findNearestBarTime(bars, p.entry_time) || bars[Math.max(0, bars.length - 50)].time;
    var lineStart = Math.max(bars[0].time, et - 24 * 3600);
    var isLong = _isLong(p.side);

    var entryLine = chart.addLineSeries({
      color: isLong ? '#22c55e' : '#ef4444', lineWidth: 2,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      autoscaleInfoProvider: function () { return null; }
    });
    entryLine.setData([{ time: lineStart, value: entry }, { time: lastBarTime, value: entry }]);

    if (p.sl) {
      var slLine = chart.addLineSeries({
        color: 'rgba(239,68,68,0.65)', lineWidth: 1, lineStyle: 2,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        autoscaleInfoProvider: function () { return null; }
      });
      slLine.setData([{ time: lineStart, value: Number(p.sl) }, { time: lastBarTime, value: Number(p.sl) }]);
    }
    if (p.tp) {
      var tpLine = chart.addLineSeries({
        color: 'rgba(34,197,94,0.65)', lineWidth: 1, lineStyle: 2,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        autoscaleInfoProvider: function () { return null; }
      });
      tpLine.setData([{ time: lineStart, value: Number(p.tp) }, { time: lastBarTime, value: Number(p.tp) }]);
    }
  }
}


/** Subscribe to crosshair for live trade tooltips */ 
function _subscribeLiveTooltip(chart, container) { 
  var tooltipEl = document.getElementById(C.prefix + "-trade-tooltip"); 
  if (!tooltipEl) { 
    tooltipEl = document.createElement("div"); 
    tooltipEl.id = C.prefix + "-trade-tooltip"; 
    tooltipEl.style.cssText = "position:fixed;display:none;z-index:9999;background:rgba(20,20,30,0.95);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 14px;font-size:12px;color:#e0e0e0;z-index:100;pointer-events:none;box-shadow:0 4px 12px rgba(0,0,0,0.4);font-family:monospace;max-width:320px;line-height:1.6;"; 
    document.body.appendChild(tooltipEl); 
  } 
  chart.subscribeCrosshairMove(function(param) { 
    if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) { 
      tooltipEl.style.display = "none"; 
      return; 
    } 
    var nearest = null, minDist = Infinity; 
    for (var j = 0; j < _allTradeMarkers.length; j++) { 
      var tm = _allTradeMarkers[j]; 
      var dist = Math.min(Math.abs(param.time - tm.entryTime), Math.abs(param.time - tm.exitTime)); 
      if (dist < minDist && dist < 3600 * 6) { minDist = dist; nearest = tm; } 
    } 
    if (nearest) { 
      var dir = nearest.direction.toUpperCase(); 
      var icon = dir === "LONG" ? "\u{1F7E2}" : "\u{1F534}"; 
      var pnlColor = nearest.isProfit ? "#22c55e" : "#ef4444"; 
      var pnlSign = nearest.pnlEur >= 0 ? "+" : ""; 
      var durMs = (nearest.exitTime - nearest.entryTime) * 1000; 
      var durH = Math.round(durMs / 3600000); 
      var durStr = durH >= 24 ? Math.round(durH / 24) + "d " + (durH % 24) + "h" : durH + "h"; 
      var html = "<div style=\"font-weight:700;margin-bottom:6px;font-size:13px\">" + icon + " " + dir + " " + nearest.symbol + "</div>";
      if (nearest.strategy)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Strategy</span><span>" + nearest.strategy + "</span></div>";
      html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Entry</span><span>" + (nearest.entryPrice||0).toFixed(5) + "</span></div>";
      if (nearest.exitPrice && nearest.exitPrice !== nearest.entryPrice)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Exit</span><span>" + (nearest.exitPrice||0).toFixed(5) + "</span></div>";
      if (nearest.sl)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#ef4444\">SL</span><span>" + nearest.sl.toFixed(5) + "</span></div>";
      if (nearest.tp)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#22c55e\">TP</span><span>" + nearest.tp.toFixed(5) + "</span></div>";
      if (nearest.riskEur != null)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Risiko</span><span>-" + Number(nearest.riskEur).toFixed(2) + " \u20ac</span></div>";
      if (nearest.rewardEur != null)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Chance</span><span>+" + Number(nearest.rewardEur).toFixed(2) + " \u20ac</span></div>";
      if (nearest.score != null)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Score</span><span>" + nearest.score + "</span></div>";
      if (nearest.rsi != null)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">RSI</span><span>" + (typeof nearest.rsi === 'number' ? nearest.rsi.toFixed(1) : nearest.rsi) + "</span></div>";
      html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Dauer</span><span>" + durStr + (nearest.holdBars ? " (" + nearest.holdBars + " bars)" : "") + "</span></div>";
      if (nearest.closeReason)
        html += "<div style=\"display:flex;justify-content:space-between;gap:16px\"><span style=\"color:#8b8b9e\">Grund</span><span>" + nearest.closeReason + "</span></div>";
      html += "<div style=\"border-top:1px solid rgba(255,255,255,0.1);margin-top:6px;padding-top:6px;color:" + pnlColor + ";font-weight:700;font-size:15px;text-align:right\">" + pnlSign + nearest.pnlEur.toFixed(2) + " \u20ac</div>";
      tooltipEl.innerHTML = html; 
      tooltipEl.style.display = "block"; 
      var rect = container.getBoundingClientRect(); 
      var x = rect.left + param.point.x + 15; 
      var y = rect.top + param.point.y + 15; 
      if (x + 320 > window.innerWidth) x = rect.left + param.point.x - 335; 
      if (y + 150 > window.innerHeight) y = rect.top + param.point.y - 165; 
      tooltipEl.style.left = x + "px"; 
      tooltipEl.style.top = y + "px"; 
    } else { 
      tooltipEl.style.display = "none"; 
    } 
  }); 
} 

function closeChart() {
  var panel = el(C.prefix + '-chart-panel');
  if (panel) panel.className = 'bot-chart-panel';
  if (_candleChart) { _candleChart.remove(); _candleChart = null; }
  if (_rsiChart) { _rsiChart.remove(); _rsiChart = null; }
  if (_chartResizeObs) { _chartResizeObs.disconnect(); _chartResizeObs = null; }
  _currentPair = null;
  _chartFocus = null;
  _lastChartData = null;
  _lastChartPair = null;
}

function setRange(days) {
  _chartRange = Number(days) || 0;
  _chartRangeTouched = true;
  _paintRangeNav();
  if (_lastChartData) _renderCandlestick(_lastChartData);
}

function toggleTradeLines() {
  _showTradeLines = !_showTradeLines;
  var btn = el(C.prefix + '-trade-toggle');
  if (btn) {
    btn.textContent = _showTradeLines ? '📊 Trades: ON' : '📊 Trades: OFF';
    btn.style.color = _showTradeLines ? '#22c55e' : 'var(--c-text-dim)';
  }
  _paintLegend();
  if (_lastChartData) _renderCandlestick(_lastChartData);
}

/* ═══════════════════════════════════════════════════════════
 *  PERFORMANCE HEATMAP
 * ═══════════════════════════════════════════════════════════ */

function renderHeatmap() {
  var grid = el(C.prefix + '-heatmap-grid');
  if (!grid || !C.heatmapPath) return;

  safeFetch(C.heatmapPath).then(function(r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function(d) {
    var rawPairs = d.pairs || [];
    // Handle dict format (from build scripts) — convert to array
    var pairs = Array.isArray(rawPairs)
      ? rawPairs
      : Object.keys(rawPairs).map(function(k) {
          var v = rawPairs[k]; v.symbol = k; return v;
        });
    if (pairs.length === 0) {
      grid.innerHTML = '<div class="bot-no-data">No heatmap data</div>';
      return;
    }
    var html = '';
    for (var i = 0; i < pairs.length; i++) {
      var p = pairs[i];
      var wr = p.win_rate || 0;
      var pnl = p.total_pnl || 0;
      var trades = p.trades || 0;
      var hasData = trades > 0;
      var color = !hasData ? '#666' : (wr >= 60 ? '#22c55e' : (wr >= 40 ? '#f0b940' : '#ef4444'));
      var barColor = !hasData ? 'rgba(128,128,128,0.15)' : (pnl >= 0 ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)');
      html += '<div class="bot-heatmap-cell' + (!hasData ? ' bot-heatmap-empty' : '') + '" onclick="BotDash.openChart(\'' + p.symbol + '\')">';
      html += '<div class="pair-name">' + p.symbol + '</div>';
      html += '<div class="wr-value" style="color:' + color + '">' + (hasData ? wr.toFixed(0) + '%' : '—') + '</div>';
      html += '<div class="pnl-value ' + (!hasData ? '' : pnlClass(pnl)) + '">' + (hasData ? fmtPnl(pnl) + ' EUR' : 'keine Daten') + '</div>';
      html += '<div class="trade-count">' + trades + ' trades</div>';
      html += '<div class="bot-heatmap-bar" style="background:' + barColor + ';width:' + (hasData ? Math.min(100, Math.abs(pnl)) : 0) + '%"></div>';
      html += '</div>';
    }
    grid.innerHTML = html;
  }).catch(function() {
    grid.innerHTML = '<div class="bot-no-data">Heatmap unavailable</div>';
  });
}

/* ═══════════════════════════════════════════════════════════
 *  BACKTEST OVERVIEW
 * ═══════════════════════════════════════════════════════════ */

/** Füllt die Benchmark-Karten im Lab-Tab (nur aufgerufen, wenn Daten existieren). */
function _fillLabBench(bt) {

  var fields = [
    { id: 'bt-wr', val: bt.win_rate != null ? bt.win_rate.toFixed(1) + '%' : '—', cls: bt.win_rate >= 50 ? 'bot-pnl-pos' : 'bot-pnl-neg' },
    { id: 'bt-pf', val: bt.profit_factor != null ? bt.profit_factor.toFixed(2) : '—', cls: bt.profit_factor >= 1.5 ? 'bot-pnl-pos' : '' },
    { id: 'bt-exp', val: bt.expectancy != null ? fmtPnl(bt.expectancy) : '—', cls: pnlClass(bt.expectancy || 0) },
    { id: 'bt-pnl', val: bt.total_pnl != null ? '€' + bt.total_pnl.toFixed(0) : '—', cls: pnlClass(bt.total_pnl || 0) },
    { id: 'bt-dd', val: bt.max_drawdown_pct != null ? bt.max_drawdown_pct.toFixed(1) + '%' : '—', cls: 'bot-pnl-neg' },
  ];
  for (var i = 0; i < fields.length; i++) {
    var f = fields[i];
    var e = el(C.prefix + '-' + f.id);
    if (e) { e.textContent = f.val; if (f.cls) e.className = 'bot-card-value ' + f.cls; }
  }

  // OOS — recipe WFO or standard walk-forward
  var oosEl = el(C.prefix + '-bt-oos');
  if (oosEl) {
    var recipe = bt.recipe;
    if (recipe) {
      var passRate = recipe.oos_pass_rate != null ? (recipe.oos_pass_rate * 100).toFixed(0) + '%' : '—';
      var mInfo = (recipe.is_months != null && recipe.oos_months != null) ? 'IS=' + recipe.is_months + 'M / OOS=' + recipe.oos_months + 'M · ' : 'WFO · ';
      oosEl.textContent = mInfo + passRate;
      oosEl.className = 'bot-card-value ' + (recipe.tier === 'A' ? 'bot-pnl-pos' : '');
    } else {
      var oosOk = bt.oos_profitable || 0;
      var oosTotal = bt.oos_total || 0;
      oosEl.textContent = oosTotal > 0 ? oosOk + '/' + oosTotal : '—';
      oosEl.className = 'bot-card-value ' + (oosOk === oosTotal && oosTotal > 0 ? 'bot-pnl-pos' : '');
    }
  }

  // OOS Sub — recipe details
  var oosSubEl = el(C.prefix + '-bt-oos-sub');
  if (oosSubEl && bt.recipe) {
    var r = bt.recipe;
    var parts = [];
    parts.push('Tier ' + r.tier);
    if (r.mc_pass) parts.push('MC ✅');
    if (r.slip_pass) parts.push('Slip ✅');
    parts.push(r.assets.length + ' Assets');
    oosSubEl.textContent = parts.join(' · ');
  }

  // Verdict
  var pairsSubEl = el(C.prefix + '-bt-pairs-sub');
  if (pairsSubEl && bt.recipe) {
    pairsSubEl.textContent = bt.recipe.assets.join(', ');
  }

  // Verdict
  var verdictEl = el(C.prefix + '-bt-verdict');
  if (verdictEl) {
    if (bt.recipe) {
      verdictEl.textContent = bt.recipe.label + ' — ' + bt.recipe.name.split(' #')[0];
    } else if (bt.verdict) {
      verdictEl.textContent = bt.verdict;
    }
  }

  // Verdict Sub — recipe params
  var verdictSubEl = el(C.prefix + '-bt-verdict-sub');
  if (verdictSubEl && bt.recipe) {
    var p = bt.recipe.params || {};
    var parts = [];
    if (p.sl_mult) parts.push('SL=' + p.sl_mult + '×ATR');
    if (p.tp_r) parts.push('TP=' + p.tp_r + 'R');
    if (p.rsi_period) parts.push('RSI(' + p.rsi_period + ')');
    if (bt.recipe.merge_mode) parts.push(bt.recipe.merge_mode);
    if (bt.recipe.risk_pct) parts.push('Risk=' + bt.recipe.risk_pct + '%');
    verdictSubEl.textContent = parts.join(' · ');
  }
}

/** Lab-Referenz-Tab (Umbau 11.10.): Backtest-Benchmark (nur wenn Daten),
    Validierungstabelle je Strategie (Join über shadow_portfolio.json) und
    Re-Opt-Status. Leere Blöcke bleiben ausgeblendet — keine „—"-Wüsten. */
function renderLab(d) {
  // 1) Backtest-Benchmark — nur wenn dashboard.backtest echte Zahlen liefert
  var benchWrap = el(C.prefix + '-lab-bench');
  var bt = d.backtest_summary || d.backtest || {};
  var hasBench = !!(bt && (bt.win_rate != null || bt.profit_factor != null || bt.total_pnl != null));
  if (benchWrap) {
    benchWrap.style.display = hasBench ? '' : 'none';
    if (hasBench) _fillLabBench(bt);
  }

  // 2) Validierungstabelle je Strategie (Slots + shadow_portfolio.json)
  var stratsWrap = el(C.prefix + '-lab-strats');
  var tbody = el(C.prefix + '-lab-strats-body');
  if (stratsWrap && tbody) {
    var wanted = [];
    var seen = {};
    var slots = d.slots || [];
    for (var i = 0; i < slots.length; i++) {
      var sid = slots[i].strategy_id;
      if (sid == null) continue;
      var key = String(sid);
      if (!seen[key]) { seen[key] = 1; wanted.push(sid); }
    }
    _loadShadowPortfolio(function(sp) {
      var byId = {};
      if (sp && sp.strategies) {
        for (var j = 0; j < sp.strategies.length; j++) byId[sp.strategies[j].id] = sp.strategies[j];
      }
      var h = '';
      for (var k = 0; k < wanted.length; k++) {
        var s2 = wanted[k];
        var m = byId[s2] || byId[String(s2)];
        var nm = (m && m.name) ? _spShortName(m.name) : '';
        var pf = (m && m.oos_pf != null) ? Number(m.oos_pf).toFixed(2) : '—';
        var trs = (m && m.oos_trades != null) ? m.oos_trades : '—';
        var pnl = '—';
        var pnlCls = '';
        if (m && m.oos_pnl != null) { pnl = fmtPnl(m.oos_pnl) + ' €'; pnlCls = pnlClass(m.oos_pnl); }
        var gap = '—';
        if (m && m.gap_pct != null) gap = (m.gap_pct >= 0 ? '+' : '') + Math.round(m.gap_pct) + ' %';
        h += '<tr><td><b>#' + escHtml(s2) + '</b>' + (nm ? ' <span style="color:var(--c-text-dim)">' + escHtml(nm) + '</span>' : '') + '</td>' +
          '<td>' + pf + '</td><td>' + trs + '</td><td class="' + pnlCls + '">' + pnl + '</td><td>' + gap + '</td></tr>';
      }
      if (h) { tbody.innerHTML = h; stratsWrap.style.display = ''; }
      else { stratsWrap.style.display = 'none'; }
    });
  }

  // 3) Re-Opt-Status (fällig/überfällig aus last_date + interval)
  renderReoptimize();

  // 4) Lab-Tab ausblenden, wenn gar kein Inhalt existiert (keine leeren Tabs)
  var tabBtn = el(C.prefix + '-tabbtn-lab');
  var reoptCard = el(C.prefix + '-reopt-card');
  var stratsVisible = !!(stratsWrap && stratsWrap.style.display !== 'none');
  if (tabBtn && !reoptCard && !hasBench && !stratsVisible) {
    tabBtn.style.display = 'none';
    var pane = el(C.prefix + '-tab-lab');
    if (pane && pane.classList.contains('active')) switchTab(C.prefix, 'history');
  }
}

/* ═══════════════════════════════════════════════════════════
 *  RE-OPTIMIZATION STATUS
 * ═══════════════════════════════════════════════════════════ */

function renderReoptimize() {
  var lastEl = el(C.prefix + '-reopt-last');
  if (!lastEl) return; // no reoptimize section

  // Read last_date from the static HTML (set by build_bot_pages.py)
  var lastDateStr = lastEl.textContent.trim();
  if (!lastDateStr || lastDateStr === '—') return;

  // Parse config from the page's init script
  // We embedded the reoptimize config as a data attribute or in the HTML
  var dueEl = el(C.prefix + '-reopt-due');
  var statusEl = el(C.prefix + '-reopt-status');
  var iconEl = el(C.prefix + '-reopt-icon');
  var bannerEl = el(C.prefix + '-reopt-banner');
  if (!dueEl) return;

  // Read interval from the details summary text (fallback: 3)
  var cardEl = el(C.prefix + '-reopt-card');
  var intervalMonths = 3;
  if (cardEl) {
    var summaryText = cardEl.querySelector('summary');
    if (summaryText) {
      var m = summaryText.textContent.match(/(\d+)M\s*Daten/);
      // interval is not in the summary — use default 3
    }
  }

  // Try to read interval from a data attribute on the card
  if (cardEl && cardEl.dataset.interval) {
    intervalMonths = parseInt(cardEl.dataset.interval, 10) || 3;
  }

  // Parse last_date (YYYY-MM-DD)
  var parts = lastDateStr.split('-');
  if (parts.length !== 3) return;
  var lastDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  var now = new Date();

  // Calculate due date
  var dueDate = new Date(lastDate);
  dueDate.setMonth(dueDate.getMonth() + intervalMonths);

  // Format due date
  var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
  dueEl.textContent = pad(dueDate.getDate()) + '.' + pad(dueDate.getMonth() + 1) + '.' + dueDate.getFullYear();

  // Calculate days remaining
  var msPerDay = 86400000;
  var daysLeft = Math.ceil((dueDate.getTime() - now.getTime()) / msPerDay);

  // Status + styling
  var status, color, icon, bgColor;
  if (daysLeft > 14) {
    status = daysLeft + ' Tage verbleibend';
    color = '#22c55e';
    icon = '🟢';
    bgColor = 'rgba(34,197,94,0.1)';
  } else if (daysLeft > 0) {
    status = daysLeft + ' Tage — bald fällig!';
    color = '#eab308';
    icon = '🟡';
    bgColor = 'rgba(234,179,8,0.1)';
  } else if (daysLeft > -14) {
    status = 'Überfällig seit ' + Math.abs(daysLeft) + ' Tagen';
    color = '#f97316';
    icon = '🟠';
    bgColor = 'rgba(249,115,22,0.1)';
  } else {
    status = 'KRITISCH: ' + Math.abs(daysLeft) + ' Tage überfällig!';
    color = '#ef4444';
    icon = '🔴';
    bgColor = 'rgba(239,68,68,0.15)';
  }

  statusEl.textContent = status;
  statusEl.style.color = color;
  iconEl.textContent = icon;

  // Show banner if overdue or soon
  if (daysLeft <= 14 && bannerEl) {
    bannerEl.style.display = 'block';
    bannerEl.style.background = bgColor;
    bannerEl.style.border = '1px solid ' + color;
    bannerEl.innerHTML = daysLeft <= 0
      ? '<b>⚠️ Re-Optimierung überfällig!</b> Die Parameter könnten veraltet sein. Bitte Anleitung unten befolgen.'
      : '<b>⏰ Re-Optimierung bald fällig.</b> In ' + daysLeft + ' Tagen sollten die Parameter aktualisiert werden.';
  }
}

/* ═══════════════════════════════════════════════════════════
 *  TAB NAVIGATION
 * ═══════════════════════════════════════════════════════════ */

function switchTab(prefix, tabName) {
  var nav = el(prefix + '-nav-tabs');
  if (nav) {
    var btns = nav.querySelectorAll('.bot-tab-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.remove('active');
    }
  }
  // Find clicked button
  if (event && event.currentTarget) {
    event.currentTarget.classList.add('active');
  }

  // Panes
  var panes = ['history', 'lab'];
  for (var p = 0; p < panes.length; p++) {
    var pane = el(prefix + '-tab-' + panes[p]);
    if (pane) {
      if (panes[p] === tabName) {
        pane.classList.add('active');
      } else {
        pane.classList.remove('active');
      }
    }
  }
}

/* ═══════════════════════════════════════════════════════════
 *  DATA LOADING
 * ═══════════════════════════════════════════════════════════ */

function loadDashboard() {
  safeFetch(C.dashboardPath).then(function(r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function(d) {
    _lastDash = d;
    renderStatus(d);
    renderAction(d);
    renderAccounts(d);
    renderPositions(d);
    if (typeof _updateLiveChart === 'function') _updateLiveChart();
    renderDataAge(d);
    renderHistory(d);
    renderBoard(d);
    if (C.hasEquity) renderEquity(d);
    renderParity(C.prefix, d.parity);
    renderParityChip(d);
    if (C.hasSignals) renderSignals(d);
    renderLab(d);
    renderSlots(d);
    // Fire custom render callback if set
    if (typeof C.onData === 'function') C.onData(d);
  }).catch(function(e) {
    console.warn('Dashboard load failed:', e);
    var dot = el(C.prefix + '-dot');
    if (dot) dot.className = 'bot-status-dot red';
    var statusEl = el(C.prefix + '-status');
    if (statusEl) statusEl.textContent = 'Connection error';
  });
}

/* ═══════════════════════════════════════════════════════════
 *  INIT
 * ═══════════════════════════════════════════════════════════ */

function init(config) {
  for (var k in config) {
    if (config.hasOwnProperty(k)) C[k] = config[k];
  }
  loadDashboard();
  if (C.hasHeatmap) renderHeatmap();
  setInterval(loadDashboard, C.refreshInterval || 60000);
}

/* ═══════════════════════════════════════════════════════════
 *  COCKPIT (23.10.2026) — ein Template für alle Bots
 *  Reihenfolge: Kopf → Konten → Equity → Positionen → Historie →
 *  Strategien → Details. Jedes Fakt genau eine Heimat; Langtexte
 *  (Beschreibung, Tech, OOS, Parität) nur im Details-Bereich.
 * ═══════════════════════════════════════════════════════════ */

var _eqView = null;          // 'indexed' | 'demo' | 'live' | 'single'
var _histFilter = 'all';     // 'all' | 'live' | 'demo'
var _histAll = false;

function _num(v, d) {
  if (v == null || isNaN(v)) return '—';
  return Number(v).toLocaleString('de-DE', {
    minimumFractionDigits: d == null ? 2 : d,
    maximumFractionDigits: d == null ? 2 : d
  });
}
function _eur(v, sign) {
  if (v == null || isNaN(v)) return '—';
  if (Math.abs(Number(v)) < 0.005) v = 0;
  var s = _num(v, 2) + ' €';
  return (sign && Number(v) > 0) ? '+' + s : s;
}
function _pct(v, sign) {
  if (v == null || isNaN(v)) return '—';
  if (Math.abs(Number(v)) < 0.05) v = 0;
  var s = _num(v, 1) + ' %';
  return (sign && Number(v) > 0) ? '+' + s : s;
}
function _shortDate(iso) {
  if (!iso) return '';
  try {
    var s = String(iso);
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
    return new Date(s).toLocaleDateString('de-DE', {
      day: '2-digit', month: '2-digit', timeZone: 'Europe/Berlin'
    });
  } catch (e) { return ''; }
}
function _tsMs(iso) {
  if (!iso) return null;
  try {
    var s = String(iso);
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
    var t = new Date(s).getTime();
    return isNaN(t) ? null : t;
  } catch (e) { return null; }
}
function _ptVal(p) {
  if (!p) return null;
  if (p.equity != null) return Number(p.equity);
  if (p.balance != null) return Number(p.balance);
  if (p.value != null) return Number(p.value);
  return null;
}

/** Normalisierte Kontenliste: default + Zusatzkonten, inkl. Kurvenpunkte. */
function _accounts(d) {
  var list = Array.isArray(d.accounts) ? d.accounts.slice() : [];
  var curves = d.curves || [];
  if (!list.length) {
    var acc = d.account || d.live_balance || {};
    list.push({
      ctid: String((acc && acc.ctid) || d.account_id || ''),
      is_live: d.mode === 'live',
      label: d.mode === 'live' ? 'Echtgeld' : 'Demo',
      balance: acc.balance, equity: acc.equity, is_default: true, flows: null
    });
    var cards0 = d.account_cards || [];
    for (var c0 = 0; c0 < cards0.length; c0++) {
      var cc0 = cards0[c0] || {};
      list.push({
        ctid: String(cc0.ctid != null ? cc0.ctid : ''), is_live: cc0.is_live !== false,
        label: cc0.label || (cc0.is_live !== false ? 'Echtgeld' : 'Demo'),
        balance: cc0.balance, equity: cc0.equity, is_default: false, flows: null
      });
    }
  }
  var eh = d.equity_history;
  if (eh && eh.snapshots) eh = eh.snapshots;
  for (var i = 0; i < list.length; i++) {
    var a = list[i];
    var pts = [];
    if (a.is_default) {
      pts = Array.isArray(eh) ? eh : [];
    } else {
      for (var k = 0; k < curves.length; k++) {
        if (String(curves[k].ctid) === String(a.ctid)) pts = curves[k].points || [];
      }
    }
    a.points = Array.isArray(pts) ? pts : [];
    a.flow = a.flows || null;
  }
  list.sort(function (x, y) {
    if (!!x.is_live !== !!y.is_live) return x.is_live ? -1 : 1;
    if (!!x.is_default !== !!y.is_default) return x.is_default ? -1 : 1;
    return String(x.ctid).localeCompare(String(y.ctid));
  });
  return list;
}

/** Inline-Sparkline (SVG, keine Chart-Instanz). */
var _sparkSeq = 0;
function _spark(vals, color, w, h) {
  w = w || 160; h = h || 34;
  var v = (vals || []).filter(function (x) { return x != null && !isNaN(x); });
  if (v.length < 2) return '';
  var lo = Math.min.apply(null, v), hi = Math.max.apply(null, v);
  var rng = (hi - lo) || 1;
  var step = (w - 4) / (v.length - 1);
  var pts = [];
  for (var i = 0; i < v.length; i++) {
    pts.push((2 + i * step).toFixed(1) + ',' + (h - 3 - (v[i] - lo) / rng * (h - 8)).toFixed(1));
  }
  var d = 'M' + pts.join(' L');
  var gid = 'spk' + (++_sparkSeq);
  return '<svg class="cp-spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' +
    '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
    '<stop offset="0" stop-color="' + color + '" stop-opacity=".26"/>' +
    '<stop offset="1" stop-color="' + color + '" stop-opacity="0"/></linearGradient></defs>' +
    '<path d="' + d + ' L' + (w - 2) + ',' + h + ' L2,' + h + ' Z" fill="url(#' + gid + ')"/>' +
    '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>';
}

/** Tages-Delta (Berlin-Mitternacht) aus einer Punktliste. */
function _dayDelta(pts) {
  if (!pts || !pts.length) return null;
  var last = null;
  for (var i = pts.length - 1; i >= 0; i--) {
    var v = _ptVal(pts[i]);
    if (v != null) { last = v; break; }
  }
  if (last == null) return null;
  var mid = new Date();
  mid.setHours(0, 0, 0, 0);
  // Berliner Mitternacht als UTC-Instant
  var berlinMid = new Date(mid.toLocaleString('en-US', { timeZone: 'Europe/Berlin' }));
  var cut = new Date(mid.getTime() - (berlinMid.getTime() - mid.getTime())).getTime();
  var prev = null;
  for (var j = 0; j < pts.length; j++) {
    var t = _tsMs(pts[j].timestamp || pts[j].date);
    var val = _ptVal(pts[j]);
    if (t != null && t < cut && val != null) prev = val;
  }
  return prev == null ? null : last - prev;
}

/** Kontokarten (Echtgeld + Demo) mit Sparkline und Kapitalbewegungen. */
function renderAccounts(d) {
  var box = el(C.prefix + '-accounts');
  if (!box) return;
  var accts = _accounts(d);
  if (!accts.length) { box.innerHTML = ''; return; }
  var html = '';
  for (var i = 0; i < accts.length; i++) {
    var a = accts[i];
    var live = !!a.is_live;
    var col = live ? '#f0b940' : '#5b8def';
    var bal = a.balance;
    if (bal == null) {
      for (var p = a.points.length - 1; p >= 0; p--) {
        var pv = _ptVal(a.points[p]);
        if (pv != null) { bal = pv; break; }
      }
    }
    var vals = [];
    for (var q = 0; q < a.points.length; q++) vals.push(_ptVal(a.points[q]));
    var day = _dayDelta(a.points);
    var first = null, last = null;
    for (var f = 0; f < vals.length; f++) { if (vals[f] != null) { first = vals[f]; break; } }
    for (var l = vals.length - 1; l >= 0; l--) { if (vals[l] != null) { last = vals[l]; break; } }
    var since = (first && last) ? (last / first - 1) * 100 : null;
    var sinceDate = a.points.length ? _shortDate(a.points[0].timestamp || a.points[0].date) : null;
    var flowLine = '';
    if (live && a.flow && a.flow.n_moves) {
      var parts = [];
      if (a.flow.einzahlungen_eur) parts.push('Einz. ' + _eur(a.flow.einzahlungen_eur));
      if (a.flow.auszahlungen_eur) parts.push('Ausz. ' + _eur(a.flow.auszahlungen_eur));
      if (a.flow.transfers_eur) parts.push('Transfers ' + _eur(a.flow.transfers_eur));
      flowLine = '<div class="cp-acct-flow" title="Kapitalbewegungen seit Konto-Start">' +
        parts.join(' · ') + ' · Netto ' + _eur(a.flow.netto_eur) + '</div>';
    }
    html += '<div class="cp-acct ' + (live ? 'live' : 'demo') + '">' +
      '<div class="cp-acct-top"><span>' + (live ? '💰 ECHTGELD' : '🧪 DEMO') + '</span>' +
      '<span class="cp-acct-id">' + escHtml(a.ctid || '—') + '</span></div>' +
      '<div class="cp-acct-bal">' + _eur(bal) + '</div>' +
      '<div class="cp-acct-row"><span>Equity ' + _eur(a.equity != null ? a.equity : bal) + '</span>' +
      '<span class="' + (day == null ? 'muted' : (day >= 0 ? 'up' : 'down')) + '">' +
      (day == null ? '—' : _eur(day, true)) + ' heute</span></div>' +
      '<div class="cp-acct-spark">' + _spark(vals.slice(-260), col) + '</div>' +
      '<div class="cp-acct-foot"><span>' + (sinceDate ? 'seit ' + sinceDate + ' · ' + _pct(since, true) : '—') +
      '</span><span class="muted">' + a.points.length + ' Punkte</span></div>' +
      flowLine + '</div>';
  }
  box.innerHTML = html;
  box.className = 'cp-accts' + (accts.length === 1 ? ' single' : '');
}

/** Kopf-Aktion: was ist gerade zu tun (eine Zeile, keine Wiederholung). */
function renderAction(d) {
  var box = el(C.prefix + '-action');
  if (!box) return;
  var slots = d.slots || [];
  var paused = !!(d.paused || (d.status && d.status.paused));
  var blocked = [], ready = [], running = [];
  for (var i = 0; i < slots.length; i++) {
    var s = slots[i];
    if (s.kind === 'planned') continue;
    if (s.stage === 'live' && s.armed === false) blocked.push(s);
    var ch = s.challenge || null;
    if (ch) {
      if (ch.ready && s.stage !== 'live') ready.push(s);
      else running.push(s);
    }
  }
  var cls = 'cp-action ok', txt = '✓ keine Aktion nötig';
  if (paused) { cls = 'cp-action muted'; txt = '⏸ GEPARKT'; }
  else if (blocked.length) {
    cls = 'cp-action warn';
    txt = '🔒 OK nötig: ' + blocked[0].slot_id + (blocked.length > 1 ? ' +' + (blocked.length - 1) : '');
  } else if (ready.length) {
    cls = 'cp-action warn';
    txt = '⚡ bereit: ' + ready[0].slot_id;
  } else if (running.length) {
    cls = 'cp-action';
    txt = '⏳ Automatik läuft · ' + running.length + ' Challenge' + (running.length > 1 ? 's' : '');
  }
  box.className = cls;
  box.textContent = txt;
}

/** Paritäts-Chip im Kopf: nur wenn es JETZT etwas zu tun gibt. */
function renderParityChip(d) {
  var chip = el(C.prefix + '-parity-chip');
  if (!chip) return;
  var p = d.parity || {};
  if (!p || p.status === 'kein_bot' || p.status === 'fehler' || !p.assets) {
    chip.style.display = 'none';
    return;
  }
  var cats = p.diagnosis_cats || [];
  var structural = false;
  for (var c = 0; c < cats.length; c++) {
    if (cats[c] === 'sl_drift' || cats[c] === 'tp_drift' ||
        cats[c] === 'risk_scaling' || cats[c] === 'entry_mismatch') structural = true;
  }
  var now = Date.now() / 1000, recent = 0;
  for (var sym in p.assets) {
    var ms = p.assets[sym].missed_shadow || [];
    for (var m = 0; m < ms.length; m++) {
      var row = ms[m] || {};
      if (!row.excused && row.ts && (now - row.ts) < 3 * 86400) recent++;
    }
  }
  if (structural) {
    chip.style.display = '';
    chip.className = 'cp-parity-chip red';
    chip.textContent = '🛡 Parität: Struktur-Abweichung';
    chip.title = (p.diagnosis || '');
  } else if (recent > 0) {
    chip.style.display = '';
    chip.className = 'cp-parity-chip warn';
    chip.textContent = '🛡 ' + recent + ' Shadow-Trade' + (recent > 1 ? 's' : '') + ' offen';
    chip.title = 'Shadow handelte, Bot nicht — Details unter Details → Shadow-Parität';
  } else {
    chip.style.display = 'none';
  }
}

/** Equity-Chart: indexiert (beide Konten) oder ein Konto absolut. */
function renderEquity(d) {
  var canvas = el(C.prefix + '-equity-chart');
  if (!canvas) return;
  var accts = _accounts(d).filter(function (a) { return a.points && a.points.length > 1; });
  if (!accts.length) return;
  var mixed = accts.length > 1;
  var hasDemo = accts.some(function (a) { return !a.is_live; });
  var hasLive = accts.some(function (a) { return a.is_live; });
  if (!_eqView || (_eqView !== 'indexed' && _eqView !== 'demo' && _eqView !== 'live')) {
    _eqView = mixed ? 'indexed' : (accts[0].is_live ? 'live' : 'demo');
  }
  if (_eqView === 'demo' && !hasDemo) _eqView = mixed ? 'indexed' : 'live';
  if (_eqView === 'live' && !hasLive) _eqView = mixed ? 'indexed' : 'demo';

  // Segmented control
  var seg = el(C.prefix + '-eq-seg');
  if (seg) {
    var sh = '';
    if (mixed) {
      sh += '<button class="' + (_eqView === 'indexed' ? 'on' : '') + '" onclick="BotDash.setEquityView(\'indexed\')">Indexiert</button>';
      if (hasDemo) sh += '<button class="' + (_eqView === 'demo' ? 'on' : '') + '" onclick="BotDash.setEquityView(\'demo\')">🧪 Demo</button>';
      if (hasLive) sh += '<button class="' + (_eqView === 'live' ? 'on' : '') + '" onclick="BotDash.setEquityView(\'live\')">💰 Echtgeld</button>';
    }
    seg.innerHTML = sh;
    seg.style.display = mixed ? '' : 'none';
  }

  var view = _eqView;
  var series = [];
  if (view === 'indexed') {
    for (var i = 0; i < accts.length; i++) {
      var a = accts[i], vals = [], base = null;
      for (var j = 0; j < a.points.length; j++) {
        var v = _ptVal(a.points[j]);
        if (v == null) continue;
        if (base == null) base = v || 1;
        vals.push({ t: a.points[j].timestamp || a.points[j].date, v: v / base * 100 });
      }
      series.push({ a: a, vals: vals });
    }
  } else {
    var wantLive = view === 'live';
    var pick = accts.filter(function (x) { return !!x.is_live === wantLive; })[0] || accts[0];
    var vv = [];
    for (var k = 0; k < pick.points.length; k++) {
      var pv = _ptVal(pick.points[k]);
      if (pv != null) vv.push({ t: pick.points[k].timestamp || pick.points[k].date, v: pv });
    }
    series.push({ a: pick, vals: vv });
  }

  // Union-Labels (ISO-Strings sortieren) + Werte zuordnen; Lücken bleiben null.
  var labels;
  if (series.length > 1) {
    var set = {};
    for (var s1 = 0; s1 < series.length; s1++) {
      for (var s2 = 0; s2 < series[s1].vals.length; s2++) set[series[s1].vals[s2].t] = true;
    }
    labels = Object.keys(set).sort();
  } else {
    labels = series[0].vals.map(function (x) { return x.t; });
  }
  var idxOf = {};
  for (var li = 0; li < labels.length; li++) idxOf[labels[li]] = li;

  var datasets = [];
  for (var si = 0; si < series.length; si++) {
    var sr = series[si];
    var data = labels.map(function () { return null; });
    for (var vi = 0; vi < sr.vals.length; vi++) {
      var ix = idxOf[sr.vals[vi].t];
      if (ix !== undefined) data[ix] = sr.vals[vi].v;
    }
    var isLive = !!sr.a.is_live;
    datasets.push({
      label: (isLive ? '💰 Echtgeld' : '🧪 Demo') + (sr.a.ctid ? ' ' + sr.a.ctid : ''),
      data: data,
      borderColor: isLive ? '#f0b940' : '#5b8def',
      backgroundColor: isLive ? 'rgba(240,185,64,0.08)' : 'rgba(91,141,239,0.08)',
      fill: series.length === 1,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2,
      spanGaps: true
    });
  }

  // Marker (Arming/Era) aus d.markers + curves[].markers
  var markers = [];
  function addMarkers(list) {
    if (!Array.isArray(list)) return;
    for (var mi = 0; mi < list.length; mi++) {
      var mm = list[mi] || {};
      var mts = mm.ts || mm.timestamp || '';
      if (!mts) continue;
      var at = -1;
      for (var lj = 0; lj < labels.length; lj++) {
        if (String(labels[lj]) >= String(mts)) { at = lj; break; }
      }
      if (at >= 0) markers.push({ idx: at, label: mm.label || '' });
    }
  }
  addMarkers(d.markers);
  var curvesM = d.curves || [];
  for (var cm = 0; cm < curvesM.length; cm++) addMarkers(curvesM[cm].markers);
  var markerPlugin = {
    id: 'cpMarkers',
    afterDatasetsDraw: function (chart) {
      if (!markers.length) return;
      var ctx = chart.ctx, xa = chart.scales && chart.scales.x, ya = chart.scales && chart.scales.y;
      if (!ctx || !xa || !ya) return;
      ctx.save();
      for (var i2 = 0; i2 < markers.length; i2++) {
        var x = xa.getPixelForValue(markers[i2].idx);
        if (x == null || isNaN(x)) continue;
        ctx.beginPath(); ctx.setLineDash([4, 3]);
        ctx.strokeStyle = 'rgba(156,163,175,0.8)'; ctx.lineWidth = 1;
        ctx.moveTo(x, ya.top); ctx.lineTo(x, ya.bottom); ctx.stroke();
        ctx.setLineDash([]);
        if (markers[i2].label) {
          ctx.fillStyle = '#9ca3af'; ctx.font = '10px sans-serif'; ctx.textAlign = 'left';
          ctx.fillText(markers[i2].label, x + 3, ya.top + 10);
        }
      }
      ctx.restore();
    }
  };

  if (_chartInstances.equity) _chartInstances.equity.destroy();
  _chartInstances.equity = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    plugins: [markerPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: datasets.length > 1,
          position: 'top',
          labels: { boxWidth: 10, boxHeight: 10, color: '#9ca3af', font: { size: 10 } }
        },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var v = ctx.parsed.y;
              return ctx.dataset.label + ': ' + (v == null ? '—' : _num(v, 1) + (view === 'indexed' ? '' : ' €'));
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: '#7d7899', font: { size: 10 }, maxTicksLimit: 8, maxRotation: 0,
            callback: function (val) {
              var l = this.getLabelForValue(val);
              return _shortDate(l);
            }
          }
        },
        y: {
          grid: { color: 'rgba(42,37,69,0.7)' },
          ticks: {
            color: '#7d7899', font: { size: 10 },
            callback: function (v) { return view === 'indexed' ? _num(v, 0) : _num(v, 0) + ' €'; }
          }
        }
      }
    }
  });

  // Fußzeile: Start/aktuell je Serie
  var foot = el(C.prefix + '-equity-summary');
  if (foot) {
    var bits = [];
    for (var f2 = 0; f2 < series.length; f2++) {
      var sr2 = series[f2], vv2 = sr2.vals;
      if (!vv2.length) continue;
      var firstV = vv2[0].v, lastV = vv2[vv2.length - 1].v;
      var chg = view === 'indexed' ? (lastV - 100) : (lastV - firstV);
      bits.push((sr2.a.is_live ? '💰 Echtgeld' : '🧪 Demo') +
        (sr2.a.ctid ? ' ' + sr2.a.ctid : '') + ': ' +
        (view === 'indexed'
          ? _pct(chg, true) + ' seit ' + _shortDate(vv2[0].t)
          : _eur(lastV) + ' (' + _eur(chg, true) + ' seit ' + _shortDate(vv2[0].t) + ')'));
    }
    foot.innerHTML = bits.join(' &nbsp;·&nbsp; ') +
      (view === 'indexed' ? ' &nbsp;·&nbsp; <span class="muted">Kontostart = 100</span>' : '');
  }
}

/** Historie: Filter, 12 Zeilen, „alle anzeigen". */
function renderHistory(d) {
  var tbody = el(C.prefix + '-history-body');
  if (!tbody) return;
  var all = (d.trade_history || d.round_trips || d.last_trades || []).slice();
  all.sort(function (a, b) {
    var ta = a.closed_at || a.timestamp || '';
    var tb = b.closed_at || b.timestamp || '';
    return String(tb).localeCompare(String(ta));
  });

  var nAll = all.length, nLive = 0, nDemo = 0;
  for (var i0 = 0; i0 < all.length; i0++) {
    if (all[i0].live === true) nLive++;
    else if (all[i0].live === false) nDemo++;
  }
  var fbox = el(C.prefix + '-hist-filter');
  if (fbox) {
    fbox.innerHTML =
      '<button class="' + (_histFilter === 'all' ? 'on' : '') + '" onclick="BotDash.setHistoryFilter(\'all\')">Alle ' + nAll + '</button>' +
      (nLive ? '<button class="' + (_histFilter === 'live' ? 'on' : '') + '" onclick="BotDash.setHistoryFilter(\'live\')">💰 ' + nLive + '</button>' : '') +
      (nDemo ? '<button class="' + (_histFilter === 'demo' ? 'on' : '') + '" onclick="BotDash.setHistoryFilter(\'demo\')">🧪 ' + nDemo + '</button>' : '');
  }

  var trades = all.filter(function (t) {
    if (_histFilter === 'live') return t.live === true;
    if (_histFilter === 'demo') return t.live === false;
    return true;
  });

  var hc = el(C.prefix + '-hist-count');
  if (hc) {
    var perf = d.performance || {};
    var pf = (perf.total_trades && perf.profit_factor != null) ? _num(perf.profit_factor, 2) : '—';
    var wr = (perf.total_trades && perf.win_rate != null) ? _num(perf.win_rate, 1) + ' %' : '—';
    var totalAll = perf.total_trades || nAll;
    hc.textContent = perf.total_trades
      ? totalAll + ' Trades · PF ' + pf + ' · WR ' + wr +
        (nAll < totalAll ? ' · ' + nAll + ' geladen' : '')
      : (nAll ? nAll + ' Trades · Testpfad (keine Strategie-Statistik)' : '');
  }

  var htbl = el(C.prefix + '-history-table');
  if (htbl && htbl.classList) {
    var hasExit = false;
    for (var x = 0; x < trades.length; x++) {
      if (trades[x].close_price || trades[x].exit_price || trades[x].current_price) { hasExit = true; break; }
    }
    if (hasExit) htbl.classList.remove('no-exit'); else htbl.classList.add('no-exit');
  }

  if (!trades.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="bot-no-data">' +
      (_histFilter === 'all' ? 'Noch keine Trades' : 'Keine Trades in dieser Auswahl') + '</td></tr>';
    var m0 = el(C.prefix + '-hist-more'); if (m0) m0.innerHTML = '';
    return;
  }

  var limit = _histAll ? trades.length : Math.min(trades.length, 10);
  var html = '';
  _focusStore.hist = {};
  for (var i = 0; i < limit; i++) {
    var t = trades[i];
    var dir = (t.direction || t.side || '').toLowerCase();
    var isShort = (dir === 'sell' || dir === 'short');
    var pnl = t.pnl != null ? t.pnl : (t.realized_pnl || t.profit || 0);
    var dur = t.duration || (t.duration_hours != null ? _num(t.duration_hours, 1) + 'h' : '—');
    var sym = t.symbol || t.pair || '—';
    var sid = t.strategy_id;
    var slot = (t.slot_id != null && t.slot_id !== '') ? t.slot_id : '';
    var badge = _liveBadge(t);
    var name = sid ? ('<b>#' + escHtml(sid) + '</b>' + (slot ? ' <span class="cp-slotmini">' + escHtml(slot) + '</span>' : ''))
                   : '<span class="muted">' + escHtml(t.strategy || 'Testpfad') + '</span>';
    var fkH = _putFocus('hist', _focusFromTrade(d, t));
    html += '<tr class="bot-pos-row" title="Kerzenchart mit SL/TP und Dauer öffnen" onclick="BotDash.openTradeChart(\'' + escHtml(sym) + '\',\'' + fkH + '\')">' +
      '<td class="cp-strat">' + (badge ? badge + ' ' : '') + name + '</td>' +
      '<td>' + fmtTime(t.closed_at || t.timestamp) + '</td>' +
      '<td><b>' + escHtml(sym) + '</b></td>' +
      '<td>' + (isShort ? '<span class="bot-badge bot-badge-sell">SHORT</span>' : '<span class="bot-badge bot-badge-buy">LONG</span>') + '</td>' +
      '<td class="num">' + fmtPrice(t.entry_price || t.open_price || t.entry, sym) + '</td>' +
      '<td class="num">' + fmtPrice(t.close_price || t.exit_price || t.current_price, sym) + '</td>' +
      '<td class="num ' + pnlClass(pnl) + '"><b>' + fmtPnl(pnl) + '</b></td>' +
      '<td>' + dur + '</td>' +
      '<td class="muted">' + fmtCloseReason(t.status, t.close_reason) + '</td>' +
      '</tr>';
  }
  tbody.innerHTML = html;

  var more = el(C.prefix + '-hist-more');
  if (more) {
    more.innerHTML = trades.length > 10
      ? '<button class="cp-more-btn" onclick="BotDash.toggleHistoryAll()">' +
        (_histAll ? '▴ weniger anzeigen' : '▸ alle ' + trades.length + ' anzeigen') + '</button>'
      : '<span class="muted">' + trades.length + ' Trades</span>';
  }
}

/** Account-Scope je Slot: Live-Slot ≠ Demo-Ära. */
function _slotStats(s) {
  var st = s.stats || {};
  var by = st.by_account || {};
  var key = s.account_id != null ? String(s.account_id) : '';
  if (key && by[key]) return by[key];
  if (key && Object.keys(by).length) {
    return { trades: 0, closed: 0, wins: 0, net_eur: null, win_rate: null,
             pnl_7d: null, pnl_30d: null, _empty: true };
  }
  return st;
}
function _slotOther(s) {
  var by = (s.stats || {}).by_account || {};
  var key = s.account_id != null ? String(s.account_id) : '';
  for (var k in by) if (k !== key) return { ctid: k, st: by[k] };
  return null;
}
function _slotCurve(d, s) {
  var rows = (d.last_trades || []).filter(function (t) {
    if (String(t.slot_id) !== String(s.slot_id)) return false;
    if (s.account_id != null && t.account_id != null &&
        String(t.account_id) !== String(s.account_id)) return false;
    return true;
  });
  if (rows.length < 2) return [];
  rows.sort(function (a, b) {
    return String(a.closed_at || a.timestamp).localeCompare(String(b.closed_at || b.timestamp));
  });
  var cum = 0, out = [];
  for (var i = 0; i < rows.length; i++) {
    cum += Number(rows[i].pnl || 0);
    out.push(cum);
  }
  return out;
}
function _slotSince(d, s) {
  var rows = (d.last_trades || []).filter(function (t) {
    if (String(t.slot_id) !== String(s.slot_id)) return false;
    if (s.account_id != null && t.account_id != null &&
        String(t.account_id) !== String(s.account_id)) return false;
    return true;
  });
  if (rows.length) {
    rows.sort(function (a, b) {
      return String(a.closed_at || a.timestamp).localeCompare(String(b.closed_at || b.timestamp));
    });
    return _shortDate(rows[0].closed_at || rows[0].timestamp);
  }
  return s.since ? _shortDate(s.since) : '—';
}

function _stagePill(s) {
  if (s.stage === 'live') {
    return '<span class="cp-pill gold">💰 LIVE' + (s.armed === false ? ' · OK nötig' : '') + '</span>';
  }
  if (s.stage === 'demo') return '<span class="cp-pill blue">🧪 DEMO</span>';
  if (s.kind === 'planned') return '<span class="cp-pill dim">GEPLANT</span>';
  return '<span class="cp-pill gray">🔵 SHADOW</span>';
}

function _spById(sp, id) {
  if (!sp || !sp.strategies) return null;
  for (var i = 0; i < sp.strategies.length; i++) {
    if (String(sp.strategies[i].id) === String(id)) return sp.strategies[i];
  }
  return null;
}

/** Strategie-Board: Belegung, Zeilen, 30-Tage-Balken. */
function renderBoard(d) {
  var box = el(C.prefix + '-board');
  if (!box) return;
  var slots = d.slots || [];
  if (!slots.length) {
    box.innerHTML = '<div class="cp-empty">Keine Slot-Konfiguration — ' +
      'dieser Bot hat noch keine Strategie- oder Rotationsplätze.</div>';
    var oc0 = el(C.prefix + '-board-occ'); if (oc0) oc0.innerHTML = '';
    var bb0 = el(C.prefix + '-board-bars'); if (bb0) bb0.innerHTML = '';
    var sub0 = el(C.prefix + '-board-sub'); if (sub0) sub0.textContent = '';
    return;
  }
  _loadShadowPortfolio(function (sp) { _renderBoardInner(d, sp); });
}

function _renderBoardInner(d, sp) {
  var box = el(C.prefix + '-board');
  if (!box) return;
  var slots = d.slots || [];
  var filled = [], doors = [], planned = [];
  for (var i = 0; i < slots.length; i++) {
    if (slots[i].kind === 'strategy') filled.push(slots[i]);
    else if (slots[i].kind === 'rotation') doors.push(slots[i]);
    else if (slots[i].kind === 'planned') planned.push(slots[i]);
  }
  var target = Math.max(d.slots_target || 0, slots.length);

  var sub = el(C.prefix + '-board-sub');
  if (sub) sub.textContent = filled.length + '/' + target + ' belegt';

  // Belegung
  var occ = el(C.prefix + '-board-occ');
  if (occ) {
    var oh = '';
    for (var o = 0; o < slots.length; o++) {
      var s0 = slots[o], cls = 'plan';
      if (s0.stage === 'live') cls = 'live';
      else if (s0.stage === 'demo') cls = 'demo';
      else if (s0.kind === 'rotation') cls = 'door';
      oh += '<i class="' + cls + '" title="' + escHtml(s0.slot_id) + ' · ' +
        escHtml(s0.kind) + '"></i>';
    }
    for (var t2 = slots.length; t2 < target; t2++) oh += '<i class="plan"></i>';
    occ.innerHTML = oh;
  }

  var html = '';
  for (var f = 0; f < filled.length; f++) {
    var s = filled[f];
    var meta = _spById(sp, s.strategy_id) || {};
    var desc = meta.desc || {};
    var st = _slotStats(s);
    var hasStats = !st._empty && (st.closed || 0) > 0;
    var p30 = hasStats ? st.pnl_30d : null;
    var wr = hasStats ? st.win_rate : null;
    var other = s.stage === 'live' ? _slotOther(s) : null;
    var era = '';
    if (other && other.st && (other.st.closed || 0) > 0) {
      era = '<span class="cp-era" title="Evidenz aus der Demo-Ära — zählt nicht als Live-Performance">Demo-Ära ' +
        _eur(other.st.net_eur, true) + '</span>';
    }
    var nm = meta.name ? String(meta.name).replace(/^RCP-CLUSTER:\s*/, '')
      .replace(/\s*\(\d{8}_\d{6}\)\s*$/, '') : ('#' + s.strategy_id);
    var chal = s.challenge || null;
    var stat = '';
    if (chal) {
      stat = (chal.ready ? '✅ bereit' : 'Challenge ' + (chal.trades || 0) + '/3') +
        (chal.days_left != null ? ' · ' + chal.days_left + ' T' : '');
    } else if (hasStats) {
      stat = (s.stage === 'live' ? 'Live seit ' : 'seit ') + _slotSince(d, s);
    } else if (s.stage === 'live') {
      stat = 'noch keine Live-Trades';
    } else if (s.stage === 'demo') {
      stat = 'noch keine Trades';
    }
    html += '<div class="cp-srow">' +
      '<div class="cp-slot">' + escHtml(s.slot_id) + '</div>' +
      '<div class="cp-sname"><b>#' + escHtml(s.strategy_id) + ' ' + escHtml(nm) + '</b>' +
      '<span>' + escHtml(desc.tag || '') + '</span>' + era + '</div>' +
      '<div>' + _stagePill(s) + '</div>' +
      '<div class="cp-snum ' + (p30 == null ? 'muted' : (p30 >= 0 ? 'up' : 'down')) + '">' +
      (p30 == null ? '—' : _eur(p30, true)) + '<span>30 T · ' +
      (s.stage === 'live' ? 'Live' : 'Demo') + '-Konto</span></div>' +
      '<div class="cp-snum">' + (wr == null ? '—' : _num(wr, 1) + ' %') +
      '<span>WR · ' + (st.closed || 0) + ' Trades</span></div>' +
      '<div class="cp-sspark">' + (_spark(_slotCurve(d, s), s.stage === 'live' ? '#f0b940' : '#5b8def', 120, 26) ||
        '<span class="muted">—</span>') + '</div>' +
      '<div class="cp-sstat">' + stat + '</div>' +
      '</div>';
  }

  for (var dr = 0; dr < doors.length; dr++) {
    var sd = doors[dr], ch = sd.challenge || {};
    var cand = _spById(sp, ch.candidate) || {};
    var cnm = cand.name ? String(cand.name).replace(/^RCP-CLUSTER:\s*/, '')
      .replace(/\s*\(\d{8}_\d{6}\)\s*$/, '') : ('#' + (ch.candidate != null ? ch.candidate : '?'));
    var pct = Math.min(100, ((ch.trades || 0) / 3) * 100);
    html += '<div class="cp-srow door">' +
      '<div class="cp-slot">' + escHtml(sd.slot_id) + '</div>' +
      '<div class="cp-sname"><b>' + escHtml(cnm) + '</b><span>Tür · Kandidat im Shadow</span></div>' +
      '<div><span class="cp-pill gray">🔵 SHADOW</span></div>' +
      '<div class="cp-snum muted">—<span>kein Slot-PnL</span></div>' +
      '<div class="cp-snum">' + (ch.trades || 0) + '/3<span>Trades</span></div>' +
      '<div class="cp-sspark"><div class="cp-prog"><i style="width:' + pct.toFixed(0) + '%"></i></div></div>' +
      '<div class="cp-sstat">' + (ch.days_left != null ? ch.days_left + ' T Frist' : '—') + '</div>' +
      '</div>';
  }

  if (!filled.length) {
    html = '<div class="cp-empty">Noch keine Strategie deployt' +
      (doors.length ? ' — Kandidaten laufen im Shadow.' : '.') + '</div>' + html;
  }
  if (planned.length) {
    var ids = [];
    for (var pl = 0; pl < planned.length; pl++) ids.push(planned[pl].slot_id);
    html += '<div class="cp-planned"><b>' + planned.length + ' Reserve-Plätze</b> vorbereitet — ' +
      'scharf erst nach Kandidat-Verdikt (' + escHtml(ids.join(', ')) + ')</div>';
  }
  if (!filled.length && !doors.length && !planned.length) {
    html = '<div class="cp-empty">Noch keine Strategie deployt.</div>';
  }
  box.innerHTML = html;

  // 30-Tage-Balken (account-scoped!)
  var bars = el(C.prefix + '-board-bars');
  if (bars) {
    var vals = [], mx = 0;
    for (var b = 0; b < filled.length; b++) {
      var stb = _slotStats(filled[b]);
      if (stb._empty || (stb.closed || 0) === 0 || stb.pnl_30d == null) continue;
      vals.push([filled[b].slot_id, Number(stb.pnl_30d)]);
      if (Math.abs(Number(stb.pnl_30d)) > mx) mx = Math.abs(Number(stb.pnl_30d));
    }
    if (vals.length) {
      var bh = '<div class="cp-bars-head">Netto 30 Tage je Strategie</div>';
      for (var v2 = 0; v2 < vals.length; v2++) {
        var w = mx ? (Math.abs(vals[v2][1]) / mx * 46) : 0;
        var left = vals[v2][1] >= 0 ? 50 : 50 - w;
        bh += '<div class="cp-bar"><span class="cp-bl">' + escHtml(vals[v2][0]) + '</span>' +
          '<div class="cp-btrack"><i class="' + (vals[v2][1] >= 0 ? 'pos' : 'neg') +
          '" style="left:' + left.toFixed(1) + '%;width:' + w.toFixed(1) + '%"></i></div>' +
          '<span class="cp-bv ' + (vals[v2][1] >= 0 ? 'up' : 'down') + '">' +
          _eur(vals[v2][1], true) + '</span></div>';
      }
      bars.innerHTML = bh;
    } else {
      bars.innerHTML = '';
    }
  }
}

/* ═══════════════════════════════════════════════════════════
 *  PUBLIC API
 * ═══════════════════════════════════════════════════════════ */

var _lastDash = null;

function setEquityView(v) {
  _eqView = v;
  if (_lastDash) renderEquity(_lastDash);
}
function setHistoryFilter(f) {
  _histFilter = f;
  if (_lastDash) renderHistory(_lastDash);
}
function toggleHistoryAll() {
  _histAll = !_histAll;
  if (_lastDash) renderHistory(_lastDash);
}

window.BotDash = {
  init: init,
  loadDashboard: loadDashboard,
  setEquityView: setEquityView,
  setHistoryFilter: setHistoryFilter,
  toggleHistoryAll: toggleHistoryAll,
  switchTab: switchTab,
  toggleParityDetail: toggleParityDetail,
  openChart: openChart,
  openTradeChart: openTradeChart,
  clearFocus: clearFocus,
  setChartTF: setChartTF,
  toggleIndicators: toggleIndicators,
  closeChart: closeChart,
  setRange: setRange,
  toggleTradeLines: toggleTradeLines,
  renderHeatmap: renderHeatmap,
  fmtTime: fmtTime,
  fmtPnl: fmtPnl,
  fmtPrice: fmtPrice,
  fmtDuration: fmtDuration,
  pnlClass: pnlClass,
  safeFetch: safeFetch,
  config: C,
  // Expose renderers for bot-specific use
  renderStatus: renderStatus,
  renderAccounts: renderAccounts,
  renderAction: renderAction,
  renderBoard: renderBoard,
  renderKPIs: renderKPIs,
  renderPerformance: renderPerformance,
  renderPositions: renderPositions,
  renderHistory: renderHistory,
  renderSlots: renderSlots,
  renderSignals: renderSignals,
  renderEquity: renderEquity,
  renderLab: renderLab,
  // Harness/Debug: Account-Scope-Auflösung je Slot
  slotStats: _slotStats,
  // Harness: TF-Logik (Chart muss zur Strategie-TF passen)
  _tf: {
    seconds: _tfSeconds,
    label: _tfLabel,
    infer: _inferTF,
    options: _tfOptions,
    aggregate: _aggregateBars,
    defaultRange: _defaultRangeDays
  },
};

function renderParity(prefix, p) {
  var banner = el(prefix + '-parity-banner');
  if (!banner) return;
  var icon = el(prefix + '-parity-icon');
  var label = el(prefix + '-parity-label');
  var inline = el(prefix + '-parity-inline');
  var detail = el(prefix + '-parity-detail');
  banner.className = 'bot-parity-banner';

  var status = (p && p.status) || 'wartet';
  var assets = (p && p.assets) || {};
  var checkedAt = p && p.checked_at ? BotDash.fmtTime(p.checked_at) : '—';

  // Ampel
  if (status === 'bestaetigt') {
    banner.classList.add('ok');
    icon.textContent = '✅';
    label.textContent = 'SHADOW-PARITÄT: ÜBEREINSTIMMEND';
  } else if (status === 'abweichung') {
    banner.classList.add('error');
    icon.textContent = '🔴';
    label.textContent = 'SHADOW-PARITÄT: ABWEICHUNG';
  } else if (status === 'qualifizierung') {
    banner.classList.add('warn');
    icon.textContent = '🟡';
    label.textContent = 'QUALIFIZIERUNG LÄUFT';
  } else if (status === 'fehler' || status === 'kein_bot') {
    banner.classList.add('idle');
    icon.textContent = '⚫';
    label.textContent = (status === 'kein_bot')
      ? 'Keine Paritätsprüfung — kein Deploy-Mapping für diesen Bot'
      : 'Parität nicht prüfbar';
  } else {
    banner.classList.add('idle');
    icon.textContent = '⚪';
    label.textContent = 'Wartet auf erste Trades';
  }

  // Inline-Asset-Übersicht — BESTÄTIGT/OFFEN statt „17/3" (das las sich wie
  // ein Bestehen, obwohl der Status rot war: 17 bestätigt von 3 nötigen).
  var minReq = (p && p.min_confirmed_per_asset) || 3;
  var parts = [];
  for (var sym in assets) {
    var a = assets[sym];
    var missAll = a.missed_shadow || [];
    var missOpen = 0;
    for (var mm2 = 0; mm2 < missAll.length; mm2++) {
      if (!(missAll[mm2] && missAll[mm2].excused)) missOpen++;
    }
    var mark = a.status === 'bestaetigt' ? '✔' : (a.status === 'abweichung' ? '✗' : '⏳');
    parts.push(mark + ' ' + sym + ' ' + a.confirmed_count + ' bestätigt' +
      (missOpen ? ' · ' + missOpen + ' offen' : '') +
      (missAll.length > missOpen ? ' · ' + (missAll.length - missOpen) + ' entsch.' : ''));
  }
  inline.textContent = parts.join(' · ') + '  (≥' + minReq + ' Trades/Asset)';

  // Missed-Shadow-Summe im Banner (2026-09-17, wie Fleet-Radar)
  var missedTotal = 0;
  for (var ms in assets) {
    var mArr = assets[ms].missed_shadow || [];
    missedTotal += mArr.length;
  }
  if (missedTotal > 0) {
    inline.textContent += ' · ⚠️ ' + missedTotal + ' Shadow ohne Bot';
  }

  // Detail-Tabelle
  if (detail) {
    var h = '<b>Shadow ↔ Bot Prüfung</b> — Stand: ' + checkedAt +
            ' · Fenster: ' + (p.recent_window_days || 30) + ' Tage';
    h += '<table><tr><th>Asset</th><th>Status</th><th>Bestätigt</th><th>Letzte Abweichung</th></tr>';
    for (var sym2 in assets) {
      var a2 = assets[sym2];
      var st2 = a2.status === 'bestaetigt' ? '✔ Bestätigt'
              : a2.status === 'abweichung' ? '✗ Abweichung'
              : a2.status === 'qualifizierung' ? '⏳ ' + a2.confirmed_count + '/' + minReq
              : '– keine Trades';
      var lastDev = '—';
      var pairs2 = a2.pairs || [];
      for (var i = 0; i < pairs2.length; i++) {
        if (!pairs2[i].ok) {
          var bits = [];
          if (pairs2[i].entry_ok === false) bits.push('Entry +' + pairs2[i].entry_diff_pips + 'p');
          if (pairs2[i].sl_ok === false) bits.push('SL +' + pairs2[i].sl_diff_pips + 'p');
          if (pairs2[i].tp_ok === false) bits.push('TP +' + pairs2[i].tp_diff_pips + 'p');
          if (pairs2[i].risk_ok === false) bits.push('Risk ×' + pairs2[i].risk_ratio);
          lastDev = bits.join(', ') || 'Exit-Mismatch';
        }
      }
      var missed2 = a2.missed_shadow || [];
      if (missed2.length) {
        lastDev = '⚠ ' + missed2.length + '× Shadow-Trade ohne Bot-Gegenstück (zuletzt ' +
          new Date(missed2[missed2.length - 1].ts * 1000).toLocaleDateString('de-DE') + ')';
      }
      h += '<tr><td><b>' + sym2 + '</b></td><td>' + st2 + '</td><td>' +
           a2.confirmed_count + '/' + minReq + '</td><td>' + lastDev + '</td></tr>';
    }
    h += '</table>';

    // Auto-Diagnose (Stufe 1, 2026-09-02)
    var dg = (p && p.diagnosis) || '';
    var dgCats = (p && p.diagnosis_cats) || [];
    if (dgCats.length) {
    var catLabels = {
      missed_trades: 'Verpasste Trades',
      sl_drift: 'SL-Drift',
      tp_drift: 'TP-Drift',
      risk_scaling: 'Risk-Skalierung',
      entry_mismatch: 'Entry-Fehler',
      exit_mismatch: 'Exit-Mismatch',
      single_outlier: 'Einzelausreisser'
    };
    var catTags = '';
    for (var ci = 0; ci < dgCats.length; ci++) {
      catTags += '<span style="display:inline-block;background:rgba(240,90,90,.15);color:#f0a0a0;' +
        'border-radius:10px;padding:1px 8px;margin:2px 4px 2px 0;font-size:.8em">' +
        (catLabels[dgCats[ci]] || dgCats[ci]) + '</span>';
    }
    h += '<div style="margin-top:var(--s-3)"><b>🔍 Auto-Diagnose:</b> ' + catTags +
         '<div style="color:var(--txt-dim,#9aa4b2);font-size:.92em;margin-top:4px">' + dg + '</div></div>';
    }

    // Ersetzte Strategien (Tagging)
    var rep = (p && p.replaced_strategies) || {};
    var repKeys = Object.keys(rep);
    if (repKeys.length) {
      h += '<div style="margin-top:var(--s-3)"><b>Frühere Strategien dieses Bots:</b><br>';
      for (var j = 0; j < repKeys.length; j++) {
        var r = rep[repKeys[j]];
        var badge = r.status === 'bestaetigt' ? '<span style="color:#22c55e">✔ Bestätigt</span>'
                  : r.status === 'abgeloest' ? '<span style="color:#f0b940">⏸ Ersetzt</span>'
                  : '○ ungeprüft';
        h += '#' + repKeys[j] + ': ' + badge + ' (' + r.matched + ' Paare, letzter Trade ' +
             (r.last_trade || '—') + ')<br>';
      }
      h += '</div>';
    }
    detail.innerHTML = h;
  }
}

function toggleParityDetail(prefix) {
  var d = el(prefix + '-parity-detail');
  if (d) d.style.display = (d.style.display === 'none') ? 'block' : 'none';
  var t = el(prefix + '-parity-toggle');
  if (t) t.textContent = (d && d.style.display === 'none') ? '▾' : '▴';
}

})();

/* ═══════════════════════════════════════════════════════════
 *  SHADOW-PARITÄT BADGE (2026-09-02, plakativ)
 * ═══════════════════════════════════════════════════════════ */
