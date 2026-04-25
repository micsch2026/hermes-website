# Trading Bot — Leitfaden, Prozess & TODOs

> Gewinnorientierter Ansatz. Multidimensionalität als Grundsatz.
> Kimi optimiert sich selbst (Review) und dokumentiert.

---

## 1. ÜBERBLICK

**Ziel:** Autonomer Swing-Trading Bot auf Pepperstone (Demo → Live)
**Broker:** Pepperstone GmbH (BaFin, Düsseldorf) — Abgeltungssteuer automatisch
**API:** cTrader Open API (gRPC/Protobuf)
**KI:** Kimi 2.6 (OpenRouter) für Analyse + Review
**Dashboard:** hermes.nexusfortis.org/bot

---

## 2. KERNPRINZIPIEN

### Gewinnorientierung
- **Mindest-R:R 1:2** — jeder Trade muss das Potenzial haben, doppelt so viel zu gewinnen wie zu riskieren
- **Profit-Faktor > 1.5** als Ziel über 20 Trades
- **Höheres Risiko erlaubt** wenn Setup-Qualität hoch ist (A-Setup → bis 3% statt 2%)
- **Kein Risiko = kein Trade** — aber Risiko ist Werkzeug, nicht Feind

### Multidimensionalität
- **Mehrere Zeitrahmen** analysieren (1H + 4H + Daily)
- **Mehrere Indikatoren** kombinieren (Trend + Momentum + Volumen)
- **Mehrere Märkte** scannen (Forex, Indizes, Crypto, Aktien)
- **Korrelation prüfen** — keine 3 Long-Positionen im selben Sektor
- **Makro-Kontext** berücksichtigen (Fed, Earnings, geopolitisch)

### Selbstoptimierung (Kimi Review)
- **Jeder Trade** wird von Kimi reviewt
- **Wöchentlicher Prozess-Review** — Kimi evaluiert den Workflow selbst
- **Prompt-Tuning** — Kimi verbessert seine eigenen Prompts basierend auf Ergebnissen
- **Dokumentation** — Kimi hält Änderungen und Begründungen fest

---

## 3. PROZESS (7 Schritte)

```
┌─────────────────────────────────────────────────┐
│  1. SCAN       → cTrader Live-Daten (OHLCV)    │
│  2. SCREEN     → Kimi prüft 8 Swing-Setups     │
│  3. SCORE      → Signal-Qualität (ATR, RR, Korr)│
│  4. RISK       → Risikomodul validiert          │
│  5. EXECUTE    → cTrader Order (Market)         │
│  6. MONITOR    → SL/TP Management               │
│  7. REVIEW     → Kimi reviewt + dokumentiert    │
└─────────────────────────────────────────────────┘
```

### Detail je Schritt:

**1. SCAN (automatisch, Stream)**
- cTrader Stream liefert Live Bid/Ask für Watchlist
- OHLCV Trendbars (M1, M5, H1) für Top-Symbole
- Daten in /root/trading/data/stream/

**2. SCREEN (Kimi, manuell oder bei Signal)**
- Kimi analysiert 8 Setup-Typen:
  - MA-Cross (20/50, 50/200)
  - RSI-Divergenz
  - Bollinger Squeeze
  - VWAP-Bounce
  - Support/Resistance Break
  - Trendfortsetzung (Flag, Pennant)
  - Mean-Reversion
  - Momentum-Breakout
- Filter: nur A-Setups (R:R ≥ 1:2, Trend bestätigt)

**3. SCORE (Kimi + Regeln)**
- SL < 1.2 × ATR(14)
- R:R ≥ 1:2
- Korrelation < 0.6 vs offene Positionen
- Volumen-Bestätigung (steigend bei Breakout)
- Kein Earnings in < 5 Tagen

**4. RISK (automatisch, risk_manager.py)**
- SL Pflicht (ohne SL → ablehnen)
- Max 2% Equity pro Trade (3% bei A-Setup)
- Max 5% Tagesverlust → BLOCKED
- Max 10% Exposure insgesamt
- Max 20 Trades/Tag
- Weekend-Block (Fr 22:00 - So 22:00)

