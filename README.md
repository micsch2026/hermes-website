# Hermes Website — Struktur

## Architektur (Template-basiert, Atomic Design)

Das Website-System ist **datengetrieben** und wird per Build-Script generiert.

```
/root/.hermes/site/
├── src/
│   ├── data/
│   │   └── nav.json              ← Single Source of Truth (Navigation)
│   ├── templates/
│   │   └── base.html             ← Base-Template (Atomic Design: Template-Ebene)
│   └── content/                  ← Content-Fragmente pro Seite
│       ├── index.html
│       ├── trading.html
│       ├── bot.html
│       ├── depot.html
│       ├── report.html
│       └── pages/
│           ├── notes.html
│           ├── projects.html
│           ├── knowledge.html
│           └── system.html
├── build.py                      ← Generator-Script
├── assets/
└── api/                          ← JSON-Endpunkte (public)
```

**Atomic Design Ebenen:**
- **Atom:** Nav-Link (aus `nav.json` generiert)
- **Molekuel:** `<nav>` (aus Atomen + Theme-Toggle)
- **Organismus:** `<header>` (Nav + Inline Theme-Script)
- **Template:** `base.html` (HTML-Geruest mit Platzhaltern)
- **Page:** Generierte `.html` Dateien im Root

## Build-Prozess

```bash
cd /root/.hermes/site && python3 build.py
```

Dies generiert aus `src/content/*.html` + `src/templates/base.html` + `src/data/nav.json` alle statischen HTML-Dateien. Die Navigation ist **server-side gerendert** — kein JS-Replacement mehr, kein FOUC.

## Neue Seite hinzufuegen

1. Content-Fragment unter `src/content/` (oder `src/content/pages/`) anlegen
2. Optional: `src/data/nav.json` erweitern
3. `python3 build.py` laufen lassen
4. Fertig

## Content-Fragment Format

```html
<!--TITLE:Seitenname — Hermes-->
<!--HEAD-->
<style>
  /* Seiten-spezifische Styles */
</style>
<!--/HEAD-->
<!--BODY-->
<div class="container">
  <h1>Seitenname</h1>
  <p>Inhalt...</p>
</div>
<!--/BODY-->
```

**WICHTIG:**
- Kein `<main>` wrappen — Template macht das
- Kein `<header>` oder `<nav>` hartcodieren
- Kein Theme-Toggle-Script einbauen — ist im Template
- Kein `_nav.js` laden — Navigation ist server-side

## Seiten-Zweck

| Seite | Zweck |
|-------|-------|
| `index.html` | Dashboard — Uebersicht, Status, Quick Links |
| `trading.html` | Trading-Uebersicht — Pipeline, Marktdaten |
| `bot.html` | Trading Bot — Status, Entscheidungen, Log |
| `depot.html` | Depot-Verwaltung — Positionen, P&L, Editieren |
| `report.html` | Trading Report — Kimi-Analyse, Kennzahlen |
| `pages/notes.html` | Persoenliche Notizen — Stichpunkte, To-Dos |
| `pages/projects.html` | Projekte & Status |
| `pages/knowledge.html` | Wissensbasis — Fakten, Recherche, Referenzen |
| `pages/system.html` | Server- & System-Status |

## CSS / Design

- Dark Theme (var(--c-bg) background, var(--c-surface) cards)
- Font: System-Stack
- Keine externen Dependencies
- Theme-Toggle: Dark/Light via localStorage
