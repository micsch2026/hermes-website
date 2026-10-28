#!/usr/bin/env python3
"""
build_bot_pages.py — ONE builder for ALL bot dashboard pages.

Reads template + per-bot JSON config → generates content HTML files
that build.py can process into final pages.

Struktur (Cockpit 23.10.2026 — EIN Template für alle Bots):
  - Kopf: Dot/Status/Mode/Fokus/ECHTGELD + eine Aktions-Zeile (Handlungsbedarf)
  - Kontokarten: ALLE Konten (Echtgeld + Demo) mit Sparkline/Kapitalbewegungen
  - Equity: indexiert auf Kontostart (umschaltbar Demo/Echtgeld absolut)
  - Offene Positionen · Historie (10 Zeilen, Filter, „alle")
  - Strategie-Board: Belegung, Zeile je Slot (account-scharfe PnL), Balken
  - Details (Akkordeon): Assets, Parität, Mandat, Slot-Karten/Radar/Historie, Lab
Daten: dashboard.json `accounts[]` + `slots[].stats.by_account` (fx-bot).
Die frühere Karten-IA (11.10.2026) lebt nur noch im Details-Akkordeon.

Usage:
    python3 build_bot_pages.py              # build all bots
    python3 build_bot_pages.py bot1         # build only Bot #1
    python3 build_bot_pages.py bot2         # build only Bot #2

Output:
    /root/.hermes/site/src/content/bot1.html
    /root/.hermes/site/src/content/bot2.html
    (and any future bots added to data/bots/*.json)
"""

import json
import os
import re
import sys
import glob

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
TMPL_DIR = os.path.join(SITE_DIR, 'src', 'templates')
DATA_DIR = os.path.join(SITE_DIR, 'src', 'data')
BOTS_DIR = os.path.join(DATA_DIR, 'bots')
CONTENT_DIR = os.path.join(SITE_DIR, 'src', 'content')

TEMPLATE_FILE = os.path.join(TMPL_DIR, 'bot.html')


def load_template():
    """Load the bot dashboard template."""
    with open(TEMPLATE_FILE, 'r') as f:
        return f.read()


def load_config(bot_id):
    """Load a bot's JSON config."""
    path = os.path.join(BOTS_DIR, f'{bot_id}.json')
    if not os.path.exists(path):
        raise FileNotFoundError(f'Bot config not found: {path}')
    with open(path, 'r') as f:
        return json.load(f)


def find_all_configs():
    """Discover all bot configs."""
    configs = []
    for path in sorted(glob.glob(os.path.join(BOTS_DIR, '*.json'))):
        with open(path, 'r') as f:
            configs.append(json.load(f))
    return configs


def build_short_name(config):
    """Kurzer Anzeigename für den Cockpit-Kopf (ohne Klammern/„— Hermes")."""
    nm = str(config.get('name') or config.get('bot_id') or 'Bot')
    nm = nm.replace(' — Hermes', '').strip()
    nm = re.sub(r'\s*\([^()]*\)\s*$', '', nm).strip()
    return nm or str(config.get('bot_id') or 'Bot')


def build_meta_chips(chips):
    """Bot-Steckbrief: kompakte Chips (bot-level Fakten, je Fakt genau 1×)."""
    parts = []
    for chip in chips or []:
        parts.append(f'    <span class="bot-config-chip">{chip}</span>')
    return '\n'.join(parts)


def build_focus_badge(config):
    """Fokus-Badge (12.10.2026, User): Assetklassen-Fokus sofort sichtbar.
    Quelle: botN.json → focus {label, icon}; SSOT der Klassen = rotation_policy targets."""
    f = config.get("focus") or {}
    label = str(f.get("label") or "").strip()
    if not label:
        return ""
    icon = str(f.get("icon") or "").strip()
    txt = f"{icon} {label}".strip()
    return ('<span class="bot-focus-badge" style="background:rgba(120,180,255,0.14);'
            'border:1px solid rgba(120,180,255,0.35);color:#7ab4ff;border-radius:999px;'
            'padding:2px 10px;font-size:var(--text-xs);font-weight:700;white-space:nowrap">'
            f'{txt}</span>')