**5. EXECUTE (cTrader API)**
- Market Order mit SL/TP
- Volume = Equity × RiskPct / (SL-Distanz × TickValue)
- Logging in trade_log.jsonl

**6. MONITOR (Stream + Cron)**
- Live P&L Tracking
- Bei 50% TP → SL auf Break-Even schieben
- Bei SL-Trigger → automatisch geschlossen
- Swap-Kosten tracken

**7. REVIEW (Kimi, nach jedem Trade + wöchentlich)**
- Kimi bewertet: Timing, Größe, Risiko, Ergebnis
- Vorschläge für Verbesserung
- Dokumentation in kimi_review.json
- Wöchentlicher Prozess-Review

---

## 4. KOSTEN-TRACKING

### Trading-Kosten (pro Trade)
| Kostenart      | Geschätzt        | Tracking     |
|----------------|-------------------|--------------|
| Spread         | 0.1-0.3 pips FX  | automatisch  |
| Swap (Overnight)| -4 bis +2 €/Lot  | manuell      |
| Kommission     | €0 (Zero-Acc)     | —            |
| Slippage       | ~0.1 pips         | geschätzt    |

### KI-Kosten
| Service        | Kosten            | Tracking     |
|----------------|-------------------|--------------|
| Kimi 2.6       | ~€0.08/Analyse    | automatisch  |
| Geschätzt/Monat| ~€2.40            | Dashboard    |

### Steuer
- Pepperstone GmbH (Düsseldorf) führt automatisch ab:
  - 25% Abgeltungssteuer
  - 5.5% Solidaritätszuschlag darauf
  - = **26.375%** auf Gewinne
- Verluste werden automatisch verrechnet
- Jahressteuerbescheinigung verfügbar

### Netto-Rechnung
```
Brutto-P&L:        +€100
- Spread-Kosten:    -€4
- KI-Kosten:        -€0.16
= Vor Steuer:       +€95.84
- Steuer (26.375%): -€25.27
= NETTO:            +€70.57
```

---

## 5. KIMI SELBSTOPTIMIERUNG

### Review-Protokoll
Kimi dokumentiert nach jedem Trade:
```json
{
  "trade_id": "...",
  "setup_type": "MA-Cross",
  "bewertung": {
    "timing": "7/10 — Entry 2h nach Signal, ok",
    "groesse": "5/10 — Volume zu hoch für B-Setup",
    "risiko": "8/10 — SL korrekt bei 1.2 ATR",
    "ergebnis": "WIN +12 pips"
  },
  "lerneffekt": "Bei B-Setup Volume auf 0.5% statt 1% reduzieren",
  "prompt_aenderung": null
}
```

### Wöchentlicher Prozess-Review
Kimi evaluiert:
- Welche Setups performen besser?
- Ist der R:R realistisch oder zu optimistisch?
- Braucht es mehr oder weniger Konfirmation?
- Soll das Risiko angepasst werden?
- Prompt-Verbesserungen?

### Dokumentation
- Kimi schreibt Reviews nach /root/trading/data/kimi_review.json
- Wöchentliche Zusammenfassung nach /root/trading/data/weekly_review.md
- Änderungen am Prozess werden hier im Leitfaden dokumentiert

---

## 6. TODOs

### KURZFRISTIG (diese Woche)
- [ ] Ersten echten Swing-Trade platzieren (mit Risikomodul)
- [ ] Spread-Tracking automatisieren (aus cTrader Spreads)
- [ ] Swap-Kosten pro Position tracken
- [ ] Equity-Kurve im Dashboard zeigen
- [ ] Kimi Review nach Trade #1 laufen lassen

### MITTELFRISTIG (nächste 2 Wochen)
- [ ] Kimi-Prompt mit Live-Spreads/VWAP erweitern
- [ ] Feature-Engine: RSI, MACD, ATR aus OHLCV berechnen
- [ ] Korrelations-Check vor jedem Trade
- [ ] Automatischer SL-Trail bei 50% TP
- [ ] Earnings-Kalender Integration
- [ ] Wöchentlichen Kimi-Prozess-Review einrichten

