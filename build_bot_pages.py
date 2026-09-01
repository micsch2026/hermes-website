#!/usr/bin/env python3
"""
build_bot_pages.py — ONE builder for ALL bot dashboard pages.

Reads template + per-bot JSON config → generates content HTML files
that build.py can process into final pages.

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


def build_strategy_tags(tags):
    """Generate strategy tag HTML from config list."""
    parts = []
    for tag in tags:
        tag_id = tag.get('id', '')
        id_attr = f' id="{tag_id}"' if tag_id else ''
        parts.append(
            f'  <div class="bot-strategy-tag">\n'
            f'    <span class="label">{tag["label"]}</span>\n'
            f'    <span class="value"{id_attr}>{tag["value"]}</span>\n'
            f'  </div>'
        )
    return '\n'.join(parts)


def build_config_chips(chips):
    """Generate config chip HTML."""
    parts = []
    for chip in chips:
        parts.append(f'    <span class="bot-config-chip">{chip}</span>')
    return '\n'.join(parts)


def build_backtest_section(features, bot_id, config):
    """Generate backtest overview section if enabled."""
    if not features.get('backtest', False):
        return ''
    ro = config.get('reoptimize', {})
    tf = ro.get('timeframe', '?')
    strategy = ro.get('strategy', '')
    dm = ro.get('data_months', '?')
    im = ro.get('interval_months', '?')
    if strategy == 'lab_live':
        bt_title = f'🧪 Backtest Benchmark ({tf} WFO, 11 Splits, 6M Hold-Out)'
    else:
        bt_title = f'🧪 Backtest Benchmark ({tf} WFO, IS={dm}M/OOS={im}M)'
    return f'''
<!-- BACKTEST BENCHMARK TABLE & STATS -->
<div class="bot-card" style="margin-bottom:var(--s-4);padding:var(--s-4)">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--s-3);flex-wrap:wrap;gap:var(--s-2)">
    <span style="font-weight:700;font-size:var(--text-md)">{bt_title}</span>
    <span id="{bot_id}-bt-verdict" class="bot-badge bot-badge-signal" style="font-size:var(--text-xs)">—</span>
  </div>

  <div class="bot-grid" id="{bot_id}-bt-grid" style="margin-bottom:var(--s-4)">
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
      <div class="bot-card-sub" id="{bot_id}-bt-exp-ci">Per trade</div>
    </div>
    <div class="bot-card" style="background:rgba(255,255,255,0.02);padding:var(--s-3)">
      <div class="bot-card-title">Backtest PnL</div>
      <div class="bot-card-value" id="{bot_id}-bt-pnl">—</div>
      <div class="bot-card-sub" id="{bot_id}-bt-pnl-sub">Simulated Net</div>
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
    <span><b>Aktive Assets:</b> <span id="{bot_id}-bt-pairs-sub">—</span> (<span id="{bot_id}-bt-pairs">—</span> Paare)</span>
  </div>
</div>'''


def build_signal_section(features, bot_id):
    """Generate signal overview section if enabled."""
    if not features.get('signals', False):
        return ''
    return f'''
<!-- 6. SIGNAL OVERVIEW -->
<p class="bot-section-title">📡 Signal Overview</p>
<div class="bot-signal-grid" id="{bot_id}-signal-grid">
  <div class="bot-signal-card"><div class="bot-no-data">Loading signals...</div></div>
</div>'''


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
      <button id="{bot_id}-trade-toggle" class="bot-chart-close"
        onclick="BotDash.toggleTradeLines()"
        style="background:rgba(34,197,94,0.15);color:#22c55e;border:1px solid rgba(34,197,94,0.3)">
        📊 Trades: ON
      </button>
      <button class="bot-chart-close" onclick="BotDash.closeChart()">✕ Close</button>
    </div>
  </div>
  <div class="bot-pair-nav" id="{bot_id}-pair-nav"></div>
  <div class="bot-range-nav" id="{bot_id}-range-nav">
    <span class="bot-range-chip" data-days="0" onclick="BotDash.setRange(0)">All</span>
    <span class="bot-range-chip bot-range-active" data-days="90" onclick="BotDash.setRange(90)">3M</span>
    <span class="bot-range-chip" data-days="30" onclick="BotDash.setRange(30)">1M</span>
    <span class="bot-range-chip" data-days="14" onclick="BotDash.setRange(14)">2W</span>
    <span class="bot-range-chip" data-days="7" onclick="BotDash.setRange(7)">1W</span>
  </div>
  <div class="bot-chart-config" id="{bot_id}-chart-config"></div>
  <div class="bot-chart-legend" style="display:flex;gap:var(--s-3);flex-wrap:wrap;margin-bottom:var(--s-2);font-size:var(--text-xs);color:var(--c-text-dim)">
    <span><span style="color:#22c55e">━</span> Profit</span>
    <span><span style="color:#ef4444">━</span> Loss</span>
    <span><span style="color:#22c55e">┈</span> Timeout (profit)</span>
    <span><span style="color:#ef4444">┈</span> Timeout (loss)</span>
    <span style="opacity:0.6">Each arrow = one simulated backtest trade</span>
  </div>
  <div class="bot-chart-wrap">
    <div id="{bot_id}-candle-chart" style="height:320px"></div>
    <div class="bot-trade-tooltip" id="{bot_id}-trade-tooltip"></div>
    <div class="bot-chart-rsi-label">RSI</div>
    <div id="{bot_id}-rsi-chart" style="height:100px"></div>
  </div>
</div>'''


def build_heatmap_section(features, bot_id):
    """Generate performance heatmap section if enabled."""
    if not features.get('heatmap', False):
        return ''
    return f'''
<!-- 10. PERFORMANCE HEATMAP -->
<p class="bot-section-title">🗺️ Asset Performance Heatmap</p>
<div class="bot-card">
  <div class="bot-heatmap-grid" id="{bot_id}-heatmap-grid">
    <div class="bot-no-data">Loading heatmap...</div>
  </div>
</div>'''


def build_reoptimize_section(config, bot_id):
    """Generate re-optimization status + instructions section."""
    ro = config.get('reoptimize')
    if not ro:
        return ''

    last_date = ro.get('last_date', '')
    interval = ro.get('interval_months', 3)
    steps = ro.get('steps', [])
    pairs = ro.get('pairs', [])
    timeframe = ro.get('timeframe', '?')
    data_months = ro.get('data_months', 6)
    script = ro.get('script', '')

    # Steps HTML
    steps_html = ''
    for i, step in enumerate(steps):
        if step.startswith('#'):
            steps_html += f'<div style="color:var(--c-text-dim);margin-top:var(--s-2)">{step}</div>\n'
        else:
            steps_html += (
                f'<div style="display:flex;align-items:center;gap:var(--s-2);margin-top:var(--s-1)">'
                f'<code style="flex:1;background:var(--c-bg);padding:6px 10px;border-radius:var(--r-sm);'
                f'font-size:var(--text-xs);user-select:all">{step}</code>'
                f'</div>\n'
            )

    return f'''
<!-- RE-OPTIMIZATION STATUS -->
<p class="bot-section-title">🔄 Re-Optimierung</p>
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
        Grid-Search ({timeframe}, {data_months}M Daten, {len(pairs)} Paare) + Walk-Forward Validation
      </div>
      {steps_html}
    </div>
  </details>
</div>'''


def load_descriptions():
    """Load human-readable strategy descriptions from portfolio_descriptions.json."""
    desc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio_descriptions.json')
    if os.path.exists(desc_path):
        try:
            with open(desc_path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def describe_strategy(sid, lab_name, desc_data):
    """Return structured description dict (tag, was, gut, nicht, ausmacht, ergaenzt)."""
    name_l = (lab_name or "").lower()
    overrides = desc_data.get("overrides", {}) or {}
    if str(sid) in overrides:
        o = overrides[str(sid)]
        return {"tag": o.get("tag") or "Individuell",
                "was": o.get("was", ""), "gut": o.get("gut", ""), "nicht": o.get("nicht", ""),
                "ausmacht": o.get("ausmacht", ""), "ergaenzt": o.get("ergaenzt", "")}
    for a in desc_data.get("approaches", []) or []:
        for kw in a.get("match", []) or []:
            if kw in name_l or kw in str(sid):
                return {"tag": a.get("tag"), "was": a.get("was", ""),
                        "gut": a.get("gut", ""), "nicht": a.get("nicht", ""),
                        "ausmacht": a.get("ausmacht", ""), "ergaenzt": a.get("ergaenzt", "")}
    return {"tag": "Trading-Strategie", "was": "", "gut": "", "nicht": "", "ausmacht": "", "ergaenzt": ""}


def build_strategy_concept_section(bot_id, config, desc_data):
    """Generate a clean visual strategy explanation card based on portfolio_descriptions."""
    # Extract strategy ID from config/tags
    strat_id = ""
    strat_name = config.get("name", "")
    for tag in config.get("strategy_tags", []):
        val = tag.get("value", "")
        if "#" in val:
            parts = val.split("#")[1].split()[0].replace("—", "").strip()
            if parts.isdigit():
                strat_id = parts
                break
    if not strat_id and "reoptimize" in config:
        script = config["reoptimize"].get("script", "")
        if "#" in script:
            strat_id = script.split("#")[1].split("'")[0].strip()

    desc = describe_strategy(strat_id, strat_name, desc_data)
    tag = desc.get("tag", "Trading-Strategie")
    was = desc.get("was", "")
    gut = desc.get("gut", "")
    nicht = desc.get("nicht", "")
    ausmacht = desc.get("ausmacht", "")
    ergaenzt = desc.get("ergaenzt", "")

    chips_html = ""
    for chip in config.get("config_chips", []):
        chips_html += f'<span class="bot-strategy-tag" style="background:var(--c-surface-2);border:1px solid var(--c-border);font-size:var(--text-xs);padding:4px 10px;border-radius:var(--r-md);">{chip}</span>\n'

    return f"""
