# /dashboard → Fleet-Übersicht: MiMo-Konsultation + Design-Spec (2026-10-11)

**Auftrag (User):** „überlege mit mimo zusammen wie wir bei /dashboard eine
aussagekräftige Übersicht hinbekommen. Performance, aktuelle Entwicklung,
Empfehlung etc. Aktuell ist die Seite nichtssagend."

**Status:** UMGESETZT 2026-10-12 (User-Go "weiter, go"). Commit `0a1bbec1c` (+ Follow-up: TITLE „Fleet-Cockpit", README-Sync). **Abweichungen vom Konzept:** E1 auf `n_7d`/`n_30d` je Bot reduziert (Top-3-Empfehlungs-Clustering + PnL-% laufen im Frontend aus vorhandenen Feldern — kein `recommendations_top3`-Feld nötig); `tools/generate_home_sidebar.py` archiviert → `archive_legacy/scripts/` (Fleet-Block wird nicht mehr generiert). **Verifikation:** `make test` SITE TESTS OK, Browser-E2E lokal + live (Basic-Auth) — 10 Matrix-Zeilen, alle Module, kein Fehlerbanner.
**Konsultation:** `xiaomi/mimo-v2.6-pro` via OpenRouter (Provider: Xiaomi),
79 s, $0.0031, finish=stop. Brief + Antwort: `~/.hermes/cache/scratch/mimo_dashboard_review.md`.
Ergebnis ist ADVISOR-INPUT — Entscheidung bleibt bei Hermes/User; System-Evidenz schlägt Modellmeinung.

---

## 1. Ist-Zustand (verifiziert)

`src/content/dashboard.html` (145 Zeilen, generiert teilweise von
`tools/generate_home_sidebar.py`):

- Hero „Hermes" + **Bot-Fleet-Kacheln** = reine Links zu /botN mit Slot-Texten
  (z. B. „s724 #724 + r1 (geplant) … · max 4 Slots · Demo"). **Keine Zahlen.**
- 1 Tool-Kachel (Data Pipeline).
- 3 statische System-Karten: „Online" (hardcodiert), „v0.21.5", „mimo-v2.5"
  (beide hardcodiert, veralten still).

→ Fazit: Link-Launcher ohne Performance, Entwicklung oder Empfehlung. Der
E4-Swap (29.09.) hat das alte Dashboard bewusst unangetastet gelassen; es ist
heute die einzige Top-Nav-Zielfläche („Bots"-Dropdown) ohne Substanz.

## 2. Datenbasis (alles vorhanden, frisch, kein neues Backend nötig)

| Quelle | Alter | Kerninhalt |
|---|---|---|
| `api/overview/overview.json` | ~2 min | verdict (Ampel+why), 16 findings (7🔴/3🟡/6ℹ), live.kpis (equity_demo 7.912 € / equity_live 2.245 € / total 10.157 €, pnl_7d −45,80 €, pnl_30d +333,77 €, 4 offene Pos.), live.fleet[] je Bot (equity, pnl_7d, pnl_30d, dd_pct, dd_level, blocked, daily_pnl_pct, open_positions, slots[], equity_curve), shadow.kpis (782 Tr/30d, netto −777,58 €, 16 deployed), gates (62 Blocks/7d, release FX+Indices an / Metalle aus), execution_guard (TCA median/p90 2,95 bps), market_open |
| `api/strategy-lab/shadow_portfolio.json` | ~2 min | bots{} je Bot (strategy_id/name, pnl = nur aktuelle Strategie, trades, open_positions, equity, equity_curve), advisor.fleet (je Slot: state, recommendation action/priority/trigger/summary, reasons), portfolio_view (asset_class_coverage, clump_warnings z. B. „#317/#672 überlappen 60 %"), correlation, gate_skips_7d |
| `api/supervisor/supervisor_status.json` | ~7 min | 10 offene Empfehlungen (Quelle advisor/decay/promote, Priorität, Klartext), Woche 2026-W41, ops |
| `api/missions/missions_status.json` | ~7 min | 3 aktive Missionen, 6/17 Etappen |
| `api/botN/dashboard.json` | ~min | Detaildaten (bleiben auf Bot-Seiten) |

Bereits existierende Seiten (NICHT duplizieren): `/` Kommandocenter (Lage,
Findings, Gates-Leiste, Charts), `/strategy-lab` (Fleet-Radar, Advisor),
`/botN` (Details), `/supervisor`, `/missions`.

## 3. MiMo-Befunde (Advisor-Input, ungefiltert)

**Module (oben → unten):** 1) Lage-Zeile (Ampel + „7 Findings, 2 Bots
blockiert" + Daten-Timestamp, Link Kommandocenter). 2) „Jetzt zu tun"
(Top-3-Empfehlungen ÜBER der Performance: „Der Nutzer soll handeln, nicht
bewundern"). 3) Performance-Kompakt (Equity Demo/Live/Total, PnL 7d/30d in €
und %). 4) Fleet-Matrix = Herzstück (1 Zeile/Bot: Name · Equity · PnL 30d ·
Sparkline · Risk-Ampel · offene Pos. · Slots · Flags; sortierbar nach
Dringlichkeit). 5) Entwicklungs-Signale (Top/Bottom 7d, DD-Warnungen, Streaks,
Decay — nur mit n). 6) Risiko & Reibung (62 Blocks/7d, Slippage, Cluster-Warnungen).
7) Shadow-Kontext (1–2 Zeilen: 782 Tr/30d, −778 € — „ehrlich zeigen, dass
Strategie-Entwicklung kostet"). 8) Missionen/Wochenbericht (1 Zeile + Link).

**Performance-Regeln:** Primär % sekundär €; Fenster 7d + 30d + „seit Start
der aktuellen Slot-Strategie" (Rotation zerhackt Bot-Historie → kumulierte
Bot-Rendite widerspricht Evidenz-Doktrin); „zu wenig Daten" sichtbar machen
(Vorschlag n<20 grau, Tooltip „n=6, Stichprobe"); kein Gesamtscore; Demo und
Live getrennt zeichnen.

**Entwicklung:** 7d- vs 30d-Rate (zwei reale Fenster, keine Prognose);
DD aktuell + Zeit im DD; Decay-Flag mit Auslöser = ehrlichste Entwicklungs-
Aussage; Streak erst ab 5 Trades als Rohzahl; NICHTS unter n=10 — „keine
Evidenz" ist ein Feature.

**Empfehlungen:** Cluster nach Objekt (Bot/Slot) statt Quelle; Priorität
(a) Echtgeld/Handel blockiert → (b) aktiver Kapitalverlust (Decay/DD) →
(c) Optimierung. Zeilenformat mit Datenwert-Begründung + Status „Vorschlag,
offen"; Rest „+7 weitere → Supervisor"; nie Automatik suggerieren.

**3 typische Fehler:** Hierarchielosigkeit (Wand aus KPIs), Scheinpräzision
(Aggregat ohne Basis/n), Selbstbelohnungs-Charts. **Kniff:** Jede Zeile
beantwortet genau eine Frage — *Handeln / Beobachten / Nichts tun*.

## 4. Filter-Verdikte (Hermes gegen System-Realität)

| MiMo-Punkt | Verdikt | Begründung |
|---|---|---|
| 8-Modul-Struktur, „Jetzt zu tun" oben | ✅ bestätigt | Daten (supervisor/advisor) vorhanden; deckt User-Wunsch „Empfehlung" direkt |
| Fleet-Matrix als Herzstück | ✅ bestätigt | `overview.live.fleet[]` hat bereits alle Felder inkl. Sparkline-Kurven |
| Demo/Live getrennt, kein Gesamtscore | ✅ bestätigt | deckt Doktrin „ehrliche Ampeln, kein Schein-Score"; Messkonten ≠ Investment |
| „Zu wenig Daten" sichtbar | ✅ bestätigt, Schwellen angepasst | System-Konvention: Advisor nutzt bereits „Lesart: vorläufig" bei kleinen n → n immer mitschreiben, dimmen ab n<10 (statt hart n<20) |
| Fenster „seit Slot-Strategie-Start" | ✅ bestätigt | entspricht bestehender `bots_summary`-Logik (PnL nur aktuelle Strategie) |
| R-Multiples als Kennzahl | ❌ gestrichen | nicht Teil des Anzeige-Datenmodells; überflüssige Komplexität auf Übersichtsseite |
| Fenster-Toggle | ⚠️ vereinfacht | statische Seite ohne Backend → 7d UND 30d fix nebeneinander statt Toggle |
| Streaks ab 5 | 🟡 optional | Daten via decay_monitor ableitbar; nice-to-have, nicht Kern |
| „Zeit im DD" | 🟡 optional | wäre neue Ableitung aus risk_state; Phase 2 |
| Shadow-Zeile „Entwicklung kostet" | ✅ bestätigt | ehrliche Kontextzeile, genau die Transparenz-Doktrin |

**Hermes-Ergänzungen (nicht in MiMo-Antwort):**
- **Markt-Status** (`market_open`): am Wochenende „Markt geschlossen" statt
  irreführendem „0 Trades" — sonst wirkt jede ruhige Phase kaputt.
- **Frische-Chip** („Daten: vor 2 min") + Datenstand wie Kommandocenter.
- **Launcher erhalten:** Bot-Name in der Matrix klickbar → /botN (ersetzt die
  alten Kacheln; Slot-Texte entfallen, Details stehen auf den Bot-Seiten).
- **Kein neuer Dienst:** alles aus den 4 vorhandenen JSONs (Timer: overview
  5 min, shadow 15 min, supervisor/missions 15 min). Ggf. 1 kleiner
  Aggregat-Schritt in `build_overview_status.py` (Top-3-Empfehlungen, PnL-%).
- **Read-only:** Dashboard führt NICHTS aus; Empfehlungen sind Text + Links.

## 5. Gefilterte Design-Spec (Vorschlag zur Freigabe)

**Zielbild:** `/dashboard` = Fleet-Cockpit „Wie läuft's, was ist zu tun?" —
komplementär zum Kommandocenter (systemische Lage), ohne Detail-Duplikate.

**Module (oben → unten):**
1. **Lage-Zeile:** Gesamt-Ampel + „7 kritische Findings · 2 Bots blockiert" +
   Markt-Status + Datenfrische. Link → Kommandocenter.
2. **„Jetzt zu tun" (Top 1–3):** priorisiert gesperrt > Verlust > Optimierung;
   je Zeile: Bot/Slot · Was · Datenwert-Begründung · Status „Vorschlag".
   Rest-Zeile „+N weitere → Supervisor".
3. **Performance-Kompakt:** Equity LIVE / DEMO / Total (getrennt!), PnL 7d/30d
   (€ + % auf Kontostand), offene Positionen.
4. **Fleet-Matrix:** je Bot 1 Zeile — Dringlichkeits-Ampel, Name+Strategie
   (klickbar), Equity, PnL 7d/30d, Sparkline 30d, offene Pos., Slots ●/○/–,
   Flags (Decay/Parität/Risk-Block/neu). Sortierung: Dringlichkeit.
5. **Entwicklung:** Top/Flop 7d vs 30d (nur mit n), DD-Warnungen, Decay-Signale.
6. **Risiko & Reibung:** Blocks/7d (Release-Gate), Slippage median/p90,
   Cluster-/Korrelations-Warnungen.
7. **Shadow-Kontext:** 1–2 Zeilen (782 Tr/30d, netto −778 €, 16 deployed).
8. **Missionen:** 1 Zeile (3 aktiv, 6/17 Etappen) + Link.

**NICHT drauf:** Bot-Equity-Charts, Heatmap, Trade-History, Advisor-Score-
Zahlen, Paritäts-Details, Slot-Texte, Missions-Etappen, Wochenbericht-Text
(alles existiert auf den Detailseiten → sonst Duplikat wie beim Launcher).

**Messbares Erfolgssignal:** Seite beantwortet in <10 s: (a) Wie läuft die
Fleet? (b) Was ist die aktuelle Entwicklung? (c) Was ist jetzt zu tun? —
und keine Zahl ohne n/Basis/Fenster.

## 6. Umsetzungsvorschlag (nach Freigabe)

- E1: Aggregat erweitern (`build_overview_status.py`): `recommendations_top3`
  (Cluster+Priorität aus advisor/supervisor), `pnl_pct`, `market_open`-Label.
- E2: `dashboard.html` neu (Module 1–8; JS aus vorhandenen JSONs, SVG-
  Sparklines; `generate_home_sidebar.py`-Block wird durch Matrix ersetzt).
- E3: Tests (`tests/test_dashboard_page.py`: Pflicht-IDs, node --check,
  build_page-Smoke) + `make test`; E2E lokal (http.server + DOM) + Live-Check.
- Reihenfolge: kein Echtgeld berührt; Umsetzung autonom möglich, Etappen +
  Verifikation wie üblich. Aufwand: 1–2 Arbeitseinheiten (mittel).

## 7. Entscheidungsliste (User)

1. Zielbild ok? (/dashboard = Fleet-Cockpit, komplementär zum Kommandocenter)
2. Module/Reihenfolge ok? Insb. „Jetzt zu tun" ÜBER der Performance?
3. PnL-%: Basis = aktueller Kontostand (Vorschlag) oder Startkapital?
4. Streak-/„Zeit im DD"-Anzeige: jetzt oder Phase 2?
5. Go für Umsetzung (E1–E3)?

**Konsultations-Kosten:** $0.0031 (ein Call). Antwort-Roh: 4.364 Zeichen,
vollständig (finish=stop).
