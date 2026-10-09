#!/usr/bin/env python3
"""Pflicht-Checks fuer die Seite /missions (src/content/missions.html).

Prueft: Fragment-Marker, Pflicht-IDs, inline-JS parst (node --check),
CSS-Variablen existieren in base.css (Fallback erlaubt), build_page-Smoke.

Ausfuehrung: cd site && /usr/bin/python3 tests/test_missions_page.py
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
SRC = SITE / "src/content/missions.html"

REQUIRED_IDS = [
    "mi-meta", "mi-error", "mi-kpis",
    "mi-next-run", "mi-next-run-note",
    "mi-active", "mi-active-count",
    "mi-proposed", "mi-proposed-count",
    "mi-done", "mi-done-count",
    "mi-proposals", "mi-proposals-count",
    "mi-sources",
]

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

    # 3) Inline-JS parst (node --check)
    scripts = re.findall(r"<script>(.*?)</script>", text, re.S)
    check("genau 1 inline-<script>", len(scripts) == 1, len(scripts))
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
    out = SITE / "_build/missions.html"
    r = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import build; build.build_page('src/content/missions.html', '_build/missions.html')"],
        cwd=str(SITE), capture_output=True, text=True)
    ok = r.returncode == 0 and out.exists() and "mi-kpis" in out.read_text(encoding="utf-8")
    check("build_page-Smoke", ok, (r.stderr or r.stdout)[-200:])

    print()
    if fails:
        print(f"{len(fails)} FAIL: {fails}")
        return 1
    print("ALLE CHECKS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
