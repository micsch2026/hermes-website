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
  hasBacktest: true,
};

var _chartInstances = {};
var _candleChart = null;
var _allTradeMarkers = [];
var _rsiChart = null;
var _currentPair = null;
var _allPairs = [];
var _showTradeLines = true;
var _currentRangeDays = 90;

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
  var mode = d.mode || (d.demo ? 'demo' : 'live');

  var dot = el(C.prefix + '-dot');
  if (dot) dot.className = dotClass(isActive);

  var statusEl = el(C.prefix + '-status');
  if (statusEl) statusEl.textContent = isActive
    ? (d.status && d.status.message || 'Bot active')
    : 'Bot inactive';

  var badge = el(C.prefix + '-mode-badge');
  if (badge) {
    badge.textContent = mode.toUpperCase();
    badge.className = 'bot-badge ' + (mode === 'live' ? 'bot-badge-live' : 'bot-badge-demo');
  }

  var upd = el(C.prefix + '-last-update');
  if (upd) upd.textContent = 'Updated: ' + fmtTime(d.timestamp || d.last_update);

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

  if (!isActive && !isMarketClosed) {
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
  var tradesToday = d.trades_today || 0;
  var ttEl = el(C.prefix + '-trades-today');
  if (ttEl) ttEl.textContent = tradesToday + ' trade' + (tradesToday === 1 ? '' : 's') + ' today';

  // Total P&L — realized + unrealized (the TRUE trading performance)
  var perf = d.performance || {};
  var realized = (d.realized_pnl != null ? d.realized_pnl : (perf.realized_pnl || 0));
  var unrealized = (d.unrealized_pnl != null ? d.unrealized_pnl : (perf.unrealized_pnl || perf.open_pnl || 0));
  var totalPnl = realized + unrealized;
  var totalEl = el(C.prefix + '-total-pnl');
  if (totalEl) {
    totalEl.textContent = fmtPnl(totalPnl) + ' EUR';
    totalEl.className = 'bot-card-value ' + pnlClass(totalPnl);
  }
  var wrSub = el(C.prefix + '-winrate-sub');
  if (wrSub) wrSub.textContent = (perf.total_trades || 0) + ' total trades';
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
  for (var i = 0; i < pos.length; i++) {
    var p = pos[i];
    var sym = p.symbol || p.pair || '—';
    html += '<tr class="bot-pos-row" onclick="BotDash.openChart(\'' + sym + '\')">';
    for (var c = 0; c < cols.length; c++) {
      var col = cols[c];
      var val = _resolveField(p, col.field || col.key);
      html += '<td>' + _fmtCell(val, col.fmt, p) + '</td>';
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
      return '<span class="' + pnlClass(val) + '"><b>' + fmtPnl(val) + '</b></span>';
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
    html += '<tr class="bot-pos-row" onclick="BotDash.openChart(\'' + sym + '\')">';
    html += '<td style="font-size:var(--text-xs);color:var(--c-text-dim)">' + stratId + '</td>';
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
    var stratId = t.strategy_id || '—';
    html += '<tr class="bot-pos-row" onclick="BotDash.openChart(\'' + sym + '\')">';
    html += '<td style="font-size:var(--text-xs);color:var(--c-text-dim)">' + stratId + '</td>';
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

/** Equity curve (Chart.js) */
function renderEquity(d) {
  var canvas = el(C.prefix + '-equity-chart');
  if (!canvas) return;
  var data = d.equity_history || d.balance_history || {};
  var snapshots = data.snapshots || data;
  if (!Array.isArray(snapshots) || snapshots.length === 0) return;

  var labels = [], values = [], drawdowns = [];
  var peak = 0;
  var minVal = Infinity, maxVal = -Infinity;
  for (var i = 0; i < snapshots.length; i++) {
    var s = snapshots[i];
    var val = s.equity || s.balance || s.value || 0;
    labels.push(s.timestamp || s.date || '');
    values.push(val);
    if (val > peak) peak = val;
    if (val < minVal) minVal = val;
    if (val > maxVal) maxVal = val;
    drawdowns.push(peak > 0 ? ((val - peak) / peak * 100) : 0);
  }

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

  if (_chartInstances.equity) _chartInstances.equity.destroy();
  _chartInstances.equity = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Equity',
          data: values,
          borderColor: '#5b8def',
          backgroundColor: 'rgba(91,141,239,0.08)',
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
          yAxisID: 'y',
        },
        {
          label: 'Drawdown %',
          data: drawdowns,
          borderColor: 'rgba(239,68,68,0.4)',
          backgroundColor: 'rgba(239,68,68,0.05)',
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 1,
          yAxisID: 'y1',
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, labels: { color: '#8b8b9e', font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              if (ctx.datasetIndex === 0) return ' €' + ctx.parsed.y.toFixed(2);
              return ' ' + ctx.parsed.y.toFixed(2) + '%';
            }
          }
        }
      },
      scales: {
        x: { display: true, ticks: { color: '#555', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { position: 'left', min: yMin, max: yMax, ticks: { color: '#5b8def', callback: function(v) { return '€' + v.toFixed(0); } }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y1: { position: 'right', ticks: { color: '#ef4444', callback: function(v) { return v.toFixed(0) + '%'; } }, grid: { drawOnChartArea: false } }
      }
    }
  });

  // Summary
  var summary = el(C.prefix + '-equity-summary');
  if (summary) {
    var first = values[0] || 0;
    var last = values[values.length - 1] || 0;
    var minDD = Math.min.apply(null, drawdowns);
    var tradeCount = (d.last_trades && d.last_trades.length) || 0;
    var note = tradeCount === 0 ? '<span style="color:var(--c-text-dim);margin-left:auto;font-style:italic">ℹ️ Startwert nach Deploy (noch keine Trades der aktuellen Strategie)</span>' : '';
    summary.innerHTML =
      '<span>Start: <b>€' + first.toFixed(2) + '</b></span>' +
      '<span>Current: <b>€' + last.toFixed(2) + '</b></span>' +
      '<span>P&L: <b class="' + pnlClass(last - first) + '">' + fmtPnl(last - first) + '</b></span>' +
      '<span>Max DD: <b class="bot-pnl-neg">' + minDD.toFixed(2) + '%</b></span>' +
      note;
  }
}

