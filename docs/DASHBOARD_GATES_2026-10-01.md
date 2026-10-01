# DASHBOARD GATES — Release-/Markt-Gate-Transparenz (A+B) — 2026-10-01

## Was & warum

User-Frage: „Sind die Trading-Gates transparent dargestellt — bei den Bots oder im
Shadow?" Befund: Release-Gate (aktiv seit 28.09.) war **nirgends** im UI sichtbar;
Botleitfaden zeigte veraltete Regeln („Fr 19:30 alle schließen", „60min-Blackout").
User-Entscheid: **„a+b"**.

- **A** — Kommandocenter: feste „Markt & Gates"-Leiste + Datenlayer `overview.json.gates`;
  Botleitfaden auf Ist-Stand korrigiert.
- **B** — Jede Gate-Blockade wird persistiert (`gate_skips.jsonl`) und im
  Shadow-Tab als „🚧 Gate-Blocks (7 d)" je Strategie sichtbar.

## Datenfluss (Single Source of Truth)

```
trend_executor / shadow_trader  (Release-Blackout beim Entry-Filter)
   └─ src/gate_skip_log.py :: log_gate_skip()   [fail-soft, wirft nie]
        → /root/fx-bot/data/gate_skips.jsonl    [append-only JSONL]
             ├─ build_overview_status.release_gate_section()
             │     → api/overview/overview.json [gates]
             │     → Kommandocenter #gates-strip:
             │       Markt 🟢/🔴 · Release-Gate (Klassen) · Nächster Block · Gate-Skips 7 d
             └─ shadow_portfolio_builder.build_gate_skips_7d()
                   → api/strategy-lab/shadow_portfolio.json [gate_skips_7d]
                   → build_v4 renderShadowDashboard → Shadow-Tab
                     „🚧 Gate-Blocks (7 d)" (Sektion 3, per-SID-Karten)
```

Klassen-Schalter & Fenster-Referenz bleiben SSOT: `src/market_hours.py`
(`RELEASE_GATE_ENABLED`, `_GATE_CLASSES`, `pre_min=30`) — das Kommandocenter
importiert sie (`_gate_classes`), die Doku hier ist nur Spiegel.

## Dateien (alle Änderungen 2026-10-01)

| Datei | Änderung |
|---|---|
| `fx-bot/src/gate_skip_log.py` | NEU — `log_gate_skip(gate, source, symbol, reason, bot, sid)`; append-only, fail-soft |
| `fx-bot/src/trend_executor.py` | Release-Skip-Hook (lazy import, best-effort) |
| `fx-bot/src/shadow_trader.py` | Release-Skip-Hook (SKIP-Pfad) |
| `fx-bot/src/shadow_portfolio_builder.py` | `build_gate_skips_7d()` + `output["gate_skips_7d"]` |
| `fx-bot/tests/test_gate_skip_log.py` | 6 Tests (JSONL-Format, fail-soft, Append) |
| `fx-bot/tests/test_shadow_gate_skips.py` | 4 Tests (7d-Fenster, per_sid, recent, Berlin-Zeit) |
| `site/build_overview_status.py` | `release_gate_section()` (+ `gates` in overview_v1) |
| `site/src/content/index.html` | CSS + `#gates-strip` + `renderGates()` |
| `site/src/content/botleitfaden.html` | Weekend-Gate + Release-Gate auf Ist-Stand |
| `site/tests/*` + `fixtures/overview_small.json` | Gates-Asserts (20/20, 25/25, 25/25) |
| `strategy-lab/src/website/build_v4.py` | Shadow-Tab „Gate-Blocks (7 d)" |
| `strategy-lab/tests/test_shadow_gate_blocks.py` | 8 Checks (Quelltext + node --check) |

## Betrieb

- `overview-rebuild.timer` — alle 5 min → `overview.json` (inkl. gates).
- `shadow-portfolio-builder.timer` — alle 5 min (`shadow_portfolio.json`; 240-s-Cooldown
  → „skip" ist normal); zusätzlich rebuildet der `shadow-trader`-Zyklus (15 min) die Datei.
- Executoren: nach Hook-Deploy einmalig `systemctl restart bot{1..10}-executor` nötig;
  Shadow übernimmt neuen Code beim nächsten Zyklus automatisch.
- **Fail-soft überall**: fehlende/kaputte Quellen → `0`/`null`, nie Crash; Release-Daten
  gelten als `stale` bei >48 h mtime (Badge „Daten alt" im Kommandocenter).

## Verifikation (Evidenz 01.10.)

- Builder-Tests: `test_build_overview.py` 20/20 · `test_overview_page.py` 25/25 ·
  `verify_overview_charts.js` 25/25 (davon 4 Gates-DOM-Checks) · `test_shadow_gate_blocks.py` 8/8 ·
  fx-bot: `test_gate_skip_log.py` 6/6 + `test_shadow_gate_skips.py` 4/4.
- Live-Build: `overview.json.gates` = release an, classes `{fx, indices}`, nächste Blöcke
  NFP + Unemployment Rate 02.10. 14:00–14:30 BZ, `data_age_h` plausibel, `stale:false`.
- **DOM Kommandocenter** (`127.0.0.2:8099`): `#gates-strip` = „Markt: offen · Release-Gate:
  an (FX + Indizes · Metalle aus) · Nächster Block: Non-Farm Employment Change 02.10.
  14:00–14:30 BZ · 30 min vor +1 · Gate-Skips 7 d: 0".
- **DOM Shadow-Tab**: Sektion „🚧 Gate-Blocks (7 d) — geblockte Entry-Signale" als
  Sektion 3 (nach Klumpenrisiko, vor Offene Positionen), Inhalt „🟢 0 Blocks in 7 d"
  (stabil über Tab-Wechsel); badge-shadow unverändert.
- Botleitfaden: „19:30"-/„60min"-Reste = 0; Weekend-Gate ×4 in gebauter Seite.
- Executoren 10/10 `active`, keine Fehler-Logs seit Restart.

## Ehrliches Kleingedrucktes / Offen

- Erste **echte** `gate_skips.jsonl`-Zeilen entstehen erst beim nächsten Entry-Signal im
  Block-Fenster (z. B. NFP Fr 02.10. 14:30 BZ) — bis dahin zeigen beide Oberflächen
  ehrlich **0**.
- Markt-Gates (Weekend/Feiertag/Tagespause) werden in v1 bewusst **nicht** persistiert
  (kein Rauschen; Release-Gate zuerst) — bei Bedarf als `gate:"market"` nachrüstbar.
- Shadow-Empfehlung „Release-Gate auch für Metalle prüfen" offen (keine Evidenz, n=18).