def build_live_badge(config):
    """ECHTGELD-Badge (16.10.2026, User): Bots mit Echtgeld-Handel sofort sichtbar.
    Quelle: botN.json → live_badge {label, icon, detail}; detail als Tooltip.
    Nur setzen, wenn der Bot (teilweise) auf Echtgeld-Konten handelt."""
    lb = config.get("live_badge") or {}
    label = str(lb.get("label") or "").strip()
    if not label:
        return ""
    icon = str(lb.get("icon") or "").strip()
    detail = str(lb.get("detail") or "").strip()
    title = f' title="{detail}"' if detail else ""
    txt = f"{icon} {label}".strip()
    return ('<span class="bot-live-badge" style="background:rgba(240,185,64,0.14);'
            'border:1px solid rgba(240,185,64,0.45);color:#f0b940;border-radius:999px;'
            'padding:2px 10px;font-size:var(--text-xs);font-weight:700;white-space:nowrap"'
            f'{title}>'
            f'{txt}</span>')


def build_multi_intro_section(config):
    """Konzept & Regeln des Bots — statischer Text je Bot (botN.json `multi_intro`).

    Aufklappbar (details): erklärt das Slot-/Rotations-Modell des Bots. Leer für
    Bots ohne eigenen Text → Block entfällt (die Slots-Sektion selbst wird nur
    bei vorhandenen dashboard.slots sichtbar).
    """
    intro = (config.get('multi_intro') or '').strip()
    if not intro:
        return ''
    return (
        '<details style="margin-bottom:var(--s-3)">\n'
        '  <summary style="cursor:pointer;font-size:var(--text-xs);color:var(--c-text-dim);user-select:none">'
        '📘 Konzept &amp; Regeln dieses Bots ▸</summary>\n'
        '  <div style="font-size:var(--text-xs);color:var(--c-text-2);line-height:1.65;margin-top:var(--s-2);'
        'background:var(--c-surface-2);border:1px solid var(--c-border);border-left:3px solid #8b5cf6;'
        'border-radius:var(--r-md);padding:var(--s-3) var(--s-4)">🧩 ' + intro + '</div>\n'
        '</details>'
    )


def build_ausrichtung_section(config):
    """🎯 Ausrichtung & Mandat — obere Ebene je Bot (botN.json `ausrichtung`).

    Struktur: {type: produktiv|erprobung|erkundung, familie: [..], text: '...'}.
    Statischer Block (immer sichtbar wenn Text vorhanden), bewusst VOR der
    Slots-Sektion (Strategie-Details folgen dort). Ehrlichkeits-Regeln:
    keine Gewinnversprechen, Experimente kennzeichnen (Erkundung/Erprobung).
    """
    a = config.get('ausrichtung') or {}
    text = (a.get('text') or '').strip()
    if not text:
        return ''
    t = str(a.get('type') or 'produktiv').strip().lower()
    badge_icon, badge_label, badge_color = {
        'produktiv': ('✅', 'Produktiv', '#22c55e'),
        'erprobung': ('🧪', 'Erprobung (Demo, kein Live-Kandidat)', '#f59e0b'),
        'erkundung': ('🔭', 'Erkundung (Experiment-Frame)', '#8b5cf6'),
    }.get(t, ('✅', 'Produktiv', '#22c55e'))
    fams = a.get('familie') or []
    chips = ''.join(
        f'<span class="bot-config-chip" style="margin:0 6px 6px 0">{fam}</span>' for fam in fams
    )
    chips_html = f'<div style="margin-bottom:var(--s-2)">{chips}</div>' if chips else ''
    return (
        '<div class="bot-card" style="margin-bottom:var(--s-4);padding:var(--s-4)">\n'
        '  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--s-2);flex-wrap:wrap;gap:var(--s-2)">\n'
        '    <span style="font-weight:700;font-size:var(--text-md)">🎯 Ausrichtung &amp; Mandat</span>\n'
        f'    <span style="font-size:var(--text-xs);font-weight:600;color:{badge_color}">{badge_icon} {badge_label}</span>\n'
        '  </div>\n'
        + chips_html +
        f'  <div style="font-size:var(--text-sm);color:var(--c-text-2);line-height:1.65">{text}</div>\n'
        '</div>'
    )


