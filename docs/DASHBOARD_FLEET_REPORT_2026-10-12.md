# REPORT — /dashboard → Fleet-Cockpit (v1)

Workspace: `/root/worktrees/dashboard-fleet-2026-10-12` (Repo `site`).
Auftrag: `AGENTS.md` (Workspace-Root). Datengrundlage: api-JSONs Stand 11.10.2026.

## Deliverables (alle erledigt)

| # | Datei | Status |
|---|-------|--------|
| 1 | `site/src/content/dashboard.html` | neu (Fleet-Cockpit M1–M8 + Meta) |
| 2 | `site/build_overview_status.py` | additiv: `n_7d`/`n_30d` je Bot |
| 3 | `site/tests/test_dashboard_page.py` | NEU (7 Checks) |
| 4 | `site/tests/test_build_overview.py` | 1 additiver Assert in `t_fleet` |
| 5 | `site/tools/generate_home_sidebar.py` → `site/archive_legacy/scripts/` | `git mv` + Archiv-Docstring |
| 6 | `REPORT.md` | diese Datei |

## Abnahme (selbst ausgeführt, Ausgaben wörtlich)

### 1) Seiten-Checks
```
$ cd site && /usr/bin/python3 tests/test_dashboard_page.py
PASS Fragment-Marker TITLE/HEAD/BODY
PASS Pflicht-IDs vorhanden (16)
PASS genau 1 inline-<script>
PASS node --check inline-JS
PASS CSS-Variablen definiert oder Fallback
PASS build_page-Smoke enthält db-matrix
PASS keine Alt-Reste (generate_home_sidebar/quick-link/v0.21.5/mimo-v2.5)

ALLE CHECKS OK
```

### 2) Gesamt-Suite
```
$ cd site && make test
== tests/test_build_missions.py … == tests/verify_overview_charts.js   (alle einzeln)
… RESULT: 27 PASS, 0 FAIL   (verify_overview_charts.js)
SITE TESTS OK
```
`tests/test_dashboard_page.py` läuft in `make test` mit (Zeile `== tests/test_dashboard_page.py` im Lauf).

`tests/test_build_overview.py`: `20/20 PASS, 0 FAIL` / `ALLE PASS` (neuer Roster-Assert in `t_fleet` grün).

### 3) Einzel-Build
```
$ cd site && /usr/bin/python3 -c "import build; build.build_page('src/content/dashboard.html','_build/dashboard.html')"
  Built _build/dashboard.html (path=/dashboard)
```
`_build/dashboard.html` enthält `db-matrix` (vom Smoke-Check mitgeprüft).

### 4) Git-Status / Diff-Stat
```
$ cd site && git status --short
RM  tools/generate_home_sidebar.py -> archive_legacy/scripts/generate_home_sidebar.py
 M  build_overview_status.py
 M  src/content/dashboard.html
 M  tests/test_build_overview.py
??  tests/test_dashboard_page.py

$ git diff --stat
 site/-…/scripts/generate_home_sidebar.py   |   4 +-
 site/build_overview_status.py              |  16 +-
 site/src/content/dashboard.html            | 644 +++++++++++++++++++++++++-----
 site/tests/test_build_overview.py          |   3 +
 4 files changed, 527 insertions(+), 140 deletions(-)
$ git diff --cached --stat      # Rename (Staging aus git mv)
 site/{tools => archive_legacy/scripts}/generate_home_sidebar.py | 0
```
Nur erwartete Dateien. `api/*.json`, `assets/base.css`, `base.html`, `nav.json` unangetastet.
Getrackte `__pycache__/*.pyc` (Test-Artefakte des Baseline-Repos) wurden nach den Testläufen
per `git restore` auf den Commit-Stand zurückgesetzt → nicht im Diff.

## Builder-Änderung (additiv, exakt wie Spec)

`site/build_overview_status.py`:
- Z. 639 `counts = {d: 0 for d in THRESH_PNL_WINDOW_DAYS}`
- Z. 673 `counts[d] += 1` in der Fenster-Schleife
- Z. 681/683 Fehlerreturns `(None, {}, {}, {})`; Z. 684 `return sums, daily, monthly, counts`
- Z. 1127 einziger Aufrufer → 4er-Tupel `trades_counts`
- Z. 1182/1183 `"n_7d": trades_counts.get(7)`, `"n_30d": trades_counts.get(30)` direkt nach `pnl_30d`

Verifikation: `/usr/bin/python3 -m py_compile build_overview_status.py` → OK; Fixture-Test
`tests/test_build_overview.py` grün (bot1 → 2/3, bot4 → 1/1 Trades in 7/30 d, Assert grün).

