# REPORT — dash-e1-overview: Datenlayer „System-Overview" (build_overview_status.py)

## 1. Kurzüberblick

| Deliverable | Pfad (Workspace) | Zeilen |
|---|---|---|
| Tool | `site/build_overview_status.py` | 1451 |
| Tests | `site/tests/test_build_overview.py` | 466 (18 asserts) |
| Report | `REPORT.md` (diese Datei) | — |

`build_overview_status.py` erzeugt `api/overview/overview.json` (Schema `overview_v1`) aus
ausschließlich vorhandenen Quellen (fx-bot-Daten, Strategy-Lab, Spot-Feed, Site-Pipeline,
decay/tca-Subprozesse). Reiner Datenlayer: keine HTML/CSS/JS-Änderung, kein build.py-/
smart_rebuild-Lauf, keine Änderung an fx-bot-Code (`git status --short`: nur die 3 neuen
Pfade, s. §3).

## 2. Verifikation (Pflicht)

### 2.1 py_compile
```
$ cd site && python3 -m py_compile build_overview_status.py tests/test_build_overview.py
COMPILE_OK
```

### 2.2 Fixture-Tests
```
$ python3 tests/test_build_overview.py
PASS  schema+top-keys
PASS  fleet-discovery
PASS  equity/balance-Skalierung
PASS  PnL-Fenster 7/30d + daily
PASS  is_live/dd_level/blocked/multi
PASS  shadow-kpis+mirror-exclusion
PASS  ranking aus catalog
PASS  challenge+rotation
PASS  curves+total_curve
PASS  monthly_pnl 12 Monate
PASS  exposure-Klassen
PASS  corr-Matrix
PASS  sources vollständigkeit
PASS  verdict YELLOW (risk_state fehlt)
PASS  verdict RED (decay demote)
PASS  verdict GREEN (healthy)
PASS  feed-rule red@market_open
PASS  missing-root: kein Crash

18/18 PASS, 0 FAIL
ALLE PASS
```
18 assert-Statements (Spec-Ziel 10–18), 0 FAIL. Tests monkeypatchen
`run_decay_monitor`/`run_tca_report` (build_overview_status.py:228-294 — eigene
Modulfunktionen wie gefordert); Fakes schreiben die Output-Datei wie der echte
Subprozess (decay_monitor.py:799-802 legt Zielverzeichnis selbst an).

### 2.3 Trockenlauf gegen Workspace-Fixtures (ECHTE decay/tca-Subprozesse)
Fixture: per `test_build_overview.make_fixture()` erzeugtes tmp-Fx/SL/TD-Set im
Workspace-Scratch (`.dryrun/fixture_final`, nach dem Lauf entfernt) + Kopien der
Workspace-`fx-bot/scripts/decay_monitor.py`/`tca_report.py` ins Fixture-fx (die echten
Subprozesse laufen gegen das Fixture-fx-root, cwd=fx).
```
$ python3 site/build_overview_status.py \
    --root .dryrun/fixture_final/root --fx-root .dryrun/fixture_final/fx \
    --sl-root .dryrun/fixture_final/sl --trading-data .dryrun/fixture_final/td \
    --now 1790683200 --out .dryrun/fixture_final/root/api/overview/overview.json

[build_overview_status] .../api/overview/overview.json
[build_overview_status] overall=yellow (GELB: 1 Warnung) | findings=2 fleet=2 sources=16 market_open=True

real    0m0.201s   (Spec: < 15 s ✓; decay- + tca-Subprozess erfolgreich, exit 0)
```
JSON-Kopf (kompakt):
```json
{
 "schema": "overview_v1",
 "generated_at_utc": "2026-09-29T12:00:00Z",
 "generated_at_bz": "2026-09-29T14:00:00+02:00",
 "market_open": true,
 "verdict.overall": {"status": "yellow", "headline": "GELB: 1 Warnung",
                     "why": ["risk_state fehlt für bot4"]},
 "kpis": {"equity_demo": 985.1, "equity_live": null, "equity_total": 985.1,
          "pnl_7d": 21.5, "pnl_30d": 41.5, "open_positions": 2},
 "shadow.kpis": {"n_trades_30d": 8, "net_30d": 18.0, "n_deployed": 2},
 "fleet": [["bot1", 985.1, 982.34, 9.5, 29.5, false],
           ["bot4", null, 500.0, 12.0, 12.0, true]],
 "n_findings": 2, "n_sources": 16
}
```
Echter decay-Subprozess gegen Fixture (Beleg echte Feldnamen, `shadow.decay.counts`):
`{"total": 2, "tableau": 0, "demote": 0, "watch": 0, "ok": 0, "insufficient": 2}`;
Row-Keys (echter Lauf): `bot, sid, role, is_live, account_id, live, sim, ratio, status,
status_label, reasons`. tca `groups` = `overall, by_symbol, by_session, by_month`
(`overall` leer bei Fixture-Trades ohne fill_price → p90 null, korrekt defensiv).