<!-- STRATEGY CONCEPT & PROFILE -->
<div class="bot-card" style="padding:var(--s-4);margin-bottom:var(--s-4);">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--s-3);flex-wrap:wrap;gap:var(--s-2);">
    <div>
      <span class="bot-tag-primary" style="font-size:11px;font-weight:700;padding:3px 10px;border-radius:var(--r-md);background:rgba(99,102,241,0.15);color:#818cf8;margin-right:8px;">{tag}</span>
      <strong style="font-size:var(--text-md);color:var(--c-text);">Strategie-Profil {'#' + strat_id if strat_id else ''}</strong>
    </div>
  </div>

  <div class="bot-desc-grid" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:var(--s-4);margin-bottom:var(--s-4);">
    <div style="display:flex;flex-direction:column;gap:8px;">
      <div class="bot-desc-row"><span class="bot-desc-label">Konzept:</span><span style="color:var(--c-text);">{was or 'Systematische Handelsstrategie basierend auf quantitativen Signalfiltern.'}</span></div>
      {f'<div class="bot-desc-row"><span class="bot-desc-label">Profil:</span><span style="color:var(--c-text);">{ausmacht}</span></div>' if ausmacht else ''}
      {f'<div class="bot-desc-row"><span class="bot-desc-label">Portfolio:</span><span style="color:var(--c-text);">{ergaenzt}</span></div>' if ergaenzt else ''}
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      {f'<div class="bot-desc-row"><span class="bot-desc-label">Stärken:</span><span style="color:var(--c-success,#10b981);">{gut}</span></div>' if gut else ''}
      {f'<div class="bot-desc-row"><span class="bot-desc-label">Schwächen:</span><span style="color:var(--c-warn,#f59e0b);">{nicht}</span></div>' if nicht else ''}
    </div>
  </div>

  <div style="border-top:1px solid var(--c-border);padding-top:var(--s-3);margin-top:var(--s-2);">
    <p style="font-size:var(--text-xs);font-weight:600;color:var(--c-text-muted);margin-bottom:var(--s-2);text-transform:uppercase;letter-spacing:0.5px;">Setup- & Execution-Parameter</p>
    <div style="display:flex;flex-wrap:wrap;gap:6px;">
      {chips_html}
    </div>
  </div>
