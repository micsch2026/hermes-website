#!/usr/bin/env python3
"""
Hermes Site Builder — Single Source of Truth for Navigation
Generates all HTML pages from templates + data.
Usage: python3 build.py
"""
import json, os, re, subprocess, sys

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SITE_DIR, 'src')
DATA_DIR = os.path.join(SRC_DIR, 'data')
TMPL_DIR = os.path.join(SRC_DIR, 'templates')
CONTENT_DIR = os.path.join(SRC_DIR, 'content')

# Load base template
with open(os.path.join(TMPL_DIR, 'base.html'), 'r') as f:
    BASE_TMPL = f.read()

# Load nav data
with open(os.path.join(DATA_DIR, 'nav.json'), 'r') as f:
    NAV_DATA = json.load(f)

# Icons (simplified SVG paths)
ICONS = {
    'home': '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'
}

THEME_TOGGLE_HTML = '''<button id="theme-toggle" aria-label="Theme wechseln" title="Theme wechseln" style="background:none;border:none;cursor:pointer;color:var(--c-text-muted);padding:var(--s-2);border-radius:var(--r-sm);display:flex;align-items:center;margin-left:auto;transition:color var(--t)">
    <svg id="icon-sun" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="display:none"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
    <svg id="icon-moon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
  </button>'''

THEME_SCRIPT = '''<script>
(function(){
  var btn = document.getElementById('theme-toggle');
  var iconSun = document.getElementById('icon-sun');
  var iconMoon = document.getElementById('icon-moon');
  function setTheme(t){
    document.documentElement.className = t;
    localStorage.setItem('theme', t);
    if(iconSun) iconSun.style.display = t === 'dark' ? 'none' : 'block';
    if(iconMoon) iconMoon.style.display = t === 'dark' ? 'block' : 'none';
  }
  var current = localStorage.getItem('theme') || 'dark';
  setTheme(current);
  if(btn) btn.addEventListener('click', function(){
    current = current === 'dark' ? 'light' : 'dark';
    setTheme(current);
  });
})();
</script>'''

# ── Widget Engine ───────────────────────────────────────────────

def icon_html(name):
    return f'<i data-lucide="{name}" style="width:16px;height:16px;vertical-align:middle;margin-right:6px"></i>' if name else ''

WIDGET_HTML = {
    'status-bar': lambda w: f'''
  <div class="refresh-bar" id="widget-{w['id']}">
    <div>
      <span class="status-dot" id="conn-dot"></span>
      <span id="conn-status">Lade...</span>
      <span class="badge" id="mode-badge" style="margin-left:8px"></span>
      <span class="badge" id="risk-badge" style="margin-left:4px; display:none"></span>
    </div>
    <span id="last-update"><i data-lucide="refresh-cw" style="width:12px;height:12px"></i> lade...</span>
  </div>''',

    'phase-card': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div class="card" id="widget-{w['id']}">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--s-3);">
      <span class="card-title">Phase</span>
      <span class="badge" id="phase-badge">Lade...</span>
    </div>
    <div class="card-value" id="phase-name">—</div>
    <div class="card-sub" id="phase-desc">—</div>
    <div class="progress" style="margin-top:var(--s-3);"><div class="progress-fill" id="phase-progress" style="width:0%"></div></div>
    <div class="card-sub" id="phase-count" style="margin-top:var(--s-1);">—</div>
  </div>''',

    'metric-grid': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div class="grid" id="widget-{w['id']}"></div>''',

    'mc-analysis': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div id="widget-{w['id']}">
    <div class="alert-box" id="mc-alert">
      <i data-lucide="info" style="width:14px;height:14px;vertical-align:middle;margin-right:4px"></i>
      Noch nicht genug Trades für statistisch signifikante Monte Carlo Analyse. Mindestens 10 Roundtrips nötig.
    </div>
  </div>''',

    'benchmark': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div class="grid grid-3" id="widget-{w['id']}">
    <div class="card"><div class="card-title">Bot P&L</div><div class="card-value" id="bench-bot">—</div></div>
    <div class="card"><div class="card-title">Buy &amp; Hold</div><div class="card-value" id="bench-bh">—</div></div>
    <div class="card"><div class="card-title">Outperformance</div><div class="card-value" id="bench-diff">—</div></div>
  </div>''',

    'asset-table': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div id="widget-{w['id']}"><span class="no-data">Lade...</span></div>''',

    'price-table': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div class="card" id="widget-{w['id']}">
    <table>
      <thead><tr><th>Symbol</th><th>Bid</th><th>Ask</th><th>Spread</th><th>Letztes Update</th></tr></thead>
      <tbody id="spots-body"><tr><td colspan="5" class="no-data">Lade...</td></tr></tbody>
    </table>
  </div>''',

    'trade-log': lambda w: f'''
  <p class="section-title">{icon_html(w.get('icon'))}{w.get('title','')}</p>
  <div class="card" id="widget-{w['id']}">
    <table>
      <thead><tr><th>Zeit</th><th>Symbol</th><th>Seite</th><th>Preis</th><th>Volumen</th><th>Kommentar</th></tr></thead>
      <tbody id="trades-body"><tr><td colspan="6" class="no-data">Keine Trades</td></tr></tbody>
    </table>
  </div>''',
}

