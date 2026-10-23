#!/usr/bin/env python3
"""Pflicht-Checks fuer die Seite /dashboard (src/content/dashboard.html).

Prueft: Fragment-Marker, Pflicht-IDs, inline-JS parst (node --check),
CSS-Variablen existieren in base.css (Fallback erlaubt), build_page-Smoke
(+ "db-matrix" im Output), NEGATIV-Strings (kein Alt-Launcher-Code).

Ausfuehrung: cd site && /usr/bin/python3 tests/test_dashboard_page.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
SRC = SITE / "src/content/dashboard.html"

REQUIRED_IDS = [
    "db-error", "db-status", "db-status-text", "db-links",
    "db-perf", "db-perf-demo", "db-perf-live", "db-perf-total",
    "db-tiles", "db-vt", "db-matrix",
    "db-dev", "db-risk", "db-meta",
    "db-live-accounts", "db-feed",
]

# Single-Home-Regel (23.10.2026): Findings/Shadow/Missionen nicht auf /dashboard
FORBIDDEN_IDS = ["db-actions", "db-actions-list", "db-actions-more",
                 "db-shadow", "db-missions"]

# Alt-Launcher-Reste, die auf der neuen Seite NICHT mehr vorkommen duerfen
FORBIDDEN = ["generate_home_sidebar", "quick-link", "v0.21.5", "mimo-v2.5"]

fails = []


def check(name, ok, detail=None):
    if detail is None:
        detail = ""
    print(("PASS " if ok else "FAIL ") + name + ((" — " + str(detail)) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids.add(v)


def main() -> int:
    text = SRC.read_text(encoding="utf-8")

    # 1) Fragment-Marker
    check("Fragment-Marker TITLE/HEAD/BODY",
          "<!--TITLE:" in text and "<!--HEAD-->" in text and "<!--/HEAD-->" in text
          and "<!--BODY-->" in text and "<!--/BODY-->" in text)

    # 2) Pflicht-IDs
    p = IdCollector()
    p.feed(text)
    missing = [i for i in REQUIRED_IDS if i not in p.ids]
    check(f"Pflicht-IDs vorhanden ({len(REQUIRED_IDS)})", not missing, missing)
    left = [i for i in FORBIDDEN_IDS if i in p.ids]
    check("Single-Home: keine gedoppelten Blöcke", not left, left)

    # 3) Inline-JS parst (node --check)
    scripts = re.findall(r"<script>(.*?)</script>", text, re.S)
    check("genau 1 inline-<script>", len(scripts) == 1, len(scripts))

    # 3b) Kachel-Ansicht (v3, 16.10.2026): Renderer, Umschalter, Gruppen
    check("Kachel-Renderer + Umschalter vorhanden",
          "renderTiles" in text and "dbFleetView" in text
          and "▦ Kacheln" in text and "▤ Tabelle" in text)
    check("Kachel-Gruppen (LIVE/SPLIT/DEMO) vorhanden",
          "LIVE — ECHTGELD" in text and "LIVE + DEMO-SPLIT" in text
          and "DEMO — PROMOTION-PIPELINE" in text)
    # 3b2) Bot-Tag-Fallback: Bots ohne deployte Strategie zeigen ihren
    # bot_overrides-Tag (tileSpark/db-t-strat + Matrix), nicht '—' (17.10.2026)
    check("Kachel/Tabelle: Bot-Tag-Fallback ohne deployte Strategie",
          "tag ? esc(tag) : '—'" in text)

    # 3c) v4 (16.10.2026): Zwei-Kurven (Demo+Echtgeld) + absoluter Echtgeld-G/V
    check("v4/v5: Zwei-Kurven + Absolut-G/V vorhanden",
          "live_curve" in text and "db-t-rows" in text and "tileSpark" in text
          and "tileBalances" in text and "abs_pnl" in text and "seit Einzahlung" in text)

    # 3d) v6 (18.10.2026): LIVE-Bot mit Demo-Seite (bot9) — zweite Kachel-Zeile
    check("v6: Demo-Seiten-Zeile + Badge (demo_acct) vorhanden",
          "demo_acct" in text and "demo_balance" in text and "demo_curve" in text
          and "DEMO-SEITE" in text and "Demo-Seite" in text)

    node = shutil.which("node")
    if scripts and node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         dir=str(SITE)) as fh:
            fh.write(scripts[0])
            tmp = fh.name
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        Path(tmp).unlink(missing_ok=True)
        check("node --check inline-JS", r.returncode == 0, r.stderr[-200:])
    else:
        check("node --check inline-JS", bool(node), "node nicht gefunden")

    # 4) CSS-Variablen (Fallback erlaubt)
    base = (SITE / "assets/base.css").read_text(encoding="utf-8")
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", base))
    used = re.findall(r"var\((--[a-z0-9-]+)\s*(,[^)]*)?\)", text)
    bad = [v for v, fb in used if v not in defined and not fb]
    check("CSS-Variablen definiert oder Fallback", not bad, bad)

    # 5) build_page-Smoke (Einzel-Smoke, kein Voll-Build)
    out = SITE / "_build/dashboard.html"
    r = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import build; build.build_page('src/content/dashboard.html', '_build/dashboard.html')"],
        cwd=str(SITE), capture_output=True, text=True)
    ok = r.returncode == 0 and out.exists() and "db-matrix" in out.read_text(encoding="utf-8")
    if ok:
        out_text = out.read_text(encoding="utf-8")
        ok = "db-tiles" in out_text and "renderTiles" in out_text
    check("build_page-Smoke enthält db-matrix + db-tiles", ok, (r.stderr or r.stdout)[-200:])

    # 6) NEGATIV: keine Alt-Launcher-/Versions-Reste
    present = [s for s in FORBIDDEN if s in text]
    check("keine Alt-Reste (generate_home_sidebar/quick-link/v0.21.5/mimo-v2.5)",
          not present, present)

    print()
    if fails:
        print(f"{len(fails)} FAIL: {fails}")
        return 1
    print("ALLE CHECKS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
