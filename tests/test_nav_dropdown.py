#!/usr/bin/env python3
"""Tests fuer das Bots-Dropdown in der Top-Nav (Klick-Toggle + Mobile).

Prueft die gemeinsamen Bausteine (base.html-Script, base.css-Regeln,
nav.json-Struktur) sowie die gebauten Seiten in _build/ (Marker-Scan).
"""
import json
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


css = (SITE / "assets" / "base.css").read_text()
check("base.css: .nav-drop.open-Regel vorhanden",
      ".nav-drop.open .nav-drop-menu" in css)
check("base.css: keine !important-Sperre mehr (Mobile)",
      "display: none !important" not in css)
check("base.css: Mobile-Menue position:fixed",
      "position: fixed; top: 58px" in css)

tpl = (SITE / "src" / "templates" / "base.html").read_text()
check("base.html: Klick-Toggle-Script",
      "Klick-Toggle" in tpl and "classList.toggle('open'" in tpl)

nav = json.loads((SITE / "src" / "data" / "nav.json").read_text())
bots = next(l for l in nav["links"] if l["label"] == "Bots")
check("nav.json: Bots-Kind-Links = 11 (Hub + 10)", len(bots["children"]) == 11)
check("nav.json: erster Kind = /dashboard (Bots-Hub)",
      bots["children"][0]["href"] == "/dashboard")

for page in ("index.html", "supervisor.html", "dashboard.html", "bot1.html"):
    fb = SITE / "_build" / page
    if fb.exists():
        html = fb.read_text()
        check(f"_build/{page}: Toggle-Script vorhanden",
              "classList.toggle('open'" in html)
        check(f"_build/{page}: Bots-Hub-Eintrag", "Bots-Hub" in html)

print("NAV-DROPDOWN TESTS " + ("OK" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
