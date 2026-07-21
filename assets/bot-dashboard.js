/**
 * bot-dashboard.js — Shared Bot Dashboard Template Engine
 * 
 * Usage:
 *   <script src="/assets/bot-dashboard.js"></script>
 *   <script>
 *     BotDashboard.init({
 *       botId: 'fx',
 *       apiPath: '/api/fx',
 *       botName: 'FX Mean Reversion Bot',
 *       refreshInterval: 60,
 *       features: { candlestick: true, heatmap: true, signalGrid: true }
 *     });
 *   </script>
 * 
 * Requires: bot-base.css, Chart.js, LightweightCharts (if candlestick enabled)
 * Timezone: All times displayed in Europe/Berlin (Michael's preference)
 */

var BotDashboard = (function() {
  'use strict';

  // ── Config ──────────────────────────────────────────────────
  var _config = {
    botId: 'bot',
    apiPath: '/api/bot',
    botName: 'Bot',
    refreshInterval: 60,
    features: {
      healthBanner: true,
      strategyInfo: true,
      candlestick: false,
      heatmap: false,
      signalGrid: false,
      pairParams: false,
    },
    indicators: { type: 'rsi_bb', label: 'RSI + BB' },
    positionsColumns: ['Pair', 'Direction', 'Score', 'Entry', 'SL', 'TP', 'Margin', 'P&L', 'Duration'],
    historyColumns: ['Time', 'Pair', 'Direction', 'Entry', 'Exit', 'P&L', 'Duration'],
  };

  var _dashboardData = null;
  var _chartInstance = null;
  var _mainChart = null;
  var _rsiChart = null;
  var _mainSeries = null;
  var _allPairs = [];
  var _chartRawData = null;
  var _rangeDays = 0;
  var _tradeLineSeries = [];

  // ── Helpers ─────────────────────────────────────────────────

  function _id(suffix) {
    return _config.botId + '-' + suffix;
  }

  function _el(suffix) {
    return document.getElementById(_id(suffix));
  }

  function safeFetch(path, opts) {
    var url = window.location.origin + path + (path.indexOf('?') >= 0 ? '&' : '?') + '_t=' + Date.now();
    opts = opts || {};
    opts.cache = 'no-store';
    opts.credentials = 'same-origin';
    return fetch(url, opts);
  }

  // Berlin timezone formatting (Michael's preference)
  function fmtTime(iso) {
    if (!iso) return '\u2014';
    try {
      if (typeof iso === 'number') iso = new Date(iso * 1000);
      else {
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso) && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(iso)) iso += 'Z';
        iso = new Date(iso);
      }
      return iso.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' });
    } catch (e) { return iso; }
  }

  function pnlClass(val) { return val >= 0 ? 'bot-pnl-pos' : 'bot-pnl-neg'; }
  function pnlFormat(val) { if (val == null) return '\u2014'; return (val >= 0 ? '+' : '') + val.toFixed(2); }
  function dotClass(active) { return active ? 'bot-status-dot green' : 'bot-status-dot red'; }

  function fmtPrice(p, pair) {
    if (p == null) return '\u2014';
    if (String(pair).indexOf('JPY') >= 0) return p.toFixed(3);
    return p.toFixed(5);
  }

  function fmtDuration(openedAt) {
    if (!openedAt) return '\u2014';
    try {
      var opened = new Date(openedAt);
      var now = new Date();
      var diffMs = now - opened;
      var diffH = diffMs / 3600000;
      if (diffH < 1) return Math.floor(diffMs / 60000) + 'm';
      if (diffH < 24) return diffH.toFixed(1) + 'h';
      return Math.floor(diffH / 24) + 'd ' + Math.floor(diffH % 24) + 'h';
    } catch (e) { return '\u2014'; }
  }

  function fmtVolume(vol) {
    if (vol == null) return '\u2014';
    // Volume in micro-lots (10,000,000 = 1 standard lot)
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

  // ── Render Functions ────────────────────────────────────────

  function renderStatus(d) {
    var dot = _el('dot');
    var status = _el('status');
    var badge = _el('mode-badge');
    var lastUpdate = _el('last-update');

    if (!dot) return;

    var isActive = !!(d.status && d.status.active);
    dot.className = dotClass(isActive);
    status.textContent = isActive ? 'Bot active' : (d.status && d.status.message ? d.status.message : 'Bot inactive');

    var mode = d.mode || 'demo';
    badge.textContent = mode.toUpperCase();
    badge.className = 'bot-badge ' + (mode === 'live' ? 'bot-badge-live' : 'bot-badge-demo');

    lastUpdate.textContent = 'Updated: ' + fmtTime(d.timestamp || d.last_update);

    // Health banner
    if (_config.features.healthBanner) {
      var banner = _el('health-banner');
      var healthText = _el('health-text');
      var healthTime = _el('health-time');
      if (banner) {
        var st = d.status || {};
        var bannerVisible = false;

        // Market-closed detection — stale data is expected on weekends
        var msgLower = (st.message || '').toLowerCase();
        var isMarketClosed = msgLower.indexOf('market closed') >= 0;

        if (!isActive && !isMarketClosed) {
          banner.className = 'bot-health-banner visible error';
          healthText.textContent = st.last_error_msg || st.message || 'Connection lost';
          if (st.last_error) healthTime.textContent = 'since ' + fmtTime(st.last_error);
          bannerVisible = true;
        } else if (st.consecutive_errors > 0) {
          banner.className = 'bot-health-banner visible warn';
          healthText.textContent = st.consecutive_errors + ' recent error(s). Last: ' + (st.last_error_msg || 'unknown');
          if (st.last_success) healthTime.textContent = 'last OK: ' + fmtTime(st.last_success);
          bannerVisible = true;
        } else if (isMarketClosed) {
          banner.className = 'bot-health-banner visible info';
          healthText.textContent = st.message || '🔒 Market closed — sync paused';
          healthTime.textContent = '';
          bannerVisible = true;
        } else if (st.health_age_seconds != null && st.health_age_seconds > 1800) {
          banner.className = 'bot-health-banner visible warn';
          healthText.textContent = 'Data may be stale \u2014 last sync ' + Math.round(st.health_age_seconds / 60) + ' min ago';
          bannerVisible = true;
        }

        if (!bannerVisible) banner.className = 'bot-health-banner';
      }
    }
  }

  function renderCards(d) {
    // Handle both d.account.balance and d.balance (fix F01/F02)
    var bal = d.account ? d.account.balance : d.balance;
    var eq = d.account ? d.account.equity : d.equity;
    var balEl = _el('balance');
    if (balEl) {
      balEl.textContent = bal != null ? '\u20ac' + bal.toFixed(2) : '\u2014';
      _el('equity-sub').textContent = eq != null ? 'Equity: \u20ac' + eq.toFixed(2) : '\u2014';
    }

    var pos = d.positions || [];
    var posCountEl = _el('positions-count');
    if (posCountEl) {
      posCountEl.textContent = pos.length;
      var totalMargin = d.performance ? d.performance.total_margin_eur : null;
      var marginText = totalMargin != null ? ' | Margin: \u20ac' + totalMargin.toFixed(2) : '';
      _el('positions-sub').textContent = (pos.length === 1 ? 'open position' : 'open positions') + marginText;
    }

    var daily = d.daily_pnl != null ? d.daily_pnl : (d.performance ? d.performance.daily_pnl : 0) || 0;
    var dailyEl = _el('daily-pnl');
    if (dailyEl) {
      dailyEl.textContent = pnlFormat(daily) + ' EUR';
      dailyEl.className = 'bot-card-value ' + pnlClass(daily);
      var tday = d.trades_today || 0;
      _el('trades-today').textContent = tday + ' trade' + (tday === 1 ? '' : 's') + ' today';
    }

    var perf = d.performance || {};
    var totalPnl = perf.total_pnl || 0;
    var totalEl = _el('total-pnl');
    if (totalEl) {
      totalEl.textContent = pnlFormat(totalPnl) + ' EUR';
      totalEl.className = 'bot-card-value ' + pnlClass(totalPnl);
      _el('winrate-sub').textContent = (perf.total_trades || 0) + ' total trades';
    }
  }

  function renderPerformance(d) {
    var perf = d.performance || {};
    var totalTrades = perf.total_trades || 0;
    var wins = perf.wins || perf.winning_trades || 0;
    var losses = perf.losses || 0;

    var wrEl = _el('winrate');
    if (wrEl) {
      var wr = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) + '%' : '\u2014';
      wrEl.textContent = wr;
      if (totalTrades > 0) {
        wrEl.className = 'bot-card-value ' + ((wins / totalTrades) >= 0.5 ? 'bot-pnl-pos' : 'bot-pnl-neg');
      }
      _el('winrate-detail').textContent = wins + 'W / ' + losses + 'L';
    }

    var pfEl = _el('profit-factor');
    if (pfEl) {
      var pf = perf.profit_factor;
      pfEl.textContent = pf != null ? pf.toFixed(2) : '\u2014';
      if (pf != null) pfEl.className = 'bot-card-value ' + (pf >= 1.5 ? 'bot-pnl-pos' : 'bot-pnl-neg');
    }

    var expEl = _el('expectancy');
    if (expEl) {
      var exp = perf.expectancy || 0;
      expEl.textContent = (exp >= 0 ? '+' : '') + exp.toFixed(2) + ' EUR';
      expEl.className = 'bot-card-value ' + pnlClass(exp);
    }

    var ddEl = _el('max-dd');
    if (ddEl) {
      // Use live max_drawdown first, fall back to backtest (fix F07)
      var dd = perf.max_drawdown_pct || perf.max_drawdown || 0;
      ddEl.textContent = dd.toFixed(2) + '%';
      ddEl.className = 'bot-card-value ' + (dd <= 10 ? 'bot-pnl-pos' : 'bot-pnl-neg');
    }

    // Margin utilization (fix F12)
    var marginEl = _el('margin-util');
    if (marginEl) {
      var mu = perf.margin_utilization_pct;
      marginEl.textContent = mu != null ? mu.toFixed(1) + '%' : '\u2014';
      if (mu != null) marginEl.className = 'bot-card-value ' + (mu <= 50 ? 'bot-pnl-pos' : mu <= 80 ? '' : 'bot-pnl-neg');
    }
  }

  function renderEquityChart(d) {
    var data = d.equity_history || [];
    if (data.length === 0) return;
    if (typeof Chart === 'undefined') { console.warn('Chart.js not loaded'); return; }

    var labels = [], values = [];
    for (var i = 0; i < data.length; i++) {
      var pt = data[i];
      var ts = pt.timestamp || pt.time;
      if (ts && !/[Zz]|[+\-]\d{2}:?\d{2}$/.test(ts)) ts += 'Z';
      labels.push(new Date(ts));
      values.push(pt.adjusted_equity != null ? pt.adjusted_equity : (pt.equity || pt.balance));
    }
    var minV = Math.min.apply(null, values), maxV = Math.max.apply(null, values);
    var padding = (maxV - minV) * 0.1 || 50;

    var canvas = document.getElementById(_id('equity-chart'));
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    if (_chartInstance) _chartInstance.destroy();
    _chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Equity (\u20ac)',
          data: values,
          borderColor: '#22c55e',
          backgroundColor: 'rgba(34,197,94,0.08)',
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          pointHitRadius: 8,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function(ctx) { return '\u20ac' + ctx.parsed.y.toFixed(2); }
            }
          }
        },
        scales: {
          x: { type: 'time', time: { unit: 'day', tooltipFormat: 'dd.MM.yyyy HH:mm' }, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b949e', maxTicksLimit: 10 } },
          y: { min: Math.floor(minV - padding), max: Math.ceil(maxV + padding), grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b949e', callback: function(v) { return '\u20ac' + v; } } }
        }
      }
    });

    var first = values[0], last = values[values.length - 1];
    var change = last - first, pct = ((change / first) * 100).toFixed(1);
    var sign = change >= 0 ? '+' : '';
    var summaryEl = _el('equity-summary');
    if (summaryEl) {
      summaryEl.innerHTML =
        '<span>Start: <b>\u20ac' + first.toFixed(2) + '</b></span>' +
        '<span>Current: <b>\u20ac' + last.toFixed(2) + '</b></span>' +
        "<span>Change: <b style='color:" + (change >= 0 ? '#22c55e' : '#ef4444') + "'>" + sign + change.toFixed(2) + ' \u20ac (' + sign + pct + '%)</b></span>' +
        '<span>Points: <b>' + values.length + '</b></span>';
    }
  }

  function renderPositions(d) {
    var tbody = _el('positions-body');
    if (!tbody) return;
    var pos = d.positions || [];
    if (pos.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="bot-no-data">No open positions</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < pos.length; i++) {
      var p = pos[i];
      var dir = (p.direction || p.side || '').toLowerCase();
      var dirBadge = dir === 'sell' || dir === 'short'
        ? '<span class="bot-badge bot-badge-sell">SHORT</span>'
        : '<span class="bot-badge bot-badge-buy">LONG</span>';
      var upnl = p.unrealized_pnl != null ? p.unrealized_pnl : (p.pnl || 0);
      html += '<tr class="bot-pos-row">';
      html += '<td><b>' + (p.symbol || p.pair || '\u2014') + '</b></td>';
      html += '<td>' + dirBadge + '</td>';
      var sc = p.score != null ? p.score : '\u2014';
      var scClass = sc >= 60 ? 'bot-pnl-pos' : (sc >= 50 ? '' : 'bot-pnl-neg');
      html += '<td style="font-size:var(--text-xs)" class="' + scClass + '"><b>' + sc + '</b></td>';
      var ep = p.entry_price || p.entry || null;
      html += '<td>' + fmtPrice(ep, p.symbol || p.pair) + '</td>';
      html += '<td>' + fmtPrice(p.sl, p.symbol || p.pair) + '</td>';
      html += '<td>' + fmtPrice(p.tp, p.symbol || p.pair) + '</td>';
      var margin = p.margin_eur;
      html += '<td>' + (margin != null ? '\u20ac' + margin.toFixed(2) : '\u2014') + '</td>';
      // Volume column (fix F13)
      html += '<td style="font-size:var(--text-xs)">' + fmtVolume(p.volume) + '</td>';
      html += '<td class="' + pnlClass(upnl) + '"><b>' + pnlFormat(upnl) + '</b></td>';
      html += '<td style="font-size:var(--text-xs)">' + fmtDuration(p.opened_at || p.timestamp) + '</td>';
      html += '</tr>';
    }
    tbody.innerHTML = html;
  }

  function renderHistory(d) {
    var tbody = _el('history-body');
    if (!tbody) return;
    var trades = d.last_trades || d.trade_history || d.round_trips || [];
    if (trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="bot-no-data">No completed trades</td></tr>';
      return;
    }
    var html = '';
    var limit = Math.min(trades.length, 20);
    for (var i = trades.length - 1; i >= trades.length - limit; i--) {
      var t = trades[i];
      var dir = (t.direction || t.side || '').toLowerCase();
      var dirBadge = dir === 'sell' || dir === 'short'
        ? '<span class="bot-badge bot-badge-sell">SHORT</span>'
        : '<span class="bot-badge bot-badge-buy">LONG</span>';
      var pnl = t.pnl != null ? t.pnl : (t.realized_pnl || t.profit || 0);
      var dur = t.duration || (t.duration_hours != null ? t.duration_hours.toFixed(1) + 'h' : '\u2014');
      html += '<tr>';
      html += '<td>' + fmtTime(t.close_time || t.closed_at || t.exit_time || t.timestamp) + '</td>';
      html += '<td><b>' + (t.symbol || t.pair || '\u2014') + '</b></td>';
      html += '<td>' + dirBadge + '</td>';
      html += '<td>' + fmtPrice(t.entry_price || t.entry, t.symbol || t.pair) + '</td>';
      html += '<td>' + fmtPrice(t.close_price || t.exit_price || t.current_price, t.symbol || t.pair) + '</td>';
      html += '<td class="' + pnlClass(pnl) + '"><b>' + pnlFormat(pnl) + '</b></td>';
      var closeReason = t.close_reason || t.status || '—';
      var closeLabels = {'sl_hit': '🛑 SL', 'tp_hit': '🎯 TP', 'timeout': '⏰ Timeout',
        'manually_closed': '🤚 Manual', 'closed_by_us': '🤚 Closed', 'test_close': '🧪 Test',
        'tp_sl_closed': '⚡ TP/SL', 'replaced': '🔄 Replaced'};
      var closeLabel = closeLabels[closeReason] || closeReason;
      html += '<td style="font-size:var(--text-xs)">' + dur + '</td>';
      html += '<td style="font-size:var(--text-xs)">' + closeLabel + '</td>';
      html += '</tr>';
    }
    tbody.innerHTML = html;
  }

  // ── Signal Grid (optional) ──────────────────────────────────

  function renderSignalGrid(d) {
    if (!_config.features.signalGrid) return;
    var grid = _el('signal-grid');
    if (!grid) return;

    var signals = d.active_signals || d.signals || [];
    if (signals.length === 0) {
      grid.innerHTML = '<div class="bot-no-data">No active signals</div>';
      return;
    }

    _allPairs = [];
    var html = '';
    for (var i = 0; i < signals.length; i++) {
      var s = signals[i];
      var sym = s.symbol || s.pair || '';
      _allPairs.push(sym);
      var signal = (s.signal || s.direction || '').toUpperCase();
      var rsi = s.rsi != null ? s.rsi : (s.indicators ? s.indicators.rsi : null);
      var score = s.score;
      var isActive = s.active || s.in_position;

      var sigClass = '';
      var sigText = signal;
      if (signal === 'LONG' || signal === 'BUY') { sigClass = 'bot-pnl-pos'; sigText = 'LONG \u2713'; }
      else if (signal === 'SHORT' || signal === 'SELL') { sigClass = 'bot-pnl-neg'; sigText = 'SHORT \u2713'; }
      else if (signal === 'NEAR_OVERSOLD' || signal === 'NEAR OS') { sigClass = 'bot-pnl-pos'; sigText = 'NEAR OS'; }
      else if (signal === 'NEAR_OVERBOUGHT' || signal === 'NEAR OB') { sigClass = 'bot-pnl-neg'; sigText = 'NEAR OB'; }

      html += '<div class="bot-signal-card' + (isActive ? ' bot-active-card' : '') + '" data-pair="' + sym + '" onclick="BotDashboard.showChart(\'' + sym + '\')">';
      html += '<div class="bot-signal-pair">' + sym + '</div>';
      html += '<div class="bot-signal-status ' + sigClass + '">' + sigText + '</div>';
      if (rsi != null) html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim);margin-top:2px">RSI: ' + rsi.toFixed(0) + '</div>';
      if (score != null) html += '<div style="font-size:var(--text-xs);color:var(--c-text-dim)">Score: ' + score + '</div>';
      html += '</div>';
    }
    grid.innerHTML = html;

    // Build pair nav chips for chart panel
    if (_config.features.candlestick && _allPairs.length > 0) {
      buildPairNav(_allPairs);
    }
  }

  function buildPairNav(pairs) {
    var nav = _el('pair-nav');
    if (!nav) return;
    var html = '';
    for (var i = 0; i < pairs.length; i++) {
      html += '<span class="bot-pair-chip" data-pair="' + pairs[i] + '" onclick="BotDashboard.showChart(\'' + pairs[i] + '\')">' + pairs[i] + '</span>';
    }
    nav.innerHTML = html;
  }

  // ── Heatmap (optional) ──────────────────────────────────────

  function renderHeatmap() {
    if (!_config.features.heatmap) return;
    var grid = _el('heatmap-grid');
    if (!grid) return;

    safeFetch(_config.apiPath + '/performance_heatmap.json').then(function(r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function(d) {
      var pairs = d.pairs || {};
      var symbols = Object.keys(pairs).sort();
      if (symbols.length === 0) {
        grid.innerHTML = '<div class="bot-no-data">No trade data yet</div>';
        return;
      }
      var html = '';
      for (var i = 0; i < symbols.length; i++) {
        var sym = symbols[i];
        var p = pairs[sym];
        var wr = p.win_rate || 0;
        var pnl = p.total_pnl || 0;
        var trades = p.trades || 0;
        var rr = p.rr_ratio || 0;
        var open = p.open_positions || 0;

        var wrColor;
        if (trades === 0) wrColor = 'var(--c-text-dim)';
        else if (wr >= 70) wrColor = '#22c55e';
        else if (wr >= 50) wrColor = '#f0b940';
        else if (wr >= 30) wrColor = '#f0a050';
        else wrColor = '#ef4444';

        var pnlColor = pnl >= 0 ? '#22c55e' : '#ef4444';
        var pnlSign = pnl >= 0 ? '+' : '';
        var rrBg = rr >= 2 ? 'rgba(34,197,94,0.15)' : rr >= 1 ? 'rgba(240,185,64,0.15)' : 'rgba(239,68,68,0.15)';
        var rrColor = rr >= 2 ? '#22c55e' : rr >= 1 ? '#f0b940' : '#ef4444';
        var barWidth = Math.max(0, Math.min(100, wr));
        var barColor = wr >= 70 ? '#22c55e' : wr >= 50 ? '#f0b940' : '#ef4444';

        html += '<div class="bot-heatmap-cell" data-pair="' + sym + '" onclick="BotDashboard.showChart(\'' + sym + '\')">';
        html += '<div class="pair-name">' + sym + '</div>';
        if (trades > 0) {
          html += '<div class="wr-value" style="color:' + wrColor + '">' + wr.toFixed(0) + '%</div>';
          html += '<div class="pnl-value" style="color:' + pnlColor + '">' + pnlSign + pnl.toFixed(1) + '\u20ac</div>';
          html += '<div class="trade-count">' + trades + ' trade' + (trades !== 1 ? 's' : '') + (open > 0 ? ' \u00b7 ' + open + ' open' : '') + '</div>';
          html += '<div class="rr-badge" style="background:' + rrBg + ';color:' + rrColor + '">R:R ' + rr.toFixed(1) + '</div>';
        } else {
          html += '<div class="wr-value" style="color:var(--c-text-dim)">\u2014</div>';
          html += '<div class="trade-count">No trades</div>';
        }
        html += '<div class="bot-heatmap-bar" style="width:' + barWidth + '%;background:' + barColor + ';opacity:0.6"></div>';
        html += '</div>';
      }
      grid.innerHTML = html;
    }).catch(function(e) {
      console.warn('Heatmap load failed:', e);
      grid.innerHTML = '<div class="bot-no-data">Heatmap data not available</div>';
    });
  }

  // ── Candlestick Chart (LightweightCharts) ───────────────────

  function showChart(pair) {
    if (!_config.features.candlestick) return;
    var panel = _el('chart-panel');
    if (!panel) return;

    panel.className = 'bot-chart-panel active';
    _el('chart-pair-name').textContent = pair;

    // Update active states
    var cards = document.querySelectorAll('.bot-signal-card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('bot-active-card', cards[i].getAttribute('data-pair') === pair);
    }
    var chips = document.querySelectorAll('.bot-pair-chip');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('bot-pair-active', chips[i].getAttribute('data-pair') === pair);
    }

    // Load chart data
    safeFetch(_config.apiPath + '/charts/' + pair + '.json').then(function(r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function(data) {
      _chartRawData = data;
      renderCandlestickChart(data, pair);
    }).catch(function(e) {
      console.warn('Chart load failed for ' + pair + ':', e);
      var wrap = _el('chart-wrap');
      if (wrap) wrap.innerHTML = '<div class="bot-no-data">Chart data not available for ' + pair + '</div>';
    });

    // Scroll chart into view
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function hideChart() {
    var panel = _el('chart-panel');
    if (panel) panel.className = 'bot-chart-panel';
    if (_mainChart) { _mainChart.remove(); _mainChart = null; }
    if (_rsiChart) { _rsiChart.remove(); _rsiChart = null; }
    _mainSeries = null;
    _tradeLineSeries = [];
  }

  function renderCandlestickChart(data, pair) {
    if (typeof LightweightCharts === 'undefined') { console.warn('LightweightCharts not loaded'); return; }

    var wrap = _el('chart-wrap');
    if (!wrap) return;
    wrap.innerHTML = '';

    var bars = data.bars || [];
    if (bars.length === 0) { wrap.innerHTML = '<div class="bot-no-data">No candle data</div>'; return; }

    // Apply range filter
    var filteredBars = bars;
    if (_rangeDays > 0) {
      var cutoff = Date.now() / 1000 - _rangeDays * 86400;
      filteredBars = bars.filter(function(b) { return b.time >= cutoff; });
    }

    // Render config chips from indicator data
    renderChartConfig(data);

    // Create main chart
    var chartHeight = _config.indicators.chart_height || 320;
    _mainChart = LightweightCharts.createChart(wrap, {
      width: wrap.clientWidth,
      height: chartHeight,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b949e' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true },
    });

    // Candlestick series
    _mainSeries = _mainChart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    var candleData = filteredBars.map(function(b) {
      return { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close };
    });
    _mainSeries.setData(candleData);

    // Overlay indicators based on type
    var indType = _config.indicators.type || 'rsi_bb';
    if (indType === 'rsi_bb') {
      renderBBOverlay(filteredBars);
    } else if (indType === 'ema_adx') {
      renderEMAOverlay(filteredBars);
    }

    // Trade lines (diagonal, Michael's preference)
    renderTradeLines(data.trade_lines || []);

    // ResizeObserver (fix F19: chart width=0 bug)
    var ro = new ResizeObserver(function(entries) {
      for (var i = 0; i < entries.length; i++) {
        var cr = entries[i].contentRect;
        if (_mainChart && cr.width > 0) _mainChart.resize(cr.width, chartHeight);
        if (_rsiChart && cr.width > 0) _rsiChart.resize(cr.width, 120);
      }
    });
    ro.observe(wrap);

    // RSI / ADX sub-chart
    renderSubChart(filteredBars, wrap);

    // Live price line
    if (data.live_price) {
      _mainSeries.createPriceLine({
        price: data.live_price,
        color: '#5b8def',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'Live',
      });
    }

    _mainChart.timeScale().fitContent();
  }

  function renderBBOverlay(bars) {
    if (!_mainSeries) return;
    var bbUpper = [], bbMiddle = [], bbLower = [];
    for (var i = 0; i < bars.length; i++) {
      var b = bars[i];
      if (b.bb_upper != null) bbUpper.push({ time: b.time, value: b.bb_upper });
      if (b.bb_middle != null) bbMiddle.push({ time: b.time, value: b.bb_middle });
      if (b.bb_lower != null) bbLower.push({ time: b.time, value: b.bb_lower });
    }
    if (bbUpper.length > 0) {
      _mainSeries.setMarkers ? _mainSeries.setMarkers([]) : 0;
      // BB as line overlays
      var upperLine = _mainChart.addLineSeries({ color: 'rgba(91,141,239,0.3)', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      upperLine.setData(bbUpper);
      var midLine = _mainChart.addLineSeries({ color: 'rgba(91,141,239,0.5)', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
      midLine.setData(bbMiddle);
      var lowerLine = _mainChart.addLineSeries({ color: 'rgba(91,141,239,0.3)', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      lowerLine.setData(bbLower);
    }
  }

  function renderEMAOverlay(bars) {
    if (!_mainSeries) return;
    var emaFast = [], emaSlow = [];
    for (var i = 0; i < bars.length; i++) {
      var b = bars[i];
      if (b.ema_fast != null) emaFast.push({ time: b.time, value: b.ema_fast });
      if (b.ema_slow != null) emaSlow.push({ time: b.time, value: b.ema_slow });
    }
    if (emaFast.length > 0) {
      var fastLine = _mainChart.addLineSeries({ color: '#f0b940', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      fastLine.setData(emaFast);
    }
    if (emaSlow.length > 0) {
      var slowLine = _mainChart.addLineSeries({ color: '#5b8def', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      slowLine.setData(emaSlow);
    }
  }

  function renderTradeLines(tradeLines) {
    if (!_mainChart || !tradeLines || tradeLines.length === 0) return;
    // Clear old trade lines
    for (var i = 0; i < _tradeLineSeries.length; i++) {
      try { _mainChart.removeSeries(_tradeLineSeries[i]); } catch(e) {}
    }
    _tradeLineSeries = [];

    for (var i = 0; i < tradeLines.length; i++) {
      var tl = tradeLines[i];
      var entryTime = findNearestBarTime(_chartRawData ? _chartRawData.bars : [], tl.entry_time);
      var exitTime = findNearestBarTime(_chartRawData ? _chartRawData.bars : [], tl.exit_time);
      if (!entryTime || !exitTime) continue;

      var color = tl.color || (tl.pnl >= 0 ? '#22c55e' : '#ef4444');
      var lineSeries = _mainChart.addLineSeries({
        color: color,
        lineWidth: 2,
        lineStyle: tl.dashed ? 1 : 0,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      lineSeries.setData([
        { time: entryTime, value: tl.price },
        { time: exitTime, value: tl.exit_price }
      ]);
      _tradeLineSeries.push(lineSeries);
    }
  }

  function renderSubChart(bars, container) {
    var subType = _config.indicators.sub_chart ? _config.indicators.sub_chart.type : null;
    if (!subType) return;

    // RSI sub-chart label
    var labelEl = _el('rsi-label');
    if (labelEl) labelEl.style.display = 'block';

    var subWrap = _el('rsi-wrap');
    if (!subWrap) return;

    _rsiChart = LightweightCharts.createChart(subWrap, {
      width: subWrap.clientWidth,
      height: 120,
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b949e' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
      timeScale: { visible: false },
    });

    if (subType === 'rsi') {
      var rsiLine = _rsiChart.addLineSeries({ color: '#a78bfa', lineWidth: 1.5, priceLineVisible: false });
      var rsiData = [];
      for (var i = 0; i < bars.length; i++) {
        if (bars[i].rsi != null) rsiData.push({ time: bars[i].time, value: bars[i].rsi });
      }
      rsiLine.setData(rsiData);

      // RSI zones (green oversold, red overbought)
      rsiLine.createPriceLine({ price: 70, color: 'rgba(239,68,68,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
      rsiLine.createPriceLine({ price: 30, color: 'rgba(34,197,94,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    } else if (subType === 'adx') {
      var adxLine = _rsiChart.addLineSeries({ color: '#f0b940', lineWidth: 1.5, priceLineVisible: false });
      var adxData = [];
      for (var i = 0; i < bars.length; i++) {
        if (bars[i].adx != null) adxData.push({ time: bars[i].time, value: bars[i].adx });
      }
      adxLine.setData(adxData);
      adxLine.createPriceLine({ price: 25, color: 'rgba(91,141,239,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    }

    _rsiChart.timeScale().fitContent();

    // Sync crosshair between main and sub chart
    if (_mainChart && _rsiChart) {
      _mainChart.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
        if (range) _rsiChart.timeScale().setVisibleLogicalRange(range);
      });
      _rsiChart.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
        if (range) _mainChart.timeScale().setVisibleLogicalRange(range);
      });
    }
  }

  function renderChartConfig(data) {
    var configEl = _el('chart-config');
    if (!configEl) return;
    var config = data.config || {};
    var chips = [];

    if (config.rsi_period) chips.push('RSI(' + config.rsi_period + ')');
    if (config.rsi_oversold && config.rsi_overbought) chips.push(config.rsi_oversold + '/' + config.rsi_overbought + ' levels');
    if (config.bb_period) chips.push('BB(' + config.bb_period + ', ' + (config.bb_mult || 2.0) + ')');
    if (config.ema_fast_period) chips.push('EMA(' + config.ema_fast_period + '/' + config.ema_slow_period + ')');
    if (config.adx_period) chips.push('ADX(' + config.adx_period + ')');
    if (config.sl_pips) chips.push('SL: ' + config.sl_pips + ' pips');
    if (config.tp_pips) chips.push('TP: ' + config.tp_pips + ' pips');

    var html = '';
    for (var i = 0; i < chips.length; i++) {
      html += '<span class="bot-config-chip">' + chips[i] + '</span>';
    }
    configEl.innerHTML = html;
  }

  // ── Range Filter ────────────────────────────────────────────

  function setRange(days) {
    _rangeDays = days;
    var chips = document.querySelectorAll('.bot-range-chip');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('bot-range-active', parseInt(chips[i].getAttribute('data-days')) === days);
    }
    if (_chartRawData) {
      var pair = _el('chart-pair-name');
      if (pair) renderCandlestickChart(_chartRawData, pair.textContent);
    }
  }

  // ── Main Render ─────────────────────────────────────────────

  function renderAll(d) {
    _dashboardData = d;
    var renders = [
      function() { renderStatus(d); },
      function() { renderCards(d); },
      function() { renderPerformance(d); },
      function() { renderPositions(d); },
      function() { renderHistory(d); },
      function() { renderEquityChart(d); },
      function() { renderSignalGrid(d); },
      function() { renderHeatmap(); },
    ];
    for (var i = 0; i < renders.length; i++) {
      try { renders[i](); } catch (e) { console.warn('Bot render error #' + i + ':', e); }
    }
  }

  // ── Data Loading ────────────────────────────────────────────

  function loadData() {
    safeFetch(_config.apiPath + '/dashboard.json').then(function(r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function(d) {
      renderAll(d);
    }).catch(function(e) {
      console.error('Dashboard load failed:', e);
      var statusEl = _el('status');
      if (statusEl) statusEl.textContent = 'Connection error';
      var dotEl = _el('dot');
      if (dotEl) dotEl.className = 'bot-status-dot red';
    });
  }

  // ── Public API ──────────────────────────────────────────────

  function init(config) {
    // Merge config
    for (var key in config) {
      if (config.hasOwnProperty(key)) {
        if (key === 'features' && typeof config[key] === 'object') {
          for (var f in config[key]) {
            if (config[key].hasOwnProperty(f)) _config.features[f] = config[key][f];
          }
        } else if (key === 'indicators' && typeof config[key] === 'object') {
          for (var ind in config[key]) {
            if (config[key].hasOwnProperty(ind)) _config.indicators[ind] = config[key][ind];
          }
        } else {
          _config[key] = config[key];
        }
      }
    }

    // Initial load
    loadData();

    // Auto-refresh
    setInterval(loadData, _config.refreshInterval * 1000);
  }

  return {
    init: init,
    showChart: showChart,
    hideChart: hideChart,
    setRange: setRange,
    loadData: loadData,
  };
})();
