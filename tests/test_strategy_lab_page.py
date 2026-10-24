#!/usr/bin/env python3
"""Pflicht-Checks fuer /strategy-lab (Seed-Pipeline-Sektion, 24.10.2026)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
SRC = SITE / "src/content/strategy-lab.html"

REQUIRED_IDS = [
    "sl4-updated", "sl4-summary", "sl4-seed", "sl4-seed-updated",
    "sl4-seed-stats", "sl4-seed-families", "sl4-seed-note", "sl4-content",
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
    check("Fragment-Marker TITLE/HEAD/BODY",
          "<!--TITLE:" in text and "<!--HEAD-->" in text and "<!--/HEAD-->" in text
          and "<!--BODY-->" in text and "<!--/BODY-->" in text)

    p = IdCollector()
    p.feed(text)
    missing = [i for i in REQUIRED_IDS if i not in p.ids]
    check(f"Pflicht-IDs vorhanden ({len(REQUIRED_IDS)})", not missing, missing)

    scripts = re.findall(r"<script>(.*?)</script>", text, re.S)
    check("genau 1 inline-<script>", len(scripts) == 1, len(scripts))
    node = shutil.which("node")
    if scripts and node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, dir=str(SITE)) as fh:
            fh.write(scripts[0])
            tmp = fh.name
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        Path(tmp).unlink(missing_ok=True)
        check("node --check inline-JS", r.returncode == 0, r.stderr[-200:])
    else:
        check("node --check inline-JS", bool(node), "node nicht gefunden")

    out = SITE / "_build/strategy-lab.html"
    r = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import build; build.build_page('src/content/strategy-lab.html', '_build/strategy-lab.html')"],
        cwd=str(SITE), capture_output=True, text=True)
    ok = r.returncode == 0 and out.exists() and "sl4-seed" in out.read_text(encoding="utf-8")
    check("build_page-Smoke", ok, (r.stderr or r.stdout)[-200:])

    print()
    if fails:
        print(f"{len(fails)} FAIL: {fails}")
        return 1
    print("ALLE CHECKS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