### LANGFRISTIG (nächster Monat)
- [ ] Pepperstone Demo → Live Konto wechseln
- [ ] Steuer-Report Generator (Jahresübersicht)
- [ ] Backtesting-Framework (historische Daten)
- [ ] Multi-Asset Diversifikation (max 3 unkorrelierte)
- [ ] Kimi Prompt-Engineering Optimierung
- [ ] Performance vs Benchmark (S&P 500)

### OFFENE FRAGEN
- [ ] Wann von Demo auf Live wechseln? (Nach X profitablen Wochen?)
- [ ] Maximaler Drawdown für Live-Betrieb? (10%? 15%?)
- [ ] Soll Kimi eigenständig traden dürfen oder nur empfehlen?

---

## 7. SYMBOLE & WATCHLIST

### Aktuell im Stream
| Symbol   | Typ     | Min-Lot | Spread (geschätzt) |
|----------|---------|---------|-------------------|
| EURUSD   | Forex   | 0.01    | 0.1-0.3 pips     |
| GBPUSD   | Forex   | 0.01    | 0.2-0.4 pips     |
| USDJPY   | Forex   | 0.01    | 0.2-0.3 pips     |
| AUDUSD   | Forex   | 0.01    | 0.2-0.3 pips     |
| USDCAD   | Forex   | 0.01    | 0.2-0.4 pips     |
| BTCUSD   | Crypto  | 0.01    | $20-40           |
| ETHUSD   | Crypto  | 0.01    | $2-5             |
| QQQ      | ETF     | 1       | $0.01-0.02       |

### Erweiterung geplant
- GOLD (XAUUSD)
- DE40 (DAX)
- US500 (S&P 500)
- NVDA, AAPL (Einzeltitel)

---

## 8. DATEIEN & INFRASTRUKTUR

### Code
```
/root/trading/src/
├── ctrader_stream.py        ← Live-Daten Stream (systemd)
├── ctrader_snapshot.py      ← Snapshot für Dashboard (Cron 15min)
├── pepperstone_trader.py    ← Trading Engine (buy/sell/close)
├── risk_manager.py          ← Risikomodul
├── performance_tracker.py   ← Performance & Kosten
├── kimi_review.py           ← Kimi Trade Review
├── execute_kimi_decision.py ← Kimi → Order Bridge
└── check_api_status.py      ← API Status Check
```

### Daten
```
/root/trading/data/
├── trade_log.jsonl          ← Alle Trades
├── kimi_review.json         ← Letztes Kimi Review
├── risk_state.json          ← Risiko-Status (täglich reset)
├── stream/
│   ├── spots_all.json       ← Live Preise
│   └── spots/*.json         ← Pro Symbol
└── weekly_review.md         ← Wöchentliche Zusammenfassung
```

### Services
```
ctrader-stream.service       ← Live-Daten (systemd, auto-restart)
Cron: Snapshot               ← alle 15min
Cron: API Status Check       ← alle 6h
```

### Dashboard
```
hermes.nexusfortis.org/bot
├── Performance & Kosten
├── Live-Preise (8 Symbole)
├── Kontostand & Positionen
├── Risiko-Management
├── Kimi Review
├── Trade-Log
├── Review-Zyklus
└── Pipeline Status
```

---

## 9. ENTSCHEIDUNGSMATRIX

### Wann traden?
| Bedingung           | Aktion        |
|---------------------|---------------|
| A-Setup + R:R ≥ 1:3 | 3% Risiko     |
| B-Setup + R:R ≥ 1:2 | 2% Risiko     |
| C-Setup             | Nicht traden  |
| FEAR-Regime         | Nur Long, 1%  |
| Earnings < 5 Tage   | Kein Trade    |
| Weekend             | Kein Trade    |

### Wann Position schließen?
| Bedingung           | Aktion        |
|---------------------|---------------|
| TP erreicht         | Auto-close    |
| SL erreicht         | Auto-close    |
| 50% TP → SL auf BE | Trail SL      |
| Fundament ändert    | Manuell prüfen |
| 5% Daily Loss       | ALLES schließen|

---

*Letzte Aktualisierung: 2026-04-24 15:50 Berlin*
*Nächster Review: nach dem ersten echten Swing-Trade*