## Archivierung (Deliverable 5)

`git mv tools/generate_home_sidebar.py archive_legacy/scripts/generate_home_sidebar.py`,
Docstring-Kopf ergänzt: `ARCHIVIERT 2026-10-12: /dashboard rendert live aus api-JSONs; kein Aufrufer.`

`grep -rn "generate_home_sidebar" .` vor/nach dem Move — **weitere Fundstellen (nur gemeldet, NICHT geändert)**:
- `site/docs/DASHBOARD_FLEET_UEBERSICHT_MIMO_2026-10-11.md:17` und `:137`
- `site/docs/DASHBOARD_NACHTRAG_2026-09-29-ABEND.md:12` und `:30`
- `site/README.md:28`
- (im archivierten Skript selbst: `archive_legacy/scripts/generate_home_sidebar.py:16,113`)
- (in der neuen Negativ-Testliste: `tests/test_dashboard_page.py`)

Kein Produktivcode ruft das Skript auf; die Marke im früheren `dashboard.html` ist mit der
neuen Seite entfallen.

## Seite: Struktur und Modul-Mapping

`src/content/dashboard.html` — Fragment-Marker TITLE/HEAD/BODY, `<style>` im HEAD, genau **ein**
inline-`<script>`, keine externen Libs. `setInterval(load, 60000)` + `cache:'no-store'`; Module
werden per `innerHTML` neu gerendert; alle dynamischen Strings durch `esc()`. Beträge de-DE via
`Intl.NumberFormat`, Prozente 1 Dezimale mit Vorzeichen, Zeiten `DD.MM. HH:MM` (Europe/Berlin).
Ampel über `--c-err/--c-warn/--c-ok`; Layout zentriert, Karten `--c-surface/--c-border`, CSS-Grid,
`@media (max-width:720px)` stapelt.

| Modul | ID(s) | Quelle |
|-------|-------|--------|
| Fehlerbanner | `#db-error` | overview.json (bei Ausfall) |
| M1 Status | `#db-status` / `#db-status-text` | `verdict.overall`, `market_open`, `generated_at_bz` |
| M2 Aktionen | `#db-actions` / `-list` / `-more` | supervisor `recommendations.items` (high→mid→low, Top 3) |
| M3 Performance | `#db-perf` / `-demo` / `-live` / `-total` | `live.kpis` + Σ`pnl_7d/30d` über `fleet[is_live]` |
| M4 Matrix | `#db-matrix` | `live.fleet` + `shadow_portfolio.bots/advisor.fleet` + `findings` |
| M5 Entwicklung | `#db-dev` | `fleet` (Top/Flop 7d), `dd_level`, `findings ^Decay` |
| M6 Risiko | `#db-risk` | `gates.blocks_7d`, `execution_guard.tca/counterfactual`, `clump_warnings` |
| M7 Shadow | `#db-shadow` | `shadow.kpis` |
| M8 Missionen | `#db-missions` | missions `kpis` |
| Meta | `#db-meta` | `generated_at_bz`, `shadow_portfolio.updated_at` |

Laufzeit-Smoke (Node-Harness, außerhalb des Repos; DOM- + fetch-Stub gegen die echten JSONs):
Status, 3 Performance-Karten, 10 Matrix-Zeilen (Sortierung 1,3,6,9,10 → 5,7,8 → 2,4),
Entwicklung/Risiko/Shadow/Missionen/Meta korrekt gerendert; Fehlerbanner `display:none`.
Beispiele: `ROT: 7 kritische Findings · Markt geschlossen · Stand 11.10. 22:11`;
`GESAMT 10.157,07 € 7d −45,80 € (−0,5 %) · 30d +333,77 € · 4 offene Positionen`;
`Shadow 782 Trades/30d · netto −777,58 € · 16 deployt`;
`62 geblockte Entries/7d … Slippage median −0,34 bps / p90 2,95 bps (n=223) · Guard: costs (n=5, 36,5 h alt)`.

## Hinweise / offene Punkte

- Der mitgelieferte Snapshot `site/api/overview/overview.json` stammt **vor** der Builder-Änderung
  und enthält noch kein `n_7d`/`n_30d`; die Seite rendert dort regelkonform „—" (keine erfundenen
  Zahlen). Nach dem nächsten `build_overview_status.py`-Lauf zeigen M4 `7d ±X € (n)` und M5
  Top/Flop die Zählwerte.
- Keine Live-Pfade angefasst, keine Secrets gelesen, keine systemd-/Deploy-Aktionen.