def build_signal_section(features, bot_id):
    """Asset-Monitor: Live-Status je Paar + Asset-Performance (Heatmap-Widget).

    Review 11.10.: Die Heatmap bleibt ein EIGENES Widget innerhalb des
    Monitor-Bereichs (visuelle Scanbarkeit erhalten), statt in die Live-Karten
    eingeschmolzen zu werden.
    """
    if not features.get('signals', False):
        return ''
    html = f'''
<!-- 7. ASSET-MONITOR -->
<p class="bot-section-title">📡 Asset-Monitor</p>
<div class="bot-signal-grid" id="{bot_id}-signal-grid">
  <div class="bot-signal-card"><div class="bot-no-data">Loading signals...</div></div>
</div>'''
    if features.get('heatmap', False):
        html += f'''
<div style="margin-top:var(--s-3);border-top:1px solid var(--c-border);padding-top:var(--s-3)">
  <p class="bot-section-title" style="margin-top:0">🗺️ Asset-Performance <span style="color:var(--c-text-dim);font-weight:400;font-size:var(--text-xs)">(geschlossene Trades je Paar)</span></p>
  <div class="bot-heatmap-grid" id="{bot_id}-heatmap-grid">
    <div class="bot-no-data">Loading heatmap...</div>
  </div>
</div>'''
    return html


def build_candlestick_section(features, bot_id):
    """Generate candlestick chart panel if enabled."""
    if not features.get('candlestick', False):
        return ''
    return f'''
<!-- 6b. CANDLESTICK CHART PANEL -->
<div class="bot-chart-panel" id="{bot_id}-chart-panel">
  <div class="bot-chart-header">
    <div>
      <span class="bot-chart-pair-name" id="{bot_id}-chart-pair">—</span>
      <span class="bot-badge bot-badge-signal" id="{bot_id}-chart-strategy" style="margin-left:8px"></span>
    </div>
    <div style="display:flex;gap:var(--s-2);align-items:center">
      <button id="{bot_id}-ind-toggle" class="bot-chart-close"
        onclick="BotDash.toggleIndicators()"
        style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.3)">
        📈 Indikatoren: ON
      </button>
      <button id="{bot_id}-trade-toggle" class="bot-chart-close"
        onclick="BotDash.toggleTradeLines()"
        style="background:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.3)">
        📊 Trades: ON
      </button>
      <button class="bot-chart-close" onclick="BotDash.closeChart()">✕ Close</button>
    </div>
  </div>
  <div class="bot-trade-focus" id="{bot_id}-trade-focus" style="display:none"></div>
  <div class="bot-pair-nav" id="{bot_id}-pair-nav"></div>
  <div class="bot-range-nav" id="{bot_id}-range-nav">
    <span class="bot-range-chip" data-days="0" onclick="BotDash.setRange(0)">All</span>
    <span class="bot-range-chip" data-days="14" onclick="BotDash.setRange(14)">14T</span>
    <span class="bot-range-chip" data-days="7" onclick="BotDash.setRange(7)">7T</span>
    <span class="bot-range-chip bot-range-active" data-days="3" onclick="BotDash.setRange(3)">3T</span>
    <span class="bot-range-chip" data-days="1" onclick="BotDash.setRange(1)">1T</span>
  </div>
  <div class="bot-chart-config" id="{bot_id}-chart-config"></div>
  <div class="bot-chart-legend" id="{bot_id}-chart-legend" style="display:flex;gap:var(--s-3);flex-wrap:wrap;margin-bottom:var(--s-2);font-size:var(--text-xs);color:var(--c-text-dim)">
    <span class="muted">Lade Chart…</span>
  </div>
  <div class="bot-level-legend" id="{bot_id}-level-legend" style="display:none"></div>
  <div class="bot-chart-wrap">
    <div id="{bot_id}-candle-chart" style="height:320px"></div>
    <div class="bot-trade-tooltip" id="{bot_id}-trade-tooltip"></div>
    <div class="bot-chart-rsi-label" id="{bot_id}-rsi-label">RSI</div>
    <div id="{bot_id}-rsi-chart" style="height:100px"></div>
  </div>
</div>'''