### 2.4 Während der Arbeit gefundene und behobene Bugs (evidenzbasiert)
| Bug | Fix |
|---|---|
| Relative Pfade + `cwd=`-Wechsel: Subprozess resolve'te Skript-Pfad relativ zum KIND-Cwd → decay/tca „fehlgeschlagen" im Trockenlauf | abspath von fx_root/out_path/script VOR dem Aufruf (build_overview_status.py:236-237, 261-262) |
| `queue_counts=None` bei fehlendem catalog.db → Crash in verdict-Metrics (Zeile 1303 im ersten Lauf, AttributeError) | Normalisierung direkt nach `_catalog_stats` (:1072-1076) |
| `equity_live: 0.0`, obwohl der Live-Bot keine Equity hat (Schein-Zahl) | `_kpi_sum` → None wenn kein Bot einen Wert liefert (:991-997); Test-Assert erweitert |
| Fehlende trades-Datei ergab `pnl_7d: 0.0` (Schein-Zahl) | `null` statt 0 (:855) |
| Duplikat-Block „bucket = …" nach Risk-Findings | entfernt (jetzt :924-928) |
| Trailing-Comma machte `sources.add(...)` zum Tuple-Ausdruck (spots) | behoben (:784-786) |

## 3. Design-Entscheidungen (jeweils mit Beleg)

1. **balance/equity-Skalierung**: `botN_balance.json` hält RAW-Einheiten
   (×10**money_digits) — Umrechnung `/10**money_digits` wie
   `fetch_bot_balance.py:199-203` und `shadow_portfolio_builder.py:253-257`.
   `risk_state.equity` und balance_history-Snapshots sind bereits EUR
   (`risk_guard.py:125-145` rechnet dd_pct direkt daraus) → keine Skalierung.
2. **Equity-Priorität je Bot**: risk_state.equity → letzte Curve-Equity →
   balance.json-Equity; Equity in Curves bevorzugt mit dem dokumentierten
   Sanity-Guard `|equity−balance| ≤ max(75€, 10 %|balance|)` (Regel aus
   `shadow_portfolio_builder.py:293-298`), Fallback balance.
3. **is_live-Regel**: `risk_state.is_live` (bool) falls vorhanden; sonst Registry:
   `demo: false → live`, `demo: true → demo`, `demo` unbekannt → **live**
   (konservativ, dokumentiert in :864-871). Begründung: ein als Demo angezeigter
   Live-Bot würde Risk-Aggregate unterschlagen.
4. **multi**: `len(slots) > 1` (:517; Multi-TOML-Slots + Rotationsslots, Konvention
   `shadow_portfolio_builder.py:64-134`), zusätzlich Registry-`strategy_id`-Liste > 1.