WIDGET_JS = {
    'status-bar': lambda w: '''
    const connected = d.ctrader && d.ctrader.connected;
    const auth = d.ctrader && d.ctrader.authenticated;
    const dot = document.getElementById('conn-dot');
    if (auth) { dot.className = 'status-dot green'; document.getElementById('conn-status').textContent = 'cTrader verbunden'; }
    else if (connected) { dot.className = 'status-dot yellow'; document.getElementById('conn-status').textContent = 'cTrader Auth ausstehend'; }
    else { dot.className = 'status-dot red'; document.getElementById('conn-status').textContent = 'cTrader offline'; }
    const modeBadge = document.getElementById('mode-badge');
    modeBadge.textContent = d.demo ? 'DEMO' : 'LIVE';
    modeBadge.className = 'badge ' + (d.demo ? 'badge-demo' : 'badge-live');
    if (d.risk && d.risk.blocked) {
      const rb = document.getElementById('risk-badge');
      rb.style.display = 'inline-block';
      rb.textContent = 'BLOCKED';
      rb.className = 'badge badge-blocked';
    }
    document.getElementById('last-update').innerHTML = '<i data-lucide="refresh-cw" style="width:12px;height:12px"></i> ' + formatTime(d.timestamp);''',

    'phase-card': lambda w: '''
    if (d.review_phase) {
      const rp = d.review_phase;
      document.getElementById('phase-name').textContent = rp.name || '—';
      document.getElementById('phase-desc').textContent = rp.per_trade || '—';
      document.getElementById('phase-count').textContent = (rp.trade_count || 0) + ' Trades';
      const pb = document.getElementById('phase-badge');
      pb.textContent = 'Phase ' + (rp.phase || '?');
      pb.className = 'badge badge-phase' + (rp.phase || 1);
      let target = rp.phase === 1 ? 30 : rp.phase === 2 ? 100 : 999;
      let pct = Math.min(100, ((rp.trade_count || 0) / target) * 100);
      document.getElementById('phase-progress').style.width = pct + '%';
    }''',

    'metric-grid': lambda w: _metric_grid_js(w),

    'mc-analysis': lambda w: '''
    const sec = document.getElementById('widget-''' + w['id'] + '''');
    if (d.warning) {
      sec.innerHTML = '<div class="alert-box"><i data-lucide="info" style="width:14px;height:14px;vertical-align:middle;margin-right:4px"></i>' + d.warning + '</div>';
    } else {
      const mcd = d.monte_carlo || {};
      const mcm = mcd.monte_carlo || {};
      const prob = mcm.prob_profit_pct || 0;
      const probClass = prob >= 70 ? 'green' : prob >= 55 ? 'yellow' : 'red';
      sec.innerHTML = '<div class="mc-box">' +
        '<div class="mc-bar"><span class="mc-bar-label">Prob. Gewinn</span><div class="mc-bar-track"><div class="mc-bar-fill ' + probClass + '" style="width:' + Math.min(100, prob) + '%"></div><span class="mc-bar-value">' + prob + '%</span></div></div>' +
        '<div class="mc-bar"><span class="mc-bar-label">Median Equity</span><div class="mc-bar-track"><div class="mc-bar-fill green" style="width:70%"></div><span class="mc-bar-value">€' + (mcm.final_equity_median || '—') + '</span></div></div>' +
        '<div class="mc-bar"><span class="mc-bar-label">Worst Case (5%)</span><div class="mc-bar-track"><div class="mc-bar-fill red" style="width:30%"></div><span class="mc-bar-value">€' + (mcm.final_equity_5th || '—') + '</span></div></div>' +
        '<div class="mc-bar"><span class="mc-bar-label">Max Drawdown</span><div class="mc-bar-track"><div class="mc-bar-fill yellow" style="width:50%"></div><span class="mc-bar-value">' + (mcm.max_drawdown_median_pct || '—') + '%</span></div></div>' +
        '<div class="card-sub" style="margin-top:var(--s-3)">' + (mcd.interpretation || '') + '</div>' +
        '</div>';
    }''',

    'benchmark': lambda w: '''
    if (d.benchmark) {
      const b = d.benchmark;
      document.getElementById('bench-bot').innerHTML = b.bot_total_pnl != null ? pnlFmt(b.bot_total_pnl) : '—';
      document.getElementById('bench-bh').innerHTML = b.buyhold_total_pnl != null ? pnlFmt(b.buyhold_total_pnl) : '—';
      const diff = b.outperformance;
      document.getElementById('bench-diff').innerHTML = diff != null ? '<span class="' + pnlClass(diff) + '">' + pnlFmt(diff) + '</span>' : '—';
    }''',

    'asset-table': lambda w: '''
    const sec = document.getElementById('widget-''' + w['id'] + '''');
    if (d.assets && d.assets.length > 0) {
      let html = '<div class="card"><table><thead><tr><th>Asset</th><th>Score</th><th>Typ</th><th>Tradeable</th></tr></thead><tbody>';
      for (const asset of d.assets) {
        const typeClass = asset.type === 'forex' ? 'asset-forex' : asset.type === 'crypto' ? 'asset-crypto' : 'asset-stock';
        html += '<tr><td><b>' + asset.name + '</b></td><td>' + asset.score + '/100</td><td><span class="asset-tag ' + typeClass + '">' + asset.type + '</span></td><td>' + (asset.score >= 70 ? '<span class="badge badge-ok" style="background:rgba(63,185,80,0.15);color:var(--c-ok)">JA</span>' : '<span class="badge" style="background:rgba(248,81,73,0.15);color:var(--c-err)">NEIN</span>') + '</td></tr>';
      }
      html += '</tbody></table></div>';
      sec.innerHTML = html;
    } else {
      sec.innerHTML = '<span class="no-data">Keine Assets ausgewählt</span>';
    }''',

    'price-table': lambda w: '''
    let html = '';
    for (const sym in d) {
      const dd = d[sym];
      html += '<tr><td><b>' + sym + '</b></td><td>' + (dd.bid != null ? dd.bid.toFixed(5) : '—') + '</td><td>' + (dd.ask != null ? dd.ask.toFixed(5) : '—') + '</td><td>' + (dd.spread_pips != null ? dd.spread_pips.toFixed(1) : '—') + '</td><td>' + fmtDate(dd.timestamp) + '</td></tr>';
    }
    document.getElementById('spots-body').innerHTML = html || '<tr><td colspan="5" class="no-data">Keine Preisdaten</td></tr>';''',

    'trade-log': lambda w: '''
    if (d.trade_log && d.trade_log.length > 0) {
      let html = '';
      const seen = new Set();
      for (const t of d.trade_log.slice().reverse()) {
        if (!t.symbol || t.symbol === '0' || t.volume === 0) continue;
        const key = t.deal_id + '_' + t.timestamp;
        if (seen.has(key)) continue;
        seen.add(key);
        const sideBadge = t.side === 'BUY' ? '<span class="badge badge-demo">BUY</span>' : '<span class="badge badge-live">SELL</span>';
        html += '<tr><td>' + formatTime(t.timestamp) + '</td><td><b>' + t.symbol + '</b></td><td>' + sideBadge + '</td><td>' + (t.price || '—') + '</td><td>' + (t.volume || '—') + '</td><td>' + (t.comment || '') + '</td></tr>';
      }
      document.getElementById('trades-body').innerHTML = html || '<tr><td colspan="6" class="no-data">Keine validen Trades</td></tr>';
    } else {
      document.getElementById('trades-body').innerHTML = '<tr><td colspan="6" class="no-data">Keine Trades</td></tr>';
    }''',
}

