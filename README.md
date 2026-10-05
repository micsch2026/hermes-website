# Hermes Website — Struktur

Statische, template-basierte Site für **hermes.nexusfortis.org** (Caddy, Basic Auth).
Letztes Struktur-Update: **2026-10-05** (Struktur-Audit: Nav 6 Punkte + Bots-Dropdown,
Alt-Seiten/APIs archiviert, Alt-Timer gestoppt).

## Architektur

```
/root/.hermes/site/
├── src/
│   ├── data/
│   │   └── nav.json          ← Single Source of Truth (Navigation: 6 Punkte, „Bots" mit children)
│   ├── templates/
│   │   ├── base.html         ← Base-Template ({{title}}, {{nav}}, {{content}})
│   │   ├── bot.html          ← Bot-Seiten-Template (build_bot_pages.py)
│   │   └── bot-components.js, bot.css  (→ nach assets/ synchronisiert)
│   └── content/              ← Content-Fragmente (DAS ist die Quelle, nie _build editieren)
│       ├── index.html        ← Kommandocenter (/)
│       ├── dashboard.html    ← Bots-Hub (/dashboard, Nav-Eintrag „Bots")
│       ├── botN.html         ← Bot #N Dashboard — GENERIERT von build_bot_pages.py
│       ├── strategy-lab.html ← Strategy Lab — GENERIERT von strategy-lab/src/website/build_v4.py
│       ├── research-library.html
│       └── data/index.html   ← Data Pipeline (/data/)
├── build.py                  ← Generator: src/content/** → _build/**  (+ git_auto_push)
├── _build/                   ← GENERATED OUTPUT (Caddy-Root, .gitignore'd)
├── assets/, api/             ← CSS/JS bzw. JSON-Endpunkte (via Symlink in _build)
├── tools/generate_home_sidebar.py  ← schreibt den Fleet-Block in src/content/dashboard.html
└── archive_legacy/           ← Archiv: alte Seiten/Skripte/Backups (NICHT gebaut)
```

## Build-Prozess

```bash
cd /root/.hermes/site && python3 build.py
```

`build.py` baut alle Seiten aus `src/content/**` nach `_build/`, synchronisiert die Bot-Templates,
generiert die Bot-Seiten (`build_bot_pages.py`) und committet + pusht (`git_auto_push`, Auto-build).

Automatik: `site-rebuild.timer` (smart_rebuild.py site, 6 h + Change-Detection), der
Strategy-Lab-Worker ruft `build.py` am Zyklusende; Bot-Status-Timer schreiben nur `api/**`.

Semantische Änderungen **vor** dem Build mit expliziten Pfaden committen — sonst landen sie im
„Auto-build"-Sammelcommit.

## Navigation

`src/data/nav.json` (SSOT): **6 Top-Punkte** —
Kommandocenter · Bots (Dropdown → `/dashboard`) · Strategy Lab · Research Library · Data Pipeline · Systemkarte.

- Kind-Links (`children`-Array) werden von `build_nav()` (build.py) als `.nav-drop`/`.nav-drop-menu` gerendert;
  CSS in `assets/base.css` (Hover/Focus; ≤980 px ohne Dropdown, Scroll-Nav).
- Live-Punkt + MULTI-Chip gelten auch für Kind-Links; Eltern-Link bekommt `aria-current`, wenn ein Kind aktiv ist.

## Content-Fragment-Format

```html
<!--TITLE:Seitenname — Hermes-->
<!--HEAD-->
<style>/* Seiten-spezifische Styles */</style>
<!--/HEAD-->
<!--BODY-->
<div class="container">
  <h1>Seitenname</h1>
  <p>Inhalt...</p>
</div>
<!--/BODY-->
```

**WICHTIG:** Kein `<main>` wrappen · kein `<header>/<nav>` hartcodieren · Theme-Toggle kommt aus dem Template ·
kein `_nav.js` laden (Navigation ist server-side gerendert).

## Seiten (Stand 2026-10-05)

| Seite | Zweck |
|---|---|
| `/` | Kommandocenter — Gesamtlage, Gates, Live/Shadow/Lab, Charts |
| `/dashboard` | Bots-Hub — Fleet-Übersicht (Sidebar generiert) + Sprung zu Bot #1–#10 |
| `/bot1` … `/bot10` | Bot-Dashboards (generiert; 5 Reiter je Seite) |
| `/strategy-lab` | Strategy Lab (4 Reiter: 🚀 / 🔬 / 👻 / 🧠) |
| `/research-library` | Konzept-Inspirationsquelle mit Lab-Provenance |
| `/data/` | Data Pipeline Status (stündlich) |
| `/assets/system-map/` | Systemkarte (+ Gesamtübersicht) |

**Archiviert** (aus Live-Build entfernt; Quellen unter `archive_legacy/content/`, Restore = zurückkopieren + build):
charts, report, strategies, smc, self-learning, bot (Reversal), bot1-guide, botleitfaden,
pages/knowledge, pages/projects, optimization/, backtest/, reports/, archive/.
Backup aller gelöschten Alt-Backups/Strays: `archive_legacy/backups_removed_2026-10-05.tar.gz`.

## CSS / Design

- Dark Theme (`var(--c-bg)`, `var(--c-surface)`), System-Font, keine externen Dependencies.
- Theme-Toggle Dark/Light via localStorage (im Base-Template).
- Shared CSS: `assets/base.css` (direkt editieren — keine Template-Kopie); Bot-CSS: `assets/bot.css` (Quelle in `src/templates/`).