def build_reopt_block(config, bot_id):
    """Re-Opt-/Wartungs-Block für den Lab-Tab (Status + methoden-korrekte Anleitung)."""
    ro = config.get('reoptimize')
    if not ro:
        return ''
    last_date = ro.get('last_date', '')
    interval = ro.get('interval_months', 3)
    steps = ro.get('steps', []) or []
    timeframe = ro.get('timeframe', '?')
    data_months = ro.get('data_months', 6)
    method = ro.get('method', '')

    if steps:
        steps_html = ''
        for step in steps:
            if step.startswith('#'):
                steps_html += f'<div style="color:var(--c-text-dim);margin-top:var(--s-2)">{step}</div>\n'
            else:
                steps_html += (
                    f'<div style="display:flex;align-items:center;gap:var(--s-2);margin-top:var(--s-1)">'
                    f'<code style="flex:1;background:var(--c-bg);padding:6px 10px;border-radius:var(--r-sm);'
                    f'font-size:var(--text-xs);user-select:all">{step}</code>'
                    f'</div>\n'
                )
    else:
        # Kein handgeschriebener Ablauf → methoden-korrekte Standard-Anleitung.
        # (Früher stand hier „Grid-Search" — falsch für Tree-/Lab-Bots.)
        steps_html = (
            '<div style="margin-top:var(--s-2);line-height:1.6">'
            'Ablauf bei Fälligkeit: neue Variante über den <b>Strategy-Lab-Worker</b> rechnen '
            '(WFO-Gates) → <b>Shadow-Challenge</b> → bei Bestehen Slot-Fill durch die Rotation. '
            'Regeln am laufenden Bot (SL/TP/R:R) werden <b>NICHT</b> geändert.</div>'
        )

    return f'''
<p class="bot-section-title" style="margin-top:var(--s-4)">🔧 Re-Optimierung &amp; Wartung</p>
<div class="bot-card" id="{bot_id}-reopt-card" data-interval="{interval}">
  <div style="display:flex;align-items:center;gap:var(--s-3);margin-bottom:var(--s-3);flex-wrap:wrap">
    <div>
      <div style="font-size:var(--text-xs);color:var(--c-text-dim)">Letzte Optimierung</div>
      <div style="font-weight:600" id="{bot_id}-reopt-last">{last_date}</div>
    </div>
    <div style="font-size:1.5em" id="{bot_id}-reopt-icon">—</div>
    <div>
      <div style="font-size:var(--text-xs);color:var(--c-text-dim)">Nächste fällig</div>
      <div style="font-weight:600" id="{bot_id}-reopt-due">—</div>
    </div>
    <div>
      <div style="font-size:var(--text-xs);color:var(--c-text-dim)">Status</div>
      <div style="font-weight:600" id="{bot_id}-reopt-status">—</div>
    </div>
  </div>
  <div id="{bot_id}-reopt-banner" style="display:none;padding:var(--s-2) var(--s-3);border-radius:var(--r-sm);margin-bottom:var(--s-3);font-size:var(--text-sm)"></div>
  <details style="font-size:var(--text-xs)">
    <summary style="cursor:pointer;color:var(--c-text-dim);user-select:none">Anleitung — Was tun wenn fällig? ▸</summary>
    <div style="margin-top:var(--s-3)">
      <div style="margin-bottom:var(--s-2);color:var(--c-text-dim)">
        Methode: {method or '—'} · {timeframe}, {data_months}M Daten
      </div>
      {steps_html}
    </div>
  </details>
</div>'''