def _metric_grid_js(widget):
    field = widget.get('field', '')
    wid = widget['id']
    if field == 'account':
        return f'''
    let html = '';
    html += '<div class="card"><div class="card-title">Balance</div><div class="card-value">' + (d.balance != null ? '€' + d.balance.toFixed(2) : '—') + '</div></div>';
    html += '<div class="card"><div class="card-title">TWR (Time-Weighted)</div><div class="card-value">' + (d.cashflow && d.cashflow.twr_pct != null ? '<span class="' + pnlClass(d.cashflow.twr_pct) + '">' + (d.cashflow.twr_pct >= 0 ? '+' : '') + d.cashflow.twr_pct.toFixed(2) + '%</span>' : '—') + '</div></div>';
    html += '<div class="card"><div class="card-title">Realisiertes P&L</div><div class="card-value">' + (d.cashflow && d.cashflow.realized_pnl != null ? pnlFmt(d.cashflow.realized_pnl) : '—') + '</div></div>';
    html += '<div class="card"><div class="card-title">Symbole geladen</div><div class="card-value">' + (d.symbols_count != null ? d.symbols_count : '—') + '</div></div>';
    document.getElementById('widget-{wid}').innerHTML = html;'''
    elif field == 'performance':
        return f'''
    let html = '';
    if (d.performance) {{
      const p = d.performance;
      html += '<div class="card"><div class="card-title">Trades</div><div class="card-value">' + (p.total_trades || '—') + '</div><div class="card-sub">' + (p.wins || 0) + 'W / ' + (p.losses || 0) + 'L</div></div>';
      html += '<div class="card"><div class="card-title">Winrate</div><div class="card-value">' + (p.win_rate != null ? '<span class="' + (p.win_rate >= 50 ? 'pnl-pos' : 'pnl-neg') + '">' + p.win_rate.toFixed(1) + '%</span>' : '—') + '</div><div class="card-sub">Ziel: > 50%</div></div>';
      html += '<div class="card"><div class="card-title">Profit Factor</div><div class="card-value">' + (p.profit_factor != null ? (p.profit_factor >= 1.5 ? '<span class="pnl-pos">' + p.profit_factor.toFixed(2) + '</span>' : p.profit_factor.toFixed(2)) : '—') + '</div><div class="card-sub">Ziel: > 1.5</div></div>';
      html += '<div class="card"><div class="card-title">Max Drawdown</div><div class="card-value">' + (p.max_drawdown != null ? '<span class="' + (p.max_drawdown <= 10 ? 'pnl-pos' : 'pnl-neg') + '">' + p.max_drawdown.toFixed(2) + '%</span>' : '—') + '</div><div class="card-sub">Limit: 10%</div></div>';
      html += '<div class="card"><div class="card-title">Net P&L</div><div class="card-value">' + (p.total_pnl_net != null ? pnlFmt(p.total_pnl_net) : '—') + '</div><div class="card-sub" id="perf-costs-sub">—</div></div>';
      html += '<div class="card"><div class="card-title">Avg R:R</div><div class="card-value">' + (p.avg_rr != null ? '1:' + p.avg_rr.toFixed(2) : '—') + '</div><div class="card-sub">Ziel: >= 1:2</div></div>';
    }}
    document.getElementById('widget-{wid}').innerHTML = html;
    if (d.costs) {{
      const el = document.getElementById('perf-costs-sub');
      if (el) el.textContent = 'Kosten: €' + ((d.costs.spread_total || 0) + (d.costs.ki_total || 0)).toFixed(2);
    }}'''
    elif field == 'risk':
        return f'''
    let html = '';
    if (d.risk) {{
      const r = d.risk;
      html += '<div class="card"><div class="card-title">Daily P&L</div><div class="card-value">' + (r.daily_pnl != null ? pnlFmt(r.daily_pnl) : '—') + '</div><div class="card-sub">' + (r.daily_pnl_pct != null ? r.daily_pnl_pct.toFixed(2) + '%' : '—') + '</div></div>';
      html += '<div class="card"><div class="card-title">Trades Heute</div><div class="card-value">' + (r.trades_today != null ? r.trades_today : '—') + '</div><div class="card-sub">Limit: 20</div></div>';
      html += '<div class="card"><div class="card-title">Max Risk/Trade</div><div class="card-value">' + (r.max_risk_per_trade_pct != null ? r.max_risk_per_trade_pct + '%' : '—') + '</div><div class="card-sub">A-Setup: 3%</div></div>';
      html += '<div class="card"><div class="card-title">Daily Loss Limit</div><div class="card-value">' + (r.max_daily_loss != null ? '-€' + r.max_daily_loss.toFixed(2) : '—') + '</div><div class="card-sub">Verbleibend: €' + (r.max_daily_loss != null && r.daily_pnl != null ? (r.max_daily_loss + r.daily_pnl).toFixed(2) : '—') + '</div></div>';
    }}
    document.getElementById('widget-{wid}').innerHTML = html;'''
    elif field == 'costs':
        return f'''
    let html = '';
    if (d.costs) {{
      const c = d.costs;
      html += '<div class="card"><div class="card-title">Spread gesamt</div><div class="card-value">€' + (c.spread_total || 0).toFixed(2) + '</div></div>';
      html += '<div class="card"><div class="card-title">KI-Analysen</div><div class="card-value">€' + (c.ki_total || 0).toFixed(2) + '</div></div>';
      html += '<div class="card"><div class="card-title">KI/Monat (gesch.)</div><div class="card-value">€' + (c.ki_estimated_monthly || 0).toFixed(2) + '</div></div>';
      html += '<div class="card"><div class="card-title">Steuer</div><div class="card-value" style="font-size:var(--text-base)">26.375%</div><div class="card-sub">Pepperstone auto</div></div>';
    }}
    document.getElementById('widget-{wid}').innerHTML = html;'''
    return f'// unknown metric-grid field: {field}'


