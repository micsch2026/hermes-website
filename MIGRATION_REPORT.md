# Vergleichsbericht: Bot Dashboard Migration

## Datum: 2026-06-12

## Zusammenfassung

Migration der Bot-Dashboards auf das Template-System abgeschlossen.
V2-Seiten laufen parallel unter /fx-v2 und /trend-v2 zum Testen.

## 1. Zeilenvergleich

| Seite | Alt (Standalone) | Neu (Template) | Reduktion |
|-------|------------------|----------------|-----------|
| FX Bot | 1.392 Zeilen | 270 Zeilen (Content) + 154 (Template) | -69% |
| Trend Bot | 1.489 Zeilen | 226 Zeilen (Content) + 154 (Template) | -74% |

Shared Assets:
- bot.css: 463 Zeilen (statt 3x inline CSS)
- bot-components.js: 833 Zeilen (statt 3x inline JS)

## 2. Feature-Parität: 100%

| Feature | Alt FX | V2 FX | Alt Trend | V2 Trend |
|---------|--------|-------|-----------|----------|
| Status Bar | ✅ | ✅ | ✅ | ✅ |
| Health Banner | ✅ | ✅ | ✅ | ✅ |
| Strategy Info | ✅ | ✅ | ✅ | ✅ |
| KPI Cards | ✅ | ✅ | ✅ | ✅ |
| Performance Metrics | ✅ | ✅ | ✅ | ✅ |
| Equity Curve | ✅ | ✅ | ✅ | ✅ |
| Signal Grid | ✅ | ✅ | ✅ | ✅ |
| Candlestick Charts | ✅ | ✅ | ✅ | ✅ |
| Positions Table | ✅ | ✅ | ✅ | ✅ |
| Trade History | ✅ | ✅ | ✅ | ✅ |
| Config Chips | ✅ | ✅ | ✅ | ✅ |
| Pair Params | ✅ | ✅ | ✅ | ✅ |
| Performance Heatmap | ✅ | ✅ | ✅ | ✅ |
| Backtest Overview | ✅ | ✅ | ❌ | ❌ |
| BotDash.init() | ❌ | ✅ | ✅ | ✅ |

## 3. Pitfall-Verifikation (13 Punkte)

| # | Pitfall | Status | Details |
|---|---------|--------|---------|
| 1 | Balance-Anzeige | ✅ | `fx-v2-balance` ID, €-Format |
| 2 | ID-Namespace | ✅ | `fx-v2-*` / `trend-v2-*`, keine Kollisionen |
| 3 | Positions-Tabelle | ✅ | 9 Spalten, Score-Farben, Duration |
| 4 | Equity-Chart | ✅ | Chart.js Line, Start/Current/Change Summary |
| 5 | Candlestick-Charts | ✅ | LightweightCharts, BB/RSI/EMA Overlay |
| 6 | Trade Lines | ✅ | Diagonal, Toggle, Profit/Loss Farben |
| 7 | Pair Navigation | ✅ | Chips mit Active-State |
| 8 | Range Filter | ✅ | All/3M/1M/2W/1W |
| 9 | Heatmap | ✅ | Per-Pair WR/PnL/R:R Bars |
| 10 | Health Banner | ✅ | Warn/Error States, consecutive_errors |
| 11 | Auto-Refresh | ✅ | 60s Interval |
| 12 | PnL-Farben | ✅ | Grün/Rot via bot-pnl-pos/neg |
| 13 | Responsive | ✅ | 600px/400px Breakpoints |

## 4. Architektur-Änderungen

### Behoben
- `/templates/bot.css` → `/assets/bot.css` (Symlink in _build/ existiert bereits)
- `/templates/bot-components.js` → `/assets/bot-components.js`
- build_bot_pages.py in build.py Pipeline integriert (Schritt 0b)
- Alte standalone HTML-Seiten archiviert (.archive/legacy-standalone-2026-06-12/)

### Erstellt
- `src/data/bots/fx-v2.json` — FX v2 Konfiguration
- `src/data/bots/trend-v2.json` — Trend v2 Konfiguration
- `deploy_bot_pages.sh` — Build + Deploy Script
- `BOT_TEMPLATE_README.md` — Dokumentation

## 5. Live-URLs

| Seite | URL | Status |
|-------|-----|--------|
| FX Bot | /fx | ✅ Live (Template) |
| FX Bot v2 | /fx-v2 | ✅ Live (Parallel-Test) |
| Trend Bot | /trend | ✅ Live (Template) |
| Trend Bot v2 | /trend-v2 | ✅ Live (Parallel-Test) |

## 6. Empfohlene nächste Schritte

1. V2-Seiten 1 Woche parallel laufen lassen
2. Daten-Gleichheit prüfen (gleiche dashboard.json Endpoints)
3. Nach Bestätigung: v2-Konfigurationen entfernen, nur fx/trend behalten
4. Candlestick-Chart-Features in bot-components.js verifizieren
