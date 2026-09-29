# Dashboard-Neubau hermes.nexusfortis.org — Konzept (FREIGEGEBEN 2026-09-29)

**Status:** Konzept von Michael freigegeben („konzept ok. viele charts. visuell
unterstützend. umsetzen wenn alles fertig"). Umsetzung startet NACH Abschluss des
Systematik-Builds (Multibot Teil B/C). Das alte Dashboard (/) bleibt bis dahin
UNANGETASTET.

**Umsetzungsstand (29.09. abends):** E1 (Datenlayer `build_overview_status.py`)
und E2 (Seite `/overview` „System-Kommandocenter") **fertig** — Commits
`d817d794d`/`f5f71afbc`, Tests 18/18 + 18/18, Browser-E2E grün, live unter
`/overview` (Basic Auth). Offen: **E3** = Charts in den 5 Platzhaltern
(`#chart-equity/-monthly/-corr/-tca/-exposure`), **E4** = nav.json-Eintrag +
Swap ( `/` → neue Seite, altes Dashboard ersetzt).

**Ziel:** Neue Startseite „System-Kommandocenter" ersetzt das aktuelle Dashboard.
Detaillierte Auswertung, Auffälligkeiten, Gesamtbeurteilung — **viele Charts,
visuell unterstützend**.

## Struktur (freigegeben)
1. 🎯 **Gesamtbeurteilung** — Gesamt-Ampel + 5 Komponenten-Ampeln (Lab · Shadow ·
   Demo/Live · Risiko · Daten), berechnet aus harten Kennzahlen (keine Schein-Scores).
2. ⚠️ **Auffälligkeiten (Auto-Findings, priorisiert)** — Decay 🔴/🟠, Paritäts-Lücken,
   DD-Leiter-Alerts, Daten-Staleness, TCA-Ausreißer, Challenge-ready-Slots, Feed-Freeze.
3. 📈 **Live & Demo** — Equity gesamt + je Bot, Drawdown-Chart, PnL 7/30d, offene
   Positionen, DD-Leiter-Status L0–L3.
4. 👻 **Shadow** — Ranking, P6-Decay-Matrix, Challenges, Rotations-Slot-Karten.
5. 🔬 **Lab** — Worker-Status, frische WFO-Passes/Tiers, Queue, 7d-Produktion.
6. 📊 **Charts-Block** — Monats-PnL-Balken, Slippage-Verteilung (P5),
   Korrelations-Heatmap, Exposure je Assetklasse (+ mehr, „viele Charts").
7. 🔎 **Fußzeile** — Datenstand je Quelle (frisch/alt), Timer-/Systemstatus.

## Datenquellen (alle vorhanden)
catalog.db · data/shadow/shadow_trades.jsonl + shadow_portfolio.json ·
botN_trades/balance/risk_state · Rotation (slot_history/state/log, pool_report) ·
P6 decay_monitor --json · P5 tca_report --json · pipeline_status.json ·
Feed-/Timer-Health.

## Bauweise
- Statische Seite im bestehenden Site-System (`/root/.hermes/site`): Templates,
  Charts-Muster (LightweightCharts/SVG wie Bot-Seiten), Daten als API-JSONs.
- Auto-Rebuild wie bestehende Pages (Timer bzw. ans bestehende Rebuild-System hängen).
- Umsetzung via opencode-Delegationen in Etappen + eigene unabhängige E2E-Verifikation,
  Basic-Auth/Caddy bleibt.

## Merker für die Umsetzung
- P7 (zentrales Risikobuch): kommt nach/neben dem Dashboard; P7-Daten können später
  in Komponente „Risiko" einfließen.
- Skill-Grundlagen: hermes-site-management, hermes-site-bot-components,
  strategy-lab-website, site-rebuilder-pipeline.