5. **Shadow-Scopes**: KPIs/Charts 30d; **Ranking = Top 15 über 30d** (aligniert mit
   `kpis_30d`; Spec nennt kein Fenster — bewusst gewählt, frische Top-View). Nur
   int-`strategy_id`-Rows zählen; `"<sid>@<bot>"`-Mirror-Rows werden wie in
   `decay_monitor.py:520-533` ausgeschlossen (keine Doppelzählung, Test belegt).
6. **PnL-Regel**: `cTrader_profit` → Fallback `pnl`; `closed_at` toleriert ISO (Z/
   Offset) und `YYYY-MM-DD HH:MM:SS`; nur `0 ≤ now−closed ≤ Fenster`
   (`_sum_trades`, :733-774; Test `PnL-Fenster` belegt beide Formate + Fallback).
7. **risk_guards `.defaults`**: `l1_alert_pct`/`l2_block_pct` werden NICHT hardcodiert —
   sie liefern den Level-Fallback, wenn `risk_state.level` fehlt aber `dd_pct` da ist
   (:893-900); fehlen die Schwellen, bleibt dd_level null (keine Annahme).
8. **market_open**: exakt die geforderte vereinfachte UTC-Regel (Sa ganz, So <21:00,
   Fr ≥21:00 zu; :212-224). Feed-Regel: >900 s red bei market_open, sonst yellow;
   >300 s yellow.