def build_lab_section(config, bot_id):
    """Lab-Referenz-Tab: Validierung je Strategie (JS-Fill aus shadow_portfolio.json),
    Backtest-Benchmark (nur sichtbar wenn dashboard.backtest Daten liefert) und
    Re-Opt-Status. Leere Blöcke bleiben ausgeblendet (keine „—"-Wüsten)."""
    ro = config.get('reoptimize', {})
    tf = ro.get('timeframe', '?')

    bench = f'''
<div id="{bot_id}-lab-bench" style="display:none;margin-bottom:var(--s-4)">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--s-3);flex-wrap:wrap;gap:var(--s-2)">
    <span style="font-weight:700;font-size:var(--text-md)">🧪 Backtest-Benchmark ({tf} WFO)</span>
    <span id="{bot_id}-bt-verdict" class="bot-badge bot-badge-signal" style="font-size:var(--text-xs)">—</span>
  </div>
  <div class="bot-grid" style="margin-bottom:var(--s-3)">
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">Backtest WR</div>
      <div class="bot-card-value" id="{bot_id}-bt-wr">—</div>
      <div class="bot-card-sub" id="{bot_id}-bt-wr-ci">Expected WR</div>
    </div>
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">Backtest PF</div>
      <div class="bot-card-value" id="{bot_id}-bt-pf">—</div>
      <div class="bot-card-sub" id="{bot_id}-bt-pf-sub">Profit Factor</div>
    </div>
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">Backtest Exp</div>
      <div class="bot-card-value" id="{bot_id}-bt-exp">—</div>
      <div class="bot-card-sub">Per trade</div>
    </div>
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">Backtest PnL</div>
      <div class="bot-card-value" id="{bot_id}-bt-pnl">—</div>
      <div class="bot-card-sub">Simulated Net</div>
    </div>
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">Backtest DD</div>
      <div class="bot-card-value" id="{bot_id}-bt-dd">—</div>
      <div class="bot-card-sub">Max Drawdown</div>
    </div>
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">OOS Validation</div>
      <div class="bot-card-value" id="{bot_id}-bt-oos">—</div>
      <div class="bot-card-sub" id="{bot_id}-bt-oos-sub">Walk-Forward</div>
    </div>
  </div>
  <div style="font-size:var(--text-xs);color:var(--c-text-dim);border-top:1px solid var(--c-border);padding-top:var(--s-3);display:flex;justify-content:space-between;flex-wrap:wrap;gap:var(--s-2)">
    <span><b>Setup Parameter:</b> <span id="{bot_id}-bt-verdict-sub">—</span></span>
    <span><b>Assets:</b> <span id="{bot_id}-bt-pairs-sub">—</span></span>
  </div>
</div>'''

    strats = f'''
<div id="{bot_id}-lab-strats" style="display:none;margin-bottom:var(--s-4)">
  <p class="bot-section-title" style="margin-top:0">📊 Validierung je Strategie (Lab-WFO)</p>
  <div class="bot-table-wrap">
    <table class="bot-table" style="font-size:var(--text-xs)">
      <thead><tr><th>Strategie</th><th>OOS PF</th><th>OOS Trades</th><th>OOS PnL</th><th>Gap</th></tr></thead>
      <tbody id="{bot_id}-lab-strats-body"></tbody>
    </table>
  </div>
  <p style="font-size:10px;color:var(--c-text-dim);margin-top:var(--s-2)">OOS-Referenz aus der Lab-WFO; Gap = Abweichung Shadow vs. OOS-Erwartung. Karten-Detail (Tier/TF/Budget/Setup) steht in „Strategien &amp; Slots".</p>
</div>'''

    return f'''
<div class="bot-card" style="padding:var(--s-4)">
{bench}
{strats}
{build_reopt_block(config, bot_id)}
</div>'''


