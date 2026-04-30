# Bot Leitfaden — Referenz (v2.5.2)

> **Canonical Version:** [hermes.nexusfortis.org/botleitfaden](https://hermes.nexusfortis.org/botleitfaden)
> Diese Markdown-Datei ist eine Referenz. Die HTML-Version ist die Single Source of Truth.

---

## 1. ÜBERBLICK

- **Ziel:** Autonomer Swing-Trading Bot auf Pepperstone (Demo → Live)
- **Broker:** Pepperstone GmbH (BaFin, Düsseldorf) — Abgeltungssteuer automatisch
- **API:** cTrader Open API (gRPC/Protobuf)
- **Konto:** Demo #47109084, ~504 EUR, 1:30 Hebel
- **KI:** DeepSeek-R1-0528 via OpenRouter (~0.012 EUR/Call, ~10 EUR/Monat)
- **Dashboard:** hermes.nexusfortis.org/bot

---

## 2. ARCHITEKTUR (Zwei-Schicht)

```
STRATEGIST (DeepSeek-R1) ──→ briefing.json ──→ Executor (Python, 0 EUR)
     ↑                                         ↓
     └── next_check_in (adaptiv)         Risk Engine → Atomic SL → cTrader
                                                ↓
                                         Watchdog (60s)
```

### Services (systemd)
| Service | Script | Intervall | Aufgabe |
|---------|--------|-----------|---------|
| hermes-strategist | 18_scheduler.py | adaptiv (0.5-24h) | Triggert Strategist |
| hermes-executor | 19_executor_daemon.py | 60 Min (15 bei M15) | MTF-Setups + Orders |
| ctrader-stream | ctrader_stream.py | Live (5s) | Bid/Ask Streaming |
| hermes-snapshot | 20_snapshot_daemon.py | 5 Min | Trailing, Performance |
| hermes-watchdog | 20_watchdog.py | 60s | Dead-Man-Switch |

### Cron-Jobs
| Cron | Script | Aufgabe |
|------|--------|---------|
| */5 Min | build_bot_status.py | Dashboard JSON |
| */2 Std | 01_scanner.py | 31 Symbole × 3 TFs |

---

## 3. STRATEGIST

Eingabedaten: scan_summary.json (31 Symbole), market_data.json, events_calendar.json, self_critique.json, correlations.json, review_phase.json.

Ausgabe: briefing.json mit market_regime, preferred_assets, allowed_directions, technical_rules, veto_conditions, m15_refine[], next_check_in.

### Adaptive Intervalle
| Marktlage | next_check_in |
|-----------|---------------|
| Normal (VIX 15-25) | 6-10h |
| Hohe Volatilität (VIX >30) | 1-4h |
| Pre-Event (FOMC <2h) | 0.5-1h |
| Post-Trade | 1-2h |
| Ruhig (ADX <20) | 12-24h |

---

## 4. EXECUTOR

MTF-Gating: 1D Regime → 4H Bias → 1H Entry (Top-Down). Min 2/3 TFs müssen übereinstimmen.

### M15 Entry-Refinement (optional)
Wenn Strategist m15_refine[] setzt: 10 Gates (Session, ATR, Spread, News, SL-Abstand, etc.). Max 3 Symbole. Gold NIE. TTL 2-6h.

### Setup-Qualität
| Score | Setup | Risiko |
|-------|-------|--------|
| ≥5 | A | 5% Equity |
| ≥3 | B | 3% Equity |
| ≥1 | C | 1.5% Equity |
| <1 | D | SKIP |

### Spread Hard Caps
Majors 2.5, JPY/GBP 4.0, Gold 30, Indizes 6.0. News-Blackout: 2.0 Pips.

---

## 5. RISIKO-MANAGEMENT

- Tages-Loss-Limit: -3% Equity
- Emergency Stop: Equity < 10% von Reference-Balance (dynamisch)
- Weekend-Block: Fr 21:00 - So 22:00 UTC
- News-Blackout: FOMC/NFP 60min vorher
- Watchdog: Emergency Close bei Daemon-Hang
- Margin-Limit: Max 30% Equity
- Atomic SL via relativeStopLoss (kein Race Condition)
- Position-Sizing: Setup-Qualität bestimmt Risiko (A=5%, B=3%, C=1.5%)
- Confidence < 0.6 → Risiko × 0.7

---

## 6. CASHFLOW-PROTOKOLL

Bot validiert Ein-/Auszahlungen bevor User sie bei Pepperstone ausführt.
POST /api/cashflow → Bot prüft Margin-Auswirkung → Status pending/ready/rejected → User bestätigt.

---

## 7. PHASEN-SYSTEM

| Phase | Trades | Max Pos. | Risiko | Assets | Size |
|-------|--------|----------|--------|--------|------|
| 1 — Lernphase | 0-30 | 2 | 3% | 2-3 | ×0.7 |
| 2 — Stabil | 30-100 | 3 | 4% | 5-6 | ×0.9 |
| 3 — Optimiert | 100+ | 4 | 5% | Alle | ×1.0 |

---

## 8. SYMBOLE (31)

- **Forex Majors (7):** EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, USDCAD, NZDUSD
- **Forex Crosses (6):** EURJPY, GBPJPY, EURGBP, AUDJPY, EURAUD, GBPAUD
- **Metalle (8):** XAUUSD, XAGUSD, XAUEUR, XAUGBP, XAUCHF, XAUAUD, XAGEUR, XAGAUD
- **Indizes (4):** US500, NAS100, US30, UK100 (kein DE40 auf Demo)
- **Crypto (4):** BTCUSD, ETHUSD, SOLUSD, XRPUSD
- **Energie (2):** SpotBrent, SpotCrude

---

## 9. KOSTEN

| Posten | Kosten |
|--------|--------|
| DeepSeek-R1 (Strategist) | ~0.012 EUR/Call, ~10 EUR/Monat |
| Executor + Scanner | 0 EUR |
| Spread | 0.1-0.5 Pips/Trade |
| Steuer | 26.375% auf Gewinne |

---

## 10. TRADE LIFECYCLE

- trade_log.jsonl: Entry + Exit mit PnL gross/net
- exit_log.jsonl: Hold-Time, Close-Reason, Snapshot
- rejected_setups.jsonl: Abgelehnte Kandidaten
- briefing_archive/: Alle Briefings archiviert
- Monte Carlo: 10.000 Simulationen auf echten Trades

---

*Letzte Aktualisierung: 2026-04-30 — v2.5.2*