9. **exposure.open_risk_eur = null**: Position-Risk in EUR bräuchte contract_sizes/
   EUR-Raten (fx-bot-Modul, nicht stdlib-replizierbar ohne Logik-Fork) — bewusst null
   statt Schein-Zahl (Hermes-Regel „keine Schein-Scores"). Offener Punkt §5.
10. **corr**: Pearson über Tages-PnL (30d) der Slot-SIDs (Multi-TOML + Rotation/Challenge),
    Union-Datumsraster mit 0-Fill; Varianz 0 oder n<2 → null (`_pearson` :183-202).
    Labels = sortierte unique Slot-SIDs, ≤8.
11. **Sources-Familien**: pro Bot-Datei-Familie EIN sources-Eintrag (Glob-Pfad,
    max-Alter über vorhandene Dateien, Note nennt fehlende Bots) — 16 Einträge
    statt ~50. Pflichtquellen: je fehlender max 1 yellow-Finding
    (`src_finding`-Dedupe :715-724).
12. **decay `tableau` → red**: Spec-Pflichtregeln nennen demote/red und watch/yellow;
    `tableau` ist in decay_monitor die schärfere Stufe (STATUS_ORDER, decay_monitor.py:56)
    → ebenfalls red (Erweiterung, keine Lücke).
13. **Atomarer Write**: tmp + `os.replace` (Muster `smart_rebuild.py:203-208`),
    Zielverzeichnis wird angelegt (:1408-1418 + `os.makedirs(out_dir)` :1119).
14. **Nur stdlib** (argparse/json/math/os/sqlite3/subprocess/sys/time/datetime/
    pathlib/zoneinfo/tomllib — py_compile + Import-Check belegt); catalog.db wird
    READ-ONLY via `file:...?mode=ro` geöffnet (Konvention `build_trend_status.py:723`).

## 4. Annahmen (echte decay/tca-Feldnamen)

- decay: Feldnamen aus ECHTEM Lauf der Workspace-Kopie gegen Fixture-Daten
  verifiziert (§2.3): `bots[]{bot,sid,role,is_live,account_id,live,sim,ratio,status,
  status_label,reasons}`, `summary{total,tableau,demote,watch,ok,insufficient}` —
  **Annahme: identisch mit Live-Daten**; Reader ist defensiv (fehlende Keys →
  keine Findings, `shadow.decay` null).
- tca: `groups{overall,by_symbol,by_session,by_month}`, Stats-Keys
  `n, mean_bps, median_bps, p90_bps, adverse_pct, mean_drift_pips,
  mean_exec_slip_pips` (tca_report.py:326-334) — **Annahme: identisch mit Live**;
  `charts.tca_groups` wird unverändert durchgereicht, p90-Threshold liest nur
  `groups.overall.p90_bps` defensiv.
- `THRESH_TCA_P90_BPS = 2.0` ist ein Platzhalter-Wert (kein Vorgabewert in der Spec);
  als THRESH-Konstante justierbar (build_overview_status.py:69).

## 5. Offene Punkte

1. **open_risk_eur** bleibt null (Entscheidung §3.9); echte EUR-Risiko-Berechnung
   bräuchte einen stdlib-sicheren Export von `contract_sizes.py`-Logik oder eine
   risk_seitige Vorberechnung.
2. **smart_rebuild/build.py-Registrierung** fehlt bewusst (Spec verbietet
   build.py/smart_rebuild-Arbeit): der Builder wird erst nach Freigabe in die
   `JOBS`-Registry von `smart_rebuild.py` (watch_dirs: fx-bot/data, out:
   api/overview/overview.json) und die Cron-Liste aufgenommen.
3. **worker_status-Feldnamen** (`status, strategy_type, elapsed_s, message,
   updated_at`) sind aus dem Konsumenten `site/src/content/strategy-lab.html:1432-1458`
   abgeleitet (Workspace enthält keine strategy-lab-Kopie) — Reader defensiv
   (fehlende Keys → null).
4. **Ranking-Fenster 30d** ist eine Design-Wahl (§3.5); falls All-Time gewünscht,
   THRESH-ähnlich umstellbar.
5. **Monthly-Chart zeigt 0.0** für Monate ohne Trades (Basislinie fürs Charting);
   KPIs/Quellen bleiben bei fehlenden Quellen null. Falls null bevorzugt wird:
   `_round2(...get(ym, 0.0))` → `get(ym)` in :1247-1252.

## 6. Harte Regeln — Compliance

- Nur im Workspace geschrieben (`git status --short`: `site/build_overview_status.py`,
  `site/tests/`, `site/__pycache__/*.pyc`, `REPORT.md`); Scratch `.dryrun/` wieder
  entfernt. Live-Pfade (/root/fx-bot, /root/strategy-lab, /root/trading,
  /root/.hermes/**) nicht gelesen und nicht beschrieben — alle Daten aus Fixtures.
- Kein Netzwerk, kein systemctl, kein git commit/push, keine Installationen, kein
  build.py/smart_rebuild-Lauf.
- Keine Secrets in Deliverables.

## 7. Nachtrag: Hermes-Verifikation & Live-Integration (2026-09-29)

- Integration nach `/root/.hermes/site`: `build_overview_status.py`,
  `tests/test_build_overview.py` (+ dieses Dokument). Fixture-Suite im Live-Repo:
  **18/18 PASS**; `py_compile` OK; `delegate_verify --apply-check` **ALLE CHECKS OK**.
- **E2E-Trockenlauf gegen ECHTE Quellen** (erste `api/overview/overview.json`):
  verdict=yellow, findings=1 (`bot8: Risk-Level 1` — deckt sich mit bekannter Live-Lage),
  sources=16 (11 fresh, 5 old, 0 stale), fleet=10 Bots, equity_total≈9987 €.
- **E2E-Fund + Fix (Z.851ff, `trades_family_age` min statt max):** vorher nahm die
  Family die ÄLTESTE `botN_trades.jsonl`-Mtime (idle Bots, z. B. bot10 10,9 d) → fälschlich
  "stale". Jetzt min = frischeste Datei (idle Bots sind normal); balance/hist/rs/pos bleiben
  bewusst max (Writer laufen minütlich). Nach Fix: `fx.trades` "old" (~33 min), 0 staleness.
- Offene Punkte §5 gelten weiter; smart_rebuild-Registrierung erfolgt mit der
  Seiten-Integration (E2/E4), alte Homepage bleibt bis dahin unangetastet.