def build_nav(current_path):
    """Build navigation HTML with active link highlighted."""
    current = current_path.replace('.html', '')
    if current.endswith('/index'):
        current = current[:-5] or '/'
    if current == 'index':
        current = '/'

    parts = ['<nav class="nav" aria-label="Hauptnavigation">']
    for link in NAV_DATA['links']:
        href = link['href']
        label = link['label']
        icon = link.get('icon')

        is_active = False
        if href == '/' and current == '/':
            is_active = True
        elif href != '/' and (current == href or current.startswith(href + '/')):
            is_active = True

        attrs = ' aria-current="page"' if is_active else ''

        if icon and icon in ICONS:
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</svg>'
            parts.append(f'  <a href="{href}"{attrs}>{svg}\n    {label}\n  </a>')
        else:
            parts.append(f'  <a href="{href}"{attrs}>{label}</a>')

    if len(parts) > 1:
        parts.insert(2, '  <span class="sep" aria-hidden="true">\u00b7</span>')

    parts.append(THEME_TOGGLE_HTML)
    parts.append('</nav>')
    parts.append(THEME_SCRIPT)
    return '\n'.join(parts)


def parse_content_file(path):
    """Parse a content fragment file into title, extra_head, body."""
    with open(path, 'r') as f:
        raw = f.read()

    title_match = re.search(r'<!--TITLE:(.*?)-->', raw)
    title = title_match.group(1).strip() if title_match else 'Hermes'

    head_match = re.search(r'<!--HEAD-->(.*?)<!--/HEAD-->', raw, re.DOTALL)
    extra_head = head_match.group(1).strip() if head_match else ''

    body_match = re.search(r'<!--BODY-->(.*?)<!--/BODY-->', raw, re.DOTALL)
    body = body_match.group(1).strip() if body_match else raw

    data_match = re.search(r'<!--DATA:(.+?)-->', body)
    if data_match:
        data_path = data_match.group(1).strip()
        full_data_path = os.path.join(SITE_DIR, data_path.lstrip('/'))
        if os.path.exists(full_data_path):
            with open(full_data_path, 'r') as df:
                data_content = df.read()
            json.loads(data_content)
            data_script = '<script>window.__DATA__ = ' + data_content + ';</script>\n'
            body = body.replace(data_match.group(0), '')
            script_match = re.search(r'<script', body)
            if script_match:
                pos = script_match.start()
                body = body[:pos] + data_script + body[pos:]
            else:
                body = body + '\n' + data_script
        else:
            print(f'  WARN: Data file not found: {full_data_path}')

    return title, extra_head, body