def build_page(config, template):
    """Generate a complete content HTML from config + template."""
    bot_id = config['bot_id']
    features = config.get('features', {})

    meta_chips = build_meta_chips(config.get('meta_chips', []))
    multi_intro_section = build_multi_intro_section(config)
    ausrichtung_section = build_ausrichtung_section(config)
    signal_section = build_signal_section(features, bot_id)
    candlestick_section = build_candlestick_section(features, bot_id)
    lab_section = build_lab_section(config, bot_id)

    # Extra sections (bot-specific)
    extra_sections = config.get('extra_sections_html', '')
    extra_scripts = config.get('extra_scripts_js', '')

    # Fill template
    html = template
    html = html.replace('{{TITLE}}', config.get('title', 'Hermes'))
    html = html.replace('{{BOT_NAME}}', config.get('name', 'Bot'))
    html = html.replace('{{BOT_SHORT_NAME}}', build_short_name(config))
    html = html.replace('{{BOT_ID}}', bot_id)
    html = html.replace('{{API_BASE}}', config.get('api_base', ''))
    html = html.replace('{{DASHBOARD_JSON}}', config.get('dashboard_json', ''))
    html = html.replace('{{CHARTS_PATH}}', config.get('charts_path', ''))
    html = html.replace('{{HEATMAP_PATH}}', config.get('heatmap_path', ''))
    html = html.replace('{{REFRESH_INTERVAL}}', str(config.get('refresh_interval', 60000)))
    html = html.replace('{{META_CHIPS}}', meta_chips)
    html = html.replace('{{FOCUS_BADGE}}', build_focus_badge(config))
    html = html.replace('{{LIVE_BADGE}}', build_live_badge(config))
    html = html.replace('{{AUSRICHTUNG}}', ausrichtung_section)
    html = html.replace('{{MULTI_INTRO}}', multi_intro_section)
    html = html.replace('{{SIGNAL_SECTION}}', signal_section)
    html = html.replace('{{CANDLESTICK_SECTION}}', candlestick_section)
    html = html.replace('{{LAB_SECTION}}', lab_section)
    html = html.replace('{{EXTRA_SECTIONS}}', extra_sections)
    html = html.replace('{{EXTRA_SCRIPTS}}', extra_scripts)

    # Feature flags
    html = html.replace('{{HAS_SIGNALS}}', 'true' if features.get('signals') else 'false')
    html = html.replace('{{HAS_CANDLESTICK}}', 'true' if features.get('candlestick') else 'false')
    html = html.replace('{{HAS_HEATMAP}}', 'true' if features.get('heatmap') else 'false')

    # Position columns (JSON array from config, or empty array as fallback)
    pos_cols = config.get('position_columns', [])
    html = html.replace('{{POSITION_COLUMNS}}', json.dumps(pos_cols))

    # Chart labels (JSON array from config, or empty array as fallback)
    chart_labels = config.get('chart_labels', [])
    html = html.replace('{{CHART_LABELS}}', json.dumps(chart_labels))

    return html


def write_content(bot_id, html):
    """Write the generated HTML to the content directory."""
    out_path = os.path.join(CONTENT_DIR, f'{bot_id}.html')
    with open(out_path, 'w') as f:
        f.write(html)
    size = len(html)
    lines = html.count('\n') + 1
    print(f'  ✅ {out_path} ({lines} lines, {size:,} bytes)')
    return out_path


def main():
    # Determine which bots to build
    if len(sys.argv) > 1:
        bot_ids = sys.argv[1:]
        configs = []
        for bid in bot_ids:
            configs.append(load_config(bid))
    else:
        configs = find_all_configs()

    if not configs:
        print('❌ No bot configs found in', BOTS_DIR)
        sys.exit(1)

    template = load_template()
    print(f'Building {len(configs)} bot page(s) from template...\n')

    results = []
    for cfg in configs:
        bot_id = cfg['bot_id']
        print(f'  Building {cfg.get("name", bot_id)}...')
        html = build_page(cfg, template)
        out = write_content(bot_id, html)
        results.append((bot_id, out))

    print(f'\n✅ Done — {len(results)} page(s) generated.')
    print('   Run "cd /root/.hermes/site && python3 build.py" to build final HTML.')


if __name__ == '__main__':
    main()