/* ═══════════════════════════════════════════════════════════
 *  CANDLESTICK CHART (LightweightCharts)
 * ═══════════════════════════════════════════════════════════ */

function openChart(pair) {
  var panel = el(C.prefix + '-chart-panel');
  if (!panel) return;
  panel.className = 'bot-chart-panel active';
  _currentPair = pair;

  // Highlight active signal card
  var cards = document.querySelectorAll('.bot-signal-card');
  for (var i = 0; i < cards.length; i++) {
    cards[i].classList.toggle('bot-active-card', cards[i].getAttribute('data-pair') === pair);
  }

  // Update pair name
  var pairName = el(C.prefix + '-chart-pair');
  if (pairName) pairName.textContent = pair;

  // Build pair nav chips
  var nav = el(C.prefix + '-pair-nav');
  if (nav && _allPairs.length > 0) {
    var html = '';
    for (var i = 0; i < _allPairs.length; i++) {
      var active = _allPairs[i] === pair ? ' bot-pair-active' : '';
      html += '<span class="bot-pair-chip' + active + '" onclick="BotDash.openChart(\'' + _allPairs[i] + '\')">' + _allPairs[i] + '</span>';
    }
    nav.innerHTML = html;
  }

  setTimeout(function() { panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 100);

  // Load chart data
  safeFetch(C.chartsPath + pair + '.json').then(function(r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function(d) {
    _renderCandlestick(d);
  }).catch(function(e) {
    console.warn('Chart load failed:', e);
  });
}

function _renderCandlestick(d) {
  var container = el(C.prefix + '-candle-chart');
  var rsiContainer = el(C.prefix + '-rsi-chart');
  if (!container) return;

  // Destroy previous
  if (_candleChart) { _candleChart.remove(); _candleChart = null; }
  if (_rsiChart) { _rsiChart.remove(); _rsiChart = null; }

  var bars = d.bars || [];
  if (bars.length === 0) return;

  // Extract per-bar indicators into separate arrays if not already top-level
  if (!d.rsi && bars.length > 0 && bars[0].rsi != null) {
    d.rsi = bars.map(function(b) { return { time: b.time, value: b.rsi }; });
    d.rsi_oversold = d.rsi_oversold || 35;
    d.rsi_overbought = d.rsi_overbought || 65;
  }
  if (!d.bb_upper && bars.length > 0 && bars[0].bb_upper != null) {
    d.bb_upper = bars.map(function(b) { return { time: b.time, value: b.bb_upper }; });
    d.bb_lower = bars.map(function(b) { return { time: b.time, value: b.bb_lower }; });
    d.bb_middle = bars.map(function(b) { return { time: b.time, value: b.bb_middle }; });
  }

  var _visibleStart = 0;
  // Filter by range
  if (_currentRangeDays > 0) {
    var cutoff = Math.floor(Date.now() / 1000) - _currentRangeDays * 86400;
    bars = bars.filter(function(b) { return b.time >= cutoff; });
    _visibleStart = cutoff;
  }

  _candleChart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight || 400,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b8b9e' },
    grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
    crosshair: { mode: 0 },
    timeScale: { timeVisible: true },
  });

  var candleSeries = _candleChart.addCandlestickSeries({
    upColor: '#145c32', downColor: '#7a1f1f',
    borderUpColor: '#145c32', borderDownColor: '#7a1f1f',
    wickUpColor: '#145c32', wickDownColor: '#7a1f1f',
  });
  candleSeries.setData(bars.map(function(b) {
    return { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close };
  }));


  // Apply backtest markers (trade entry arrows) — only when trades visible
  if (_showTradeLines && d.markers && d.markers.length > 0) {
    var visMarkers = d.markers;
    if (_currentRangeDays > 0) {
      var mc = Math.floor(Date.now() / 1000) - _currentRangeDays * 86400;
      visMarkers = d.markers.filter(function(m) { return m.time >= mc; });
    }
    candleSeries.setMarkers(visMarkers);
  }
  // BB overlay
  if (d.bb_upper) {
    var bbUp = _candleChart.addLineSeries({ color: 'rgba(91,141,239,0.08)', lineWidth: 1, priceLineVisible: false, autoscaleInfoProvider: function() { return null; } });
    var bbLo = _candleChart.addLineSeries({ color: 'rgba(91,141,239,0.08)', lineWidth: 1, priceLineVisible: false, autoscaleInfoProvider: function() { return null; } });
    var bbMid = _candleChart.addLineSeries({ color: 'rgba(91,141,239,0.08)', lineWidth: 1, lineStyle: 2, priceLineVisible: false, autoscaleInfoProvider: function() { return null; } });
    bbUp.setData(d.bb_upper.filter(function(p) { return p.value != null; }).map(function(p) { return { time: p.time, value: p.value }; }));
    bbLo.setData(d.bb_lower.filter(function(p) { return p.value != null; }).map(function(p) { return { time: p.time, value: p.value }; }));
    bbMid.setData(d.bb_middle.filter(function(p) { return p.value != null; }).map(function(p) { return { time: p.time, value: p.value }; }));
  }

  // EMA overlay
  if (d.ema_fast) {
    var emaF = _candleChart.addLineSeries({ color: 'rgba(240,185,64,0.4)', lineWidth: 1, priceLineVisible: false, autoscaleInfoProvider: function() { return null; } });
    var emaS = _candleChart.addLineSeries({ color: 'rgba(100,149,237,0.4)', lineWidth: 1, priceLineVisible: false, autoscaleInfoProvider: function() { return null; } });
    emaF.setData(d.ema_fast.filter(function(p) { return p.value != null; }).map(function(p) { return { time: p.time, value: p.value }; }));
    emaS.setData(d.ema_slow.filter(function(p) { return p.value != null; }).map(function(p) { return { time: p.time, value: p.value }; }));
  }

  // Trade lines overlay (backtest — only visible at narrow ranges)
  // At 90T/30T the lines are < 5% chart width → invisible. Show at 14T and below.
  var showLines = _showTradeLines && _currentRangeDays <= 14;
  if (showLines && d.trade_lines) {
    _renderTradeLines(_candleChart, candleSeries, d.trade_lines, bars, 0.7, _visibleStart);
  }

  // Live trades overlay (actual bot trades — bold)
  if (d.live_trades && d.live_trades.length > 0) {
    _renderLiveTrades(_candleChart, candleSeries, d.live_trades, bars, _visibleStart);
  }

  // Open position overlay (entry/SL/TP lines)
  if (d.open_positions && d.open_positions.length > 0) {
    _renderOpenPositions(_candleChart, d.open_positions, bars, _visibleStart);
  }

  _candleChart.timeScale().fitContent();

  // ResizeObserver to fix width=0 bug
  new ResizeObserver(function() {
    if (_candleChart && container.clientWidth > 0) {
      _candleChart.applyOptions({ width: container.clientWidth });
    }
  }).observe(container);

  // RSI sub-chart
  if (rsiContainer && d.rsi) {
    _rsiChart = LightweightCharts.createChart(rsiContainer, {
      width: rsiContainer.clientWidth,
      height: rsiContainer.clientHeight || 120,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b8b9e' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } },
      timeScale: { visible: false },
    });
    var rsiSeries = _rsiChart.addLineSeries({ color: '#a78bfa', lineWidth: 1.5, priceLineVisible: false, autoscaleInfoProvider: function() { return null; } });
    var rsiData = d.rsi.filter(function(p) { return p.value != null; }).map(function(p) { return { time: p.time, value: p.value }; });
    rsiSeries.setData(rsiData);

    // OS/OB lines
    var os = d.rsi_oversold || 35;
    var ob = d.rsi_overbought || 65;
    rsiSeries.createPriceLine({ price: os, color: 'rgba(34,197,94,0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OS' });
    rsiSeries.createPriceLine({ price: ob, color: 'rgba(239,68,68,0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'OB' });
    rsiSeries.createPriceLine({ price: 50, color: 'rgba(255,255,255,0.1)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });

    new ResizeObserver(function() {
      if (_rsiChart && rsiContainer.clientWidth > 0) {
        _rsiChart.applyOptions({ width: rsiContainer.clientWidth });
      }
    }).observe(rsiContainer);
  }

  // Config chips
  var configEl = el(C.prefix + '-chart-config');
  if (configEl && d.config) {
    var chips = '';
    var cfg = d.config;
    for (var k in cfg) {
      if (cfg.hasOwnProperty(k)) {
        chips += '<span class="bot-config-chip">' + k + ': ' + cfg[k] + '</span>';
      }
    }
    configEl.innerHTML = chips;
  }
}

function _renderTradeLines(chart, candleSeries, tradeLines, bars, alpha, visibleStart) {
  // Clear previous markers
  if (typeof _allTradeMarkers !== "undefined") _allTradeMarkers = [];
  // Store trade data for hover tooltips
  var _tradeMarkers = _allTradeMarkers;

  for (var i = 0; i < tradeLines.length; i++) {
    var tl = tradeLines[i];
    // Skip trades outside visible range (check ORIGINAL time, not snapped)
    if (visibleStart && tl.entry_time < visibleStart) continue;
    var entryTime = findNearestBarTime(bars, tl.entry_time);
    var exitTime = findNearestBarTime(bars, tl.exit_time);
    if (!entryTime) continue;

    var pnl = tl.pnl_pips || tl.pnl || 0;
    var isProfit = pnl >= 0;
    var isTimeout = tl.status === 'timeout' || tl.result === 'timeout' || tl.close_reason === 'timeout';
    var _a = (typeof alpha === 'number') ? alpha : 1.0;
    var lineColor = tl.color || (isProfit ? 'rgba(34,197,94,' + _a + ')' : 'rgba(239,68,68,' + _a + ')');
    var lineAlpha = isProfit ? 'rgba(34,197,94,' : 'rgba(239,68,68,';

    // Entry → exit line (THICKER: lineWidth 3)
    if (exitTime) {
      var lineSeries = chart.addLineSeries({
        color: lineColor,
        lineWidth: 2,
        lineStyle: isTimeout ? 2 : 0, // dashed for timeout
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
      lineSeries.setData([
        { time: entryTime, value: tl.entry_price || tl.price || tl.entry },
        { time: exitTime, value: tl.exit_price || tl.price || tl.entry }
      ]);

      // Store trade info for tooltip
      _tradeMarkers.push({
        entryTime: entryTime,
        exitTime: exitTime,
        entryPrice: tl.entry_price || tl.price || tl.entry,
        exitPrice: tl.exit_price || tl.price || tl.entry,
        direction: tl.direction || tl.side || 'long',
        margin: tl.margin || tl.margin_eur || (tl.sl_pips ? Math.round(tl.sl_pips * 0.092 * 0.02 * 1000) : 20),
        pnl: pnl,
        pnlEur: tl.pnl_eur || pnl,
        symbol: tl.symbol || '',
        sl: tl.sl,
        tp: tl.tp,
        score: tl.score,
        rsi: tl.rsi,
        strategy: tl.strategy || tl.strategy_id || '',
        holdBars: tl.hold_bars,
        closeReason: tl.result || tl.close_reason || '',
        isProfit: isProfit,
        isTimeout: isTimeout,
      });
    }

    // SL/TP horizontal lines (slightly more visible)
    if (tl.sl) {
      var slLine = chart.addLineSeries({
        color: lineAlpha + (0.15 * _a) + ')', lineWidth: 1, lineStyle: 2,
        priceLineVisible: false, lastValueVisible: false, autoscaleInfoProvider: function() { return null; } });
      slLine.setData([{ time: entryTime, value: tl.sl }, { time: exitTime || entryTime + 3600, value: tl.sl }]);
    }
    if (tl.tp) {
      var tpLine = chart.addLineSeries({
        color: 'rgba(34,197,94,' + (0.15 * _a) + ')', lineWidth: 1, lineStyle: 2,
        priceLineVisible: false, lastValueVisible: false, autoscaleInfoProvider: function() { return null; } });
      tpLine.setData([{ time: entryTime, value: tl.tp }, { time: exitTime || entryTime + 3600, value: tl.tp }]);
    }
  }

  // Unified tooltip (covers backtest + live + open)
  _subscribeLiveTooltip(chart, container);
}

/** Format EUR amount for chart labels */
function _fmtEur(val) {
  if (val === undefined || val === null) return '';
  var sign = val >= 0 ? '+' : '';
  return sign + val.toFixed(2) + ' €';
}

/** Render open position entry/SL/TP as horizontal lines on the chart */
function _renderOpenPositions(chart, positions, bars, visibleStart) {
  if (!bars || bars.length === 0) return;
  var lastBarTime = bars[bars.length - 1].time;
  var chartLabels = (C && C.chart_labels) ? C.chart_labels : [];

  for (var i = 0; i < positions.length; i++) {
    var p = positions[i];
    var entryTime = findNearestBarTime(bars, p.entry_time || p.timestamp) || bars[Math.max(0, bars.length - 50)].time;
    // Skip trades outside visible range
    if (visibleStart && entryTime < visibleStart) continue;
    var isShort = (p.side === 'sell' || p.side === 'short');

    // Extend lines left (24h before entry) so they're visible on longer charts
    var lookback = 24 * 60 * 60; // 24h in seconds
    var lineStart = Math.max(bars[0].time, entryTime - lookback);

    // Entry line — solid, prominent
    var entryLine = chart.addLineSeries({
      color: isShort ? '#ef4444' : '#22c55e',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
    entryLine.setData([
      { time: lineStart, value: p.entry_price || p.price || p.entry },
      { time: lastBarTime, value: p.entry_price || p.price || p.entry }
    ]);

    // SL line — red dashed
    if (p.sl) {
      var slLine = chart.addLineSeries({
        color: 'rgba(239,68,68,0.6)',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
      slLine.setData([
        { time: lineStart, value: p.sl },
        { time: lastBarTime, value: p.sl }
      ]);
    }

    // TP line — green dashed
    if (p.tp) {
      var tpLine = chart.addLineSeries({
        color: 'rgba(34,197,94,0.6)',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
      tpLine.setData([
        { time: lineStart, value: p.tp },
        { time: lastBarTime, value: p.tp }
      ]);
    }

    // Config-driven chart labels (EUR amounts for SL/TP, etc.)
    for (var li = 0; li < chartLabels.length; li++) {
      var lbl = chartLabels[li];
      var val = p[lbl.field];
      if (val !== undefined && val !== null && entryLine) {
        // Determine which price level to attach the label to
        var priceLevel = null;
        if (lbl.field === 'sl_eur' && p.sl) priceLevel = p.sl;
        else if (lbl.field === 'tp_eur' && p.tp) priceLevel = p.tp;
        // Future: add more field-to-price mappings here

        if (priceLevel !== null) {
          var labelText = (lbl.prefix || '') + _fmtEur(val) + (lbl.suffix || '');
          entryLine.createPriceLine({
            price: priceLevel,
            color: lbl.color || 'rgba(150,150,150,0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: labelText,
          });
        }
      }
    }
  }
}

/** Render live trades (actual bot trades) with bold entry/SL/TP lines */
function _renderLiveTrades(chart, candleSeries, liveTrades, bars, visibleStart) {
  if (!bars || bars.length === 0 || !liveTrades) return;
  var lastBarTime = bars[bars.length - 1].time;

  for (var i = 0; i < liveTrades.length; i++) {
    var t = liveTrades[i];
    var entryPrice = t.entry || 0;
    var sl = t.sl || 0;
    var tp = t.tp || 0;
    var exitPrice = t.exit_price || 0;
    var pnl = t.pnl || 0;
    var isShort = (t.side === 'sell' || t.side === 'short');
    var isProfit = pnl >= 0;
    var entryTime = findNearestBarTime(bars, t.timestamp) || bars[Math.max(0, bars.length - 50)].time;
    // Skip trades outside visible range
    if (visibleStart && entryTime < visibleStart) continue;
    var exitTime = findNearestBarTime(bars, t.closed_at) || lastBarTime;

    // Entry line — solid, prominent
    var entryLine = chart.addLineSeries({
      color: isShort ? '#ef4444' : '#22c55e',
      lineWidth: 3,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
    entryLine.setData([
      { time: entryTime, value: entryPrice },
      { time: exitTime, value: entryPrice }
    ]);

    // SL line — red dashed
    if (sl) {
      var slLine = chart.addLineSeries({
        color: 'rgba(239,68,68,0.7)',
        lineWidth: 2,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
      slLine.setData([
        { time: entryTime, value: sl },
        { time: exitTime, value: sl }
      ]);
    }

    // TP line — green dashed
    if (tp) {
      var tpLine = chart.addLineSeries({
        color: 'rgba(34,197,94,0.7)',
        lineWidth: 2,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
      tpLine.setData([
        { time: entryTime, value: tp },
        { time: exitTime, value: tp }
      ]);
    }

    // Exit marker — thick bar at exit point
    if (exitPrice && exitTime) {
      var exitColor = isProfit ? '#22c55e' : '#ef4444';
      var exitMarker = chart.addLineSeries({
        color: exitColor,
        lineWidth: 4,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false, autoscaleInfoProvider: function() { return null; } });
      exitMarker.setData([
        { time: Math.max(entryTime, exitTime - 3600), value: exitPrice },
        { time: exitTime, value: exitPrice }
      ]);
    }

    // Register for tooltip
    _allTradeMarkers.push({
      entryTime: entryTime,
      exitTime: exitTime,
      entryPrice: entryPrice,
      exitPrice: exitPrice || entryPrice,
      direction: isShort ? 'short' : 'long',
      pnl: pnl,
      pnlEur: pnl,
      symbol: t.symbol || '',
      sl: sl,
      tp: tp,
      isProfit: isProfit,
      isTimeout: false,
      isLive: true,
    });
  }

  // Subscribe to crosshair for live trade tooltips (if not already subscribed)
  _subscribeLiveTooltip(chart, container);
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
  _currentPair = null;
}

function setRange(days) {
  _currentRangeDays = days;
  var chips = document.querySelectorAll('.bot-range-chip');
  for (var i = 0; i < chips.length; i++) {
    chips[i].classList.toggle('bot-range-active', parseInt(chips[i].getAttribute('data-days')) === days);
  }
  if (_currentPair) openChart(_currentPair);
}

function toggleTradeLines() {
  _showTradeLines = !_showTradeLines;
  var btn = el(C.prefix + '-trade-toggle');
  if (btn) {
    btn.textContent = _showTradeLines ? '📊 Trades: ON' : '📊 Trades: OFF';
    btn.style.color = _showTradeLines ? '#22c55e' : 'var(--c-text-dim)';
  }
  if (_currentPair) openChart(_currentPair);
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

function renderBacktest(d) {
  var bt = d.backtest_summary || d.backtest || {};
  if (!bt || Object.keys(bt).length === 0) return;

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
      oosEl.textContent = 'IS=' + recipe.is_months + 'M / OOS=' + recipe.oos_months + 'M · ' + passRate;
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

  // Pairs
  var pairsEl = el(C.prefix + '-bt-pairs');
  if (pairsEl) {
    if (bt.recipe) pairsEl.textContent = bt.recipe.assets.length;
    else if (bt.total_pairs) pairsEl.textContent = bt.total_pairs;
  }

  // Pairs Sub — recipe asset list
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

/** Per-pair parameters table */
function renderPairParams(d) {
  var tbody = el(C.prefix + '-pair-params-body');
  if (!tbody) return;
  var bt = d.backtest_summary || d.backtest || {};
  var perPair = bt.per_pair || bt.per_index || {};
  var pairs = d.pairs || [];
  if (pairs.length === 0 && Object.keys(perPair).length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="bot-no-data">No pair data</td></tr>';
    return;
  }
  var pairList = pairs.length > 0 ? pairs.map(function(p) { return p.symbol; }) : Object.keys(perPair);

  // Detect index portfolio mode (has pf, wr, pnl fields)
  var isIndex = pairList.length > 0 && perPair[pairList[0]] && perPair[pairList[0]].pf != null;

  var html = '';
  if (isIndex) {
    for (var i = 0; i < pairList.length; i++) {
      var sym = pairList[i];
      var pp = perPair[sym] || {};
      html += '<tr>';
      html += '<td><b>' + sym + '</b></td>';
      html += '<td>' + (pp.pass_rate || '—') + '</td>';
      html += '<td class="' + (pp.pf >= 2.0 ? 'bot-pnl-pos' : '') + '">' + (pp.pf != null ? pp.pf.toFixed(2) : '—') + '</td>';
      html += '<td class="' + (pp.wr >= 50 ? 'bot-pnl-pos' : 'bot-pnl-neg') + '">' + (pp.wr != null ? pp.wr.toFixed(1) + '%' : '—') + '</td>';
      html += '<td class="' + pnlClass(pp.pnl || 0) + '">' + (pp.pnl != null ? fmtPnl(pp.pnl) + ' pts' : '—') + '</td>';
      html += '<td class="bot-pnl-neg">' + (pp.dd != null ? pp.dd.toFixed(0) + ' pts' : '—') + '</td>';
      html += '<td>' + (pp.trades || '—') + '</td>';
      html += '</tr>';
    }
    // Update header for index mode
    var thead = tbody.parentElement ? tbody.parentElement.querySelector('thead tr') : null;
    if (thead) thead.innerHTML = '<th>Index</th><th>MFO Pass</th><th>PF</th><th>WR</th><th>PnL</th><th>Max DD</th><th>Trades</th>';
  } else {
    for (var i = 0; i < pairList.length; i++) {
      var sym = pairList[i];
      var pp = perPair[sym] || {};
      var rsiLo = pp.rsi_oversold || pp.oversold || '—';
      var rsiHi = pp.rsi_overbought || pp.overbought || '—';
      var strategy = pp.strategy || '—';
      var sl = pp.sl_pips != null ? pp.sl_pips : (pp.sl || '—');
      var tp = pp.tp_pips != null ? pp.tp_pips : (pp.tp || '—');
      var rr = (typeof sl === 'number' && typeof tp === 'number' && sl > 0) ? (tp / sl).toFixed(1) : '—';
      var exp = pp.expectancy != null ? fmtPnl(pp.expectancy) : '—';
      html += '<tr>';
      html += '<td><b>' + sym + '</b></td>';
      html += '<td>' + rsiLo + '–' + rsiHi + '</td>';
      html += '<td>' + strategy + '</td>';
      html += '<td>' + sl + '</td>';
      html += '<td>' + tp + '</td>';
      html += '<td>1:' + rr + '</td>';
      html += '<td class="' + pnlClass(pp.expectancy || 0) + '">' + exp + '</td>';
      html += '</tr>';
    }
  }
  tbody.innerHTML = html || '<tr><td colspan="7" class="bot-no-data">No pair data</td></tr>';
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
  var panes = ['history', 'backtest', 'params', 'reopt'];
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
    renderStatus(d);
    renderKPIs(d);
    renderPerformance(d);
    renderPositions(d);
    renderDataAge(d);
    renderHistory(d);
    if (C.hasEquity) renderEquity(d);
    if (C.hasSignals) renderSignals(d);
    if (C.hasBacktest) renderBacktest(d);
    renderPairParams(d);
    renderReoptimize();
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
 *  PUBLIC API
 * ═══════════════════════════════════════════════════════════ */

window.BotDash = {
  init: init,
  loadDashboard: loadDashboard,
  switchTab: switchTab,
  openChart: openChart,
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
  renderKPIs: renderKPIs,
  renderPerformance: renderPerformance,
  renderPositions: renderPositions,
  renderHistory: renderHistory,
  renderSignals: renderSignals,
  renderEquity: renderEquity,
  renderBacktest: renderBacktest,
  renderPairParams: renderPairParams,
};

})();