def build_page(content_path, out_path):
    """Render a single page."""
    rel = os.path.relpath(content_path, CONTENT_DIR)
    web_path = '/' + rel.replace('.html', '')
    if web_path.endswith('/index'):
        web_path = web_path[:-5] or '/'
    if web_path == '/index':
        web_path = '/'

    title, extra_head, body = parse_content_file(content_path)
    nav_html = build_nav(web_path)

    html = BASE_TMPL \
        .replace('{{title}}', title) \
        .replace('{{extra_head}}', extra_head) \
        .replace('{{nav}}', nav_html) \
        .replace('{{content}}', body)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(html)
    print(f'  Built {out_path} (path={web_path})')


# ── Widget Page Generator ───────────────────────────────────────

def build_widget_page(config_path, out_content_path):
    """Generate a content HTML file from a sections.json config."""
    with open(config_path, 'r') as f:
        cfg = json.load(f)

    page_title = cfg.get('title', 'Hermes')
    refresh = cfg.get('refresh_interval', 30)
    data_sources = cfg.get('data_sources', {})
    sections = cfg.get('sections', [])

    # Build HTML
    html_parts = ['<div class="container">']
    for w in sections:
        wtype = w.get('type', '')
        if wtype in WIDGET_HTML:
            html_parts.append(WIDGET_HTML[wtype](w))
        else:
            html_parts.append(f'<!-- Unknown widget type: {wtype} -->')
    html_parts.append('</div>')
    body_html = '\n'.join(html_parts)

    # Build JS data loading
    ds_js = []
    for key, path in data_sources.items():
        ds_js.append(f'''
    try {{
      const r{key} = await safeFetch('{path}');
      if (r{key}.ok) data['{key}'] = await r{key}.json();
    }} catch(e) {{ console.warn('Failed to load {key}:', e); }}''')

    # Build JS rendering
    render_js = []
    for w in sections:
        wtype = w.get('type', '')
        ds = w.get('data_source', 'status')
        wid = w['id']
        if wtype in WIDGET_JS:
            renderer = WIDGET_JS[wtype](w)
            render_js.append(f'''
    try {{
      const d = data['{ds}'];
      if (d) {{
        {renderer}
      }}
    }} catch(e) {{ console.warn('Widget {wid} render error:', e); }}''')

    full_js = '\n'.join(ds_js) + '\n' + '\n'.join(render_js)

    content = f'''<!--TITLE:{page_title} — Hermes-->
<!--HEAD-->
<style>
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--s-4); margin-bottom: var(--s-6); }}
  .grid-3 {{ grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
  .card {{ background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-xl); padding: var(--s-5); }}
  .card-title {{ font-weight: 600; font-size: var(--text-sm); color: var(--c-text-dim); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: var(--s-3); }}
  .card-value {{ font-size: var(--text-2xl); font-weight: 700; }}
  .card-sub {{ font-size: var(--text-sm); color: var(--c-text-dim); margin-top: var(--s-1); }}

  .status-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: var(--s-2); }}
  .status-dot.green {{ background: var(--c-ok); box-shadow: 0 0 6px var(--c-ok); }}
  .status-dot.yellow {{ background: var(--c-warn); }}
  .status-dot.red {{ background: var(--c-err); }}
  .status-dot.gray {{ background: var(--c-text-dim); }}

  .badge {{ display: inline-block; padding: 2px 10px; border-radius: var(--r-lg); font-size: var(--text-xs); font-weight: 600; }}
  .badge-phase1 {{ background: rgba(210,153,34,0.15); color: var(--c-warn); }}
  .badge-phase2 {{ background: rgba(100,149,237,0.15); color: #6495ed; }}
  .badge-phase3 {{ background: rgba(63,185,80,0.15); color: var(--c-ok); }}
  .badge-demo {{ background: rgba(100,149,237,0.15); color: #6495ed; }}
  .badge-live {{ background: rgba(63,185,80,0.15); color: var(--c-ok); }}
  .badge-blocked {{ background: rgba(248,81,73,0.15); color: var(--c-err); }}

  .progress {{ height: 8px; border-radius: 4px; background: var(--c-border); overflow: hidden; margin-top: var(--s-2); }}
  .progress-fill {{ height: 100%; border-radius: 4px; background: var(--c-accent); transition: width 0.3s; }}

  table {{ width: 100%; border-collapse: collapse; font-size: var(--text-sm); }}
  th {{ text-align: left; color: var(--c-text-dim); font-weight: 600; padding: var(--s-2) var(--s-3); border-bottom: 1px solid var(--c-border); font-size: var(--text-xs); text-transform: uppercase; }}
  td {{ padding: var(--s-2) var(--s-3); border-bottom: 1px solid var(--c-border); }}
  tr:last-child td {{ border-bottom: none; }}

  .section-title {{ font-size: var(--text-lg); font-weight: 600; margin: var(--s-8) 0 var(--s-4); color: var(--c-text); border-bottom: 1px solid var(--c-border); padding-bottom: var(--s-2); }}
  .section-title:first-of-type {{ margin-top: var(--s-6); }}

  .no-data {{ color: var(--c-text-dim); font-style: italic; padding: var(--s-4); }}
  .pnl-pos {{ color: var(--c-ok); }}
  .pnl-neg {{ color: var(--c-err); }}

  .refresh-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--s-4); flex-wrap: wrap; gap: var(--s-2); }}
  #last-update {{ color: var(--c-text-dim); font-size: var(--text-xs); }}

  .mc-box {{ background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-xl); padding: var(--s-5); }}
  .mc-bar {{ display: flex; align-items: center; gap: var(--s-3); margin: var(--s-2) 0; }}
  .mc-bar-label {{ width: 120px; font-size: var(--text-sm); color: var(--c-text-dim); }}
  .mc-bar-track {{ flex: 1; height: 20px; border-radius: var(--r-sm); background: var(--c-border); position: relative; overflow: hidden; }}
  .mc-bar-fill {{ height: 100%; border-radius: var(--r-sm); }}
  .mc-bar-fill.green {{ background: rgba(63,185,80,0.3); }}
  .mc-bar-fill.yellow {{ background: rgba(210,153,34,0.3); }}
  .mc-bar-fill.red {{ background: rgba(248,81,73,0.3); }}
  .mc-bar-value {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; align-items: center; justify-content: center; font-size: var(--text-xs); font-weight: 600; }}

  .asset-tag {{ display: inline-block; padding: 2px 8px; border-radius: var(--r-lg); font-size: var(--text-xs); margin-right: 4px; }}
  .asset-forex {{ background: rgba(100,149,237,0.15); color: #6495ed; }}
  .asset-crypto {{ background: rgba(210,153,34,0.15); color: var(--c-warn); }}
  .asset-stock {{ background: rgba(63,185,80,0.15); color: var(--c-ok); }}

  .stat-row {{ display: flex; justify-content: space-between; padding: var(--s-2) 0; border-bottom: 1px solid var(--c-border); }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-label {{ color: var(--c-text-dim); font-size: var(--text-sm); }}
  .stat-value {{ font-weight: 600; font-size: var(--text-sm); }}

  .alert-box {{ background: rgba(210,153,34,0.08); border: 1px solid rgba(210,153,34,0.2); border-radius: var(--r-lg); padding: var(--s-3) var(--s-4); margin-bottom: var(--s-4); }}
  .alert-box.err {{ background: rgba(248,81,73,0.08); border-color: rgba(248,81,73,0.2); }}
  .alert-box.ok {{ background: rgba(63,185,80,0.08); border-color: rgba(63,185,80,0.2); }}
</style>
<!--/HEAD-->
<!--BODY-->
{body_html}
<script>
function safeFetch(path, opts) {{
  var url = new URL(path, window.location.origin);
  return fetch(url.href, opts);
}}
function formatTime(iso) {{
  if (!iso) return '—';
  try {{ return new Date(iso).toLocaleString('de-DE', {{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}}); }} catch(e) {{ return iso; }}
}}
function fmtDate(iso) {{
  if (!iso) return '—';
  try {{ return new Date(iso).toLocaleDateString('de-DE'); }} catch(e) {{ return iso; }}
}}
function pnlClass(v) {{ return v >= 0 ? 'pnl-pos' : 'pnl-neg'; }}
function pnlFmt(v) {{ if (v == null) return '—'; return (v >= 0 ? '+' : '') + v.toFixed(2) + ' €'; }}

async function loadAll() {{
  const data = {{}};
{full_js}
  if (typeof lucide !== 'undefined') lucide.createIcons();
}}

loadAll();
setInterval(loadAll, {refresh}000);
</script>
<!--/BODY-->'''

    os.makedirs(os.path.dirname(out_content_path), exist_ok=True)
    with open(out_content_path, 'w') as f:
        f.write(content)
    print(f'  Generated widget page {out_content_path}')


