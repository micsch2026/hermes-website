#!/usr/bin/env python3
"""
test_overview_page.py — Struktur-/Build-Tests fuer src/content/overview.html
(System-Kommandocenter, /overview). Rein stdlib.

Run:  python3 tests/test_overview_page.py   → alle PASS / exit 1 bei FAIL
"""
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
sys.path.insert(0, SITE)

SRC = os.path.join(SITE, "src", "content", "overview.html")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


class IdCollector(HTMLParser):
    """Sammelt alle id="..." Attribute aus dem statischen HTML."""
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids.add(v)


def extract_blocks(raw, start, end):
    out = []
    pos = 0
    while True:
        i = raw.find(start, pos)
        if i < 0:
            break
        j = raw.find(end, i + len(start))
        if j < 0:
            break
        out.append(raw[i + len(start):j])
        pos = j + len(end)
    return out


def main():
    raw = open(SRC, encoding="utf-8").read()

    # ── 1. Pflicht-IDs im statischen HTML ──────────────────────
    p = IdCollector()
    p.feed(raw)
    ids = p.ids

    required = [
        # container + hero
        "overview-page", "hero", "hero-amp", "hero-headline", "hero-why", "data-age",
        # komponenten
        "verdict-components", "comp-lab", "comp-shadow", "comp-demo_live", "comp-risk", "comp-data",
        # findings
        "findings",
        # live/demo
        "live-block", "live-kpis", "fleet-table",
        # shadow
        "shadow-block", "shadow-kpis", "shadow-ranking", "shadow-decay",
        "shadow-challenges", "shadow-rotation",
        # lab
        "lab-block", "lab-worker", "lab-queue", "lab-7d",
        # charts
        "charts-block", "chart-equity", "chart-monthly", "chart-corr", "chart-tca", "chart-exposure",
        # quellen
        "sources",
    ]
    missing = [i for i in required if i not in ids]
    check(f"pflicht-ids ({len(required)} stueck, alle statisch)", not missing,
          f"fehlend: {missing}")

    # ── 2. Charts: genau 5 pending-Container, keine Chart-Lib ──
    pending = re.findall(r'data-status="pending"', raw)
    check("genau 5 data-status='pending'-Container", len(pending) == 5, f"gefunden: {len(pending)}")

    chart_libs = [
        "lightweight-charts", "lightweightcharts", "apexcharts", "chart.js",
        "chartjs", "highcharts", "echarts", "plotly", "d3js", "cdn.jsdelivr",
        "unpkg.com", "cdnjs.cloudflare",
    ]
    low = raw.lower()
    hit = [c for c in chart_libs if c in low]
    check("keine Chart-Bibliothek / kein CDN", not hit, f"treffer: {hit}")
    check("kein <script src", "<script src" not in low)

    # ── 3. Jeder inline <script>-Block: node --check ───────────
    scripts = extract_blocks(raw, "<script", "</script>")
    scripts = [s.split(">", 1)[1] if ">" in s else s for s in scripts]
    check("mind. 1 inline <script>-Block vorhanden", len(scripts) >= 1, f"gefunden: {len(scripts)}")

    node = "/usr/local/bin/node"
    if not os.path.exists(node):
        node = "node"
    all_ok = True
    for i, body in enumerate(scripts):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
            tf.write(body)
            tmp = tf.name
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        os.unlink(tmp)
        ok = r.returncode == 0
        all_ok = all_ok and ok
        check(f"node --check script-block #{i + 1}", ok, r.stderr.strip()[:200])
    check("fetch auf /api/overview/overview.json (absolut, mit Slash)",
          "fetch(API" in raw and "'/api/overview/overview.json'" in raw)
    check("setInterval 60 s Reload", "setInterval" in raw and "60000" in raw)

    # ── 4. build_page-Smoke ────────────────────────────────────
    import build  # site/build.py

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "overview.html")
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            build.build_page(os.path.relpath(SRC, SITE), out)
        stdout = buf.getvalue()
        built = open(out, encoding="utf-8").read()

    check("build_page rc 0 + 'Built ...' auf stdout",
          f"overview.html" in stdout and "Built" in stdout, stdout.strip()[:200])
    check("Build-Output enthaelt id=\"hero-amp\"", 'id="hero-amp"' in built)
    check("Build-Output enthaelt overview.json", "overview.json" in built)
    check("Build-Output ohne unersetzte '{{'", "{{" not in built)
    n_auto = built.count("AUTO-GENERATED")
    check("genau 1 AUTO-GENERATED-Marker (kein Doppel)", n_auto == 1, f"count: {n_auto}")

    # ── 5. HEAD-Style nutzt Design-System-Variablen ────────────
    head = extract_blocks(raw, "<!--HEAD-->", "<!--/HEAD-->")[0]
    css_vars = set(re.findall(r"var\((--c-[a-z0-9-]+)", head))
    check("HEAD-Style nutzt mind. 4 verschiedene var(--c-*)-Variablen",
          len(css_vars) >= 4, f"gefunden: {sorted(css_vars)}")
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", head)
    check("keine vollstaendigen Hex-Theme-Werte im HEAD (nur Alpha-Overlays)",
          len(hexes) == 0, f"hex: {hexes}")

    # ── 6. Keine Reste ─────────────────────────────────────────
    for token in ("TODO", "FIXME", "lorem"):
        check(f"keine '{token}'-Reste", token.lower() not in low)

    print(f"\n{'=' * 60}")
    print(f"RESULT: {PASS} PASS, {FAIL} FAIL")
    print(f"{'=' * 60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