</div>
"""


def build_page(config, template, desc_data=None):
    """Generate a complete content HTML from config + template."""
    bot_id = config['bot_id']
    features = config.get('features', {})
    desc_data = desc_data or {}

    # Strategy tags
    strategy_tags = build_strategy_tags(config.get('strategy_tags', []))

    # Config chips
    config_chips = build_config_chips(config.get('config_chips', []))

    # Strategy Concept
    strategy_concept_section = build_strategy_concept_section(bot_id, config, desc_data)

    # Conditional sections
    backtest_section = build_backtest_section(features, bot_id, config)
    signal_section = build_signal_section(features, bot_id)
    candlestick_section = build_candlestick_section(features, bot_id)
    heatmap_section = build_heatmap_section(features, bot_id)
    reoptimize_section = build_reoptimize_section(config, bot_id)

    # Extra sections (bot-specific)
    extra_sections = config.get('extra_sections_html', '')
    extra_scripts = config.get('extra_scripts_js', '')

    # Fill template
    html = template
    html = html.replace('{{TITLE}}', config.get('title', 'Hermes'))
    html = html.replace('{{BOT_NAME}}', config.get('name', 'Bot'))
    html = html.replace('{{BOT_ID}}', bot_id)
    html = html.replace('{{API_BASE}}', config.get('api_base', ''))
    html = html.replace('{{DASHBOARD_JSON}}', config.get('dashboard_json', ''))
    html = html.replace('{{CHARTS_PATH}}', config.get('charts_path', ''))
    html = html.replace('{{HEATMAP_PATH}}', config.get('heatmap_path', ''))
    html = html.replace('{{REFRESH_INTERVAL}}', str(config.get('refresh_interval', 60000)))
    html = html.replace('{{STRATEGY_TAGS}}', strategy_tags)
    html = html.replace('{{CONFIG_CHIPS}}', config_chips)
    html = html.replace('{{STRATEGY_CONCEPT_SECTION}}', strategy_concept_section)
    html = html.replace('{{BACKTEST_SECTION}}', backtest_section)
    html = html.replace('{{SIGNAL_SECTION}}', signal_section)
    html = html.replace('{{CANDLESTICK_SECTION}}', candlestick_section)
    html = html.replace('{{HEATMAP_SECTION}}', heatmap_section)
    html = html.replace('{{REOPTIMIZE_SECTION}}', reoptimize_section)
    html = html.replace('{{EXTRA_SECTIONS}}', extra_sections)
    html = html.replace('{{EXTRA_SCRIPTS}}', extra_scripts)

    # Feature flags
    html = html.replace('{{HAS_SIGNALS}}', 'true' if features.get('signals') else 'false')
    html = html.replace('{{HAS_CANDLESTICK}}', 'true' if features.get('candlestick') else 'false')
    html = html.replace('{{HAS_HEATMAP}}', 'true' if features.get('heatmap') else 'false')
    html = html.replace('{{HAS_BACKTEST}}', 'true' if features.get('backtest') else 'false')

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
    desc_data = load_descriptions()
    print(f'Building {len(configs)} bot page(s) from template...\n')

    results = []
    for cfg in configs:
        bot_id = cfg['bot_id']
        print(f'  Building {cfg.get("name", bot_id)}...')
        html = build_page(cfg, template, desc_data)
        out = write_content(bot_id, html)
        results.append((bot_id, out))

    print(f'\n✅ Done — {len(results)} page(s) generated.')
    print('   Run "cd /root/.hermes/site && python3 build.py" to build final HTML.')


if __name__ == '__main__':
    main()
