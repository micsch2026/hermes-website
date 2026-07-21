# Bot Dashboard Template System

## Übersicht

Alle Bot-Dashboard-Seiten (FX, Trend, zukünftige Bots) nutzen ein einheitliches Template-System.
Statt 800-1.400 Zeilen HTML pro Seite generiert `build_bot_pages.py` aus einer JSON-Konfiguration
und einem gemeinsamen Template vollständige Dashboard-Seiten.

## Architektur

```
src/
├── templates/
│   ├── bot.html              # HTML-Template (154 Zeilen, {{BOT_ID}}-Platzhalter)
│   ├── bot.css               # Shared CSS (463 Zeilen, .bot-* Klassen)
│   ├── bot-components.js     # Shared JS Engine (833 Zeilen, BotDash.* Namespace)
│   └── base.html             # Site-Wrapper (Nav, Theme, Footer)
├── data/bots/
│   ├── fx.json               # FX Bot Konfiguration
│   ├── trend.json            # Trend Bot Konfiguration
│   └── *.json                # Weitere Bots einfach hinzufügen
└── content/
    ├── fx.html               # ← Generiert (NICHT manuell editieren!)
    └── trend.html             # ← Generiert (NICHT manuell editieren!)

build_bot_pages.py             # Template → Content Fragment Generator
build.py                       # Content Fragment → Final HTML (mit Nav, Theme)
```

## Einen neuen Bot hinzufügen

### 1. JSON-Konfiguration erstellen

`src/data/bots/mein-bot.json`:

```json
{
  "id": "mein-bot",
  "name": "Mein Trading Bot",
  "title": "Mein Trading Bot — Hermes",
  "bot_id": "mein-bot",
  "api_base": "/api/mein-bot",
  "dashboard_json": "/api/mein-bot/dashboard.json",
  "charts_path": "/api/mein-bot/charts/",
  "heatmap_path": "/api/mein-bot/performance_heatmap.json",
  "refresh_interval": 60000,

  "features": {
    "equity": true,
    "signals": true,
    "candlestick": true,
    "heatmap": true,
    "backtest": false
  },

  "strategy_tags": [
    {"label": "Strategy", "value": "Meine Strategie"},
    {"label": "Timeframe", "value": "1H"},
    {"label": "Pairs", "value": "10 Pairs", "id": "mein-bot-pairs-count"},
    {"label": "Type", "value": "Mean Reversion"}
  ],

  "config_chips": [
    "RSI(14) · 30/70",
    "1H Timeframe",
    "10 Pairs"
  ]
}
```

### 2. Build ausführen

```bash
cd /root/.hermes/site
python3 build_bot_pages.py mein-bot   # Generiert src/content/mein-bot.html
python3 build.py                       # Baut _build/mein-bot.html mit Nav/Theme
```

### 3. Caddy-Route (optional)

Die Seiten sind automatisch unter `/<bot-id>` erreichbar (z.B. `/mein-bot`).
Keine Caddy-Änderung nötig — `try_files {path} {path}.html` greift automatisch.

## Feature-Flags

| Flag | Beschreibung | Benötigt |
|------|-------------|----------|
| `equity` | Equity Curve Chart | Chart.js |
| `signals` | Signal-Grid pro Pair | — |
| `candlestick` | Candlestick-Charts mit Indikatoren | LightweightCharts |
| `heatmap` | Pair Performance Heatmap | — |
| `backtest` | Backtest-Overview (89d 1H Data) | backtest_report.json |

## Build-Pipeline

```
python3 build.py
  ├─ 0a. build_backtest_status.py   → Backtest API-Daten
  ├─ 0b. build_bot_pages.py         → Bot-Seiten aus Template
  ├─ 1.  Widget-Pages aus sections.json
  ├─ 2.  Alle Content-Fragments → _build/
  └─ 3.  Git auto-push
```

## Shared Assets

| Datei | Namespace | Beschreibung |
|-------|-----------|-------------|
| `assets/bot.css` | `.bot-*` | Shared CSS-Klassen |
| `assets/bot-components.js` | `BotDash.*` | Shared JS-Engine |
| `assets/base.css` | `--c-*`, `--s-*` | CSS Custom Properties |

## ID-Namenkonvention

Alle Element-IDs nutzen `{{BOT_ID}}-` als Prefix:
- `fx-dot`, `fx-balance`, `fx-positions-body`
- `trend-dot`, `trend-balance`, `trend-positions-body`

BotDash.init({prefix: 'fx'}) setzt den Namespace automatisch.

## Vergleich: Alt vs Neu

| Metrik | Alt (Standalone) | Neu (Template) |
|--------|------------------|----------------|
| Zeilen HTML | 1.392 - 1.489 | 270 - 226 |
| CSS | Inline (dupliziert) | Shared (bot.css) |
| JS | Inline (dupliziert) | Shared (bot-components.js) |
| Neuer Bot | ~800 Zeilen kopieren | 35 Zeilen JSON |
| Features | Manuell pro Seite | Automatisch via Flags |

## Archivierte Dateien

- `.archive/legacy-standalone-2026-06-12/` — Alte standalone HTML-Seiten (nicht löschen!)