# ── Git helpers ─────────────────────────────────────────────────

def git_auto_push():
    """Auto-commit and push changes if git repo exists."""
    git_dir = os.path.join(SITE_DIR, '.git')
    if not os.path.isdir(git_dir):
        print('  [git] No repo found, skipping auto-push')
        return

    try:
        # Check if there are changes
        result = subprocess.run(
            ['git', '-C', SITE_DIR, 'status', '--porcelain'],
            capture_output=True, text=True, check=True
        )
        if not result.stdout.strip():
            print('  [git] No changes to commit')
            return

        # Add all changes
        subprocess.run(['git', '-C', SITE_DIR, 'add', '-A'], check=True, capture_output=True)

        # Commit with timestamp
        ts = subprocess.run(['date', '+%Y-%m-%d %H:%M:%S'], capture_output=True, text=True).stdout.strip()
        subprocess.run(
            ['git', '-C', SITE_DIR, 'commit', '-m', f'Auto-build: {ts}'],
            check=True, capture_output=True
        )
        print(f'  [git] Committed: Auto-build: {ts}')

        # Push
        push_result = subprocess.run(
            ['git', '-C', SITE_DIR, 'push', 'origin', 'main'],
            capture_output=True, text=True
        )
        if push_result.returncode == 0:
            print('  [git] Pushed to origin/main')
        else:
            print(f'  [git] Push failed: {push_result.stderr.strip()}')

    except subprocess.CalledProcessError as e:
        print(f'  [git] Error: {e}')
    except FileNotFoundError:
        print('  [git] git not found in PATH')


# ── Main ────────────────────────────────────────────────────────

def main():
    print('Building Hermes site...')

    # 1. Generate widget pages from sections.json configs
    for root, dirs, files in os.walk(os.path.join(SITE_DIR, 'content')):
        for fname in files:
            if fname != 'sections.json':
                continue
            config_path = os.path.join(root, fname)
            # Determine output path: content/<page>/sections.json -> src/content/<page>.html
            rel_dir = os.path.relpath(root, os.path.join(SITE_DIR, 'content'))
            out_path = os.path.join(CONTENT_DIR, rel_dir + '.html')
            build_widget_page(config_path, out_path)

    # 2. Build all content files
    for root, dirs, files in os.walk(CONTENT_DIR):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            content_path = os.path.join(root, fname)
            rel = os.path.relpath(content_path, CONTENT_DIR)
            out_path = os.path.join(SITE_DIR, rel)
            build_page(content_path, out_path)

    # 3. Auto git push
    git_auto_push()

    print('Done.')


if __name__ == '__main__':
    main()
