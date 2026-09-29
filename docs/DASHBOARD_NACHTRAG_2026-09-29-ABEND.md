# Nachtrag 2026-09-29 (abends) — E4-Folgearbeiten & Multibot-Textfixes

## 1. Multibot-Seiten vs. Kommandocenter (User-Befund)

Befund: Kommandocenter (`/`, `api/overview/overview.json`) war korrekt
(bot3 5 Slots, bot5 2, bot7 3). Veraltet waren:

- `src/data/bots/bot3.json` — Intro/Tags/Chips sagten „2 Slots + 1 Rotationsslot“;
  real: 2 feste Slots + Türen srot/d4/d5 (Challenges #663/#696/#681).
- `src/data/bots/bot7.json` — m3 fehlte (Challenge #684); Chip „2 Slots“ → 3.
- Bot-Fleet-Sidebar in `src/content/dashboard.html` — Zeilen ohne d4/d5/m3.
- `tools/generate_home_sidebar.py` zeigte noch auf `index.html` (seit E4-Swap falsch) →
  Fix: Ziel `src/content/dashboard.html`; danach `build_bot_pages.py` + `build.py` + Push
  (Commit c3972cb91).

## 2. Kommandocenter-Datenlayer-Refresh (neu)

`build_overview_status.py` (Laufzeit ~0,5 s) hatte keinen Timer — `overview.json` alterte
ab dem letzten manuellen Lauf. Neu: `overview-rebuild.service` + `.timer`
(`/etc/systemd/system/`, OnBootSec=3min, OnUnitActiveSec=5min, Type=oneshot,
TimeoutStartSec=120). Erster Lauf 29.09. 19:31 ✓, Journal sauber.

## 3. Verifikation

- Lokal `_build`: bot3 („5 Slots (2 fest + 3 Türen)“, „3 Rotations-Türen (srot, d4, d5)“),
  bot7 („3 Slots (1 fest + 2 Türen)“, „mrot und m3“), dashboard.html
  („+ d4 → #696 + d5 → #681“, „+ m3 → #684“) ✓.
- Live-Check (curl mit Basic-Auth) vom Consent-Guard blockiert — offen (User-Check/Consent).

Hinweis: `build_bot_pages.py` + `tools/generate_home_sidebar.py` sind NICHT im 6h-Auto-Rebuild
(`site-rebuild.timer` = `smart_rebuild.py site`) → nach Bot-/Slot-Umbauten manuell laufen.
