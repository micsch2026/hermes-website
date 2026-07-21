# Hermes Design System

> Single Source of Truth für alle visuellen und inhaltlichen Elemente.
> Jede Seite MUSS diese Komponenten verwenden — keine individuellen Styles mehr.

---

## 1. Farben (CSS Variablen)

```css
/* Semantic Colors */
--c-ok: #3fb950;           /* Erfolg, Gewinn, Aktiv */
--c-warn: #d29922;         /* Warnung, Vorsicht */
--c-err: #f85149;          /* Fehler, Verlust, Blocked */
--c-accent: #58a6ff;       /* Links, Highlights, Primary */
--c-info: #58a6ff;         /* Info, Hinweise */

/* Backgrounds */
--c-bg: #0d1117;           /* Page background */
--c-surface: #161b22;      /* Cards, Panels */
--c-surface-2: #21262d;    /* Hover states, secondary */
--c-border: #30363d;       /* Borders, Dividers */
--c-border-2: #484f58;     /* Hover borders */

/* Text */
--c-text: #e6edf3;         /* Primary text */
--c-text-dim: #8b949e;     /* Secondary, Labels */
--c-text-muted: #6e7681;   /* Tertiary, Disabled */
```

## 2. Icons

**NUR Lucide Icons.** Keine FontAwesome, keine SVG-Handarbeit.

```html
<i data-lucide="name" style="width:16px;height:16px;vertical-align:middle"></i>
```

**Standard-Größen:**
- Section-Titel: 16px
- Card-Titel: 14px  
- Inline/Text: 12px
- Buttons: 14px

## 3. Komponenten

### Card
```html
<div class="card">
  <div class="card-title">TITEL <i data-lucide="icon"></i></div>
  <div class="card-value">WERT</div>
  <div class="card-sub">Unterzeile</div>
</div>
```

### Metric Grid
```html
<div class="grid">
  <div class="card">...</div>
  <div class="card">...</div>
</div>
```

### Table
```html
<table>
  <thead><tr><th>COL1</th><th>COL2</th></tr></thead>
  <tbody><tr><td>val1</td><td>val2</td></tr></tbody>
</table>
```

### Progress Bar
```html
<div class="progress"><div class="progress-fill" style="width:XX%"></div></div>
```

### Badge
```html
<span class="badge badge-ok">AKTIV</span>
<span class="badge badge-warn">WARNUNG</span>
<span class="badge badge-err">BLOCKED</span>
<span class="badge badge-demo">DEMO</span>
```

### Status Dot
```html
<span class="status-dot green"></span>  <!-- OK -->
<span class="status-dot yellow"></span> <!-- Warn -->
<span class="status-dot red"></span>    <!-- Error -->
```

## 4. Layout-Konventionen

- **Container:** `.container` für max-width + padding
- **Grid:** `.grid` für auto-fit cards, `.grid-3` für 3-spaltig
- **Section-Titel:** `.section-title` mit Icon prefix
- **Abstände:** NUR CSS-Variablen (`--s-1` bis `--s-8`)

## 5. Charts (SVG-only)

Keine externen Chart-Libraries. Reines SVG + CSS:

- **Line:** `<path d="M...">` + `stroke`
- **Area:** Geschlossener Pfad + `<linearGradient>`
- **Bar:** Flex-Layout mit prozentualer Höhe
- **Donut:** `<circle>` mit `stroke-dasharray`
- **Gauge:** Halbkreis + `stroke-dasharray`

## 6. Responsive

- Mobile-first
- Breakpoint: 768px (Tablet/Desktop)
- Grid: `repeat(auto-fit, minmax(260px, 1fr))`

## 7. Content-First Regel

> Jeder Text, jede Zahl, jede Konfiguration kommt aus JSON.
> HTML-Templates enthalten NUR Layout-Logik.

Beispiel:
- ❌ `trading.html` hat hardcodierte "Balance", "Winrate"
- ✅ `content/trading/sections.json` definiert welche Metriken angezeigt werden
- ✅ Template rendert dynamisch aus JSON
